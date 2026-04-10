"""
Tests for admin router: cache logic, API key validation, cost estimation,
trigger routing, key management, and usage dashboard.

Tests real behavior by mocking I/O (HTTP requests, env vars, DB imports)
while exercising all logic in the subject module.
"""

import time
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from civicos_services.servers.routers.admin import (
    _get_cached_validation,
    _set_cached_validation,
    _get_cached_usage,
    _set_cached_usage,
    _validate_assemblyai_key,
    _validate_legiscan_key,
    _fetch_assemblyai_usage,
    _api_key_cache,
    _usage_cache,
    _API_KEY_CACHE_TTL_SECONDS,
    _USAGE_CACHE_TTL_SECONDS,
    ASSEMBLYAI_COST_PER_MINUTE,
    router,
    provider_stats,
)


# === Fixtures ===

@pytest.fixture(autouse=True)
def clear_caches():
    """Clear module-level caches before each test."""
    _api_key_cache.clear()
    _usage_cache.clear()
    provider_stats.clear()
    yield
    _api_key_cache.clear()
    _usage_cache.clear()
    provider_stats.clear()


@pytest.fixture
def app():
    """Create a FastAPI app with the admin router and auth bypassed."""
    app = FastAPI()
    app.include_router(router, prefix="/admin")
    return app


@pytest.fixture
def client(app):
    """Create a test client with auth dependency overridden."""
    from civicos_services.servers.routers.dependencies import verify_auth, AuthContext

    async def mock_auth():
        return AuthContext(key_id="test-key", source="env", tier="admin")

    app.dependency_overrides[verify_auth] = mock_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# === Validation Cache Tests ===

class TestValidationCache:
    def test_returns_none_for_empty_cache(self):
        result = _get_cached_validation("nonexistent")
        assert result is None

    def test_stores_and_retrieves_result(self):
        data = {"is_valid": True, "response_time_ms": 42}
        _set_cached_validation("test_service", data)
        cached = _get_cached_validation("test_service")
        assert cached["is_valid"] is True
        assert cached["response_time_ms"] == 42

    def test_adds_cached_at_timestamp(self):
        before = time.time()
        _set_cached_validation("svc", {"is_valid": False})
        after = time.time()
        cached = _get_cached_validation("svc")
        assert before <= cached["cached_at"] <= after

    def test_expired_entry_returns_none(self):
        _set_cached_validation("old", {"is_valid": True})
        # Backdate the cached_at to make it expired
        _api_key_cache["old"]["cached_at"] = time.time() - _API_KEY_CACHE_TTL_SECONDS - 1
        assert _get_cached_validation("old") is None

    def test_entry_just_within_ttl_returns_data(self):
        _set_cached_validation("fresh", {"is_valid": True})
        # Set cached_at to just within TTL
        _api_key_cache["fresh"]["cached_at"] = time.time() - _API_KEY_CACHE_TTL_SECONDS + 10
        cached = _get_cached_validation("fresh")
        assert cached["is_valid"] is True


# === Usage Cache Tests ===

class TestUsageCache:
    def test_returns_none_for_empty_cache(self):
        assert _get_cached_usage("missing_key") is None

    def test_stores_and_retrieves_usage(self):
        data = {"transcript_count": 5, "total_minutes": 30.5}
        _set_cached_usage("aai_usage", data)
        cached = _get_cached_usage("aai_usage")
        assert cached["transcript_count"] == 5
        assert cached["total_minutes"] == 30.5

    def test_expired_usage_returns_none(self):
        _set_cached_usage("old_usage", {"transcript_count": 1})
        _usage_cache["old_usage"]["cached_at"] = time.time() - _USAGE_CACHE_TTL_SECONDS - 1
        assert _get_cached_usage("old_usage") is None

    def test_usage_cache_ttl_is_one_hour(self):
        assert _USAGE_CACHE_TTL_SECONDS == 3600


# === AssemblyAI Key Validation Tests ===

