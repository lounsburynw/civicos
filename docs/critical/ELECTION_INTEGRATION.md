# Election Data Integration Reference

> **Future State:** This document describes a planned integration that has not yet been implemented. It is included as a design reference for post-launch work. No election data is currently ingested.

**Purpose:** Reference document for future implementation after core data ingestion is complete.
**Target:** Post-launch
**Primary use case:** Upcoming elections + deadlines in `whats_next()`

---

## Multi-Source Strategy

```
Google Civic API (Primary) ──┐
                             ├──> Source Fusion ──> Storage ──> whats_next()
Marin County Registrar ──────┘
```

| Source | Role | Data | Cost |
|--------|------|------|------|
| **Google Civic Info API** | Primary | Elections, polling locations, reps | Free (have key) |
| **Marin County Registrar** | Authoritative | Official dates, local measures | Free (scraping) |

**Fusion strategy:** Merge by election date + jurisdiction. Prefer Marin Registrar for local data conflicts.

## Election Scope (Multi-Level)

Elections span all government levels. Google Civic API returns all applicable elections for an address:

| Level | Examples | Source |
|-------|----------|--------|
| **Federal** | President, US House CA-02, US Senate | Google Civic API |
| **State** | Governor, State Assembly D-12, Propositions | Google Civic API + CA SoS |
| **County** | Board of Supervisors D-1, County Measures | Marin Registrar |
| **City** | Mayor, City Council, Local Measures | Marin Registrar |

---

## 1. Add ELECTIONS to CorpusType

**File:** `packages/civicos/src/civicos/storage/corpus_types.py`

```python
# Add to CorpusType enum (line ~44, after ISSUES)
class CorpusType(str, Enum):
    # ... existing types ...
    ISSUES = "issues"           # Community issues (aka "issue" singular)

    # NEW: Elections corpus
    ELECTIONS = "elections"     # Elections, contests, ballot measures

    # State/federal-level corpora
    LEGISLATION = "legislation"
    # ...
```

```python
# Add to CORPUS_REGISTRY (line ~163, before closing brace)
    CorpusType.ELECTIONS: CorpusConfig(
        display_name="Elections",
        storage_method="get_elections",
        count_method="get_election_count",
        text_extractor="_election_to_text",
        jurisdiction_type="both",  # Elections span federal/state/local
        aliases=("election", "ballot", "vote"),
        has_meeting_context=False,
    ),
```

---

## 2. Data Models

**New file:** `packages/civicos/src/civicos/_internal/elections/__init__.py`

