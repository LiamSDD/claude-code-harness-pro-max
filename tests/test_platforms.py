import json
import os

from helpers import ROOT, ProjectTestCase

from harnesspro import limits, platforms


class CursorAdapterTests(ProjectTestCase):
    def cursor(self, event, **data):
        data.setdefault("conversation_id", "conv-1")
        data.setdefault("workspace_roots", [self.project])
        result = platforms.run("cursor", event, json.dumps(data))
        self.assertEqual(result.exit_code, 0, result.stderr)
        return json.loads(result.stdout)

    def test_shell_permissions(self):
        out = self.cursor("beforeShellExecution", command="rm -rf ~")
        self.assertEqual(out["permission"], "deny")
        self.assertIn("rm-dangerous-target", out["agent_message"])
        self.assertEqual(self.cursor("beforeShellExecution", command="git reset --hard")["permission"], "ask")
        self.assertEqual(self.cursor("beforeShellExecution", command="npm test"), {"permission": "allow"})
        self.assertEqual(self.cursor("beforeShellExecution", command="git log")["permission"], "deny")

    def test_read_has_no_ask(self):
        out = self.cursor("beforeReadFile", file_path=self.path(".env"))
        self.assertEqual(out["permission"], "deny")
        self.assertNotIn("agent_message", out)
        out = self.cursor("beforeReadFile", file_path=self.write("package-lock.json", "{}"))
        self.assertEqual(out["permission"], "deny")
        self.assertEqual(self.cursor("beforeReadFile", file_path=self.write("src/a.py", "x=1"))["permission"], "allow")

    def test_prompt_limits_and_secrets(self):
        limits.set_limits(self.project, [("input.max-words", "3")])
        out = self.cursor("beforeSubmitPrompt", prompt="one two three four five")
        self.assertEqual(out["continue"], False)
        self.assertIn("limit is 3", out["user_message"])
        self.assertEqual(self.cursor("beforeSubmitPrompt", prompt="fix it"), {"continue": True})

    def test_session_start_bootstrap(self):
        out = self.cursor("sessionStart")
        self.assertIn("Using Claude Code Harness Pro Max", out["additional_context"])
        self.assertIn("Cursor tool mapping", out["additional_context"])
        self.assertIn("Guardrails are active", out["additional_context"])

    def test_mcp_and_unknown_events(self):
        out = self.cursor("beforeMCPExecution", tool_name="delete_repository", server="github", tool_input={})
        self.assertEqual(out["permission"], "ask")
        self.assertEqual(self.cursor("afterAgentThought"), {})
        self.assertEqual(self.cursor("afterFileEdit", file_path=self.path("a.py")), {})

    def test_generic_platform_bootstrap(self):
        result = platforms.run("codex", "SessionStart", json.dumps({"cwd": self.project}))
        text = json.loads(result.stdout)["additionalContext"]
        self.assertIn("Codex tool mapping", text)
        self.assertIn("Guardrails are active", text)


class ManifestTests(ProjectTestCase):
    git = False

    def load(self, rel):
        with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
            return json.load(fh)

    def test_all_platform_manifests(self):
        version = self.load(".claude-plugin/plugin.json")["version"]
        for rel in (
            ".claude-plugin/plugin.json",
            ".codex-plugin/plugin.json",
            ".cursor-plugin/plugin.json",
            ".antigravity-plugin/plugin.json",
            ".kimi-plugin/plugin.json",
            "gemini-extension.json",
        ):
            with self.subTest(manifest=rel):
                m = self.load(rel)
                self.assertEqual(m["name"], "harness-pro-max")
                self.assertEqual(m["version"], version)
                for key in ("skills", "hooks"):
                    if isinstance(m.get(key), str):
                        self.assertTrue(os.path.exists(os.path.join(ROOT, m[key])), m[key])
        for agent in self.load(".claude-plugin/plugin.json")["agents"]:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, agent)), agent)

    def test_cursor_hooks_use_the_adapter(self):
        hooks = self.load("hooks/hooks-cursor.json")["hooks"]
        for event, entries in hooks.items():
            self.assertIn(event, platforms.CURSOR_EVENTS)
            self.assertIn("--platform cursor", entries[0]["command"])

    def test_gemini_context_and_tool_maps_exist(self):
        with open(os.path.join(ROOT, "GEMINI.md")) as fh:
            for line in fh:
                self.assertTrue(os.path.isfile(os.path.join(ROOT, line.strip().lstrip("@"))), line)
        for platform in ("claude-code", "codex", "cursor", "gemini", "antigravity", "kimi", "opencode", "generic"):
            self.assertTrue(
                os.path.isfile(os.path.join(ROOT, "skills", "using-harness-pro-max", "references", f"{platform}-tools.md")), platform
            )
