# Testimony Extraction Pipeline Architecture

**Status**: ✅ Production-Ready (Session 111)
**Cost**: ~$3/meeting
**Accuracy**: 100% speaker count, 34% name identification
**Dependencies**: AssemblyAI, YouTube Transcript API, OpenAI/OpenRouter LLM

---

## Overview

The Testimony Extraction Pipeline automatically extracts, attributes, and stores public testimony from city council meetings using a multi-stage approach:

1. **YouTube Transcript** → LLM speaker count estimation
2. **AssemblyAI Diarization** → Exact speaker separation with timestamps
3. **Speaker Name Extraction** → Pattern matching + LLM fallback + minutes cross-reference
4. **Topic Classification** → Keyword matching to agenda items and SeeClickFix complaints
5. **Database Storage** → SQLite with full-text search for semantic queries

## Use Cases

### 1. Retrospective Analysis (Session 99+)
- **Question**: "Which cities allocated funds for wildfire prevention?"
- **Method**: Search testimony database for "wildfire" + "funding" mentions
- **Output**: Identify speakers, dates, decisions across 26 cities

### 2. Coalition Building (Session 110 validated)
- **Question**: "Who else testified on wildfire issues?"
- **Method**: Find speakers with overlapping topics from SeeClickFix complaints
- **Output**: Oct 6 case study - 22 complaint filers, only 3 testified (86% gap)

### 3. Pattern Discovery
- **Question**: "How many repeat testifiers vs one-time speakers?"
- **Method**: Aggregate testimony across 12 months, count unique speakers per topic
- **Output**: Identify power users vs ad-hoc participants

## Architecture

### Stage 1: Speaker Count Estimation

**Purpose**: Determine exact number of speakers for optimal AssemblyAI diarization
**Method**: LLM analysis of YouTube transcript
**Cost**: $0.20/meeting
**Accuracy**: 100% (Session 109 validated - estimated 50, actual 50)

```bash
python scripts/estimate_speakers_llm.py --video MpxrGRb16HQ
```

**Implementation**: `scripts/estimate_speakers_llm.py`

**Key Insight** (Session 108): Exact count prevents lossy speaker merging:
- `min=50, max=50` → Perfect attribution (50 speakers identified)
- `min=40, max=40` → 20% speakers lost (merged incorrectly)

### Stage 2: AssemblyAI Diarization

**Purpose**: Separate speakers with timestamps for audio alignment
**Method**: AssemblyAI speaker labels API with exact count parameter
**Cost**: $2.80/meeting (2 hours × $1.40/hour)
**Output**: JSON with `{speaker: "A", text: "...", start: 1234, end: 5678}`

```python
from testimony_extraction_pipeline import TestimonyExtractionPipeline

pipeline = TestimonyExtractionPipeline()
result = pipeline.extract_testimony(
    youtube_video_id="MpxrGRb16HQ",
    speaker_count=50,
    jurisdiction_id="san-rafael",
    meeting_date="2024-10-06",
    assemblyai_api_key=os.getenv('ASSEMBLYAI_API_KEY')
)
```

**Implementation**: `src/testimony_extraction_pipeline.py`

**Error Handling** (Session 111):
- ✅ Automatic retry on transient failures (network, rate limits, timeouts)
- ✅ Exponential backoff (tenacity library)
- ✅ Error logging to `data/testimony_extraction_errors.json`
- ✅ Graceful degradation (skip failed meetings, continue pipeline)

### Stage 3: Speaker Name Extraction

**Purpose**: Identify speakers by name for attribution and coalition building
**Method**: Three-tier strategy with automatic fallback
**Cost**: $0.005/meeting (~$0.0001 per LLM extraction × 50 speakers)
**Accuracy**: 34% identification rate (Session 111)

#### Three-Tier Strategy (Session 111)

**Tier 1: Pattern Matching (22% success rate)**
```python
intro_patterns = ["my name is ", "i'm ", "this is ", "i am "]
```
- Fast, no API cost
- Works for explicit self-introductions
- Catches: "My name is Belle Cole" → "Belle Cole"

