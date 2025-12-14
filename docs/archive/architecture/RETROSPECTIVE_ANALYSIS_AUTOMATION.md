# Retrospective Analysis Automation Architecture

**Created**: Session 96 (November 2025)
**Status**: Design Document
**Priority**: CRITICAL - Required for scaling to 26+ cities

---

## TL;DR

**The Problem**: Manual retrospective analysis doesn't scale (26 cities × 24 meetings = 624 meetings/year × 5 high-stakes items = 3,120 decisions annually)

**The Solution**: Automated pipeline from meeting extraction → high-stakes classification → SeeClickFix matching → gap measurement → pattern recognition

**The Goal**: One command generates comprehensive city state representation for any jurisdiction

---

## Why Automation is Critical

### Scale Requirements

**Current**: 26 cities operational
**Target**: 340+ cities (all SeeClickFix jurisdictions)
**Annual Load**:
- 26 cities × 24 meetings/year = **624 meetings**
- 624 meetings × 5 high-stakes items = **3,120 decisions**
- 3,120 decisions × 30 SeeClickFix queries = **93,600 API calls**
- 3,120 decisions × LLM classification = **$15-30/year**

**Manual Analysis**: Impossible at this scale
**Automated Pipeline**: <$50/year operational cost (already in budget)

### Foundation Pitch Requirement

**Foundation funders need**:
- Multi-city evidence (not just San Rafael)
- Systemic patterns (not isolated incidents)
- Measurable gaps (quantified coordination opportunities)
- Replicability proof (automation = scalability)

**Without automation**: "We analyzed San Rafael manually" (weak)
**With automation**: "We analyzed 26 cities systematically, found X patterns affecting Y residents" (strong)

### City State Representation

**From docs/core**: Platform must maintain "real-time city state"

**What this means**:
- What decisions are happening now?
- What issues are residents raising?
- What patterns exist (budget cycles, development seasons)?
- What's the coordination opportunity?

**Automation enables**:
- Continuous monitoring (not one-time analysis)
- Predictive model (next high-stakes decisions)
- Opportunity detection (coordination gaps identified automatically)
- Scalability (add new city = run pipeline)

---

## Architecture Overview

### Six-Component Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                     RETROSPECTIVE ANALYSIS PIPELINE              │
└─────────────────────────────────────────────────────────────────┘

INPUT: Jurisdiction ID + Date Range
   │
   ├─► [1] Historical Meeting Extraction
   │       civic_digest.py (temporal expansion)
   │       Platform-specific (Legistar, CivicClerk, Granicus, HTML)
   │       Output: Meetings + Agenda Items
   │
   ├─► [2] High-Stakes Decision Filter
   │       LLM-powered classifier
   │       Criteria: Budget >$100K, Development >20 units, Environmental, Policy >1K residents
   │       Output: High-stakes decisions flagged
   │
   ├─► [3] SeeClickFix Complaint Matcher
   │       seeclickfix_client.py + operational_agenda_matcher.py
   │       Keyword + semantic matching
   │       Output: Related complaints per decision
   │
   ├─► [4] Testimony Analysis (Optional - Phase 2)
   │       Video transcript (YouTube API + Whisper) OR Meeting minutes
   │       Extract: Who testified, themes, quotes
   │       Output: Testimony count + themes
   │
   ├─► [5] Coordination Gap Measurement
   │       Calculate: gap = complaints - testimony
   │       Estimate: coordination potential (5-10 residents)
   │       Output: Priority score per decision
   │
   └─► [6] Pattern Recognition
         Analyze: Budget cycles, development seasons, environmental allocations
         Predict: Next occurrence of decision type
         Output: Decision calendar + predictive model

