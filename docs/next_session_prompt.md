# Decision Detail QC — Citizen Panel Findings

**Priority:** P0 (continuation of `extension_ux_parity`)
**Area:** edge_intelligence > browser_extension + MCP handlers
**Date:** 2026-02-16

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Speaker attribution in decision detail was fixed this session. A simulated 4-persona citizen panel (Maria/parent, Harold/retiree, Jade/renter, Ray/business owner) QC'd the `decision_detail` API output across 4 real San Rafael decisions. Average score: **2.1/5**. The housing development decision (4040 Civic Center) scored best at 3.0/5 because it had hard numbers (210 units, 8 stories).

### What Was Fixed This Session

- **Speaker attribution**: `"?"` → real names via 3-tier resolution (per-meeting label map → jurisdiction roster → display fallbacks). Uses existing `Roster` system (`config/rosters/city-san-rafael.json`).
- **Speaker classification**: `is_public_comment` re-classification from text labels (`[Public Speaker N]` → public, `[Staff Member N]` → council).
- **Roster mounting**: `config/rosters/` now deployed to Modal alongside registry.json.

### Before/After Examples

| Decision | Before | After |
|----------|--------|-------|
| SAFE Team | `"?"` | `Dave Spiller`, `Council discussion` |
| City Manager | `"?"` | `Robert Epstein, City Attorney` |
| 4040 Housing | `"?"` | `Council discussion`, `Council/Staff` |

## Remaining QC Issues (Citizen Panel)

These are the top issues cited by 3+ of 4 panelists. Fix in priority order:

### 1. No Context / Synthesized Summary (Critical — all 4 panelists)

Raw transcript fragments leave every persona confused. Nobody understood what the SAFE Team is, what the Housing Study Session discussed, or who was appointed Acting City Manager.

**Fix:** Add an AI-generated 2-3 sentence summary to decision_detail output. This should answer: What is this about? What was decided? Why does it matter? Can reuse the existing `askAI()` / LLM infrastructure. Consider caching summaries to avoid per-request LLM calls.

### 2. Missing Key Facts (Critical — all 4 panelists)

- Acting City Manager: WHO was appointed is never stated
- Housing Study Session: what was actually discussed (RHNA numbers, ADU policy, inclusionary zoning)
- SAFE Team: what the program actually does (mental health crisis response alternative to police)
- All decisions: vote tallies are null (not extracted into decisions table)

**Fix:** Two approaches — (a) extract more structured data during ingestion (votes, appointee names, key facts), or (b) synthesize from transcript context at query time via LLM.

### 3. Testimony Excerpts Are Mid-Sentence Fragments (High — all 4 panelists)

The `_extract_excerpt()` function tries to find relevant sentences, but transcript diarization often produces chunks that start mid-sentence. Harold (retiree): "These quote fragments are mid-sentence snippets that don't explain anything."

**Fix:** Improve excerpt extraction — try to find chunk boundaries that start at sentence beginnings, or use LLM to clean/summarize the excerpt into a coherent statement.

### 4. No Video Links or Timestamps (High — Harold, Ray)

All `video_url` and `start_timestamp` fields are null despite the meeting videos existing on YouTube. The fallback video URL lookup added this session didn't find matches.

**Fix:** Debug the meeting video URL lookup — check if `meetings` table has `video_url` populated and whether the meeting_id join is working. The video IDs are embedded in transcript chunk IDs (e.g., `transcript-NYkGE9nVLUc-42`).

### 5. Related Decisions Are Tangential (Medium — Harold, Jade)

"SAFE Team" → "Lincoln Avenue Safety Improvements" is a keyword match on "safety", not topical. Vector similarity is too shallow for real topic matching.

**Fix:** This is a deeper vector quality issue. Consider adding topic tags to decisions during ingestion, or filtering related decisions to same body/category.

### 6. Outcome Labels Unexplained (Medium — Maria, Jade)

"Adopted", "received", "approved" are unclear to non-civic-jargon speakers.

**Fix:** Add a `outcome_description` field that maps: adopted → "Passed by council vote", received → "Heard but no vote taken", approved → "Approved by council vote", denied → "Rejected by council vote".

## Key Files

**Backend (decision_detail handler):**
- `apps/civicos-mcp/tools/handlers.py` — `decision_detail()`, `_resolve_speaker()`, `_build_meeting_speaker_map()`, `_extract_excerpt()`

**Speaker resolution:**
- `packages/civicos/src/civicos/roster.py` — `Roster.load()`, `find_official()`, alias matching
- `config/rosters/city-san-rafael.json` — officials, aliases, overrides

**Transcript data:**
- `packages/civicos/src/civicos/history.py` — `_search_decision_transcripts_pgvector()`, `TranscriptLink`

**Extension rendering:**
- `apps/civicos-extension/src/side-panel/SidePanel.svelte` — decision detail UI (testimony cards, outcome badges)

## Uncommitted Changes

```bash
git diff --name-only
# apps/civicos-mcp/tools/handlers.py — speaker resolution, roster integration
# apps/civicos-mcp/modal_mcp.py — roster mount
# packages/civicos/src/civicos/history.py — speaker default None (not "?")
```
