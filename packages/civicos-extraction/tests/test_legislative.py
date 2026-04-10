"""
Tests for legislative refresh CLI module.

Tests the LegislativeCheckpoint dataclass, checkpoint persistence,
API key checking, bulk ingestion logic, JSON migration, and
the run_legislative dispatch logic.

Run:
    pytest packages/civicos-extraction/tests/test_legislative.py -v
"""

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from civicos_extraction.cli.legislative import (
    TOPIC_KEYWORDS,
    LegislativeCheckpoint,
    add_legislative_parser,
    bulk_ingest_legislation,
    check_api_keys,
    checkpoint_path_for_legislative,
    load_checkpoint,
    migrate_json_to_cloud,
    run_legislative,
    run_legislative_refresh,
    save_checkpoint,
    _run_post_store_enrichment,
)


# ---------------------------------------------------------------------------
# LegislativeCheckpoint dataclass
# ---------------------------------------------------------------------------

class TestLegislativeCheckpoint:
    """Tests for LegislativeCheckpoint dataclass."""

    def test_to_dict_returns_all_fields(self):
        cp = LegislativeCheckpoint(
            topic="housing",
            state="california",
            bills_fetched=42,
            bills_filtered=7,
            timestamp="2026-04-01T10:00:00",
        )
        d = cp.to_dict()
        assert d["topic"] == "housing"
        assert d["state"] == "california"
        assert d["bills_fetched"] == 42
        assert d["bills_filtered"] == 7
        assert d["timestamp"] == "2026-04-01T10:00:00"

    def test_from_dict_restores_fields(self):
        data = {
            "topic": "environment",
            "state": "federal",
            "bills_fetched": 100,
            "bills_filtered": 25,
            "timestamp": "2026-03-15T08:30:00",
        }
        cp = LegislativeCheckpoint.from_dict(data)
        assert cp.topic == "environment"
        assert cp.state == "federal"
        assert cp.bills_fetched == 100
        assert cp.bills_filtered == 25
        assert cp.timestamp == "2026-03-15T08:30:00"

    def test_roundtrip_preserves_all_values(self):
        original = LegislativeCheckpoint(
            topic="budget",
            state="california",
            bills_fetched=55,
            bills_filtered=12,
            timestamp="2026-04-09T12:00:00",
        )
        restored = LegislativeCheckpoint.from_dict(original.to_dict())
        assert restored.topic == original.topic
        assert restored.state == original.state
        assert restored.bills_fetched == original.bills_fetched
        assert restored.bills_filtered == original.bills_filtered
        assert restored.timestamp == original.timestamp

    def test_zero_counts(self):
        cp = LegislativeCheckpoint(
            topic="transportation",
            state="california",
            bills_fetched=0,
            bills_filtered=0,
            timestamp="2026-01-01T00:00:00",
        )
        d = cp.to_dict()
        assert d["bills_fetched"] == 0
        assert d["bills_filtered"] == 0


# ---------------------------------------------------------------------------
# TOPIC_KEYWORDS constant
# ---------------------------------------------------------------------------

class TestTopicKeywords:
    """Tests for the TOPIC_KEYWORDS constant."""

    def test_all_expected_topics_present(self):
        expected = {"housing", "transportation", "environment", "budget", "education"}
        assert set(TOPIC_KEYWORDS.keys()) == expected

    def test_housing_keywords_include_adu_and_rhna(self):
        assert "ADU" in TOPIC_KEYWORDS["housing"]
        assert "RHNA" in TOPIC_KEYWORDS["housing"]

    def test_each_topic_has_at_least_three_keywords(self):
        for topic, keywords in TOPIC_KEYWORDS.items():
            assert len(keywords) >= 3, f"{topic} has only {len(keywords)} keywords"


# ---------------------------------------------------------------------------
# check_api_keys
# ---------------------------------------------------------------------------

class TestCheckApiKeys:
    """Tests for check_api_keys function."""

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "abc123", "OPENAI_API_KEY": "sk-xyz"})
    def test_both_keys_present(self):
        result = check_api_keys()
        assert result["LEGISCAN_API_KEY"] is True
        assert result["OPENAI_API_KEY"] is True

    @patch.dict(os.environ, {}, clear=True)
    def test_no_keys_present(self):
        # Explicitly remove these keys if they exist
        os.environ.pop("LEGISCAN_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        result = check_api_keys()
        assert result["LEGISCAN_API_KEY"] is False
        assert result["OPENAI_API_KEY"] is False

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "abc123"}, clear=True)
    def test_only_legiscan_key_present(self):
        os.environ.pop("OPENAI_API_KEY", None)
        result = check_api_keys()
        assert result["LEGISCAN_API_KEY"] is True
        assert result["OPENAI_API_KEY"] is False

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "", "OPENAI_API_KEY": ""})
    def test_empty_strings_are_falsy(self):
        result = check_api_keys()
        assert result["LEGISCAN_API_KEY"] is False
        assert result["OPENAI_API_KEY"] is False


