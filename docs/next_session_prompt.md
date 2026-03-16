# Close Marin Data Gaps — Mill Valley & San Anselmo

**Priority:** P0 (override `cross_marin_query_prototype` — gaps must close first)
**Area:** federation_testbed / data_readiness
**Date:** 2026-03-16

> Cross-Marin queries won't be meaningful if two of three jurisdictions have empty corpora. Close the data gaps before moving to query prototype.

## Current State (as of 2026-03-16)

| Corpus | San Rafael (baseline) | Mill Valley | San Anselmo |
|---|---|---|---|
| Meetings | 96 | 113 | 171 |
| Chunks | 7,078 (73.7/mtg) | **601** (5.3/mtg) | **489** (2.9/mtg) |
| Decisions | 83 (0.9/mtg) | **2** (0.0/mtg) | 96 (0.6/mtg) |
| Transcripts | 41 | **0** | **0** |
| Agenda Items | 402 | 476 | 788 |
| Issues | 7,430 | **0** | **0** |
| Municipal Code | 46,663 | **0** | **0** |
| Budget | 58 | **0** | **0** |
| Vectors | 25,426 | **591** | **1,037** |

## Work Items (in priority order)

### 1. Vector Indexing for New Chunks (FIRST — biggest unlock)

601 MV chunks + 489 SA chunks are in Postgres but have zero vector embeddings. No vectors = no semantic search.

```bash
# Index vectors via Modal GPU
modal run scripts/modal_ingest.py --jurisdiction city-mill-valley
modal run scripts/modal_ingest.py --jurisdiction city-san-anselmo
```

Or use `/vectors` slash command. Verify with `/vector-coverage`.

**Done when:** chunk vectors > 0 for both jurisdictions.

### 2. Mill Valley Decisions (2 → ~80)

81 meetings have `minutes_url` but only 2 decisions extracted. Root cause identified:

- Granicus `MinutesViewer.php` returns **302 redirect** to Google Docs viewer
- Google Docs viewer wraps the actual PDF: `DocumentViewer.php?file=cityofmillvalley_*.pdf`
- Our decisions extraction doesn't follow this redirect chain

**Fix approach:**
1. In the decisions CLI, when fetching minutes, follow the redirect chain
2. Extract the actual PDF URL from the Google Docs viewer `gview?url=` parameter
3. Download the PDF directly from `DocumentViewer.php`

**Test:**
```python
import requests, urllib.parse
minutes_url = "https://cityofmillvalley.granicus.com/MinutesViewer.php?view_id=2&clip_id=2042"
resp = requests.get(minutes_url, allow_redirects=False)
# Status 302, Location → Google Docs gview URL
location = resp.headers['location']
# Parse the embedded PDF URL from gview?url=...
parsed = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
actual_pdf = parsed['url'][0]  # DocumentViewer.php?file=...&view=1
# Download the actual minutes PDF
pdf_resp = requests.get(actual_pdf)
# pdf_resp.content starts with %PDF-
```

**Key files:**
- `packages/civicos-extraction/src/civicos_extraction/cli/decisions.py`
- The extraction likely calls a minutes download function — check how it handles redirects

**Done when:** Mill Valley decisions > 20.

### 3. Issues (SeeClickFix)

San Rafael has 7,430 issues. Check if Mill Valley and San Anselmo have SeeClickFix coverage:

```bash
# Check SeeClickFix API for these cities
civic-extract seeclickfix --jurisdiction city-mill-valley --dry-run
civic-extract seeclickfix --jurisdiction city-san-anselmo --dry-run
```

May need to configure SeeClickFix place IDs in jurisdiction YAML files. Check `data/jurisdictions/city-mill-valley.yaml` and `data/jurisdictions/city-san-anselmo.yaml` for `seeclickfix` config.

**Done when:** Issues > 0 for at least one jurisdiction, or documented as "no SeeClickFix coverage."

### 4. Municipal Code

San Rafael has 46,663 sections. Identify sources for MV/SA:

- Mill Valley likely uses Municode or similar
- San Anselmo likely uses Municode or similar
- Check jurisdiction YAML files for `municipal_code` config
- May need to discover the code URL and add to config

```bash
civic-extract municipal-code --jurisdiction city-mill-valley --dry-run
civic-extract municipal-code --jurisdiction city-san-anselmo --dry-run
```

**Done when:** Municipal code > 0 for both, or sources identified and ingestion started.

### 5. Transcripts (if time permits)

Video URLs now available (MV: 106, SA: 132). Transcription pipeline:

```bash
/ingest-audio city-mill-valley 5    # Download 5 YouTube audio files
/ingest-audio city-san-anselmo 5
```

Then transcribe and index. This is the longest pipeline — may span multiple sessions.

## Bugs Fixed This Session (uncommitted)

Three bugs were fixed in the chunk extraction pipeline:

1. **chunk_index duplicate key** — `chunks.py:542` used per-section index instead of global counter. Fixed to use `chunk_idx`. Also fixed `postgres_backend.py:2901` and `sqlite_backend.py:1317` to use loop index.
2. **SSL cert bypass for Granicus S3** — `chunks.py:818-842` added SSLError retry with `verify=False` for `granicus_production_attachments.s3.amazonaws.com` (broken hostname with underscores).
3. **Download failure HTML fallback** — `chunks.py:960-990` now falls back to HTML extraction when PDF download fails entirely.

**Commit before starting new work:**
```bash
git add packages/civicos-extraction/src/civicos_extraction/cli/chunks.py \
       packages/civicos/src/civicos/storage/postgres_backend.py \
       packages/civicos/src/civicos/storage/sqlite_backend.py \
       launch.json claude-progress.txt
git commit -m "fix: Chunk extraction — duplicate key, SSL retry, download fallback"
```

## Key Files

| Component | File |
|-----------|------|
| Chunk extraction CLI | `packages/civicos-extraction/src/civicos_extraction/cli/chunks.py` |
| Decision extraction CLI | `packages/civicos-extraction/src/civicos_extraction/cli/decisions.py` |
| Postgres store_chunks | `packages/civicos/src/civicos/storage/postgres_backend.py:2844` |
| Granicus client | `packages/civicos-extraction/src/civicos_extraction/clients/granicus.py` |
| MV jurisdiction config | `data/jurisdictions/city-mill-valley.yaml` |
| SA jurisdiction config | `data/jurisdictions/city-san-anselmo.yaml` |
| Vector indexing | `scripts/modal_ingest.py` |
| SeeClickFix CLI | `packages/civicos-extraction/src/civicos_extraction/cli/seeclickfix.py` |
| Municipal code CLI | `packages/civicos-extraction/src/civicos_extraction/cli/municipal_code.py` |
