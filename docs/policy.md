# Policy reference

The effective policy is the built-in [defaults](../src/harnesspro/defaults/policy.json) merged with each layer that exists:

| Layer | Path | Commit it? |
| --- | --- | --- |
| user | `~/.claude/harness/policy.json` (or `$CLAUDE_CONFIG_DIR/harness/policy.json`) | no |
| project | `.claude/harness/policy.json` | yes |
| local | `.claude/harness/policy.local.json` | no (ignored by `harness init`) |
| env | the file named by `$HARNESS_POLICY` | CI only |

Merge rules: objects merge key by key, lists append without duplicates, scalars override, and a key ending in `!` replaces the list (`"deny_read!": [...]`). Keys starting with `$` are comments. A layer that is not valid JSON or fails validation is skipped, reported at session start and by `harness doctor`.

`harness policy show` prints the merged result; `harness policy sources` lists the layers in order.

## Top-level keys

| Key | Values | Default | Meaning |
| --- | --- | --- | --- |
| `mode` | `enforce`, `warn`, `off` | `enforce` | `warn` logs and shows would-be decisions without blocking |
| `fail_mode` | `open`, `closed` | `open` | what `PreToolUse` does if the harness itself errors |
| `disable` | rule ids | `[]` | switch built-in rules off |

## Rules

Every finding carries a rule id. It appears in Claude's denial reason, in `harness check` and in the audit log.

### Shell (`Bash` tool)

| Rule | Decision | Fires on |
| --- | --- | --- |
| `rm-dangerous-target` | deny | recursive `rm` / `rmdir` / `find -delete` of `/`, system directories, `~`, the project root or a parent; `--no-preserve-root`. A bare `rm *` in the project root asks |
| `pipe-to-shell` | deny / ask | `curl`, `wget`, `base64 -d` ... piped into `sh`, `bash`, `python` and other interpreters, and `bash <(curl ...)`. Other input piped into a shell asks |
| `git-force-push` | deny / ask | force push to `main`, `master`, `develop`, `release/*`, `production` or with no branch (deny); to other branches, `--mirror` and ref deletion (ask) |
| `git-no-verify` | deny | `--no-verify` / `commit -n` |
| `git-destructive` | ask | `reset --hard`, `clean -f`, `checkout -- .`, `restore .`, `branch -D`, `stash drop/clear`, `filter-branch`, `reflog expire` |
| `chmod-world-writable` | deny | `chmod 777`/`666`/`o+w`, recursive `chown` of system directories |
| `disk-destroy` | deny | `dd of=/dev/...`, `mkfs`, `fdisk`, `wipefs`, `shred`, `diskutil erase*`, redirects to block devices |
| `system-power` | deny | `shutdown`, `reboot`, `halt`, `systemctl poweroff` |
| `kill-all` | deny / ask | `kill -9 -1` (deny), `killall -9`, `pkill -9` (ask) |
| `persistence` | deny | `crontab -r` |
| `history-tamper` | ask | `history -c`, `unset HISTFILE` |
| `env-dump` | ask | bare `env`, `printenv`, `set`, `export -p`, `/proc/*/environ` |
| `network-upload` | ask | `curl -d @file`/`-T`, `wget --post-file`, `scp`/`rsync` to a remote, `nc`/`socat` |
| `publish` | ask | `npm/yarn/pnpm publish`, `twine upload`, `cargo publish`, `docker push`, `gh release create`, `gh repo delete/edit --visibility`, `gh pr merge` |
| `infra-destroy` | ask | `terraform destroy` / `apply -auto-approve`, `pulumi destroy`, `kubectl delete`, `helm uninstall`, `aws ... delete-*`, `docker system prune` |
| `db-destroy` | ask | `DROP`/`TRUNCATE` through database CLIs, `dropdb`, `redis-cli FLUSHALL`, `prisma migrate reset`, `supabase db reset` |
| `sudo` | `bash.sudo` (ask) | any command run through `sudo` or `doas` |
| `fork-bomb` | deny | `:(){ :|:& };:` |
| `shell-parse-error` | `bash.on_parse_error` (ask) | unbalanced quotes or parentheses |
| `secret-in-command` | `secrets.scan_commands` (ask) | a literal provider token in the command line |
| `web-domain` | see `web` | `curl`/`wget` to a denied or ask-listed host |

