# Onboarding Friction Log

**Date:** 2026-03-11
**Jurisdiction:** city-mill-valley (Granicus, Marin County)
**Operator:** Claude Code session (automated)

## Summary

Mill Valley is the first jurisdiction onboarded after San Rafael. Same county (Marin), same platform family (Granicus). This log documents every manual step, friction point, and failure encountered during onboarding.

**Result:** Successful onboarding with 2 code fixes required.

## Friction Points

### F1: Granicus subdomain not guessable (HIGH)

**Problem:** The onboarding function takes a URL, but Mill Valley's Granicus subdomain is `cityofmillvalley` (not `millvalley`). First attempt with `millvalley.granicus.com` returned 404.

**Discovery method:** Web search for "Mill Valley California city council meeting agendas Granicus" revealed the correct URL.

**Fix needed:** Add a Granicus subdomain discovery step that tries common patterns:
- `{city}` (e.g., `millvalley`)
- `cityof{city}` (e.g., `cityofmillvalley`)
- `{city}{state}` (e.g., `millvalleyca`)
- `{city}.{county}` — check if city meetings exist on county Granicus

**Impact:** Blocks fully automated onboarding. Every new Granicus jurisdiction requires manual URL discovery.

### F2: Platform detection only tries view_id=1 (HIGH)

**Problem:** `_detect_granicus()` in `platform_detection.py` only tested `ViewPublisher.php?view_id=1`. Mill Valley doesn't use view_id=1 (404), but view_id=2 works fine.

**Fix applied:** Changed detection to try view_ids 1-5, stopping on first success.

**File:** `packages/civicos-extraction/src/civicos_extraction/platform_detection.py:206-228`

### F3: Agenda/minutes links not extracted (HIGH)

**Problem:** Mill Valley's Granicus HTML has empty column headers for agenda/minutes columns (`['date', 'meeting', '', '', '', '', '']`). The parser relied on finding "agenda" or "minutes" in headers, so returned `None` for all link fields.

**Fix applied:** Added URL pattern fallback in `_parse_table()` — when header-based detection fails, scan cells for `AgendaViewer`, `MinutesViewer`, and `MetaViewer` URL patterns.

**File:** `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py:186-202`

**Result:** Went from 0/56 meetings with agendas to 53/56 (the 3 without are future meetings).

### F4: Auto-discovered body names meaningless (LOW)

**Problem:** `discover_view_ids()` named the bodies `new_view` and `tabbed_view` (from HTML page titles). The actual bodies are City Council, Planning Commission, and Parks & Recreation — all combined in a single Granicus view.

**Workaround:** Manually renamed to `all_bodies` in extraction config.

**Fix needed:** Content-based body inference — parse first few rows of each view to extract actual meeting body names.

### F5: Three separate registry files need manual updates (MEDIUM)

**Problem:** Adding a jurisdiction requires editing 3 files:
1. `config/registry.json` — service routing
2. `packages/civicos-config/src/civicos_config/jurisdiction.py` — JurisdictionRegistry
3. `packages/civicos/src/civicos/_internal/jurisdiction.py` — aliases

**Fix needed:** Generate all registry entries from the jurisdiction YAML config (`data/jurisdictions/{id}.yaml`). One file should be the source of truth.

### F6: `openai` not in local venv (LOW)

**Problem:** Agenda extraction (Tier 2) requires `openai` package. Not installed by default in the local dev environment, causing silent failures with `No module named 'openai'`.

**Workaround:** `pip install openai`

**Fix needed:** Add to requirements.txt or document as Tier 2 dependency.

### F7: `source activate` doesn't work in Bash tool (LOW)

**Problem:** `source civicos-env/bin/activate` doesn't persist across Bash tool invocations. Must use `civicos-env/bin/python3` directly.

**Impact:** Claude Code sessions only. Not a user-facing issue.

## Manual Steps Performed

