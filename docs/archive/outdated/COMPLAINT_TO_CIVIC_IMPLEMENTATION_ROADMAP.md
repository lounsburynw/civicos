# Complaint-to-Civic Implementation Roadmap
## Optimized for Claude Code Context Management

**Version**: 1.0
**Date**: 2025-10-12
**Purpose**: Sequential implementation guide organized by abstraction degree

---

## Roadmap Philosophy

**Abstraction-First Architecture**: Build from schema → storage → logic → API → UI

**Why This Order**:
1. **Schema changes are expensive** - get data model right first
2. **Storage patterns constrain logic** - define persistence before algorithms
3. **API contracts enable parallel work** - backend/frontend can diverge once API stable
4. **UI is most volatile** - defer to last, iterate rapidly

**Context Management Strategy**:
- Each layer has **minimal context requirements** from previous layers
- Claude Code can implement each layer in **separate focused sessions**
- **Validation gates** between layers prevent cascading failures
- **Rollback points** at each layer boundary

---

## Layer 1: Schema & Data Model (Most Abstract)
### Estimated Time: 1-2 hours | Context: Schema files only

### 1.1 Extend civic-app-schema.json

**File**: `civic-app-schema.json`

**Changes Required**:

```json
{
  "definitions": {
    "Complaint": {
      "type": "object",
      "description": "User-generated civic concern (ephemeral focal point)",
      "required": ["id", "user_id", "description", "jurisdiction_id", "created_at", "status"],
      "properties": {
        "id": {"type": "string", "format": "uuid"},
        "user_id": {"type": "string"},
        "description": {"type": "string", "maxLength": 2000},
        "issue_type": {
          "type": "string",
          "enum": ["housing", "transportation", "environment", "public_safety", "infrastructure", "other"]
        },
        "jurisdiction_id": {"type": "string"},
        "location": {
          "type": "object",
          "properties": {
            "address": {"type": "string"},
            "latitude": {"type": "number"},
            "longitude": {"type": "number"}
          }
        },
        "created_at": {"type": "string", "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
        "status": {
          "type": "string",
          "enum": ["open", "matched", "community_formed", "escalated", "resolved"],
          "description": "Lifecycle status (RAM → disk transition)"
        },
        "matched_events": {
          "type": "array",
          "items": {"$ref": "#/definitions/EventReference"},
          "description": "Links to CivicEvent focal points (disk)"
        },
        "related_complaints": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Similar complaints from neighbors (clustering)"
        },
        "discussion_group_id": {
          "type": "string",
          "description": "External messaging group (Slack/Discord)"
        },
        "ai_analysis": {
          "type": "object",
          "description": "Reserved for Phase 2+ AI features (null for Phase 1)",
          "properties": {
            "match_confidence": {"type": "number"},
            "suggested_actions": {"type": "array", "items": {"type": "string"}},
            "escalation_probability": {"type": "number"}
          }
        }
      }
    },
    "EventReference": {
      "type": "object",
      "description": "Lightweight pointer to CivicEvent (avoid duplication)",
      "required": ["event_id", "match_score"],
      "properties": {
        "event_id": {"type": "string"},
        "match_score": {"type": "number", "minimum": 0, "maximum": 100},
        "match_reason": {"type": "string"}
      }
    },
    "ProposedAgendaItem": {
      "type": "object",
      "description": "Community proposal for official agenda (escalation path)",
      "required": ["id", "title", "description", "supporting_users", "target_event"],
      "properties": {
        "id": {"type": "string", "format": "uuid"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "source_complaints": {
          "type": "array",
          "items": {"type": "string"},
          "description": "Complaints that led to this proposal"
        },
        "supporting_users": {
          "type": "array",
          "items": {"type": "string"}
        },
        "target_event": {"type": "string", "description": "Which meeting to submit to"},
        "status": {
          "type": "string",
          "enum": ["draft", "submitted", "accepted", "rejected"]
        }
      }
    },
    "DiscussionGroup": {
      "type": "object",
      "description": "External messaging group around focal point",
      "required": ["id", "platform", "focal_point_type", "focal_point_id"],
      "properties": {
        "id": {"type": "string"},
        "platform": {"type": "string", "enum": ["slack", "discord", "signal"]},
        "platform_url": {"type": "string", "format": "uri"},
        "focal_point_type": {
          "type": "string",
          "enum": ["CivicEvent", "Complaint", "ProposedAgendaItem"]
        },
        "focal_point_id": {"type": "string"},
        "member_count": {"type": "integer"},
        "created_at": {"type": "string", "format": "date-time"}
      }
    }
  }
}
```

**Validation Criteria**:
- [ ] Schema validates with JSON Schema validator
- [ ] All enum values documented
- [ ] Relationships clearly typed (EventReference not full CivicEvent)
- [ ] Reserved fields present but nullable (`ai_analysis`)

**Claude Code Session Requirements**:
- Context: `civic-app-schema.json` only
- Tools: Read, Edit
- Validation: `python -m json.tool civic-app-schema.json`

---

### 1.2 Define ParticipationMechanism Interface

**File**: New file `src/interfaces/participation_mechanism.py`

**Purpose**: Unified interface for any focal point that enables civic action

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime

class ParticipationMechanism(ABC):
    """
    Abstract interface for any civic focal point.

    Enables unified handling of CivicEvent, Complaint, ProposedAgendaItem
    without tight coupling.
    """

    @abstractmethod
    def get_id(self) -> str:
        """Unique identifier for this focal point"""
        pass

    @abstractmethod
    def get_type(self) -> str:
        """Focal point type: 'CivicEvent' | 'Complaint' | 'ProposedAgendaItem'"""
        pass

    @abstractmethod
    def get_actions(self) -> List[Dict]:
        """
        Available actions for this focal point.

        Returns:
            List of action dictionaries matching MessageAction schema:
            {
                "action_type": "email" | "calendar" | "link" | "complaint_submit",
                "action_label": "Email Council",
                "action_target": "mailto:council@city.gov",
                ...
            }
        """
        pass

    @abstractmethod
    def get_context(self) -> Dict:
        """
        Multi-dimensional context for engagement decision.

        Returns:
            {
                "legislative_context": {...},     # State bills, federal programs
                "financial_context": {...},       # CDBG allocations, budgets
                "community_context": {            # NEW for complaints
                    "neighbor_count": 15,
                    "organizing_status": "active"
                },
                "temporal_context": {
                    "urgency": "high" | "medium" | "low",
                    "time_until_event": 604800  # seconds
                }
            }
        """
        pass

    @abstractmethod
    def get_lifecycle_status(self) -> str:
        """
        Lifecycle stage for this focal point.

        CivicEvent: 'scheduled' | 'in_progress' | 'completed'
        Complaint: 'open' | 'matched' | 'community_formed' | 'escalated' | 'resolved'
        ProposedAgendaItem: 'draft' | 'submitted' | 'accepted' | 'rejected'
        """
        pass

    def is_government_generated(self) -> bool:
        """True if immutable government data (disk), False if user-generated (RAM)"""
        return self.get_type() in ['CivicEvent', 'ElectedOfficial', 'BallotMeasure']

    def get_participation_threshold(self) -> str:
        """Required civic literacy level: 'low' | 'medium' | 'high'"""
        # Default: government focal points require higher literacy
        return 'high' if self.is_government_generated() else 'low'
