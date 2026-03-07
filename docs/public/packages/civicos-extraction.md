# civicos-extraction

Platform parsers for extracting civic data from municipal websites and government APIs.

**Location:** `packages/civicos-extraction/`

## Supported Platforms

### Municipal Meeting Platforms

| Platform | Type | Cities |
|----------|------|--------|
| **ProudCity** | Web scraper | San Rafael (primary pilot) |
| **Legistar** | API | Berkeley, Oakland, SF, Richmond, Hayward, San Pablo |
| **CivicClerk** | API + OData | El Cerrito, Hayward, San Pablo, Richmond, Vallejo, Antioch |

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

Configuration is YAML-based per jurisdiction.
