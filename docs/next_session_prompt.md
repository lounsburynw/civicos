# Recommended: Validate Mass-Ingest Jurisdictions (`validate_mass_ingest_jurisdictions`)

**Priority:** P0
**Area:** federation_testbed > validate_mass_ingest_jurisdictions
**Date:** 2026-04-07

> Recommended context from prior session. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

Two parallel sessions landed on 2026-04-07. One fixed the dedup P0 (`fix_decision_storage_dedup` shipped via `compute_stable_decision_id()` content-hash IDs — see `packages/civicos/src/civicos/storage/integrity.py`, 21 unit + 4 integration tests). The other did a data-status audit of all 15 mass-ingest jurisdictions (Marin 11 cities + county-marin + SF + county-alameda + city-berkeley) and filed 7 new launch.json items. Both sessions are now done.

The audit surfaced two concrete silent failures (tiburon empty, alameda ghost) plus several quality gaps. **None of these were caught by automated checks — they only showed up when someone counted rows per jurisdiction.** The umbrella P0 codifies that manual pass so the next launch readiness review is reproducible, not ad hoc.

## Recommended Task

Run a per-jurisdiction launch-validation pass across all 15 mass-ingest jurisdictions. For each: verify storage/vector counts, run 3 canonical v2 API queries, eyeball results for sanity. Produce a pass/fail checklist. Promote failures into concrete follow-up items (several are already filed — see below).

## Key Files

- `launch.json` ~line 1195 — `validate_mass_ingest_jurisdictions` (P0) with full item notes
- `launch.json` — already-filed sub-items: `fix_tiburon_empty` (P1), `complete_alameda_ingest_or_scope` (P1), `index_county_marin_decision_vectors` (P2), `fairfax_cortemadera_video_discovery` (P2), `sf_audio_backfill` (P2), `document_mass_ingest_cost_ceiling` (P2)
- `scripts/verify_cross_county_phase_b.py` — existing verification script pattern, good starting point for a broader version
- `/tmp/mass_ingest_status.json` — live counts snapshot from 2026-04-07 audit (may not persist across restarts)
- Memory: `project_mass_ingest_april_2026.md` — scope, validation tiers, known issues per jurisdiction
- Memory: `feedback_verify_handoff_diagnoses.md` — **READ THIS FIRST.** Don't treat same-title rows as duplicates without inspecting disambiguating fields. The prior session learned this the hard way.

## Suggested Approach

1. **Read the audit snapshot.** `cat /tmp/mass_ingest_status.json` if it's still there, otherwise regenerate (use `civic.storage.get_*_count(jid)` and `civic.vectors.count(jid, corpus)` — per `feedback_data_status_gaps`, query `elections` and `elected_officials` tables directly since the API counts undercount them).
2. **Write a validation script** (`scripts/validate_mass_ingest.py`) that iterates the 15 jurisdictions and for each: (a) fetches storage + vector counts for decisions/meetings/transcripts/chunks/issues/municipal_code/agenda_items, (b) runs 3 v2 API queries (`housing`, `budget`, `what's next`), (c) reports pass/fail with a clear reason. Output to stdout + JSON file.
3. **Run it. Eyeball the results.** Known failures you should see: `city-tiburon` (0 everywhere), `county-alameda` (decisions but no drill-down context), `county-marin` (0 decision vectors despite 105 decisions).
4. **File any NEW failures** as launch.json items. Don't re-file the already-known ones (check the list above).
5. **Mark `validate_mass_ingest_jurisdictions` done** only after the pass has been run AND all findings are either fixed or filed.
6. **Promote one of the P1 sub-items** (`fix_tiburon_empty` or `complete_alameda_ingest_or_scope`) to P0 before `/nextsesh`.

## Tests to Run

```bash
# Smoke
source civicos-env/bin/activate && pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Verify dedup fix is still intact (parallel session's work)
pytest packages/civicos/tests/test_integration_decision_dedup.py -q --override-ini="addopts="

# Cross-county verification from the earlier Phase B work
python3 scripts/verify_cross_county_phase_b.py
```

## Success Criteria

- [ ] `scripts/validate_mass_ingest.py` exists and runs against all 15 jurisdictions
- [ ] Pass/fail report produced (JSON or markdown) with reason codes per failure
- [ ] Known issues (tiburon, alameda, marin vectors) re-surfaced by the script (proving it works)
- [ ] Any NEW failures filed as launch.json items
- [ ] `validate_mass_ingest_jurisdictions` marked done in launch.json
- [ ] New P0 promoted (recommend `fix_tiburon_empty` — smallest concrete next step)

## Caveats

- **Don't expand scope.** This is a validation pass, not a fix-everything sprint. Surfacing and filing is enough — the actual fixes are separate launch.json items.
- **The dedup fix is already live.** `compute_stable_decision_id()` in `packages/civicos/src/civicos/storage/integrity.py` is the authoritative ID scheme. Don't write a new dedup key. Don't treat same-title rows as duplicates — per `feedback_verify_handoff_diagnoses.md`, same title ≠ same decision (e.g., 4 Berkeley housing projects at 4 different sites with identical generic LLM summaries).
- **DataStatus undercounts elections/officials.** Query `elections` and `elected_officials` tables directly via `civic.storage._get_connection()` — the API count methods return 0 for these even when rows exist (659 elections, 532 officials in DB as of 2026-04-07).
- **Foundation-funded.** If the validation pass wants to kick off remediation (re-ingestion, audio backfill, vector indexing), wait on `document_mass_ingest_cost_ceiling` or get explicit budget approval. $50 proxy surprise on 2026-04-05 is the reason for this guardrail.

## Open PRs

None as of session end.
