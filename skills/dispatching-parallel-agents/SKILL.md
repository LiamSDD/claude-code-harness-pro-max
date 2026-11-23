---
name: dispatching-parallel-agents
description: Use when facing two or more independent problems (separate failing test files, unrelated bugs, different subsystems) that need no shared state. Dispatch one focused subagent per problem in the same message so they run concurrently, then verify and integrate.
---

# Dispatching parallel agents

Independent problems investigated one after another waste time. When they share no state, give each to its own subagent and run them at once.

## Is it parallel work?

- **Yes**: different failing test files with different causes; unrelated bugs; separate modules with no shared files.
- **No**: failures that might share a cause (fixing one may fix the others); work that needs the whole system's state; agents that would edit the same files.

When unsure, investigate one first. If it turns out to be a shared cause, the rest may disappear.

## Writing each brief

Each subagent gets only its brief, so make it complete:

- **Scope**: one test file, one module or one bug
- **Goal**: "make `tests/test_export.py` pass" or "find why invoices over 10,000 rows time out"
- **Context**: the error output, relevant file paths, the test command
- **Constraints**: which files it may change; "do not modify shared fixtures"
- **Report**: root cause, what it changed, test results

## Dispatch

Send all briefs in a single message; separate messages run one after another. Use the `test-runner` subagent for diagnosis-only work and a general-purpose subagent when changes are allowed.

## Integrate

1. Read every report.
2. Check the diffs do not conflict and stayed in scope.
3. Run the full suite yourself (`verification-before-completion`).
4. Record what was fixed: `harness progress note "..."`.

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
