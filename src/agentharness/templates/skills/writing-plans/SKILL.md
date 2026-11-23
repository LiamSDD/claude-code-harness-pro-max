---
name: writing-plans
description: Use when you have an approved design, spec or clear requirements for multi-step work, before touching code. Writes an implementation plan an engineer new to the codebase could follow task by task, and loads it into the harness feature list.
---

# Writing plans

Write the plan for a capable engineer who has never seen this codebase or the spec. They will write idiomatic code once they know the exact files, names, signatures, values and tests. What they cannot know is what you decided, so write that down.

Save plans to `docs/plans/YYYY-MM-DD-<feature>.md` unless the project has its own convention.

## Before the tasks

1. **Scope.** If the spec covers independent subsystems, write one plan per subsystem, each producing working software on its own.
2. **File map.** List the files to create or change and what each is responsible for. Prefer small, focused files; follow the codebase's existing patterns.
3. **Global constraints.** Versions, dependency limits, naming rules and platform requirements, copied exactly from the spec.
4. **Review focus.** The few inputs or conditions most likely to break the software that no task's tests would otherwise exercise (empty input, concurrency, permissions, unicode, time zones), each with the behaviour a user would expect. Then add a test for each one to the task that owns that code.

## Plan header

```markdown
# <Feature> implementation plan

**Goal:** one sentence.
**Approach:** two or three sentences.
**Stack:** key technologies.
**Spec:** path to the design or spec.

## Global constraints
- ...

## Review focus
- ...
```

## Tasks

A task is the smallest unit with its own test cycle that a reviewer could accept or reject on its own. Fold setup, configuration and docs into the task that needs them.

````markdown
### Task 3: Rate-limit login attempts

**Files:** create `src/auth/ratelimit.py`; modify `src/auth/login.py:40-62`; test `tests/auth/test_ratelimit.py`
**Uses:** `get_user(email) -> User | None` from Task 1
**Provides:** `check_rate_limit(ip: str, now: float) -> bool`

- [ ] **Step 1: Write the failing test** for 5 attempts allowed and the 6th refused within 60 s
- [ ] **Step 2: Run it** and confirm it fails because `check_rate_limit` does not exist
- [ ] **Step 3: Implement** a sliding window keyed by IP
- [ ] **Step 4: Run the suite**: `python -m pytest -q`, expect 0 failures
- [ ] **Step 5: Commit**: `git commit -m "Rate-limit login attempts per IP"`
````

Each step is one action with a checkable result. Include the exact commands and the expected output. Include real code where the decision matters (signatures, data shapes, tricky logic); leave routine code to the implementer.

## After writing

1. Re-read the plan against the spec: every requirement maps to a task, and no task invents scope.
2. Load it into the harness so progress survives sessions:

   ```bash
   harness progress import docs/plans/YYYY-MM-DD-<feature>.md
   harness progress show
   ```

3. Offer the user a choice of execution: `subagent-driven-development` (a fresh subagent and a review per task, higher quality, more tokens) or `executing-plans` (you implement inline, one review at the end, cheaper).

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
