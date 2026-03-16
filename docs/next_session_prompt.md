# Recommended: Turnkey Onboard Hardening (continued)

**Priority:** P0 (`turnkey_onboard_hardening`)
**Area:** federation_testbed
**Date:** 2026-03-16

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## What was done this session

Committed in `519b19a`:

1. **Validation gate** (Gap 0) — `scripts/onboard.py` now runs a 30-day sample before full 365-day backfill. Quality report with red flag detection against San Rafael baselines. `--no-validate` to skip.
2. **Cross-view dedup** (Gap 2/3) — `granicus.py:get_meetings()` deduplicates by (date, title) across views instead of by ID. Prevents duplicate LLM processing for multi-view Granicus sites like Mill Valley (views 2+3 are mirrors). Test added.
3. **Quality report** (Gap 4) — Post-onboard Phase 4 now auto-generates a quality assessment with ratios (chunks/meeting, agenda_items/meeting, decisions/meeting) compared to baselines, plus actionable red flags.
4. **YAML enrichment** (Gap 6) — Uses `yaml.safe_load()`/`yaml.dump()` instead of fragile string patching.
5. **Slug normalization** (Gap 7) — `re.sub(r"[^a-z0-9]+", "-", ...)` handles special chars consistently.

## What remains (prioritized)

### 1. Granicus video_url extraction (QUICK WIN)
Granicus meetings have `clip_id` in their agenda URLs (e.g., `AgendaViewer.php?view_id=2&clip_id=2042`) but we don't set `video_url` on the Meeting. Mill Valley has ~10 meetings with clip_ids, San Anselmo ~10. Fix: extract clip_id in `normalize_event()` and set `video_url = f"https://{domain}.granicus.com/player/clip/{clip_id}"`. This unblocks transcription/diarization for Granicus cities.

### 2. Mill Valley decisions quality (2/113 meetings)
The MinutesViewer HTML is too thin for the LLM. 81 meetings have `minutes_url` but extraction only found 2 decisions. Need to investigate: is the HTML genuinely sparse, or is the minutes parser not extracting enough content? Manual QC needed (see below).

### 3. HTML chunk extraction for Granicus (Gap 1)
Both Mill Valley and San Anselmo have 0 chunks because agenda URLs point to `AgendaViewer.php` (HTML) not PDFs. The chunk pipeline only handles PDFs. Fix: extract text from HTML agenda pages via BeautifulSoup when no PDF link is found.
- `packages/civicos-extraction/cli/chunks.py:794+` — where PDF is validated
- Affects all Granicus HTML jurisdictions

### 4. Idempotency on re-run (Gap 5)
Re-running onboard may double LLM spend on agenda/decisions. Chunks already have checkpoint tracking. Agenda and decision extraction need similar checkpoint logic.

### 5. San Rafael agenda items seem low (1.3/meeting vs 4+ for Granicus cities)
May be a ProudCity extraction path issue or different meeting composition. Worth investigating.

## Manual QC needed

**Before fixing extraction code, manually inspect the source content** to understand what's actually available:

1. **Mill Valley minutes** — Open a `minutes_url` (e.g., `https://cityofmillvalley.granicus.com/MinutesViewer.php?view_id=2&clip_id=2042`) in a browser. How much actual content is in the HTML? Is it a full minutes document or just a sparse summary?

2. **Mill Valley agenda** — Open an `agenda_url` (e.g., `https://cityofmillvalley.granicus.com/AgendaViewer.php?view_id=2&clip_id=2042`). What does the HTML contain? Are there embedded attachments/PDFs we're missing?

3. **San Anselmo minutes vs Mill Valley** — San Anselmo got 96 decisions from 171 meetings. Compare their minutes HTML to Mill Valley's to understand why the extraction quality differs.

4. **Granicus video** — Visit a clip URL (e.g., `https://cityofmillvalley.granicus.com/player/clip/2042`). Does it play? Is there a direct video/audio download link we can use for transcription?

5. **Spot-check extracted decisions** — The 2 Mill Valley decisions ("$250K Downtown Revitalization", "Zoning Amendment for New Residential Development") — are these real decisions from real meetings, or LLM hallucinations from thin source content?

## Current Data State

| | San Rafael | Mill Valley | San Anselmo |
|---|---|---|---|
| Meetings | 96 | 113 (dupes in DB) | 171 |
| Agenda items | 129 (1.3/mtg) | 476 (4.2/mtg) | 770 (4.5/mtg) |
| Chunks | 7,078 | **0** | **0** |
| Decisions | 83 (0.86/mtg) | **2** (0.02/mtg) | 96 (0.56/mtg) |
| Video URLs | 31 (YouTube) | 0 stored (~10 available) | 0 stored (~10 available) |
| Transcripts | 41 | 0 | 0 |

## Key Files

- `scripts/onboard.py` — turnkey script with validation gate + quality report
- `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py:488` — `normalize_event()` (add video_url here)
- `packages/civicos-extraction/cli/chunks.py:794+` — PDF validation (HTML extraction goes here)
- `scripts/modal_ingest.py` — ingestion pipeline orchestration

## Success Criteria

- [x] Validation gate before full backfill
- [x] Cross-view meeting deduplication
- [x] Post-onboard quality report with red flags
- [ ] Granicus video_url extracted from clip_ids
- [ ] Manual QC on Mill Valley minutes/decisions content
- [ ] Mill Valley chunks > 0 (HTML agenda extraction)
- [ ] Idempotent re-runs (agenda/decision checkpoints)
- [ ] `cross_marin_query_prototype` (P1) unblocked with quality data
