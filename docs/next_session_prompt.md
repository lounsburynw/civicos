# Recommended: Election Coverage Monitoring

**Priority:** P0 (election_coverage_monitoring)
**Area:** election_coverage_lifecycle
**Date:** 2026-04-01

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

We completed the election cron enrollment pipeline over two sessions: calendar-aware refresh cadence, Marin consolidation, enrollment validation (require explicit `jurisdiction_id`, merge duplicates), officials refresh cron validation, and fixed 29 pre-existing test failures across the extraction suite. The election cron now reliably dispatches to all 26 jurisdictions with correct cadence gating.

This next item adds observability: a monthly completeness report that flags jurisdictions with zero elections, contests, deadlines, or officials data — catching silent failures in the pipeline.

## What This Session Completed

- Fixed `get_active_jurisdictions()`: require explicit `jurisdiction_id`, merge duplicate configs, exclude `civera_instances.json` (11 enrollment tests)
- Validated officials refresh cron: Congress.gov monthly, derivation near elections, not gated by per-source logic (12 tests)
- Fixed 29 pre-existing test failures: entity ID format updates, `civic.storage` → `civicos.storage` mock paths, missing `jsonschema` dep, stale `/tmp/test_chunks` files, ProudCity empty archives, Playwright skip guards, SAM.gov tolerance
- Full extraction suite: 1130 passed, 12 skipped, 0 real failures

## Recommended Task

Build a monthly election coverage completeness report. For each jurisdiction with `election_sources`, count elections, contests, deadlines, and officials. Flag any jurisdiction with zero data in any category. Output as structured logs and optionally as a GitHub issue (following the `cron-failure` pattern).

## Key Files

- `scripts/modal_ingest.py:6176` — `scheduled_election_refresh()` already iterates all jurisdictions
- `packages/civicos/src/civicos/storage/postgres_backend.py` — `get_elections()`, `get_election_deadlines()`, `get_elected_officials()` methods
- `.github/workflows/cron-election-refresh.yml` — existing daily cron, could add monthly coverage check
- `packages/civicos-extraction/src/civicos_extraction/config.py:108` — `get_active_jurisdictions()` (just fixed)
- `packages/civicos-extraction/tests/test_election_cron_enrollment.py` — enrollment test patterns
- `packages/civicos/src/civicos/_internal/elections/derive.py` — officials derivation

## Suggested Approach

1. Add a `check_election_coverage()` function in `scripts/modal_ingest.py` that:
   - Iterates `get_active_jurisdictions()` (only those with `election_sources`)
   - For each, queries: election count, contest count, deadline count, officials count
   - Returns structured report with per-jurisdiction status
2. Add to `scheduled_election_refresh()` as a monthly step (1st of month only)
3. If any jurisdiction has zero data in a category, log a warning
4. Optionally create/update a GitHub issue with label `election-coverage` (follow `cron-failure` pattern in the workflow YAML)
5. Write tests validating the coverage check logic

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Election enrollment + cadence + officials (from recent sessions)
pytest packages/civicos-extraction/tests/test_election_cron_enrollment.py -q --override-ini="addopts="
pytest packages/civicos-extraction/tests/test_election_refresh_cadence.py -q --override-ini="addopts="
pytest packages/civicos-extraction/tests/test_officials_refresh_cron.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] Coverage check function queries elections, contests, deadlines, officials per jurisdiction
- [ ] Flags jurisdictions with zero data in any category
- [ ] Integrated into monthly run (1st of month) within `scheduled_election_refresh()`
- [ ] Structured log output with per-jurisdiction status
- [ ] Tests validate coverage check logic with mock data
- [ ] Smoke tests pass

## Notes

- The `PostgresBackend` already has `get_elections()`, `get_election_deadlines()`, etc. — use these, don't write raw SQL
- Keep the report lightweight — it runs inside the existing cron, not as a separate workflow
- `city-ghost`, `city-test`, `city-warn` are test configs with no `election_sources` — they won't appear in the coverage check
- Estimated ~0.5-1 session
