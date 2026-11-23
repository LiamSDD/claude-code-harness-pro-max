---
name: optimizing-token-usage
description: Use when working in a large codebase, on a long session, under a budget, or when the user asks to reduce cost or tokens. Practical rules that cut context size and request count without lowering quality - targeted search before reading, bounded outputs, no re-reads, delegation of wide reading, compaction between tasks - and how to measure the result.
---

# Optimizing token usage

In Claude Code, most of the bill is context: every request re-reads the whole conversation (from cache, but still billed per token). Anything that enters the context, a file, a log, a long answer, is paid for again on every later turn. Keep the context small and the work stays cheap.

## Reading code

- **Search first.** Glob for file names and Grep for symbols, then Read only the files that matter.
- **Read ranges.** For large files, Grep for the line, then Read with `offset` and `limit` around it.
- **Read once.** A file you read is still in context until compaction. The harness refuses an unchanged re-read; use what you have.
- **Skip generated files.** Lockfiles, minified bundles, source maps, `node_modules`, coverage output. Read the source or the manifest instead.

## Running commands

- Bound the output: `git log --oneline -20`, `tail -n 200`, `docker logs --tail 200`, `head -n 50`, `pytest -q`, `npm test --silent`.
- Filter before printing: `grep`, `jq`, `--format`, `wc -l` when you only need a count.
- Never run commands that do not exit (`tail -f`, `watch`) in the foreground.
- Prefer one command that answers the question over several exploratory ones.

## Delegating

- Wide reading (a whole module, many logs, several sources) goes to an `explorer` subagent with a short report contract. Its reading never enters your context.
- Give subagents excerpts and file:line ranges you already have, so they do not re-read.
- See `orchestrating-agent-teams` for sizing and model choice.

## Writing

- Prefer Edit over rewriting a whole file with Write.
- Keep status updates and final reports short and specific; long prose is paid for on every following turn.
- Do not repeat file contents or command output back to the user; cite file:line.

## Between tasks

- When a task is done and the next one is unrelated, suggest `/clear` (after a `harness progress note` if the work spans sessions).
- When the context is large but the task continues, `/compact` with a focus ("keep the failing test output and the plan") beats carrying everything.

## Measure

```bash
harness cost --since 7d        # spend by model, main vs subagents, tool output, recommendations
harness optimize               # preview token-saving settings; --apply to write them
```

Compare `harness cost` before and after a change instead of guessing.
