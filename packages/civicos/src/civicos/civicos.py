"""
Civic - Main Entry Point

The unified interface to the Civic platform.

Usage:
    from civicos import CivicOS

    c = CivicOS("san-rafael-ca")

    # Query (Learn)
    c.what_applies("housing")
    c.what_happened("bike lanes")
    c.whats_next(["transportation"])

    # Coordination (Act) — see civicos-relay package

"""

from typing import Optional, List, Any, Dict, Union, Literal, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime

# Import from internal modules (consolidated)
import logging

from civicos._internal.state import StateManager
from civicos.storage import StorageBackend, StorageStats, SQLiteBackend, get_storage_backend, get_vector_backend
from civicos.storage.data_source import DataSource, LocalDataSource
from civicos.storage.vector import VectorBackend
from civicos.paths import get_state_db_path

if TYPE_CHECKING:
    from civicos.config import CivicOSConfig

logger = logging.getLogger(__name__)

# Optional imports - gracefully degrade if not available
try:
    from civicos._internal.legal import LegalSearch, enrich_opportunity
    LEGAL_AVAILABLE = True
except ImportError:
    LEGAL_AVAILABLE = False
    LegalSearch = None


# ─────────── RESULT TYPES (imported from types.py) ───────────
# Re-exported for backward compatibility with existing imports from civicos.civic

from civicos.types import (
    RegulatoryStack,
    Decision,
    TranscriptExcerpt,
    TranscriptLink,
    DecisionWithContext,
    Meeting,
    UpcomingElection,

    ActionDraft,
    BudgetItem,
    BudgetSummary,
    FundingFlow,
    FundingFlowImpact,
    FederalExpenditure,
    IntergovernmentalRevenue,
    IntergovernmentalRevenueSummary,
    FederalProgram,
)

# HybridSearchResult is imported from history.py (canonical location)
from civicos.history import HybridSearchResult


# ─────────── MAIN CIVIC CLASS ───────────

