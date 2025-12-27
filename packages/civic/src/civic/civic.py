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

from typing import Optional, List, Any
from dataclasses import dataclass, field
from datetime import datetime

# Import from internal modules (consolidated)
from civic._internal.state import StateManager
from civic.storage import StorageBackend, StorageStats, SQLiteBackend, get_storage_backend
from civic.paths import get_state_db_path

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

    def whats_next(self, topics: List[str] = None, days: int = 30) -> List[Meeting]:
        """
        Get upcoming meetings matching topics.

        Uses civic-state StateManager to query meetings.

        Args:
            topics: Optional list of topics to filter by
            days: Number of days to look ahead (default 30)

        Returns:
            List of upcoming meetings
        """
        # Get city state from StateManager
        state = self._state.get_city_state(self.jurisdiction)

        if state is None:
            return []

        meetings_data = state.get("meetings", [])

        # Convert to Meeting objects
        meetings = []
        for m in meetings_data:
            # Parse meeting_datetime (from StateManager) or fall back to date
            meeting_date = m.get("meeting_datetime") or m.get("date")
            if isinstance(meeting_date, str):
                try:
                    meeting_date = datetime.fromisoformat(meeting_date.replace('Z', '+00:00'))
                except ValueError:
                    meeting_date = datetime.now()
            elif meeting_date is None:
                meeting_date = datetime.now()

            # Get agenda items: prefer relational (m.agenda_items) over embedded (full_data)
            # Relational items have project_type; embedded have topic
            agenda_items = m.get("agenda_items", [])
            if not agenda_items:
                # Fall back to full_data if relational items not available
                full_data = m.get("full_data", {})
                if isinstance(full_data, str):
                    import json
                    try:
                        full_data = json.loads(full_data)
                    except (json.JSONDecodeError, TypeError):
                        full_data = {}
                agenda_items = full_data.get("agenda_items", [])

            meetings.append(Meeting(
                id=m.get("id", ""),
                title=m.get("title", ""),
                date=meeting_date,
                body=m.get("meeting_type", ""),
                agenda_items=agenda_items,
                location=m.get("location"),
            ))

        # Filter by days (only include meetings within the window)
        from datetime import timedelta, timezone
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days)

        def in_window(meeting_date):
            # Make naive datetime UTC-aware for comparison
            if meeting_date.tzinfo is None:
                meeting_date = meeting_date.replace(tzinfo=timezone.utc)
            return now <= meeting_date <= cutoff

        meetings = [m for m in meetings if in_window(m.date)]

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

        # Sort by date
        meetings.sort(key=lambda x: x.date)

        return meetings

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
