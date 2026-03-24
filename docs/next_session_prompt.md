# Recommended: Onboard Quality Gates

**Priority:** P0 (onboard_quality_gates)
**Area:** turnkey_onboarding
**Date:** 2026-03-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

We've been building out the turnkey onboarding pipeline. Recent sessions completed `issue_provider_dispatch` (config-driven 311 client routing) and `issue_provider_detection` (auto-detect SeeClickFix via API probe). The onboarding script (`scripts/onboard.py`) now generates configs, detects platforms, detects issue providers, runs ingestion, and produces a quality report.

**The quality report is currently advisory only.** It prints red flags but doesn't block progression. A city with zero meetings still proceeds to vector indexing (wasting resources). Transient API errors (rate limits, timeouts) look the same as genuine platform limitations (no PDFs, no minutes).

## What Was Done This Session

1. `detect_issue_source()` in `packages/civicos-extraction/src/civicos_extraction/onboard.py:466` — probes SeeClickFix API
2. Wired into `onboard_jurisdiction()` at line 1376 (Step 2.5)
3. `--detect-issues` CLI flag in `scripts/onboard.py:259` for re-running detection
4. Exported from `__init__.py`

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `scripts/onboard.py:55-116` | `_quality_report()` | Current quality report — needs strengthening |
| `scripts/onboard.py:397-427` | Phase 2.5 validation gate | Sample ingestion + quality check (advisory) |
| `scripts/onboard.py:440-475` | Phase 4 final report | Post-ingestion quality report |
| `scripts/onboard.py:35-52` | `_get_data_counts()` | Queries PostgreSQL for corpus counts |
| `scripts/onboard.py:175-196` | `_run_modal_ingestion()` | Runs Modal ingestion stages |

## Suggested Approach

1. **Distinguish transient errors from platform limitations** in `_quality_report()`:
   - `chunks/meeting = 0` could be HTML-only agendas (permanent) OR failed PDF downloads (transient)
   - Add retry logic or separate error categories
   - Consider checking if the platform type is known to use HTML agendas vs PDFs

2. **Gate progression to vector indexing** on minimum data thresholds:
   - If meetings = 0 and platform should have meetings → fail-fast, don't proceed to chunks/vectors
   - If chunks = 0 but meetings > 0 → warn but continue (HTML agenda platforms are valid)
   - Configurable thresholds via CLI flags (e.g., `--min-meetings 5`)

3. **Generate actionable remediation steps** instead of generic warnings:
   - "meetings = 0" → "Check extraction config: verify view_id {X} returns data at {URL}"
   - "chunks = 0" → "This platform uses HTML agendas. Chunks come from HTML extraction (supported since commit 05feb38)"
   - "decisions = 0" → "Minutes may not be posted yet. Re-run after {N} days"

4. **Add exit codes** reflecting quality status:
   - 0 = clean (all quality checks pass)
   - 1 = error (ingestion failed)
   - 2 = warning (completed but quality issues found)

## Important Context

- San Rafael baseline ratios: ~52 chunks/meeting, ~3 agenda_items/meeting, ~0.45 decisions/meeting
- HTML agenda extraction was added in commit `05feb38` — some platforms legitimately have 0 PDF chunks
- The validation gate (Phase 2.5) runs a 30-day sample before full backfill — this is the right place to fail-fast

## Success Criteria

- [ ] Quality report distinguishes transient errors from platform limitations
- [ ] Vector indexing gated on minimum data thresholds (meetings > 0 for meeting platforms)
- [ ] Actionable remediation steps in quality report output
- [ ] Exit codes reflect quality status
- [ ] Existing onboarding flow still works (San Rafael, Mill Valley, San Anselmo)
- [ ] Smoke tests pass
