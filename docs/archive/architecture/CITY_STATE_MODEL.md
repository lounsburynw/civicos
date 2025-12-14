# City State Model: Comprehensive Municipal Reality Representation

**Version**: 1.0
**Date**: 2025-11-14
**Status**: Design Phase
**Goal**: Build foundation for Civic Data Protocol

---

## Executive Summary

Define a **complete, queryable snapshot** of municipal civic activity that serves as:
1. **Single source of truth** for all city data
2. **Foundation for Civic Data Protocol** (external API)
3. **Temporal consistency** (query historical states)
4. **Decoupled backend** (frontend becomes protocol client)

### Key Principles

- ✅ **Complete**: All civic data in one queryable model
- ✅ **Temporal**: Support "state at time T" queries
- ✅ **Normalized**: Single canonical representation
- ✅ **Versioned**: Track changes over time
- ✅ **Protocol-ready**: Maps directly to civic:// URIs

---

## City State Schema

### Core Entity: `CityState`

```python
CityState {
    # Identity
    jurisdiction_id: str           # e.g., "city-berkeley"
    jurisdiction_name: str          # e.g., "Berkeley, CA"
    as_of: datetime                 # State timestamp

    # Civic Calendar
    meetings: List[Meeting]         # All meetings (past + future)
    agenda_items: List[AgendaItem]  # With actionability scores

    # Operational Reality (SeeClickFix)
    complaints: List[Issue]         # Active community issues

    # Legislative Context
    relevant_bills: List[StateBill] # Matched state legislation
    federal_programs: List[Program] # CDBG, HUD programs, etc.

    # Financial
    budget: Budget                  # Allocations by category
    cdbg_allocation: Money          # Federal funding

    # Community Engagement
    active_residents: int           # Users with recent activity
    pending_comments: int           # Draft comments
    coordination_threads: int       # Active discussions

    # Data Quality
    last_updated: Dict[str, datetime]  # Per-source freshness
    completeness_score: float          # 0-1 data quality metric

    # Metadata
    data_sources: List[str]         # Platforms used (Legistar, etc.)
    extraction_version: str         # Versioning for schema changes
}
```

### Sub-Entities

#### Meeting
```python
Meeting {
    id: str                        # Unique identifier
    title: str                     # "City Council Regular Meeting"
    meeting_datetime: datetime     # When it occurs
    meeting_type: str              # council, planning, committee
    status: str                    # scheduled, completed, cancelled

    # Participation
    location: str
    virtual_url: str
    agenda_url: str
    minutes_url: str
    video_url: str
    comment_deadline: datetime

    # Content
    agenda_items: List[AgendaItem]

    # Metadata
    source_platform: str           # legistar, civicclerk, granicus
    source_url: str
    last_verified: datetime
    data_quality_score: float
}
```

#### AgendaItem
```python
AgendaItem {
    id: str                        # Unique identifier
    meeting_id: str                # Parent meeting
    item_number: str               # "5.2", "VII.A"
    title: str
    description: str

    # Classification
    project_type: str              # housing, transportation, etc.
    actionability: str             # public_comment, rsvp, advocate
    impact_level: str              # high, medium, low

    # Legislative Enrichment
    relevant_bills: List[str]      # State bill IDs
    federal_programs: List[str]    # Program IDs
    financial_impact: Money        # If budget item

    # Community Response
    matched_complaints: List[str]  # SeeClickFix issue IDs
    comment_count: int             # Drafts + submitted
    following_count: int           # Users tracking this

    # AI Analysis
    summary: str                   # Plain language
    why_it_matters: str            # Impact explanation
    participation_guide: str       # How to engage

    # Metadata
    extracted_at: datetime
    enriched_at: datetime
}
```

#### Issue (Operational Complaint)
```python
Issue {
    id: str                        # Unique identifier
    source: str                    # seeclickfix, native
    source_id: str                 # External ID if applicable

    # Content
    title: str
    description: str
    issue_type: str                # pothole, graffiti, etc.

    # Location
    address: str
    latitude: float
    longitude: float
    jurisdiction_id: str

    # Status
    status: str                    # open, closed
    closed_reason: str
    created_at: datetime
    updated_at: datetime

    # Matching
    matched_meetings: List[str]    # Meeting IDs
    matched_agenda_items: List[str]
    match_score: float             # AI confidence
    match_reason: str

    # Community
    follower_count: int
    coordination_thread_id: str    # If discussion exists
}
```