```python
"""Election data models."""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from enum import Enum


class ElectionType(str, Enum):
    """Type of election."""
    GENERAL = "general"
    PRIMARY = "primary"
    SPECIAL = "special"
    RUNOFF = "runoff"
    RECALL = "recall"


class ContestType(str, Enum):
    """Type of contest/race."""
    FEDERAL_PRESIDENT = "federal_president"
    FEDERAL_SENATE = "federal_senate"
    FEDERAL_HOUSE = "federal_house"
    STATE_GOVERNOR = "state_governor"
    STATE_LEGISLATURE = "state_legislature"
    STATE_PROPOSITION = "state_proposition"
    LOCAL_MAYOR = "local_mayor"
    LOCAL_COUNCIL = "local_council"
    LOCAL_SCHOOL_BOARD = "local_school_board"
    LOCAL_MEASURE = "local_measure"
    JUDICIAL = "judicial"
    OTHER = "other"


@dataclass
class ElectionDeadline:
    """Key deadline in election timeline."""
    deadline_type: str  # registration, early_voting_start, election_day
    deadline_date: date
    description: str
    is_passed: bool = False


@dataclass
class PollingLocation:
    """Voting location information."""
    id: str
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    hours: Optional[str] = None
    is_early_voting: bool = False
    is_dropbox: bool = False


@dataclass
class Candidate:
    """Candidate in a race."""
    id: str
    name: str
    party: Optional[str] = None
    incumbent: bool = False
    website: Optional[str] = None
    source: str = "unknown"
    # Link to elected official record (if incumbent)
    official_id: Optional[str] = None


@dataclass
class BallotMeasure:
    """Ballot measure/proposition."""
    id: str
    title: str
    description: str
    measure_type: str  # bond, tax, ordinance, initiative
    full_text_url: Optional[str] = None
    arguments_for: List[str] = field(default_factory=list)
    arguments_against: List[str] = field(default_factory=list)
    passed: Optional[bool] = None
    source: str = "unknown"


@dataclass
class Contest:
    """A contest/race within an election."""
    id: str
    title: str
    contest_type: ContestType
    district_name: Optional[str] = None
    candidates: List[Candidate] = field(default_factory=list)
    ballot_measure: Optional[BallotMeasure] = None
    number_elected: int = 1
    source: str = "unknown"


@dataclass
class Election:
    """An election event."""
    id: str
    jurisdiction_id: str
    name: str
    election_date: date
    election_type: ElectionType
    deadlines: List[ElectionDeadline] = field(default_factory=list)
    contests: List[Contest] = field(default_factory=list)
    polling_locations: List[PollingLocation] = field(default_factory=list)
    is_past: bool = False
    source: str = "unknown"
    source_url: Optional[str] = None
    last_updated: Optional[datetime] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def next_deadline(self) -> Optional[ElectionDeadline]:
        """Get next upcoming deadline."""
        today = date.today()
        upcoming = [d for d in self.deadlines if d.deadline_date >= today]
        return min(upcoming, key=lambda d: d.deadline_date) if upcoming else None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "jurisdiction_id": self.jurisdiction_id,
            "name": self.name,
            "election_date": self.election_date.isoformat(),
            "election_type": self.election_type.value,
            "deadlines": [
                {
                    "deadline_type": d.deadline_type,
                    "deadline_date": d.deadline_date.isoformat(),
                    "description": d.description,
                }
                for d in self.deadlines
            ],
            "contests": [
                {
                    "id": c.id,
                    "title": c.title,
                    "contest_type": c.contest_type.value,
                    "candidates": [{"id": x.id, "name": x.name, "party": x.party} for x in c.candidates],
                    "ballot_measure": {
                        "id": c.ballot_measure.id,
                        "title": c.ballot_measure.title,
                        "description": c.ballot_measure.description,
                    } if c.ballot_measure else None,
                }
                for c in self.contests
            ],
            "source": self.source,
            "source_url": self.source_url,
            "raw_data": self.raw_data,
        }


# ========== Elected Officials (for voting record linkage) ==========

@dataclass
class ElectedOfficial:
    """
    An elected official who votes on council decisions.

    Links elections (candidates) to decisions (votes).
    """
    id: str
    name: str                      # Full name: "Jane Smith"
    seat: str                      # "City Council District 1", "Mayor"
    jurisdiction_id: str           # "city-san-rafael"
    term_start: date
    term_end: Optional[date]       # None if current

    # Name variations for matching
    name_variations: List[str] = field(default_factory=list)
    # e.g., ["Councilmember Smith", "J. Smith", "Jane Smith"]

    # Link to election candidate record
    candidate_id: Optional[str] = None

    def matches_name(self, name: str) -> bool:
        """Check if a name matches this official."""
        name_lower = name.lower()
        if self.name.lower() in name_lower or name_lower in self.name.lower():
            return True
        return any(v.lower() in name_lower for v in self.name_variations)


@dataclass
class VotingRecord:
    """An official's voting record on a topic."""
    official_id: str
    official_name: str
    topic: str
    total_votes: int
    yes_votes: int
    no_votes: int
    abstain_votes: int
    decisions: List[Dict[str, Any]]  # [{decision_id, title, date, vote}]

    @property
    def yes_percentage(self) -> float:
        if self.total_votes == 0:
            return 0.0
        return (self.yes_votes / self.total_votes) * 100
```

---

## 3. Voting Record Linkage

