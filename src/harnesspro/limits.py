from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import settings_merge
from .config import harness_dir, load_policy, user_policy_path

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


@dataclass(frozen=True)
class Knob:
    key: str
    kind: str
    target: str
    enforcement: str
    summary: str
    parse: Callable[[str], Any]


def _int(minimum: int = 1, maximum: Optional[int] = None) -> Callable[[str], int]:
    def parse(raw: str) -> int:
        try:
            value = int(str(raw).replace("_", "").replace(",", ""))
        except ValueError as exc:
            raise ValueError(f"expected a whole number, got {raw!r}") from exc
        if value < minimum or (maximum is not None and value > maximum):
            bound = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
            raise ValueError(f"must be {bound}")
        return value

    return parse


def _money(raw: str) -> float:
    try:
        value = float(str(raw).lstrip("$"))
    except ValueError as exc:
        raise ValueError(f"expected an amount in USD, got {raw!r}") from exc
    if value <= 0:
        raise ValueError("must be more than 0")
    return value


def _choice(options: Tuple[str, ...]) -> Callable[[str], str]:
    def parse(raw: str) -> str:
        value = str(raw).strip().lower()
        if value not in options:
            raise ValueError(f"must be one of {', '.join(options)}")
        return value

    return parse


def _model(raw: str) -> str:
    value = str(raw).strip()
    if not re.fullmatch(r"[A-Za-z0-9._\-\[\]]{2,80}", value):
        raise ValueError("expected a model alias (opus, sonnet, haiku, fable) or a model id")
    return value


def _flag(raw: str) -> str:
    value = str(raw).strip().lower()
    if value in ("off", "false", "0", "no", "disable", "disabled"):
        return "1"
    raise ValueError("use 'off' to disable it; reset turns it back on")


KNOBS: Dict[str, Knob] = {
    k.key: k
    for k in [
        Knob(
            "output.max-tokens",
            "env",
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
            "hard",
            "Maximum tokens Claude may generate per response",
            _int(1, 128000),
        ),
        Knob(
            "output.max-words",
            "policy",
            "limits.output.max_words",
            "hook",
            "Longest reply in words; longer replies are sent back to be shortened",
            _int(1),
        ),
        Knob(
            "output.min-words",
            "policy",
            "limits.output.min_words",
            "hook",
            "Shortest reply in words; shorter replies are sent back to be expanded",
            _int(1),
        ),
        Knob("output.max-chars", "policy", "limits.output.max_chars", "hook", "Longest reply in characters", _int(1)),
        Knob("output.min-chars", "policy", "limits.output.min_chars", "hook", "Shortest reply in characters", _int(1)),
        Knob("input.max-words", "policy", "limits.input.max_words", "hook", "Longest prompt you can send, in words", _int(1)),
        Knob("input.min-words", "policy", "limits.input.min_words", "hook", "Shortest prompt you can send, in words", _int(1)),
        Knob("input.max-chars", "policy", "limits.input.max_chars", "hook", "Longest prompt you can send, in characters", _int(1)),
        Knob("input.min-chars", "policy", "limits.input.min_chars", "hook", "Shortest prompt you can send, in characters", _int(1)),
        Knob(
            "effort", "env", "CLAUDE_CODE_EFFORT_LEVEL", "hard", "Reasoning effort: low, medium, high, xhigh, max", _choice(EFFORT_LEVELS)
        ),
        Knob("model", "setting", "model", "hard", "Default model for new sessions (alias or id)", _model),
        Knob("turns.max", "env", "CLAUDE_CODE_MAX_TURNS", "hard", "Maximum agentic turns per request", _int(1)),
        Knob(
            "budget.session-usd", "policy", "cost.session_budget_usd", "hook", "Session spend at which tool calls need confirmation", _money
        ),
        Knob(
            "subagents.max-concurrent",
            "env+policy",
            "CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS|subagents.max_concurrent",
            "hard",
            "Subagents running at the same time",
            _int(1, 100),
        ),
        Knob("subagents.max-per-session", "policy", "subagents.max_per_session", "hook", "Subagents one session may start", _int(1)),
        Knob(
            "subagents.max-depth",
            "env",
            "CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH",
            "hard",
            "How deep subagents may spawn subagents",
            _int(1, 10),
        ),
        Knob("web.max-searches", "env", "CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION", "hard", "WebSearch calls per session", _int(1)),
        Knob(
            "bash.max-output-chars",
            "env",
            "BASH_MAX_OUTPUT_LENGTH",
            "hard",
            "Characters of command output Claude reads back",
            _int(1000, 150000),
        ),
        Knob(
            "read.max-tokens", "env", "CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS", "hard", "Tokens a single file read may return", _int(1000)
        ),
        Knob(
            "compact.at-percent",
            "env",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE",
            "hard",
            "Context fill percentage at which auto-compaction starts",
            _int(1, 100),
        ),
        Knob("thinking", "env", "CLAUDE_CODE_DISABLE_THINKING", "hard", "Set to off to send requests without extended thinking", _flag),
    ]
}

