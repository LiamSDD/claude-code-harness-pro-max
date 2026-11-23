---
name: systematic-debugging
description: Use when you hit any bug, test failure, build failure or unexpected behaviour, before proposing a fix. Find the root cause first through evidence, then fix it once with a test.
---

# Systematic debugging

Guessing at fixes is slower than investigating: each wrong fix adds a change you then have to understand. Find the cause, then fix it once.

## Phase 1: investigate

1. **Read the error completely**: the message, the whole stack trace, file paths and line numbers. It often names the answer.
2. **Reproduce it reliably.** Write down the exact steps. If you cannot reproduce it, gather more data; do not guess.
3. **Check what changed**: `git diff`, `git log -10`, new dependencies, configuration, environment.
4. **In multi-component systems** (CI → build → deploy, API → service → database), add temporary logging at each boundary showing what goes in and what comes out, run once, and find the layer where good data turns bad.
5. **Trace the bad value backwards** to where it originates. See [root-cause-tracing.md](root-cause-tracing.md).

## Phase 2: compare

Find similar code in the project that works. List every difference between the working and the broken case, however small. Read any reference implementation in full before copying its pattern.

## Phase 3: hypothesise and test

State one hypothesis: "X is the cause because Y." Test it with the smallest possible change, one variable at a time. If it is wrong, form a new hypothesis; do not stack fixes. If you do not understand something, say so and investigate or ask.

## Phase 4: fix

1. Write a failing test that reproduces the bug (`test-driven-development`).
2. Make one change that addresses the root cause. No unrelated improvements in the same change.
3. Run the test and the full suite (`verification-before-completion`).
4. Consider adding validation at other layers so the bad value cannot get through again: [defense-in-depth.md](defense-in-depth.md).

## When fixes keep failing

After three failed fixes, stop. Each fix revealing a new problem somewhere else means the design is wrong, not the details. Explain to the user what you found and discuss the architecture before trying a fourth.

## Signs you skipped a step

- "Let me just try changing X"
- Several changes before re-running the tests
- A fix you cannot explain
- The user asking "is that actually happening?" or "stop guessing"

Go back to phase 1.

## Flaky and timing-dependent failures

Replace fixed sleeps with waiting for the actual condition: [condition-based-waiting.md](condition-based-waiting.md). If an investigation really shows the cause is external (a third-party outage), document what you checked, handle it explicitly (retry, timeout, clear error) and add logging.

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
