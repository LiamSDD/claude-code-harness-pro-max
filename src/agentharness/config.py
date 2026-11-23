"""Policy loading, layering and validation.

Layers, lowest to highest precedence::

    built-in defaults        src/agentharness/defaults/policy.json
    user                     ~/.claude/harness/policy.json
    project (committed)      <project>/.claude/harness/policy.json
    project local (personal) <project>/.claude/harness/policy.local.json
    environment              HARNESS_POLICY=/path/to/policy.json

Objects merge key by key. Lists are appended (duplicates dropped) so a layer
can add rules without copying the defaults. To replace a list instead, suffix
the key with ``!``, e.g. ``"deny_read!": ["*.pem"]``. Scalars override.
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "defaults", "policy.json")
HARNESS_DIRNAME = os.path.join(".claude", "harness")

DECISIONS = ("allow", "ask", "deny")


class PolicyError(ValueError):
    pass


def project_dir(payload: Optional[dict] = None) -> str:
    """Resolve the project root the way Claude Code does for hooks."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return os.path.abspath(env)
    if payload and isinstance(payload.get("cwd"), str) and payload["cwd"]:
        return os.path.abspath(payload["cwd"])
    return os.path.abspath(os.getcwd())


def harness_dir(project: str) -> str:
    return os.path.join(project, HARNESS_DIRNAME)


def user_policy_path() -> str:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "harness", "policy.json")


def layer_paths(project: str) -> List[Tuple[str, str]]:
    layers = [
        ("user", user_policy_path()),
        ("project", os.path.join(harness_dir(project), "policy.json")),
        ("local", os.path.join(harness_dir(project), "policy.local.json")),
    ]
    env = os.environ.get("HARNESS_POLICY")
    if env:
        layers.append(("env", os.path.abspath(env)))
    return layers


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise PolicyError(f"{path}: invalid JSON ({exc.msg} at line {exc.lineno})") from exc
    if not isinstance(data, dict):
        raise PolicyError(f"{path}: top level must be an object")
    return data


def merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in over.items():
        if key.startswith("$"):  # "$schema", "$comment"
            continue
        replace = key.endswith("!")
        k = key[:-1] if replace else key
        if replace:
            out[k] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], value)
        elif isinstance(value, list) and isinstance(out.get(k), list):
            merged = list(out[k])
            for item in value:
                if item not in merged:
                    merged.append(item)
            out[k] = merged
        else:
            out[k] = copy.deepcopy(value)
    return out


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

_STR = str
_BOOL = bool
_INT = int
_LIST = list
_DICT = dict

SCHEMA: Dict[str, Any] = {
    "version": _INT,
    "mode": ("enforce", "warn", "off"),
    "fail_mode": ("open", "closed"),
    "disable": [_STR],
    "bash": {
        "on_parse_error": DECISIONS,
        "sudo": DECISIONS,
        "rules": [_DICT],
    },
    "paths": {
        "deny_read": [_STR],
        "deny_write": [_STR],
        "ask_write": [_STR],
        "write_outside_project": DECISIONS,
        "write_allow_outside": [_STR],
    },
    "secrets": {
        "scan_writes": _BOOL,
        "scan_prompts": ("off", "warn", "block"),
        "scan_commands": DECISIONS,
        "allow_patterns": [_STR],
        "ignore_paths": [_STR],
    },
    "web": {"allow_domains": [_STR], "ask_domains": [_STR], "deny_domains": [_STR]},
    "mcp": {"deny_tools": [_STR], "ask_tools": [_STR]},
    "post_edit": {"formatters": [_DICT], "timeout": _INT},
    "stop_gate": {
        "enabled": _BOOL,
        "command": _STR,
        "timeout": _INT,
        "only_if_edited": _BOOL,
        "max_blocks": _INT,
    },
    "context": {
        "session_start": _BOOL,
        "git": _BOOL,
        "recent_commits": _INT,
        "progress": _BOOL,
        "max_chars": _INT,
    },
    "compaction": {"checkpoint": _BOOL, "instructions": _STR},
    "audit": {"enabled": _BOOL, "path": _STR, "max_bytes": _INT, "keep": _INT},
    "notify": {"enabled": _BOOL, "on": [_STR]},
}


