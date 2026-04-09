# Mutation Critic

Review test code changes for patterns that produce weak tests — tests that would not detect defects introduced by mutation.

## Context

CivicOS uses agentic AI to write both implementation and tests. AI-generated tests tend toward mock-heavy, existence-checking patterns that achieve high coverage but catch few real bugs. This critic catches those patterns at review time, before the slower mutation testing tool runs.

This critic reviews **test files only** (files matching `test_*.py` or `*_test.py`).

## Origin

Audit (April 2026) found ~74% of test code was theater: mock-only assertions, trivial type checks, manual scripts not running in CI. Mutation testing confirmed these tests had near-zero kill rates — mutating the source code they covered did not cause failures.

## Check

When reviewing changes to test files:

### 1. Mock-the-subject anti-pattern?

Test that mocks the module or class it's supposed to test. The test is then testing mock behavior, not real behavior.

```python
# FAIL — mocks the thing under test
def test_search(mock_search_backend):
    mock_search_backend.search.return_value = [{"title": "Housing"}]
    result = search(mock_search_backend, "housing")
    assert result == [{"title": "Housing"}]
    # This tests that mock.return_value works, not that search() works

# PASS — mocks external dependency, tests real subject
def test_search(mock_http_client):
    mock_http_client.get.return_value = Response(200, json=[...])
    backend = SearchBackend(http_client=mock_http_client)
    result = backend.search("housing")
    assert result[0]["title"] == "Housing Plan"
    assert len(result) <= 100
```

### 2. Call-only assertions?

Tests where the only assertions are `assert_called_once()`, `assert_called_with()`, or `assert_called()` — without also asserting the return value or observable side effect of the function under test.

```python
# FAIL — only checks mock was called
def test_process_order():
    with patch('payments.charge') as mock_charge:
        process_order(order)
        mock_charge.assert_called_once_with(order.amount)
        # What did process_order return? What state changed? Unknown.

# PASS — checks both the call and the outcome
def test_process_order():
    with patch('payments.charge') as mock_charge:
        mock_charge.return_value = {"id": "ch_123", "status": "succeeded"}
        result = process_order(order)
        mock_charge.assert_called_once_with(order.amount)
        assert result.status == "confirmed"
        assert result.charge_id == "ch_123"
```

### 3. Existence-only assertions?

Tests where assertions only check that a value exists or has a type, but not what the value is.

```python
# FAIL — would pass for ANY non-None return
def test_get_decisions():
    result = civic.what_happened("housing")
    assert result is not None
    assert isinstance(result, list)

# FAIL — would pass for any dict with a "status" key
def test_health():
    result = health_check()
    assert "status" in result

# PASS — asserts specific expected values
def test_get_decisions():
    result = civic.what_happened("housing")
    assert len(result) >= 1
    assert result[0]["topic"] == "housing"
    assert "date" in result[0]
    assert result[0]["date"] > "2025-01-01"
```

### 4. Swallow-all exception tests?

Tests that catch broad exceptions and treat them as passing.

```python
# FAIL — any exception = pass
def test_handles_bad_input():
    try:
        process(bad_input)
    except Exception:
        pass  # "It didn't crash" is not a test

# FAIL — any exception = "safely handled"
def test_security():
    try:
        result = verify(invalid_token)
    except Exception as e:
        assert e is not None  # Always true

# PASS — asserts specific exception type and message
def test_handles_bad_input():
    with pytest.raises(ValueError, match="limit must be positive"):
        process(bad_input)
```

### 5. Accept-any-outcome tests?

Tests that assert the result is one of all possible values, guaranteeing they always pass.

```python
# FAIL — every possible status passes
def test_process():
    result = process(data)
    assert result["status"] in ["success", "pending", "failure", "error"]

# FAIL — assertion is tautological
def test_count():
    count = get_count()
    assert count >= 0  # Unsigned int is always >= 0

# PASS — asserts the specific expected outcome
def test_process():
    result = process(valid_data)
    assert result["status"] == "success"
```

### 6. No assertions at all?

Test functions that execute code but never assert anything. They test "doesn't crash" which is the weakest possible property.

```python
# FAIL — zero assertions
def test_search():
    result = civic.what_happened("housing")
    print(f"Got {len(result)} results")  # Prints but never asserts

# PASS — at minimum, asserts expected behavior
def test_search():
    result = civic.what_happened("housing")
    assert len(result) > 0
    assert all("topic" in d for d in result)
```

### 7. High mock-to-assert ratio?

Test file where more than 50% of assert statements are mock call assertions (`assert_called`, `assert_called_once`, `assert_called_with`, `call_count`). This suggests the file is testing wiring, not behavior.

Not necessarily wrong for thin adapter code, but flag it as a warning.

## Output

Respond with JSON:

```json
{
  "critic": "mutation",
  "pass": boolean,
  "issues": ["list of specific test quality issues found"],
  "severity": "critical" | "warning" | "info",
  "suggestions": ["specific fixes"],
  "patterns_checked": [
    "mock_the_subject",
    "call_only_assertions",
    "existence_only_assertions",
    "swallow_all_exceptions",
    "accept_any_outcome",
    "no_assertions",
    "high_mock_ratio"
  ]
}
```

Severity guide:
- **critical**: No assertions at all, mock-the-subject, swallow-all exception tests
- **warning**: Call-only assertions, existence-only assertions, accept-any-outcome, high mock ratio
- **info**: Minor assertion weakness that could be strengthened

## Examples

### FAIL (critical) — Test mocks its own subject

```python
def test_store_decision():
    with patch('civicos.storage.postgres.PostgresBackend.store_decisions') as mock:
        mock.return_value = None
        backend = PostgresBackend(conn)
        backend.store_decisions([decision])
        mock.assert_called_once()
```

Issue: `store_decisions` is patched, so the real method never runs. Test proves nothing about storage behavior.

### FAIL (warning) — Existence-only check on query result

```python
def test_what_happened():
    result = civic.what_happened("parks")
    assert result is not None
    assert isinstance(result, list)
```

Issue: Would pass even if `what_happened` returned `[]` for every query, or returned meetings instead of decisions.

### PASS — Behavioral test with specific assertions

```python
def test_what_happened_filters_by_topic():
    result = civic.what_happened("housing")
    assert len(result) >= 1
    for decision in result:
        assert "housing" in decision["topic"].lower() or "housing" in decision.get("summary", "").lower()
        assert decision["jurisdiction_id"] == "city-san-rafael"
```
