# Recommended: State Legislative Client

**Priority:** P0 (state_legislative_client)
**Area:** multi_scale_participation
**Date:** 2026-03-20

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session completed `vertical_query_tier_tuning` — parent jurisdictions now have level-aware tier weights: county 0.9, state 0.7, federal 0.5 (was all 1.0). `get_jurisdiction_tier()` returns `parent_county`/`parent_state`/`parent_federal` instead of generic `parent`. The multi-scale stack is functionally complete at the query layer, but **state-california has zero legislation rows** in the DB. County, city, and federal all have data. State is the gap.

## What Needs to Be Done

Build a California legislature data client that ingests:
1. **Committee hearing schedules** — when bills are heard, which committee
2. **Bill status with vote dates** — passage/failure, vote counts
3. **Public comment windows** — testimony opportunities (the participation data LegiScan lacks)

The existing `LegiScanClient` (`clients/legiscan.py`) already fetches bill text/status from the LegiScan API, but it doesn't provide participation-oriented data (hearings, comment windows, testimony). The new client targets `leginfo.legislature.ca.gov` which has this structured data for California specifically.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/clients/legiscan.py` — Existing bill discovery client (LegiScan API). Good pattern reference, but covers different data.
- `packages/civicos-extraction/src/civicos_extraction/clients/federal_register.py` — Best pattern reference: API client with throttling, pagination, retry logic.
- `packages/civicos-extraction/src/civicos_extraction/clients/base.py` — `HealthStatus` and `ValidationResult` types for standardized health checks.
- `packages/civicos/src/civicos/storage/backend.py:1085` — `store_legislation()` method: takes `state`, `bills: List[Dict]`, `topic`, `as_of`. Uses upsert on `(bill_id, state)`.
- `packages/civicos-extraction/src/civicos_extraction/legislative/legislative_discovery.py` — Existing discovery pipeline (LegiScan + LLM filtering). May need extension for CA leginfo data.
- `config/registry.json:19` — `state-california` jurisdiction entry (parent: `country-united-states`)
- `scripts/modal_ingest.py` — Where ingestion functions are registered for Modal. New client needs a Modal function.

## Data Source: leginfo.legislature.ca.gov

The CA Legislature site has structured data but **no official API**. Approach options:
1. **Open States API** (openstates.org) — Free API with CA bill data, hearing schedules, votes. May be sufficient and cleaner than scraping.
2. **Direct scraping** with Playwright — `leginfo.legislature.ca.gov` has structured HTML. The site is NOT Cloudflare-protected (simpler than some other sources). See `memory/feedback_browser_automation.md` for scraping guidance.
3. **Hybrid** — Open States for bill metadata + direct scraping for hearing schedules and comment windows not in Open States.

Recommendation: Start with Open States API to assess coverage, fall back to scraping only for participation data gaps.

## Storage Schema

The `store_legislation()` method expects bills as dicts. Check existing LegiScan bills for field names:
```python
# From legiscan.py search_bills() return format:
{
    "bill_id": str,        # e.g., "CA-AB1234"
    "bill_number": str,    # e.g., "AB 1234"
    "title": str,
    "description": str,
    "state": str,          # "CA"
    "status": str,         # e.g., "Introduced", "Passed Assembly"
    "status_date": str,    # ISO date
    "url": str,
    "last_action": str,
    "last_action_date": str,
}
```

For participation data, the legislation table may need new columns (e.g., `next_hearing_date`, `comment_deadline`). Check `docs/internal/storage-schema.md` and the Postgres schema.

## Suggested Approach

1. **Research Open States API** — Check coverage for CA committee hearings and vote data. Docs at `https://v3.openstates.org/docs`. Free tier may suffice.
2. **Build `ca_legislature.py` client** — Follow `federal_register.py` pattern: session-based, throttled, paginated. Place in `packages/civicos-extraction/src/civicos_extraction/clients/`.
3. **Ingest initial data** — Fetch current session bills (2025-2026), committee hearing schedules, recent votes.
4. **Store via `store_legislation()`** — Map API response to the bill dict format. Jurisdiction: `state-california`, state: `CA`.
5. **Add Modal function** — Register in `scripts/modal_ingest.py` for scheduled ingestion.
6. **Verify tier weighting** — Run a cross-jurisdiction search with `include_parents=True` from `city-san-rafael` and confirm state results now appear with 0.7 weight.

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
# Cross-jurisdiction (verifies state data flows through)
pytest packages/civicos-services/tests/test_query_v2.py -q --override-ini="addopts=" -k "jurisdiction or tier"
```

## Success Criteria

- [ ] `ca_legislature.py` client fetches CA bill data (hearing schedules, votes, status)
- [ ] `store_legislation()` populated for `state-california` (non-zero count)
- [ ] Data includes participation-oriented fields (hearing dates, comment windows)
- [ ] Modal function registered for scheduled ingestion
- [ ] Cross-jurisdiction search surfaces state legislation with 0.7 tier weight

## Notes

- This is estimated at 2-3 sessions. Session 1 should focus on API research + initial client skeleton.
- LegiScan API key is in `.env` (`LEGISCAN_API_KEY`). Open States may need a separate key.
- The `state_server_deployment` item (P3) depends on this data being available.
