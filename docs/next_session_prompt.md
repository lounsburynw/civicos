# Recommended: marin_registrar_scraper

**Priority:** P0
**Area:** data_readiness > election_data
**Date:** 2026-01-08

> Local election data is a gap. Google Civic API has limited coverage for city-level races (mayor, city council, local ballot measures). This task fills that gap.

## Context

Previous session completed `election_vector_embeddings` - elections are now indexed and searchable via pgvector. However, we only have 4 national special elections in the database. **Local San Rafael elections are missing.**

Data source status:
- **Google Civic API**: Limited local coverage, good for federal/state
- **Democracy Works API**: Comprehensive (school board to federal), but **pricing pending** - awaiting email response
- **Marin County Registrar**: Authoritative local source, no known API

**Strategy**: First investigate if Marin County has any APIs or data feeds. Only resort to Playwright scraping if no structured data is available.

## Key Files

- `packages/civic-extraction/src/civic_extraction/clients/` - Client implementations
- `packages/civic-extraction/src/civic_extraction/clients/google_civic.py` - Pattern to follow
- `packages/civic/src/civic/storage/postgres_backend.py:6102-6448` - Election storage methods
- `docs/critical/ELECTION_INTEGRATION.md` - Architecture reference

## Suggested Approach

1. **Investigate Marin County data sources** (before writing code)
   - Check https://www.marincounty.gov/departments/elections for:
     - XML/JSON feeds
     - RSS feeds for election updates
     - iCal calendar exports
     - Open data portal links
   - Search for Marin County open data portals
   - Check if they use a vendor (e.g., Scytl, ES&S) that has an API

2. **Check alternative data providers**
   - Ballotpedia API (they have local measure data)
   - Vote.org or similar civic tech APIs
   - CA Secretary of State feeds

3. **If API found**: Implement client following `google_civic.py` pattern

4. **If scraping required**: Use Playwright (site returns 403 to requests)
   - Target: https://www.marincounty.gov/departments/elections
   - Extract: upcoming elections, local measures, city races, deadlines

## Data We Need

| Data Type | Priority | Source |
|-----------|----------|--------|
| San Rafael city council races | High | Marin Registrar |
| Local ballot measures (Measure A, B, etc.) | High | Marin Registrar |
| School board elections | Medium | Marin Registrar |
| Voter registration deadlines | Medium | Already have via Google |

## Tests to Run

```bash
# Existing election tests
pytest packages/civic/tests/test_election_api.py -v

# After implementation
pytest packages/civic-extraction/tests/ -k marin -v
```

## Success Criteria

- [ ] Identify best data source for Marin local elections
- [ ] Implement client (API or scraper)
- [ ] Ingest San Rafael local election data
- [ ] Local elections appear in `whats_next(include_elections=True)`
- [ ] Update pilot.json status to "ready"

## Blocked Item

**`democracy_works_api`** (P1, blocked): Waiting on pricing response. If affordable (<$50/mo), may replace need for Marin scraper entirely since it covers "jurisdictions >5k population" including school board races.

## Related Items

- `election_discovery_cron` (P1) - Automation for election ingestion
- `election_vector_embeddings` (ready) - Already complete
