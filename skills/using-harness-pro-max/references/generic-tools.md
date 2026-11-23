# Any other agent

Skills describe actions (read a file, run a command, dispatch a subagent, track tasks). Use whatever tool your agent exposes for each. If it has no subagent tool, do the work sequentially and say so; never invent a tool call.

The harness tools run anywhere Python 3.9 runs: `python3 <this-repo>/bin/harness <command>`.
