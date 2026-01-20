# How to Set Up Civic for a New Jurisdiction

This guide walks administrators through deploying Civic for a new city or county. It assumes familiarity with command-line tools and basic server administration.

**Audience:** Technical administrators, civic tech organizations, municipal IT staff

---

## Table of Contents

1. [Pre-Setup Checklist](#pre-setup-checklist)
2. [Environment Configuration](#environment-configuration)
3. [Jurisdiction Configuration](#jurisdiction-configuration)
4. [Data Source Connection](#data-source-connection)
5. [Database Setup](#database-setup)
6. [Vector Database & RAG](#vector-database--rag)
7. [Deployment](#deployment)
8. [Operational Readiness](#operational-readiness)
9. [Verification Checklist](#verification-checklist)
10. [Troubleshooting](#troubleshooting)

---

## Pre-Setup Checklist

Before starting, gather this information about your target jurisdiction:

### Research

- [ ] **Jurisdiction type**: City, county, or special district
- [ ] **Official name**: e.g., "City of Berkeley" or "Marin County"
- [ ] **Meeting management platform**: Identify which system the city uses
  - Legistar (most common for larger cities)
  - CivicClerk (common for smaller cities)
  - Granicus (video-focused)
  - Custom website (will require custom extractor)
- [ ] **Meeting schedule**: When does city council meet? Planning commission?
- [ ] **Video platform**: YouTube, Granicus, or other

### Credentials & Access

- [ ] **OpenAI API key**: Required for AI features ([Get one here](https://platform.openai.com/api-keys))
- [ ] **City API access**: Some platforms require API keys (check with city IT)
- [ ] **SeeClickFix**: For citizen issue reports (uses public API)

### Contacts (for AI routing)

Gather contact information for AI to route citizen inquiries:

- [ ] City clerk email
- [ ] Planning department contact
- [ ] Public works department contact
- [ ] City council member emails

---

## Environment Configuration

### Step 1: Clone the Repository

```bash
git clone https://github.com/civic-os/civic.git
cd civic
```

### Step 2: Create Python Environment

```bash
python3 -m venv civicos-env
source civicos-env/bin/activate
pip install -e packages/civic
pip install -e packages/civicos-extraction
pip install -e packages/civicos-services
```

### Step 3: Configure Environment Variables

Copy the example configuration and edit it:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
# REQUIRED: Environment type
CIVICOS_ENV=development  # or staging, production

# REQUIRED: OpenAI API key for AI features
OPENAI_API_KEY=sk-proj-your-key-here

# REQUIRED FOR PRODUCTION: Authentication token
# Generate with: openssl rand -hex 32
CIVICOS_WEB_KEY=dev_key_local  # Use generated key in production

# REQUIRED FOR PRODUCTION: Allowed frontend domains
CIVICOS_CORS_ORIGINS=https://your-domain.com

# OPTIONAL: Local embeddings (free, default)
CIVICOS_EMBEDDING_PROVIDER=local
CIVICOS_EMBEDDING_MODEL=all-MiniLM-L6-v2

# OPTIONAL: Google Maps for geocoding
GOOGLE_MAPS_API_KEY=AIza-your-key

# OPTIONAL: LegiScan for state/federal bills
LEGISCAN_API_KEY=your-key
```

For a complete list of environment variables, see [SECRETS_MANAGEMENT.md](../critical/SECRETS_MANAGEMENT.md).

### Step 4: Verify Environment

```bash
./init.sh
```

This runs smoke tests and verifies your environment is configured correctly.

---

## Jurisdiction Configuration

Civic identifies jurisdictions using a normalized ID format: `city-{name}` or `county-{name}`.

### Step 1: Create Jurisdiction Override File

Create a JSON file in `data/jurisdiction_overrides/`:

```bash
# Example for Berkeley
touch data/jurisdiction_overrides/city-berkeley.json
```

Add jurisdiction-specific configuration:

```json
{
  "jurisdiction_id": "city-berkeley",
  "jurisdiction_name": "Berkeley, CA",
  "last_updated": "2025-12-15T00:00:00.000000",
  "federal_programs": {
    "cdbg": {
      "program_name": "Community Development Block Grant",
      "fy2025_allocation": 2500000,
      "allocation_source": "HUD FY2025 CDBG Allocations",
      "allocation_url": "https://www.hudexchange.info/GRANTEES/ALLOCATIONS-AWARDS/",
      "key_contacts": {
        "department": "Housing & Community Development",
        "planning_contact": "Check city website for current director"
      }
    }
  }
}
```

**Finding CDBG allocations**: Search [HUD Exchange](https://www.hudexchange.info/GRANTEES/ALLOCATIONS-AWARDS/) for your city's allocation.

### Step 2: Register Jurisdiction Alias (Optional)

If you want to support short names (e.g., "berkeley" instead of "city-berkeley"), add an alias in `packages/civic/src/civic/_internal/jurisdiction.py`:

```python
_JURISDICTION_ALIASES = {
    # ... existing aliases ...
    "berkeley": "city-berkeley",
}
```

---

## Data Source Connection

### Identifying Your Platform

Check your city's meeting page to identify the platform:

| Platform | URL Pattern | Example Cities |
|----------|-------------|----------------|
| Legistar | `legistar.com/{city}` or `{city}.legistar.com` | Berkeley, Oakland, SF |
| CivicClerk | `civicclerk.blob.core.windows.net` | El Cerrito, Hayward |
| Granicus | `granicus.com/ViewPublisher` | Various |

### Legistar Setup

Most Bay Area cities use Legistar. Connection is straightforward:

```python
from civic_extraction import LegistarClient

# Test connection
client = LegistarClient("berkeley")  # Use your city's Legistar client ID
meetings = client.get_meetings(days_ahead=30)
print(f"Found {len(meetings)} upcoming meetings")
```

To find your city's Legistar client ID:
1. Go to `https://{city}.legistar.com/` or search "{city} legistar"
2. The subdomain or path segment is usually the client ID
3. Common format: city name in lowercase

### CivicClerk Setup

For cities using CivicClerk:

```python
from civic_extraction import CivicClerkClient

# Test connection
client = CivicClerkClient("elcerritoca")  # Check city's CivicClerk URL
meetings = client.get_meetings(days_ahead=30)
print(f"Found {len(meetings)} upcoming meetings")
```

To find your city's CivicClerk ID:
1. Go to the city's meeting page
2. Look for OData API references or check the agenda PDF URLs
3. The blob storage path usually contains the client identifier

### YouTube Integration

Most cities post meeting videos to YouTube. To discover the channel:

1. Search YouTube for "{city name} city council"
2. Find the official channel
3. Note the channel ID from the URL

Videos are linked via meeting dates in the extraction process.

### SeeClickFix Integration

SeeClickFix provides citizen issue reports (potholes, graffiti, etc.):

```python
import requests

# Test SeeClickFix availability
response = requests.get(
    "https://seeclickfix.com/api/v2/issues",
    params={"place_url": "berkeley-ca", "per_page": 10}
)
issues = response.json()
print(f"Found {len(issues['issues'])} recent issues")
```

Find your city's SeeClickFix place_url at [seeclickfix.com](https://seeclickfix.com/).

---

## Database Setup

### Step 1: Initialize SQLite Database

```bash
# Run migrations to create schema
python scripts/migrate.py --status  # Check current state
python scripts/migrate.py           # Apply migrations
```

The database is created at `data/civic_state.db`.

### Step 2: Load Initial Data

Create a script to load your jurisdiction's initial data:

```python
from civic_extraction import LegistarClient  # or CivicClerkClient
from civic._internal.state import StateManager

# Initialize
client = LegistarClient("your-city")
state = StateManager("data/civic_state.db")

# Extract and load meetings
meetings = client.get_meetings(days_ahead=90, days_past=30)
state.update_meetings(
    "city-your-city",
    [m.to_dict() for m in meetings]
)

print(f"Loaded {len(meetings)} meetings")
```

### Step 3: Verify Database

```python
from civic._internal.state import StateManager

state = StateManager("data/civic_state.db")
meetings = state.get_meetings("city-your-city")
print(f"Stored {len(meetings)} meetings")
```

---

## Vector Database & RAG

The RAG (Retrieval-Augmented Generation) system requires document embeddings.

### Step 1: Create Directory Structure

```bash
mkdir -p data/pilot/rag_corpus/city-your-city
mkdir -p data/pilot/vectors/city-your-city
```

### Step 2: Download Meeting Documents

Download agenda PDFs, staff reports, and minutes:

```bash
# Example script structure
# scripts/download_documents.py
import requests
from pathlib import Path

output_dir = Path("data/pilot/rag_corpus/city-your-city")

# Download each agenda/minutes PDF from your extraction results
for meeting in meetings:
    if meeting.agenda_url:
        # Download and save PDF
        response = requests.get(meeting.agenda_url)
        filename = f"{meeting.id}_agenda.pdf"
        (output_dir / filename).write_bytes(response.content)
```

### Step 3: Process Documents

Chunk and embed documents:

```python
from civic._internal.rag import RAGEngine

# Initialize RAG for your jurisdiction
rag = RAGEngine("city-your-city")

# Process PDFs in corpus directory
corpus_dir = "data/pilot/rag_corpus/city-your-city"
rag.index_documents(corpus_dir)

print(f"Indexed documents for city-your-city")
```

### Step 4: Verify RAG

Test the search functionality:

```python
from civic._internal.rag import RAGEngine

rag = RAGEngine("city-your-city")
results = rag.search("housing policy", top_k=5)
print(f"Found {len(results)} relevant documents")
```

---

## Deployment

For production deployment, see [DEPLOYMENT_GUIDE.md](../critical/DEPLOYMENT_GUIDE.md).

### Quick Local Test

```bash
# Start API server
python -m civic_services.civic_api_integrated
# Server runs on http://localhost:8001

# Start WebSocket server (separate terminal)
python -m civic_services.civic_socketio_server
# Server runs on http://localhost:8002

# Start frontend (separate terminal)
cd apps/civicos-workspace && npm run dev
# Frontend runs on http://localhost:5173
```

### Production Deployment (Fly.io)

1. **Create Fly.io apps:**
   ```bash
   fly apps create civic-api-your-city
   fly apps create civic-websocket-your-city
   ```

2. **Create volumes:**
   ```bash
   fly volumes create civic_data --region sjc --size 3 -a civic-api-your-city
   fly volumes create civic_data --region sjc --size 3 -a civic-websocket-your-city
   ```

3. **Configure secrets:**
   ```bash
   fly secrets set OPENAI_API_KEY="sk-proj-..." -a civic-api-your-city
   fly secrets set CIVICOS_WEB_KEY="$(openssl rand -hex 32)" -a civic-api-your-city
   ```

4. **Deploy:**
   ```bash
   fly deploy -a civic-api-your-city
   fly deploy -a civic-websocket-your-city --config fly.websocket.toml
   ```

---

## Operational Readiness

### Set Up Monitoring

1. **Health endpoint**: `GET /health` on your API server
2. **External monitoring**: Configure UptimeRobot or similar
   - Monitor `https://your-api-domain.fly.dev/health`
   - Set 5-minute check interval
   - Configure alerts

See [UPTIME_MONITORING.md](../critical/UPTIME_MONITORING.md) for detailed setup.

### Configure Backups

Automated backups run via GitHub Actions. Manual backup:

```bash
# On production server
fly ssh console -a civic-api-your-city -C "python scripts/backup.py"
```

Backups are retained:
- 7 daily backups
- 4 weekly backups

See [DAILY_BACKUP_SCHEDULE.md](../critical/DAILY_BACKUP_SCHEDULE.md) for schedule details.

### Schedule Data Refresh

Set up a cron job or GitHub Action to refresh meeting data:

```yaml
# .github/workflows/refresh-data.yml
name: Refresh Meeting Data
on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM UTC
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Refresh meetings
        run: python scripts/refresh_meetings.py city-your-city
```

---

## Verification Checklist

Before launching, verify each component:

### API Endpoints

- [ ] Health check: `curl https://your-api/health`
- [ ] Events list: `curl -H "Authorization: Bearer $KEY" https://your-api/api/events`
- [ ] Civic info: `curl -H "Authorization: Bearer $KEY" https://your-api/api/civic/your-city`

### Core Features

```python
from civicos import CivicOS

c = CivicOS("your-city")

# Test each method
print("Testing whats_next...")
result = c.whats_next()
assert result.meetings, "No meetings found"

print("Testing what_happened...")
result = c.what_happened("housing")
assert result.decisions or result.message, "Query failed"

print("Testing what_applies...")
result = c.what_applies("zoning")
assert result.context, "No regulatory context"

print("All tests passed!")
```

### WebSocket Connection

```javascript
// Test from browser console
const socket = io("wss://your-websocket-domain.fly.dev");
socket.on("connect", () => console.log("Connected!"));
socket.on("error", (e) => console.error("Error:", e));
```

### RAG Search

```python
from civic._internal.rag import RAGEngine

rag = RAGEngine("city-your-city")
results = rag.search("recent decisions", top_k=3)
assert len(results) > 0, "RAG search returned no results"
print("RAG working correctly")
```

---

## Troubleshooting

### "No meetings found"

1. Check platform client configuration
2. Verify the city's meeting management URL
3. Test extraction manually:
   ```python
   from civic_extraction import LegistarClient
   client = LegistarClient("your-city")
   events = client.get_events(days_ahead=30)
   print(f"Raw events: {len(events)}")
   ```

### "Database not found"

1. Verify database path: `data/civic_state.db`
2. Run migrations: `python scripts/migrate.py`
3. Check file permissions

### "Vector search returns no results"

1. Verify documents were indexed:
   ```python
   rag = RAGEngine("city-your-city")
   print(f"Document count: {rag.document_count}")
   ```
2. Re-index if needed: `rag.index_documents(corpus_dir)`

### "OpenAI API errors"

1. Verify API key: `echo $OPENAI_API_KEY`
2. Test key directly:
   ```bash
   curl https://api.openai.com/v1/models \
     -H "Authorization: Bearer $OPENAI_API_KEY"
   ```
3. Check usage limits at [platform.openai.com/usage](https://platform.openai.com/usage)

### "CORS errors in browser"

1. Verify `CIVICOS_CORS_ORIGINS` includes your frontend domain
2. Ensure protocol matches (http vs https)
3. Redeploy after changing secrets

---

## Cost Estimation

Target operational cost: **< $7/month**

| Service | Expected Usage | Monthly Cost |
|---------|---------------|--------------|
| Fly.io hosting | 2 small apps | ~$4-5 |
| OpenAI (gpt-4o-mini) | ~10,000 queries | ~$1-3 |
| OpenAI Embeddings | N/A (using local) | $0 |
| External monitoring | UptimeRobot free tier | $0 |

**Cost optimization tips:**
- Use `gpt-4o-mini` instead of `gpt-4` (10x cheaper)
- Use local embeddings (free)
- Cache legislative data to reduce API calls

---

## Support & Resources

- **Architecture overview**: [FINAL_PACKAGE_ARCHITECTURE.md](../critical/FINAL_PACKAGE_ARCHITECTURE.md)
- **Deployment details**: [DEPLOYMENT_GUIDE.md](../critical/DEPLOYMENT_GUIDE.md)
- **All secrets**: [SECRETS_MANAGEMENT.md](../critical/SECRETS_MANAGEMENT.md)
- **Rollback procedures**: [ROLLBACK_PROCEDURES.md](../critical/ROLLBACK_PROCEDURES.md)

For issues, open a ticket at the project repository.
