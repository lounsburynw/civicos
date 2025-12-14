# Retrospective Analysis Pipeline

**Status**: Session 98 Complete - Full pipeline operational
**Purpose**: Extract high-stakes municipal decisions and measure coordination gaps at scale
**Use Case**: Foundation pitch evidence, pilot validation, pattern recognition

---

## Overview

The Retrospective Analysis Pipeline transforms 12 months of meeting archives into coordination gap measurements. It answers: **How many affected residents never testified at high-stakes decisions?**

**Key Innovation**: Automated high-stakes extraction with budget/impact metadata + SeeClickFix complaint matching

---

## Pipeline Architecture

**Extraction Strategy**: Hybrid Structured + RAG Approach (Session 99+)
- **Structured extraction**: Item-by-item processing with metadata (budget, date, type)
- **RAG-ready**: Embeddings pipeline for semantic search, pattern discovery, coalition building
- **Scalable**: Handles both formatted agendas AND unformatted documents across 26+ cities

```
1. SCRAPE ARCHIVES (Multi-Document)
   └─> scripts/scrape_sanrafael_archives.py
       Input:  Archive URLs (City Council, Planning, etc.)
       Output: data/pilot/san_rafael_meetings_enhanced.json
       Result: 114 meetings with agenda packet + minutes URLs
       Note:   Session 99 - Now extracts both agenda packets AND minutes

2. EXTRACT HIGH-STAKES DECISIONS (Item-by-Item)
   └─> scripts/analyze_sanrafael_retrospective.py
       Input:  Meeting metadata from (1)
       Method: Item-by-item extraction (no 200K truncation)
       Output: data/pilot/san_rafael_high_stakes_decisions.json
       Result: 15-30 decisions with budget/impact/keywords
       RAG:    Generates embeddings for semantic search (Session 100+)

3. MATCH SEECLICKFIX COMPLAINTS
   └─> scripts/match_seeclickfix_to_decisions.py
       Input:  High-stakes decisions from (2)
       Output: data/pilot/san_rafael_complaint_matches.json
       Result: Per-decision complaint counts (30-day lookback)

4. EXTRACT TESTIMONY DATA (Session 104+)
   Two approaches depending on city platform:

   A. Legistar API (Oakland, Santa Rosa, Hayward, etc.)
      └─> scripts/extract_legistar_testimony.py
          Input:  High-stakes decisions from (2) with EventItemIds
          Method: Direct API call to EventItems/{id}/EventItemPersons
          Output: SQLite database (decisions + testimony tables)
          Result: Speaker names, speaking order (no position/org)
          Speed:  Fast (API calls only)
          Cost:   $0 (API is free)

   B. Minutes Parsing (San Rafael, Berkeley, El Cerrito, etc.)
      └─> scripts/enrich_with_testimony.py
          Input:  Minutes PDFs from (1)
          Method: PyMuPDF extraction + LLM structured extraction
          Output: Enriched JSON with testimony counts, speakers, votes
          Result: Speaker names + position + organization (if mentioned)
          Speed:  Slower (PDF + LLM per meeting)
          Cost:   ~$0.01 per meeting

5. QUERY TESTIMONY DATA (Session 104+)
   └─> scripts/query_testimony.py
       Input:  SQLite testimony database
       Output: Coalition discovery insights
       Queries:
         - Advocacy leaders (repeat speakers)
         - Active organizations by topic
         - Testimony for specific decisions
         - Coordination gaps (complaints vs testimony)

6. CALCULATE COORDINATION GAPS
   └─> scripts/calculate_coordination_gaps.py
       Input:  Complaint matches from (3) + testimony from (4)
       Output: data/pilot/san_rafael_coordination_gaps.json
       Result: Gap statistics, pattern analysis, foundation evidence

6. BUILD VECTOR INDEX (Future - Session 100+)
   └─> scripts/build_decision_embeddings.py
       Input:  High-stakes decisions from (2)
       Method: ChromaDB + sentence transformers
       Output: data/pilot/decision_vectors.db
       Result: Semantic search, similarity, historical precedent queries
```