OUTPUT: Decision Database + City State Dashboard + Coordination Opportunities
```

---

## Component 1: Historical Meeting Extraction

### Current Status
✅ **Core extraction exists** in `civic_digest.py`
⚠️ **Needs temporal parameter** for 12-month lookback

### Implementation

```python
def extract_historical_meetings(
    jurisdiction_id: str,
    start_date: str,  # "2024-11-01"
    end_date: str,    # "2025-11-12"
    platforms: List[str] = ["city_council", "planning_commission", "budget_hearings"]
) -> List[Meeting]:
    """
    Extract all meetings for jurisdiction in date range.

    Args:
        jurisdiction_id: "san-rafael", "berkeley", etc.
        start_date: ISO format YYYY-MM-DD
        end_date: ISO format YYYY-MM-DD
        platforms: Meeting types to extract

    Returns:
        List of Meeting objects with agenda items
    """

    # Get platform config (Legistar, CivicClerk, Granicus, etc.)
    config = CITY_CONFIGS[jurisdiction_id]
    platform = config["agent_type"]

    # Platform-specific extraction
    if platform == "legistar":
        meetings = extract_legistar_historical(config, start_date, end_date)
    elif platform == "civicclerk":
        meetings = extract_civicclerk_historical(config, start_date, end_date)
    elif platform == "granicus":
        meetings = extract_granicus_historical(config, start_date, end_date)
    else:
        meetings = extract_html_historical(config, start_date, end_date)

    # Parse agendas (PDF or structured data)
    for meeting in meetings:
        if meeting.agenda_url:
            meeting.agenda_items = parse_agenda(meeting.agenda_url)

    return meetings
```

### Required Changes to civic_digest.py

**Add temporal filtering**:
```python
# Current: Only future meetings
# New: Support historical range

def main(args):
    if args.start_date and args.end_date:
        # Historical mode
        meetings = extract_historical_meetings(
            jurisdiction=args.jurisdiction,
            start_date=args.start_date,
            end_date=args.end_date
        )
    else:
        # Future mode (existing)
        meetings = extract_future_meetings(jurisdiction=args.jurisdiction)
```

### Cost Impact
**Existing**: Event extraction $5/month (all cities)
**Historical**: One-time per city (~$0.20 for 12 months)
**Total**: Negligible (within existing budget)

---

## Component 2: High-Stakes Decision Filter

### Current Status
❌ **Needs implementation** (Session 97)

### Purpose
Filter 100+ agenda items → 5-10 high-stakes decisions per month

### Criteria (from Session 96)
- Budget allocations >$100K
- Development projects >20 units
- Environmental decisions (wildfire, climate, water)
- Policy changes affecting >1,000 residents

### Implementation

```python
def classify_decision_stakes(agenda_item: Dict) -> Dict:
    """
    LLM-powered high-stakes decision classifier.

    Args:
        agenda_item: {
            "title": string,
            "description": string,
            "item_number": integer,
            "meeting_date": string
        }

    Returns:
        {
            "stakes_level": "high" | "medium" | "low",
            "decision_type": "budget" | "development" | "environmental" | "policy",
            "budget_amount": float | None,
            "project_size": integer | None (units),
            "affected_population": integer | None,
            "reasoning": string,
            "confidence": float (0-1)
        }
    """

    prompt = f"""
    You are analyzing a municipal agenda item to determine if it's a high-stakes decision requiring civic coordination.

    AGENDA ITEM:
    Title: {agenda_item['title']}
    Description: {agenda_item['description']}

    HIGH-STAKES CRITERIA:
    - Budget allocation >$100,000
    - Development project >20 units
    - Environmental decision (wildfire, climate, water, infrastructure)
    - Policy change affecting >1,000 residents

    TASK:
    1. Classify stakes level (high/medium/low)
    2. Identify decision type (budget/development/environmental/policy)
    3. Extract budget amount (if mentioned)
    4. Extract project size (if development)
    5. Estimate affected population
    6. Explain reasoning

    Return JSON with fields: stakes_level, decision_type, budget_amount, project_size, affected_population, reasoning, confidence
    """

    response = llm_provider.generate(
        prompt=prompt,
        model="gpt-4o-mini",  # Cheap, structured output
        response_format={"type": "json_object"}
    )

    return json.loads(response)
