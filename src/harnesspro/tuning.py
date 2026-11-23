from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from . import settings_merge
from .config import harness_dir, merge

HOOKS_DOC = "https://code.claude.com/docs/en/hooks.md"

HANDLED = {
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "UserPromptSubmit",
    "SessionStart",
    "Stop",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
    "PostCompact",
    "SessionEnd",
    "Notification",
    "ConfigChange",
    "PermissionDenied",
    "StopFailure",
    "PostModelSwitch",
    "TaskCreated",
    "TaskCompleted",
    "InstructionsLoaded",
}
NOT_FOR_OBSERVERS = {
    "WorktreeCreate",
    "WorktreeRemove",
    "PermissionRequest",
    "Elicitation",
    "ElicitationResult",
    "MessageDisplay",
    "UserPromptExpansion",
    "PreModelSwitch",
    "Setup",
    "PostToolBatch",
    "CwdChanged",
    "DirectoryAdded",
    "FileChanged",
    "TeammateIdle",
}

PROFILES: Dict[str, Dict[str, Any]] = {
    "balanced": {
        "env": {
            "BASH_MAX_OUTPUT_LENGTH": "20000",
            "CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS": "15000",
            "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "6",
            "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "2",
            "CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION": "40",
            "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
        },
        "policy": {
            "cost": {"read_dedupe": True, "output_guard": "deny", "generated_reads": "deny"},
            "subagents": {"max_concurrent": 6, "models": {"Explore": "haiku", "statusline-setup": "haiku", "*": "sonnet"}},
        },
    },
    "lean": {
        "env": {
            "BASH_MAX_OUTPUT_LENGTH": "12000",
            "CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS": "10000",
            "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS": "4",
            "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH": "1",
            "CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION": "20",
            "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "70",
        },
        "policy": {
            "cost": {"read_dedupe": True, "output_guard": "deny", "generated_reads": "deny", "max_read_bytes": 120000},
            "subagents": {
                "max_concurrent": 4,
                "max_per_session": 20,
                "models": {"*": "haiku", "general-purpose": "sonnet", "Plan": "sonnet"},
            },
        },
    },
}

GENERATED_DENY = [
    "Read(./**/node_modules/**)",
    "Read(./**/*.min.js)",
    "Read(./**/*.min.css)",
    "Read(./**/*.map)",
    "Read(./**/coverage/**)",
    "Read(./**/.next/**)",
]


def optimize(project: str, profile: str = "balanced", budget: Optional[float] = None, apply: bool = False) -> List[str]:
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {', '.join(PROFILES)}")
    spec = PROFILES[profile]
    changes: List[str] = []

    settings_path = os.path.join(project, ".claude", "settings.json")
    existing = settings_merge.load(settings_path)
    fragment = {"env": dict(spec["env"]), "permissions": {"deny": list(GENERATED_DENY)}}
    merged, notes = settings_merge.merge_settings(existing, fragment)
    for key, value in spec["env"].items():
        if (existing.get("env") or {}).get(key) is None:
            changes.append(f"settings env {key}={value}")
        elif str(existing["env"][key]) != value:
            changes.append(f"settings env {key} kept at {existing['env'][key]} (profile suggests {value})")
    added_rules = [r for r in GENERATED_DENY if r not in ((existing.get("permissions") or {}).get("deny") or [])]
    if added_rules:
        changes.append(f"settings permissions.deny +{len(added_rules)} generated-file read rules")
    if apply and notes:
        settings_merge.write(settings_path, merged, backup=bool(existing))

    policy_path = os.path.join(harness_dir(project), "policy.json")
    current = settings_merge.load(policy_path)
    layer = json.loads(json.dumps(spec["policy"]))
    if budget is not None:
        layer["cost"]["session_budget_usd"] = float(budget)
    new_policy = merge(current, layer)
    if new_policy != current:
        for section, values in layer.items():
            for key, value in values.items():
                if (current.get(section) or {}).get(key) != value:
                    changes.append(f"policy {section}.{key} = {json.dumps(value)}")
        if apply:
            new_policy.setdefault("version", 1)
            settings_merge.write(policy_path, new_policy, backup=bool(current))
    return changes


def fetch_doc(url: str = HOOKS_DOC, timeout: float = 15.0) -> str:
    if not url.startswith("https://"):
        raise OSError("only https URLs are fetched")
    req = urllib.request.Request(url, headers={"User-Agent": "harness-pro-max"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


SINGLE_WORD_EVENTS = {"Stop", "Setup", "Notification", "Elicitation"}


def documented_events(text: str) -> List[str]:
    headings = set(re.findall(r"^#{2,4}\s+`?([A-Z][A-Za-z]+)`?\s*$", text, re.M))
    return sorted(h for h in headings if re.fullmatch(r"[A-Z][a-z]+(?:[A-Z][a-z]+)+", h) or h in SINGLE_WORD_EVENTS)


def upstream_report(text: str) -> Tuple[List[str], List[str], List[str]]:
    events = documented_events(text)
    new = [e for e in events if e not in HANDLED and e not in NOT_FOR_OBSERVERS]
    skipped = [e for e in events if e in NOT_FOR_OBSERVERS]
    missing = sorted(e for e in HANDLED if e not in events)
    return new, skipped, missing


def register_events(hooks_file: str, events: List[str], command_prefix: str) -> List[str]:
    data = settings_merge.load(hooks_file)
    hooks = data.setdefault("hooks", {})
    added = []
    for event in events:
        if event in hooks:
            continue
        hooks[event] = [{"hooks": [{"type": "command", "command": f"{command_prefix} hook {event}", "timeout": 10}]}]
        added.append(event)
    if added:
        settings_merge.write(hooks_file, data, backup=False)
    return added
