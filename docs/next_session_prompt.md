# Recommended: r2_source_caching

**Priority:** P0
**Area:** pipeline_automation > cloud_integration
**Date:** 2025-12-27

> This is recommended context from Session 377. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 377 completed `pipeline_cloud_storage` and identified **9 remaining items** needed for complete E2E cloud ETL. The `r2_source_caching` item is P0 because caching scraped content will speed up development iterations for all subsequent items.

## E2E Cloud ETL Roadmap (10 items)

| # | Item | Status | Data Flow |
|---|------|--------|-----------|
| 1 | `pipeline_cloud_storage` | ✅ Done | Meetings → Postgres |
| 2 | **`r2_source_caching`** | **P0** | Cache HTML/PDFs in R2 |
| 3 | `youtube_cloud_storage` | P1 | Video metadata → Postgres |
| 4 | `audio_cloud_storage` | P1 | Audio files → R2 |
| 5 | `assemblyai_transcript_storage` | P1 | Transcripts → Postgres |
| 6 | `decision_extraction_pipeline` | P1 | Minutes PDF → Decisions |
| 7 | `chunks_cloud_storage` | P1 | PDF chunks → Postgres |
| 8 | `seeclickfix_cloud_storage` | P1 | Issues → Postgres |
| 9 | `vector_indexing_cloud` | P1 | All data → pgvector |
| 10 | `e2e_fresh_ingestion` | P1 | Full verification |

## Current Cloud Status

| Data Type | Backend | Count |
|-----------|---------|-------|
| Meetings | PostgresBackend (Supabase) | 46 |
| Decisions | PostgresBackend | 0 (cleared, await E2E pipeline) |
| Vectors | PgVectorBackend (Supabase) | 0 (cleared, await E2E pipeline) |
| Blobs | R2Backend | Ready, not used yet |

## Recommended Task

Add a caching layer that stores raw scraped content in R2:
- Cache HTML pages with URL hash as key
- Cache downloaded PDFs before parsing
- TTL-based expiration (24h for meeting pages)
- Speeds up re-runs during development of other ETL items

## Key Files

- `packages/civic-extraction/src/civic_extraction/clients/proudcity.py` - Scraper to add caching
- `packages/civic/src/civic/storage/blob.py:144-280` - R2Backend (ready)
- `packages/civic/src/civic/storage/__init__.py:60` - `get_blob_storage()` factory

## Suggested Approach

1. **Create SourceCache class** in `civic_extraction/cache.py`:
   ```python
   class SourceCache:
       def __init__(self, blob_storage: BlobStorage):
           self.storage = blob_storage

       def cache_key(self, url: str) -> str:
           return f"source-cache/{hashlib.sha256(url.encode()).hexdigest()[:16]}"

       def get(self, url: str) -> Optional[bytes]:
           key = self.cache_key(url)
           if self.storage.exists(key):
               metadata = self.storage.get_metadata(key)
               if not self._is_expired(metadata):
                   return self.storage.download(key)
           return None

       def put(self, url: str, content: bytes, ttl_hours: int = 24):
           key = self.cache_key(url)
           self.storage.upload(key, content, metadata={"url": url, "expires": ...})
   ```

2. **Integrate with ProudCitySource**:
   - Add `cache: Optional[SourceCache]` parameter
   - Check cache before HTTP requests
   - Store responses after successful fetches

3. **CLI integration** in `discover.py`:
   ```python
   from civic.storage import get_blob_storage
   from civic_extraction.cache import SourceCache

   blob = get_blob_storage()  # Returns R2Backend if BLOB_STORAGE_URL set
   cache = SourceCache(blob) if blob else None
   source = ProudCitySource(jurisdiction_id, cache=cache)
   ```

## Tests to Run

```bash
# Blob storage tests
pytest packages/civic/tests/test_storage_protocols.py::TestR2Backend -v

# After creating cache tests
pytest packages/civic-extraction/tests/test_source_cache.py -v

# Full smoke tests
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] SourceCache class with get/put/is_expired operations
- [ ] ProudCitySource uses cache when provided
- [ ] Cache key format: `source-cache/{url_hash}`
- [ ] TTL metadata stored with cached content
- [ ] Second pipeline run is faster (cache hits logged)
- [ ] Existing tests pass

## Why This First?

Caching raw content accelerates development of all remaining items:
- `youtube_cloud_storage` - won't re-scrape video IDs
- `decision_extraction_pipeline` - won't re-download PDFs
- `chunks_cloud_storage` - same PDF caching benefit
- Testing iterations become much faster
