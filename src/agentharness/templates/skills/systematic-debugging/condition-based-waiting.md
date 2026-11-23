# Condition-based waiting

Fixed sleeps (`sleep(2)`, `setTimeout(..., 500)`) are guesses about timing. They make tests slow when the guess is long and flaky when it is short. Wait for the condition you actually need, with a timeout.

```python
import time


def wait_for(condition, timeout=5.0, interval=0.05, what="condition"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = condition()
        if result:
            return result
        time.sleep(interval)
    raise TimeoutError(f"timed out after {timeout}s waiting for {what}")


wait_for(lambda: os.path.exists(pid_file), what="server pid file")
```

```typescript
async function waitFor<T>(check: () => T | Promise<T>, timeoutMs = 5000, what = "condition"): Promise<T> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await check();
    if (value) return value;
    await new Promise((r) => setTimeout(r, 50));
  }
  throw new Error(`timed out after ${timeoutMs}ms waiting for ${what}`);
}
```

Good conditions: a port accepting connections, a file existing, a log line appearing, a status endpoint returning ready, a mock having been called. Always include a timeout and say in the error what you were waiting for.
