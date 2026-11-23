from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from . import secrets as secretlib
from .config import LoadedPolicy
from .pathmatch import PathMatcher, is_inside, resolve
from .shell import INTERPRETERS, SHELLS, Analysis, SimpleCommand, analyze, expand_user_path, path_like_args

ALLOW, ASK, DENY = "allow", "ask", "deny"
_RANK = {ALLOW: 0, ASK: 1, DENY: 2}


@dataclass
class Finding:
    decision: str
    rule: str
    reason: str


@dataclass
class Verdict:
    decision: str = ALLOW
    findings: List[Finding] = field(default_factory=list)

    def add(self, decision: str, rule: str, reason: str) -> None:
        self.findings.append(Finding(decision, rule, reason))
        if _RANK[decision] > _RANK[self.decision]:
            self.decision = decision

    @property
    def reason(self) -> str:
        relevant = [f for f in self.findings if f.decision == self.decision] or self.findings
        seen: List[str] = []
        for f in relevant:
            line = f"[{f.rule}] {f.reason}"
            if line not in seen:
                seen.append(line)
        return " ".join(seen)

    @property
    def rules(self) -> List[str]:
        return [f.rule for f in self.findings if f.decision == self.decision]


class Context:
    def __init__(self, policy: LoadedPolicy, cwd: str):
        self.policy = policy
        self.project = policy.project
        self.cwd = cwd or policy.project
        self.home = os.path.expanduser("~")
        p = policy.data.get("paths", {})
        self.deny_read = PathMatcher(p.get("deny_read", []), self.home)
        self.deny_write = PathMatcher(p.get("deny_write", []), self.home)
        self.ask_write = PathMatcher(p.get("ask_write", []), self.home)
        self.allow_outside = PathMatcher(p.get("write_allow_outside", []), self.home)
        self.secret_ignore = PathMatcher(policy.data.get("secrets", {}).get("ignore_paths", []), self.home)

    def enabled(self, rule: str) -> bool:
        return self.policy.rule_enabled(rule)

    def add(self, verdict: Verdict, decision: str, rule: str, reason: str) -> None:
        if decision != ALLOW and self.enabled(rule):
            verdict.add(decision, rule, reason)

    def rel(self, path: str) -> str:
        try:
            if is_inside(path, self.project):
                return os.path.relpath(path, self.project)
        except ValueError:
            pass
        return path.replace(self.home, "~", 1) if path.startswith(self.home) else path


def check_read(ctx: Context, verdict: Verdict, raw_path: str, via: str = "") -> None:
    path = resolve(raw_path, ctx.cwd)
    hit = ctx.deny_read.match(path, ctx.project)
    if hit:
        ctx.add(
            verdict,
            DENY,
            "secret-file-read",
            f"{via}reading {ctx.rel(path)} is blocked (matches '{hit}'). It may contain credentials; "
            "ask the user to share only the value you need.",
        )


def check_write(ctx: Context, verdict: Verdict, raw_path: str, via: str = "") -> None:
    path = resolve(raw_path, ctx.cwd)
    hit = ctx.deny_write.match(path, ctx.project)
    if hit:
        ctx.add(verdict, DENY, "protected-path-write", f"{via}writing {ctx.rel(path)} is blocked (matches '{hit}').")
        return
    hit = ctx.ask_write.match(path, ctx.project)
    if hit:
        ctx.add(verdict, ASK, "sensitive-path-write", f"{via}{ctx.rel(path)} is sensitive (matches '{hit}'); confirm the change.")
    if not is_inside(path, ctx.project) and not ctx.allow_outside.matches(path, ctx.project):
        decision = ctx.policy.get("paths.write_outside_project", ASK)
        ctx.add(verdict, decision, "write-outside-project", f"{via}{ctx.rel(path)} is outside the project directory.")


