"""
Civic - Main Entry Point

The unified interface to the Civic platform.

Usage:
    from civic import Civic

    c = Civic("san-rafael-ca")

    # Query (Learn)
    c.what_applies("housing")
    c.what_happened("bike lanes")
    c.whats_next(["transportation"])
    c.whos_with_me("traffic safety")

    # Action (Act)
    c.start_something(topic="traffic", title="Protected bike lane")
    c.add_voice("agenda_item", "item_123", "support", "As a cyclist...")
    c.follow("meeting", "mtg_456")
    c.prepare("item_789")

    # AI Orchestration
    c.suggestions()
    c.coordinate("init_123", "plan_testimony")
    c.report_outcome("item_789", "passed")
"""

from typing import Optional, List, Any, Dict, Union
from dataclasses import dataclass, field
from datetime import datetime

# Import from internal modules (consolidated)
import logging

from civic._internal.state import StateManager
from civic.storage import StorageBackend, StorageStats, SQLiteBackend, get_storage_backend, get_vector_backend
from civic.storage.vector import VectorBackend
from civic.paths import get_state_db_path

logger = logging.getLogger(__name__)

# Optional imports - gracefully degrade if not available
try:
    from civic._internal.legal import LegalSearch, enrich_opportunity
    LEGAL_AVAILABLE = True
except ImportError:
    LEGAL_AVAILABLE = False
    LegalSearch = None

try:
    from civic._internal.coordination import run_coordination, get_campaign_state
    COORDINATION_AVAILABLE = True
except ImportError:
    COORDINATION_AVAILABLE = False
    run_coordination = None


# ─────────── RESULT TYPES ───────────

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
class DecisionWithContext:
    """
    A decision enriched with linked transcript excerpts from what_happened_full_context().

    Combines the official decision (from minutes) with relevant transcript
    excerpts (from meeting video) showing what was said during discussion.
    """
    decision: Decision
    transcript_links: List["TranscriptLink"] = field(default_factory=list)
    link_confidence: float = 0.0  # Overall confidence of linking
    link_type: str = ""  # "high_confidence", "medium_confidence", "low_confidence", "none"

    @property
    def has_transcript(self) -> bool:
        """Whether any transcript excerpts were found."""
        return len(self.transcript_links) > 0

    @property
    def public_comments(self) -> List["TranscriptLink"]:
        """Get only public comment excerpts."""
        return [link for link in self.transcript_links if link.is_public_comment]

    @property
    def staff_discussion(self) -> List["TranscriptLink"]:
        """Get only staff presentation excerpts."""
        return [link for link in self.transcript_links if link.speaker_role == "staff"]

    @property
    def council_discussion(self) -> List["TranscriptLink"]:
        """Get only council deliberation excerpts."""
        return [link for link in self.transcript_links if link.speaker_role == "council"]


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
class HybridSearchResult:
    """
    Combined result from what_happened_with_discussion().

    Links official documents (staff reports, agenda packets) with meeting
    discussion (public testimony, council deliberation) for complete context.
    """
    id: str
    text: str
    source_type: str  # "pdf" or "transcript"
    score: float

    # PDF-specific fields
    agenda_item: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None

    # Transcript-specific fields
    speaker: Optional[str] = None
    speaker_role: Optional[str] = None
    speaker_name: Optional[str] = None
    video_id: Optional[str] = None
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    is_public_comment: bool = False

    @property
    def video_url(self) -> Optional[str]:
        """Generate YouTube URL with timestamp if video_id is available."""
        if not self.video_id or not self.start_ms:
            return None
        seconds = self.start_ms // 1000
        return f"https://www.youtube.com/watch?v={self.video_id}&t={seconds}s"


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


@dataclass
class Suggestion:
    """Proactive suggestion from suggestions()."""
    type: str  # upcoming_meeting, trending_initiative, coordination_ready
    title: str
    reason: str
    action: str
    item_id: str


@dataclass
class CoordinationPlan:
    """Coordination plan from coordinate()."""
    action: str
    steps: List[dict]
    participants: List[str]
    deadline: Optional[datetime] = None


@dataclass
class Outcome:
    """Recorded outcome from report_outcome()."""
    item_id: str
    outcome: str  # passed, failed, continued, modified
    notes: Optional[str] = None
    recorded_at: datetime = field(default_factory=datetime.now)


