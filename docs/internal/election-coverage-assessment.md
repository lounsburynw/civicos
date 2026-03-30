# Election Coverage Assessment

**Date:** 2026-03-30
**Status:** Living document
**Scope:** Current state of election/officials data coverage across California jurisdictions in CivicOS

Builds on [election-data-research.md](election-data-research.md) (source evaluation) and [election-onboarding-spec.md](election-onboarding-spec.md) (onboarding flow). This document focuses on coverage gaps and the work required to fill them.

## Coverage Map

California jurisdictions fall into three tiers based on election data availability.

### Tier A — Civera Counties (4 of 58)

Full historical local race data via Civera ElectionStats GraphQL API. Includes city council, mayor, local ballot measures, precinct breakdowns.

| County | Endpoint | Elections | Years | Cities Covered |
|--------|----------|-----------|-------|---------------|
| Marin | `pastelections.marincounty.gov` | 46 | 2010-2025 | San Rafael, Mill Valley, San Anselmo, + all Marin cities |
| Sonoma | `electionstats.sonomacounty.ca.gov` | 43 | 2009-2024 | All Sonoma cities |
| Yolo | `electionstats.elections.yolocounty.gov` | 52 | 1997-2025 | All Yolo cities |
| San Joaquin | `electionstats.sjgov.org` | 2 | 2024 | All San Joaquin cities (thin coverage) |

Registry: `data/extraction/civera_instances.json`
Discovery: `scripts/probe_civera_counties.py` (probes all 58 counties)

### Tier B — Non-Civera Counties (54 of 58)

Only statewide + district races from the CA SOS API, for the current/most-recent election only. No local race data. No historical results.

A resident of a Tier B city (e.g., Oakland, Sacramento, Los Angeles) can see:
- Who won the US House / State Senate / State Assembly race in their district
- State ballot propositions and their outcomes
- County-level vote totals for state races

They **cannot** see:
- City council election results
- Mayoral races
- Local ballot measures
- Any historical election data (prior primary/general results)

### Tier C — Unconfigured Jurisdictions (24 extraction configs)

Extraction configs exist but have no `election_sources` field. Zero election data flows.

**With election_sources (7):**
city-san-rafael, city-mill-valley, city-san-anselmo, county-marin, county-sonoma, county-yolo, state-california

**Without election_sources (24):**
city-berkeley, city-sacramento, city-national-city, county-alameda, county-travis, college-marin, school-kentfield, school-larkspur-corte-madera, school-marin-county-oe, school-mill-valley-sd, school-miller-creek, school-novato, school-reed-union, school-ross-valley, school-sausalito-marin-city, school-tamalpais, plus test/supplementary configs

Most of these are CA jurisdictions that would auto-detect `ca_sos_results` + district info if `detect_election_sources()` were run against them.

## Data Sources Inventory

### Election Results

| Source | Endpoint | Auth | Scope | Capabilities | Limitations |
|--------|----------|------|-------|-------------|-------------|
| CA SOS Results | `api.sos.ca.gov` | None | All CA statewide/district races | Current results, county breakdowns, ballot measures, reporting status | **Only serves one election at a time.** Data overwritten when new election loads. No historical access. No local races. |
| Civera ElectionStats | Per-county GraphQL | None | 4 CA counties | Historical results (1997-2025), local races, precinct breakdowns, candidates with vote counts | Only 4 of 58 counties. Each county has different depth. |
| CA SOS Ballot Preview | SOS CDN (PDF) | None | All CA statewide/district candidates | Pre-election certified candidate data: name, party, designation, contact, incumbent flag | State/district races only. One-shot per election cycle. No vote counts. |

### Representatives & Officials

| Source | Endpoint | Auth | Scope | Capabilities | Limitations |
|--------|----------|------|-------|-------------|-------------|
| Congress.gov | `api.congress.gov/v3` | API key (free) | National | Federal legislators, terms, committees, votes | Federal only |
| LegiScan | `api.legiscan.com` | API key | National | State legislators, bill tracking | Rate-limited |
| Census Geocoder | `geocoding.geo.census.gov` | None | National | Lat/lng to congressional + state legislative districts | District detection only |
| Curated local | Manual | N/A | Pilot cities | City council, county supervisors | Manual maintenance, does not scale |

