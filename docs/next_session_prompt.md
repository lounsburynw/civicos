# Recommended: Election Calendar

**Priority:** P0 (election_calendar)
**Area:** ballot_awareness
**Date:** 2026-03-28

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Previous session completed `congress_gov_federal_officials` — `RepresentativesClient` is now config-driven (reads state/districts from `data/extraction/*.json`), federal officials (Schiff, Padilla, Huffman) are stored for all 3 pilot jurisdictions, and `explore/representatives` shows federal + local officials together. Also cleaned up 456 stale LegiScan entries from city-san-rafael.

The gap: we know *who* represents you, but not *what's on your ballot*. The June 2 CA primary is **66 days away**. The election calendar is the data layer that tells you which seats are up when — it powers `whats_on_my_ballot`.

## What Needs to Be Done

Build a data model and seed data for **election cycle awareness**: given an office type + district, when is the next election?

Key insight from launch.json notes: **federal and state cycles are deterministic** (can be computed from office type + district number + year). Local cycles require registrar data.

### Deterministic Cycles (compute, don't scrape)
- **US House**: Every 2 years (even years), all seats
- **US Senate**: 6-year terms, staggered into 3 classes. CA Class I (Padilla) up 2030, Class III (Schiff) up 2028
- **CA Governor**: Every 4 years (2026, 2030...)
- **CA Assembly**: Every 2 years (all 80 seats)
- **CA State Senate**: 4-year terms, odd districts in 2026/2030, even districts in 2028/2032
- **Statewide offices** (controller, treasurer, AG, etc.): Same cycle as governor

### Non-deterministic (need registrar data)
- City council (staggered 4-year, city-specific)
- County supervisor (staggered 4-year, county-specific)
- School board (staggered, district-specific)
- Special districts

## Key Files

- `packages/civicos/src/civicos/_internal/elections/__init__.py:121` — `Election` dataclass with `election_date`, `election_type`, `contests`, `deadlines`
- `packages/civicos/src/civicos/storage/protocols/elections.py:13` — `ElectionStorage` protocol with `store_elections()`, `get_elections()`
- `data/extraction/city-san-rafael.json:35` — `ca_sos_ballot_preview` config with `election_slug: "2026-primary"`, `election_date: "2026-06-02"`, per-race districts
- `packages/civicos-extraction/src/civicos_extraction/clients/ca_sos_ballot_preview.py` — CA SOS ballot preview client (parses candidate PDFs from SOS CDN)
- `packages/civicos/src/civicos/civicos.py:773` — `whats_next()` already filters elections by date window

## Data Already Available

The extraction config already has the June 2 primary defined:
```json
"ca_sos_ballot_preview": {
  "election_slug": "2026-primary",
  "election_date": "2026-06-02",
  "election_type": "primary",
  "races": {"congress": [2], "state-senate": [2], "assembly": [12], ...}
}
```

Districts are configured: `{"us-rep": [2], "state-assembly": [12], "state-senate": [2]}`.

## Suggested Approach

1. **Build a deterministic cycle resolver** — a pure function `get_next_election(office_type, district, as_of_date) -> date` that computes the next election date for federal/state offices. No scraping needed, just calendar math.

2. **Create election calendar entries** — use the resolver + extraction config to generate `Election` objects for the June 2 primary with the right contests for each jurisdiction.

3. **Store to Postgres** — use `store_elections()` with contests listing which races are on the ballot for each jurisdiction's districts.

4. **Wire into `whats_next()`** — elections should appear in upcoming events when queried. The `civicos.py:773` code already handles elections from storage.

5. **Seed local cycle data** — for city council and school board, the Marin Registrar results may already have historical election dates we can extrapolate from. Check `marin_registrar_results.from_year` in extraction config.

## Tests to Run

```bash
# Election data model tests
pytest packages/civicos/tests/test_elected_officials.py -v --override-ini="addopts="
# Explore endpoint (should still work)
pytest packages/civicos-services/tests/test_query_v2.py -k "explore" -v --override-ini="addopts="
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Deterministic cycle resolver: `get_next_election("us-house", district=2)` -> `2026-11-03`
- [ ] June 2 primary stored as Election with correct contests for pilot jurisdictions
- [ ] `whats_next()` returns the upcoming primary when queried
- [ ] Election has deadlines (registration: ~May 18, early voting, election day)
- [ ] Data model supports both deterministic (computed) and non-deterministic (scraped) cycles
