from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional


def _git(args: List[str], cwd: str, timeout: float = 3.0) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


@dataclass
class GitStatus:
    branch: str = ""
    ahead: int = 0
    behind: int = 0
    staged: int = 0
    modified: int = 0
    untracked: int = 0
    conflicted: int = 0
    changed_files: List[str] = field(default_factory=list)

    @property
    def dirty(self) -> bool:
        return bool(self.staged or self.modified or self.untracked or self.conflicted)

    def summary(self) -> str:
        parts = [self.branch or "(detached)"]
        if self.ahead or self.behind:
            parts.append(f"ahead {self.ahead}, behind {self.behind}")
        counts = []
        for label, n in (
            ("staged", self.staged),
            ("modified", self.modified),
            ("untracked", self.untracked),
            ("conflicted", self.conflicted),
        ):
            if n:
                counts.append(f"{n} {label}")
        parts.append(", ".join(counts) if counts else "clean")
        return " | ".join(parts)


def is_repo(cwd: str) -> bool:
    return _git(["rev-parse", "--is-inside-work-tree"], cwd) is not None


def status(cwd: str) -> Optional[GitStatus]:
    out = _git(["status", "--porcelain=v2", "--branch", "--untracked-files=normal"], cwd)
    if out is None:
        return None
    st = GitStatus()
    for line in out.splitlines():
        if line.startswith("# branch.head "):
            st.branch = line.split(" ", 2)[2]
        elif line.startswith("# branch.ab "):
            _, _, a, b = line.split(" ")
            st.ahead, st.behind = int(a.lstrip("+")), abs(int(b))
        elif line.startswith(("1 ", "2 ")):
            fields = line.split(" ", 8 if line[0] == "1" else 9)
            xy = fields[1]
            if xy[0] != ".":
                st.staged += 1
            if xy[1] != ".":
                st.modified += 1
            st.changed_files.append(fields[-1].split("\t")[0])
        elif line.startswith("u "):
            st.conflicted += 1
            st.changed_files.append(line.split(" ", 10)[-1])
        elif line.startswith("? "):
            st.untracked += 1
            st.changed_files.append(line[2:])
    return st


def recent_commits(cwd: str, n: int = 5) -> List[str]:
    out = _git(["log", f"-{max(1, n)}", "--pretty=format:%h %s (%cr)"], cwd)
    return out.splitlines() if out else []


def staged_files(cwd: str) -> List[str]:
    out = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd)
    if not out:
        return []
    return [p for p in out.split("\0") if p]


def root(cwd: str) -> Optional[str]:
    out = _git(["rev-parse", "--show-toplevel"], cwd)
    return out.strip() if out else None