### The Linkage Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   ELECTIONS     │     │ ELECTED_OFFICIALS│     │   DECISIONS     │
├─────────────────┤     ├──────────────────┤     ├─────────────────┤
│ candidate_id    │────▶│ official_id      │◀────│ vote_results    │
│ name            │     │ name             │     │ {official_id:   │
│ office          │     │ seat             │     │  "yes"|"no"}    │
│ election_date   │     │ term_start       │     │                 │
└─────────────────┘     │ term_end         │     └─────────────────┘
                        │ name_variations  │
                        └──────────────────┘
                               │
                               ▼
                    "Jane Smith voted YES on
                     12 of 15 housing items"
```

### What We Need to Build

#### 1. Extract Roll Call Votes from Minutes

Minutes contain patterns like:
```
AYES: Councilmember Smith, Councilmember Jones, Mayor Brown
NOES: Councilmember Wilson
ABSENT: Councilmember Davis
```

**Add to decision extraction:**
```python
def extract_roll_call(minutes_text: str) -> Dict[str, str]:
    """
    Extract roll call votes from minutes text.

    Returns:
        {"Smith": "yes", "Jones": "yes", "Brown": "yes",
         "Wilson": "no", "Davis": "absent"}
    """
    import re
    votes = {}

    # Pattern: AYES: Name1, Name2, ...
    ayes_match = re.search(r'AYES?:?\s*([^\n]+)', minutes_text, re.I)
    if ayes_match:
        for name in ayes_match.group(1).split(','):
            name = name.strip()
            # Extract last name from "Councilmember Smith"
            parts = name.split()
            if parts:
                votes[parts[-1]] = "yes"

    # Pattern: NOES: Name1, Name2, ...
    noes_match = re.search(r'NOES?:?\s*([^\n]+)', minutes_text, re.I)
    if noes_match:
        for name in noes_match.group(1).split(','):
            name = name.strip()
            if name.lower() != 'none':
                parts = name.split()
                if parts:
                    votes[parts[-1]] = "no"

    return votes
```

#### 2. Elected Officials Table

```sql
CREATE TABLE IF NOT EXISTS elected_officials (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    seat TEXT NOT NULL,
    jurisdiction_id TEXT NOT NULL,
    term_start TEXT NOT NULL,
    term_end TEXT,  -- NULL = current
    name_variations TEXT,  -- JSON array
    candidate_id TEXT,  -- Link to election candidate
    valid_from TEXT NOT NULL DEFAULT (datetime('now')),
    valid_to TEXT
);