_CRITICAL_DIRS = {
    "/",
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/lib",
    "/lib64",
    "/opt",
    "/proc",
    "/root",
    "/sbin",
    "/sys",
    "/usr",
    "/var",
    "/home",
    "/Users",
    "/System",
    "/Library",
    "/Applications",
    "/Volumes",
    "/private",
    "/mnt",
    "/srv",
    "C:",
    "C:/",
    "C:\\",
}
_DOWNLOADERS = {"curl", "wget", "fetch", "aria2c", "http", "https", "xh", "base64", "xxd", "openssl", "nc", "ncat"}
_PROTECTED_BRANCHES = re.compile(r"^(?:refs/heads/)?(main|master|trunk|develop|production|prod|release(?:/.*)?)$")
_SAFE_PATH_COMMANDS = {
    "ls",
    "stat",
    "test",
    "[",
    "[[",
    "realpath",
    "basename",
    "dirname",
    "file",
    "touch",
    "mkdir",
    "which",
    "echo",
    "printf",
    "gh",
    "true",
    "false",
    ":",
}
_GIT_PATH_SUBCOMMANDS = {"add", "show", "cat-file", "blame", "diff", "grep", "stash"}
_WRITE_DEST_COMMANDS = {"cp", "mv", "install", "ln", "rsync", "tee"}
_SQL_DESTRUCTIVE = re.compile(r"(?i)\b(drop\s+(?:database|schema|table)|truncate\s+(?:table\s+)?\w|delete\s+from\s+\w+\s*;?\s*$)")


def _flags(args: Iterable[str]) -> set:
    out = set()
    for a in args:
        if a.startswith("--"):
            out.add(a.split("=", 1)[0])
        elif a.startswith("-") and len(a) > 1:
            for ch in a[1:]:
                out.add("-" + ch)
    return out


def _positional(args: List[str]) -> List[str]:
    out, after_dd = [], False
    for a in args:
        if after_dd:
            out.append(a)
        elif a == "--":
            after_dd = True
        elif not a.startswith("-") or a == "-":
            out.append(a)
    return out


def _is_critical(ctx: Context, target: str) -> bool:
    t = expand_user_path(target, ctx.home)
    for suffix in ("/*", "/.*", "/"):
        while len(t) > 1 and t.endswith(suffix):
            t = t[: -len(suffix)] or "/"
    if t in ("~", ""):
        return True
    if t in ("*", ".*"):
        return _is_critical(ctx, ctx.cwd)
    if t in _CRITICAL_DIRS or t.rstrip("/") in _CRITICAL_DIRS:
        return True
    absolute = os.path.normpath(os.path.join(ctx.cwd, t))
    if absolute in (ctx.home, os.path.dirname(ctx.home)):
        return True
    if absolute == os.path.normpath(ctx.project) or is_inside(ctx.project, absolute) and absolute != ctx.project:
        return True
    if absolute in _CRITICAL_DIRS:
        return True
    return False


def rule_rm(ctx: Context, v: Verdict, cmd: SimpleCommand) -> None:
    if cmd.name not in ("rm", "rmdir", "unlink", "find"):
        return
    args = cmd.args
    if cmd.name == "find":
        if "-delete" in args or ("-exec" in args and any(a in ("rm", "/bin/rm") for a in args)):
            roots = []
            for a in args:
                if a.startswith("-") or a in ("(", "!"):
                    break
                roots.append(a)
            for r in roots or ["."]:
                if _is_critical(ctx, r):
                    ctx.add(v, DENY, "rm-dangerous-target", f"'find {r} ... -delete' would delete a critical directory.")
        return
    flags = _flags(args)
    if "--no-preserve-root" in flags:
        ctx.add(v, DENY, "rm-dangerous-target", "rm --no-preserve-root is never allowed.")
        return
    recursive = bool(flags & {"-r", "-R", "--recursive"})
    for target in _positional(args):
        if not _is_critical(ctx, target):
            continue
        if recursive or cmd.name == "rmdir" or target in ("/*", "~/*"):
            ctx.add(v, DENY, "rm-dangerous-target", f"'rm {' '.join(args)}' would delete '{target}', a critical or parent directory.")
        else:
            where = ctx.rel(ctx.cwd)
            where = "the project root" if where == "." else where
            ctx.add(v, ASK, "rm-dangerous-target", f"'rm {target}' deletes every file it matches in {where}.")


