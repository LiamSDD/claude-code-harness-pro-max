"""Session-to-session handoff for long-running work.

Each Claude Code session starts with an empty context. Following Anthropic's
"effective harnesses for long-running agents" pattern, the harness keeps two
files that outlive any session:

``.claude/harness/features.json``
    The work broken into features, each with a status and a ``passes`` flag
    that only flips to true once the feature has been verified end to end.

``.claude/harness/progress.md``
    An append-only log of what each session did, decided and left next.

The SessionStart hook injects a summary of both, so a fresh session (or one
resumed after compaction) knows where to pick up.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from .store import _atomic_write, locked, now_iso

STATUSES = ("todo", "in_progress", "blocked", "done")


class ProgressError(ValueError):
    pass


class Progress:
    def __init__(self, harness_dir: str):
        self.dir = harness_dir
        self.features_path = os.path.join(harness_dir, "features.json")
        self.log_path = os.path.join(harness_dir, "progress.md")

    # -- features ---------------------------------------------------------

    def load(self) -> Dict[str, Any]:
        try:
            with open(self.features_path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return {"version": 1, "features": []}
        except json.JSONDecodeError as exc:
            raise ProgressError(f"{self.features_path} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("features"), list):
            raise ProgressError(f"{self.features_path} must contain an object with a 'features' array")
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        os.makedirs(self.dir, exist_ok=True)
        _atomic_write(self.features_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def features(self) -> List[Dict[str, Any]]:
        return self.load()["features"]

    def add(self, title: str, steps: Optional[List[str]] = None, priority: int = 2) -> Dict[str, Any]:
        title = title.strip()
        if not title:
            raise ProgressError("feature title is empty")
        with locked(self.features_path):
            data = self.load()
            next_id = max([f.get("id", 0) for f in data["features"]] + [0]) + 1
            feature = {
                "id": next_id,
                "title": title,
                "status": "todo",
                "passes": False,
                "priority": priority,
                "steps": steps or [],
                "notes": "",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            data["features"].append(feature)
            self._save(data)
        return feature

    def _find(self, data: Dict[str, Any], feature_id: int) -> Dict[str, Any]:
        for f in data["features"]:
            if f.get("id") == feature_id:
                return f
        raise ProgressError(f"no feature with id {feature_id}")

    def set_status(self, feature_id: int, status: str, note: str = "", passes: Optional[bool] = None) -> Dict[str, Any]:
        if status not in STATUSES:
            raise ProgressError(f"status must be one of {', '.join(STATUSES)}")
        with locked(self.features_path):
            data = self.load()
            f = self._find(data, feature_id)
            f["status"] = status
            if passes is not None:
                f["passes"] = passes
            elif status == "done":
                f["passes"] = True
            elif status != "done":
                f["passes"] = False
            if note:
                f["notes"] = note
            f["updated_at"] = now_iso()
            self._save(data)
        return f

    def next_feature(self) -> Optional[Dict[str, Any]]:
        open_ = [f for f in self.features() if not f.get("passes")]
        if not open_:
            return None
        order = {"in_progress": 0, "todo": 1, "blocked": 2, "done": 3}
        return sorted(open_, key=lambda f: (order.get(f.get("status"), 9), f.get("priority", 2), f.get("id", 0)))[0]

    def counts(self) -> Dict[str, int]:
        feats = self.features()
        out = {s: 0 for s in STATUSES}
        for f in feats:
            out[f.get("status", "todo")] = out.get(f.get("status", "todo"), 0) + 1
        out["total"] = len(feats)
        out["passing"] = sum(1 for f in feats if f.get("passes"))
        return out

    # -- log --------------------------------------------------------------

    def note(self, text: str, session_id: Optional[str] = None, heading: Optional[str] = None) -> None:
        text = text.strip()
        if not text:
            raise ProgressError("note is empty")
        os.makedirs(self.dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        title = heading or "Note"
        sid = f" · session {session_id[:8]}" if session_id else ""
        entry = f"\n### {stamp} · {title}{sid}\n\n{text}\n"
        with locked(self.log_path):
            new = not os.path.exists(self.log_path)
            with open(self.log_path, "a", encoding="utf-8") as fh:
                if new:
                    fh.write("# Progress log\n\nAppend-only. Newest entries at the bottom.\n")
                fh.write(entry)

    def tail(self, max_chars: int = 2500) -> str:
        try:
            with open(self.log_path, encoding="utf-8") as fh:
                text = fh.read()
        except FileNotFoundError:
            return ""
        start = text.find("\n### ")
        if start < 0:
            return ""  # only the header, no entries yet
        text = text[start + 1 :]
        if len(text) <= max_chars:
            return text.strip()
        cut = text[-max_chars:]
        idx = cut.find("\n### ")
        return ("…\n" + (cut[idx + 1 :] if idx >= 0 else cut)).strip()

    # -- summary for SessionStart -------------------------------------------

    def summary(self, max_chars: int = 3500) -> str:
        try:
            feats = self.features()
        except ProgressError as exc:
            return f"Feature list unreadable: {exc}"
        parts: List[str] = []
        if feats:
            c = self.counts()
            parts.append(f"Features: {c['passing']}/{c['total']} passing ({c['in_progress']} in progress, {c['blocked']} blocked).")
            nxt = self.next_feature()
            if nxt:
                parts.append(f"Next: #{nxt['id']} {nxt['title']} [{nxt['status']}]")
                for s in nxt.get("steps", [])[:8]:
                    parts.append(f"  - {s}")
        log = self.tail(max_chars=max(500, max_chars - sum(len(p) for p in parts)))
        if log:
            parts.append("Recent progress log:\n" + log)
        return "\n".join(parts)
