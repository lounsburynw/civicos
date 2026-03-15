# Data Ingestion

An empty CivicOS instance returns empty results. This guide walks you through the complete ingestion pipeline — from registering a new jurisdiction to verifying data with semantic search.

## The Pipeline

All extractors follow a 4-stage pattern:

```
FETCH → NORMALIZE → VALIDATE → STORE → INDEX
```

1. **Fetch** — Pull raw data from a platform API or website (Legistar, Granicus, ProudCity, etc.)
2. **Normalize** — Convert platform-specific formats to CivicOS schemas (meetings, decisions, transcripts, etc.)
3. **Validate** — Check against JSON schema definitions
4. **Store** — Persist to PostgreSQL via the storage backend (never raw SQL)
5. **Index** — Generate vector embeddings for semantic search (pgvector)

```
┌─────────────────┐
│   Data Sources   │
│                  │
│  City Websites   │
│  Government APIs │──────┐
│  Agenda PDFs     │      │
│  YouTube Video   │      │
└─────────────────┘      │
                          v
                 ┌──────────────────┐
                 │ civicos-extraction│
                 │ (platform parsers)│
                 │ Legistar, Granicus│
                 │ ProudCity, ...    │
                 └────────┬─────────┘
                          │
            ┌─────────────┼─────────────┐
            v             v             v
     ┌────────────┐ ┌──────────┐ ┌───────────┐
     │ PostgreSQL │ │ pgvector │ │ R2 Blobs  │
     │ (records)  │ │(semantic │ │ (PDFs,    │
     │            │ │ search)  │ │  audio)   │
     └────────────┘ └──────────┘ └───────────┘
```

## Supported Platforms

### Municipal Meeting Platforms

| Platform | Integration | Example Jurisdictions |
|----------|------------|---------------|
| **ProudCity** | Web scraper | San Rafael |
| **Granicus** | API | Marin County, San Anselmo, Berkeley |
| **Legistar** | API | Oakland, SF, Richmond, Hayward, San Pablo |
| **CivicClerk** | API + OData | El Cerrito, Hayward, San Pablo, Richmond, Vallejo, Antioch |

### Community Issues

| Platform | Integration | Coverage |
|----------|------------|----------|
| **SeeClickFix** | API | 311/service requests (nationwide) |

### Legislation & Legal Code

| Platform | Integration | Coverage |
|----------|------------|----------|
| **LegiScan** | API | State + federal bills |
| **Federal Register** | API | Executive orders, regulations |
| **Municode** | Web scraper | Municipal code sections |

### Other

| Platform | Integration | Coverage |
|----------|------------|----------|
| **YouTube Boards** | Web + yt-dlp | Meeting video → audio → transcript |
| **USAspending** | API | Federal spending |
| **SAM Assistance** | API | Federal assistance programs |
| **CA State Controller** | Web | Financial data (ACFR) |

## Adding a New City

Adding a city is **configuration, not code** — if the city uses a supported platform. There are four steps: configure, register, ingest, and verify.

### Step 1: Create a jurisdiction config

Each jurisdiction has a YAML file in `data/jurisdictions/`. The file name matches the jurisdiction ID.

```yaml
# data/jurisdictions/city-berkeley.yaml
jurisdiction_id: city-berkeley
level: city
display_name: Berkeley
parent_jurisdictions:
  - county-alameda
  - state-california
  - country-united-states

contact_info:
  clerk_email: clerk@berkeleyca.gov
  website: https://berkeleyca.gov

data_sources:
  meetings:
    source_type: granicus        # or "legistar", "proudcity", "civicclerk"
    base_url: https://berkeley.granicus.com
    archives:
      city_council: "5"          # platform-specific IDs (Granicus view_id, Legistar body_id, etc.)
      zoning_adjustments_board: "2"
    metadata:
      granicus_domain: berkeley
      default_view_id: "2"
  issues: seeclickfix            # or null if not available
  municipal_code: municode       # or null
  transcripts:
    source: youtube              # or null
    playlist_id: null            # auto-discovered from meeting pages if null

financial:
  state: CA
  county: Alameda

ingestion:
  # Tier 1: Free
  meetings: true
  pdf_chunks: true
  issues: false                  # set false to skip
  municipal_code: false
  # Tier 2: Low cost (LLM-powered)
  agenda_items: true
  decisions: true
  legislation: true
  # Tier 3: Higher cost (audio)
  transcription: false
  diarization: false
  # Tier 4: GPU
  vector_indexing: true

metadata:
  created: "2026-03-15"
  updated: "2026-03-15"
```

