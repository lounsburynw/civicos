"""
Civic Type Definitions

Dataclasses representing the result types returned by Civic API methods.
Extracted from civicos.py for cleaner module organization.

Usage:
    from civicos.types import Decision, Meeting, RegulatoryStack
    # or via main module:
    from civicos import Decision, Meeting
"""

from typing import Optional, List, Dict, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime


# ─────────── QUERY RESULT TYPES ───────────

@dataclass
class RegulatoryStack:
    """Result from what_applies() - regulatory context for a topic."""
    topic: str
    jurisdiction: str
    federal: List[dict] = field(default_factory=list)
    state: List[dict] = field(default_factory=list)
    local: List[dict] = field(default_factory=list)
    retrieved_at: datetime = field(default_factory=datetime.now)


@dataclass
class Decision:
    """A past decision from what_happened()."""
    id: str
    title: str
    date: datetime
    outcome: str
    body: str
    votes: Optional[dict] = None


@dataclass
class TranscriptExcerpt:
    """A video transcript excerpt from what_was_said()."""
    id: str
    text: str
    speaker: str
    speaker_role: Optional[str] = None  # "council", "staff", "public", etc.
    speaker_name: Optional[str] = None
    video_id: str = ""
    start_timestamp: str = ""  # HH:MM:SS format
    end_timestamp: str = ""
    start_ms: int = 0
    end_ms: int = 0
    is_public_comment: bool = False
    score: float = 0.0  # Search relevance score

    @property
    def video_url(self) -> Optional[str]:
        """Generate YouTube URL with timestamp if video_id is available."""
        if not self.video_id:
            return None
        seconds = self.start_ms // 1000
        return f"https://www.youtube.com/watch?v={self.video_id}&t={seconds}s"


@dataclass
class TranscriptLink:
    """A link from a decision to a transcript excerpt."""
    chunk_id: str
    text: str
    speaker: str
    speaker_role: Optional[str] = None
    speaker_name: Optional[str] = None
    video_id: Optional[str] = None
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    is_public_comment: bool = False
    agenda_item: Optional[str] = None
    confidence: float = 0.0

    @property
    def video_url(self) -> Optional[str]:
        """Generate YouTube URL with timestamp if video_id is available."""
        if not self.video_id or not self.start_ms:
            return None
        seconds = self.start_ms // 1000
        return f"https://www.youtube.com/watch?v={self.video_id}&t={seconds}s"


@dataclass
class DecisionWithContext:
    """
    A decision enriched with linked transcript excerpts from what_happened_full_context().

    Combines the official decision (from minutes) with relevant transcript
    excerpts (from meeting video) showing what was said during discussion.
    """
    decision: Decision
    transcript_links: List[TranscriptLink] = field(default_factory=list)
    link_confidence: float = 0.0  # Overall confidence of linking
    link_type: str = ""  # "high_confidence", "medium_confidence", "low_confidence", "none"

    @property
    def has_transcript(self) -> bool:
        """Whether any transcript excerpts were found."""
        return len(self.transcript_links) > 0

    @property
    def public_comments(self) -> List[TranscriptLink]:
        """Get only public comment excerpts."""
        return [link for link in self.transcript_links if link.is_public_comment]

    @property
    def staff_discussion(self) -> List[TranscriptLink]:
        """Get only staff presentation excerpts."""
        return [link for link in self.transcript_links if link.speaker_role == "staff"]

    @property
    def council_discussion(self) -> List[TranscriptLink]:
        """Get only council deliberation excerpts."""
        return [link for link in self.transcript_links if link.speaker_role == "council"]


@dataclass
class Meeting:
    """An upcoming meeting from whats_next()."""
    id: str
    title: str
    date: datetime
    body: str
    agenda_items: List[dict] = field(default_factory=list)
    location: Optional[str] = None


@dataclass
class UpcomingElection:
    """An upcoming election from whats_next()."""
    id: str
    name: str
    election_date: datetime
    election_type: str
    deadlines: List[dict] = field(default_factory=list)
    source: Optional[str] = None
    source_url: Optional[str] = None


