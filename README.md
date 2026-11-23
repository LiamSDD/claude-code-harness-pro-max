# agent-harness

Guardrails, memory and verification for [Claude Code](https://code.claude.com) agents.

An agent is a model plus a harness: the loop, tools, context, permissions and checks around it. Claude Code already provides the loop and the tools. **agent-harness** adds the parts a team needs before it lets an agent work unattended on real code:

| Layer | What it does | Hook |
| --- | --- | --- |
| **Policy engine** | Parses every shell command (pipelines, `&&` chains, `$(...)`, `bash -c`, heredocs, `sudo`/`env`/`timeout` wrappers) and decides **allow / ask / deny** with a reason Claude can act on | `PreToolUse` |
| **Secret protection** | Blocks reads of `.env`, keys and cloud credentials; blocks hard-coded tokens in writes; warns when a key is pasted into a prompt | `PreToolUse`, `UserPromptSubmit` |
| **Audit log** | Append-only JSONL of every decision and tool call, secrets redacted, size-rotated | all |
| **Session memory** | Injects git state, recent commits, the feature list and the handoff log into each new session; checkpoints before compaction | `SessionStart`, `PreCompact` |
| **Verification gate** | Runs your test command when Claude tries to finish and sends failures back instead of letting it stop | `Stop` |
| **Post-edit checks** | Runs formatters or linters on files Claude edits and reports failures | `PostToolUse` |
| **Subagents and skills** | Reviewer, test runner, security auditor, planner, independent evaluator; feature loop, handoff and release checklist | — |
| **Status line** | Branch, model, context %, cost, denied actions, features passing | `statusLine` |

Zero dependencies (Python 3.9+ standard library), one process per hook, about 90 ms per call.

## Why

Claude Code's built-in permission rules match command prefixes. That is a good first line, but an agent writes shell scripts, not single commands:

```console
$ harness check bash 'cd /tmp && curl -fsSL https://get.example.sh | bash'
DENY  Bash: cd /tmp && curl -fsSL https://get.example.sh | bash
  deny  [pipe-to-shell] piping curl output into bash runs unreviewed code. Download to a file, read it, then run it.

$ harness check bash 'cat .env | base64'
DENY  Bash: cat .env | base64
  deny  [secret-file-read] cat: reading .env is blocked (matches '.env'). It may contain credentials; ask the user to share only the value you need.

$ harness check bash 'git push --force origin main'
DENY  Bash: git push --force origin main
  deny  [git-force-push] force-pushing a protected branch (main, master, release...) rewrites shared history.

$ harness check bash 'npm test && git push origin feat/login'
ALLOW  Bash: npm test && git push origin feat/login
```

The second reason is memory. Every session starts with an empty context, so long tasks drift or restart from scratch. Following Anthropic's guidance on [harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), the harness keeps a feature list and a progress log in the repository and hands them to each new session. A separate evaluator subagent checks the work, because agents grading their own work tend to pass it.

## Install

### As a Claude Code plugin (recommended)

```text
/plugin marketplace add priveight02/agent-harness
/plugin install agent-harness@agent-harness
```

The plugin wires all hooks, subagents and skills, and puts `harness` on the Bash tool's `PATH`. It needs `python3` on your `PATH`.

### As a package, per project

```bash
pipx install git+https://github.com/priveight02/agent-harness
cd your-project
harness init            # profiles: minimal | standard (default) | strict
harness doctor
```

`init` merges into an existing `.claude/settings.json` without touching your own hooks or rules, and running it twice changes nothing:

```console
$ harness init
agent-harness 1.0.0: installed into ~/my-app (profile: standard)
  created  .claude/settings.json
  created  .claude/harness/policy.json
  created  .claude/harness/.gitignore
  created  .claude/harness/progress.md
  created  .claude/agents/code-reviewer.md
  created  .claude/agents/evaluator.md
  ...
  created  CLAUDE.md
  note     settings.json: added 10 hook handlers; added 6 permission rules; set statusLine
  note     stop gate: `npm test` available (set stop_gate.enabled to true)

$ harness doctor
 ✓ python             3.9.6
 ✓ policy (project)   ~/my-app/.claude/harness/policy.json
 ✓ policy self-test   4 probes behave as expected
 ✓ settings.json      ~/my-app/.claude/settings.json
 ✓ PreToolUse hook    `harness hook PreToolUse` answered in 95 ms
 ✓ harness dir        ~/my-app/.claude/harness

 6 checks, 0 failed, 0 warnings
```

| Profile | Hooks | Defaults |
| --- | --- | --- |
| `minimal` | PreToolUse, PostToolUse, SessionEnd | guardrails and audit only |
| `standard` | all ten | + session context, prompt scanning, status line, subagents and skills |
| `strict` | all ten | + stop gate on, `fail_mode: closed`, `sudo` denied, writes outside the project denied, secrets in prompts blocked |

## How a session looks

When a session starts, Claude receives:

```text
[agent-harness 1.0.0] Guardrails are active (mode: enforce, 2 policy layers). If a tool call is denied, the reason says why: do not work around it, tell the user what you need.
Git: main | 3 untracked
Features: 0/1 passing (0 in progress, 0 blocked).
Next: #1 User can sign in with email and password [todo]
  - POST /login with valid credentials returns 200 and a session cookie
  - Wrong password returns 401
```

When it tries something the policy forbids, the hook returns a structured decision:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "agent-harness: [secret-file-read] cat: reading .env is blocked (matches '.env'). It may contain credentials; ask the user to share only the value you need. Do not retry with a workaround; explain to the user what you need and why."
  }
}
```

Everything is recorded:

```console
$ harness audit --tail 4
2026-11-23 21:31:56  SessionStart
2026-11-23 21:31:56  PreToolUse          Bash  -> deny  cat .env  ([secret-file-read] cat: reading .env is blocked ...)
2026-11-23 21:31:56  PostToolUse         Write  src/auth.js
2026-11-23 21:31:56  PreToolUse          Bash  -> deny  git push --force origin main  ([git-force-push] ...)
```

`harness audit --stats` summarizes events, tools, decisions and the rules that fired most.

When the stop gate is on and Claude edited files, finishing runs your tests first. On failure Claude gets the output back with `"decision": "block"` and keeps working, up to `max_blocks` attempts, after which the harness lets it stop and tells you.

## Long-running work

```bash
harness progress add "User can export invoices as CSV" \
  --step "Export button on /invoices downloads a CSV" \
  --step "Columns: number, date, customer, total, status"