Paths in arguments and redirects are checked too: `cat .env`, `python app.py < .env`, `cp ~/.ssh/id_rsa /tmp` and `git add .env` hit `secret-file-read`; `echo x > .git/HEAD` hits `protected-path-write`. `cd` inside a chain is followed, so `cd build && rm -rf .` is judged against `build/`.

### Files

| Rule | Decision | Tools |
| --- | --- | --- |
| `secret-file-read` | deny | `Read`, `Grep` (path or literal glob), and Bash arguments, for paths in `paths.deny_read` |
| `protected-path-write` | deny | `Write`, `Edit`, `MultiEdit`, `NotebookEdit`, redirects, `tee`, `cp`/`mv` destinations, for `paths.deny_write` |
| `sensitive-path-write` | ask | the same, for `paths.ask_write` (lockfiles, CI workflows, `.env`, the harness policy) |
| `write-outside-project` | `paths.write_outside_project` (ask) | writes outside the project that are not in `paths.write_allow_outside` |
| `secret-in-write` | deny / ask | new content containing a provider token (deny) or a likely credential (ask) |

### Web and MCP

| Rule | Decision | Fires on |
| --- | --- | --- |
| `web-domain` | deny / ask | `WebFetch` and shell HTTP clients: `web.deny_domains` (deny), `web.ask_domains` such as paste sites, request bins and tunnels (ask), anything outside a non-empty `web.allow_domains` (ask) |
| `mcp-tool` | deny / ask | MCP tools matching `mcp.deny_tools` / `mcp.ask_tools` (default: `*delete*`, `*drop*`, `*destroy*`, `*purge*`) |

## Sections

### `bash`

```json
"bash": {
  "on_parse_error": "ask",
  "sudo": "ask",
  "rules": [
    { "id": "no-prod-deploy", "pattern": "deploy\\.sh\\s+prod", "decision": "deny", "reason": "Production deploys run from CI.", "scope": "segment" }
  ]
}
```

`rules[].pattern` is a Python regex. With `scope: "segment"` (default) it is matched against each simple command after unwrapping; with `scope: "command"`, against the whole string.

### `paths`

Gitignore-style patterns, last match wins:

- `*.pem` (no slash) matches a file name anywhere
- `**/.ssh/**` matches anywhere, inside or outside the project
- `.github/workflows/**` is relative to the project root
- `~/.aws/**` and `/etc/**` are absolute
- `!pattern` re-includes a path

### `secrets`

| Key | Default | Meaning |
| --- | --- | --- |
| `scan_writes` | `true` | check new file content |
| `scan_prompts` | `warn` | `off`, `warn` (tell the user, instruct Claude not to reuse it) or `block` |
| `scan_commands` | `ask` | decision when a command line contains a token |
| `allow_patterns` | `[]` | regexes for known false positives |
| `ignore_paths` | `[]` | path patterns whose writes are not scanned (test fixtures) |

### `stop_gate`

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `false` | run the gate when Claude stops |
| `command` | `""` | shell command; exit 0 means pass |
| `timeout` | `300` | seconds; a timeout counts as a failure |
| `only_if_edited` | `true` | skip when no file was edited since the last pass |
| `max_blocks` | `3` | after this many consecutive failures Claude may stop, and you are told |

### `verify_claims`

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | check Claude's final message when it stops |
| `max_blocks` | `1` | how many times per edit cycle Claude is sent back |
| `test_commands` | `[]` | extra regexes for commands that count as verification |