@dataclass
class Community:
    """Result from whos_with_me() - others who care about a topic."""
    topic: str
    jurisdiction: str
    follower_count: int = 0
    recent_voices: List[dict] = field(default_factory=list)
    active_initiatives: List[dict] = field(default_factory=list)


# ─────────── ACTION RESULT TYPES ───────────

@dataclass
class Initiative:
    """User-created initiative from start_something()."""
    id: str
    topic: str
    title: str
    description: str
    creator_id: str
    jurisdiction: str
    location: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Voice:
    """User voice from add_voice()."""
    id: str
    item_type: str
    item_id: str
    stance: str  # support, oppose, question
    comment: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Subscription:
    """Subscription from follow()."""
    id: str
    item_type: str
    item_id: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Preparation:
    """Meeting preparation from prepare()."""
    agenda_item_id: str
    regulatory_context: dict
    historical_decisions: List[dict]
    talking_points: List[str]
    allies: List[dict]
    logistics: dict
    legal_citations: List[dict] = field(default_factory=list)


@dataclass
class ActionDraft:
    """AI-generated draft for a civic action from draft_action()."""
    draft: str
    description: Optional[str] = None
    citations: List[str] = field(default_factory=list)



# ─────────── BUDGET & FUNDING TYPES ───────────

@dataclass
class BudgetItem:
    """A municipal budget line item from budget().

    Amounts are in dollars (converted from internal cents representation).
    Source URL and page enable verification against official budget documents.
    """
    id: str
    fund: str
    department: str
    line_item: str
    budgeted_dollars: float
    fiscal_year: str
    program: Optional[str] = None
    revised_dollars: Optional[float] = None
    actual_dollars: Optional[float] = None
    source_url: Optional[str] = None
    source_page: Optional[int] = None
    notes: Optional[str] = None


@dataclass
class BudgetSummary:
    """Aggregated budget summary from budget_summary()."""
    name: str  # Department, fund, or program name
    budgeted_dollars: float
    item_count: int
    revised_dollars: Optional[float] = None
    actual_dollars: Optional[float] = None


@dataclass
class FundingFlow:
    """Complete funding flow from federal → state → city for tracing intergovernmental dollars.

    Traces how federal/state funding flows through the system:
    Federal Award (USAspending) → State Pass-Through (CA Grants Portal) → City Budget Item

    Amounts are in dollars (converted from internal cents representation).
    """
    # Budget item (city level)
    budget_item_id: str
    budget_description: str
    budget_dollars: float
    department: Optional[str] = None
    fund: Optional[str] = None
    fiscal_year: Optional[str] = None

    # Federal level (source)
    federal_award_id: Optional[str] = None
    federal_cfda_number: Optional[str] = None
    federal_program_name: Optional[str] = None
    federal_agency: Optional[str] = None
    federal_dollars: Optional[float] = None
    federal_period_start: Optional[str] = None
    federal_period_end: Optional[str] = None

    # State level (pass-through)
    passthrough_id: Optional[str] = None
    state_agency: Optional[str] = None
    state_grant_id: Optional[str] = None
    state_program_name: Optional[str] = None
    state_dollars: Optional[float] = None
    state_period_start: Optional[str] = None
    state_period_end: Optional[str] = None

    # Match quality
    match_type: str = "unknown"
    match_confidence: float = 0.0
    reconciliation_status: str = "unverified"
    variance_dollars: Optional[float] = None
    variance_percentage: Optional[float] = None


@dataclass
class FundingFlowImpact:
    """Impact analysis for hypothetical funding cuts.

    Shows which budget items would be affected by a cut to a federal/state program.
    """
    program_name: str
    cfda_number: Optional[str]
    cut_percentage: float
    total_current_dollars: float
    total_impact_dollars: float
    affected_items: List[FundingFlow] = field(default_factory=list)


