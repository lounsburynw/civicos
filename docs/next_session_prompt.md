# Recommended: Congress.gov Federal Officials

**Priority:** P0 (congress_gov_federal_officials)
**Area:** representative_lookup
**Date:** 2026-03-28

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Previous session built the full "who represents me?" pipeline: `derive_officials_from_contests()` turns election winners into officials, and `civic.explore what=representatives` surfaces them via API with jurisdiction hierarchy walk. Real data ingested for San Rafael, Mill Valley, San Anselmo — local officials (mayor, council, school board, county supervisor) all working.

The gap: the representatives response shows no federal or state legislators because they aren't stored at the county/state jurisdiction level yet. The `CongressGovClient` already exists with `get_members_by_state()` and `get_members_by_district()`. A storage mapper `representative_to_elected_official()` also exists. This item wires them together with a Modal function.

## What Needs to Be Done

Build a Modal function that:
1. Reads a jurisdiction's `election_sources.ca_sos_results.districts` config (e.g., `{"us-rep": [2], "state-senate": [2], "state-assembly": [12]}`)
2. Calls `CongressGovClient.get_members_by_district()` for each district
3. Maps via `representative_to_elected_official()` to storage format
4. Stores via `storage.store_elected_officials()` under the jurisdiction

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/clients/representatives.py:80` — `CongressGovClient` with `get_members_by_state()`, `get_members_by_district()`
- `packages/civicos-extraction/src/civicos_extraction/clients/representatives.py:1468` — `representative_to_elected_official()` mapper (already exists)
- `packages/civicos-extraction/src/civicos_extraction/clients/representatives.py:1525` — `extract_elected_officials_to_storage()` (already exists, may just need wiring)
- `data/extraction/city-san-rafael.json` — Districts config: `{"us-rep": [2], "state-assembly": [12], "state-senate": [2]}`
- `scripts/modal_ingest.py:1916` — Congressional votes section (nearby, pattern reference)
- `packages/civicos/src/civicos/_internal/elections/derive.py` — The derive function from this session (reference)

## Data Already Available

The extraction config for each jurisdiction already has district numbers (auto-detected during onboarding via Census Bureau API):
- San Rafael: US House District 2, State Assembly 12, State Senate 2
- Mill Valley: Same districts
- San Anselmo: Same districts

The API key is `CONGRESS_GOV_API_KEY` / `FAC_API_KEY` / `DATA_GOV_API_KEY` (all data.gov keys, already in Modal secrets).

## Data Quality Issue to Note

The `city-san-rafael` jurisdiction has 161 officials from a previous LegiScan ingestion that incorrectly stored ALL CA legislators under the city. The new derivation stores under the correct jurisdiction with `candidate_id` links. The old data should be cleaned up (or the explore endpoint should filter to only officials relevant to the jurisdiction's districts). Consider this when testing.

## Suggested Approach

1. Check if `extract_elected_officials_to_storage()` already does what we need (it might — it's already wired)
2. If yes: just add a Modal function that calls it with the right config
3. If no: build a simpler function that reads districts from extraction config and calls `get_members_by_district()` → `representative_to_elected_official()` → `store_elected_officials()`
4. Store federal officials under the city jurisdiction (so they appear in `explore/representatives`)
5. Test the explore endpoint shows federal + local officials together

## Election Sprint Context

The June 2 CA primary is 66 days away. After this item, the time-sensitive items are:
- `election_deadlines_scraping` (registration deadline ~May 18)
- `election_calendar` (powers "what's on my ballot")
- `ballot_measure_content` (measure explanations for voters)

All are P1 with `time_sensitive` flags in launch.json.

## Tests to Run

```bash
# Existing representative tests
pytest packages/civicos-extraction/tests/test_representatives.py -v --override-ini="addopts="
# Elected officials derivation tests (should still pass)
pytest packages/civicos/tests/test_elected_officials.py -v --override-ini="addopts="
# Explore endpoint tests
pytest packages/civicos-services/tests/test_query_v2.py::TestExploreIntegration -v --override-ini="addopts="
```

## Success Criteria

- [ ] Federal officials (US House, US Senate) stored for pilot jurisdictions
- [ ] State officials (Assembly, Senate) stored for pilot jurisdictions
- [ ] `civic.explore what=representatives` shows federal + state + local officials
- [ ] Officials have proper seat names (e.g., "US House District 2", "State Senate District 2")
- [ ] Modal function wired for remote execution
- [ ] Idempotent via temporal versioning (safe to re-run)