@dataclass
class BudgetItem:
    """A municipal budget line item from budget().

    Amounts are in dollars (converted from internal cents representation).
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
    source_page: Optional[int] = None
    notes: Optional[str] = None
    # Future extensibility for intergovernmental funding (Phase 2)
    # funding_source: Optional[str] = None  # "federal", "state", "local"
    # cfda_number: Optional[str] = None     # Federal program identifier


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
    affected_items: List["FundingFlow"]


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
    details: List[IntergovernmentalRevenue]


# ─────────── MAIN CIVIC CLASS ───────────

@dataclass
class Civic:
    """
    Main entry point for the Civic platform.

    Wraps civic-state, civic-legal, and civic-coordination packages
    into a unified, query-centric API.

    Usage:
        c = Civic("san-rafael-ca")
        c.what_applies("housing")
        c.whats_next(["transportation"])
    """
    jurisdiction: str
    db_path: str = field(default=None)  # Defaults to get_state_db_path() in __post_init__
    _state: StateManager = field(default=None, repr=False)
    _search: Any = field(default=None, repr=False)  # LegalSearch if available
    _storage: StorageBackend = field(default=None, repr=False)  # StorageBackend for stats
    _vectors: Optional[VectorBackend] = field(default=None, repr=False)  # VectorBackend for semantic search

    def __post_init__(self):
        """Initialize internal services."""
        import os

        # Normalize jurisdiction ID to canonical format (e.g., "san-rafael" -> "city-san-rafael")
        from civic._internal.jurisdiction import normalize_jurisdiction
        self.jurisdiction = normalize_jurisdiction(self.jurisdiction)

        # Check for DATABASE_URL environment variable for cloud storage
        database_url = os.getenv("DATABASE_URL")

        # Default db_path using get_state_db_path() which respects CIVIC_DATA_ROOT
        if self.db_path is None:
            self.db_path = get_state_db_path()

        self._state = StateManager(self.db_path)

        # Use get_storage_backend() factory to support both SQLite and Postgres
        # DATABASE_URL takes precedence for cloud deployments
        if database_url:
            self._storage = get_storage_backend(database_url)
        else:
            self._storage = SQLiteBackend(self.db_path)

        # Vector backend for semantic search (pgvector or None for ChromaDB fallback)
        self._vectors = get_vector_backend(database_url)
        if self._vectors:
            logger.debug(
                f"Civic({self.jurisdiction}): storage={type(self._storage).__name__}, "
                f"vectors={self._vectors.backend_type}"
            )
        else:
            logger.debug(
                f"Civic({self.jurisdiction}): storage={type(self._storage).__name__}, "
                f"vectors=ChromaDB (local fallback)"
            )

        # LegalSearch requires embeddings - make optional
        if LEGAL_AVAILABLE:
            try:
                self._search = LegalSearch()
            except Exception:
                self._search = None

    # ─────────── STORAGE METHODS ───────────

    def get_storage_stats(self, jurisdiction_id: str = None) -> StorageStats:
        """
        Get storage statistics for dashboard display.

        Returns statistics about stored data including meeting counts,
        temporal range, and storage size. Used by admin dashboards to
        show the "stored" stage of the 4-stage ETL pipeline.

        Args:
            jurisdiction_id: Optional override (default: self.jurisdiction)

        Returns:
            StorageStats with counts, temporal info, and metadata
        """
        jurisdiction_id = jurisdiction_id or self.jurisdiction
        return self._storage.get_stats(jurisdiction_id)

    # ─────────── QUERY METHODS (Learn) ───────────

    def what_applies(self, topic: str, location: str = None) -> RegulatoryStack:
        """
        Get regulatory stack for a topic.

        Returns federal, state, and local rules that apply to the topic.
        Uses legislative_context_cache for state bills and federal programs.

        Args:
            topic: The topic to search (e.g., "housing", "bike lanes")
            location: Optional location for local rules

        Returns:
            RegulatoryStack with federal, state, and local context
        """
        from civic.context import get_regulatory_context
        result = get_regulatory_context(self.jurisdiction, topic, location)
        # Convert to this module's RegulatoryStack to ensure type consistency
        return RegulatoryStack(
            topic=result.topic,
            jurisdiction=result.jurisdiction,
            federal=result.federal,
            state=result.state,
            local=result.local,
            retrieved_at=result.retrieved_at,
        )

    def what_happened(self, query: str, since: str = None) -> List[Decision]:
        """
        Search past decisions.

        Uses civic-state for meeting/decision history with optional
        semantic search via civic-legal.

        Args:
            query: Search query (e.g., "bike lanes", "housing development")
            since: Optional date filter (ISO format)

        Returns:
            List of matching decisions
        """
        from civic.history import search_decisions

        results = search_decisions(
            state_manager=self._state,
            jurisdiction=self.jurisdiction,
            query=query,
            since=since,
            vector_backend=self._vectors,  # Explicit backend, no auto-detection
        )

        # Convert to this module's Decision type for consistency
        return [
            Decision(
                id=d.id,
                title=d.title,
                date=d.date,
                outcome=d.outcome,
                body=d.body,
                votes=d.votes,
            )
            for d in results
        ]

    def what_happened_full_context(
        self,
        query: str,
        since: str = None,
        top_k: int = 5,
        transcript_excerpts_per_decision: int = 3,
    ) -> List[DecisionWithContext]:
        """
        Search past decisions with linked transcript excerpts.

        Returns both the official decision (from minutes) and what was actually
        said during the meeting (from video transcript). This provides complete
        context including:
        - What public testimony was given
        - What staff recommended and why
        - What council members discussed before voting

        Args:
            query: Search query (e.g., "bike lanes", "housing development")
            since: Optional date filter (ISO format)
            top_k: Maximum number of decisions to return (default 5)
            transcript_excerpts_per_decision: Max excerpts per decision (default 3)

        Returns:
            List of DecisionWithContext objects with decisions + linked transcripts

        Example:
            >>> c = Civic("san-rafael")
            >>> results = c.what_happened_full_context("homeless shelter")
            >>> for r in results:
            ...     print(f"{r.decision.title}: {r.decision.outcome}")
            ...     if r.has_transcript:
            ...         for link in r.public_comments:
            ...             print(f"  Public: {link.text[:60]}...")
        """
        from civic.history import search_decisions_with_context

        results = search_decisions_with_context(
            state_manager=self._state,
            jurisdiction=self.jurisdiction,
            query=query,
            since=since,
            top_k=top_k,
            transcript_excerpts_per_decision=transcript_excerpts_per_decision,
        )

        # Convert to this module's types for consistency
        return [
            DecisionWithContext(
                decision=Decision(
                    id=r.decision.id,
                    title=r.decision.title,
                    date=r.decision.date,
                    outcome=r.decision.outcome,
                    body=r.decision.body,
                    votes=r.decision.votes,
                ),
                transcript_links=[
                    TranscriptLink(
                        chunk_id=link.chunk_id,
                        text=link.text,
                        speaker=link.speaker,
                        speaker_role=link.speaker_role,
                        speaker_name=link.speaker_name,
                        video_id=link.video_id,
                        start_timestamp=link.start_timestamp,
                        end_timestamp=link.end_timestamp,
                        start_ms=link.start_ms,
                        end_ms=link.end_ms,
                        is_public_comment=link.is_public_comment,
                        agenda_item=link.agenda_item,
                        confidence=link.confidence,
                    )
                    for link in r.transcript_links
                ],
                link_confidence=r.link_confidence,
                link_type=r.link_type,
            )
            for r in results
        ]

    def what_was_said(self, query: str, top_k: int = 10) -> List[TranscriptExcerpt]:
        """
        Search video transcripts for spoken content.

        Use when looking for public testimony, staff presentations, council
        deliberations, or any spoken content that isn't a formal decision.

        Args:
            query: Search query (e.g., "homeless shelter", "traffic concerns")
            top_k: Maximum number of results (default 10)

        Returns:
            List of transcript excerpts with speaker info and video timestamps
        """
        from civic.history import search_transcripts

        results = search_transcripts(
            jurisdiction=self.jurisdiction,
            query=query,
            top_k=top_k,
        )

        return [
            TranscriptExcerpt(
                id=r.id,
                text=r.text,
                speaker=r.speaker,
                speaker_role=r.speaker_role,
                speaker_name=r.speaker_name,
                video_id=r.video_id,
                start_timestamp=r.start_timestamp,
                end_timestamp=r.end_timestamp,
                start_ms=r.start_ms,
                end_ms=r.end_ms,
                is_public_comment=r.is_public_comment,
                score=r.score,
            )
            for r in results
        ]

    def get_public_testimony(self, topic: str, top_k: int = 10) -> List[TranscriptExcerpt]:
        """
        Retrieve public testimony on a specific topic with speaker attribution.

        Searches video transcripts for spoken content that occurred during
        public comment sections of meetings. Results include speaker names
        where identified.

        Use for finding what community members have said about specific issues,
        gathering citizen perspectives, or identifying engaged constituents.

        Args:
            topic: Topic to search for (e.g., "affordable housing", "traffic")
            top_k: Maximum number of results (default 10)

        Returns:
            List of transcript excerpts from public comment sections,
            with speaker attribution where available
        """
        from civic.history import search_transcripts

        results = search_transcripts(
            jurisdiction=self.jurisdiction,
            query=topic,
            top_k=top_k,
            public_comment_only=True,
        )

        return [
            TranscriptExcerpt(
                id=r.id,
                text=r.text,
                speaker=r.speaker,
                speaker_role=r.speaker_role,
                speaker_name=r.speaker_name,
                video_id=r.video_id,
                start_timestamp=r.start_timestamp,
                end_timestamp=r.end_timestamp,
                start_ms=r.start_ms,
                end_ms=r.end_ms,
                is_public_comment=r.is_public_comment,
                score=r.score,
            )
            for r in results
        ]

    def what_happened_with_discussion(
        self,
        query: str,
        top_k: int = 10,
        agenda_item: Optional[str] = None,
    ) -> List[HybridSearchResult]:
        """
        Get the complete picture: staff reports AND meeting discussion.

        Combines results from official documents (agenda packets, staff reports)
        and meeting transcripts (public testimony, council deliberation) to
        provide full context for civic decisions.

        Use this when you want to understand both:
        - What was written (staff recommendations, fiscal analysis, legal context)
        - What was said (public testimony, council questions, staff responses)

        Args:
            query: Search query (e.g., "homeless shelter funding", "traffic safety")
            top_k: Maximum number of results (default 10)
            agenda_item: Optional agenda item filter (e.g., "6.a") to get
                        related content from both documents and discussion

        Returns:
            List of HybridSearchResult objects with source attribution.
            Results include both PDF excerpts (with page numbers) and
            transcript excerpts (with timestamps and speaker info).

        Example:
            >>> c = Civic("san-rafael")
            >>> results = c.what_happened_with_discussion("shelter funding")
            >>> for r in results:
            ...     if r.source_type == "pdf":
            ...         print(f"[Staff Report p{r.page_start}] {r.text[:100]}")
            ...     else:
            ...         speaker = r.speaker_name or r.speaker
            ...         print(f"[Video @{r.start_timestamp}] {speaker}: {r.text[:100]}")
        """
        from civic.history import search_hybrid

        results = search_hybrid(
            jurisdiction=self.jurisdiction,
            query=query,
            top_k=top_k,
            agenda_item=agenda_item,
        )

        return [
            HybridSearchResult(
                id=r.id,
                text=r.text,
                source_type=r.source_type,
                score=r.score,
                # PDF fields
                agenda_item=r.agenda_item,
                page_start=r.page_start,
                page_end=r.page_end,
                # Transcript fields
                speaker=r.speaker,
                speaker_role=r.speaker_role,
                speaker_name=r.speaker_name,
                video_id=r.video_id,
                start_timestamp=r.start_timestamp,
                end_timestamp=r.end_timestamp,
                start_ms=r.start_ms,
                end_ms=r.end_ms,
                is_public_comment=r.is_public_comment,
            )
            for r in results
        ]

    def whats_next(
        self,
        topics: List[str] = None,
        days: int = 30,
        include_elections: bool = False,
    ) -> Union[List[Meeting], List[Union[Meeting, UpcomingElection]]]:
        """
        Get upcoming meetings and optionally elections.

        Uses PostgresBackend (cloud) or SQLiteBackend (local) via _storage
        to query meetings and elections. Falls back to StateManager for local dev.

        Args:
            topics: Optional list of topics to filter by
            days: Number of days to look ahead (default 30)
            include_elections: If True, also include upcoming elections

        Returns:
            List of upcoming meetings, or mixed list including elections
        """
        from datetime import timedelta, timezone

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days)

        # Try storage backend first (PostgresBackend or SQLiteBackend)
        try:
            meetings_data = self._storage.get_meetings(
                jurisdiction_id=self.jurisdiction,
                since=now,
                until=cutoff,
            )
        except Exception as e:
            # Fall back to StateManager for local dev without storage
            logger.debug(f"Storage backend failed, falling back to StateManager: {e}")
            state = self._state.get_city_state(self.jurisdiction)
            if state is None:
                meetings_data = []
            else:
                meetings_data = state.get("meetings", [])

        # Convert to Meeting objects
        meetings: List[Meeting] = []
        for m in meetings_data:
            # Parse meeting_datetime
            meeting_date = m.get("meeting_datetime") or m.get("date")
            if isinstance(meeting_date, str):
                try:
                    meeting_date = datetime.fromisoformat(meeting_date.replace('Z', '+00:00'))
                except ValueError:
                    meeting_date = datetime.now(timezone.utc)
            elif meeting_date is None:
                meeting_date = datetime.now(timezone.utc)

            # Make naive datetime UTC-aware for filtering
            if meeting_date.tzinfo is None:
                meeting_date = meeting_date.replace(tzinfo=timezone.utc)

            # Skip meetings outside the window (in case backend doesn't filter)
            if not (now <= meeting_date <= cutoff):
                continue

            # Get agenda items from storage backend
            meeting_id = m.get("id", "")
            agenda_items = []
            if meeting_id:
                try:
                    agenda_items = self._storage.get_agenda_items(meeting_id=meeting_id)
                except Exception:
                    pass

            # Fall back to embedded agenda items if relational query fails
            if not agenda_items:
                agenda_items = m.get("agenda_items", [])
                if not agenda_items:
                    full_data = m.get("full_data", {})
                    if isinstance(full_data, str):
                        import json
                        try:
                            full_data = json.loads(full_data)
                        except (json.JSONDecodeError, TypeError):
                            full_data = {}
                    agenda_items = full_data.get("agenda_items", [])

            meetings.append(Meeting(
                id=meeting_id,
                title=m.get("title", ""),
                date=meeting_date,
                body=m.get("meeting_type", ""),
                agenda_items=agenda_items,
                location=m.get("location"),
            ))

        # Filter by topics if provided
        if topics:
            def has_matching_topic(meeting):
                for item in meeting.agenda_items:
                    # Support both 'topic' (JSON) and 'project_type' (relational)
                    item_topic = (item.get("topic") or item.get("project_type") or "").lower()
                    if any(t.lower() in item_topic for t in topics):
                        return True
                return False
            meetings = [m for m in meetings if has_matching_topic(m)]

        # Sort meetings by date
        meetings.sort(key=lambda x: x.date)

        # If not including elections, return meetings only
        if not include_elections:
            return meetings

        # Fetch upcoming elections
        elections: List[UpcomingElection] = []
        try:
            elections_data = self._storage.get_elections(
                jurisdiction_id=self.jurisdiction,
                include_past=False,
            )
            for e in elections_data:
                # Parse election_date
                election_date = e.get("election_date")
                if isinstance(election_date, str):
                    try:
                        # election_date is typically just a date string (YYYY-MM-DD)
                        from datetime import date as date_type
                        parsed_date = date_type.fromisoformat(election_date)
                        # Convert to datetime at midnight UTC for consistent comparison
                        election_date = datetime(
                            parsed_date.year, parsed_date.month, parsed_date.day,
                            tzinfo=timezone.utc
                        )
                    except ValueError:
                        continue  # Skip malformed dates
                elif election_date is None:
                    continue

                # Skip elections outside the window
                if not (now <= election_date <= cutoff):
                    continue

                # Fetch deadlines for this election
                deadlines = []
                try:
                    deadline_data = self._storage.get_election_deadlines(
                        election_id=e.get("id")
                    )
                    for d in deadline_data:
                        deadlines.append({
                            "deadline_type": d.get("deadline_type"),
                            "deadline_date": d.get("deadline_date"),
                            "description": d.get("description"),
                        })
                except Exception:
                    pass  # Deadlines are optional

                elections.append(UpcomingElection(
                    id=e.get("id", ""),
                    name=e.get("name", ""),
                    election_date=election_date,
                    election_type=e.get("election_type", ""),
                    deadlines=deadlines,
                    source=e.get("source"),
                    source_url=e.get("source_url"),
                ))
        except Exception as e:
            logger.debug(f"Failed to fetch elections: {e}")

        # Combine meetings and elections, sorted by date
        combined: List[Union[Meeting, UpcomingElection]] = list(meetings) + list(elections)
        combined.sort(key=lambda x: x.date if isinstance(x, Meeting) else x.election_date)

        return combined

    def whos_with_me(
        self,
        topic: str,
        semantic: bool = True,
        similarity_threshold: float = 0.3,
    ) -> Community:
        """
        Find others who care about this topic.

        Uses civic-state to query issues, followers, and initiatives
        related to the topic. When embeddings are available, uses semantic
        matching to find related issue types beyond exact matches.

        Args:
            topic: Topic to search (e.g., "traffic safety")
            semantic: If True (default), use semantic matching to find
                     related issue types. Falls back to exact match if
                     embeddings unavailable.
            similarity_threshold: Minimum similarity score for semantic
                                 matching (0.0-1.0, default 0.3)

        Returns:
            Community with followers, voices, and initiatives
        """
        all_issues = []

        # Try semantic matching first if enabled
        if semantic:
            related_types = self._find_semantic_issue_types(
                topic, threshold=similarity_threshold
            )
            if related_types:
                # Query for each semantically related issue type
                for issue_type, _score in related_types:
                    issues = self._state.query_issues(
                        self.jurisdiction, issue_type=issue_type
                    )
                    if issues:
                        all_issues.extend(issues)

        # If no semantic results (or semantic disabled), fall back to exact match
        if not all_issues:
            issues = self._state.query_issues(self.jurisdiction, issue_type=topic)
            if issues:
                all_issues = issues

        return Community(
            topic=topic,
            jurisdiction=self.jurisdiction,
            follower_count=len(all_issues),
            recent_voices=[],
            active_initiatives=[],
        )

    def _find_semantic_issue_types(
        self,
        topic: str,
        threshold: float = 0.3,
    ) -> list:
        """
        Find issue types semantically related to a topic.

        Uses embeddings to match user's natural language query to actual
        issue type names in the database.

        Args:
            topic: Natural language topic (e.g., "traffic problems")
            threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of (issue_type, score) tuples, or empty list if unavailable
        """
        import os
        from civic._internal.jurisdiction import normalize_jurisdiction
        from civic.paths import get_vectors_dir

        try:
            from civic._internal.meetings.embeddings import CivicEmbeddings
        except ImportError:
            return []

        # Check if embeddings are available for this jurisdiction
        jurisdiction = normalize_jurisdiction(self.jurisdiction)
        persist_dir = get_vectors_dir(jurisdiction)
        if not os.path.exists(persist_dir):
            return []

        # Get available issue types from StateManager
        stats = self._state.get_issue_stats(self.jurisdiction)
        top_types = stats.get("top_types", [])
        if not top_types:
            return []

        # Extract just the type names
        issue_type_names = [t[0] for t in top_types]

        try:
            embedder = CivicEmbeddings(
                jurisdiction_id=jurisdiction,
                persist_directory=persist_dir,
            )
            return embedder.find_similar_issue_types(
                query_topic=topic,
                issue_types=issue_type_names,
                threshold=threshold,
            )
        except Exception:
            # Any error - fall back to empty list (exact match will be used)
            return []

    # ─────────── VOTING RECORD METHODS ───────────

    def get_voting_record(
        self,
        official_name: str,
        topic: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> "VotingRecord":
        """
        Get an elected official's voting record.

        Queries decisions where the official voted and aggregates their
        voting statistics (yes/no/absent counts).

        Args:
            official_name: Name of the elected official (fuzzy matched)
            topic: Optional topic filter (e.g., "housing", "transportation")
            since: Filter decisions on/after this date (YYYY-MM-DD)
            until: Filter decisions on/before this date (YYYY-MM-DD)

        Returns:
            VotingRecord with vote statistics and decision list

        Raises:
            ValueError: If official not found

        Example:
            >>> c = Civic("san-rafael")
            >>> record = c.get_voting_record("Maribeth Bushey", topic="housing")
            >>> print(f"Voted YES on {record.yes_percentage:.0f}% of housing items")
        """
        from civic._internal.elections import VotingRecord, ElectedOfficial

        # 1. Find official by name
        official = self._storage.get_official_by_name(
            jurisdiction_id=self.jurisdiction,
            name=official_name,
        )

        if not official:
            # Try loading elected officials and fuzzy matching
            officials = self._storage.get_elected_officials(
                jurisdiction_id=self.jurisdiction,
                current_only=True,
            )

            # Fuzzy match using ElectedOfficial.matches_name()
            for o in officials:
                eo = ElectedOfficial(
                    id=o["id"],
                    name=o["name"],
                    seat=o["seat"],
                    jurisdiction_id=o["jurisdiction_id"],
                    term_start=o.get("term_start") or "2020-01-01",
                    term_end=o.get("term_end"),  # None if current
                    name_variations=o.get("name_variations", []),
                )
                if eo.matches_name(official_name):
                    official = o
                    break

        if not official:
            raise ValueError(f"Official not found: {official_name}")

        # 2. Get all decisions for this jurisdiction
        decisions = self._storage.get_decisions(
            jurisdiction_id=self.jurisdiction,
            since=since,
            until=until,
            limit=1000,  # Get more decisions for comprehensive record
        )

        # 3. Filter decisions where this official voted
        yes_count = 0
        no_count = 0
        abstain_count = 0
        matched_decisions = []

        official_name_lower = official["name"].lower()
        variations = [v.lower() for v in official.get("name_variations", [])]

        for d in decisions:
            # Get vote data - try vote_json first, then vote field
            vote_data = d.get("vote_json") or d.get("vote") or {}

            # Skip if no vote data or vote_results not populated
            if not vote_data:
                continue

            # vote_data could be {"vote_count": "4-1", "passed": true, ...}
            # or it could be vote_results format {"Name": "yes/no/absent"}
            vote_results = vote_data if isinstance(vote_data, dict) else {}

            # Look for this official in the vote results
            official_vote = None
            for voter_name, vote in vote_results.items():
                if vote not in ("yes", "no", "absent"):
                    # This isn't a vote_results entry, skip
                    continue
                voter_lower = voter_name.lower()
                if (official_name_lower in voter_lower or
                    voter_lower in official_name_lower or
                    any(v in voter_lower for v in variations)):
                    official_vote = vote
                    break

            if official_vote is None:
                continue

            # Apply topic filter if specified
            if topic:
                decision_topics = d.get("topics") or []
                topic_lower = topic.lower()
                if not any(topic_lower in t.lower() for t in decision_topics):
                    continue

            # Count the vote
            if official_vote == "yes":
                yes_count += 1
            elif official_vote == "no":
                no_count += 1
            elif official_vote == "absent":
                abstain_count += 1

            # Add to decision list
            matched_decisions.append({
                "decision_id": d.get("id"),
                "title": d.get("title", ""),
                "date": d.get("meeting_date", ""),
                "vote": official_vote,
                "outcome": d.get("outcome", ""),
                "topics": d.get("topics", []),
            })

        return VotingRecord(
            official_id=official["id"],
            official_name=official["name"],
            topic=topic or "all",
            total_votes=yes_count + no_count + abstain_count,
            yes_votes=yes_count,
            no_votes=no_count,
            abstain_votes=abstain_count,
            decisions=matched_decisions,
        )

    # ─────────── BUDGET METHODS ───────────

    def budget(
        self,
        department: Optional[str] = None,
        fund: Optional[str] = None,
        fiscal_year: Optional[str] = None,
        min_amount: Optional[int] = None,
        max_amount: Optional[int] = None,
        limit: Optional[int] = None,
        # Future extensibility for intergovernmental funding (Phase 2)
        # funding_source: Optional[str] = None,      # "federal", "state", "local"
        # cfda_number: Optional[str] = None,         # Federal program identifier
        # include_upstream: bool = False,            # Include federal/state source data
    ) -> List["BudgetItem"]:
        """
        Query municipal budget by department, fund, or amount.

        Returns budget line items from the jurisdiction's adopted budget.
        Amounts are in dollars (converted from internal cents representation).

        Args:
            department: Filter by department name (e.g., "Police", "Fire")
            fund: Filter by fund (e.g., "General Fund", "Enterprise Fund")
            fiscal_year: Filter by fiscal year (e.g., "2025-2026").
                        Defaults to most recent available.
            min_amount: Minimum budgeted amount in dollars
            max_amount: Maximum budgeted amount in dollars
            limit: Maximum number of items to return

        Returns:
            List of BudgetItem with matching budget entries

        Example:
            >>> c = Civic("san-rafael")
            >>> c.budget(department="Police")
            [BudgetItem(department='Police', budgeted_dollars=30870956.0, ...)]

            >>> c.budget(fund="General Fund", min_amount=10_000_000)
            [BudgetItem(department='Police', ...), BudgetItem(department='Fire', ...)]
        """
        # Query storage backend
        results = self._storage.get_budget_items(
            jurisdiction_id=self.jurisdiction,
            fiscal_year=fiscal_year,
            fund=fund,
            department=department,
            limit=limit,
        )

        # Convert to BudgetItem dataclass with amount filtering
        items = []
        for r in results:
            budgeted_cents = r.get("budgeted_cents", 0) or 0
            budgeted_dollars = budgeted_cents / 100

            # Apply client-side amount filtering
            if min_amount is not None and budgeted_dollars < min_amount:
                continue
            if max_amount is not None and budgeted_dollars > max_amount:
                continue

            items.append(
                BudgetItem(
                    id=str(r.get("item_id", "")),
                    fund=r.get("fund", ""),
                    department=r.get("department", ""),
                    program=r.get("program"),
                    line_item=r.get("line_item", ""),
                    budgeted_dollars=budgeted_dollars,
                    revised_dollars=(r.get("revised_cents") or 0) / 100 if r.get("revised_cents") else None,
                    actual_dollars=(r.get("actual_cents") or 0) / 100 if r.get("actual_cents") else None,
                    fiscal_year=r.get("fiscal_year", ""),
                    source_page=r.get("source_page"),
                    notes=r.get("notes"),
                )
            )

        return items

    def budget_summary(
        self,
        fiscal_year: Optional[str] = None,
        group_by: str = "department",
    ) -> List["BudgetSummary"]:
        """
        Get aggregated budget summary grouped by department, fund, or program.

        Args:
            fiscal_year: Fiscal year (e.g., "2025-2026"). Defaults to most recent.
            group_by: Grouping field ("department", "fund", or "program")

        Returns:
            List of BudgetSummary with aggregated totals

        Example:
            >>> c = Civic("san-rafael")
            >>> c.budget_summary(fiscal_year="2025-2026")
            [BudgetSummary(name='Police', budgeted_dollars=30870956.0, item_count=1), ...]
        """
        # Get fiscal year if not specified (use most recent available)
        if fiscal_year is None:
            # Query for any budget item to get the fiscal year
            items = self._storage.get_budget_items(
                jurisdiction_id=self.jurisdiction,
                limit=1,
            )
            if items:
                fiscal_year = items[0].get("fiscal_year", "2025-2026")
            else:
                fiscal_year = "2025-2026"

        results = self._storage.get_budget_summary(
            jurisdiction_id=self.jurisdiction,
            fiscal_year=fiscal_year,
            group_by=group_by,
        )

        return [
            BudgetSummary(
                name=r.get(group_by, "Unknown"),
                budgeted_dollars=(r.get("budgeted_cents") or 0) / 100,
                revised_dollars=(r.get("revised_cents") or 0) / 100 if r.get("revised_cents") else None,
                actual_dollars=(r.get("actual_cents") or 0) / 100 if r.get("actual_cents") else None,
                item_count=r.get("item_count", 0),
            )
            for r in results
        ]

    def funding_flow(
        self,
        program: Optional[str] = None,
        cfda_number: Optional[str] = None,
        budget_item_id: Optional[str] = None,
        fiscal_year: Optional[str] = None,
        min_confidence: float = 0.5,
    ) -> List["FundingFlow"]:
        """
        Trace intergovernmental funding flow from federal → state → city.

        Shows how federal/state dollars flow through the system to city budget items.
        Enables analysis like "what if CDBG cut 20%?" by following the funding chain.

        IMPORTANT: This method returns flows only when explicit linkages exist between
        budget items and federal/state funding sources. Because city budget documents
        rarely contain CFDA numbers or explicit grant identifiers, automatic matching
        is unreliable and this method may return empty results.

        For authoritative federal expenditure data, use `federal_expenditures()` which
        returns audited SEFA data from the Federal Audit Clearinghouse.

        The flow traces:
        1. Federal Award (from USAspending.gov) →
        2. State Pass-Through (from CA Grants Portal, if applicable) →
        3. City Budget Item (local budget)

        Args:
            program: Filter by program name (e.g., "CDBG", "HOME", "FEMA")
            cfda_number: Filter by CFDA number (e.g., "14.218" for CDBG)
            budget_item_id: Trace specific budget item
            fiscal_year: Filter by fiscal year
            min_confidence: Minimum match confidence threshold (0.0-1.0, default 0.5)

        Returns:
            List of FundingFlow objects showing federal→state→city paths.
            Returns empty list if no explicit budget-to-funding linkages exist.

        See Also:
            federal_expenditures(): Returns audited federal spending data (authoritative)
            federal_expenditures_summary(): Aggregated summary of federal spending

        Example:
            >>> c = Civic("san-rafael")
            >>> flows = c.funding_flow(program="CDBG")
            >>> for flow in flows:
            ...     print(f"{flow.budget_description}: ${flow.budget_dollars:,.0f}")
            ...     if flow.federal_dollars:
            ...         print(f"  Federal ({flow.federal_program_name}): ${flow.federal_dollars:,.0f}")
            ...     if flow.state_dollars:
            ...         print(f"  State ({flow.state_agency}): ${flow.state_dollars:,.0f}")
        """
        # Get budget items
        budget_items = self._storage.get_budget_items(
            jurisdiction_id=self.jurisdiction,
            fiscal_year=fiscal_year,
            limit=None,
        )

        # Get funding links (connections between budget & sources)
        funding_links = self._storage.get_budget_funding_links(
            jurisdiction_id=self.jurisdiction,
            budget_item_id=budget_item_id,
            federal_cfda_number=cfda_number,
            limit=None,
        )

        # Get federal awards and state passthroughs
        federal_awards = self._storage.get_federal_awards(
            jurisdiction_id=self.jurisdiction,
            cfda_number=cfda_number,
            limit=None,
        )

        passthroughs = self._storage.get_state_passthrough_funds(
            jurisdiction_id=self.jurisdiction,
            federal_cfda_number=cfda_number,
            limit=None,
        )

        # Build lookup maps
        budget_by_id = {b.get("item_id"): b for b in budget_items}
        awards_by_id = {a.get("award_id"): a for a in federal_awards}
        passthroughs_by_id = {p.get("passthrough_id"): p for p in passthroughs}
        # Also index passthroughs by federal_award_id for cross-referencing
        passthroughs_by_award = {}
        for p in passthroughs:
            award_id = p.get("federal_award_id")
            if award_id:
                passthroughs_by_award.setdefault(award_id, []).append(p)

        # Build flows from links
        flows: List[FundingFlow] = []
        for link in funding_links:
            # Filter by confidence
            confidence = link.get("match_confidence", 0)
            if confidence < min_confidence:
                continue

            budget_item = budget_by_id.get(link.get("budget_item_id"), {})

            # Filter by program name if provided
            if program:
                item_text = " ".join([
                    budget_item.get("program") or "",
                    budget_item.get("line_item") or "",
                    budget_item.get("notes") or "",
                ]).lower()
                if program.lower() not in item_text:
                    continue

            # Get federal award info
            federal_award = awards_by_id.get(link.get("federal_award_id"))

            # Get passthrough info (either direct or via federal award)
            passthrough = passthroughs_by_id.get(link.get("passthrough_id"))
            if not passthrough and federal_award:
                # Try to find passthrough linked to this federal award
                linked_passthroughs = passthroughs_by_award.get(federal_award.get("award_id"), [])
                if linked_passthroughs:
                    passthrough = linked_passthroughs[0]

            # Build flow
            flow = FundingFlow(
                # Budget item
                budget_item_id=link.get("budget_item_id", ""),
                budget_description=budget_item.get("line_item") or budget_item.get("program") or "Unknown",
                budget_dollars=(link.get("budget_cents") or budget_item.get("budgeted_cents") or 0) / 100,
                department=budget_item.get("department"),
                fund=budget_item.get("fund"),
                fiscal_year=budget_item.get("fiscal_year"),
                # Federal
                federal_award_id=federal_award.get("award_id") if federal_award else link.get("federal_award_id"),
                federal_cfda_number=link.get("federal_cfda_number"),
                federal_program_name=federal_award.get("program_name") if federal_award else None,
                federal_agency=federal_award.get("awarding_agency") if federal_award else None,
                federal_dollars=(federal_award.get("amount_cents") or 0) / 100 if federal_award else None,
                federal_period_start=federal_award.get("period_start") if federal_award else None,
                federal_period_end=federal_award.get("period_end") if federal_award else None,
                # State passthrough
                passthrough_id=passthrough.get("passthrough_id") if passthrough else link.get("passthrough_id"),
                state_agency=passthrough.get("state_agency") if passthrough else None,
                state_grant_id=passthrough.get("state_grant_id") if passthrough else link.get("state_grant_id"),
                state_program_name=passthrough.get("state_program_name") if passthrough else None,
                state_dollars=(passthrough.get("local_amount_cents") or 0) / 100 if passthrough else None,
                state_period_start=passthrough.get("period_start") if passthrough else None,
                state_period_end=passthrough.get("period_end") if passthrough else None,
                # Match quality
                match_type=link.get("match_type", "unknown"),
                match_confidence=confidence,
                reconciliation_status=link.get("reconciliation_status", "unverified"),
                variance_dollars=(link.get("variance_cents") or 0) / 100 if link.get("variance_cents") is not None else None,
                variance_percentage=link.get("variance_percentage"),
            )
            flows.append(flow)

        return flows

    def funding_flow_impact(
        self,
        program: Optional[str] = None,
        cfda_number: Optional[str] = None,
        cut_percentage: float = 0.20,
        fiscal_year: Optional[str] = None,
    ) -> FundingFlowImpact:
        """
        Analyze impact of hypothetical funding cut to a federal/state program.

        Shows which budget items would be affected and by how much if a program
        were cut by the specified percentage.

        Args:
            program: Program name to analyze (e.g., "CDBG")
            cfda_number: CFDA number to analyze (e.g., "14.218")
            cut_percentage: Fraction to cut (0.20 = 20% cut, default)
            fiscal_year: Filter by fiscal year

        Returns:
            FundingFlowImpact with affected items and total impact

        Example:
            >>> c = Civic("san-rafael")
            >>> impact = c.funding_flow_impact(program="CDBG", cut_percentage=0.20)
            >>> print(f"20% CDBG cut would impact ${impact.total_impact_dollars:,.0f}")
            >>> for flow in impact.affected_items:
            ...     print(f"  - {flow.department}: ${flow.budget_dollars * 0.20:,.0f}")
        """
        flows = self.funding_flow(
            program=program,
            cfda_number=cfda_number,
            fiscal_year=fiscal_year,
            min_confidence=0.5,
        )

        # Calculate totals
        total_current = sum(f.budget_dollars for f in flows)
        total_impact = total_current * cut_percentage

        # Determine program name for display
        program_name = program or ""
        if not program_name and cfda_number:
            # Try to get program name from first flow
            for f in flows:
                if f.federal_program_name:
                    program_name = f.federal_program_name
                    break
        if not program_name:
            program_name = cfda_number or "Unknown"

        return FundingFlowImpact(
            program_name=program_name,
            cfda_number=cfda_number,
            cut_percentage=cut_percentage,
            total_current_dollars=total_current,
            total_impact_dollars=total_impact,
            affected_items=flows,
        )

    def federal_expenditures(
        self,
        cfda_number: Optional[str] = None,
        audit_year: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List["FederalExpenditure"]:
        """
        Get audited federal expenditures from Single Audit data (FAC).

        This returns authoritative data on how the city actually spent federal funds,
        sourced from the Schedule of Expenditures of Federal Awards (SEFA) in
        the city's annual Single Audit filed with the Federal Audit Clearinghouse.

        This is the recommended method for understanding federal funding because the data
        is audited and verified, unlike `funding_flow()` which relies on estimated
        linkages between budget items and federal awards.

        Args:
            cfda_number: Filter by CFDA/ALN number (e.g., "20.205" for Highway Planning)
            audit_year: Filter by audit fiscal year (e.g., 2023)
            limit: Maximum number of records to return

        Returns:
            List of FederalExpenditure objects with audited spending data

        See Also:
            federal_expenditures_summary(): Aggregated summary by program
            funding_flow(): Budget→federal linkages (requires explicit mappings)

        Example:
            >>> c = Civic("san-rafael")
            >>> expenditures = c.federal_expenditures(audit_year=2023)
            >>> for exp in expenditures:
            ...     print(f"{exp.cfda_number}: ${exp.amount_expended_dollars:,.0f}")
            ...     print(f"  Program: {exp.federal_program_name}")
            93.778: $658,492
              Program: MEDICAL ASSISTANCE PROGRAM
            20.205: $637,452
              Program: HIGHWAY PLANNING AND CONSTRUCTION
        """
        # Try postgres backend first (has federal_audit_expenditures table)
        if hasattr(self._storage, 'get_federal_audit_expenditures'):
            records = self._storage.get_federal_audit_expenditures(
                jurisdiction_id=self.jurisdiction,
                cfda_number=cfda_number,
                audit_year=audit_year,
                limit=limit,
            )

            expenditures = []
            for r in records:
                exp = FederalExpenditure(
                    report_id=r.get("report_id", ""),
                    cfda_number=r.get("cfda_number", ""),
                    audit_year=r.get("audit_year", 0),
                    amount_expended_dollars=(r.get("amount_expended_cents", 0) or 0) / 100,
                    federal_program_total_dollars=(
                        (r.get("federal_program_total_cents") or 0) / 100
                        if r.get("federal_program_total_cents") else None
                    ),
                    cluster_total_dollars=(
                        (r.get("cluster_total_cents") or 0) / 100
                        if r.get("cluster_total_cents") else None
                    ),
                    federal_program_name=r.get("federal_program_name"),
                    cluster_name=r.get("cluster_name"),
                    federal_agency_prefix=r.get("federal_agency_prefix"),
                    is_major=r.get("is_major", False),
                    is_passthrough=r.get("is_passthrough", False),
                    source_url=r.get("source_url"),
                )
                expenditures.append(exp)

            return expenditures

        # Fallback: return empty list if backend doesn't support audit data
        return []

    def federal_expenditures_summary(
        self,
        audit_year: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get summary of federal expenditures by program for a given audit year.

        Provides a quick overview of where federal dollars went.

        Args:
            audit_year: Audit fiscal year (default: most recent available)

        Returns:
            Dict with total, year, and breakdown by CFDA number

        Example:
            >>> c = Civic("san-rafael")
            >>> summary = c.federal_expenditures_summary(audit_year=2023)
            >>> print(f"Total: ${summary['total_dollars']:,.0f}")
            >>> for program in summary['programs']:
            ...     print(f"  {program['cfda']}: ${program['dollars']:,.0f}")
        """
        expenditures = self.federal_expenditures(audit_year=audit_year)

        if not expenditures:
            return {
                "total_dollars": 0,
                "audit_year": audit_year,
                "programs": [],
            }

        # Aggregate by CFDA
        by_cfda: Dict[str, Dict[str, Any]] = {}
        for exp in expenditures:
            cfda = exp.cfda_number
            if cfda not in by_cfda:
                by_cfda[cfda] = {
                    "cfda": cfda,
                    "program_name": exp.federal_program_name,
                    "dollars": 0,
                    "is_major": exp.is_major,
                }
            by_cfda[cfda]["dollars"] += exp.amount_expended_dollars

        programs = sorted(by_cfda.values(), key=lambda x: x["dollars"], reverse=True)
        total = sum(p["dollars"] for p in programs)
        year = expenditures[0].audit_year if expenditures else audit_year

        return {
            "total_dollars": total,
            "audit_year": year,
            "programs": programs,
        }

    def intergovernmental_revenue(
        self,
        fiscal_year: Optional[int] = None,
        source: Optional[str] = None,
    ) -> IntergovernmentalRevenueSummary:
        """
        Get intergovernmental revenue from CA State Controller data.

        This returns federal, state, and county revenue as reported to the CA State
        Controller. Unlike FAC data (which only has federal expenditures and lags
        18-24 months), this source:

        - Includes state and county funding (not in FAC)
        - Has more recent data (FY2024 already available vs FY2023 in FAC)
        - Goes back 20+ years (to FY2003)

        The data comes from the CA State Controller's ByTheNumbers portal
        (bythenumbers.sco.ca.gov), which is the authoritative source for
        California city/county financial data.

        Args:
            fiscal_year: Fiscal year to query (default: most recent available, 2024)
            source: Filter by source ("federal", "state", "county") or None for all

        Returns:
            IntergovernmentalRevenueSummary with totals and line-item details

        Example:
            >>> c = Civic("san-rafael")
            >>> summary = c.intergovernmental_revenue(fiscal_year=2024)
            >>> print(f"Total: ${summary.total_dollars:,.0f}")
            >>> print(f"  Federal: ${summary.federal_total_dollars:,.0f}")
            >>> print(f"  State: ${summary.state_total_dollars:,.0f}")
            >>> print(f"  County: ${summary.county_total_dollars:,.0f}")
            Total: $8,833,401
              Federal: $171,463
              State: $7,753,350
              County: $908,588

        See Also:
            federal_expenditures(): Audited federal spending from FAC (Single Audit)
        """
        from civic_extraction.clients.ca_state_controller import CAStateControllerClient

        # Map jurisdiction to entity name
        entity_name_map = {
            "san-rafael": "San Rafael",
            "city-san-rafael": "San Rafael",
            # Add other jurisdictions as needed
        }

        entity_name = entity_name_map.get(self.jurisdiction)
        if not entity_name:
            # Try extracting from jurisdiction ID (e.g., "city-san-rafael" -> "San Rafael")
            parts = self.jurisdiction.replace("city-", "").replace("-", " ").title()
            entity_name = parts

        # Default to most recent year
        if fiscal_year is None:
            fiscal_year = 2024

        # Create client and fetch data
        client = CAStateControllerClient(
            jurisdiction_id=self.jurisdiction,
            entity_name=entity_name,
        )

        summary_data = client.get_revenue_summary(fiscal_year=fiscal_year)

        # Convert to IntergovernmentalRevenue objects
        details = []
        for d in summary_data.get("details", []):
            # Apply source filter if specified
            if source and d["source"] != source:
                continue

            revenue = IntergovernmentalRevenue(
                fiscal_year=fiscal_year,
                form_table=d["form_table"],
                source=d["source"],
                amount_dollars=d["amount_cents"] / 100,
                category=d.get("category"),
                subcategory=d.get("subcategory_1"),
                line_description=d.get("line_description"),
                entity_name=entity_name,
            )
            details.append(revenue)

        # Build summary
        return IntergovernmentalRevenueSummary(
            fiscal_year=fiscal_year,
            entity_name=entity_name,
            federal_total_dollars=summary_data["federal_total_cents"] / 100,
            state_total_dollars=summary_data["state_total_cents"] / 100,
            county_total_dollars=summary_data["county_total_cents"] / 100,
            undetermined_total_dollars=summary_data["undetermined_total_cents"] / 100,
            total_dollars=summary_data["total_intergovernmental_cents"] / 100,
            details=details,
        )

    # ─────────── ACTION METHODS (Act) ───────────

    def start_something(
        self,
        topic: str,
        title: str,
        description: str,
        location: str = None,
        creator_id: str = "anonymous"
    ) -> Initiative:
        """
        Start a new initiative.

        Creates a user-spawned initiative that others can support.

        Args:
            topic: Topic category (e.g., "traffic safety")
            title: Initiative title (e.g., "Protected bike lane on 4th St")
            description: Full description
            location: Optional location
            creator_id: ID of the creator (default: anonymous)

        Returns:
            Created Initiative
        """
        from civic.actions.initiatives import start_initiative

        result = start_initiative(
            jurisdiction=self.jurisdiction,
            topic=topic,
            title=title,
            description=description,
            creator_id=creator_id,
            location=location,
            db_path=self.db_path,
        )

        # Convert to this module's Initiative type for consistency
        return Initiative(
            id=result.id,
            topic=result.topic,
            title=result.title,
            description=result.description,
            creator_id=result.creator_id,
            jurisdiction=result.jurisdiction,
            location=result.location,
            created_at=result.created_at,
        )

    def add_voice(
        self,
        item_type: str,
        item_id: str,
        stance: str,
        comment: str,
        user_id: str = "anonymous"
    ) -> Voice:
        """
        Add your voice to an item.

        Express support, opposition, or questions about an initiative,
        agenda item, or decision.

        Args:
            item_type: Type of item ("initiative", "agenda_item", "decision")
            item_id: ID of the item
            stance: Your stance ("support", "oppose", "question")
            comment: Your comment
            user_id: ID of the user (default: anonymous)

        Returns:
            Created Voice
        """
        from civic.actions.voices import add_voice as _add_voice

        result = _add_voice(
            item_type=item_type,
            item_id=item_id,
            stance=stance,
            comment=comment,
            user_id=user_id,
            db_path=self.db_path,
        )

        # Convert to this module's Voice type for consistency
        return Voice(
            id=result.id,
            item_type=result.item_type,
            item_id=result.item_id,
            stance=result.stance,
            comment=result.comment,
            created_at=result.created_at,
        )

    def follow(
        self,
        item_type: str,
        item_id: str,
        user_id: str = "anonymous",
        notification_prefs: dict = None
    ) -> Subscription:
        """
        Follow an item for updates.

        Subscribe to notifications about a meeting, initiative,
        topic, or decision.

        Args:
            item_type: Type ("meeting", "initiative", "topic", "decision")
            item_id: ID of the item
            user_id: ID of the user (default: anonymous)
            notification_prefs: Optional notification preferences

        Returns:
            Created Subscription
        """
        from civic.actions.subscriptions import follow_item

        result = follow_item(
            item_type=item_type,
            item_id=item_id,
            user_id=user_id,
            notification_prefs=notification_prefs,
            db_path=self.db_path,
        )

        # Convert to this module's Subscription type for consistency
        return Subscription(
            id=result.id,
            item_type=result.item_type,
            item_id=result.item_id,
            created_at=result.created_at,
        )

    def prepare(self, agenda_item_id: str, user_id: str = None) -> Preparation:
        """
        Get preparation materials for participating.

        Returns context, talking points, allies, and logistics
        for an upcoming agenda item.

        Args:
            agenda_item_id: ID of the agenda item
            user_id: Optional user ID for personalization

        Returns:
            Preparation with context, talking points, allies, logistics
        """
        from civic.actions.preparation import prepare_for_meeting

        result = prepare_for_meeting(
            agenda_item_id=agenda_item_id,
            jurisdiction=self.jurisdiction,
            user_id=user_id,
            db_path=self.db_path,
        )

        # Convert to this module's Preparation type for consistency
        return Preparation(
            agenda_item_id=result.agenda_item_id,
            regulatory_context=result.regulatory_context,
            historical_decisions=result.historical_decisions,
            talking_points=result.talking_points,
            allies=result.allies,
            logistics=result.logistics,
        )

    # ─────────── ORCHESTRATION METHODS (AI) ───────────

    def suggestions(self, user_id: str = None) -> List[Suggestion]:
        """
        Get proactive suggestions.

        AI-driven suggestions based on user interests and system state.
        Returns suggestions for:
        - Upcoming meetings matching interests
        - Trending initiatives gaining momentum
        - Coordination opportunities (for user's initiatives with 5+ supporters)
        - Pending outcomes to report

        Args:
            user_id: Optional user ID for personalization

        Returns:
            List of suggestions sorted by priority
        """
        from civic.orchestrator.suggestions import get_suggestions as _get_suggestions

        results = _get_suggestions(
            jurisdiction=self.jurisdiction,
            user_id=user_id,
            db_path=self.db_path,
        )

        # Convert to this module's Suggestion type for consistency
        return [
            Suggestion(
                type=s.type,
                title=s.title,
                reason=s.reason,
                action=s.action,
                item_id=s.item_id,
            )
            for s in results
        ]

    def coordinate(self, initiative_id: str, action: str) -> CoordinationPlan:
        """
        Request coordination support.

        Uses civic-coordination LangGraph workflows to help groups
        take collective action.

        Args:
            initiative_id: ID of the initiative to coordinate
            action: Action type ("plan_testimony", "draft_letter", etc.)

        Returns:
            CoordinationPlan with steps and participants
        """
        if not COORDINATION_AVAILABLE:
            raise ImportError(
                "civic-coordination not installed. "
                "Install with: pip install civic-coordination"
            )

        # Use civic-coordination LangGraph
        result = run_coordination(self.jurisdiction, initiative_id)

        return CoordinationPlan(
            action=action,
            steps=result.get("steps", []),
            participants=result.get("actors", {}).get("residents", []),
            deadline=result.get("deadline"),
        )

    def report_outcome(
        self,
        item_id: str,
        outcome: str,
        notes: str = None,
        item_type: str = "agenda_item",
        user_id: str = "anonymous",
        vote_breakdown: dict = None
    ) -> Outcome:
        """
        Report outcome of a decision.

        Closes the feedback loop by recording what happened.
        This improves future recommendations.

        Args:
            item_id: ID of the item
            outcome: Result ("passed", "failed", "continued", "modified")
            notes: Optional notes (e.g., "Passed 4-1, starts Q2")
            item_type: Type of item ("initiative", "agenda_item", "decision")
            user_id: ID of the reporter (default: anonymous)
            vote_breakdown: Optional vote breakdown (e.g., {"yes": 4, "no": 1})

        Returns:
            Recorded Outcome
        """
        from civic.orchestrator.outcomes import report_outcome as _report_outcome

        result = _report_outcome(
            item_id=item_id,
            outcome=outcome,
            notes=notes,
            item_type=item_type,
            user_id=user_id,
            vote_breakdown=vote_breakdown,
            db_path=self.db_path,
        )

        # Convert to this module's Outcome type for consistency
        return Outcome(
            item_id=result.item_id,
            outcome=result.outcome,
            notes=result.notes,
            recorded_at=result.recorded_at,
        )
