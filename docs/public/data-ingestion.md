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

## Prerequisites

Before onboarding a city, you need infrastructure and API keys. Not everything is required — it depends on which ingestion tiers you want to run.

> **Want to try it first?** Use `--sandbox` mode — it runs entirely on your machine with SQLite, no cloud accounts needed. Just install the Python environment below, then jump to [Adding a New City](#adding-a-new-city).

### Infrastructure (required for production)

| Service | What to do | Cost | Notes |
|---------|-----------|------|-------|
| **Python environment** | `python3 -m venv civicos-env && source civicos-env/bin/activate && pip install -r requirements.txt` | Free | Python 3.10+ |
| **Modal** | `pip install modal && modal setup` | Free ($30/mo credits) | Runs the ingestion pipeline serverless |
| **Supabase PostgreSQL** | Create project at [supabase.com](https://supabase.com), copy the connection string | $25/mo (Pro) | pgvector enabled by default |

### Database setup

After creating your Supabase project:

1. Copy the connection string from Supabase → Settings → Database → Connection string (URI)
2. Add to `.env`:
   ```
   DATABASE_URL=postgresql://postgres.[project-ref]:[password]@aws-0-[region].pooler.supabase.com:6543/postgres
   ```
3. Run the schema migrations:
   ```bash
   psql "$DATABASE_URL" -f scripts/sql/create_tables.sql
   psql "$DATABASE_URL" -f scripts/sql/enable_rls.sql
   ```
4. Add the same `DATABASE_URL` to Modal secrets:
   ```bash
   modal secret create civicos-env DATABASE_URL="postgresql://..."
   ```

### API keys (by tier)

Add these to both `.env` (local) and Modal secrets (`modal secret create civicos-env KEY=value`).

| Key | Env var | Tier | Cost | What it enables |
|-----|---------|------|------|-----------------|
| **Google Maps** | `GOOGLE_MAPS_API_KEY` | Config gen | Free tier | Geocoding during YAML generation (city → county → state hierarchy) |
| **OpenAI** | `OPENAI_API_KEY` | Tier 2 | ~$0.01-0.10/meeting | Agenda item + decision extraction, body naming |
| **YouTube Data** | `YOUTUBE_API_KEY` | Config gen | Free tier | Auto-detect city's YouTube meeting channel |
| **LegiScan** | `LEGISCAN_API_KEY` | Tier 2 | Free (30K queries/mo) | State + federal legislation sync |
| **AssemblyAI** | `ASSEMBLYAI_API_KEY` | Tier 3 | $0.21/hr audio | Transcription with speaker diarization |

**Minimum for testing:** No API keys needed. Platform detection and Tier 1 ingestion (meetings, PDFs, issues) work without any keys. You'll get warnings about missing keys but the pipeline continues.

### Verify your setup

```bash
source civicos-env/bin/activate
python3 -c "
from dotenv import load_dotenv; load_dotenv()
import os
db = os.environ.get('DATABASE_URL', '')
print(f'DATABASE_URL: {\"set\" if db else \"NOT SET\"} ({db[:30]}...)')
print(f'GOOGLE_MAPS_API_KEY: {\"set\" if os.environ.get(\"GOOGLE_MAPS_API_KEY\") else \"not set (optional)\"}')
print(f'OPENAI_API_KEY: {\"set\" if os.environ.get(\"OPENAI_API_KEY\") else \"not set (Tier 2 disabled)\"}')
print(f'YOUTUBE_API_KEY: {\"set\" if os.environ.get(\"YOUTUBE_API_KEY\") or os.environ.get(\"GOOGLE_API_KEY\") else \"not set (optional)\"}')
"
modal secret list  # Should show civicos-env
```

## Supported Platforms

### Municipal Meeting Platforms

| Platform | Integration | Example Jurisdictions |
|----------|------------|---------------|
| **ProudCity** | Web scraper + WP REST API | San Rafael, Fairfax, Belvedere |
| **Granicus** | API | Marin County, San Anselmo, Sausalito, Berkeley |
| **Legistar** | API | Oakland, SF, Richmond, Hayward, San Pablo |
| **CivicClerk** | API + OData | El Cerrito, Hayward, San Pablo, Richmond, Vallejo, Antioch |
| **CivicPlus** | Web scraper (Archive.aspx) | Corte Madera, Larkspur |
| **Universal Adapter** | LLM-generated CSS selectors | Ross, other custom sites |
| **eScribe** | JSON API | National City, Canadian municipalities |
| **Simbli** | Playwright | School districts (eboardsolutions.com) |
| **BoardDocs** | Web scraper | School boards |

### Community Issues

| Platform | Integration | Coverage | Auth |
|----------|------------|----------|------|
| **SeeClickFix** | Public API | 311/service requests (nationwide) | None |
| **GOGov** | Authenticated API | FixItMarin, other GOGov cities | Staff credentials |

#### GOGov / FixItMarin

[GOGov](https://www.gogovapps.com/) (formerly GovOutreach) powers FixItMarin and similar 311 apps in other jurisdictions. Unlike SeeClickFix, the API requires authenticated access.

**API details:**
- Base URL: `https://api.govoutreach.com`
- Auth: email/password → bearer token
- PyPI package: [`gogov`](https://pypi.org/project/gogov/) (unofficial client, v0.8.4)
- Key methods: `Client.search()` (paginated), `Client.get_topics()`, `Client.export_requests()`
- Data: caseId, description, location (lat/lon), dateEntered, status, priority, custom fields
- Public portal (read-only, no API): `https://user.govoutreach.com/{site}/`

**To enable for a jurisdiction:**
1. Obtain staff credentials from the city/county (data sharing agreement)
2. Add to `.env`: `GOGOV_EMAIL`, `GOGOV_PASSWORD`, `GOGOV_SITE` (e.g., `marincountyca`)
3. Set `issue_source: "gogov"` in the extraction config
4. GOGov client implementation is pending — detection works but fetching is deferred until credentials are available

**Known GOGov deployments:**
- Marin County, CA (`marincountyca`) — FixItMarin, launched Feb 2026, unincorporated areas only

**Note:** GOGov serves county-level unincorporated areas, not individual cities. Cities within Marin still use SeeClickFix or have no 311 provider.

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

### Turnkey (Recommended)

One command from zero to searchable data:

```bash
python scripts/onboard.py --city "Mill Valley" --state CA --county Marin
```

This auto-detects the civic platform (Granicus, Legistar, etc.), generates both config files, then runs the full ingestion pipeline on Modal:

1. **Config generation** — Creates `data/extraction/city-mill-valley.json` (platform config) and `data/jurisdictions/city-mill-valley.yaml` (governance metadata) via platform auto-discovery and geocoding
2. **Meeting fetch** — Scrapes meetings from the detected platform (365 days of history by default)
3. **Chunk extraction** — Downloads and parses agenda PDFs
4. **Agenda items** — LLM-powered extraction of actionable items from agendas
5. **Decisions** — LLM-powered extraction of high-stakes decisions from minutes
6. **Vector indexing** — Embeds all corpora for semantic search

**Options:**

```bash
# Dry run — generate configs only, no Modal, no API calls, no cost
python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --dry-run

# Generate configs but skip ingestion (same as dry-run but also saves YAML)
python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --skip-ingestion

# Re-run on existing city (skips config generation, runs ingestion)
python scripts/onboard.py --city "Mill Valley" --state CA --county Marin

# Force regenerate configs
python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --force

# Local sandbox — ingest to SQLite, no Modal or Postgres needed
python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --sandbox

# Direct URL instead of auto-discovery
python scripts/onboard.py --url "https://cityofmillvalley.granicus.com" --jurisdiction city-mill-valley --state CA --county Marin
```

**Testing a city without committing:**

```bash
# Option A: Local sandbox (no Modal, no Postgres, no cost)
python scripts/onboard.py --city "Portland" --state OR --sandbox

# Data goes to data/sandbox_city-portland.sqlite — production untouched.
# Clean up when done:
python scripts/ingest_local.py --cleanup city-portland
python scripts/onboard.py --cleanup city-portland

# Option B: Production pipeline with cleanup (requires Modal + Postgres)
# 1. Dry run — generate configs, check platform detection (free, no Modal)
python scripts/onboard.py --city "Portland" --state OR --dry-run

# 2. Meetings only — validate data pipeline with minimal cost (~$0.05-0.10)
modal run scripts/modal_ingest.py --meetings --jurisdiction city-portland --meetings-days-past 365

# 3. Verify it worked
python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
c = CivicOS('city-portland')
print(f'Upcoming: {len(c.whats_next())} meetings')
"

# 4. Clean up when done testing — removes all data + config files
python scripts/onboard.py --cleanup city-portland
```

**Verify a full onboarding:**

```bash
modal run scripts/modal_ingest.py --stats-only --jurisdiction city-mill-valley
```

### Manual (Step-by-Step)

For more control, or if the turnkey flow doesn't support your platform:

#### Step 1: Create a jurisdiction config

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
