# Recommended: election_ingestion_pipeline

**Priority:** P0
**Area:** data_readiness > election_data
**Date:** 2026-01-05

> This is recommended context from Session 478. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 478 verified that `election_postgres_backend` is already fully implemented (9 methods). The PostgresBackend election storage is ready, but the production elections table is nearly empty (4 elections, none San Rafael-specific). We need a Modal job to ingest election data.

The infrastructure exists:
- `GoogleCivicClient` with `get_elections()` and `get_voter_info()` methods
- Storage mappers: `extract_elections_to_storage()`, `extract_voter_info_to_storage()`
- PostgresBackend election methods: verified working with Supabase

## Recommended Task

Create a Modal job in `scripts/modal_ingest.py` to ingest San Rafael election data from Google Civic API, following the pattern of existing Modal jobs.

## Key Files

- `scripts/modal_ingest.py` - Modal pipeline (add new `fetch_elections` function)
- `packages/civic-extraction/src/civic_extraction/clients/google_civic.py` - GoogleCivicClient class
- `packages/civic-extraction/src/civic_extraction/clients/google_civic.py:380-430` - `extract_elections_to_storage()` function
- `packages/civic/src/civic/storage/postgres_backend.py:5982-6064` - PostgresBackend.store_elections()

## Suggested Approach

1. **Explore existing Modal patterns:**
   ```bash
   grep -n "def fetch_" scripts/modal_ingest.py | head -10
   ```
   Follow pattern of `fetch_meetings`, `fetch_issues`, etc.

2. **Create `fetch_elections()` Modal function:**
   ```python
   @app.function(image=civic_image, secrets=[modal.Secret.from_name("civic-env")])
   def fetch_elections(jurisdiction: str = "city-san-rafael"):
       from civic_extraction.clients import GoogleCivicClient
       from civic_extraction.clients.google_civic import extract_elections_to_storage
       from civic.storage import get_storage_backend

       client = GoogleCivicClient(api_key=os.environ["GOOGLE_CIVIC_API_KEY"])
       backend = get_storage_backend()

       elections = client.get_elections()
       count = extract_elections_to_storage(elections, backend, jurisdiction)
       return {"elections_stored": count}
   ```

3. **Add to main() dispatcher:**
   Similar to `--meetings`, `--issues`, add `--elections` flag

4. **Test locally first:**
   ```bash
   source civic-env/bin/activate && export $(grep -v '^#' .env | xargs)
   python3 -c "
   from civic_extraction.clients import GoogleCivicClient
   import os
   client = GoogleCivicClient(api_key=os.environ.get('GOOGLE_CIVIC_API_KEY'))
   elections = client.get_elections()
   print(f'Found {len(elections)} elections')
   for e in elections[:3]:
       print(f'  - {e}')
   "
   ```

## Tests to Run

```bash
# Unit tests for GoogleCivicClient
pytest packages/civic-extraction/tests/test_clients.py -v -k "google" --override-ini="addopts="

# Voting record API tests (use election storage)
pytest packages/civic/tests/test_voting_record_api.py -v --override-ini="addopts="
```

## Success Criteria

- [ ] `fetch_elections()` function added to `scripts/modal_ingest.py`
- [ ] `--elections` flag added to main() dispatcher
- [ ] Local test shows elections fetched from Google Civic API
- [ ] `modal run scripts/modal_ingest.py --elections` stores data to Supabase
- [ ] pilot.json updated: election_ingestion_pipeline -> ready