@dataclass
class FederalExpenditure:
    """
    Audited federal expenditure from Single Audit (SEFA data).

    This is authoritative spending data from the Federal Audit Clearinghouse (FAC).
    Unlike federal_awards (which show allocations/awards), these are actual
    audited expenditures - what the city actually spent.

    Amounts are in dollars (converted from internal cents representation).
    """
    # Identifiers
    report_id: str
    cfda_number: str
    audit_year: int

    # Amounts
    amount_expended_dollars: float
    federal_program_total_dollars: Optional[float] = None
    cluster_total_dollars: Optional[float] = None

    # Program info
    federal_program_name: Optional[str] = None
    cluster_name: Optional[str] = None
    federal_agency_prefix: Optional[str] = None

    # Flags
    is_major: bool = False
    is_passthrough: bool = False

    # Source
    source_url: Optional[str] = None


@dataclass
class IntergovernmentalRevenue:
    """
    Intergovernmental revenue from CA State Controller data.

    Represents federal, state, or county revenue received by a city as reported
    to the CA State Controller. More recent than FAC data (current fiscal year
    available) and includes state/county funding that FAC doesn't track.

    Sources:
    - Federal: Grants, pass-through funding from federal agencies
    - State: Gas tax, Prop 172, mandated cost reimbursements, state grants
    - County: County grants and intergovernmental transfers
    """
    fiscal_year: int
    form_table: str  # SCO form code (e.g., "FUNC_GAS_TAX")
    source: str  # "federal", "state", "county", or "undetermined"
    amount_dollars: float

    # Category info
    category: Optional[str] = None
    subcategory: Optional[str] = None
    line_description: Optional[str] = None

    # Entity info
    entity_name: Optional[str] = None
    county: Optional[str] = None


@dataclass
class IntergovernmentalRevenueSummary:
    """
    Summary of intergovernmental revenue by source for a fiscal year.

    Aggregates federal, state, and county funding with breakdown by line item.
    """
    fiscal_year: int
    entity_name: str
    federal_total_dollars: float
    state_total_dollars: float
    county_total_dollars: float
    undetermined_total_dollars: float
    total_dollars: float
    details: List[IntergovernmentalRevenue] = field(default_factory=list)


# ─────────── ENTITY TYPES (from Storage) ───────────
# These types represent entities returned from StorageBackend methods.
# Previously returned as untyped List[Dict[str, Any]], now formalized as dataclasses.


@dataclass
class Legislation:
    """A legislative bill (state or federal) from get_legislation().

    Represents bills tracked in the legislation table, used for:
    - what_applies() regulatory context (state and federal bills)
    - Vector search for relevant legislation

    The bill_id is the unique identifier (e.g., 'ca-ab1234', 'us-hr5678').
    Status codes are LegiScan numeric codes (1=Introduced, 2=Engrossed, etc.).
    """
    id: str  # Database row ID
    bill_id: str  # Unique bill identifier (e.g., 'ca-ab1234')
    state: str  # State code ('CA', 'US', etc.)

    # Core bill information
    bill_number: Optional[str] = None  # 'AB1234', 'HR5678'
    bill_name: Optional[str] = None  # Full bill title
    status: Optional[str] = None  # LegiScan status code
    status_label: Optional[str] = None  # Human-readable status

    # Content
    summary: Optional[str] = None
    full_text: Optional[str] = None
    leverage_point: Optional[str] = None  # Key advocacy point

    # Classification
    keywords: List[str] = field(default_factory=list)
    topic: Optional[str] = None  # LLM-classified topic

    # Dates and URLs
    enacted_date: Optional[str] = None
    official_url: Optional[str] = None

    # Local implementation tracking
    local_implementation_required: bool = False
    local_deadline: Optional[str] = None

    # Jurisdiction context
    jurisdiction_id: Optional[str] = None  # 'city-san-rafael' for local relevance

    # External IDs
    legiscan_id: Optional[int] = None

    # Metadata
    metadata: Optional[dict] = None


