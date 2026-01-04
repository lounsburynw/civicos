# Recommended: election_integration (Phase 3 - Elections Storage)

**Priority:** P0
**Area:** data_readiness > election_data
**Date:** 2026-01-03

> This is recommended context from Session 462. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 462 discovered Google Civic Representatives API was **turned down April 2025** and created an alternative:

- Created `RepresentativesClient` combining free APIs (Open States + Congress.gov + local data)
- Achieves Ballotpedia-equivalent coverage at $0/month
- Commit: `8f3195e`

**What still needs to be done for election_integration:**
1. Elections storage integration (mapper + StorageBackend)
2. The elections and voterinfo endpoints still work - just representatives is gone

## Recommended Task

Create the elections storage integration:

1. **Map Google Civic responses to Election models:**
   ```python
   def google_civic_to_election(api_response: dict, jurisdiction_id: str) -> Election:
       # Map elections endpoint response to Election dataclass
   ```

2. **Create extraction helper:**
   ```python
   def extract_elections(client: GoogleCivicClient, storage: StorageBackend) -> int:
       elections = client.get_elections()
       mapped = [google_civic_to_election(e, jurisdiction_id) for e in elections]
       storage.store_elections(mapped)
       return len(mapped)
   ```

3. **Test with SQLite backend**

## Key Files

- `packages/civic-extraction/src/civic_extraction/clients/google_civic.py` - Client (620 lines, working)
- `packages/civic/src/civic/_internal/elections/__init__.py` - Data models (Election, Contest, etc.)
- `packages/civic/src/civic/storage/backend.py:1448-1670` - Election storage methods
- `docs/critical/ELECTION_INTEGRATION.md` - Full implementation reference

## API Status (verified Session 462)

| Endpoint | Status | Notes |
|----------|--------|-------|
| `elections` | ✅ Working | Returns available elections list |
| `voterinfo` | ✅ Working | Returns contests, polling locations |
| `representatives` | ❌ Gone | Turned down April 2025 |

## Tests to Run

```bash
# GoogleCivicClient tests
pytest packages/civic-extraction/tests/test_clients.py::TestGoogleCivicClient -v -q --override-ini="addopts="

# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `google_civic_to_election()` mapper function created
- [ ] Elections fetched and stored via StorageBackend
- [ ] Integration test with real API + SQLite storage
- [ ] All tests passing

## Related Work (Completed Session 462)

The `RepresentativesClient` is available if needed:
```python
from civic_extraction.clients import create_san_rafael_representatives_client
client = create_san_rafael_representatives_client()
reps = client.get_representatives()  # Returns 11 reps (federal + state + local)
```

Uses existing env vars: `FAC_API_KEY` (Congress.gov) and `OPENSTATES_API_KEY` (Open States).