def rule_pipe_to_shell(ctx: Context, v: Verdict, cmd: SimpleCommand, analysis: Analysis) -> None:
    name = cmd.name
    if name in INTERPRETERS and cmd.piped_from:
        script_args = [a for a in _positional(cmd.args) if a != "-"]
        if "-c" in cmd.args or "-e" in cmd.args and name in ("perl", "ruby", "node"):
            return
        if not script_args:
            if cmd.piped_from in _DOWNLOADERS:
                ctx.add(
                    v,
                    DENY,
                    "pipe-to-shell",
                    f"piping {cmd.piped_from} output into {name} runs unreviewed code. Download to a file, read it, then run it.",
                )
            else:
                ctx.add(v, ASK, "pipe-to-shell", f"piping {cmd.piped_from} output into {name} executes generated code.")
    if name in SHELLS | {"source", "."}:
        for a in cmd.args:
            if a.startswith("<(") and re.search(r"\b(curl|wget|fetch)\b", a):
                ctx.add(v, DENY, "pipe-to-shell", f"'{name} <(curl ...)' runs remote code without review.")


def rule_git(ctx: Context, v: Verdict, cmd: SimpleCommand) -> None:
    if cmd.name != "git":
        return
    args = list(cmd.args)
    while args and args[0].startswith("-"):
        opt = args.pop(0)
        if opt in ("-C", "-c", "--git-dir", "--work-tree", "--namespace") and args:
            args.pop(0)
    if not args:
        return
    sub, rest = args[0], args[1:]
    flags = _flags(rest)
    if "--no-verify" in flags or (sub == "commit" and "-n" in flags):
        ctx.add(v, DENY, "git-no-verify", f"'git {sub} --no-verify' skips the project's hooks. Fix the hook failure instead.")
    if sub == "push":
        pos = _positional(rest)
        refspecs = pos[1:] if len(pos) > 1 else []
        force = bool(flags & {"-f", "--force", "--force-with-lease", "--force-if-includes"}) or any(r.startswith("+") for r in refspecs)
        if "--mirror" in flags or ("--delete" in flags) or "-d" in flags or any(r.startswith(":") for r in refspecs):
            ctx.add(v, ASK, "git-force-push", "this push deletes or mirrors remote refs.")
        if force:
            branches = [r.lstrip("+").split(":")[-1] for r in refspecs]
            protected = not branches or any(_PROTECTED_BRANCHES.match(b) for b in branches) or "--all" in flags
            if protected:
                ctx.add(v, DENY, "git-force-push", "force-pushing a protected branch (main, master, release...) rewrites shared history.")
            else:
                ctx.add(v, ASK, "git-force-push", f"force push to {', '.join(branches)} rewrites remote history.")
    elif sub == "reset" and "--hard" in flags:
        ctx.add(v, ASK, "git-destructive", "'git reset --hard' discards uncommitted work.")
    elif sub == "clean" and ("-f" in flags or "--force" in flags):
        ctx.add(v, ASK, "git-destructive", "'git clean -f' permanently deletes untracked files.")
    elif (
        sub in ("checkout", "restore")
        and "." in _positional(rest)
        and not (sub == "restore" and "--staged" in flags and "--worktree" not in flags)
    ):
        ctx.add(v, ASK, "git-destructive", f"'git {sub} .' discards local changes.")
    elif sub == "branch" and ("-D" in flags or ("--delete" in flags and "--force" in flags)):
        ctx.add(v, ASK, "git-destructive", "force-deleting a branch can lose unmerged commits.")
    elif sub == "stash" and rest[:1] and rest[0] in ("drop", "clear"):
        ctx.add(v, ASK, "git-destructive", f"'git stash {rest[0]}' deletes stashed work.")
    elif sub in ("filter-branch", "filter-repo") or (sub == "reflog" and rest[:1] == ["expire"]) or (sub == "update-ref" and "-d" in flags):
        ctx.add(v, ASK, "git-destructive", f"'git {sub}' rewrites history or deletes refs.")


def rule_permissions(ctx: Context, v: Verdict, cmd: SimpleCommand) -> None:
    if cmd.name == "chmod":
        modes = _positional(cmd.args)[:1]
        if modes and re.match(r"^(0?[0-7]?77[0-7]|0?[0-7]?[0-7]{1}6[0-7]|a\+[rwx]*w|o\+[rwx]*w|\+w|ugo\+[rwx]*w|777|666)$", modes[0]):
            ctx.add(v, DENY, "chmod-world-writable", f"'chmod {modes[0]}' makes files writable by every user.")
    if cmd.name in ("chown", "chgrp") and _flags(cmd.args) & {"-R", "--recursive"}:
        for t in _positional(cmd.args)[1:]:
            if _is_critical(ctx, t):
                ctx.add(v, DENY, "chmod-world-writable", f"recursive {cmd.name} on '{t}'.")