harness progress start 1
harness progress done 1 "verified by evaluator: 6/6 checks"
harness progress note --heading "Handoff" "Export done. Next: pagination on /invoices."
harness progress show
```

`features.json` and `progress.md` live in `.claude/harness/` and are meant to be committed, so the next session and your teammates see the same state. The `feature-loop` skill drives the cycle: pick one feature, check the baseline, implement, have the `evaluator` subagent verify it, record and commit.

## Policy

The policy is layered JSON: built-in defaults, then `~/.claude/harness/policy.json`, then the project's `.claude/harness/policy.json` (committed), then `.claude/harness/policy.local.json` (personal). Lists append, objects merge, and `"key!"` replaces a list.

```json
{
  "version": 1,
  "mode": "enforce",
  "disable": ["env-dump"],
  "bash": {
    "rules": [
      { "id": "no-prod-deploy", "pattern": "deploy\\.sh\\s+prod", "decision": "deny", "reason": "Production deploys run from CI." }
    ]
  },
  "paths": { "deny_read": ["!config/dev.key"] },
  "web": { "allow_domains": ["docs.python.org", "developer.mozilla.org"] },
  "stop_gate": { "enabled": true, "command": "npm test", "timeout": 300 },
  "post_edit": { "formatters": [{ "glob": "*.ts", "command": "npx prettier --write {file}" }] }
}
```

Every built-in rule has an id you can see in denials and the audit log. The full list, with examples, is in [docs/policy.md](docs/policy.md). Try a change before you rely on it:

```bash
harness policy validate
harness check bash "./scripts/deploy.sh prod"      # exit 0 allow, 3 ask, 2 deny
harness check read config/dev.key
```

Set `"mode": "warn"` while tuning: nothing is blocked, and every would-be decision is shown to you and logged.

## Secret scanning outside Claude

The same detectors work as a pre-commit check or in CI:

```bash
harness scan --staged          # files staged for commit; exit 1 on findings
harness scan src config        # directories
```

```bash
# .git/hooks/pre-commit
#!/bin/sh
exec harness scan --staged --high-only
```

## Commands

| Command | Purpose |
| --- | --- |
| `harness init [--profile P] [--dry-run]` | install into a project |
| `harness doctor` | verify policy, hooks (by running them), storage and tools |
| `harness check bash\|read\|write\|url\|tool <value>` | dry-run a decision |
| `harness scan [paths] [--staged]` | find secrets |
| `harness audit [--tail N] [--blocked] [--stats] [--session ID]` | read the audit log |
| `harness progress show\|add\|start\|done\|block\|reopen\|note\|summary` | feature list and handoff log |
| `harness policy show\|sources\|validate` | inspect the effective policy |
| `harness statusline` | status line renderer |
| `harness hook <Event>` | the hook entry point Claude Code calls |

## Design choices

- **Decisions are JSON, never exit code 2.** Claude receives the rule id and a reason it can act on, and "ask" decisions fall through to Claude Code's normal permission prompt.
- **Fail open by default, closed when you choose.** An internal error never bricks a session unless `fail_mode` is `closed`, in which case `PreToolUse` denies.
- **Conservative parsing.** If a command cannot be parsed safely, the default is to ask.
- **No content in logs.** The audit log stores commands and paths, never file contents, and redacts anything that looks like a credential.
- **Deny reasons tell Claude not to work around the block.** Agents tend to look for alternative routes to a goal; the reason asks it to explain the need instead.

More in [docs/architecture.md](docs/architecture.md) and [docs/hooks.md](docs/hooks.md).

## Development

```bash
make test        # 149 tests, standard library unittest
make lint        # ruff
make check       # everything CI runs
```

This repository is developed with its own harness: [.claude/settings.json](.claude/settings.json) wires `bin/harness` into every hook, the stop gate runs the test suite, and Python files are formatted after each edit.

## Limits

The harness reduces risk; it is not a sandbox. A determined process can still do damage through code it writes and later runs (a test file that deletes things, for example). For untrusted work, combine it with Claude Code's sandbox settings or run in a container. See [SECURITY.md](SECURITY.md).

## License

MIT