```

**Validation Criteria**:
- [ ] ABC properly defined with abstractmethod decorators
- [ ] Type hints complete
- [ ] Docstrings describe return schema
- [ ] Helper methods documented

**Claude Code Session Requirements**:
- Context: `civic-app-schema.json` (for action types)
- Tools: Write (new file)
- Validation: `python -m py_compile src/interfaces/participation_mechanism.py`

---

## Layer 2: Storage & Persistence (Abstract)
### Estimated Time: 2-3 hours | Context: Schema + DB schema

### 2.1 Extend SQLite Schema

**File**: Migration script `migrations/002_add_complaints.sql`

```sql
-- Complaints table (ephemeral user-generated focal points)
CREATE TABLE IF NOT EXISTS complaints (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    description TEXT NOT NULL CHECK(length(description) <= 2000),
    issue_type TEXT CHECK(issue_type IN (
        'housing', 'transportation', 'environment',
        'public_safety', 'infrastructure', 'other'
    )),
    jurisdiction_id TEXT NOT NULL,

    -- Location
    address TEXT,
    latitude REAL,
    longitude REAL,

    -- Lifecycle
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN (
        'open', 'matched', 'community_formed', 'escalated', 'resolved'
    )),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Reserved for Phase 2+
    ai_analysis TEXT,  -- JSON blob

    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id)
);

-- Junction table: complaints to events (many-to-many)
CREATE TABLE IF NOT EXISTS complaints_to_events (
    complaint_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    match_score REAL NOT NULL CHECK(match_score >= 0 AND match_score <= 100),
    match_reason TEXT,
    matched_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (complaint_id, event_id),
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- Junction table: users to complaints (many-to-many for clustering)
CREATE TABLE IF NOT EXISTS users_to_complaints (
    user_id TEXT NOT NULL,
    complaint_id TEXT NOT NULL,
    relationship_type TEXT CHECK(relationship_type IN (
        'author', 'supporter', 'mentioned'
    )),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id, complaint_id),
    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id),
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- Discussion groups (external messaging integration)
CREATE TABLE IF NOT EXISTS discussion_groups (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL CHECK(platform IN ('slack', 'discord', 'signal')),
    platform_url TEXT,
    focal_point_type TEXT NOT NULL CHECK(focal_point_type IN (
        'CivicEvent', 'Complaint', 'ProposedAgendaItem'
    )),
    focal_point_id TEXT NOT NULL,
    member_count INTEGER DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Proposed agenda items (escalation path)
CREATE TABLE IF NOT EXISTS proposed_agenda_items (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    target_event_id TEXT,  -- Which meeting to submit to
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN (
        'draft', 'submitted', 'accepted', 'rejected'
    )),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Junction: proposals to complaints (what led to this proposal)
CREATE TABLE IF NOT EXISTS proposals_to_complaints (
    proposal_id TEXT NOT NULL,
    complaint_id TEXT NOT NULL,

    PRIMARY KEY (proposal_id, complaint_id),
    FOREIGN KEY (proposal_id) REFERENCES proposed_agenda_items(id) ON DELETE CASCADE,
    FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
);

-- Junction: users to proposals (who supports this)
CREATE TABLE IF NOT EXISTS users_to_proposals (
    user_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    role TEXT CHECK(role IN ('author', 'supporter', 'editor')),
    joined_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id, proposal_id),
    FOREIGN KEY (user_id) REFERENCES user_profiles(user_id),
    FOREIGN KEY (proposal_id) REFERENCES proposed_agenda_items(id) ON DELETE CASCADE
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_complaints_jurisdiction ON complaints(jurisdiction_id);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);
CREATE INDEX IF NOT EXISTS idx_complaints_created ON complaints(created_at);
CREATE INDEX IF NOT EXISTS idx_complaints_issue_type ON complaints(issue_type);
CREATE INDEX IF NOT EXISTS idx_complaints_location ON complaints(latitude, longitude);

CREATE INDEX IF NOT EXISTS idx_complaints_to_events_complaint ON complaints_to_events(complaint_id);
CREATE INDEX IF NOT EXISTS idx_complaints_to_events_event ON complaints_to_events(event_id);

CREATE INDEX IF NOT EXISTS idx_discussion_groups_focal ON discussion_groups(focal_point_type, focal_point_id);
```

**Validation Criteria**:
- [ ] All tables have PRIMARY KEYs
- [ ] Foreign keys properly defined with ON DELETE CASCADE
- [ ] CHECK constraints match schema enums
- [ ] Indexes cover common query patterns
- [ ] Junction tables for many-to-many relationships

**Claude Code Session Requirements**:
- Context: `civic-app-schema.json`, existing `civic_participation.db` schema
- Tools: Write (new migration), Bash (test migration)
- Validation: `sqlite3 data/civic_participation.db < migrations/002_add_complaints.sql`

---

### 2.2 Implement Complaint Storage Interface

**File**: New file `src/complaint_storage.py`

**Purpose**: CRUD operations for complaints with ParticipationMechanism interface

```python
"""
Complaint storage and retrieval with SQLite.

Phase 1: Basic CRUD + event matching
Phase 2: Clustering queries + community formation
"""

import sqlite3
import json
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

from src.interfaces.participation_mechanism import ParticipationMechanism

DB_PATH = Path("data/civic_participation.db")