ALIASES = {
    "output.max": "output.max-words",
    "output.min": "output.min-words",
    "input.max": "input.max-chars",
    "input.min": "input.min-chars",
    "max-output-tokens": "output.max-tokens",
    "budget": "budget.session-usd",
    "turns": "turns.max",
}

GROUPS = {
    "output": [k for k in KNOBS if k.startswith("output.")],
    "input": [k for k in KNOBS if k.startswith("input.")],
    "subagents": [k for k in KNOBS if k.startswith("subagents.")],
}


def resolve_key(raw: str) -> str:
    key = raw.strip().lower().replace("_", "-")
    key = ALIASES.get(key, key)
    if key not in KNOBS:
        close = [k for k in KNOBS if key.split(".")[0] in k][:6]
        hint = f" Did you mean: {', '.join(close)}?" if close else " Run `harness limits` to list them."
        raise KeyError(f"unknown limit '{raw}'.{hint}")
    return key


@dataclass
class Scope:
    name: str
    settings: str
    policy: str


def scope_paths(project: str, scope: str) -> Scope:
    if scope == "user":
        base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
        return Scope("user", os.path.join(base, "settings.json"), user_policy_path())
    if scope == "shared":
        return Scope("shared", os.path.join(project, ".claude", "settings.json"), os.path.join(harness_dir(project), "policy.json"))
    return Scope("local", os.path.join(project, ".claude", "settings.local.json"), os.path.join(harness_dir(project), "policy.local.json"))


