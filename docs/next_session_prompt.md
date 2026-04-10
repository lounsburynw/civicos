# Recommended: Index county-marin decision vectors (`index_county_marin_decision_vectors`)

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-04-09

> Recommended context from prior sessions. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

Two sessions ran on 2026-04-09:
1. **Parallel session** completed `complete_alameda_ingest_or_scope` (full ingest — issues, municipal code, audio pipeline). Kicked off Modal transcription for 80 Alameda meetings via AssemblyAI free tier.
2. **Main session** completed `fairfax_cortemadera_video_discovery` — populated video_url for Fairfax (0→16) and Corte Madera (0→12) via YouTube channel/playlist discovery. Added `--channel` and `--backfill` modes to youtube.py CLI.

county-marin has 105 decisions in storage but **0 decision vectors indexed**. Semantic search on county-marin decisions returns nothing — a gap given county-marin is the heaviest-content jurisdiction (49,505 chunks, 2,976 muni_code entries).

## Key Files

- `scripts/modal_ingest.py` — Modal vector indexing orchestration
- `packages/civicos-extraction/src/civicos_extraction/cli/vectors.py` — Vector indexing CLI
- `data/jurisdictions/county-marin.yaml` — county-marin config

## Suggested Approach

1. **Verify the gap**:
   ```bash
   civicos-env/bin/python3 -c "
   from dotenv import load_dotenv; load_dotenv()
   from civicos import CivicOS
   c = CivicOS('county-marin')
   print('Decisions:', c.storage.get_decision_count('county-marin'))
   print('Decision vectors:', c.vectors.count('county-marin', corpus_type='decisions'))
   "
   ```

2. **Run vector indexing** (local or Modal):
   ```bash
   # Local (~5-10 min for 105 decisions):
   civicos-env/bin/python3 -c "
   from dotenv import load_dotenv; load_dotenv()
   from civicos_extraction.cli.vectors import run_vector_indexing
   run_vector_indexing('county-marin', corpus_type='decisions', provider_type='fastembed')
   "

   # Or via Modal:
   modal run scripts/modal_ingest.py --vectors --jurisdiction county-marin
   ```

3. **Verify** vectors were created, then check other jurisdictions for similar gaps via `/vector-coverage`

4. **Mark done** in launch.json, promote new P0

## Also Check: Alameda Transcription Status

The parallel session kicked off Modal transcription for county-alameda (80 meetings). Check completion:
```bash
civicos-env/bin/python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
c = CivicOS('county-alameda')
print(f'Transcripts: {c.storage.get_transcript_count(\"county-alameda\")}')
"
```

If still 0, re-run:
```bash
modal run scripts/modal_ingest.py --transcripts --jurisdiction county-alameda --transcripts-since 2026-01-01 --transcripts-cost-cap 100
```

## New YouTube Discovery Tool

This session added reusable commands for future jurisdictions:
```bash
civic-extract youtube --jurisdiction city-X --channel     # Discover + store + backfill video_url
civic-extract youtube --jurisdiction city-X --backfill    # Just sync video_url from videos table
```
Works for any jurisdiction with `data_sources.transcripts.channel_id` or `playlist_id` in its YAML config.

## Success Criteria

- [ ] county-marin decision vectors indexed (~105 vectors)
- [ ] Verify county-alameda transcription completed (or re-run if failed)
- [ ] `index_county_marin_decision_vectors` marked done in launch.json
- [ ] New P0 promoted

## Open PRs

None.
