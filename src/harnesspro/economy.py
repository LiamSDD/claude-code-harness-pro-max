from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from .pathmatch import PathMatcher, resolve
from .policy import ALLOW, ASK, DENY, Verdict
from .shell import analyze, expand_user_path

AGENT_TOOLS = ("Agent", "Task")
_LOG_TOOLS = {("docker", "logs"), ("kubectl", "logs"), ("podman", "logs"), ("oc", "logs")}
_GIT_LIMIT = re.compile(r"^(-n\d*|--max-count(=\d+)?|-\d+|--since.*|--after.*|--until.*|--oneline|.*\.\..*)$")


def _agent_key(payload: Dict[str, Any]) -> str:
    return str(payload.get("agent_id") or "main")


def _file_sig(path: str) -> Optional[List[float]]:
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [st.st_mtime, st.st_size]


def record_read(state: Dict[str, Any], payload: Dict[str, Any], path: str) -> None:
    sig = _file_sig(path)
    if sig is None:
        return
    reads = state.setdefault("reads", {}).setdefault(_agent_key(payload), {})
    reads[path] = sig
    if len(reads) > 400:
        for k in list(reads)[:100]:
            reads.pop(k, None)


def forget_reads(state: Dict[str, Any]) -> None:
    state["reads"] = {}


