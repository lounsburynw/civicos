# Recommended: Election Source Auto-Detection (Session 2)

**Priority:** P0 (election_source_auto_detection)
**Area:** multi_state_portability
**Date:** 2026-04-02

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Sessions 1a+1b (2026-04-02) built `ClarityElectionsClient` and wired it into CaliforniaElectionProvider for 7 net-new CA counties. Then addressed all codebase critic warnings: moved `CLARITY_INSTANCES` from hardcoded dict to `data/extraction/clarity_instances.json`, added `_check_partial_fetch()` guard to all 3 election handlers, fixed candidate ID collisions, and updated `refresh.critic.md` + `configuration.critic.md` with election-specific guidance.

**What still needs work:** The client has NOT been tested against live Clarity endpoints. The JSON summary parser handles multiple format variants speculatively. Session 2 should validate against real data, implement archive-on-fetch, and solve election ID discovery.

## What to Build

### 1. Validate Against Live Clarity Data (highest priority)
Probe a known-working Clarity county. Santa Clara's Dec 2025 runoff was live as of 2026-03-30. Fetch the real JSON summary, compare against what `parse_summary_contests()` and `clarity_contest_to_storage()` expect. Fix any format mismatches.

### 2. Election ID Discovery
`discover_elections()` scrapes HTML for IDs — Clarity pages are JS SPAs so this likely won't work. Options: static registry in `clarity_instances.json` (add `election_ids` array per county), or `pip install clarify` library for page-level discovery.

### 3. Archive-on-Fetch Pipeline
Clarity data is ephemeral (purged without warning). On first fetch, archive raw JSON to R2 before parsing. See `BLOB_STORAGE_URL` in `.env`.

### 4. Optional: Extend to Non-CA States
Clarity covers 30+ states. Expanding `clarity_instances.json` and adding Clarity detection to `DefaultElectionProvider` would give non-CA states working election data.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/clients/clarity_elections.py` — Client, detection, mappers, extraction. Registry loads from JSON at line 59. Parser at line 475.
- `data/extraction/clarity_instances.json` — Source of truth for known Clarity counties (9 CA entries).
- `packages/civicos-extraction/src/civicos_extraction/election_fetch.py` — `_check_partial_fetch()` at line 20, `_fetch_clarity` at line 270.
- `packages/civicos-extraction/src/civicos_extraction/providers/california.py:65` — Clarity detection, requires `state` in config.
- `docs/internal/clarity-elections-research.md` — URL patterns, API endpoints, ephemerality, `clarify` library.
- `packages/civicos-extraction/tests/test_clarity_elections.py` — 61 tests.

## Suggested Approach

1. **Probe live endpoint**: `curl https://results.enr.clarityelections.com/CA/Santa_Clara/` — find election ID in page source or try known IDs from research doc
2. **Fetch real data**: `GET /{eid}/current_ver.txt` then `GET /{eid}/{ver}/json/en/summary.json`
3. **Compare JSON structure** to parser expectations, fix mismatches
4. **Run end-to-end extraction** against 1 real county, verify contests stored in Postgres
5. **Add election IDs** to `clarity_instances.json` for discovered elections

## Tests to Run

```bash
pytest packages/civicos-extraction/tests/test_clarity_elections.py -q --override-ini="addopts="
pytest packages/civicos-extraction/tests/test_election_fetch.py -q --override-ini="addopts="
pytest packages/civicos-extraction/tests/ -k election -q --override-ini="addopts="
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] JSON summary parser validated against real Clarity data (at least 1 county)
- [ ] End-to-end extraction works for at least 1 Clarity county (contests in Postgres)
- [ ] Election ID discovery solved (static registry or library-based)
- [ ] All existing tests still pass (no regressions)
