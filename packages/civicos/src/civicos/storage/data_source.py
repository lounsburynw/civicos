"""
DataSource protocol for abstracting local vs federated data access.

Separates WHERE data comes from (local StorageBackend vs federated MCP relay)
from HOW data is queried (unified read-only interface). This enables CivicOS
to query data without knowing if it's local or from a remote city.

For pilot: LocalDataSource wraps StorageBackend (zero behavior change).
Post-pilot: FederatedDataSource uses civicos-relay MCP protocol for fan-out queries.

Design principle: DataSource is READ-ONLY. Write operations stay on StorageBackend
because only local data should be written (federation is query-only).

Usage:
    from civicos.storage.data_source import DataSource, LocalDataSource

    # Pilot: wrap existing StorageBackend
    storage = get_storage_backend()
    data_source = LocalDataSource(storage)

    # Use unified query interface
    meetings = data_source.get_meetings("city-san-rafael")
    decisions = data_source.get_decisions("city-san-rafael", topic="housing")

    # Future: federated queries
    data_source = FederatedDataSource([relay_url_1, relay_url_2])
    meetings = data_source.get_meetings("city-berkeley")  # queries remote city
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from civicos.storage.backend import StorageBackend, StorageStats


@runtime_checkable
class DataSource(Protocol):
    """
    Protocol for read-only civic data access (local or federated).

    Abstracts the source of data, enabling seamless switching between:
    - LocalDataSource: Wraps StorageBackend for single-city queries
    - FederatedDataSource: MCP relay for multi-city fan-out queries (post-pilot)

    This is a query-only interface. Write operations (store_*, update_*, delete_*)
    stay on StorageBackend because only local data should be written.

    All methods are read-only and return Dict/List results suitable for
    JSON serialization and cross-process communication.
    """

    # ========== System Properties ==========

    @property
    def source_type(self) -> str:
        """
        Type identifier for this data source.

        Returns:
            'local' - LocalDataSource wrapping StorageBackend
            'federated' - FederatedDataSource with MCP relay
            'hybrid' - Combination of local and federated (future)
        """
        ...

    def validate(self) -> Dict[str, Any]:
        """
        Validate data source connectivity and availability.

        Returns:
            Dict with 'is_valid', 'connected', 'errors', 'warnings'
        """
        ...

    # ========== Meeting Queries ==========

    def get_meetings(
        self,
        jurisdiction_id: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get meetings for a jurisdiction with optional date filtering.

        Args:
            jurisdiction_id: CivicOS jurisdiction (e.g., 'city-san-rafael')
            since: Filter meetings after this datetime
            until: Filter meetings before this datetime
            limit: Maximum number of results

        Returns:
            List of meeting dicts with id, title, meeting_datetime, meeting_type, etc.
        """
        ...

    def get_agenda_items(
        self,
        meeting_id: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get agenda items, optionally filtered by meeting or jurisdiction.

        Args:
            meeting_id: Filter by specific meeting
            jurisdiction_id: Filter by jurisdiction
            limit: Maximum number of results

        Returns:
            List of agenda item dicts
        """
        ...

    # ========== Decision Queries ==========

    def get_decisions(
        self,
        jurisdiction_id: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get decisions (votes/outcomes) for a jurisdiction.

        Args:
            jurisdiction_id: CivicOS jurisdiction
            since: Filter decisions after this date (ISO format)
            until: Filter decisions before this date (ISO format)
            limit: Maximum number of results

        Returns:
            List of decision dicts with id, title, outcome, date, etc.
        """
        ...

    # ========== Election Queries ==========

    def get_elections(
        self,
        jurisdiction_id: str,
        include_past: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get elections for a jurisdiction.

        Args:
            jurisdiction_id: CivicOS jurisdiction
            include_past: If True, include past elections
            limit: Maximum number of results

        Returns:
            List of election dicts with id, name, election_date, election_type, etc.
        """
        ...

    def get_election_deadlines(
        self,
        election_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Get deadlines for a specific election.

        Args:
            election_id: Election ID

        Returns:
            List of deadline dicts with deadline_type, deadline_date, description
        """
        ...

    def get_elected_officials(
        self,
        jurisdiction_id: str,
        current_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Get elected officials for a jurisdiction.

        Args:
            jurisdiction_id: CivicOS jurisdiction
            current_only: If True, only return currently serving officials

        Returns:
            List of official dicts with name, title, party, etc.
        """
        ...

    def get_official_by_name(
        self,
        jurisdiction_id: str,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Look up a specific official by name.

        Args:
            jurisdiction_id: CivicOS jurisdiction
            name: Official's name (case-insensitive match)

        Returns:
            Official dict or None if not found
        """
        ...

    # ========== Budget Queries ==========

    def get_budget_items(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
        department: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get budget line items for a jurisdiction.

        Args:
            jurisdiction_id: CivicOS jurisdiction
            fiscal_year: Filter by fiscal year (e.g., 'FY2025-26')
            department: Filter by department
            limit: Maximum number of results

        Returns:
            List of budget item dicts
        """
        ...

    def get_budget_summary(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get budget summary with totals by category.

        Args:
            jurisdiction_id: CivicOS jurisdiction
            fiscal_year: Filter by fiscal year

        Returns:
            Dict with total_revenue, total_expenses, by_department, etc.
        """
        ...

    def get_budget_funding_links(
        self,
        jurisdiction_id: str,
        budget_item_id: Optional[str] = None,
        federal_cfda_number: Optional[str] = None,
        fiscal_year: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get links between budget items and funding sources.

        Args:
            jurisdiction_id: CivicOS jurisdiction
            budget_item_id: Filter by specific budget item
            federal_cfda_number: Filter by CFDA number
            fiscal_year: Filter by fiscal year (joins with budget_items)
            limit: Maximum number of results

        Returns:
            List of funding link dicts
        """
        ...

    # ========== Federal Funding Queries ==========

    def get_federal_awards(
        self,
        jurisdiction_id: str,
        cfda_number: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get federal awards/grants for a jurisdiction.

        Args:
            jurisdiction_id: CivicOS jurisdiction
            cfda_number: Filter by CFDA number
            limit: Maximum number of results

        Returns:
            List of federal award dicts
        """
        ...

    def get_state_passthrough_funds(
        self,
        jurisdiction_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get state pass-through funds for a jurisdiction.

        Args:
            jurisdiction_id: CivicOS jurisdiction
            limit: Maximum number of results

        Returns:
            List of state pass-through dicts
        """
        ...

    def get_federal_audit_expenditures(
        self,
        jurisdiction_id: str,
        audit_year: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get federal audit expenditure data (from FAC).

        Args:
            jurisdiction_id: CivicOS jurisdiction
            audit_year: Filter by audit year
            limit: Maximum number of results

        Returns:
            List of expenditure dicts
        """
        ...

    # ========== Cost/Operations Queries ==========

    def get_operating_cost_summary(
        self,
        service: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get operating cost summary for dashboard display.

        Args:
            service: Filter by service (modal, openai, anthropic)
            jurisdiction_id: Filter by jurisdiction (optional)
            since: Filter records from this timestamp (ISO format)
            until: Filter records until this timestamp (ISO format)

        Returns:
            Dict with total_cost_usd, record_count, by_service, by_category
        """
        ...

    def get_operating_costs(
        self,
        service: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get operating cost records for time-series analysis.

        Args:
            service: Filter by service (modal, openai, anthropic)
            jurisdiction_id: Filter by jurisdiction (optional)
            since: Filter records from this timestamp (ISO format)
            until: Filter records until this timestamp (ISO format)
            limit: Maximum records to return

        Returns:
            List of cost records
        """
        ...

    # ========== Statistics ==========

    def get_stats(self, jurisdiction_id: str) -> StorageStats:
        """
        Get storage statistics for a jurisdiction.

        Args:
            jurisdiction_id: CivicOS jurisdiction

        Returns:
            StorageStats with meeting_count, agenda_item_count, temporal info
        """
        ...


class LocalDataSource:
    """
    DataSource implementation wrapping local StorageBackend.

    Provides zero-behavior-change access to local data through the
    DataSource protocol. All calls delegate directly to StorageBackend.

    This is the pilot implementation. Post-pilot, FederatedDataSource
    will provide the same interface but query remote cities via MCP relay.

    Usage:
        from civicos.storage import get_storage_backend
        from civicos.storage.data_source import LocalDataSource

        storage = get_storage_backend()
        data_source = LocalDataSource(storage)

        # Same interface as DataSource protocol
        meetings = data_source.get_meetings("city-san-rafael")
    """

    def __init__(self, storage: StorageBackend):
        """
        Initialize with a StorageBackend.

        Args:
            storage: StorageBackend instance (SQLiteBackend or PostgresBackend)
        """
        self._storage = storage

    @property
    def source_type(self) -> str:
        """Return 'local' for local data source."""
        return "local"

    def validate(self) -> Dict[str, Any]:
        """Validate underlying storage backend."""
        result = self._storage.validate()
        return {
            "is_valid": result.is_valid,
            "connected": result.connected,
            "schema_valid": result.schema_valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "source_type": self.source_type,
        }

    # ========== Meeting Queries ==========

    def get_meetings(
        self,
        jurisdiction_id: str,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_meetings()."""
        return self._storage.get_meetings(
            jurisdiction_id=jurisdiction_id,
            since=since,
            until=until,
            limit=limit,
        )

    def get_agenda_items(
        self,
        meeting_id: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_agenda_items()."""
        return self._storage.get_agenda_items(
            meeting_id=meeting_id,
            jurisdiction_id=jurisdiction_id,
            limit=limit,
        )

    # ========== Decision Queries ==========

    def get_decisions(
        self,
        jurisdiction_id: str,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_decisions()."""
        return self._storage.get_decisions(
            jurisdiction_id=jurisdiction_id,
            since=since,
            until=until,
            limit=limit,
        )

    # ========== Election Queries ==========

    def get_elections(
        self,
        jurisdiction_id: str,
        include_past: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_elections()."""
        return self._storage.get_elections(
            jurisdiction_id=jurisdiction_id,
            include_past=include_past,
            limit=limit,
        )

    def get_election_deadlines(
        self,
        election_id: str,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_election_deadlines()."""
        return self._storage.get_election_deadlines(election_id=election_id)

    def get_elected_officials(
        self,
        jurisdiction_id: str,
        current_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_elected_officials()."""
        return self._storage.get_elected_officials(
            jurisdiction_id=jurisdiction_id,
            current_only=current_only,
        )

    def get_official_by_name(
        self,
        jurisdiction_id: str,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        """Delegate to StorageBackend.get_official_by_name()."""
        return self._storage.get_official_by_name(
            jurisdiction_id=jurisdiction_id,
            name=name,
        )

    # ========== Budget Queries ==========

    def get_budget_items(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
        department: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_budget_items()."""
        return self._storage.get_budget_items(
            jurisdiction_id=jurisdiction_id,
            fiscal_year=fiscal_year,
            department=department,
            limit=limit,
        )

    def get_budget_summary(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delegate to StorageBackend.get_budget_summary()."""
        return self._storage.get_budget_summary(
            jurisdiction_id=jurisdiction_id,
            fiscal_year=fiscal_year,
        )

    def get_budget_funding_links(
        self,
        jurisdiction_id: str,
        budget_item_id: Optional[str] = None,
        federal_cfda_number: Optional[str] = None,
        fiscal_year: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_budget_funding_links()."""
        return self._storage.get_budget_funding_links(
            jurisdiction_id=jurisdiction_id,
            budget_item_id=budget_item_id,
            federal_cfda_number=federal_cfda_number,
            fiscal_year=fiscal_year,
            limit=limit,
        )

    # ========== Federal Funding Queries ==========

    def get_federal_awards(
        self,
        jurisdiction_id: str,
        cfda_number: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_federal_awards()."""
        return self._storage.get_federal_awards(
            jurisdiction_id=jurisdiction_id,
            cfda_number=cfda_number,
            limit=limit,
        )

    def get_state_passthrough_funds(
        self,
        jurisdiction_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_state_passthrough_funds()."""
        return self._storage.get_state_passthrough_funds(
            jurisdiction_id=jurisdiction_id,
            limit=limit,
        )

    def get_federal_audit_expenditures(
        self,
        jurisdiction_id: str,
        audit_year: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_federal_audit_expenditures()."""
        return self._storage.get_federal_audit_expenditures(
            jurisdiction_id=jurisdiction_id,
            audit_year=audit_year,
            limit=limit,
        )

    # ========== Cost/Operations Queries ==========

    def get_operating_cost_summary(
        self,
        service: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Delegate to StorageBackend.get_operating_cost_summary()."""
        return self._storage.get_operating_cost_summary(
            service=service,
            jurisdiction_id=jurisdiction_id,
            since=since,
            until=until,
        )

    def get_operating_costs(
        self,
        service: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Delegate to StorageBackend.get_operating_costs()."""
        return self._storage.get_operating_costs(
            service=service,
            jurisdiction_id=jurisdiction_id,
            since=since,
            until=until,
            limit=limit,
        )

    # ========== Statistics ==========

    def get_stats(self, jurisdiction_id: str) -> StorageStats:
        """Delegate to StorageBackend.get_stats()."""
        return self._storage.get_stats(jurisdiction_id)


def get_data_source(
    storage: Optional[StorageBackend] = None,
    database_url: Optional[str] = None,
) -> DataSource:
    """
    Factory function to get a DataSource instance.

    For pilot, always returns LocalDataSource wrapping StorageBackend.
    Post-pilot, this will support federated configuration.

    Args:
        storage: Optional StorageBackend to wrap. If not provided,
                 creates one using database_url or DATABASE_URL env var.
        database_url: Optional database URL. If not provided,
                      uses DATABASE_URL environment variable.

    Returns:
        DataSource instance (LocalDataSource for pilot)

    Examples:
        # Use existing StorageBackend
        data_source = get_data_source(storage=my_backend)

        # Create from environment
        data_source = get_data_source()

        # Create from explicit URL
        data_source = get_data_source(database_url="postgresql://...")
    """
    from civicos.storage import get_storage_backend

    if storage is None:
        storage = get_storage_backend(database_url)

    return LocalDataSource(storage)
