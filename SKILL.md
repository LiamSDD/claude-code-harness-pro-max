---
name: agent-harness
description: Use when starting software work in a project, when planning, implementing, debugging, reviewing or finishing code, when the user says "continue" on multi-session work, or before installing a third-party skill or plugin. Engineering workflows (TDD, systematic debugging, verification, plans, subagent execution, code review) plus guardrail and progress tools.
---

# agent-harness

This folder is both a Claude Code plugin (guardrail hooks, subagents, skills) and a standalone skill. Installed as a skill (cloned into `~/.claude/skills/agent-harness`), it gives you the workflows below; the hooks only run when it is installed as a plugin or with `harness init`.

## Pick a workflow

Read the one that fits before you start. Each is short.

| Situation | Read |
| --- | --- |
| Something new to build with open choices | [brainstorming](src/agentharness/templates/skills/brainstorming/SKILL.md), then [writing-plans](src/agentharness/templates/skills/writing-plans/SKILL.md) |
| Executing a plan yourself | [executing-plans](src/agentharness/templates/skills/executing-plans/SKILL.md) |
| Executing a plan with a subagent per task | [subagent-driven-development](src/agentharness/templates/skills/subagent-driven-development/SKILL.md) |
| Multi-session work, "continue", "next feature" | [feature-loop](src/agentharness/templates/skills/feature-loop/SKILL.md) |
| Writing production code | [test-driven-development](src/agentharness/templates/skills/test-driven-development/SKILL.md) |
| A bug or failing test | [systematic-debugging](src/agentharness/templates/skills/systematic-debugging/SKILL.md) |
| About to say it works or is done | [verification-before-completion](src/agentharness/templates/skills/verification-before-completion/SKILL.md) |
| Want a review | [requesting-code-review](src/agentharness/templates/skills/requesting-code-review/SKILL.md) |
| Got review feedback | [receiving-code-review](src/agentharness/templates/skills/receiving-code-review/SKILL.md) |
| Several independent problems | [dispatching-parallel-agents](src/agentharness/templates/skills/dispatching-parallel-agents/SKILL.md) |
| Isolate work from the current branch | [using-git-worktrees](src/agentharness/templates/skills/using-git-worktrees/SKILL.md) |
| Tests green, ready to integrate | [finishing-a-development-branch](src/agentharness/templates/skills/finishing-a-development-branch/SKILL.md) |
| Ending a session | [session-handoff](src/agentharness/templates/skills/session-handoff/SKILL.md) |
| Before a release | [release-check](src/agentharness/templates/skills/release-check/SKILL.md) |
| Writing a skill | [writing-skills](src/agentharness/templates/skills/writing-skills/SKILL.md) |

The full map, with how the harness checks your work, is in [using-agent-harness](src/agentharness/templates/skills/using-agent-harness/SKILL.md).

## Tools in this folder

`bin/harness` runs with any Python 3.9+ and needs no installation:

```bash
python3 bin/harness vet <path>                   # security-scan a skill, plugin or repo before using it
python3 bin/harness skills check <path>          # lint a skill's frontmatter, size and links
python3 bin/harness check bash "<command>"       # would the guardrail policy allow this?
python3 bin/harness progress show                # feature list for multi-session work
python3 bin/harness progress import <plan.md>    # turn a plan's tasks into tracked features
python3 bin/harness progress note "<text>"       # append to the handoff log
```

Run them from the project directory, giving the path to this folder's `bin/harness`.

## Subagent roles

Briefs for these roles live in [src/agentharness/templates/agents](src/agentharness/templates/agents): `implementer`, `code-reviewer`, `test-runner`, `security-auditor`, `planner`, `evaluator`. When installed as a plugin they are registered automatically; as a skill, read the file and pass its instructions to a general-purpose subagent.