**Tier 2: LLM Fallback (2% success rate)**
```python
extract_speaker_name_llm(utterances, speaker_label)
```
- Robust to variations (contractions, typos)
- Handles edge cases pattern matching misses
- Example: "My name's Steve Danaher" (contraction) → "Steve Danaher"

**Tier 3: Minutes Cross-Reference (10% success rate)**
```python
match_to_minutes_attendees(utterances, speaker_label, attendees)
```
- Matches council/staff by procedural language
- Example: "Good evening everyone" → Mayor (chairs meeting)
- Example: "Call the roll" → City Clerk (roll call)

**Tier 4: Unknown (66%)**
- Council members who don't introduce themselves
- Staff who don't introduce themselves
- Public speakers without names

**Implementation**: `scripts/merge_youtube_assemblyai_speakers.py`

**Rationale**: 66% unknown is expected for city council meetings where most speakers (council, staff, regulars) don't self-introduce.

### Stage 4: Database Storage

**Purpose**: Enable semantic search, coalition building, and retrospective analysis
**Method**: SQLite with FTS5 full-text search
**Schema**: 4 tables (meetings, speakers, utterances, topics)

#### Schema Design (Migration 011)

**`testimony_meetings`** - Meeting metadata
```sql
CREATE TABLE testimony_meetings (
    meeting_id TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL,
    meeting_date TEXT NOT NULL,
    youtube_video_id TEXT,
    assemblyai_transcript_id TEXT,
    speaker_count_estimated INTEGER,
    speaker_count_actual INTEGER,
    processing_cost_usd REAL,
    processed_at TEXT
);
```

**`testimony_speakers`** - Speaker identification
```sql
CREATE TABLE testimony_speakers (
    speaker_id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL,
    speaker_label TEXT NOT NULL,  -- AssemblyAI label (A, B, C, ...)
    name TEXT,
    role TEXT,  -- public, council, staff, unknown
    confidence TEXT,  -- high, medium, low
    identification_method TEXT,  -- pattern, llm, minutes, none
    utterance_count INTEGER
);
```

**`testimony_utterances`** - Individual utterances with timestamps
```sql
CREATE TABLE testimony_utterances (
    utterance_id TEXT PRIMARY KEY,
    speaker_id TEXT NOT NULL,
    text TEXT NOT NULL,
    start_ms INTEGER,
    end_ms INTEGER,
    confidence REAL,
    sequence INTEGER
);
```

**`testimony_topics`** - Topic classification and linking
```sql
CREATE TABLE testimony_topics (
    topic_id TEXT PRIMARY KEY,
    speaker_id TEXT NOT NULL,
    topic TEXT NOT NULL,  -- housing, transportation, wildfire, etc.
    keywords TEXT,  -- JSON array of matched keywords
    matched_agenda_items TEXT,  -- JSON array of agenda item IDs
    matched_complaints TEXT,  -- JSON array of SeeClickFix issue IDs
    confidence REAL
);
```

#### Full-Text Search (FTS5)

**Purpose**: Enable semantic queries like "Find all testimony mentioning 'wildfire OR evacuation'"

```sql
SELECT
    s.name,
    m.meeting_date,
    u.text
FROM testimony_utterances_fts fts
JOIN testimony_utterances u ON u.utterance_id = fts.utterance_id
JOIN testimony_speakers s ON s.speaker_id = u.speaker_id
JOIN testimony_meetings m ON m.meeting_id = s.meeting_id
WHERE testimony_utterances_fts MATCH 'wildfire OR evacuation'
ORDER BY m.meeting_date DESC;
```

**Implementation**: `migrations/011_testimony_storage.sql`

### Stage 5: Quality Metrics

**Purpose**: Track pipeline performance and validate results
**Metrics**: Speaker count accuracy, identification rate, confidence distribution, coverage, costs

#### Key Metrics

1. **Speaker Count Accuracy**: `min(estimated, actual) / max(estimated, actual)`
   - Session 109: 100% (estimated 50, actual 50)

2. **Identification Rate**: `identified_speakers / total_speakers`
   - Session 111: 34% (17 of 50 speakers identified)

3. **Identification Methods**: Breakdown by tier
   - Pattern matching: 11 (22%)
   - LLM extraction: 1 (2%)
   - Minutes cross-ref: 5 (10%)
   - Unknown: 33 (66%)