def rule_disk(ctx: Context, v: Verdict, cmd: SimpleCommand) -> None:
    name = cmd.name
    if name == "dd" and any(a.startswith("of=/dev/") for a in cmd.args):
        ctx.add(v, DENY, "disk-destroy", "dd to a raw device overwrites the disk.")
    if name.startswith("mkfs") or name in ("fdisk", "sfdisk", "parted", "wipefs", "shred", "mkswap"):
        ctx.add(v, DENY, "disk-destroy", f"'{name}' formats or wipes storage.")
    if name == "diskutil" and cmd.args and re.match(r"(?i)^(erase|zero|secureErase|partitionDisk|reformat)", cmd.args[0]):
        ctx.add(v, DENY, "disk-destroy", f"'diskutil {cmd.args[0]}' erases a disk.")
    for r in cmd.redirects:
        if r.is_write and re.match(r"^/dev/(sd|hd|nvme|disk|rdisk|mmcblk|xvd|vd)", r.target):
            ctx.add(v, DENY, "disk-destroy", f"writing to {r.target} overwrites a disk.")


def rule_system(ctx: Context, v: Verdict, cmd: SimpleCommand) -> None:
    name, args = cmd.name, cmd.args
    if name in ("shutdown", "reboot", "halt", "poweroff") or (name == "init" and args[:1] in (["0"], ["6"])):
        ctx.add(v, DENY, "system-power", f"'{name}' would stop or restart the machine.")
    if name == "systemctl" and args[:1] and args[0] in ("poweroff", "reboot", "halt", "suspend", "hibernate"):
        ctx.add(v, DENY, "system-power", f"'systemctl {args[0]}' would stop the machine.")
    if name == "kill" and "-1" in args[1:] + args[:1] and any(a in ("-9", "-KILL", "-s") for a in args):
        ctx.add(v, DENY, "kill-all", "'kill -9 -1' kills every process you own.")
    if name in ("killall", "pkill") and ("-9" in args or "-KILL" in args):
        ctx.add(v, ASK, "kill-all", f"'{name} -9' force-kills processes by name.")
    if name == "crontab" and ("-r" in args):
        ctx.add(v, DENY, "persistence", "'crontab -r' deletes every scheduled job.")
    if name == "history" and "-c" in args:
        ctx.add(v, ASK, "history-tamper", "clearing shell history hides what was run.")
    if name == "unset" and any(a in ("HISTFILE", "HISTSIZE") for a in args):
        ctx.add(v, ASK, "history-tamper", "disabling shell history hides what was run.")


def rule_env_dump(ctx: Context, v: Verdict, cmd: SimpleCommand) -> None:
    dumping = (
        (not cmd.argv and "env" in cmd.wrappers and not cmd.assignments)
        or (cmd.name == "printenv" and not cmd.args)
        or (cmd.name == "set" and not cmd.args)
        or (cmd.name == "export" and cmd.args in ([], ["-p"]))
        or (cmd.name in ("cat", "strings", "xxd") and any(re.match(r"^/proc/[^/]+/environ$", a) for a in cmd.args))
    )
    if dumping:
        ctx.add(v, ASK, "env-dump", "dumping the environment can print API keys into the transcript; read the specific variable you need.")


def rule_network(ctx: Context, v: Verdict, cmd: SimpleCommand) -> None:
    name, args = cmd.name, cmd.args
    if name == "curl":
        for i, a in enumerate(args):
            nxt = args[i + 1] if i + 1 < len(args) else ""
            if a in ("-d", "--data", "--data-binary", "--data-raw", "--data-urlencode", "-F", "--form") and "@" in nxt:
                ctx.add(v, ASK, "network-upload", f"curl uploads a local file ({nxt}).")
            if a in ("-T", "--upload-file"):
                ctx.add(v, ASK, "network-upload", f"curl uploads {nxt or 'a file'}.")
    if name == "wget" and any(a.startswith("--post-file") or a.startswith("--body-file") for a in args):
        ctx.add(v, ASK, "network-upload", "wget posts a local file.")
    if name in ("scp", "sftp", "rsync") and any(re.match(r"^(?:[\w.-]+@)?[\w.-]{2,}:", a) for a in _positional(args)):
        ctx.add(v, ASK, "network-upload", f"{name} copies files to or from a remote host.")
    if name in ("nc", "ncat", "netcat", "socat", "telnet"):
        ctx.add(v, ASK, "network-upload", f"'{name}' opens a raw network connection.")
    if name in ("curl", "wget", "http", "xh", "httpie"):
        for a in args:
            if re.match(r"^(https?://|[\w.-]+\.[a-z]{2,}(/|$))", a):
                url = a if "://" in a else "https://" + a
                check_url(ctx, v, url, via=f"{name}: ")


