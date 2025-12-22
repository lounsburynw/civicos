# Platform-Specific Notes

Technical reference for the three civic meeting platforms supported by Civic. Use this guide when onboarding new cities or troubleshooting extraction issues.

## Quick Reference

| Platform | API Type | Detection | Example Cities |
|----------|----------|-----------|----------------|
| Legistar | REST API | `webapi.legistar.com` endpoint responds | Berkeley, Oakland, San Francisco |
| CivicClerk | OData v4 | `{subdomain}.api.civicclerk.com` responds | El Cerrito, Hayward, San Pablo |
| ProudCity | Web scraping | `/meetings/` page with `-meetings/` links | San Rafael |

**Auto-detection:**
```python
from civic_extraction.platform_detection import detect_platform

result = detect_platform("https://www.cityofsanrafael.org")
if result.confidence >= 0.8:
    print(f"Detected: {result.source_type}")  # "proudcity"
```

---

## Legistar (REST API)

Legistar is a commercial agenda management system used by many California cities. It provides a REST API at `webapi.legistar.com`.

### Base URL Pattern

```
https://webapi.legistar.com/v1/{client_name}
```

The `client_name` is typically the city name in lowercase:
- Berkeley: `https://webapi.legistar.com/v1/berkeley`
- Oakland: `https://webapi.legistar.com/v1/oakland`
- San Francisco: `https://webapi.legistar.com/v1/sfgov`

**Deriving client_name:** Extract from the city's Legistar portal URL. For `https://berkeley.legistar.com`, the client is `berkeley`.

### Key Endpoints

| Endpoint | Description | Example |
|----------|-------------|---------|
| `/events` | Meeting list | `/events?$filter=EventDate ge datetime'2025-01-01'` |
| `/events/{id}` | Single event | `/events/12345` |
| `/bodies` | Councils, commissions | `/bodies` |
| `/matters/{id}` | Legislation details | `/matters/67890` |

### Date Format

Legistar uses ISO 8601 format with `datetime'...'` wrapper in OData filters:

```
EventDate ge datetime'2025-01-15'
EventDate le datetime'2025-02-15T23:59:59'
```

API responses return dates as ISO 8601 strings:
```json
{
  "EventDate": "2025-01-15T00:00:00",
  "EventTime": "2025-01-15T19:00:00"
}
```

**Parsing quirk:** `EventDate` and `EventTime` are separate fields. Combine them:
```python
date_str = event["EventDate"].split("T")[0]  # "2025-01-15"
time_str = event["EventTime"].split("T")[1]  # "19:00:00"
meeting_datetime = datetime.fromisoformat(f"{date_str}T{time_str}")
```

### Rate Limiting

Legistar APIs are sensitive to burst requests. The client implements:

- **Throttle interval:** 1.0 second between requests (prevents 500 errors)
- **Retryable errors:** HTTP 429, 500, 502, 503
- **Backoff strategy:** Exponential (1s, 2s, 4s)
- **Timeout:** 10 seconds per request
- **Max retries:** 3 attempts

```python
# From LegistarClient (legistar.py:47)
self.min_request_interval = 1.0  # Throttle to avoid 500 errors
```

**Effective rate:** ~100 requests/minute when throttling. Some cities may have stricter API access restrictions.

### Error Handling

| Error Type | Retry? | Resolution |
|------------|--------|------------|
| HTTP 429 (rate limit) | Yes | Wait with exponential backoff |
| HTTP 500/502/503 | Yes | Retry up to 3 times |
| HTTP 404 | No | Client name doesn't exist |
| Timeout | Yes | Increase timeout or retry |
| Connection error | Yes | Check network, retry |

Non-retryable HTTP errors (e.g., 401, 403, 404) fail immediately.

### Meeting Type Inference

The client infers meeting type from `EventBodyName`:

