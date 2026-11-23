# Installing on each platform

The content is the same everywhere: the skills in `skills/`, the subagent briefs in `agents/`, and the `bin/harness` command (Python 3.9+, no dependencies). What differs is how each agent loads them.

## Claude Code

```text
/plugin marketplace add priveight02/claude-code-harness-pro-max
/plugin install harness-pro-max@harness-pro-max
```

Everything is active: guardrail, token and limit hooks, 21 skills, 7 subagents, `harness` on the Bash path. Without the plugin: `pipx install git+https://github.com/priveight02/claude-code-harness-pro-max`, then `harness init` in each project.

## Cursor

Install the repository as a Cursor plugin (it ships `.cursor-plugin/plugin.json`), or clone it and point Cursor's plugin install at the folder. `hooks/hooks-cursor.json` runs `bin/harness hook <event> --platform cursor` for:

| Cursor event | Harness behaviour |
| --- | --- |
| `sessionStart` | injects the skill map, tool mapping and project context |
| `beforeSubmitPrompt` | secret scan and prompt length limits |
| `beforeShellExecution` | full policy and token guards (`allow`, `ask`, `deny`) |
| `beforeReadFile` | secret files, generated files, duplicate reads |
| `beforeMCPExecution` | destructive MCP tool rules |
| `afterFileEdit`, `stop`, `sessionEnd`, `subagentStart`, `subagentStop` | audit and session state |

## Codex

The repository ships `.codex-plugin/plugin.json` and `.agents/plugins/marketplace.json`. Add it as a plugin source in Codex, or clone it into `~/.codex/skills/harness-pro-max` (or `~/.agents/skills/harness-pro-max`). For subagent workflows enable multi-agent support in `~/.codex/config.toml`:

```toml
[features]
multi_agent = true
```

Tool names: `skills/using-harness-pro-max/references/codex-tools.md`. Run harness commands through the shell: `python3 <path>/bin/harness check bash "<command>"`.

## Gemini CLI

```bash
gemini extensions install https://github.com/priveight02/claude-code-harness-pro-max
```

`gemini-extension.json` declares `GEMINI.md`, which loads the skill map and the Gemini tool mapping at session start.

## Antigravity

Install from the repository (it ships `.antigravity-plugin/plugin.json`). Skills load from `skills/`; tool names in `references/antigravity-tools.md`.

## Kimi Code

The repository ships `.kimi-plugin/plugin.json`, which loads `using-harness-pro-max` at session start and maps skill actions to Kimi's tools.

## OpenCode, Copilot CLI and other agents

Clone into the agent's skills folder:

```bash
git clone https://github.com/priveight02/claude-code-harness-pro-max ~/.agents/skills/harness-pro-max
```

`~/.agents/skills/` is read by several agents (Codex, Gemini CLI, Copilot CLI); OpenCode also reads `~/.config/opencode/skills/`. Tool names: `references/opencode-tools.md` and `references/generic-tools.md`.

## What works where

| Capability | Claude Code | Cursor | Codex, Gemini, Antigravity, Kimi, others |
| --- | --- | --- | --- |
| Skills and subagent briefs | yes | yes | yes |
| Session-start bootstrap | yes | yes | Gemini, Kimi: yes; others: skill discovery |
| Shell and file guardrails | hooks | hooks | `harness check` on request |
| Token guards | hooks | shell and read hooks | `harness check` on request |
| Prompt limits | hook | hook | n/a |
| Reply limits | hook | instruction | instruction via skill |
| Cost analytics, budgets | yes | n/a (different transcript format) | n/a |
| `harness vet`, `scan`, `progress`, `limits` | yes | yes | yes |
