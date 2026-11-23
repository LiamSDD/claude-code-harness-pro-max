---
name: using-git-worktrees
description: Use before feature work or plan execution that should not disturb the current checkout. Detects existing isolation, prefers Claude Code's native worktree support, and falls back to a safe git worktree with a verified baseline.
---

# Using git worktrees

A worktree is a second checkout of the same repository on its own branch. Your changes cannot disturb the user's working copy, and abandoning the work is as simple as removing the folder.

## 1. Already isolated?

```bash
git rev-parse --git-dir --git-common-dir --show-toplevel
git branch --show-current
```

If `--git-dir` and `--git-common-dir` differ, you are already in a linked worktree (unless `git rev-parse --show-superproject-working-tree` prints a path, which means a submodule). Do not create another; go to step 3.

## 2. Create one

Ask first, unless the user's instructions already state a preference: "Shall I work in a separate worktree so your current branch is untouched?"

- **Prefer native support.** If you have a worktree tool (for example `EnterWorktree`, or `claude --worktree`), use it: Claude Code then tracks and cleans it up.
- **Otherwise use git:**

  ```bash
  git check-ignore -q .worktrees || { echo ".worktrees/" >> .gitignore && git add .gitignore && git commit -m "Ignore local worktrees"; }
  git worktree add .worktrees/<branch-name> -b <branch-name>
  cd .worktrees/<branch-name>
  ```

  Never create the worktree folder inside the repository without it being ignored: its files would be committed.

## 3. Prepare and check the baseline

Install dependencies the way the project does (`npm ci`, `uv sync`, `pip install -e .`, `go mod download`), then run the test suite. Report the result before changing anything. A red baseline is information the user needs; do not build on it silently.

## Cleaning up

Only after the work is merged or the user says to discard it:

```bash
git worktree remove .worktrees/<branch-name>
git branch -d <branch-name>     # -D only if the user asked to discard unmerged work
```

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
