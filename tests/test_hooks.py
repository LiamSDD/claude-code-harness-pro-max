import os
import sys
import unittest

from helpers import FAKE_ANTHROPIC, FAKE_GITHUB, ProjectTestCase

from agentharness.hooks import dispatch
from agentharness.progress import Progress
from agentharness.store import AuditLog, SessionState


class PreToolUseTests(ProjectTestCase):
    def test_deny_contract(self):
        res, out = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "rm -rf ~"}, tool_use_id="t1")
        self.assertEqual(res.exit_code, 0)
        hso = out["hookSpecificOutput"]
        self.assertEqual(hso["hookEventName"], "PreToolUse")
        self.assertEqual(hso["permissionDecision"], "deny")
        self.assertIn("rm-dangerous-target", hso["permissionDecisionReason"])

    def test_ask_contract(self):
        _, out = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "git reset --hard"})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_allow_is_silent(self):
        res, out = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "git status"})
        self.assertEqual((res.exit_code, res.stdout), (0, ""))

    def test_warn_mode(self):
        self.write_policy({"mode": "warn"})
        _, out = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "rm -rf ~"})
        self.assertNotIn("hookSpecificOutput", out)
        self.assertIn("would deny", out["systemMessage"])

    def test_decisions_are_audited_and_counted(self):
        self.hook("PreToolUse", tool_name="Read", tool_input={"file_path": self.path(".env")})
        records = AuditLog(self.path(".claude", "harness", "audit.jsonl")).read()
        self.assertEqual(records[-1]["decision"], "deny")
        self.assertEqual(records[-1]["rules"], ["secret-file-read"])
        state = SessionState(self.path(".claude", "harness"), "test-session-0001").load()
        self.assertEqual(state["denied"], 1)

    def test_audit_redacts_secrets(self):
        self.hook("PreToolUse", tool_name="Bash", tool_input={"command": f"curl -H 'token: {FAKE_GITHUB}' https://x"})
        raw = self.read(".claude", "harness", "audit.jsonl")
        self.assertNotIn(FAKE_GITHUB, raw)
        self.assertIn("REDACTED", raw)

    def test_fail_closed(self):
        self.write_policy({"fail_mode": "closed"})
        import agentharness.hooks as hooks

        original = hooks.evaluate
        hooks.evaluate = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            res, out = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "ls"})
        finally:
            hooks.evaluate = original
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("boom", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_fail_open(self):
        import agentharness.hooks as hooks

        original = hooks.evaluate
        hooks.evaluate = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            res, _ = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "ls"})
        finally:
            hooks.evaluate = original
        self.assertEqual(res.exit_code, 1)
        self.assertIn("boom", res.stderr)


class DispatchTests(ProjectTestCase):
    git = False

    def test_bad_input(self):
        self.assertEqual(dispatch("PreToolUse", "not json").exit_code, 1)
        self.assertEqual(dispatch("PreToolUse", "[1]").exit_code, 1)
        self.assertEqual(dispatch("NoSuchEvent", "{}").exit_code, 1)

    def test_empty_input_is_tolerated(self):
        self.assertEqual(dispatch("SessionEnd", "").exit_code, 0)


class PostToolUseTests(ProjectTestCase):
    def test_tracks_edited_files(self):
        for name in ("a.py", "b.py", "a.py"):
            self.hook(
                "PostToolUse",
                tool_name="Edit",
                tool_input={"file_path": self.path(name), "old_string": "x", "new_string": "y"},
                tool_response={},
            )
        self.hook("PostToolUse", tool_name="Bash", tool_input={"command": "ls"}, tool_response={"stdout": "", "interrupted": False})
        st = SessionState(self.path(".claude", "harness"), "test-session-0001").load()
        self.assertEqual(st["edited_files"], ["a.py", "b.py"])
        self.assertEqual(st["tool_calls"], 4)
        self.assertTrue(st["dirty_since_gate"])

    def test_formatter_failure_is_reported(self):
        script = self.write("fmt.py", "import sys\nprint('E501 line too long')\nsys.exit(1)\n")
        self.write_policy({"post_edit": {"formatters": [{"glob": "*.py", "command": f"{sys.executable} {script} {{file}}"}]}})
        target = self.write("src/app.py", "x=1\n")
        _, out = self.hook("PostToolUse", tool_name="Write", tool_input={"file_path": target, "content": "x=1\n"}, tool_response={})
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("E501", ctx)

    def test_missing_formatter_is_skipped(self):
        self.write_policy({"post_edit": {"formatters": [{"glob": "*.py", "command": "definitely-not-installed-fmt {file}"}]}})
        res, _ = self.hook("PostToolUse", tool_name="Write", tool_input={"file_path": self.path("a.py"), "content": ""}, tool_response={})
        self.assertEqual(res.stdout, "")

    def test_failure_event(self):
        self.hook("PostToolUseFailure", tool_name="Bash", tool_input={"command": "false"}, error="Exit code 1\nboom")
        rec = AuditLog(self.path(".claude", "harness", "audit.jsonl")).read()[-1]
        self.assertEqual(rec["error"], "Exit code 1")


class PromptTests(ProjectTestCase):
    def test_warn(self):
        _, out = self.hook("UserPromptSubmit", prompt=f"use this key {FAKE_ANTHROPIC} please")
        self.assertIn("Anthropic", out["systemMessage"])
        self.assertIn("Never echo", out["hookSpecificOutput"]["additionalContext"])

    def test_block(self):
        self.write_policy({"secrets": {"scan_prompts": "block"}})
        _, out = self.hook("UserPromptSubmit", prompt=f"key: {FAKE_GITHUB}")
        self.assertEqual(out["decision"], "block")
        self.assertNotIn(FAKE_GITHUB, out["reason"])

    def test_clean_prompt(self):
        res, _ = self.hook("UserPromptSubmit", prompt="add a login page")
        self.assertEqual(res.stdout, "")