class ComplaintStorage:
    """CRUD interface for complaints"""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def create_complaint(
        self,
        user_id: str,
        description: str,
        jurisdiction_id: str,
        issue_type: Optional[str] = None,
        location: Optional[Dict] = None
    ) -> str:
        """
        Create new complaint.

        Args:
            user_id: User filing complaint
            description: Complaint text (max 2000 chars)
            jurisdiction_id: City/county identifier
            issue_type: Category (housing, transportation, etc.)
            location: {"address": str, "latitude": float, "longitude": float}

        Returns:
            complaint_id (uuid)
        """
        import uuid
        complaint_id = str(uuid.uuid4())

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO complaints (
                    id, user_id, description, jurisdiction_id, issue_type,
                    address, latitude, longitude, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                complaint_id,
                user_id,
                description[:2000],  # Enforce limit
                jurisdiction_id,
                issue_type,
                location.get("address") if location else None,
                location.get("latitude") if location else None,
                location.get("longitude") if location else None
            ))

            # Track as civic action
            cursor.execute("""
                INSERT INTO civic_actions (
                    id, user_id, event_type, opportunity_id, jurisdiction_id,
                    timestamp, completion_status, metadata
                ) VALUES (?, ?, 'complaint_submit', ?, ?, CURRENT_TIMESTAMP, 'completed', ?)
            """, (
                str(uuid.uuid4()),
                user_id,
                complaint_id,
                jurisdiction_id,
                json.dumps({"issue_type": issue_type})
            ))

            conn.commit()

        return complaint_id

    def get_complaint(self, complaint_id: str) -> Optional[Dict]:
        """Retrieve complaint by ID"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,))
            row = cursor.fetchone()

            if not row:
                return None

            complaint = dict(row)

            # Load matched events
            cursor.execute("""
                SELECT event_id, match_score, match_reason
                FROM complaints_to_events
                WHERE complaint_id = ?
                ORDER BY match_score DESC
            """, (complaint_id,))
            complaint["matched_events"] = [
                {
                    "event_id": r[0],
                    "match_score": r[1],
                    "match_reason": r[2]
                }
                for r in cursor.fetchall()
            ]

            return complaint

    def link_to_event(
        self,
        complaint_id: str,
        event_id: str,
        match_score: float,
        match_reason: str
    ) -> None:
        """Link complaint to matched event"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO complaints_to_events
                (complaint_id, event_id, match_score, match_reason)
                VALUES (?, ?, ?, ?)
            """, (complaint_id, event_id, match_score, match_reason))

            # Update complaint status
            cursor.execute("""
                UPDATE complaints
                SET status = 'matched', updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'open'
            """, (complaint_id,))

            conn.commit()

    def find_similar_complaints(
        self,
        jurisdiction_id: str,
        issue_type: str,
        location: Optional[Dict] = None,
        radius_km: float = 5.0
    ) -> List[Dict]:
        """
        Find similar complaints for clustering.

        Phase 1: Basic issue_type + jurisdiction matching
        Phase 2: Add geographic clustering with Haversine distance
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Phase 1: Simple query
            cursor.execute("""
                SELECT * FROM complaints
                WHERE jurisdiction_id = ?
                  AND issue_type = ?
                  AND status IN ('open', 'matched')
                  AND created_at >= datetime('now', '-30 days')
                ORDER BY created_at DESC
                LIMIT 20
            """, (jurisdiction_id, issue_type))

            return [dict(row) for row in cursor.fetchall()]

    def update_status(self, complaint_id: str, new_status: str) -> None:
        """Update complaint lifecycle status"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE complaints
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (new_status, complaint_id))
            conn.commit()


class Complaint(ParticipationMechanism):
    """
    Complaint focal point implementing ParticipationMechanism interface.

    Enables unified handling alongside CivicEvent.
    """

    def __init__(self, complaint_data: Dict):
        self.data = complaint_data
        self.storage = ComplaintStorage()

    def get_id(self) -> str:
        return self.data["id"]

    def get_type(self) -> str:
        return "Complaint"

    def get_actions(self) -> List[Dict]:
        """
        Actions available for complaint.

        Phase 1: View matched events
        Phase 2: Join discussion, escalate to proposal
        """
        actions = []

        # If matched to events, show "View Meeting" actions
        for event_ref in self.data.get("matched_events", []):
            actions.append({
                "action_type": "link",
                "action_label": f"View Meeting (Match: {event_ref['match_score']:.0f}%)",
                "action_target": f"/events/{event_ref['event_id']}",
                "mcp_tool": "view_event_details"
            })

        # If no matches, show "Track Issue" action
        if not self.data.get("matched_events"):
            actions.append({
                "action_type": "button",
                "action_label": "Track This Issue",
                "action_target": "track_complaint",
                "mcp_tool": "track_issue"
            })

        return actions

    def get_context(self) -> Dict:
        """Multi-dimensional context for complaint"""
        return {
            "complaint_context": {
                "issue_type": self.data.get("issue_type"),
                "status": self.data.get("status"),
                "days_open": (
                    datetime.now() - datetime.fromisoformat(self.data["created_at"])
                ).days
            },
            "community_context": {
                "related_complaints": len(self.data.get("related_complaints", [])),
                "organizing_potential": "high" if len(self.data.get("related_complaints", [])) >= 3 else "low"
            },
            "matched_events_count": len(self.data.get("matched_events", []))
        }

    def get_lifecycle_status(self) -> str:
        return self.data.get("status", "open")

    def get_participation_threshold(self) -> str:
        # Complaints are low-barrier entry point
        return "low"
```

**Validation Criteria**:
- [ ] All CRUD operations tested
- [ ] ParticipationMechanism interface fully implemented
- [ ] Foreign key relationships enforced
- [ ] JSON fields properly serialized/deserialized
- [ ] Civic actions tracking works

**Claude Code Session Requirements**:
- Context: `src/interfaces/participation_mechanism.py`, DB schema
- Tools: Write (new file), Bash (pytest)
- Validation: `python -m pytest tests/test_complaint_storage.py -v`

---

## Layer 3: Business Logic (Concrete)
### Estimated Time: 3-4 hours | Context: Schema + Storage + Legislative enrichment

### 3.1 Implement Complaint Matcher

**File**: New file `src/complaint_matcher.py`

**Purpose**: Match complaints to relevant civic events using keyword scoring

**Pattern**: Reuse `legislative_enrichment.py` algorithm (0.03ms, $0 cost)

```python
"""
Complaint-to-Event matching using keyword scoring.

