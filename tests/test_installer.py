import json
import os
import unittest

from helpers import ProjectTestCase

from harnesspro import installer, settings_merge


class MergeTests(unittest.TestCase):
    def test_existing_hooks_are_kept_and_not_duplicated(self):
        existing = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}]}, "model": "opus"}
        frag = installer.settings_fragment("standard", "harness")
        merged, changes = settings_merge.merge_settings(existing, frag)
        cmds = [h["command"] for g in merged["hooks"]["PreToolUse"] for h in g["hooks"]]
        self.assertIn("mine.sh", cmds)
        self.assertIn("harness hook PreToolUse", cmds)
        self.assertEqual(merged["model"], "opus")
        again, changes2 = settings_merge.merge_settings(merged, frag)
        self.assertEqual(again, merged)
        self.assertEqual(changes2, [])

    def test_existing_statusline_kept_unless_forced(self):
        frag = installer.settings_fragment("standard", "harness")
        merged, _ = settings_merge.merge_settings({"statusLine": {"type": "command", "command": "mine"}}, frag)
        self.assertEqual(merged["statusLine"]["command"], "mine")
        merged, _ = settings_merge.merge_settings({"statusLine": {"type": "command", "command": "mine"}}, frag, force=True)
        self.assertEqual(merged["statusLine"]["command"], "harness statusline")

    def test_permissions_union(self):
        merged, _ = settings_merge.merge_permissions(
            {"allow": ["Bash(ls)"], "defaultMode": "plan"}, {"allow": ["Bash(ls)", "Bash(pwd)"], "deny": ["Read(./.env)"]}
        )
        self.assertEqual(merged["allow"], ["Bash(ls)", "Bash(pwd)"])
        self.assertEqual(merged["deny"], ["Read(./.env)"])
        self.assertEqual(merged["defaultMode"], "plan")


class InitTests(ProjectTestCase):
    def test_standard_init(self):
        self.write("package.json", json.dumps({"scripts": {"test": "vitest run"}}))
        report = installer.init_project(self.project, "standard", hook_command="harness")
        settings = self.read_json(".claude", "settings.json")
        self.assertIn("Stop", settings["hooks"])
        self.assertEqual(settings["statusLine"]["command"], "harness statusline")
        policy = self.read_json(".claude", "harness", "policy.json")
        self.assertEqual(policy["stop_gate"], {"enabled": False, "command": "npm test"})
        for f in ("CLAUDE.md", ".claude/agents/evaluator.md", ".claude/skills/feature-loop/SKILL.md", ".claude/harness/.gitignore"):
            self.assertTrue(os.path.exists(self.path(f)), f)
        self.assertIn("npm test", self.read("CLAUDE.md"))
        self.assertTrue(report.created)

    def test_idempotent_and_non_destructive(self):
        self.write("CLAUDE.md", "# mine\n")
        installer.init_project(self.project, "standard", hook_command="harness")
        before = self.read(".claude", "settings.json")
        report = installer.init_project(self.project, "standard", hook_command="harness")
        self.assertEqual(self.read(".claude", "settings.json"), before)
        self.assertEqual(report.created, [])
        self.assertEqual(self.read("CLAUDE.md"), "# mine\n")

    def test_minimal_and_strict(self):
        installer.init_project(self.project, "minimal", hook_command="harness", with_agents=False)
        s = self.read_json(".claude", "settings.json")
        self.assertNotIn("Stop", s["hooks"])
        self.assertFalse(os.path.exists(self.path(".claude", "agents")))

    def test_strict_enables_gate(self):
        self.write("Makefile", "test:\n\tpytest\n")
        installer.init_project(self.project, "strict", hook_command="harness")
        policy = self.read_json(".claude", "harness", "policy.json")
        self.assertEqual(policy["stop_gate"], {"enabled": True, "command": "make test"})
        self.assertEqual(policy["fail_mode"], "closed")

    def test_dry_run_writes_nothing(self):
        installer.init_project(self.project, "standard", hook_command="harness", dry_run=True)
        self.assertFalse(os.path.exists(self.path(".claude")))

    def test_detect_test_command(self):
        self.assertIsNone(installer.detect_test_command(self.project))
        self.write("go.mod", "module x\n")
        self.assertEqual(installer.detect_test_command(self.project), "go test ./...")


if __name__ == "__main__":
    unittest.main()
