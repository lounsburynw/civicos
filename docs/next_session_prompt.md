# Recommended: Onboard San Anselmo

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-03-11

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Mill Valley was successfully onboarded as the first federation test jurisdiction. Two code fixes were made to the Granicus parser during onboarding:

1. **Platform detection** now tries view_ids 1-5 (was only trying 1)
2. **Agenda link extraction** now scans cells for URL patterns (AgendaViewer, MinutesViewer) when column headers are empty

These fixes should make San Anselmo's onboarding smoother — it's the same platform (Granicus), same county (Marin). This validates that the fixes are general, not Mill Valley-specific.

## Recommended Task

Run `/onboard` for San Anselmo. The flow should be faster now:

1. Find San Anselmo's Granicus subdomain (try `sananselmo.granicus.com`, `cityofsananselmo.granicus.com`, or search)
2. Run `onboard_jurisdiction(url, 'city-san-anselmo')`
3. Review and fix body names in extraction config
4. Create jurisdiction YAML, registry entries, aliases
5. Ingest meetings and run agenda extraction
6. Compare friction against Mill Valley friction log — are the fixes working?

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/onboard.py` — Onboarding orchestration
- `packages/civicos-extraction/src/civicos_extraction/platform_detection.py` — Fixed detection
- `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py` — Fixed parser
- `docs/internal/onboarding-friction-log.md` — Mill Valley friction log (compare against)
- `data/extraction/city-mill-valley.json` — Example extraction config
- `data/jurisdictions/city-mill-valley.yaml` — Example jurisdiction YAML

## Mill Valley Results (for comparison)

| Metric | Mill Valley |
|--------|-------------|
| Meetings | 56 |
| With agenda | 53 |
| Agenda items | 310 |
| Bodies | City Council, Planning, Parks & Rec |
| Errors | 3 (empty Granicus pages) |
| Friction points | 7 |

## Tests to Run

```bash
# Granicus parser tests (should still pass)
pytest packages/civicos-extraction/tests/test_granicus.py -q --override-ini="addopts="

# Verify both jurisdictions work
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
for j in ['city-mill-valley', 'city-san-anselmo']:
    c = CivicOS(j)
    meetings = c.storage.get_meetings(j)
    print(f'{j}: {len(meetings)} meetings')
"
```

## Success Criteria

- [ ] San Anselmo added to all registries
- [ ] Meetings and agenda items ingested
- [ ] Friction log updated with San Anselmo comparison
- [ ] Fewer friction points than Mill Valley (fixes working)
- [ ] No regressions in San Rafael or Mill Valley data

## Recent Completions

- **Mill Valley onboarded** (this session) — 56 meetings, 310 agenda items, 7 friction points documented
- **Granicus parser fixes** — Detection tries view_ids 1-5, URL pattern fallback for agenda links
- **Friction log** — `docs/internal/onboarding-friction-log.md`
