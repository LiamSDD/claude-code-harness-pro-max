import json
import os
import unittest

from helpers import ProjectTestCase

from harnesspro.config import PolicyError, load_defaults, load_policy, merge, validate
from harnesspro.pathmatch import PathMatcher, glob_to_regex


class MergeTests(unittest.TestCase):
    def test_lists_append_without_duplicates(self):
        self.assertEqual(merge({"a": [1, 2]}, {"a": [2, 3]}), {"a": [1, 2, 3]})

    def test_bang_replaces(self):
        self.assertEqual(merge({"a": [1, 2]}, {"a!": [9]}), {"a": [9]})

    def test_nested_and_scalars(self):
        self.assertEqual(merge({"x": {"y": 1, "z": 2}}, {"x": {"y": 5}}), {"x": {"y": 5, "z": 2}})

    def test_comments_ignored(self):
        self.assertEqual(merge({}, {"$comment": "hi", "a": 1}), {"a": 1})


class ValidateTests(unittest.TestCase):
    def test_defaults_are_valid(self):
        self.assertEqual(validate(load_defaults()), [])

    def test_errors(self):
        errs = validate({"mode": "loud", "paths": {"deny_read": "x"}, "bogus": 1})
        self.assertTrue(any("mode" in e for e in errs))
        self.assertTrue(any("deny_read" in e for e in errs))
        self.assertTrue(any("bogus" in e for e in errs))

    def test_rule_validation(self):
        errs = validate({"bash": {"rules": [{"id": "x", "pattern": "(", "decision": "allow"}]}})
        self.assertTrue(any("decision" in e for e in errs))
        self.assertTrue(any("regex" in e for e in errs))

    def test_formatter_needs_file_placeholder(self):
        errs = validate({"post_edit": {"formatters": [{"glob": "*.py", "command": "ruff format"}]}})
        self.assertTrue(any("{file}" in e for e in errs))

    def test_bool_is_not_int(self):
        self.assertTrue(validate({"stop_gate": {"timeout": True}}))


class LayerTests(ProjectTestCase):
    git = False

    def test_layers_in_order(self):
        user = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "harness", "policy.json")
        os.makedirs(os.path.dirname(user))
        with open(user, "w") as fh:
            json.dump({"bash": {"sudo": "deny"}, "disable": ["a"]}, fh)
        self.write_policy({"bash": {"sudo": "allow"}, "disable": ["b"]})
        self.write_policy({"mode": "warn"}, name="policy.local.json")
        p = load_policy(self.project)
        self.assertEqual(p.get("bash.sudo"), "allow")
        self.assertEqual(p.data["disable"], ["a", "b"])
        self.assertEqual(p.mode, "warn")
        self.assertEqual(len(p.sources), 4)

    def test_env_layer(self):
        path = self.write("custom.json", json.dumps({"mode": "off"}))
        os.environ["HARNESS_POLICY"] = path
        self.assertEqual(load_policy(self.project).mode, "off")

    def test_broken_layer_is_skipped_and_reported(self):
        self.write(".claude/harness/policy.json", "{not json")
        p = load_policy(self.project)
        self.assertEqual(p.mode, "enforce")
        self.assertEqual(len(p.errors), 1)
        with self.assertRaises(PolicyError):
            load_policy(self.project, strict=True)

    def test_invalid_layer_is_skipped(self):
        self.write_policy({"mode": "nope"})
        p = load_policy(self.project)
        self.assertEqual(p.mode, "enforce")
        self.assertIn("mode", p.errors[0])


class PathMatchTests(unittest.TestCase):
    def test_glob_regex(self):
        self.assertTrue(glob_to_regex("**/.ssh/**").match("a/b/.ssh/id"))
        self.assertTrue(glob_to_regex("**/.ssh/**").match(".ssh/id"))
        self.assertTrue(glob_to_regex("*.pem").match("x.pem"))
        self.assertFalse(glob_to_regex("*.pem").match("a/x.pem"))
        self.assertTrue(glob_to_regex("id_[re]*").match("id_rsa"))

    def test_last_match_wins(self):
        m = PathMatcher([".env.*", "!.env.example"])
        self.assertTrue(m.matches("/p/.env.local", "/p"))
        self.assertFalse(m.matches("/p/.env.example", "/p"))

    def test_relative_and_absolute(self):
        m = PathMatcher([".github/workflows/**", "/etc/**", "~/.aws/**"], home="/home/u")
        self.assertTrue(m.matches("/p/.github/workflows/ci.yml", "/p"))
        self.assertFalse(m.matches("/other/.github/workflows/ci.yml", "/p"))
        self.assertTrue(m.matches("/etc/hosts", "/p"))
        self.assertTrue(m.matches("/home/u/.aws/credentials", "/p"))


if __name__ == "__main__":
    unittest.main()
