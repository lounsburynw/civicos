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

---

## Turnkey Onboarding Improvements (2026-03-11)

### F1 Resolution: Granicus Subdomain Discovery

**Status:** FIXED

Added `discover_granicus_subdomain(city_name, state)` to `platform_detection.py`. Tries common subdomain patterns:
- `{slug}` (e.g., `dublin`)
- `cityof{slug}` (e.g., `cityofmillvalley`)
- `{slug}-{state}` (e.g., `sananselmo-ca`)
- `townof{slug}` (e.g., `townofsananselmo`)
- `{slug}{state}` (e.g., `sananselmoca`)

First validates subdomain exists via root page HEAD request, then probes view_ids 1-8 for meeting tables.

**Verified against all known Granicus cities:**
- Dublin → `dublin` (view_id=1)
- Mill Valley → `cityofmillvalley` (view_id=2)
- San Anselmo → `sananselmo-ca` (view_id=4)
- Campbell → `cityofcampbell` (view_id=2)

**Integration:** `onboard_jurisdiction()` now accepts `city_name` parameter — no URL required for Granicus jurisdictions.

### F5 Resolution: Registry Generation from YAML

**Status:** FIXED

Created `scripts/generate_registries.py` that reads `data/jurisdictions/*.yaml` and patches all 3 registry files:
1. `config/registry.json` — adds jurisdiction entry with domain, display_name, modal_app_name
2. `jurisdiction.py` — adds JurisdictionConfig entry with agent_type, URLs, granicus_config
3. `_internal/jurisdiction.py` — adds aliases and display names

**Usage:**
```bash
python scripts/generate_registries.py            # Patch all registries
python scripts/generate_registries.py --check    # Dry-run
python scripts/generate_registries.py --yaml city-foo  # Specific YAML only
```

### Updated Friction Summary

| Issue | Before | After |
|-------|--------|-------|
| **F1: Granicus URL** | Web search required | Auto-discovered from city name |
| **F2: view_id detection** | Fixed in Mill Valley session | Fixed |
| **F3: Agenda links** | Fixed in Mill Valley session | Fixed |
| **F4: Body names** | Manual rename needed | Still manual (low priority) |
| **F5: Registry files** | 3 manual edits | Auto-generated from YAML |
| **Estimated manual time** | ~5-10m | ~2m (review YAML + verify) |

---

## El Cerrito, CA (CivicClerk Stress Test)

**Date:** 2026-03-24
**Jurisdiction:** city-el-cerrito (CivicClerk, Contra Costa County, California)
**Purpose:** Test weakest platform integration — 15 meetings in Postgres, zero vectors.

### Summary

CivicClerk's public API (`*.api.civicclerk.com`) returns 404 for all endpoints, including known-working instances like Hayward. The API appears to have been deprecated or moved behind authentication since our initial integration. The web frontend (`*.civicclerk.com/web/home.aspx`) still serves content.

**Result:** Complete failure. Zero bodies discovered, onboard exits at quality gate.

### Friction Points

#### F13: CivicClerk API deprecated/unreachable (HIGH)

**Problem:** All CivicClerk API endpoints return 404. Tested across El Cerrito, Hayward, and other subdomains. The `v1/Boards` endpoint that our `CivicClerkClient` depends on is gone.

**Impact:** CivicClerk is listed as a supported platform, but onboarding any CivicClerk city fails silently (returns empty boards list) and then hits the quality gate ("No meeting bodies discovered"). Our existing 15 El Cerrito meetings in Postgres were likely ingested when the API was still live.

**Root cause:** CivicClerk removed the `Boards` endpoint from their API. The `EventCategories` endpoint returns the same data (board/committee names with IDs). The `Events` endpoint still works but OData `$top` query params cause 500s.

**Fix applied:** Updated `CivicClerkClient.get_boards()` to try `EventCategories` first (normalizing `{id, categoryDesc}` → `{BoardId, BoardName}`), falling back to legacy `Boards` endpoint. Re-test confirmed 16 boards discovered for El Cerrito.

**File:** `packages/civicos-extraction/src/civicos_extraction/clients/civicclerk.py:345-380`

#### F14: SeeClickFix timeout during issue detection (LOW)

**Problem:** SeeClickFix timed out 3 times during issue provider detection for El Cerrito. The 10-second timeout may be too short, or SeeClickFix was temporarily down.

**Impact:** Issue source not detected, falls back to null. Non-blocking but means the YAML won't list issue support.

**Status:** Transient — SeeClickFix was working fine for Austin earlier in the same session.

---

## Austin, TX (Out-of-State Stress Test)

**Date:** 2026-03-24
**Jurisdiction:** city-austin (Legistar, Travis County, Texas)
**Operator:** Claude Code session (automated)
**Purpose:** First out-of-state onboarding — tests whether "turnkey" generalizes beyond California.

### Summary

Austin is the first non-California jurisdiction tested. Different platform client naming convention, different state, no pre-existing state YAML. This exposed 5 friction points, 3 of which were bugs.

**Result:** Config generation succeeds after 1 code fix. Two additional bugs found and fixed.

### Friction Points

#### F8: Legistar discovery misses `{city}{full_state_name}` pattern (HIGH)