@dataclass
class MunicipalCodeSection:
    """A local ordinance section from get_municipal_code().

    Represents sections of municipal/county code stored in the municipal_code table.
    Used for:
    - what_applies() local regulatory context
    - Vector search for relevant local laws

    Hierarchical structure: Title > Chapter > Section
    """
    id: str  # Unique section ID
    jurisdiction_id: str  # 'city-san-rafael', 'county-marin'
    section_number: str  # '14.06.030'
    section_title: str  # 'Accessory Dwelling Units'
    full_text: str  # Complete section text
    chapter: str  # Chapter number

    # Hierarchy
    chapter_title: Optional[str] = None
    title_number: Optional[str] = None
    title_name: Optional[str] = None

    # Source tracking
    node_id: Optional[str] = None  # Original code platform node ID
    ordinance_history: Optional[str] = None  # Amendment history
    source: Optional[str] = None  # 'municode', 'qcode', etc.

    # Versioning
    extraction_version: Optional[str] = None


@dataclass
class ElectedOfficial:
    """An elected official from get_elected_officials().

    Represents current and former elected officials for a jurisdiction.
    Used for:
    - Voting record lookups
    - Meeting attendance tracking
    - Official contact information

    The name_variations field supports fuzzy matching across different
    name formats in meeting minutes and transcripts.
    """
    id: str
    name: str  # Primary display name
    seat: str  # 'Mayor', 'Council Member', 'Supervisor'
    jurisdiction_id: str  # 'city-san-rafael'

    # Term dates (stored as text for flexibility)
    term_start: str
    term_end: Optional[str] = None  # None = currently serving

    # Name matching
    name_variations: List[str] = field(default_factory=list)  # ['K. Mullen', 'Councilmember Mullen']

    # Cross-references
    candidate_id: Optional[str] = None  # Link to election candidate records


@dataclass
class ExecutiveOrder:
    """A presidential executive order from get_executive_orders().

    Represents executive orders tracked from the Federal Register.
    Used for:
    - what_applies() federal regulatory context
    - Vector search for relevant executive actions

    The document_number is the Federal Register document number.
    The eo_number is the traditional EO number (when available).
    """
    id: int  # Database row ID
    document_number: str  # Federal Register document number
    title: str  # Official title
    president: str  # 'Biden', 'Trump', etc.

    # EO identification
    eo_number: Optional[int] = None  # Traditional EO number (e.g., 14008)
    president_id: Optional[str] = None  # Standardized president identifier

    # Content
    abstract: Optional[str] = None  # Brief summary
    full_text: Optional[str] = None  # Complete text

    # Dates
    signing_date: Optional[str] = None
    publication_date: Optional[str] = None

    # URLs
    html_url: Optional[str] = None
    pdf_url: Optional[str] = None
    raw_text_url: Optional[str] = None

    # Status tracking
    status: Optional[str] = None  # 'active', 'revoked', etc.
    revoked_by_eo: Optional[int] = None  # EO number that revoked this one

    # Metadata
    metadata: Optional[dict] = None


# ─────────── FEDERAL PROGRAM TYPE ───────────

@dataclass
class FederalProgram:
    """Federal grant program with jurisdiction-specific allocation info.

    Used to represent federal programs like CDBG, HOME, Section 8 with their
    funding details and jurisdiction-specific allocations.
    """
    program_id: str                          # 'cdbg', 'home', 'section_8_hcv'
    program_name: str                        # 'Community Development Block Grant'
    administering_agency: str                # 'HUD'
    description: str

    # Scope
    scope: str = "national"                  # 'national' or 'jurisdiction'
    jurisdiction_id: Optional[str] = None    # 'city-san-rafael' for local

    # Program details
    eligible_activities: List[str] = field(default_factory=list)
    compliance_requirements: List[str] = field(default_factory=list)
    citizen_participation: List[str] = field(default_factory=list)

    # Allocation (jurisdiction-specific)
    fiscal_year: Optional[str] = None        # 'FY2026'
    allocation_amount: Optional[int] = None
    allocation_status: Optional[str] = None  # 'CONFIRMED', 'UNCERTAIN', 'DRAFT'

    # Contacts and URLs
    key_contacts: Optional[Dict] = None
    official_url: Optional[str] = None