```

### LLM Model Selection
**Model**: `gpt-4o-mini` (60x cheaper than Claude)
**Cost**: ~$0.000006 per classification
**Annual**: 3,120 decisions × $0.000006 = **$0.02/year** (negligible)

### Validation
- Manual validation on San Rafael sample (100 decisions)
- Target accuracy: >80%
- False positives acceptable (over-include, manual review)
- False negatives unacceptable (miss coordination opportunities)

---

## Component 3: SeeClickFix Complaint Matcher

### Current Status
⚠️ **Partial** - `seeclickfix_client.py` exists, needs AI matcher integration

### Purpose
Match operational complaints → policy decisions

### Two-Stage Matching

#### Stage 1: Keyword Matching (Fast Filter)
```python
def keyword_match_complaints(
    decision: Dict,
    jurisdiction_id: str,
    days_before: int = 30
) -> List[str]:
    """
    Fast keyword-based filtering.
    Returns: List of potentially related complaint IDs
    """

    # Extract keywords from decision
    keywords = extract_keywords(decision['title'], decision['description'])

    # Query SeeClickFix
    client = SeeClickFixClient()
    end_date = decision['meeting_date']
    start_date = end_date - timedelta(days=days_before)

    complaints = client.get_issues(
        place_url=jurisdiction_id,
        per_page=100,
        # Filter by date range
    )

    # Keyword matching
    related = []
    for complaint in complaints:
        if any(kw in complaint['title'].lower() or
               kw in complaint['description'].lower()
               for kw in keywords):
            related.append(complaint['id'])

    return related
```

#### Stage 2: Semantic Matching (AI Validation)
```python
def semantic_match_complaints(
    decision: Dict,
    complaint_ids: List[str]
) -> List[Dict]:
    """
    LLM-powered semantic matching.
    Returns: Complaints with match confidence scores
    """

    matches = []

    for complaint_id in complaint_ids:
        complaint = get_complaint_details(complaint_id)

        prompt = f"""
        POLICY DECISION:
        Title: {decision['title']}
        Description: {decision['description']}
        Type: {decision['decision_type']}

        OPERATIONAL COMPLAINT:
        Title: {complaint['title']}
        Description: {complaint['description']}
        Category: {complaint['category']}

        QUESTION: Is this complaint related to the policy decision?

        Consider:
        - Does the operational issue connect to the policy area?
        - Would the resident care about this decision?
        - Is the timing relevant (complaint filed before decision)?

        Return JSON: {{"related": true/false, "confidence": 0-1, "reasoning": string}}
        """

        response = llm_provider.generate(
            prompt=prompt,
            model="gpt-4o-mini"
        )

        result = json.loads(response)
        if result['related'] and result['confidence'] > 0.6:
            matches.append({
                "complaint_id": complaint_id,
                "confidence": result['confidence'],
                "reasoning": result['reasoning']
            })

    return matches
```

### Integration with Existing Code

**Use `operational_agenda_matcher.py`** (Session 90):
- Already implements keyword + LLM semantic matching
- Modify to work on historical decisions (not just real-time)
- Add batch processing for efficiency

### Cost Impact
**Keyword matching**: Free (just queries)
**Semantic matching**: ~$0.000012 per complaint × 30 complaints/decision = $0.00036/decision
**Annual**: 3,120 decisions × $0.00036 = **$1.12/year**

---

## Component 4: Testimony Analysis (Phase 2 - Optional)

### Current Status
❌ **Not implemented** (defer to manual for pilot)

### Purpose
Extract testimony data from meeting records

### Two Options

#### Option A: Video Transcription (Automated)
```python
def analyze_testimony_from_video(meeting: Dict) -> Dict:
    """
    Extract testimony from YouTube video.
    Requires: YouTube API + Whisper transcription
    """

    # Get video URL
    video_url = meeting['video_url']

    # Download audio (youtube-dl or similar)
    audio_file = download_audio(video_url)

    # Transcribe (OpenAI Whisper API)
    transcript = whisper_api.transcribe(audio_file)

    # Parse transcript for public comment section
    # Heuristics: "Public comment", speaker changes, timestamps

    # Extract: Who spoke, what they said
    # LLM summarization of themes

    return {
        "testimony_count": count,
        "speakers": [list of names],
        "themes": [extracted topics],
        "quotes": [relevant excerpts]
    }
```

**Cost**: ~$0.006 per hour of audio (Whisper API)
**Feasibility**: High (YouTube videos available for most cities)
**Accuracy**: Moderate (requires speaker diarization)

#### Option B: Meeting Minutes Parsing (Simpler)
```python
def analyze_testimony_from_minutes(meeting: Dict) -> Dict:
    """
    Extract testimony from written minutes.
    Simpler but less detailed.
    """

    # Fetch meeting minutes (PDF or HTML)
    minutes = fetch_minutes(meeting['minutes_url'])

    # Parse for public comment section
    # Extract: Count of speakers, topics mentioned

    # LLM summarization
    prompt = f"""
    Extract public testimony information from these meeting minutes:
    {minutes}

    Return JSON: {{
        "testimony_count": integer,
        "themes": [list of topics],
        "notable_quotes": [list of excerpts]
    }}
    """

    return llm_provider.generate(prompt, model="gpt-4o-mini")