def rule_publish(ctx: Context, v: Verdict, cmd: SimpleCommand) -> None:
    name, args = cmd.name, cmd.args
    first = args[0] if args else ""
    pairs = {
        ("npm", "publish"),
        ("yarn", "publish"),
        ("pnpm", "publish"),
        ("bun", "publish"),
        ("twine", "upload"),
        ("poetry", "publish"),
        ("cargo", "publish"),
        ("gem", "push"),
        ("docker", "push"),
        ("podman", "push"),
        ("flit", "publish"),
        ("hatch", "publish"),
        ("uv", "publish"),
        ("vsce", "publish"),
        ("ovsx", "publish"),
    }
    if (name, first) in pairs:
        ctx.add(v, ASK, "publish", f"'{name} {first}' publishes to a public registry.")
    if name == "gh":
        sub = " ".join(args[:2])
        if sub in ("release create", "release delete", "repo delete", "repo archive", "repo rename", "secret set", "secret delete") or (
            sub == "repo edit" and any("--visibility" in a for a in args)
        ):
            ctx.add(v, ASK, "publish", f"'gh {sub}' changes a GitHub repository or release.")
        if sub == "pr merge" or (args[:2] == ["api", "-X"] and len(args) > 2 and args[2] in ("DELETE", "PUT", "PATCH")):
            ctx.add(v, ASK, "publish", f"'gh {sub}' changes state on GitHub.")


def rule_infra(ctx: Context, v: Verdict, cmd: SimpleCommand) -> None:
    name, args = cmd.name, cmd.args
    first = args[0] if args else ""
    flags = _flags(args)
    if name in ("terraform", "tofu", "terragrunt") and (
        first == "destroy" or (first == "apply" and ("-auto-approve" in args or "--auto-approve" in args))
    ):
        ctx.add(v, ASK, "infra-destroy", f"'{name} {first}' changes or destroys infrastructure without a plan review.")
    if name == "pulumi" and first in ("destroy", "up") and ("--yes" in flags or "-y" in flags or first == "destroy"):
        ctx.add(v, ASK, "infra-destroy", f"'pulumi {first}' changes infrastructure.")
    if name in ("kubectl", "oc") and first in ("delete", "drain", "replace"):
        ctx.add(v, ASK, "infra-destroy", f"'{name} {first}' changes a live cluster.")
    if name == "helm" and first in ("uninstall", "delete", "rollback"):
        ctx.add(v, ASK, "infra-destroy", f"'helm {first}' changes a live release.")
    if (
        name == "aws"
        and len(args) >= 2
        and ((args[0] == "s3" and args[1] in ("rm", "rb")) or re.match(r"^(delete|terminate|remove|destroy)-", args[1]))
    ):
        ctx.add(v, ASK, "infra-destroy", f"'aws {args[0]} {args[1]}' deletes cloud resources.")
    if name in ("gcloud", "az") and any(a in ("delete", "destroy") for a in args):
        ctx.add(v, ASK, "infra-destroy", f"'{name} ... delete' deletes cloud resources.")
    if name in ("docker", "podman") and (
        (first == "system" and "prune" in args) or (first == "volume" and len(args) > 1 and args[1] in ("rm", "prune"))
    ):
        ctx.add(v, ASK, "infra-destroy", f"'{name} {' '.join(args[:2])}' deletes containers, images or volumes.")
    if name in ("psql", "mysql", "mariadb", "sqlite3", "mongosh", "mongo", "redis-cli", "supabase", "prisma", "dropdb"):
        joined = " ".join(args)
        if (
            name == "dropdb"
            or _SQL_DESTRUCTIVE.search(joined)
            or (name == "redis-cli" and re.search(r"(?i)\bflush(all|db)\b", joined))
            or (name == "prisma" and "reset" in args)
            or (name == "supabase" and args[:2] == ["db", "reset"])
        ):
            ctx.add(v, ASK, "db-destroy", f"'{name}' command drops or wipes data.")


