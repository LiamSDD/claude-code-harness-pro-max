from __future__ import annotations

import glob
import json
import os
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

DEFAULT_PRICES: Dict[str, Dict[str, float]] = {
    "claude-fable-5-2": {"input": 8.0, "output": 40.0, "cache_read": 0.20},
    "claude-mythos-5-2": {"input": 8.0, "output": 40.0, "cache_read": 0.20},
    "claude-fable-5-1": {"input": 10.0, "output": 50.0},
    "claude-mythos-5-1": {"input": 10.0, "output": 50.0},
    "claude-fable-5": {"input": 10.0, "output": 50.0},
    "claude-opus-5-5": {"input": 4.0, "output": 20.0, "cache_read": 0.20},
    "claude-opus-5": {"input": 5.0, "output": 25.0},
    "claude-opus-4-8": {"input": 5.0, "output": 25.0},
    "claude-opus-4-7": {"input": 5.0, "output": 25.0},
    "claude-opus-4-6": {"input": 5.0, "output": 25.0},
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.10},
    "claude-sonnet-5": {"input": 2.0, "output": 10.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50},
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
}
CACHE_WRITE_5M = 1.25
CACHE_WRITE_1H = 2.0
CACHE_READ = 0.10
FAMILY_FALLBACK = {
    "fable": "claude-fable-5-2",
    "mythos": "claude-mythos-5-2",
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
}
MTOK = 1_000_000


def projects_root() -> str:
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(base, "projects")


def encode_project(path: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(path))


def transcripts_for(project: Optional[str] = None, since: Optional[float] = None) -> List[str]:
    root = projects_root()
    pattern = os.path.join(root, encode_project(project), "*.jsonl") if project else os.path.join(root, "*", "*.jsonl")
    files = glob.glob(pattern)
    if project:
        files += glob.glob(os.path.join(root, encode_project(project), "*", "subagents", "*.jsonl"))
    if since:
        files = [f for f in files if os.path.getmtime(f) >= since]
    return sorted(set(files), key=os.path.getmtime)


def parse_since(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    m = re.fullmatch(r"(\d+)([hdw])", value.strip())
    if not m:
        raise ValueError("use a duration like 24h, 7d or 4w")
    seconds = int(m.group(1)) * {"h": 3600, "d": 86400, "w": 604800}[m.group(2)]
    return time.time() - seconds


def price_for(model: str, prices: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    if model in prices:
        return prices[model]
    for family, fallback in FAMILY_FALLBACK.items():
        if family in model and fallback in prices:
            return prices[fallback]
    return prices.get("claude-sonnet-5-5", {"input": 2.0, "output": 10.0})


@dataclass
class Usage:
    input: int = 0
    output: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    cache_read: int = 0
    thinking: int = 0
    requests: int = 0
    web_searches: int = 0

    def add(self, other: "Usage") -> None:
        for k in self.__dataclass_fields__:
            setattr(self, k, getattr(self, k) + getattr(other, k))

    @property
    def context_tokens(self) -> int:
        return self.input + self.cache_write_5m + self.cache_write_1h + self.cache_read

    @property
    def cache_hit_rate(self) -> float:
        total = self.context_tokens
        return self.cache_read / total if total else 0.0

    def cost(self, p: Dict[str, float]) -> float:
        inp = p.get("input", 0.0)
        return (
            self.input * inp
            + self.output * p.get("output", 0.0)
            + self.cache_write_5m * p.get("cache_write_5m", inp * CACHE_WRITE_5M)
            + self.cache_write_1h * p.get("cache_write_1h", inp * CACHE_WRITE_1H)
            + self.cache_read * p.get("cache_read", inp * CACHE_READ)
        ) / MTOK


def usage_from(raw: Dict[str, Any]) -> Usage:
    u = Usage(requests=1)
    u.input = int(raw.get("input_tokens") or 0)
    u.output = int(raw.get("output_tokens") or 0)
    u.cache_read = int(raw.get("cache_read_input_tokens") or 0)
    creation = raw.get("cache_creation") or {}
    if isinstance(creation, dict) and creation:
        u.cache_write_5m = int(creation.get("ephemeral_5m_input_tokens") or 0)
        u.cache_write_1h = int(creation.get("ephemeral_1h_input_tokens") or 0)
    else:
        u.cache_write_5m = int(raw.get("cache_creation_input_tokens") or 0)
    details = raw.get("output_tokens_details") or {}
    u.thinking = int(details.get("thinking_tokens") or 0) if isinstance(details, dict) else 0
    server = raw.get("server_tool_use") or {}
    u.web_searches = int(server.get("web_search_requests") or 0) if isinstance(server, dict) else 0
    return u


def iter_entries(path: str, offset: int = 0) -> Iterator[Tuple[Dict[str, Any], int]]:
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            for raw in fh:
                end = fh.tell()
                if not raw.endswith(b"\n"):
                    return
                try:
                    entry = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(entry, dict):
                    yield entry, end
    except OSError:
        return


@dataclass
class Report:
    files: int = 0
    sessions: set = field(default_factory=set)
    by_model: Dict[str, Usage] = field(default_factory=lambda: defaultdict(Usage))
    by_scope: Dict[str, Dict[str, Usage]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(Usage)))
    by_session: Dict[str, Dict[str, Usage]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(Usage)))
    by_day: Dict[str, Dict[str, Usage]] = field(default_factory=lambda: defaultdict(lambda: defaultdict(Usage)))
    tool_calls: Counter = field(default_factory=Counter)
    tool_output_chars: Counter = field(default_factory=Counter)
    largest_outputs: List[Tuple[int, str, str]] = field(default_factory=list)
    reads: Counter = field(default_factory=Counter)
    session_titles: Dict[str, str] = field(default_factory=dict)
    prices: Dict[str, Dict[str, float]] = field(default_factory=lambda: dict(DEFAULT_PRICES))

    def cost_of(self, table: Dict[str, Usage]) -> float:
        return sum(u.cost(price_for(m, self.prices)) for m, u in table.items())

    @property
    def total_cost(self) -> float:
        return self.cost_of(self.by_model)

    @property
    def total(self) -> Usage:
        t = Usage()
        for u in self.by_model.values():
            t.add(u)
        return t