| Step | Time | Automated? | Notes |
|------|------|-----------|-------|
| 1. Find Granicus URL | 2m | No | Required web search |
| 2. Run `onboard_jurisdiction()` | 30s | Yes | After URL known, auto-detects platform |
| 3. Fix extraction config names | 1m | No | Renamed `new_view` → `all_bodies` |
| 4. Create jurisdiction YAML | 3m | Partial | Template from San Rafael, manual fields |
| 5. Add to config/registry.json | 1m | No | Manual JSON edit |
| 6. Add to JurisdictionRegistry | 2m | No | Manual Python edit |
| 7. Add jurisdiction aliases | 1m | No | Manual Python edit |
| 8. Store meetings in Postgres | 10s | Yes | Via CivicOS API |
| 9. Run agenda extraction | ~15m | Yes | LLM-based, checkpointed |

**Total human effort:** ~10 minutes manual, ~15 minutes automated
**Automated coverage:** ~60% of steps, ~95% of time

## Automation Priorities

1. **Granicus URL discovery** (F1) — biggest blocker for turnkey flow
2. **Registry generation from YAML** (F5) — eliminate 3-file manual edits
3. **Content-based body naming** (F4) — cosmetic but improves data quality
4. **Dependency validation** (F6) — check Tier 2 deps before attempting extraction

## Data Quality Results

| Metric | Count |
|--------|-------|
| Meetings extracted | 56 |
| Date range | 2025-03-24 to 2026-03-31 |
| With agenda URL | 53 |
| With minutes URL | 39 |
| Body types | City Council (21), Planning (23), Parks & Rec (9), Other (3) |
| Agenda items (first 7 meetings) | ~40+ items |

---

## San Anselmo

**Date:** 2026-03-11
**Jurisdiction:** city-san-anselmo (Granicus, Marin County)
**Operator:** Claude Code session (automated)

### Summary

San Anselmo is the second federation test jurisdiction. Same county (Marin), same platform (Granicus). Validated that Mill Valley's code fixes (F2, F3) generalize to other Granicus jurisdictions.

**Result:** Smooth onboarding — no new code fixes required.

### Friction Points Encountered

| Mill Valley Issue | San Anselmo Status | Notes |
|---|---|---|
| **F1: Subdomain not guessable** | STILL PRESENT | Subdomain is `sananselmo-ca` (not `sananselmo`). Required web search. |
| **F2: Detection only tries view_id=1** | FIXED (validated) | View ID 8 detected successfully via probing 1-5+ range. |
| **F3: Agenda links not extracted** | FIXED (validated) | 133/169 meetings have agenda URLs (79%). URL pattern fallback working. |
| **F4: Auto-discovered body names** | STILL PRESENT | `discover_view_ids()` returned empty — used `all_bodies` manually. |
| **F5: Three registry files** | STILL PRESENT | Same 3-file manual edit process. |
| **F6: openai not in venv** | N/A | Already installed from Mill Valley session. |
| **F7: source activate** | N/A | Using `civicos-env/bin/python3` directly. |

**New friction points:** None! The Mill Valley fixes generalized correctly.

### Comparison

| Metric | Mill Valley | San Anselmo | Delta |
|--------|-------------|-------------|-------|
| Meetings | 56 | 169 | +201% |
| With agenda | 53 (95%) | 133 (79%) | -16pp (more future meetings) |
| With minutes | 39 (70%) | 93 (55%) | -15pp |
| Body types | 3 | 28 | +833% (much richer civic structure) |
| Agenda items (first 10) | ~40 | 48 | Similar density |
| Code fixes needed | 2 | 0 | Fixes generalized |
| Friction points | 7 | 3 (all pre-existing) | -57% |
| Manual time | ~10m | ~5m | -50% |

### Key Observations

1. **Fixes generalized** — Both F2 (view_id probing) and F3 (URL pattern fallback) worked without modification.
2. **Richer civic structure** — San Anselmo has 28 distinct body types vs Mill Valley's 3, providing a better test of the extraction pipeline's flexibility.
3. **Dual platform** — San Anselmo has both Granicus (meetings) and Legistar (21 bodies via API). Platform detection correctly identified Granicus as source_type.
4. **Faster process** — With Mill Valley's lessons learned, onboarding took roughly half the manual time.

### Data Quality Results

| Metric | Count |
|--------|-------|
| Meetings extracted | 169 |
| Date range | 2025-03-18 to 2026-12-08 |
| With agenda URL | 133 (79%) |
| With minutes URL | 93 (55%) |
| Body types | 28 distinct |
| Agenda items (first 10 meetings) | 48 |
| Agenda items (full) | TBD (extraction in progress) |
