# Recommended: Fix low_velocity_cron_timeout

**Priority:** P0
**Area:** election_integration / cron reliability
**Date:** 2026-04-19

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Prior session completed the jurisdiction QC walkthrough (all 29 jurisdictions audited, item marked done) and landed two systemic-data prod migrations: BIGINT column widening for `financial_impact_cents` (474 INT32-clamped decisions cleared) and chunk label rename `closing` → `unparsed` (36,611 rows). The BIGINT-cleared decisions sit at NULL until the weekly cron re-extracts them, so fixing the weekly cron is now the highest-leverage unblock.

**10 commits landed this sprint; 12 bugs fixed; see `claude-progress.txt` for full tally.**

## Recommended Task

Fix `scheduled_low_velocity_refresh` in `scripts/modal_ingest.py`. It has hit Modal's 4h (14400s) timeout in 3 of the last 5 weekly runs (2026-04-12, 2026-03-29, 2026-03-22). When it times out mid-run, every alphabetically-later jurisdiction gets zero work done that week. Last crash was at `school-marin-county-oe` meeting [73/84], leaving `school-miller-creek` through `school-tamalpais` and `state-california` entirely skipped.

**Impact of staying broken:**
- 474 BIGINT-cleared decisions stay at NULL forever unless the cron completes
- `school-marin-county-oe` and `school-ross-valley` (BoardDocs) remain stale indefinitely (`last_verified=2026-04-09` today)
- New jurisdiction onboards will make the timeout more frequent

## Key Files

- `scripts/modal_ingest.py:6778` — `scheduled_low_velocity_refresh()` (the crashing function)
- `scripts/modal_ingest.py:7046` — `for jid, config in jurisdictions.items():` (serial per-jurisdiction loop)
- `scripts/modal_ingest.py:6352` — **existing Modal `.spawn()` pattern** that can be mirrored (`extract_decisions.spawn(...)`)
- `.github/workflows/cron-low-velocity-refresh.yml` — schedule + notify-failure job
- `packages/civicos/tests/test_integration_cron_wiring.py` — follow the integration-test pattern here for orchestration changes
- `launch.json` → `low_velocity_cron_timeout` item — three fix options documented (spawn fan-out, sharding, checkpointing)

## Suggested Approach

1. Read the three options in `launch.json` `low_velocity_cron_timeout.description`.
2. Recommended: **Modal `.spawn()` fan-out** per jurisdiction. Spawn all per-jurisdiction work (`fetch_municipal_code`, `extract_agenda_items`, `extract_decisions`) as parallel Modal function calls, collect via `.get()` with per-stage timeout. Respects dependency ordering (`extract_decisions` still runs after agenda items by chaining spawn → get → spawn).
3. Add integration test in `test_integration_cron_wiring.py` validating the fan-out against mocked Modal function handles.
4. Deploy to Modal, manually trigger `gh workflow run cron-low-velocity-refresh.yml`, watch logs.
5. Verify success: `gh run view <id> --log | grep 'passed\|failed'` — all stages completed, no timeout.
6. Spot-check prod: the 474 BIGINT-cleared decisions should have real values after one successful run.

## Tests to Run

```bash
# Full suite for modal_ingest orchestration
civicos-env/bin/python3 -m pytest packages/civicos/tests/test_integration_cron_wiring.py -v --override-ini="addopts="

# Sanity check other affected tests
civicos-env/bin/python3 -m pytest packages/civicos/tests/test_postgres_backend.py packages/civicos-extraction/tests/test_granicus.py packages/civicos/tests/test_pdf_parser.py --override-ini="addopts=" -q
```

## Success Criteria

- [ ] Modal cron completes within 4h for all 31 jurisdictions
- [ ] `gh run list --workflow=cron-low-velocity-refresh.yml --limit 3` shows all successes
- [ ] 474 decisions with `financial_impact_cents IS NULL AND valid_to IS NULL` drop to near-zero after one successful cron
- [ ] `school-marin-county-oe` and `school-ross-valley` `last_verified` updated to current week
- [ ] Integration test covers the new fan-out path

## Known Pending Items (do not re-discover)

- `simbli_incapsula_bypass` (P1, refined 2026-04-19) — 3 active Simbli schools have 0 chunks/decisions (novato, tamalpais, san-rafael) because Simbli doesn't populate `agenda_url`; 4 more are WAF-blocked (kentfield, mill-valley-sd, miller-creek, reed-union). `school-sausalito-marin-city` and `school-larkspur-corte-madera` work because they retain legacy `boarddocs_app_path` fallback.
- **LLM-based agenda parser** (future #13 work) — 36,611 chunks currently labeled `agenda_item='unparsed'` need per-item recovery via an LLM-based item-boundary detector. Secondary numbered-bullet regex already added for Alameda/SF/Berkeley-style agendas; LLM pass covers the long tail.
- `diligent_client` (P2), `expand_granicus_discovery` (P2), `multi_source_advisory_body_coverage` (P1).
- 15 QC follow-ups documented in `jurisdiction_qc_walkthrough.notes` (items #1-#15). Highlights: universal.py:461-474 meeting_type inference; meeting disappearance detection; SF/Marin playwright_llm cleanup; Alameda CDA multi-body flattening; multi-sub-item decision collapse.

## Open PRs

None (verified via `gh pr list` at end of 2026-04-19 session).
