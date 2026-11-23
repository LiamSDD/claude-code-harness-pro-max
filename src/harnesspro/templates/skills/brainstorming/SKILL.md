---
name: brainstorming
description: Use before building something new (a feature, component, behaviour change or project) when the request leaves choices open that would change what gets built. Understand what the user wants and why, agree on an approach and a short design, then plan.
---

# Brainstorming

You build what you believe the user wants, and that belief is often thinner than it feels. A few minutes on what they actually want saves hours of rework.

## First: what do you actually know?

- **Everything that matters is in the request** ("make the button blue"): just do it and say what you did.
- **Something that would change the result is missing**: start the conversation below.

## Look before you ask

Read what the user pointed at and the code it touches until you can explain how it works today and what the change would affect. Never ask what the project already answers, and never reopen a decision they already made.

## The first message

- **If they described what they want**: restate it in your own words (what, for whom, why), add what you found in the code that bears on it (constraints, conflicts, a cheaper path), and ask the one question whose answer would change the build most. If nothing is open, propose a short design and ask for approval.
- **If they did not**: ask one open question about the biggest unknown, and say why the answer matters: "If it's mostly for people deciding whether to visit, I'd lead with opening hours; taking orders is a different site. What should a visitor be able to do?"
- If they did not ask for a discussion, offer to just get going instead.

## The conversation

- One question at a time, only when the answer changes what gets built. Otherwise state your choice and reason as a proposal they can correct.
- Use their vocabulary, not process jargon.
- When there are real options, describe two or three concretely, with trade-offs and your recommendation.

## The design

When the approach is agreed, write a short design (a few lines for small work, a page for large): goal, approach, what is out of scope, risks, how it will be tested. Save larger ones in `docs/designs/YYYY-MM-DD-<topic>.md`. Get the user's approval, then use `writing-plans`.

For large requests with independent parts, split them into separate designs and plans, each delivering something usable on its own.

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
