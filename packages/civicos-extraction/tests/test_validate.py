"""
Tests for the validation pipeline.

Tests Tiers 1-2 with mocked HTTP, factory function, and SQLite store_agenda_items.
Tiers 3-5 require LLM + embedding model and are tested manually.
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.validate import (
    TierResult,
    ValidationReport,
    _create_source_from_config,
    _load_config,
    _run_tier1,
    _run_tier2,
)


class TestTierResult:
    def test_to_dict(self):
        result = TierResult(
            tier=1, name="Test", status="passed",
            duration_seconds=1.5, details={"key": "val"},
            errors=[], warnings=["warn1"],
        )
        d = result.to_dict()
        assert d["tier"] == 1
        assert d["status"] == "passed"
        assert d["duration_seconds"] == 1.5
        assert d["warnings"] == ["warn1"]


class TestValidationReport:
    def test_summary(self):
        report = ValidationReport(
            jurisdiction_id="city-test",
            tiers=[
                TierResult(tier=1, name="Config", status="passed", duration_seconds=0.5),
                TierResult(tier=2, name="Fetch", status="failed", duration_seconds=1.0,
                           errors=["No meetings"]),
            ],
            highest_tier_passed=1,
        )
        s = report.summary()
        assert "city-test" in s
        assert "Config" in s
        assert "passed" in s
        assert "No meetings" in s

    def test_to_dict(self):
        report = ValidationReport(
            jurisdiction_id="city-test",
            tiers=[TierResult(tier=1, name="T", status="passed", duration_seconds=0.1)],
            highest_tier_passed=1,
        )
        d = report.to_dict()
        assert d["jurisdiction_id"] == "city-test"
        assert len(d["tiers"]) == 1


class TestSourceFactory:
    def test_granicus_source(self):
        from civicos_extraction.clients.granicus import GranicusSource
        config = _load_config("test", config={
            "source_id": "granicus-test",
            "source_type": "granicus",
            "jurisdiction_id": "city-test",
            "base_url": "https://test.granicus.com",
            "metadata": {"granicus_domain": "test", "default_view_id": "1"},
        })
        source = _create_source_from_config(config)
        assert isinstance(source, GranicusSource)
        assert source.config.jurisdiction_id == "city-test"

    def test_legistar_source(self):
        from civicos_extraction.clients.legistar import LegistarClient
        config = _load_config("test", config={
            "source_id": "legistar-test",
            "source_type": "legistar",
            "jurisdiction_id": "city-test",
            "base_url": "https://webapi.legistar.com/v1/test",
            "metadata": {"client_name": "test"},
        })
        source = _create_source_from_config(config)
        assert isinstance(source, LegistarClient)
        assert source.jurisdiction_id == "city-test"

    def test_civicclerk_source(self):
        from civicos_extraction.clients.civicclerk import CivicClerkClient
        config = _load_config("test", config={
            "source_id": "civicclerk-test",
            "source_type": "civicclerk",
            "jurisdiction_id": "city-test",
            "base_url": "https://test.api.civicclerk.com/v1",
            "metadata": {"subdomain": "test"},
        })
        source = _create_source_from_config(config)
        assert isinstance(source, CivicClerkClient)
        assert source.jurisdiction_id == "city-test"

    def test_unsupported_source(self):
        config = _load_config("test", config={
            "source_id": "unknown-test",
            "source_type": "unknown",
            "jurisdiction_id": "city-test",
            "base_url": "https://example.com",
        })
        with pytest.raises(ValueError, match="Unsupported"):
            _create_source_from_config(config)


class TestTier1:
    def test_tier1_pass(self):
        mock_source = MagicMock()
        mock_source.validate.return_value = MagicMock(
            is_valid=True, config_valid=True, api_reachable=True,
            errors=[], warnings=[],
        )
        mock_config = MagicMock()
        mock_config.source_type = "granicus"

        result = _run_tier1(mock_source, mock_config)
        assert result.status == "passed"
        assert result.tier == 1

    def test_tier1_fail(self):
        mock_source = MagicMock()
        mock_source.validate.return_value = MagicMock(
            is_valid=False, config_valid=False, api_reachable=False,
            errors=["Bad config"], warnings=[],
        )
        mock_config = MagicMock()
        mock_config.source_type = "granicus"

        result = _run_tier1(mock_source, mock_config)
        assert result.status == "failed"
        assert "Bad config" in result.errors

    def test_tier1_exception(self):
        mock_source = MagicMock()
        mock_source.validate.side_effect = ConnectionError("unreachable")
        mock_config = MagicMock()
        mock_config.source_type = "granicus"

        result = _run_tier1(mock_source, mock_config)
        assert result.status == "error"


class TestTier2:
    def test_tier2_with_meetings(self):
        mock_source = MagicMock()
        # Use a real Meeting object instead of fragile mock
        from civicos_extraction import Meeting
        meeting = Meeting(
            id="m1", title="Council Meeting",
            meeting_datetime=datetime(2025, 6, 1, 18, 0),
            jurisdiction_id="city-test",
            agenda_url="https://example.com/agenda.pdf",
        )
        mock_source.get_meetings.return_value = [meeting]

        mock_config = MagicMock()
        mock_config.jurisdiction_id = "city-test"

        mock_storage = MagicMock()
        mock_storage.store_meetings.return_value = MagicMock(stored_count=1)

        result = _run_tier2(mock_source, mock_config, mock_storage)
        assert result.status == "passed"
        assert result.details["meetings_fetched"] == 1

    def test_tier2_no_meetings(self):
        mock_source = MagicMock()
        mock_source.get_meetings.return_value = []

        mock_config = MagicMock()
        mock_config.jurisdiction_id = "city-test"

        mock_storage = MagicMock()

        result = _run_tier2(mock_source, mock_config, mock_storage)
        assert result.status == "failed"


class TestSQLiteAgendaItems:
    """Test that store_agenda_items actually works in SQLite."""

    def test_store_and_retrieve(self):
        from civicos.storage.sqlite_backend import SQLiteBackend

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            storage = SQLiteBackend(db_path=db_path)

            # Store a meeting first (agenda items need meeting_id)
            from civicos_extraction import Meeting
            meeting = Meeting(
                id="m1", title="Test Meeting",
                meeting_datetime=datetime(2025, 6, 1, 18, 0),
                jurisdiction_id="city-test",
            )
            storage.store_meetings("city-test", [meeting])

            # Store agenda items
            items = [
                {
                    "title": "Public Hearing: Zoning",
                    "item_number": "5.A",
                    "description": "Zoning amendment",
                    "actionability": "actionable",
                    "impact_level": "high",
                },
                {
                    "title": "Consent Calendar",
                    "item_number": "3.A",
                    "description": "Routine items",
                    "actionability": "informational",
                },
            ]
            count = storage.store_agenda_items("m1", items)
            assert count == 2

            # Retrieve by meeting_id
            retrieved = storage.get_agenda_items(meeting_id="m1")
            assert len(retrieved) == 2

            # Retrieve by jurisdiction_id
            by_jid = storage.get_agenda_items(jurisdiction_id="city-test")
            assert len(by_jid) == 2

            # Count
            total = storage.get_agenda_item_count()
            assert total == 2
            by_jid_count = storage.get_agenda_item_count(jurisdiction_id="city-test")
            assert by_jid_count == 2

    def test_temporal_versioning(self):
        from civicos.storage.sqlite_backend import SQLiteBackend

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            storage = SQLiteBackend(db_path=db_path)

            from civicos_extraction import Meeting
            meeting = Meeting(
                id="m1", title="Test Meeting",
                meeting_datetime=datetime(2025, 6, 1, 18, 0),
                jurisdiction_id="city-test",
            )
            storage.store_meetings("city-test", [meeting])

            # Store v1
            storage.store_agenda_items("m1", [{"title": "Item v1", "item_number": "1"}])
            assert storage.get_agenda_item_count() == 1

            # Store v2 — should close v1
            storage.store_agenda_items("m1", [
                {"title": "Item v2a", "item_number": "1"},
                {"title": "Item v2b", "item_number": "2"},
            ])
            # Only v2 items should be current
            assert storage.get_agenda_item_count() == 2
            items = storage.get_agenda_items(meeting_id="m1")
            assert len(items) == 2
            titles = {i["title"] for i in items}
            assert titles == {"Item v2a", "Item v2b"}
