from __future__ import annotations

import contextlib
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional

from .secrets import redact_text

try:
    import fcntl

    def _lock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)

    def _unlock(fh) -> None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

except ImportError:
    import msvcrt

    def _lock(fh) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(fh) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@contextlib.contextmanager
def locked(path: str) -> Iterator[None]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "a+") as fh:
        _lock(fh)
        try:
            yield
        finally:
            _unlock(fh)


def _atomic_write(path: str, text: str) -> None:
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


class AuditLog:
    MAX_FIELD = 500

    def __init__(self, path: str, max_bytes: int = 5_000_000, keep: int = 3, enabled: bool = True):
        self.path = path
        self.max_bytes = max_bytes
        self.keep = max(0, keep)
        self.enabled = enabled

    @classmethod
    def for_policy(cls, policy) -> "AuditLog":
        audit = policy.data.get("audit", {})
        path = audit.get("path", ".claude/harness/audit.jsonl")
        if not os.path.isabs(path):
            path = os.path.join(policy.project, path)
        enabled = audit.get("enabled", True) and not os.environ.get("HARNESS_AUDIT_DISABLED")
        return cls(path, audit.get("max_bytes", 5_000_000), audit.get("keep", 3), enabled)

    def _clean(self, value: Any) -> Any:
        if isinstance(value, str):
            return redact_text(value, max_len=self.MAX_FIELD)
        if isinstance(value, dict):
            return {k: self._clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._clean(v) for v in value[:50]]
        return value

    def _rotate(self) -> None:
        if self.keep == 0:
            os.remove(self.path)
            return
        for i in range(self.keep - 1, 0, -1):
            src = f"{self.path}.{i}"
            if os.path.exists(src):
                os.replace(src, f"{self.path}.{i + 1}")
        os.replace(self.path, f"{self.path}.1")

    def write(self, record: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        entry = {"ts": now_iso()}
        entry.update({k: self._clean(v) for k, v in record.items() if v is not None})
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        with locked(self.path):
            try:
                if os.path.getsize(self.path) + len(line) > self.max_bytes:
                    self._rotate()
            except OSError:
                pass
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(line)

    def read(self, include_rotated: bool = False) -> List[Dict[str, Any]]:
        paths = [self.path]
        if include_rotated:
            paths = [f"{self.path}.{i}" for i in range(self.keep, 0, -1)] + paths
        out: List[Dict[str, Any]] = []
        for p in paths:
            if not os.path.exists(p):
                continue
            with open(p, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return out


_SAFE_ID = re.compile(r"[^A-Za-z0-9_.-]")


class SessionState:
    def __init__(self, harness_dir: str, session_id: Optional[str]):
        sid = _SAFE_ID.sub("_", session_id or "default")[:128]
        self.path = os.path.join(harness_dir, "state", f"{sid}.json")
        self.session_id = session_id or "default"

    def load(self) -> Dict[str, Any]:
        try:
            with open(self.path, encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError):
            pass
        return {
            "session_id": self.session_id,
            "started_at": now_iso(),
            "tool_calls": 0,
            "denied": 0,
            "asked": 0,
            "failures": 0,
            "edited_files": [],
            "stop_blocks": 0,
        }

    @contextlib.contextmanager
    def update(self) -> Iterator[Dict[str, Any]]:
        with locked(self.path):
            data = self.load()
            yield data
            data["updated_at"] = now_iso()
            _atomic_write(self.path, json.dumps(data, indent=2))

    @staticmethod
    def prune(harness_dir: str, max_age_days: int = 14) -> int:
        state_dir = os.path.join(harness_dir, "state")
        if not os.path.isdir(state_dir):
            return 0
        cutoff = time.time() - max_age_days * 86400
        removed = 0
        for name in os.listdir(state_dir):
            p = os.path.join(state_dir, name)
            try:
                if os.path.getmtime(p) < cutoff:
                    os.remove(p)
                    removed += 1
            except OSError:
                continue
        return removed
