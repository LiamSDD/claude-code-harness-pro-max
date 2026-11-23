---
name: release-check
description: Pre-release checklist covering tests, secrets, changelog, version and a clean tree. Use before tagging a release, publishing a package or deploying.
disable-model-invocation: true
---

# Release check

Run every step and report each as PASS or FAIL with evidence. Stop at the first FAIL that would ship a broken or unsafe release, and ask the user how to proceed.

1. **Clean tree**: `git status --porcelain` is empty and the branch is up to date with its remote (`git fetch && git status -sb`).
2. **Tests**: the full suite passes (see `CLAUDE.md` for the command). Include the pass count.
3. **Lint and types**: the project's linters and type checker pass, if it has them.
4. **Secrets**: `harness scan .` reports no findings, or every finding is a documented false positive.
5. **Version**: the version number is bumped consistently everywhere it appears (package manifest, `__version__`, plugin manifest).
6. **Changelog**: `CHANGELOG.md` has an entry for this version describing user-visible changes.
7. **Dependencies**: no new dependency is unpinned or unexplained.
8. **Build**: the package or app builds from a clean checkout.
9. **Policy audit**: `harness audit --blocked --tail 50` shows nothing unexpected from this release cycle.

Finish with a summary table and a GO or NO-GO recommendation. Do not tag, publish or deploy yourself; the user does that.
