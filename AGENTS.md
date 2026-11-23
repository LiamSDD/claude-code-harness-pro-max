# Agent instructions

This repository is Claude Code Harness Pro Max: skills in `skills/`, subagent briefs in `agents/`, the `harness` command in `bin/harness`, Python source in `src/harnesspro/`.

## Using it

- Before a task, read `skills/using-harness-pro-max/SKILL.md` and the tool mapping for your agent in `skills/using-harness-pro-max/references/`.
- Commands: `python3 bin/harness <command>`; list them with `python3 bin/harness --help`.

## Working on it

- Tests: `python3 -m unittest discover -s tests -q`. Everything CI runs: `make check`.
- Python 3.9 compatible, standard library only, no comments or docstrings in code files; explanations go in `docs/`.
- Every policy change needs a test for the blocked case and one for an everyday command that must stay allowed.
- Never put a real-looking credential in a test; build it with `helpers.fake(...)`.