---

## Step 1: Scrape Meeting Archives

### Command

```bash
python scripts/scrape_sanrafael_archives.py \
  --start-date 2024-11-01 \
  --end-date 2025-11-30 \
  --output data/pilot/san_rafael_meetings_12month.json
```

### What It Does

- Visits 6 San Rafael archive pages (City Council, Planning, Tax Oversight, Fire, Zoning, Subcommittees)
- Extracts meeting titles, dates, agenda URLs
- Filters to date range (12-month window)
- Outputs structured JSON with 114 meetings

### Output Format

```json
{
  "jurisdiction_id": "city-san-rafael",
  "total_meetings": 114,
  "meetings_by_type": {
    "city_council": 33,
    "planning_commission": 23,
    "tax_oversight": 2,
    ...
  },
  "meetings": {
    "city_council": [
      {
        "title": "City Council – October 6, 2025",
        "meeting_slug": "city-council-october-6-2025",
        "meeting_url": "https://...",
        "agenda_packet_url": "https://...#tab-agenda-packet",
        "date_parsed": "2025-10-06",
        "meeting_type": "city_council"
      },
      ...
    ]
  }
}
```

### Time: ~10 seconds (no LLM calls, just HTML parsing)

---

## Step 2: Extract High-Stakes Decisions

### Command

```bash
# All meeting types
python scripts/analyze_sanrafael_retrospective.py \
  data/pilot/san_rafael_meetings_12month.json \
  --output data/pilot/san_rafael_high_stakes_decisions.json \
  --min-budget 100000 \
  --min-stakes 6

# City Council only (faster testing)
python scripts/analyze_sanrafael_retrospective.py \
  data/pilot/san_rafael_meetings_12month.json \
  --output data/pilot/san_rafael_high_stakes_test.json \
  --meeting-types city_council \
  --min-stakes 6
```

### What It Does

