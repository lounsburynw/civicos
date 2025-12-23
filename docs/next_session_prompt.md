# Recommended: E2E Data Ingestion Verification

**Priority:** P0 (IMMEDIATE)
**Area:** pilot_validation > data_pipeline
**Date:** 2025-12-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 356 completed `research_abstraction` - extracted `BaseResearcher` abstract class from housing-specific code, enabling extensibility for new topic researchers.

**This task:** Before Jan 2026 pilot, verify the entire data ingestion pipeline works end-to-end, including the status dashboard. This is a manual verification task to ensure all components integrate correctly.

## Data Pipeline Components

1. **Pipeline** (`packages/civic-extraction/src/civic_extraction/pipeline.py`)
   - 4-stage ETL: discover → ingest → store → index
   - Checkpoint/resume support
   - Validation on ingest (added Session 349)

2. **Platform Sources** (`packages/civic-extraction/src/civic_extraction/sources/`)
   - Legistar (REST API)
   - CivicClerk (OData v4)
   - ProudCity (web scraping)

3. **Storage** (`packages/civic/src/civic/_internal/storage/`)
   - ChromaDB vector store
   - JSON file storage

4. **Status Dashboard** (`scripts/city_status_dashboard.py`)
   - Reads from `data/city_status_registry.json`
   - Shows city health: healthy/degraded/broken

## Suggested Verification Steps

1. **Check current registry status**
   ```bash
   python scripts/city_status_dashboard.py
   python scripts/city_status_dashboard.py --broken
   ```

2. **Run pipeline for a test city (San Rafael)**
   ```bash
   source civic-env/bin/activate
   civic-extract pipeline run san-rafael --stages discover,ingest
   ```

3. **Verify data persisted**
   ```bash
   ls -la data/meetings/san-rafael/
   cat data/meetings/san-rafael/manifest.json
   ```

4. **Check indexing**
   ```bash
   civic-extract pipeline run san-rafael --stages index
   ```

5. **Verify via Civic API**
   ```python
   from civic import Civic
   c = Civic("san-rafael")
   print(c.whats_next())
   ```

6. **Update and check dashboard**
   ```bash
   python scripts/update_city_registry.py
   python scripts/city_status_dashboard.py san-rafael
   ```

## Key Files

- `packages/civic-extraction/src/civic_extraction/pipeline.py` - Main pipeline
- `packages/civic-extraction/src/civic_extraction/manifest.py` - Manifest tracking
- `scripts/city_status_dashboard.py` - Status dashboard
- `scripts/update_city_registry.py` - Registry updater
- `data/city_status_registry.json` - City health data

## Success Criteria

- [ ] Pipeline runs without errors for at least one city
- [ ] All 4 stages complete: discover → ingest → store → index
- [ ] Meetings appear in ChromaDB
- [ ] `Civic.whats_next()` returns valid data
- [ ] Status dashboard shows correct city health
- [ ] Document any issues found for follow-up

## Pilot Progress

- 163/176 items ready (92.6%)
- 13 items remaining
- P0: e2e_data_ingestion_verification (this item)