#### StateBill
```python
StateBill {
    id: str                        # e.g., "california-ab-1482"
    bill_number: str               # "AB 1482"
    title: str
    summary: str
    status: str                    # introduced, passed, enacted

    # Legislative Tracking
    author: str
    introduced_date: date
    last_action: str
    last_action_date: date

    # Relevance
    topics: List[str]              # housing, transportation, etc.
    local_impact: str              # Why it matters locally

    # Links
    full_text_url: str
    tracking_url: str
}
```

#### Budget
```python
Budget {
    fiscal_year: str               # "FY2025"
    total_budget: Money

    # By Category (aligned with project_type taxonomy)
    housing: Money
    transportation: Money
    environment: Money
    public_safety: Money
    education: Money

    # Federal Funding
    cdbg_allocation: Money
    other_federal: Dict[str, Money]

    # Metadata
    source_url: str
    last_updated: datetime
}
```

---

## Storage Architecture: Hybrid Approach

### Primary Store: PostgreSQL (or SQLite)

**Why SQL:**
- ✅ Structured queries (JOIN meetings + agenda_items + bills)
- ✅ Temporal queries (state at time T)
- ✅ Transaction support (atomic updates)
- ✅ Strong typing and constraints

**Schema Design:**

```sql
-- Core city state table
CREATE TABLE city_states (
    jurisdiction_id TEXT PRIMARY KEY,
    jurisdiction_name TEXT NOT NULL,
    as_of TIMESTAMP NOT NULL,
    active_residents INTEGER,
    pending_comments INTEGER,
    coordination_threads INTEGER,
    completeness_score REAL,
    data_sources JSONB,  -- Array of source platforms
    extraction_version TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Meetings (temporal versioning)
CREATE TABLE meetings (
    id TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL REFERENCES city_states(jurisdiction_id),
    title TEXT NOT NULL,
    meeting_datetime TIMESTAMP NOT NULL,
    meeting_type TEXT,
    status TEXT,
    location TEXT,
    virtual_url TEXT,
    agenda_url TEXT,
    minutes_url TEXT,
    video_url TEXT,
    comment_deadline TIMESTAMP,
    source_platform TEXT NOT NULL,
    source_url TEXT,
    last_verified TIMESTAMP,
    data_quality_score REAL,

    -- Temporal versioning
    valid_from TIMESTAMP NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMP,  -- NULL = current version

    -- Full text search
    search_vector tsvector,

    CONSTRAINT valid_time_range CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX idx_meetings_temporal ON meetings(jurisdiction_id, valid_from, valid_to);
CREATE INDEX idx_meetings_datetime ON meetings(meeting_datetime);
CREATE INDEX idx_meetings_search ON meetings USING GIN(search_vector);

-- Agenda Items (with legislative enrichment)
CREATE TABLE agenda_items (
    id TEXT PRIMARY KEY,
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    item_number TEXT,
    title TEXT NOT NULL,
    description TEXT,
    project_type TEXT,
    actionability TEXT,
    impact_level TEXT,
    financial_impact_cents BIGINT,  -- Store as cents for precision

    -- AI Analysis
    summary TEXT,
    why_it_matters TEXT,
    participation_guide TEXT,

    -- Community metrics
    comment_count INTEGER DEFAULT 0,
    following_count INTEGER DEFAULT 0,

    -- Legislative context (stored as JSON arrays of IDs)
    relevant_bills JSONB,  -- ["california-ab-1482", ...]
    federal_programs JSONB,  -- ["cdbg", ...]
    matched_complaints JSONB,  -- ["issue-123", ...]

    -- Timestamps
    extracted_at TIMESTAMP,
    enriched_at TIMESTAMP,

    -- Temporal versioning
    valid_from TIMESTAMP NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMP,

    -- Full text search
    search_vector tsvector
);

CREATE INDEX idx_agenda_items_meeting ON agenda_items(meeting_id);
CREATE INDEX idx_agenda_items_type ON agenda_items(project_type);
CREATE INDEX idx_agenda_items_temporal ON agenda_items(valid_from, valid_to);
CREATE INDEX idx_agenda_items_search ON agenda_items USING GIN(search_vector);

-- Issues (operational complaints)
CREATE TABLE issues (
    id TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL REFERENCES city_states(jurisdiction_id),
    source TEXT NOT NULL,  -- seeclickfix, native
    source_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    issue_type TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    status TEXT NOT NULL DEFAULT 'open',
    closed_reason TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Matching to agenda items
    matched_meetings JSONB,  -- Meeting IDs
    matched_agenda_items JSONB,  -- Agenda item IDs
    match_score REAL,
    match_reason TEXT,

    -- Community
    follower_count INTEGER DEFAULT 0,
    coordination_thread_id TEXT,

    -- Temporal versioning
    valid_from TIMESTAMP NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMP,

    -- Geospatial index
    location geography(POINT, 4326)
);

CREATE INDEX idx_issues_jurisdiction ON issues(jurisdiction_id);
CREATE INDEX idx_issues_status ON issues(status);
CREATE INDEX idx_issues_location ON issues USING GIST(location);
CREATE INDEX idx_issues_temporal ON issues(valid_from, valid_to);

-- State Bills (legislative context)
CREATE TABLE state_bills (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL,  -- california, etc.
    bill_number TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    status TEXT,
    author TEXT,
    introduced_date DATE,
    last_action TEXT,
    last_action_date DATE,
    topics JSONB,  -- ["housing", "transportation"]
    local_impact TEXT,
    full_text_url TEXT,
    tracking_url TEXT,

    -- Temporal versioning (bill status changes)
    valid_from TIMESTAMP NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMP,

    -- Full text search
    search_vector tsvector
);

CREATE INDEX idx_bills_state ON state_bills(state);
CREATE INDEX idx_bills_topics ON state_bills USING GIN(topics);
CREATE INDEX idx_bills_search ON state_bills USING GIN(search_vector);

-- Federal Programs
CREATE TABLE federal_programs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    agency TEXT,
    description TEXT,
    topics JSONB,
    eligibility TEXT,
    application_url TEXT,

    -- Full text search
    search_vector tsvector
);

-- Jurisdiction Budget
CREATE TABLE budgets (
    jurisdiction_id TEXT NOT NULL REFERENCES city_states(jurisdiction_id),
    fiscal_year TEXT NOT NULL,
    total_budget_cents BIGINT,
    housing_cents BIGINT,
    transportation_cents BIGINT,
    environment_cents BIGINT,
    public_safety_cents BIGINT,
    education_cents BIGINT,
    cdbg_allocation_cents BIGINT,
    other_federal JSONB,  -- {"program_id": amount_cents}
    source_url TEXT,
    last_updated TIMESTAMP,

    -- Temporal versioning (budget revisions)
    valid_from TIMESTAMP NOT NULL DEFAULT NOW(),
    valid_to TIMESTAMP,

    PRIMARY KEY (jurisdiction_id, fiscal_year, valid_from)
);

-- Junction tables for many-to-many relationships

CREATE TABLE agenda_item_bills (
    agenda_item_id TEXT NOT NULL REFERENCES agenda_items(id) ON DELETE CASCADE,
    bill_id TEXT NOT NULL REFERENCES state_bills(id) ON DELETE CASCADE,
    relevance_score REAL,  -- AI confidence
    matched_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (agenda_item_id, bill_id)
);

CREATE TABLE agenda_item_programs (
    agenda_item_id TEXT NOT NULL REFERENCES agenda_items(id) ON DELETE CASCADE,
    program_id TEXT NOT NULL REFERENCES federal_programs(id) ON DELETE CASCADE,
    relevance_score REAL,
    matched_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (agenda_item_id, program_id)
);
```

