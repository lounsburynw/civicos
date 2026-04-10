# Recommended: Index county-marin decision vectors (`index_county_marin_decision_vectors`)

**Priority:** P0
**Area:** federation_testbed
**Date:** 2026-04-09

> Recommended context from prior session. Review and decide whether to accept, modify, or `/start` for fresh prioritization.

## Context

The previous session completed `complete_alameda_ingest_or_scope` (Path A: full ingest). county-alameda now has issues (1,498), municipal code (2,997 sections), and all vectors indexed. Transcription for 80 2026 meetings is running on Modal via AssemblyAI free tier.

county-marin has 105 decisions in storage but **0 decision vectors indexed**. This means semantic search on county-marin decisions returns nothing — a gap given county-marin is the heaviest-content jurisdiction (49,505 chunks, 2,976 muni_code entries).

## The Problem

```
county-marin decisions: 105 stored, 0 indexed
```

The fix is straightforward: run vector indexing for the decisions corpus on county-marin.

## Key Files

- `packages/civicos-extraction/src/civicos_extraction/cli/vectors.py` — Vector indexing CLI
- `scripts/modal_ingest.py` — Modal orchestration (for cloud indexing)
- `data/jurisdictions/county-marin.yaml` — county-marin config

## Suggested Approach

1. **Verify the gap**: `python3 -c "from dotenv import load_dotenv; load_dotenv('.env'); from civicos import CivicOS; c = CivicOS('county-marin'); print('Decisions:', c.storage.get_decision_count('county-marin')); print('Decision vectors:', c.vectors.count('county-marin', corpus_type='decisions'))"`

2. **Run vector indexing** (either locally or on Modal):
   ```bash
   # Local (fastembed, CPU, ~5-10 min for 105 decisions):
   python3 -c "
   from dotenv import load_dotenv; load_dotenv('.env')
   from civicos_extraction.cli.vectors import run_vector_indexing
   run_vector_indexing('county-marin', corpus_type='decisions', provider_type='fastembed')
   "

   # Or via Modal:
   modal run scripts/modal_ingest.py --vectors --jurisdiction county-marin
   ```

3. **Verify**: Re-run the gap check from step 1

4. **Check other jurisdictions** for similar gaps — run `/data-status` or `/vector-coverage` across federation testbed jurisdictions

## Also Check: Alameda Transcription Status

The previous session kicked off Modal transcription for county-alameda (80 2026 meetings). Check if it completed:

```bash
# Check transcript count
python3 -c "
from dotenv import load_dotenv; load_dotenv('.env')
from civicos import CivicOS
c = CivicOS('county-alameda')
print(f'Transcripts: {c.storage.get_transcript_count(\"county-alameda\")}')
"

# If still 0, check Modal logs:
modal app logs civicos-ingest
```

If transcription failed, the likely cause is the Granicus audio download step. The httpx resolver fix (commit `f07d2978`) should handle it, but Modal may have cached a stale image. Re-run with:
```bash
modal run scripts/modal_ingest.py --transcripts --jurisdiction county-alameda --transcripts-since 2026-01-01 --transcripts-cost-cap 100
```

## Code Fixes from This Session

These are already committed (`f07d2978`) but worth knowing:
- **store_issues() batch dedup** — SeeClickFix pagination overlap caused PK violations
- **Alameda County Municode mapping** — product is "Code of Ordinances" not "Municipal Code"
- **Granicus URL resolvers** — switched from urllib to httpx (SSL cert fix)

## Tests to Run

```bash
# Smoke tests
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] county-marin decision vectors indexed (105 decisions → ~105 vectors)
- [ ] Verify county-alameda transcription completed (or re-run if failed)
- [ ] Check for vector gaps in other federation testbed jurisdictions
- [ ] `index_county_marin_decision_vectors` marked done in launch.json
- [ ] New P0 promoted

## Open PRs

None.
