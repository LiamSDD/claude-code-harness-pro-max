# Progress log

Append-only. Newest entries at the bottom.

### 2026-11-23 22:36 · v1.0.0

First release. Policy engine with 27 rules and a shell parser, 24 secret detectors, ten hook handlers, stop gate, progress tracking, init/doctor/check/scan/audit CLI, five subagents, four skills, plugin manifest. 149 tests on Python 3.9 standard library; ruff clean.

Decisions: no runtime dependencies (hook latency ~90 ms); decisions returned as JSON, never exit 2; fail open by default; unparseable commands ask.

Next: #8 JSON Schema for policy files, then #9 Windows support.
