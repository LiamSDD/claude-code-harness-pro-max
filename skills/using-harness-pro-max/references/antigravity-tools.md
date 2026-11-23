# Antigravity tool mapping

| Action | On Antigravity |
| --- | --- |
| Dispatch a subagent | `invoke_subagent` with `self` for full-capability work or `research` for read-only search |
| Track tasks | a task artifact: `write_to_file` with `IsArtifact: true` and `ArtifactType: "task"`, updated as steps finish (not `manage_task`, which manages background processes) |
| Read, edit, run, search | Antigravity's file, terminal and search tools by their exposed names |

Run harness tools from the terminal: `python3 <plugin>/bin/harness <command>`.
