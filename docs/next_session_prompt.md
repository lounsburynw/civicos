# Recommended: r2_source_caching

**Priority:** P0
**Area:** pipeline_automation > cloud_integration
**Date:** 2025-12-27

> This is recommended context from Session 377. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 377 completed **pipeline_cloud_storage** - the ETL pipeline CLI now uses cloud storage (PostgresBackend) when DATABASE_URL is set. The factory function `get_storage_backend()` automatically selects the right backend.

Now the pipeline stores structured data to Supabase, but **raw scraped content is not cached**. Each pipeline run re-scrapes ProudCity pages, which is slow and wasteful.

## Cloud Storage Status

| Data Type | Backend | Status |
|-----------|---------|--------|
| SQL (meetings, decisions) | PostgresBackend (Supabase) | **READY** |
| Vectors (embeddings) | PgVectorBackend (Supabase pgvector) | **READY** |
| Blobs (PDFs, audio) | R2Backend (Cloudflare R2) | **READY** |
| Source cache (HTML, API) | R2Backend | **NOT IMPLEMENTED** |

## Recommended Task

Add a caching layer to the ETL pipeline that stores raw scraped content in R2:
- Cache scraped HTML pages with URL hash as key
- Cache downloaded PDFs before parsing
- Cache API responses from external services
- Add TTL-based expiration (e.g., 24 hours for meeting pages)

## Key Files

- `packages/civic-extraction/src/civic_extraction/clients/proudcity.py` - ProudCity scraper to add caching
- `packages/civic/src/civic/storage/blob.py:144-280` - R2Backend implementation (already ready)
- `packages/civic/src/civic/storage/__init__.py:60` - `get_blob_storage()` factory function

## Suggested Approach

1. **Create SourceCache class** in `civic_extraction/cache.py`:
   - `cache_key(url: str) -> str` - SHA256 hash of URL
   - `get(url: str) -> Optional[bytes]` - Check R2 for cached content
   - `put(url: str, content: bytes, ttl_hours: int)` - Store with metadata
   - Use `get_blob_storage()` to get R2/Local backend from environment

2. **Integrate with ProudCitySource**:
   - Add `source_cache: Optional[SourceCache]` parameter
   - Check cache before HTTP requests in `_fetch_page()` and `_fetch_json()`
   - Store responses after successful fetches

3. **CLI integration**:
   - Load blob storage from `BLOB_STORAGE_URL` env var
   - Pass cache to source constructor

## Environment Variables

```bash
# Already configured in .env
BLOB_STORAGE_URL=r2://[account_id]/civic-blobs
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
```

## Tests to Run

```bash
# Blob storage tests
pytest packages/civic/tests/test_storage_protocols.py::TestR2Backend -v

# Source cache tests (to be created)
pytest packages/civic-extraction/tests/test_source_cache.py -v

# Smoke tests
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] SourceCache class with get/put operations
- [ ] ProudCitySource uses cache when provided
- [ ] Cache key format: `source-cache/{url_hash}.{ext}`
- [ ] TTL metadata stored with cached content
- [ ] Second pipeline run is significantly faster (cached)
- [ ] Existing tests pass

## Related P1 Items (After P0 Complete)

1. `e2e_fresh_ingestion` - Full E2E data pull from scratch with cloud storage
2. `assemblyai_transcript_storage` - Store transcripts in Postgres, audio in R2