```python
body_lower = body_name.lower()
if "council" in body_lower:
    return "city_council"
elif "planning" in body_lower:
    return "planning_commission"
elif "zoning" in body_lower:
    return "zoning_board"
elif "school" in body_lower or "board of education" in body_lower:
    return "school_board"
# ... etc
```

### Meeting ID Generation

```
legistar-{client_name}-{event_id}
```
Example: `legistar-berkeley-12345`

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| All requests return 500 | Burst requests | Increase throttle interval |
| Client name 404 | Wrong client name | Check Legistar portal URL |
| Empty events list | Date filter too narrow | Expand date range |
| Missing agenda URL | Event has no EventId | Handle None gracefully |
| API key required | City restricts access | Contact city IT for API key |

### Example Config

```json
{
  "source_id": "legistar-berkeley",
  "source_type": "legistar",
  "jurisdiction_id": "city-berkeley",
  "base_url": "https://webapi.legistar.com/v1/berkeley"
}
```

---

## CivicClerk (OData v4)

CivicClerk is a SaaS civic engagement platform that uses OData v4 for its API.

### Base URL Pattern

```
API: https://{subdomain}.api.civicclerk.com/v1
Portal: https://{subdomain}.portal.civicclerk.com
```

The subdomain is typically the city name with state abbreviation:
- El Cerrito: `elcerritoca`
- Hayward: `haywardca`
- San Pablo: `sanpabloca`

### Key Endpoints

| Endpoint | Description | Example |
|----------|-------------|---------|
| `/Events` | Meeting list | `/Events?$filter=startDateTime ge 2025-01-01T00:00:00.000Z` |
| `/Events/{id}` | Single event with details | `/Events/12345` |
| `/Boards` | Meeting groups | `/Boards` |
| `/MeetingGroups` | Alternative board endpoint | `/MeetingGroups` |

### OData Filter Syntax

CivicClerk uses standard OData v4 filtering. Key differences from Legistar:

```
$filter=startDateTime ge 2025-01-01T00:00:00.000Z and startDateTime le 2025-12-31T23:59:59.999Z
$orderby=startDateTime asc
$top=100
$skip=0
```

**Date format:** ISO 8601 with milliseconds and Z suffix:
```
2025-01-15T00:00:00.000Z
```

**URL encoding:** Filter values must be URL-encoded:
```python
from urllib.parse import quote
filter_str = "startDateTime ge 2025-01-01T00:00:00.000Z"
api_url = f"{api_base}/Events?$filter={quote(filter_str)}"
```

### Pagination

CivicClerk requires explicit `$top` parameter. Without it, results may be limited:

```
/Events?$top=100&$skip=0     # First 100
/Events?$top=100&$skip=100   # Next 100
```

Default behavior varies by endpoint. Always specify `$top` for predictable results.

### Event Enrichment

The events list returns minimal data. For full details (agenda URLs, published files), fetch each event individually:

```python
# 1. Get event list
events = get_events()

# 2. Enrich each event
for event in events:
    event_id = event.get('id')
    details = requests.get(f"{api_base}/Events/{event_id}").json()
    # details includes 'publishedFiles' array
```

Published files contain agenda PDFs:
```json
{
  "publishedFiles": [
    {"name": "Agenda", "url": "https://...agenda.pdf"},
    {"name": "Minutes", "url": "https://...minutes.pdf"}
  ]
}
```

### Meeting Type Inference

Similar to Legistar, inferred from event name:

```python
name_lower = name.lower()
if "council" in name_lower:
    return "city_council"
elif "planning" in name_lower:
    return "planning_commission"
# ... etc
```

### Meeting ID Generation

```
civicclerk-{subdomain}-{event_id}
```
Example: `civicclerk-elcerritoca-5678`

### Health Check

The `/Boards` endpoint is lightweight and used for health checks:

