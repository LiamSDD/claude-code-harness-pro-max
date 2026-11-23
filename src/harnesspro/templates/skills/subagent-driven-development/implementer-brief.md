# Implementer brief template

Fill in every placeholder. The implementer sees only this brief and the repository.

```text
You are implementing one task of a larger plan in the repository at <PATH>, on branch <BRANCH>.
Base commit for this task: <BASE_SHA>.

## Task
<paste the full task text from the plan, including its steps and expected outputs>

## Interfaces
Uses (already exists): <exact signatures from earlier tasks>
Provides (later tasks depend on these exact names and types): <signatures>

## Constraints
<global constraints from the plan, copied verbatim>

## How to work
- Follow test-driven development: write the failing test, run it and see it fail for the
  expected reason, write the minimum code, run it and see it pass.
- Run the full suite with `<TEST_COMMAND>` before you report. Report every failure you see,
  including ones you did not cause.
- Stay inside this task. Do not refactor unrelated code or add features the task does not ask for.
- Commit with the message the plan gives.
- If something in the task is ambiguous or contradicts the code, ask before guessing.
- If the harness denies a command, do not work around it; mention it in your report.

## Report
1. What you changed (files and a one-line summary each).
2. The test you wrote first, and the failure you saw before implementing.
3. The full-suite result (command and counts).
4. Anything you decided that the task did not specify, and anything you could not do.
```
