# Recommended: Backfill Election Sources

**Priority:** P0 (backfill_election_sources)
**Area:** election_coverage_lifecycle
**Date:** 2026-03-30

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session added a new `election_coverage_lifecycle` category to launch.json with 11 items prioritized: CA depth first, automation second, ingestion strategy third. Currently 24 extraction configs have zero `election_sources` — Berkeley, Sacramento, county-alameda, 10 school districts, and others get no election data at all. Running `detect_election_sources()` against them populates at minimum `ca_sos_results` + legislative districts via Census geocoder. This is the quickest way to expand election coverage across CA.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/onboard.py:687` — `detect_election_sources()` dispatcher. Takes jurisdiction_id, state, county, lat, lng. Returns source config dict.
- `packages/civicos-extraction/src/civicos_extraction/providers/california.py` — CA provider: returns `ca_sos_results` + Civera (if county has instance) + districts (if lat/lng).
- `data/extraction/*.json` — 24 configs without `election_sources` (listed below).
- `data/jurisdictions/*.yaml` — Jurisdiction YAML files with state, county, lat/lng for geocoding.
- `packages/civicos-extraction/src/civicos_extraction/onboard.py:608` — `detect_districts()` — Census geocoder for legislative district detection.

## Jurisdictions Needing Backfill

**CA cities/counties (would get ca_sos_results + districts):**
city-berkeley, city-sacramento, city-national-city, county-alameda

**CA school districts (would get ca_sos_results, possibly Civera if in covered county):**
school-kentfield, school-larkspur-corte-madera, school-marin-county-oe, school-mill-valley-sd, school-miller-creek, school-novato, school-reed-union, school-ross-valley, school-sausalito-marin-city, school-tamalpais

**Other:** college-marin, county-travis (TX — would get tx_sos_results)

**Skip:** city-ghost, city-test, city-warn (test fixtures), san-rafael.json/san-anselmo.json (legacy duplicates), .marin-granicus-discovery.json, civera_instances.json (not jurisdiction configs)

## Suggested Approach

1. **Write a one-time backfill script** (or extend `onboard.py` with `--re-detect-elections` flag) that:
   - Iterates `data/extraction/*.json` files missing `election_sources`
   - For each, reads the jurisdiction YAML to get state, county, lat, lng
   - Calls `detect_election_sources(jurisdiction_id, state, county, lat, lng)`
   - Writes the result into the extraction config's `election_sources` field
   - Skips test/supplementary configs

2. **Verify results** — Spot-check a few configs (Berkeley should get `ca_sos_results` with `county: alameda`, Marin school districts should get Civera + SOS).

3. **Run election provider + detection tests** to ensure no regression.

4. **Optionally combine with `populate_deadlines_in_cron`** (next P1) — since both are quick wins that expand coverage without building new clients.

## Tests to Run

```bash
pytest packages/civicos-extraction/tests/test_election_providers.py -q --override-ini="addopts="
pytest packages/civicos-extraction/tests/test_election_detection.py -q --override-ini="addopts="
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] All CA extraction configs have `election_sources` populated
- [ ] county-travis gets `tx_sos_results` (validates multi-state)
- [ ] Marin school districts get Civera + CA SOS (in covered county)
- [ ] Non-Marin CA jurisdictions get CA SOS + districts
- [ ] Test/supplementary configs skipped cleanly
- [ ] All existing tests pass (zero regression)

## Item Sequence After This

| Next | Item | Est. |
|------|------|------|
| P1 | `populate_deadlines_in_cron` | 0.5 session |
| P1 | `ca_sos_snapshot_archival` | 1 session |
| P1 | `officials_derivation_in_cron` | 0.5 session |
| P1 | `wire_election_fetch_into_onboard` | 1 session |
| P2 | `officials_refresh_cron` | 0.5 session |

See `docs/internal/election-coverage-assessment.md` for the full gap analysis.
