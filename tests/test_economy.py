import json
import os

from helpers import ProjectTestCase

from harnesspro import cost
from harnesspro.store import SessionState


def transcript(path, entries):
    with open(path, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    return path


def assistant(mid, model="claude-opus-5-5", inp=10, out=1000, read=100000, write_1h=2000, thinking=200, sidechain=False, tools=()):
    return {
        "type": "assistant",
        "sessionId": "sess-1",
        "isSidechain": sidechain,
        "timestamp": "2026-11-24T10:00:00Z",
        "message": {
            "id": mid,
            "model": model,
            "content": [{"type": "tool_use", "id": t[0], "name": t[1], "input": t[2]} for t in tools],
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read_input_tokens": read,
                "cache_creation_input_tokens": write_1h,
                "cache_creation": {"ephemeral_1h_input_tokens": write_1h, "ephemeral_5m_input_tokens": 0},
                "output_tokens_details": {"thinking_tokens": thinking},
            },
        },
    }


def tool_result(tid, size):
    return {
        "type": "user",
        "sessionId": "sess-1",
        "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": "x" * size}]},
    }


class CostAnalysisTests(ProjectTestCase):
    git = False

    def test_cost_math_and_dedupe(self):
        p = transcript(self.path("t.jsonl"), [assistant("m1"), assistant("m1"), assistant("m2", model="claude-haiku-5-5")])
        r = cost.analyze([p])
        self.assertEqual(r.total.requests, 2)
        opus = (10 * 4 + 1000 * 20 + 100000 * 0.20 + 2000 * 8) / 1e6
        haiku = (10 * 0.10 + 1000 * 0.50 + 100000 * 0.01 + 2000 * 0.20) / 1e6
        self.assertAlmostEqual(r.total_cost, opus + haiku, places=9)
        self.assertGreater(r.total.cache_hit_rate, 0.9)

    def test_scopes_tools_and_reads(self):
        entries = [
            assistant("m1", tools=[("t1", "Read", {"file_path": "/p/a.py"}), ("t2", "Bash", {"command": "ls"})]),
            tool_result("t1", 5000),
            tool_result("t2", 300),
            assistant("m2", tools=[("t3", "Read", {"file_path": "/p/a.py"})]),
            assistant("m3", sidechain=True),
        ]
        r = cost.analyze([transcript(self.path("t.jsonl"), entries)])
        self.assertEqual(set(r.by_scope), {"main", "subagent"})
        self.assertEqual(r.tool_calls["Read"], 2)
        self.assertGreater(r.tool_output_chars["Read"], 5000)
        self.assertEqual(r.reads[("sess-1", "/p/a.py")], 2)
        self.assertEqual(r.largest_outputs[0][1], "Read")

    def test_recommendations(self):
        entries = [assistant(f"s{i}", sidechain=True, out=200000) for i in range(3)] + [assistant("m", read=1000, inp=400000, write_1h=0)]
        advice = {a.title for a in cost.recommend(cost.analyze([transcript(self.path("t.jsonl"), entries)]))}
        self.assertIn("Subagents run on a premium model", advice)
        self.assertIn("Low prompt-cache hit rate", advice)

    def test_render_and_json(self):
        r = cost.analyze([transcript(self.path("t.jsonl"), [assistant("m1")])])
        self.assertIn("Estimated cost", cost.render(r))
        data = json.loads(cost.to_json(r))
        self.assertEqual(data["sessions"], 1)
        self.assertIn("claude-opus-5-5", data["by_model"])

    def test_price_fallback_and_overrides(self):
        self.assertEqual(cost.price_for("claude-sonnet-9-9", cost.DEFAULT_PRICES)["input"], 2.0)
        r = cost.analyze(
            [transcript(self.path("t.jsonl"), [assistant("m1", inp=1_000_000, out=0, read=0, write_1h=0)])],
            {"claude-opus-5-5": {"input": 1.0, "output": 1.0}},
        )
        self.assertAlmostEqual(r.total_cost, 1.0)

    def test_transcript_discovery(self):
        folder = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "projects", cost.encode_project(self.project))
        os.makedirs(folder)
        transcript(os.path.join(folder, "abc.jsonl"), [assistant("m1")])
        self.assertEqual(len(cost.transcripts_for(self.project)), 1)
        self.assertEqual(len(cost.transcripts_for(None)), 1)
        with self.assertRaises(ValueError):
            cost.parse_since("yesterday")

    def test_meter_is_incremental(self):
        p = self.path("live.jsonl")
        transcript(p, [assistant("m1")])
        state = {}
        first = cost.Meter().update(state, p)
        with open(p, "a") as fh:
            fh.write(json.dumps(assistant("m1")) + "\n" + json.dumps(assistant("m2")) + "\n")
        second = cost.Meter().update(state, p)
        self.assertAlmostEqual(second, first * 2, places=9)
        self.assertEqual(cost.Meter().update(state, p), second)