```

**Cost**: ~$0.0001 per meeting (minimal LLM use)
**Feasibility**: High (minutes widely available)
**Accuracy**: Lower (minutes often sparse)

### Recommendation
- **Pilot**: Manual counting (Session 97 for Oct 6)
- **Phase 2**: Automated minutes parsing (simpler, cheaper)
- **Phase 3**: Video transcription (higher accuracy, research intensive)

---

## Component 5: Coordination Gap Measurement

### Current Status
❌ **Needs implementation** (Session 97)

### Purpose
Calculate coordination opportunity per decision

### Implementation

```python
def measure_coordination_gap(decision: Dict) -> Dict:
    """
    Calculate coordination gap and priority score.

    Args:
        decision: {
            "id": uuid,
            "meeting_date": string,
            "stakes_level": "high" | "medium" | "low",
            "decision_type": string,
            "seeclickfix_complaints": List[complaint_id],
            "testimony_count": integer (if available)
        }

    Returns:
        {
            "gap_size": integer (complaints - testimony),
            "affected_residents": integer,
            "coordination_potential": integer (estimated participants),
            "priority_score": integer (1-100),
            "reasoning": string
        }
    """

    complaints_count = len(decision['seeclickfix_complaints'])
    testimony_count = decision.get('testimony_count', 0)  # May not be available

    # Gap calculation
    gap_size = complaints_count - testimony_count

    # Coordination potential (conservative estimate)
    # Assume 20-30% of complainants would coordinate
    coordination_potential = int(gap_size * 0.25)

    # Priority score (weighted)
    priority_score = (
        (decision['stakes_level'] == 'high') * 40 +  # High stakes = 40 points
        min(complaints_count, 50) +                    # Up to 50 complaints = 50 points
        (gap_size > 10) * 10                           # Large gap = 10 points bonus
    )

    reasoning = f"""
    {complaints_count} residents filed related complaints.
    {testimony_count} residents testified (estimated).
    Gap: {gap_size} residents likely didn't know about decision.
    Coordination potential: {coordination_potential} residents (25% of gap).
    Priority: {priority_score}/100
    """

    return {
        "gap_size": gap_size,
        "affected_residents": complaints_count,
        "coordination_potential": coordination_potential,
        "priority_score": priority_score,
        "reasoning": reasoning.strip()
    }
```

### Output Example
```json
{
  "decision_id": "4f616d49-428f-4c32-9019-524fa02e3d1f",
  "gap_size": 21,
  "affected_residents": 24,
  "coordination_potential": 6,
  "priority_score": 84,
  "reasoning": "24 residents filed complaints. 3 testified. Gap: 21 residents likely didn't know. Coordination potential: 6 residents (25% of gap). Priority: 84/100"
}
```

---

## Component 6: Pattern Recognition

### Current Status
❌ **Needs implementation** (Session 97)

### Purpose
Identify decision patterns for predictive model

### Pattern Types

#### Budget Cycles
```python
def identify_budget_pattern(decision_database: List[Dict]) -> Dict:
    """
    Identify when budget decisions typically happen.
    """

    budget_decisions = [d for d in decision_database
                       if d['decision_type'] == 'budget']

    # Group by month
    months = {}
    for d in budget_decisions:
        month = d['meeting_date'].split('-')[1]  # Extract month
        months[month] = months.get(month, 0) + 1

    # Find peak months
    peak_month = max(months, key=months.get)

    return {
        "pattern_type": "annual_budget",
        "peak_month": peak_month,
        "frequency": "annual",
        "confidence": months[peak_month] / len(budget_decisions),
        "next_occurrence": predict_next_budget(peak_month)
    }
```

#### Development Seasons
```python
def identify_development_pattern(decision_database: List[Dict]) -> Dict:
    """
    Identify when development approvals typically happen.
    """

    dev_decisions = [d for d in decision_database
                    if d['decision_type'] == 'development']

    # Group by season
    seasons = {"spring": 0, "summer": 0, "fall": 0, "winter": 0}

    for d in dev_decisions:
        month = int(d['meeting_date'].split('-')[1])
        if month in [3, 4, 5]:
            seasons["spring"] += 1
        elif month in [6, 7, 8]:
            seasons["summer"] += 1
        elif month in [9, 10, 11]:
            seasons["fall"] += 1
        else:
            seasons["winter"] += 1

    return {
        "pattern_type": "seasonal_development",
        "peak_season": max(seasons, key=seasons.get),
        "frequency": "seasonal clustering",
        "confidence": seasons[max(seasons, key=seasons.get)] / sum(seasons.values())
    }
