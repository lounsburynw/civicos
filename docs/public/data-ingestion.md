# Data Ingestion

An empty CivicOS instance returns empty results. This page covers how civic data gets into the system — the extraction pipeline, supported platforms, and what it takes to add a new city.

## The Pipeline

All extractors follow a 4-stage pattern:

```
FETCH → NORMALIZE → VALIDATE → STORE
```

1. **Fetch** — Pull raw data from a platform API or website (Legistar, Granicus, ProudCity, etc.)
2. **Normalize** — Convert platform-specific formats to CivicOS schemas (meetings, decisions, transcripts, etc.)
3. **Validate** — Check against JSON schema definitions
4. **Store** — Persist to PostgreSQL via the storage backend (never raw SQL)

After storage, a separate indexing step generates vector embeddings for semantic search.

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

| Platform | Integration | Jurisdictions |
|----------|------------|---------------|
| **ProudCity** | Web scraper | San Rafael (primary pilot) |
| **Granicus** | API | Marin County |
| **Legistar** | API | Berkeley, Oakland, SF, Richmond, Hayward, San Pablo |
| **CivicClerk** | API + OData | El Cerrito, Hayward, San Pablo, Richmond, Vallejo, Antioch |

### Community Issues

| Platform | Integration | Coverage |
|----------|------------|----------|
| **SeeClickFix** | API | San Rafael (311 reports) |

### Legislation

| Platform | Integration | Coverage |
|----------|------------|----------|
| **LegiScan** | API | State + federal bills |
| **Federal Register** | API | Executive orders, regulations |
| **USAspending** | API | Federal spending |
| **SAM Assistance** | API | Federal assistance programs |

### Other

| Platform | Integration | Coverage |
|----------|------------|----------|
| **Municode** | Web scraper | Municipal code sections |
| **YouTube Boards** | Web/API | Meeting video → audio → transcript |
| **CA State Controller** | Web | Financial data (ACFR) |

## Adding a New City

Adding a city is **configuration, not code** — if the city uses a platform CivicOS already supports. Here's what's involved:

### Step 1: Create a jurisdiction config

Each jurisdiction has a YAML file defining its data sources:

```yaml
# config/city-berkeley.yaml
jurisdiction_id: city-berkeley
display_name: Berkeley
level: city
state: CA
parent_jurisdictions:
  - county-alameda
  - state-california
  - country-united-states

platforms:
  meetings: legistar
  issues: seeclickfix  # or null if not available

legistar:
  base_url: https://berkeley.legistar.com
  bodies:
    - name: City Council
      body_id: 148
    - name: Planning Commission
      body_id: 149
```

### Step 2: Register the jurisdiction

Add an entry to `config/registry.json`:

```json
{
  "city-berkeley": {
    "domain": "berkeley.civicosproject.org",
    "display_name": "Berkeley",
    "modal_app_name": "civicos-berkeley",
    "parent_jurisdictions": ["state-california", "country-united-states"]
  }
}
```

### Step 3: Run the ingestion pipeline

```bash
# Ingest meetings and decisions
python scripts/ingest_jurisdiction.py city-berkeley

# Index for semantic search
modal run scripts/modal_ingest.py --jurisdiction city-berkeley
```

### Step 4: Deploy

```bash
CIVICOS_JURISDICTION=city-berkeley modal deploy apps/civicos-mcp/modal_mcp.py
```

### What if the city uses an unsupported platform?

You'll need to write a new extractor. The interface is straightforward:

```python
class MyPlatformExtractor:
    def get_events(self, days_ahead=30, days_past=0) -> List[Dict]:
        """Fetch raw platform data"""

    def get_meetings(self, days_ahead=30) -> List[Meeting]:
        """Normalize to CivicOS meeting schema"""

    def health(self) -> HealthStatus:
        """Platform availability check"""
```

See `packages/civicos-extraction/` for examples. The ProudCity extractor (web scraper) is a good starting point for sites without APIs. The Legistar extractor (API client) is a good model for platforms with structured APIs.

## Pipeline Features

### Checkpoint System
Extraction runs save progress to JSON checkpoint files. If a run crashes mid-way through 200 meetings, it resumes from where it stopped rather than re-fetching everything.

### Request Throttling
All extractors implement exponential backoff and respect platform rate limits. This matters — some municipal APIs are fragile.

### Schema Validation
Every record is validated against JSON schemas before storage. Malformed data is logged and skipped, not silently stored.

### Manifest Tracking
Each extraction run generates a manifest recording what was fetched, from where, and when. This supports audit trails and incremental updates.

## Estimated Effort

For a city using a **supported platform** (Legistar, Granicus, CivicClerk, ProudCity):

| Task | Effort |
|------|--------|
| Jurisdiction config (YAML) | ~30 minutes |
| Registry entry + deployment config | ~15 minutes |
| Initial ingestion run | 1-4 hours (depends on data volume) |
| Vector indexing | ~30 minutes (GPU on Modal) |
| Verification and QA | ~2 hours |
| **Total** | **Half a day to one day** |

For a city on an **unsupported platform**, add 2-5 days for extractor development, depending on the platform's API quality.

## Further Reading

- [civicos-extraction package docs](packages/civicos-extraction.md) — parser details and config reference
- [Data dictionary](data-dictionary.md) — schema definitions for all corpus types
- [Operator guide](operator-guide.md) — full deployment walkthrough
- [What's live](status.md) — which platforms are active in production
