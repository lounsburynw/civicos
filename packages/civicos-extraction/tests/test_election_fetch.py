"""Tests for election_fetch.py — shared election fetch dispatch logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.election_fetch import (
    fetch_elections_for_jurisdiction,
    _FETCH_HANDLERS,
)

# PostgresBackend is imported inside the function body, so we patch at the source
_PG_BACKEND = "civicos.storage.postgres_backend.PostgresBackend"


class TestFetchElectionsForJurisdiction:
    """Test the top-level dispatch function."""

    def test_no_database_url(self):
        """Returns error when no DATABASE_URL available."""
        with patch.dict("os.environ", {}, clear=True):
            result = fetch_elections_for_jurisdiction("city-test", {"civera_election_stats": {}})
        assert "error" in result
        assert "DATABASE_URL" in result["error"]

    def test_no_election_sources(self):
        """Returns skipped when no election sources configured."""
        result = fetch_elections_for_jurisdiction("city-test", {}, database_url="postgresql://test")
        assert result["skipped"] is True

    @patch("civicos_extraction.election_fetch._fetch_officials")
    @patch(_PG_BACKEND)
    def test_dispatches_civera(self, mock_backend_cls, mock_officials):
        """Civera source in config dispatches to registered handler."""
        mock_handler = MagicMock(return_value={"status": "completed", "elections_stored": 3})
        mock_officials.return_value = {"status": "skipped"}

        sources = {"civera_election_stats": {"county_slug": "marin"}}
        with patch.dict(_FETCH_HANDLERS, {"civera_election_stats": mock_handler}):
            result = fetch_elections_for_jurisdiction("city-test", sources, database_url="postgresql://test")

        mock_handler.assert_called_once()
        assert result["civera_election_stats"]["status"] == "completed"

    @patch("civicos_extraction.election_fetch._fetch_officials")
    @patch(_PG_BACKEND)
    def test_dispatches_ca_sos(self, mock_backend_cls, mock_officials):
        """CA SOS source in config dispatches to registered handler."""
        mock_handler = MagicMock(return_value={"status": "completed", "contests_stored": 5})
        mock_officials.return_value = {"status": "skipped"}

        sources = {"ca_sos_results": {"county": "marin"}}
        with patch.dict(_FETCH_HANDLERS, {"ca_sos_results": mock_handler}):
            result = fetch_elections_for_jurisdiction("city-test", sources, database_url="postgresql://test")

        mock_handler.assert_called_once()
        assert result["ca_sos_results"]["status"] == "completed"

    @patch("civicos_extraction.election_fetch._fetch_officials")
    @patch(_PG_BACKEND)
    def test_dispatches_both_sources(self, mock_backend_cls, mock_officials):
        """Multiple sources each get dispatched to their handlers."""
        mock_civera = MagicMock(return_value={"status": "completed"})
        mock_ca_sos = MagicMock(return_value={"status": "completed"})
        mock_officials.return_value = {"status": "skipped"}

        sources = {
            "civera_election_stats": {"county_slug": "marin"},
            "ca_sos_results": {"county": "marin"},
        }
        with patch.dict(_FETCH_HANDLERS, {
            "civera_election_stats": mock_civera,
            "ca_sos_results": mock_ca_sos,
        }):
            result = fetch_elections_for_jurisdiction("city-test", sources, database_url="postgresql://test")

        mock_civera.assert_called_once()
        mock_ca_sos.assert_called_once()
        assert "civera_election_stats" in result
        assert "ca_sos_results" in result
        assert "elected_officials" in result

    @patch("civicos_extraction.election_fetch._fetch_officials")
    @patch(_PG_BACKEND)
    def test_always_fetches_officials(self, mock_backend_cls, mock_officials):
        """Officials fetch always runs even with no election sources."""
        mock_officials.return_value = {"status": "completed", "officials_stored": 5}
        mock_handler = MagicMock(return_value={"status": "completed"})

        sources = {"ca_sos_results": True}
        with patch.dict(_FETCH_HANDLERS, {"ca_sos_results": mock_handler}):
            result = fetch_elections_for_jurisdiction("city-test", sources, database_url="postgresql://test")

        mock_officials.assert_called_once()
        assert result["elected_officials"]["status"] == "completed"

    @patch("civicos_extraction.election_fetch._fetch_officials")
    @patch(_PG_BACKEND)
    def test_elapsed_seconds_included(self, mock_backend_cls, mock_officials):
        """Result includes elapsed_seconds for non-empty sources."""
        mock_handler = MagicMock(return_value={"status": "completed"})
        mock_officials.return_value = {"status": "skipped"}

        sources = {"civera_election_stats": {"county_slug": "marin"}}
        with patch.dict(_FETCH_HANDLERS, {"civera_election_stats": mock_handler}):
            result = fetch_elections_for_jurisdiction("city-test", sources, database_url="postgresql://test")
        assert "elapsed_seconds" in result


class TestFetchCivera:
    """Test _fetch_civera error handling."""

    def test_config_true_treated_as_empty_dict(self):
        """config=True should be treated as empty dict."""
        from civicos_extraction.election_fetch import _fetch_civera

        mock_backend = MagicMock()
        result = _fetch_civera("city-unknown", True, mock_backend)
        assert result["status"] in ("skipped", "failed")


class TestFetchClarity:
    """Test _fetch_clarity handler."""

    def test_missing_state_skips(self):
        """Clarity handler requires explicit state in config."""
        from civicos_extraction.election_fetch import _fetch_clarity

        mock_backend = MagicMock()
        result = _fetch_clarity("city-test", {"county": "butte"}, mock_backend)
        assert result["status"] == "skipped"
        assert "state" in result["reason"]

    def test_missing_county_skips(self):
        from civicos_extraction.election_fetch import _fetch_clarity

        mock_backend = MagicMock()
        result = _fetch_clarity("city-test", {"state": "CA"}, mock_backend)
        assert result["status"] == "skipped"
        assert "county" in result["reason"]


class TestCheckPartialFetch:
    """Test the partial-fetch guard."""

    def test_warns_on_zero_results_with_existing(self):
        """Should log a warning when fetch returns 0 but data exists."""
        import logging
        from civicos_extraction.election_fetch import _check_partial_fetch

        mock_backend = MagicMock()
        mock_backend.get_election_count.return_value = 5

        with patch.object(logging.getLogger("civicos_extraction.election_fetch"), "warning") as mock_warn:
            _check_partial_fetch("city-test", "test_source", mock_backend, 0, 0)
            mock_warn.assert_called_once()
            assert "0 elections" in mock_warn.call_args[0][0]

    def test_warns_on_large_drop(self):
        """Should warn when new count drops >50% from existing."""
        import logging
        from civicos_extraction.election_fetch import _check_partial_fetch

        mock_backend = MagicMock()
        mock_backend.get_election_count.return_value = 10

        with patch.object(logging.getLogger("civicos_extraction.election_fetch"), "warning") as mock_warn:
            _check_partial_fetch("city-test", "test_source", mock_backend, 3, 5)
            mock_warn.assert_called_once()
            assert "50%" in mock_warn.call_args[0][0]

    def test_no_warning_on_normal_fetch(self):
        """No warning when new count is reasonable."""
        import logging
        from civicos_extraction.election_fetch import _check_partial_fetch

        mock_backend = MagicMock()
        mock_backend.get_election_count.return_value = 5

        with patch.object(logging.getLogger("civicos_extraction.election_fetch"), "warning") as mock_warn:
            _check_partial_fetch("city-test", "test_source", mock_backend, 5, 10)
            mock_warn.assert_not_called()

    def test_no_warning_on_first_fetch(self):
        """No warning when no existing data (first fetch)."""
        import logging
        from civicos_extraction.election_fetch import _check_partial_fetch

        mock_backend = MagicMock()
        mock_backend.get_election_count.return_value = 0

        with patch.object(logging.getLogger("civicos_extraction.election_fetch"), "warning") as mock_warn:
            _check_partial_fetch("city-test", "test_source", mock_backend, 2, 5)
            mock_warn.assert_not_called()

    def test_graceful_on_backend_error(self):
        """Should not raise if backend.get_election_count fails."""
        from civicos_extraction.election_fetch import _check_partial_fetch

        mock_backend = MagicMock()
        mock_backend.get_election_count.side_effect = Exception("db error")

        # Should not raise
        _check_partial_fetch("city-test", "test_source", mock_backend, 0, 0)


class TestFetchOfficials:
    """Test _fetch_officials graceful degradation."""

    def test_no_api_keys_skips(self):
        """Without API keys, officials fetch is skipped."""
        from civicos_extraction.election_fetch import _fetch_officials

        mock_backend = MagicMock()
        with patch.dict("os.environ", {}, clear=True):
            result = _fetch_officials("city-test", mock_backend)
        assert result["status"] == "skipped"
        assert "API keys" in result["reason"]