@dataclass
class CivicOS:
    """
    Main entry point for the Civic platform.

    Wraps civicos-state, civicos-legal, and civicos-coordination packages
    into a unified, query-centric API.

    Usage:
        # String (backward compatible)
        c = CivicOS("san-rafael-ca")

        # Config-driven (turnkey deployment)
        from civicos.config import CivicOSConfig
        config = CivicOSConfig.from_yaml("civicos.yaml")
        c = CivicOS(config)

        # Query and act
        c.what_applies("housing")
        c.whats_next(["transportation"])
    """
    jurisdiction: str  # Accepts str or CivicOSConfig (normalized to str in __post_init__)
    db_path: str = field(default=None)  # Defaults to get_state_db_path() in __post_init__
    _state: StateManager = field(default=None, repr=False)
    _search: Any = field(default=None, repr=False)  # LegalSearch if available
    _storage: StorageBackend = field(default=None, repr=False)  # StorageBackend for stats
    _data_source: DataSource = field(default=None, repr=False)  # DataSource for query abstraction
    _vectors: Optional[VectorBackend] = field(default=None, repr=False)  # VectorBackend for semantic search
    _config: Optional["CivicOSConfig"] = field(default=None, repr=False)  # Config object (if provided)

    def __post_init__(self):
        """Initialize internal services."""
        import os

        # Handle CivicOSConfig input (backward compatible with string)
        from civicos.config import CivicOSConfig
        if isinstance(self.jurisdiction, CivicOSConfig):
            self._config = self.jurisdiction
            self.jurisdiction = self._config.jurisdiction_id
            # Use db_path from config if not explicitly provided
            if self.db_path is None and self._config.db_path:
                self.db_path = self._config.db_path
        else:
            # Normalize jurisdiction ID to canonical format (e.g., "san-rafael" -> "city-san-rafael")
            # Use strict=False to allow unknown jurisdictions (returns empty results instead of raising)
            from civicos._internal.jurisdiction import normalize_jurisdiction
            self.jurisdiction = normalize_jurisdiction(self.jurisdiction, strict=False)

        # Check for DATABASE_URL environment variable for cloud storage
        database_url = os.getenv("DATABASE_URL")

        # Default db_path using get_state_db_path() which respects CIVICOS_DATA_ROOT
        if self.db_path is None:
            self.db_path = get_state_db_path()

        self._state = StateManager(self.db_path)

        # Use get_storage_backend() factory to support both SQLite and Postgres
        # DATABASE_URL takes precedence for cloud deployments
        if database_url:
            self._storage = get_storage_backend(database_url)
        else:
            self._storage = SQLiteBackend(self.db_path)

        # DataSource wraps StorageBackend for read queries (enables future federation)
        self._data_source = LocalDataSource(self._storage)

        # Vector backend for semantic search (pgvector or None for ChromaDB fallback)
        self._vectors = get_vector_backend(database_url)
        if self._vectors:
            logger.debug(
                f"CivicOS({self.jurisdiction}): storage={type(self._storage).__name__}, "
                f"data_source={self._data_source.source_type}, vectors={self._vectors.backend_type}"
            )
        else:
            logger.debug(
                f"CivicOS({self.jurisdiction}): storage={type(self._storage).__name__}, "
                f"data_source={self._data_source.source_type}, vectors=ChromaDB (local fallback)"
            )

        # LegalSearch requires embeddings - make optional
        if LEGAL_AVAILABLE:
            try:
                self._search = LegalSearch()
            except Exception:
                self._search = None

    @property
    def storage(self) -> StorageBackend:
        """Public access to the storage backend."""
        return self._storage

    @property
    def config(self) -> Optional["CivicOSConfig"]:
        """Get the CivicOSConfig if one was provided, or create one from current state."""
        if self._config is not None:
            return self._config
        # Create a config from current state (for introspection)
        from civicos.config import CivicOSConfig
        return CivicOSConfig(
            jurisdiction_id=self.jurisdiction,
            db_path=self.db_path,
        )

    @property
    def display_name(self) -> str:
        """Get human-readable display name for this jurisdiction."""
        if self._config and self._config.display_name:
            return self._config.display_name
        from civicos.jurisdiction import JurisdictionRegistry
        return JurisdictionRegistry.get_display_name(self.jurisdiction, default=self.jurisdiction)

    @property
    def timezone(self) -> str:
        """Get timezone for this jurisdiction."""
        if self._config and self._config.timezone:
            return self._config.timezone
        from civicos.jurisdiction import JurisdictionRegistry
        return JurisdictionRegistry.get_timezone(self.jurisdiction, default="UTC")

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
        return self._data_source.get_stats(jurisdiction_id)

    def get_operating_cost_dashboard(
        self,
        period: str = "month",
        service: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get operating cost dashboard data with aggregation and time-series.

        Returns actual costs logged to operating_costs table (LLM and Modal
        compute). Provides summary totals and daily breakdown for visualization.
        Used by admin dashboards for cost monitoring.

        Args:
            period: Time period - "day", "week", "month", or "all"
            service: Filter by service (modal, openai, anthropic)
            jurisdiction_id: Filter by jurisdiction

        Returns:
            Dictionary with summary (totals, by_service, by_category)
            and time_series (daily breakdown)
        """
        from datetime import timedelta
        from collections import defaultdict

        # Calculate date range based on period
        now = datetime.utcnow()
        if period == "day":
            since = (now - timedelta(days=1)).isoformat()
        elif period == "week":
            since = (now - timedelta(days=7)).isoformat()
        elif period == "month":
            since = (now - timedelta(days=30)).isoformat()
        else:  # "all"
            since = None

        until = now.isoformat()

        # Get summary using data source method
        summary = self._data_source.get_operating_cost_summary(
            service=service,
            jurisdiction_id=jurisdiction_id,
            since=since,
            until=until,
        )

        # Get raw records for time-series aggregation
        records = self._data_source.get_operating_costs(
            service=service,
            jurisdiction_id=jurisdiction_id,
            since=since,
            until=until,
            limit=10000,
        )

        # Aggregate by day for time-series
        daily_costs: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for record in records:
            ts = record.get("timestamp", "")
            if isinstance(ts, str) and len(ts) >= 10:
                date_str = ts[:10]  # YYYY-MM-DD
            else:
                continue
            svc = record.get("service", "unknown")
            amount = float(record.get("amount_usd", 0))
            daily_costs[date_str][svc] += amount
            daily_costs[date_str]["total"] += amount

        # Convert to sorted list
        time_series = [
            {
                "date": date,
                "total_usd": round(costs.pop("total", 0), 6),
                "by_service": {k: round(v, 6) for k, v in costs.items()},
            }
            for date, costs in sorted(daily_costs.items())
        ]

        return {
            "timestamp": now.isoformat() + "Z",
            "period": period,
            "range": {"since": since, "until": until},
            "summary": {
                "total_cost_usd": round(summary["total_cost_usd"], 6),
                "record_count": summary["record_count"],
                "by_service": {k: round(v, 6) for k, v in summary["by_service"].items()},
                "by_category": {k: round(v, 6) for k, v in summary["by_category"].items()},
            },
            "time_series": time_series,
        }

    # ─────────── QUERY METHODS (Learn) ───────────

    def what_applies(
        self,
        topic: str,
        location: str = None,
        *,
        ranking_mode: Literal["section_first", "bill_first", "auto"] = "auto",
        max_results: int = 30,
        min_score: float = 0.4,
        legislation_status: Literal["active", "passed", "pending", "all"] = "active",
    ) -> RegulatoryStack:
        """
        Get regulatory stack for a topic.

        Returns federal, state, and local rules that apply to the topic.
        Queries legislation from storage backend and municipal code from vectors.

        Args:
            topic: The topic to search (e.g., "housing", "bike lanes")
            location: Optional location for local rules
            ranking_mode: How to rank legislation results:
                - "section_first": Rank by chunk similarity (good for broad queries)
                - "bill_first": Rank by bill-level max score (good for specific bills)
                - "auto": Detect based on query (uses bill_first if query has bill numbers)
            max_results: Maximum bills to return (default 30)
            min_score: Minimum similarity score to include (default 0.4)
            legislation_status: Filter legislation by status:
                - "active": Exclude vetoed/failed (default)
                - "passed": Only enacted legislation
                - "pending": In progress bills (status 1-3)
                - "all": Include everything including vetoed/failed

        Returns:
            RegulatoryStack with federal, state, and local context.
            Each bill in state list includes a "tier" field ("primary" for top 10,
            "secondary" for the rest) for pagination support.
        """
        from civicos.context import get_regulatory_context
        result = get_regulatory_context(
            jurisdiction=self.jurisdiction,
            topic=topic,
            location=location,
            storage=self._storage,
            vectors=self._vectors,
            ranking_mode=ranking_mode,
            max_results=max_results,
            min_score=min_score,
            legislation_status=legislation_status,
        )
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

        Uses civicos-state for meeting/decision history with optional
        semantic search via civicos-legal.

        Args:
            query: Search query (e.g., "bike lanes", "housing development")
            since: Optional date filter (ISO format)

        Returns:
            List of matching decisions
        """
        from civicos.history import search_decisions

        results = search_decisions(
            state_manager=self._state,
            jurisdiction=self.jurisdiction,
            query=query,
            since=since,
            vector_backend=self._vectors,  # Explicit backend, no auto-detection
            storage_backend=self._storage,
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
            >>> c = CivicOS("san-rafael")
            >>> results = c.what_happened_full_context("homeless shelter")
            >>> for r in results:
            ...     print(f"{r.decision.title}: {r.decision.outcome}")
            ...     if r.has_transcript:
            ...         for link in r.public_comments:
            ...             print(f"  Public: {link.text[:60]}...")
        """
        from civicos.history import search_decisions_with_context

        results = search_decisions_with_context(
            state_manager=self._state,
            jurisdiction=self.jurisdiction,
            query=query,
            since=since,
            top_k=top_k,
            transcript_excerpts_per_decision=transcript_excerpts_per_decision,
            vector_backend=self._vectors,
            storage_backend=self._storage,
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
        from civicos.history import search_transcripts

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
        from civicos.history import search_transcripts

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
            >>> c = CivicOS("san-rafael")
            >>> results = c.what_happened_with_discussion("shelter funding")
            >>> for r in results:
            ...     if r.source_type == "pdf":
            ...         print(f"[Staff Report p{r.page_start}] {r.text[:100]}")
            ...     else:
            ...         speaker = r.speaker_name or r.speaker
            ...         print(f"[Video @{r.start_timestamp}] {speaker}: {r.text[:100]}")
        """
        from civicos.history import search_hybrid

        results = search_hybrid(
            jurisdiction=self.jurisdiction,
            query=query,
            top_k=top_k,
            agenda_item=agenda_item,
            vector_backend=self._vectors,
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

        # Use start of today for the query to include today's meetings
        # even if they have no specific time (stored as midnight)
        start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Try data source first (abstracts local vs federated)
        try:
            meetings_data = self._data_source.get_meetings(
                jurisdiction_id=self.jurisdiction,
                since=start_of_today,
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
            # Use date comparison for meetings without specific times (stored as midnight)
            if meeting_date.hour == 0 and meeting_date.minute == 0:
                if not (start_of_today.date() <= meeting_date.date() <= cutoff.date()):
                    continue
            else:
                if not (start_of_today <= meeting_date <= cutoff):
                    continue

            # Get agenda items from data source
            meeting_id = m.get("id", "")
            agenda_items = []
            if meeting_id:
                try:
                    agenda_items = self._data_source.get_agenda_items(meeting_id=meeting_id)
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
            elections_data = self._data_source.get_elections(
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
                    deadline_data = self._data_source.get_election_deadlines(
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
            >>> c = CivicOS("san-rafael")
            >>> record = c.get_voting_record("Maribeth Bushey", topic="housing")
            >>> print(f"Voted YES on {record.yes_percentage:.0f}% of housing items")
        """
        from civicos._internal.elections import VotingRecord, ElectedOfficial

        # 1. Find official by name
        official = self._data_source.get_official_by_name(
            jurisdiction_id=self.jurisdiction,
            name=official_name,
        )

        if not official:
            # Try loading elected officials and fuzzy matching
            officials = self._data_source.get_elected_officials(
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
        decisions = self._data_source.get_decisions(
            jurisdiction_id=self.jurisdiction,
            since=since,
            until=until,
            limit=1000,  # Get more decisions for comprehensive record
        )

        # 2.5. If topic specified, use semantic search to find relevant decision IDs
        semantically_relevant_ids: Optional[set] = None
        if topic and self._vectors:
            try:
                semantic_results = self._vectors.search(
                    query=topic,
                    jurisdiction_id=self.jurisdiction,
                    corpus_type="decisions",
                    top_k=100,  # Get many results to capture related decisions
                    min_score=0.3,  # Minimum similarity threshold
                )
                if semantic_results:
                    semantically_relevant_ids = {r.id for r in semantic_results}
            except Exception:
                # Fall back to exact matching if semantic search fails
                pass

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
                decision_id = d.get("id")
                # Use semantic matching if available, fall back to exact topic match
                if semantically_relevant_ids is not None:
                    # Semantic search found relevant decisions - use those
                    if decision_id not in semantically_relevant_ids:
                        continue
                else:
                    # Fall back to exact topic array matching
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
            >>> c = CivicOS("san-rafael")
            >>> c.budget(department="Police")
            [BudgetItem(department='Police', budgeted_dollars=30870956.0, ...)]

            >>> c.budget(fund="General Fund", min_amount=10_000_000)
            [BudgetItem(department='Police', ...), BudgetItem(department='Fire', ...)]
        """
        # Query data source
        results = self._data_source.get_budget_items(
            jurisdiction_id=self.jurisdiction,
            fiscal_year=fiscal_year,
            department=department,
            limit=limit,
        )

        # Additional client-side filtering by fund (DataSource interface is simpler)
        if fund:
            results = [r for r in results if r.get("fund", "").lower() == fund.lower()]

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
                    source_url=r.get("source_url"),
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
            >>> c = CivicOS("san-rafael")
            >>> c.budget_summary(fiscal_year="2025-2026")
            [BudgetSummary(name='Police', budgeted_dollars=30870956.0, item_count=1), ...]
        """
        # Get fiscal year if not specified (use most recent available)
        if fiscal_year is None:
            # Query for any budget item to get the fiscal year
            items = self._data_source.get_budget_items(
                jurisdiction_id=self.jurisdiction,
                limit=1,
            )
            if items:
                fiscal_year = items[0].get("fiscal_year", "2025-2026")
            else:
                fiscal_year = "2025-2026"

        results = self._data_source.get_budget_summary(
            jurisdiction_id=self.jurisdiction,
            fiscal_year=fiscal_year,
        )

        # Client-side grouping if needed (DataSource returns flat summary)
        if group_by != "department":
            # Re-query raw items and group client-side
            items = self._data_source.get_budget_items(
                jurisdiction_id=self.jurisdiction,
                fiscal_year=fiscal_year,
            )
            grouped = {}
            for item in items:
                key = item.get(group_by, "Unknown")
                if key not in grouped:
                    grouped[key] = {"budgeted_cents": 0, "revised_cents": 0, "actual_cents": 0, "item_count": 0}
                grouped[key]["budgeted_cents"] += item.get("budgeted_cents", 0) or 0
                grouped[key]["revised_cents"] += item.get("revised_cents", 0) or 0
                grouped[key]["actual_cents"] += item.get("actual_cents", 0) or 0
                grouped[key]["item_count"] += 1
            results = [{group_by: k, **v} for k, v in grouped.items()]

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
        Trace intergovernmental funding flow from federal -> state -> city.

        Shows how federal/state dollars flow through the system to city budget items.
        Enables analysis like "what if CDBG cut 20%?" by following the funding chain.

        IMPORTANT: This method returns flows only when explicit linkages exist between
        budget items and federal/state funding sources. Because city budget documents
        rarely contain CFDA numbers or explicit grant identifiers, automatic matching
        is unreliable and this method may return empty results.

        For authoritative federal expenditure data, use `federal_expenditures()` which
        returns audited SEFA data from the Federal Audit Clearinghouse.

        The flow traces:
        1. Federal Award (from USAspending.gov) ->
        2. State Pass-Through (from CA Grants Portal, if applicable) ->
        3. City Budget Item (local budget)

        Args:
            program: Filter by program name (e.g., "CDBG", "HOME", "FEMA")
            cfda_number: Filter by CFDA number (e.g., "14.218" for CDBG)
            budget_item_id: Trace specific budget item
            fiscal_year: Filter by fiscal year
            min_confidence: Minimum match confidence threshold (0.0-1.0, default 0.5)

        Returns:
            List of FundingFlow objects showing federal->state->city paths.
            Returns empty list if no explicit budget-to-funding linkages exist.

        See Also:
            federal_expenditures(): Returns audited federal spending data (authoritative)
            federal_expenditures_summary(): Aggregated summary of federal spending

        Example:
            >>> c = CivicOS("san-rafael")
            >>> flows = c.funding_flow(program="CDBG")
            >>> for flow in flows:
            ...     print(f"{flow.budget_description}: ${flow.budget_dollars:,.0f}")
            ...     if flow.federal_dollars:
            ...         print(f"  Federal ({flow.federal_program_name}): ${flow.federal_dollars:,.0f}")
            ...     if flow.state_dollars:
            ...         print(f"  State ({flow.state_agency}): ${flow.state_dollars:,.0f}")
        """
        # Get budget items
        budget_items = self._data_source.get_budget_items(
            jurisdiction_id=self.jurisdiction,
            fiscal_year=fiscal_year,
            limit=None,
        )

        # Get funding links (connections between budget & sources)
        funding_links = self._data_source.get_budget_funding_links(
            jurisdiction_id=self.jurisdiction,
            budget_item_id=budget_item_id,
            federal_cfda_number=cfda_number,
            fiscal_year=fiscal_year,
        )

        # Get federal awards and state passthroughs
        federal_awards = self._data_source.get_federal_awards(
            jurisdiction_id=self.jurisdiction,
            cfda_number=cfda_number,
            limit=None,
        )

        passthroughs = self._data_source.get_state_passthrough_funds(
            jurisdiction_id=self.jurisdiction,
            limit=None,
        )
        # Filter by cfda_number client-side (StorageBackend uses federal_cfda_number param)
        if cfda_number:
            passthroughs = [p for p in passthroughs if p.get("federal_cfda_number") == cfda_number]

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
            >>> c = CivicOS("san-rafael")
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
            funding_flow(): Budget->federal linkages (requires explicit mappings)

        Example:
            >>> c = CivicOS("san-rafael")
            >>> expenditures = c.federal_expenditures(audit_year=2023)
            >>> for exp in expenditures:
            ...     print(f"{exp.cfda_number}: ${exp.amount_expended_dollars:,.0f}")
            ...     print(f"  Program: {exp.federal_program_name}")
            93.778: $658,492
              Program: MEDICAL ASSISTANCE PROGRAM
            20.205: $637,452
              Program: HIGHWAY PLANNING AND CONSTRUCTION
        """
        # Try data source (has federal_audit_expenditures via StorageBackend)
        records = self._data_source.get_federal_audit_expenditures(
            jurisdiction_id=self.jurisdiction,
            audit_year=str(audit_year) if audit_year else None,
            limit=limit,
        )
        # Filter by cfda_number client-side if needed
        if cfda_number:
            records = [r for r in records if r.get("cfda_number") == cfda_number]

        if records:

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
            >>> c = CivicOS("san-rafael")
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
                    "source_url": exp.source_url,
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
            >>> c = CivicOS("san-rafael")
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
        from civicos_extraction.clients.ca_state_controller import CAStateControllerClient

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

    # ─────────── AI DRAFT GENERATION ───────────

    def draft_action(
        self,
        action_type: str,
        topic: str,
        description: str,
        target: Optional[str] = None,
        template: Optional[str] = None,
    ) -> ActionDraft:
        """
        Generate an AI draft for a civic action.

        Uses recent decisions as context and Claude Haiku for generation.
        Supports written_comment, public_comment, and contact_official types.

        Args:
            action_type: One of written_comment, public_comment, contact_official
            topic: Initiative topic (e.g., "affordable housing")
            description: Action description or initiative context
            target: Who to address (email, name, body)
            template: Existing talking points to build on

        Returns:
            ActionDraft with generated text, optional description, and citations
        """
        import os

        valid_types = {"written_comment", "public_comment", "contact_official"}
        if action_type not in valid_types:
            raise ValueError(f"Invalid action_type '{action_type}'. Valid: {', '.join(sorted(valid_types))}")

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")

        # Gather context from recent decisions (lightweight DB query)
        citations = []
        context_parts = []

        try:
            all_decisions = self._storage.get_decisions(
                jurisdiction_id=self.jurisdiction, limit=50
            )
            topic_lower = topic.lower()
            keywords = topic_lower.split()
            matched = [
                d for d in all_decisions
                if any(
                    kw in (d.get("title") or "").lower() or kw in (d.get("body") or "").lower()
                    for kw in keywords
                )
            ]
            relevant = matched[:5] if matched else all_decisions[:3]
            for d in relevant:
                title = d.get("title", "")
                outcome = d.get("outcome", "")
                body = d.get("body", "")
                if title:
                    entry = f"- {title}"
                    if outcome:
                        entry += f" (Outcome: {outcome})"
                    if body:
                        entry += f"\n  {body[:200]}"
                    context_parts.append(entry)
                    citations.append(title)
        except Exception as e:
            logger.warning(f"draft_action: decisions query error: {e}")

        rag_context = "\n\n".join(context_parts) if context_parts else "No specific context available."

        # Build prompt
        type_instructions = {
            "written_comment": "Write a formal written comment (2-3 paragraphs) suitable for submission to a city body." + (f" Address it to: {target}." if target else ""),
            "public_comment": "Write 2-minute speaking points in bullet format (~300 words) for delivering public comment at a city meeting.",
            "contact_official": "Write a concise email draft (1-2 paragraphs) to a city official." + (f" Address it to: {target}." if target else ""),
        }
        action_type_labels = {
            "written_comment": "Submit a written comment",
            "public_comment": "Deliver public comment",
            "contact_official": "Email city official",
        }

        template_section = ""
        if template:
            template_section = f"\nThe user provided these talking points or draft text to build on:\n{template}\n"

        prompt = f"""You are helping a resident write a civic communication about: {topic}

Action: {description}
{template_section}
{type_instructions[action_type]}

Use this context from actual city records to make the draft specific and well-informed:

{rag_context}

Guidelines:
- Write in first person as a concerned resident
- Be specific — reference actual decisions, code sections, or facts from the context
- Maintain a respectful, constructive tone
- Do not make up facts not supported by the provided context
- Do not include placeholders like [YOUR NAME] — the user will personalize it

IMPORTANT: Start your response with a one-line action description (max 80 chars) on its own line, then a blank line, then the full draft. The action description should be a short imperative like "{action_type_labels.get(action_type, 'Take action')} about [specific topic]". Do NOT include any label or prefix on the description line."""

        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        # Parse description from first line
        parts = text.split("\n", 1)
        if len(parts) == 2 and len(parts[0]) <= 120:
            action_desc = parts[0].strip()
            draft = parts[1].strip()
        else:
            action_desc = None
            draft = text

        return ActionDraft(draft=draft, description=action_desc, citations=citations)