def analyze(paths: Iterable[str], prices: Optional[Dict[str, Dict[str, float]]] = None) -> Report:
    report = Report()
    if prices:
        report.prices.update(prices)
    for path in paths:
        report.files += 1
        seen: Dict[str, Tuple[str, str, str, str, Usage]] = {}
        tool_names: Dict[str, Tuple[str, str]] = {}
        for entry, _ in iter_entries(path):
            session = str(entry.get("sessionId") or os.path.splitext(os.path.basename(path))[0])
            if entry.get("type") == "custom-title" and entry.get("customTitle"):
                report.session_titles[session] = str(entry["customTitle"])
            msg = entry.get("message")
            if not isinstance(msg, dict):
                continue
            scope = "subagent" if entry.get("isSidechain") or "/subagents/" in path else "main"
            if entry.get("type") == "assistant":
                model = str(msg.get("model") or "unknown")
                if model == "<synthetic>":
                    continue
                for block in msg.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = str(block.get("name"))
                        tool_names[str(block.get("id"))] = (name, _target(name, block.get("input") or {}))
                        report.tool_calls[name] += 1
                        if name == "Read":
                            fp = (block.get("input") or {}).get("file_path")
                            if fp and not (block.get("input") or {}).get("offset"):
                                report.reads[(session, fp)] += 1
                usage = msg.get("usage")
                if isinstance(usage, dict):
                    key = str(msg.get("id") or entry.get("uuid") or len(seen))
                    day = str(entry.get("timestamp") or "")[:10] or "unknown"
                    seen[key] = (model, scope, session, day, usage_from(usage))
            elif entry.get("type") == "user":
                content = msg.get("content")
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        size = len(json.dumps(block.get("content"), ensure_ascii=False))
                        name, target = tool_names.get(str(block.get("tool_use_id")), ("unknown", ""))
                        report.tool_output_chars[name] += size
                        report.largest_outputs.append((size, name, target))
        for model, scope, session, day, usage in seen.values():
            report.sessions.add(session)
            report.by_model[model].add(usage)
            report.by_scope[scope][model].add(usage)
            report.by_session[session][model].add(usage)
            report.by_day[day][model].add(usage)
    report.largest_outputs = sorted(report.largest_outputs, reverse=True)[:10]
    return report


def _target(name: str, tool_input: Dict[str, Any]) -> str:
    for key in ("file_path", "command", "pattern", "url", "query", "description"):
        if isinstance(tool_input.get(key), str):
            return tool_input[key][:120]
    return ""


@dataclass
class Advice:
    title: str
    detail: str
    fix: str
    saving: float = 0.0


