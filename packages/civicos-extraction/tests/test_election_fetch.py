"""Tests for election_fetch.py — shared election fetch dispatch logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.election_fetch import fetch_elections_for_jurisdiction

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
    @patch("civicos_extraction.election_fetch._fetch_civera")
    @patch(_PG_BACKEND)
    def test_dispatches_civera(self, mock_backend_cls, mock_civera, mock_officials):
        """Civera source in config dispatches to _fetch_civera."""
        mock_civera.return_value = {"status": "completed", "elections_stored": 3}
        mock_officials.return_value = {"status": "skipped"}

        sources = {"civera_election_stats": {"county_slug": "marin"}}
        result = fetch_elections_for_jurisdiction("city-test", sources, database_url="postgresql://test")

        mock_civera.assert_called_once()
        assert result["civera_election_stats"]["status"] == "completed"

    @patch("civicos_extraction.election_fetch._fetch_officials")
    @patch("civicos_extraction.election_fetch._fetch_ca_sos")
    @patch(_PG_BACKEND)
    def test_dispatches_ca_sos(self, mock_backend_cls, mock_ca_sos, mock_officials):
        """CA SOS source in config dispatches to _fetch_ca_sos."""
        mock_ca_sos.return_value = {"status": "completed", "contests_stored": 5}
        mock_officials.return_value = {"status": "skipped"}

        sources = {"ca_sos_results": {"county": "marin"}}
        result = fetch_elections_for_jurisdiction("city-test", sources, database_url="postgresql://test")

        mock_ca_sos.assert_called_once()
        assert result["ca_sos_results"]["status"] == "completed"

    @patch("civicos_extraction.election_fetch._fetch_officials")
    @patch("civicos_extraction.election_fetch._fetch_ca_sos")
    @patch("civicos_extraction.election_fetch._fetch_civera")
    @patch(_PG_BACKEND)
    def test_dispatches_both_sources(self, mock_backend_cls, mock_civera, mock_ca_sos, mock_officials):
        """Multiple sources each get dispatched."""
        mock_civera.return_value = {"status": "completed"}
        mock_ca_sos.return_value = {"status": "completed"}
        mock_officials.return_value = {"status": "skipped"}

        sources = {
            "civera_election_stats": {"county_slug": "marin"},
            "ca_sos_results": {"county": "marin"},
        }
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

        sources = {"ca_sos_results": True}
        with patch("civicos_extraction.election_fetch._fetch_ca_sos") as mock_sos:
            mock_sos.return_value = {"status": "completed"}
            result = fetch_elections_for_jurisdiction("city-test", sources, database_url="postgresql://test")

        mock_officials.assert_called_once()
        assert result["elected_officials"]["status"] == "completed"

    @patch("civicos_extraction.election_fetch._fetch_officials")
    @patch("civicos_extraction.election_fetch._fetch_marin_legacy")
    @patch(_PG_BACKEND)
    def test_dispatches_marin_legacy(self, mock_backend_cls, mock_marin, mock_officials):
        """Legacy marin_registrar_results source dispatches correctly."""
        mock_marin.return_value = {"status": "completed"}
        mock_officials.return_value = {"status": "skipped"}

        sources = {"marin_registrar_results": True}
        result = fetch_elections_for_jurisdiction("city-test", sources, database_url="postgresql://test")

        mock_marin.assert_called_once()
        assert "marin_registrar_results" in result

    @patch("civicos_extraction.election_fetch._fetch_officials")
    @patch("civicos_extraction.election_fetch._fetch_civera")
    @patch(_PG_BACKEND)
    def test_elapsed_seconds_included(self, mock_backend_cls, mock_civera, mock_officials):
        """Result includes elapsed_seconds for non-empty sources."""
        mock_civera.return_value = {"status": "completed"}
        mock_officials.return_value = {"status": "skipped"}

        sources = {"civera_election_stats": {"county_slug": "marin"}}
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
