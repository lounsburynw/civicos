"""
Data models for civicos-state package.

These are simple dataclasses representing civic entities.
They can be used for type hints and data validation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any


@dataclass
class CityState:
    """
    Represents the state of a city/jurisdiction.

    Attributes:
        jurisdiction_id: Unique identifier (e.g., "city-berkeley")
        jurisdiction_name: Display name (e.g., "City of Berkeley")
        as_of: Timestamp of this state snapshot
        active_residents: Number of active users in this jurisdiction
        pending_comments: Number of draft comments awaiting submission
        coordination_threads: Active coordination discussions
        completeness_score: Data quality score (0.0-1.0)
        data_sources: List of platforms providing data
    """
    jurisdiction_id: str
    jurisdiction_name: str
    as_of: datetime
    active_residents: int = 0
    pending_comments: int = 0
    coordination_threads: int = 0
    completeness_score: float = 0.0
    data_sources: List[str] = field(default_factory=list)
    extraction_version: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Meeting:
    """
    Represents a municipal meeting (council, commission, board, etc.).

    Attributes:
        id: Unique meeting identifier
        jurisdiction_id: Parent jurisdiction
        title: Meeting title
        meeting_datetime: Scheduled date/time
        meeting_type: Type (city_council, planning_commission, etc.)
        status: Current status (scheduled, completed, cancelled)
        location: Physical location
        virtual_url: Virtual meeting link
        agenda_url: Link to agenda document
        source_platform: Data source (legistar, civicclerk, etc.)
    """
    id: str
    jurisdiction_id: str
    title: str
    meeting_datetime: datetime
    meeting_type: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    virtual_url: Optional[str] = None
    agenda_url: Optional[str] = None
    minutes_url: Optional[str] = None
    video_url: Optional[str] = None
    comment_deadline: Optional[datetime] = None
    source_platform: str = "unknown"
    source_url: Optional[str] = None
    last_verified: Optional[datetime] = None
    data_quality_score: float = 0.0
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    full_data: Optional[Dict[str, Any]] = None


@dataclass
class AgendaItem:
    """
    Represents an item on a meeting agenda.

    Attributes:
        id: Unique item identifier
        meeting_id: Parent meeting
        item_number: Agenda item number (e.g., "5.1")
        title: Item title
        project_type: Category (housing, transportation, etc.)
        actionability: Level of public participation possible
        impact_level: Significance assessment
        video_start_ms: Timestamp (ms) when item discussion starts in video
        video_end_ms: Timestamp (ms) when item discussion ends in video
    """
    id: str
    meeting_id: str
    title: str
    item_number: Optional[str] = None
    description: Optional[str] = None
    project_type: Optional[str] = None
    actionability: Optional[str] = None
    impact_level: Optional[str] = None
    financial_impact_cents: Optional[int] = None
    summary: Optional[str] = None
    why_it_matters: Optional[str] = None
    participation_guide: Optional[str] = None
    comment_count: int = 0
    following_count: int = 0
    relevant_bills: List[str] = field(default_factory=list)
    federal_programs: List[str] = field(default_factory=list)
    matched_complaints: List[str] = field(default_factory=list)
    extracted_at: Optional[datetime] = None
    enriched_at: Optional[datetime] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    full_data: Optional[Dict[str, Any]] = None
    # Video timestamp alignment (populated during transcript processing)
    video_start_ms: Optional[int] = None
    video_end_ms: Optional[int] = None


@dataclass
class Issue:
    """
    Represents a civic issue/complaint (from SeeClickFix or native).

    Attributes:
        id: Unique issue identifier
        jurisdiction_id: Parent jurisdiction
        source: Data source (seeclickfix, native)
        title: Issue summary
        issue_type: Category (pothole, graffiti, etc.)
        address: Location address
        status: Current status (open, closed, acknowledged)
    """
    id: str
    jurisdiction_id: str
    source: str
    title: str
    source_id: Optional[str] = None
    description: Optional[str] = None
    issue_type: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: str = "open"
    closed_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    matched_meetings: List[str] = field(default_factory=list)
    matched_agenda_items: List[str] = field(default_factory=list)
    match_score: Optional[float] = None
    match_reason: Optional[str] = None
    follower_count: int = 0
    coordination_thread_id: Optional[str] = None
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "jurisdiction_id": self.jurisdiction_id,
            "source": self.source,
            "title": self.title,
            "source_id": self.source_id,
            "description": self.description,
            "issue_type": self.issue_type,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
