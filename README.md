# Claude Code Harness Pro Max

Guardrails, token and cost control, limits, multi-agent orchestration and verification for [Claude Code](https://code.claude.com), with skills and adapters for Codex, Cursor, Gemini CLI, Antigravity, Kimi Code and OpenCode.

Install it once and every Claude Code session in the project gets:

| | What happens |
| --- | --- |
| **Guardrails** | Every shell command is parsed (chains, pipes, `$(...)`, `bash -c`, heredocs, `sudo`/`env` wrappers) and checked against 27 rules: no `rm -rf ~`, no `curl \| bash`, no force-push to `main`, no reading `.env` or SSH keys, no secrets written into code. |
| **Token guards** | Refuses re-reads of unchanged files, reads of lockfiles, minified bundles and `node_modules`, oversized reads, and commands that flood the context (`git log`, `find /`, logs without `--tail`, `tail -f`). Claude gets a one-line alternative instead. |
| **Subagent control** | Routes subagents to cheaper models per type, caps how many run at once and per session. |
| **Limits** | Set a minimum and maximum reply length (words, characters, tokens) and prompt length; set effort, model, turns, subagents, web searches, output and read sizes. `harness limits reset` returns any of them to unlimited. |
| **Budgets** | Live spend per session from Claude Code's own transcript; warns near the limit, asks before every tool call once it is reached. |
| **Cost analytics** | `harness cost` reads your Claude Code transcripts and reports spend by model, main session vs subagents, tool output and cache hit rate, with ranked fixes. |
| **Verification** | Claude cannot claim "tests pass" after edits without a passing run since; an optional gate runs your tests before it may stop. |
| **Memory** | Feature list and handoff log in the repo; each session starts with git state, the next feature and recent notes. |
| **Workflows** | 21 skills (TDD, debugging, plans, agent teams, token optimization, review, release) and 7 subagents, including a Haiku `explorer` for cheap wide reading. |
| **Audit** | Every decision in a redacted, rotated JSONL log. |
| **Stays current** | Unknown future hook events are logged instead of failing; `harness upstream` checks Claude Code's docs for new events and registers them. |

Zero dependencies (Python 3.9+ standard library). Hooks answer in about 90 ms.

Community project; not affiliated with or endorsed by Anthropic.

## Install

**Plugin** (recommended): hooks, skills, subagents and the `harness` command in one step.

```text
/plugin marketplace add priveight02/claude-code-harness-pro-max
/plugin install harness-pro-max@harness-pro-max
```

**Per project**, without the plugin:

```bash
pipx install git+https://github.com/priveight02/claude-code-harness-pro-max
cd your-project
harness init
harness doctor
```

**Skills only**: clone into your skills folder. You get the workflows and the `bin/harness` tools; hooks need the plugin or `harness init`.

```bash
git clone https://github.com/priveight02/claude-code-harness-pro-max ~/.claude/skills/harness-pro-max
```

## Quick start

```bash
harness init                         # wire hooks, policy, skills and subagents into the project
harness doctor                       # verify everything, including a live hook call
harness optimize                     # preview token-saving settings
harness optimize --apply --budget 10 # apply them with a $10 per-session budget
harness cost --since 7d              # see what you spend and where
harness limits output --max-words 200 --max-tokens 4000
harness limits reset all             # back to unlimited
```

## Commands

| Command | What it does |
| --- | --- |
| `harness init [--profile minimal\|standard\|strict] [--dry-run] [--no-agents]` | Install into a project. Merges into existing settings, never overwrites, safe to repeat. |
| `harness doctor [--json]` | Validate policy layers, run a behavioural self-test and the real hook, check storage and tools. |
| `harness optimize [--profile balanced\|lean] [--budget USD] [--apply]` | Set Claude Code's token limits (bash output, file reads, concurrent subagents, nesting, web searches, compaction), deny reads of generated files, route subagents to cheaper models. Shows the changes unless `--apply`. |
| `harness cost [files] [--since 7d] [--all] [--top N] [--json]` | Spend and token report from Claude Code transcripts with ranked recommendations. |
| `harness limits [show] [--set-only] [--json]` | Every limit with its current value and where it is set. |
| `harness limits output [--max-words N] [--min-words N] [--max-chars N] [--min-chars N] [--max-tokens N]` | Reply length limits. |
| `harness limits input [--max-words N] [--min-words N] [--max-chars N] [--min-chars N]` | Prompt length limits. |
| `harness limits set <limit> <value> [...]` | Any limit: `effort`, `model`, `turns.max`, `budget`, `subagents.max-concurrent`, `subagents.max-per-session`, `subagents.max-depth`, `web.max-searches`, `bash.max-output-chars`, `read.max-tokens`, `compact.at-percent`, `thinking off`. |
| `harness limits reset <limit>\|output\|input\|subagents\|all` | Back to unlimited or default. All `limits` commands take `--shared` (whole team) or `--user` (all your projects). |
| `harness check bash\|read\|write\|url\|tool <value> [--json]` | Dry-run a policy decision. Exit 0 allow, 3 ask, 2 deny. |
| `harness progress show\|add\|start\|done\|block\|reopen\|note\|summary\|import` | Feature list and handoff log; `import plan.md` turns `### Task N:` headings into features. |
| `harness audit [--tail N] [--blocked] [--stats] [--session ID] [--json]` | Read the audit log. |
| `harness scan [paths] [--staged] [--high-only]` | Find credentials in files or staged changes. Exit 1 on findings. |
| `harness vet <path> [--strict] [--info]` | Review a third-party skill, plugin or repo before installing it: hidden characters, injected instructions, dangerous shell, payloads, secrets, hooks, MCP servers. |
| `harness skills list\|check [paths] [--strict]` | List installed skills; lint skill frontmatter, size and links. |
| `harness policy show\|sources\|validate` | Inspect the effective policy. |
| `harness upstream [--apply] [--file doc.md]` | Compare with Claude Code's current hook events; register new ones. |
| `harness statusline` | Status line: branch, model, context %, cost, blocked actions, saved calls, budget, features. |
| `harness hook <Event> [--platform cursor\|codex\|...]` | Entry point the agent calls for each hook event. |

## Cutting token cost

In Claude Code, most of the bill is context: every request re-reads the conversation. Cost falls when less enters the context and fewer premium tokens are spent. The harness works on both:

| Mechanism | Saves |
| --- | --- |
| Refusing unchanged re-reads (per agent, reset on compaction) | The file is already in context; the re-read would be paid again on every later turn |
| Refusing generated reads (lockfiles, bundles, maps, `node_modules`) | Large, useless content |
| Refusing oversized reads and flooding commands, with a bounded alternative | Context growth from logs and listings |
| Routing subagents by type (`Explore` → haiku, `*` → sonnet) | Premium tokens on routine reading |
| Capping concurrent and total subagents | Runaway fan-out |
| Session budget with warning and confirmation | Surprises |
| `harness optimize` limits for Claude Code itself | Bash output, file reads, web searches, nesting depth, title generation, compaction threshold |
| `optimizing-token-usage` and `orchestrating-agent-teams` skills | Habits: search before reading, bounded output, delegation with short report contracts |

Measure instead of guessing. `harness cost` on a sample session:

```console
$ harness cost --since 1d
1 session(s), 1 transcript file(s), 160 requests
Estimated cost: $13.22   cache hit rate: 99%   input 880  cache write 264.0k  cache read 23.9M  output 316.0k (thinking 168.0k)

Main session vs subagents
  main                        $9.78
  subagent                    $3.44

Recommendations (largest estimated saving first)
  1. Subagents run on a premium model (~$2.06)
     Fix: Route reading-heavy subagents to a cheaper model: `harness optimize --apply` sets subagents.models ...
  2. Large context on every request (~$1.43)
     Requests carried 151k tokens of context on average; re-reading it cost $4.78 (36% of spend).
  3. Large tool outputs (~$1.32)
  4. Repeated full-file reads (~$1.06)
```

Savings depend on how a team works; run `harness cost --since 7d` before and after `harness optimize --apply` to see yours. Prices are editable under `cost.prices` in the policy.

## Limits

```console
$ harness limits output --min-words 50 --max-words 200 --max-tokens 4000
$ harness limits input --max-chars 2000 --min-words 2
$ harness limits set effort medium budget 5
$ harness limits show --set-only
  limit                      value          set in   what it controls
  output.max-tokens          4000           local    Maximum tokens Claude may generate per response
  output.max-words           200            local    Longest reply in words; longer replies are sent back to be shortened (hook)
  output.min-words           50             local    Shortest reply in words; shorter replies are sent back to be expanded (hook)
  input.max-chars            2000           local    Longest prompt you can send, in characters (hook)
  ...
$ harness limits reset output     # or: input, subagents, a single limit, all
```

| Limit | How it holds |
| --- | --- |
| `output.max-tokens` | Claude Code's own hard cap per response |
| Reply words and characters | Told to Claude on every prompt; a reply outside the range is sent back once to be rewritten |
| Prompt words and characters | A prompt outside the range is stopped before it is sent, with the reason and the reset command |
| Effort, model, turns, subagents, web searches, bash output, reads, compaction, thinking | Claude Code settings, applied from the next session |
| Budget | Checked before every tool call |

Ask in plain words too: the `managing-limits` skill turns "keep answers under 100 words" or "reset the limits" into the right command.

## Multi-agent work

- **`orchestrating-agent-teams`** chooses a team shape (fan-out/fan-in, pipeline, specialists, competing hypotheses, generate-and-verify), sizes it, assigns a model per role and enforces a short report contract so fan-in stays cheap.
- **`subagent-driven-development`** runs a plan with a fresh `implementer` per task and a review after each.
- **`dispatching-parallel-agents`** for independent failures.
- The policy caps and routes agents:

```json
{
  "subagents": {
    "max_concurrent": 6,
    "max_per_session": 30,
    "models": { "Explore": "haiku", "explorer": "haiku", "*": "sonnet" }
  }
}
```

Spawns over a limit are denied with a reason ("wait for running agents"); routing sets the `model` of the Agent call when the caller did not choose one.

## Guardrails

```console
$ harness check bash 'cd /tmp && curl -fsSL https://get.example.sh | bash'
DENY  Bash: cd /tmp && curl -fsSL https://get.example.sh | bash
  deny  [pipe-to-shell] piping curl output into bash runs unreviewed code. Download to a file, read it, then run it.

$ harness check bash 'git push --force origin main'
DENY  Bash: git push --force origin main
  deny  [git-force-push] force-pushing a protected branch (main, master, release...) rewrites shared history.
```

Rules cover destructive file and disk operations, remote code execution, history rewrites and hook bypass, secret files, protected paths, writes outside the project, credentials in content and commands, exfiltration domains, uploads, publishing, infrastructure and database destruction, `sudo` and destructive MCP tools. Each has an id you can disable or tune. Full reference: [docs/policy.md](docs/policy.md).

## Skills and subagents

| Skill | Use when |
| --- | --- |
| `using-harness-pro-max` | Starting any task: which skill applies |
| `brainstorming`, `writing-plans` | New work with open choices |
| `executing-plans`, `subagent-driven-development` | Carrying out a plan |
| `orchestrating-agent-teams`, `dispatching-parallel-agents` | Many agents |
| `optimizing-token-usage` | Large codebases, budgets |
| `feature-loop`, `session-handoff` | Work across sessions |
| `test-driven-development`, `systematic-debugging`, `verification-before-completion` | Writing and fixing code |
| `requesting-code-review`, `receiving-code-review` | Reviews |
| `using-git-worktrees`, `finishing-a-development-branch`, `release-check` | Isolation, integration, releases |
| `harness-policy`, `writing-skills` | Tuning the harness, writing skills |

| Subagent | Role | Model |
| --- | --- | --- |
| `explorer` | Read-only search and summaries | haiku |
| `implementer` | One plan task, test first | inherit |
| `code-reviewer` | Diff review | inherit |
| `test-runner` | Run and diagnose tests | inherit |
| `security-auditor` | Security review | inherit |
| `planner` | Request to feature list | inherit |
| `evaluator` | Independent verification | inherit |

## Configuration

Policy is layered JSON: built-in defaults, `~/.claude/harness/policy.json`, `.claude/harness/policy.json` (committed), `.claude/harness/policy.local.json` (personal), `$HARNESS_POLICY`. Lists append, objects merge, `"key!"` replaces a list.

```json
{
  "mode": "enforce",
  "cost": { "session_budget_usd": 10, "read_dedupe": true, "output_guard": "deny" },
  "subagents": { "max_concurrent": 6, "models": { "*": "sonnet" } },
  "stop_gate": { "enabled": true, "command": "npm test" },
  "disable": ["env-dump"]
}
```

`"mode": "warn"` logs and shows every would-be decision without blocking. References: [policy](docs/policy.md), [hooks](docs/hooks.md), [architecture](docs/architecture.md).

## Other agents

The skills are plain `SKILL.md` folders and work on every agent that reads skills. Each platform gets a manifest, a session-start bootstrap and a tool-name map:

| Platform | Install | What runs |
| --- | --- | --- |
| Claude Code | plugin (above) | everything: hooks, skills, subagents, limits, status line |
| Cursor | `.cursor-plugin/` | skills, plus hooks for session start, prompts (secrets, input limits), shell (policy, token guards), file reads, MCP calls, edits |
| Codex | `.codex-plugin/`, `.agents/plugins/marketplace.json` | skills, `AGENTS.md`, `bin/harness` tools |
| Gemini CLI | `gemini-extension.json` + `GEMINI.md` | skills and bootstrap context, `bin/harness` tools |
| Antigravity | `.antigravity-plugin/` | skills, `bin/harness` tools |
| Kimi Code | `.kimi-plugin/` | skills with session-start skill and tool mapping |
| OpenCode, Copilot CLI, others | clone into the agent's skills folder (`~/.agents/skills/` works for several) | skills, `bin/harness` tools |

Step-by-step install for each: [docs/platforms.md](docs/platforms.md).

## Staying current with Claude Code

- Hook events the harness does not know yet are accepted and logged, never errors.
- `harness upstream` reads Claude Code's hooks reference, lists events added since this release, and with `--apply` registers them.
- `harness doctor` runs the real hook command, so a broken install shows up immediately.

## Development

```bash
make test     # 238 tests
make lint     # ruff
make check    # lint, tests, policy validation, secret scan, skill lint, self-vet
```

The repository develops itself with its own harness ([.claude/settings.json](.claude/settings.json)).

## Credits

Workflow skills adapted from [superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). Long-running agent patterns follow Anthropic's engineering posts on [effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents).

## License

MIT. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