# ---------------------------------------------------------------------------
# checkpoint_path_for_legislative
# ---------------------------------------------------------------------------

class TestCheckpointPathForLegislative:
    """Tests for checkpoint path generation."""

    def test_returns_correct_filename(self, tmp_path):
        path = checkpoint_path_for_legislative("housing", "california", str(tmp_path))
        assert path == tmp_path / "legislative_california_housing.json"

    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c"
        path = checkpoint_path_for_legislative("budget", "federal", str(nested))
        assert nested.exists()
        assert path == nested / "legislative_federal_budget.json"

    def test_different_topics_produce_different_paths(self, tmp_path):
        p1 = checkpoint_path_for_legislative("housing", "california", str(tmp_path))
        p2 = checkpoint_path_for_legislative("budget", "california", str(tmp_path))
        assert p1 != p2
        assert "housing" in str(p1)
        assert "budget" in str(p2)


# ---------------------------------------------------------------------------
# save_checkpoint / load_checkpoint
# ---------------------------------------------------------------------------

class TestCheckpointPersistence:
    """Tests for checkpoint save/load utilities."""

    def test_save_and_load_roundtrip(self, tmp_path):
        cp = LegislativeCheckpoint(
            topic="housing",
            state="california",
            bills_fetched=10,
            bills_filtered=3,
            timestamp="2026-04-09T10:00:00",
        )
        path = tmp_path / "test_checkpoint.json"
        save_checkpoint(cp, path)

        loaded = load_checkpoint(path)
        assert loaded is not None
        assert loaded.topic == "housing"
        assert loaded.state == "california"
        assert loaded.bills_fetched == 10
        assert loaded.bills_filtered == 3
        assert loaded.timestamp == "2026-04-09T10:00:00"

    def test_load_nonexistent_returns_none(self, tmp_path):
        path = tmp_path / "does_not_exist.json"
        loaded = load_checkpoint(path)
        assert loaded is None

    def test_load_corrupted_file_returns_none(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("NOT VALID JSON {{{")
        loaded = load_checkpoint(path)
        assert loaded is None

    def test_save_creates_valid_json(self, tmp_path):
        cp = LegislativeCheckpoint(
            topic="education",
            state="california",
            bills_fetched=5,
            bills_filtered=2,
            timestamp="2026-04-09T15:00:00",
        )
        path = tmp_path / "cp.json"
        save_checkpoint(cp, path)

        with open(path) as f:
            data = json.load(f)
        assert data["topic"] == "education"
        assert data["bills_fetched"] == 5


# ---------------------------------------------------------------------------
# add_legislative_parser
# ---------------------------------------------------------------------------

class TestAddLegislativeParser:
    """Tests for CLI parser setup."""

    def _make_parser(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_legislative_parser(subparsers)
        return parser

    def test_topic_is_required(self):
        parser = self._make_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["legislative"])

    def test_default_state_is_california(self):
        parser = self._make_parser()
        args = parser.parse_args(["legislative", "--topic", "housing"])
        assert args.state == "california"

    def test_default_days_back_is_90(self):
        parser = self._make_parser()
        args = parser.parse_args(["legislative", "--topic", "housing"])
        assert args.days_back == 90

    def test_default_limit_is_20(self):
        parser = self._make_parser()
        args = parser.parse_args(["legislative", "--topic", "housing"])
        assert args.limit == 20

    def test_dry_run_defaults_false(self):
        parser = self._make_parser()
        args = parser.parse_args(["legislative", "--topic", "housing"])
        assert args.dry_run is False

    def test_dry_run_flag_sets_true(self):
        parser = self._make_parser()
        args = parser.parse_args(["legislative", "--topic", "housing", "--dry-run"])
        assert args.dry_run is True

    def test_cloud_flag(self):
        parser = self._make_parser()
        args = parser.parse_args(["legislative", "--topic", "housing", "--cloud"])
        assert args.cloud is True

    def test_bulk_flag(self):
        parser = self._make_parser()
        args = parser.parse_args(["legislative", "--topic", "all", "--bulk"])
        assert args.bulk is True

    def test_enrich_flag(self):
        parser = self._make_parser()
        args = parser.parse_args(["legislative", "--topic", "all", "--enrich"])
        assert args.enrich is True

    def test_topic_all_accepted(self):
        parser = self._make_parser()
        args = parser.parse_args(["legislative", "--topic", "all"])
        assert args.topic == "all"

    def test_invalid_topic_rejected(self):
        parser = self._make_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["legislative", "--topic", "invalid_topic"])

    def test_custom_limit(self):
        parser = self._make_parser()
        args = parser.parse_args(["legislative", "--topic", "housing", "--limit", "50"])
        assert args.limit == 50


