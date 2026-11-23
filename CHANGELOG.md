# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-11-24

### Added

- 14 engineering-workflow skills: `using-agent-harness`, `brainstorming`, `writing-plans`, `executing-plans`, `subagent-driven-development` (with implementer and task-review briefs), `test-driven-development` (with `writing-good-tests.md`), `systematic-debugging` (with root-cause tracing, defense in depth and condition-based waiting), `verification-before-completion`, `requesting-code-review`, `receiving-code-review`, `dispatching-parallel-agents`, `using-git-worktrees`, `finishing-a-development-branch`, `writing-skills`. Adapted from obra/superpowers (MIT) and integrated with the harness.
- `implementer` subagent.
- `harness vet`: supply-chain scanner for skills, plugins and repositories (hidden Unicode including tag smuggling, prompt injection, dangerous shell in scripts and code blocks via the policy engine, code execution, remote network calls, encoded blobs, secrets, binaries, escaping symlinks, hook commands and MCP servers), with counted inline suppression.
- `harness skills list|check`: skill discovery and a linter for frontmatter, size, links and injection.
- Claim check on `Stop` (`verify_claims`): success claims after edits need a successful test or build command since the last edit.
- `harness progress import <plan.md>`: one feature per `### Task N:` heading, checkbox lines as steps, idempotent.
- Session start lists available skills (`context.skills`).
- The repository root is a standalone skill (`SKILL.md`).
- CI runs `vet` and `skills check` on the repository itself; tests assert the source contains no invisible characters.

### Fixed

- `[[ ... ]]` test expressions are parsed as one command, so regex alternation inside them is no longer read as a pipe.

## [1.0.0] - 2026-11-23

### Added

- Policy engine for `PreToolUse` with a shell parser that follows pipelines, `&&`/`||`/`;` chains, subshells, command and process substitution, heredocs and here-strings into shells, `bash -c`/`eval`, and wrappers such as `sudo`, `env`, `timeout`, `nice` and `xargs`. Tracks `cd` within a chain.
- 27 rules with stable ids covering destructive file and disk operations, remote code execution, git history rewrites and hook bypass, secret files, protected and sensitive paths, writes outside the project, credentials in content and command lines, exfiltration domains, uploads, publishing, infrastructure and database destruction, privilege escalation and destructive MCP tools.
- Layered JSON policy (defaults, user, project, local, `$HARNESS_POLICY`) with merge semantics, `!` list replacement, schema validation, custom regex rules and per-rule disabling. `enforce`, `warn` and `off` modes; fail-open or fail-closed.
- Secret scanner with 24 detectors, placeholder and entropy filtering and redaction, used on writes, prompts, commands, the audit log and `harness scan` (including `--staged` for pre-commit).
- Hooks for `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PostToolUseFailure`, `Stop`, `SubagentStop`, `PreCompact`, `SessionEnd` and `Notification`.
- Verification gate on `Stop` with retry limit, timeout and skip-when-unchanged.
- Post-edit formatter and linter hooks.
- Long-running work support: `features.json` with a `passes` flag, append-only `progress.md`, session-start summaries and compaction checkpoints.
- Audit log in JSON Lines with locking, rotation and redaction; `harness audit` with filters and statistics.
- Status line with git state, model, context usage, cost, duration, denied actions and feature progress.
- `harness init` with `minimal`, `standard` and `strict` profiles, test-command detection and an idempotent, non-destructive settings merge.
- `harness doctor`, which validates every policy layer, runs a behavioural self-test and executes the configured hook.
- Subagents: `code-reviewer`, `test-runner`, `security-auditor`, `planner`, `evaluator`. Skills: `feature-loop`, `session-handoff`, `release-check`, `harness-policy`.
- Claude Code plugin manifest, hooks file and single-plugin marketplace.

[1.1.0]: https://github.com/priveight02/agent-harness/releases/tag/v1.1.0
[1.0.0]: https://github.com/priveight02/agent-harness/releases/tag/v1.0.0
