# civicos-extraction

Platform clients for extracting civic meeting data from municipal websites.

## Overview

`civicos-extraction` provides clients for municipal meeting platforms, extracting meetings, agendas, and related data. All clients implement a common interface and normalize to a standard format.

## Supported Platforms

| Platform | Cities | Features |
|----------|--------|----------|
| **Legistar** | Berkeley, Oakland, SF, etc. | Full API access, bodies, events, matters |
| **CivicClerk** | El Cerrito, Hayward, San Pablo, etc. | OData API, published files |
| **Granicus** | (future) | ViewPublisher HTML parsing |

## Installation

```bash
# From source (development)
pip install -e packages/civicos-extraction

# From PyPI (future)
pip install civicos-extraction
```

## Quick Start

### Legistar

```python
from civic_extraction import LegistarClient

client = LegistarClient("berkeley")

# Get raw events
events = client.get_events(days_ahead=30)

# Get normalized meetings
meetings = client.get_meetings(days_ahead=30)
for meeting in meetings:
    print(f"{meeting.title} - {meeting.meeting_datetime}")
```

### CivicClerk

```python
from civic_extraction import CivicClerkClient

client = CivicClerkClient("elcerritoca")

# Get events with agendas only
events = client.get_events(days_ahead=30, has_agenda=True)

# Get normalized meetings
meetings = client.get_meetings(days_ahead=30)
```

## Common Interface

All clients implement the `Extractor` protocol:

```python
from civic_extraction import BaseExtractor, Meeting

class MyExtractor(BaseExtractor):
    def get_events(self, days_ahead=90, days_past=0) -> List[Dict]:
        """Extract raw events from platform."""
        ...

    def normalize_event(self, event: Dict) -> Meeting:
        """Normalize to standard Meeting format."""
        ...

    @property
    def platform_name(self) -> str:
        return "my_platform"
```

## Meeting Format

All extractors normalize to the `Meeting` dataclass:

```python
@dataclass
class Meeting:
    id: str
    title: str
    meeting_datetime: datetime
    jurisdiction_id: str
    meeting_type: Optional[str]  # city_council, planning_commission, etc.
    status: Optional[str]
    location: Optional[str]
    virtual_url: Optional[str]
    agenda_url: Optional[str]
    minutes_url: Optional[str]
    video_url: Optional[str]
    source_platform: str
    source_url: Optional[str]
    raw_data: Optional[Dict]
```

## Integration with civic-state

```python
from civic_extraction import LegistarClient
from civic_state import StateManager

# Extract meetings
client = LegistarClient("berkeley")
meetings = client.get_meetings(days_ahead=30)

# Store in StateManager
state = StateManager("data/civic.db")
state.update_meetings(
    "city-berkeley",
    [m.to_dict() for m in meetings]
)
```

## Dependencies

- `requests>=2.28.0` - HTTP client (required)

## License

Apache 2.0
