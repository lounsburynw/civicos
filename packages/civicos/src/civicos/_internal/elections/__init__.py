"""
Election data models.

Supports multi-level elections (federal, state, county, city) and links
to elected officials for voting record queries.
"""

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
                    "candidates": [
                        {"id": x.id, "name": x.name, "party": x.party}
                        for x in c.candidates
                    ],
                    "ballot_measure": (
                        {
                            "id": c.ballot_measure.id,
                            "title": c.ballot_measure.title,
                            "description": c.ballot_measure.description,
                        }
                        if c.ballot_measure
                        else None
                    ),
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
    name: str  # Full name: "Jane Smith"
    seat: str  # "City Council District 1", "Mayor"
    jurisdiction_id: str  # "city-san-rafael"
    term_start: date
    term_end: Optional[date]  # None if current

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

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "name": self.name,
            "seat": self.seat,
            "jurisdiction_id": self.jurisdiction_id,
            "term_start": self.term_start.isoformat(),
            "term_end": self.term_end.isoformat() if self.term_end else None,
            "name_variations": self.name_variations,
            "candidate_id": self.candidate_id,
        }


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

    @property
    def no_percentage(self) -> float:
        if self.total_votes == 0:
            return 0.0
        return (self.no_votes / self.total_votes) * 100

    @property
    def abstain_percentage(self) -> float:
        if self.total_votes == 0:
            return 0.0
        return (self.abstain_votes / self.total_votes) * 100
