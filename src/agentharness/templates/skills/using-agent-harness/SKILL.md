---
name: using-agent-harness
description: Use when starting any task, to pick the right agent-harness skill. Maps situations (new feature, bug, plan, review, finishing) to the skill that covers them, and explains how the harness guardrails, progress files and verification gate fit together.
---

# Using agent-harness

The harness gives you guardrails (some tool calls are denied or need confirmation), memory between sessions (`.claude/harness/`), and checks before you finish. The skills below are proven ways of working. Before you start a task, check whether one of them fits; if it does, follow it. Your user's instructions (CLAUDE.md, direct requests) always come first.

## Which skill when

| Situation | Skill |
| --- | --- |
| Something new to build, and the request leaves real choices open | `brainstorming`, then `writing-plans` |
| A written plan or spec with several tasks | `executing-plans` (you implement) or `subagent-driven-development` (fresh subagent per task) |
| Work spanning sessions, or "continue" / "next feature" | `feature-loop` |
| Writing any production code | `test-driven-development` |
| A bug, failing test or surprising behaviour | `systematic-debugging` |
| About to say something works, is fixed or is done | `verification-before-completion` |
| A change is ready for a second pair of eyes | `requesting-code-review` |
| Review feedback arrived | `receiving-code-review` |
| Two or more independent problems | `dispatching-parallel-agents` |
| Work that should not touch the current branch | `using-git-worktrees` |
| Implementation finished, tests green | `finishing-a-development-branch` |
| Ending a session or running out of context | `session-handoff` |
| Before a release | `release-check` |
| The harness blocked something | `harness-policy` |
| Writing or editing a skill | `writing-skills` |

Process skills (brainstorming, debugging) decide *how* to approach the work; use them before skills about a specific technology.

## What the harness does around you

- **Denied tool calls** come with a rule id and a reason. Do not look for another route to the same action. Tell the user what you need and why.
- **Session context** at start-up lists git state, recent commits, the next feature and the latest progress notes. Trust it over memory.
- **Claims are checked.** If you say tests pass or a bug is fixed without having run a test or build command since your last edit, the harness sends you back to verify.
- **The stop gate**, when enabled, runs the project's tests when you finish and returns failures to you.
- **Progress lives in files**: `harness progress show`, `harness progress note "..."`.

## Commands you can run

```bash
harness progress show | start <id> | done <id> "evidence" | note "..."
harness progress import docs/plans/<plan>.md
harness check bash "<command>"      # would the policy allow it?
harness vet <path>                  # security-scan a skill or plugin before using it
harness skills check                # lint skills
```