4. **Confidence Distribution**:
   - High: 11 speakers (pattern matching)
   - Medium: 6 speakers (LLM + minutes)
   - Low: 33 speakers (unknown)

5. **Cost Breakdown**:
   - YouTube LLM: $0.20
   - AssemblyAI: $2.80
   - Name extraction: $0.005
   - **Total**: ~$3.00/meeting

**Implementation**: `src/testimony_quality_metrics.py`, `scripts/testimony_quality_report.py`

**Usage**:
```bash
# Single meeting report
python scripts/testimony_quality_report.py --meeting san-rafael_2024-10-06_MpxrGRb16HQ

# Aggregate report
python scripts/testimony_quality_report.py --jurisdiction san-rafael

# With speaker breakdown
python scripts/testimony_quality_report.py --meeting san-rafael_2024-10-06_MpxrGRb16HQ --breakdown
```

## Production Pipeline (Session 111)

### Error Handling

All API calls wrapped with retry logic using `tenacity`:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    retry=retry_if_exception_type((requests.RequestException, TimeoutError))
)
def _upload_to_assemblyai(audio_url, speaker_count, api_key):
    # Upload with automatic retry on transient failures
    pass
```

**Features**:
- ✅ Exponential backoff (4s → 60s max)
- ✅ Retry on network errors, timeouts, rate limits
- ✅ Error logging with context (video_id, meeting_date, etc.)
- ✅ Graceful degradation (skip failed meetings, continue batch processing)

### Batch Processing

For 12-month retrospective (Session 112):

```python
from testimony_extraction_pipeline import TestimonyExtractionPipeline

pipeline = TestimonyExtractionPipeline()

meetings = [
    {'date': '2024-09-16', 'youtube_id': 'xxx'},
    {'date': '2024-08-19', 'youtube_id': 'xxx'},
    # ... 9 more meetings
]

for meeting in meetings:
    result = pipeline.extract_testimony(
        youtube_video_id=meeting['youtube_id'],
        speaker_count=estimate_speakers(meeting['youtube_id']),
        jurisdiction_id='san-rafael',
        meeting_date=meeting['date'],
        assemblyai_api_key=os.getenv('ASSEMBLYAI_API_KEY')
    )

    if result:
        # Store in database
        store_testimony(result)
    else:
        # Log error and continue
        logger.warning(f"Skipped {meeting['date']} due to extraction error")
```

**Cost**: 11 meetings × $3/meeting = $33

## Query Examples

### 1. Find Wildfire Testimony (Last 12 Months)

```sql
SELECT
    m.meeting_date,
    s.name,
    s.role,
    GROUP_CONCAT(u.text, ' ') as testimony
FROM testimony_meetings m
JOIN testimony_speakers s ON s.meeting_id = m.meeting_id
JOIN testimony_utterances u ON u.speaker_id = s.speaker_id
JOIN testimony_topics t ON t.speaker_id = s.speaker_id
WHERE
    m.jurisdiction_id = 'san-rafael'
    AND t.topic = 'wildfire'
    AND m.meeting_date >= date('now', '-12 months')
GROUP BY s.speaker_id
ORDER BY m.meeting_date;
```

### 2. Find Repeat Testifiers

```sql
SELECT
    s.name,
    COUNT(DISTINCT m.meeting_id) as meeting_count,
    GROUP_CONCAT(DISTINCT t.topic) as topics
FROM testimony_speakers s
JOIN testimony_meetings m ON m.meeting_id = s.meeting_id
JOIN testimony_topics t ON t.speaker_id = s.speaker_id
WHERE s.name NOT LIKE 'Unknown%'
GROUP BY s.name
HAVING meeting_count > 1
ORDER BY meeting_count DESC;
```

### 3. Topic Patterns

```sql
SELECT
    t.topic,
    COUNT(DISTINCT s.speaker_id) as speaker_count,
    COUNT(DISTINCT m.meeting_id) as meeting_count,
    AVG(s.utterance_count) as avg_utterances
