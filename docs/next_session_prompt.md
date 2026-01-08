# Recommended: election_whats_next_integration

**Priority:** P0
**Area:** data_readiness > election_data
**Date:** 2026-01-07

> This is recommended context from Session 488. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 488 completed `codified_law_vectors` - 490k vector embeddings for U.S. Code, CA Codes, and CFR are now in pgvector. Semantic search verified working across all jurisdictions.

Election data infrastructure is 8/11 items ready. The postgres backend and ingestion pipeline are complete. The next step is integrating election data with the `whats_next()` API.

## Recommended Task

Integrate election data into the `whats_next()` API so users can see upcoming elections alongside meetings.

## Key Files

- `packages/civic/src/civic/context.py` - Contains `whats_next()` implementation
- `packages/civic/src/civic/storage/postgres_backend.py` - Election data queries
- `packages/civic/tests/test_civic.py` - Core API tests
- `pilot.json` - data_readiness > election_data section

## Steps

1. **Understand current whats_next() implementation:**
```python
from dotenv import load_dotenv; load_dotenv()
from civic import Civic
c = Civic('city-san-rafael')
result = c.whats_next()
print(result.keys())  # See what's currently returned
```

2. **Check election data in database:**
```python
from civic.storage.postgres_backend import PostgresBackend
import os
db = PostgresBackend(os.environ['DATABASE_URL'])
# Find election-related tables/methods
```

3. **Design integration approach:**
   - What election data should appear in `whats_next()`?
   - Upcoming elections? Candidate filing deadlines? Ballot measures?
   - Should it be a separate key or merged with meetings?

4. **Implement integration in context.py**

5. **Add tests for election data in whats_next()**

6. **Update pilot.json status to ready**

## Data Available

Election infrastructure ready items:
- election_integration
- roll_call_extraction
- elected_officials_table
- voting_record_api
- election_postgres_backend
- election_ingestion_pipeline

## Success Criteria

- [ ] `whats_next()` returns upcoming election information
- [ ] Tests pass for election data in whats_next()
- [ ] pilot.json: election_whats_next_integration -> ready
