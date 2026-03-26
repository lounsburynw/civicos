# civicos-extraction

Platform parsers for extracting civic data from municipal websites and government APIs.

**Location:** `packages/civicos-extraction/`

## Supported Platforms

### Municipal Meeting Platforms

| Platform | Type | Jurisdictions |
|----------|------|---------------|
| **ProudCity** | Web scraper | San Rafael (primary pilot) |
| **Granicus** | API | Marin County |
| **Legistar** | API | Berkeley, Oakland, SF, Richmond, Hayward, San Pablo |
| **CivicClerk** | API + OData | El Cerrito, Hayward, San Pablo, Richmond, Vallejo, Antioch |
| **BoardDocs** | POST/HTML | Ross Valley SD, MCOE, Larkspur-Corte Madera SD, Sausalito-Marin City SD, College of Marin |
| **Simbli** | Playwright | San Rafael City Schools, Novato USD, Tamalpais Union HSD |
| **eScribe** | HTML | (available, no current jurisdictions) |

### Community Issues
| Platform | Type | Coverage |
|----------|------|----------|
| **SeeClickFix** | API | San Rafael (311 reports) |

### Legislation & Federal Data
| Platform | Type | Coverage |
|----------|------|----------|
| **LegiScan** | API | State + federal bills |
| **Federal Register** | API | Executive orders, regulations |
| **FAC v2** | API | Federal Audit Clearinghouse (grants) |
| **USAspending** | API | Federal spending |
| **SAM Assistance** | API | Federal assistance programs |
| **HUD Exchange** | API | CDBG data |

### Financial
| Platform | Type | Coverage |
|----------|------|----------|
| **CA State Controller** | Web | ACFR financial data |
| **CA Grants** | API | State grant programs |

### Media
| Platform | Type | Coverage |
|----------|------|----------|
| **YouTube Boards** | Web/API | Meeting video extraction |

## Extraction Pipeline

All extractors follow a 4-stage pattern:

```
FETCH → NORMALIZE → VALIDATE → STORE
```

- **FETCH**: Pull raw data from platform API or website
- **NORMALIZE**: Convert to CivicOS schema (meetings, decisions, etc.)
- **VALIDATE**: Check against JSON schema
- **STORE**: Persist to storage backend

Features:
- Checkpoint system for crash recovery (JSON files)
- Request throttling and exponential backoff
- Schema validation against `MEETING_SCHEMA`
- Manifest tracking per extraction run

## Adding a New Extractor

Implement the base interface:

```python
class MyExtractor:
    def get_events(self, days_ahead=30, days_past=0) -> List[Dict]:
        """Raw platform data"""

    def get_meetings(self, days_ahead=30) -> List[Meeting]:
        """Normalized to CivicOS schema"""

    def health(self) -> HealthStatus:
        """Platform availability check"""
```

Register in the factory (`clients/factory.py`) and add to `SUPPORTED_MEETING_SOURCES` in `clients/__init__.py` so the standard pipeline dispatches to it.

## Config-Driven Ingestion

Each jurisdiction has an extraction config JSON in `data/extraction/`:

```json
{
  "source_id": "boarddocs-ca-rova",
  "source_type": "boarddocs",
  "jurisdiction_id": "school-ross-valley",
  "base_url": "https://go.boarddocs.com/ca/rova/Board.nsf",
  "metadata": {
    "app_path": "ca/rova",
    "committee_id": "AB9A2R259AF0"
  }
}
```

The ingestion pipeline reads `source_type` to dispatch to the correct client. All platforms in `SUPPORTED_MEETING_SOURCES` work with the standard `fetch_meetings()` dispatcher in `scripts/modal_ingest.py`.

## Platform Discovery

The onboarding system auto-detects platforms from URLs or city names:

| Platform | Auto-discovery method |
|----------|----------------------|
| Legistar | Probe `{slug}.legistar.com` API |
| CivicClerk | Probe `{slug}.civicclerk.com` OData |
| Granicus | Probe `{slug}.granicus.com` + view IDs |
| eScribe | Probe `pub-{slug}.escribemeetings.com` |
| Simbli | Probe `{slug}.simbli.com` subdomains |
| BoardDocs | URL detection (`go.boarddocs.com/{state}/{site}`) + committee auto-discovery |
| ProudCity | Scrape city website `/meetings/` page |

**BoardDocs note:** Site codes can't be guessed from district names. During agentic onboarding, use WebSearch (`site:go.boarddocs.com "{district name}"`) to find the URL, then pass it to `onboard_jurisdiction()` which handles everything else automatically.
