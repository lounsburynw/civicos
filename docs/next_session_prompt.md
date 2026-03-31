# Recommended: Civera Periodic Discovery

**Priority:** P0 (civera_periodic_discovery)
**Area:** election_coverage_lifecycle
**Date:** 2026-03-30

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The election data pipeline is now fully wired: sources → officials fetch → deadlines → officials derivation → snapshot archival. This session generalized the snapshot archival into a shared `_detect_election_transition()` helper used by all three election fetch functions (CA SOS, Marin, Civera).

Currently only 4 of 58 CA counties have Civera ElectionStats instances (Marin, San Joaquin, Sonoma, Yolo). The probe script exists but has never been scheduled. New Civera deployments could appear at any time — quarterly probing ensures we discover them.

## What This Session Completed

- Created `_detect_election_transition()` shared helper in `modal_ingest.py:3402`
- Refactored all 3 election fetch functions to use it (CA SOS, Marin, Civera)
- Extraction functions now return election IDs for transition tracking
- Zero-election fetches preserve previous fingerprint IDs (avoids false transitions)
- Marked `ca_sos_snapshot_archival` as done

## Recommended Task

Schedule `scripts/probe_civera_counties.py` as a quarterly GitHub Actions cron job. When new instances are discovered, auto-update `data/extraction/civera_instances.json`.

1. Create `.github/workflows/cron-civera-discovery.yml` — quarterly schedule
2. The workflow should run the probe script with `--json` output
3. Compare output against current `data/extraction/civera_instances.json`
4. If new instances found, commit the updated JSON (or open a PR)
5. Consider: also update jurisdiction YAML configs to add the new source

## Key Files

- `scripts/probe_civera_counties.py` — 277-line probe script, already works. Scans all 58 CA counties for Civera GraphQL endpoints. Has `--json` flag for machine-readable output.
- `data/extraction/civera_instances.json` — Registry of known instances (currently 4: marin, san-joaquin, sonoma, yolo)
- `packages/civicos-extraction/src/civicos_extraction/clients/civera_election_stats.py` — `CIVERA_INSTANCES` dict and `CiveraElectionStatsClient`
- `.github/workflows/cron-election-refresh.yml` — Existing election cron (pattern to follow for scheduling)
- `scripts/modal_ingest.py:3623` — `fetch_civera_election_results()` — uses `CIVERA_INSTANCES` registry

## Suggested Approach

1. Read `scripts/probe_civera_counties.py` to understand its output format and CLI args
2. Read `.github/workflows/cron-election-refresh.yml` as a template for the new workflow
3. Create `.github/workflows/cron-civera-discovery.yml`:
   - Schedule: quarterly (`cron: '0 12 1 */3 *'` — 1st of Jan/Apr/Jul/Oct)
   - Run `probe_civera_counties.py --json` on Modal or directly
   - Compare against `data/extraction/civera_instances.json`
   - If diff, commit updated file or open PR
4. Verify `CIVERA_INSTANCES` in `civera_election_stats.py` reads from the JSON registry (or is kept in sync)
5. Consider: when a new instance is discovered, should it auto-enroll in the election refresh cron?

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Run the probe locally to verify it works
python scripts/probe_civera_counties.py --timeout 10 --verbose
```

## Success Criteria

- [ ] GitHub Actions workflow created for quarterly Civera discovery
- [ ] Workflow runs probe script and detects new instances
- [ ] New instances update `data/extraction/civera_instances.json`
- [ ] `CIVERA_INSTANCES` in client code stays in sync with JSON registry
- [ ] Smoke tests pass

## Item Sequence After This

| Next | Item | Est. |
|------|------|------|
| P1 | `non_civera_local_race_research` | 1 session |
| P1 | `wire_election_fetch_into_onboard` | 1 session |
| P2 | `election_cron_enrollment_validation` | 0.5 session |

## Notes

- Cron jobs run via GitHub Actions, NOT `modal.Cron()` (Modal starter plan limits crons)
- The probe script uses `requests` with ThreadPoolExecutor for parallel scanning
- 2 pre-existing test failures in `test_integration_election_dispatch.py` — unrelated
- This is estimated at ~0.5 session since the probe script already exists