def rule_paths_in_command(ctx: Context, v: Verdict, cmd: SimpleCommand) -> None:
    via = f"{cmd.name}: " if cmd.name else ""
    if cmd.name and cmd.name not in _SAFE_PATH_COMMANDS:
        candidates = path_like_args(cmd)
        dest = None
        if cmd.name in _WRITE_DEST_COMMANDS and len(candidates) >= 2 and cmd.name != "tee":
            dest = candidates[-1]
            candidates = candidates[:-1]
        if cmd.name == "tee":
            for c in candidates:
                check_write(ctx, v, expand_user_path(c, ctx.home), via)
            candidates = []
        if cmd.name == "git":
            candidates = candidates[1:] if cmd.args[:1] and cmd.args[0] in _GIT_PATH_SUBCOMMANDS else []
        for c in candidates:
            if c.startswith(("http://", "https://")) or "://" in c:
                continue
            check_read(ctx, v, expand_user_path(c, ctx.home), via)
        if dest:
            check_write(ctx, v, expand_user_path(dest, ctx.home), via)
    for r in cmd.redirects:
        if (
            not r.target
            or r.target.startswith("&")
            or r.target in ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty")
            or r.target.isdigit()
        ):
            continue
        if r.target.startswith("/dev/"):
            continue
        if r.is_write:
            check_write(ctx, v, expand_user_path(r.target, ctx.home), "redirect: ")
        elif r.is_read:
            check_read(ctx, v, expand_user_path(r.target, ctx.home), "redirect: ")


_FORK_BOMB = re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:")

CommandRule = Callable[[Context, Verdict, SimpleCommand], None]
_COMMAND_RULES: List[CommandRule] = [
    rule_rm,
    rule_git,
    rule_permissions,
    rule_disk,
    rule_system,
    rule_env_dump,
    rule_network,
    rule_publish,
    rule_infra,
    rule_paths_in_command,
]


def evaluate_bash(ctx: Context, command: str) -> Verdict:
    v = Verdict()
    if not command.strip():
        return v
    analysis = analyze(command)
    if analysis.parse_error:
        ctx.add(
            v,
            ctx.policy.get("bash.on_parse_error", ASK),
            "shell-parse-error",
            f"could not parse the command safely ({analysis.parse_error}).",
        )
    if _FORK_BOMB.search(command):
        ctx.add(v, DENY, "fork-bomb", "fork bomb.")
    start_cwd = ctx.cwd
    for cmd in analysis.commands:
        if cmd.name in ("cd", "pushd") and cmd.depth == 0:
            target = _positional(cmd.args)[:1]
            if not target:
                ctx.cwd = ctx.home
            elif target[0] != "-" and "$" not in target[0] and "`" not in target[0]:
                ctx.cwd = os.path.normpath(os.path.join(ctx.cwd, expand_user_path(target[0], ctx.home)))
            continue
        if cmd.sudo:
            ctx.add(v, ctx.policy.get("bash.sudo", ASK), "sudo", f"'sudo {cmd.name}' runs with root privileges.")
        for rule in _COMMAND_RULES:
            rule(ctx, v, cmd)
        rule_pipe_to_shell(ctx, v, cmd, analysis)
    ctx.cwd = start_cwd

    mode = ctx.policy.get("secrets.scan_commands", ASK)
    if mode != ALLOW:
        found = secretlib.scan_text(command, allow_patterns=ctx.policy.get("secrets.allow_patterns", []), min_confidence=secretlib.HIGH)
        if found:
            kinds = ", ".join(sorted({f.title for f in found}))
            ctx.add(
                v,
                mode,
                "secret-in-command",
                f"the command contains a literal {kinds}; load it from the environment or a secrets manager instead.",
            )

    for rule in ctx.policy.get("bash.rules", []):
        try:
            rx = re.compile(rule["pattern"])
        except (re.error, KeyError):
            continue
        targets = [command] if rule.get("scope") == "command" else [" ".join(c.argv) for c in analysis.commands]
        if any(rx.search(t) for t in targets):
            ctx.add(v, rule.get("decision", ASK), rule.get("id", "custom"), rule.get("reason", f"matches custom rule {rule.get('id')}."))
    return v