### Not Recommended (from election-data-research.md)

Ballotpedia, BallotReady, Democracy Works, Open States (VC-acquired) — all have opaque/gated pricing or reliability issues. Prefer government primary sources.

## Infrastructure Status

| Component | Built? | Wired to Pipeline? | Notes |
|-----------|--------|-------------------|-------|
| `CaliforniaElectionProvider` | Yes | Onboard detection only | Returns source config, does not fetch data |
| `TexasElectionProvider` | Yes | Onboard detection only | Same pattern as CA |
| `CASOSResultsClient` | Yes | Monthly cron | Fetches current election only |
| `CiveraElectionStatsClient` | Yes | Monthly cron | Historical local race data |
| `CASOSBallotPreviewClient` | Yes | Monthly cron | Pre-election candidate PDFs |
| Election storage protocol | Yes | Yes | `store_elections()`, `store_election_contests()`, `store_elected_officials()`, `store_election_deadlines()` |
| `generate_deadlines()` | Yes | **No** | Exists in `deadlines.py`, called only by `seed_election_calendar.py` (manual, 3 pilot cities) |
| `derive_officials_from_contests()` | Yes | **No** | Modal function exists (`modal_ingest.py:3973`), not called by monthly cron |
| Election source detection in onboard | Yes | Partial | Detects and writes config. Does NOT trigger data fetch. |
| `scheduled_election_refresh()` | Yes | Monthly cron (1st, 3 AM UTC) | Iterates configured jurisdictions, dispatches to providers |

## Gap Analysis

### Priority 1 — CA Depth

**SOS data is ephemeral.** The CA SOS API overwrites data when a new election loads. If the monthly cron runs on the 1st and the SOS loads new data on the 3rd, the previous election's results are gone. No archival mechanism exists. This affects all 58 CA counties.

**54 counties have no local race data.** City council, mayoral, and local ballot measure results are published by county registrars, not the state SOS. Only 4 counties have Civera. The other 54 use diverse platforms (Clarity Elections/Scytl, custom websites, PDF-only). No research exists on which platform covers the most counties.

**24 extraction configs lack election_sources.** Berkeley, Sacramento, all 10 school districts, county-alameda, and others have zero election configuration. Running `detect_election_sources()` against them would add at minimum CA SOS statewide coverage.

**Election deadlines not populated.** `generate_deadlines()` and `store_election_deadlines()` exist and work. But `scheduled_election_refresh()` never calls them. Only the 3 pilot jurisdictions have deadlines (from a manual seed script run).

### Priority 2 — Automation

**New cities don't get election data on onboard.** `detect_election_sources()` runs during onboarding and writes the config, but no election clients are invoked. The city waits up to 30 days for the next monthly cron.

**Officials not derived after election ingest.** `derive_elected_officials()` exists as a Modal function but `scheduled_election_refresh()` does not call it. Officials are only updated when someone runs the function manually.

**Cron enrollment is implicit.** `scheduled_election_refresh()` scans `data/extraction/*.json` for configs with `election_sources`. This works, but it's unverified whether school districts, colleges, and county configs are correctly included.

### Priority 3 — Ingestion Strategy

**Monthly blind cron is too coarse.** Election results become available on election night. A monthly schedule cannot capture this. The CA June primary and November general are known dates — the cron should fetch daily around them.

**SOS overwrite risk between fetches.** If a new election loads between monthly fetches, the old data is lost permanently. Daily fetching around election dates plus archival would mitigate this.

**Ballot preview runs monthly but is one-shot.** Certified candidate PDFs are published ~90 days before election day. Monthly fetching outside this window is wasted work.

## Related Documents

- [election-data-research.md](election-data-research.md) — Source evaluation and recommendations
- [election-onboarding-spec.md](election-onboarding-spec.md) — Onboarding flow for election data
- [federal-data-plan.md](federal-data-plan.md) — Federal data pipeline (Congress.gov, Federal Register)