def recommend(r: Report) -> List[Advice]:
    out: List[Advice] = []
    total = r.total
    cost = r.total_cost
    if not total.requests or cost <= 0:
        return out
    if total.context_tokens > 50_000 and total.cache_hit_rate < 0.6:
        out.append(
            Advice(
                "Low prompt-cache hit rate",
                f"{total.cache_hit_rate:.0%} of input tokens came from cache; well-cached Claude Code sessions reach 85-95%.",
                "Keep CLAUDE.md and settings stable during a session, avoid editing them mid-task, and prefer one long session over many short restarts.",
                cost * 0.15,
            )
        )
    read_cost = (
        sum(
            u.cache_read * price_for(m, r.prices).get("cache_read", price_for(m, r.prices).get("input", 0) * CACHE_READ)
            for m, u in r.by_model.items()
        )
        / MTOK
    )
    avg_context = total.context_tokens / total.requests
    if avg_context > 120_000 and read_cost > 0.35 * cost:
        out.append(
            Advice(
                "Large context on every request",
                f"Requests carried {avg_context / 1000:.0f}k tokens of context on average; re-reading it cost {money(read_cost)} ({read_cost / cost:.0%} of spend).",
                "Use /clear between unrelated tasks, compact earlier (harness optimize --profile lean sets CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=70), and give wide reading to explorer subagents so it never enters the main context.",
                read_cost * 0.3,
            )
        )
    sub = r.by_scope.get("subagent", {})
    sub_cost = r.cost_of(sub)
    expensive_sub = {m: u for m, u in sub.items() if price_for(m, r.prices).get("output", 0) >= 20}
    if expensive_sub and sub_cost > 0.15 * cost:
        exp_cost = r.cost_of(expensive_sub)
        out.append(
            Advice(
                "Subagents run on a premium model",
                f"Subagents cost ${sub_cost:.2f} ({sub_cost / cost:.0%} of spend), ${exp_cost:.2f} of it on {', '.join(sorted(expensive_sub))}.",
                "Route reading-heavy subagents to a cheaper model: `harness optimize --apply` sets subagents.models, or add `model: haiku` / `model: sonnet` to agent files.",
                exp_cost * 0.6,
            )
        )
    tool_chars = sum(r.tool_output_chars.values())
    if tool_chars > 400_000:
        top = ", ".join(f"{n} {c / 1000:.0f}k chars" for n, c in r.tool_output_chars.most_common(3))
        out.append(
            Advice(
                "Large tool outputs",
                f"Tool results added {tool_chars / 1000:.0f}k characters to context ({top}). Every later request re-reads them.",
                "Enable the output guards (on by default in harness policy), lower BASH_MAX_OUTPUT_LENGTH, and Grep before Read.",
                cost * 0.10,
            )
        )
    repeats = sum(n - 1 for n in r.reads.values() if n > 1)
    if repeats >= 5:
        out.append(
            Advice(
                "Repeated full-file reads",
                f"{repeats} full reads of files already read in the same session.",
                "Keep cost.read_dedupe on: the harness refuses unchanged re-reads and tells Claude the file is still in context.",
                cost * min(0.08, repeats * 0.004),
            )
        )
    if total.output and total.thinking / max(total.output, 1) > 0.75 and cost > 1:
        out.append(
            Advice(
                "Most output tokens are thinking",
                f"{total.thinking / total.output:.0%} of output tokens were thinking.",
                "Use a lower effort level for routine work (CLAUDE_CODE_EFFORT_LEVEL=medium, or /effort) and keep high effort for hard problems.",
                cost * 0.10,
            )
        )
    premium = {m: u for m, u in r.by_model.items() if price_for(m, r.prices).get("output", 0) >= 40}
    if premium and r.cost_of(premium) > 0.5 * cost:
        out.append(
            Advice(
                "Premium-tier model for most work",
                f"{r.cost_of(premium) / cost:.0%} of spend is on {', '.join(sorted(premium))}.",
                "Use Opus or Sonnet as the default model and switch to the premium tier only for the hardest tasks.",
                r.cost_of(premium) * 0.4,
            )
        )
    if total.web_searches > 50:
        out.append(
            Advice(
                "Many web searches",
                f"{total.web_searches} web searches.",
                "Cap them with CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION (harness optimize sets 40).",
                0.0,
            )
        )
    return sorted(out, key=lambda a: -a.saving)


