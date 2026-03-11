# Recommended: Turnkey Onboarding

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-03-11

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Three Marin County jurisdictions are now onboarded (San Rafael, Mill Valley, San Anselmo). Onboarding friction dropped 57% between Mill Valley and San Anselmo, but 3 friction points still require manual work every time:

- **F1 (HIGH):** Granicus subdomain not guessable — requires web search (e.g., `sananselmo-ca.granicus.com`, `cityofmillvalley.granicus.com`)
- **F5 (MEDIUM):** Three registry files need manual edits per jurisdiction

Fixing these makes onboarding nearly zero-touch: provide a city name, get everything generated.

## Recommended Task

### Part 1: Granicus Subdomain Discovery (F1)

Add pattern-based subdomain discovery to `onboard_jurisdiction()`. Try common patterns before requiring manual URL:

- `{city}.granicus.com` (e.g., `millvalley`)
- `cityof{city}.granicus.com` (e.g., `cityofmillvalley`)
- `{city}-{state}.granicus.com` (e.g., `sananselmo-ca`)
- `{city}{state}.granicus.com` (e.g., `sananselmoca`)

Test each with a HEAD request to `ViewPublisher.php?view_id=1` through `view_id=8`. First 200 response wins.

### Part 2: Registry Generation from YAML (F5)

Currently 3 files need manual edits per jurisdiction:
1. `config/registry.json` — service routing
2. `packages/civicos-config/src/civicos_config/jurisdiction.py` — JurisdictionRegistry
3. `packages/civicos/src/civicos/_internal/jurisdiction.py` — aliases

Generate all three from the jurisdiction YAML (`data/jurisdictions/{id}.yaml`). Options:
- **A)** Build script that reads YAMLs and writes/patches the three files
- **B)** Runtime loader that reads YAMLs directly (eliminates static files)
- **C)** `onboard_jurisdiction()` generates the YAML and patches registries as part of its flow

Option C is probably best — keeps the existing static files but automates their creation.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/onboard.py` — `onboard_jurisdiction()` entry point
- `packages/civicos-extraction/src/civicos_extraction/platform_detection.py:206-228` — Granicus detection (tries view_ids 1-5)
- `config/registry.json` — Service routing (see `city-san-anselmo` entry for pattern)
- `packages/civicos-config/src/civicos_config/jurisdiction.py:109-138` — JurisdictionRegistry (see `san_anselmo` and `mill_valley` entries)
- `packages/civicos/src/civicos/_internal/jurisdiction.py:55-65` — Aliases dict
- `data/jurisdictions/city-san-anselmo.yaml` — Example jurisdiction YAML (has all needed fields)
- `data/jurisdictions/city-mill-valley.yaml` — Another example
- `docs/internal/onboarding-friction-log.md` — Full friction documentation

## Tests to Run

```bash
# Granicus parser tests
pytest packages/civicos-extraction/tests/test_granicus.py -q --override-ini="addopts="

# Verify all jurisdictions still work after registry changes
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
for j in ['city-san-rafael', 'city-mill-valley', 'city-san-anselmo']:
    c = CivicOS(j)
    meetings = c.storage.get_meetings(j)
    print(f'{j}: {len(meetings)} meetings')
"
```

## Success Criteria

- [ ] `onboard_jurisdiction("San Anselmo, CA")` (or similar) finds Granicus URL without manual search
- [ ] Registry entries generated automatically (registry.json, JurisdictionRegistry, aliases)
- [ ] Existing jurisdictions unaffected (San Rafael, Mill Valley, San Anselmo all still work)
- [ ] Friction log updated with improvements

## Recent Completions

- **San Anselmo onboarded** — 169 meetings, 564+ agenda items, 28 body types, 0 code fixes needed
- **Mill Valley onboarded** — 56 meetings, 310 agenda items, 2 code fixes (now generalized)
- **Friction log** — `docs/internal/onboarding-friction-log.md` with Mill Valley vs San Anselmo comparison
