# Council Data Project (CDP) Access Guide

**✅ BREAKTHROUGH DISCOVERY (2025-09-26)**: CDP uses anonymous public access - no special credentials required!

## Quick Start - Oakland Example

```python
# Install CDP backend
pip install cdp-backend

# Connect using anonymous credentials
import fireo
from google.auth.credentials import AnonymousCredentials
from google.cloud.firestore import Client
from cdp_backend.database import models as db_models

# Connect to Oakland CDP
client = Client(
    project="cdp-oakland-ba81c097",
    credentials=AnonymousCredentials()
)
fireo.connection(client=client)

# Query events
events = db_models.Event.collection.limit(5).fetch()
for event in events:
    print(f"Event: {event.event_datetime}")
    print(f"Agenda: {event.agenda_uri}")
```

## Known CDP Project IDs

- **Oakland**: `cdp-oakland-ba81c097` ✅ **Tested Working**
- **Denver**: `cdp-denver-962aefef` (confirmed from docs)
- **Seattle**: `cdp-seattle-21723dcf` (estimated pattern)

## Discovery Method for New Locales

1. **GitHub Repository**: Check `github.com/CouncilDataProject/{city-name}`
2. **Configuration Files**: Look for project ID in README or config files
3. **Pattern**: Usually follows `cdp-{city}-{hash}` format

## Oakland Reality Check

**✅ Connection**: Anonymous access works perfectly
**❌ Data Freshness**: Contains 2023 data (archival), not current events
**✅ Use Case**: Historical validation for Legistar API cross-referencing

## Available Event Fields

**Working Fields**:
- `event.event_datetime` - Meeting date/time
- `event.agenda_uri` - URL to agenda document
- `event.external_source_id` - External system reference
- `event.body_ref` - Reference to governing body

**Limitations**:
- `video_uri` not available in Oakland CDP
- Data appears to be from 2023, not current

## Integration with Civic Platform

**Primary Use**: Historical cross-validation
**Secondary Use**: Archival civic data sovereignty
**Implementation**: See `src/cdp_client.py` for full integration

## Why Anonymous Access Works

CDP is designed for **civic transparency** with intentional public access:
- No authentication barriers for public meeting data
- Google Cloud Firestore with anonymous read permissions
- Aligned with open government mission

## Other CDP Deployments to Test

Based on active projects, these may have more current data:
- **Seattle**: Likely most maintained (original CDP instance)
- **Denver**: Mentioned in recent documentation
- **Check**: `data.cdp.net` for list of active deployments

## Key Insight

**No "credential obtaining" process exists** - anonymous public access is the intended method for CDP civic data transparency.