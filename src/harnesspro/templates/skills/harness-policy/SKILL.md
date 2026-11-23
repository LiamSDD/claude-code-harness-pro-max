---
name: harness-policy
description: Explain why the harness blocked an action and propose a safe policy change. Use when a tool call was denied or asked for confirmation unexpectedly, or when the user wants to tune the guardrails.
---

# Tuning the harness policy

1. Find the decision: `harness audit --blocked --tail 20`. Each record names the rule id (for example `secret-file-read`, `git-force-push`).
2. Reproduce it without side effects: `harness check bash "<command>"`, `harness check read <path>` or `harness check url <url>`. Exit codes: 0 allow, 3 ask, 2 deny.
3. Decide with the user whether the block is correct. Most blocks are; explain the risk in one or two sentences.
4. If a change is warranted, propose the narrowest one, as a diff to `.claude/harness/policy.json` (shared) or `policy.local.json` (only this machine):
   - re-allow one path: add `"!path/to/file"` to the relevant `paths` list,
   - add a project rule: append to `bash.rules` with an `id`, `pattern`, `decision` (`ask` or `deny`) and `reason`,
   - switch a rule off entirely, as a last resort: add its id to `disable`.
5. Validate: `harness policy validate`, then re-run the `harness check` from step 2.

Never edit the policy to get past a block without the user's explicit agreement. The policy file is protected: editing it asks for confirmation.
