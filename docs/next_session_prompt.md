# Recommended: Continue Jurisdiction QC Walkthrough

**Priority:** P0
**Area:** data quality / ingestion audit
**Date:** 2026-04-15

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Manual QC walkthrough of 24 ingested jurisdictions against live municipal websites. Goal: verify ingested data is accurate, up-to-date, and complete before launch. Completed **10/~18 so far** and uncovered **4 significant data quality bugs**, all fixed and tested:

1. **ProudCity P.M. regex** (`9c0c12c0`) — "6:00 P.M." with dots not matched → meetings stored at 06:00 instead of 18:00 → time flip-flopping on every cron run. San Rafael had 59 phantom duplicates.
2. **Phantom version bloat from tz mismatch** (`7e42ca84`) — CivicPlus sends `2026-04-07T00:00:00+00:00`, stored as naive `2026-04-07T00:00:00`. String comparison triggered "change" every cron run. Corte Madera had 80 phantom versions across 19 meetings. Deleted 221 phantom versions globally.
3. **CivicPlus AMID discovery** (`35d91023` + `df4656e9`) — Platform detection passed single confirmation AMID as authoritative list, so full 1-80 scan was skipped. Larkspur missed Planning Commission, Design Review, Heritage Preservation boards.
4. **BoardDocs unbounded fetch** — Daily cron re-fetched all 367 college-marin meetings back to 2014 every run. Added `days_past=90` guard.

Plus contextual time extraction in ProudCity (closed session vs regular meeting) with 23 new tests, and an advisory body gap probe added to the onboarding pipeline.

## Recommended Task

Continue the jurisdiction-by-jurisdiction walkthrough. **Next jurisdiction: city-ross** (playwright_llm source, 20 meetings, 0 transcripts). Then work through the remaining list.

### Completed (10)
san-rafael, mill-valley, san-anselmo, sausalito, fairfax, corte-madera, novato, belvedere, tiburon, larkspur

### Remaining (~18)
- **Cities:** city-ross (next), county-marin, city-san-francisco, city-berkeley, county-alameda
- **Schools (11):** school-kentfield, school-larkspur-corte-madera, school-marin-county-oe, school-mill-valley-sd, school-miller-creek, school-novato, school-reed-union, school-ross-valley, school-san-rafael, school-sausalito-marin-city, school-tamalpais
- **Other:** college-marin, county-sonoma, state-california

## Key Files

- `reports/ingestion-audits/2026-04-14.md` — latest automated audit (run weekly via GH Actions)
- `.claude/commands/audit.md` — `/audit` slash command for full automated audit
- `.github/workflows/cron-ingestion-audit.yml` — weekly headless Claude audit
- `packages/civicos-extraction/src/civicos_extraction/clients/proudcity.py:935` — time extraction (contextual)
- `packages/civicos/src/civicos/storage/postgres_backend.py:1923` — meeting change detection (tz-normalized)
- `packages/civicos-extraction/tests/test_proudcity.py` — 23 new regression tests
- `packages/civicos/tests/test_postgres_backend.py:262` — 2 new regression tests

## Suggested Approach (per jurisdiction)

1. Query DB: meeting counts by type, recent meetings, decisions, transcripts, version bloat
2. Compare against live municipal website via `WebFetch`
3. Check extraction config for missing archives (common pattern: only one body configured, others missing)
4. Flag and investigate discrepancies
5. If a pattern bug is found, fix it + add tests + clean up data for all affected jurisdictions
6. Annotate YAML with known gaps if any
7. Move to next jurisdiction

Expect 3-5 jurisdictions per session. Schools will go fast (many are Simbli-blocked — verify and move on).

## Tests to Run

```bash
civicos-env/bin/python3 -m pytest packages/civicos-extraction/tests/test_proudcity.py -v --override-ini="addopts="
civicos-env/bin/python3 -m pytest packages/civicos/tests/test_postgres_backend.py -k "timezone_mismatch or none_vs_empty" -v --override-ini="addopts="
```

## Success Criteria
- [ ] All remaining jurisdictions audited
- [ ] Config gaps fixed (add missing archives)
- [ ] Any bugs found → fixed with tests + data cleanup
- [ ] Roadmap items added for unfixable issues
- [ ] Each audit: update `/audit` report or note findings in jurisdiction YAML

## Known Pending Issues (from roadmap, do not re-discover)
- `simbli_incapsula_bypass` (P2) — 8 school districts bot-blocked
- `diligent_client` (P2) — school-ross-valley, school-marin-county-oe migrated from BoardDocs
- `multi_source_advisory_body_coverage` (P1) — Granicus cities with advisory bodies on CivicPlus (Mill Valley, Novato confirmed)
