"""Command line interface: ``harness <command>``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional

from . import __version__, doctor, gitinfo, installer, vet
from . import secrets as secretlib
from . import skills as skilllib
from .config import harness_dir, load_policy, project_dir
from .hooks import HANDLERS, dispatch
from .policy import ALLOW, ASK, DENY, evaluate
from .progress import Progress, ProgressError
from .statusline import main_from_stdin
from .store import AuditLog

EXIT_DENY = 2
EXIT_ASK = 3


def _tty() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def _project(args: argparse.Namespace) -> str:
    return os.path.abspath(args.project) if getattr(args, "project", None) else project_dir()


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------


def cmd_hook(args: argparse.Namespace) -> int:
    result = dispatch(args.event, sys.stdin.read())
    if result.stdout:
        sys.stdout.write(result.stdout)
        if not result.stdout.endswith("\n"):
            sys.stdout.write("\n")
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.exit_code


def cmd_check(args: argparse.Namespace) -> int:
    project = _project(args)
    policy = load_policy(project)
    value = " ".join(args.value)
    if args.kind == "bash":
        tool, ti = "Bash", {"command": value}
    elif args.kind == "read":
        tool, ti = "Read", {"file_path": os.path.abspath(value)}
    elif args.kind == "write":
        content = sys.stdin.read() if args.stdin else ""
        tool, ti = "Write", {"file_path": os.path.abspath(value), "content": content}
    elif args.kind == "url":
        tool, ti = "WebFetch", {"url": value, "prompt": ""}
    else:
        tool, ti = value, {}
    v = evaluate(tool, ti, policy, os.getcwd())
    if args.json:
        print(json.dumps({"decision": v.decision, "findings": [f.__dict__ for f in v.findings]}, indent=2))
    else:
        color = {ALLOW: "\033[32m", ASK: "\033[33m", DENY: "\033[31m"}[v.decision] if _tty() else ""
        reset = "\033[0m" if color else ""
        print(f"{color}{v.decision.upper()}{reset}  {tool}: {value}")
        for f in v.findings:
            print(f"  {f.decision:<5} [{f.rule}] {f.reason}")
    return {ALLOW: 0, ASK: EXIT_ASK, DENY: EXIT_DENY}[v.decision]


def cmd_scan(args: argparse.Namespace) -> int:
    project = _project(args)
    policy = load_policy(project)
    allow = policy.get("secrets.allow_patterns", [])
    min_conf = secretlib.HIGH if args.high_only else secretlib.MEDIUM
    if args.staged:
        root = gitinfo.root(project) or project
        files = [os.path.join(root, p) for p in gitinfo.staged_files(root)]
    else:
        files = list(secretlib.iter_files(args.paths or [project]))
    findings = []
    for f in files:
        findings.extend(secretlib.scan_file(f, allow_patterns=allow, min_confidence=min_conf))
    if args.json:
        print(json.dumps([f.__dict__ for f in findings], indent=2))
    else:
        for f in findings:
            rel = os.path.relpath(f.path, project) if f.path else "?"
            print(f"{rel}:{f.line}:{f.column}  {f.confidence:<6} {f.title}  {f.preview}")
        print(
            f"\n{len(files)} file{'s' if len(files) != 1 else ''} scanned, {len(findings)} finding{'s' if len(findings) != 1 else ''}",
            file=sys.stderr,
        )
    return 1 if findings else 0


def _local_time(ts: str) -> str:
    try:
        dt = datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts[:19]


def cmd_audit(args: argparse.Namespace) -> int:
    project = _project(args)
    log = AuditLog.for_policy(load_policy(project))
    records = log.read(include_rotated=args.all)
    if args.session:
        records = [r for r in records if str(r.get("session", "")).startswith(args.session)]
    if args.blocked:
        records = [r for r in records if r.get("decision") in (DENY, ASK, "block")]
    if args.stats:
        events = Counter(r.get("event") for r in records)
        tools = Counter(r.get("tool") for r in records if r.get("event") == "PostToolUse")
        decisions = Counter(r.get("decision") for r in records if r.get("decision"))
        rules = Counter(rule for r in records for rule in (r.get("rules") or []))
        sessions = {r.get("session") for r in records if r.get("session")}
        out = {
            "records": len(records),
            "sessions": len(sessions),
            "events": dict(events.most_common()),
            "tools": dict(tools.most_common(15)),
            "decisions": dict(decisions.most_common()),
            "rules": dict(rules.most_common(15)),
        }
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(f"{out['records']} records across {out['sessions']} sessions ({log.path})")
            for title in ("events", "tools", "decisions", "rules"):
                if out[title]:
                    print(f"\n{title}:")
                    for k, n in out[title].items():
                        print(f"  {n:>6}  {k}")
        return 0
    records = records[-args.tail :] if args.tail else records
    for r in records:
        if args.json:
            print(json.dumps(r, ensure_ascii=False))
            continue
        bits = [_local_time(r.get("ts", "")), f"{r.get('event', ''):<18}"]
        if r.get("tool"):
            bits.append(r["tool"])
        if r.get("decision"):
            bits.append(f"-> {r['decision']}")
        inp = r.get("input") or {}
        target = inp.get("command") or inp.get("file_path") or inp.get("url") or inp.get("pattern") or ""
        if target:
            target = str(target)
            if target.startswith(project + os.sep):
                target = os.path.relpath(target, project)
            bits.append(target[:100])
        if r.get("gate"):
            bits.append(f"gate {r['gate']}")
        if r.get("reason") and r.get("decision"):
            bits.append(f"({r['reason'][:140]})")
        print("  ".join(bits))
    return 0


def cmd_progress(args: argparse.Namespace) -> int:
    project = _project(args)
    prog = Progress(harness_dir(project))
    try:
        if args.action == "show":
            if args.json:
                print(json.dumps(prog.load(), indent=2))
                return 0
            feats = prog.features()
            if not feats:
                print('No features yet. Add one: harness progress add "User can reset password"')
            for f in feats:
                mark = "✓" if f.get("passes") else {"in_progress": "▸", "blocked": "■"}.get(f.get("status"), "·")
                print(f" {mark} #{f['id']:<3} {f['status']:<11} {f['title']}")
            c = prog.counts()
            if feats:
                print(f"\n {c['passing']}/{c['total']} passing")
            nxt = prog.next_feature()
            if nxt:
                print(f" next: #{nxt['id']} {nxt['title']}")
        elif args.action == "add":
            f = prog.add(" ".join(args.text), steps=args.step or [], priority=args.priority)
            print(f"added #{f['id']} {f['title']}")
        elif args.action in ("start", "done", "block", "reopen"):
            status = {"start": "in_progress", "done": "done", "block": "blocked", "reopen": "todo"}[args.action]
            f = prog.set_status(args.id, status, note=" ".join(args.note or []))
            print(f"#{f['id']} {f['title']} -> {f['status']}{' (passes)' if f['passes'] else ''}")
        elif args.action == "note":
            prog.note(" ".join(args.text), session_id=os.environ.get("CLAUDE_SESSION_ID"), heading=args.heading)
            print(f"noted in {os.path.relpath(prog.log_path, project)}")
        elif args.action == "summary":
            print(prog.summary() or "No progress recorded yet.")
        elif args.action == "import":
            added = prog.import_plan(args.plan)
            for f in added:
                print(f"added #{f['id']} {f['title']} ({len(f['steps'])} steps)")
            print(f"{len(added)} task(s) imported from {args.plan}")
    except ProgressError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    project = _project(args)
    report = installer.init_project(
        project,
        profile=args.profile,
        hook_command=args.hook_command,
        with_agents=not args.no_agents,
        force=args.force,
        dry_run=args.dry_run,
    )
    print(f"agent-harness {__version__}: {'dry run for' if args.dry_run else 'installed into'} {project} (profile: {args.profile})")
    print(report.render(project))
    if not args.dry_run:
        print("\nNext: run `harness doctor`, then start Claude Code in this folder.")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    checks = doctor.run_checks(_project(args))
    if args.json:
        print(json.dumps([c.__dict__ for c in checks], indent=2))
    else:
        print(doctor.render(checks, color=_tty()))
    return 1 if any(c.status == doctor.FAIL for c in checks) else 0


def cmd_policy(args: argparse.Namespace) -> int:
    policy = load_policy(_project(args))
    if args.action == "show":
        print(json.dumps(policy.data, indent=2))
    elif args.action == "sources":
        for s in policy.sources:
            print(s)
        for e in policy.errors:
            print(f"error: {e}", file=sys.stderr)
    elif args.action == "validate":
        if policy.errors:
            for e in policy.errors:
                print(f"error: {e}", file=sys.stderr)
            return 1
        print(f"ok: {len(policy.sources)} layer(s) valid")
    return 0


def cmd_vet(args: argparse.Namespace) -> int:
    if not os.path.exists(args.path):
        print(f"error: {args.path} does not exist", file=sys.stderr)
        return 2
    result = vet.vet(args.path)
    print(vet.to_json(result) if args.json else vet.render(result, show_info=args.info))
    return vet.exit_code(result.findings, strict=args.strict)


def cmd_skills(args: argparse.Namespace) -> int:
    project = _project(args)
    if args.action == "list":
        found = skilllib.list_skills(project)
        if args.json:
            print(json.dumps([{"name": s.name, "source": s.source, "path": s.path, "description": s.description} for s in found], indent=2))
            return 0
        for s in found:
            desc = s.description if len(s.description) <= 100 else s.description[:99] + "…"
            print(f"  {s.source:<13} {s.name:<32} {desc}")
        print(f"\n{len(found)} skill(s)")
        return 0
    paths = args.paths or [loc for _, loc in skilllib.default_locations(project)]
    files = skilllib.find_skill_files(paths)
    if os.path.isfile(os.path.join(project, "SKILL.md")) and not args.paths:
        files.append(os.path.join(project, "SKILL.md"))
    errors = warnings = 0
    for f in files:
        root_skill = os.path.dirname(f) == project
        for issue in skilllib.check_skill(f, root_is_skill=root_skill):
            print(issue.render(project))
            errors += issue.severity == "error"
            warnings += issue.severity == "warning"
    print(f"\n{len(files)} skill(s) checked, {errors} error(s), {warnings} warning(s)")
    return 1 if errors or (args.strict and warnings) else 0


def cmd_statusline(_args: argparse.Namespace) -> int:
    print(main_from_stdin(sys.stdin.read()))
    return 0


# --------------------------------------------------------------------------
# parser
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="harness",
        description="Guardrails, memory and verification for Claude Code agents.",
    )
    p.add_argument("--version", action="version", version=f"agent-harness {__version__}")
    p.add_argument("-C", "--project", help="project directory (default: $CLAUDE_PROJECT_DIR or cwd)")
    sub = p.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    s = sub.add_parser("hook", help="run a Claude Code hook (reads event JSON on stdin)")
    s.add_argument("event", choices=sorted(HANDLERS), metavar="event")
    s.set_defaults(func=cmd_hook)

    s = sub.add_parser("init", help="install the harness into a project")
    s.add_argument("--profile", choices=installer.PROFILES, default="standard")
    s.add_argument("--hook-command", help="command hooks call (default: harness if on PATH)")
    s.add_argument("--no-agents", action="store_true", help="do not copy subagents and skills")
    s.add_argument("--force", action="store_true", help="overwrite non-hook settings such as statusLine")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("doctor", help="verify the installation")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_doctor)

    s = sub.add_parser("check", help="dry-run the policy (exit 0 allow, 2 deny, 3 ask)")
    s.add_argument("kind", choices=["bash", "read", "write", "url", "tool"])
    s.add_argument("value", nargs="+")
    s.add_argument("--stdin", action="store_true", help="for write: read the new content from stdin")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("scan", help="scan files for secrets (exit 1 on findings)")
    s.add_argument("paths", nargs="*")
    s.add_argument("--staged", action="store_true", help="scan files staged in git (pre-commit)")
    s.add_argument("--high-only", action="store_true", help="only provider-specific detectors")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("audit", help="read the audit log")
    s.add_argument("--tail", type=int, default=30, help="last N records (0 = all)")
    s.add_argument("--session", help="filter by session id prefix")
    s.add_argument("--blocked", action="store_true", help="only denied, asked or blocked actions")
    s.add_argument("--stats", action="store_true")
    s.add_argument("--all", action="store_true", help="include rotated logs")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_audit)

    s = sub.add_parser("progress", help="feature list and handoff log for long-running work")
    ps = s.add_subparsers(dest="action", metavar="<action>")
    ps.required = True
    a = ps.add_parser("show")
    a.add_argument("--json", action="store_true")
    a = ps.add_parser("add")
    a.add_argument("text", nargs="+")
    a.add_argument("--step", action="append", help="acceptance step (repeatable)")
    a.add_argument("--priority", type=int, default=2, choices=[1, 2, 3])
    for name in ("start", "done", "block", "reopen"):
        a = ps.add_parser(name)
        a.add_argument("id", type=int)
        a.add_argument("note", nargs="*")
    a = ps.add_parser("note")
    a.add_argument("text", nargs="+")
    a.add_argument("--heading")
    ps.add_parser("summary")
    a = ps.add_parser("import", help="add one feature per '### Task N:' heading of a plan")
    a.add_argument("plan")
    s.set_defaults(func=cmd_progress)

    s = sub.add_parser("vet", help="security-scan a skill, plugin or repo before installing it")
    s.add_argument("path")
    s.add_argument("--strict", action="store_true", help="also fail on medium findings")
    s.add_argument("--info", action="store_true", help="list informational findings (hooks, MCP servers)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_vet)

    s = sub.add_parser("skills", help="list or lint Claude Code skills")
    s.add_argument("action", choices=["list", "check"])
    s.add_argument("paths", nargs="*", help="for check: skill folders or SKILL.md files")
    s.add_argument("--strict", action="store_true", help="fail on warnings too")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_skills)

    s = sub.add_parser("policy", help="inspect the effective policy")
    s.add_argument("action", choices=["show", "sources", "validate"])
    s.set_defaults(func=cmd_policy)

    s = sub.add_parser("statusline", help="render the Claude Code status line (stdin JSON)")
    s.set_defaults(func=cmd_statusline)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "project", None):
        os.environ["CLAUDE_PROJECT_DIR"] = os.path.abspath(args.project)
    try:
        return args.func(args)
    except BrokenPipeError:  # e.g. `harness audit | head`
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