class TestValidateAssemblyAIKey:
    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_valid_key_returns_true(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        result = _validate_assemblyai_key("valid-key")
        assert result["is_valid"] is True
        assert result["validation_method"] == "api_call"
        assert isinstance(result["response_time_ms"], int)

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_invalid_key_returns_false_with_401(self, mock_get):
        mock_get.return_value = MagicMock(status_code=401)
        result = _validate_assemblyai_key("bad-key")
        assert result["is_valid"] is False
        assert "401 Unauthorized" in result["error_message"]

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_unexpected_status_returns_false(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500)
        result = _validate_assemblyai_key("some-key")
        assert result["is_valid"] is False
        assert "500" in result["error_message"]

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_timeout_returns_none_validity(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.Timeout("timed out")
        result = _validate_assemblyai_key("key")
        assert result["is_valid"] is None
        assert "timed out" in result["error_message"].lower()

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_connection_error_returns_none_validity(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.ConnectionError("refused")
        result = _validate_assemblyai_key("key")
        assert result["is_valid"] is None
        assert "Connection error" in result["error_message"]

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_calls_correct_endpoint(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        _validate_assemblyai_key("my-key")
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://api.assemblyai.com/v2/transcript"
        assert call_args[1]["headers"]["Authorization"] == "my-key"
        assert call_args[1]["params"]["limit"] == 1


# === LegiScan Key Validation Tests ===

class TestValidateLegiscanKey:
    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_valid_key_returns_true(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"status": "OK"})
        )
        result = _validate_legiscan_key("good-key")
        assert result["is_valid"] is True
        assert result["validation_method"] == "api_call"

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_error_status_in_response(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "status": "ERROR",
                "alert": {"message": "Invalid key"}
            })
        )
        result = _validate_legiscan_key("bad-key")
        assert result["is_valid"] is False
        assert "Invalid key" in result["error_message"]

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_non_200_status_returns_false(self, mock_get):
        mock_get.return_value = MagicMock(status_code=403)
        result = _validate_legiscan_key("key")
        assert result["is_valid"] is False
        assert "403" in result["error_message"]

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_timeout_returns_none_validity(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.Timeout()
        result = _validate_legiscan_key("key")
        assert result["is_valid"] is None
        assert "timed out" in result["error_message"].lower()

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_calls_correct_endpoint(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={"status": "OK"})
        )
        _validate_legiscan_key("ls-key")
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://api.legiscan.com/"
        assert call_args[1]["params"]["key"] == "ls-key"
        assert call_args[1]["params"]["op"] == "getStateList"


# === AssemblyAI Usage Fetching Tests ===

class TestFetchAssemblyAIUsage:
    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_calculates_minutes_and_cost_for_completed_transcripts(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "transcripts": [
                    {
                        "id": "t1",
                        "status": "completed",
                        "audio_duration": 600_000,  # 10 minutes in ms
                        "created": "2026-04-05T10:00:00.000000Z",
                    },
                    {
                        "id": "t2",
                        "status": "completed",
                        "audio_duration": 300_000,  # 5 minutes in ms
                        "created": "2026-04-04T10:00:00.000000Z",
                    },
                ],
                "page_details": {},
            })
        )
        result = _fetch_assemblyai_usage("key", "last_30_days")
        assert result["transcript_count"] == 2
        assert result["total_minutes"] == 15.0
        assert result["estimated_cost_usd"] == round(15.0 * ASSEMBLYAI_COST_PER_MINUTE, 2)

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_excludes_non_completed_transcripts_from_count(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "transcripts": [
                    {
                        "id": "t1",
                        "status": "completed",
                        "audio_duration": 60_000,  # 1 minute
                        "created": "2026-04-05T10:00:00.000000Z",
                    },
                    {
                        "id": "t2",
                        "status": "error",
                        "audio_duration": 120_000,
                        "created": "2026-04-04T10:00:00.000000Z",
                    },
                ],
                "page_details": {},
            })
        )
        result = _fetch_assemblyai_usage("key", "last_30_days")
        # Only the completed transcript is counted
        assert result["transcript_count"] == 1
        # Only completed transcript's duration counted
        assert result["total_minutes"] == 1.0

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_api_error_returns_error_dict(self, mock_get):
        mock_get.return_value = MagicMock(status_code=500)
        result = _fetch_assemblyai_usage("key", "current_month")
        assert "error" in result
        assert "500" in result["error"]

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_timeout_returns_error(self, mock_get):
        import requests as req
        mock_get.side_effect = req.exceptions.Timeout()
        result = _fetch_assemblyai_usage("key", "current_month")
        assert "error" in result
        assert "timed out" in result["error"].lower()

    @patch("civicos_services.servers.routers.admin.requests.get")
    def test_empty_transcript_list_returns_zeros(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                "transcripts": [],
                "page_details": {},
            })
        )
        result = _fetch_assemblyai_usage("key", "current_month")
        assert result["transcript_count"] == 0
        assert result["total_minutes"] == 0.0
        assert result["estimated_cost_usd"] == 0.0


