# Recommended: Continue Jurisdiction QC Walkthrough

**Priority:** P0
**Area:** election_integration / data quality
**Date:** 2026-04-17

> Recommended context from prior session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Manual QC walkthrough of 24 ingested jurisdictions against live municipal websites. Goal: verify ingested data is accurate, up-to-date, and complete before launch. Completed **13/~18 so far** and uncovered **7 significant bugs**, all fixed:

1. **ProudCity P.M. regex** (`9c0c12c0`) — "6:00 P.M." dotted format not matched
2. **Phantom version bloat from tz mismatch** (`7e42ca84`) — naive string comparison on tz-aware Granicus dates
3. **CivicPlus AMID discovery** (`35d91023`+`df4656e9`) — single-hit probe taken as authoritative list
4. **BoardDocs unbounded fetch** — added `days_past=90` guard
5. **Ross mixed-client stale rows** (`e878fb33`) — domain migration + playwright_llm commit
6. **Granicus Spanish Audio Files** (`508db7eb`) — Marin's translation-audio section ingested as meetings
7. **Granicus default_view skipped + times dropped** (`8261cd4c`) — upcoming meetings + TAM missing; "MM/DD/YY - HH:MM AM/PM" stripped to midnight

Plus SF QC documented (3 follow-ups) and `expand_granicus_discovery` logged as P2 roadmap item.

## Recommended Task

Continue jurisdiction-by-jurisdiction walkthrough. **Next jurisdiction: city-berkeley.**

### Completed (13)
san-rafael, mill-valley, san-anselmo, sausalito, fairfax, corte-madera, novato, belvedere, tiburon, larkspur, ross, county-marin, city-san-francisco

### Remaining (~14)
- **Cities/Counties:** city-berkeley (next), county-alameda
- **Schools (11):** kentfield, larkspur-corte-madera, marin-county-oe, mill-valley-sd, miller-creek, novato, reed-union, ross-valley, san-rafael, sausalito-marin-city, tamalpais
- **Other:** college-marin, county-sonoma, state-california

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py:774` — `discover_view_ids()` (probes 1-50, stops at 5 consecutive empties)
- `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py:466` — `_parse_date()` (now preserves time from "MM/DD/YY - HH:MM AM/PM")
- `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py:558` — `get_events()` (always fetches default_view_id alongside archives)
- `packages/civicos-extraction/tests/test_granicus.py` — 45 tests, all passing
- `data/extraction/city-berkeley.json` — archives=[2, 5], default=2

## Suggested Approach (per jurisdiction)

1. Query DB counts by meeting_type + source_platform (look for variant duplicates and mixed clients)
2. WebFetch live municipal website; diff against configured archives
3. If pattern bug found → fix client + add test + note DB cleanup risk separately
4. If coverage gap found → consider running `expand_granicus_discovery` pass (P2 launch item)
5. Document findings in launch.json QC notes + `claude-progress.txt`

Expect 3-5 jurisdictions per session. Schools often Simbli-blocked — verify, note, move on.

## Tests to Run

```bash
civicos-env/bin/python3 -m pytest packages/civicos-extraction/tests/test_granicus.py -v --override-ini="addopts="
civicos-env/bin/python3 -m pytest packages/civicos-extraction/tests/test_proudcity.py -v --override-ini="addopts="
```

## Success Criteria

- [ ] All remaining jurisdictions audited
- [ ] Config gaps fixed (add missing archives via `expand_granicus_discovery` when relevant)
- [ ] Any bugs found → fixed with tests + documented cleanup
- [ ] Roadmap items added for unfixable issues

## Known Pending Items (from roadmap — do not re-discover)

- `simbli_incapsula_bypass` (P2) — 8 school districts bot-blocked
- `diligent_client` (P2) — school-ross-valley, school-marin-county-oe migrated from BoardDocs
- `multi_source_advisory_body_coverage` (P1) — Granicus cities with CivicPlus advisory bodies
- `expand_granicus_discovery` (P2) — new this session: probe view_ids beyond 1-50 + add missing bodies (SF-specific list but likely applies to Berkeley/Alameda)

## Follow-ups Documented in Launch QC Notes (not launch blockers)

1. `universal.py:461-474` meeting_type inference broken; same bug also hits `playwright_llm`
2. Meeting disappearance detection not wired into refresh pipeline
3. county-marin: 30 stale `granicus-playwright-v1` rows with 11.8k chunks — migration decision pending
4. county-marin: BOS titles are year folders ("Board of Supervisors 2025") — needs AgendaViewer drill-down
5. SF: 44 stale playwright_llm rows with 992 unique chunks + 177 unique decisions; cleanup needs re-extraction under granicus IDs first
6. SF: 14+ advisory bodies missing from config — covered by `expand_granicus_discovery`

## Open PRs

None (verified via `gh pr list` at end of 2026-04-17 session).
