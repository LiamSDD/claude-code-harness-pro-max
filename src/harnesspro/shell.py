from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

MAX_DEPTH = 6

SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "ash"}
INTERPRETERS = SHELLS | {
    "python",
    "python3",
    "python2",
    "perl",
    "ruby",
    "node",
    "deno",
    "bun",
    "php",
    "lua",
}

_WRAPPERS = {
    "command": 0,
    "builtin": 0,
    "exec": 0,
    "nohup": 0,
    "time": 0,
    "nice": 0,
    "ionice": 0,
    "stdbuf": 0,
    "caffeinate": 0,
    "doas": 0,
    "sudo": 0,
    "env": 0,
    "timeout": 1,
    "watch": 0,
    "xargs": 0,
    "chronic": 0,
}

_WRAPPER_OPTS_WITH_VALUE = {
    "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"},
    "doas": {"-u", "-C"},
    "nice": {"-n"},
    "ionice": {"-c", "-n", "-p"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
    "env": {"-u", "-C", "-S", "--unset", "--chdir"},
    "xargs": {"-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a"},
    "watch": {"-n", "-d"},
    "stdbuf": {"-i", "-o", "-e"},
}

_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_REDIRECT = re.compile(r"^(\d*)(>>|>&|>\||>|<<<|<<-|<<|<&|<>|<)$")


@dataclass
class Redirect:
    op: str
    target: str

    @property
    def is_write(self) -> bool:
        return self.op in (">", ">>", ">|", "&>", "&>>", "<>")

    @property
    def is_read(self) -> bool:
        return self.op in ("<", "<>")


@dataclass
class SimpleCommand:
    argv: List[str]
    raw: str = ""
    redirects: List[Redirect] = field(default_factory=list)
    wrappers: List[str] = field(default_factory=list)
    assignments: List[str] = field(default_factory=list)
    piped_from: Optional[str] = None
    pipes_to: Optional[str] = None
    background: bool = False
    depth: int = 0
    heredoc: Optional[str] = None

    @property
    def name(self) -> str:
        if not self.argv:
            return ""
        return os.path.basename(self.argv[0])

    @property
    def args(self) -> List[str]:
        return self.argv[1:]

    @property
    def sudo(self) -> bool:
        return "sudo" in self.wrappers or "doas" in self.wrappers

    def __str__(self) -> str:
        return " ".join(self.argv)


@dataclass
class Analysis:
    command: str
    commands: List[SimpleCommand]
    parse_error: Optional[str] = None

    def names(self) -> List[str]:
        return [c.name for c in self.commands]


class ShellParseError(ValueError):
    pass


_OP = "OP"
_WORD = "WORD"


@dataclass
class _Token:
    kind: str
    value: str
    subs: List[str] = field(default_factory=list)


def _find_closing_paren(s: str, start: int) -> int:
    depth = 1
    i = start
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                raise ShellParseError("unterminated single quote")
            i = j + 1
            continue
        if c == '"':
            i = _skip_double_quoted(s, i + 1)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ShellParseError("unbalanced parenthesis")


def _skip_double_quoted(s: str, i: int) -> int:
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i + 1
        if c == "$" and i + 1 < n and s[i + 1] == "(":
            i = _find_closing_paren(s, i + 2) + 1
            continue
        i += 1
    raise ShellParseError("unterminated double quote")