When Claude stops after editing files and its last message claims success ("all tests pass", "fixed the bug", "ready to merge" ...), the harness checks that a test, build, lint or type-check command succeeded after the last edit. Recognised commands include pytest, unittest, npm/pnpm/yarn/bun test and build, jest, vitest, tsc, go test, cargo test, make test, gradle, mvn, rspec, phpunit, dotnet test, ruff and mypy, plus the stop gate command. A failed run does not count.

### `cost`

| Key | Default | Meaning |
| --- | --- | --- |
| `session_budget_usd` | `0` (off) | estimated spend at which tool calls need confirmation |
| `warn_at` | `0.8` | fraction of the budget at which Claude and the user are warned once |
| `on_budget` | `ask` | decision once the budget is reached |
| `read_dedupe` | `true` | refuse a full re-read of an unchanged file in the same agent context |
| `max_read_bytes` | `200000` | refuse full reads and `cat` of larger files; range reads are allowed |
| `output_guard` | `deny` | decision for large reads and flooding commands (`allow` turns them off) |
| `generated_reads` | `deny` | decision for reads matching `generated_paths` |
| `generated_paths` | lockfiles, `node_modules`, `*.min.*`, `*.map`, build caches | gitignore-style patterns |
| `prices` | built-in table | per-model USD per million tokens: `input`, `output`, optional `cache_read`, `cache_write_5m`, `cache_write_1h` |

Spend is computed from the session transcript Claude Code writes, read incrementally by the hooks.

| Rule | Fires on |
| --- | --- |
| `token-duplicate-read` | full `Read` of a file already read by this agent and unchanged since; reset on `/clear` and compaction |
| `token-generated-read` | `Read` of a generated or vendored file |
| `token-large-read` | full `Read` of a file over `max_read_bytes` |
| `token-output-flood` | `cat`/`less` of large files, `find /` or `find ~` without `-maxdepth`, `tail -f`, `watch`, `docker`/`kubectl logs` without `--tail`/`--since`, `journalctl` without `-n`/`--since`, `git log` without a limit, `ls -R`/`tree` of the project |
| `budget-exceeded` | any tool call once the session budget is reached |

### `subagents`

| Key | Default | Meaning |
| --- | --- | --- |
| `max_per_session` | `0` (off) | subagents one session may start |
| `max_concurrent` | `0` (off) | subagents running at the same time |
| `on_limit` | `deny` | decision when a limit is hit (`subagent-limit`, `subagent-concurrency`) |
| `models` | `{}` | `subagent_type` → model (`haiku`, `sonnet`, `opus` or an id); `*` is the fallback. Applied only when the Agent call names no model |

### `post_edit`

```json
"post_edit": {
  "formatters": [
    { "glob": "*.py", "command": "ruff format --quiet {file}" },
    { "glob": "*.ts", "command": "npx eslint --fix {file}" },
    { "glob": "*.tsx", "command": "npx eslint --fix {file}" }
  ],
  "timeout": 30
}
```

`{file}` is replaced with the shell-quoted absolute path. Formatters that are not installed are skipped. A non-zero exit is reported back to Claude as context.

### `context`, `compaction`, `audit`, `notify`

| Key | Default |
| --- | --- |
| `context.session_start`, `context.git`, `context.progress` | `true` |
| `context.recent_commits` | `5` |
| `context.skills` | `true`: list available skills at session start |
| `context.max_chars` | `6000` |
| `compaction.checkpoint` | `true`: append a checkpoint to `progress.md` before compaction |
| `compaction.instructions` | what the compacted summary must keep |
| `audit.path` | `.claude/harness/audit.jsonl` |
| `audit.max_bytes`, `audit.keep` | `5000000`, `3` rotated files |
| `notify.enabled`, `notify.on` | `false`, `["permission_prompt", "idle_prompt"]` (desktop notification via `osascript` or `notify-send`) |
