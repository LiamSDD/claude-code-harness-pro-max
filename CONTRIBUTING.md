# Contributing

## Setup

```bash
git clone https://github.com/LiamSDD/claude-code-harness-pro-max && cd claude-code-harness-pro-max
python3 -m venv .venv && . .venv/bin/activate
python3 -m pip install --upgrade pip
pip install -e ".[dev]"
make check
```

The `pip` upgrade matters on older interpreters: the pip that ships with Python 3.9 (21.2) cannot do an editable install from `pyproject.toml`. `make test` runs only the unit tests (standard library `unittest`, about 30 seconds); `make format` applies `ruff` fixes. There is no hosted CI: `make check` on your machine is the gate, so run it before you push.

Code files contain no comments or docstrings; document behaviour in `docs/`. The package has no runtime dependencies and supports Python 3.9 to 3.13. Keep it that way: hooks start a fresh interpreter on every tool call, so every import costs latency.

## Making a change

1. Add or change a test first. Policy changes need a test in `tests/test_policy.py` for the case you are fixing **and** for an everyday command that must stay allowed. False positives make people turn guardrails off.
2. `make check` runs lint, formatting, the full suite, policy validation and a secret scan of the source.
3. Update `CHANGELOG.md` under `Unreleased` and the rule tables in `docs/policy.md` if behaviour changed.

Never put a real-looking token in a test. Build it at runtime with `helpers.fake(...)` so scanners and GitHub push protection do not flag the repository.

## Proposing a change

1. For anything bigger than a small fix, open an issue first so the approach can be agreed before you write code. Wrong decisions go in a **False positive** report, other defects in a **Bug report**; questions and open-ended ideas go to [Discussions](https://github.com/LiamSDD/claude-code-harness-pro-max/discussions). Rule bypasses are security issues: see [SECURITY.md](SECURITY.md).
2. Issues labelled [`good first issue`](https://github.com/LiamSDD/claude-code-harness-pro-max/labels/good%20first%20issue) are small, scoped and have acceptance criteria.
3. Fork the repository, branch from `main` and keep each pull request to one change. Fill in the pull request template.

## Commit messages

Write the subject as a short imperative sentence, capitalised and without a trailing full stop, saying what changed: `Load agents from the standard agents/ folder`, `Make the README flow diagram readable`. Use the body to explain why. Squash-merged pull requests get the PR number appended.

## Adding a rule

- Give it a stable kebab-case id; ids appear in user policies (`disable`) and audit logs, so do not rename them.
- Prefer `ask` unless the action is destructive and almost never intended.
- The reason should tell Claude what to do instead.

## Releasing

1. Bump the version in `pyproject.toml`, `src/harnesspro/__init__.py` and `.claude-plugin/plugin.json`.
2. Move `Unreleased` entries in `CHANGELOG.md` under the new version.
3. Run `make check`, commit, then tag `vX.Y.Z` and push the tag.
4. Create the GitHub release from that tag with the new `CHANGELOG.md` section as its notes, for example `gh release create vX.Y.Z --title vX.Y.Z --notes-file notes.md`. The release workflow in `.github/workflows/release.yml` is disabled, so nothing is built or attached automatically.

## Code of conduct

Everyone taking part is expected to follow the [code of conduct](CODE_OF_CONDUCT.md).
