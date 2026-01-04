# Recommended: election_integration (Phase 3 - OAuth + Storage)

**Priority:** P0
**Area:** data_readiness > election_data
**Date:** 2026-01-03

> This is recommended context from Session 461. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 461 completed **Phase 2: Google Civic API Client**:
- `GoogleCivicClient` created with `get_elections()`, `get_voter_info()`, `get_representatives()`
- API key handling from `GOOGLE_CIVIC_API_KEY` or `GOOGLE_API_KEY` env vars
- Request throttling (5 req/sec), exponential backoff
- 25 unit tests passing

**API Status (verified with real key):**
- `elections` endpoint: **Working** - returns available elections
- `voterinfo` endpoint: **Working** - returns polling locations, contests (when election available)
- `representatives` endpoint: **Returns "Method not found"** - needs OAuth investigation

Commit: `d02c2e9`

## Recommended Task

1. **Investigate OAuth for representatives endpoint** - the API returns "Method not found" with API key auth, may require OAuth 2.0
2. **Integrate with storage backend** - map API responses to Election data models and store via StorageBackend

## Key Files

- `packages/civic-extraction/src/civic_extraction/clients/google_civic.py` - Client implementation (620 lines)
- `packages/civic/src/civic/_internal/elections/__init__.py` - Data models (Election, Contest, etc.)
- `packages/civic/src/civic/storage/backend.py:1448-1670` - Election storage methods
- `docs/critical/ELECTION_INTEGRATION.md` - Full implementation reference

## Suggested Approach

### Part A: OAuth for Representatives

1. Check Google Cloud Console for OAuth 2.0 credentials
2. Research if Civic Information API representatives endpoint requires OAuth vs API key
3. If OAuth needed:
   - Add `google-auth` / `google-auth-oauthlib` dependencies
   - Implement OAuth flow in `GoogleCivicClient`
   - Test with real API

### Part B: Storage Integration

1. Create helper to map `GoogleCivicClient` responses to `Election` data models:
   ```python
   def google_civic_to_election(api_response: dict, jurisdiction_id: str) -> Election:
       # Map elections endpoint response to Election dataclass
   ```

2. Add extraction method to fetch and store:
   ```python
   def extract_elections(client: GoogleCivicClient, storage: StorageBackend) -> int:
       elections = client.get_elections()
       mapped = [google_civic_to_election(e, client.jurisdiction_id) for e in elections]
       storage.store_elections(mapped)
       return len(mapped)
   ```

3. Test with SQLite backend

## Tests to Run

```bash
# GoogleCivicClient tests
pytest packages/civic-extraction/tests/test_clients.py::TestGoogleCivicClient -v -q --override-ini="addopts="

# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Representatives endpoint working (OAuth or determine it's not needed)
- [ ] `google_civic_to_election()` mapper function created
- [ ] Elections fetched and stored via StorageBackend
- [ ] Integration test with real API + SQLite storage
- [ ] All tests passing

## API Reference

```bash
# Load .env for API key
from dotenv import load_dotenv; load_dotenv()

# Test elections (works)
curl "https://civicinfo.googleapis.com/civicinfo/v2/elections?key=$GOOGLE_API_KEY"

# Test representatives (returns 404 "Method not found")
curl "https://civicinfo.googleapis.com/civicinfo/v2/representatives?key=$GOOGLE_API_KEY&address=San+Rafael,+CA"
```

## Alternative

If OAuth investigation is blocked, focus on storage integration with the working endpoints (elections, voterinfo) first. Representatives can be added later.