CREATE INDEX IF NOT EXISTS idx_officials_jurisdiction
    ON elected_officials(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_officials_current
    ON elected_officials(term_end) WHERE term_end IS NULL;
```

#### 3. Populate from Google Civic API

```python
def sync_elected_officials(self, jurisdiction_id: str) -> int:
    """
    Sync elected officials from Google Civic API representatives endpoint.

    This creates the linkage between elections and decisions.
    """
    result = self.google_civic.get_representatives()
    if not result:
        return 0

    officials = []
    for office in result.get("offices", []):
        for idx in office.get("officialIndices", []):
            official_data = result["officials"][idx]
            officials.append(ElectedOfficial(
                id=f"{jurisdiction_id}-{office['name'].lower().replace(' ', '-')}",
                name=official_data["name"],
                seat=office["name"],
                jurisdiction_id=jurisdiction_id,
                term_start=date.today(),  # Approximate
                term_end=None,
                name_variations=self._generate_name_variations(official_data["name"]),
            ))

    return self._storage.store_elected_officials(jurisdiction_id, officials)
```

#### 4. Link Decisions to Officials

```python
def get_voting_record(
    self,
    official_name: str,
    topic: Optional[str] = None,
) -> VotingRecord:
    """
    Get voting record for an elected official.

    Args:
        official_name: Name of official (e.g., "Jane Smith")
        topic: Optional topic filter (e.g., "housing")

    Returns:
        VotingRecord with aggregated stats and decision list
    """
    # Find official
    official = self._find_official_by_name(official_name)
    if not official:
        raise ValueError(f"Official not found: {official_name}")

    # Get decisions with votes
    decisions = self._storage.get_decisions(
        jurisdiction_id=self.jurisdiction,
        limit=500,
    )

    # Filter to decisions where this official voted
    voted_decisions = []
    for d in decisions:
        vote_results = d.get("vote_results", {})
        # Match by name variations
        for name, vote in vote_results.items():
            if official.matches_name(name):
                voted_decisions.append({
                    "decision_id": d["id"],
                    "title": d["title"],
                    "date": d["meeting_date"],
                    "vote": vote,
                    "topics": d.get("topics", []),
                })
                break

    # Filter by topic if provided
    if topic:
        voted_decisions = [
            d for d in voted_decisions
            if topic.lower() in [t.lower() for t in d.get("topics", [])]
        ]

    # Aggregate
    yes_votes = sum(1 for d in voted_decisions if d["vote"] == "yes")
    no_votes = sum(1 for d in voted_decisions if d["vote"] == "no")
    abstain = sum(1 for d in voted_decisions if d["vote"] == "abstain")

    return VotingRecord(
        official_id=official.id,
        official_name=official.name,
        topic=topic or "all",
        total_votes=len(voted_decisions),
        yes_votes=yes_votes,
        no_votes=no_votes,
        abstain_votes=abstain,
        decisions=voted_decisions,
    )
```

---

## 4. Example Queries

### Basic Election Queries

```python
from civicos import CivicOS
from datetime import date

c = CivicOS("san-rafael")

# ========================================
# 1. whats_next() with elections
# ========================================

>>> c.whats_next(days=90, include_elections=True)
[
    Meeting(
        id="deadline-reg-2026-primary",
        title="Voter Registration Deadline: June 2026 Primary",
        date=datetime(2026, 5, 18),
        body="Last day to register to vote in the June 2026 Primary Election",
    ),
    Meeting(
        id="city-council-2026-01-21",
        title="City Council Meeting",
        date=datetime(2026, 1, 21),
        body="Regular Meeting",
        agenda_items=[...],
    ),
    Meeting(
        id="election-2026-primary",
        title="California Primary Election",
        date=datetime(2026, 6, 2),
        body="primary election",
    ),
]

# ========================================
# 2. whats_on_ballot() - detailed view
# ========================================

>>> election = c.whats_on_ballot(election_date=date(2026, 6, 2))
>>> election
Election(
    id="ca-2026-primary",
    name="California Primary Election",
    election_date=date(2026, 6, 2),
    election_type=ElectionType.PRIMARY,
    deadlines=[
        ElectionDeadline(
            deadline_type="registration",
            deadline_date=date(2026, 5, 18),
            description="Last day to register online or by mail",
        ),
        ElectionDeadline(
            deadline_type="early_voting_start",
            deadline_date=date(2026, 5, 9),
            description="Vote centers open, vote-by-mail begins",
        ),
    ],
    contests=[...],
)

# What's on MY ballot? (multi-level)
>>> for contest in election.contests:
...     print(f"{contest.contest_type.value}: {contest.title}")
...
federal_senate: U.S. Senator
federal_house: U.S. Representative, District 2
state_governor: Governor
state_legislature: State Assembly, District 12
local_council: San Rafael City Council, District 1
local_measure: Measure A - San Rafael Parks Bond
state_proposition: Proposition 1 - Housing Bond Act

# ========================================
# 3. Semantic search for ballot measures
# ========================================

# "I care about housing - what's on the ballot?"
>>> c.search_ballot_measures("affordable housing", election_date=date(2026, 11, 3))
[
    BallotMeasure(
        id="ca-prop-1-2026",
        title="Proposition 1 - Housing Bond Act",
        description="$10 billion bond for affordable housing construction...",
        measure_type="bond",
        # semantic match score: 0.89
    ),
    BallotMeasure(
        id="marin-measure-b-2026",
        title="Measure B - Marin Housing Trust Fund",
        description="1/4 cent sales tax for affordable housing preservation...",
        measure_type="tax",
        # semantic match score: 0.82
    ),
]

# ========================================
# 4. Polling location
# ========================================

>>> c.get_polling_location("1234 Fourth St, San Rafael, CA 94901")
PollingLocation(
    id="poll-san-rafael-1",
    name="San Rafael Community Center",
    address="618 B St",
    city="San Rafael",
    state="CA",
    zip_code="94901",
    hours="7am - 8pm",
    is_early_voting=True,
)
```

### Voting Record Queries (The Closed Loop)

```python
# ========================================
# 5. Get incumbent's voting record
# ========================================

>>> record = c.get_voting_record("Jane Smith", topic="housing")
>>> record
VotingRecord(
    official_id="city-san-rafael-council-d1",
    official_name="Jane Smith",
    topic="housing",
    total_votes=15,
    yes_votes=12,
    no_votes=2,
    abstain_votes=1,
    decisions=[...],
)

>>> print(f"{record.official_name} voted YES on {record.yes_percentage:.0f}% of housing items")
Jane Smith voted YES on 80% of housing items

# See specific votes
>>> for d in record.decisions[:3]:
...     print(f"{d['date']}: {d['title']} - {d['vote'].upper()}")
...
2025-11-04: Shelter Expansion Project - YES
2025-09-16: Inclusionary Housing Ordinance Update - YES
2025-06-02: ADU Permit Streamlining - NO

# ========================================
# 6. Compare candidates on an issue
# ========================================

>>> council_race = c.get_contest("city-council-d1-2026")
>>> for candidate in council_race.candidates:
...     if candidate.incumbent:
...         record = c.get_voting_record(candidate.name, topic="housing")
...         print(f"{candidate.name} (incumbent): {record.yes_percentage:.0f}% YES on housing")
...     else:
...         print(f"{candidate.name}: No voting record (challenger)")
...
Jane Smith (incumbent): 80% YES on housing
Bob Jones: No voting record (challenger)

# ========================================
# 7. The full "closed loop" user journey
# ========================================

# User queries housing topic

# whats_next shows upcoming housing-related items AND election info
>>> events = c.whats_next(topics=["housing"], days=90, include_elections=True)
>>> for e in events:
...     print(f"{e.date.strftime('%Y-%m-%d')}: {e.title}")
...
2026-01-21: City Council Meeting (Housing Element Update on agenda)
2026-05-18: Voter Registration Deadline: June 2026 Primary
2026-06-02: California Primary Election (Prop 1 - Housing Bond on ballot)

# User clicks through to see incumbent's housing record
>>> incumbent_record = c.get_voting_record("Jane Smith", topic="housing")
>>> print(f"Incumbent voted YES on {incumbent_record.yes_percentage:.0f}% of housing items")
```

---

## 5. Extend StorageBackend Protocol

**File:** `packages/civicos/src/civicos/storage/backend.py`

Add after `get_transcript_count` method (line ~727):

```python
    # ========== Election Methods ==========

    def store_elections(
        self,
        jurisdiction_id: str,
        elections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store elections with temporal versioning."""
        ...

    def get_elections(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        include_past: bool = False,
        election_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve elections with optional filtering."""
        ...

    def get_election_count(self, jurisdiction_id: str) -> int:
        """Get count of current elections for a jurisdiction."""
        ...

    # ========== Elected Officials Methods ==========

    def store_elected_officials(
        self,
        jurisdiction_id: str,
        officials: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store elected officials with temporal versioning."""
        ...

    def get_elected_officials(
        self,
        jurisdiction_id: str,
        current_only: bool = True,
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve elected officials."""
        ...

    def get_official_by_name(
        self,
        jurisdiction_id: str,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """Find official by name (fuzzy match on name_variations)."""
        ...
```

---

## 6. Database Schema

```sql
-- Elections
CREATE TABLE IF NOT EXISTS elections (
    id TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL,
    name TEXT NOT NULL,
    election_date TEXT NOT NULL,
    election_type TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    raw_data TEXT,
    valid_from TEXT NOT NULL DEFAULT (datetime('now')),
    valid_to TEXT
);

-- Election deadlines
CREATE TABLE IF NOT EXISTS election_deadlines (
    id TEXT PRIMARY KEY,
    election_id TEXT NOT NULL REFERENCES elections(id),
    deadline_type TEXT NOT NULL,
    deadline_date TEXT NOT NULL,
    description TEXT,
    valid_from TEXT NOT NULL DEFAULT (datetime('now')),
    valid_to TEXT
);

-- Election contests
CREATE TABLE IF NOT EXISTS election_contests (
    id TEXT PRIMARY KEY,
    election_id TEXT NOT NULL REFERENCES elections(id),
    title TEXT NOT NULL,
    contest_type TEXT NOT NULL,
    district_name TEXT,
    raw_data TEXT,
    valid_from TEXT NOT NULL DEFAULT (datetime('now')),
    valid_to TEXT
);

-- Elected officials (links elections to decisions)
CREATE TABLE IF NOT EXISTS elected_officials (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    seat TEXT NOT NULL,
    jurisdiction_id TEXT NOT NULL,
    term_start TEXT NOT NULL,
    term_end TEXT,
    name_variations TEXT,  -- JSON array for fuzzy matching
    candidate_id TEXT,     -- Link to election candidate
    valid_from TEXT NOT NULL DEFAULT (datetime('now')),
    valid_to TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_elections_jurisdiction ON elections(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_elections_date ON elections(election_date);
CREATE INDEX IF NOT EXISTS idx_officials_jurisdiction ON elected_officials(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_officials_current ON elected_officials(term_end) WHERE term_end IS NULL;
```

---

## 7. Implementation Phases

### Phase 1: Foundation
1. Create `packages/civicos/src/civicos/_internal/elections/__init__.py` with data models
2. Add `ELECTIONS` to `CorpusType` in `corpus_types.py` (with `jurisdiction_type="both"`)
3. Add election methods to `StorageBackend` protocol
4. Implement SQLite storage

### Phase 2: Google Civic API Client
1. Create `packages/civicos-extraction/src/civic_extraction/clients/google_civic.py`
2. Add tests
3. Test with real API key against San Rafael address

### Phase 3: Elected Officials Linkage
1. Add `ElectedOfficial` model and storage
2. Sync officials from Google Civic API `representatives` endpoint
3. Extract roll call votes from meeting minutes
4. Populate `vote_results` field in decisions

### Phase 4: Civic API Integration
1. Extend `whats_next()` with `include_elections` parameter
2. Add `whats_on_ballot()`, `get_polling_location()`
3. Add `get_voting_record()` method
4. Integration tests

### Phase 5: Marin County Registrar (optional)
1. Web scraping for local measures and deadlines
2. Source fusion logic

---

## Key Files Summary

| File | Change |
|------|--------|
| `packages/civicos/src/civicos/storage/corpus_types.py` | Add `ELECTIONS` enum (jurisdiction_type="both") |
| `packages/civicos/src/civicos/storage/backend.py` | Add election + official storage methods |
| `packages/civicos/src/civicos/storage/sqlite_backend.py` | Implement election + official storage |
| `packages/civicos/src/civicos/_internal/elections/__init__.py` | NEW: Election + ElectedOfficial models |
| `packages/civicos-extraction/src/civic_extraction/clients/google_civic.py` | NEW: Google Civic API client |
| `packages/civicos/src/civicos/civic.py` | Add `whats_on_ballot()`, `get_voting_record()` |

---

## Cost Analysis

| Resource | Monthly Cost |
|----------|-------------|
| Google Civic API | $0 (free tier: 25k/day) |
| Web scraping | $0 |
| Storage | Included in existing Supabase |
| **Total** | **$0** |

---

## Prerequisites

Before implementing election integration:

1. **Roll call extraction** - Decision extraction must populate `vote_results` field
2. **Current officials known** - Need to seed `elected_officials` table from Google Civic API
3. **Name matching** - Need fuzzy matching between "Councilmember Smith" and "Jane Smith"

Currently `vote_results` is empty in all decisions. This needs to be addressed by:
- Re-running decision extraction with roll call parsing
- Or adding roll call extraction as a separate enrichment step
