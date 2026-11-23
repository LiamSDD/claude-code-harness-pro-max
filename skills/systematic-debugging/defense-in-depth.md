# Defense in depth

After fixing a root cause, ask where else the same bad data could enter. Validate at each boundary it crosses, so the next bug of this kind fails loudly and early instead of silently and late.

| Layer | Check |
| --- | --- |
| Entry (CLI, API handler, form) | Reject malformed input with a clear message |
| Business logic | Assert the invariants the function relies on |
| Persistence and side effects | Refuse writes outside expected locations or with missing keys |
| Tests | Guard against environment leakage (a temp dir, not the real home folder) |

```python
def init_workspace(path: str) -> None:
    if not path:
        raise ValueError("workspace path is empty")
    if not os.path.isabs(path):
        raise ValueError(f"workspace path must be absolute, got {path!r}")
    ...
```

Do not add checks you cannot explain. Each one should correspond to a way the system actually failed or plausibly could.