Phase 1: Keyword matching only (reuse legislative_enrichment.py pattern)
Phase 2: Add semantic embeddings if match rate < 30%
Phase 3: Add LLM classification if needed
"""

import json
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta

# Topic-to-keyword mapping (similar to TOPIC_ENRICHMENT_POLICY)
ISSUE_TYPE_KEYWORDS = {
    "housing": {
        "keywords": [
            "housing", "rent", "affordable", "eviction", "zoning",
            "ADU", "duplex", "apartment", "development", "tenant",
            "landlord", "lease", "residential", "multi-family"
        ],
        "project_types": ["housing", "development"],
        "weight": 1.0
    },
    "transportation": {
        "keywords": [
            "transit", "bus", "bike", "pedestrian", "traffic",
            "road", "street", "highway", "parking", "crosswalk",
            "sidewalk", "BART", "train", "congestion"
        ],
        "project_types": ["transportation"],
        "weight": 1.0
    },
    "environment": {
        "keywords": [
            "climate", "pollution", "air quality", "water", "green",
            "park", "tree", "sustainability", "carbon", "emissions",
            "renewable", "solar", "wildlife", "conservation"
        ],
        "project_types": ["environment"],
        "weight": 1.0
    },
    "infrastructure": {
        "keywords": [
            "pothole", "repair", "maintenance", "street light",
            "water main", "sewer", "infrastructure", "public works",
            "road repair", "sidewalk repair", "utility"
        ],
        "project_types": ["public_works", "infrastructure"],
        "weight": 0.8  # Often operational, not policy
    },
    "public_safety": {
        "keywords": [
            "police", "fire", "emergency", "crime", "safety",
            "911", "security", "violence", "patrol", "response time"
        ],
        "project_types": ["public_safety"],
        "weight": 0.9
    }
}

class ComplaintMatcher:
    """Keyword-based matcher for complaints to events"""

    def __init__(self, events_cache_path: Path = Path("data/events")):
        self.events_cache_path = events_cache_path
        self._events_by_jurisdiction = {}
        self._load_events()

    def _load_events(self):
        """Load all events into memory (lazy loading)"""
        # Only load if not already cached
        if self._events_by_jurisdiction:
            return

        for event_file in self.events_cache_path.glob("events_*.json"):
            with open(event_file) as f:
                events = json.load(f)

                for event in events:
                    jid = event.get("jurisdiction_id")
                    if jid not in self._events_by_jurisdiction:
                        self._events_by_jurisdiction[jid] = []
                    self._events_by_jurisdiction[jid].append(event)

    def match_complaint_to_events(
        self,
        complaint: Dict,
        max_results: int = 3,
        min_score: float = 20.0,
        future_only: bool = True
    ) -> List[Tuple[Dict, float, str]]:
        """
        Match complaint to relevant civic events.

        Args:
            complaint: Complaint dict with description, issue_type, jurisdiction_id
            max_results: Return top N matches (default: 3)
            min_score: Minimum score threshold (default: 20.0)
            future_only: Only match future events (default: True)

        Returns:
            List of (event_dict, match_score, match_reason) tuples
        """
        jurisdiction_id = complaint.get("jurisdiction_id")
        issue_type = complaint.get("issue_type", "other")
        description = complaint.get("description", "").lower()

        # Get events for this jurisdiction
        events = self._events_by_jurisdiction.get(jurisdiction_id, [])
        if not events:
            return []

        # Score each event
        scored_events = []
        for event in events:
            # Skip past events if future_only
            if future_only:
                event_date = datetime.fromisoformat(event["start_time"].replace("Z", "+00:00"))
                if event_date < datetime.now(event_date.tzinfo):
                    continue

            score, reason = self._score_event(event, complaint, description, issue_type)

            if score >= min_score:
                scored_events.append((event, score, reason))

        # Sort by score descending, take top N
        scored_events.sort(key=lambda x: x[1], reverse=True)
        return scored_events[:max_results]

    def _score_event(
        self,
        event: Dict,
        complaint: Dict,
        description_lower: str,
        issue_type: str
    ) -> Tuple[float, str]:
        """
        Score event relevance to complaint.

        Scoring algorithm (adapted from legislative_enrichment.py):
        - Keyword match: 10 points per keyword
        - Project type match: 20 points
        - Temporal proximity: up to 15 points
        - Title/description relevance: 10 points
        """
        score = 0.0
        reasons = []

        # 1. Keyword matching (10 points per match)
        if issue_type in ISSUE_TYPE_KEYWORDS:
            keywords = ISSUE_TYPE_KEYWORDS[issue_type]["keywords"]

            # Check event title
            event_title = event.get("title", "").lower()
            keyword_matches = sum(1 for kw in keywords if kw in event_title or kw in description_lower)

            if keyword_matches > 0:
                score += keyword_matches * 10
                reasons.append(f"{keyword_matches} keyword matches")

        # 2. Project type matching (20 points)
        event_project_types = []
        for opp in event.get("participation_opportunities", []):
            event_project_types.extend(opp.get("project_types", []))

        if issue_type in ISSUE_TYPE_KEYWORDS:
            matching_types = set(event_project_types) & set(ISSUE_TYPE_KEYWORDS[issue_type]["project_types"])
            if matching_types:
                score += 20
                reasons.append(f"Project type match: {', '.join(matching_types)}")

        # 3. Temporal proximity (up to 15 points)
        event_date = datetime.fromisoformat(event["start_time"].replace("Z", "+00:00"))
        days_until = (event_date - datetime.now(event_date.tzinfo)).days

        if 0 <= days_until <= 7:
            score += 15  # Very soon
            reasons.append("Meeting within 7 days")
        elif 7 < days_until <= 30:
            score += 10  # Soon
            reasons.append("Meeting within 30 days")
        elif 30 < days_until <= 90:
            score += 5   # Future
            reasons.append("Meeting within 90 days")

        # 4. Title/description relevance (10 points)
        # Simple heuristic: if complaint description shares words with event title
        complaint_words = set(description_lower.split())
        event_words = set(event_title.split())
        shared_words = complaint_words & event_words

        if len(shared_words) >= 2:
            score += 10
            reasons.append(f"Shared terms: {', '.join(list(shared_words)[:3])}")

        match_reason = "; ".join(reasons) if reasons else "No strong match"
        return score, match_reason

    def get_match_statistics(self, jurisdiction_id: str) -> Dict:
        """Get matching statistics for debugging"""
        events = self._events_by_jurisdiction.get(jurisdiction_id, [])

        issue_type_coverage = {}
        for issue_type in ISSUE_TYPE_KEYWORDS:
            matching_events = 0
            for event in events:
                event_project_types = []
                for opp in event.get("participation_opportunities", []):
                    event_project_types.extend(opp.get("project_types", []))

                if any(pt in ISSUE_TYPE_KEYWORDS[issue_type]["project_types"] for pt in event_project_types):
                    matching_events += 1

            issue_type_coverage[issue_type] = {
                "matching_events": matching_events,
                "total_events": len(events),
                "coverage_rate": matching_events / len(events) if events else 0
            }

        return issue_type_coverage
```

**Validation Criteria**:
- [ ] Matches >30% of complaints in test set
- [ ] Latency <100ms per complaint
- [ ] Top match is correct >60% of time (manual review)
- [ ] Zero false positives (matched event must be relevant)

**Claude Code Session Requirements**:
- Context: `src/legislative_enrichment.py` (reference pattern), events JSON files
- Tools: Write (new file), Bash (pytest)
- Validation: `python -m pytest tests/test_complaint_matching.py -v`

---

### 3.2 Implement Fallback Strategies

**File**: New file `src/complaint_fallback.py`

**Purpose**: Handle complaints with no event matches (issue banking only for Phase 1)

```python
"""
Fallback strategies for complaints without civic event matches.

