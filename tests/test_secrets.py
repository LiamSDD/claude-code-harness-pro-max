import os
import tempfile
import unittest

from helpers import FAKE_ANTHROPIC, FAKE_AWS_ID, FAKE_GITHUB, FAKE_PRIVATE_KEY, FAKE_STRIPE, fake

from agentharness import secrets


class DetectorTests(unittest.TestCase):
    def ids(self, text, **kw):
        return [f.detector for f in secrets.scan_text(text, **kw)]

    def test_provider_tokens(self):
        self.assertEqual(self.ids(f"token={FAKE_GITHUB}"), ["github-token"])
        self.assertEqual(self.ids(FAKE_ANTHROPIC), ["anthropic-api-key"])
        self.assertEqual(self.ids(f"id: {FAKE_AWS_ID}"), ["aws-access-key-id"])
        self.assertEqual(self.ids(FAKE_STRIPE), ["stripe-live-key"])
        self.assertEqual(self.ids(FAKE_PRIVATE_KEY), ["private-key"])
        self.assertIn("openai-api-key", self.ids(fake("sk-", "proj-", "Q" * 20, "w" * 30)))
        self.assertIn("google-api-key", self.ids(fake("AI", "za", "Sy" + "A1b2C3d4E5" * 3 + "xYz")))
        self.assertIn("slack-token", self.ids(fake("xo", "xb-", "8472619035-Qm7Rt2Lp9Xv4")))

    def test_connection_string(self):
        self.assertEqual(self.ids("postgres://app:s3cr3tP4ss@db:5432/x"), ["connection-string-password"])

    def test_generic_assignment_needs_entropy(self):
        self.assertEqual(self.ids('api_key = "Zq8#pL2mVx9!rT4w"'), ["generic-assignment"])
        self.assertEqual(self.ids('password = "passwordpassword"'), [])
        self.assertEqual(self.ids('token = "/usr/local/share/tokens/x.txt"'), [])

    def test_placeholders_are_ignored(self):
        for text in (
            'API_KEY = "your-api-key-here"',
            'aws_access_key_id = "AKIAIOSFODNN7EXAMPLE"',
            'token = "${GITHUB_TOKEN}"',
            'secret = "<replace-me-with-secret>"',
            'key = os.environ["OPENAI_API_KEY"]',
            'password = "xxxxxxxxxxxxxxxx"',
        ):
            with self.subTest(text=text):
                self.assertEqual(self.ids(text), [])

    def test_allow_patterns(self):
        self.assertEqual(self.ids(FAKE_GITHUB, allow_patterns=["A1b2C3d4"]), [])

    def test_line_and_column(self):
        f = secrets.scan_text(f"first\nsecond {FAKE_GITHUB}\n")[0]
        self.assertEqual((f.line, f.column), (2, 8))

    def test_preview_never_contains_secret(self):
        f = secrets.scan_text(FAKE_ANTHROPIC)[0]
        self.assertNotIn(FAKE_ANTHROPIC[8:], f.preview)
        self.assertTrue(f.preview.startswith("sk-a"))

    def test_high_only(self):
        self.assertEqual(self.ids("postgres://u:s3cr3tP4ss@h/db", min_confidence=secrets.HIGH), [])


class RedactionTests(unittest.TestCase):
    def test_redact_text(self):
        out = secrets.redact_text(f"curl -H 'Authorization: token {FAKE_GITHUB}' x")
        self.assertNotIn(FAKE_GITHUB, out)
        self.assertIn("[REDACTED:github-token]", out)

    def test_truncation(self):
        self.assertEqual(len(secrets.redact_text("a" * 100, max_len=10)), 10)

    def test_entropy(self):
        self.assertLess(secrets.shannon_entropy("aaaa"), 0.1)
        self.assertGreater(secrets.shannon_entropy("aZ3$kP9!"), 2.9)


class FileScanTests(unittest.TestCase):
    def test_scan_directory_skips_binary_and_vendor(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "config.py"), "w") as fh:
                fh.write(f"TOKEN = '{FAKE_GITHUB}'\n")
            with open(os.path.join(d, "image.bin"), "wb") as fh:
                fh.write(b"\x00\x01" + FAKE_GITHUB.encode())
            os.makedirs(os.path.join(d, "node_modules", "x"))
            with open(os.path.join(d, "node_modules", "x", "a.js"), "w") as fh:
                fh.write(FAKE_GITHUB)
            found = [f for p in secrets.iter_files([d]) for f in secrets.scan_file(p)]
            self.assertEqual(len(found), 1)
            self.assertTrue(found[0].path.endswith("config.py"))


if __name__ == "__main__":
    unittest.main()
