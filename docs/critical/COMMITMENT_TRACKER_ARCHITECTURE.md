# Commitment Tracker Architecture

*Created: Session 210 (December 2025)*
*Status: Design Draft*

## Overview

Track commitments made in public meetings ("staff will return with a report on X") and surface them for accountability - both for city staff (internal tracking) and residents (public accountability).

**Design constraint:** Modular enough to spin off as standalone product while integrating cleanly with Civic coordination platform.

---

## Architecture Principles

### 1. Separation of Concerns

```
┌─────────────────────────────────────────────────────────────┐
│                    CIVIC PLATFORM                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ Coordination│  │  What's     │  │  Who's      │         │
│  │  Workflows  │  │  Next/Past  │  │  With Me    │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                 │
│         └────────────────┼────────────────┘                 │
│                          │                                  │
│                          ▼                                  │
│              ┌───────────────────────┐                      │
│              │  Commitment Tracker   │◄── Integration layer │
│              │      (adapter)        │                      │
│              └───────────┬───────────┘                      │
└──────────────────────────┼──────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────┐
│              COMMITMENT TRACKER CORE                         │
│                  (standalone module)                         │
│                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ Detection  │  │  Storage   │  │  Matching  │            │
│  │  Engine    │  │   Layer    │  │   Engine   │            │
│  └────────────┘  └────────────┘  └────────────┘            │
│                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │ Resolution │  │   Query    │  │   Export   │            │
│  │  Tracker   │  │    API     │  │  Formats   │            │
│  └────────────┘  └────────────┘  └────────────┘            │
└──────────────────────────────────────────────────────────────┘
```

### 2. Spinoff-Ready Design

