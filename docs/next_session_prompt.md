# Recommended: Election Source Auto-Detection (Session 2)

**Priority:** P0 (election_source_auto_detection)
**Area:** multi_state_portability
**Date:** 2026-04-02

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 1 (2026-04-02) built the `ClarityElectionsClient` and wired it into the CaliforniaElectionProvider. 7 net-new CA counties (Butte, Contra Costa, Madera, Merced, Santa Clara, Shasta, Ventura) are now auto-detected during onboarding, with a registered fetch handler in the dispatch pipeline. All 271 election tests pass including 59 new Clarity-specific tests.

**What still needs work:** The client was built against the documented Clarity API format but has NOT been tested against live endpoints. The JSON summary parser handles multiple format variants speculatively. Session 2 should validate against real Clarity data, implement archive-on-fetch (data is ephemeral), and optionally extend detection to non-CA states.

## What Changed Last Session

- **NEW** `clients/clarity_elections.py` — ClarityElectionsClient (ElectionExtractor protocol), detection, mappers, extraction
- **UPDATED** `providers/california.py` — CaliforniaElectionProvider detects Clarity for 7 net-new counties
- **UPDATED** `election_fetch.py` — `_fetch_clarity` handler registered in `_FETCH_HANDLERS`
- **UPDATED** `clients/__init__.py` — `clarity_elections` in `SUPPORTED_ELECTION_SOURCES`
- **NEW** `tests/test_clarity_elections.py` — 59 tests (all mocked HTTP)

## What to Build

### 1. Validate Against Live Clarity Data (highest priority)
Probe a known-working Clarity county to validate JSON summary parsing. Santa Clara's Dec 2025 runoff was still live as of 2026-03-30. Fetch the real JSON, compare against what `parse_summary_contests()` and `clarity_contest_to_storage()` expect. Fix any format mismatches.

### 2. Archive-on-Fetch Pipeline
Clarity data is ephemeral (old elections are purged). On first fetch, archive the raw JSON/XML to R2 blob storage before parsing. Pattern: download to temp file, upload to R2, then parse.

### 3. Election ID Discovery
Current `discover_elections()` scrapes HTML for election IDs — Clarity pages are JavaScript SPAs so this may not work well. Consider: maintained static registry of election IDs per county (updated quarterly), or using the `clarify` Python library (`pip install clarify`, MIT) for page-level discovery.

### 4. Optional: Extend to Non-CA States
`DefaultElectionProvider` still generates placeholder `{state}_sos_results` keys. Could add Clarity detection there too — Clarity covers counties in 30+ states, not just CA. Would require expanding `CLARITY_INSTANCES` or building a dynamic probe.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/clients/clarity_elections.py` — ClarityElectionsClient (608 lines). Registry at line 47, detection at line 78, client at line 108, mappers at line 275, extraction at line 435.
- `packages/civicos-extraction/src/civicos_extraction/providers/california.py:65` — Clarity detection in CaliforniaElectionProvider.
- `packages/civicos-extraction/src/civicos_extraction/election_fetch.py:237` — `_fetch_clarity` handler.
- `packages/civicos-extraction/src/civicos_extraction/clients/__init__.py:128` — `SUPPORTED_ELECTION_SOURCES` includes `clarity_elections`.
- `docs/internal/clarity-elections-research.md` — Clarity API research (URL patterns, data ephemerality, `clarify` library).
- `packages/civicos-extraction/tests/test_clarity_elections.py` — 59 tests.

## Suggested Approach

1. **Probe a live Clarity endpoint** to get real JSON summary data:
   - Santa Clara: `results.enr.clarityelections.com/CA/Santa_Clara/` (find election ID on page)
   - Get `/{eid}/current_ver.txt`, then `/{eid}/{ver}/json/en/summary.json`
   - Compare real JSON structure to what `parse_summary_contests()` expects
2. **Fix any parser mismatches** — the format may use different field names than what we coded
3. **Add archive-on-fetch** — store raw response in R2 before parsing (see `BLOB_STORAGE_URL` in `.env`)
4. **Run the full extraction** against one real county to validate end-to-end

## Tests to Run

```bash
# Clarity-specific tests
pytest packages/civicos-extraction/tests/test_clarity_elections.py -q --override-ini="addopts="

# All election tests (regression)
pytest packages/civicos-extraction/tests/ -k election -q --override-ini="addopts="

# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] JSON summary parser validated against real Clarity data (at least 1 county)
- [ ] Archive-on-fetch stores raw data in R2 before parsing
- [ ] End-to-end extraction works for at least 1 Clarity county (contests stored in Postgres)
- [ ] Election ID discovery works or has a maintained fallback (static registry)
- [ ] All existing tests still pass (no regressions)
