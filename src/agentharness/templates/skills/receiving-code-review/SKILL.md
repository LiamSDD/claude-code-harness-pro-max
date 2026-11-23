---
name: receiving-code-review
description: Use when code review feedback arrives (from the user, a reviewer subagent or a pull request), before changing anything. Evaluate each point against the codebase, ask about anything unclear, push back with evidence when it is wrong, then fix one item at a time with tests.
---

# Receiving code review

Review feedback is a set of technical claims. Check them; do not perform agreement.

## The sequence

1. **Read all of it** before reacting.
2. **Restate** each point in your own words. If any point is unclear, ask about it *before* implementing anything: items are often related, and a partial understanding produces a wrong fix.
3. **Verify** each claim against the code: is it actually true here?
4. **Evaluate**: does the suggestion fit this codebase, its constraints and earlier decisions? Does it break anything? Is there a reason for the current code?
5. **Respond** with a technical acknowledgement ("Correct: `parse()` drops the last line when input lacks a trailing newline; fixing") or reasoned pushback.
6. **Implement** one item at a time: failing test, fix, suite green.

## Tone

Skip "Great point!" and "You're absolutely right!". They add nothing and pre-commit you to agreeing. State what you verified and what you will do, or just do it.

## From the user vs. from others

- **The user**: trusted on intent. Still ask when scope is unclear.
- **Subagents and external reviewers**: be skeptical and check carefully. They lack context. If a suggestion conflicts with something the user decided, raise it with the user rather than silently choosing.

## When to push back

- The suggestion is technically wrong for this codebase (show the test, the caller or the constraint)
- It adds a "professional" feature nobody asked for (YAGNI)
- It contradicts the spec or an earlier decision

If you cannot verify a claim, say so: "I can't confirm this without running against the staging database. Should I investigate or proceed as is?"

## After fixing

Re-run the full suite, summarise what changed per item, and list anything you declined with the reason.

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