### Secondary Store: ChromaDB (Vector Search)

**Why Vector DB:**
- ✅ Semantic search ("find housing meetings mentioning wildfire")
- ✅ Similarity queries ("similar agenda items across cities")
- ✅ RAG support (future AI features)

**Collections:**
- `agenda_items_embeddings` - For semantic search
- `bills_embeddings` - Legislative similarity
- `issues_embeddings` - Complaint clustering

### Tertiary Store: Redis Cache (Fast Access)

**Why Redis:**
- ✅ Fast reads for common queries
- ✅ Session management
- ✅ Rate limiting
- ✅ Real-time features (WebSocket state)

**Cached Data:**
- Current city state snapshots (JSON)
- Top 10 upcoming meetings per jurisdiction
- Hot agenda items (high engagement)
- Legislative context lookup tables

---

## Temporal Consistency: State at Time T

### The Problem

Current architecture can't answer:
- "What meetings were scheduled on Oct 6, 2024?"
- "What was the state of issue #123 last week?"
- "How did agenda item 5.2 change between extraction runs?"

### The Solution: Bi-Temporal Data Model

**Two time dimensions:**
1. **Valid Time** - When the fact was true in reality
2. **Transaction Time** - When we learned about the fact

**Example:**

```sql
-- Meeting scheduled for Nov 15, extracted on Nov 1
INSERT INTO meetings (id, meeting_datetime, valid_from, valid_to)
VALUES ('mtg-123', '2025-11-15 18:00', '2025-11-01 10:00', NULL);

-- Meeting rescheduled to Nov 16, discovered on Nov 5
UPDATE meetings SET valid_to = '2025-11-05 14:00'
WHERE id = 'mtg-123' AND valid_to IS NULL;

INSERT INTO meetings (id, meeting_datetime, valid_from, valid_to)
VALUES ('mtg-123', '2025-11-16 18:00', '2025-11-05 14:00', NULL);
```

