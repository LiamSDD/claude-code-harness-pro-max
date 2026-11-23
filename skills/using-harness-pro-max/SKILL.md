---
name: using-harness-pro-max
description: Use when starting any task, to pick the right Harness Pro Max skill. Maps situations (new feature, bug, plan, many agents, cost, review, finishing) to the skill that covers them, and explains how the harness guardrails, token guards, progress files and verification checks behave.
---

# Using Claude Code Harness Pro Max

The harness gives you guardrails, token guards, memory between sessions (`.claude/harness/`) and checks before you finish. The skills below are proven ways of working. Before you start a task, check whether one fits and follow it. The user's instructions (CLAUDE.md, direct requests) always come first.

## Which skill when

| Situation | Skill |
| --- | --- |
| Something new to build, with open choices | `brainstorming`, then `writing-plans` |
| A plan with several tasks | `executing-plans` (inline) or `subagent-driven-development` (agent per task) |
| Wide reading, many independent changes, verification by others | `orchestrating-agent-teams` |
| Large codebase, long session, budget, "reduce cost" | `optimizing-token-usage` |
| "Keep answers under N words", "limit my prompts", "low effort", "reset limits" | `managing-limits` |
| Work across sessions, "continue", "next feature" | `feature-loop` |
| Writing production code | `test-driven-development` |
| A bug, failing test or surprising behaviour | `systematic-debugging` |
| About to say it works, is fixed or is done | `verification-before-completion` |
| Ready for a second pair of eyes | `requesting-code-review` |
| Review feedback arrived | `receiving-code-review` |
| Two or more independent problems | `dispatching-parallel-agents` |
| Work that should not touch the current branch | `using-git-worktrees` |
| Tests green, ready to integrate | `finishing-a-development-branch` |
| Ending a session or running out of context | `session-handoff` |
| Before a release | `release-check` |
| The harness blocked something | `harness-policy` |
| Writing or editing a skill | `writing-skills` |

## Subagents

| Agent | Use for | Model |
| --- | --- | --- |
| `explorer` | Finding and summarizing code or logs, read-only | haiku |
| `implementer` | One plan task, test first | inherit |
| `code-reviewer` | Reviewing a diff | inherit |
| `test-runner` | Running tests and diagnosing failures | inherit |
| `security-auditor` | Security review before release | inherit |
| `planner` | Turning a request into a feature list | inherit |
| `evaluator` | Independent verification of a feature | inherit |

## What the harness does around you

- **Denied tool calls** carry a rule id and a reason. Security denials: do not look for another route; tell the user what you need. Token denials (`token-*`): follow the suggestion in the reason (Grep, a range read, a bounded command).
- **Unchanged re-reads are refused**: the file is still in your context.
- **Subagents** may be routed to a cheaper model and are capped in number and concurrency by the policy.
- **Budget**: when the session nears its budget you are told; once it is reached, tool calls need the user's confirmation.
- **Claims are checked**: saying tests pass or a bug is fixed after edits, without a successful test or build since, sends you back to verify.
- **The stop gate**, when enabled, runs the tests when you finish.
- **Session context** at start-up lists git state, the next feature and recent progress notes.

## On other agents

Tool names differ per platform; read the matching reference: [Claude Code](references/claude-code-tools.md), [Codex](references/codex-tools.md), [Cursor](references/cursor-tools.md), [Gemini CLI](references/gemini-tools.md), [Antigravity](references/antigravity-tools.md), [Kimi Code](references/kimi-tools.md), [OpenCode](references/opencode-tools.md), [anything else](references/generic-tools.md).

## Commands

```bash
harness progress show | start <id> | done <id> "evidence" | note "..." | import <plan.md>
harness check bash "<command>"
harness cost --since 1d
harness limits show --set-only
```