class Meter:
    def __init__(self, prices: Optional[Dict[str, Dict[str, float]]] = None):
        self.prices = dict(DEFAULT_PRICES)
        if prices:
            self.prices.update(prices)

    def update(self, state: Dict[str, Any], transcript: Optional[str]) -> float:
        if not transcript or not os.path.isfile(transcript):
            return float(state.get("cost_usd", 0.0))
        if state.get("transcript") != transcript:
            state["transcript"], state["transcript_offset"], state["cost_usd"], state["cost_ids"] = transcript, 0, 0.0, []
        seen = set(state.get("cost_ids", []))
        offset = int(state.get("transcript_offset", 0))
        total = float(state.get("cost_usd", 0.0))
        for entry, end in iter_entries(transcript, offset):
            offset = end
            msg = entry.get("message")
            if entry.get("type") != "assistant" or not isinstance(msg, dict) or not isinstance(msg.get("usage"), dict):
                continue
            mid = str(msg.get("id") or entry.get("uuid"))
            if mid in seen:
                continue
            seen.add(mid)
            total += usage_from(msg["usage"]).cost(price_for(str(msg.get("model")), self.prices))
        state["transcript_offset"] = offset
        state["cost_usd"] = round(total, 6)
        state["cost_ids"] = list(seen)[-500:]
        return total


def money(v: float) -> str:
    return f"${v:,.2f}" if v >= 0.01 or v == 0 else f"${v:.4f}"


def tokens(n: int) -> str:
    for unit, size in (("B", 1e9), ("M", 1e6), ("k", 1e3)):
        if n >= size:
            return f"{n / size:.1f}{unit}"
    return str(n)


def render(r: Report, top_sessions: int = 5) -> str:
    total = r.total
    lines = [
        f"{len(r.sessions)} session(s), {r.files} transcript file(s), {total.requests} requests",
        f"Estimated cost: {money(r.total_cost)}   cache hit rate: {total.cache_hit_rate:.0%}   "
        f"input {tokens(total.input)}  cache write {tokens(total.cache_write_5m + total.cache_write_1h)}  "
        f"cache read {tokens(total.cache_read)}  output {tokens(total.output)} (thinking {tokens(total.thinking)})",
        "",
        "By model",
    ]
    for model, u in sorted(r.by_model.items(), key=lambda kv: -kv[1].cost(price_for(kv[0], r.prices))):
        lines.append(f"  {model:<22} {money(u.cost(price_for(model, r.prices))):>10}  {u.requests:>6} req  out {tokens(u.output):>7}")
    lines += ["", "Main session vs subagents"]
    for scope in ("main", "subagent"):
        if scope in r.by_scope:
            lines.append(f"  {scope:<22} {money(r.cost_of(r.by_scope[scope])):>10}")
    if r.by_session:
        lines += ["", "Most expensive sessions"]
        ranked = sorted(r.by_session.items(), key=lambda kv: -r.cost_of(kv[1]))[:top_sessions]
        for sid, table in ranked:
            title = r.session_titles.get(sid, "")
            lines.append(f"  {sid[:8]}  {money(r.cost_of(table)):>10}  {title[:60]}")
    if r.tool_output_chars:
        lines += ["", "Tool output added to context"]
        for name, chars in r.tool_output_chars.most_common(6):
            lines.append(f"  {name:<22} {tokens(chars):>8} chars  {r.tool_calls.get(name, 0):>5} calls")
    advice = recommend(r)
    if advice:
        lines += ["", "Recommendations (largest estimated saving first)"]
        for i, a in enumerate(advice, 1):
            saving = f" (~{money(a.saving)})" if a.saving else ""
            lines += [f"  {i}. {a.title}{saving}", f"     {a.detail}", f"     Fix: {a.fix}"]
    return "\n".join(lines)


def to_json(r: Report) -> str:
    def table(t: Dict[str, Usage]) -> Dict[str, Any]:
        return {m: {**u.__dict__, "cost_usd": round(u.cost(price_for(m, r.prices)), 6)} for m, u in t.items()}

    return json.dumps(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sessions": len(r.sessions),
            "files": r.files,
            "cost_usd": round(r.total_cost, 6),
            "cache_hit_rate": round(r.total.cache_hit_rate, 4),
            "by_model": table(r.by_model),
            "by_scope": {s: table(t) for s, t in r.by_scope.items()},
            "by_day": {d: round(r.cost_of(t), 6) for d, t in sorted(r.by_day.items())},
            "tool_output_chars": dict(r.tool_output_chars),
            "recommendations": [a.__dict__ for a in recommend(r)],
        },
        indent=2,
    )