def _get_path(data: Dict[str, Any], dotted: str) -> Any:
    node: Any = data
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _set_path(data: Dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = data
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _del_path(data: Dict[str, Any], dotted: str) -> bool:
    parts = dotted.split(".")
    chain = [data]
    for part in parts[:-1]:
        nxt = chain[-1].get(part) if isinstance(chain[-1], dict) else None
        if not isinstance(nxt, dict):
            return False
        chain.append(nxt)
    if parts[-1] not in chain[-1]:
        return False
    del chain[-1][parts[-1]]
    for i in range(len(chain) - 1, 0, -1):
        if not chain[i]:
            del chain[i - 1][parts[i - 1]]
    return True


def _targets(knob: Knob) -> List[Tuple[str, str]]:
    if knob.kind == "env+policy":
        env, pol = knob.target.split("|")
        return [("env", env), ("policy", pol)]
    return [(knob.kind, knob.target)]


class Store:
    def __init__(self, scope: Scope):
        self.scope = scope
        self.settings = settings_merge.load(scope.settings)
        self.policy = settings_merge.load(scope.policy)
        self.dirty_settings = False
        self.dirty_policy = False

    def get(self, kind: str, target: str) -> Any:
        if kind == "env":
            return (self.settings.get("env") or {}).get(target)
        if kind == "setting":
            return self.settings.get(target)
        return _get_path(self.policy, target)

    def put(self, kind: str, target: str, value: Any) -> None:
        if kind == "env":
            self.settings.setdefault("env", {})[target] = str(value)
            self.dirty_settings = True
        elif kind == "setting":
            self.settings[target] = value
            self.dirty_settings = True
        else:
            _set_path(self.policy, target, value)
            self.policy.setdefault("version", 1)
            self.dirty_policy = True

    def remove(self, kind: str, target: str) -> bool:
        if kind == "env":
            env = self.settings.get("env") or {}
            if target in env:
                del env[target]
                if not env:
                    self.settings.pop("env", None)
                self.dirty_settings = True
                return True
            return False
        if kind == "setting":
            if target in self.settings:
                del self.settings[target]
                self.dirty_settings = True
                return True
            return False
        removed = _del_path(self.policy, target)
        self.dirty_policy = self.dirty_policy or removed
        return removed

    def save(self) -> None:
        for dirty, path, data, empty in (
            (self.dirty_settings, self.scope.settings, self.settings, {}),
            (self.dirty_policy, self.scope.policy, self.policy, {"version": 1}),
        ):
            if not dirty:
                continue
            if data in ({}, empty) and os.path.exists(path):
                os.remove(path)
            elif data not in ({}, empty):
                settings_merge.write(path, data, backup=False)


def set_limits(project: str, pairs: List[Tuple[str, str]], scope: str = "local") -> List[str]:
    store = Store(scope_paths(project, scope))
    staged: Dict[str, Any] = {}
    for raw_key, raw_value in pairs:
        key = resolve_key(raw_key)
        try:
            staged[key] = KNOBS[key].parse(raw_value)
        except ValueError as exc:
            raise ValueError(f"{key}: {exc}") from exc
    for low, high in (
        ("output.min-words", "output.max-words"),
        ("output.min-chars", "output.max-chars"),
        ("input.min-words", "input.max-words"),
        ("input.min-chars", "input.max-chars"),
    ):
        lo = staged.get(low, current_value(project, low))
        hi = staged.get(high, current_value(project, high))
        if lo is not None and hi is not None and float(lo) > float(hi):
            raise ValueError(f"{low} ({lo}) cannot be greater than {high} ({hi})")
    changes = []
    for key, value in staged.items():
        for kind, target in _targets(KNOBS[key]):
            store.put(kind, target, value)
        changes.append(f"{key} = {value}")
    store.save()
    return changes


def reset_limits(project: str, keys: List[str], scope: str = "local") -> List[str]:
    store = Store(scope_paths(project, scope))
    wanted: List[str] = []
    for raw in keys:
        name = raw.strip().lower()
        if name in ("all", "*"):
            wanted = list(KNOBS)
            break
        if name in GROUPS:
            wanted += GROUPS[name]
        else:
            wanted.append(resolve_key(raw))
    cleared = []
    for key in dict.fromkeys(wanted):
        if any(store.remove(kind, target) for kind, target in _targets(KNOBS[key])):
            cleared.append(key)
    if store.policy.get("limits") == {}:
        store.policy.pop("limits", None)
    store.save()
    return cleared


def current_value(project: str, key: str) -> Any:
    knob = KNOBS[key]
    for scope in ("local", "shared", "user"):
        store = Store(scope_paths(project, scope))
        for kind, target in _targets(knob):
            if kind == "policy":
                continue
            value = store.get(kind, target)
            if value is not None:
                return value
    for kind, target in _targets(knob):
        if kind == "policy":
            value = load_policy(project).get(target)
            if value not in (None, 0):
                return value
    return None


def table(project: str) -> List[Dict[str, Any]]:
    rows = []
    for key, knob in KNOBS.items():
        value = current_value(project, key)
        source = None
        if value is not None:
            for scope in ("local", "shared", "user"):
                store = Store(scope_paths(project, scope))
                if any(store.get(kind, target) is not None for kind, target in _targets(knob)):
                    source = scope
                    break
        rows.append({"key": key, "value": value, "source": source, "enforcement": knob.enforcement, "summary": knob.summary})
    return rows


def render(rows: List[Dict[str, Any]], only_set: bool = False) -> str:
    lines = [f"  {'limit':<26} {'value':<14} {'set in':<8} what it controls"]
    for r in rows:
        if only_set and r["value"] is None:
            continue
        value = "off" if r["key"] == "thinking" and r["value"] == "1" else ("unlimited" if r["value"] is None else str(r["value"]))
        where = r["source"] or "-"
        lines.append(f"  {r['key']:<26} {value:<14} {where:<8} {r['summary']}{'' if r['enforcement'] == 'hard' else ' (hook)'}")
    return "\n".join(lines)


def output_limits(policy) -> Dict[str, int]:
    out = policy.get("limits.output") or {}
    return {k: int(v) for k, v in out.items() if isinstance(v, (int, float)) and v > 0}


def input_limits(policy) -> Dict[str, int]:
    out = policy.get("limits.input") or {}
    return {k: int(v) for k, v in out.items() if isinstance(v, (int, float)) and v > 0}


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def count_words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def output_instruction(limits: Dict[str, int]) -> Optional[str]:
    parts = []
    lo_w, hi_w = limits.get("min_words"), limits.get("max_words")
    lo_c, hi_c = limits.get("min_chars"), limits.get("max_chars")
    if lo_w and hi_w:
        parts.append(f"between {lo_w} and {hi_w} words")
    elif hi_w:
        parts.append(f"at most {hi_w} words")
    elif lo_w:
        parts.append(f"at least {lo_w} words")
    if lo_c and hi_c:
        parts.append(f"between {lo_c} and {hi_c} characters")
    elif hi_c:
        parts.append(f"at most {hi_c} characters")
    elif lo_c:
        parts.append(f"at least {lo_c} characters")
    if not parts:
        return None
    return f"Reply length limit set by the user: keep your final reply to {' and '.join(parts)}. Code you write to files does not count."


def check_output(text: str, limits: Dict[str, int]) -> Optional[str]:
    words, chars = count_words(text), len((text or "").strip())
    if limits.get("max_words") and words > limits["max_words"]:
        return f"your reply is {plural(words, 'word')}; the user's limit is {limits['max_words']}. Rewrite it in at most {limits['max_words']} words, keeping the essential content."
    if limits.get("max_chars") and chars > limits["max_chars"]:
        return f"your reply is {plural(chars, 'character')}; the user's limit is {limits['max_chars']}. Rewrite it in at most {limits['max_chars']} characters."
    if limits.get("min_words") and words < limits["min_words"]:
        return f"your reply is {plural(words, 'word')}; the user asked for at least {limits['min_words']}. Expand it with useful detail (not filler) to at least {limits['min_words']} words."
    if limits.get("min_chars") and chars < limits["min_chars"]:
        return f"your reply is {plural(chars, 'character')}; the user asked for at least {limits['min_chars']}. Expand it to at least {limits['min_chars']} characters."
    return None


def check_input(prompt: str, limits: Dict[str, int]) -> Optional[str]:
    if (prompt or "").lstrip().startswith("/"):
        return None
    words, chars = count_words(prompt), len((prompt or "").strip())
    checks = [
        (
            "max_words",
            words > limits.get("max_words", 10**12),
            f"{plural(words, 'word')}; the limit is {limits.get('max_words')}",
            "input.max-words",
        ),
        (
            "max_chars",
            chars > limits.get("max_chars", 10**12),
            f"{plural(chars, 'character')}; the limit is {limits.get('max_chars')}",
            "input.max-chars",
        ),
        (
            "min_words",
            words < limits.get("min_words", 0),
            f"{plural(words, 'word')}; the minimum is {limits.get('min_words')}",
            "input.min-words",
        ),
        (
            "min_chars",
            chars < limits.get("min_chars", 0),
            f"{plural(chars, 'character')}; the minimum is {limits.get('min_chars')}",
            "input.min-chars",
        ),
    ]
    for _, failed, detail, key in checks:
        if failed:
            return f"Your message is {detail}. It was not sent. Edit it, or remove the limit with `harness limits reset {key}`."
    return None
