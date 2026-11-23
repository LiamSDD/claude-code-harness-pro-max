"""Claude Code hook handlers.

Every hook runs ``harness hook <Event>``. Claude Code writes the event JSON to
stdin; the handler answers on stdout using the documented output contract:

* exit 0 + JSON object  -> structured decision / context
* exit 0 + plain text   -> context (SessionStart, UserPromptSubmit) or
                           compaction instructions (PreCompact)
* exit 1                -> non-blocking error, Claude Code carries on

Policy decisions are always returned as JSON (never via exit 2) so the
reason reaches Claude intact.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from . import __version__, gitinfo
from . import secrets as secretlib
from .config import LoadedPolicy, harness_dir, load_policy, project_dir
from .pathmatch import PathMatcher, resolve
from .policy import ALLOW, DENY, evaluate
from .progress import Progress
from .store import AuditLog, SessionState

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
PREFIX = "agent-harness"


@dataclass
class HookResult:
    stdout: str = ""
    exit_code: int = 0
    stderr: str = ""


def _json(obj: Dict[str, Any]) -> HookResult:
    return HookResult(stdout=json.dumps(obj, ensure_ascii=False))


def _tail(text: str, limit: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else "…" + text[-limit:]


def summarize_input(tool_name: str, tool_input: Any) -> Dict[str, Any]:
    """What the audit log keeps about a tool call: never file contents."""
    if not isinstance(tool_input, dict):
        return {}
    keep = {}
    for key in ("command", "file_path", "notebook_path", "path", "pattern", "glob", "url", "query", "description", "subagent_type"):
        if key in tool_input and isinstance(tool_input[key], (str, int)):
            keep[key] = tool_input[key]
    if tool_name in ("Write",) and isinstance(tool_input.get("content"), str):
        keep["bytes"] = len(tool_input["content"].encode("utf-8"))
    if tool_name == "MultiEdit" and isinstance(tool_input.get("edits"), list):
        keep["edits"] = len(tool_input["edits"])
    return keep


class Harness:
    """Shared context for one hook invocation."""

    def __init__(self, payload: Dict[str, Any]):
        self.payload = payload
        self.project = project_dir(payload)
        self.policy: LoadedPolicy = load_policy(self.project)
        self.dir = harness_dir(self.project)
        self.session_id = payload.get("session_id")
        self.audit = AuditLog.for_policy(self.policy)
        self.state = SessionState(self.dir, self.session_id)
        self.cwd = payload.get("cwd") or self.project

    def log(self, event: str, **fields: Any) -> None:
        try:
            self.audit.write({"event": event, "session": (self.session_id or "")[:12], **fields})
        except OSError as exc:  # never fail a hook because the log is unwritable
            sys.stderr.write(f"{PREFIX}: audit log unavailable: {exc}\n")


# --------------------------------------------------------------------------
# PreToolUse
# --------------------------------------------------------------------------


def pre_tool_use(h: Harness) -> HookResult:
    tool = h.payload.get("tool_name", "")
    tool_input = h.payload.get("tool_input") or {}
    verdict = evaluate(tool, tool_input, h.policy, h.cwd)
    mode = h.policy.mode

    if verdict.decision != ALLOW:
        with h.state.update() as st:
            st["denied" if verdict.decision == DENY else "asked"] += 1
        h.log(
            "PreToolUse",
            tool=tool,
            decision=verdict.decision if mode == "enforce" else f"{verdict.decision} (warn)",
            rules=verdict.rules,
            reason=verdict.reason,
            input=summarize_input(tool, tool_input),
        )

    if verdict.decision == ALLOW or mode == "off":
        return HookResult()
    if mode == "warn":
        return _json({"systemMessage": f"{PREFIX} (warn mode) would {verdict.decision}: {verdict.reason}"})
    reason = f"{PREFIX}: {verdict.reason}"
    if verdict.decision == DENY:
        reason += " Do not retry with a workaround; explain to the user what you need and why."
    return _json(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": verdict.decision,
                "permissionDecisionReason": reason,
            }
        }
    )


# --------------------------------------------------------------------------
# PostToolUse / PostToolUseFailure
# --------------------------------------------------------------------------


def _edited_path(tool_input: Dict[str, Any]) -> Optional[str]:
    p = tool_input.get("file_path") or tool_input.get("notebook_path")
    return p if isinstance(p, str) and p else None


def run_formatters(h: Harness, path: str) -> List[str]:
    """Run matching ``post_edit.formatters``. Returns problems for Claude."""
    problems: List[str] = []
    formatters = h.policy.get("post_edit.formatters", []) or []
    timeout = int(h.policy.get("post_edit.timeout", 30))
    abs_path = resolve(path, h.cwd)
    for fmt in formatters:
        matcher = PathMatcher([fmt.get("glob", "")])
        if not matcher.matches(abs_path, h.project):
            continue
        command = fmt["command"].replace("{file}", shlex.quote(abs_path))
        exe = shlex.split(command)[0] if command.strip() else ""
        if not exe or (shutil.which(exe) is None and not os.path.exists(exe)):
            continue  # formatter not installed on this machine: skip quietly
        try:
            proc = subprocess.run(command, shell=True, cwd=h.project, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            problems.append(f"`{command}` timed out after {timeout}s")
            continue
        if proc.returncode != 0:
            problems.append(f"`{command}` exited {proc.returncode}:\n{_tail(proc.stdout + proc.stderr, 1500)}")
    return problems


def post_tool_use(h: Harness) -> HookResult:
    tool = h.payload.get("tool_name", "")
    tool_input = h.payload.get("tool_input") or {}
    path = _edited_path(tool_input) if tool in EDIT_TOOLS else None
    with h.state.update() as st:
        st["tool_calls"] += 1
        if path:
            rel = os.path.relpath(resolve(path, h.cwd), h.project) if path else None
            if rel and rel not in st["edited_files"]:
                st["edited_files"] = (st["edited_files"] + [rel])[-200:]
            st["dirty_since_gate"] = True
    response = h.payload.get("tool_response")
    extra: Dict[str, Any] = {}
    if isinstance(response, dict) and tool == "Bash":
        extra["interrupted"] = response.get("interrupted")
    h.log("PostToolUse", tool=tool, input=summarize_input(tool, tool_input), duration_ms=h.payload.get("duration_ms"), **extra)

    if path:
        problems = run_formatters(h, path)
        if problems:
            return _json(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "additionalContext": f"{PREFIX}: post-edit checks failed for {path}:\n" + "\n\n".join(problems),
                    }
                }
            )
    return HookResult()


def post_tool_use_failure(h: Harness) -> HookResult:
    tool = h.payload.get("tool_name", "")
    with h.state.update() as st:
        st["failures"] += 1
    error = str(h.payload.get("error", "")).splitlines()[:1]
    h.log(
        "PostToolUseFailure",
        tool=tool,
        input=summarize_input(tool, h.payload.get("tool_input") or {}),
        error=error[0] if error else "",
        interrupted=h.payload.get("is_interrupt"),
    )
    return HookResult()


# --------------------------------------------------------------------------
# UserPromptSubmit
# --------------------------------------------------------------------------


def user_prompt_submit(h: Harness) -> HookResult:
    mode = h.policy.get("secrets.scan_prompts", "warn")
    prompt = h.payload.get("prompt") or ""
    if mode == "off" or not prompt:
        return HookResult()
    found = secretlib.scan_text(prompt, allow_patterns=h.policy.get("secrets.allow_patterns", []), min_confidence=secretlib.HIGH)
    if not found:
        return HookResult()
    kinds = ", ".join(sorted({f.title for f in found}))
    h.log(
        "UserPromptSubmit",
        decision="block" if mode == "block" else "warn",
        rules=["secret-in-prompt"],
        reason=kinds,
        prompt_chars=len(prompt),
    )
    if mode == "block":
        return _json(
            {
                "decision": "block",
                "reason": f"{PREFIX}: your prompt contains a {kinds}. It was not sent. Remove it (and consider rotating it), "
                "then reference it through an environment variable instead.",
            }
        )
    return _json(
        {
            "systemMessage": f"{PREFIX}: your prompt contains what looks like a live {kinds}. Consider rotating it.",
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": f"The user's message contains a credential ({kinds}). Never echo it back, write it to a "
                "file, put it in a command line or send it to any service. Use an environment variable reference instead.",
            },
        }
    )


# --------------------------------------------------------------------------
# SessionStart
# --------------------------------------------------------------------------


def session_context(h: Harness) -> str:
    ctx = h.policy.data.get("context", {})
    max_chars = int(ctx.get("max_chars", 6000))
    lines: List[str] = []
    layers = len(h.policy.sources)
    lines.append(
        f"[{PREFIX} {__version__}] Guardrails are active (mode: {h.policy.mode}, {layers} policy layer{'s' if layers != 1 else ''}). "
        "If a tool call is denied, the reason says why: do not work around it, tell the user what you need."
    )
    if h.policy.get("stop_gate.enabled") and h.policy.get("stop_gate.command"):
        lines.append(f"Before you finish, `{h.policy.get('stop_gate.command')}` must pass; the harness runs it when you stop.")
    if ctx.get("git", True) and gitinfo.is_repo(h.project):
        st = gitinfo.status(h.project)
        if st:
            lines.append(f"Git: {st.summary()}")
            if st.changed_files:
                shown = st.changed_files[:15]
                more = len(st.changed_files) - len(shown)
                lines.append("Changed: " + ", ".join(shown) + (f" (+{more} more)" if more > 0 else ""))
        commits = gitinfo.recent_commits(h.project, int(ctx.get("recent_commits", 5)))
        if commits:
            lines.append("Recent commits:\n" + "\n".join(f"  {c}" for c in commits))
    if ctx.get("progress", True):
        summary = Progress(h.dir).summary(max_chars=max(800, max_chars // 2))
        if summary:
            lines.append(summary)
    if h.policy.errors:
        lines.append("Policy problems (these layers were skipped): " + "; ".join(h.policy.errors))
    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def session_start(h: Harness) -> HookResult:
    SessionState.prune(h.dir)
    h.log("SessionStart", source=h.payload.get("source"), model=h.payload.get("model"), permission_mode=h.payload.get("permission_mode"))
    if not h.policy.get("context.session_start", True):
        return HookResult()
    out: Dict[str, Any] = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": session_context(h)}}
    if h.policy.errors:
        out["systemMessage"] = f"{PREFIX}: policy file problem, run `harness doctor`: " + "; ".join(h.policy.errors)
    return _json(out)


# --------------------------------------------------------------------------
# Stop: the verification gate
# --------------------------------------------------------------------------


def stop(h: Harness) -> HookResult:
    gate = h.policy.data.get("stop_gate", {})
    command = (gate.get("command") or "").strip()
    if not gate.get("enabled") or not command:
        h.log("Stop")
        return HookResult()
    st = h.state.load()
    if gate.get("only_if_edited", True) and not st.get("dirty_since_gate"):
        h.log("Stop", gate="skipped (no edits since last pass)")
        return HookResult()
    timeout = int(gate.get("timeout", 300))
    try:
        proc = subprocess.run(command, shell=True, cwd=h.project, capture_output=True, text=True, timeout=timeout)
        ok, output, code = proc.returncode == 0, proc.stdout + proc.stderr, proc.returncode
    except subprocess.TimeoutExpired as exc:
        ok, code = False, "timeout"
        output = f"timed out after {timeout}s\n" + (
            (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        )

    max_blocks = int(gate.get("max_blocks", 3))
    with h.state.update() as s:
        if ok:
            s["dirty_since_gate"] = False
            s["stop_blocks"] = 0
            blocks = 0
        else:
            s["stop_blocks"] = s.get("stop_blocks", 0) + 1
            blocks = s["stop_blocks"]
    if ok:
        h.log("Stop", gate="passed", command=command)
        return HookResult()
    if blocks > max_blocks:
        h.log("Stop", gate="failed, released", command=command, exit=code, attempts=blocks)
        return _json(
            {
                "systemMessage": f"{PREFIX}: `{command}` still fails after {max_blocks} attempts; letting Claude stop. Check the failures yourself."
            }
        )
    h.log("Stop", gate="failed, blocked", command=command, exit=code, attempts=blocks)
    return _json(
        {
            "decision": "block",
            "reason": (
                f"{PREFIX} verification gate: `{command}` failed (exit {code}, attempt {blocks}/{max_blocks}). "
                "Fix the cause, do not skip or delete tests, then finish.\n\n" + _tail(secretlib.redact_text(output), 3000)
            ),
        }
    )


def subagent_stop(h: Harness) -> HookResult:
    h.log("SubagentStop", agent_type=h.payload.get("agent_type"))
    return HookResult()


# --------------------------------------------------------------------------
# PreCompact / SessionEnd / Notification
# --------------------------------------------------------------------------


def pre_compact(h: Harness) -> HookResult:
    comp = h.policy.data.get("compaction", {})
    st = h.state.load()
    h.log("PreCompact", trigger=h.payload.get("trigger"))
    if comp.get("checkpoint", True):
        files = st.get("edited_files", [])
        body = [f"Context compaction ({h.payload.get('trigger') or 'auto'})."]
        if files:
            body.append("Files edited this session: " + ", ".join(files[-30:]))
        body.append(f"Tool calls: {st.get('tool_calls', 0)}, denied: {st.get('denied', 0)}, failures: {st.get('failures', 0)}.")
        try:
            Progress(h.dir).note("\n".join(body), session_id=h.session_id, heading="Compaction checkpoint")
        except OSError as exc:
            sys.stderr.write(f"{PREFIX}: could not write checkpoint: {exc}\n")
    instructions = comp.get("instructions", "")
    return HookResult(stdout=instructions)


def session_end(h: Harness) -> HookResult:
    st = h.state.load()
    h.log(
        "SessionEnd",
        reason=h.payload.get("reason"),
        tool_calls=st.get("tool_calls", 0),
        denied=st.get("denied", 0),
        asked=st.get("asked", 0),
        failures=st.get("failures", 0),
        edited=len(st.get("edited_files", [])),
    )
    SessionState.prune(h.dir)
    return HookResult()


def _desktop_notify(title: str, message: str) -> None:
    message = message[:200]
    if sys.platform == "darwin" and shutil.which("osascript"):
        script = f"display notification {json.dumps(message)} with title {json.dumps(title)}"
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    elif shutil.which("notify-send"):
        subprocess.run(["notify-send", title, message], capture_output=True, timeout=5)


def notification(h: Harness) -> HookResult:
    cfg = h.policy.data.get("notify", {})
    kind = h.payload.get("notification_type") or h.payload.get("type") or ""
    h.log("Notification", kind=kind)
    if cfg.get("enabled") and (not kind or kind in cfg.get("on", [])):
        try:
            _desktop_notify("Claude Code", h.payload.get("message") or "Claude needs your attention")
        except (OSError, subprocess.TimeoutExpired):
            pass
    return HookResult()


HANDLERS: Dict[str, Callable[[Harness], HookResult]] = {
    "PreToolUse": pre_tool_use,
    "PostToolUse": post_tool_use,
    "PostToolUseFailure": post_tool_use_failure,
    "UserPromptSubmit": user_prompt_submit,
    "SessionStart": session_start,
    "Stop": stop,
    "SubagentStop": subagent_stop,
    "PreCompact": pre_compact,
    "SessionEnd": session_end,
    "Notification": notification,
}


def dispatch(event: str, stdin_text: str) -> HookResult:
    handler = HANDLERS.get(event)
    if handler is None:
        return HookResult(exit_code=1, stderr=f"{PREFIX}: unknown hook event '{event}'. Known: {', '.join(HANDLERS)}\n")
    try:
        payload = json.loads(stdin_text) if stdin_text.strip() else {}
        if not isinstance(payload, dict):
            raise ValueError("hook input must be a JSON object")
    except (json.JSONDecodeError, ValueError) as exc:
        return HookResult(exit_code=1, stderr=f"{PREFIX}: invalid hook input: {exc}\n")
    event_name = payload.get("hook_event_name")
    if event_name and event_name != event:
        payload.setdefault("_dispatched_as", event)
    harness: Optional[Harness] = None
    try:
        harness = Harness(payload)
        return handler(harness)
    except Exception as exc:  # noqa: BLE001 - hooks must never crash Claude Code
        detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        fail_closed = harness is not None and harness.policy.data.get("fail_mode") == "closed"
        if event == "PreToolUse" and fail_closed:
            return _json(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": DENY,
                        "permissionDecisionReason": f"{PREFIX}: internal error while checking this call ({detail}); fail_mode is 'closed'.",
                    }
                }
            )
        if os.environ.get("HARNESS_DEBUG"):
            detail = traceback.format_exc()
        return HookResult(exit_code=1, stderr=f"{PREFIX}: {event} hook error: {detail}\n")
