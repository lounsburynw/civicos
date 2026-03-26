# Recommended: Simbli District Expansion — Onboard 6 Marin School Districts

**Priority:** P0 (simbli_district_expansion)
**Area:** election_integration
**Date:** 2026-03-26

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Recent sessions completed the election/school-board extraction pipeline: Marin Registrar GraphQL (county results), BoardDocs (5 districts), and CA SOS Results (statewide). Six Marin school districts remain unboarded — they all use Simbli/eBoard (CSBA merged AgendaOnline into GAMUT/Simbli).

The SimbliClient exists and works (Playwright-based, Incapsula WAF). Factory dispatch and onboard discovery are wired. What's missing: extraction config JSONs, Modal ingestion function, and `simbli` added to `SUPPORTED_MEETING_SOURCES`.

## Target Districts

| District | Simbli Code | URL Pattern |
|----------|-------------|-------------|
| Novato USD | S=36030351 | `simbli.eboardsolutions.com/...?S=36030351` |
| Tamalpais Union HSD | S=36030468 | `simbli.eboardsolutions.com/...?S=36030468` |
| Miller Creek SD | TBD | Need to discover via WebSearch |
| Mill Valley SD | TBD | Need to discover via WebSearch |
| Reed Union SD | TBD | Need to discover via WebSearch |
| Kentfield SD | TBD | Need to discover via WebSearch |

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/clients/simbli.py` — SimbliClient (Playwright-based)
- `packages/civicos-extraction/src/civicos_extraction/clients/factory.py:40` — Simbli dispatch exists
- `packages/civicos-extraction/src/civicos_extraction/onboard.py:419` — `_discover_simbli()` discovery
- `packages/civicos-extraction/src/civicos_extraction/clients/__init__.py:117` — `SUPPORTED_MEETING_SOURCES` (simbli NOT listed)
- `data/extraction/san-rafael-schools.json` — SRCS uses YouTube, not Simbli config
- `data/extraction/school-ross-valley.json` — Example BoardDocs config for reference
- `scripts/modal_ingest.py` — No `fetch_simbli_meetings` function yet

## Important Considerations

1. **Playwright requirement:** SimbliClient uses Playwright (Incapsula WAF blocks requests). Modal image needs `playwright install chromium`. Check if `eboardsolutions.com` subdomains also need Playwright or if they're accessible via plain HTTP.

2. **SUPPORTED_MEETING_SOURCES:** `simbli` is not in the frozenset, so the standard `fetch_meetings()` dispatcher won't handle it. Either add it (if the fetch pattern fits) or create a separate `fetch_simbli_meetings()` Modal function.

3. **Onboarding path:** Use `/onboard` with each district's Simbli URL, or manually create configs. The `_discover_simbli()` function exists but is lightweight (just builds config from URL).

4. **Config format:** Simbli configs need `source_type: "simbli"` and `board_url` in metadata. See `factory.py:42` — it reads `metadata.board_url` or falls back to `base_url`.

## Suggested Approach

1. Discover Simbli URLs for the 4 TBD districts (WebSearch `site:simbli.eboardsolutions.com "{district name}"`)
2. Test if `eboardsolutions.com` URLs are accessible via plain HTTP (if so, can skip Playwright)
3. Create extraction config JSONs for all 6 districts in `data/extraction/`
4. Add `simbli` to `SUPPORTED_MEETING_SOURCES` if compatible with standard pipeline, OR write `fetch_simbli_meetings()` Modal function with Playwright image
5. Test extraction against at least 1 district
6. Register jurisdictions in `config/registry.json`

## Tests to Run

```bash
# Existing Simbli tests
pytest packages/civicos-extraction/tests/test_simbli.py -v --override-ini="addopts="
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] 6 Simbli extraction configs created in `data/extraction/`
- [ ] Simbli either added to SUPPORTED_MEETING_SOURCES or has dedicated Modal function
- [ ] At least 1 district successfully fetches meetings
- [ ] Jurisdictions registered in `config/registry.json`
- [ ] No regressions in smoke tests
