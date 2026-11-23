# Claude Code tool mapping

Skills name actions; on Claude Code they map to these tools.

| Action | Tool |
| --- | --- |
| Read a file | `Read` (use `offset` and `limit` for parts) |
| Create a file | `Write` |
| Edit a file | `Edit`, `MultiEdit` |
| Run a command | `Bash` |
| Search file contents | `Grep` |
| Find files by name | `Glob` |
| Fetch a URL / search the web | `WebFetch` / `WebSearch` |
| Invoke a skill | `Skill` |
| Dispatch a subagent | `Agent` with `subagent_type` (`explorer`, `implementer`, `code-reviewer`, ... or `general-purpose`); several `Agent` calls in one message run in parallel |
| Track tasks | the task list tool |
| Ask the user a question | `AskUserQuestion` |
| Isolated workspace | `EnterWorktree`, or `isolation: worktree` in an agent definition |

Instructions file: `CLAUDE.md`. Personal skills: `~/.claude/skills/`. All harness hooks run here.
