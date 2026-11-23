---
name: harness-pro-max
description: Use when starting software work, when planning, implementing, debugging, reviewing or finishing code, when coordinating several subagents, when cost or tokens matter, or when the user says "continue" on multi-session work. Engineering workflows (TDD, debugging, verification, plans, agent teams, token optimization, review) plus cost, progress and safety tools.
---

# Claude Code Harness Pro Max

Workflows and tools for Claude Code. As a plugin it also installs guardrail and token-guard hooks; as a skill (this folder in `~/.claude/skills/harness-pro-max`) it provides the workflows and the `bin/harness` tools.

## Pick a workflow

| Situation | Read |
| --- | --- |
| New work with open choices | [brainstorming](skills/brainstorming/SKILL.md), then [writing-plans](skills/writing-plans/SKILL.md) |
| Carry out a plan yourself | [executing-plans](skills/executing-plans/SKILL.md) |
| Carry out a plan with an agent per task | [subagent-driven-development](skills/subagent-driven-development/SKILL.md) |
| Many files to read, many agents, independent changes | [orchestrating-agent-teams](skills/orchestrating-agent-teams/SKILL.md) |
| Large codebase, long session, budget | [optimizing-token-usage](skills/optimizing-token-usage/SKILL.md) |
| Reply, prompt, effort, model, budget or agent limits | [managing-limits](skills/managing-limits/SKILL.md) |
| Multi-session work, "continue" | [feature-loop](skills/feature-loop/SKILL.md) |
| Writing production code | [test-driven-development](skills/test-driven-development/SKILL.md) |
| A bug or failing test | [systematic-debugging](skills/systematic-debugging/SKILL.md) |
| About to say it works | [verification-before-completion](skills/verification-before-completion/SKILL.md) |
| Review | [requesting-code-review](skills/requesting-code-review/SKILL.md), [receiving-code-review](skills/receiving-code-review/SKILL.md) |
| Independent problems | [dispatching-parallel-agents](skills/dispatching-parallel-agents/SKILL.md) |
| Isolation and integration | [using-git-worktrees](skills/using-git-worktrees/SKILL.md), [finishing-a-development-branch](skills/finishing-a-development-branch/SKILL.md) |
| Ending a session | [session-handoff](skills/session-handoff/SKILL.md) |
| Releasing | [release-check](skills/release-check/SKILL.md) |
| Writing a skill | [writing-skills](skills/writing-skills/SKILL.md) |

Full map: [using-harness-pro-max](skills/using-harness-pro-max/SKILL.md).

## Subagent briefs

[agents](agents): `explorer` (haiku, read-only search), `implementer`, `code-reviewer`, `test-runner`, `security-auditor`, `planner`, `evaluator`. As a plugin they are registered automatically; as a skill, pass the file's instructions to a subagent.

## Tools

`bin/harness` runs with Python 3.9+, no installation. Run from the project directory:

```bash
python3 <this-folder>/bin/harness cost --since 7d          # spend by model and agent, with fixes
python3 <this-folder>/bin/harness optimize                 # preview token-saving settings (--apply to write)
python3 <this-folder>/bin/harness progress show            # feature list
python3 <this-folder>/bin/harness progress import plan.md  # plan tasks into features
python3 <this-folder>/bin/harness check bash "<command>"   # would the policy allow it
python3 <this-folder>/bin/harness vet <path>               # review a third-party skill or plugin
```
