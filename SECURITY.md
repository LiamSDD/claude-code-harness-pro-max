# Security

## Threat model

Claude Code Harness Pro Max protects a developer's machine and repository from mistakes an AI coding agent is likely to make, and from prompt injection that tries to turn the agent against its user (for example a README or web page telling it to upload `~/.ssh` somewhere). It does this by inspecting each tool call before Claude Code executes it.

It is **not a sandbox**. It cannot:

- see what a program does once it runs: a test file the agent writes and then executes can still delete files or open network connections;
- inspect binaries, compiled code or obfuscated scripts;
- protect against a user who disables it.

For untrusted repositories or fully autonomous runs, combine it with Claude Code's sandbox settings, a container or a disposable VM, and least-privilege credentials.

## Design decisions

- Decisions fail open by default so an internal error does not block work; set `"fail_mode": "closed"` where blocking is safer.
- When a shell command cannot be parsed, the default is to ask, not to allow.
- Logs never contain file contents, and anything matching a secret detector is redacted before it is written.
- The policy files and `.claude/settings.json` are on the ask-before-writing list, so the agent cannot quietly loosen its own guardrails.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's private vulnerability reporting for this repository (Security → Report a vulnerability). Include a command or tool input that bypasses a rule, the expected and actual decision, and the output of `harness --version`.

Bypasses of a deny rule are treated as security bugs and fixed in a patch release with a regression test.
