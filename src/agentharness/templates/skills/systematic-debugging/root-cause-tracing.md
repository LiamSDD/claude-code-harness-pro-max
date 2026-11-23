# Root-cause tracing

Errors surface far from their cause: a file written to the wrong folder, a `None` deep in a call chain, a test that fails only after another test ran. Fix where the bad value is *created*, not where it is noticed.

1. **Symptom**: write down exactly what is wrong and where it shows up.
2. **Immediate cause**: which line produces the symptom, and with what values?
3. **Walk up the call chain**: who called that with the bad value? Repeat until you reach the code that created it.
4. **Instrument if the chain is unclear**: log the value, the caller and a stack trace at the point of failure:

   ```python
   import traceback, sys

   print(f"DEBUG path={path!r} cwd={os.getcwd()!r}", file=sys.stderr)
   traceback.print_stack(file=sys.stderr)
   ```

   In tests, write to stderr: some runners hide stdout.
5. **Fix at the source**, then add a check at the entry point of the layer that received the bad value (see `defense-in-depth.md`).

## Finding the test that pollutes others

When a test passes alone but fails in the suite, another test leaves state behind (files, environment variables, globals, a database row). Bisect: run the failing test after the first half of the suite, then the first quarter, until one test remains. Then fix that test's cleanup.
