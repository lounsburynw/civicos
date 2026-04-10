# Recommended: Complete SF audio backfill (`sf_audio_backfill`)

**Priority:** P0
**Area:** turnkey_onboarding
**Date:** 2026-04-09

> Recommended context from prior sessions. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

This session completed two items:
1. **county-marin decision vectors** — indexed 105 vectors, all 18 jurisdictions now have full decision vector coverage.
2. **SF video URL discovery** — discovered Granicus video URLs for San Francisco: 6 → 46 out of 57 meetings (80% coverage). Mapped 7 Granicus ViewPublisher views to committee bodies.

## What's Left: Transcription

33 SF meetings now have video_url but no transcripts. The audio pipeline is verified:
- Granicus MP3 resolution works (archive-video.granicus.com)
- Local audio download tested: 328MB MP3 → 122MB opus → R2 upload
- Estimated cost: ~$43 via AssemblyAI (~66 audio hours)

## Key Files

- `data/extraction/city-san-francisco.json` — updated with `granicus_view_map` (view→committee)
- `data/jurisdictions/city-san-francisco.yaml` — updated `transcripts.source: granicus`
- `scripts/modal_ingest.py` — `extract_transcripts()` handles Granicus URLs natively

## Suggested Approach

1. **Run transcription on Modal** (~$43, fits within $50 cost cap):
   ```bash
   modal run scripts/modal_ingest.py --transcripts --jurisdiction city-san-francisco --transcripts-since 2026-01-01 --transcripts-cost-cap 50
   ```

2. **Verify** transcripts were created:
   ```python
   from dotenv import load_dotenv; load_dotenv()
   from civicos import CivicOS
   c = CivicOS('city-san-francisco')
   print(f'Transcripts: {c.storage.get_transcript_count("city-san-francisco")}')
   ```

3. **Index transcript vectors**:
   ```python
   from civicos_extraction.cli.vectors import run_vector_indexing
   run_vector_indexing('city-san-francisco', corpus_type='transcripts', provider_type='fastembed')
   ```

4. **Mark done** in launch.json, promote new P0

## Also Check: Alameda Transcription Status

county-alameda has 257 meetings with video_url but 0 transcripts. A prior session kicked off Modal transcription but it didn't complete. Re-run if still 0:
```bash
modal run scripts/modal_ingest.py --transcripts --jurisdiction county-alameda --transcripts-since 2026-01-01 --transcripts-cost-cap 100
```

## Remaining Video URL Gaps

12 SF meetings still lack video_url (mostly Land Use and Transportation Committee — Granicus view 45 only has 3 recent clips). These videos may not be posted yet. The Granicus view map is stored in the extraction config for future refresh cycles.

## Granicus View Map (for reference)

| View ID | Committee |
|---------|-----------|
| 10 | Board of Supervisors |
| 7 | Budget and Finance Committee |
| 11 | Government Audit and Oversight Committee |
| 13 | Rules Committee |
| 20 | Public Safety and Neighborhood Services Committee |
| 21 | Budget and Appropriations Committee |
| 45 | Land Use and Transportation Committee |

## Success Criteria

- [ ] 30+ SF transcripts created (from 33 meetings with video_url)
- [ ] Transcript vectors indexed
- [ ] `sf_audio_backfill` marked done in launch.json
- [ ] New P0 promoted
- [ ] (Optional) Check/re-run Alameda transcription

## Open PRs

None.
