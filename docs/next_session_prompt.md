# Recommended: Re-extract Alameda County (`onboard_county_alameda`)

**Priority:** P0
**Area:** federation_testbed > onboard_county_alameda
**Status in launch.json:** not_started (re-opened 2026-04-07)
**Date:** 2026-04-07

> Recommended context from prior session. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

Phase B of `cross_county_query_prototype` shipped today. The cross-county query layer is fully validated end-to-end against `city-berkeley` and `city-san-francisco` (real Postgres, 6 new integration tests + 8 unit tests). A new `SearchRequest.per_jurisdiction_limit` knob was added to guarantee visibility of named cross-county jurisdictions in the flat ranked stream.

**The blocker for Phase B follow-on**: `county-alameda` is empty in Postgres despite `onboard_county_alameda` being marked done back on 2026-03-13 (commit `d6f3adc`). Verified 0 meetings, 0 decisions, 0 transcripts as of 2026-04-07. Berkeley's parent-chain queries (`include_parents=True` from `city-berkeley`) currently return nothing at the county level, which means we can't fully demonstrate cross-county *parent* semantics — only sibling/explicit cases.

## Why This Happened

The original extraction config (`data/extraction/county-alameda.json` in commit `d6f3adc`) had 6 Granicus archive views: `view_2` through `view_9`. In commit `ee9d584` (2026-03-18) the file was simplified to a single `board: "1"` view as a "chore" — but extraction was never re-run after the simplification. Either the original views were wrong (which is why they were simplified) or `board: 1` is wrong (which is why the database is empty). Both are possible; the prior session didn't verify.

## Recommended Task

Re-run Alameda County extraction with the correct Granicus archive view IDs, and verify it actually populates Postgres.

### Key Files
- `data/extraction/county-alameda.json` — current config (single `board: "1"` view)
- `data/jurisdictions/county-alameda.yaml` — jurisdiction registration
- `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py` — Granicus client
- `scripts/verify_cross_county_phase_b.py` — Phase B verification script (use to retest after onboarding)

### Suggested Approach

1. **Visit the Granicus archive UI directly** to find the correct view ID(s):
   `https://alamedacounty.granicus.com/ViewPublisher.php?view_id=N` — try N=1..15. Look for the Board of Supervisors archive. The git history of `county-alameda.json` shows what was tried before (commits `d6f3adc` and `ee9d584`).
2. **Update `data/extraction/county-alameda.json`** with the verified view ID(s) — possibly multiple if BoS, committees, etc. are split across views.
3. **Re-run the extraction** via the onboarding pipeline:
   ```bash
   /onboard county-alameda
   # or directly: python3 -m civicos_extraction.cli.onboard_cli county-alameda
   ```
4. **Verify Postgres population**:
   ```bash
   source civicos-env/bin/activate && python3 -c "
   from dotenv import load_dotenv; load_dotenv()
   from civicos import CivicOS
   c = CivicOS('county-alameda')
   print(f'meetings: {len(c.storage.get_meetings(\"county-alameda\"))}')
   print(f'decisions: {len(c.storage.get_decisions(\"county-alameda\"))}')"
   ```
5. **Re-run the Phase B verification script** to confirm Berkeley parent-chain queries now find county-alameda:
   ```bash
   python3 scripts/verify_cross_county_phase_b.py
   ```
   Then add a new test to `TestCrossCountyIntegration` that runs `include_parents=True` from `city-berkeley` and asserts `county-alameda` appears in the bucket.

### Caveats

- The notes field on `onboard_county_alameda` still says "Onboarded via turnkey pipeline" from the prior failed attempt — that's misleading. Don't trust prior status; verify directly against Postgres before declaring done.
- If the Granicus archive genuinely has no public meetings (unlikely for a major California county), document the dead-end and consider Legistar as a fallback. Alameda County uses both depending on the body.
- This is **only Phase B follow-on**, not a brand-new ETL piece. Don't expand scope.

## Tests to Run

```bash
# Smoke (always)
source civicos-env/bin/activate && pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Re-run Phase B integration tests after onboarding to confirm no regressions
pytest packages/civicos-services/tests/test_integration_query_v2.py::TestCrossCountyIntegration -q --override-ini="addopts="

# Phase B live verification (requires Postgres)
python3 scripts/verify_cross_county_phase_b.py
```

## Success Criteria

- [ ] `data/extraction/county-alameda.json` has verified working Granicus view ID(s) (or Legistar config)
- [ ] `county-alameda` has nonzero meetings AND nonzero decisions in Postgres
- [ ] Berkeley parent-chain query (`include_parents=True` from `city-berkeley`) returns at least one `county-alameda` result for a relevant query
- [ ] New integration test added to `TestCrossCountyIntegration` covering Berkeley→county-alameda parent chain
- [ ] `onboard_county_alameda` marked `done` in `launch.json`
- [ ] New P0 promoted before `/nextsesh`

## Phase B Summary (just shipped)

For full context, see `claude-progress.txt` Session 2026-04-07 entry. Key bits:

- `cross_county_query_prototype` marked **done**, demoted to P1
- New `SearchRequest.per_jurisdiction_limit: Optional[int]` (1-50) — when set, each jid bucket is capped at N AND the flat results list is built by interleaving top-N from each jid (not winner-take-all). Default `None` preserves backwards compat.
- Validated end-to-end with `also_include=[city-berkeley, city-san-francisco]` from `city-san-rafael`. Tier weight 0.5x enforced. Latency ~900-2500ms for 3 jids, ~4700ms for 19-jid Marin sibling fan-out.
- Spec `docs/internal/cross-county-relevance-spec.md` updated with answers to 4 of 5 open questions (topic classification still deferred).

## Other Open Items (background, not P0)

| Priority | Item | Notes |
|---|---|---|
| P2 | `fix_decision_storage_dedup` | Berkeley + SF have 4-5 identical decision rows each. Likely upsert idempotency bug in Granicus/Legistar paths. Not blocking. |
| P3 | `fix_sf_county_parent` | `city-san-francisco` registry lacks `county-san-francisco` parent. Works coincidentally for cross-county tier. Cosmetic. |
| P3 | `federation_adr` | Architecture decision record (deferred). |
| P3 | `direct_city_submission` | Authenticated clerk endpoint (deferred). |
| P2 | `token_purchase_ui` | **Deprioritized** per April 2026 roadmap pivot. Don't promote. |

## Open PRs

None as of session end.