# ---------------------------------------------------------------------------
# bulk_ingest_legislation
# ---------------------------------------------------------------------------

class TestBulkIngestLegislation:
    """Tests for bulk ingestion from LegiScan master list."""

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_legiscan_key_returns_1(self):
        os.environ.pop("LEGISCAN_API_KEY", None)
        os.environ.pop("DATABASE_URL", None)
        result = bulk_ingest_legislation(state="california")
        assert result == 1

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123"}, clear=True)
    def test_missing_database_url_returns_1(self):
        os.environ.pop("DATABASE_URL", None)
        result = bulk_ingest_legislation(state="california")
        assert result == 1

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123", "DATABASE_URL": "postgres://test"})
    @patch("civicos_extraction.clients.legiscan.LegiScanClient")
    def test_empty_master_list_returns_1(self, MockClient):
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.get_master_list.return_value = []

        result = bulk_ingest_legislation(state="california")
        assert result == 1

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123", "DATABASE_URL": "postgres://test"})
    @patch("civicos_extraction.clients.legiscan.LegiScanClient")
    def test_dry_run_returns_0_without_storing(self, MockClient):
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.get_master_list.return_value = [
            {"number": "SB 100", "title": "Housing Bill", "bill_id": 12345}
        ]

        result = bulk_ingest_legislation(state="california", dry_run=True)
        assert result == 0

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123", "DATABASE_URL": "postgres://test"})
    @patch("civicos.storage.postgres_backend.PostgresBackend")
    @patch("civicos_extraction.clients.legiscan.LegiScanClient")
    def test_successful_ingestion_returns_0(self, MockClient, MockPostgres):
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.get_master_list.return_value = [
            {"number": "SB 100", "title": "Housing Bill", "bill_id": 12345,
             "status": 1, "url": "http://example.com", "description": "Test",
             "last_action": "Introduced", "last_action_date": "2026-01-01",
             "status_date": "2026-01-01"},
        ]
        mock_client.query_count = 1

        mock_backend = MagicMock()
        MockPostgres.return_value = mock_backend
        mock_backend.store_legislation.return_value = 1
        mock_backend.get_legislation_count.return_value = 1

        result = bulk_ingest_legislation(state="california")
        assert result == 0

        # Verify store_legislation was called with correct state code
        call_kwargs = mock_backend.store_legislation.call_args
        assert call_kwargs.kwargs["state"] == "CA"

        # Verify the bill was normalized correctly
        bills = call_kwargs.kwargs["bills"]
        assert len(bills) == 1
        assert bills[0]["bill_id"] == "ca-sb100"
        assert bills[0]["bill_number"] == "SB 100"
        assert bills[0]["bill_name"] == "Housing Bill"
        assert bills[0]["legiscan_id"] == 12345

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123", "DATABASE_URL": "postgres://test"})
    @patch("civicos.storage.postgres_backend.PostgresBackend")
    @patch("civicos_extraction.clients.legiscan.LegiScanClient")
    def test_state_code_mapping_federal(self, MockClient, MockPostgres):
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.get_master_list.return_value = [
            {"number": "HR 200", "title": "Federal Bill", "bill_id": 99}
        ]
        mock_client.query_count = 1

        mock_backend = MagicMock()
        MockPostgres.return_value = mock_backend
        mock_backend.store_legislation.return_value = 1
        mock_backend.get_legislation_count.return_value = 1

        result = bulk_ingest_legislation(state="federal")
        assert result == 0

        call_kwargs = mock_backend.store_legislation.call_args
        assert call_kwargs.kwargs["state"] == "US"
        bills = call_kwargs.kwargs["bills"]
        assert bills[0]["bill_id"] == "us-hr200"

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123", "DATABASE_URL": "postgres://test"})
    @patch("civicos.storage.postgres_backend.PostgresBackend")
    @patch("civicos_extraction.clients.legiscan.LegiScanClient")
    def test_state_code_mapping_congress(self, MockClient, MockPostgres):
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        mock_client.get_master_list.return_value = [
            {"number": "S 50", "title": "Senate Bill", "bill_id": 88}
        ]
        mock_client.query_count = 1

        mock_backend = MagicMock()
        MockPostgres.return_value = mock_backend
        mock_backend.store_legislation.return_value = 1
        mock_backend.get_legislation_count.return_value = 1

        result = bulk_ingest_legislation(state="congress")
        assert result == 0

        call_kwargs = mock_backend.store_legislation.call_args
        assert call_kwargs.kwargs["state"] == "US"


