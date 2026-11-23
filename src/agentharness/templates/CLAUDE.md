# Project memory

This file is loaded into every Claude Code session. Keep it short and true:
commands that work, conventions that matter, and traps to avoid.

## Commands

- Test: `{{TEST_COMMAND}}`
- Lint / format: <add>
- Run locally: <add>

## Conventions

- <language, framework and style rules that are not obvious from the code>
- Small, focused commits with messages in the imperative ("Add retry to webhook sender").

## Working agreement

- Read the relevant code before changing it. Prefer editing existing files to adding new ones.
- Every behaviour change comes with a test. Run the tests before saying you are done.
- Never hard-code credentials. Read them from environment variables.
- If the harness denies a tool call, do not look for a workaround. Explain what you need and why.

## Long-running work

The harness keeps state between sessions in `.claude/harness/`:

- `harness progress show` lists features and which ones pass.
- Work on one feature at a time: `harness progress start <id>`, then `harness progress done <id>` only after it is verified end to end.
- Before you stop or the context is compacted, record what you did and what is next: `harness progress note "..."`.

## Do not touch

- <generated files, vendored code, migrations that already ran>
