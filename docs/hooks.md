# Hooks

Claude Code runs `harness hook <Event>` with the event JSON on stdin. The table shows what each handler does and what it returns, using the [documented contract](https://code.claude.com/docs/en/hooks).

| Event | Matcher | Does | Returns |
| --- | --- | --- | --- |
| `SessionStart` | `startup\|resume\|clear\|compact` | prunes old session state, builds context: guardrail notice, git status, changed files, recent commits, feature list, last progress entries, policy errors | `hookSpecificOutput.additionalContext`; `systemMessage` if a policy layer is broken |
| `UserPromptSubmit` | — | scans the prompt for provider tokens | nothing, a warning plus context for Claude, or `decision: "block"` |
| `PreToolUse` | `Bash\|Read\|Write\|Edit\|MultiEdit\|NotebookEdit\|Grep\|WebFetch\|Agent\|Task\|mcp__.*` | security policy, token guards, budget, subagent limits and model routing | nothing, `permissionDecision: "ask" \| "deny"` with a reason, or `allow` with `updatedInput` for a routed subagent |
| `PostToolUse` | `*` | counts calls and output size, tracks edits and full reads, updates spend, runs formatters | `additionalContext` when a formatter fails or the budget warning fires |
| `PostToolUseFailure` | `*` | logs the first line of the error | nothing |
| `Stop` | — | runs the verification gate if enabled and files changed | nothing, or `decision: "block"` with the test output |
| `SubagentStop` | — | logs | nothing |
| `PreCompact` | — | appends a checkpoint (edited files, counters) to `progress.md` | plain text: compaction instructions |
| `SessionEnd` | — | logs a session summary, prunes state older than 14 days | nothing |
| `Notification` | — | optional desktop notification | nothing |
| `SubagentStart` | — | tracks running subagents for the concurrency limit | nothing |
| `PostCompact` | — | resets read deduplication | nothing |
| `ConfigChange` | — | warns when `.claude/settings.json` no longer runs the harness | `systemMessage` |
| `PermissionDenied`, `StopFailure`, `PostModelSwitch`, `TaskCreated`, `TaskCompleted`, `InstructionsLoaded` | — | logged | nothing |
| any other event | — | logged, so new Claude Code events never break the harness | nothing |

## Exit codes

- `0` with JSON on stdout: a decision or context.
- `0` with no output: nothing to add.
- `1`: the harness hit an internal error. Claude Code shows a hook error and carries on (fail open). With `fail_mode: "closed"`, `PreToolUse` returns a deny instead.

The harness never uses exit code `2`, so decisions always arrive as structured JSON with a reason.

## Where state lives

```text
.claude/harness/
├── policy.json        committed: project policy
├── policy.local.json  ignored: personal overrides
├── features.json      committed: feature list
├── progress.md        committed: handoff log
├── audit.jsonl        ignored: audit log (+ .1 .2 .3 rotations)
└── state/<session>.json  ignored: per-session counters and edited files
```

Writes take an advisory lock, because Claude Code can run several tools, and therefore several hooks, in parallel.

## Testing a hook by hand

```bash
echo '{"session_id":"t","cwd":"'"$PWD"'","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"rm -rf ~"}}' \
  | harness hook PreToolUse
```

Use `harness upstream` to see events Claude Code added since this release.

Set `HARNESS_DEBUG=1` for full tracebacks on internal errors, and `HARNESS_AUDIT_DISABLED=1` to keep a run out of the audit log.
