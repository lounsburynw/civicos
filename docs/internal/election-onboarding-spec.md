# Spec: Election & School Board Onboarding Integration

**Date:** 2026-03-26
**Status:** Draft
**Scope:** 4 items to close the gap between election/school-board extraction clients and the onboarding pipeline

## Problem

Election data and school board jurisdictions are handled through separate, manual pipelines that don't connect to the standard `onboard.py` flow. Specifically:

1. **CA SOS client exists but isn't wired** — `ca_sos_results.py` has 8 query methods and 3 storage mappers, but no Modal function or cron integration
2. **School districts require manual URL hunting** — onboarding a Simbli or BoardDocs school district requires manually finding the board URL, looking up the `simbli_district_id`, and hand-creating configs
3. **Election sources aren't in extraction configs** — `scheduled_election_refresh()` runs Google Civic for every jurisdiction but doesn't know about Marin Registrar, CA SOS, or jurisdiction-specific election parameters
4. **Onboarding doesn't detect or configure elections** — `onboard.py` discovers meetings, YouTube, and 311 sources but ignores election data entirely

## Items

### 1. `ca_sos_pipeline_wiring`

**Goal:** Wire `CASOSResultsClient` into Modal ingestion and monthly cron.

**What exists:**
- `ca_sos_results.py`: `get_all_results()`, `extract_ca_sos_results_to_storage()`, county breakdowns, ballot measures
- `fetch_ca_sos_election_results()` Modal function already exists in `modal_ingest.py:3678` — but it's NOT called by `scheduled_election_refresh()`
- Storage protocol (`ElectionStorageProtocol`) and mappers (`ca_sos_results_to_election`, `ca_sos_race_to_contest`, `ca_sos_measure_to_contest`) are implemented

**What's needed:**
1. Add CA SOS to `scheduled_election_refresh()` — call `fetch_ca_sos_election_results.local()` for jurisdictions that have `ca_sos_results` in their `election_sources` config
2. Default: run for `state-california` (statewide races + ballot measures). If a jurisdiction specifies `county` and `districts`, fetch breakdowns too
3. Wire into GitHub Actions cron (currently only triggers `scheduled_election_refresh`, which will now include CA SOS)

**Config integration:**
```json
// data/extraction/city-san-rafael.json
{
  "election_sources": {
    "google_civic": true,
    "ca_sos_results": {
      "county": "marin",
      "districts": {"us-rep": [2], "state-assembly": [12], "state-senate": [2]}
    }
  }
}
```

**Test approach:**
```bash
# Dry run to verify
modal run scripts/modal_ingest.py::fetch_ca_sos_election_results --jurisdiction state-california --county marin --dry-run
```

**Files:**
- `scripts/modal_ingest.py` — add CA SOS dispatch to `scheduled_election_refresh()`
- `data/extraction/city-san-rafael.json` — add `election_sources` field
- `data/extraction/state-california.json` — create if not exists, with CA SOS config

---

### 2. `election_source_config`

**Goal:** Add `election_sources` field to extraction configs so the monthly cron knows which election APIs to query per jurisdiction.

**Current state:** `scheduled_election_refresh()` calls `fetch_elections()` (Google Civic) for every jurisdiction in `data/extraction/*.json` with no filtering. Marin Registrar and CA SOS are only runnable manually.

**Design:**

Add optional `election_sources` to extraction config schema:

```json
{
  "source_id": "proudcity-city-san-rafael",
  "source_type": "proudcity",
  "jurisdiction_id": "city-san-rafael",
  "base_url": "...",
  "archives": { ... },
  "issue_source": "seeclickfix",
  "election_sources": {
    "google_civic": true,
    "marin_registrar_results": {
      "from_year": 2010,
      "division_filter": "City of San Rafael"
    },
    "ca_sos_results": {
      "county": "marin",
      "districts": {"us-rep": [2], "state-assembly": [12], "state-senate": [2]}
    }
  }
}
```

Rules:
- `election_sources` is optional. If absent, `scheduled_election_refresh()` falls back to current behavior (Google Civic only)
- Each provider key maps to `true` (use defaults) or a config dict with provider-specific params
- `scheduled_election_refresh()` reads config, dispatches to the appropriate `fetch_*` function for each enabled provider
- School districts default to `{"google_civic": true}` unless Marin-specific sources apply

**Implementation:**
1. Update `scheduled_election_refresh()` to read `election_sources` from each jurisdiction's config
2. Dispatch to `fetch_marin_election_results.local()` and `fetch_ca_sos_election_results.local()` when configured
3. Add `election_sources` to existing configs for San Rafael, Marin County, and state-california
4. Document the field in extraction config schema

