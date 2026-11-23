---
name: managing-limits
description: Use when the user asks to limit or stop limiting reply length, prompt length, effort, model, turns, spend, subagents, web searches or output size - for example "keep answers under 100 words", "at least 300 words", "block prompts over 2000 characters", "use low effort", "cap this at $5", "reset the limits". Sets, shows and resets limits with harness limits.
---

# Managing limits

`harness limits` sets limits that hold across the session; `reset` returns any of them to unlimited.

## Map the request to a command

| The user says | Run |
| --- | --- |
| "Keep replies under 150 words" | `harness limits output --max-words 150` |
| "Write at least 300 words" | `harness limits output --min-words 300` |
| "Between 50 and 200 words" | `harness limits output --min-words 50 --max-words 200` |
| "Never more than 4000 tokens per answer" | `harness limits output --max-tokens 4000` |
| "Reject my prompts over 2000 characters" | `harness limits input --max-chars 2000` |
| "Prompts must be at least 3 words" | `harness limits input --min-words 3` |
| "Use low effort" | `harness limits set effort low` |
| "Default to Sonnet" | `harness limits set model sonnet` |
| "Stop after 30 turns" | `harness limits set turns.max 30` |
| "Cap this session at $5" | `harness limits set budget 5` |
| "At most 3 agents at once" | `harness limits set subagents.max-concurrent 3` |
| "No more than 10 web searches" | `harness limits set web.max-searches 10` |
| "Turn thinking off" | `harness limits set thinking off` |
| "Remove the reply limits" | `harness limits reset output` |
| "Remove all limits" | `harness limits reset all` |
| "What limits are set?" | `harness limits show --set-only` |

Add `--shared` to apply a limit for everyone on the project (committed files), or `--user` for all of the user's projects. Without either, limits are personal to this project.

## How each limit holds

- **Reply word and character limits** are told to you on every prompt and checked when you finish: a reply outside them is sent back once to be rewritten. Stay inside them the first time.
- **`output.max-tokens`** is Claude Code's hard per-response cap.
- **Prompt limits** stop an over- or under-length message before it is sent and tell the user why and how to reset.
- **Effort, model, turns, subagents, web searches, bash output, file reads, compaction, thinking** are Claude Code settings: they apply from the next session (or after `/clear`). Say so when you set one.
- **Budget** is checked before every tool call.

After setting or resetting, run `harness limits show --set-only` and tell the user what is now in effect.
