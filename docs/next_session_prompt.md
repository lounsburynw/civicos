# Recommended: Cron Health Investigation

**Priority:** P0 (cron_health_investigation)
**Area:** observability
**Date:** 2026-03-30

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

User reported that "a lot of our cron jobs are failing." This session completed `backfill_election_sources` (all 16 configs now have election data), but the next planned items (`populate_deadlines_in_cron`, `officials_derivation_in_cron`) wire new logic into cron infrastructure. There's no point adding features to broken infrastructure. Investigate broadly first.

## What This Session Completed

- Added reusable `backfill_election_sources()` to `onboard.py` with CLI (`python -m civicos_extraction.onboard backfill-elections`)
- All 16 extraction configs now have `election_sources` populated (CA SOS, Marin Civera, TX SOS)
- 114 tests pass, 0 failures

## Recommended Task

Broad investigation of cron job health:
1. Which GitHub Actions cron workflows exist and are they running?
2. Which are failing, and why?
3. Are the Modal functions they trigger still deployed and functional?
4. Fix the failures before wiring new cron features

## Key Files

- `.github/workflows/cron-*.yml` — Cron workflow definitions (GH Actions triggers `modal run`)
- `scripts/modal_ingest.py` — Main Modal ingest script with scheduled functions
- `scripts/modal_usage_rollup.py` — Usage rollup cron
- `packages/civicos-extraction/src/civicos_extraction/cron/` — Cron job implementations (if dir exists)

## Suggested Approach

1. **Inventory cron workflows**: `ls .github/workflows/cron-*.yml` and read each
2. **Check GH Actions run history**: `gh run list --workflow=<name> --limit=5` for each workflow
3. **Check Modal app status**: `modal app list` and `modal app logs <app-name>`
4. **Identify failure patterns**: Are all failing? Some? Auth/secrets, code errors, or infrastructure?
5. **Fix root causes**: Could be expired Modal tokens, missing secrets, code bugs, or stale deployments
6. **Verify fixes**: Re-trigger a workflow manually and confirm it succeeds

## Tests to Run

```bash
# Smoke tests (baseline)
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# If cron code is modified, run integration tests
pytest packages/civicos-extraction/tests/ -q --override-ini="addopts=" -k "cron"
```

## Success Criteria

- [ ] All cron workflows inventoried with current status (passing/failing/disabled)
- [ ] Root cause identified for each failing workflow
- [ ] Critical cron jobs fixed and verified running
- [ ] Non-critical failures documented with fix plan
- [ ] Infrastructure confirmed ready for new cron features

## Item Sequence After This

| Next | Item | Est. |
|------|------|------|
| P1 | `populate_deadlines_in_cron` | 0.5 session |
| P1 | `ca_sos_snapshot_archival` | 1 session |
| P1 | `officials_derivation_in_cron` | 0.5 session |

These all depend on healthy cron infrastructure.