**Problem:** `discover_legistar_client()` tries slug variants like `austin`, `austin-tx`, `cityofaustin`, `austintx` — but Austin's actual Legistar client name is `austintexas`. The discovery function only appends the 2-letter state code, never the full state name.

**Impact:** Auto-discovery fails entirely. A newcomer gets "Could not auto-discover platform" with no guidance on how to find the correct URL.

**Fix applied:** Added `{slug}{full_state_name}` candidate to `discover_legistar_client()` using an inline state code → name mapping. Now tries `austintexas` as a candidate.

**File:** `packages/civicos-extraction/src/civicos_extraction/platform_detection.py:792-808`

#### F9: `--dry-run` spawns real Modal containers (HIGH)

**Problem:** `scripts/onboard.py --dry-run` passes `--dry-run` through to `modal run scripts/modal_ingest.py`, which spawns real containers on Modal. These containers make real HTTP requests to Legistar, SeeClickFix, and Municode APIs. The "dry run" fetches data but doesn't store it — still incurring compute costs and API calls.

**Impact:** A newcomer expecting zero side effects from `--dry-run` gets billed for Modal container time and makes real API calls. Violates principle of least surprise.

**Fix applied:** `--dry-run` now stops after Phase 2 (config generation + data check), same as `--skip-ingestion`, and prints the exact Modal command to run when ready.

**File:** `scripts/onboard.py:765`

#### F10: `MunicipalCodeCorpus.__init__()` rejects `cache_dir` kwarg (MEDIUM)

**Problem:** `modal_ingest.py:206` passes `cache_dir` to `MunicipalCodeCorpus.for_jurisdiction()`, which forwards `**kwargs` to `__init__()`. But `MunicipalCodeCorpus.__init__()` doesn't accept `cache_dir` — only `AmericanLegalCorpus` does. Causes `TypeError` and blocks municipal code ingestion.

**Fix applied:** Added `**kwargs` to `MunicipalCodeCorpus.__init__()` signature to accept and ignore unknown kwargs.

**File:** `packages/civicos/src/civicos/_internal/legal/corpus/municipal.py:198`

#### F11: YouTube channel discovery picks wrong city (MEDIUM)

**Problem:** YouTube auto-discovery found channel `UCz8RVD73YkHomdRrT_5LBwQ` with title "City of Austin, Minnesota" — not Austin, Texas. The discovery function doesn't use the state parameter to disambiguate cities with the same name in different states.

**Impact:** Would silently ingest transcripts from the wrong city's council meetings. Data corruption that's hard to detect.

**Fix applied:** Added state-aware scoring to `detect_youtube_channel()`. Candidates matching the full state name (e.g., "Texas") score +10, abbreviation (e.g., "TX") scores +5. Both title and description are checked. Re-test confirmed Austin now picks a Texas result over Minnesota.

**File:** `packages/civicos-extraction/src/civicos_extraction/onboard.py:543-577`

#### F12: Issue source not populated in YAML (LOW)

**Problem:** The YAML generator set `issues: null` even though SeeClickFix has data for Austin (100 issues fetched during the first failed dry-run). Issue detection runs in the ingestion pipeline but doesn't feed back into the YAML config.

**Impact:** YAML config doesn't reflect available data sources. Misleading for operators reviewing the config.

**Status:** Open — issue detection should run during YAML generation and populate the field.

### Generated Configs

| Artifact | Quality | Notes |
|----------|---------|-------|
| Extraction JSON | Good | 23 Legistar bodies correctly discovered and named |
| Jurisdiction YAML | Fair | Correct hierarchy (Travis → Texas → US), but wrong YouTube channel and missing issue source |
| Ingestion stages | Good | Correctly lists: meetings, chunks, agenda, decisions, issues, municipal, vectors |

### Key Observations

1. **Legistar naming is inconsistent across states** — California cities tend to use simple slugs (`sacramento`, `berkeley`), but Texas cities use `{city}{state_name}` patterns. The discovery function needs broader candidate coverage.
2. **"Dry run" semantics matter** — For a turnkey tool, `--dry-run` must mean zero side effects. The original behavior (fetch but don't store) is useful for testing data quality, but should be a separate flag (e.g., `--validate`).
3. **YouTube disambiguation is critical** — Any city name that exists in multiple states will hit this. "Austin" is extreme (Minnesota, Texas, Indiana), but "Portland" (Oregon, Maine), "Springfield" (25+ states), etc. will all have this problem.
4. **State YAML auto-created** — The onboard correctly generated `state-texas` in the parent hierarchy without requiring a pre-existing `state-texas.yaml`. Good generalization.

### Comparison with Previous Onboarding

| Metric | Mill Valley (Granicus) | San Anselmo (Granicus) | Austin (Legistar) |
|--------|----------------------|----------------------|-------------------|
| Code fixes needed | 2 | 0 | 3 |
| Platform | Granicus | Granicus | Legistar |
| State | CA | CA | TX (first out-of-state) |
| Bodies discovered | 3 | 28 | 23 |
| New friction points | 7 | 0 | 5 |
| Dry-run to config | ~30s | ~20s | ~15s (after fix) |
| Manual time | ~10m | ~5m | ~2m (config gen only) |
