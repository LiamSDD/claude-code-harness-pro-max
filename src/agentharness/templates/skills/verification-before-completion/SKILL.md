---
name: verification-before-completion
description: Use before saying work is done, fixed, passing or ready, and before committing, opening a PR or marking a feature done. Run the command that proves the claim in this session, read its output, then report what it showed.
---

# Verification before completion

A claim about the state of the code needs evidence from this session. "Should work" and "looks right" are predictions, not results.

## Before any success claim

1. **Identify** the command that would prove it (test suite, build, linter, the actual reproduction of the bug).
2. **Run it** in full, now. A run from before your last edit does not count.
3. **Read** the output: exit code, number of failures, warnings.
4. **Report** what it showed. If it failed, say so with the numbers. If it passed, say so with the numbers.

The harness enforces part of this: if you claim tests pass or a bug is fixed after editing files without a successful test or build command since, it sends you back.

## What counts as evidence

| Claim | Evidence | Not evidence |
| --- | --- | --- |
| Tests pass | The suite's output with 0 failures | An earlier run, one test file |
| Build works | The build command exiting 0 | The linter passing |
| Bug fixed | The original reproduction now passes | The code changed |
| Regression test works | It fails with the fix reverted and passes with it | It passes once |
| A subagent finished | The diff and a test run you checked yourself | The subagent's report |
| Requirements met | Each requirement checked off against the spec | Tests passing |

## Words to watch

"Should", "probably", "seems to", "I'm confident", or satisfaction ("Done!", "Perfect!") before you have run anything. Replace them with the command and its result.

## If you cannot verify

Say so plainly: what you could not run and why, and what the user should run to confirm. That is a complete, honest report.

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