See `data/jurisdictions/schema.yaml` for the full schema reference. See `data/jurisdictions/city-san-rafael.yaml` for a fully populated example.

**Platform detection**: If you're unsure which platform a city uses, the extraction package can auto-detect it:

```python
from civicos_extraction.platform_detection import detect_platform
result = detect_platform("https://berkeleyca.gov")
print(result)  # {'platform': 'granicus', 'base_url': 'https://berkeley.granicus.com', ...}
```

### Step 2: Register the jurisdiction

Add an entry to `config/registry.json` under the `jurisdictions` key:

```json
{
  "city-berkeley": {
    "domain": "berkeley.civicosproject.org",
    "display_name": "Berkeley",
    "modal_app_name": "civicos-berkeley",
    "parent_jurisdictions": ["county-alameda", "state-california", "country-united-states"]
  }
}
```

### Step 3: Run the ingestion pipeline

Ingestion runs on [Modal](https://modal.com) (serverless Python with GPU access). Each data source has its own function. Run them in order — later stages depend on earlier ones.

#### Tier 1: Free sources (no API keys required)

```bash
# 1. Meetings — fetch from configured platform (ProudCity, Granicus, Legistar, CivicClerk)
modal run scripts/modal_ingest.py::fetch_meetings --jurisdiction city-berkeley

# 2. PDF chunks — extract text from agenda packet PDFs
modal run scripts/modal_ingest.py::extract_chunks --jurisdiction city-berkeley

# 3. Issues — fetch from SeeClickFix (if configured)
modal run scripts/modal_ingest.py::fetch_issues --jurisdiction city-berkeley

# 4. Municipal code — fetch from Municode (if configured)
modal run scripts/modal_ingest.py::fetch_municipal_code --jurisdiction city-berkeley
```

#### Tier 2: LLM-powered extraction (~$0.02-0.15 per meeting)

These use Gemini Flash / GPT-4o-mini to extract structured data from meeting text.

```bash
# 5. Agenda items — LLM extraction from meeting agendas
modal run scripts/modal_ingest.py::extract_agenda_items --jurisdiction city-berkeley

# 6. Decisions — LLM extraction of outcomes from minutes
modal run scripts/modal_ingest.py::extract_decisions --jurisdiction city-berkeley

# 7. Legislation — sync state/federal bills via LegiScan (free tier)
modal run scripts/modal_ingest.py::sync_legislation --jurisdiction state-CA
```

#### Tier 3: Audio transcription (~$0.46 per 2-hour meeting)

Requires an AssemblyAI API key. Optional but enables `what_was_said()` and public testimony search.

```bash
# 8. Discover and download meeting videos from YouTube
modal run scripts/modal_ingest.py::fetch_videos --jurisdiction city-berkeley

# 9. Transcribe with speaker diarization
modal run scripts/modal_ingest.py::extract_transcripts --jurisdiction city-berkeley
```

#### Tier 4: Vector indexing (~$0.05-0.15 per run)

Runs on Modal T4 GPU. Generates embeddings for semantic search using `nomic-embed-text-v1.5`.

```bash
# 10. Index all corpus types for the jurisdiction
modal run scripts/modal_vectors.py --jurisdiction city-berkeley

# Or index a specific corpus type
modal run scripts/modal_vectors.py --corpus meetings --jurisdiction city-berkeley
modal run scripts/modal_vectors.py --corpus decisions --jurisdiction city-berkeley
modal run scripts/modal_vectors.py --corpus chunks --jurisdiction city-berkeley
modal run scripts/modal_vectors.py --corpus municipal_code --jurisdiction city-berkeley
modal run scripts/modal_vectors.py --corpus transcripts --jurisdiction city-berkeley
modal run scripts/modal_vectors.py --corpus issues --jurisdiction city-berkeley
```

#### Dry run mode

Every ingestion function supports `--dry-run` to preview what would be fetched/stored without writing anything:

```bash
modal run scripts/modal_ingest.py::fetch_meetings --jurisdiction city-berkeley --dry-run
```

### Step 4: Verify

After ingestion, check that data landed correctly.

**Check corpus counts:**
```python
from dotenv import load_dotenv
load_dotenv()
from civicos import CivicOS, DataStatus, format_data_status

c = CivicOS('city-berkeley')
status = DataStatus(c.storage, c._vectors, 'city-berkeley')
print(format_data_status(status.summary()))
```

**Check vector coverage:**
```python
# Which corpora have gaps between stored records and indexed embeddings?
print(status.gaps())
```

**Check vector stats from Modal:**
```bash
modal run scripts/modal_vectors.py --jurisdiction city-berkeley --stats-only
```

Expected output shows indexed/total counts per corpus type with coverage percentages.

### Step 5: Deploy (optional)

If running your own MCP server instance:

```bash
CIVICOS_JURISDICTION=city-berkeley modal deploy apps/civicos-mcp/modal_mcp.py
```

See the [Operator Guide](operator-guide.md) for full deployment instructions.

## Ingestion Cost Tiers

Ingestion costs are tiered so operators can start free and add capabilities incrementally.

| Tier | Sources | Cost | Enables |
|------|---------|------|---------|
| **Tier 1: Free** | Meetings, PDF chunks, issues, municipal code | $0 | Basic meeting/agenda search |
| **Tier 2: LLM** | Agenda items, decisions, legislation | ~$0.02-0.15/meeting | Decision search, legislation tracking |
| **Tier 3: Audio** | Transcription with speaker diarization | ~$0.46/2hr meeting | Transcript search, public testimony |
| **Tier 4: GPU** | Vector indexing | ~$0.05-0.15/run | Semantic search across all corpora |

**Recommendation**: Start with Tiers 1 + 2 + 4. Add Tier 3 (transcription) once you've verified the basic pipeline works. See [cost_registry.yaml](../../docs/public/cost_registry.yaml) for detailed pricing.

## Pipeline Features

### Checkpoint System

Extraction runs save progress to JSON files in `data/checkpoints/`. If a run crashes mid-way through 200 meetings, it resumes from where it stopped.

```bash
# View checkpoints for a jurisdiction
ls data/checkpoints/*berkeley*

# Checkpoint files are plain JSON with last-processed IDs and timestamps
cat data/checkpoints/city-berkeley.json
```

To force a full re-fetch (ignoring checkpoints), delete or rename the relevant checkpoint file.

### Request Throttling

All extractors implement exponential backoff and respect platform rate limits. Municipal APIs can be fragile — the default rate limit is 1 request/second for most platforms, configurable per-jurisdiction.

### Schema Validation

Every record is validated against JSON schemas before storage. Malformed data is logged and skipped, not silently stored.

### Idempotent Storage

All storage operations use upsert semantics. Running the same ingestion twice produces no duplicates — safe to re-run if you're unsure whether a previous run completed.

## What if the city uses an unsupported platform?

You'll need to write a new extractor in `packages/civicos-extraction/`. The interface is straightforward:

```python
class MyPlatformClient:
    def get_events(self, days_ahead=30, days_past=0) -> list[dict]:
        """Fetch raw platform data"""

    def get_meetings(self, days_ahead=30) -> list[Meeting]:
        """Normalize to CivicOS meeting schema"""

    def health(self) -> HealthStatus:
        """Platform availability check"""
```

The ProudCity extractor (web scraper) is a good starting point for sites without APIs. The Legistar extractor (API client) is a good model for platforms with structured APIs. Register the new client in `packages/civicos-extraction/src/civicos_extraction/clients/__init__.py`.

## Estimated Effort

For a city using a **supported platform** (Legistar, Granicus, CivicClerk, ProudCity):

| Task | Effort |
|------|--------|
| Jurisdiction config (YAML) | ~30 minutes |
| Registry entry | ~15 minutes |
| Tier 1+2 ingestion | 1-4 hours (depends on data volume) |
| Vector indexing (Tier 4) | ~30 minutes (GPU on Modal) |
| Verification and QA | ~1 hour |
| **Total** | **Half a day** |

For a city on an **unsupported platform**, add 2-5 days for extractor development.

## Further Reading

- [Data dictionary](data-dictionary.md) — schema definitions for all corpus types
- [Operator guide](operator-guide.md) — full deployment walkthrough
- [civicos-extraction package docs](packages/civicos-extraction.md) — parser details and config reference
- [What's live](status.md) — which platforms are active in production