The commitment tracker core should:
- Have its own data models (not depend on Civic's StateManager)
- Have its own database schema (separate tables, or separate DB entirely)
- Expose a clean API that Civic consumes (but others could too)
- Have no imports from `civic.*` except through explicit adapter

```python
# GOOD: Commitment tracker is self-contained
from commitments import CommitmentTracker
tracker = CommitmentTracker(db_path="commitments.db")

# GOOD: Civic integrates via adapter
from civic._internal.commitments import CivicCommitmentAdapter
adapter = CivicCommitmentAdapter(tracker, civic_state_manager)

# BAD: Commitment tracker depends on Civic
from civic import StateManager  # NO - creates coupling
```

### 3. Dual-Use API

Same core, different interfaces:

| Interface | User | Focus |
|-----------|------|-------|
| `CommitmentTracker` | Standalone / City staff | CRUD, search, export |
| `CivicCommitmentAdapter` | Civic platform | Accountability, coordination triggers |
| REST API | External integrations | Programmatic access |

---

## Data Model

### Core Entities

```python
@dataclass
class Commitment:
    """A promise or commitment made in a public meeting."""
    id: str                          # UUID
    jurisdiction_id: str             # e.g., "city-san-rafael"

    # Source
    source_type: str                 # "meeting_transcript", "minutes", "staff_report"
    source_id: str                   # Video ID, document ID, etc.
    source_timestamp_ms: int | None  # For video/audio sources
    source_text: str                 # Exact quote
    source_context: str              # Surrounding context

    # Commitment details
    commitment_type: str             # "report_back", "study", "action", "policy", "follow_up"
    summary: str                     # LLM-generated plain language summary

    # Actors
    committed_by: str | None         # Speaker who made commitment (if identifiable)
    committed_by_role: str | None    # "council", "staff", "city_manager"
    assigned_to: str | None          # Department or person responsible

    # Timing
    made_at: datetime                # When commitment was made
    due_by: datetime | None          # Explicit deadline if stated
    implied_timeframe: str | None    # "next meeting", "Q1 2026", "within 90 days"

    # Status tracking
    status: str                      # "open", "in_progress", "completed", "stale", "superseded"
    resolution_date: datetime | None
    resolution_source_id: str | None # Meeting/doc where resolved
    resolution_notes: str | None

    # Metadata
    detected_at: datetime            # When our system found it
    detection_confidence: float      # 0.0-1.0
    detection_method: str            # "llm_extraction", "manual", "pattern_match"
    tags: list[str]                  # Topic tags

    # Linking
    related_agenda_item_id: str | None  # Link to agenda item if applicable
    related_commitment_ids: list[str]   # Supersedes/superseded_by relationships


@dataclass
class CommitmentUpdate:
    """An update or progress report on a commitment."""
    id: str
    commitment_id: str

    update_type: str                 # "progress", "completion", "deferral", "cancellation"
    source_type: str
    source_id: str
    source_timestamp_ms: int | None
    source_text: str

    reported_by: str | None
    reported_at: datetime

    notes: str | None
    detected_at: datetime
    detection_confidence: float


@dataclass
class CommitmentMatch:
    """A potential resolution match between commitment and later event."""
    commitment_id: str
    candidate_source_type: str       # "agenda_item", "staff_report", "meeting_transcript"
    candidate_source_id: str

    match_type: str                  # "likely_resolution", "progress_update", "related_discussion"
    match_confidence: float          # 0.0-1.0
    match_reasoning: str             # LLM explanation

    status: str                      # "pending_review", "confirmed", "rejected"
    reviewed_by: str | None          # "auto", "user:xxx"
    reviewed_at: datetime | None
```

### Database Schema (SQLite)

```sql
-- Standalone schema, no foreign keys to Civic tables

CREATE TABLE commitments (
    id TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL,

    -- Source
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_timestamp_ms INTEGER,
    source_text TEXT NOT NULL,
    source_context TEXT,

    -- Details
    commitment_type TEXT NOT NULL,
    summary TEXT NOT NULL,

    -- Actors
    committed_by TEXT,
    committed_by_role TEXT,
    assigned_to TEXT,

    -- Timing
    made_at TEXT NOT NULL,  -- ISO 8601
    due_by TEXT,
    implied_timeframe TEXT,

    -- Status
    status TEXT NOT NULL DEFAULT 'open',
    resolution_date TEXT,
    resolution_source_id TEXT,
    resolution_notes TEXT,

    -- Metadata
    detected_at TEXT NOT NULL,
    detection_confidence REAL NOT NULL,
    detection_method TEXT NOT NULL,
    tags TEXT,  -- JSON array

    -- Linking
    related_agenda_item_id TEXT,
    related_commitment_ids TEXT,  -- JSON array

    -- Indexes
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_commitments_jurisdiction ON commitments(jurisdiction_id);
CREATE INDEX idx_commitments_status ON commitments(status);
CREATE INDEX idx_commitments_made_at ON commitments(made_at);
CREATE INDEX idx_commitments_source ON commitments(source_type, source_id);

CREATE TABLE commitment_updates (
    id TEXT PRIMARY KEY,
    commitment_id TEXT NOT NULL REFERENCES commitments(id),

    update_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_timestamp_ms INTEGER,
    source_text TEXT NOT NULL,

    reported_by TEXT,
    reported_at TEXT NOT NULL,

    notes TEXT,
    detected_at TEXT NOT NULL,
    detection_confidence REAL NOT NULL,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_updates_commitment ON commitment_updates(commitment_id);

CREATE TABLE commitment_matches (
    id TEXT PRIMARY KEY,
    commitment_id TEXT NOT NULL REFERENCES commitments(id),

    candidate_source_type TEXT NOT NULL,
    candidate_source_id TEXT NOT NULL,

    match_type TEXT NOT NULL,
    match_confidence REAL NOT NULL,
    match_reasoning TEXT,

    status TEXT NOT NULL DEFAULT 'pending_review',
    reviewed_by TEXT,
    reviewed_at TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_matches_commitment ON commitment_matches(commitment_id);
CREATE INDEX idx_matches_status ON commitment_matches(status);
```

---

## Core Module Design

### Package Structure

```
packages/
├── civic/                          # Existing Civic package
│   └── src/civic/
│       └── _internal/
│           └── commitments/
│               └── adapter.py      # CivicCommitmentAdapter
│
└── commitments/                    # NEW: Standalone package
    ├── pyproject.toml
    ├── src/commitments/
    │   ├── __init__.py
    │   ├── models.py               # Dataclasses above
    │   ├── storage.py              # Database layer
    │   ├── detection.py            # LLM extraction
    │   ├── matching.py             # Resolution matching
    │   ├── tracker.py              # Main API class
    │   ├── export.py               # PRA/report formatters
    │   └── api/
    │       ├── __init__.py
    │       └── rest.py             # FastAPI endpoints
    └── tests/
```

### Core API

```python
# packages/commitments/src/commitments/tracker.py

class CommitmentTracker:
    """
    Standalone commitment tracking system.

    Can be used independently or integrated with Civic platform.
    """

    def __init__(
        self,
        db_path: str | Path,
        llm_provider: LLMProvider | None = None,  # For detection/matching
    ):
        self.storage = CommitmentStorage(db_path)
        self.detector = CommitmentDetector(llm_provider)
        self.matcher = CommitmentMatcher(llm_provider)

    # === Detection ===

    def extract_from_transcript(
        self,
        transcript_path: str | Path,
        jurisdiction_id: str,
        meeting_date: date,
    ) -> list[Commitment]:
        """Extract commitments from a meeting transcript."""
        ...

    def extract_from_minutes(
        self,
        minutes_text: str,
        jurisdiction_id: str,
        meeting_date: date,
    ) -> list[Commitment]:
        """Extract commitments from official minutes."""
        ...

    def extract_from_chunks(
        self,
        chunks: list[dict],  # RAG chunks with metadata
        jurisdiction_id: str,
    ) -> list[Commitment]:
        """Extract commitments from pre-chunked transcript."""
        ...

    # === Storage ===

    def add_commitment(self, commitment: Commitment) -> str:
        """Add a commitment (returns ID)."""
        ...

    def get_commitment(self, commitment_id: str) -> Commitment | None:
        """Get a single commitment by ID."""
        ...

    def update_status(
        self,
        commitment_id: str,
        status: str,
        resolution_source_id: str | None = None,
        resolution_notes: str | None = None,
    ) -> bool:
        """Update commitment status."""
        ...

    # === Querying ===

    def get_open_commitments(
        self,
        jurisdiction_id: str,
        older_than_days: int | None = None,
        commitment_type: str | None = None,
        assigned_to: str | None = None,
    ) -> list[Commitment]:
        """Get open commitments, optionally filtered."""
        ...

    def get_stale_commitments(
        self,
        jurisdiction_id: str,
        stale_threshold_days: int = 90,
    ) -> list[Commitment]:
        """Get commitments with no updates past threshold."""
        ...

    def search_commitments(
        self,
        jurisdiction_id: str,
        query: str,
        status: str | None = None,
        date_range: tuple[date, date] | None = None,
    ) -> list[Commitment]:
        """Semantic search over commitments."""
        ...

    # === Matching ===

    def find_potential_resolutions(
        self,
        commitment_id: str,
        search_sources: list[str],  # ["agenda_items", "transcripts", "staff_reports"]
    ) -> list[CommitmentMatch]:
        """Find candidates that might resolve this commitment."""
        ...

    def match_against_agenda(
        self,
        jurisdiction_id: str,
        agenda_items: list[dict],
    ) -> list[CommitmentMatch]:
        """Check if any agenda items might resolve open commitments."""
        ...

    # === Export ===

    def export_pra_response(
        self,
        jurisdiction_id: str,
        query: str,
        date_range: tuple[date, date] | None = None,
        format: str = "pdf",  # "pdf", "csv", "json"
    ) -> bytes | dict:
        """Generate PRA-ready export of commitments matching query."""
        ...

    def export_dashboard_data(
        self,
        jurisdiction_id: str,
    ) -> dict:
        """Export data for dashboard visualization."""
        ...

    def export_accountability_report(
        self,
        jurisdiction_id: str,
        period: str = "quarterly",
    ) -> dict:
        """Generate accountability report (open, resolved, stale)."""
        ...
```

### Detection Engine

```python
# packages/commitments/src/commitments/detection.py

class CommitmentDetector:
    """Extract commitments from meeting content using LLM."""

    COMMITMENT_PATTERNS = [
        # Explicit promises
        r"staff will (return|come back|report|provide|prepare)",
        r"we('ll| will) (bring|come) back",
        r"direct(s|ed|ing) staff to",
        r"request(s|ed|ing) (a |that )?staff",

        # Timeline indicators
        r"(within|by|before) (the next|\d+) (days|weeks|months|meeting)",
        r"at (the|our|a) (next|future|upcoming) meeting",
        r"by (Q[1-4]|January|February|March|April|May|June|July|August|September|October|November|December)",

        # Action items
        r"action item",
        r"follow[- ]up",
        r"(will|to) be (scheduled|agendized|placed on)",
    ]

    def __init__(self, llm_provider: LLMProvider | None = None):
        self.llm = llm_provider
        self._patterns = [re.compile(p, re.IGNORECASE) for p in self.COMMITMENT_PATTERNS]

    def detect_in_text(
        self,
        text: str,
        context: dict,  # source_type, source_id, timestamp, etc.
    ) -> list[Commitment]:
        """
        Two-phase detection:
        1. Pattern matching to find candidates (fast, cheap)
        2. LLM extraction to parse details (accurate, costs tokens)
        """
        # Phase 1: Find candidate passages
        candidates = self._find_candidates(text)

        if not candidates:
            return []

        # Phase 2: LLM extraction
        if self.llm:
            return self._extract_with_llm(candidates, context)
        else:
            return self._extract_with_patterns(candidates, context)

    def _find_candidates(self, text: str) -> list[tuple[int, int, str]]:
        """Find text spans that might contain commitments."""
        candidates = []
        for pattern in self._patterns:
            for match in pattern.finditer(text):
                # Expand to sentence boundaries
                start = text.rfind('.', 0, match.start()) + 1
                end = text.find('.', match.end())
                if end == -1:
                    end = len(text)
                candidates.append((start, end, text[start:end].strip()))
        return candidates

    def _extract_with_llm(
        self,
        candidates: list[tuple[int, int, str]],
        context: dict,
    ) -> list[Commitment]:
        """Use LLM to extract structured commitments from candidates."""

        prompt = """Analyze these passages from a city council meeting and extract any commitments or promises made.

PASSAGES:
{passages}

For each commitment found, extract:
1. summary: Plain language description of what was promised
2. commitment_type: One of "report_back", "study", "action", "policy", "follow_up"
3. committed_by: Who made the commitment (if identifiable)
4. committed_by_role: "council", "staff", "city_manager", "mayor", or null
5. assigned_to: Department or person responsible (if stated)
6. due_by: Explicit deadline if stated (ISO date or null)
7. implied_timeframe: Relative timeframe if stated ("next meeting", "within 90 days", etc.)
8. exact_quote: The exact text containing the commitment

Return JSON array of commitments. If no commitments found, return [].
"""
        # ... LLM call and parsing
```

---

## Civic Platform Integration

### Adapter Layer

```python
# packages/civicos/src/civicos/_internal/commitments/adapter.py

class CivicCommitmentAdapter:
    """
    Integrates standalone CommitmentTracker with Civic platform.

    Provides:
    - Automatic extraction when meetings are processed
    - Linking to Civic agenda items and decisions
    - Accountability triggers for coordination workflows
    """

    def __init__(
        self,
        tracker: CommitmentTracker,
        state_manager: StateManager,
    ):
        self.tracker = tracker
        self.state = state_manager

    # === Automatic Processing ===

    def process_meeting(
        self,
        jurisdiction_id: str,
        meeting_id: str,
    ) -> list[Commitment]:
        """
        Extract commitments when a meeting is processed.
        Called automatically by Civic's meeting ingestion pipeline.
        """
        # Get transcript chunks (already processed by Civic)
        chunks = self.state.get_transcript_chunks(meeting_id)

        # Extract commitments
        commitments = self.tracker.extract_from_chunks(chunks, jurisdiction_id)

        # Link to agenda items
        for commitment in commitments:
            self._link_to_agenda_items(commitment, meeting_id)

        return commitments

    def check_agenda_for_resolutions(
        self,
        jurisdiction_id: str,
        agenda_items: list[dict],
    ) -> list[dict]:
        """
        Check if upcoming agenda might resolve open commitments.
        Used to enrich 'whats_next()' responses.

        Returns items with potential_resolutions attached.
        """
        matches = self.tracker.match_against_agenda(jurisdiction_id, agenda_items)

        # Group matches by agenda item
        item_matches = defaultdict(list)
        for match in matches:
            item_matches[match.candidate_source_id].append(match)

        # Enrich agenda items
        for item in agenda_items:
            if item['id'] in item_matches:
                item['potential_commitment_resolutions'] = [
                    {
                        'commitment_id': m.commitment_id,
                        'commitment_summary': self.tracker.get_commitment(m.commitment_id).summary,
                        'confidence': m.match_confidence,
                    }
                    for m in item_matches[item['id']]
                ]

        return agenda_items

    # === Coordination Triggers ===

    def get_accountability_opportunities(
        self,
        jurisdiction_id: str,
    ) -> list[dict]:
        """
        Find stale commitments that could be coordination opportunities.

        "Council promised X 6 months ago. No update.
         This could be a focus for resident coordination."
        """
        stale = self.tracker.get_stale_commitments(jurisdiction_id, stale_threshold_days=90)

        opportunities = []
        for commitment in stale:
            opportunities.append({
                'type': 'stale_commitment',
                'commitment': commitment.to_dict(),
                'suggested_action': 'public_comment',
                'talking_point': f"On {commitment.made_at.strftime('%B %d, %Y')}, "
                                 f"council committed to: {commitment.summary}. "
                                 f"What is the status of this commitment?",
                'days_since_commitment': (date.today() - commitment.made_at.date()).days,
            })

        return opportunities

    # === Civic API Extensions ===

    def what_was_promised(
        self,
        jurisdiction_id: str,
        topic: str | None = None,
        status: str = "open",
    ) -> list[Commitment]:
        """
        API method for residents: "What did council promise about housing?"

        Exposes commitment tracker through Civic's query interface.
        """
        if topic:
            return self.tracker.search_commitments(
                jurisdiction_id,
                query=topic,
                status=status,
            )
        else:
            return self.tracker.get_open_commitments(
                jurisdiction_id,
            )
```

### Integration with Civic API

```python
# packages/civicos/src/civicos/civic.py (additions to main Civic class)

class Civic:

    def __init__(self, jurisdiction_id: str):
        # ... existing init ...

        # Commitment tracking (lazy loaded)
        self._commitment_adapter: CivicCommitmentAdapter | None = None

    @property
    def commitments(self) -> CivicCommitmentAdapter:
        """Access commitment tracking features."""
        if self._commitment_adapter is None:
            from civic._internal.commitments.adapter import CivicCommitmentAdapter
            from commitments import CommitmentTracker

            tracker = CommitmentTracker(
                db_path=self._get_commitments_db_path(),
                llm_provider=self._llm_provider,
            )
            self._commitment_adapter = CivicCommitmentAdapter(tracker, self._state)
        return self._commitment_adapter

    # === New API Methods ===

    def what_was_promised(
        self,
        topic: str | None = None,
        status: str = "open",
    ) -> list[dict]:
        """
        Query commitments made by council/staff.

        Examples:
            c.what_was_promised()  # All open commitments
            c.what_was_promised("housing")  # Housing-related commitments
            c.what_was_promised(status="stale")  # Commitments with no recent updates
        """
        commitments = self.commitments.what_was_promised(
            self.jurisdiction_id,
            topic=topic,
            status=status,
        )
        return [c.to_dict() for c in commitments]

    def accountability_opportunities(self) -> list[dict]:
        """
        Find stale commitments that could be coordination targets.

        Returns opportunities for residents to ask "what happened to X?"
        """
        return self.commitments.get_accountability_opportunities(self.jurisdiction_id)
```

---

## Standalone Product Interface

### REST API (for city staff dashboard)

```python
# packages/commitments/src/commitments/api/rest.py

from fastapi import FastAPI, Query
from commitments import CommitmentTracker

app = FastAPI(title="Commitment Tracker API")

@app.get("/jurisdictions/{jurisdiction_id}/commitments")
def list_commitments(
    jurisdiction_id: str,
    status: str = Query("open", enum=["open", "in_progress", "completed", "stale", "all"]),
    type: str | None = Query(None),
    assigned_to: str | None = Query(None),
    older_than_days: int | None = Query(None),
):
    """List commitments for a jurisdiction."""
    ...

@app.get("/jurisdictions/{jurisdiction_id}/commitments/search")
def search_commitments(
    jurisdiction_id: str,
    q: str = Query(..., description="Search query"),
    status: str = Query("all"),
):
    """Semantic search over commitments."""
    ...

@app.get("/jurisdictions/{jurisdiction_id}/commitments/stale")
def get_stale_commitments(
    jurisdiction_id: str,
    threshold_days: int = Query(90),
):
    """Get commitments with no updates past threshold."""
    ...

@app.get("/jurisdictions/{jurisdiction_id}/dashboard")
def get_dashboard(jurisdiction_id: str):
    """Get dashboard data (counts by status, recent activity, etc.)."""
    ...

@app.get("/jurisdictions/{jurisdiction_id}/export/pra")
def export_pra(
    jurisdiction_id: str,
    query: str = Query(...),
    format: str = Query("pdf", enum=["pdf", "csv", "json"]),
):
    """Generate PRA-ready export."""
    ...

@app.post("/jurisdictions/{jurisdiction_id}/commitments/{commitment_id}/status")
def update_status(
    jurisdiction_id: str,
    commitment_id: str,
    status: str,
    notes: str | None = None,
):
    """Update commitment status (manual resolution)."""
    ...
```

### CLI Interface

```python
# packages/commitments/src/commitments/cli.py

import click
from commitments import CommitmentTracker

@click.group()
def cli():
    """Commitment Tracker CLI"""
    pass

@cli.command()
@click.argument('transcript_path')
@click.option('--jurisdiction', '-j', required=True)
@click.option('--date', '-d', required=True, help='Meeting date (YYYY-MM-DD)')
def extract(transcript_path, jurisdiction, date):
    """Extract commitments from a transcript."""
    tracker = CommitmentTracker("commitments.db")
    commitments = tracker.extract_from_transcript(transcript_path, jurisdiction, date)
    click.echo(f"Extracted {len(commitments)} commitments")
    for c in commitments:
        click.echo(f"  - {c.summary}")

@cli.command()
@click.option('--jurisdiction', '-j', required=True)
@click.option('--status', '-s', default='open')
def list(jurisdiction, status):
    """List commitments."""
    tracker = CommitmentTracker("commitments.db")
    commitments = tracker.get_open_commitments(jurisdiction) if status == 'open' else ...
    for c in commitments:
        click.echo(f"[{c.status}] {c.summary} (made {c.made_at})")

@cli.command()
@click.option('--jurisdiction', '-j', required=True)
@click.option('--days', '-d', default=90)
def stale(jurisdiction, days):
    """Show stale commitments."""
    tracker = CommitmentTracker("commitments.db")
    stale = tracker.get_stale_commitments(jurisdiction, days)
    click.echo(f"{len(stale)} commitments with no updates in {days} days:")
    for c in stale:
        click.echo(f"  - {c.summary}")
```

---

## Implementation Phases

### Phase 1: Core Detection (2-3 sessions)
- [ ] Data models and storage layer
- [ ] Basic pattern-based detection
- [ ] LLM extraction prompts
- [ ] Unit tests

### Phase 2: Civic Integration (2 sessions)
- [ ] Adapter layer
- [ ] `what_was_promised()` API method
- [ ] Integration with meeting processing pipeline
- [ ] Integration tests

### Phase 3: Matching & Resolution (2-3 sessions)
- [ ] Resolution matching engine
- [ ] Agenda checking for potential resolutions
- [ ] `accountability_opportunities()` method
- [ ] Stale commitment detection

### Phase 4: Export & Dashboard (2 sessions)
- [ ] PRA export formatting
- [ ] Dashboard data API
- [ ] Basic REST API
- [ ] CLI tools

### Phase 5: Standalone Polish (if pursuing spinoff)
- [ ] Standalone package structure
- [ ] Documentation
- [ ] Docker deployment
- [ ] Demo instance

---

## Success Metrics

### For Civic Platform
- Commitments detected per meeting (target: 3-10)
- Accountability opportunities surfaced (target: 5+ stale commitments per quarter)
- Resident usage of `what_was_promised()`

### For Standalone Product
- City staff time saved on PRA responses
- Commitment resolution rate improvement
- User engagement with dashboard

---

## Open Questions

1. **Storage separation**: Same DB as Civic, or fully separate? (Leaning: separate for clean spinoff)

2. **LLM costs**: Detection is ~$0.01-0.02 per meeting. Acceptable for both paths?

3. **Manual override UI**: City staff need to mark resolutions manually. Build basic UI or rely on API/CLI?

4. **Historical backfill**: Process past meetings to build commitment history? (Probably yes for pilot city)

---

## Related Documentation

- `docs/critical/FOUNDATION_FUNDING_THESIS.md` - Revenue considerations
- `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md` - Overall architecture
- `packages/civicos/src/civicos/_internal/meetings/transcript.py` - Transcript processing
