import json
import os

from helpers import ProjectTestCase

from harnesspro import limits
from harnesspro.config import load_policy


class LimitsCommandTests(ProjectTestCase):
    git = False

    def test_set_show_reset_roundtrip(self):
        changes = limits.set_limits(
            self.project, [("output.max-words", "120"), ("output.min-words", "10"), ("output.max-tokens", "4000"), ("effort", "low")]
        )
        self.assertEqual(len(changes), 4)
        settings = self.read_json(".claude", "settings.local.json")
        self.assertEqual(settings["env"], {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "4000", "CLAUDE_CODE_EFFORT_LEVEL": "low"})
        policy = self.read_json(".claude", "harness", "policy.local.json")
        self.assertEqual(policy["limits"]["output"], {"max_words": 120, "min_words": 10})
        rows = {r["key"]: r for r in limits.table(self.project)}
        self.assertEqual((rows["output.max-words"]["value"], rows["output.max-words"]["source"]), (120, "local"))
        self.assertIsNone(rows["input.max-chars"]["value"])
        self.assertEqual(limits.reset_limits(self.project, ["output"]), ["output.max-tokens", "output.max-words", "output.min-words"])
        self.assertEqual(limits.reset_limits(self.project, ["all"]), ["effort"])
        self.assertFalse(os.path.exists(self.path(".claude", "settings.local.json")))
        self.assertFalse(os.path.exists(self.path(".claude", "harness", "policy.local.json")))

    def test_existing_settings_are_preserved(self):
        self.write(".claude/settings.local.json", json.dumps({"permissions": {"allow": ["Bash(ls)"]}}))
        limits.set_limits(self.project, [("turns.max", "30")])
        limits.reset_limits(self.project, ["turns.max"])
        self.assertEqual(self.read_json(".claude", "settings.local.json"), {"permissions": {"allow": ["Bash(ls)"]}})

    def test_validation(self):
        for key, value in (
            ("output.max-words", "0"),
            ("output.max-words", "many"),
            ("effort", "extreme"),
            ("output.max-tokens", "999999"),
            ("budget", "-2"),
            ("thinking", "maybe"),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                limits.set_limits(self.project, [(key, value)])
        with self.assertRaises(KeyError):
            limits.set_limits(self.project, [("output.maximum", "5")])
        limits.set_limits(self.project, [("output.max-words", "100")])
        with self.assertRaises(ValueError):
            limits.set_limits(self.project, [("output.min-words", "200")])

    def test_aliases_and_scopes(self):
        limits.set_limits(self.project, [("budget", "$7.5")], scope="shared")
        self.assertEqual(self.read_json(".claude", "harness", "policy.json")["cost"]["session_budget_usd"], 7.5)
        limits.set_limits(self.project, [("model", "sonnet")], scope="user")
        user_settings = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "settings.json")
        with open(user_settings) as fh:
            self.assertEqual(json.load(fh)["model"], "sonnet")
        self.assertEqual(limits.current_value(self.project, "model"), "sonnet")
        limits.set_limits(self.project, [("subagents.max-concurrent", "3")])
        self.assertEqual(load_policy(self.project).get("subagents.max_concurrent"), 3)
        self.assertEqual(self.read_json(".claude", "settings.local.json")["env"]["CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS"], "3")
        limits.set_limits(self.project, [("thinking", "off")])
        self.assertIn("off", limits.render(limits.table(self.project), only_set=True))

    def test_cli(self):
        r = self.cli("limits", "output", "--max-words", "80", "--max-tokens", "2000")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("new session", r.stdout)
        r = self.cli("limits", "input", "--max-chars", "300")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.cli("limits", "show", "--set-only")
        self.assertIn("output.max-words", r.stdout)
        self.assertIn("input.max-chars", r.stdout)
        self.assertEqual(self.cli("limits", "set", "effort").returncode, 2)
        self.assertEqual(self.cli("limits", "set", "nope", "1").returncode, 2)
        self.assertEqual(self.cli("limits", "output").returncode, 2)
        self.assertIn("output.max-words", self.cli("limits", "reset", "output").stdout)
        self.assertIn("nothing was set", self.cli("limits", "reset", "output").stdout)
        rows = json.loads(self.cli("limits", "show", "--json").stdout)
        self.assertEqual(len(rows), len(limits.KNOBS))


class LimitEnforcementTests(ProjectTestCase):
    def test_prompt_too_long_or_short_is_blocked(self):
        limits.set_limits(self.project, [("input.max-chars", "20"), ("input.min-words", "2")])
        _, out = self.hook("UserPromptSubmit", prompt="this prompt is definitely longer than twenty characters")
        self.assertEqual(out["decision"], "block")
        self.assertIn("characters; the limit is 20", out["reason"])
        self.assertIn("harness limits reset input.max-chars", out["reason"])
        _, out = self.hook("UserPromptSubmit", prompt="hi")
        self.assertIn("is 1 word; the minimum is 2", out["reason"])
        res, _ = self.hook("UserPromptSubmit", prompt="fix tests")
        self.assertEqual(res.stdout, "")
        res, _ = self.hook("UserPromptSubmit", prompt="/clear")
        self.assertEqual(res.stdout, "")

    def test_reply_limits_are_injected_and_enforced_once(self):
        limits.set_limits(self.project, [("output.max-words", "5"), ("output.min-words", "2")])
        _, out = self.hook("UserPromptSubmit", prompt="explain the bug")
        self.assertIn("between 2 and 5 words", out["hookSpecificOutput"]["additionalContext"])
        _, out = self.hook("Stop", last_assistant_message="This reply has far more than five words in it.")
        self.assertEqual(out["decision"], "block")
        self.assertIn("at most 5 words", out["reason"])
        res, _ = self.hook("Stop", last_assistant_message="Still too long for the limit, sorry about that.")
        self.assertEqual(res.stdout, "")
        self.hook("UserPromptSubmit", prompt="again please")
        _, out = self.hook("Stop", last_assistant_message="Ok")
        self.assertIn("at least 2", out["reason"])
        res, _ = self.hook("Stop", last_assistant_message="Fixed it now.")
        self.assertEqual(res.stdout, "")

    def test_reply_within_limits_passes_and_reset_restores_normal(self):
        limits.set_limits(self.project, [("output.max-chars", "40")])
        self.hook("UserPromptSubmit", prompt="short answer please")
        res, _ = self.hook("Stop", last_assistant_message="Done: 3 tests pass.")
        self.assertEqual(res.stdout, "")
        limits.reset_limits(self.project, ["all"])
        res, _ = self.hook("UserPromptSubmit", prompt="explain everything")
        self.assertEqual(res.stdout, "")
        res, _ = self.hook("Stop", last_assistant_message="x " * 500)
        self.assertEqual(res.stdout, "")

    def test_session_start_mentions_limits(self):
        limits.set_limits(self.project, [("output.max-words", "200")])
        _, out = self.hook("SessionStart", source="startup")
        self.assertIn("at most 200 words", out["hookSpecificOutput"]["additionalContext"])