```

#### Environmental Allocations
```python
def identify_environmental_pattern(decision_database: List[Dict]) -> Dict:
    """
    Identify when environmental decisions typically happen.
    Examples: Wildfire funding (pre-fire season), water allocations (drought season)
    """

    env_decisions = [d for d in decision_database
                    if d['decision_type'] == 'environmental']

    # Look for annual recurrence
    # Wildfire: Typically Sept-Oct (before fire season)
    # Water: Typically Feb-April (drought planning)

    # Group by topic (wildfire, water, climate, etc.)
    topics = {}
    for d in env_decisions:
        topic = extract_environmental_topic(d)  # LLM classification
        if topic not in topics:
            topics[topic] = []
        topics[topic].append(d['meeting_date'])

    # Find patterns per topic
    patterns = {}
    for topic, dates in topics.items():
        # Calculate typical month
        months = [int(d.split('-')[1]) for d in dates]
        typical_month = mode(months)

        patterns[topic] = {
            "typical_month": typical_month,
            "occurrences": len(dates),
            "confidence": months.count(typical_month) / len(months)
        }

    return {
        "pattern_type": "environmental_cycles",
        "topic_patterns": patterns,
        "frequency": "annual or event-driven"
    }
```

### Predictive Model Output

```json
{
  "jurisdiction": "san-rafael",
  "analysis_period": "2024-11-01 to 2025-11-12",
  "patterns": {
    "budget_cycle": {
      "peak_month": "March",
      "frequency": "annual",
      "confidence": 0.95,
      "next_occurrence": "2026-03-15"
    },
    "development_season": {
      "peak_season": "summer",
      "frequency": "seasonal",
      "confidence": 0.72,
      "next_occurrence": "2026-06-01 to 2026-08-31"
    },
    "environmental_allocations": {
      "wildfire": {
        "typical_month": "September",
        "confidence": 0.85,
        "next_occurrence": "2026-09-15"
      }
    }
  },
  "upcoming_opportunities": [
    {
      "decision_type": "budget",
      "predicted_date": "2026-03-15",
      "confidence": 0.95,
      "coordination_potential": "high"
    },
    {
      "decision_type": "environmental",
      "topic": "wildfire",
      "predicted_date": "2026-09-15",
      "confidence": 0.85,
      "coordination_potential": "medium"
    }
  ]
}
```

---

## End-to-End Pipeline

### Command-Line Interface

```bash
# Run retrospective analysis for one city
python src/retrospective_analysis.py \
  --jurisdiction san-rafael \
  --start-date 2024-11-01 \
  --end-date 2025-11-12 \
  --output docs/pilot/SAN_RAFAEL_DECISION_DATABASE.csv

# Run for all 26 cities
python src/retrospective_analysis.py \
  --all-cities \
  --months-back 12 \
  --output data/decision_databases/

# Update continuously (cron job)
python src/retrospective_analysis.py \
  --continuous \
  --check-interval 7d  # Run weekly
