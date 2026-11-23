---
name: requesting-code-review
description: Use after finishing a task or feature, after fixing a complex bug, or before merging, to get an independent review from the code-reviewer subagent with exactly the context it needs.
---

# Requesting code review

A reviewer that did not write the code sees what you stopped seeing. Give it the work product and the requirements, never your conversation history: it should judge the code, not your reasoning.

## When

- After each task in `subagent-driven-development`, and at the end of `executing-plans`
- After a major feature or a tricky bug fix
- Before merging into the main branch
- When you are stuck: a fresh look is cheap

## How

1. Pick the range:

   ```bash
   BASE=$(git merge-base main HEAD)   # whole branch, or the commit before the task
   HEAD_SHA=$(git rev-parse HEAD)
   ```

2. Dispatch the `code-reviewer` subagent with:
   - one paragraph on what you built and why,
   - the requirements (plan task, spec section or issue),
   - the range `BASE..HEAD_SHA`,
   - the test command.

3. Act on the result:
   - **Critical**: fix now, test first.
   - **Important**: fix before moving on.
   - **Minor**: note it (`harness progress note`) and continue.
   - **Wrong**: push back with evidence (see `receiving-code-review`).

4. Re-run the suite after fixes, then re-request review if anything critical changed.

Reviewing your own diff inline is not a substitute: it costs your context and you will read what you meant rather than what you wrote.

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
