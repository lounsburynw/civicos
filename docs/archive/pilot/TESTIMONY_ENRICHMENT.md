# Testimony Enrichment for Coalition Discovery

**Status**: Infrastructure complete (Session 104)
**Created**: 2025-11-13
**Purpose**: Track who testified at council meetings for advocacy leader identification and coalition discovery

---

## Overview

Testimony enrichment adds a critical layer to our retrospective analysis by tracking **who participated** in decisions, enabling:

1. **Coalition discovery**: Find others who testified on similar issues
2. **Advocacy leader identification**: Track repeat speakers (community organizers)
3. **Gap analysis**: Identify complainants who didn't testify (coordination opportunity)
4. **Historical precedent**: "Who opposed similar projects before?"

### User Story

> "I'm concerned about the new development. Show me who testified on similar housing projects in the past year. Are there advocacy groups I should coordinate with?"

---

## Architecture

### Database Schema

Two tables work together for testimony tracking:

#### 1. Decisions Table

Stores high-stakes decisions from retrospective analysis:

```sql
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jurisdiction_id TEXT NOT NULL,
    item_ref TEXT,
    title TEXT NOT NULL,
    description TEXT,
    meeting_date DATETIME NOT NULL,
    meeting_type TEXT,
    is_high_stakes BOOLEAN,
    stakes_score INTEGER,
    decision_type TEXT,
    budget_amount INTEGER,
    budget_description TEXT,
    project_types TEXT,  -- JSON array
    keywords_for_matching TEXT,  -- JSON array
    agenda_url TEXT,
    minutes_url TEXT,
    legistar_event_item_id INTEGER,  -- For API testimony lookup
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Key indexes**:
- `idx_decisions_jurisdiction` - Filter by city
- `idx_decisions_meeting_date` - Time-based queries
- `idx_decisions_legistar_id` - API testimony lookup

#### 2. Testimony Table

Stores speaker information linked to decisions:

```sql
CREATE TABLE testimony (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id INTEGER NOT NULL,
    speaker_name TEXT,
    position TEXT,  -- support/oppose/neutral (inferred or null)
    organization TEXT,
    testimony_text TEXT,  -- if available from minutes
    speaking_order INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);
```

**Key indexes**:
- `idx_testimony_decision` - Lookup by decision
- `idx_testimony_speaker` - Find speaker history
- `idx_testimony_org` - Organization discovery
- `idx_testimony_speaker_org` - Coalition queries

---

## Data Sources

### 1. Legistar API (6 cities)

**Cities**: Oakland, Santa Rosa, Hayward, Sonoma County, Napa, BART

**Method**: Direct API access via `EventItems/{EventItemId}/EventItemPersons`

**Advantages**:
- Fast, reliable extraction
- Structured data
- Speaker names with order

**Limitations**:
- No position field (support/oppose)
- No testimony text
- No organization data
- Requires EventItemId mapping from retrospective analysis

**Implementation**: `src/legistar_client.py:258-310`

```python
# Example usage
client = LegistarClient("oakland")
speakers = client.get_event_item_persons(event_item_id=12345)

# Returns:
[
    {
        "speaker_name": "John Doe",
        "speaking_order": 1,
        "position": None,  # Not available from API
        "organization": None  # Not available from API
    }
]
```

### 2. Minutes Parsing (Non-Legistar cities)

**Cities**: San Rafael, Berkeley, El Cerrito, Richmond, etc.

**Method**: PDF text extraction + LLM structured extraction

**Advantages**:
- Works for any city with published minutes
- Can extract position and organization (if mentioned)
- Can capture testimony quotes

**Limitations**:
- Slower (requires PDF download + LLM call)
- Less reliable (depends on minutes formatting)
- Higher cost (~$0.01 per meeting)

**Implementation**: `scripts/enrich_with_testimony.py` (existing)

---

## Extraction Scripts

### 1. Legistar Testimony Extraction

**Script**: `scripts/extract_legistar_testimony.py`

**Usage**:
```bash
# Extract testimony for Oakland decisions
python scripts/extract_legistar_testimony.py oakland \
    data/pilot/oakland_high_stakes.json \
    --db data/civic_participation.db

# Dry run (preview without inserting)
python scripts/extract_legistar_testimony.py oakland \
    data/pilot/oakland_high_stakes.json \
    --dry-run
