"""
Tests for core router: health, status, jurisdictions, config, help,
onboarding cards, and data provenance.

Tests real behavior by mocking I/O (database connections, filesystem,
env vars) while exercising all logic in the subject module.

To run:
    pytest packages/civicos-services/tests/test_core.py -q --override-ini="addopts="
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from civicos_services.servers.routers.core import (
    _check_database_health,
    _check_chromadb_health,
    _check_external_services,
    router,
)


# === Fixtures ===

@pytest.fixture
def app():
    """Create a FastAPI app with the core router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Test client with auth dependency overridden for authenticated endpoints."""
    from civicos_services.servers.routers.dependencies import verify_auth, AuthContext

    async def mock_auth():
        return AuthContext(key_id="test-key", source="env", tier="admin")

    app.dependency_overrides[verify_auth] = mock_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client(app):
    """Test client without auth override — public endpoints only."""
    with TestClient(app) as c:
        yield c


# === Helper Function Tests ===

class TestCheckDatabaseHealth:
    def test_returns_healthy_when_civicos_loads(self):
        mock_civicos_module = MagicMock()
        mock_civicos_module.CivicOS.return_value = MagicMock()
        with patch.dict("sys.modules", {"civicos": mock_civicos_module}):
            result = _check_database_health()
            assert result["status"] == "healthy"
            assert result["message"] == "Database connected"

    def test_returns_unhealthy_on_exception(self):
        mock_civicos_module = MagicMock()
        mock_civicos_module.CivicOS.side_effect = ConnectionError("Connection refused")
        with patch.dict("sys.modules", {"civicos": mock_civicos_module}):
            result = _check_database_health()
            assert result["status"] == "unhealthy"
            assert "Connection refused" in result["message"]


class TestCheckChromadbHealth:
    def test_returns_healthy_when_backend_exists(self):
        mock_vector_module = MagicMock()
        mock_vector_module.get_vector_backend.return_value = MagicMock()
        with patch.dict("sys.modules", {
            "civicos": MagicMock(),
            "civicos.storage": MagicMock(),
            "civicos.storage.vector_backend": mock_vector_module,
        }):
            result = _check_chromadb_health()
            assert result["status"] == "healthy"

    def test_returns_degraded_when_backend_is_none(self):
        mock_vector_module = MagicMock()
        mock_vector_module.get_vector_backend.return_value = None
        with patch.dict("sys.modules", {
            "civicos": MagicMock(),
            "civicos.storage": MagicMock(),
            "civicos.storage.vector_backend": mock_vector_module,
        }):
            result = _check_chromadb_health()
            assert result["status"] == "degraded"

    def test_returns_degraded_on_exception(self):
        mock_vector_module = MagicMock()
        mock_vector_module.get_vector_backend.side_effect = RuntimeError("No chromadb")
        with patch.dict("sys.modules", {
            "civicos": MagicMock(),
            "civicos.storage": MagicMock(),
            "civicos.storage.vector_backend": mock_vector_module,
        }):
            result = _check_chromadb_health()
            assert result["status"] == "degraded"
            assert "No chromadb" in result["message"]


class TestCheckExternalServices:
    def test_returns_both_services_available(self):
        result = _check_external_services()
        assert result["legistar"] == "available"
        assert result["seeclickfix"] == "available"
        assert len(result) == 2


# === Public Endpoint Tests ===

class TestGetStatus:
    def test_returns_healthy_when_all_checks_pass(self, unauthed_client):
        mock_civicos_module = MagicMock()
        mock_civicos_module.CivicOS.return_value = MagicMock()
        mock_vector_module = MagicMock()
        mock_vector_module.get_vector_backend.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake newsletter file
            events_dir = Path(tmpdir) / "data" / "events"
            events_dir.mkdir(parents=True)
            newsletter = events_dir / "newsletter_2026_01.json"
            newsletter.write_text("{}")

            with patch.dict("sys.modules", {
                "civicos": mock_civicos_module,
                "civicos.storage": MagicMock(),
                "civicos.storage.vector_backend": mock_vector_module,
            }):
                with patch(
                    "civicos_services.servers.routers.core.Path",
                    side_effect=lambda p: Path(tmpdir) / p if p == "data/events" else Path(p),
                ):
                    resp = unauthed_client.get("/api/status")

            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == "healthy"
            assert body["version"] == "0.4.0"
            assert body["timestamp"].endswith("Z")
            assert body["authentication"] == "Bearer token required for protected endpoints"
            assert "/api/status" in body["endpoints"]["public"]
            assert len(body["endpoints"]["authenticated"]) == 7

    def test_returns_unhealthy_when_database_fails(self, unauthed_client):
        mock_civicos_module = MagicMock()
        mock_civicos_module.CivicOS.side_effect = Exception("DB down")
        mock_vector_module = MagicMock()
        mock_vector_module.get_vector_backend.return_value = MagicMock()

        with patch.dict("sys.modules", {
            "civicos": mock_civicos_module,
            "civicos.storage": MagicMock(),
            "civicos.storage.vector_backend": mock_vector_module,
        }):
            with patch(
                "civicos_services.servers.routers.core.Path",
                side_effect=lambda p: Path("/nonexistent") if p == "data/events" else Path(p),
            ):
                resp = unauthed_client.get("/api/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "unhealthy"
        assert body["checks"]["database"]["status"] == "unhealthy"

    def test_returns_degraded_when_data_missing_but_db_healthy(self, unauthed_client):
        mock_civicos_module = MagicMock()
        mock_civicos_module.CivicOS.return_value = MagicMock()
        mock_vector_module = MagicMock()
        mock_vector_module.get_vector_backend.return_value = MagicMock()

        with patch.dict("sys.modules", {
            "civicos": mock_civicos_module,
            "civicos.storage": MagicMock(),
            "civicos.storage.vector_backend": mock_vector_module,
        }):
            # Point to nonexistent dir so no newsletter files found
            with patch(
                "civicos_services.servers.routers.core.Path",
                side_effect=lambda p: Path("/nonexistent") if p == "data/events" else Path(p),
            ):
                resp = unauthed_client.get("/api/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "degraded"
        assert body["checks"]["data"]["status"] == "degraded"
        assert body["checks"]["data"]["schema_files_available"] == 0
        assert body["checks"]["data"]["latest_data"] is None

    def test_degraded_when_legistar_unavailable(self, unauthed_client):
        """If external services report unavailable, overall degrades."""
        mock_civicos_module = MagicMock()
        mock_civicos_module.CivicOS.return_value = MagicMock()
        mock_vector_module = MagicMock()
        mock_vector_module.get_vector_backend.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            events_dir = Path(tmpdir) / "data" / "events"
            events_dir.mkdir(parents=True)
            (events_dir / "newsletter_2026_01.json").write_text("{}")

            with patch.dict("sys.modules", {
                "civicos": mock_civicos_module,
                "civicos.storage": MagicMock(),
                "civicos.storage.vector_backend": mock_vector_module,
            }):
                with patch(
                    "civicos_services.servers.routers.core.Path",
                    side_effect=lambda p: Path(tmpdir) / p if p == "data/events" else Path(p),
                ):
                    with patch(
                        "civicos_services.servers.routers.core._check_external_services",
                        return_value={"legistar": "unavailable", "seeclickfix": "available"},
                    ):
                        resp = unauthed_client.get("/api/status")

        body = resp.json()
        assert body["status"] == "degraded"


class TestGetGoogleMapsKey:
    def test_returns_api_key_when_set(self, unauthed_client):
        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "test-key-abc123"}):
            resp = unauthed_client.get("/api/config/google-maps-key")
        assert resp.status_code == 200
        assert resp.json()["api_key"] == "test-key-abc123"

    def test_returns_500_when_key_not_set(self, unauthed_client):
        with patch.dict(os.environ, {}, clear=True):
            # Make sure the key is actually absent
            with patch("civicos_services.servers.routers.core.os.getenv", return_value=None):
                resp = unauthed_client.get("/api/config/google-maps-key")
        assert resp.status_code == 500
        assert "not configured" in resp.json()["detail"]

    def test_returns_exact_key_value_not_truncated(self, unauthed_client):
        long_key = "AIzaSyB" + "x" * 30
        with patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": long_key}):
            resp = unauthed_client.get("/api/config/google-maps-key")
        assert resp.json()["api_key"] == long_key


class TestGetHelp:
    def test_returns_correct_api_metadata(self, unauthed_client):
        resp = unauthed_client.get("/help")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Civic API"
        assert body["version"] == "0.4.0"
        assert body["documentation"] == "/docs"
        assert body["openapi"] == "/openapi.json"

    def test_lists_public_endpoints(self, unauthed_client):
        resp = unauthed_client.get("/help")
        body = resp.json()
        public = body["endpoints"]["public"]
        assert public["/health"] == "Basic health check"
        assert public["/api/status"] == "Detailed system status"
        assert public["/help"] == "This documentation"
        assert "/api/config/google-maps-key" in public

    def test_lists_authenticated_endpoints(self, unauthed_client):
        resp = unauthed_client.get("/help")
        body = resp.json()
        authed = body["endpoints"]["authenticated"]
        assert authed["/api/events"] == "List civic events and opportunities"
        assert authed["/api/jurisdictions"] == "List jurisdictions"
        assert authed["/api/conversation"] == "AI conversation"

    def test_authentication_info(self, unauthed_client):
        resp = unauthed_client.get("/help")
        body = resp.json()
        assert body["authentication"]["method"] == "Bearer token"
        assert "Authorization: Bearer" in body["authentication"]["header"]


class TestGetOnboardingCards:
    def test_returns_four_cards(self, unauthed_client):
        resp = unauthed_client.get("/api/onboarding/cards")
        assert resp.status_code == 200
        cards = resp.json()["cards"]
        assert len(cards) == 4

    def test_card_ids_are_correct(self, unauthed_client):
        resp = unauthed_client.get("/api/onboarding/cards")
        cards = resp.json()["cards"]
        card_ids = [c["id"] for c in cards]
        assert card_ids == ["welcome", "events", "issues", "community"]

    def test_card_actions_are_correct(self, unauthed_client):
        resp = unauthed_client.get("/api/onboarding/cards")
        cards = resp.json()["cards"]
        actions = [c["action"] for c in cards]
        assert actions == ["get_started", "browse_events", "file_issue", "explore_community"]

    def test_each_card_has_title_and_description(self, unauthed_client):
        resp = unauthed_client.get("/api/onboarding/cards")
        cards = resp.json()["cards"]
        for card in cards:
            assert len(card["title"]) > 5
            assert len(card["description"]) > 10

    def test_welcome_card_content(self, unauthed_client):
        resp = unauthed_client.get("/api/onboarding/cards")
        welcome = resp.json()["cards"][0]
        assert welcome["title"] == "Welcome to Civic"
        assert "civic engagement" in welcome["description"].lower()


# === Authenticated Endpoint Tests ===

class TestGetJurisdictions:
    def test_returns_empty_when_no_events_dir(self, client):
        with patch(
            "civicos_services.servers.routers.core.Path",
            side_effect=lambda p: Path("/nonexistent") if p == "data/events" else Path(p),
        ):
            with patch.dict("sys.modules", {
                "civicos_services.monitoring.automated_civic_refresh": MagicMock(CITY_CONFIGS={}),
            }):
                resp = client.get("/api/jurisdictions")

        assert resp.status_code == 200
        body = resp.json()
        assert body["jurisdictions"] == []
        assert body["total"] == 0

    def test_parses_jurisdiction_from_event_filename(self, client):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_dir = Path(tmpdir)
            event_file = events_dir / "events_city-san-rafael_20260101_120000.json"
            event_file.write_text(json.dumps({"events": [{"id": 1}, {"id": 2}, {"id": 3}]}))

            with patch(
                "civicos_services.servers.routers.core.Path",
                side_effect=lambda p: Path(tmpdir) if p == "data/events" else Path(p),
            ):
                with patch.dict("sys.modules", {
                    "civicos_services.monitoring.automated_civic_refresh": MagicMock(CITY_CONFIGS={}),
                    "civicos_services.storage.issue_storage": MagicMock(side_effect=ImportError),
                }):
                    resp = client.get("/api/jurisdictions")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        j = body["jurisdictions"][0]
        assert j["id"] == "city-san-rafael"
        assert j["name"] == "San Rafael"
        assert j["type"] == "city"
        assert j["event_count"] == 3

    def test_county_type_detected_from_id(self, client):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_dir = Path(tmpdir)
            event_file = events_dir / "events_county-marin_20260101_120000.json"
            event_file.write_text(json.dumps({"events": [{"id": 1}]}))

            with patch(
                "civicos_services.servers.routers.core.Path",
                side_effect=lambda p: Path(tmpdir) if p == "data/events" else Path(p),
            ):
                with patch.dict("sys.modules", {
                    "civicos_services.monitoring.automated_civic_refresh": MagicMock(CITY_CONFIGS={}),
                    "civicos_services.storage.issue_storage": MagicMock(side_effect=ImportError),
                }):
                    resp = client.get("/api/jurisdictions")

        j = resp.json()["jurisdictions"][0]
        assert j["type"] == "county"
        # The code only strips "city-" prefix, not "county-", so county remains in name
        assert j["name"] == "County Marin"

    def test_takes_max_event_count_across_files(self, client):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_dir = Path(tmpdir)
            # Two files for same jurisdiction with different counts
            f1 = events_dir / "events_city-san-rafael_20260101_120000.json"
            f1.write_text(json.dumps({"events": [{"id": 1}, {"id": 2}]}))
            f2 = events_dir / "events_city-san-rafael_20260102_120000.json"
            f2.write_text(json.dumps({"events": [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}, {"id": 5}]}))

            with patch(
                "civicos_services.servers.routers.core.Path",
                side_effect=lambda p: Path(tmpdir) if p == "data/events" else Path(p),
            ):
                with patch.dict("sys.modules", {
                    "civicos_services.monitoring.automated_civic_refresh": MagicMock(CITY_CONFIGS={}),
                    "civicos_services.storage.issue_storage": MagicMock(side_effect=ImportError),
                }):
                    resp = client.get("/api/jurisdictions")

        j = resp.json()["jurisdictions"][0]
        assert j["event_count"] == 5

    def test_sorts_jurisdictions_by_event_count_descending(self, client):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_dir = Path(tmpdir)
            # City A: 2 events, City B: 5 events
            fa = events_dir / "events_city-alpha_20260101_120000.json"
            fa.write_text(json.dumps({"events": [{"id": 1}, {"id": 2}]}))
            fb = events_dir / "events_city-beta_20260101_120000.json"
            fb.write_text(json.dumps({"events": [{"id": i} for i in range(5)]}))

            with patch(
                "civicos_services.servers.routers.core.Path",
                side_effect=lambda p: Path(tmpdir) if p == "data/events" else Path(p),
            ):
                with patch.dict("sys.modules", {
                    "civicos_services.monitoring.automated_civic_refresh": MagicMock(CITY_CONFIGS={}),
                    "civicos_services.storage.issue_storage": MagicMock(side_effect=ImportError),
                }):
                    resp = client.get("/api/jurisdictions")

        jurisdictions = resp.json()["jurisdictions"]
        assert jurisdictions[0]["id"] == "city-beta"
        assert jurisdictions[0]["event_count"] == 5
        assert jurisdictions[1]["id"] == "city-alpha"
        assert jurisdictions[1]["event_count"] == 2

    def test_includes_city_config_metadata(self, client):
        mock_refresh = MagicMock()
        mock_refresh.CITY_CONFIGS = {
            "city-san-rafael": {
                "cdbg_allocation": "$1.2M",
                "population": 60000,
                "timezone": "America/Los_Angeles",
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            events_dir = Path(tmpdir)
            f = events_dir / "events_city-san-rafael_20260101_120000.json"
            f.write_text(json.dumps({"events": [{"id": 1}]}))

            with patch(
                "civicos_services.servers.routers.core.Path",
                side_effect=lambda p: Path(tmpdir) if p == "data/events" else Path(p),
            ):
                with patch.dict("sys.modules", {
                    "civicos_services.monitoring.automated_civic_refresh": mock_refresh,
                    "civicos_services.storage.issue_storage": MagicMock(side_effect=ImportError),
                }):
                    resp = client.get("/api/jurisdictions")

        j = resp.json()["jurisdictions"][0]
        assert j["cdbg_allocation"] == "$1.2M"
        assert j["population"] == 60000
        assert j["timezone"] == "America/Los_Angeles"

    def test_defaults_when_no_city_config(self, client):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_dir = Path(tmpdir)
            f = events_dir / "events_city-unknown_20260101_120000.json"
            f.write_text(json.dumps({"events": [{"id": 1}]}))

            with patch(
                "civicos_services.servers.routers.core.Path",
                side_effect=lambda p: Path(tmpdir) if p == "data/events" else Path(p),
            ):
                with patch.dict("sys.modules", {
                    "civicos_services.monitoring.automated_civic_refresh": MagicMock(CITY_CONFIGS={}),
                    "civicos_services.storage.issue_storage": MagicMock(side_effect=ImportError),
                }):
                    resp = client.get("/api/jurisdictions")

        j = resp.json()["jurisdictions"][0]
        assert j["cdbg_allocation"] == "N/A"
        assert j["population"] is None
        assert j["timezone"] == "America/Los_Angeles"

    def test_ignores_malformed_event_filenames(self, client):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_dir = Path(tmpdir)
            # Valid file
            f1 = events_dir / "events_city-san-rafael_20260101_120000.json"
            f1.write_text(json.dumps({"events": [{"id": 1}]}))
            # Malformed filename (no date suffix)
            f2 = events_dir / "events_badname.json"
            f2.write_text(json.dumps({"events": [{"id": 1}]}))

            with patch(
                "civicos_services.servers.routers.core.Path",
                side_effect=lambda p: Path(tmpdir) if p == "data/events" else Path(p),
            ):
                with patch.dict("sys.modules", {
                    "civicos_services.monitoring.automated_civic_refresh": MagicMock(CITY_CONFIGS={}),
                    "civicos_services.storage.issue_storage": MagicMock(side_effect=ImportError),
                }):
                    resp = client.get("/api/jurisdictions")

        body = resp.json()
        assert body["total"] == 1
        assert body["jurisdictions"][0]["id"] == "city-san-rafael"

    def test_handles_corrupt_event_file(self, client):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_dir = Path(tmpdir)
            # Valid file
            f1 = events_dir / "events_city-alpha_20260101_120000.json"
            f1.write_text(json.dumps({"events": [{"id": 1}]}))
            # Corrupt JSON
            f2 = events_dir / "events_city-beta_20260101_120000.json"
            f2.write_text("not valid json{{{")

            with patch(
                "civicos_services.servers.routers.core.Path",
                side_effect=lambda p: Path(tmpdir) if p == "data/events" else Path(p),
            ):
                with patch.dict("sys.modules", {
                    "civicos_services.monitoring.automated_civic_refresh": MagicMock(CITY_CONFIGS={}),
                    "civicos_services.storage.issue_storage": MagicMock(side_effect=ImportError),
                }):
                    resp = client.get("/api/jurisdictions")

        # Should still succeed, just skip the corrupt file
        body = resp.json()
        assert body["total"] == 1
        assert body["jurisdictions"][0]["id"] == "city-alpha"

    def test_name_formatting_removes_city_prefix_and_titlecases(self, client):
        with tempfile.TemporaryDirectory() as tmpdir:
            events_dir = Path(tmpdir)
            f = events_dir / "events_city-mill-valley_20260101_120000.json"
            f.write_text(json.dumps({"events": [{"id": 1}]}))

            with patch(
                "civicos_services.servers.routers.core.Path",
                side_effect=lambda p: Path(tmpdir) if p == "data/events" else Path(p),
            ):
                with patch.dict("sys.modules", {
                    "civicos_services.monitoring.automated_civic_refresh": MagicMock(CITY_CONFIGS={}),
                    "civicos_services.storage.issue_storage": MagicMock(side_effect=ImportError),
                }):
                    resp = client.get("/api/jurisdictions")

        j = resp.json()["jurisdictions"][0]
        assert j["name"] == "Mill Valley"


class TestDataProvenance:
    def test_returns_provenance_data(self, unauthed_client):
        # Build mock DataStatus report
        mock_corpus_count = MagicMock()
        mock_corpus_count.corpus_type = "decisions"
        mock_corpus_count.display_name = "Decisions"
        mock_corpus_count.storage_count = 44
        mock_corpus_count.vector_count = 44
        mock_corpus_count.coverage_percent = 100.0
        mock_corpus_count.last_indexed = datetime(2026, 4, 1, 12, 0, 0)

        mock_stats = MagicMock()
        mock_stats.earliest_meeting = datetime(2025, 10, 1)
        mock_stats.latest_meeting = datetime(2026, 4, 1)
        mock_stats.last_updated = datetime(2026, 4, 10)

        mock_report = MagicMock()
        mock_report.corpus_counts = {"decisions": mock_corpus_count}
        mock_report.storage_stats = mock_stats
        mock_report.total_storage_docs = 500
        mock_report.total_vector_docs = 400
        mock_report.overall_coverage_percent = 80.0
        mock_report.timestamp = datetime(2026, 4, 10, 12, 0, 0)

        mock_civic = MagicMock()
        mock_civic._storage = MagicMock()
        mock_civic._vectors = MagicMock()

        mock_data_status = MagicMock()
        mock_data_status.return_value.summary.return_value = mock_report

        mock_registry = MagicMock()
        mock_registry.get_jurisdiction_url.return_value = "https://mcp.example.com"
        mock_registry.get_relay_url.return_value = "https://relay.example.com"

        with patch.dict("sys.modules", {
            "civicos": MagicMock(CivicOS=MagicMock(return_value=mock_civic)),
            "civicos.diagnostics": MagicMock(DataStatus=mock_data_status),
            "civicos.registry": mock_registry,
        }):
            resp = unauthed_client.get("/api/tools/data-provenance")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["jurisdiction"] == "city-san-rafael"
        assert data["total_storage_docs"] == 500
        assert data["total_vector_docs"] == 400
        assert data["overall_coverage_percent"] == 80.0
        assert len(data["corpora"]) == 1
        assert data["corpora"][0]["corpus_type"] == "decisions"
        assert data["corpora"][0]["storage_count"] == 44
        assert data["corpora"][0]["coverage_percent"] == 100.0
        assert data["freshness"]["earliest_meeting"] == "2025-10-01T00:00:00"
        assert data["freshness"]["latest_meeting"] == "2026-04-01T00:00:00"
        assert data["mcp_endpoint"] == "https://mcp.example.com"
        assert data["relay_url"] == "https://relay.example.com"

    def test_returns_500_on_failure(self, unauthed_client):
        mock_civicos = MagicMock()
        mock_civicos.CivicOS.side_effect = RuntimeError("DB unavailable")

        with patch.dict("sys.modules", {
            "civicos": mock_civicos,
            "civicos.diagnostics": MagicMock(),
            "civicos.registry": MagicMock(),
        }):
            resp = unauthed_client.get("/api/tools/data-provenance")

        assert resp.status_code == 500
        assert "DB unavailable" in resp.json()["detail"]

    def test_handles_null_coverage_percent(self, unauthed_client):
        mock_corpus_count = MagicMock()
        mock_corpus_count.corpus_type = "transcripts"
        mock_corpus_count.display_name = "Transcripts"
        mock_corpus_count.storage_count = 10
        mock_corpus_count.vector_count = 0
        mock_corpus_count.coverage_percent = None
        mock_corpus_count.last_indexed = None

        mock_report = MagicMock()
        mock_report.corpus_counts = {"transcripts": mock_corpus_count}
        mock_report.storage_stats = None
        mock_report.total_storage_docs = 10
        mock_report.total_vector_docs = 0
        mock_report.overall_coverage_percent = None
        mock_report.timestamp = datetime(2026, 4, 10, 12, 0, 0)

        mock_civic = MagicMock()

        mock_data_status = MagicMock()
        mock_data_status.return_value.summary.return_value = mock_report

        mock_registry = MagicMock()
        mock_registry.get_jurisdiction_url.return_value = "https://mcp.example.com"
        mock_registry.get_relay_url.return_value = "https://relay.example.com"

        with patch.dict("sys.modules", {
            "civicos": MagicMock(CivicOS=MagicMock(return_value=mock_civic)),
            "civicos.diagnostics": MagicMock(DataStatus=mock_data_status),
            "civicos.registry": mock_registry,
        }):
            resp = unauthed_client.get("/api/tools/data-provenance")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["overall_coverage_percent"] is None
        assert body["data"]["corpora"][0]["coverage_percent"] is None
        assert body["data"]["corpora"][0]["last_indexed"] is None
        assert body["data"]["freshness"] == {}


