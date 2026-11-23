from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from . import gitinfo
from .config import harness_dir, load_policy
from .progress import Progress, ProgressError
from .store import SessionState

RESET = "\033[0m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"


def _color(enabled: bool, code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if enabled else text


def _get(d: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    node: Any = d
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return default
        node = node.get(part)
    return default if node is None else node


def _duration(ms: Optional[float]) -> str:
    if not ms:
        return ""
    minutes = int(ms // 60000)
    if minutes < 1:
        return f"{int(ms // 1000)}s"
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h{minutes % 60:02d}m"


def render(data: Dict[str, Any], color: Optional[bool] = None) -> str:
    if color is None:
        color = not os.environ.get("NO_COLOR")
    sep = _color(color, DIM, " · ")
    cwd = _get(data, "workspace.project_dir") or _get(data, "workspace.current_dir") or data.get("cwd") or os.getcwd()
    parts: List[str] = []

    st = gitinfo.status(cwd)
    if st is not None:
        branch = st.branch or "detached"
        mark = "*" if st.dirty else ""
        arrows = ""
        if st.ahead:
            arrows += f" ↑{st.ahead}"
        if st.behind:
            arrows += f" ↓{st.behind}"
        parts.append(_color(color, CYAN, f"{branch}{mark}{arrows}"))
    else:
        parts.append(_color(color, CYAN, os.path.basename(cwd.rstrip("/")) or cwd))

    model = _get(data, "model.display_name")
    if model:
        parts.append(str(model))

    pct = _get(data, "context_window.used_percentage")
    if isinstance(pct, (int, float)):
        code = GREEN if pct < 50 else YELLOW if pct < 80 else RED
        parts.append(_color(color, code, f"ctx {int(round(pct))}%"))

    cost = _get(data, "cost.total_cost_usd")
    if isinstance(cost, (int, float)) and cost > 0:
        parts.append(f"${cost:.2f}")

    dur = _duration(_get(data, "cost.total_duration_ms"))
    if dur:
        parts.append(dur)

    hdir = harness_dir(cwd)
    if os.path.isdir(hdir):
        state = SessionState(hdir, data.get("session_id")).load()
        denied = state.get("denied", 0)
        saved = state.get("saved_calls", 0)
        if denied - saved > 0:
            parts.append(_color(color, YELLOW, f"guard {denied - saved} blocked"))
        if saved:
            parts.append(_color(color, GREEN, f"saved {saved} calls"))
        budget = float(load_policy(cwd).get("cost.session_budget_usd") or 0)
        if budget > 0:
            spent = float(cost if isinstance(cost, (int, float)) else state.get("cost_usd", 0.0))
            code = GREEN if spent < budget * 0.8 else YELLOW if spent < budget else RED
            parts.append(_color(color, code, f"budget ${spent:.2f}/${budget:.2f}"))
        try:
            counts = Progress(hdir).counts()
            if counts["total"]:
                parts.append(f"{counts['passing']}/{counts['total']} features")
        except ProgressError:
            pass

    return sep.join(parts)


def main_from_stdin(stdin_text: str) -> str:
    try:
        data = json.loads(stdin_text) if stdin_text.strip() else {}
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return render(data)
