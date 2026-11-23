"""Secret detection and redaction.

Used in three places:

* before Claude writes or edits a file (block credentials landing in code),
* on prompts and Bash commands (warn when a live key is about to enter the
  transcript or a shell history),
* by ``harness scan`` for files, directories and staged git changes.

High-confidence detectors match provider-specific formats. The generic
detector looks for ``key = "value"`` assignments and only reports values
with enough entropy that do not look like placeholders.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Pattern, Sequence

HIGH = "high"
MEDIUM = "medium"


@dataclass(frozen=True)
class Detector:
    id: str
    title: str
    pattern: Pattern[str]
    confidence: str = HIGH
    group: int = 0  # regex group holding the secret value


@dataclass(frozen=True)
class Finding:
    detector: str
    title: str
    confidence: str
    line: int
    column: int
    preview: str  # redacted
    path: Optional[str] = None

    def describe(self) -> str:
        where = f"{self.path}:{self.line}" if self.path else f"line {self.line}"
        return f"{self.title} ({self.preview}) at {where}"


def _d(id_: str, title: str, regex: str, confidence: str = HIGH, group: int = 0, flags: int = 0) -> Detector:
    return Detector(id_, title, re.compile(regex, flags), confidence, group)


DETECTORS: Sequence[Detector] = (
    _d("private-key", "Private key block", r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"),
    _d("aws-access-key-id", "AWS access key ID", r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b"),
    _d(
        "aws-secret-access-key",
        "AWS secret access key",
        r"(?i)aws_?secret_?access_?key['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})(?![A-Za-z0-9/+=])",
        group=1,
    ),
    _d("github-token", "GitHub token", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36,255}\b"),
    _d("github-fine-grained-pat", "GitHub fine-grained token", r"\bgithub_pat_[A-Za-z0-9_]{22,255}\b"),
    _d("anthropic-api-key", "Anthropic API key", r"\bsk-ant-(?:api|admin|oat|sid)\d{2}-[A-Za-z0-9_\-]{20,}"),
    _d("openai-api-key", "OpenAI API key", r"\bsk-(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{40,}"),
    _d("openai-legacy-key", "OpenAI API key", r"\bsk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}\b"),
    _d("slack-token", "Slack token", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    _d(
        "slack-webhook",
        "Slack webhook URL",
        r"https://hooks\.slack\.com/services/T[A-Z0-9]{6,}/B[A-Z0-9]{6,}/[A-Za-z0-9]{20,}",
    ),
    _d("stripe-live-key", "Stripe live key", r"\b(?:sk|rk)_live_[A-Za-z0-9]{20,}\b"),
    _d("stripe-webhook-secret", "Stripe webhook secret", r"\bwhsec_[A-Za-z0-9]{24,}\b"),
    _d("google-api-key", "Google API key", r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    _d("gitlab-token", "GitLab token", r"\bglpat-[A-Za-z0-9_\-]{20,}\b"),
    _d("npm-token", "npm token", r"\bnpm_[A-Za-z0-9]{36}\b"),
    _d("pypi-token", "PyPI token", r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_\-]{50,}"),
    _d("huggingface-token", "Hugging Face token", r"\bhf_[A-Za-z0-9]{34,}\b"),
    _d("sendgrid-key", "SendGrid API key", r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b"),
    _d("twilio-key", "Twilio API key", r"\bSK[0-9a-fA-F]{32}\b", MEDIUM),
    _d("discord-bot-token", "Discord bot token", r"\b[MN][A-Za-z\d]{23,25}\.[\w-]{6}\.[\w-]{27,38}\b", MEDIUM),
    _d("telegram-bot-token", "Telegram bot token", r"\b\d{8,10}:AA[A-Za-z0-9_\-]{33}\b"),
    _d(
        "jwt",
        "JSON Web Token",
        r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}",
        MEDIUM,
    ),
    _d(
        "connection-string-password",
        "Password in connection string",
        r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|rediss|amqps?|mssql)://[^:\s/@]+:([^@\s]{6,})@",
        MEDIUM,
        group=1,
    ),
    _d(
        "generic-assignment",
        "Hard-coded credential",
        r"(?i)\b[A-Za-z0-9_]*(?:api[_-]?key|secret|token|passwd|password|private[_-]?key|access[_-]?key)"
        r"[A-Za-z0-9_]*['\"]?\s*[:=]\s*['\"]([^'\"\s]{12,})['\"]",
        MEDIUM,
        group=1,
    ),
)

_PLACEHOLDER = re.compile(
    r"(?i)(example|sample|dummy|placeholder|changeme|change_me|your[_-]|my[_-]?(api|secret|token)|"
    r"xxxx|\*\*\*|redacted|<[^>]*>|\$\{|\{\{|%\(|process\.env|os\.environ|getenv|fake|test[_-]?(key|token|secret)|"
    r"not[_-]?a[_-]?real|0000000000|1234567890|abcdefghij)"
)

# Published documentation keys that are safe by definition.
_KNOWN_SAFE = {
    "AKIAIOSFODNN7EXAMPLE",
    "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
}


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def redact(value: str, keep: int = 4) -> str:
    """``sk-ant-api03-abcdef...`` -> ``sk-a…(108 chars)``."""
    if len(value) <= keep:
        return "…"
    return f"{value[:keep]}…({len(value)} chars)"


def _is_placeholder(value: str) -> bool:
    if value in _KNOWN_SAFE:
        return True
    if _PLACEHOLDER.search(value):
        return True
    if len(set(value)) <= 3:  # "aaaaaaaaaaaa", "------------"
        return True
    return False


def scan_text(
    text: str,
    path: Optional[str] = None,
    allow_patterns: Iterable[str] = (),
    min_confidence: str = MEDIUM,
) -> List[Finding]:
    """Return secrets found in ``text``. Values are never returned in clear."""
    allow = [re.compile(p) for p in allow_patterns]
    findings: List[Finding] = []
    seen_spans = []
    # Precompute line starts for line/column numbers.
    line_starts = [0]
    for m in re.finditer("\n", text):
        line_starts.append(m.end())

    def locate(pos: int):
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, pos - line_starts[lo] + 1

    for det in DETECTORS:
        if min_confidence == HIGH and det.confidence != HIGH:
            continue
        for m in det.pattern.finditer(text):
            value = m.group(det.group) if det.group else m.group(0)
            start = m.start(det.group) if det.group else m.start()
            end = start + len(value)
            if any(s <= start < e or s < end <= e for s, e in seen_spans):
                continue  # already reported by a more specific detector
            if det.id != "private-key" and _is_placeholder(value):
                continue
            if any(a.search(value) or a.search(m.group(0)) for a in allow):
                continue
            if det.id == "generic-assignment":
                if shannon_entropy(value) < 3.3 or value.isalpha() or value.isdigit():
                    continue
                if "/" in value and value.count("/") >= 2 and " " not in value and "." in value:
                    continue  # paths and URLs
            line, col = locate(start)
            findings.append(Finding(det.id, det.title, det.confidence, line, col, redact(value), path))
            seen_spans.append((start, end))
    findings.sort(key=lambda f: (f.line, f.column))
    return findings


def redact_text(text: str, max_len: Optional[int] = None) -> str:
    """Replace every detected secret in ``text`` with a redacted preview."""
    out = text
    for det in DETECTORS:

        def _sub(m, det=det):
            value = m.group(det.group) if det.group else m.group(0)
            if det.id != "private-key" and _is_placeholder(value):
                return m.group(0)
            return m.group(0).replace(value, "[REDACTED:" + det.id + "]")

        out = det.pattern.sub(_sub, out)
    if max_len is not None and len(out) > max_len:
        out = out[: max_len - 1] + "…"
    return out


# --------------------------------------------------------------------------
# File scanning
# --------------------------------------------------------------------------

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
    ".tox",
    "target",
    ".idea",
    ".gradle",
}
MAX_FILE_BYTES = 2_000_000


def is_binary(chunk: bytes) -> bool:
    if b"\x00" in chunk:
        return True
    if not chunk:
        return False
    text_chars = bytes(range(32, 127)) + b"\n\r\t\f\b"
    nontext = chunk.translate(None, text_chars)
    return len(nontext) / len(chunk) > 0.30


def iter_files(paths: Iterable[str]) -> Iterator[str]:
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
                for f in sorted(files):
                    yield os.path.join(root, f)
        elif os.path.isfile(p):
            yield p


def scan_file(path: str, allow_patterns: Iterable[str] = (), min_confidence: str = MEDIUM) -> List[Finding]:
    try:
        size = os.path.getsize(path)
        if size > MAX_FILE_BYTES:
            return []
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return []
    if is_binary(data[:4096]):
        return []
    text = data.decode("utf-8", errors="replace")
    return scan_text(text, path=path, allow_patterns=allow_patterns, min_confidence=min_confidence)
