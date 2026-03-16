# Recommended: Turnkey Onboard Hardening — Data Quality Verification

**Priority:** P0 (`turnkey_onboard_hardening`)
**Area:** federation_testbed
**Date:** 2026-03-16

> Code work is complete. This session should verify the new code against live data and close out remaining data quality gaps.

## What's been built (ready to verify)

| Feature | Commit | Status |
|---------|--------|--------|
| Validation gate (sample before full backfill) | `519b19a` | Done |
| Cross-view meeting dedup | `519b19a` | Done |
| Post-onboard quality report | `519b19a` | Done |
| Granicus video_url from clip_ids | `a2484f1` | Done — needs live verify |
| HTML chunk extraction fallback | `a2484f1` | Done — needs live verify |
| Decision checkpoint idempotency | `a2484f1` | Done |
| LLM date parsing fallback | `3172a26` | Done |

## Remaining: Data Quality Verification

### 1. Live test HTML chunk extraction (FIRST PRIORITY)
Mill Valley and San Anselmo have 0 chunks because agendas are HTML, not PDF. The new HTML fallback should fix this.

```bash
# Test with a small batch first
civic-extract chunks --jurisdiction city-mill-valley --cloud --limit 5
civic-extract chunks --jurisdiction city-san-anselmo --cloud --limit 5

# Check results
/data-status city-mill-valley
/data-status city-san-anselmo
```

**What to look for:**
- Chunks count > 0 for both jurisdictions
- Chunk text is meaningful (not nav elements, boilerplate, etc.)
- `source_type: html_agenda` in chunk metadata

### 2. Mill Valley decisions quality (2/113 meetings)
81 meetings have `minutes_url` but only 2 decisions were extracted. Need to understand why.

**Manual QC steps:**
- Open a Mill Valley `minutes_url` in browser (e.g., `https://cityofmillvalley.granicus.com/MinutesViewer.php?view_id=2&clip_id=2042`)
- Is the HTML a full minutes document or a sparse summary?
- Compare to San Anselmo minutes (96/171 decisions) — what's different?
- If HTML is too thin, decisions may require video transcription first

**If minutes are genuinely sparse:** This is a data availability issue, not a code bug. Document it and move on.

### 3. Verify Granicus video_url extraction
```python
from dotenv import load_dotenv; load_dotenv()
from civicos.storage import get_storage_backend
backend = get_storage_backend()
meetings = backend.get_meetings('city-mill-valley')
with_video = [m for m in meetings if m.get('video_url')]
print(f"Mill Valley meetings with video_url: {len(with_video)}/{len(meetings)}")
```

If video_urls aren't stored yet, need to re-run meeting extraction to pick up the new `normalize_event()` logic.

### 4. San Rafael agenda items low (1.3/meeting vs 4+)
May be a ProudCity extraction path issue or different meeting composition (fewer committee meetings). Lower priority — investigate if time permits.

## When to close this P0

Mark `turnkey_onboard_hardening` as `done` when:
- [ ] HTML chunks extracted for Mill Valley (count > 0)
- [ ] HTML chunks extracted for San Anselmo (count > 0)
- [ ] Mill Valley decisions gap understood (code fix or documented limitation)
- [ ] Video URLs verified in at least one Granicus jurisdiction

## Key Files
- `packages/civicos-extraction/src/civicos_extraction/cli/chunks.py` — HTML chunk extraction
- `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py` — video_url + LLM date fallback
- `packages/civicos-extraction/src/civicos_extraction/cli/decisions.py` — idempotent checkpoints
- `scripts/onboard.py` — turnkey onboarding with validation gate