**Queries:**

```sql
-- What was scheduled as of Nov 3?
SELECT * FROM meetings
WHERE valid_from <= '2025-11-03'
  AND (valid_to IS NULL OR valid_to > '2025-11-03');

-- What is currently scheduled?
SELECT * FROM meetings WHERE valid_to IS NULL;

-- History of changes to meeting mtg-123
SELECT meeting_datetime, valid_from, valid_to
FROM meetings WHERE id = 'mtg-123'
ORDER BY valid_from;
```

---

## Migration from Current Architecture

### Phase 1: Unify Storage (Week 1-2)

**Goal:** Consolidate scattered JSON → SQL

**Tasks:**
1. Create new schema in `civic_participation.db` (or new PostgreSQL DB)
2. Migrate existing `civic_events` table → new `meetings` table with temporal versioning
3. Migrate `issues` table → new schema with matching columns
4. Import JSON files (`data/events/*.json`) as historical versions
5. Import legislative context JSON → `state_bills`, `federal_programs` tables

**Migration Script:**
```bash
python scripts/migrate_to_unified_state.py \
  --source data/events/ \
  --target civic_state.db \
  --preserve-history  # Create temporal versions
```

### Phase 2: Ingestion Pipeline (Week 3-4)

**Goal:** Clean separation: Extract → Normalize → Store

**New Architecture:**

```
┌──────────────────────────────────────────────────┐
│ EXTRACTORS (unchanged)                           │
│ - civic_digest.py                                │
│ - seeclickfix_client.py                          │
│ - legislative_discovery.py                       │
└─────────────────┬────────────────────────────────┘
                  │ Raw data (platform-specific)
                  ▼
┌──────────────────────────────────────────────────┐
│ NORMALIZER (new)                                 │
│ - Validates against civic-app-schema.json        │
│ - Enriches with legislative context              │
│ - Generates embeddings (ChromaDB)                │
└─────────────────┬────────────────────────────────┘
                  │ Normalized CityState objects
                  ▼
┌──────────────────────────────────────────────────┐
│ STATE STORE (new)                                │
│ - PostgreSQL/SQLite (structured data)            │
│ - ChromaDB (vector embeddings)                   │
│ - Redis (cache layer)                            │
└─────────────────┬────────────────────────────────┘
                  │ SQL + Vector queries
                  ▼
┌──────────────────────────────────────────────────┐
│ PROTOCOL API (new)                               │
│ - civic://city-berkeley/state                    │
│ - civic://city-berkeley/meetings?date=2025-11-14 │
│ - civic://city-berkeley/complaints               │
└──────────────────────────────────────────────────┘
```

