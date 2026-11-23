from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, Optional

from .assets import asset_dir
from .hooks import HookResult, dispatch

PLATFORMS = ("claude", "cursor", "codex", "gemini", "antigravity", "kimi", "opencode", "generic")


def _cursor_payload(event: str, data: Dict[str, Any]) -> Dict[str, Any]:
    roots = data.get("workspace_roots") or []
    cwd = data.get("cwd") or (roots[0] if roots else os.getcwd())
    base = {
        "session_id": data.get("conversation_id") or data.get("session_id") or "cursor",
        "transcript_path": data.get("transcript_path"),
        "cwd": cwd,
        "hook_event_name": event,
    }
    os.environ.setdefault("CLAUDE_PROJECT_DIR", roots[0] if roots else cwd)
    return base


def _hso(result: HookResult) -> Dict[str, Any]:
    try:
        out = json.loads(result.stdout) if result.stdout.strip().startswith("{") else {}
    except ValueError:
        out = {}
    return out


def _cursor_session_start(data: Dict[str, Any]) -> Dict[str, Any]:
    payload = {**_cursor_payload("SessionStart", data), "source": "startup"}
    out = _hso(dispatch("SessionStart", json.dumps(payload)))
    context = (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
    return {"additional_context": "\n\n".join(p for p in (bootstrap_text("cursor"), context) if p)}


def _cursor_permission(event: str, tool: str, tool_input: Dict[str, Any], data: Dict[str, Any], ask_allowed: bool = True) -> Dict[str, Any]:
    payload = {**_cursor_payload("PreToolUse", data), "tool_name": tool, "tool_input": tool_input}
    out = _hso(dispatch("PreToolUse", json.dumps(payload)))
    hso = out.get("hookSpecificOutput") or {}
    decision = hso.get("permissionDecision", "allow")
    if decision == "ask" and not ask_allowed:
        decision = "deny"
    if decision not in ("allow", "deny", "ask"):
        decision = "allow"
    result: Dict[str, Any] = {"permission": decision}
    reason = hso.get("permissionDecisionReason")
    if reason and decision != "allow":
        result["user_message"] = reason
        if ask_allowed:
            result["agent_message"] = reason
    return result


def _cursor_shell(data: Dict[str, Any]) -> Dict[str, Any]:
    return _cursor_permission("beforeShellExecution", "Bash", {"command": data.get("command", "")}, data)


def _cursor_read(data: Dict[str, Any]) -> Dict[str, Any]:
    return _cursor_permission("beforeReadFile", "Read", {"file_path": data.get("file_path", "")}, data, ask_allowed=False)


def _cursor_mcp(data: Dict[str, Any]) -> Dict[str, Any]:
    name = str(data.get("tool_name") or data.get("name") or "")
    server = str(data.get("server") or data.get("server_name") or "server")
    tool = name if name.startswith("mcp__") else f"mcp__{server}__{name}"
    return _cursor_permission("beforeMCPExecution", tool, data.get("tool_input") or {}, data)


def _cursor_prompt(data: Dict[str, Any]) -> Dict[str, Any]:
    payload = {**_cursor_payload("UserPromptSubmit", data), "prompt": data.get("prompt", "")}
    out = _hso(dispatch("UserPromptSubmit", json.dumps(payload)))
    if out.get("decision") == "block":
        return {"continue": False, "user_message": out.get("reason", "blocked by harness-pro-max")}
    result: Dict[str, Any] = {"continue": True}
    if out.get("systemMessage"):
        result["user_message"] = out["systemMessage"]
    return result


def _cursor_after_edit(data: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        **_cursor_payload("PostToolUse", data),
        "tool_name": "Edit",
        "tool_input": {"file_path": data.get("file_path", "")},
        "tool_response": {},
    }
    dispatch("PostToolUse", json.dumps(payload))
    return {}


def _cursor_observe(event: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    def handler(data: Dict[str, Any]) -> Dict[str, Any]:
        payload = {**_cursor_payload(event, data)}
        dispatch(event, json.dumps(payload))
        return {}

    return handler


CURSOR_EVENTS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "sessionStart": _cursor_session_start,
    "beforeShellExecution": _cursor_shell,
    "beforeReadFile": _cursor_read,
    "beforeMCPExecution": _cursor_mcp,
    "beforeSubmitPrompt": _cursor_prompt,
    "afterFileEdit": _cursor_after_edit,
    "stop": _cursor_observe("Stop"),
    "sessionEnd": _cursor_observe("SessionEnd"),
    "subagentStart": _cursor_observe("SubagentStart"),
    "subagentStop": _cursor_observe("SubagentStop"),
}


def run(platform: str, event: str, stdin_text: str) -> HookResult:
    if platform in ("claude", ""):
        return dispatch(event, stdin_text)
    try:
        data = json.loads(stdin_text) if stdin_text.strip() else {}
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if platform == "cursor":
        handler = CURSOR_EVENTS.get(event)
        if handler is None:
            return HookResult(stdout="{}")
        try:
            return HookResult(stdout=json.dumps(handler(data)))
        except Exception as exc:
            return HookResult(stdout="{}", stderr=f"harness-pro-max: {event} adapter error: {exc}\n", exit_code=1)
    if event in ("SessionStart", "sessionStart", "session-start"):
        payload = {
            "session_id": data.get("session_id") or platform,
            "cwd": data.get("cwd") or os.getcwd(),
            "hook_event_name": "SessionStart",
            "source": "startup",
        }
        out = _hso(dispatch("SessionStart", json.dumps(payload)))
        context = (out.get("hookSpecificOutput") or {}).get("additionalContext", "")
        text = "\n\n".join(p for p in (bootstrap_text(platform), context) if p)
        return HookResult(stdout=json.dumps({"additionalContext": text}))
    return dispatch(event, stdin_text)


def bootstrap_text(platform: str) -> str:
    parts = []
    skill = os.path.join(asset_dir("skills"), "using-harness-pro-max", "SKILL.md")
    mapping = os.path.join(asset_dir("skills"), "using-harness-pro-max", "references", f"{platform}-tools.md")
    for path in (skill, mapping):
        text = _read(path)
        if text:
            parts.append(text.split("---", 2)[2].strip() if text.startswith("---") else text.strip())
    return "\n\n".join(parts)


def _read(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None