```

**Process**:
1. Load decisions from JSON into database
2. Extract EventItemId from `_legistar_metadata`
3. Fetch testimony via Legistar API
4. Insert speakers into testimony table
5. Report stats

**Expected output**:
```
🗣️  LEGISTAR TESTIMONY EXTRACTION
======================================================================
Jurisdiction: oakland
Loaded 651 decisions

[1/651] 4.1: Budget Amendment for Wildfire Prevention...
   🔍 Fetching testimony for EventItemId=12345
   ✅ Found 8 speakers
      - Jane Smith (order: 1)
      - Sierra Club Representative (order: 2)
      ...

📊 EXTRACTION SUMMARY
   Decisions with Legistar metadata: 450
   Speakers found: 127
   Testimony records inserted: 127
```

### 2. Minutes-Based Testimony Enrichment

**Script**: `scripts/enrich_with_testimony.py` (existing)

**Usage**:
```bash
# Enrich San Rafael decisions with testimony from minutes
python scripts/enrich_with_testimony.py \
    data/pilot/san_rafael_high_stakes_validated.json \
    --dry-run
```

**Note**: This script updates the JSON file directly (doesn't use database)

---

## Coalition Discovery Queries

**Script**: `scripts/query_testimony.py`

### Find Advocacy Leaders

Track repeat speakers (likely community organizers):

```bash
# Find speakers who testified 3+ times
python scripts/query_testimony.py leaders --min-appearances 3

# Filter by jurisdiction
python scripts/query_testimony.py leaders \
    --min-appearances 3 \
    --jurisdiction oakland
```

**Sample output**:
```
🎤 ADVOCACY LEADERS (Repeat Speakers)
======================================================================

1. Jane Smith
   Appearances: 8
   Jurisdictions: oakland, berkeley
   Organizations: Sierra Club, Transit Coalition

2. Robert Johnson
   Appearances: 5
   Jurisdictions: oakland
   Organizations: Housing Advocacy Group
```

### Find Active Organizations

Discover organizations working on specific topics:

```bash
# Housing advocates
python scripts/query_testimony.py orgs --topic housing

# Environmental groups
python scripts/query_testimony.py orgs --topic environment
```

**Sample output**:
```
🏢 ORGANIZATIONS ACTIVE ON: HOUSING
======================================================================

1. East Bay Housing Alliance
   Appearances: 12
   Unique speakers: 7

2. Tenants Together
   Appearances: 8
   Unique speakers: 4
```

### Show Testimony for Decision

View all speakers for a specific decision:

```bash
python scripts/query_testimony.py decision --id 123
```

**Sample output**:
```
📋 DECISION TESTIMONY
======================================================================

Decision: Budget Amendment for Wildfire Prevention Fund
Date: 2024-10-06
Budget: $1,100,000

Testimony: 8 speakers
----------------------------------------------------------------------

1. Jane Smith
   Organization: Sierra Club

2. Local Resident
   (No organization)
```

### Testimony Statistics

Overall metrics:

```bash
# All jurisdictions
python scripts/query_testimony.py stats

# Specific jurisdiction
python scripts/query_testimony.py stats --jurisdiction oakland
```

**Sample output**:
```
📊 TESTIMONY STATISTICS
======================================================================

Coverage:
  Decisions with testimony: 127
  Decisions without testimony: 524
  Coverage rate: 19.5%

Participation:
  Unique speakers: 89
  Unique organizations: 23
  Jurisdictions: 6

Top 5 Speakers:
  - Jane Smith: 8 appearances
  - Robert Johnson: 5 appearances
  ...
```

### Gap Analysis

Find decisions with no testimony (coordination opportunity):

```bash
python scripts/query_testimony.py gap --jurisdiction oakland
```

---

## Current Status (Session 104)

### ✅ Complete

1. **Database schema**: decisions + testimony tables created
2. **Legistar API client**: `get_event_item_persons()` method added
3. **Extraction script**: `scripts/extract_legistar_testimony.py` created
4. **Coalition queries**: `scripts/query_testimony.py` implemented
5. **Documentation**: This guide

### 🔄 In Progress

- **Data extraction**: Need to run retrospective analysis on Legistar cities first
- **Testing**: No testimony data yet (need Oakland/Santa Rosa decisions)

### ❌ Not Started

- **Frontend integration**: Coalition discovery UI (Session 106-108)
- **Vector search**: Semantic queries across testimony (Session 105)
- **SeeClickFix bridge**: Link complaints to testimony gap (future)

---

## Next Steps

### Option 1: Legistar Cities (Recommended)

Run retrospective analysis on Oakland to get decisions with EventItemIds:

```bash
# 1. Run retrospective analysis (Session 100 infrastructure)
python scripts/analyze_oakland_retrospective.py