```python
response = session.get(f"{api_base}/Boards", timeout=10)
if response.status_code == 200:
    boards = response.json().get('value', [])
    return len(boards)  # board_count
```

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Empty response | Wrong subdomain | Try variations: `{city}`, `{city}ca`, `{city}{state}` |
| OData parse error | Malformed filter | Check date format, URL encoding |
| 401 Unauthorized | Auth required | Some endpoints need tokens |
| Missing agenda URL | Not in publishedFiles | Fetch event details, check publishedFiles array |
| Pagination issues | Missing $top | Always specify $top parameter |

### Example Config

```json
{
  "source_id": "civicclerk-elcerritoca",
  "source_type": "civicclerk",
  "jurisdiction_id": "city-el-cerrito",
  "base_url": "https://elcerritoca.api.civicclerk.com/v1"
}
```

---

## ProudCity (Web Scraping)

ProudCity is a WordPress-based platform for government websites. It has no API, so data is extracted via HTML scraping.

### Detection

ProudCity sites can be detected by:

1. **Meta tag:** `<meta name="generator" content="ProudCity...">`
2. **URL pattern:** `/meetings/` page with links like `/city-council-meetings/`

```python
archive_pattern = re.compile(r'/([a-z0-9-]+)-(meetings|hearings)/?')
```

### Archive Discovery

ProudCity organizes meetings by type in archive pages:

```
/city-council-meetings/
/planning-commission-meetings/
/fire-commission-meetings/
/zoning-administrator-hearings/
```

**Auto-discovery:** Scrape `/meetings/` to find all archive URLs:

```python
client = ProudCityClient(base_url="https://www.cityofsanrafael.org", ...)
discovered = client.discover_meeting_types()
# Returns: {'city_council': '/city-council-meetings/', ...}
```

### Slug-to-Key Conversion

URL slugs are converted to keys by replacing hyphens with underscores:

```
city-council-meetings -> city_council
planning-commission-meetings -> planning_commission
ada-access-advisory-committee-meetings -> ada_access_advisory_committee
```

### Date Extraction

Dates are embedded in meeting page URLs/slugs:

```
/meetings/city-council-october-6-2025/
```

Extraction uses regex pattern matching:
```python
pattern = rf'{month_name}[-\s]+(\d{{1,2}})[-\s]+(\d{{4}})'
# Matches: october-6-2025, october 6 2025
```

**Parsing quirk:** No time information in URLs. Meetings default to date-only.

### Rate Limiting

ProudCity scraping uses polite rate limiting:

```python
self.min_request_interval = 1.0  # Be polite to servers
```

The client waits at least 1 second between requests to avoid overloading municipal servers.

### PDF Extraction

Meeting pages contain PDF links for agendas and minutes. The client searches for:

1. **Tab sections:** `#tab-agenda-packet`, `#tab-minutes`
2. **URL patterns:**
   - Agenda packet: `agenda-packet*.pdf`, `full*packet*.pdf`
   - Minutes: `cc-minutes*.pdf`, `minutes-YYYY-MM-DD*.pdf`

```python
pdfs = client.get_meeting_pdfs(meeting_url)
# Returns: {'agenda_packet_url': '...', 'minutes_url': '...', 'individual_items': [...]}
```

### Coverage Analysis

ProudCity sources can report coverage (configured vs discovered meeting types):

```python
inventory = client.get_source_inventory(include_coverage=True)
# inventory['coverage'] = {
#   'configured_count': 6,
#   'discovered_count': 15,
#   'missing': ['ada_access_advisory_committee', 'library_board', ...],
#   'coverage_percent': 40.0
# }
```

Use this to identify unconfigured meeting types during onboarding.

### URL Handling

ProudCity links can be relative or absolute:

```python
def _make_absolute_url(self, url: str) -> str:
    if url.startswith('http'):
        return url
    return f"{self.base_url}{url}"
```

### Meeting ID Generation

