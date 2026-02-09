"""
Context Assembly API — Pydantic models.

Request/response models for the context assembly endpoint.
Given any civic item, returns a rich context bundle that any consumer
surface can pass to an LLM.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field


# === Enums ===

class ItemType(str, Enum):
    """Supported civic item types."""
    agenda_item = "agenda_item"
    decision = "decision"
    issue = "issue"
    legislation = "legislation"
    meeting = "meeting"
    initiative = "initiative"


class ContextDepth(str, Enum):
    """How much context to assemble."""
    minimal = "minimal"    # Item + summary only
    standard = "standard"  # All sections
    deep = "deep"          # Extra cross-references, more testimony


# === Item Detail Models (type-specific) ===

class AgendaItemDetails(BaseModel):
    item_number: Optional[str] = None
    meeting_id: str
    meeting_title: str
    meeting_date: Optional[datetime] = None
    meeting_location: Optional[str] = None
    project_type: Optional[str] = None
    stance_eligible: bool = False
    comment_eligible: bool = False


class DecisionDetails(BaseModel):
    outcome: Optional[str] = None
    decision_date: Optional[datetime] = None
    votes: Optional[dict] = None
    body: Optional[str] = None


class IssueDetails(BaseModel):
    issue_type: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    created_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None


class LegislationDetails(BaseModel):
    bill_number: Optional[str] = None
    state: Optional[str] = None
    status_label: Optional[str] = None
    keywords: List[str] = []
    leverage_point: Optional[str] = None
    official_url: Optional[str] = None


class MeetingDetails(BaseModel):
    body: Optional[str] = None
    date: Optional[datetime] = None
    location: Optional[str] = None
    agenda_item_count: int = 0


class InitiativeDetails(BaseModel):
    creator_id: Optional[str] = None
    created_at: Optional[datetime] = None
    location: Optional[str] = None


# === Focal Item ===

class ContextItem(BaseModel):
    """The focal civic item with type-specific details."""
    type: ItemType
    id: str
    title: str
    description: Optional[str] = None
    why_it_matters: Optional[str] = None
    jurisdiction: str
    item_details: Union[
        AgendaItemDetails, DecisionDetails, IssueDetails,
        LegislationDetails, MeetingDetails, InitiativeDetails,
    ] = Field(discriminator=None)


# === Section Models ===

class RelatedDecision(BaseModel):
    id: str
    title: str
    outcome: Optional[str] = None
    date: Optional[str] = None
    relevance: Optional[str] = None


class HistorySection(BaseModel):
    related_decisions: List[RelatedDecision] = []
    timeline_summary: Optional[str] = None


class MunicipalCodeRef(BaseModel):
    section_number: str
    section_title: str
    excerpt: Optional[str] = None
    relevance_score: Optional[float] = None


class StateLegislationRef(BaseModel):
    bill_id: Optional[str] = None
    bill_number: Optional[str] = None
    status_label: Optional[str] = None
    summary: Optional[str] = None
    leverage_point: Optional[str] = None


class FederalRef(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    official_url: Optional[str] = None


class RegulatorySection(BaseModel):
    municipal_code: List[MunicipalCodeRef] = []
    state_legislation: List[StateLegislationRef] = []
    federal: List[FederalRef] = []
    executive_orders: List[FederalRef] = []


class SimilarIssue(BaseModel):
    id: str
    title: str
    issue_type: Optional[str] = None
    status: Optional[str] = None


class CommunitySection(BaseModel):
    similar_issues: List[SimilarIssue] = []
    related_initiatives: List[dict] = []
    voice_summary: Optional[dict] = None


class BudgetRef(BaseModel):
    department: str
    line_item: str
    budgeted_dollars: float
    fiscal_year: str


class FinancialSection(BaseModel):
    budget_items: List[BudgetRef] = []
    funding_flows: List[dict] = []
    total_relevant_budget: float = 0.0


class TestimonyExcerpt(BaseModel):
    speaker: str
    speaker_role: Optional[str] = None
    text: str
    video_url: Optional[str] = None
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None


class TestimonySection(BaseModel):
    public_comments: List[TestimonyExcerpt] = []
    staff_discussion: List[TestimonyExcerpt] = []
    council_discussion: List[TestimonyExcerpt] = []


class CommentStatus(BaseModel):
    open: bool = False
    closes_at: Optional[datetime] = None
    clerk_email: Optional[str] = None


class MeetingLogistics(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    location: Optional[str] = None
    how_to_attend: Optional[str] = None


class ParticipationSection(BaseModel):
    comment_status: Optional[CommentStatus] = None
    voice_enabled: bool = False
    actions_available: List[str] = []
    meeting_logistics: Optional[MeetingLogistics] = None


# === Aggregate Models ===

class ContextSections(BaseModel):
    """All context sections. None means requested but failed/empty."""
    history: Optional[HistorySection] = None
    regulatory: Optional[RegulatorySection] = None
    community: Optional[CommunitySection] = None
    financial: Optional[FinancialSection] = None
    testimony: Optional[TestimonySection] = None
    participation: Optional[ParticipationSection] = None


class ContextMetadata(BaseModel):
    """Assembly diagnostics and provenance."""
    assembled_at: datetime
    jurisdiction: str
    depth: str
    sections_included: List[str] = []
    section_status: Dict[str, str] = {}
    section_errors: Dict[str, str] = {}
    degraded: bool = False
    assembly_time_ms: int = 0
    section_times_ms: Dict[str, int] = {}


class ContextBundle(BaseModel):
    """Complete context assembly response."""
    item: ContextItem
    sections: ContextSections
    suggested_questions: List[str] = []
    metadata: ContextMetadata