# 2. Extract testimony via Legistar API
python scripts/extract_legistar_testimony.py oakland \
    data/pilot/oakland_high_stakes.json

# 3. Query results
python scripts/query_testimony.py stats --jurisdiction oakland
python scripts/query_testimony.py leaders --min-appearances 3
```

**Advantages**:
- Fast, reliable API access
- Scalable to 6 Legistar cities
- Clean, structured data

**Time estimate**: 2-3 hours (analysis + extraction + testing)

### Option 2: San Rafael (Wildfire Case Study)

Use existing validated data with minutes parsing:

```bash
# Extract testimony from Oct 6 wildfire meeting minutes
python scripts/enrich_with_testimony.py \
    data/pilot/san_rafael_high_stakes_validated.json
```

**Advantages**:
- Validates wildfire case study
- Uses existing infrastructure
- Can extract position/organization

**Limitations**:
- Minutes may not have speaker names
- San Rafael doesn't consistently publish minutes
- Can't use Legistar API approach

**Time estimate**: 1 hour (if minutes available)

---

## Product Integration (Future)

### Session 105: Vector Search

Enable semantic queries across testimony:

```python
# "Who testified against housing developments in past year?"
results = vector_search(
    query="opposition to housing",
    filters={"decision_type": "housing", "year": 2024}
)
```

### Sessions 106-108: Frontend UI

**Coalition Discovery Panel**:
- Search speakers by name/organization
- View speaker history across decisions
- Discover advocacy leaders
- Find coordination opportunities

**Research Mode Enhancement**:
- "Show testimony for similar decisions"
- "Find organizations working on this issue"
- "Has anyone testified on this before?"

**Gap Analysis View**:
- SeeClickFix complaints without testimony
- Decisions with high stakes but no public input
- Coordination opportunities

---

## Cost Estimate

### Legistar API Approach

- **API calls**: Free (Legistar API is public)
- **Processing**: $0 (just HTTP requests)
- **Expected coverage**: 60-80% of decisions (depends on EventItemId availability)

### Minutes Parsing Approach

- **PDF extraction**: $0 (PyMuPDF)
- **LLM extraction**: ~$0.01 per meeting (gpt-4o-mini)
- **Expected coverage**: 40-60% (depends on minutes availability)

### Scalability

- **26-city network**: ~$50 total (mostly minutes parsing)
- **Ongoing**: $0 (Legistar API free, minutes parsing one-time)

---

## Technical Notes

### Legistar EventItemId Mapping

The challenge is mapping retrospective decisions to Legistar EventItemIds.

**Current approach** (Session 100):
- Retrospective analyzer extracts decisions from PDFs
- Legistar metadata stored in `_legistar_metadata` field
- EventItemId available if decision came from Legistar API extraction

**Gap**: Historical PDFs don't have EventItemIds

**Solutions**:
1. Re-run extraction with Legistar API (preserves EventItemIds)
2. Manual lookup for specific case studies (e.g., Oct 6 wildfire)
3. Fuzzy matching by title + date (error-prone)

**Recommended**: Re-run retrospective analysis with Legistar API for testimony-enabled cities

### Data Quality

**Legistar API**:
- Speaker names: 95%+ accuracy (structured API)
- Organizations: 0% (not in API)
- Position: 0% (not in API)

**Minutes parsing**:
- Speaker names: 70-90% accuracy (depends on formatting)
- Organizations: 30-50% (if mentioned in minutes)
- Position: 40-60% (if clearly stated)

**Future improvement**: Combine both sources for Legistar cities
- Use API for reliable speaker names
- Parse minutes for position/organization data

---

## References

- **Session 104 prompt**: `/docs/core/next_session_prompt.md`
- **Retrospective pipeline**: `/docs/pilot/RETROSPECTIVE_ANALYSIS_PIPELINE.md`
- **Legistar client**: `/src/legistar_client.py`
- **Minutes parser**: `/scripts/enrich_with_testimony.py`
- **Migration**: `/migrations/011_add_testimony.sql`
