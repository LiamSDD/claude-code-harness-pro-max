# Codex tool mapping

| Action | On Codex |
| --- | --- |
| Run a command, read or search files | the shell tool (`rg` for search, `sed -n` or `head` for ranges) |
| Edit or create files | `apply_patch` |
| Track tasks | `update_plan` |
| Dispatch a subagent | `spawn_agent` (enable `[features] multi_agent = true` in `~/.codex/config.toml`); start children with a clean context (`fork_turns: "none"`) and give them the full brief |
| Wait for subagents | `wait_agent`; follow up with `followup_task` instead of spawning a new one |
| Invoke a skill | skills are listed by description; read the skill file when it applies |

Instructions file: `AGENTS.md`. Personal skills: `~/.codex/skills/` or `~/.agents/skills/`.

Harness tools work the same: run `python3 <plugin>/bin/harness <command>`. Claude Code hook guards do not run on Codex; use `harness check bash "<command>"` before risky commands and `harness scan --staged` before commits.
