---
name: executing-plans
description: Use when implementing a written plan yourself in this session, task by task, for example when the user chose inline execution or no subagent tool is available. Executes each task with TDD, records decisions in the progress log, and ends with one independent review.
---

# Executing plans

The plan already did the thinking. Execute it exactly, prove each step with a test you watched fail and then pass, and leave a record that survives compaction and new sessions.

## Setup

1. Work on a branch or in a worktree, never directly on `main` without the user's consent (`using-git-worktrees`).
2. Read the plan and the spec it points to in full.
3. Make sure the tasks are in the feature list: `harness progress import <plan>` (safe to repeat).
4. Run the test suite once to confirm a green baseline. If it is red, stop and report.

## Per task

```bash
harness progress start <id>
```

1. Work through the steps in order. Run every command the plan lists and compare the output with what the plan expects.
2. **Output differs from the plan?** If the code is wrong, use `systematic-debugging`. If the plan is wrong, decide, and record the decision (see Rulings).
3. Commit as the plan says.
4. Run the full suite. Then:

   ```bash
   harness progress done <id> "suite: 142 passed"
   ```

Move straight on to the next task: the user asked for the whole plan, so a "shall I continue?" after each task only costs them time. Progress stays visible in `harness progress show`.

## Rulings

Ambiguities, conflicts and plan defects are yours to decide. The spec is the authority, the plan is its argument, your judgement settles what neither covers. Record each one so it is not a decision made in secret:

```bash
harness progress note --heading "Ruling" "Used UTC for stored timestamps (plan silent; spec says reports are per-region). Cost if wrong: one migration."
```

Stop and ask only for: an irreversible or destructive action, a security-sensitive one, a side effect outside the branch (merge, push to a shared branch, publish, deploy), or a plan so broken that every way forward is a guess.

## Finish

1. Run the full suite and the build, and read the output (`verification-before-completion`).
2. Ask for one review of the whole branch (`requesting-code-review`) with the `code-reviewer` subagent. Fix critical and important findings, each with a failing test first.
3. Use `finishing-a-development-branch`.

## After compaction or a new session

The session start-up context shows the next feature and recent progress notes. Trust the files over your memory: `harness progress show`, `git log --oneline -20`. Never redo a task the feature list marks as done.

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
