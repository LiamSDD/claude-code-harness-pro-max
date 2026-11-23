# Gemini CLI tool mapping

| Action | On Gemini CLI |
| --- | --- |
| Read a file / several files | `read_file` / `read_many_files` |
| Create a file | `write_file` |
| Edit a file | `replace` |
| Run a command | `run_shell_command` |
| Search contents / find files | `grep_search` / `glob` |
| List a directory | `list_directory` |
| Fetch a URL / search the web | `web_fetch` / `google_web_search` |
| Invoke a skill | `activate_skill` |
| Dispatch a subagent | `invoke_agent` with `agent_name: "generalist"` (or `codebase_investigator` for read-only search); several calls in one response run in parallel |
| Track tasks | `write_todos` |

Instructions file: `GEMINI.md`. Personal skills: `~/.gemini/skills/` or `~/.agents/skills/`. Run harness tools with `run_shell_command`: `python3 <extension>/bin/harness <command>`.
