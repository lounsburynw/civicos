# Recommended: Onboard End-to-End Test

**Priority:** P0 (onboard_end_to_end_test)
**Area:** turnkey_onboarding
**Date:** 2026-03-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The turnkey onboarding pipeline is now 6/10 complete. Recent sessions built out: platform pipeline wiring (CivicClerk, eScribe), HTML agenda extraction, config-driven issue provider dispatch, auto-detection of 311 providers, and (just now) severity-classified quality gates. The pipeline is functionally complete for onboarding cities — what's missing is an automated test proving it works end-to-end.

Currently the onboarding flow has only been tested manually (`--skip-ingestion` on San Rafael). There's no integration test that exercises the full chain: config generation -> sample ingestion -> quality gate -> full ingestion -> final report.

## What Was Done This Session

Added severity-classified quality gates to `scripts/onboard.py`:
- `QualityIssue` class (line 55) with CRITICAL/WARNING severity + actionable remediation text
- Phase 2.5 validation gate now **fails-fast** on CRITICAL issues (exits 2) instead of proceeding
- `--force-continue` flag to override the gate for debugging
- Exit codes: 0=clean, 1=ingestion error, 2=quality issues
- Commit: `a9f8430`

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/onboard.py` | Full file | Onboarding orchestrator — the thing being tested |
| `scripts/onboard.py:55-67` | `QualityIssue` class | Severity classification |
| `scripts/onboard.py:70-164` | `_quality_report()` | Quality assessment with severity |
| `scripts/onboard.py:459-487` | Phase 2.5 gate | Fail-fast on CRITICAL issues |
| `packages/civicos-extraction/src/civicos_extraction/onboard.py` | `onboard_jurisdiction()` | Config generation + discovery |
| `packages/civicos-extraction/tests/test_onboard_yaml.py` | Existing test | YAML generation tests (pattern to follow) |

## Suggested Approach

1. **Create test file** at `packages/civicos-extraction/tests/test_onboard_e2e.py` (or `tests/test_onboard_integration.py` at project root)

2. **Test the quality report function directly** (unit-level):
   - Clean data -> 0 issues, exit 0
   - Zero meetings on meeting platform -> CRITICAL
   - Zero meetings, no meeting stages -> OK (expected)
   - Zero agenda items with meetings -> CRITICAL
   - HTML platform (chunks=0) -> WARNING, not CRITICAL
   - Low decisions -> WARNING

3. **Test the CLI orchestration** (integration-level):
   - Mock `_run_modal_ingestion()` and `_get_data_counts()` to avoid real Modal/Postgres
   - Test that CRITICAL issues cause sys.exit(2) in Phase 2.5
   - Test that `--force-continue` overrides the gate
   - Test that `--skip-ingestion` still works
   - Test that `--no-validate` skips Phase 2.5 entirely

4. **Test config generation** (may already be covered by `test_onboard_yaml.py`):
   - Verify `onboard_jurisdiction()` produces valid extraction JSON + YAML
   - Verify `detect_issue_source()` works for known cities

## Important Context

- `_quality_report()` is a pure function (dict in, list + issues out) — easy to unit test
- The CLI `main()` calls `sys.exit()` — use `pytest.raises(SystemExit)` to test exit codes
- Real Modal/Postgres calls should be mocked — this is a test of the orchestration logic, not the infra
- San Rafael baseline ratios: ~52 chunks/meeting, ~3 agenda_items/meeting, ~0.45 decisions/meeting
- See `test_integration_cron_wiring.py` for the project's pattern of mocking external services in integration tests

## Success Criteria

- [ ] Unit tests for `_quality_report()` covering all severity classifications
- [ ] Integration test for CLI flow with mocked Modal/Postgres
- [ ] Tests verify exit codes (0, 1, 2) match expected behavior
- [ ] Tests verify `--force-continue` and `--no-validate` flags
- [ ] All existing smoke tests still pass