**Files:**
- `scripts/modal_ingest.py` — update `scheduled_election_refresh()`
- `data/extraction/city-san-rafael.json` — add election_sources
- `data/extraction/county-marin.json` — add election_sources (if exists)
- `docs/public/data-dictionary.md` — document election_sources field

---

### 3. `school_district_lookup`

**Goal:** Enable onboarding school districts by name instead of requiring manual URL lookup.

**Current flow:** Must manually find a Simbli/BoardDocs URL, then:
```bash
onboard.py --url "https://simbli.eboardsolutions.com/...?S=36030351" --jurisdiction school-novato --level district
```

**Proposed flow:**
```bash
onboard.py --city "Novato" --state CA --level school
# or
onboard.py --county "Marin" --state CA --level school  # batch: all districts in county
```

**Approach:** Static lookup table + discovery fallback.

1. **Static lookup table** (`data/school_districts.json`):
   ```json
   {
     "california": {
       "marin": [
         {
           "name": "Novato Unified School District",
           "jurisdiction_id": "school-novato",
           "platform": "simbli",
           "simbli_district_id": "36030351",
           "board_url": "https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030351"
         },
         {
           "name": "Ross Valley School District",
           "jurisdiction_id": "school-ross-valley",
           "platform": "boarddocs",
           "board_url": "https://go.boarddocs.com/ca/rvsd/Board.nsf"
         }
       ]
     }
   }
   ```

2. **Lookup logic in `onboard.py`:**
   - `--level school --city "Novato"` → search school_districts.json by name match
   - `--level school --county "Marin"` → return all districts in Marin County
   - If no match in lookup table, fall back to platform discovery (probe BoardDocs, Simbli URLs)

3. **Seed data:** Populate Marin County districts from existing `data/extraction/school-*.json` configs (we already have 8 districts onboarded)

4. **Future:** Can extend with CDE CALPADS API scraping to auto-populate other counties

**Files:**
- `data/school_districts.json` — new lookup table
- `packages/civicos-extraction/src/civicos_extraction/onboard.py` — add school lookup logic
- `scripts/onboard.py` — `--level school` dispatches to lookup

---

### 4. `onboard_election_detection`

**Goal:** During city/county onboarding, auto-detect available election data sources and populate `election_sources` in the extraction config.

**Current state:** `onboard.py` discovers meetings, YouTube channels, and 311 providers but ignores elections entirely.

**Proposed detection logic:**

```python
def detect_election_sources(jurisdiction_id: str, state: str, county: str) -> dict:
    """Detect available election data sources for a jurisdiction."""
    sources = {}

    # Google Civic — always available for US jurisdictions
    sources["google_civic"] = True

    # CA SOS — available for all California jurisdictions
    if state.upper() == "CA":
        sources["ca_sos_results"] = {"county": county.lower()}
        # Auto-detect legislative districts from geocoded address
        # (future: use Census geocoder for district assignment)

    # Marin Registrar — available for Marin County jurisdictions
    if county.lower() == "marin":
        sources["marin_registrar_results"] = {
            "from_year": 2010,
            "division_filter": _infer_division_name(jurisdiction_id)
        }

    return sources
```

**Integration point:** After geocoding (Step 3.5 in onboard flow), before saving extraction config:

```python
# In onboard.py, after geocoding
if county_name:
    election_sources = detect_election_sources(jurisdiction_id, state, county_name)
    config["election_sources"] = election_sources
```

**Division filter inference:** Map jurisdiction_id to Marin Registrar division name:
- `city-san-rafael` → `"City of San Rafael"`
- `city-mill-valley` → `"City of Mill Valley"`
- `school-novato` → `"Novato Unified School District"`

**Files:**
- `packages/civicos-extraction/src/civicos_extraction/onboard.py` — add `detect_election_sources()`
- `packages/civicos-extraction/src/civicos_extraction/election_detection.py` — new module (or inline in onboard.py)

---

## Execution Order

```
1. election_source_config     — Define the schema, update scheduled_election_refresh()
2. ca_sos_pipeline_wiring     — Wire CA SOS into the cron (depends on #1)
3. school_district_lookup      — Static lookup table for school districts
4. onboard_election_detection  — Auto-detect election sources during onboarding
```

Items 1-2 are tightly coupled (config schema must exist before CA SOS can read it). Items 3-4 are independent of each other but both improve onboarding ergonomics.

## Success Criteria

- [ ] `scheduled_election_refresh()` reads `election_sources` from configs and dispatches to all 3 providers
- [ ] CA SOS results flow into Postgres monthly for configured jurisdictions
- [ ] `onboard.py --city "Novato" --state CA --level school` finds the Simbli URL automatically
- [ ] `onboard.py --county "Marin" --state CA --level school` onboards all Marin school districts
- [ ] New city onboarding auto-populates `election_sources` in extraction config
- [ ] Marin Registrar results include division-filtered data for each jurisdiction