def _domain_in(host: str, domains: Iterable[str]) -> Optional[str]:
    host = host.lower().rstrip(".")
    for d in domains:
        d = d.lower().lstrip("*.").rstrip(".")
        if host == d or host.endswith("." + d):
            return d
    return None


def check_url(ctx: Context, v: Verdict, url: str, via: str = "") -> None:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return
    if not host:
        return
    web = ctx.policy.data.get("web", {})
    d = _domain_in(host, web.get("deny_domains", []))
    if d:
        ctx.add(v, DENY, "web-domain", f"{via}{host} is on the deny list.")
        return
    d = _domain_in(host, web.get("ask_domains", []))
    if d:
        ctx.add(v, ASK, "web-domain", f"{via}{host} is a paste/webhook/tunnel service often used to exfiltrate data.")
    allow = web.get("allow_domains", [])
    if allow and not _domain_in(host, allow):
        ctx.add(v, ASK, "web-domain", f"{via}{host} is not in web.allow_domains.")


def _check_content(ctx: Context, v: Verdict, path: Optional[str], texts: List[str]) -> None:
    if not ctx.policy.get("secrets.scan_writes", True):
        return
    if path and ctx.secret_ignore.matches(resolve(path, ctx.cwd), ctx.project):
        return
    allow = ctx.policy.get("secrets.allow_patterns", [])
    high, medium = [], []
    for t in texts:
        if not isinstance(t, str) or not t:
            continue
        for f in secretlib.scan_text(t, allow_patterns=allow):
            (high if f.confidence == secretlib.HIGH else medium).append(f)
    if high:
        kinds = ", ".join(sorted({f"{f.title} ({f.preview})" for f in high}))
        ctx.add(
            v, DENY, "secret-in-write", f"the new content contains {kinds}. Read it from an environment variable instead of hard-coding it."
        )
    elif medium:
        kinds = ", ".join(sorted({f.title for f in medium}))
        ctx.add(v, ASK, "secret-in-write", f"the new content may contain a {kinds}; confirm it is not a real credential.")


def evaluate(tool_name: str, tool_input: Dict, policy: LoadedPolicy, cwd: Optional[str] = None) -> Verdict:
    ctx = Context(policy, cwd or policy.project)
    v = Verdict()
    if policy.mode == "off" or not isinstance(tool_input, dict):
        return v
    ti = tool_input
    if tool_name == "Bash":
        return evaluate_bash(ctx, str(ti.get("command", "")))
    if tool_name in ("Read", "NotebookRead"):
        p = ti.get("file_path") or ti.get("notebook_path")
        if p:
            check_read(ctx, v, p)
    elif tool_name == "Grep":
        if ti.get("path"):
            check_read(ctx, v, ti["path"])
        g = ti.get("glob")
        if isinstance(g, str) and g and not any(ch in g for ch in "*?[{"):
            check_read(ctx, v, os.path.join(ti.get("path") or ctx.cwd, g))
    elif tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        p = ti.get("file_path") or ti.get("notebook_path")
        if p:
            check_write(ctx, v, p)
        texts = [ti.get("content"), ti.get("new_string"), ti.get("new_source")]
        for e in ti.get("edits", []) or []:
            if isinstance(e, dict):
                texts.append(e.get("new_string"))
        _check_content(ctx, v, p, [t for t in texts if t])
    elif tool_name == "WebFetch":
        if ti.get("url"):
            check_url(ctx, v, str(ti["url"]))
    elif tool_name.startswith("mcp__"):
        mcp = policy.data.get("mcp", {})
        for pat in mcp.get("deny_tools", []):
            if fnmatch.fnmatchcase(tool_name, pat):
                ctx.add(v, DENY, "mcp-tool", f"{tool_name} is denied by mcp.deny_tools ('{pat}').")
        for pat in mcp.get("ask_tools", []):
            if fnmatch.fnmatchcase(tool_name, pat):
                ctx.add(v, ASK, "mcp-tool", f"{tool_name} is a destructive MCP action ('{pat}').")
    return v
