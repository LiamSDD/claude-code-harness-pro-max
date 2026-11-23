# Cursor tool mapping

| Action | On Cursor |
| --- | --- |
| Read, edit, create files | Cursor's file tools |
| Run a command | the terminal tool |
| Search | codebase or grep search |
| Dispatch a subagent | Cursor's subagent / background agent tool when available; otherwise work sequentially |
| Track tasks | the todo tool |

Instructions file: `AGENTS.md` or `.cursor/rules`. The plugin's `hooks/hooks-cursor.json` runs the harness on `sessionStart`, `beforeSubmitPrompt` (secrets and input limits), `beforeShellExecution` (policy and token guards), `beforeReadFile` (secret files, generated files, re-reads), `beforeMCPExecution`, `afterFileEdit` and `stop`.