# ---------------------------------------------------------------------------
# migrate_json_to_cloud
# ---------------------------------------------------------------------------

class TestMigrateJsonToCloud:
    """Tests for JSON-to-PostgreSQL migration."""

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_database_url_returns_1(self):
        os.environ.pop("DATABASE_URL", None)
        result = migrate_json_to_cloud()
        assert result == 1

    @patch.dict(os.environ, {"DATABASE_URL": "postgres://test"})
    def test_missing_state_dir_returns_1(self, tmp_path):
        result = migrate_json_to_cloud(
            state="california",
            output_dir=str(tmp_path / "nonexistent"),
        )
        assert result == 1

    @patch.dict(os.environ, {"DATABASE_URL": "postgres://test"})
    def test_empty_state_dir_returns_1(self, tmp_path):
        state_dir = tmp_path / "state" / "california"
        state_dir.mkdir(parents=True)
        # No JSON files
        result = migrate_json_to_cloud(
            state="california",
            output_dir=str(tmp_path),
        )
        assert result == 1

    @patch.dict(os.environ, {"DATABASE_URL": "postgres://test"})
    def test_non_topic_json_files_ignored(self, tmp_path):
        state_dir = tmp_path / "state" / "california"
        state_dir.mkdir(parents=True)
        # Write a non-topic JSON file (should be ignored)
        (state_dir / "verification.json").write_text('{"data": []}')

        result = migrate_json_to_cloud(
            state="california",
            output_dir=str(tmp_path),
        )
        assert result == 1  # No topic files found

    @patch.dict(os.environ, {"DATABASE_URL": "postgres://test"})
    def test_dry_run_counts_bills_without_storing(self, tmp_path):
        state_dir = tmp_path / "state" / "california"
        state_dir.mkdir(parents=True)

        data = {
            "state_legislation": {
                "ca-sb9": {"bill_number": "SB 9", "bill_name": "Housing"},
                "ca-sb10": {"bill_number": "SB 10", "bill_name": "Zoning"},
            }
        }
        (state_dir / "housing.json").write_text(json.dumps(data))

        result = migrate_json_to_cloud(
            state="california",
            output_dir=str(tmp_path),
            dry_run=True,
        )
        assert result == 0

    @patch.dict(os.environ, {"DATABASE_URL": "postgres://test"})
    @patch("civicos.storage.postgres_backend.PostgresBackend")
    def test_successful_migration(self, MockPostgres, tmp_path):
        state_dir = tmp_path / "state" / "california"
        state_dir.mkdir(parents=True)

        data = {
            "state_legislation": {
                "ca-sb9": {"bill_number": "SB 9", "bill_name": "Housing"},
                "ca-ab1400": {"bill_number": "AB 1400", "bill_name": "CalCare"},
            }
        }
        (state_dir / "housing.json").write_text(json.dumps(data))

        mock_backend = MagicMock()
        MockPostgres.return_value = mock_backend
        mock_backend.store_legislation.return_value = 2
        mock_backend.get_legislation_count.return_value = 2

        result = migrate_json_to_cloud(
            state="california",
            output_dir=str(tmp_path),
        )
        assert result == 0

        call_kwargs = mock_backend.store_legislation.call_args
        assert call_kwargs.kwargs["state"] == "CA"
        assert call_kwargs.kwargs["topic"] == "housing"
        bills = call_kwargs.kwargs["bills"]
        assert len(bills) == 2
        # Verify bill_id is set from dict key
        bill_ids = {b["bill_id"] for b in bills}
        assert "ca-sb9" in bill_ids
        assert "ca-ab1400" in bill_ids

    @patch.dict(os.environ, {"DATABASE_URL": "postgres://test"})
    @patch("civicos.storage.postgres_backend.PostgresBackend")
    def test_migration_skips_empty_state_legislation(self, MockPostgres, tmp_path):
        state_dir = tmp_path / "state" / "california"
        state_dir.mkdir(parents=True)

        # Housing has bills, budget has empty state_legislation
        (state_dir / "housing.json").write_text(json.dumps({
            "state_legislation": {"ca-sb9": {"bill_number": "SB 9"}}
        }))
        (state_dir / "budget.json").write_text(json.dumps({
            "state_legislation": {}
        }))

        mock_backend = MagicMock()
        MockPostgres.return_value = mock_backend
        mock_backend.store_legislation.return_value = 1
        mock_backend.get_legislation_count.return_value = 1

        result = migrate_json_to_cloud(
            state="california",
            output_dir=str(tmp_path),
        )
        assert result == 0

        # store_legislation called only for housing (budget was empty)
        assert mock_backend.store_legislation.call_count == 1