def _tokenize(s: str) -> List[_Token]:
    tokens: List[_Token] = []
    buf: List[str] = []
    subs: List[str] = []
    has_word = False
    i = 0
    n = len(s)

    def flush() -> None:
        nonlocal buf, subs, has_word
        if has_word or buf:
            tokens.append(_Token(_WORD, "".join(buf), subs))
        buf, subs, has_word = [], [], False

    while i < n:
        c = s[i]

        if not buf and not has_word and s.startswith("[[", i) and i + 2 < n and s[i + 2] in " \t":
            close = re.compile(r"\s\]\](?=\s|$|;|&|\||\))").search(s, i + 2)
            j = close.start() + 1 if close else -1
            if j > 0:
                for word in s[i : j + 2].split():
                    tokens.append(_Token(_WORD, word))
                i = j + 2
                continue

        if c == "#" and not buf and not has_word:
            j = s.find("\n", i)
            i = n if j < 0 else j
            continue

        if c == "\\":
            if i + 1 < n:
                if s[i + 1] == "\n":
                    i += 2
                    continue
                buf.append(s[i + 1])
                has_word = True
            i += 2
            continue

        if c == "'":
            j = s.find("'", i + 1)
            if j < 0:
                raise ShellParseError("unterminated single quote")
            buf.append(s[i + 1 : j])
            has_word = True
            i = j + 1
            continue

        if c == '"':
            j = i + 1
            out: List[str] = []
            while True:
                if j >= n:
                    raise ShellParseError("unterminated double quote")
                d = s[j]
                if d == "\\" and j + 1 < n and s[j + 1] in '"\\$`\n':
                    out.append(s[j + 1])
                    j += 2
                    continue
                if d == '"':
                    break
                if d == "$" and j + 1 < n and s[j + 1] == "(":
                    end = _find_closing_paren(s, j + 2)
                    subs.append(s[j + 2 : end])
                    out.append(s[j : end + 1])
                    j = end + 1
                    continue
                if d == "`":
                    end = s.find("`", j + 1)
                    if end < 0:
                        raise ShellParseError("unterminated backtick")
                    subs.append(s[j + 1 : end])
                    out.append(s[j : end + 1])
                    j = end + 1
                    continue
                out.append(d)
                j += 1
            buf.append("".join(out))
            has_word = True
            i = j + 1
            continue

        if c == "$" and i + 1 < n and s[i + 1] == "(":
            end = _find_closing_paren(s, i + 2)
            subs.append(s[i + 2 : end])
            buf.append(s[i : end + 1])
            has_word = True
            i = end + 1
            continue

        if c in "<>" and i + 1 < n and s[i + 1] == "(" and not buf:
            end = _find_closing_paren(s, i + 2)
            subs.append(s[i + 2 : end])
            buf.append(s[i : end + 1])
            has_word = True
            i = end + 1
            continue

        if c == "`":
            end = s.find("`", i + 1)
            if end < 0:
                raise ShellParseError("unterminated backtick")
            subs.append(s[i + 1 : end])
            buf.append(s[i : end + 1])
            has_word = True
            i = end + 1
            continue

        if c in " \t":
            flush()
            i += 1
            continue

        if c == "\n":
            flush()
            tokens.append(_Token(_OP, "\n"))
            i += 1
            continue

        if c in ";&|()":
            if c == "&" and i + 1 < n and s[i + 1] == ">":
                flush()
                if i + 2 < n and s[i + 2] == ">":
                    tokens.append(_Token(_OP, "&>>"))
                    i += 3
                else:
                    tokens.append(_Token(_OP, "&>"))
                    i += 2
                continue
            flush()
            two = s[i : i + 2]
            if two in ("&&", "||", "|&", ";;"):
                tokens.append(_Token(_OP, two))
                i += 2
            else:
                tokens.append(_Token(_OP, c))
                i += 1
            continue

        if c in "<>":
            fd = ""
            if buf and not has_word and "".join(buf).isdigit():
                fd = "".join(buf)
                buf = []
            elif buf and "".join(buf).isdigit() and not subs:
                fd = "".join(buf)
                buf, has_word = [], False
            else:
                flush()
            j = i + 1
            while j < n and s[j] in "<>&|-" and j - i < 3:
                j += 1
            op = s[i:j]
            m = _REDIRECT.match(op)
            if not m:
                op = c
                j = i + 1
            tokens.append(_Token(_OP, fd + op))
            i = j
            continue

        buf.append(c)
        has_word = True
        i += 1

    flush()
    return tokens


_SEPARATORS = {"&&", "||", ";", "\n", "&", ";;", "(", ")"}
_PIPES = {"|", "|&"}


def _strip_fd(op: str) -> str:
    return op.lstrip("0123456789")


def _unwrap(cmd: SimpleCommand) -> None:
    argv = cmd.argv
    while argv:
        word = argv[0]
        if _ASSIGNMENT.match(word) and cmd.name != "env":
            cmd.assignments.append(argv.pop(0))
            continue
        if word in ("{", "}", "!"):
            argv.pop(0)
            continue
        base = os.path.basename(word)
        if base in _WRAPPERS:
            cmd.wrappers.append(base)
            argv.pop(0)
            opts = _WRAPPER_OPTS_WITH_VALUE.get(base, set())
            while argv and argv[0].startswith("-") and argv[0] != "-":
                opt = argv.pop(0)
                if opt == "--":
                    break
                if opt in opts and argv:
                    argv.pop(0)
            if base == "env":
                while argv and _ASSIGNMENT.match(argv[0]):
                    cmd.assignments.append(argv.pop(0))
            for _ in range(_WRAPPERS[base]):
                if argv:
                    argv.pop(0)
            if base == "nice" and argv and re.match(r"^-\d+$", argv[0] or ""):
                argv.pop(0)
            continue
        break
    while argv and argv[-1] == "}":
        argv.pop()


