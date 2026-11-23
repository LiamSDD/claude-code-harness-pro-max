# OpenCode tool mapping

| Action | On OpenCode |
| --- | --- |
| Read, edit, write files | `read`, `edit`, `write` |
| Run a command | `bash` |
| Search contents / find files | `grep` / `glob` |
| Dispatch a subagent | `task` with the agent name |
| Track tasks | `todowrite` |
| Invoke a skill | the skill tool, or read the skill file when its description applies |

Instructions file: `AGENTS.md`. Skills directory: `~/.config/opencode/skills/` or `.agents/skills/`.
