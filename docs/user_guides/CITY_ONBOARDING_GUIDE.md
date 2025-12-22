# City Onboarding Guide

**Adding a New City to Civic**

This guide walks through the complete process of onboarding a new city into the Civic platform. It documents the patterns that worked for San Rafael and generalizes them for new jurisdictions.

**Audience:** Operators deploying Civic to new cities
**Time Estimate:** 30-60 minutes (depending on platform complexity)

---

## Table of Contents

1. [Overview](#overview)
2. [Pre-Onboarding: Research & Detection](#pre-onboarding-research--detection)
3. [Step 1: Gather City Information](#step-1-gather-city-information)
4. [Step 2: Create Configuration Files](#step-2-create-configuration-files)
5. [Step 3: Test Data Source Connectivity](#step-3-test-data-source-connectivity)
6. [Step 4: Bootstrap the City](#step-4-bootstrap-the-city)
7. [Step 5: Verify Ingestion](#step-5-verify-ingestion)
8. [Step 6: Deploy](#step-6-deploy)
9. [Troubleshooting](#troubleshooting)
10. [Appendix: Platform-Specific Details](#appendix-platform-specific-details)

---

## Overview

### What Gets Ingested

For each city, Civic ingests:

| Data Type | Source | Purpose |
|-----------|--------|---------|
| **Meetings** | City platform (Legistar/CivicClerk/ProudCity) | Council, planning, commission meetings |
| **Decisions** | Extracted from meeting agendas | Votes, resolutions, ordinances |
| **Issues** | SeeClickFix API | Citizen-reported problems |
| **Legislative Context** | State bills, federal programs | Regulatory stack |
| **Municipal Code** | Municode (if available) | Local ordinances |

### Supported Platforms

| Platform | Detection | API Type | Example Cities |
|----------|-----------|----------|----------------|
| **Legistar** | API probe at `webapi.legistar.com` | REST API | Berkeley, Oakland, San Francisco |
| **CivicClerk** | OData endpoint probe | OData | El Cerrito, Hayward, San Pablo |
| **ProudCity** | WordPress meta tag detection | Web scraping | San Rafael |

### Cost & Resources

- **API Calls:** Varies by city size (100-1000 calls for initial load)
- **Storage:** ~50-200 MB per city (meetings + vectors)
- **OpenAI:** $0.10-2.00 for embedding generation (depends on content volume)

---

## Pre-Onboarding: Research & Detection

Before creating configuration files, determine which platform the city uses.

### Automatic Detection

Use the platform detection helper to auto-detect:

```python
from civic_extraction.platform_detection import detect_platform

# Probe the city's website
result = detect_platform("https://www.cityofberkeley.info")

if result.source_type:
    print(f"Detected: {result.source_type}")
    print(f"Confidence: {result.confidence:.0%}")
    print(f"Source ID: {result.source_id}")
    print(f"Metadata: {result.metadata}")
else:
    print("No supported platform detected")
    print(f"Errors: {result.errors}")
```

**Confidence Levels:**
- `90%+`: High confidence - proceed with auto-config
- `50-89%`: Medium confidence - verify manually
- `<50%`: Low confidence - manual investigation needed

### Manual Detection

If auto-detection fails, check manually:

1. **Legistar:** Look for `legistar.com` links on city meeting pages
2. **CivicClerk:** Look for URLs containing `civicclerk` or `civicplus`
3. **ProudCity:** Check for `generator` meta tag containing "ProudCity"
4. **Granicus:** Video-focused platform (meetings link to granicus.com)

### Decision: Which Path?

| If Platform Is... | Then... |
|-------------------|---------|
| Legistar | Create extraction config with `source_type: legistar` |
| CivicClerk | Create extraction config with `source_type: civicclerk` |
| ProudCity | Create extraction config with `source_type: proudcity`, run discovery |
| Unknown | Investigate further or build custom extractor |

---

## Step 1: Gather City Information

Before creating configs, gather this information:

### Required Information

| Field | Example | How to Find |
|-------|---------|-------------|
| **Jurisdiction ID** | `city-san-rafael` | Lowercase city name with hyphens |
| **Official Name** | `San Rafael, CA` | City website header |
| **Base URL** | `https://www.cityofsanrafael.org` | City's official website |
| **Platform Type** | `proudcity` | From auto-detection (Step 0) |

### Platform-Specific Information

**Legistar:**
- Client name (e.g., `berkeley`, `sanfrancisco`) - extracted from Legistar URL
- Available via API probe in auto-detection

**CivicClerk:**
- Client ID (e.g., `elcerrito`, `hayward`) - in the URL path
- OData endpoint URL

**ProudCity:**
- Archive page URLs for each meeting type
- Can be auto-discovered with `discover_meeting_types()`

### Optional: Federal Programs

Look up the city's federal allocations at [HUD Exchange](https://www.hudexchange.info/grantees/allocations-awards/):
- CDBG allocation (Community Development Block Grant)
- HOME allocation (if applicable)

---

## Step 2: Create Configuration Files

You need two configuration files:

### 2a. Extraction Config

Create `data/extraction/{city-name}.json`:

```json
{
  "source_id": "{platform}-{city-name}",
  "source_type": "{legistar|civicclerk|proudcity}",
  "jurisdiction_id": "city-{city-name}",
  "base_url": "https://www.city-website.org",
  "auto_discover": true,
  "archives": {},
  "metadata": {
    "created": "2025-01-15",
    "notes": "Initial configuration"
  }
}
```

**Example (San Rafael):**

```json
{
  "source_id": "proudcity-san-rafael",
  "source_type": "proudcity",
  "jurisdiction_id": "city-san-rafael",
  "base_url": "https://www.cityofsanrafael.org",
  "auto_discover": true,
  "archives": {
    "city_council": "/city-council-meetings/",
    "planning_commission": "/planning-commission-meetings/"
  },
  "metadata": {
    "created": "2025-12-21",
    "notes": "Archives discovered via discover_meeting_types()"
  }
}
```

### Discovering Archives (ProudCity)

For ProudCity sites, you can auto-discover meeting types:

```python
from civic_extraction.clients.proudcity import ProudCitySource

# Load from config
source = ProudCitySource.from_jurisdiction("city-san-rafael")

# Or create manually
source = ProudCitySource(
    base_url="https://www.cityofsanrafael.org",
    jurisdiction_id="city-san-rafael"
)

# Discover meeting archive pages
meeting_types = source.discover_meeting_types()
print(f"Found {len(meeting_types)} meeting types:")
for mt in meeting_types:
    print(f"  - {mt['name']}: {mt['path']}")
```

Then add the discovered paths to `archives` in your config.

### 2b. Jurisdiction Override (Optional)

Create `data/jurisdiction_overrides/city-{city-name}.json` for federal program details:

```json
{
  "jurisdiction_id": "city-{city-name}",
  "jurisdiction_name": "City Name, CA",
  "last_updated": "2025-01-15T00:00:00.000000",
  "federal_programs": {
    "cdbg": {
      "program_name": "Community Development Block Grant",
      "fy2025_allocation": 500000,
      "allocation_source": "HUD FY2025 CDBG Allocations",
      "allocation_url": "https://www.hudexchange.info/..."
    }
  }
}
```

This is optional but enables the `what_applies()` method to return accurate federal program context.

---

## Step 3: Test Data Source Connectivity

Before running the full bootstrap, validate that the source is accessible.

### Preflight Validation

```python
from civic_extraction.clients.proudcity import ProudCitySource

# Load source from config
source = ProudCitySource.from_jurisdiction("city-san-rafael")

# Run health check
health = source.health()
print(f"Healthy: {health.healthy}")
print(f"Latency: {health.latency_ms}ms")

if not health.healthy:
    print(f"Error: {health.error_message}")

# Check source info
print(f"Source ID: {source.source_id}")
print(f"Jurisdiction: {source.jurisdiction_id}")
```

### Common Validation Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Connection refused` | Firewall or VPN blocking | Try from different network |
| `404 Not Found` | Wrong URL path | Check archive URLs manually |
| `SSL Certificate Error` | Outdated certificates | Add cert verification override |
| `Rate limited` | Too many requests | Add delay between requests |

---

## Step 4: Bootstrap the City

Once configuration is ready, run the bootstrap command.

### Using the CLI

```bash
# Activate environment
source civic-env/bin/activate

# Run bootstrap (standard)
civic-bootstrap san-rafael

# With options
civic-bootstrap san-rafael --days-past 90 --verbose

# Skip indexing (ingest only)
civic-bootstrap san-rafael --skip-index

# JSON output for scripting
civic-bootstrap san-rafael --json
```

### What Bootstrap Does

The pipeline runs three stages:

1. **Discover:** Finds available meeting types and date ranges
2. **Ingest:** Fetches meeting agendas, extracts decisions, stores in SQLite
3. **Index:** Creates vector embeddings for semantic search

### Expected Output

```
Civic Bootstrap: city-san-rafael
========================================
Source: proudcity-san-rafael
URL: https://www.cityofsanrafael.org

  discover: OK (2.1s)
  ingest: OK (157 items) [45.3s]
  index: OK (312 items) [12.8s]

Bootstrap Summary
--------------------
Status: SUCCESS
Duration: 60.2s
Meetings: 157 ingested
Indexed: 312 items

Next: civic-status --jurisdiction san-rafael
```

### Checkpoint & Resume

If bootstrap fails partway through, it can resume from a checkpoint:

```bash
# First run fails at meeting 50
civic-bootstrap san-rafael
# Error at meeting 50...

# Resume from checkpoint
civic-bootstrap san-rafael --resume
# Continues from meeting 50...
```

Checkpoints are stored in `data/checkpoints/`.

---

## Step 5: Verify Ingestion

After bootstrap completes, verify the data was ingested correctly.

### Check Status

```bash
# Overall status
civic-status --jurisdiction san-rafael

# Compare ingested vs source counts
civic-status --jurisdiction san-rafael --check-gaps
```

### Expected Output

```
Civic Status: city-san-rafael
========================================
Data Corpus Summary
--------------------
  meetings        : 157 items (7d ago) [OK]
  decisions       : 423 items (7d ago) [OK]
  issues          : 89 items  (2d ago) [OK]

Source Comparison
--------------------
  meetings        : 157/160 | 98.1% coverage | gap: 3 [OK]
  issues          : 89/95   | 93.7% coverage | gap: 6 [OK]

  Overall coverage: 95.9%
```

### Verify Vector Search

```python
from civic import Civic

c = Civic("san-rafael")

# Test semantic search
results = c.what_happened("housing")
print(f"Found {len(results)} results about housing")

# Test upcoming meetings
meetings = c.whats_next()
print(f"Found {len(meetings)} upcoming meetings")
```

### Troubleshooting Low Coverage

| Gap | Possible Cause | Fix |
|-----|----------------|-----|
| `>10%` meetings | Archive pages not all discovered | Run `discover_meeting_types()` again |
| `>10%` issues | SeeClickFix place_url wrong | Check SeeClickFix API manually |
| `0` items | Connection or auth failure | Check preflight validation |

---

## Step 6: Deploy

Once data is verified locally, deploy the city to production.

For deployment details, see [DEPLOYMENT_GUIDE.md](../critical/DEPLOYMENT_GUIDE.md).

### Quick Checklist

- [ ] Data directory synced to production storage
- [ ] Vector database files included (`data/pilot/vectors/`)
- [ ] Environment variables configured (OpenAI key, CIVIC_WEB_KEY)
- [ ] API endpoints tested
- [ ] Frontend configured for new jurisdiction

---

## Troubleshooting

### Platform Detection Fails

**Symptoms:** `detect_platform()` returns `None` or low confidence.

**Fixes:**
1. Check if the site uses JavaScript rendering (try `curl` to see raw HTML)
2. Look for platform mentions in page source
3. Check if city uses a different domain for meetings
4. Fall back to manual investigation

### Bootstrap Times Out

**Symptoms:** `civic-bootstrap` hangs or takes >30 minutes.

**Fixes:**
1. Use `--verbose` to see which stage is slow
2. Reduce date range: `--days-past 7` for testing
3. Check network connectivity to source
4. Use `--skip-index` to test ingest separately

### No Meetings Found

**Symptoms:** Bootstrap completes but shows `0 items`.

**Decision Tree:**
```
Is source.health() passing?
├─ No → Fix connectivity issues first
└─ Yes → Are archive URLs correct?
   ├─ No → Run discover_meeting_types() or check manually
   └─ Yes → Is date range correct?
      ├─ No → Adjust --days-past / --days-ahead
      └─ Yes → Check if site uses JavaScript rendering
```

### Vector Indexing Fails

**Symptoms:** Ingest succeeds but index fails.

**Fixes:**
1. Check OpenAI API key is set and has credits
2. Check disk space for ChromaDB
3. Try `--skip-index` then index manually
4. Check for corrupted embeddings in previous runs

---

## Appendix: Platform-Specific Details

### Legistar

**API Base:** `https://webapi.legistar.com/v1/{client}`

**Key Endpoints:**
- `/Events` - Meetings list
- `/EventItems/{id}` - Agenda items
- `/Matters/{id}` - Legislation details

**Gotchas:**
- Date format: ISO 8601 (`2025-01-15T00:00:00`)
- Rate limits: ~100 requests/minute
- Some cities restrict API access (need to request key)

**Example Config:**
```json
{
  "source_id": "legistar-berkeley",
  "source_type": "legistar",
  "jurisdiction_id": "city-berkeley",
  "base_url": "https://webapi.legistar.com/v1/berkeley"
}
```

### CivicClerk

**API Type:** OData v4

**Key Endpoints:**
- `/MeetingGroups` - Committee types
- `/Meetings` - Meeting list
- `/AgendaItems` - Agenda details

**Gotchas:**
- OData filter syntax: `$filter=MeetingDate ge 2025-01-01`
- Some endpoints require authentication token
- Pagination via `$skip` and `$top`

**Example Config:**
```json
{
  "source_id": "civicclerk-elcerrito",
  "source_type": "civicclerk",
  "jurisdiction_id": "city-el-cerrito",
  "base_url": "https://elcerritoca.civicclerk.com/odata"
}
```

### ProudCity

**API Type:** WordPress/HTML scraping

**Detection:** Look for `<meta name="generator" content="ProudCity...">`

**Meeting Page Pattern:** `/city-council-meetings/`, `/planning-commission-meetings/`

**Gotchas:**
- JavaScript-rendered content may need special handling
- Archive page structure varies by theme
- Video links may point to YouTube or Granicus

**Auto-Discovery:**
```python
# ProudCity supports auto-discovery of meeting types
source = ProudCitySource.from_jurisdiction("city-san-rafael")
meeting_types = source.discover_meeting_types()
```

**Example Config:**
```json
{
  "source_id": "proudcity-san-rafael",
  "source_type": "proudcity",
  "jurisdiction_id": "city-san-rafael",
  "base_url": "https://www.cityofsanrafael.org",
  "auto_discover": true,
  "archives": {
    "city_council": "/city-council-meetings/",
    "planning_commission": "/planning-commission-meetings/"
  }
}
```

---

## Related Documentation

- [ADMIN_SETUP_GUIDE.md](./ADMIN_SETUP_GUIDE.md) - Full environment setup
- [DEPLOYMENT_GUIDE.md](../critical/DEPLOYMENT_GUIDE.md) - Production deployment
- [DATA_INGESTION_OPERATIONS.md](../critical/DATA_INGESTION_OPERATIONS.md) - Ingestion operations
- [TESTING_STRATEGY.md](../TESTING_STRATEGY.md) - Testing approach
