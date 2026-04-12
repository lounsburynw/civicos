"""
Tests for DataSource protocol and LocalDataSource implementation.

Validates that:
1. LocalDataSource correctly delegates to StorageBackend
2. DataSource protocol is properly defined
3. CivicOS uses DataSource for queries (zero behavior change)
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional
from unittest.mock import MagicMock, patch

from civicos.storage.data_source import (
    DataSource,
    LocalDataSource,
    get_data_source,
)
from civicos.storage.backend import StorageBackend, StorageStats, StorageValidationResult


class MockStorageBackend:
    """Minimal mock StorageBackend for testing LocalDataSource delegation."""

    def __init__(self):
        self.calls = []  # Track all calls for verification

    def _record_call(self, method: str, **kwargs):
        """Record method calls for test assertions."""
        self.calls.append({"method": method, "kwargs": kwargs})

    def validate(self) -> StorageValidationResult:
        self._record_call("validate")
        return StorageValidationResult(
            is_valid=True,
            connected=True,
            schema_valid=True,
            errors=[],
            warnings=[],
        )

    def get_stats(self, jurisdiction_id: str) -> StorageStats:
        self._record_call("get_stats", jurisdiction_id=jurisdiction_id)
        return StorageStats(
            jurisdiction_id=jurisdiction_id,
            meeting_count=10,
            agenda_item_count=50,
        )

    def get_meetings(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_meetings",
            jurisdiction_id=jurisdiction_id,
            as_of=as_of,
            since=since,
            until=until,
            limit=limit,
        )
        return [
            {"id": "meeting-1", "title": "City Council", "meeting_datetime": "2026-01-15T18:00:00"},
            {"id": "meeting-2", "title": "Planning Commission", "meeting_datetime": "2026-01-20T19:00:00"},
        ]

    def get_agenda_items(
        self,
        meeting_id: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_agenda_items",
            meeting_id=meeting_id,
            jurisdiction_id=jurisdiction_id,
            limit=limit,
        )
        return [{"id": "item-1", "title": "Housing Policy Update"}]

    def get_decisions(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_decisions",
            jurisdiction_id=jurisdiction_id,
            since=since,
            until=until,
            limit=limit,
        )
        return [{"id": "decision-1", "title": "Approved Housing Project"}]

    def get_elections(
        self,
        jurisdiction_id: str,
        include_past: bool = False,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_elections",
            jurisdiction_id=jurisdiction_id,
            include_past=include_past,
            limit=limit,
        )
        return [{"id": "election-1", "name": "City Council Election 2026"}]

    def get_election_deadlines(
        self,
        election_id: str,
    ) -> List[Dict[str, Any]]:
        self._record_call("get_election_deadlines", election_id=election_id)
        return [{"deadline_type": "registration", "deadline_date": "2026-05-01"}]

    def get_elected_officials(
        self,
        jurisdiction_id: str,
        current_only: bool = True,
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_elected_officials",
            jurisdiction_id=jurisdiction_id,
            current_only=current_only,
        )
        return [{"id": "official-1", "name": "Jane Smith", "seat": "Mayor"}]

    def get_official_by_name(
        self,
        jurisdiction_id: str,
        name: str,
    ) -> Optional[Dict[str, Any]]:
        self._record_call(
            "get_official_by_name",
            jurisdiction_id=jurisdiction_id,
            name=name,
        )
        if "smith" in name.lower():
            return {"id": "official-1", "name": "Jane Smith", "seat": "Mayor"}
        return None

    def get_budget_items(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
        fund: Optional[str] = None,
        department: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_budget_items",
            jurisdiction_id=jurisdiction_id,
            fiscal_year=fiscal_year,
            department=department,
            limit=limit,
        )
        return [
            {"item_id": "budget-1", "department": "Police", "budgeted_cents": 1000000}
        ]

    def get_budget_summary(
        self,
        jurisdiction_id: str,
        fiscal_year: Optional[str] = None,
        group_by: str = "department",
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_budget_summary",
            jurisdiction_id=jurisdiction_id,
            fiscal_year=fiscal_year,
        )
        return [{"department": "Police", "budgeted_cents": 1000000, "item_count": 5}]

    def get_budget_funding_links(
        self,
        jurisdiction_id: str,
        budget_item_id: Optional[str] = None,
        federal_cfda_number: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_budget_funding_links",
            jurisdiction_id=jurisdiction_id,
            fiscal_year=None,
        )
        return []

    def get_federal_awards(
        self,
        jurisdiction_id: str,
        cfda_number: Optional[str] = None,
        program: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_federal_awards",
            jurisdiction_id=jurisdiction_id,
            program=program,
            limit=limit,
        )
        return []

    def get_state_passthrough_funds(
        self,
        jurisdiction_id: str,
        federal_cfda_number: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_state_passthrough_funds",
            jurisdiction_id=jurisdiction_id,
            limit=limit,
        )
        return []

    def get_federal_audit_expenditures(
        self,
        jurisdiction_id: str,
        cfda_number: Optional[str] = None,
        audit_year: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_federal_audit_expenditures",
            jurisdiction_id=jurisdiction_id,
            audit_year=audit_year,
            limit=limit,
        )
        return []

    def get_operating_cost_summary(
        self,
        service: Optional[str] = None,
        category: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._record_call(
            "get_operating_cost_summary",
            service=service,
            jurisdiction_id=jurisdiction_id,
            since=since,
            until=until,
        )
        return {"total_cost_usd": 5.50, "record_count": 10}

    def get_operating_costs(
        self,
        service: Optional[str] = None,
        category: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        self._record_call(
            "get_operating_costs",
            service=service,
            jurisdiction_id=jurisdiction_id,
            since=since,
            until=until,
            limit=limit,
        )
        return [{"timestamp": "2026-01-15T10:00:00", "service": "modal", "amount_usd": 0.05}]


class TestDataSourceProtocol:
    """Test that DataSource protocol is properly defined."""

    def test_local_data_source_is_instance_of_protocol(self):
        """LocalDataSource should satisfy DataSource protocol."""
        mock_storage = MockStorageBackend()
        data_source = LocalDataSource(mock_storage)

        # Protocol compliance check
        assert isinstance(data_source, DataSource)

    def test_source_type_property(self):
        """LocalDataSource should return 'local' for source_type."""
        mock_storage = MockStorageBackend()
        data_source = LocalDataSource(mock_storage)

        assert data_source.source_type == "local"

    def test_validate_delegates_and_adds_source_type(self):
        """validate() should delegate to StorageBackend and add source_type."""
        mock_storage = MockStorageBackend()
        data_source = LocalDataSource(mock_storage)

        result = data_source.validate()

        assert result["is_valid"] is True
        assert result["connected"] is True
        assert result["source_type"] == "local"
        assert "validate" in [c["method"] for c in mock_storage.calls]


class TestLocalDataSourceDelegation:
    """Test that LocalDataSource correctly delegates to StorageBackend."""

    def test_get_meetings_delegates(self):
        """get_meetings() should delegate with correct parameters."""
        mock_storage = MockStorageBackend()
        data_source = LocalDataSource(mock_storage)

        now = datetime.now(timezone.utc)
        result = data_source.get_meetings(
            jurisdiction_id="city-san-rafael",
            since=now,
            until=now + timedelta(days=30),
            limit=10,
        )

        # Check delegation
        call = next(c for c in mock_storage.calls if c["method"] == "get_meetings")
        assert call["kwargs"]["jurisdiction_id"] == "city-san-rafael"
        assert call["kwargs"]["since"] == now
        assert call["kwargs"]["limit"] == 10

        # Check return value passed through
        assert len(result) == 2
        assert result[0]["title"] == "City Council"

    def test_get_agenda_items_delegates(self):
        """get_agenda_items() should delegate correctly."""
        mock_storage = MockStorageBackend()
        data_source = LocalDataSource(mock_storage)

        result = data_source.get_agenda_items(meeting_id="meeting-1")

        call = next(c for c in mock_storage.calls if c["method"] == "get_agenda_items")
        assert call["kwargs"]["meeting_id"] == "meeting-1"
        assert len(result) == 1

    def test_get_decisions_delegates(self):
        """get_decisions() should delegate correctly."""
        mock_storage = MockStorageBackend()
        data_source = LocalDataSource(mock_storage)

        result = data_source.get_decisions(
            jurisdiction_id="city-san-rafael",
            since="2026-01-01",
            limit=50,
        )

        call = next(c for c in mock_storage.calls if c["method"] == "get_decisions")
        assert call["kwargs"]["jurisdiction_id"] == "city-san-rafael"
        assert call["kwargs"]["since"] == "2026-01-01"
        assert len(result) == 1

    def test_get_elections_delegates(self):
        """get_elections() should delegate correctly."""
        mock_storage = MockStorageBackend()
        data_source = LocalDataSource(mock_storage)

        result = data_source.get_elections(
            jurisdiction_id="city-san-rafael",
            include_past=True,
        )

        call = next(c for c in mock_storage.calls if c["method"] == "get_elections")
        assert call["kwargs"]["include_past"] is True
        assert len(result) == 1

    def test_get_official_by_name_delegates(self):
        """get_official_by_name() should delegate correctly."""
        mock_storage = MockStorageBackend()
        data_source = LocalDataSource(mock_storage)

        result = data_source.get_official_by_name(
            jurisdiction_id="city-san-rafael",
            name="Jane Smith",
        )

        call = next(c for c in mock_storage.calls if c["method"] == "get_official_by_name")
        assert call["kwargs"]["name"] == "Jane Smith"
        assert result["seat"] == "Mayor"

    def test_get_budget_items_delegates(self):
        """get_budget_items() should delegate correctly."""
        mock_storage = MockStorageBackend()
        data_source = LocalDataSource(mock_storage)

        result = data_source.get_budget_items(
            jurisdiction_id="city-san-rafael",
            fiscal_year="2025-2026",
            department="Police",
        )

        call = next(c for c in mock_storage.calls if c["method"] == "get_budget_items")
        assert call["kwargs"]["fiscal_year"] == "2025-2026"
        assert call["kwargs"]["department"] == "Police"

        # Check return value passed through
        assert len(result) == 1
        assert result[0]["department"] == "Police"
        assert result[0]["budgeted_cents"] == 1000000

    def test_get_stats_delegates(self):
        """get_stats() should delegate correctly."""
        mock_storage = MockStorageBackend()
        data_source = LocalDataSource(mock_storage)

        result = data_source.get_stats("city-san-rafael")

        call = next(c for c in mock_storage.calls if c["method"] == "get_stats")
        assert call["kwargs"]["jurisdiction_id"] == "city-san-rafael"
        assert result.meeting_count == 10

    def test_get_operating_costs_delegates(self):
        """get_operating_costs() should delegate correctly."""
        mock_storage = MockStorageBackend()
        data_source = LocalDataSource(mock_storage)

        result = data_source.get_operating_costs(
            service="modal",
            jurisdiction_id="city-san-rafael",
            since="2026-01-01T00:00:00",
            until="2026-01-31T23:59:59",
        )

        call = next(c for c in mock_storage.calls if c["method"] == "get_operating_costs")
        assert call["kwargs"]["service"] == "modal"
        assert len(result) == 1


class TestGetDataSourceFactory:
    """Test the get_data_source factory function."""

    def test_get_data_source_with_storage(self):
        """get_data_source() should wrap provided StorageBackend."""
        mock_storage = MockStorageBackend()
        data_source = get_data_source(storage=mock_storage)

        assert isinstance(data_source, LocalDataSource)
        assert data_source.source_type == "local"

    def test_get_data_source_creates_backend_from_env(self):
        """get_data_source() should create backend from DATABASE_URL if no storage provided."""
        # This test verifies the factory pattern works, not the actual backend
        # In a real test environment, this would use a test DATABASE_URL
        with patch.dict("os.environ", {"DATABASE_URL": ""}, clear=False):
            with patch("civicos.storage.get_storage_backend") as mock_factory:
                mock_backend = MockStorageBackend()
                mock_factory.return_value = mock_backend

                data_source = get_data_source()

                mock_factory.assert_called_once_with(None)
                assert isinstance(data_source, LocalDataSource)
                assert data_source.source_type == "local"


class TestCivicOSDataSourceIntegration:
    """Test that CivicOS uses DataSource correctly."""

    def test_civicos_initializes_data_source(self):
        """CivicOS should initialize _data_source as LocalDataSource."""
        from civicos import CivicOS

        c = CivicOS("city-san-rafael")

        assert hasattr(c, "_data_source")
        assert isinstance(c._data_source, LocalDataSource)
        assert c._data_source.source_type == "local"

    def test_civicos_data_source_uses_storage_backend(self):
        """CivicOS._data_source should wrap _storage."""
        from civicos import CivicOS

        c = CivicOS("city-san-rafael")

        # The LocalDataSource should use the same storage as CivicOS
        # We can verify this by checking that get_stats returns consistent results
        stats_via_storage = c._storage.get_stats(c.jurisdiction)
        stats_via_data_source = c._data_source.get_stats(c.jurisdiction)

        assert stats_via_storage.meeting_count == stats_via_data_source.meeting_count


# Smoke test to verify imports work
def test_imports():
    """Verify all DataSource exports are importable."""
    from civicos.storage import DataSource, LocalDataSource, get_data_source

    # Verify correct symbols imported, not just non-None
    assert DataSource.__name__ == "DataSource"
    assert LocalDataSource.__name__ == "LocalDataSource"
    assert callable(get_data_source)