class Economy:
    def __init__(self, policy, cwd: str, payload: Dict[str, Any], state: Dict[str, Any]):
        self.policy = policy
        self.cfg = policy.data.get("cost", {})
        self.sub = policy.data.get("subagents", {})
        self.cwd = cwd
        self.project = policy.project
        self.payload = payload
        self.state = state
        self.generated = PathMatcher(self.cfg.get("generated_paths", []))
        self.updated_input: Optional[Dict[str, Any]] = None

    def enabled(self, rule: str) -> bool:
        return self.policy.rule_enabled(rule)

    def add(self, v: Verdict, decision: str, rule: str, reason: str) -> None:
        if decision in (ASK, DENY) and self.enabled(rule):
            v.add(decision, rule, reason)

    def evaluate(self, tool: str, tool_input: Dict[str, Any], v: Verdict) -> Tuple[Verdict, Optional[Dict[str, Any]]]:
        self.budget(v)
        if tool == "Read":
            self.read(tool_input, v)
        elif tool == "Bash":
            self.bash(str(tool_input.get("command", "")), v)
        elif tool in AGENT_TOOLS:
            self.agents(tool_input, v)
        return v, self.updated_input

    def budget(self, v: Verdict) -> None:
        limit = float(self.cfg.get("session_budget_usd") or 0)
        spent = float(self.state.get("cost_usd") or 0)
        if limit > 0 and spent >= limit:
            self.add(
                v,
                self.cfg.get("on_budget", ASK),
                "budget-exceeded",
                f"this session has spent ${spent:.2f} of its ${limit:.2f} budget. Finish with the cheapest path, or ask the user to raise cost.session_budget_usd.",
            )

    def read(self, ti: Dict[str, Any], v: Verdict) -> None:
        raw = ti.get("file_path")
        if not isinstance(raw, str) or not raw:
            return
        path = resolve(raw, self.cwd)
        partial = bool(ti.get("offset") or ti.get("limit") or ti.get("pages"))
        hit = self.generated.match(path, self.project)
        if hit:
            self.add(
                v,
                self.cfg.get("generated_reads", DENY),
                "token-generated-read",
                f"{os.path.relpath(path, self.project) if path.startswith(self.project) else path} is generated or vendored (matches '{hit}'). "
                "Read the source it comes from, or Grep it for the one thing you need.",
            )
            return
        sig = _file_sig(path)
        if sig is None:
            return
        max_bytes = int(self.cfg.get("max_read_bytes") or 0)
        if max_bytes and not partial and sig[1] > max_bytes:
            self.add(
                v,
                self.cfg.get("output_guard", DENY),
                "token-large-read",
                f"the file is {int(sig[1]) // 1024} KB. Grep for what you need, or Read it in parts with offset and limit.",
            )
            return
        if self.cfg.get("read_dedupe", True) and not partial:
            seen = self.state.get("reads", {}).get(_agent_key(self.payload), {}).get(path)
            if seen and list(seen) == sig:
                self.add(
                    v,
                    DENY,
                    "token-duplicate-read",
                    "you already read this file in full and it has not changed since; its content is still in your context. "
                    "Use it from there (or Read a specific range with offset and limit if you need to re-check a part).",
                )

    def bash(self, command: str, v: Verdict) -> None:
        decision = self.cfg.get("output_guard", DENY)
        if decision == ALLOW or not command.strip():
            return
        max_bytes = int(self.cfg.get("max_read_bytes") or 0)
        cwd = self.cwd
        for cmd in analyze(command).commands:
            name, args = cmd.name, cmd.args
            if name in ("cd", "pushd") and args:
                cwd = os.path.normpath(os.path.join(cwd, expand_user_path(args[0])))
                continue
            if name in ("cat", "less", "more", "bat") and not cmd.pipes_to and max_bytes:
                for a in args:
                    if a.startswith("-"):
                        continue
                    sig = _file_sig(resolve(expand_user_path(a), cwd))
                    if sig and sig[1] > max_bytes:
                        self.add(
                            v,
                            decision,
                            "token-output-flood",
                            f"'{name} {a}' prints {int(sig[1]) // 1024} KB. Use grep, head -n, or the Read tool with offset and limit.",
                        )
            if name == "find" and args:
                root = expand_user_path(args[0])
                if root in ("/", os.path.expanduser("~"), "~") and "-maxdepth" not in args:
                    self.add(
                        v,
                        decision,
                        "token-output-flood",
                        f"'find {args[0]}' without -maxdepth walks the whole disk. Search the project, or add -maxdepth and -name.",
                    )
            if name in ("tail", "less") and ("-f" in args or "-F" in args or "+F" in args):
                self.add(
                    v,
                    decision,
                    "token-output-flood",
                    f"'{name} -f' never exits. Use tail -n 200, or run it in the background and read the output file.",
                )
            if name == "watch" or "watch" in cmd.wrappers:
                self.add(v, decision, "token-output-flood", "'watch' never exits. Run the command once, or poll with a bounded loop.")
            if (name, args[0] if args else "") in _LOG_TOOLS and not any(a.startswith(("--tail", "--since", "-n")) for a in args):
                follow = any(a in ("-f", "--follow") for a in args)
                self.add(
                    v,
                    decision,
                    "token-output-flood",
                    f"'{name} logs' without --tail prints the whole log{' and never exits' if follow else ''}. Add --tail 200 (or --since 10m).",
                )
            if name == "journalctl" and not any(a.startswith(("-n", "--lines", "--since", "-S", "-b")) for a in args):
                self.add(
                    v,
                    decision,
                    "token-output-flood",
                    "'journalctl' without -n or --since prints the entire journal. Add -n 200 or --since '10 min ago'.",
                )
            if name == "git" and args[:1] == ["log"] and not cmd.pipes_to and not any(_GIT_LIMIT.match(a) for a in args[1:]):
                self.add(
                    v,
                    decision,
                    "token-output-flood",
                    "'git log' without a limit prints the whole history. Use git log --oneline -20 or -n 20.",
                )
            if name in ("ls", "tree") and ("-R" in args or (name == "tree" and not any(a.startswith("-L") for a in args))):
                targets = [a for a in args if not a.startswith("-")]
                if not targets or any(os.path.normpath(os.path.join(cwd, t)) == self.project for t in targets):
                    self.add(
                        v,
                        decision,
                        "token-output-flood",
                        f"recursive '{name}' of the project lists every file. Use Glob with a pattern, or tree -L 2.",
                    )

    def agents(self, ti: Dict[str, Any], v: Verdict) -> None:
        on_limit = self.sub.get("on_limit", DENY)
        max_total = int(self.sub.get("max_per_session") or 0)
        spawned = int(self.state.get("subagents_spawned", 0))
        if max_total and spawned >= max_total:
            self.add(
                v,
                on_limit,
                "subagent-limit",
                f"this session already started {spawned} subagents (limit {max_total}). Do the remaining work directly or batch it into fewer agents.",
            )
        max_running = int(self.sub.get("max_concurrent") or 0)
        running = len(self.state.get("subagents_running", []))
        if max_running and running >= max_running:
            self.add(
                v,
                on_limit,
                "subagent-concurrency",
                f"{running} subagents are still running (limit {max_running}). Wait for one to finish before starting another.",
            )
        models = self.sub.get("models") or {}
        if models and not ti.get("model"):
            kind = str(ti.get("subagent_type") or "general-purpose")
            model = models.get(kind, models.get("*"))
            if model:
                self.updated_input = {**ti, "model": model}
