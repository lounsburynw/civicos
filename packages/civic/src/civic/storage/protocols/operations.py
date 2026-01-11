"""
OperationsStorage protocol for ETL operations and cost tracking.

Handles long-running operations (fetch_meetings, discover_videos, etc.)
and ETL cost monitoring for budget optimization.
"""

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class OperationsStorage(Protocol):
    """
    Protocol for operations and cost tracking.

    Covers system operations:
    - Operations: Long-running tasks with progress tracking
    - ETL Costs: API usage and processing cost records

    Operations track status (pending, running, completed, failed)
    and provide progress info for admin dashboards.
    """

    # ========== Operation Tracking Methods ==========

    def create_operation(
        self,
        operation_id: str,
        jurisdiction_id: str,
        name: str,
    ) -> Dict[str, Any]:
        """Create a new operation record with 'pending' status."""
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
        """Update operation progress."""
        ...

    def complete_operation(
        self,
        operation_id: str,
        result: Dict[str, Any],
        error: Optional[str] = None,
    ) -> bool:
        """Mark operation as completed (success or failure)."""
        ...

    def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get operation by ID."""
        ...

    def get_operations(
        self,
        jurisdiction_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Query operations with optional filters."""
        ...

    # ========== ETL Cost Methods ==========

    def store_etl_cost(
        self,
        pipeline: str,
        jurisdiction_id: str,
        items_processed: int,
        cost_usd: float,
        duration_seconds: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> int:
        """Store ETL cost record for tracking pipeline expenses."""
        ...

    def get_etl_costs(
        self,
        jurisdiction_id: Optional[str] = None,
        pipeline: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Retrieve ETL cost records with optional filtering."""
        ...

    def get_etl_cost_summary(
        self,
        jurisdiction_id: Optional[str] = None,
        pipeline: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get aggregated ETL cost summary."""
        ...