**New Module:** `src/state_manager.py`

```python
class StateManager:
    """
    Unified interface for city state management.

    Replaces scattered JSON writes with atomic state updates.
    """

    def __init__(self, db_path: str):
        self.db = Database(db_path)
        self.vector_store = ChromaDB()
        self.cache = Redis()

    def update_meetings(
        self,
        jurisdiction_id: str,
        meetings: List[Meeting],
        as_of: datetime
    ) -> None:
        """
        Update meeting data with temporal versioning.

        Args:
            jurisdiction_id: City identifier
            meetings: List of meeting objects
            as_of: Timestamp of extraction
        """
        # Start transaction
        with self.db.transaction():
            # Close previous versions
            self.db.execute("""
                UPDATE meetings
                SET valid_to = ?
                WHERE jurisdiction_id = ?
                  AND valid_to IS NULL
            """, (as_of, jurisdiction_id))

            # Insert new versions
            for meeting in meetings:
                self.db.execute("""
                    INSERT INTO meetings (
                        id, jurisdiction_id, title, meeting_datetime,
                        valid_from, valid_to, ...
                    ) VALUES (?, ?, ?, ?, ?, NULL, ...)
                """, (meeting.id, jurisdiction_id, meeting.title, ...))

                # Generate embeddings
                embedding = self.generate_embedding(meeting.title + " " + meeting.description)
                self.vector_store.add(meeting.id, embedding, metadata=meeting.dict())

            # Invalidate cache
            self.cache.delete(f"city_state:{jurisdiction_id}")

    def get_city_state(
        self,
        jurisdiction_id: str,
        as_of: datetime = None
    ) -> CityState:
        """
        Get complete city state at specific time.

        Args:
            jurisdiction_id: City identifier
            as_of: Point in time (default: now)

        Returns:
            Complete CityState object
        """
        as_of = as_of or datetime.now()

        # Check cache
        cache_key = f"city_state:{jurisdiction_id}:{as_of.isoformat()}"
        cached = self.cache.get(cache_key)
        if cached:
            return CityState.parse_raw(cached)

        # Query database (temporal)
        meetings = self.db.query("""
            SELECT * FROM meetings
            WHERE jurisdiction_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to > ?)
        """, (jurisdiction_id, as_of, as_of))

        agenda_items = self.db.query("""
            SELECT ai.* FROM agenda_items ai
            JOIN meetings m ON ai.meeting_id = m.id
            WHERE m.jurisdiction_id = ?
              AND ai.valid_from <= ?
              AND (ai.valid_to IS NULL OR ai.valid_to > ?)
        """, (jurisdiction_id, as_of, as_of))

        issues = self.db.query("""
            SELECT * FROM issues
            WHERE jurisdiction_id = ?
              AND valid_from <= ?
              AND (valid_to IS NULL OR valid_to > ?)
        """, (jurisdiction_id, as_of, as_of))

        # Assemble CityState
        state = CityState(
            jurisdiction_id=jurisdiction_id,
            as_of=as_of,
            meetings=meetings,
            agenda_items=agenda_items,
            complaints=issues,
            ...
        )

        # Cache for 1 hour
        self.cache.setex(cache_key, 3600, state.json())

        return state
```

### Phase 3: Protocol API (Week 5-6)

**Goal:** Expose city state via standard protocol

**Implementation:** Extend `civic_api_integrated.py` → `civic_protocol_server.py`

