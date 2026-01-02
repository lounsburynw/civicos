"""
StorageBackend protocol for primary data persistence.

Defines the interface for CRUD operations on civic data (SQLite, Postgres).
Part of the 4-stage pipeline: discover -> ingest -> store -> index.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class StorageStats:
    """
    Statistics for a storage backend.

    Used by dashboards to show storage utilization and health.
    """

    jurisdiction_id: str
    meeting_count: int
    agenda_item_count: int

    # Temporal info
    earliest_meeting: Optional[datetime] = None
    latest_meeting: Optional[datetime] = None
    last_updated: Optional[datetime] = None

    # Size metrics (optional, backend-specific)
    size_bytes: Optional[int] = None

    # Extra backend-specific stats
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "meeting_count": self.meeting_count,
            "agenda_item_count": self.agenda_item_count,
            "earliest_meeting": (
                self.earliest_meeting.isoformat() if self.earliest_meeting else None
            ),
            "latest_meeting": (
                self.latest_meeting.isoformat() if self.latest_meeting else None
            ),
            "last_updated": (
                self.last_updated.isoformat() if self.last_updated else None
            ),
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
        }


@dataclass
class StorageValidationResult:
    """
    Result of storage backend validation.

    Preflight check for database connectivity and schema.
    """

    is_valid: bool  # All checks passed
    connected: bool  # Can connect to database
    schema_valid: bool  # Schema exists and is correct version

    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    check_duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_valid": self.is_valid,
            "connected": self.connected,
            "schema_valid": self.schema_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "check_duration_ms": self.check_duration_ms,
        }


@runtime_checkable
class StorageBackend(Protocol):
    """
    Protocol for primary data storage (SQLite, Postgres).

    Handles CRUD operations for meetings and agenda items with
    temporal versioning support. Part of the 4-stage pipeline.

    Implementations:
    - SQLiteBackend: Wraps StateManager for local development
    - PostgresBackend: Direct Postgres connection for production

    Usage:
        backend = SQLiteBackend("civic.db")

        # Validate before use
        result = backend.validate()
        if not result.is_valid:
            raise RuntimeError(result.errors)

        # Store meetings from ingestion
        count = backend.store_meetings(
            jurisdiction_id="city-san-rafael",
            meetings=normalized_meetings,
            as_of=datetime.now()
        )

        # Retrieve for indexing
        meetings = backend.get_meetings(
            jurisdiction_id="city-san-rafael"
        )
    """

    @property
    def backend_type(self) -> str:
        """Type identifier: 'sqlite', 'postgres'."""
        ...

    def validate(self) -> StorageValidationResult:
        """
        Validate storage backend connectivity and schema.

        Preflight check that fails fast with clear error messages for:
        - Database connectivity issues
        - Missing or invalid schema
        - Permission problems

        Returns:
            StorageValidationResult with is_valid, errors, warnings
        """
        ...

    def store_meetings(
        self,
        jurisdiction_id: str,
        meetings: List[Any],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store meetings with temporal versioning.

        Atomic operation: either all meetings are stored or none.
        Updates existing meetings if IDs match, inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            meetings: List of normalized Meeting objects
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of meetings successfully stored

        Raises:
            StorageError: If atomic store operation fails
        """
        ...

    def get_meetings(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve meetings with optional temporal query.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            since: Filter meetings after this datetime
            until: Filter meetings before this datetime
            limit: Maximum number of meetings to return

        Returns:
            List of meeting dictionaries ready for indexing
        """
        ...

    def get_stats(self, jurisdiction_id: str) -> StorageStats:
        """
        Get storage statistics for a jurisdiction.

        Used by dashboards and monitoring.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            StorageStats with counts and temporal info
        """
        ...

    def delete_meetings(
        self,
        jurisdiction_id: str,
        meeting_ids: Optional[List[str]] = None,
    ) -> int:
        """
        Delete meetings (soft delete with temporal versioning).

        If meeting_ids is None, deletes all meetings for jurisdiction.
        This is a soft delete - data can be recovered via temporal queries.

        Args:
            jurisdiction_id: Target jurisdiction
            meeting_ids: Specific meetings to delete (None = all)

        Returns:
            Number of meetings deleted
        """
        ...

    # ========== Operation Tracking Methods ==========
    #
    # Operations are long-running tasks (fetch_meetings, discover_videos, etc.)
    # that need progress tracking and history for admin dashboards.
    #
    # Status values: 'pending', 'running', 'completed', 'failed'

    def create_operation(
        self,
        operation_id: str,
        jurisdiction_id: str,
        name: str,
    ) -> Dict[str, Any]:
        """
        Create a new operation record with 'pending' status.

        Args:
            operation_id: Unique operation ID (UUID)
            jurisdiction_id: City identifier (e.g., "city-san-rafael")
            name: Operation name (fetch_meetings, discover_videos, etc.)

        Returns:
            Dict with operation record containing:
            - id, jurisdiction_id, name, status, started_at
            - progress_percent, items_processed, items_total (all 0)
        """
        ...

    def update_operation_status(
        self,
        operation_id: str,
        status: str,
        current_step: Optional[str] = None,
        progress_percent: Optional[float] = None,
        items_processed: Optional[int] = None,
        items_total: Optional[int] = None,
    ) -> bool:
        """
        Update operation progress.

        Args:
            operation_id: Operation ID
            status: New status ('pending', 'running', 'completed', 'failed')
            current_step: Description of current step (e.g., "Fetching page 3")
            progress_percent: Progress percentage (0-100)
            items_processed: Number of items processed so far
            items_total: Total items to process

        Returns:
            True if update succeeded, False if operation not found
        """
        ...

    def complete_operation(
        self,
        operation_id: str,
        result: Dict[str, Any],
        error: Optional[str] = None,
    ) -> bool:
        """
        Mark operation as completed (success or failure).

        Sets status to 'completed' (success) or 'failed' (if error provided).
        Calculates duration_seconds from started_at to now.
        Sets progress_percent to 100.

        Args:
            operation_id: Operation ID
            result: Result dictionary to store as JSON
            error: Error message if failed (triggers 'failed' status)

        Returns:
            True if update succeeded, False if operation not found
        """
        ...

    def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """
        Get operation by ID.

        Args:
            operation_id: Operation ID

        Returns:
            Operation dict with parsed result field, or None if not found.
            Dict includes: id, jurisdiction_id, name, status, started_at,
            completed_at, result, error, duration_seconds, current_step,
            progress_percent, items_processed, items_total
        """
        ...

    def get_operations(
        self,
        jurisdiction_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Query operations with optional filters.

        Args:
            jurisdiction_id: Filter by jurisdiction (None = all)
            status: Filter by status (None = all)
            limit: Max results (default 20)

        Returns:
            List of operation dicts, most recent first (by started_at)
        """
        ...

    # ========== Decision Methods ==========
    #
    # Decisions are extracted from meeting minutes and stored for
    # what_happened() queries and vector indexing.

    def store_decisions(
        self,
        jurisdiction_id: str,
        decisions: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store decisions with temporal versioning.

        Atomic operation: either all decisions are stored or none.
        Updates existing decisions if IDs match, inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            decisions: List of decision dictionaries
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of decisions successfully stored
        """
        ...

    def get_decisions(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve decisions with optional filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            since: Filter decisions on/after this date (YYYY-MM-DD)
            until: Filter decisions on/before this date (YYYY-MM-DD)
            limit: Maximum number of decisions to return

        Returns:
            List of decision dictionaries
        """
        ...

    def get_decision_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current decisions for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) decisions
        """
        ...

    # ========== Chunk Methods ==========
    #
    # Chunks are PDF text segments from agenda packets, stored for
    # RAG retrieval and semantic search.

    def store_chunks(
        self,
        jurisdiction_id: str,
        chunks: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        meeting_id: Optional[str] = None,
    ) -> int:
        """
        Store PDF chunks with temporal versioning.

        Atomic operation: either all chunks are stored or none.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            chunks: List of chunk dictionaries with text, agenda_item, etc.
            as_of: Timestamp for temporal versioning (default: now)
            meeting_id: Optional meeting ID to associate chunks with

        Returns:
            Number of chunks successfully stored
        """
        ...

    def get_chunks(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        meeting_id: Optional[str] = None,
        agenda_item: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve chunks with optional filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            meeting_id: Filter by meeting ID
            agenda_item: Filter by agenda item
            source_type: Filter by source type (agenda_packet, staff_report)
            limit: Maximum number of chunks to return

        Returns:
            List of chunk dictionaries
        """
        ...

    def get_chunk_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current chunks for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) chunks
        """
        ...

    # ========== Issue Methods (SESSION 385) ==========
    #
    # Issues are 311 complaints from providers like SeeClickFix, PublicStuff, etc.
    # Stored with provider field for multi-source queries.

    def store_issues(
        self,
        jurisdiction_id: str,
        issues: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store 311 issues with temporal versioning.

        Atomic operation: either all issues are stored or none.
        Uses upsert semantics based on (provider, external_id).

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            issues: List of issue dictionaries (from NormalizedIssue.to_dict())
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of issues successfully stored
        """
        ...

    def get_issues(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        provider: Optional[str] = None,
        status: Optional[str] = None,
        issue_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve 311 issues with optional filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            provider: Filter by provider ("seeclickfix", "publicstuff", etc.)
            status: Filter by status ("open", "closed", "acknowledged")
            issue_type: Filter by issue type
            limit: Maximum number of issues to return

        Returns:
            List of issue dictionaries
        """
        ...

    def get_issue_count(self, jurisdiction_id: str, provider: Optional[str] = None) -> int:
        """
        Get count of current issues for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction
            provider: Optional filter by provider

        Returns:
            Number of current (non-expired) issues
        """
        ...

    # ========== Municipal Code Methods ==========

    def store_municipal_code(
        self,
        jurisdiction_id: str,
        sections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store municipal code sections with temporal versioning.

        Atomic operation: either all sections are stored or none.
        Uses upsert semantics - closes previous versions and inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            sections: List of section dictionaries with section_number, section_title, etc.
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of sections successfully stored
        """
        ...

    def get_municipal_code(
        self,
        jurisdiction_id: str,
        chapter: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve municipal code sections with temporal filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            chapter: Filter to specific chapter (e.g., "1.04")
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of sections to return

        Returns:
            List of section dictionaries
        """
        ...

    def get_municipal_code_section(
        self,
        jurisdiction_id: str,
        section_number: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific municipal code section by section number.

        Args:
            jurisdiction_id: Target jurisdiction
            section_number: Section identifier (e.g., "1.04.010")
            as_of: Point-in-time query (for temporal versioning)

        Returns:
            Section dictionary or None if not found
        """
        ...

    def get_municipal_code_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current municipal code sections for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) sections
        """
        ...

    # ========== Video Methods ==========
    #
    # Videos are YouTube recordings of city council meetings.
    # Source data for transcript extraction.

    def store_videos(
        self,
        jurisdiction_id: str,
        videos: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store YouTube video metadata with temporal versioning.

        Atomic operation: either all videos are stored or none.
        Uses upsert semantics - closes previous versions and inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            videos: List of video dictionaries with id, meeting_url, title, date, youtube_url
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of videos successfully stored
        """
        ...

    def get_videos(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve videos with temporal filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of videos to return

        Returns:
            List of video dictionaries
        """
        ...

    def get_video_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current videos for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) videos
        """
        ...

    # ========== Transcript Methods ==========
    #
    # Transcripts are AssemblyAI-processed audio from meeting videos.
    # Used for what_happened() queries and semantic search.

    def store_transcripts(
        self,
        jurisdiction_id: str,
        transcripts: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store AssemblyAI transcripts with temporal versioning.

        Atomic operation: either all transcripts are stored or none.
        Uses upsert semantics - closes previous versions and inserts new ones.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
            transcripts: List of transcript dictionaries with video_id, utterances, etc.
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of transcripts successfully stored
        """
        ...

    def get_transcripts(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve transcripts with temporal filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of transcripts to return

        Returns:
            List of transcript dictionaries
        """
        ...

    def get_transcript(
        self,
        video_id: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific transcript by video_id.

        Args:
            video_id: YouTube video ID
            as_of: Point-in-time query (for temporal versioning)

        Returns:
            Transcript dictionary or None if not found
        """
        ...

    def get_transcript_count(self, jurisdiction_id: str) -> int:
        """
        Get count of current transcripts for a jurisdiction.

        Args:
            jurisdiction_id: Target jurisdiction

        Returns:
            Number of current (non-expired) transcripts
        """
        ...

    # ========== ETL Cost Methods ==========
    #
    # ETL costs track API usage and processing costs for ingestion operations.
    # Used for budget monitoring and optimization.

    def store_etl_cost(
        self,
        pipeline: str,
        jurisdiction_id: str,
        items_processed: int,
        cost_usd: float,
        duration_seconds: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> int:
        """
        Store ETL cost record for tracking pipeline expenses.

        Args:
            pipeline: Pipeline name (e.g., "transcribe_video", "ingest_meetings")
            jurisdiction_id: Target jurisdiction
            items_processed: Number of items processed in this run
            cost_usd: Cost in USD
            duration_seconds: Optional duration of the pipeline run
            notes: Optional notes about the run

        Returns:
            ID of the stored cost record
        """
        ...

    def get_etl_costs(
        self,
        jurisdiction_id: Optional[str] = None,
        pipeline: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve ETL cost records with optional filtering.

        Args:
            jurisdiction_id: Filter by jurisdiction (optional)
            pipeline: Filter by pipeline name (optional)
            limit: Maximum records to return (default 100)

        Returns:
            List of cost record dictionaries
        """
        ...

    def get_etl_cost_summary(
        self,
        jurisdiction_id: Optional[str] = None,
        pipeline: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get aggregated ETL cost summary.

        Args:
            jurisdiction_id: Filter by jurisdiction (optional)
            pipeline: Filter by pipeline name (optional)

        Returns:
            Dictionary with total_cost_usd, total_items, run_count
        """
        ...

    # ========== Legislation Methods ==========
    #
    # Legislation includes state and federal bills that may affect local
    # jurisdictions. Used for what_applies() queries and proactive alerts.

    def store_legislation(
        self,
        state: str,
        bills: List[Dict[str, Any]],
        topic: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> int:
        """
        Store state/federal legislation with temporal versioning.

        Atomic operation: either all bills are stored or none.
        Uses upsert semantics based on (bill_id, state).

        Args:
            state: State code (e.g., "CA", "US" for federal)
            bills: List of bill dictionaries with bill_id, bill_name, etc.
            topic: Optional topic to tag all bills with (e.g., "housing")
            as_of: Timestamp for temporal versioning (default: now)

        Returns:
            Number of bills successfully stored
        """
        ...

    def get_legislation(
        self,
        state: str,
        topic: Optional[str] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve legislation with optional filtering.

        Args:
            state: State code (e.g., "CA", "US")
            topic: Filter by topic (e.g., "housing")
            status: Filter by status (e.g., "Active", "Enacted")
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of bills to return

        Returns:
            List of bill dictionaries
        """
        ...

    def get_legislation_by_bill_id(
        self,
        state: str,
        bill_id: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get specific legislation by bill_id.

        Args:
            state: State code (e.g., "CA")
            bill_id: Bill identifier (e.g., "ca-sb9")
            as_of: Point-in-time query (for temporal versioning)

        Returns:
            Bill dictionary or None if not found
        """
        ...

    def get_legislation_count(self, state: str, topic: Optional[str] = None) -> int:
        """
        Get count of current legislation for a state.

        Args:
            state: State code (e.g., "CA")
            topic: Optional filter by topic

        Returns:
            Number of current (non-expired) bills
        """
        ...

    def update_legislation_text(
        self,
        state: str,
        updates: List[Dict[str, Any]],
    ) -> int:
        """
        Update full_text for legislation bills.

        Args:
            state: State code (e.g., "CA")
            updates: List of dicts with 'bill_id' and 'full_text'

        Returns:
            Number of bills updated
        """
        ...

    # ========== Codified Law Methods ==========
    #
    # Codified law includes U.S. Code and state codes (e.g., California Codes).
    # Used for what_applies() queries to find applicable federal/state law.

    def store_codified_law(
        self,
        jurisdiction_id: str,
        sections: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        use_copy: bool = True,
    ) -> int:
        """
        Store codified law sections (U.S. Code, CA Codes) with temporal versioning.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "federal-US", "state-CA")
            sections: List of section dictionaries with citation, title_number, etc.
            as_of: Timestamp for temporal versioning (default: now)
            use_copy: If True (default), use COPY for bulk inserts

        Returns:
            Number of sections successfully stored
        """
        ...

    def get_codified_law(
        self,
        jurisdiction_id: str,
        title_number: Optional[int] = None,
        status: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve codified law sections with optional filtering.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "federal-US", "state-CA")
            title_number: Filter by title number (e.g., 42 for Title 42)
            status: Filter by status (None for active, "repealed" for repealed)
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of sections to return

        Returns:
            List of section dictionaries
        """
        ...

    def search_codified_law(
        self,
        jurisdiction_id: str,
        query: str,
        title_number: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search codified law sections by topic/keyword.

        Uses full-text search for relevance ranking.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "federal-US")
            query: Search query (topic keywords)
            title_number: Optional filter by title number
            limit: Maximum results to return

        Returns:
            List of matching sections with relevance scores
        """
        ...

    def get_codified_law_count(
        self,
        jurisdiction_id: str,
        title_number: Optional[int] = None,
        include_inactive: bool = False,
    ) -> int:
        """
        Get count of current codified law sections for a jurisdiction.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "federal-US")
            title_number: Optional filter by title number
            include_inactive: Whether to include repealed/omitted sections

        Returns:
            Number of current (non-expired) sections
        """
        ...

    # ========== Executive Orders Methods ==========
    #
    # Executive Orders from the Federal Register. Federal-level corpus
    # without jurisdiction_id since EOs apply nationally.

    def store_executive_orders(
        self,
        orders: List[Dict[str, Any]],
        use_copy: bool = True,
    ) -> int:
        """
        Store Executive Orders from Federal Register API.

        Args:
            orders: List of order dictionaries with fields:
                - eo_number: Executive Order number (may be None)
                - document_number: FR document number (unique key)
                - title, abstract, full_text, president, etc.
            use_copy: If True (default), use COPY for bulk inserts

        Returns:
            Number of orders successfully stored
        """
        ...

    def get_executive_orders(
        self,
        president: Optional[str] = None,
        eo_number: Optional[int] = None,
        status: Optional[str] = None,
        signing_date_after: Optional[date] = None,
        signing_date_before: Optional[date] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve Executive Orders with optional filtering.

        Args:
            president: Filter by president name
            eo_number: Filter by specific EO number
            status: Filter by status ("active", "revoked", "superseded")
            signing_date_after: Filter orders signed after this date
            signing_date_before: Filter orders signed before this date
            limit: Maximum number of orders to return

        Returns:
            List of order dictionaries
        """
        ...

    def search_executive_orders(
        self,
        query: str,
        president: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search Executive Orders by topic/keyword.

        Uses full-text search for relevance ranking.

        Args:
            query: Search query (topic keywords)
            president: Optional filter by president
            limit: Maximum results to return

        Returns:
            List of matching orders with relevance scores
        """
        ...

    def get_executive_orders_count(
        self,
        president: Optional[str] = None,
        status: Optional[str] = None,
    ) -> int:
        """
        Get count of Executive Orders.

        Args:
            president: Optional filter by president name
            status: Optional filter by status

        Returns:
            Number of matching orders
        """
        ...

    # ========== Budget Items Methods (Municipal/County Budget Line Items) ==========

    def store_budget_items(
        self,
        jurisdiction_id: str,
        items: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        use_copy: bool = True,
    ) -> int:
        """
        Store budget line items with temporal versioning.

        Budget items track municipal/county spending by department, fund, and program.
        Amounts are stored in cents to avoid floating-point precision issues.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            items: List of budget item dictionaries with keys:
                - id: Unique identifier (e.g., "san-rafael-fy2526-general-fund-police")
                - fiscal_year: Fiscal year (e.g., "2025-2026")
                - fund: Fund name (e.g., "General Fund", "Enterprise")
                - department: Department name (e.g., "Police", "Fire")
                - program: Optional program name
                - line_item: Budget line description
                - budgeted_cents: Budgeted amount in cents
                - revised_cents: Optional revised amount in cents
                - actual_cents: Optional actual spend in cents
                - source_url: URL or filename of source document
                - source_page: Optional page number in source
                - notes: Optional notes
            as_of: Timestamp for temporal versioning (default: now)
            use_copy: If True (default), use COPY for bulk inserts

        Returns:
            Number of items successfully stored
        """
        ...

    def get_budget_items(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
        fund: Optional[str] = None,
        department: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve budget items with optional filtering.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            fiscal_year: Filter by fiscal year (e.g., "2025-2026")
            fund: Filter by fund (e.g., "General Fund")
            department: Filter by department (e.g., "Police")
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of items to return

        Returns:
            List of budget item dictionaries
        """
        ...

    def get_budget_summary(
        self,
        jurisdiction_id: str,
        fiscal_year: str,
        group_by: str = "department",
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get aggregated budget summary grouped by department, fund, or program.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            fiscal_year: Fiscal year (e.g., "2025-2026")
            group_by: Grouping field ("department", "fund", or "program")
            as_of: Point-in-time query (for temporal versioning)

        Returns:
            List of summary dictionaries with group name and totals:
            [{"department": "Police", "budgeted_cents": 25000000, "count": 15}, ...]
        """
        ...

    def get_budget_items_count(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
    ) -> int:
        """
        Get count of budget items for a jurisdiction.

        Args:
            jurisdiction_id: Jurisdiction identifier (e.g., "san-rafael")
            fiscal_year: Optional filter by fiscal year

        Returns:
            Number of current (non-expired) budget items
        """
        ...
