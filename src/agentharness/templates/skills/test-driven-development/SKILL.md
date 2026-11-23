---
name: test-driven-development
description: Use when implementing any feature, bug fix or behaviour change, before writing the implementation. Write the test first, watch it fail for the right reason, then write the minimum code to pass.
---

# Test-driven development

A test you never saw fail proves nothing: it may test the wrong thing, or nothing at all. Writing it first and watching it fail is how you know it can catch the bug.

## The cycle

1. **Red.** Write one small test for one behaviour, named after that behaviour. Use real code; mock only what is slow or external.
2. **Watch it fail.** Run it. It must *fail* (not error), with the message you expected, because the feature is missing (not because of a typo). If it passes, it tests existing behaviour: change the test.
3. **Green.** Write the simplest code that passes. No extra options, no refactoring elsewhere.
4. **Watch it pass**, then run the project's **whole** suite, not just your file. Report any failure you see, including ones you did not cause.
5. **Refactor** with the suite green: remove duplication, improve names. No new behaviour.
6. Repeat for the next behaviour.

## Rules that keep tests honest

- Before writing a test, name the production change that would make it fail. If only a deliberate redesign could fail it (a constant's value, exact wording), it is a change detector, not a test.
- Assert on literal, hand-checked values. An expectation computed by the code under test always passes.
- Test behaviour through the public interface, not private structure.
- Keep test helpers in test code, never in production classes.
- Understand a dependency's side effects before you mock it.

See [writing-good-tests.md](writing-good-tests.md) for examples.

## When the code came first

If you wrote implementation before a test, set it aside and write the test against the behaviour you want. Watch it fail against the old code (or with your change reverted), then bring the implementation back. Tests written after the fact tend to confirm what the code does rather than what it should do.

## Bug fixes

Reproduce the bug as a failing test first. The test proves the fix and stops the bug coming back. Then follow `systematic-debugging` to find the cause.

## Exceptions

Throwaway prototypes, generated code and pure configuration can skip the cycle, but ask the user rather than deciding alone.

## Before you say you are done

- [ ] Every new behaviour has a test that you saw fail first
- [ ] Each failed for the expected reason
- [ ] The full suite passes and the output has no new warnings
- [ ] Edge cases and error paths are covered

---
Adapted from [obra/superpowers](https://github.com/obra/superpowers) by Jesse Vincent (MIT). See THIRD_PARTY_NOTICES.md.
