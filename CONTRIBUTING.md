# Contributing

## Setup

```bash
git clone https://github.com/priveight02/claude-code-harness-pro-max && cd claude-code-harness-pro-max
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
make check
```

Code files contain no comments or docstrings; document behaviour in `docs/`. The package has no runtime dependencies and supports Python 3.9 to 3.13. Keep it that way: hooks start a fresh interpreter on every tool call, so every import costs latency.

## Making a change

1. Add or change a test first. Policy changes need a test in `tests/test_policy.py` for the case you are fixing **and** for an everyday command that must stay allowed. False positives make people turn guardrails off.
2. `make check` runs lint, formatting, the full suite, policy validation and a secret scan of the source.
3. Update `CHANGELOG.md` under `Unreleased` and the rule tables in `docs/policy.md` if behaviour changed.

Never put a real-looking token in a test. Build it at runtime with `helpers.fake(...)` so scanners and GitHub push protection do not flag the repository.

## Adding a rule

- Give it a stable kebab-case id; ids appear in user policies (`disable`) and audit logs, so do not rename them.
- Prefer `ask` unless the action is destructive and almost never intended.
- The reason should tell Claude what to do instead.

## Releasing

1. Bump the version in `pyproject.toml`, `src/harnesspro/__init__.py` and `.claude-plugin/plugin.json`.
2. Move `Unreleased` entries in `CHANGELOG.md` under the new version.
3. Tag `vX.Y.Z` and push the tag; the release workflow tests, builds and attaches the artifacts.
