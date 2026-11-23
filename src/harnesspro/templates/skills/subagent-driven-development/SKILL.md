---
name: subagent-driven-development
description: Use when executing a plan whose tasks are mostly independent and a subagent tool is available. Dispatch a fresh implementer subagent per task with a precise brief, review each task before moving on, and finish with a whole-branch review.
---

# Subagent-driven development

You coordinate; subagents implement. Each implementer starts with a clean context and exactly the information you give it, which keeps it focused and keeps your own context free for coordination. A review after every task catches problems before later tasks build on them.

## Setup

1. Isolated branch or worktree (`using-git-worktrees`); never `main` without consent.
2. Read the plan and spec. Load tasks: `harness progress import <plan>`.
3. Confirm the suite is green before the first task.

## Per task

1. `harness progress start <id>`, then record the base commit: `git rev-parse HEAD`.
2. **Dispatch the `implementer` subagent** with a brief built from [implementer-brief.md](implementer-brief.md). Give it the task text, the interfaces it uses and provides, the global constraints, the test command and the base commit. Never paste your conversation history.
3. **Answer its questions** if it asks; it is better to pause than to guess.
4. **Check its report against reality**: read `git diff <base>..HEAD` and run the tests yourself. A subagent saying "done" is not evidence.
5. **Dispatch the `code-reviewer` subagent** for this task's range with [task-review-brief.md](task-review-brief.md): does it meet the spec, and is the code sound?
6. **Fix loop.** For critical or important findings, send the implementer the findings and the failing scenario, then re-review. After two rounds on the same issue, record a ruling (see `executing-plans`) and move on, or ask the user if it is a blocker.
7. `harness progress done <id> "reviewed: spec ok, 0 critical; suite 87 passed"`.

Move straight on to the next task; progress stays visible in `harness progress show`. Stop only for the four reasons in `executing-plans` (destructive, security-sensitive, outside-the-branch side effects, a hopelessly broken plan).

## Final review

When all tasks are done, dispatch `code-reviewer` on the whole branch (`git merge-base main HEAD`..HEAD) with the spec, plus the `evaluator` subagent for each feature's acceptance steps. Fix critical and important findings test-first, run the full suite, then use `finishing-a-development-branch`.

## Choosing between this and executing-plans

| | Subagent-driven | Inline (`executing-plans`) |
| --- | --- | --- |
| Context | Fresh per task | One context for everything |
| Reviews | After every task and at the end | At the end |
| Cost | Higher (new context per task and review) | Lower |
| Best for | Long plans, high-stakes code | Short plans, tight budgets, no subagent tool |

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
