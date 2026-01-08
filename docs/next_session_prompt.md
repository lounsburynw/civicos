# Recommended: pgvector_integration_tests

**Priority:** P0
**Area:** data_architecture > vector_sql_linkage
**Date:** 2026-01-08

> This is recommended context from Session 491. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 491 completed `pgvector_cross_corpus_search` - `what_applies()` now uses PgVectorBackend.search() for municipal code, enabling access to the 500k+ vectors in pgvector. The API is now fully connected to production vector storage. Next step is to add integration tests that validate this works in CI.

## Recommended Task

Add `@pytest.mark.requires_pgvector` integration tests that validate vector search against production pgvector. These tests should:
- Run in CI using GitHub Actions secrets for DATABASE_URL
- Follow security best practices (no secrets in code)
- Test the new municipal_code search in `what_applies()`

## Key Files

- `packages/civic/src/civic/context.py:217-249` - Municipal code search using PgVectorBackend
- `packages/civic/src/civic/storage/pgvector_backend.py:869-983` - PgVectorBackend.search()
- `packages/civic/tests/conftest.py` - Test fixtures and markers
- `.github/workflows/tests.yml` - CI configuration for test parallelization
- `pilot.json:1136` - pgvector_integration_tests item

## Suggested Approach

1. **Create pytest marker** in `conftest.py`:
```python
@pytest.mark.requires_pgvector
```

2. **Add integration test file** `test_pgvector_integration.py`:
```python
@pytest.mark.requires_pgvector
def test_municipal_code_search():
    """Validate municipal code search returns results from pgvector."""
    from civic import Civic
    c = Civic('city-san-rafael')
    result = c.what_applies('accessory dwelling unit')

    # Should have municipal code results
    ordinances = [r for r in result.local if r.get('type') == 'ordinance']
    assert len(ordinances) > 0

    # ADU query should find Section 14.16.285
    sections = [r.get('section_number') for r in ordinances]
    assert any('14.16.285' in s for s in sections if s)
```

3. **Configure CI** to run pgvector tests with DATABASE_URL secret:
```yaml
# In .github/workflows/tests.yml
- name: Run pgvector integration tests
  if: github.event_name != 'pull_request'  # Only on main
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
  run: pytest -m requires_pgvector
```

4. **Skip locally** when DATABASE_URL not set using `skipif` in conftest

## Tests to Run

```bash
# Verify current tests still pass
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# Manual verification that pgvector search works
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civic import Civic
c = Civic('city-san-rafael')
result = c.what_applies('ADU zoning')
print(f'Local results: {len(result.local)}')
for loc in result.local[:3]:
    print(f'  Type: {loc.get(\"type\")}, Section: {loc.get(\"section_number\")}')
"
```

## Success Criteria

- [ ] `@pytest.mark.requires_pgvector` marker defined in conftest.py
- [ ] Integration test validates municipal_code search returns results
- [ ] Test skips gracefully when DATABASE_URL not set
- [ ] CI workflow configured to run pgvector tests with secrets
- [ ] pilot.json: pgvector_integration_tests -> ready

## Session 491 Insights

- `what_applies()` now uses PgVectorBackend.search() for municipal_code (context.py:217-249)
- Pattern mirrors existing codified_law search (context.py:153-183)
- ADU query returns Section 14.16.285 with score 0.744
- 39 smoke tests pass with the new integration