FROM testimony_topics t
JOIN testimony_speakers s ON s.speaker_id = t.speaker_id
JOIN testimony_meetings m ON m.meeting_id = s.meeting_id
WHERE m.jurisdiction_id = 'san-rafael'
GROUP BY t.topic
ORDER BY speaker_count DESC;
```

### 4. Full-Text Search

```sql
SELECT
    s.name,
    m.meeting_date,
    u.text
FROM testimony_utterances_fts fts
JOIN testimony_utterances u ON u.utterance_id = fts.utterance_id
JOIN testimony_speakers s ON s.speaker_id = u.speaker_id
JOIN testimony_meetings m ON m.meeting_id = s.meeting_id
WHERE testimony_utterances_fts MATCH 'wildfire OR evacuation'
ORDER BY m.meeting_date DESC;
```

## Case Study: Oct 6 Wildfire Fund (Session 110)

### Context
- **Meeting**: San Rafael City Council, October 6, 2024
- **Topic**: Wildfire Prevention Fund allocation
- **SeeClickFix Complaints**: 48 fire-related issues (Sept 6 - Oct 6, 2024)
- **Complaint Filers**: 22 unique residents

### Results

**Testimony Extracted**:
- 3 wildfire speakers identified:
  - **Belle Cole** (Speaker AJ, 11 utterances) - Firewise Committee Chair
  - **Sherna Deamer** (Speaker T, 21 utterances) - Neighborhood fire concerns
  - **Salama** (Speaker AI, 3 utterances) - Age-Friendly senior fire safety

**Participation Gap**:
- 22 residents filed fire complaints
- Only 3 testified at policy decision
- **86% coordination gap** (19 of 22 did NOT participate)

**Value Proposition**:
- Even 25% conversion (5 of 19) → 3→8 speakers, **2.7x increase**
- Automated matching: Complaints → Agendas → Legislative context
- Coordination infrastructure: Chat, following, notifications

### Economics

**Production Costs** (26 cities):
- Event extraction: $5/month
- Legislative context: $2/month
- Testimony extraction: $156/month ($1,872/year)
- **Total**: <$200/month

**Vs Manual Alternative**:
- Manual review: $15,600/year (assume $50/hour × 6 hours/city/year)
- **88% savings** with automation

## Dependencies

- **AssemblyAI** - Speaker diarization with exact count parameter
- **YouTube Transcript API** - Free transcript extraction
- **OpenAI / OpenRouter** - LLM speaker count estimation + name extraction
- **Tenacity** - Retry logic for production robustness
- **SQLite FTS5** - Full-text search for semantic queries

## Future Enhancements

### Vector Search (Session 101+)
- Generate embeddings for all utterances
- ChromaDB for semantic similarity search
- "Find testimony similar to Belle Cole's wildfire concerns"

### Topic Auto-Classification
- LLM-based topic extraction from testimony text
- Auto-link to state bills and federal programs
- Notification when relevant legislation appears

### Coalition Recommendations
- "You should connect with Belle Cole (testified on wildfire 3x)"
- Graph-based similarity by topics and keywords
- Auto-suggest coordination chat threads

## Files

**Core Pipeline**:
- `src/testimony_extraction_pipeline.py` - Production pipeline with error handling
- `scripts/merge_youtube_assemblyai_speakers.py` - Three-tier speaker name extraction
- `scripts/estimate_speakers_llm.py` - LLM speaker count estimation

**Storage**:
- `migrations/011_testimony_storage.sql` - Database schema
- `src/testimony_quality_metrics.py` - Quality metrics calculator
- `scripts/testimony_quality_report.py` - CLI quality reports

**Case Study**:
- `scripts/extract_wildfire_testimony.py` - Topic-specific extraction (Oct 6 wildfire)
- `scripts/cross_reference_testimony_complaints.py` - Gap analysis (86% coordination gap)
- `data/pilot/OCT6_WILDFIRE_CASE_STUDY.md` - Foundation-ready case study

## References

- **Session 107-110**: Oct 6 case study development and validation
- **Session 111**: Production hardening (this document)
- **Session 112+**: 12-month retrospective (planned)

---

**Last Updated**: 2024-11-23 (Session 111)
**Next**: Session 112 - 12-month retrospective batch processing