# === Cost Estimation Endpoint Tests ===

class TestCostEstimateEndpoint:
    @patch("civicos_services.servers.routers.admin.get_provider_stats", create=True)
    def test_cost_estimate_day_period(self, mock_stats, client):
        # Patch the import inside the endpoint
        with patch.dict("sys.modules", {
            "civicos_services.core.llm_provider": MagicMock(
                get_provider_stats=MagicMock(return_value={
                    "openai": {"count": 10, "total_tokens": 1_000_000}
                })
            )
        }):
            resp = client.get("/admin/cost-estimate?period=day")
            assert resp.status_code == 200
            data = resp.json()
            assert data["period"] == "day"
            # openai: 1M tokens * (0.7 * 0.50 + 0.3 * 1.50) / 1M = 0.35 + 0.45 = 0.80
            assert data["estimated_cost"] == 0.8
            assert data["breakdown"]["openai"] == 0.8

    @patch.dict("sys.modules", {
        "civicos_services.core.llm_provider": MagicMock(
            get_provider_stats=MagicMock(return_value={
                "openai": {"count": 10, "total_tokens": 1_000_000}
            })
        )
    })
    def test_cost_estimate_week_multiplier(self, client):
        resp = client.get("/admin/cost-estimate?period=week")
        data = resp.json()
        # 0.80 * 7 = 5.60
        assert data["estimated_cost"] == 5.6
        assert data["period"] == "week"

    @patch.dict("sys.modules", {
        "civicos_services.core.llm_provider": MagicMock(
            get_provider_stats=MagicMock(return_value={
                "openai": {"count": 10, "total_tokens": 1_000_000}
            })
        )
    })
    def test_cost_estimate_month_multiplier(self, client):
        resp = client.get("/admin/cost-estimate?period=month")
        data = resp.json()
        # 0.80 * 30 = 24.0
        assert data["estimated_cost"] == 24.0

    @patch.dict("sys.modules", {
        "civicos_services.core.llm_provider": MagicMock(
            get_provider_stats=MagicMock(return_value={})
        )
    })
    def test_cost_estimate_no_providers_returns_zero(self, client):
        resp = client.get("/admin/cost-estimate?period=day")
        data = resp.json()
        assert data["estimated_cost"] == 0.0
        assert data["breakdown"] == {}

    @patch.dict("sys.modules", {
        "civicos_services.core.llm_provider": MagicMock(
            get_provider_stats=MagicMock(return_value={
                "anthropic": {"count": 5, "total_tokens": 2_000_000}
            })
        )
    })
    def test_cost_estimate_anthropic_rates(self, client):
        resp = client.get("/admin/cost-estimate?period=day")
        data = resp.json()
        # anthropic: 2M tokens * (0.7 * 3.00 + 0.3 * 15.00) / 1M = 2 * (2.1 + 4.5) = 13.2
        assert data["estimated_cost"] == 13.2

    @patch.dict("sys.modules", {
        "civicos_services.core.llm_provider": MagicMock(
            get_provider_stats=MagicMock(return_value={
                "unknown_provider": {"count": 1, "total_tokens": 1_000_000}
            })
        )
    })
    def test_cost_estimate_unknown_provider_uses_defaults(self, client):
        resp = client.get("/admin/cost-estimate?period=day")
        data = resp.json()
        # Default: 1M * (0.7 * 1.0 + 0.3 * 2.0) / 1M = 0.7 + 0.6 = 1.3
        assert data["estimated_cost"] == 1.3