def _build(tokens: List[_Token], source: str, depth: int) -> Tuple[List[SimpleCommand], List[str]]:
    commands: List[SimpleCommand] = []
    nested: List[str] = []
    current: List[str] = []
    redirects: List[Redirect] = []
    pending_pipe_from: Optional[SimpleCommand] = None
    heredoc_delims: List[str] = []
    i = 0

    def finish(next_op: Optional[str]) -> None:
        nonlocal current, redirects, pending_pipe_from
        if current or redirects:
            cmd = SimpleCommand(argv=list(current), redirects=list(redirects), depth=depth)
            cmd.raw = " ".join(current)
            _unwrap(cmd)
            if not (cmd.argv or cmd.redirects or cmd.wrappers or cmd.assignments):
                current, redirects = [], []
                return
            if pending_pipe_from is not None:
                cmd.piped_from = pending_pipe_from.name
                pending_pipe_from.pipes_to = cmd.name
            commands.append(cmd)
            if next_op in _PIPES:
                pending_pipe_from = cmd
            else:
                pending_pipe_from = None
            if next_op == "&":
                cmd.background = True
        else:
            if next_op not in _PIPES:
                pending_pipe_from = None
        current = []
        redirects = []

    while i < len(tokens):
        tok = tokens[i]
        if tok.kind == _WORD:
            current.append(tok.value)
            nested.extend(tok.subs)
            i += 1
            continue
        op = tok.value
        base = _strip_fd(op)
        if base in ("<<", "<<-"):
            target = tokens[i + 1].value if i + 1 < len(tokens) and tokens[i + 1].kind == _WORD else ""
            redirects.append(Redirect(base, target))
            heredoc_delims.append(target)
            i += 2
            continue
        if base in (">", ">>", ">|", ">&", "<", "<&", "<>", "<<<", "&>", "&>>"):
            target = ""
            if i + 1 < len(tokens) and tokens[i + 1].kind == _WORD:
                target = tokens[i + 1].value
                nested.extend(tokens[i + 1].subs)
                i += 1
            redirects.append(Redirect(base, target))
            i += 1
            continue
        if op in _PIPES:
            finish(op)
            i += 1
            continue
        if op in _SEPARATORS:
            finish(op)
            i += 1
            continue
        i += 1

    finish(None)
    return commands, nested


def _extract_heredocs(script: str) -> Tuple[str, List[Tuple[str, str]]]:
    lines = script.split("\n")
    out_lines: List[str] = []
    bodies: List[Tuple[str, str]] = []
    pattern = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
    i = 0
    while i < len(lines):
        line = lines[i]
        out_lines.append(line)
        delims = [m.group(2) for m in pattern.finditer(line)]
        i += 1
        for delim in delims:
            body: List[str] = []
            while i < len(lines) and lines[i].strip() != delim:
                body.append(lines[i])
                i += 1
            i += 1
            bodies.append((delim, "\n".join(body)))
    return "\n".join(out_lines), bodies


def _inline_script(cmd: SimpleCommand) -> Optional[str]:
    name = cmd.name
    args = cmd.args
    if name in SHELLS:
        for idx, a in enumerate(args):
            if a == "-c" or (a.startswith("-") and not a.startswith("--") and "c" in a[1:]):
                if idx + 1 < len(args):
                    return args[idx + 1]
    if name == "eval" and args:
        return " ".join(args)
    if name in ("python", "python3") and "-c" in args:
        return None
    return None


def analyze(command: str, _depth: int = 0) -> Analysis:
    if _depth > MAX_DEPTH:
        return Analysis(command, [], parse_error="nesting too deep")
    stripped, heredocs = _extract_heredocs(command)
    try:
        tokens = _tokenize(stripped)
    except ShellParseError as exc:
        fallback = SimpleCommand(argv=command.split(), raw=command, depth=_depth)
        _unwrap(fallback)
        return Analysis(command, [fallback], parse_error=str(exc))

    commands, nested = _build(tokens, stripped, _depth)
    result = Analysis(command, list(commands))

    if heredocs:
        hd_iter = iter(heredocs)
        for cmd in commands:
            for r in cmd.redirects:
                if r.op in ("<<", "<<-"):
                    try:
                        _, body = next(hd_iter)
                    except StopIteration:
                        break
                    cmd.heredoc = body
                    if cmd.name in SHELLS and not cmd.args:
                        nested.append(body)

    for cmd in commands:
        script = _inline_script(cmd)
        if script:
            nested.append(script)
        if cmd.name in SHELLS:
            for r in cmd.redirects:
                if r.op == "<<<" and r.target:
                    nested.append(r.target)

    for script in nested:
        sub = analyze(script, _depth + 1)
        result.commands.extend(sub.commands)
        if sub.parse_error and not result.parse_error:
            result.parse_error = sub.parse_error
    return result


def expand_user_path(arg: str, home: Optional[str] = None) -> str:
    home = home or os.path.expanduser("~")
    if arg == "~" or arg.startswith("~/"):
        arg = home + arg[1:]
    for var in ("$HOME", "${HOME}"):
        if arg.startswith(var):
            arg = home + arg[len(var) :]
    return arg


def path_like_args(cmd: SimpleCommand) -> List[str]:
    out: List[str] = []
    for a in cmd.args:
        if not a:
            continue
        if a.startswith("-"):
            if "=" in a:
                out.append(a.split("=", 1)[1])
            continue
        if a.startswith("@") and len(a) > 1:
            out.append(a[1:])
            continue
        out.append(a)
    return out
