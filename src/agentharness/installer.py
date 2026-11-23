"""``harness init``: install the harness into a project.

Writes (never overwriting user content):

* ``.claude/settings.json``          hooks, status line, permission rules (merged)
* ``.claude/harness/policy.json``    profile policy, only if absent
* ``.claude/harness/.gitignore``     keeps logs and session state out of git
* ``.claude/harness/progress.md``    handoff log (committed)
* ``.claude/agents/*.md``            reviewer, test runner, security auditor, planner, evaluator
* ``.claude/skills/*/SKILL.md``      feature loop, session handoff, release check, policy tuning
* ``CLAUDE.md``                      project memory template, only if absent
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from . import settings_merge

TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")
PROFILES = ("minimal", "standard", "strict")

PRETOOL_MATCHER = "Bash|Read|Write|Edit|MultiEdit|NotebookEdit|Grep|WebFetch|mcp__.*"


def detect_test_command(project: str) -> Optional[str]:
    """Best guess at the project's test command, used for the stop gate."""

    def exists(*parts: str) -> bool:
        return os.path.exists(os.path.join(project, *parts))

    pkg = os.path.join(project, "package.json")
    if os.path.isfile(pkg):
        try:
            with open(pkg, encoding="utf-8") as fh:
                scripts = json.load(fh).get("scripts", {})
        except (OSError, ValueError):
            scripts = {}
        test = scripts.get("test", "")
        if test and "no test specified" not in test:
            if exists("pnpm-lock.yaml"):
                return "pnpm test"
            if exists("yarn.lock"):
                return "yarn test"
            if exists("bun.lockb") or exists("bun.lock"):
                return "bun test"
            return "npm test"
    if exists("Makefile"):
        try:
            with open(os.path.join(project, "Makefile"), encoding="utf-8") as fh:
                if any(line.startswith("test:") for line in fh):
                    return "make test"
        except OSError:
            pass
    if exists("pyproject.toml") or exists("pytest.ini") or exists("setup.cfg") or exists("tox.ini"):
        if exists("pytest.ini") or _file_contains(os.path.join(project, "pyproject.toml"), "[tool.pytest"):
            return "python -m pytest -q"
        if exists("tests"):
            return "python -m pytest -q" if shutil.which("pytest") else "python -m unittest discover -s tests -q"
    if exists("go.mod"):
        return "go test ./..."
    if exists("Cargo.toml"):
        return "cargo test --quiet"
    if exists("Gemfile") and exists("spec"):
        return "bundle exec rspec"
    if exists("mix.exs"):
        return "mix test"
    if exists("pom.xml"):
        return "mvn -q test"
    if exists("build.gradle") or exists("build.gradle.kts"):
        return "./gradlew test"
    return None


def _file_contains(path: str, needle: str) -> bool:
    try:
        with open(path, encoding="utf-8") as fh:
            return needle in fh.read()
    except OSError:
        return False


def default_hook_command() -> str:
    if shutil.which("harness"):
        return "harness"
    return f'"{sys.executable}" -m agentharness'


def settings_fragment(profile: str, hook_cmd: str, stop_timeout: int = 300) -> Dict[str, Any]:
    def h(event: str, timeout: int) -> Dict[str, Any]:
        return {"type": "command", "command": f"{hook_cmd} hook {event}", "timeout": timeout}

    hooks: Dict[str, Any] = {
        "PreToolUse": [{"matcher": PRETOOL_MATCHER, "hooks": [h("PreToolUse", 10)]}],
        "PostToolUse": [{"matcher": "*", "hooks": [h("PostToolUse", 60)]}],
        "SessionEnd": [{"hooks": [h("SessionEnd", 10)]}],
    }
    if profile in ("standard", "strict"):
        hooks.update(
            {
                "PostToolUseFailure": [{"matcher": "*", "hooks": [h("PostToolUseFailure", 10)]}],
                "UserPromptSubmit": [{"hooks": [h("UserPromptSubmit", 10)]}],
                "SessionStart": [{"matcher": "startup|resume|clear|compact", "hooks": [h("SessionStart", 15)]}],
                "Stop": [{"hooks": [h("Stop", stop_timeout + 30)]}],
                "SubagentStop": [{"hooks": [h("SubagentStop", 10)]}],
                "PreCompact": [{"hooks": [h("PreCompact", 15)]}],
                "Notification": [{"hooks": [h("Notification", 10)]}],
            }
        )
    fragment: Dict[str, Any] = {
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "hooks": hooks,
        "permissions": {
            "allow": [],
            "deny": [
                "Read(./.env)",
                "Read(./.env.*)",
                "Read(./**/*.pem)",
                "Read(./**/*.key)",
                "Read(~/.ssh/**)",
                "Read(~/.aws/**)",
            ],
        },
    }
    if hook_cmd == "harness":
        fragment["permissions"]["allow"] = ["Bash(harness progress *)", "Bash(harness check *)", "Bash(harness audit *)"]
    if profile in ("standard", "strict"):
        fragment["statusLine"] = {"type": "command", "command": f"{hook_cmd} statusline", "padding": 0}
    return fragment


