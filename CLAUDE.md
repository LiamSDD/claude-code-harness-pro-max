# agent-harness

Guardrails, memory and verification for Claude Code, written in standard-library Python (3.9+). This repository is developed with its own harness (see `.claude/settings.json`).

## Commands

- Test: `python3 -m unittest discover -s tests -q` (also `make test`). The stop gate runs this before you finish.
- Lint and format: `make lint`, `make format` (ruff).
- Everything CI runs: `make check`.
- Try a policy decision: `./bin/harness check bash "<command>"` (exit 0 allow, 3 ask, 2 deny).

## Layout

- `src/agentharness/shell.py`: shell tokenizer and command builder. Changes here need tests in `tests/test_shell.py`.
- `src/agentharness/policy.py`: rules. Each rule has a stable id; never rename one.
- `src/agentharness/hooks.py`: one handler per hook event; output must follow the Claude Code hook contract.
- `src/agentharness/defaults/policy.json`: built-in policy. Validate with `./bin/harness policy validate`.
- `src/agentharness/templates/`: CLAUDE.md template, subagents and skills shipped with the plugin and `harness init`.

## Rules

- No runtime dependencies. Every hook is a fresh interpreter, so keep imports light.
- Python 3.9 compatible: no `match`, no `X | Y` types at runtime.
- Every policy change needs a test for the blocked case and one for an everyday command that must stay allowed.
- Never write a real-looking token in a test; use `helpers.fake(...)`.
- Hooks must never crash Claude Code: catch, log to stderr, exit 1 (or deny when `fail_mode` is `closed`).
- Update `CHANGELOG.md` and `docs/policy.md` when behaviour changes.

## Progress

Feature list and handoff log: `./bin/harness progress show` and `.claude/harness/progress.md`.
