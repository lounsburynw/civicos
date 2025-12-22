"""
StorageBackend protocol for primary data persistence.

Defines the interface for CRUD operations on civic data (SQLite, Postgres).
Part of the 4-stage pipeline: discover -> ingest -> store -> index.
"""

from dataclasses import dataclass, field
from datetime import datetime
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