# ---------------------------------------------------------------------------
# run_legislative_refresh
# ---------------------------------------------------------------------------

class TestRunLegislativeRefresh:
    """Tests for the main legislative refresh logic."""

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_legiscan_key_returns_none(self, tmp_path):
        os.environ.pop("LEGISCAN_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        result = run_legislative_refresh(
            topic="housing",
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )
        assert result is None

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123"}, clear=True)
    def test_dry_run_returns_validated_dict(self, tmp_path):
        os.environ.pop("OPENAI_API_KEY", None)
        result = run_legislative_refresh(
            topic="housing",
            state="california",
            dry_run=True,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )
        assert result == {"dry_run": True, "status": "validated", "cloud": False}

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123"}, clear=True)
    def test_dry_run_all_topics_validated(self, tmp_path):
        os.environ.pop("OPENAI_API_KEY", None)
        result = run_legislative_refresh(
            topic="all",
            state="california",
            dry_run=True,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )
        assert result["dry_run"] is True
        assert result["status"] == "validated"

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123"}, clear=True)
    def test_dry_run_cloud_without_database_url_returns_none(self, tmp_path):
        """Cloud mode requires DATABASE_URL even in dry-run."""
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("DATABASE_URL", None)
        result = run_legislative_refresh(
            topic="housing",
            dry_run=True,
            cloud=True,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )
        assert result is None

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123"}, clear=True)
    def test_cloud_mode_without_database_url_returns_none(self, tmp_path):
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("OPENAI_API_KEY", None)
        result = run_legislative_refresh(
            topic="housing",
            cloud=True,
            dry_run=False,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )
        assert result is None

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123"}, clear=True)
    @patch("civicos_extraction.legislative.legislative_discovery.LegislativeDiscovery")
    def test_single_topic_no_results(self, MockDiscovery, tmp_path):
        os.environ.pop("OPENAI_API_KEY", None)
        mock_discovery = MagicMock()
        MockDiscovery.return_value = mock_discovery
        mock_discovery.discover_topic.return_value = []
        mock_discovery.legiscan.get_query_stats.return_value = {
            "queries_this_session": 1,
            "monthly_limit": 30000,
            "estimated_remaining": 29999,
        }

        result = run_legislative_refresh(
            topic="housing",
            state="california",
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result["total_bills_filtered"] == 0
        assert result["topics"] == ["housing"]
        assert result["state"] == "california"
        assert result["results_by_topic"]["housing"]["bills_filtered"] == 0

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123"}, clear=True)
    @patch("civicos_extraction.legislative.legislative_discovery.LegislativeDiscovery")
    def test_all_topics_expands_to_all_keywords(self, MockDiscovery, tmp_path):
        os.environ.pop("OPENAI_API_KEY", None)
        mock_discovery = MagicMock()
        MockDiscovery.return_value = mock_discovery
        mock_discovery.discover_topic.return_value = []
        mock_discovery.legiscan.get_query_stats.return_value = {
            "queries_this_session": 5,
            "monthly_limit": 30000,
            "estimated_remaining": 29995,
        }

        result = run_legislative_refresh(
            topic="all",
            state="california",
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert set(result["topics"]) == set(TOPIC_KEYWORDS.keys())
        assert mock_discovery.discover_topic.call_count == len(TOPIC_KEYWORDS)

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123"}, clear=True)
    @patch("civicos_extraction.legislative.legislative_discovery.LegislativeDiscovery")
    def test_saves_checkpoint_per_topic(self, MockDiscovery, tmp_path):
        os.environ.pop("OPENAI_API_KEY", None)
        mock_discovery = MagicMock()
        MockDiscovery.return_value = mock_discovery
        mock_discovery.discover_topic.return_value = [
            {"bill_number": "SB 100", "leverage_point": "public_comment"}
        ]
        mock_discovery.legiscan.get_query_stats.return_value = {
            "queries_this_session": 1,
            "monthly_limit": 30000,
            "estimated_remaining": 29999,
        }

        cp_dir = tmp_path / "cp"
        run_legislative_refresh(
            topic="housing",
            state="california",
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(cp_dir),
        )

        cp_file = cp_dir / "legislative_california_housing.json"
        assert cp_file.exists()
        data = json.loads(cp_file.read_text())
        assert data["topic"] == "housing"
        assert data["state"] == "california"
        assert data["bills_fetched"] == 1
        assert data["bills_filtered"] == 1

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123"}, clear=True)
    @patch("civicos_extraction.legislative.legislative_discovery.LegislativeDiscovery")
    def test_writes_summary_json_output(self, MockDiscovery, tmp_path):
        os.environ.pop("OPENAI_API_KEY", None)
        mock_discovery = MagicMock()
        MockDiscovery.return_value = mock_discovery
        mock_discovery.discover_topic.return_value = []
        mock_discovery.legiscan.get_query_stats.return_value = {
            "queries_this_session": 1,
            "monthly_limit": 30000,
            "estimated_remaining": 29999,
        }

        out_dir = tmp_path / "out"
        result = run_legislative_refresh(
            topic="housing",
            state="california",
            output_dir=str(out_dir),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert "output_file" in result
        output_file = Path(result["output_file"])
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert data["state"] == "california"
        assert data["topics"] == ["housing"]

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123", "DATABASE_URL": "postgres://test"}, clear=True)
    @patch("civicos.storage.postgres_backend.PostgresBackend")
    @patch("civicos_extraction.legislative.legislative_discovery.LegislativeDiscovery")
    def test_cloud_mode_stores_to_postgres(self, MockDiscovery, MockPostgres, tmp_path):
        os.environ.pop("OPENAI_API_KEY", None)
        mock_discovery = MagicMock()
        MockDiscovery.return_value = mock_discovery
        mock_discovery.discover_topic.return_value = [
            {"bill_number": "SB 100", "bill_id": 12345, "leverage_point": "public_comment"}
        ]
        mock_discovery.legiscan.get_query_stats.return_value = {
            "queries_this_session": 1,
            "monthly_limit": 30000,
            "estimated_remaining": 29999,
        }

        mock_backend = MagicMock()
        MockPostgres.return_value = mock_backend
        mock_backend.store_legislation.return_value = 1
        mock_backend.get_legislation_count.return_value = 1

        result = run_legislative_refresh(
            topic="housing",
            state="california",
            cloud=True,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result["cloud"] is True
        mock_backend.store_legislation.assert_called_once()
        call_kwargs = mock_backend.store_legislation.call_args
        assert call_kwargs.kwargs["state"] == "CA"
        assert call_kwargs.kwargs["topic"] == "housing"

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123", "DATABASE_URL": "postgres://test"}, clear=True)
    @patch("civicos.storage.postgres_backend.PostgresBackend")
    @patch("civicos_extraction.legislative.legislative_discovery.LegislativeDiscovery")
    def test_cloud_normalizes_bill_id_from_bill_number(self, MockDiscovery, MockPostgres, tmp_path):
        """Bills with bill_number get normalized bill_ids (e.g. SB 838 -> ca-sb838)."""
        os.environ.pop("OPENAI_API_KEY", None)
        mock_discovery = MagicMock()
        MockDiscovery.return_value = mock_discovery
        mock_discovery.discover_topic.return_value = [
            {"bill_number": "SB 838", "leverage_point": "public_comment"}
        ]
        mock_discovery.legiscan.get_query_stats.return_value = {
            "queries_this_session": 1,
            "monthly_limit": 30000,
            "estimated_remaining": 29999,
        }

        mock_backend = MagicMock()
        MockPostgres.return_value = mock_backend
        mock_backend.store_legislation.return_value = 1
        mock_backend.get_legislation_count.return_value = 1

        run_legislative_refresh(
            topic="housing",
            state="california",
            cloud=True,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        bills = mock_backend.store_legislation.call_args.kwargs["bills"]
        assert bills[0]["bill_id"] == "ca-sb838"

    @patch.dict(os.environ, {"LEGISCAN_API_KEY": "key123"}, clear=True)
    @patch("civicos_extraction.legislative.legislative_discovery.LegislativeDiscovery")
    def test_discovery_exception_yields_zero_results(self, MockDiscovery, tmp_path):
        os.environ.pop("OPENAI_API_KEY", None)
        mock_discovery = MagicMock()
        MockDiscovery.return_value = mock_discovery
        mock_discovery.discover_topic.side_effect = RuntimeError("API timeout")
        mock_discovery.legiscan.get_query_stats.return_value = {
            "queries_this_session": 1,
            "monthly_limit": 30000,
            "estimated_remaining": 29999,
        }

        result = run_legislative_refresh(
            topic="housing",
            state="california",
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result["total_bills_filtered"] == 0
        assert result["results_by_topic"]["housing"]["bills_filtered"] == 0


# ---------------------------------------------------------------------------
# run_legislative (dispatch)
# ---------------------------------------------------------------------------

class TestRunLegislative:
    """Tests for the top-level dispatch function."""

    def _make_args(self, **overrides):
        defaults = {
            "topic": "housing",
            "state": "california",
            "days_back": 90,
            "limit": 20,
            "output_dir": "/tmp/test_out",
            "dry_run": False,
            "schedule": False,
            "checkpoint_dir": "/tmp/test_cp",
            "cloud": False,
            "migrate_json": False,
            "bulk": False,
            "enrich": False,
            "verbose": False,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_migrate_json_without_cloud_returns_1(self):
        args = self._make_args(migrate_json=True, cloud=False)
        result = run_legislative(args)
        assert result == 1

    @patch("civicos_extraction.cli.legislative.migrate_json_to_cloud")
    def test_migrate_json_with_cloud_calls_migrate(self, mock_migrate):
        mock_migrate.return_value = 0
        args = self._make_args(migrate_json=True, cloud=True)
        result = run_legislative(args)
        assert result == 0
        mock_migrate.assert_called_once_with(
            state="california",
            output_dir="/tmp/test_out",
            dry_run=False,
        )

    def test_bulk_without_cloud_returns_1(self):
        args = self._make_args(bulk=True, cloud=False)
        result = run_legislative(args)
        assert result == 1

    @patch("civicos_extraction.cli.legislative.bulk_ingest_legislation")
    def test_bulk_with_cloud_calls_bulk_ingest(self, mock_bulk):
        mock_bulk.return_value = 0
        args = self._make_args(bulk=True, cloud=True)
        result = run_legislative(args)
        assert result == 0
        mock_bulk.assert_called_once_with(state="california", dry_run=False)

    @patch("civicos_extraction.cli.legislative._run_post_store_enrichment")
    @patch("civicos_extraction.cli.legislative.bulk_ingest_legislation")
    def test_bulk_with_enrich_calls_enrichment_on_success(self, mock_bulk, mock_enrich):
        mock_bulk.return_value = 0
        mock_enrich.return_value = 0
        args = self._make_args(bulk=True, cloud=True, enrich=True)
        result = run_legislative(args)
        assert result == 0
        mock_enrich.assert_called_once_with("california")

    @patch("civicos_extraction.cli.legislative._run_post_store_enrichment")
    @patch("civicos_extraction.cli.legislative.bulk_ingest_legislation")
    def test_bulk_failure_skips_enrichment(self, mock_bulk, mock_enrich):
        mock_bulk.return_value = 1
        args = self._make_args(bulk=True, cloud=True, enrich=True)
        result = run_legislative(args)
        assert result == 1
        mock_enrich.assert_not_called()

    @patch("civicos_extraction.cli.legislative._run_post_store_enrichment")
    @patch("civicos_extraction.cli.legislative.bulk_ingest_legislation")
    def test_bulk_dry_run_skips_enrichment(self, mock_bulk, mock_enrich):
        mock_bulk.return_value = 0
        args = self._make_args(bulk=True, cloud=True, enrich=True, dry_run=True)
        result = run_legislative(args)
        assert result == 0
        mock_enrich.assert_not_called()

    @patch("civicos_extraction.cli.legislative.run_legislative_refresh")
    def test_normal_mode_calls_refresh(self, mock_refresh):
        mock_refresh.return_value = {"total_bills_filtered": 5}
        args = self._make_args()
        result = run_legislative(args)
        assert result == 0
        mock_refresh.assert_called_once()

    @patch("civicos_extraction.cli.legislative.run_legislative_refresh")
    def test_normal_mode_returns_1_on_none(self, mock_refresh):
        mock_refresh.return_value = None
        args = self._make_args()
        result = run_legislative(args)
        assert result == 1

    @patch("civicos_extraction.cli.legislative.run_legislative_refresh")
    def test_dry_run_none_result_returns_0(self, mock_refresh):
        """In dry-run mode, None result is not a failure."""
        mock_refresh.return_value = None
        args = self._make_args(dry_run=True)
        result = run_legislative(args)
        assert result == 0

    @patch("civicos_extraction.cli.legislative._run_post_store_enrichment")
    @patch("civicos_extraction.cli.legislative.run_legislative_refresh")
    def test_normal_with_enrich_and_cloud(self, mock_refresh, mock_enrich):
        mock_refresh.return_value = {"total_bills_filtered": 3}
        mock_enrich.return_value = 0
        args = self._make_args(cloud=True, enrich=True)
        result = run_legislative(args)
        assert result == 0
        mock_enrich.assert_called_once_with("california")

    @patch("civicos_extraction.cli.legislative._run_post_store_enrichment")
    @patch("civicos_extraction.cli.legislative.run_legislative_refresh")
    def test_enrich_without_cloud_skipped(self, mock_refresh, mock_enrich):
        mock_refresh.return_value = {"total_bills_filtered": 3}
        args = self._make_args(cloud=False, enrich=True)
        result = run_legislative(args)
        assert result == 0
        mock_enrich.assert_not_called()


# ---------------------------------------------------------------------------
# _run_post_store_enrichment
# ---------------------------------------------------------------------------

class TestRunPostStoreEnrichment:
    """Tests for leverage point enrichment after store."""

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_anthropic_key_returns_0(self):
        """Enrichment is skipped without ANTHROPIC_API_KEY."""
        os.environ.pop("ANTHROPIC_API_KEY", None)
        result = _run_post_store_enrichment("california")
        assert result == 0

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    @patch("civicos_extraction.cli.enrich_leverage_points.enrich_batch")
    @patch("civicos_extraction.cli.enrich_leverage_points.get_unenriched_bills")
    def test_no_unenriched_bills_returns_0(self, mock_get, mock_enrich, mock_stats):
        mock_get.return_value = []
        result = _run_post_store_enrichment("california")
        assert result == 0
        mock_enrich.assert_not_called()

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "DATABASE_URL": "postgres://test"})
    @patch("civicos.storage.postgres_backend.PostgresBackend")
    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    @patch("civicos_extraction.cli.enrich_leverage_points.enrich_batch")
    @patch("civicos_extraction.cli.enrich_leverage_points.get_unenriched_bills")
    def test_state_mapping_california_to_CA(self, mock_get, mock_enrich, mock_stats, MockPg):
        mock_get.return_value = [{"bill_id": "ca-sb100"}]
        mock_enrich.return_value = [{"bill_id": "ca-sb100", "leverage_points": []}]
        mock_stats.return_value = {"enriched": 1, "total": 1}
        mock_backend = MagicMock()
        MockPg.return_value = mock_backend

        result = _run_post_store_enrichment("california")
        assert result == 0
        mock_get.assert_called_once_with("CA")

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "DATABASE_URL": "postgres://test"})
    @patch("civicos.storage.postgres_backend.PostgresBackend")
    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    @patch("civicos_extraction.cli.enrich_leverage_points.enrich_batch")
    @patch("civicos_extraction.cli.enrich_leverage_points.get_unenriched_bills")
    def test_state_mapping_federal_to_US(self, mock_get, mock_enrich, mock_stats, MockPg):
        mock_get.return_value = [{"bill_id": "us-hr100"}]
        mock_enrich.return_value = [{"bill_id": "us-hr100", "leverage_points": []}]
        mock_stats.return_value = {"enriched": 1, "total": 1}
        mock_backend = MagicMock()
        MockPg.return_value = mock_backend

        result = _run_post_store_enrichment("federal")
        assert result == 0
        mock_get.assert_called_once_with("US")

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "DATABASE_URL": "postgres://test"})
    @patch("civicos.storage.postgres_backend.PostgresBackend")
    @patch("civicos_extraction.cli.enrich_leverage_points.get_leverage_stats")
    @patch("civicos_extraction.cli.enrich_leverage_points.enrich_batch")
    @patch("civicos_extraction.cli.enrich_leverage_points.get_unenriched_bills")
    def test_unknown_state_uppercased(self, mock_get, mock_enrich, mock_stats, MockPg):
        mock_get.return_value = []
        result = _run_post_store_enrichment("texas")
        assert result == 0
        mock_get.assert_called_once_with("TEXAS")
