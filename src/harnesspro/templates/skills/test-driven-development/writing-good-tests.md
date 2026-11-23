# Writing good tests

Two principles: every test names the break it catches, and every test exercises the real thing.

## Name the break

Ask: *what production change should make this test fail, and is that change a bug or a decision?* A good test catches a wrong branch, a missing side effect, a wrong argument, a boundary or a broken contract.

```python
# Mirror assertion: both sides come from the code under test, so it can never fail.
assert build_query(tag="urgent") == build_query(tag="urgent")

# Hand-derived literal: fails if the builder breaks.
assert build_query(tag="urgent") == 'tag:"urgent"'
```

Prefer table-driven tests with literal expected values:

```python
CASES = [("", False), ("a@b.co", True), ("no-at-sign", False), (" a@b.co ", True)]


def test_is_valid_email():
    for raw, want in CASES:
        assert is_valid_email(raw) is want, raw
```

## Exercise the real thing

```python
# Tests the mock: passes even if retry() never calls the operation again.
op = Mock(side_effect=[Error(), Error(), "ok"])
retry(op)
op.assert_called()

# Tests behaviour: counts real attempts and checks the result.
attempts = []


def op():
    attempts.append(1)
    if len(attempts) < 3:
        raise Error()
    return "ok"


assert retry(op) == "ok"
assert len(attempts) == 3
```

Mock at the boundary you do not own (network, clock, payment provider), and only after the real dependency proved slow or unavailable.

## Smells

| Smell | Fix |
| --- | --- |
| Test name contains "and" | Split it |
| Sleeps for a fixed time | Wait for the condition (see `systematic-debugging/condition-based-waiting.md`) |
| Asserts that a file contains a line | Run it and assert on output or side effects |
| Needs ten mocks | The code is too coupled; inject dependencies |
| Passes the first time you run it | You have not seen it catch anything yet |
