"""
Tests for the SeeClickFix refresh CLI module.

Tests derive_place_url, SeeClickFixCheckpoint, checkpoint I/O,
run_seeclickfix_refresh (dry-run, pagination, resume, new/updated counting),
run_seeclickfix dispatch, and add_seeclickfix_parser.
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.cli.seeclickfix import (
    SeeClickFixCheckpoint,
    add_seeclickfix_parser,
    checkpoint_path_for_seeclickfix,
    derive_place_url,
    load_checkpoint,
    run_seeclickfix,
    run_seeclickfix_refresh,
    save_checkpoint,
)


# ---------------------------------------------------------------------------
# derive_place_url — pure logic, no mocks
# ---------------------------------------------------------------------------


class TestDerivePlaceUrl:
    def test_strips_city_prefix(self):
        assert derive_place_url("city-san-rafael") == "san-rafael"

    def test_strips_county_prefix(self):
        assert derive_place_url("county-marin") == "marin"

    def test_strips_town_prefix(self):
        assert derive_place_url("town-fairfax") == "fairfax"

    def test_preserves_id_without_known_prefix(self):
        assert derive_place_url("district-west") == "district-west"

    def test_only_strips_first_matching_prefix(self):
        # "city-" is stripped, rest preserved even if it contains "county-"
        assert derive_place_url("city-county-line") == "county-line"

    def test_empty_string_passthrough(self):
        assert derive_place_url("") == ""

    def test_multi_word_city(self):
        assert derive_place_url("city-new-york") == "new-york"


# ---------------------------------------------------------------------------
# SeeClickFixCheckpoint
# ---------------------------------------------------------------------------


class TestSeeClickFixCheckpoint:
    def test_to_dict_returns_all_fields(self):
        cp = SeeClickFixCheckpoint(
            jurisdiction_id="city-san-rafael",
            last_page=5,
            issues_fetched=250,
            issues_new=30,
            issues_updated=10,
            timestamp="2026-04-01T10:00:00",
        )
        d = cp.to_dict()
        assert d["jurisdiction_id"] == "city-san-rafael"
        assert d["last_page"] == 5
        assert d["issues_fetched"] == 250
        assert d["issues_new"] == 30
        assert d["issues_updated"] == 10
        assert d["timestamp"] == "2026-04-01T10:00:00"

    def test_from_dict_reconstructs_checkpoint(self):
        data = {
            "jurisdiction_id": "city-mill-valley",
            "last_page": 3,
            "issues_fetched": 100,
            "issues_new": 20,
            "issues_updated": 5,
            "timestamp": "2026-04-01T08:00:00",
        }
        cp = SeeClickFixCheckpoint.from_dict(data)
        assert cp.jurisdiction_id == "city-mill-valley"
        assert cp.last_page == 3
        assert cp.issues_fetched == 100
        assert cp.issues_new == 20
        assert cp.issues_updated == 5
        assert cp.timestamp == "2026-04-01T08:00:00"

    def test_roundtrip_to_dict_from_dict(self):
        original = SeeClickFixCheckpoint(
            jurisdiction_id="city-san-rafael",
            last_page=10,
            issues_fetched=500,
            issues_new=50,
            issues_updated=25,
            timestamp="2026-04-01T12:00:00",
        )
        reconstructed = SeeClickFixCheckpoint.from_dict(original.to_dict())
        assert reconstructed.jurisdiction_id == original.jurisdiction_id
        assert reconstructed.last_page == original.last_page
        assert reconstructed.issues_fetched == original.issues_fetched
        assert reconstructed.issues_new == original.issues_new
        assert reconstructed.issues_updated == original.issues_updated
        assert reconstructed.timestamp == original.timestamp


# ---------------------------------------------------------------------------
# checkpoint_path_for_seeclickfix
# ---------------------------------------------------------------------------


class TestCheckpointPath:
    def test_returns_correct_filename(self, tmp_path):
        path = checkpoint_path_for_seeclickfix("city-san-rafael", str(tmp_path))
        assert path == tmp_path / "seeclickfix_city-san-rafael.json"

    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "sub" / "dir"
        path = checkpoint_path_for_seeclickfix("city-test", str(nested))
        assert path.parent.exists()
        assert path.name == "seeclickfix_city-test.json"

    def test_different_jurisdictions_different_files(self, tmp_path):
        p1 = checkpoint_path_for_seeclickfix("city-san-rafael", str(tmp_path))
        p2 = checkpoint_path_for_seeclickfix("city-mill-valley", str(tmp_path))
        assert p1 != p2
        assert "san-rafael" in p1.name
        assert "mill-valley" in p2.name


# ---------------------------------------------------------------------------
# save_checkpoint / load_checkpoint
# ---------------------------------------------------------------------------


class TestCheckpointIO:
    def test_save_and_load_roundtrip(self, tmp_path):
        cp = SeeClickFixCheckpoint(
            jurisdiction_id="city-san-rafael",
            last_page=5,
            issues_fetched=250,
            issues_new=30,
            issues_updated=10,
            timestamp="2026-04-01T10:00:00",
        )
        path = tmp_path / "test_checkpoint.json"
        save_checkpoint(cp, path)
        loaded = load_checkpoint(path)

        assert loaded is not None
        assert loaded.jurisdiction_id == "city-san-rafael"
        assert loaded.last_page == 5
        assert loaded.issues_fetched == 250
        assert loaded.issues_new == 30
        assert loaded.issues_updated == 10
        assert loaded.timestamp == "2026-04-01T10:00:00"

    def test_load_returns_none_for_missing_file(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        assert load_checkpoint(path) is None

    def test_load_returns_none_for_corrupt_json(self, tmp_path):
        path = tmp_path / "corrupt.json"
        path.write_text("not valid json {{{")
        assert load_checkpoint(path) is None

    def test_save_creates_valid_json(self, tmp_path):
        cp = SeeClickFixCheckpoint(
            jurisdiction_id="city-test",
            last_page=1,
            issues_fetched=10,
            issues_new=5,
            issues_updated=2,
            timestamp="2026-04-01T09:00:00",
        )
        path = tmp_path / "check.json"
        save_checkpoint(cp, path)

        raw = json.loads(path.read_text())
        assert raw["jurisdiction_id"] == "city-test"
        assert raw["last_page"] == 1


# ---------------------------------------------------------------------------
# run_seeclickfix_refresh — mock the HTTP client, test real logic
# ---------------------------------------------------------------------------


def _make_mock_client():
    """Create a mock SeeClickFixClient for injection."""
    return MagicMock()


class TestRunSeeclickfixRefreshDryRun:
    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_dry_run_success_returns_validated(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [{"id": 1}],
            "metadata": {"page": 1, "per_page": 1, "has_more": False},
        }
        MockClient.return_value = mock_client

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            dry_run=True,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result == {"dry_run": True, "status": "validated"}

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_dry_run_api_error_returns_none(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [],
            "metadata": {"error": "Connection refused"},
        }
        MockClient.return_value = mock_client

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            dry_run=True,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result is None

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_dry_run_uses_derived_place_url(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [{"id": 1}],
            "metadata": {},
        }
        MockClient.return_value = mock_client

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            dry_run=True,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        call_kwargs = mock_client.get_issues.call_args[1]
        assert call_kwargs["place_url"] == "san-rafael"
        assert result == {"dry_run": True, "status": "validated"}

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_dry_run_uses_explicit_place_url(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [{"id": 1}],
            "metadata": {},
        }
        MockClient.return_value = mock_client

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            place_url="custom-place",
            dry_run=True,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        call_kwargs = mock_client.get_issues.call_args[1]
        assert call_kwargs["place_url"] == "custom-place"
        assert result == {"dry_run": True, "status": "validated"}


class TestRunSeeclickfixRefreshFetch:
    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_single_page_fetch_saves_output(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [
                {"id": "101", "title": "Pothole on 4th", "updated_at": "2026-04-01T10:00:00"},
                {"id": "102", "title": "Graffiti", "updated_at": "2026-04-01T11:00:00"},
            ],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        out_dir = str(tmp_path / "out")
        cp_dir = str(tmp_path / "cp")

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            max_pages=10,
            per_page=100,
            output_dir=out_dir,
            checkpoint_dir=cp_dir,
        )

        assert result is not None
        assert result["jurisdiction_id"] == "city-san-rafael"
        assert result["issues_fetched"] == 2
        assert result["issues_new"] == 2
        assert result["issues_updated"] == 0

        # Verify output file was written
        output_file = Path(out_dir) / "seeclickfix_city_san_rafael.json"
        assert output_file.exists()
        saved = json.loads(output_file.read_text())
        assert saved["count"] == 2
        assert saved["jurisdiction_id"] == "city-san-rafael"
        assert saved["place_url"] == "san-rafael"
        assert len(saved["issues"]) == 2

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_multi_page_fetch_paginates(self, MockClient, tmp_path):
        mock_client = MagicMock()
        # Page 1: full page (has_more = True)
        page1 = {
            "issues": [{"id": str(i), "updated_at": "2026-04-01"} for i in range(100)],
            "metadata": {"has_more": True},
        }
        # Page 2: partial page (has_more = False)
        page2 = {
            "issues": [{"id": str(i), "updated_at": "2026-04-01"} for i in range(100, 130)],
            "metadata": {"has_more": False},
        }
        mock_client.get_issues.side_effect = [page1, page2]
        MockClient.return_value = mock_client

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            max_pages=10,
            per_page=100,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result["issues_fetched"] == 130
        assert mock_client.get_issues.call_count == 2

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_stops_at_max_pages(self, MockClient, tmp_path):
        mock_client = MagicMock()
        # Every page returns full results with has_more=True
        full_page = {
            "issues": [{"id": "1", "updated_at": "2026-04-01"}],
            "metadata": {"has_more": True},
        }
        mock_client.get_issues.return_value = full_page
        MockClient.return_value = mock_client

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            max_pages=3,
            per_page=1,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result["issues_fetched"] == 3
        assert mock_client.get_issues.call_count == 3

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_api_error_stops_fetching(self, MockClient, tmp_path):
        mock_client = MagicMock()
        # First page succeeds, second has error
        mock_client.get_issues.side_effect = [
            {
                "issues": [{"id": "1", "updated_at": "2026-04-01"}],
                "metadata": {"has_more": True},
            },
            {
                "issues": [],
                "metadata": {"error": "Rate limited"},
            },
        ]
        MockClient.return_value = mock_client

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            max_pages=10,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        # Should still return the issues from page 1
        assert result["issues_fetched"] == 1

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_empty_first_page_returns_none(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result is None

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_has_more_fallback_uses_per_page_comparison(self, MockClient, tmp_path):
        """When metadata lacks has_more, the code uses len(issues)==per_page as fallback."""
        mock_client = MagicMock()
        # Page 1: exactly per_page issues, no has_more in metadata → continue
        mock_client.get_issues.side_effect = [
            {
                "issues": [{"id": str(i), "updated_at": "2026-04-01"} for i in range(5)],
                "metadata": {},  # no has_more key
            },
            {
                "issues": [{"id": str(i), "updated_at": "2026-04-01"} for i in range(5, 8)],
                "metadata": {},  # 3 < 5 → stop
            },
        ]
        MockClient.return_value = mock_client

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            max_pages=10,
            per_page=5,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result["issues_fetched"] == 8
        assert mock_client.get_issues.call_count == 2


class TestRunSeeclickfixRefreshNewVsUpdated:
    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_detects_new_issues(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [
                {"id": "201", "title": "New pothole", "updated_at": "2026-04-01T10:00:00"},
            ],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        out_dir = tmp_path / "out"
        result = run_seeclickfix_refresh(
            "city-san-rafael",
            output_dir=str(out_dir),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result["issues_new"] == 1
        assert result["issues_updated"] == 0

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_detects_updated_issues_from_existing_file(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [
                {"id": "201", "title": "Pothole fixed", "updated_at": "2026-04-02T10:00:00"},
            ],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        out_dir = tmp_path / "out"
        out_dir.mkdir(parents=True)
        # Pre-populate existing issues file (list format)
        existing = [
            {"id": "201", "title": "Pothole", "updated_at": "2026-04-01T10:00:00"},
        ]
        output_file = out_dir / "seeclickfix_city_san_rafael.json"
        output_file.write_text(json.dumps(existing))

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            output_dir=str(out_dir),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result["issues_new"] == 0
        assert result["issues_updated"] == 1

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_detects_unchanged_existing_issues(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [
                {"id": "201", "title": "Pothole", "updated_at": "2026-04-01T10:00:00"},
            ],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        out_dir = tmp_path / "out"
        out_dir.mkdir(parents=True)
        existing = [
            {"id": "201", "title": "Pothole", "updated_at": "2026-04-01T10:00:00"},
        ]
        output_file = out_dir / "seeclickfix_city_san_rafael.json"
        output_file.write_text(json.dumps(existing))

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            output_dir=str(out_dir),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result["issues_new"] == 0
        assert result["issues_updated"] == 0

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_loads_existing_from_dict_format(self, MockClient, tmp_path):
        """Existing file may be in {issues: [...]} dict format."""
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [
                {"id": "301", "title": "New issue", "updated_at": "2026-04-02T10:00:00"},
            ],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        out_dir = tmp_path / "out"
        out_dir.mkdir(parents=True)
        existing = {
            "jurisdiction_id": "city-san-rafael",
            "issues": [
                {"id": "201", "title": "Old issue", "updated_at": "2026-04-01T10:00:00"},
            ],
        }
        output_file = out_dir / "seeclickfix_city_san_rafael.json"
        output_file.write_text(json.dumps(existing))

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            output_dir=str(out_dir),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        assert result["issues_new"] == 1  # 301 is new
        assert result["issues_updated"] == 0

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_corrupt_existing_file_treated_as_empty(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [
                {"id": "401", "title": "Issue", "updated_at": "2026-04-01T10:00:00"},
            ],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        out_dir = tmp_path / "out"
        out_dir.mkdir(parents=True)
        output_file = out_dir / "seeclickfix_city_san_rafael.json"
        output_file.write_text("broken json {{{")

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            output_dir=str(out_dir),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        # All issues treated as new since existing couldn't be loaded
        assert result["issues_new"] == 1
        assert result["issues_updated"] == 0


class TestRunSeeclickfixRefreshCheckpoint:
    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_resumes_from_todays_checkpoint(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [{"id": "501", "updated_at": "2026-04-01"}],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        cp_dir = tmp_path / "cp"
        cp_dir.mkdir(parents=True)
        today = datetime.now().strftime("%Y-%m-%d")
        cp_data = {
            "jurisdiction_id": "city-san-rafael",
            "last_page": 3,
            "issues_fetched": 150,
            "issues_new": 0,
            "issues_updated": 0,
            "timestamp": f"{today}T08:00:00",
        }
        cp_path = cp_dir / "seeclickfix_city-san-rafael.json"
        cp_path.write_text(json.dumps(cp_data))

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            max_pages=10,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(cp_dir),
        )

        # Should start from page 4 (last_page + 1)
        first_call_kwargs = mock_client.get_issues.call_args_list[0][1]
        assert first_call_kwargs["page"] == 4
        assert result is not None
        assert result["issues_fetched"] == 1

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_ignores_stale_checkpoint(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [{"id": "601", "updated_at": "2026-04-01"}],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        cp_dir = tmp_path / "cp"
        cp_dir.mkdir(parents=True)
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        cp_data = {
            "jurisdiction_id": "city-san-rafael",
            "last_page": 7,
            "issues_fetched": 350,
            "issues_new": 0,
            "issues_updated": 0,
            "timestamp": f"{yesterday}T08:00:00",
        }
        cp_path = cp_dir / "seeclickfix_city-san-rafael.json"
        cp_path.write_text(json.dumps(cp_data))

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            max_pages=10,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(cp_dir),
        )

        # Should start from page 1 (stale checkpoint ignored)
        first_call_kwargs = mock_client.get_issues.call_args_list[0][1]
        assert first_call_kwargs["page"] == 1
        assert result is not None
        assert result["issues_fetched"] == 1

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_saves_checkpoint_every_5_pages(self, MockClient, tmp_path):
        mock_client = MagicMock()
        # 6 pages, each returns 1 issue with has_more=True, then page 7 is empty
        pages = []
        for i in range(1, 7):
            pages.append({
                "issues": [{"id": str(i), "updated_at": "2026-04-01"}],
                "metadata": {"has_more": True},
            })
        pages.append({
            "issues": [],
            "metadata": {"has_more": False},
        })
        mock_client.get_issues.side_effect = pages
        MockClient.return_value = mock_client

        cp_dir = tmp_path / "cp"

        run_seeclickfix_refresh(
            "city-san-rafael",
            max_pages=10,
            per_page=1,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(cp_dir),
        )

        # Checkpoint saved at page 5 (mid-run) + final checkpoint
        cp_path = cp_dir / "seeclickfix_city-san-rafael.json"
        assert cp_path.exists()
        saved = json.loads(cp_path.read_text())
        # Final checkpoint should reflect the last page reached
        assert saved["issues_fetched"] == 6

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_final_checkpoint_has_correct_counts(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [
                {"id": "701", "title": "A", "updated_at": "2026-04-01T10:00:00"},
                {"id": "702", "title": "B", "updated_at": "2026-04-01T11:00:00"},
            ],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        cp_dir = tmp_path / "cp"
        result = run_seeclickfix_refresh(
            "city-san-rafael",
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(cp_dir),
        )

        cp_path = cp_dir / "seeclickfix_city-san-rafael.json"
        saved_cp = json.loads(cp_path.read_text())
        assert saved_cp["issues_new"] == result["issues_new"]
        assert saved_cp["issues_updated"] == result["issues_updated"]
        assert saved_cp["issues_fetched"] == 2


class TestRunSeeclickfixRefreshStatusFilter:
    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_passes_status_filter_to_client(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [{"id": "1", "updated_at": "2026-04-01"}],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            status="closed",
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        call_kwargs = mock_client.get_issues.call_args[1]
        assert call_kwargs["status"] == "closed"
        assert result is not None
        assert result["issues_fetched"] == 1

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_none_status_passed_through(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [{"id": "1", "updated_at": "2026-04-01"}],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        result = run_seeclickfix_refresh(
            "city-san-rafael",
            status=None,
            output_dir=str(tmp_path / "out"),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        call_kwargs = mock_client.get_issues.call_args[1]
        assert call_kwargs["status"] is None
        assert result is not None
        assert result["issues_fetched"] == 1


# ---------------------------------------------------------------------------
# run_seeclickfix — dispatch logic
# ---------------------------------------------------------------------------


class TestRunSeeclickfix:
    def _make_args(self, **overrides):
        defaults = {
            "verbose": False,
            "schedule": False,
            "jurisdiction": "city-san-rafael",
            "place_url": None,
            "status": None,
            "max_pages": 50,
            "per_page": 100,
            "output_dir": "data/pilot",
            "checkpoint_dir": "data/checkpoints",
            "dry_run": False,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    @patch("civicos_extraction.cli.seeclickfix.run_seeclickfix_refresh")
    def test_non_schedule_returns_0_on_success(self, mock_refresh):
        mock_refresh.return_value = {"issues_fetched": 10}
        args = self._make_args()
        assert run_seeclickfix(args) == 0

    @patch("civicos_extraction.cli.seeclickfix.run_seeclickfix_refresh")
    def test_non_schedule_returns_1_on_failure(self, mock_refresh):
        mock_refresh.return_value = None
        args = self._make_args()
        assert run_seeclickfix(args) == 1

    @patch("civicos_extraction.cli.seeclickfix.run_seeclickfix_refresh")
    def test_dry_run_returns_0_even_when_refresh_returns_none(self, mock_refresh):
        mock_refresh.return_value = None
        args = self._make_args(dry_run=True)
        assert run_seeclickfix(args) == 0

    @patch("civicos_extraction.cli.seeclickfix.run_scheduled")
    def test_schedule_mode_calls_run_scheduled(self, mock_scheduled):
        args = self._make_args(schedule=True)
        result = run_seeclickfix(args)
        assert result == 0
        mock_scheduled.assert_called_once_with(
            "city-san-rafael",
            place_url=None,
            status=None,
            max_pages=50,
            per_page=100,
            output_dir="data/pilot",
            checkpoint_dir="data/checkpoints",
        )

    @patch("civicos_extraction.cli.seeclickfix.run_seeclickfix_refresh")
    def test_verbose_sets_debug_logging(self, mock_refresh, monkeypatch):
        mock_refresh.return_value = {"issues_fetched": 5}
        import logging

        args = self._make_args(verbose=True)
        run_seeclickfix(args)
        assert logging.getLogger().level == logging.DEBUG
        # Reset to avoid leaking state
        logging.getLogger().setLevel(logging.WARNING)

    @patch("civicos_extraction.cli.seeclickfix.run_seeclickfix_refresh")
    def test_passes_all_args_to_refresh(self, mock_refresh):
        mock_refresh.return_value = {"issues_fetched": 1}
        args = self._make_args(
            jurisdiction="city-mill-valley",
            place_url="mill-valley",
            status="open",
            max_pages=10,
            per_page=50,
            output_dir="/tmp/out",
            checkpoint_dir="/tmp/cp",
            dry_run=True,
        )
        result = run_seeclickfix(args)

        assert result == 0
        mock_refresh.assert_called_once_with(
            "city-mill-valley",
            place_url="mill-valley",
            status="open",
            max_pages=10,
            per_page=50,
            output_dir="/tmp/out",
            checkpoint_dir="/tmp/cp",
            dry_run=True,
        )


# ---------------------------------------------------------------------------
# add_seeclickfix_parser
# ---------------------------------------------------------------------------


class TestAddSeeclickfixParser:
    def test_registers_seeclickfix_subcommand(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_seeclickfix_parser(subparsers)

        # Parse a minimal valid command
        args = parser.parse_args(["seeclickfix", "--jurisdiction", "city-san-rafael"])
        assert args.jurisdiction == "city-san-rafael"

    def test_defaults_for_optional_args(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_seeclickfix_parser(subparsers)

        args = parser.parse_args(["seeclickfix", "--jurisdiction", "city-test"])
        assert args.max_pages == 50
        assert args.per_page == 100
        assert args.output_dir == "data/pilot"
        assert args.checkpoint_dir == "data/checkpoints"
        assert args.dry_run is False
        assert args.schedule is False
        assert args.place_url is None
        assert args.status is None

    def test_all_options_parse_correctly(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_seeclickfix_parser(subparsers)

        args = parser.parse_args([
            "seeclickfix",
            "--jurisdiction", "city-san-rafael",
            "--place-url", "san-rafael",
            "--status", "open",
            "--max-pages", "25",
            "--per-page", "50",
            "--output-dir", "/tmp/out",
            "--checkpoint-dir", "/tmp/cp",
            "--dry-run",
            "--schedule",
        ])
        assert args.jurisdiction == "city-san-rafael"
        assert args.place_url == "san-rafael"
        assert args.status == "open"
        assert args.max_pages == 25
        assert args.per_page == 50
        assert args.output_dir == "/tmp/out"
        assert args.checkpoint_dir == "/tmp/cp"
        assert args.dry_run is True
        assert args.schedule is True

    def test_status_choices_reject_invalid(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        add_seeclickfix_parser(subparsers)

        with pytest.raises(SystemExit):
            parser.parse_args(["seeclickfix", "--jurisdiction", "x", "--status", "invalid"])


# ---------------------------------------------------------------------------
# Output file naming
# ---------------------------------------------------------------------------


class TestOutputFileNaming:
    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_output_file_replaces_hyphens_with_underscores(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [{"id": "1", "updated_at": "2026-04-01"}],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        out_dir = tmp_path / "out"
        run_seeclickfix_refresh(
            "city-san-rafael",
            output_dir=str(out_dir),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        output_file = out_dir / "seeclickfix_city_san_rafael.json"
        assert output_file.exists()

    @patch("civicos_extraction.clients.seeclickfix.SeeClickFixClient")
    def test_output_file_path_in_result(self, MockClient, tmp_path):
        mock_client = MagicMock()
        mock_client.get_issues.return_value = {
            "issues": [{"id": "1", "updated_at": "2026-04-01"}],
            "metadata": {"has_more": False},
        }
        MockClient.return_value = mock_client

        out_dir = tmp_path / "out"
        result = run_seeclickfix_refresh(
            "city-san-rafael",
            output_dir=str(out_dir),
            checkpoint_dir=str(tmp_path / "cp"),
        )

        expected_path = str(out_dir / "seeclickfix_city_san_rafael.json")
        assert result["output_file"] == expected_path
