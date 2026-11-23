from __future__ import annotations

import copy
import json
import os
import shutil
import time
from typing import Any, Dict, List, Tuple


def _hook_commands(group: Dict[str, Any]) -> List[str]:
    return [h.get("command", "") for h in group.get("hooks", []) if isinstance(h, dict)]


def merge_hooks(existing: Dict[str, Any], fragment: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    out = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    added = 0
    for event, groups in fragment.items():
        current = out.setdefault(event, [])
        for group in groups:
            wanted = set(_hook_commands(group))
            present = set()
            for g in current:
                present.update(_hook_commands(g))
            if wanted and wanted <= present:
                continue
            same_matcher = next((g for g in current if g.get("matcher", "") == group.get("matcher", "")), None)
            if same_matcher is not None:
                for h in group.get("hooks", []):
                    if h.get("command") not in present:
                        same_matcher.setdefault("hooks", []).append(copy.deepcopy(h))
                        added += 1
            else:
                current.append(copy.deepcopy(group))
                added += len(group.get("hooks", []))
    return out, added


def merge_permissions(existing: Dict[str, Any], fragment: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    out = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    added = 0
    for key in ("allow", "ask", "deny"):
        if key not in fragment:
            continue
        current = out.setdefault(key, [])
        for rule in fragment[key]:
            if rule not in current:
                current.append(rule)
                added += 1
    for key, value in fragment.items():
        if key not in ("allow", "ask", "deny") and key not in out:
            out[key] = copy.deepcopy(value)
            added += 1
    return out, added


def merge_settings(existing: Dict[str, Any], fragment: Dict[str, Any], force: bool = False) -> Tuple[Dict[str, Any], List[str]]:
    out = copy.deepcopy(existing)
    changes: List[str] = []
    for key, value in fragment.items():
        if key == "hooks":
            out["hooks"], n = merge_hooks(out.get("hooks", {}), value)
            if n:
                changes.append(f"added {n} hook handler{'s' if n != 1 else ''}")
        elif key == "permissions":
            out["permissions"], n = merge_permissions(out.get("permissions", {}), value)
            if n:
                changes.append(f"added {n} permission rule{'s' if n != 1 else ''}")
        elif key == "env" and isinstance(value, dict):
            env = out.setdefault("env", {})
            for k, v in value.items():
                if k not in env:
                    env[k] = v
                    changes.append(f"set env {k}")
        elif key not in out or force:
            if out.get(key) != value:
                out[key] = copy.deepcopy(value)
                changes.append(f"set {key}")
    return out, changes


def load(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if not text.strip():
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be an object")
    return data


def write(path: str, data: Dict[str, Any], backup: bool = True) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if backup and os.path.exists(path):
        shutil.copy2(path, f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