class GuardTests(ProjectTestCase):
    def pre(self, tool, **ti):
        return self.hook("PreToolUse", tool_name=tool, tool_input=ti)

    def decision(self, out):
        return out["hookSpecificOutput"]["permissionDecision"] if isinstance(out, dict) and "hookSpecificOutput" in out else "allow"

    def test_duplicate_read_refused_until_file_changes(self):
        f = self.write("src/app.py", "print(1)\n")
        _, out = self.pre("Read", file_path=f)
        self.assertEqual(self.decision(out), "allow")
        self.hook("PostToolUse", tool_name="Read", tool_input={"file_path": f}, tool_response={})
        _, out = self.pre("Read", file_path=f)
        self.assertEqual(self.decision(out), "deny")
        self.assertIn("token-duplicate-read", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.assertNotIn("workaround", out["hookSpecificOutput"]["permissionDecisionReason"])
        _, out = self.pre("Read", file_path=f, offset=1, limit=5)
        self.assertEqual(self.decision(out), "allow")
        with open(f, "a") as fh:
            fh.write("print(2)\n")
        _, out = self.pre("Read", file_path=f)
        self.assertEqual(self.decision(out), "allow")

    def test_reads_reset_after_compaction_and_per_agent(self):
        f = self.write("a.py", "x = 1\n")
        self.hook("PostToolUse", tool_name="Read", tool_input={"file_path": f}, tool_response={})
        _, out = self.pre("Read", file_path=f)
        self.assertEqual(self.decision(out), "deny")
        _, out = self.hook("PreToolUse", tool_name="Read", tool_input={"file_path": f}, agent_id="agent-7")
        self.assertEqual(self.decision(out), "allow")
        self.hook("PreCompact", trigger="auto")
        _, out = self.pre("Read", file_path=f)
        self.assertEqual(self.decision(out), "allow")

    def test_generated_and_large_reads(self):
        lock = self.write("package-lock.json", "{}")
        bundle = self.write("web/node_modules/x/index.js", "1")
        _, out = self.pre("Read", file_path=lock)
        self.assertIn("token-generated-read", out["hookSpecificOutput"]["permissionDecisionReason"])
        _, out = self.pre("Read", file_path=bundle)
        self.assertEqual(self.decision(out), "deny")
        big = self.write("data/big.csv", "a,b\n" * 60000)
        _, out = self.pre("Read", file_path=big)
        self.assertIn("token-large-read", out["hookSpecificOutput"]["permissionDecisionReason"])
        _, out = self.pre("Read", file_path=big, offset=1, limit=50)
        self.assertEqual(self.decision(out), "allow")

    def test_output_flood_commands(self):
        self.write("data/big.log", "line\n" * 60000)
        for command in (
            "cat data/big.log",
            "find / -name x",
            "tail -f app.log",
            "docker logs api",
            "journalctl -u nginx",
            "git log",
            "ls -R",
            "watch ls",
        ):
            with self.subTest(command=command):
                _, out = self.pre("Bash", command=command)
                self.assertEqual(self.decision(out), "deny", command)
                self.assertIn("token-output-flood", out["hookSpecificOutput"]["permissionDecisionReason"])
        for command in (
            "cat data/big.log | grep ERROR",
            "git log --oneline -20",
            "docker logs --tail 200 api",
            "journalctl -n 100",
            "tail -n 50 app.log",
            "find . -name '*.py'",
            "ls src",
        ):
            with self.subTest(command=command):
                _, out = self.pre("Bash", command=command)
                self.assertEqual(self.decision(out), "allow", command)

    def test_guards_can_be_turned_off(self):
        self.write_policy({"cost": {"output_guard": "allow", "generated_reads": "allow", "read_dedupe": False}})
        _, out = self.pre("Bash", command="git log")
        self.assertEqual(self.decision(out), "allow")
        _, out = self.pre("Read", file_path=self.write("yarn.lock", ""))
        self.assertEqual(self.decision(out), "allow")

    def test_saved_calls_are_counted(self):
        self.pre("Bash", command="git log")
        st = SessionState(self.path(".claude", "harness"), "test-session-0001").load()
        self.assertEqual(st["saved_calls"], 1)


class SubagentTests(ProjectTestCase):
    def agent(self, **ti):
        ti.setdefault("prompt", "find the config loader")
        ti.setdefault("description", "search")
        return self.hook("PreToolUse", tool_name="Agent", tool_input=ti)

    def test_model_routing(self):
        self.write_policy({"subagents": {"models": {"Explore": "haiku", "*": "sonnet"}}})
        _, out = self.agent(subagent_type="Explore")
        hso = out["hookSpecificOutput"]
        self.assertEqual((hso["permissionDecision"], hso["updatedInput"]["model"]), ("allow", "haiku"))
        self.assertEqual(hso["updatedInput"]["prompt"], "find the config loader")
        _, out = self.agent(subagent_type="implementer")
        self.assertEqual(out["hookSpecificOutput"]["updatedInput"]["model"], "sonnet")
        res, _ = self.agent(subagent_type="Explore", model="opus")
        self.assertEqual(res.stdout, "")

    def test_session_and_concurrency_limits(self):
        self.write_policy({"subagents": {"max_per_session": 2, "max_concurrent": 1}})
        res, _ = self.agent()
        self.assertEqual(res.stdout, "")
        self.hook("SubagentStart", agent_id="a1", agent_type="general-purpose")
        _, out = self.agent()
        self.assertIn("subagent-concurrency", out["hookSpecificOutput"]["permissionDecisionReason"])
        self.hook("SubagentStop", agent_id="a1", agent_type="general-purpose")
        res, _ = self.agent()
        self.assertEqual(res.stdout, "")
        _, out = self.agent()
        self.assertIn("subagent-limit", out["hookSpecificOutput"]["permissionDecisionReason"])


class BudgetTests(ProjectTestCase):
    def test_warn_then_ask(self):
        self.write_policy({"cost": {"session_budget_usd": 0.05, "warn_at": 0.5}})
        t = transcript(self.path("session.jsonl"), [assistant("m1", out=2000, read=0, write_1h=0, inp=0)])
        _, out = self.hook("PostToolUse", tool_name="Bash", tool_input={"command": "ls"}, tool_response={}, transcript_path=t)
        self.assertIn("budget", out["systemMessage"])
        res, _ = self.hook("PostToolUse", tool_name="Bash", tool_input={"command": "ls"}, tool_response={}, transcript_path=t)
        self.assertEqual(res.stdout, "")
        with open(t, "a") as fh:
            fh.write(json.dumps(assistant("m2", out=2000, read=0, write_1h=0, inp=0)) + "\n")
        self.hook("PostToolUse", tool_name="Bash", tool_input={"command": "ls"}, tool_response={}, transcript_path=t)
        _, out = self.hook("PreToolUse", tool_name="Bash", tool_input={"command": "ls"})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")
        self.assertIn("budget-exceeded", out["hookSpecificOutput"]["permissionDecisionReason"])


class EventTests(ProjectTestCase):
    def test_config_change_warns_when_hooks_removed(self):
        self.write(".claude/settings.json", "{}")
        _, out = self.hook("ConfigChange", source="project_settings")
        self.assertIn("no longer runs", out["systemMessage"])
        self.write(
            ".claude/settings.json",
            json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"type": "command", "command": "harness hook PreToolUse"}]}]}}),
        )
        res, _ = self.hook("ConfigChange", source="project_settings")
        self.assertEqual(res.stdout, "")

    def test_observed_events_are_logged(self):
        for event in ("PermissionDenied", "TaskCompleted", "PostModelSwitch"):
            res, _ = self.hook(event, tool_name="Bash")
            self.assertEqual(res.exit_code, 0)
