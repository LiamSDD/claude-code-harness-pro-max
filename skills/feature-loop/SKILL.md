---
name: feature-loop
description: Work through the harness feature list one verified feature at a time. Use for multi-session projects, or when the user says "continue", "next feature" or "keep going".
---

# Feature loop

A disciplined loop for long-running work. State lives in `.claude/harness/`, not in your context, so any session can pick up where the last one stopped.

## 1. Get your bearings

```bash
harness progress summary
git log --oneline -10
git status
```

If the feature list is empty, stop and use the `planner` subagent first.

## 2. Pick exactly one feature

Take the feature `harness progress summary` names as next (an `in_progress` one first). Mark it:

```bash
harness progress start <id>
```

Do not start a second feature until this one is done or explicitly blocked.

## 3. Check the baseline

Run the test suite before changing anything. If it already fails, fix that first or record it as a blocker; do not build on a broken base.

## 4. Implement

Small steps, with a test for each behaviour. Commit at sensible checkpoints with clear messages.

## 5. Verify independently

Delegate to the `evaluator` subagent with the feature id. Do not mark the feature done on your own judgement. If the verdict is FAIL, fix and re-evaluate.

## 6. Record and hand off

```bash
harness progress done <id> "verified: <one line of evidence>"
harness progress note --heading "Feature <id> done" "What changed, decisions made, anything the next session should know"
git add -A && git commit -m "<feature title>"
```

If you are blocked: `harness progress block <id> "<why and what is needed>"` and tell the user.

Then return to step 1, or stop if the user asked for a single feature.
