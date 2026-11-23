from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Iterable, List, Pattern, Tuple

from . import secrets as secretlib
from .config import LoadedPolicy, load_defaults
from .policy import ASK, DENY, Context, evaluate_bash

HIGH, MEDIUM, INFO = "high", "medium", "info"
SUPPRESS_MARKER = "harness-vet: " + "ignore"
_ORDER = {HIGH: 0, MEDIUM: 1, INFO: 2}

TEXT_EXTS = {
    ".md",
    ".markdown",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".sh",
    ".bash",
    ".zsh",
    ".py",
    ".js",
    ".cjs",
    ".mjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".rb",
    ".pl",
    ".php",
    ".ps1",
    ".cmd",
    ".bat",
    ".html",
    ".htm",
    ".css",
    ".xml",
    ".dot",
    ".lua",
    ".go",
    ".rs",
}
CODE_EXTS = {".py", ".js", ".cjs", ".mjs", ".ts", ".tsx", ".jsx", ".rb", ".pl", ".php", ".lua", ".go", ".rs"}
SHELL_EXTS = {".sh", ".bash", ".zsh"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".ruff_cache", ".mypy_cache", ".pytest_cache", ".tox", "dist", "build"}
MAX_BYTES = 1_000_000

_HIDDEN = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]")
_HIDDEN_NAMES = {
    "\u200b": "ZERO WIDTH SPACE",
    "\u200c": "ZERO WIDTH NON-JOINER",
    "\u200d": "ZERO WIDTH JOINER",
    "\u200e": "LEFT-TO-RIGHT MARK",
    "\u200f": "RIGHT-TO-LEFT MARK",
    "\u202e": "RIGHT-TO-LEFT OVERRIDE",
    "\u202d": "LEFT-TO-RIGHT OVERRIDE",
    "\u2066": "LEFT-TO-RIGHT ISOLATE",
    "\u2067": "RIGHT-TO-LEFT ISOLATE",
    "\u2068": "FIRST STRONG ISOLATE",
    "\u2069": "POP DIRECTIONAL ISOLATE",
    "\ufeff": "ZERO WIDTH NO-BREAK SPACE",
}

_RULES_PATH = os.path.join(os.path.dirname(__file__), "defaults", "vet_rules.json")


def _load_rules(kind: str) -> List[Tuple[Pattern[str], str, str]]:
    with open(_RULES_PATH, encoding="utf-8") as fh:
        rules = json.load(fh)[kind]
    return [(re.compile(r["pattern"]), r["severity"], r["label"]) for r in rules]


_INJECTION = _load_rules("injection")
_CODE_PATTERNS = _load_rules("code")

_BLOB = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")
_FENCE = re.compile(r"^(```|~~~)\s*(bash|sh|shell|zsh|console)?\s*$")


@dataclass
class VetFinding:
    severity: str
    rule: str
    path: str
    line: int
    detail: str

    def render(self) -> str:
        loc = f"{self.path}:{self.line}" if self.line else self.path
        return f"{self.severity:<6} {self.rule:<22} {loc}  {self.detail}"