```
proudcity-{jurisdiction_id}-{meeting_slug}
```
Example: `proudcity-city-san-rafael-city-council-october-6-2025`

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| No meetings found | Wrong archive paths | Run discover_meeting_types() |
| Date parsing fails | Non-standard slug format | Check slug patterns, extend regex |
| Missing agenda PDF | Different tab structure | Inspect HTML, update selectors |
| JavaScript-rendered content | Dynamic page | Not supported without Selenium |
| 403 errors | Bot blocking | Check User-Agent, reduce rate |

### Example Config

```json
{
  "source_id": "proudcity-san-rafael",
  "source_type": "proudcity",
  "jurisdiction_id": "city-san-rafael",
  "base_url": "https://www.cityofsanrafael.org",
  "auto_discover": true,
  "archives": {
    "city_council": "/city-council-meetings/",
    "planning_commission": "/planning-commission-meetings/",
    "fire_commission": "/fire-commission-meetings/",
    "tax_oversight": "/voter-approved-tax-oversight-committee-meetings/",
    "zoning_administrator": "/zoning-administrator-hearings/",
    "council_subcommittees": "/council-subcommittee-meetings/"
  }
}
```

---

## Cross-Platform Patterns

### DataSource Protocol

All clients implement the `DataSource` protocol from `civic_extraction/clients/base.py`:

```python
class DataSource(Protocol):
    def health(self) -> HealthStatus:
        """Check source availability."""
        ...

    def validate(self) -> ValidationResult:
        """Preflight validation before pipeline run."""
        ...
```

**HealthStatus** includes:
- `is_available`: API/site reachable
- `available_count`: Number of items found
- `check_duration_ms`: Response time
- `errors`: List of error messages

**ValidationResult** includes:
- `is_valid`: Ready for extraction
- `config_valid`: Config fields OK
- `api_reachable`: Endpoint responds

### Error Handling Pattern

All clients use exponential backoff with retry limits:

```python
for attempt in range(retries):
    try:
        response = session.get(url, timeout=10)
        if response.status_code == 200:
            return response.json()
        elif response.status_code in [429, 500, 502, 503]:
            # Retryable
            time.sleep(2 ** attempt)  # 1s, 2s, 4s
            continue
        else:
            # Non-retryable
            return None
    except Timeout:
        time.sleep(2 ** attempt)
        continue
```

### Meeting Normalization

All clients normalize raw data to the common `Meeting` dataclass:

```python
@dataclass
class Meeting:
    id: str
    title: str
    meeting_datetime: datetime
    jurisdiction_id: str
    meeting_type: str
    status: str
    location: Optional[str]
    agenda_url: Optional[str]
    video_url: Optional[str]
    source_platform: str
    source_url: Optional[str]
    raw_data: Dict[str, Any]
```

---

## Adding New Platforms

To add support for a new civic platform:

1. **Create client class** in `packages/civic-extraction/src/civic_extraction/clients/`
2. **Extend BaseExtractor** and implement:
   - `health()` - lightweight availability check
   - `validate()` - preflight config validation
   - `get_events()` - fetch raw events
   - `normalize_event()` - convert to Meeting format
3. **Add detection logic** to `platform_detection.py`
4. **Add tests** in `packages/civic-extraction/tests/test_clients.py`
5. **Document** in this file

### Required Properties

```python
@property
def platform_name(self) -> str:
    return "newplatform"

@property
def source_id(self) -> str:
    return f"newplatform-{self.identifier}"

@property
def source_type(self) -> str:
    return "newplatform"
```

---

## Related Documentation

- [CITY_ONBOARDING_GUIDE.md](./CITY_ONBOARDING_GUIDE.md) - Full onboarding workflow
- [ADMIN_SETUP_GUIDE.md](./ADMIN_SETUP_GUIDE.md) - Environment setup
- [DATA_INGESTION_OPERATIONS.md](../critical/DATA_INGESTION_OPERATIONS.md) - Pipeline operations