class SessionStartTests(ProjectTestCase):
    def test_context(self):
        self.write("README.md", "hi\n")
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "Initial commit")
        self.write("new.txt", "x")
        prog = Progress(self.path(".claude", "harness"))
        prog.add("User can sign in", steps=["open /login", "submit valid credentials"])
        prog.note("Set up the project skeleton.")
        _, out = self.hook("SessionStart", source="startup")
        ctx = out["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Guardrails are active", ctx)
        self.assertIn("Git: main", ctx)
        self.assertIn("Initial commit", ctx)
        self.assertIn("new.txt", ctx)
        self.assertIn("Next: #1 User can sign in", ctx)
        self.assertIn("project skeleton", ctx)

    def test_reports_policy_errors(self):
        self.write(".claude/harness/policy.json", "{broken")
        _, out = self.hook("SessionStart", source="startup")
        self.assertIn("harness doctor", out["systemMessage"])

    def test_max_chars(self):
        self.write_policy({"context": {"max_chars": 120}})
        Progress(self.path(".claude", "harness")).note("x" * 2000)
        _, out = self.hook("SessionStart", source="startup")
        self.assertLessEqual(len(out["hookSpecificOutput"]["additionalContext"]), 120)


class StopGateTests(ProjectTestCase):
    def gate(self, command, **extra):
        self.write_policy({"stop_gate": {"enabled": True, "command": command, "timeout": 20, **extra}})

    def edit(self):
        self.hook("PostToolUse", tool_name="Write", tool_input={"file_path": self.path("x.py"), "content": ""}, tool_response={})

    def test_disabled_by_default(self):
        res, _ = self.hook("Stop", stop_hook_active=False)
        self.assertEqual(res.stdout, "")

    def test_blocks_on_failure_then_releases(self):
        self.gate(f"{sys.executable} -c \"import sys; print('2 failed'); sys.exit(1)\"", max_blocks=2)
        self.edit()
        _, out = self.hook("Stop", stop_hook_active=False)
        self.assertEqual(out["decision"], "block")
        self.assertIn("2 failed", out["reason"])
        self.assertIn("attempt 1/2", out["reason"])
        _, out = self.hook("Stop", stop_hook_active=True)
        self.assertEqual(out["decision"], "block")
        _, out = self.hook("Stop", stop_hook_active=True)
        self.assertNotIn("decision", out)
        self.assertIn("still fails", out["systemMessage"])

    def test_passes_and_resets(self):
        self.gate(f"{sys.executable} -c \"print('ok')\"")
        self.edit()
        res, _ = self.hook("Stop", stop_hook_active=False)
        self.assertEqual(res.stdout, "")
        st = SessionState(self.path(".claude", "harness"), "test-session-0001").load()
        self.assertFalse(st["dirty_since_gate"])

    def test_skips_without_edits(self):
        self.gate(f'{sys.executable} -c "import sys; sys.exit(1)"')
        res, _ = self.hook("Stop", stop_hook_active=False)
        self.assertEqual(res.stdout, "")

    def test_timeout_counts_as_failure(self):
        self.gate(f'{sys.executable} -c "import time; time.sleep(5)"', timeout=1)
        self.edit()
        _, out = self.hook("Stop", stop_hook_active=False)
        self.assertIn("timed out", out["reason"])


class LifecycleTests(ProjectTestCase):
    def test_pre_compact_writes_checkpoint(self):
        self.hook(
            "PostToolUse",
            tool_name="Edit",
            tool_input={"file_path": self.path("api.py"), "old_string": "a", "new_string": "b"},
            tool_response={},
        )
        res, out = self.hook("PreCompact", trigger="auto", custom_instructions="")
        self.assertIn("Preserve", out)
        log = self.read(".claude", "harness", "progress.md")
        self.assertIn("Compaction checkpoint", log)
        self.assertIn("api.py", log)

    def test_session_end_summary(self):
        self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "rm -rf ~"})
        self.hook("SessionEnd", reason="exit")
        rec = AuditLog(self.path(".claude", "harness", "audit.jsonl")).read()[-1]
        self.assertEqual(rec["event"], "SessionEnd")
        self.assertEqual(rec["denied"], 1)

    def test_notification_logged(self):
        res, _ = self.hook("Notification", message="Claude needs permission", notification_type="permission_prompt")
        self.assertEqual(res.exit_code, 0)

    def test_audit_rotation(self):
        log = AuditLog(self.path("a.jsonl"), max_bytes=300, keep=2)
        for i in range(30):
            log.write({"event": "x", "i": i})
        self.assertTrue(os.path.exists(self.path("a.jsonl.1")))
        self.assertTrue(os.path.exists(self.path("a.jsonl.2")))
        self.assertFalse(os.path.exists(self.path("a.jsonl.3")))
        self.assertEqual(log.read(include_rotated=True)[-1]["i"], 29)

    def test_audit_disabled(self):
        self.write_policy({"audit": {"enabled": False}})
        self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "rm -rf ~"})
        self.assertFalse(os.path.exists(self.path(".claude", "harness", "audit.jsonl")))


if __name__ == "__main__":
    unittest.main()