# === Provider Stats Endpoint Tests ===

class TestProviderStatsEndpoint:
    @patch.dict("sys.modules", {
        "civicos_services.core.llm_provider": MagicMock(
            get_provider_stats=MagicMock(return_value={
                "openai": {"count": 100, "total_tokens": 500_000},
                "anthropic": {"count": 50, "total_tokens": 300_000},
            })
        )
    })
    def test_aggregates_totals_across_providers(self, client):
        resp = client.get("/admin/provider-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["totals"]["requests"] == 150
        assert data["totals"]["tokens"] == 800_000

    @patch.dict("sys.modules", {
        "civicos_services.core.llm_provider": MagicMock(
            get_provider_stats=MagicMock(return_value={})
        )
    })
    def test_empty_providers_returns_zero_totals(self, client):
        resp = client.get("/admin/provider-stats")
        data = resp.json()
        assert data["totals"]["requests"] == 0
        assert data["totals"]["tokens"] == 0


# === Admin Trigger Endpoint Tests ===

class TestAdminTriggerEndpoint:
    def test_unknown_action_returns_400(self, client):
        resp = client.post("/admin/trigger", json={"action": "delete_everything"})
        assert resp.status_code == 400
        assert "Unknown action" in resp.json()["detail"]

    @patch.dict("sys.modules", {
        "civicos_services.monitoring.automated_civic_refresh": MagicMock(
            trigger_refresh=MagicMock(return_value={"status": "started"})
        )
    })
    def test_refresh_data_triggers_refresh(self, client):
        resp = client.post("/admin/trigger", json={
            "action": "refresh_data",
            "params": {"jurisdiction_id": "city-san-rafael"}
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == "refresh_data"

    @patch.dict("sys.modules", {
        "civicos_services.processing.vector_indexer": MagicMock(
            trigger_reindex=MagicMock(return_value={"status": "started"})
        )
    })
    def test_reindex_vectors_triggers_reindex(self, client):
        resp = client.post("/admin/trigger", json={
            "action": "reindex_vectors",
            "params": {"corpus_type": "decisions"}
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == "reindex_vectors"

    @patch.dict("sys.modules", {
        "civicos_services.legislative.legislative_context_cache": MagicMock(
            legislative_cache=MagicMock()
        )
    })
    def test_clear_cache_returns_success(self, client):
        resp = client.post("/admin/trigger", json={"action": "clear_cache"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["action"] == "clear_cache"
        assert "cleared" in data["message"].lower()

    def test_trigger_with_no_params_defaults_to_empty(self, client):
        # Should still fail because "invalid_action" is unknown, but params should be {}
        resp = client.post("/admin/trigger", json={"action": "unknown_thing"})
        assert resp.status_code == 400


# === Data Browser Endpoint Tests ===

class TestDataBrowserEndpoint:
    @patch("civicos_services.servers.routers.admin.load_dotenv", create=True)
    def test_invalid_data_type_returns_400(self, mock_dotenv, client):
        with patch.dict("sys.modules", {
            "civicos": MagicMock(CivicOS=MagicMock(return_value=MagicMock())),
            "dotenv": MagicMock(load_dotenv=MagicMock()),
        }):
            resp = client.get("/admin/data/unknown_type")
            assert resp.status_code == 400
            assert "Unknown data type" in resp.json()["detail"]
            assert "meetings" in resp.json()["detail"]  # Lists supported types

    @patch.dict("sys.modules", {
        "civicos": MagicMock(
            CivicOS=MagicMock(return_value=MagicMock(
                storage=MagicMock(
                    get_meetings=MagicMock(return_value=[
                        {"id": "m1", "title": "Council Meeting"}
                    ])
                )
            ))
        ),
        "dotenv": MagicMock(load_dotenv=MagicMock()),
    })
    def test_meetings_data_type_returns_items(self, client):
        resp = client.get("/admin/data/meetings?limit=10&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["type"] == "meetings"
        assert data["count"] == 1
        assert data["items"][0]["id"] == "m1"
        assert data["offset"] == 0
        assert data["limit"] == 10


# === API Key Management Endpoint Tests ===

class TestCreateAPIKey:
    def test_invalid_tier_returns_400(self, client):
        resp = client.post("/admin/keys", json={
            "name": "Test",
            "email": "test@example.com",
            "tier": "superadmin",
        })
        assert resp.status_code == 400
        assert "Invalid tier" in resp.json()["detail"]
        assert "superadmin" in resp.json()["detail"]

    @patch.dict("sys.modules", {
        "civicos_services.core.api_keys": MagicMock(
            get_api_key_store=MagicMock(return_value=MagicMock(
                available=False
            ))
        )
    })
    def test_unavailable_store_returns_503(self, client):
        resp = client.post("/admin/keys", json={
            "name": "Test",
            "email": "test@example.com",
            "tier": "free",
        })
        assert resp.status_code == 503
        assert "PLATFORM_DATABASE_URL" in resp.json()["detail"]

    @patch.dict("sys.modules", {
        "civicos_services.core.api_keys": MagicMock(
            get_api_key_store=MagicMock(return_value=MagicMock(
                available=True,
                create_key=MagicMock(return_value=("kid-123", "cvo_raw_key_abc"))
            ))
        )
    })
    def test_successful_key_creation(self, client):
        resp = client.post("/admin/keys", json={
            "name": "Journalist App",
            "email": "press@news.com",
            "tier": "journalist",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["key_id"] == "kid-123"
        assert data["raw_key"] == "cvo_raw_key_abc"
        assert data["tier"] == "journalist"

    @patch.dict("sys.modules", {
        "civicos_services.core.api_keys": MagicMock(
            get_api_key_store=MagicMock(return_value=MagicMock(
                available=True,
                create_key=MagicMock(return_value=None)
            ))
        )
    })
    def test_failed_key_creation_returns_500(self, client):
        resp = client.post("/admin/keys", json={
            "name": "Test",
            "email": "test@example.com",
            "tier": "free",
        })
        assert resp.status_code == 500
        assert "Failed to create" in resp.json()["detail"]

    @patch.dict("sys.modules", {
        "civicos_services.core.api_keys": MagicMock(
            get_api_key_store=MagicMock(return_value=MagicMock(
                available=True,
                create_key=MagicMock(return_value=("kid-1", "cvo_key_1"))
            ))
        )
    })
    def test_all_valid_tiers_accepted_by_endpoint(self, client):
        """Verify the actual endpoint accepts all expected tiers."""
        for tier in ("free", "journalist", "organization", "city", "api"):
            resp = client.post("/admin/keys", json={
                "name": "Test",
                "email": "t@example.com",
                "tier": tier,
            })
            assert resp.status_code == 200, f"Tier '{tier}' rejected with {resp.status_code}"


class TestListAPIKeys:
    @patch.dict("sys.modules", {
        "civicos_services.core.api_keys": MagicMock(
            get_api_key_store=MagicMock(return_value=MagicMock(
                available=False
            ))
        )
    })
    def test_unavailable_store_returns_empty_list(self, client):
        resp = client.get("/admin/keys")
        assert resp.status_code == 200
        data = resp.json()
        assert data["keys"] == []
        assert "not configured" in data["message"].lower()

    @patch.dict("sys.modules", {
        "civicos_services.core.api_keys": MagicMock(
            get_api_key_store=MagicMock(return_value=MagicMock(
                available=True,
                list_keys=MagicMock(return_value=[
                    {"key_id": "k1", "name": "App A", "tier": "free"},
                    {"key_id": "k2", "name": "App B", "tier": "journalist"},
                ])
            ))
        )
    })
    def test_lists_keys_with_count(self, client):
        resp = client.get("/admin/keys")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert data["keys"][0]["key_id"] == "k1"
        assert data["keys"][1]["tier"] == "journalist"


class TestRevokeAPIKey:
    @patch.dict("sys.modules", {
        "civicos_services.core.api_keys": MagicMock(
            get_api_key_store=MagicMock(return_value=MagicMock(
                available=False
            ))
        )
    })
    def test_unavailable_store_returns_503(self, client):
        resp = client.delete("/admin/keys/some-id")
        assert resp.status_code == 503

    @patch.dict("sys.modules", {
        "civicos_services.core.api_keys": MagicMock(
            get_api_key_store=MagicMock(return_value=MagicMock(
                available=True,
                revoke_key=MagicMock(return_value=False)
            ))
        )
    })
    def test_nonexistent_key_returns_404(self, client):
        resp = client.delete("/admin/keys/no-such-key")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @patch.dict("sys.modules", {
        "civicos_services.core.api_keys": MagicMock(
            get_api_key_store=MagicMock(return_value=MagicMock(
                available=True,
                revoke_key=MagicMock(return_value=True)
            ))
        )
    })
    def test_successful_revocation(self, client):
        resp = client.delete("/admin/keys/kid-123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "revoked"
        assert data["key_id"] == "kid-123"


# === Usage Dashboard Endpoint Tests ===

class TestUsageDashboard:
    @patch.dict("sys.modules", {
        "civicos_services.core.api_keys": MagicMock(
            get_api_key_store=MagicMock(return_value=MagicMock(
                available=False
            ))
        )
    })
    def test_unavailable_store_returns_empty(self, client):
        resp = client.get("/admin/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["usage"] == []

    @patch.dict("sys.modules", {
        "civicos_services.core.api_keys": MagicMock(
            get_api_key_store=MagicMock(return_value=MagicMock(
                available=True,
                get_all_usage_summary=MagicMock(return_value=[
                    {"key_id": "k1", "total_requests": 42}
                ])
            ))
        )
    })
    def test_all_usage_summary(self, client):
        resp = client.get("/admin/usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["usage"][0]["total_requests"] == 42

    def test_single_key_usage(self, client):
        class FakeStats:
            def __init__(self):
                self.key_id = "k1"
                self.total = 100
                self.by_endpoint = {"/search": 80}

        mock_store = MagicMock()
        mock_store.available = True
        mock_store.get_usage_stats = MagicMock(return_value=FakeStats())

        with patch.dict("sys.modules", {
            "civicos_services.core.api_keys": MagicMock(
                get_api_key_store=MagicMock(return_value=mock_store)
            )
        }):
            resp = client.get("/admin/usage?key_id=k1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["key_usage"]["total"] == 100
        assert data["key_usage"]["by_endpoint"]["/search"] == 80


# === API Key Status Endpoint Tests ===

class TestAPIKeyStatusEndpoint:
    @patch.dict("os.environ", {}, clear=True)
    @patch("civicos_services.servers.routers.admin.load_dotenv", create=True)
    def test_no_keys_configured_returns_unconfigured(self, mock_dotenv, client):
        # Ensure the env vars don't exist
        with patch("civicos_services.servers.routers.admin.os.getenv", return_value=None):
            resp = client.get("/admin/api-key-status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["overall_status"] == "unconfigured"
            assert data["keys"]["assemblyai"]["is_configured"] is False
            assert data["keys"]["legiscan"]["is_configured"] is False

    @patch("civicos_services.servers.routers.admin.os.getenv")
    @patch("civicos_services.servers.routers.admin._validate_assemblyai_key")
    @patch("civicos_services.servers.routers.admin._validate_legiscan_key")
    def test_all_valid_returns_healthy(self, mock_legiscan, mock_aai, mock_getenv, client):
        mock_getenv.side_effect = lambda k: {
            "ASSEMBLYAI_API_KEY": "aai-key",
            "LEGISCAN_API_KEY": "ls-key",
        }.get(k)
        mock_aai.return_value = {"is_valid": True, "response_time_ms": 50, "validation_method": "api_call"}
        mock_legiscan.return_value = {"is_valid": True, "response_time_ms": 60, "validation_method": "api_call"}

        with patch("civicos_services.servers.routers.admin.load_dotenv", create=True):
            resp = client.get("/admin/api-key-status?force_refresh=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_status"] == "healthy"
        assert data["keys"]["assemblyai"]["is_valid"] is True
        assert data["keys"]["legiscan"]["is_valid"] is True

    @patch("civicos_services.servers.routers.admin.os.getenv")
    @patch("civicos_services.servers.routers.admin._validate_assemblyai_key")
    @patch("civicos_services.servers.routers.admin._validate_legiscan_key")
    def test_one_invalid_returns_warning(self, mock_legiscan, mock_aai, mock_getenv, client):
        mock_getenv.side_effect = lambda k: {
            "ASSEMBLYAI_API_KEY": "aai-key",
            "LEGISCAN_API_KEY": "ls-key",
        }.get(k)
        mock_aai.return_value = {"is_valid": True, "response_time_ms": 50, "validation_method": "api_call"}
        mock_legiscan.return_value = {"is_valid": False, "error_message": "bad key", "response_time_ms": 60, "validation_method": "api_call"}

        with patch("civicos_services.servers.routers.admin.load_dotenv", create=True):
            resp = client.get("/admin/api-key-status?force_refresh=true")
        data = resp.json()
        assert data["overall_status"] == "warning"

    @patch("civicos_services.servers.routers.admin.os.getenv")
    @patch("civicos_services.servers.routers.admin._validate_assemblyai_key")
    @patch("civicos_services.servers.routers.admin._validate_legiscan_key")
    def test_all_invalid_returns_degraded(self, mock_legiscan, mock_aai, mock_getenv, client):
        mock_getenv.side_effect = lambda k: {
            "ASSEMBLYAI_API_KEY": "aai-key",
            "LEGISCAN_API_KEY": "ls-key",
        }.get(k)
        mock_aai.return_value = {"is_valid": False, "error_message": "bad", "response_time_ms": 50, "validation_method": "api_call"}
        mock_legiscan.return_value = {"is_valid": False, "error_message": "bad", "response_time_ms": 60, "validation_method": "api_call"}

        with patch("civicos_services.servers.routers.admin.load_dotenv", create=True):
            resp = client.get("/admin/api-key-status?force_refresh=true")
        data = resp.json()
        assert data["overall_status"] == "degraded"


# === AssemblyAI Usage Endpoint Tests ===

class TestAssemblyAIUsageEndpoint:
    @patch("civicos_services.servers.routers.admin.os.getenv", return_value=None)
    def test_no_api_key_returns_not_configured(self, mock_getenv, client):
        with patch("civicos_services.servers.routers.admin.load_dotenv", create=True):
            resp = client.get("/admin/assemblyai-usage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_configured"] is False
        assert "not set" in data["error_message"].lower()

    @patch("civicos_services.servers.routers.admin.os.getenv", return_value="aai-key")
    @patch("civicos_services.servers.routers.admin._fetch_assemblyai_usage")
    def test_successful_fetch_returns_usage(self, mock_fetch, mock_getenv, client):
        mock_fetch.return_value = {
            "period": "current_month",
            "period_start": "2026-04-01",
            "period_end": "2026-04-09",
            "transcript_count": 10,
            "total_minutes": 120.5,
            "estimated_cost_usd": 2.41,
        }
        with patch("civicos_services.servers.routers.admin.load_dotenv", create=True):
            resp = client.get("/admin/assemblyai-usage?force_refresh=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_configured"] is True
        assert data["cached"] is False
        assert data["usage"]["transcript_count"] == 10
        assert data["usage"]["total_minutes"] == 120.5
        assert data["usage"]["estimated_cost_usd"] == 2.41

    @patch("civicos_services.servers.routers.admin.os.getenv", return_value="aai-key")
    @patch("civicos_services.servers.routers.admin._fetch_assemblyai_usage")
    def test_fetch_error_returns_error_message(self, mock_fetch, mock_getenv, client):
        mock_fetch.return_value = {"error": "API error: 500", "period": "current_month"}
        with patch("civicos_services.servers.routers.admin.load_dotenv", create=True):
            resp = client.get("/admin/assemblyai-usage?force_refresh=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_configured"] is True
        assert data["usage"] is None
        assert "500" in data["error_message"]

    @patch("civicos_services.servers.routers.admin.os.getenv", return_value="aai-key")
    @patch("civicos_services.servers.routers.admin._fetch_assemblyai_usage")
    def test_invalid_period_defaults_to_current_month(self, mock_fetch, mock_getenv, client):
        mock_fetch.return_value = {
            "period": "current_month",
            "period_start": "2026-04-01",
            "period_end": "2026-04-09",
            "transcript_count": 0,
            "total_minutes": 0.0,
            "estimated_cost_usd": 0.0,
        }
        with patch("civicos_services.servers.routers.admin.load_dotenv", create=True):
            resp = client.get("/admin/assemblyai-usage?period=invalid_period&force_refresh=true")
        assert resp.status_code == 200
        # The endpoint normalizes invalid periods to current_month
        mock_fetch.assert_called_once_with("aai-key", "current_month")

    @patch("civicos_services.servers.routers.admin.os.getenv", return_value="aai-key")
    @patch("civicos_services.servers.routers.admin._fetch_assemblyai_usage")
    def test_cached_response_marked_as_cached(self, mock_fetch, mock_getenv, client):
        # First call: populate cache
        mock_fetch.return_value = {
            "period": "current_month",
            "period_start": "2026-04-01",
            "period_end": "2026-04-09",
            "transcript_count": 5,
            "total_minutes": 50.0,
            "estimated_cost_usd": 1.0,
        }
        with patch("civicos_services.servers.routers.admin.load_dotenv", create=True):
            resp1 = client.get("/admin/assemblyai-usage?force_refresh=true")
        assert resp1.json()["cached"] is False

        # Second call: should hit cache
        with patch("civicos_services.servers.routers.admin.load_dotenv", create=True):
            resp2 = client.get("/admin/assemblyai-usage")
        assert resp2.json()["cached"] is True
        assert resp2.json()["usage"]["transcript_count"] == 5


# === Operations Endpoint Tests ===

class TestOperationsEndpoint:
    def test_operations_fallback_when_tracker_unavailable(self, client):
        # When OperationTracker isn't importable, should return empty list
        with patch.dict("sys.modules", {
            "civicos_services.monitoring.operation_tracker": None,
        }):
            resp = client.get("/admin/operations")
            assert resp.status_code == 200
            data = resp.json()
            assert data["operations"] == []
            assert data["count"] == 0

    def test_operation_not_found_returns_404(self, client):
        mock_tracker = MagicMock()
        mock_tracker_cls = MagicMock(return_value=mock_tracker)
        mock_tracker.get_operation.return_value = None

        with patch.dict("sys.modules", {
            "civicos_services.monitoring.operation_tracker": MagicMock(
                OperationTracker=mock_tracker_cls
            ),
        }):
            resp = client.get("/admin/operations/nonexistent-id")
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"].lower()


# === Constants Tests ===

class TestConstants:
    def test_assemblyai_cost_per_minute_is_two_cents(self):
        assert ASSEMBLYAI_COST_PER_MINUTE == 0.02

    def test_api_key_cache_ttl_is_five_minutes(self):
        assert _API_KEY_CACHE_TTL_SECONDS == 300
