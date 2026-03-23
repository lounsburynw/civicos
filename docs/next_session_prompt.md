# Recommended: Legistar Client

**Priority:** P0 (legistar_client)
**Area:** federation_testbed
**Date:** 2026-03-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Turnkey onboarding was tested end-to-end with Sacramento. The system successfully detected Sacramento's meeting platform (Legistar, 35 bodies), generated the extraction config, loaded municipal code (5,871 sections), and indexed vectors (9,224 embeddings). Six pipeline issues were fixed along the way.

**The one remaining gap: `fetch_meetings` doesn't support Legistar source type.** Sacramento has a complete extraction config but zero meetings because the ingestion pipeline only handles `proudcity` and `granicus` today.

## What Exists Now

- **Extraction config** (`data/extraction/city-sacramento.json`) — Legistar source, 35 meeting bodies discovered
- **Jurisdiction YAML** (`data/jurisdictions/city-sacramento.yaml`) — Full config with data sources, ingestion tiers, refresh policies
- **Municipal code** — 5,871 sections in Postgres, 9,224 vector embeddings
- **SUPPORTED_MEETING_SOURCES** registry in `civicos_extraction/clients/__init__.py` — shared constant used by onboard.py and modal_ingest.py
- **LegistarClient** already exists (`civicos_extraction/clients/legistar.py`) — for API discovery, but not wired into the fetch pipeline

## Key Files

| File | Purpose |
|------|---------|
| `scripts/modal_ingest.py` | `fetch_meetings()` — add `elif source_type == "legistar":` branch |
| `packages/civicos-extraction/src/civicos_extraction/clients/legistar.py` | Existing Legistar API client |
| `packages/civicos-extraction/src/civicos_extraction/clients/__init__.py` | Add "legistar" to `SUPPORTED_MEETING_SOURCES` |
| `data/extraction/city-sacramento.json` | Sacramento's Legistar config (base_url, 35 body IDs) |

## Suggested Approach

1. **Extend LegistarClient** — add `get_meetings(days_ahead, days_past)` method that queries the Legistar API for events/meetings within the date range
2. **Wire into fetch_meetings** — add `elif source_type == "legistar":` branch in `modal_ingest.py`
3. **Update registry** — add `"legistar"` to `SUPPORTED_MEETING_SOURCES`
4. **Run turnkey onboard for Sacramento** — verify meetings are fetched, chunks extracted, agenda items parsed
5. **Verify data quality** — compare ratios against San Rafael baseline

## Legistar API Reference

Base URL: `https://webapi.legistar.com/v1/{client}`

Key endpoints:
- `GET /Events` — meetings/events (filterable by date)
- `GET /EventItems/{eventId}` — agenda items for a meeting
- `GET /MatterAttachments/{matterId}` — attached PDFs
- `GET /Bodies` — meeting bodies (committees, councils)

Sacramento client name: `sacramento`

## Tests to Run

```bash
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Sacramento meetings fetched from Legistar API (30+ days of data)
- [ ] Chunks extracted from meeting attachments
- [ ] Agenda items parsed
- [ ] Vector embeddings generated for all corpora
- [ ] `what_happened("housing", jurisdiction="city-sacramento")` returns results
- [ ] San Rafael data unaffected
