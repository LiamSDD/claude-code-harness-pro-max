---
name: finishing-a-development-branch
description: Use when implementation on a branch is complete and the tests pass, to decide with the user how to integrate it. Verifies the suite, offers merge, pull request or keep, carries out the choice and cleans up.
---

# Finishing a development branch

## 1. Verify

Run the full test suite and the build. If anything fails, report the failures and stop: integration options come after a green suite.

## 2. Find the base branch

Usually named in the plan or the conversation, or visible with `git rev-parse --abbrev-ref @{upstream}`. If unsure, ask: "This branch started from `main`, correct?" Merging into the wrong base is expensive to undo.

## 3. Offer the options

```text
Implementation complete, <N> tests passing. How would you like to integrate it?

1. Merge into <base> locally
2. Push the branch and open a pull request
3. Keep the branch as it is for now
```

Wait for the answer. The integration decision belongs to the user. Discarding work is never on the menu; do it only if the user explicitly asks, and confirm what will be lost.

## 4. Carry it out

- **Merge locally**

  ```bash
  git checkout <base> && git pull --ff-only
  git merge --no-ff <branch>
  <test command>            # the merged result must be green too
  git branch -d <branch>
  ```

- **Pull request**

  ```bash
  git push -u origin <branch>
  gh pr create --title "<title>" --body "<what changed, why, how it was tested>"
  ```

- **Keep**: report the branch name and where it lives.

## 5. Clean up and record

- If you created a worktree for this work and the branch is merged, remove it (`using-git-worktrees`).
- Mark features done and write a closing note:

  ```bash
  harness progress note --heading "Merged" "<branch>: <summary>; <N> tests; PR <url>"
  ```

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
