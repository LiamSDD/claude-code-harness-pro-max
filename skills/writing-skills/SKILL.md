---
name: writing-skills
description: Use when creating, editing or reviewing a Claude Code skill. Treats a skill like code with a test - observe how an agent fails without it, write the smallest skill that fixes that, verify the agent now complies - and lints and security-checks it with the harness.
---

# Writing skills

A skill is reusable know-how: a technique, a process or a reference that an agent would not reliably get right on its own. It is not a story about how you solved one problem once, and it is not for project conventions (those belong in `CLAUDE.md`) or rules a script could enforce (automate those instead).

## Structure

```text
my-skill/
├── SKILL.md          required: frontmatter + instructions
├── reference.md      optional: detail loaded only when needed
└── scripts/helper.py optional: code the skill runs
```

```markdown
---
name: my-skill
description: Use when <situation>. <What it does in one sentence>.
---
```

- `name`: lowercase letters, digits and hyphens, at most 64 characters, the same as the folder.
- `description`: at most 1024 characters, no XML tags. It is all Claude sees when choosing skills, so lead with **when** to use it, using the words a user or a situation would actually contain.
- Body: under 500 lines. Move long examples and references into linked files, one level deep.

## Test it like code

1. **Red: baseline.** Give a subagent a realistic task where the skill should matter, *without* the skill, and under some pressure (a deadline, a tempting shortcut). Record exactly what it does wrong and the excuses it gives.
2. **Green: minimal skill.** Write only what addresses those failures.
3. **Verify.** Run the same scenarios with the skill available. The agent should now comply.
4. **Refactor.** When it finds a new loophole, name the loophole in the skill and re-test.

## Writing style that works

- Be concrete: commands, file paths, expected output, a short good-and-bad example.
- Say why a rule exists; agents follow rules they understand better than shouted ones.
- Use calm, direct language. All-caps commands and "you have no choice" phrasing cost attention without adding reliability, and look like prompt injection to scanners.
- Tables for decisions ("situation → action"), numbered steps for processes, checklists for verification.
- Do not duplicate what the model already knows; spend words on what it gets wrong.

## Check before you ship

```bash
harness skills check path/to/my-skill      # frontmatter, size, links, hidden characters
harness vet path/to/my-skill               # scripts, code blocks, injection, secrets
```

Fix every error. For skills from someone else, always run `harness vet` before installing: a skill's instructions and scripts run with your permissions.

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
