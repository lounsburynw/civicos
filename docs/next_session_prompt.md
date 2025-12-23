# Recommended: Meeting Schema Validation on Ingest

**Priority:** P0 (IMMEDIATE)
**Area:** data_standards > schema_validation
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 348 completed `vector_backend_protocol_completion` - added embedding_model/embedding_dimension properties to VectorBackend protocol and created PgVectorBackend stub (153/174 items ready, 87.9%). The next priority is adding schema validation to the meeting ingestion pipeline.

**The problem:** Meetings are ingested without validation:
- No JSON schema validation during extraction
- Data quality issues can propagate to vector indexes and API responses
- Need to catch malformed data before it enters the system

## Recommended Task

Add JSON schema validation to meeting ingestion:

1. Find or create `civic-app-schema.json` for Meeting objects
2. Add validation step to meeting extraction/ingestion pipeline
3. Handle validation errors gracefully (log, skip, or fail)

## Key Files to Investigate

```
packages/civic/src/civic/storage/sqlite_backend.py  # store_meetings()
packages/civic/src/civic/storage/postgres_backend.py  # store_meetings()
packages/civic-extraction/  # Platform extractors
data/  # Look for existing schema files
```

## Suggested Approach

1. **Find existing schemas** - Check if civic-app-schema.json exists
2. **Identify validation point** - Where should validation happen? (extraction vs storage)
3. **Add jsonschema validation** - Use `jsonschema` library
4. **Handle errors** - Log validation failures, decide on skip vs fail behavior
5. **Add tests** - Test both valid and invalid meeting data

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# Storage tests
pytest packages/civic/tests/test_storage_protocols.py -v --override-ini="addopts="
```

## Success Criteria

- [ ] Meeting objects validated against JSON schema during ingestion
- [ ] Validation errors logged with details
- [ ] Invalid meetings handled gracefully (skip or fail with clear message)
- [ ] Existing tests still pass
- [ ] pilot.json `validate_meetings_on_ingest` marked as ready

## Pilot Progress

- 153/174 items ready (87.9%)
- 21 items remaining
- P0: validate_meetings_on_ingest (this item)
