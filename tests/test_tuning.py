import json
import os

from helpers import ProjectTestCase

from harnesspro import tuning

DOC = "\n".join(
    ["# Hooks reference", "## Configuration", "### Timeouts"]
    + [f"### {e}" for e in sorted((tuning.HANDLED | {"WorktreeCreate", "Setup", "BrandNewHook"}) - {"InstructionsLoaded"})]
)


class UpstreamTests(ProjectTestCase):
    git = False

    def test_documented_events_ignore_section_headings(self):
        events = tuning.documented_events(DOC)
        self.assertIn("BrandNewHook", events)
        self.assertIn("Setup", events)
        self.assertNotIn("Configuration", events)
        self.assertNotIn("Timeouts", events)

    def test_report(self):
        new, skipped, missing = tuning.upstream_report(DOC)
        self.assertEqual(new, ["BrandNewHook"])
        self.assertIn("WorktreeCreate", skipped)
        self.assertEqual(missing, ["InstructionsLoaded"])

    def test_register_events_is_idempotent(self):
        f = self.write("hooks.json", json.dumps({"hooks": {"Stop": []}}))
        self.assertEqual(tuning.register_events(f, ["BrandNewHook", "Stop"], "harness"), ["BrandNewHook"])
        self.assertEqual(tuning.register_events(f, ["BrandNewHook"], "harness"), [])
        data = self.read_json("hooks.json")
        self.assertEqual(data["hooks"]["BrandNewHook"][0]["hooks"][0]["command"], "harness hook BrandNewHook")

    def test_cli_with_file(self):
        doc = self.write("hooks.md", DOC)
        r = self.cli("upstream", "--file", doc)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("BrandNewHook", r.stdout)
        self.assertEqual(self.cli("upstream", "--file", self.write("empty.md", "# nothing")).returncode, 2)

    def test_only_https(self):
        with self.assertRaises(OSError):
            tuning.fetch_doc("file:///etc/passwd")


class OptimizeTests(ProjectTestCase):
    git = False

    def test_preview_then_apply_then_idempotent(self):
        changes = tuning.optimize(self.project, "balanced")
        self.assertTrue(any("BASH_MAX_OUTPUT_LENGTH" in c for c in changes))
        self.assertFalse(os.path.exists(self.path(".claude", "settings.json")))
        tuning.optimize(self.project, "balanced", budget=5, apply=True)
        settings = self.read_json(".claude", "settings.json")
        self.assertEqual(settings["env"]["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"], "6")
        self.assertIn("Read(./**/node_modules/**)", settings["permissions"]["deny"])
        policy = self.read_json(".claude", "harness", "policy.json")
        self.assertEqual(policy["cost"]["session_budget_usd"], 5.0)
        self.assertEqual(policy["subagents"]["models"]["Explore"], "haiku")
        self.assertEqual(tuning.optimize(self.project, "balanced", budget=5), [])

    def test_existing_values_are_kept(self):
        self.write(".claude/settings.json", json.dumps({"env": {"BASH_MAX_OUTPUT_LENGTH": "50000"}}))
        changes = tuning.optimize(self.project, "lean", apply=True)
        self.assertTrue(any("kept at 50000" in c for c in changes))
        self.assertEqual(self.read_json(".claude", "settings.json")["env"]["BASH_MAX_OUTPUT_LENGTH"], "50000")

    def test_cli(self):
        r = self.cli("optimize", "--profile", "lean")
        self.assertIn("Would apply", r.stdout)
        r = self.cli("cost")
        self.assertEqual(r.returncode, 1)