def profile_policy(profile: str, test_command: Optional[str]) -> Dict[str, Any]:
    policy: Dict[str, Any] = {
        "$comment": "agent-harness policy. Layers over the built-in defaults; see `harness policy show`.",
        "version": 1,
        "mode": "enforce",
    }
    if profile == "minimal":
        policy["context"] = {"session_start": False}
    if test_command:
        policy["stop_gate"] = {"enabled": profile == "strict", "command": test_command}
    if profile == "strict":
        policy.update(
            {
                "fail_mode": "closed",
                "bash": {"sudo": "deny", "on_parse_error": "deny"},
                "paths": {"write_outside_project": "deny"},
                "secrets": {"scan_prompts": "block", "scan_commands": "deny"},
                "notify": {"enabled": True},
            }
        )
    return policy


HARNESS_GITIGNORE = """# agent-harness: machine-local files
audit.jsonl
audit.jsonl.*
state/
*.lock
*.tmp
policy.local.json
"""


@dataclass
class InitReport:
    created: List[str] = field(default_factory=list)
    updated: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def render(self, project: str) -> str:
        def rel(p: str) -> str:
            return os.path.relpath(p, project)

        lines = []
        for label, items in (("created", self.created), ("updated", self.updated), ("kept", self.skipped)):
            for item in items:
                lines.append(f"  {label:<8} {rel(item) if os.path.isabs(item) else item}")
        lines.extend(f"  note     {n}" for n in self.notes)
        return "\n".join(lines)


def _write_if_absent(path: str, content: str, report: InitReport, dry_run: bool) -> None:
    if os.path.exists(path):
        report.skipped.append(path)
        return
    if not dry_run:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    report.created.append(path)


def _copy_tree_if_absent(src: str, dst: str, report: InitReport, dry_run: bool) -> None:
    for root, _dirs, files in os.walk(src):
        for name in sorted(files):
            if name.startswith("."):
                continue
            s = os.path.join(root, name)
            d = os.path.join(dst, os.path.relpath(s, src))
            with open(s, encoding="utf-8") as fh:
                _write_if_absent(d, fh.read(), report, dry_run)


def init_project(
    project: str,
    profile: str = "standard",
    hook_command: Optional[str] = None,
    with_agents: bool = True,
    force: bool = False,
    dry_run: bool = False,
) -> InitReport:
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {', '.join(PROFILES)}")
    project = os.path.abspath(project)
    report = InitReport()
    hook_cmd = hook_command or default_hook_command()
    test_cmd = detect_test_command(project)

    claude_dir = os.path.join(project, ".claude")
    hdir = os.path.join(claude_dir, "harness")

    # settings.json
    settings_path = os.path.join(claude_dir, "settings.json")
    existing = settings_merge.load(settings_path)
    merged, changes = settings_merge.merge_settings(existing, settings_fragment(profile, hook_cmd), force=force)
    if changes:
        if not dry_run:
            settings_merge.write(settings_path, merged, backup=bool(existing))
        (report.updated if existing else report.created).append(settings_path)
        report.notes.append("settings.json: " + "; ".join(changes))
    else:
        report.skipped.append(settings_path)

    # policy and harness files
    policy_path = os.path.join(hdir, "policy.json")
    _write_if_absent(policy_path, json.dumps(profile_policy(profile, test_cmd), indent=2) + "\n", report, dry_run)
    _write_if_absent(os.path.join(hdir, ".gitignore"), HARNESS_GITIGNORE, report, dry_run)
    _write_if_absent(
        os.path.join(hdir, "progress.md"),
        "# Progress log\n\nAppend-only. Newest entries at the bottom. Update it with `harness progress note`.\n",
        report,
        dry_run,
    )

    # agents and skills
    if with_agents:
        _copy_tree_if_absent(os.path.join(TEMPLATES, "agents"), os.path.join(claude_dir, "agents"), report, dry_run)
        _copy_tree_if_absent(os.path.join(TEMPLATES, "skills"), os.path.join(claude_dir, "skills"), report, dry_run)

    # CLAUDE.md
    with open(os.path.join(TEMPLATES, "CLAUDE.md"), encoding="utf-8") as fh:
        template = fh.read().replace("{{TEST_COMMAND}}", test_cmd or "<add your test command>")
    _write_if_absent(os.path.join(project, "CLAUDE.md"), template, report, dry_run)

    if test_cmd:
        state = "enabled" if profile == "strict" else "available (set stop_gate.enabled to true)"
        report.notes.append(f"stop gate: `{test_cmd}` {state}")
    else:
        report.notes.append("stop gate: no test command detected; set stop_gate.command in .claude/harness/policy.json")
    if hook_cmd != "harness":
        report.notes.append(f"hooks call {hook_cmd}; install with pipx to get a `harness` command on PATH")
    return report
