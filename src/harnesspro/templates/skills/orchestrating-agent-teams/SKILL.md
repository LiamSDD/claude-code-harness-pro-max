---
name: orchestrating-agent-teams
description: Use when work is too large or too wide for one context - many files or sources to read, several independent changes, a plan with many tasks, or a result that needs independent verification. Chooses a team shape (fan-out, pipeline, specialists, competing hypotheses), sizes it, picks a model per role, writes briefs with a fixed report contract, and keeps the team within the harness limits and budget.
---

# Orchestrating agent teams

Subagents are the main lever for both quality and cost. Each one starts with a clean context, so it reads only what its job needs, and its findings come back as a short report instead of thousands of lines in your context. Used carelessly they multiply spend: every agent re-reads files and pays for its own context.

## 1. Decide whether a team helps

| Situation | Team? |
| --- | --- |
| A question answerable with two or three Greps | No: do it yourself |
| Reading many files, sources or logs to answer one question | Yes: fan-out of readers |
| Independent changes in different files | Yes: one implementer each, isolated |
| A plan with sequential tasks | Pipeline, one task at a time (`subagent-driven-development`) |
| A bug with several plausible causes | Competing hypotheses, one agent per hypothesis |
| A result that must be right | Add an independent reviewer or `evaluator` |
| Changes that touch the same files | No parallelism: one agent, or sequential agents |

## 2. Pick the shape

- **Fan-out / fan-in.** Split the input (directories, modules, sources, test files) into independent slices, one agent per slice, all dispatched in a single message so they run concurrently. You merge the reports.
- **Pipeline.** planner → implementer → code-reviewer → evaluator, each stage with a fresh agent and only the previous stage's output.
- **Specialists.** One question answered from several angles in parallel: security-auditor, test-runner, code-reviewer on the same diff.
- **Competing hypotheses.** For a stubborn bug, one agent per hypothesis, each asked to prove or disprove its own with evidence. Keep the ones with evidence.
- **Generate and verify.** One agent produces, a different one checks against the acceptance steps. Never let the producer grade itself.

## 3. Size and route it

- Start small: 2 to 5 agents. More agents means more duplicated reading; add agents only when slices are truly independent.
- Match the model to the job. The harness can do this automatically (`subagents.models` in the policy, or `harness optimize`):

  | Role | Model |
  | --- | --- |
  | `explorer`, search, summarizing files or logs | haiku |
  | `implementer`, `test-runner`, general work | sonnet |
  | `code-reviewer`, `security-auditor`, `evaluator` on critical code, `planner` for large designs | the session's model |

- Respect the limits: `subagents.max_concurrent` and `subagents.max_per_session` in the harness policy, and Claude Code's `CLAUDE_CODE_MAX_CONCURRENT_SUBAGENTS`. A denied spawn means wait for running agents or merge slices.
- Agents that write files in parallel need isolation: give each its own files, or run them in separate worktrees (`isolation: worktree` in the agent definition, or `using-git-worktrees`).

## 4. Write each brief

Every agent sees only its brief. Include:

1. **Goal** in one sentence, and why it matters.
2. **Scope**: exact paths, inputs or hypothesis. What is out of scope.
3. **Context it cannot discover**: decisions, constraints, the test command, interfaces it must keep.
4. **Constraints**: files it may change, "read-only", time or size limits.
5. **Report contract**: the exact shape and length of the answer.

A fixed report contract keeps fan-in cheap:

```text
Report in at most 200 words:
- Answer: <one sentence>
- Evidence: <file:line or command + result, up to 5 items>
- Confidence: high | medium | low, and why
- Not checked: <anything you skipped>
```

## 5. Fan in and verify

1. Read the reports, not the agents' raw output.
2. Check the claims that matter yourself: open the cited lines, run the tests. An agent's "done" is not evidence (`verification-before-completion`).
3. Resolve conflicts between reports explicitly, and say how.
4. For parallel writers: review each diff, run the full suite once after merging.
5. Record what the team found: `harness progress note "..."`.

## 6. Keep the bill in view

- `harness cost --since 1d` shows spend split into the main session and subagents, by model.
- If subagents dominate the bill on a premium model, route them cheaper (`harness optimize`).
- If agents re-read the same large files, give them the relevant excerpt or file:line ranges in the brief instead.