```python
from fastapi import FastAPI
from state_manager import StateManager

app = FastAPI()
state_mgr = StateManager("civic_state.db")

@app.get("/civic/{jurisdiction_id}/state")
def get_city_state(
    jurisdiction_id: str,
    as_of: Optional[datetime] = None
):
    """
    Get complete city state.

    Maps to: civic://city-berkeley/state
    """
    return state_mgr.get_city_state(jurisdiction_id, as_of)

@app.get("/civic/{jurisdiction_id}/meetings")
def get_meetings(
    jurisdiction_id: str,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    project_type: Optional[str] = None
):
    """
    Query meetings with filters.

    Maps to: civic://city-berkeley/meetings?date=2025-11-14
    """
    return state_mgr.query_meetings(
        jurisdiction_id=jurisdiction_id,
        date_from=date_from,
        date_to=date_to,
        project_type=project_type
    )

@app.get("/civic/{jurisdiction_id}/complaints")
def get_complaints(
    jurisdiction_id: str,
    status: Optional[str] = None,
    issue_type: Optional[str] = None
):
    """
    Query operational issues.

    Maps to: civic://city-berkeley/complaints?status=open
    """
    return state_mgr.query_issues(
        jurisdiction_id=jurisdiction_id,
        status=status,
        issue_type=issue_type
    )
```

### Phase 4: Decouple Frontend (Week 7-8)

**Goal:** Frontend becomes protocol client

**Changes to `civic-workspace`:**

```typescript
// Old: Direct API calls
const response = await fetch('/api/events?jurisdiction=city-berkeley');

// New: Protocol client
import { CivicProtocolClient } from '@civic/protocol-client';

const client = new CivicProtocolClient('http://localhost:8001');
const state = await client.getCityState('city-berkeley');
const meetings = await client.query('civic://city-berkeley/meetings?date=2025-11-14');
```

**Benefits:**
- ✅ Frontend works with ANY protocol-compliant server
- ✅ Can swap backend without frontend changes
- ✅ Easy to A/B test different backends
- ✅ Third parties can build alternative frontends

---

## Benefits of This Architecture

### For Development

1. **Single Source of Truth**
   - No more "which is current: JSON or SQLite?"
   - Eliminates data synchronization bugs

2. **Temporal Queries**
   - "What was Berkeley's state on Oct 6?" just works
   - Historical analysis for retrospective studies

3. **Type Safety**
   - SQL constraints enforce data integrity
   - Schema validation catches errors early

4. **Testability**
   - Can snapshot test state at any point in time
   - Deterministic test fixtures

### For Protocol

1. **Clean Interface**
   - `civic://` URIs map directly to queries
   - Standardized responses (CityState objects)

2. **Extensibility**
   - Add new data sources without changing API
   - Frontend stays unchanged

3. **Federation**
   - Other orgs can run protocol servers
   - Federated queries across multiple servers

### For Foundation Narrative

1. **Infrastructure Play**
   - "We built the state representation for American democracy"
   - Not just an app, but foundational data layer

2. **Public Good**
   - Open protocol, not proprietary API
   - Others can build on top

3. **Scalability**
   - 26 cities → 340+ cities (SeeClickFix)
   - Same architecture works for counties, states

---

## Next Steps

### Immediate (This Week)

1. ✅ Create this design document
2. ⚠️ Review with stakeholders (you!)
3. ⬜ Prototype state manager (100 lines)
4. ⬜ Test with Berkeley data

### Short Term (Next 2 Weeks)

1. ⬜ Implement full state manager
2. ⬜ Migration script (JSON → SQL)
3. ⬜ Update civic_digest.py to use state manager
4. ⬜ Test with 5 cities

### Medium Term (Next Month)

1. ⬜ Protocol API implementation
2. ⬜ Decouple frontend
3. ⬜ ChromaDB integration
4. ⬜ Redis caching layer

### Long Term (2-3 Months)

1. ⬜ Publish protocol specification
2. ⬜ Build SDKs (Python, JS)
3. ⬜ Onboard first external consumer
4. ⬜ Foundation announcement

---

**Questions to resolve:**
1. PostgreSQL vs SQLite for production? (SQLite fine for 26 cities, PostgreSQL for 340+)
2. ChromaDB cloud vs local? (Local for now, cloud when scaling)
3. Redis required or optional? (Optional initially, good-to-have)
4. Backward compatibility strategy for existing JSON consumers?

