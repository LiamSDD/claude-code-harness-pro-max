# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [2.1.0] - 2026-11-24

### Added

- `harness limits`: minimum and maximum reply length (words, characters) and per-response token cap; minimum and maximum prompt length; effort, model, turns, budget, subagent concurrency, per-session count and depth, web searches, bash output, file read size, compaction threshold and thinking. `show`, `set`, `output` and `input` shortcuts, and `reset` for one limit, a group or all; `--shared` and `--user` scopes. Prompt limits block in `UserPromptSubmit`; reply limits are injected on every prompt and enforced once per turn in `Stop`.
- `managing-limits` skill.
- Cross-platform packaging: Codex (`.codex-plugin`, `.agents/plugins/marketplace.json`), Cursor (`.cursor-plugin` with `hooks/hooks-cursor.json`), Antigravity, Gemini CLI (`gemini-extension.json`, `GEMINI.md`), Kimi Code; tool-name maps for each and a generic fallback.
- `harness hook --platform cursor`: Cursor adapter for `sessionStart`, `beforeSubmitPrompt`, `beforeShellExecution`, `beforeReadFile`, `beforeMCPExecution`, `afterFileEdit`, `stop`, `sessionEnd`, `subagentStart`, `subagentStop`; bootstrap for other platforms.
- `AGENTS.md` and `docs/platforms.md`.

### Changed

- Skills and subagents moved to the top-level `skills/` and `agents/` folders (the layout every platform expects); the Python package bundles them.

### Fixed

- The project is located from the session's current directory before `CLAUDE_PROJECT_DIR`, so a session that changed folders uses that folder's policy (found by a live test: subagent routing was ignored after a folder change).
- `harness init` from a source checkout wires hooks to the checkout's `bin/harness` instead of a module that is not installed.

## [2.0.0] - 2026-11-24

Renamed to **Claude Code Harness Pro Max**. Plugin and skill id `harness-pro-max`, Python package `harness-pro-max` (module `harnesspro`), command `harness`.

### Added

- Token guards on `PreToolUse`: unchanged full re-reads (per agent, reset on clear and compaction), generated and vendored files (`cost.generated_paths`), oversized reads (`cost.max_read_bytes`), and context-flooding commands (`cat` of large files, `find /`, `tail -f`, `watch`, container and journal logs without limits, unbounded `git log`, recursive listings). Rules `token-duplicate-read`, `token-generated-read`, `token-large-read`, `token-output-flood`.
- Subagent control: routing to a model per `subagent_type` through `updatedInput` (`subagents.models`), per-session and concurrency limits (`subagent-limit`, `subagent-concurrency`), tracking via `SubagentStart` and `SubagentStop`.
- Session budgets: incremental spend from the session transcript (`cost.session_budget_usd`, `warn_at`, `on_budget`), shown in the status line.
- `harness cost`: spend, tokens and cache hit rate by model, main session vs subagents, session and day, tool output volume, repeated reads, and ranked recommendations; editable prices (`cost.prices`).
- `harness optimize`: `balanced` and `lean` profiles that set Claude Code limits (`BASH_MAX_OUTPUT_LENGTH`, `CLAUDE_CODE_FILE_READ_MAX_OUTPUT_TOKENS`, `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`, `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION`, `CLAUDE_CODE_DISABLE_TERMINAL_TITLE`, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`), deny generated-file reads and route subagents; preview by default.
- `harness upstream`: compares Claude Code's hooks reference with the events the harness handles and registers new ones.
- Handlers for `SubagentStart`, `PostCompact`, `ConfigChange` (warns when harness hooks are removed), `PermissionDenied`, `StopFailure`, `PostModelSwitch`, `TaskCreated`, `TaskCompleted`, `InstructionsLoaded`; any unknown event is logged instead of failing.
- Skills `orchestrating-agent-teams` and `optimizing-token-usage`; `explorer` subagent on haiku.

### Changed

- No comments or docstrings in code; documentation lives in Markdown.
- `harness vet` patterns moved to `defaults/vet_rules.json`.

## [1.1.0] - 2026-11-24

### Added

- 14 engineering-workflow skills: `using-harness-pro-max`, `brainstorming`, `writing-plans`, `executing-plans`, `subagent-driven-development` (with implementer and task-review briefs), `test-driven-development` (with `writing-good-tests.md`), `systematic-debugging` (with root-cause tracing, defense in depth and condition-based waiting), `verification-before-completion`, `requesting-code-review`, `receiving-code-review`, `dispatching-parallel-agents`, `using-git-worktrees`, `finishing-a-development-branch`, `writing-skills`. Adapted from obra/superpowers (MIT) and integrated with the harness.
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

[2.1.0]: https://github.com/priveight02/claude-code-harness-pro-max/releases/tag/v2.1.0
[2.0.0]: https://github.com/priveight02/claude-code-harness-pro-max/releases/tag/v2.0.0
[1.1.0]: https://github.com/priveight02/claude-code-harness-pro-max/releases/tag/v1.1.0
[1.0.0]: https://github.com/priveight02/claude-code-harness-pro-max/releases/tag/v1.0.0
