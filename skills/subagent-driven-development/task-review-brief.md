# Task review brief template

For the `code-reviewer` subagent after each task.

```text
Review one task of a plan in <PATH>. Changes are in the range <BASE_SHA>..<HEAD_SHA>
(`git diff <BASE_SHA>..<HEAD_SHA>`).

## What the task had to do
<paste the task text from the plan>

## Global constraints
<constraints from the plan>

## Answer two questions separately
1. Spec compliance: does the change do everything the task requires, and nothing it does not?
   List each requirement as met / not met / partially met, with evidence (file:line or test name).
2. Code quality: correctness bugs, missing tests for behaviour the task added, security issues,
   and anything that will make later tasks harder. Give a concrete failure scenario for each.

Run the tests for the touched area and the full suite with `<TEST_COMMAND>`, and include the result.

Classify findings as Critical (wrong or unsafe), Important (should fix before moving on)
or Minor (note for later). If there is nothing critical or important, say so plainly.
```