- For each meeting, downloads agenda packet PDF
- Uses **gemini-2.5-pro** with specialized high-stakes extraction prompt
- Extracts:
  - Budget amounts ($100K+ threshold)
  - Project sizes (# of units for development)
  - Affected population estimates
  - Stakes score (1-10 scale)
  - Keywords for SeeClickFix matching
  - Decision type (budget/development/environmental/policy)

### High-Stakes Criteria

**Auto-flagged if ANY apply:**
1. Budget ≥ $100K (supplemental appropriations, capital projects, contracts)
2. Development ≥ 20 units (residential/commercial)
3. Environmental/policy affecting ≥ 1,000 residents
4. Tax/fee changes (new taxes, fee increases)

**Stakes Score Rubric:**
- **10**: Citywide, $1M+, affects all/most residents
- **8-9**: Major district, $500K-$1M
- **6-7**: Significant local, $100K-$500K, 1,000+ residents
- **4-5**: Moderate, <$100K, 100-1,000 residents
- **1-3**: Low impact, <100 residents

### Output Format

```json
{
  "jurisdiction_id": "city-san-rafael",
  "meetings_analyzed": 33,
  "total_high_stakes_decisions": 18,
  "summary": {
    "total_budget_amount": 5200000,
    "decision_types_breakdown": {
      "budget": 8,
      "development": 5,
      "environmental": 3,
      "policy": 2
    }
  },
  "decisions": [
    {
      "item_ref": "5.g",
      "title": "Supplemental Appropriation for Wildfire Prevention Program",
      "description": "Measure C fund allocation of $1,108,319...",
      "meeting_date": "2025-10-06",
      "meeting_type": "city_council",
      "is_high_stakes": true,
      "stakes_score": 10,
      "decision_type": "budget",
      "budget_amount": 1108319,
      "budget_description": "Measure C wildfire prevention supplemental",
      "affected_population_estimate": 60000,
      "geographic_scope": "citywide",
      "project_types": ["environment", "budget"],
      "keywords_for_matching": [
        "fire", "wildfire", "tree", "vegetation", "hazard",
        "defensible", "space", "fuel", "brush"
      ],
      "agenda_url": "https://..."
    },
    ...
  ]
}
```

### Time:
- **1-2 minutes per meeting** (PDF download + LLM extraction)
- **33 City Council meetings**: 30-60 minutes
- **114 total meetings**: 2-3 hours

### Cost:
- **gemini-2.5-pro**: $1.25 per 1M tokens
- **~200K tokens per agenda** (large PDFs)
- **~$0.25 per meeting**
- **$8-10 for 33 meetings**, **$28-30 for 114 meetings**

---

## Step 3: Match SeeClickFix Complaints

### Command

```bash
python scripts/match_seeclickfix_to_decisions.py \
  data/pilot/san_rafael_high_stakes_decisions.json \
  --output data/pilot/san_rafael_complaint_matches.json \
  --lookback-days 30 \
  --max-pages 10
```

### What It Does

- For each high-stakes decision:
  - Calculates 30-day lookback window before decision date
  - Fetches San Rafael SeeClickFix issues (10 pages, ~1,000 issues)
  - Filters by date range
  - Matches by keywords from Step 2
  - Records complaint count + issue details

### Matching Logic

**Keyword matching** (case-insensitive):
- Checks: title, description, category, request_type
- Uses keywords extracted during high-stakes analysis
- Example: `["fire", "wildfire", "tree", "vegetation"]` → matches "Tree limb hanging over house" complaint

### Output Format

```json
{
  "jurisdiction_id": "city-san-rafael",
  "statistics": {
    "total_decisions": 18,
    "decisions_with_complaints": 15,
    "total_complaints": 342,
    "average_complaints_per_decision": 22.8
  },
  "matches": [
    {
      "decision_title": "Supplemental Appropriation for Wildfire...",
      "decision_date": "2025-10-06",
      "decision_type": "budget",
      "budget_amount": 1108319,
      "keywords": ["fire", "wildfire", "tree", ...],
      "lookback_window": {
        "start": "2025-09-06T00:00:00+00:00",
        "end": "2025-10-06T23:59:59+00:00",
        "days": 30
      },
      "complaints_found": 22,
      "complaints": [
        {
          "id": 12345,
          "title": "Tree limb hanging over house",
          "created_at": "2025-09-15T10:30:00Z",
          "matched_keywords": ["tree"]
        },
        ...
      ],
      "testimony_count": null,
      "coordination_gap": null
    },
    ...
  ]
}
```

### Time: ~2-3 minutes per decision (SeeClickFix API rate limits)
### Cost: Free (SeeClickFix API is public)

---

## Step 4: Extract Testimony Data (Session 104+)

### Two Approaches

#### A. Legistar API (Recommended for Legistar Cities)

**Command:**

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

**What It Does:**

1. Loads decisions from JSON into SQLite database
2. Extracts `EventItemId` from `_legistar_metadata` field
3. Calls Legistar API: `EventItems/{EventItemId}/EventItemPersons`
4. Inserts speaker records into testimony table
5. Reports statistics

**Output:**

```
🗣️  LEGISTAR TESTIMONY EXTRACTION
======================================================================
Jurisdiction: oakland
Loaded 651 decisions

[1/651] 4.1: Budget Amendment...
   🔍 Fetching testimony for EventItemId=12345
   ✅ Found 8 speakers
      - Jane Smith (order: 1)
      - Sierra Club Representative (order: 2)

📊 EXTRACTION SUMMARY
   Decisions with Legistar metadata: 450
   Speakers found: 127
   Testimony records inserted: 127
```

**Time:** ~5-10 seconds per decision (API calls)
**Cost:** $0 (Legistar API is free)

**Advantages:**
- Fast, reliable
- Structured data
- Speaker names with order

**Limitations:**
- No position field (support/oppose)
- No organization data
- No testimony text
- Requires EventItemId from retrospective analysis

#### B. Minutes Parsing (For Non-Legistar Cities)

**Command:**

```bash
# Enrich San Rafael decisions with testimony from minutes
python scripts/enrich_with_testimony.py \
  data/pilot/san_rafael_high_stakes_validated.json \
  --dry-run
```

**What It Does:**

1. Groups decisions by meeting date
2. Downloads minutes PDFs
3. Extracts text with PyMuPDF
4. Uses LLM to extract testimony data
5. Updates JSON file with counts, speakers, votes

**Time:** ~1-2 minutes per meeting (PDF + LLM)
**Cost:** ~$0.01 per meeting

**Advantages:**
- Works for any city with published minutes
- Can extract position and organization
- Can capture testimony quotes

**Limitations:**
- Slower (PDF download + LLM)
- Less reliable (depends on formatting)
- Minutes may not have speaker names
- Higher cost

---

## Step 5: Query Testimony Data (Session 104+)

### Coalition Discovery Queries

**Find Advocacy Leaders** (repeat speakers):

```bash
# Find speakers who testified 3+ times
python scripts/query_testimony.py leaders --min-appearances 3

# Filter by jurisdiction
python scripts/query_testimony.py leaders \
  --min-appearances 3 \
  --jurisdiction oakland
```

**Find Active Organizations** by topic:

```bash
# Housing advocates
python scripts/query_testimony.py orgs --topic housing

# Environmental groups
python scripts/query_testimony.py orgs --topic environment
```

**Show Testimony for Specific Decision:**

```bash
python scripts/query_testimony.py decision --id 123
```

**Testimony Statistics:**

```bash
# All jurisdictions
python scripts/query_testimony.py stats

# Specific jurisdiction
python scripts/query_testimony.py stats --jurisdiction oakland
```

**Sample Output:**

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
```

---

## Step 6: Calculate Coordination Gaps

### Prerequisites

**Manual step required**: Add testimony counts from meeting minutes/videos

Edit `data/pilot/san_rafael_complaint_matches.json` and add `testimony_count` to each match:

```json
{
  "decision_title": "Supplemental Appropriation for Wildfire...",
  "complaints_found": 22,
  "testimony_count": 4,  // ← Add this manually from minutes
  ...
}
```

### Command

```bash
python scripts/calculate_coordination_gaps.py \
  data/pilot/san_rafael_complaint_matches.json \
  --output data/pilot/san_rafael_coordination_gaps.json
```

### What It Does

- Calculates gap for each decision: `(complaints - testimony) / complaints`
- Aggregates statistics:
  - Total gap across all decisions
  - Average gap percentage
  - Patterns by decision type, budget range, month, meeting type
- Identifies top 5 coordination opportunities

### Output Format

```json
{
  "statistics": {
    "total_decisions": 18,
    "decisions_with_testimony_data": 12,
    "total_complaints": 342,
    "total_testimony": 48,
    "total_gap": 294,
    "average_gap_percentage": 85.9,
    "gaps_by_decision": [
      {
        "decision_title": "Supplemental Appropriation...",
        "complaints": 22,
        "testimony": 4,
        "gap": 18,
        "gap_percentage": 81.8,
        "budget_amount": 1108319
      },
      ...
    ],
    "patterns": {
      "by_decision_type": {
        "budget": {
          "count": 8,
          "total_complaints": 156,
          "total_testimony": 22,
          "average_gap_percentage": 85.9
        },
        ...
      },
      "by_budget_range": {
        "$1M+": {
          "count": 3,
          "total_complaints": 78,
          "average_gap_percentage": 87.2
        },
        ...
      }
    }
  }
}
```

### Time: <1 second (simple calculation)

---

## Complete Example Workflow

### Full 12-Month Analysis (All Meeting Types)

```bash
# Step 1: Scrape archives (10 seconds)
python scripts/scrape_sanrafael_archives.py \
  --start-date 2024-11-01 \
  --end-date 2025-11-30 \
  --output data/pilot/san_rafael_meetings_12month.json

# Step 2: Extract high-stakes decisions (2-3 hours, $28-30)
python scripts/analyze_sanrafael_retrospective.py \
  data/pilot/san_rafael_meetings_12month.json \
  --output data/pilot/san_rafael_high_stakes_decisions.json \
  --min-budget 100000 \
  --min-stakes 6

# Step 3: Match SeeClickFix complaints (30-60 minutes)
python scripts/match_seeclickfix_to_decisions.py \
  data/pilot/san_rafael_high_stakes_decisions.json \
  --output data/pilot/san_rafael_complaint_matches.json \
  --lookback-days 30

# Step 3.5: Manually add testimony counts to JSON file
# (Open data/pilot/san_rafael_complaint_matches.json, add "testimony_count" fields)

# Step 4: Calculate coordination gaps (<1 second)
python scripts/calculate_coordination_gaps.py \
  data/pilot/san_rafael_complaint_matches.json \
  --output data/pilot/san_rafael_coordination_gaps.json
```

### Quick Test (City Council Only)

```bash
# Step 2: Extract City Council decisions only (30-60 minutes, $8-10)
python scripts/analyze_sanrafael_retrospective.py \
  data/pilot/san_rafael_meetings_12month.json \
  --output data/pilot/san_rafael_cc_decisions.json \
  --meeting-types city_council \
  --min-stakes 6

# Steps 3-4: Same as above
```

---

## Technical Details

### Models Used

**gemini-2.5-pro** (Step 2 only):
- **Context**: 2M tokens (handles large agenda packets)
- **Cost**: $1.25 per 1M tokens
- **Speed**: Fast (newer than gemini-1.5-pro)
- **Reasoning**: Best for long documents with structured extraction

### Code Architecture

**`src/retrospective_analyzer.py`** (465 lines):
- `RetrospectiveAnalyzer` class extends `AgendaIntegrator`
- `HighStakesDecision` dataclass (16 fields)
- High-stakes extraction prompt (90 lines, specialized)
- Batch processing with progress tracking

**`scripts/scrape_sanrafael_archives.py`** (380 lines):
- `SanRafaelArchiveScraper` class
- BeautifulSoup HTML parsing
- Date extraction from meeting slugs
- Pattern: `/meetings/{slug}/` → agenda URLs

**`scripts/analyze_sanrafael_retrospective.py`** (260 lines):
- Converts scraped meetings → event format
- Batch processes with RetrospectiveAnalyzer
- Aggregates statistics

**`scripts/match_seeclickfix_to_decisions.py`** (310 lines):
- Uses `seeclickfix_client.py` (existing)
- Keyword matching across text fields
- 30-day lookback window

**`scripts/calculate_coordination_gaps.py`** (270 lines):
- Pattern analysis (decision type, budget, month, meeting type)
- Statistical aggregation
- Top opportunities identification

---

## Expected Outcomes (Hypotheses)

Based on Session 96-97 research and Oct 6 case study:

### Decision Patterns

**Budget Decisions**:
- **15-20** per year (Feb-March FY adoption, Sep-Oct supplementals)
- **$100K-$2M** range
- **85-95%** coordination gap (large affected population, low testimony)

**Development Decisions**:
- **10-15** per year (spring/summer construction season)
- **20-200 units** range
- **70-85%** coordination gap (neighborhood-specific concerns)

**Environmental Decisions**:
- **5-10** per year (seasonal: wildfire pre-fire season, stormwater pre-rain)
- **$50K-$500K** range
- **80-90%** coordination gap (diffuse impacts, high complaint volume)

### Coordination Gap Hypotheses

**Overall**:
- **85-95%** average gap across all decisions
- **10-50** SeeClickFix complaints per decision (avg ~25)
- **5-10%** testimony rate (complaints → testimony)

**If validated**:
- Gap is **systemic** across decision types
- SeeClickFix bridge works for **all** operational→policy connections
- Affected population **findable** at scale
- Pilot has **multiple opportunities** (not one-shot)

---

## Validation Checkpoints

### Session 98 Success Criteria

- ✅ **15-30 high-stakes decisions** identified (12 months)
- ✅ **10+ complaints** matched per decision (average)
- ✅ **Coordination gap >50%** (complaints vs testimony)
- ✅ **Decision patterns** identified (budget cycles, seasonal trends)

### Foundation Pitch Evidence

**Minimum viable evidence**:
- "12 months, **X decisions**, **Y residents**, **Z% avg gap**"
- "Top 5 case studies beyond Oct 6"
- "Pattern: Budget decisions in Sep-Oct have 85%+ gaps"

**Strong evidence**:
- "30 decisions, 600+ affected residents, 87% coordination gap"
- "Validated across 3 cities (San Rafael, Berkeley, Santa Rosa)"
- "Predictable: 90% of budget decisions cluster in Feb-March and Sep-Oct"

---

## Troubleshooting

### Issue: No agenda PDF URL found

**Cause**: Some meetings don't publish agenda packets to web
**Fix**: Update scraper with `--fetch-pdf-urls` flag (slower, visits each page)

### Issue: LLM extraction finds 0 high-stakes decisions

**Cause**: Agenda content might be procedural/administrative
**Fix**: Lower `--min-stakes` threshold (try 4 or 5 instead of 6)

### Issue: SeeClickFix matching finds 0 complaints

**Cause**: Keywords may be too specific
**Fix**: Review `keywords_for_matching` in decisions JSON, add broader terms manually

### Issue: Timeout on Step 2

**Cause**: 114 meetings × 2 min/meeting = 4 hours
**Fix**: Run in background with `nohup`, or split by meeting type:

```bash
# Split analysis
for type in city_council planning_commission tax_oversight; do
  python scripts/analyze_sanrafael_retrospective.py \
    data/pilot/san_rafael_meetings_12month.json \
    --output data/pilot/${type}_decisions.json \
    --meeting-types ${type}
done

# Merge results later
python scripts/merge_decisions.py data/pilot/*_decisions.json \
  --output data/pilot/san_rafael_high_stakes_all.json
```

---

## Future Enhancements

### Automation Opportunities (Session 99+)

1. **Testimony count extraction**: Parse meeting minutes/videos automatically
2. **PDF URL resolution**: Direct download links from meeting pages
3. **Multi-jurisdiction**: Generalize scraper for other cities
4. **Real-time monitoring**: Alert when high-stakes decisions scheduled

### Pattern Recognition (Session 100+)

1. **Budget cycle prediction**: Auto-identify Feb-March and Sep-Oct windows
2. **Seasonal trends**: Wildfire (Sep-Oct), stormwater (Nov-Jan)
3. **Neighborhood clustering**: Development projects in same areas
4. **State mandate correlation**: Compliance deadlines drive decisions

---

## Session 98 Deliverables

**Code** (4 new files, 1,685 lines):
- `src/retrospective_analyzer.py` (465 lines)
- `scripts/scrape_sanrafael_archives.py` (380 lines)
- `scripts/analyze_sanrafael_retrospective.py` (260 lines)
- `scripts/match_seeclickfix_to_decisions.py` (310 lines)
- `scripts/calculate_coordination_gaps.py` (270 lines)

**Data** (generated):
- `data/pilot/san_rafael_meetings_12month.json` (114 meetings)
- `data/pilot/san_rafael_high_stakes_decisions.json` (15-30 decisions)
- `data/pilot/san_rafael_complaint_matches.json` (complaint counts)
- `data/pilot/san_rafael_coordination_gaps.json` (final evidence)

**Documentation**:
- This file: Complete pipeline guide

**Model Registry**:
- Added `gemini-2.5-pro` (2M context, $1.25/1M tokens)

---

## Related Documentation

- `docs/pilot/OCT_6_WILDFIRE_CASE_STUDY.md` - Case study that validates approach
- `docs/pilot/TESTIMONY_ENRICHMENT.md` - Session 104 testimony extraction guide (NEW)
- `docs/strategy/FOCAL_POINT_DECISION_AWARENESS.md` - Strategic context
- `docs/architecture/SEECLICKFIX_INTEGRATION_ARCHITECTURE.md` - SeeClickFix bridge design
- `docs/core/next_session_prompt.md` - Current session goals

---

**Sessions**: 98 (pipeline), 103 (budget validation), 104 (testimony enrichment)
**Last Updated**: 2025-11-13
**Status**: Intelligence layer 80% complete (decisions + testimony), vector search pending (Session 105)
