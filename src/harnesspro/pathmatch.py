from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Iterable, List, Optional, Pattern, Tuple


@lru_cache(maxsize=1024)
def glob_to_regex(pattern: str) -> Pattern[str]:
    i, n = 0, len(pattern)
    out: List[str] = []
    while i < n:
        c = pattern[i]
        if c == "*":
            if pattern[i : i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
                continue
            if pattern[i : i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif c == "?":
            out.append("[^/]")
        elif c == "[":
            j = pattern.find("]", i + 1)
            if j < 0:
                out.append(re.escape(c))
            else:
                body = pattern[i + 1 : j]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = j
        else:
            out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


class PathMatcher:
    def __init__(self, patterns: Iterable[str], home: Optional[str] = None):
        self.home = home or os.path.expanduser("~")
        self.rules: List[Tuple[bool, str, str]] = []
        for raw in patterns:
            p = raw.strip()
            if not p or p.startswith("#"):
                continue
            neg = p.startswith("!")
            if neg:
                p = p[1:]
            if p.startswith("~/"):
                p = _normalize(self.home) + p[1:]
            if p.startswith("/"):
                kind = "abs"
            elif "/" not in p.rstrip("/"):
                kind = "name"
            else:
                kind = "rel"
            self.rules.append((neg, kind, p.rstrip("/") if kind == "name" else p))

    def _candidates(self, abs_path: str, project: str) -> Tuple[str, List[str], Optional[str]]:
        abs_path = _normalize(abs_path)
        abs_forms = [abs_path]
        try:
            real = _normalize(os.path.realpath(abs_path))
            if real != abs_path:
                abs_forms.append(real)
        except OSError:
            pass
        rel = None
        proj = _normalize(os.path.abspath(project)).rstrip("/") + "/"
        for form in abs_forms:
            if form.startswith(proj):
                rel = form[len(proj) :]
                break
        return os.path.basename(abs_path.rstrip("/")), abs_forms, rel

    def match(self, abs_path: str, project: str) -> Optional[str]:
        name, abs_forms, rel = self._candidates(abs_path, project)
        decided: Optional[str] = None
        for neg, kind, p in self.rules:
            rx = glob_to_regex(p)
            if kind == "name":
                hit = bool(rx.match(name))
            elif kind == "abs":
                hit = any(rx.match(f) for f in abs_forms)
            else:
                hit = (rel is not None and bool(rx.match(rel))) or (p.startswith("**/") and any(rx.match(f.lstrip("/")) for f in abs_forms))
            if hit:
                decided = None if neg else p
        return decided

    def matches(self, abs_path: str, project: str) -> bool:
        return self.match(abs_path, project) is not None


def resolve(path: str, cwd: str) -> str:
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.normpath(path)


def is_inside(path: str, root: str) -> bool:
    path = os.path.normpath(path)
    root = os.path.normpath(root)
    for p in {path, os.path.realpath(path)}:
        for r in {root, os.path.realpath(root)}:
            if p == r or p.startswith(r.rstrip(os.sep) + os.sep):
                return True
    return False