class Vetter:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.findings: List[VetFinding] = []
        policy = LoadedPolicy(data=load_defaults(), project=self.root, sources=["defaults"])
        self.ctx = Context(policy, self.root)
        self.files_scanned = 0
        self.suppressed = 0
        self._lines = {}

    def _suppressed(self, path: str, line: int) -> bool:
        if path not in self._lines:
            try:
                with open(path, encoding="utf-8", errors="replace") as fh:
                    self._lines[path] = fh.read().splitlines()
            except OSError:
                self._lines[path] = []
        lines = self._lines[path]
        return 0 < line <= len(lines) and SUPPRESS_MARKER in lines[line - 1]

    def add(self, severity: str, rule: str, path: str, line: int, detail: str) -> None:
        if line and self._suppressed(path, line):
            self.suppressed += 1
            return
        rel = os.path.relpath(path, self.root) if os.path.isabs(path) else path
        self.findings.append(VetFinding(severity, rule, rel, line, secretlib.redact_text(detail, max_len=200)))

    def files(self) -> Iterable[str]:
        if os.path.isfile(self.root):
            yield self.root
            return
        for base, dirs, names in os.walk(self.root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for d in list(dirs):
                full = os.path.join(base, d)
                if os.path.islink(full):
                    self._check_link(full)
            for n in sorted(names):
                yield os.path.join(base, n)

    def _check_link(self, path: str) -> bool:
        target = os.path.realpath(path)
        root = os.path.realpath(self.root) if os.path.isdir(self.root) else os.path.dirname(os.path.realpath(self.root))
        if target != root and not target.startswith(root + os.sep):
            self.add(HIGH, "symlink-escape", path, 0, f"symlink points outside the folder: {target}")
            return True
        return False

    def scan(self) -> List[VetFinding]:
        for path in self.files():
            if os.path.islink(path):
                if self._check_link(path):
                    continue
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            ext = os.path.splitext(path)[1].lower()
            if size > MAX_BYTES:
                self.add(INFO, "large-file", path, 0, f"{size} bytes, not scanned")
                continue
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            self.files_scanned += 1
            if secretlib.is_binary(data[:4096]):
                if ext not in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".svg", ".pdf", ".woff", ".woff2", ".ttf"}:
                    severity = HIGH if data[:4] in (b"\x7fELF", b"MZ\x90\x00", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe") else MEDIUM
                    self.add(severity, "binary-file", path, 0, "binary or executable content cannot be reviewed")
                continue
            text = data.decode("utf-8", errors="replace")
            name = os.path.basename(path)
            self._hidden(path, text)
            self._secrets(path, text)
            if ext in (".md", ".markdown", ".txt") or name == "SKILL.md":
                self._injection(path, text)
                self._markdown_shell(path, text)
            if ext in SHELL_EXTS or (not ext and text.startswith("#!") and re.match(r"#!.*\b(ba|z|da|k)?sh\b", text)):
                self._shell_script(path, text)
            if ext in CODE_EXTS or (not ext and text.startswith("#!") and re.match(r"#!.*\b(node|python3?|ruby|perl)\b", text)):
                self._code(path, text)
            if ext not in (".json",) and "lock" not in name:
                self._blobs(path, text)
            if name in ("hooks.json", "settings.json", "settings.local.json"):
                self._hooks_config(path, text)
            if name in ("plugin.json", ".mcp.json"):
                self._mcp_config(path, text)
        self.findings.sort(key=lambda f: (_ORDER[f.severity], f.path, f.line))
        return self.findings

    def _hidden(self, path: str, text: str) -> None:
        for lineno, line in enumerate(text.splitlines(), 1):
            hits = _HIDDEN.findall(line)
            if not hits:
                continue
            if set(hits) == {"\ufeff"} and lineno == 1 and line.startswith("\ufeff"):
                continue
            names = sorted({_HIDDEN_NAMES.get(h, f"U+{ord(h):04X}") for h in hits})
            tags = [h for h in hits if "\U000e0000" <= h <= "\U000e007f"]
            detail = ", ".join(names)
            if tags:
                decoded = "".join(chr(ord(t) - 0xE0000) for t in tags if 0x20 <= ord(t) - 0xE0000 < 0x7F)
                detail = f"Unicode tag characters spelling {decoded!r}"
            self.add(HIGH, "hidden-unicode", path, lineno, detail)

    def _secrets(self, path: str, text: str) -> None:
        for f in secretlib.scan_text(text, path=path, min_confidence=secretlib.HIGH):
            self.add(HIGH, "secret", path, f.line, f"{f.title} ({f.preview})")

    def _injection(self, path: str, text: str) -> None:
        in_fence = False
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.strip().startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            for rx, sev, label in _INJECTION:
                if rx.search(line):
                    if in_fence:
                        self.add(MEDIUM, "prompt-injection", path, lineno, f"{label} (inside a code block): {line.strip()[:120]}")
                    else:
                        self.add(sev, "prompt-injection", path, lineno, f"{label}: {line.strip()[:140]}")
        for m in re.finditer(r"<!--([\s\S]*?)-->", text):
            body = m.group(1)
            if any(rx.search(body) for rx, _, _ in _INJECTION) or re.search(
                r"(?i)\b(assistant|claude|agent|ai)\b.{0,40}\b(must|should|always|never)\b", body
            ):
                lineno = text.count("\n", 0, m.start()) + 1
                self.add(HIGH, "prompt-injection", path, lineno, f"instructions hidden in an HTML comment: {body.strip()[:140]}")

    def _judge_shell(self, path: str, lineno: int, command: str, origin: str) -> None:
        command = command.strip()
        if not command or command.startswith("#"):
            return
        if command.startswith("$ "):
            command = command[2:]
        v = evaluate_bash(self.ctx, command)
        if v.decision == DENY:
            self.add(HIGH, "dangerous-shell", path, lineno, f"{origin}: {command[:120]} ({', '.join(v.rules)})")
        elif v.decision == ASK and set(v.rules) - {"shell-parse-error", "write-outside-project", "sudo"}:
            self.add(MEDIUM, "risky-shell", path, lineno, f"{origin}: {command[:120]} ({', '.join(v.rules)})")

    def _markdown_shell(self, path: str, text: str) -> None:
        in_block, lang, start, buf = False, None, 0, []
        for lineno, line in enumerate(text.splitlines(), 1):
            m = _FENCE.match(line.strip())
            if m and not in_block:
                in_block, lang, start, buf = True, m.group(2), lineno, []
                continue
            if in_block and line.strip() in ("```", "~~~"):
                if lang:
                    for offset, cmd in enumerate(buf, 1):
                        if lang == "console":
                            if not cmd.lstrip().startswith("$ "):
                                continue
                            cmd = cmd.lstrip()[2:]
                        self._judge_shell(path, start + offset, cmd, "code block")
                in_block = False
                continue
            if in_block:
                buf.append(line)

    def _shell_script(self, path: str, text: str) -> None:
        logical, first = "", 0
        for lineno, line in enumerate(text.splitlines(), 1):
            if not logical:
                first = lineno
            if line.rstrip().endswith("\\"):
                logical += line.rstrip()[:-1] + " "
                continue
            logical += line
            self._judge_shell(path, first, logical, "script")
            logical = ""

    def _code(self, path: str, text: str) -> None:
        for rx, sev, label in _CODE_PATTERNS:
            for m in rx.finditer(text):
                lineno = text.count("\n", 0, m.start()) + 1
                snippet = text.splitlines()[lineno - 1].strip()[:140] if text else ""
                self.add(sev, "code-execution" if "network" not in label else "network", path, lineno, f"{label}: {snippet}")

    def _blobs(self, path: str, text: str) -> None:
        for m in _BLOB.finditer(text):
            lineno = text.count("\n", 0, m.start()) + 1
            self.add(MEDIUM, "encoded-blob", path, lineno, f"{len(m.group(0))}-character encoded string")

    def _hooks_config(self, path: str, text: str) -> None:
        try:
            data = json.loads(text)
        except ValueError:
            return
        hooks = data.get("hooks", {}) if isinstance(data, dict) else {}
        for event, groups in (hooks or {}).items():
            for g in groups or []:
                for h in (g or {}).get("hooks", []) or []:
                    if not isinstance(h, dict):
                        continue
                    if h.get("type") == "command" and h.get("command"):
                        self.add(INFO, "hook", path, 0, f"{event}: runs `{h['command'][:120]}`")
                        self._judge_shell(path, 0, h["command"], f"{event} hook")
                    elif h.get("type") == "http" and h.get("url"):
                        self.add(MEDIUM, "hook", path, 0, f"{event}: sends events to {h['url']}")

    def _mcp_config(self, path: str, text: str) -> None:
        try:
            data = json.loads(text)
        except ValueError:
            return
        servers = data.get("mcpServers", {}) if isinstance(data, dict) else {}
        if isinstance(servers, dict):
            for name, cfg in servers.items():
                if not isinstance(cfg, dict):
                    continue
                if cfg.get("url"):
                    self.add(INFO, "mcp-server", path, 0, f"{name}: remote server {cfg['url']}")
                elif cfg.get("command"):
                    cmd = " ".join([str(cfg["command"])] + [str(a) for a in cfg.get("args", [])])
                    self.add(INFO, "mcp-server", path, 0, f"{name}: runs `{cmd[:120]}`")
                    self._judge_shell(path, 0, cmd, f"MCP server {name}")


def vet(path: str) -> Vetter:
    v = Vetter(path)
    v.scan()
    return v


def summary(findings: List[VetFinding]) -> dict:
    out = {HIGH: 0, MEDIUM: 0, INFO: 0}
    for f in findings:
        out[f.severity] += 1
    return out


def to_json(v: Vetter) -> str:
    return json.dumps(
        {
            "root": v.root,
            "files": v.files_scanned,
            "suppressed": v.suppressed,
            "summary": summary(v.findings),
            "findings": [asdict(f) for f in v.findings],
        },
        indent=2,
    )


def exit_code(findings: List[VetFinding], strict: bool = False) -> int:
    s = summary(findings)
    if s[HIGH] or (strict and s[MEDIUM]):
        return 1
    return 0


def render(v: Vetter, show_info: bool = False) -> str:
    lines = [f.render() for f in v.findings if show_info or f.severity != INFO]
    s = summary(v.findings)
    verdict = "FAIL" if s[HIGH] else "REVIEW" if s[MEDIUM] else "PASS"
    lines.append("")
    if v.suppressed:
        lines.append(f"{v.suppressed} finding(s) silenced by inline '{SUPPRESS_MARKER}' markers: review them with grep.")
    lines.append(
        f"{verdict}: {v.files_scanned} files, {s[HIGH]} high, {s[MEDIUM]} medium, {s[INFO]} info"
        + ("" if show_info else " (--info to list)")
    )
    return "\n".join(lines)