def _type_name(t: Any) -> str:
    return {str: "string", bool: "boolean", int: "integer", list: "array", dict: "object"}.get(t, str(t))


def _check(value: Any, schema: Any, where: str, errors: List[str]) -> None:
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            errors.append(f"{where}: expected object")
            return
        for k, v in value.items():
            if k.startswith("$"):
                continue
            key = k[:-1] if k.endswith("!") else k
            if key not in schema:
                errors.append(f"{where}.{key}: unknown key")
                continue
            _check(v, schema[key], f"{where}.{key}", errors)
    elif isinstance(schema, tuple):
        if value not in schema:
            errors.append(f"{where}: must be one of {', '.join(schema)} (got {value!r})")
    elif isinstance(schema, list):
        if not isinstance(value, list):
            errors.append(f"{where}: expected array")
            return
        for idx, item in enumerate(value):
            _check(item, schema[0], f"{where}[{idx}]", errors)
    else:
        ok = isinstance(value, schema) and not (schema is int and isinstance(value, bool))
        if not ok:
            errors.append(f"{where}: expected {_type_name(schema)}")


def _check_rules(policy: Dict[str, Any], errors: List[str]) -> None:
    import re

    for idx, rule in enumerate(policy.get("bash", {}).get("rules", [])):
        where = f"bash.rules[{idx}]"
        if not isinstance(rule, dict):
            continue
        for k in rule:
            if k not in ("id", "pattern", "decision", "reason", "scope"):
                errors.append(f"{where}.{k}: unknown key")
        if not isinstance(rule.get("id"), str) or not rule.get("id"):
            errors.append(f"{where}.id: required string")
        if rule.get("decision") not in ("ask", "deny"):
            errors.append(f"{where}.decision: must be ask or deny")
        if rule.get("scope", "segment") not in ("segment", "command"):
            errors.append(f"{where}.scope: must be segment or command")
        try:
            re.compile(rule.get("pattern", ""))
        except (re.error, TypeError) as exc:
            errors.append(f"{where}.pattern: invalid regex ({exc})")
    for idx, fmt in enumerate(policy.get("post_edit", {}).get("formatters", [])):
        where = f"post_edit.formatters[{idx}]"
        if not isinstance(fmt, dict):
            continue
        if not isinstance(fmt.get("glob"), str) or not isinstance(fmt.get("command"), str):
            errors.append(f"{where}: needs string 'glob' and 'command'")
        elif "{file}" not in fmt["command"]:
            errors.append(f"{where}.command: must contain {{file}}")


def validate(policy: Dict[str, Any], where: str = "policy") -> List[str]:
    errors: List[str] = []
    _check(policy, SCHEMA, where, errors)
    if not errors:
        _check_rules(policy, errors)
    return errors


# --------------------------------------------------------------------------
# Loaded policy
# --------------------------------------------------------------------------


@dataclass
class LoadedPolicy:
    data: Dict[str, Any]
    project: str
    sources: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    @property
    def mode(self) -> str:
        return self.data.get("mode", "enforce")

    def rule_enabled(self, rule_id: str) -> bool:
        return rule_id not in set(self.data.get("disable", []))


def load_defaults() -> Dict[str, Any]:
    return _read_json(DEFAULTS_PATH)


def load_policy(project: Optional[str] = None, strict: bool = False) -> LoadedPolicy:
    """Load and merge every policy layer for ``project``.

    With ``strict`` a broken layer raises; otherwise it is skipped and the
    error is recorded so ``harness doctor`` can report it.
    """
    project = os.path.abspath(project or project_dir())
    data = load_defaults()
    sources = ["defaults"]
    errors: List[str] = []
    for name, path in layer_paths(project):
        if not os.path.isfile(path):
            continue
        try:
            layer = _read_json(path)
            layer_errors = validate(layer, where=name)
            if layer_errors:
                raise PolicyError("; ".join(layer_errors))
        except (OSError, PolicyError) as exc:
            if strict:
                raise PolicyError(f"{path}: {exc}") from exc
            errors.append(f"{path}: {exc}")
            continue
        data = merge(data, layer)
        sources.append(f"{name}:{path}")
    return LoadedPolicy(data=data, project=project, sources=sources, errors=errors)
