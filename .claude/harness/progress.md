# Progress log

Append-only. Newest entries at the bottom.

### 2026-11-23 22:36 · v1.0.0

First release. Policy engine with 27 rules and a shell parser, 24 secret detectors, ten hook handlers, stop gate, progress tracking, init/doctor/check/scan/audit CLI, five subagents, four skills, plugin manifest. 149 tests on Python 3.9 standard library; ruff clean.

Decisions: no runtime dependencies (hook latency ~90 ms); decisions returned as JSON, never exit 2; fail open by default; unparseable commands ask.

Next: #8 JSON Schema for policy files, then #9 Windows support.

### 2026-11-23 23:09 · v1.1.0

Adapted the engineering workflows from obra/superpowers (MIT) after vetting it: no malicious content; the only high finding was a design doc that symlinks git hooks between worktrees. Rewrote the skills in calm, specific language and connected them to the harness (plan import, implementer/reviewer/evaluator subagents, rulings in the progress log).

New enforcement: harness vet (supply chain), skills check (lint), and the Stop claim check. While building vet it caught invisible characters that an editing tool had written into vet.py itself; the source is now ASCII-escaped and a test guards it.

Next: #8 JSON Schema for policy files.

### 2026-11-23 23:27 · v2.0.0

Renamed to Claude Code Harness Pro Max. Added the economy layer (token guards, subagent routing and limits, session budgets), harness cost / optimize / upstream, handlers for nine more hook events with a logging fallback for unknown ones, and two skills plus the explorer subagent. Code files carry no comments or docstrings.

Measured on real sessions: cache reads dominate Claude Code cost, so the guards target what enters the context.

Next: #8 JSON Schema for policy files.