Phase 1: Issue banking (track for future matching)
Phase 2: Community clustering (find neighbors)
Phase 3: Municipal service routing (311 integration)
"""

from typing import Dict, List, Optional
from datetime import datetime
from src.complaint_storage import ComplaintStorage

class ComplaintFallback:
    """Handles unmatched complaints with fallback strategies"""

    def __init__(self):
        self.storage = ComplaintStorage()

    def handle_no_match(self, complaint: Dict) -> Dict:
        """
        Process complaint with no event matches.

        Phase 1: Issue banking only
        Returns fallback action recommendations
        """
        complaint_id = complaint["id"]

        # Strategy 1: Issue banking (always)
        self._bank_complaint(complaint)

        # Strategy 2: Check for similar complaints (Phase 1: simple query)
        similar = self.storage.find_similar_complaints(
            jurisdiction_id=complaint["jurisdiction_id"],
            issue_type=complaint["issue_type"]
        )

        # Build response
        response = {
            "strategy": "issue_banking",
            "message": self._generate_no_match_message(complaint, similar),
            "actions": [],
            "similar_complaints_count": len(similar)
        }

        # If 3+ similar complaints, suggest community formation
        if len(similar) >= 3:
            response["actions"].append({
                "action_type": "button",
                "action_label": f"Connect with {len(similar)} neighbors",
                "action_target": "view_similar_complaints",
                "mcp_tool": "view_neighbors"
            })
        else:
            response["actions"].append({
                "action_type": "button",
                "action_label": "Track this issue",
                "action_target": "track_complaint",
                "mcp_tool": "track_issue"
            })

        return response

    def _bank_complaint(self, complaint: Dict) -> None:
        """
        Bank complaint for future matching.

        When new events are added, re-run matcher on banked complaints.
        """
        # Update status to indicate it's banked
        self.storage.update_status(complaint["id"], "open")

        # Log as civic action
        import sqlite3, json, uuid
        with sqlite3.connect(self.storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO civic_actions (
                    id, user_id, event_type, opportunity_id, jurisdiction_id,
                    timestamp, completion_status, metadata
                ) VALUES (?, ?, 'complaint_banked', ?, ?, CURRENT_TIMESTAMP, 'completed', ?)
            """, (
                str(uuid.uuid4()),
                complaint["user_id"],
                complaint["id"],
                complaint["jurisdiction_id"],
                json.dumps({"issue_type": complaint.get("issue_type")})
            ))
            conn.commit()

    def _generate_no_match_message(self, complaint: Dict, similar: List[Dict]) -> str:
        """Generate user-facing message for no-match scenario"""
        issue_type = complaint.get("issue_type", "issue")

        if len(similar) >= 3:
            return (
                f"We're tracking your {issue_type} concern. "
                f"{len(similar)} neighbors have reported similar issues. "
                f"Consider connecting to coordinate on this together."
            )
        elif len(similar) > 0:
            return (
                f"We're tracking your {issue_type} concern. "
                f"{len(similar)} other neighbor(s) have reported similar issues. "
                f"We'll notify you when this comes up at a city meeting."
            )
        else:
            return (
                f"We're tracking your {issue_type} concern. "
                f"We'll notify you when this comes up at a city meeting or "
                f"if other neighbors report similar issues."
            )

    def check_banked_complaints_for_new_event(self, event: Dict) -> List[Dict]:
        """
        When new event is added, check if any banked complaints match.

        Called by automated_civic_refresh.py after event extraction.
        """
        from src.complaint_matcher import ComplaintMatcher

        matcher = ComplaintMatcher()
        jurisdiction_id = event.get("jurisdiction_id")

        # Get all open complaints for this jurisdiction
        import sqlite3
        with sqlite3.connect(self.storage.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM complaints
                WHERE jurisdiction_id = ?
                  AND status = 'open'
                  AND created_at >= datetime('now', '-90 days')
            """, (jurisdiction_id,))
            banked_complaints = [dict(row) for row in cursor.fetchall()]

        # Try matching each complaint
        newly_matched = []
        for complaint in banked_complaints:
            matches = matcher.match_complaint_to_events(complaint, max_results=1)
            if matches:
                event_match, score, reason = matches[0]
                if event_match["id"] == event["id"]:  # This new event matches!
                    self.storage.link_to_event(
                        complaint["id"],
                        event["id"],
                        score,
                        reason
                    )
                    newly_matched.append(complaint)

        return newly_matched
```

**Validation Criteria**:
- [ ] Issue banking records civic action
- [ ] Similar complaint query returns relevant results
- [ ] User messages are helpful and not robotic
- [ ] New event matching works on banked complaints

**Claude Code Session Requirements**:
- Context: `src/complaint_storage.py`, `src/complaint_matcher.py`
- Tools: Write (new file), Bash (pytest)
- Validation: `python tests/test_complaint_fallback.py -v`

---

## Layer 4: API Layer (Interface)
### Estimated Time: 2-3 hours | Context: Business logic + existing API

### 4.1 Add Complaint Endpoints to API

**File**: Extend `src/civic_api_integrated.py`

**Changes Required**:

```python
# Add to imports
from src.complaint_storage import ComplaintStorage, Complaint
from src.complaint_matcher import ComplaintMatcher
from src.complaint_fallback import ComplaintFallback

# Initialize services
complaint_storage = ComplaintStorage()
complaint_matcher = ComplaintMatcher()
complaint_fallback = ComplaintFallback()

# New endpoint: Submit complaint
@app.route('/api/complaints', methods=['POST'])
def submit_complaint():
    """
    Submit new complaint and get matched events.

    Request body:
    {
        "user_id": "uuid",
        "description": "Pothole on Main St",
        "jurisdiction_id": "city-berkeley",
        "issue_type": "infrastructure",
        "location": {
            "address": "Main St & Elm Ave",
            "latitude": 37.8715,
            "longitude": -122.2727
        }
    }

    Response:
    {
        "complaint_id": "uuid",
        "status": "matched" | "banked",
        "matched_events": [...],  // If matches found
        "fallback": {...},        // If no matches
        "similar_complaints": 5
    }
    """
    try:
        data = request.get_json()

        # Validate required fields
        required = ["user_id", "description", "jurisdiction_id"]
        if not all(field in data for field in required):
            return jsonify({"error": "Missing required fields"}), 400

        # Create complaint
        complaint_id = complaint_storage.create_complaint(
            user_id=data["user_id"],
            description=data["description"],
            jurisdiction_id=data["jurisdiction_id"],
            issue_type=data.get("issue_type"),
            location=data.get("location")
        )

        # Get complaint for matching
        complaint = complaint_storage.get_complaint(complaint_id)

        # Try to match to events
        matches = complaint_matcher.match_complaint_to_events(complaint)

        if matches:
            # Link to events
            for event, score, reason in matches:
                complaint_storage.link_to_event(
                    complaint_id,
                    event["id"],
                    score,
                    reason
                )

            # Reload complaint with matches
            complaint = complaint_storage.get_complaint(complaint_id)

            # Hydrate matched events with full context
            hydrated_events = []
            for event_ref in complaint["matched_events"]:
                event = get_event_by_id(event_ref["event_id"])  # Existing function
                if event:
                    hydrated_events.append({
                        **event,
                        "match_score": event_ref["match_score"],
                        "match_reason": event_ref["match_reason"]
                    })

            return jsonify({
                "complaint_id": complaint_id,
                "status": "matched",
                "matched_events": hydrated_events,
                "similar_complaints": len(complaint.get("related_complaints", []))
            }), 201

        else:
            # No matches - apply fallback
            fallback_response = complaint_fallback.handle_no_match(complaint)

            return jsonify({
                "complaint_id": complaint_id,
                "status": "banked",
                "fallback": fallback_response,
                "similar_complaints": fallback_response["similar_complaints_count"]
            }), 201

    except Exception as e:
        logger.error(f"Error submitting complaint: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/complaints/<complaint_id>', methods=['GET'])
def get_complaint_details(complaint_id: str):
    """Get complaint with matched events and context"""
    try:
        complaint = complaint_storage.get_complaint(complaint_id)
        if not complaint:
            return jsonify({"error": "Complaint not found"}), 404

        # Wrap in ParticipationMechanism interface
        complaint_obj = Complaint(complaint)

        # Hydrate matched events
        hydrated_events = []
        for event_ref in complaint.get("matched_events", []):
            event = get_event_by_id(event_ref["event_id"])
            if event:
                hydrated_events.append({
                    **event,
                    "match_score": event_ref["match_score"],
                    "match_reason": event_ref["match_reason"]
                })

        return jsonify({
            "complaint": complaint,
            "matched_events": hydrated_events,
            "actions": complaint_obj.get_actions(),
            "context": complaint_obj.get_context()
        }), 200

    except Exception as e:
        logger.error(f"Error fetching complaint: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/complaints/similar', methods=['POST'])
def find_similar_complaints():
    """Find similar complaints for clustering"""
    try:
        data = request.get_json()

        similar = complaint_storage.find_similar_complaints(
            jurisdiction_id=data["jurisdiction_id"],
            issue_type=data["issue_type"],
            location=data.get("location")
        )

        return jsonify({"similar_complaints": similar}), 200

    except Exception as e:
        logger.error(f"Error finding similar complaints: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/matching/statistics', methods=['GET'])
def get_matching_statistics():
    """Get matching statistics for jurisdiction (debugging)"""
    try:
        jurisdiction_id = request.args.get("jurisdiction_id")
        if not jurisdiction_id:
            return jsonify({"error": "jurisdiction_id required"}), 400

        stats = complaint_matcher.get_match_statistics(jurisdiction_id)
        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        return jsonify({"error": str(e)}), 500
```

**Validation Criteria**:
- [ ] All endpoints return proper status codes
- [ ] Error handling comprehensive
- [ ] Request validation prevents bad data
- [ ] Response schema matches documentation
- [ ] Logging captures important events

**Claude Code Session Requirements**:
- Context: `src/civic_api_integrated.py`, business logic modules
- Tools: Read, Edit, Bash (test with curl)
- Validation: `curl -X POST http://localhost:8080/api/complaints -d '{"user_id": "test", ...}'`

---

## Layer 5: Frontend Integration (Concrete)
### Estimated Time: 3-4 hours | Context: API + existing conversational UI

### 5.1 Add Complaint Detection to Conversational UI

**File**: Extend `frontend/mcp-civic-server/civic-conversational-OS.html`

**Changes Required**:

```javascript
// Add complaint detection to message handler
async function handleUserMessage(message) {
    // Existing: Detect jurisdiction, handle queries

    // NEW: Detect complaint patterns
    const complaintPatterns = [
        /there('s| is) (a |an )?(\w+\s)*(pothole|broken|problem|issue)/i,
        /report (a |an )?(\w+\s)*(problem|issue)/i,
        /fix (the )?(\w+\s)*/i,
        /complaint about/i,
        /(noise|trash|parking|sidewalk|street|road) (problem|issue)/i
    ];

    const isComplaint = complaintPatterns.some(pattern => pattern.test(message));

    if (isComplaint && currentJurisdiction) {
        // Ask if user wants to file complaint
        addAssistantMessage(
            "It sounds like you're reporting an issue. Would you like me to:\n" +
            "1. File this as a civic complaint and find relevant meetings\n" +
            "2. Just search for related civic events\n" +
            "3. Continue our conversation",
            [
                {
                    action_type: "button",
                    action_label: "File Complaint",
                    action_target: "file_complaint",
                    mcp_tool: "submit_complaint"
                },
                {
                    action_type: "button",
                    action_label: "Search Events Only",
                    action_target: "search_events",
                    mcp_tool: "search_events"
                }
            ]
        );

        // Store message for complaint submission
        pendingComplaint = {
            description: message,
            jurisdiction_id: currentJurisdiction,
            user_id: currentUser?.id
        };

        return;
    }

    // Existing: Handle other message types
    // ...
}

// NEW: Handle complaint submission
async function submitComplaint(complaintData) {
    try {
        showLoadingIndicator("Analyzing your complaint and finding relevant meetings...");

        const response = await fetch(`${API_BASE_URL}/api/complaints`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${getApiKey()}`
            },
            body: JSON.stringify(complaintData)
        });

        const data = await response.json();

        hideLoadingIndicator();

        if (data.status === 'matched') {
            // Show matched events
            const eventsList = data.matched_events
                .map((e, i) => `${i+1}. **${e.title}** (${new Date(e.start_time).toLocaleDateString()}) - Match: ${e.match_score.toFixed(0)}%`)
                .join('\n');

            addAssistantMessage(
                `I found ${data.matched_events.length} relevant civic meeting(s) for your complaint:\n\n` +
                eventsList +
                `\n\nYou can participate in these meetings to address your concern.`
            );

            // Render event cards
            data.matched_events.forEach(event => {
                renderEventCard(event);
            });

        } else if (data.status === 'banked') {
            // Show fallback response
            addAssistantMessage(
                data.fallback.message + '\n\n' +
                (data.similar_complaints > 0
                    ? `${data.similar_complaints} neighbors have reported similar issues.`
                    : 'You\'re the first to report this issue.')
            );

            // Render fallback actions
            data.fallback.actions.forEach(action => {
                addActionButton(action);
            });
        }

        // Track as civic action
        trackCivicAction('complaint_submit', data.complaint_id);

    } catch (error) {
        console.error('Error submitting complaint:', error);
        addAssistantMessage(
            'Sorry, there was an error submitting your complaint. Please try again.',
            'error'
        );
    }
}

// NEW: Render event card with match score
function renderEventCard(event, matchScore = null) {
    const card = document.createElement('div');
    card.className = 'event-card';

    // Existing event card rendering...

    // NEW: Add match indicator if present
    if (matchScore) {
        const matchBadge = document.createElement('span');
        matchBadge.className = 'match-badge';
        matchBadge.textContent = `${matchScore.toFixed(0)}% match`;
        card.querySelector('.event-header').appendChild(matchBadge);
    }

    return card;
}

// Button click handlers
document.addEventListener('click', (e) => {
    if (e.target.dataset.action === 'file_complaint') {
        if (pendingComplaint) {
            // Classify issue type (simple heuristic)
            const description = pendingComplaint.description.toLowerCase();
            let issue_type = 'other';

            if (/housing|rent|evict|zoning|apartment|tenant/.test(description)) {
                issue_type = 'housing';
            } else if (/road|pothole|street|sidewalk|traffic|parking/.test(description)) {
                issue_type = 'infrastructure';
            } else if (/transit|bus|bike|pedestrian/.test(description)) {
                issue_type = 'transportation';
            } else if (/noise|trash|crime|safety|police/.test(description)) {
                issue_type = 'public_safety';
            } else if (/park|tree|pollution|environment|climate/.test(description)) {
                issue_type = 'environment';
            }

            pendingComplaint.issue_type = issue_type;

            submitComplaint(pendingComplaint);
            pendingComplaint = null;
        }
    }
});
```

**CSS Additions**:

```css
/* Complaint-specific styling */
.match-badge {
    display: inline-block;
    padding: 4px 8px;
    background: #4a5568;
    color: white;
    border-radius: 4px;
    font-size: 0.85em;
    margin-left: 10px;
}

.complaint-card {
    border-left: 4px solid #f59e0b;
    background: #fffbeb;
}

.complaint-card .focal-point-type::before {
    content: "🗣️ ";
}

.banked-message {
    padding: 12px;
    background: #dbeafe;
    border-radius: 8px;
    margin: 10px 0;
}
```

**Validation Criteria**:
- [ ] Complaint detection works on test phrases
- [ ] User confirmation flow clear and non-intrusive
- [ ] Matched events render with match scores
- [ ] Fallback messages helpful and encouraging
- [ ] Loading states prevent duplicate submissions

**Claude Code Session Requirements**:
- Context: `civic-conversational-OS.html`, API endpoints
- Tools: Read, Edit, Bash (start dev server)
- Validation: Manual testing with browser

---

## Layer 6: Testing & Validation (Quality)
### Estimated Time: 2-3 hours | Context: All layers

### 6.1 Comprehensive Test Suite

**File**: New file `tests/test_complaint_to_civic_integration.py`

```python
"""
Integration tests for complaint-to-civic matching system.

Tests entire pipeline: submission → matching → storage → API → fallback
"""

import pytest
import json
from pathlib import Path
from datetime import datetime

from src.complaint_storage import ComplaintStorage, Complaint
from src.complaint_matcher import ComplaintMatcher
from src.complaint_fallback import ComplaintFallback

@pytest.fixture
def test_db(tmp_path):
    """Create temporary test database"""
    db_path = tmp_path / "test_civic.db"
    # Run migrations
    # ...
    return db_path

@pytest.fixture
def sample_events():
    """Load sample events for matching tests"""
    events = [
        {
            "id": "event-1",
            "title": "City Council - Budget Discussion",
            "jurisdiction_id": "city-berkeley",
            "start_time": "2025-10-20T19:00:00Z",
            "participation_opportunities": [
                {"project_types": ["budget", "housing"]}
            ]
        },
        {
            "id": "event-2",
            "title": "Planning Commission - Road Repairs",
            "jurisdiction_id": "city-berkeley",
            "start_time": "2025-10-15T18:30:00Z",
            "participation_opportunities": [
                {"project_types": ["transportation", "infrastructure"]}
            ]
        }
    ]
    return events

class TestComplaintMatching:
    """Test matching algorithm"""

    def test_housing_complaint_matches_budget_meeting(self, sample_events):
        matcher = ComplaintMatcher()
        matcher._events_by_jurisdiction = {"city-berkeley": sample_events}

        complaint = {
            "id": "complaint-1",
            "description": "Rent is too high, we need more affordable housing",
            "issue_type": "housing",
            "jurisdiction_id": "city-berkeley"
        }

        matches = matcher.match_complaint_to_events(complaint, max_results=1)

        assert len(matches) == 1
        assert matches[0][0]["id"] == "event-1"
        assert matches[0][1] >= 20  # Min score threshold

    def test_pothole_complaint_matches_road_repairs(self, sample_events):
        matcher = ComplaintMatcher()
        matcher._events_by_jurisdiction = {"city-berkeley": sample_events}

        complaint = {
            "id": "complaint-2",
            "description": "Big pothole on Main St needs repair",
            "issue_type": "infrastructure",
            "jurisdiction_id": "city-berkeley"
        }

        matches = matcher.match_complaint_to_events(complaint, max_results=1)

        assert len(matches) == 1
        assert matches[0][0]["id"] == "event-2"
        assert "keyword matches" in matches[0][2].lower()

    def test_no_matches_returns_empty(self, sample_events):
        matcher = ComplaintMatcher()
        matcher._events_by_jurisdiction = {"city-berkeley": sample_events}

        complaint = {
            "id": "complaint-3",
            "description": "Need more dog parks in the neighborhood",
            "issue_type": "environment",
            "jurisdiction_id": "city-berkeley"
        }

        matches = matcher.match_complaint_to_events(complaint, max_results=3)

        # Should either return no matches or very low scores
        assert len(matches) == 0 or matches[0][1] < 20

class TestComplaintStorage:
    """Test database operations"""

    def test_create_and_retrieve_complaint(self, test_db):
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="user-1",
            description="Test complaint",
            jurisdiction_id="city-berkeley",
            issue_type="housing"
        )

        complaint = storage.get_complaint(complaint_id)

        assert complaint is not None
        assert complaint["description"] == "Test complaint"
        assert complaint["status"] == "open"

    def test_link_to_event(self, test_db):
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="user-1",
            description="Test complaint",
            jurisdiction_id="city-berkeley"
        )

        storage.link_to_event(
            complaint_id=complaint_id,
            event_id="event-1",
            match_score=85.0,
            match_reason="Strong keyword match"
        )

        complaint = storage.get_complaint(complaint_id)

        assert complaint["status"] == "matched"
        assert len(complaint["matched_events"]) == 1
        assert complaint["matched_events"][0]["match_score"] == 85.0

class TestComplaintFallback:
    """Test fallback strategies"""

    def test_issue_banking_message(self, test_db):
        fallback = ComplaintFallback()
        fallback.storage = ComplaintStorage(db_path=test_db)

        complaint = {
            "id": "complaint-1",
            "user_id": "user-1",
            "description": "Noise complaint",
            "issue_type": "public_safety",
            "jurisdiction_id": "city-berkeley"
        }

        response = fallback.handle_no_match(complaint)

        assert response["strategy"] == "issue_banking"
        assert "tracking" in response["message"].lower()
        assert len(response["actions"]) > 0

class TestParticipationMechanismInterface:
    """Test unified interface"""

    def test_complaint_implements_interface(self, test_db):
        storage = ComplaintStorage(db_path=test_db)

        complaint_id = storage.create_complaint(
            user_id="user-1",
            description="Test complaint",
            jurisdiction_id="city-berkeley",
            issue_type="housing"
        )

        complaint_data = storage.get_complaint(complaint_id)
        complaint_obj = Complaint(complaint_data)

        # Test interface methods
        assert complaint_obj.get_id() == complaint_id
        assert complaint_obj.get_type() == "Complaint"
        assert isinstance(complaint_obj.get_actions(), list)
        assert isinstance(complaint_obj.get_context(), dict)
        assert complaint_obj.get_lifecycle_status() in ["open", "matched", "community_formed", "escalated", "resolved"]
        assert complaint_obj.is_government_generated() == False
        assert complaint_obj.get_participation_threshold() == "low"

class TestEndToEnd:
    """End-to-end integration tests"""

    def test_full_complaint_pipeline_with_match(self, test_db, sample_events):
        # Setup
        storage = ComplaintStorage(db_path=test_db)
        matcher = ComplaintMatcher()
        matcher._events_by_jurisdiction = {"city-berkeley": sample_events}

        # Step 1: Create complaint
        complaint_id = storage.create_complaint(
            user_id="user-1",
            description="Pothole on Main St needs fixing",
            jurisdiction_id="city-berkeley",
            issue_type="infrastructure"
        )

        # Step 2: Match to events
        complaint = storage.get_complaint(complaint_id)
        matches = matcher.match_complaint_to_events(complaint)

        assert len(matches) > 0

        # Step 3: Link to event
        for event, score, reason in matches:
            storage.link_to_event(complaint_id, event["id"], score, reason)

        # Step 4: Verify final state
        final_complaint = storage.get_complaint(complaint_id)

        assert final_complaint["status"] == "matched"
        assert len(final_complaint["matched_events"]) > 0

        # Step 5: Test ParticipationMechanism interface
        complaint_obj = Complaint(final_complaint)
        actions = complaint_obj.get_actions()

        assert any(action["action_type"] == "link" for action in actions)
```

**Validation Criteria**:
- [ ] All tests pass
- [ ] >80% code coverage
- [ ] Edge cases handled (empty strings, invalid IDs, etc.)
- [ ] Performance tests show <100ms latency

**Claude Code Session Requirements**:
- Context: All implementation files
- Tools: Write (new test file), Bash (pytest)
- Validation: `python -m pytest tests/test_complaint_to_civic_integration.py -v --cov`

---

## Implementation Sequencing Strategy

### Phase 1: Schema Foundation (Sessions 1-2)
**Context Required**: Schema files only
**Deliverables**:
- Updated `civic-app-schema.json`
- `ParticipationMechanism` interface
- SQLite migration script

**Validation Gate**: Schema validates, migration runs successfully

### Phase 2: Storage Layer (Sessions 3-4)
**Context Required**: Schema files + DB schema
**Deliverables**:
- `complaint_storage.py` with CRUD operations
- `Complaint` class implementing interface
- Basic storage tests

**Validation Gate**: All CRUD operations work, tests pass

### Phase 3: Business Logic (Sessions 5-7)
**Context Required**: Schema + Storage + Legislative enrichment reference
**Deliverables**:
- `complaint_matcher.py` with keyword algorithm
- `complaint_fallback.py` with issue banking
- Matching tests

**Validation Gate**: >30% match rate, <100ms latency

### Phase 4: API Integration (Sessions 8-9)
**Context Required**: Business logic + existing API
**Deliverables**:
- Complaint endpoints in `civic_api_integrated.py`
- Error handling and logging
- API tests

**Validation Gate**: All endpoints return correct responses

### Phase 5: Frontend Integration (Sessions 10-11)
**Context Required**: API + existing conversational UI
**Deliverables**:
- Complaint detection in message handler
- Event rendering with match scores
- User confirmation flow

**Validation Gate**: Manual testing shows complete user flow

### Phase 6: Comprehensive Testing (Session 12)
**Context Required**: All implementation files
**Deliverables**:
- Integration test suite
- Performance benchmarks
- Documentation updates

**Validation Gate**: All tests pass, PMF validation gates met

---

## Context Management Tips for Claude Code

### Session Context Files
Each session should load ONLY the files needed for that layer:

**Session 1-2 (Schema)**:
```
civic-app-schema.json
docs/COMPLAINT_TO_CIVIC_TECHNICAL_ARCHITECTURE.md (Section 1.3)
```

**Session 3-4 (Storage)**:
```
civic-app-schema.json
src/interfaces/participation_mechanism.py
src/civic_participation_metrics.py (reference)
data/civic_participation.db (schema inspection)
```

**Session 5-7 (Logic)**:
```
src/interfaces/participation_mechanism.py
src/complaint_storage.py
src/legislative_enrichment.py (reference pattern)
data/events/events_city-berkeley_*.json (sample data)
```

**Session 8-9 (API)**:
```
src/complaint_storage.py
src/complaint_matcher.py
src/complaint_fallback.py
src/civic_api_integrated.py (lines 1-200, then specific sections)
```

**Session 10-11 (Frontend)**:
```
frontend/mcp-civic-server/civic-conversational-OS.html (sections: message handling, rendering)
API documentation (endpoint signatures only)
```

### Rollback Points
Each layer completion creates a git commit:

```bash
# After schema
git commit -m "Add Complaint schema and ParticipationMechanism interface"

# After storage
git commit -m "Implement complaint storage with SQLite"

# After logic
git commit -m "Add complaint-to-event matching algorithm"

# After API
git commit -m "Integrate complaint endpoints into API"

# After frontend
git commit -m "Add complaint detection to conversational UI"

# After tests
git commit -m "Add comprehensive complaint-to-civic test suite"
```

### Validation Commands
Copy-paste validation commands for each layer:

```bash
# Schema validation
python -m json.tool civic-app-schema.json > /dev/null && echo "✓ Schema valid"

# Storage validation
python -m pytest tests/test_complaint_storage.py -v

# Matching validation
python -m pytest tests/test_complaint_matching.py -v

# API validation
curl -X POST http://localhost:8080/api/complaints -H "Content-Type: application/json" -d '{"user_id":"test","description":"pothole","jurisdiction_id":"city-berkeley"}'

# Integration validation
python -m pytest tests/test_complaint_to_civic_integration.py -v --cov
```

---

## Success Criteria

### Phase 1 MVP Success (After Layer 6)
- [ ] 50 real user complaints submitted
- [ ] >30% match rate (keyword matching)
- [ ] <100ms matching latency
- [ ] >10% of matched complaints → user action (PMF gate)
- [ ] Zero database errors
- [ ] Zero false positives (all matches relevant)

### Phase 2 Enhancement Triggers
Only implement Phase 2 features if:
- [ ] Match rate <30% despite tuning (add semantic)
- [ ] >10% of users request neighbor connections (add clustering)
- [ ] >20% of complaints are operational (add 311 integration)
- [ ] SQLite queries >500ms at p95 (migrate to Postgres)

### Foundation Grant Narrative Ready
- [ ] Working demo: "Report pothole → matched to Road Budget meeting"
- [ ] Metrics dashboard: Complaints → matching → actions
- [ ] Cost projection: <$10/month for 1000 complaints
- [ ] PMF evidence: Complaint→action conversion rate

---

## Estimated Total Effort

**Development Time**: 18-22 hours across 12 Claude Code sessions
**Testing Time**: 4-6 hours
**Documentation**: 2-3 hours
**Total**: ~25-30 hours

**Calendar Time**: 2-3 weeks (assuming 2-3 sessions/week)

**Phase 1 Complexity Budget**: ✅ Meets 500-line constraint
- Schema: ~100 lines
- Storage: ~150 lines
- Matching: ~120 lines
- Fallback: ~80 lines
- API: ~50 lines (additions)
- Total: **~500 lines**

---

## Next Steps

1. **Review this roadmap** with user for approval
2. **Start Session 1**: Schema extension (`civic-app-schema.json`)
3. **Commit after each layer** for rollback safety
4. **Validate gates** before proceeding to next layer
5. **Test with real complaints** as soon as API ready
6. **Measure PMF metrics** before building Phase 2

---

**This roadmap enables high-fidelity implementation with minimal context overhead per session.**