```

### Output Files

**Per-City Decision Database** (CSV):
```csv
decision_id,meeting_date,meeting_type,decision_title,decision_type,stakes_level,budget_amount,project_size,affected_population,seeclickfix_complaints,testimony_count,gap_size,coordination_potential,priority_score,legislative_context,outcome
4f616d49-...,2025-10-06,city_council,Measure C Wildfire Prevention Fund,environmental,high,,,,24,3,21,6,84,"ca-sb35,cdbg",approved
...
```

**City State Dashboard** (JSON):
```json
{
  "jurisdiction": "san-rafael",
  "last_updated": "2025-11-12T22:00:00Z",
  "analysis_period": {
    "start": "2024-11-01",
    "end": "2025-11-12"
  },
  "summary": {
    "total_meetings": 26,
    "total_decisions": 127,
    "high_stakes_decisions": 18,
    "total_complaints_matched": 342,
    "average_gap_per_decision": 15.2,
    "coordination_opportunities": 18
  },
  "patterns": {
    "budget_cycle": {...},
    "development_season": {...},
    "environmental_allocations": {...}
  },
  "top_opportunities": [
    {
      "decision_id": "...",
      "priority_score": 84,
      "meeting_date": "2025-10-06",
      "coordination_potential": 6
    },
    ...
  ]
}
```

**Coordination Gap Analysis** (Markdown Report):
- Decision patterns identified
- Top 5 retrospective case studies
- Coordination gap statistics
- Predictive model for upcoming opportunities

---

## Implementation Roadmap

### Session 97: Design + Prototype (6-9 hours)
**Phase 1**: Oct 6 deep dive (manual)
**Phase 2**: 12-month extraction (automated)
**Phase 3**: Architecture documentation (this document)

**Deliverables**:
- Component specifications
- LLM prompts defined
- Cost projections
- API integrations identified

### Session 98: Core Automation (6-8 hours)
**Implement**:
- Component 1: Historical extraction (civic_digest.py modification)
- Component 2: High-stakes classifier (LLM-powered)
- Component 3: SeeClickFix matcher (integrate operational_agenda_matcher.py)
- Component 5: Gap measurement (calculation logic)
- Component 6: Pattern recognition (basic version)

**Defer**: Component 4 (testimony analysis - manual for pilot)

### Session 99: Multi-City Validation (4-6 hours)
**Test on 3 cities**:
- San Rafael (validate against manual analysis)
- Berkeley (test on different CMS platform)
- Santa Rosa (test on Legistar)

**Measure**:
- Accuracy (high-stakes classifier >80%)
- Precision (SeeClickFix matcher >75%)
- Performance (time to analyze 12 months)
- Cost (LLM spend vs. budget)

### Session 100: Production Deployment (3-4 hours)
**Scale to 26 cities**:
- Run full retrospective (12 months each)
- Generate city state dashboards
- Compile foundation pitch evidence
- Document learnings

---

## Cost Projections

### Per-City Analysis (12 months)

**Meeting Extraction**: $0.20 (one-time, PDF parsing)
**High-Stakes Classification**: 120 agenda items × $0.000006 = $0.00072
**SeeClickFix Matching**: 15 decisions × $0.00036 = $0.0054
**Gap Measurement**: Free (calculation only)
**Pattern Recognition**: 1 LLM call × $0.0001 = $0.0001

**Total per city**: **~$0.21** (one-time)

### 26-City Deployment

**One-time**: 26 × $0.21 = **$5.46**
**Ongoing** (continuous monitoring): Negligible (within existing $7/month budget)

### 340-City Scale (Full SeeClickFix Network)

**One-time**: 340 × $0.21 = **$71.40**
**Annual** (monthly updates): 340 × 12 × $0.05 = **$204/year**

**Within foundation budget**: $50-100K/year easily covers this

---

## Success Metrics

### Automation Quality
- **High-stakes classifier accuracy**: >80% (validated against manual review)
- **SeeClickFix matcher precision**: >75% (related complaints correctly identified)
- **Pattern detection confidence**: >70% (budget cycles, seasonal trends)

### Performance
- **Time to analyze 12 months**: <15 minutes per city (automated)
- **Cost per city**: <$0.25 (within budget)
- **Scalability**: Add new city = run pipeline (no manual setup)

### Strategic Value
- **Foundation pitch evidence**: "12 months, 26 cities, 400+ decisions, 5,000+ residents"
- **Predictive model**: Budget decisions March, development summer, wildfire September
- **Coordination opportunities**: Top 100 highest-priority decisions identified

---

## Related Documentation

**Technical Foundation**:
- `docs/architecture/SEECLICKFIX_INTEGRATION_ARCHITECTURE.md` - SeeClickFix bridge
- `docs/core/LLM_PROVIDER_ARCHITECTURE.md` - Model selection + cost optimization
- `src/seeclickfix_client.py` - Operational complaint fetching
- `src/operational_agenda_matcher.py` - AI matching (keyword + semantic)

**Strategic Context**:
- `docs/strategy/FOCAL_POINT_DECISION_AWARENESS.md` - Why retrospective validation matters
- `docs/pilot/SESSION_96_DECISION_BRIEF.md` - Oct 6 case study
- `docs/core/next_session_prompt.md` - Session 97 implementation plan

---

**Status**: Architecture design complete. Session 97-98 implement automation. Session 99 validates multi-city.
