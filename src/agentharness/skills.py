"""``harness skills``: find and lint Claude Code skills.

A skill is a folder with a ``SKILL.md``: YAML frontmatter (``name``,
``description``) followed by Markdown instructions. Claude reads every
skill's description up front to decide which one applies, and loads the body
only when it does. That makes the description the most important line and the
body's size a context cost, which is what ``check`` enforces:

* frontmatter present, ``name`` kebab-case (max 64) and equal to the folder
  name, ``description`` present (max 1024) and free of XML tags,
* the description says *when* to use the skill,
* the body stays under 500 lines,
* relative links point at files that exist,
* no hidden characters or prompt-injection phrasing (shared with ``vet``).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .vet import HIGH, MEDIUM, Vetter

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED = ("anthropic", "claude")
MAX_NAME = 64
MAX_DESCRIPTION = 1024
MAX_BODY_LINES = 500
_LINK = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)")
_WHEN = re.compile(r"(?i)\b(use (it |this )?(when|before|after|for|to|whenever|if)|when\b|before\b|after\b)")


class FrontmatterError(ValueError):
    pass


def parse_frontmatter(text: str) -> Tuple[Dict[str, object], str, int]:
    """Parse the small YAML subset skills use. Returns (fields, body, body_start_line).

    Supports ``key: value``, quoted values, ``>``/``|`` block scalars and
    ``- item`` lists. Anything fancier is rejected rather than guessed at.
    """
    if not text.startswith("---"):
        raise FrontmatterError("missing frontmatter: the file must start with a '---' line")
    lines = text.split("\n")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        raise FrontmatterError("frontmatter is not closed with '---'")
    fields: Dict[str, object] = {}
    i = 1
    while i < end:
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not m:
            raise FrontmatterError(f"line {i + 1}: expected 'key: value'")
        key, value = m.group(1), m.group(2).strip()
        if value in (">", "|", ">-", "|-"):
            block = []
            i += 1
            while i < end and (lines[i].startswith(" ") or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            fields[key] = (" " if value.startswith(">") else "\n").join(b for b in block if b)
            continue
        if value == "":
            items = []
            j = i + 1
            while j < end and re.match(r"^\s+-\s+", lines[j]):
                items.append(re.sub(r"^\s+-\s+", "", lines[j]).strip().strip("\"'"))
                j += 1
            fields[key] = items if items else ""
            i = j
            continue
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        elif value.startswith("[") and value.endswith("]"):
            fields[key] = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
            i += 1
            continue
        fields[key] = value
        i += 1
    body = "\n".join(lines[end + 1 :])
    return fields, body, end + 2


@dataclass
class Skill:
    path: str  # SKILL.md
    name: str
    description: str
    source: str = ""
    fields: Dict[str, object] = field(default_factory=dict)

    @property
    def folder(self) -> str:
        return os.path.dirname(self.path)


@dataclass
class Issue:
    severity: str  # error | warning
    path: str
    message: str

    def render(self, root: str) -> str:
        rel = os.path.relpath(self.path, root) if os.path.isabs(self.path) else self.path
        return f"{self.severity:<7} {rel}: {self.message}"


def find_skill_files(paths: List[str]) -> List[str]:
    out: List[str] = []
    for p in paths:
        if os.path.isfile(p) and os.path.basename(p) == "SKILL.md":
            out.append(os.path.abspath(p))
            continue
        if not os.path.isdir(p):
            continue
        for base, dirs, files in os.walk(p):
            dirs[:] = sorted(d for d in dirs if d not in (".git", "node_modules", "__pycache__"))
            if "SKILL.md" in files:
                out.append(os.path.abspath(os.path.join(base, "SKILL.md")))
    return sorted(set(out))


def load_skill(path: str, source: str = "") -> Skill:
    with open(path, encoding="utf-8") as fh:
        fields, _, _ = parse_frontmatter(fh.read())
    return Skill(path, str(fields.get("name", "")), str(fields.get("description", "")), source, fields)


def check_skill(path: str, root_is_skill: bool = False) -> List[Issue]:
    issues: List[Issue] = []
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        return [Issue("error", path, f"unreadable: {exc}")]
    try:
        fields, body, body_start = parse_frontmatter(text)
    except FrontmatterError as exc:
        return [Issue("error", path, str(exc))]

    folder = os.path.basename(os.path.dirname(os.path.abspath(path)))
    name = fields.get("name")
    desc = fields.get("description")
    if not isinstance(name, str) or not name:
        issues.append(Issue("error", path, "frontmatter needs a 'name'"))
    else:
        if not NAME_RE.match(name):
            issues.append(Issue("error", path, f"name '{name}' must be lowercase letters, digits and hyphens"))
        if len(name) > MAX_NAME:
            issues.append(Issue("error", path, f"name is {len(name)} characters (max {MAX_NAME})"))
        if any(r in name.split("-") for r in RESERVED):
            issues.append(Issue("error", path, f"name '{name}' uses a reserved word ({', '.join(RESERVED)})"))
        if name != folder and not root_is_skill:
            issues.append(Issue("warning", path, f"name '{name}' differs from its folder '{folder}'"))
    if not isinstance(desc, str) or not desc.strip():
        issues.append(Issue("error", path, "frontmatter needs a 'description'"))
    else:
        if len(desc) > MAX_DESCRIPTION:
            issues.append(Issue("error", path, f"description is {len(desc)} characters (max {MAX_DESCRIPTION})"))
        if re.search(r"<[A-Za-z/][^>]*>", desc):
            issues.append(Issue("error", path, "description must not contain XML tags"))
        if not _WHEN.search(desc):
            issues.append(Issue("warning", path, "description should say when to use the skill ('Use when ...')"))
        if len(desc) < 40:
            issues.append(Issue("warning", path, "description is very short; Claude chooses skills from it"))
    body_lines = body.count("\n") + 1
    if body_lines > MAX_BODY_LINES:
        issues.append(Issue("warning", path, f"body is {body_lines} lines; move detail into reference files (max {MAX_BODY_LINES})"))
    # links
    base = os.path.dirname(path)
    for lineno, line in enumerate(body.split("\n"), body_start):
        for target in _LINK.findall(line):
            if "://" in target or target.startswith(("mailto:", "#")):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(base, target))):
                issues.append(Issue("error", path, f"line {lineno}: link to missing file '{target}'"))
    # shared security checks
    v = Vetter(os.path.dirname(path))
    v._hidden(path, text)
    v._injection(path, text)
    for f in v.findings:
        if f.severity in (HIGH, MEDIUM):
            issues.append(Issue("error" if f.severity == HIGH else "warning", path, f"line {f.line}: {f.rule}: {f.detail}"))
    return issues


def default_locations(project: str, plugin_root: Optional[str] = None) -> List[Tuple[str, str]]:
    here = os.path.join(os.path.dirname(__file__), "templates", "skills")
    locs = [("agent-harness", plugin_root and os.path.join(plugin_root, "src", "agentharness", "templates", "skills") or here)]
    locs.append(("project", os.path.join(project, ".claude", "skills")))
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    locs.append(("user", os.path.join(base, "skills")))
    return locs


def list_skills(project: str) -> List[Skill]:
    out: List[Skill] = []
    for source, loc in default_locations(project, os.environ.get("CLAUDE_PLUGIN_ROOT")):
        for p in find_skill_files([loc]):
            try:
                out.append(load_skill(p, source))
            except (OSError, FrontmatterError, UnicodeDecodeError):
                out.append(Skill(p, os.path.basename(os.path.dirname(p)), "(invalid frontmatter)", source))
    return out
