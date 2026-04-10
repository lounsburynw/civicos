"""
Tests for api_keys.py — tier resolution, tool access control, key hashing,
key generation, and ApiKeyStore database operations.

Pure functions (resolve_tier, get_allowed_tools, min_tier_for_tool, _hash_key,
_generate_key) tested with real inputs/outputs. ApiKeyStore tested with mocked
psycopg2 connections (external I/O).

To run:
    pytest packages/civicos-services/tests/test_api_keys.py -q --override-ini="addopts="
"""

import hashlib
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

import pytest

from civicos_services.core.api_keys import (
    TIER_CONFIG,
    TIER_ORDER,
    TIER_TOOLS,
    ApiKeyInfo,
    ApiKeyStore,
    UsageStats,
    _generate_key,
    _hash_key,
    get_allowed_tools,
    get_api_key_store,
    min_tier_for_tool,
    resolve_tier,
)


# ---------------------------------------------------------------------------
# resolve_tier
# ---------------------------------------------------------------------------

class TestResolveTier:
    def test_resolves_journalist_to_builder(self):
        assert resolve_tier("journalist") == "builder"

    def test_resolves_api_to_admin(self):
        assert resolve_tier("api") == "admin"

    def test_free_stays_free(self):
        assert resolve_tier("free") == "free"

    def test_admin_stays_admin(self):
        assert resolve_tier("admin") == "admin"

    def test_open_stays_open(self):
        assert resolve_tier("open") == "open"

    def test_unknown_tier_returns_itself(self):
        assert resolve_tier("nonexistent") == "nonexistent"

    def test_empty_string_returns_itself(self):
        assert resolve_tier("") == ""


# ---------------------------------------------------------------------------
# get_allowed_tools
# ---------------------------------------------------------------------------

class TestGetAllowedTools:
    def test_open_tier_has_city_pulse(self):
        tools = get_allowed_tools("open")
        assert "city_pulse" in tools
        assert "get_started" in tools

    def test_open_tier_excludes_free_tools(self):
        tools = get_allowed_tools("open")
        assert "search_meeting_history" not in tools
        assert "search_legislation" not in tools

    def test_free_tier_includes_open_tools(self):
        tools = get_allowed_tools("free")
        assert "city_pulse" in tools
        assert "search_meeting_history" in tools

    def test_builder_tier_includes_free_and_open(self):
        tools = get_allowed_tools("builder")
        assert "city_pulse" in tools  # open
        assert "search_meeting_history" in tools  # free
        assert "search_agenda_packets" in tools  # builder

    def test_admin_tier_includes_all_tiers(self):
        tools = get_allowed_tools("admin")
        assert "city_pulse" in tools  # open
        assert "search_meeting_history" in tools  # free
        assert "search_agenda_packets" in tools  # builder
        assert "admin_data_status" in tools  # admin
        assert "manage_api_keys" in tools  # admin

    def test_legacy_journalist_resolves_to_builder_tools(self):
        journalist_tools = get_allowed_tools("journalist")
        builder_tools = get_allowed_tools("builder")
        assert journalist_tools == builder_tools

    def test_legacy_api_resolves_to_admin_tools(self):
        api_tools = get_allowed_tools("api")
        admin_tools = get_allowed_tools("admin")
        assert api_tools == admin_tools

    def test_unknown_tier_falls_back_to_open(self):
        tools = get_allowed_tools("nonexistent_tier")
        open_tools = get_allowed_tools("open")
        assert tools == open_tools

    def test_cumulative_tool_count_increases_with_tier(self):
        counts = [len(get_allowed_tools(t)) for t in TIER_ORDER]
        # Each tier should have >= tools as the previous
        for i in range(1, len(counts)):
            assert counts[i] >= counts[i - 1], (
                f"{TIER_ORDER[i]} ({counts[i]}) has fewer tools than "
                f"{TIER_ORDER[i-1]} ({counts[i-1]})"
            )

    def test_organization_inherits_builder_tools(self):
        org_tools = get_allowed_tools("organization")
        builder_tools = get_allowed_tools("builder")
        assert org_tools == builder_tools

    def test_city_inherits_organization_tools(self):
        city_tools = get_allowed_tools("city")
        org_tools = get_allowed_tools("organization")
        assert city_tools == org_tools


# ---------------------------------------------------------------------------
# min_tier_for_tool
# ---------------------------------------------------------------------------

class TestMinTierForTool:
    def test_city_pulse_requires_open(self):
        assert min_tier_for_tool("city_pulse") == "open"

    def test_search_meeting_history_requires_free(self):
        assert min_tier_for_tool("search_meeting_history") == "free"

    def test_search_agenda_packets_requires_builder(self):
        assert min_tier_for_tool("search_agenda_packets") == "builder"

    def test_admin_data_status_requires_admin(self):
        assert min_tier_for_tool("admin_data_status") == "admin"

    def test_unknown_tool_requires_admin(self):
        assert min_tier_for_tool("totally_unknown_tool") == "admin"

    def test_get_started_requires_open(self):
        assert min_tier_for_tool("get_started") == "open"

    def test_compose_public_comment_requires_builder(self):
        assert min_tier_for_tool("compose_public_comment") == "builder"


# ---------------------------------------------------------------------------
# _hash_key
# ---------------------------------------------------------------------------

class TestHashKey:
    def test_sha256_of_known_input(self):
        result = _hash_key("cvk_live_abc123")
        expected = hashlib.sha256(b"cvk_live_abc123").hexdigest()
        assert result == expected

    def test_different_inputs_produce_different_hashes(self):
        h1 = _hash_key("key_a")
        h2 = _hash_key("key_b")
        assert h1 != h2

    def test_same_input_produces_same_hash(self):
        h1 = _hash_key("same_key")
        h2 = _hash_key("same_key")
        assert h1 == h2

    def test_hash_is_64_hex_chars(self):
        result = _hash_key("any_key")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


# ---------------------------------------------------------------------------
# _generate_key
# ---------------------------------------------------------------------------

class TestGenerateKey:
    def test_returns_key_id_and_raw_key(self):
        key_id, raw_key = _generate_key()
        assert key_id.startswith("cvk_")
        assert raw_key.startswith("cvk_live_")

    def test_raw_key_has_correct_length(self):
        _, raw_key = _generate_key()
        # "cvk_live_" (9 chars) + 64 hex chars = 73
        assert len(raw_key) == 73

    def test_key_id_has_correct_length(self):
        key_id, _ = _generate_key()
        # "cvk_" (4 chars) + 16 hex chars = 20
        assert len(key_id) == 20

    def test_successive_keys_are_unique(self):
        id1, raw1 = _generate_key()
        id2, raw2 = _generate_key()
        assert id1 != id2
        assert raw1 != raw2


# ---------------------------------------------------------------------------
# ApiKeyInfo dataclass
# ---------------------------------------------------------------------------

class TestApiKeyInfo:
    def test_str_returns_key_id(self):
        info = ApiKeyInfo(
            key_id="cvk_abc123",
            name="Test",
            email="test@example.com",
            tier="free",
            status="active",
            rate_limit_per_minute=60,
        )
        assert str(info) == "cvk_abc123"

    def test_default_jurisdictions_empty_list(self):
        info = ApiKeyInfo(
            key_id="k1", name="n", email="e",
            tier="free", status="active", rate_limit_per_minute=60,
        )
        assert info.jurisdictions == []

    def test_default_metadata_empty_dict(self):
        info = ApiKeyInfo(
            key_id="k1", name="n", email="e",
            tier="free", status="active", rate_limit_per_minute=60,
        )
        assert info.metadata == {}

    def test_stripe_customer_id_defaults_none(self):
        info = ApiKeyInfo(
            key_id="k1", name="n", email="e",
            tier="free", status="active", rate_limit_per_minute=60,
        )
        assert info.stripe_customer_id is None

    def test_fields_set_correctly(self):
        info = ApiKeyInfo(
            key_id="cvk_test",
            name="My App",
            email="dev@example.com",
            tier="builder",
            status="active",
            rate_limit_per_minute=300,
            jurisdictions=["city-san-rafael"],
            stripe_customer_id="cus_123",
            metadata={"org": "test"},
        )
        assert info.key_id == "cvk_test"
        assert info.name == "My App"
        assert info.email == "dev@example.com"
        assert info.tier == "builder"
        assert info.status == "active"
        assert info.rate_limit_per_minute == 300
        assert info.jurisdictions == ["city-san-rafael"]
        assert info.stripe_customer_id == "cus_123"
        assert info.metadata == {"org": "test"}


# ---------------------------------------------------------------------------
# UsageStats dataclass
# ---------------------------------------------------------------------------

class TestUsageStats:
    def test_defaults(self):
        stats = UsageStats(
            key_id="k1",
            total_requests=100,
            period_start="2026-01-01",
            period_end="2026-01-31",
        )
        assert stats.by_endpoint == {}
        assert stats.error_count == 0
        assert stats.avg_response_ms is None

    def test_fields_set_correctly(self):
        stats = UsageStats(
            key_id="k1",
            total_requests=50,
            period_start="2026-01-01",
            period_end="2026-01-31",
            by_endpoint={"/search": 30, "/context": 20},
            error_count=5,
            avg_response_ms=120,
        )
        assert stats.total_requests == 50
        assert stats.by_endpoint["/search"] == 30
        assert stats.error_count == 5
        assert stats.avg_response_ms == 120


# ---------------------------------------------------------------------------
# TIER_CONFIG consistency
# ---------------------------------------------------------------------------

class TestTierConfig:
    def test_all_tier_order_entries_in_config(self):
        for tier in TIER_ORDER:
            assert tier in TIER_CONFIG, f"{tier} missing from TIER_CONFIG"

    def test_all_tier_order_entries_have_rate_limit(self):
        for tier in TIER_ORDER:
            assert "rate_limit_per_minute" in TIER_CONFIG[tier]
            assert TIER_CONFIG[tier]["rate_limit_per_minute"] > 0

    def test_legacy_aliases_point_to_valid_tiers(self):
        for tier, config in TIER_CONFIG.items():
            if "alias_of" in config:
                assert config["alias_of"] in TIER_ORDER, (
                    f"Legacy alias {tier} points to {config['alias_of']} "
                    f"which is not in TIER_ORDER"
                )

    def test_rate_limits_are_monotonically_non_decreasing(self):
        limits = [TIER_CONFIG[t]["rate_limit_per_minute"] for t in TIER_ORDER]
        for i in range(1, len(limits)):
            assert limits[i] >= limits[i - 1], (
                f"{TIER_ORDER[i]} rate limit ({limits[i]}) < "
                f"{TIER_ORDER[i-1]} ({limits[i-1]})"
            )


# ---------------------------------------------------------------------------
# ApiKeyStore — connection handling
# ---------------------------------------------------------------------------

class TestApiKeyStoreConnection:
    def test_init_with_explicit_url(self):
        store = ApiKeyStore(database_url="postgresql://test:test@localhost/db")
        assert store._database_url == "postgresql://test:test@localhost/db"

    @patch.dict("os.environ", {"PLATFORM_DATABASE_URL": "postgresql://platform"}, clear=False)
    def test_init_prefers_platform_database_url(self):
        store = ApiKeyStore()
        assert store._database_url == "postgresql://platform"

    @patch.dict("os.environ", {"DATABASE_URL": "postgresql://main"}, clear=False)
    def test_init_falls_back_to_database_url(self):
        # Remove PLATFORM_DATABASE_URL if present
        import os
        env = {k: v for k, v in os.environ.items() if k != "PLATFORM_DATABASE_URL"}
        with patch.dict("os.environ", env, clear=True):
            store = ApiKeyStore()
            assert store._database_url == "postgresql://main"

    def test_no_url_means_not_available(self):
        with patch.dict("os.environ", {}, clear=True):
            store = ApiKeyStore(database_url=None)
            store._database_url = None
            assert store.available is False

    def test_pool_stats_without_pool(self):
        store = ApiKeyStore(database_url=None)
        store._database_url = None
        stats = store.pool_stats()
        assert stats == {"available": False}

    @patch("civicos_services.core.api_keys.psycopg2.pool.SimpleConnectionPool")
    def test_get_pool_appends_sslmode_when_missing(self, mock_pool_cls):
        mock_pool_cls.return_value = MagicMock()
        store = ApiKeyStore(database_url="postgresql://host/db")
        store._get_pool()
        call_args = mock_pool_cls.call_args
        dsn = call_args[0][2]  # positional args: (minconn, maxconn, dsn)
        assert "sslmode=require" in dsn

    @patch("civicos_services.core.api_keys.psycopg2.pool.SimpleConnectionPool")
    def test_get_pool_preserves_existing_sslmode(self, mock_pool_cls):
        mock_pool_cls.return_value = MagicMock()
        store = ApiKeyStore(database_url="postgresql://host/db?sslmode=disable")
        store._get_pool()
        call_args = mock_pool_cls.call_args
        dsn = call_args[0][2]
        assert dsn == "postgresql://host/db?sslmode=disable"

    @patch("civicos_services.core.api_keys.psycopg2.pool.SimpleConnectionPool")
    def test_get_pool_uses_ampersand_when_query_params_exist(self, mock_pool_cls):
        mock_pool_cls.return_value = MagicMock()
        store = ApiKeyStore(database_url="postgresql://host/db?timeout=30")
        store._get_pool()
        call_args = mock_pool_cls.call_args
        dsn = call_args[0][2]
        assert "timeout=30&sslmode=require" in dsn

    @patch("civicos_services.core.api_keys.psycopg2.pool.SimpleConnectionPool")
    def test_pool_stats_with_live_pool(self, mock_pool_cls):
        mock_pool = MagicMock()
        mock_pool._used = {"conn1": True}
        mock_pool._pool = {"conn2": True, "conn3": True}
        mock_pool.minconn = 1
        mock_pool.maxconn = 5
        mock_pool_cls.return_value = mock_pool
        store = ApiKeyStore(database_url="postgresql://host/db")
        stats = store.pool_stats()
        assert stats["available"] is True
        assert stats["used"] == 1
        assert stats["free"] == 2
        assert stats["min_connections"] == 1
        assert stats["max_connections"] == 5
        assert stats["utilization_pct"] == 20.0


# ---------------------------------------------------------------------------
# ApiKeyStore.validate_key
# ---------------------------------------------------------------------------

class TestValidateKey:
    def _make_store_with_mock_conn(self, row, fetchone_return=None):
        """Helper: create store with a mocked DB connection returning a given row."""
        store = ApiKeyStore(database_url="postgresql://test")
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = row
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        store._pool = mock_pool
        return store, mock_cursor

    def test_returns_api_key_info_for_active_key(self):
        row = (
            "cvk_abc", "My App", "dev@test.com", "builder", "active",
            300, ["city-san-rafael"], "cus_123", {"org": "test"}, None,
        )
        store, _ = self._make_store_with_mock_conn(row)
        result = store.validate_key("cvk_live_somekey")
        assert result.key_id == "cvk_abc"
        assert result.name == "My App"
        assert result.email == "dev@test.com"
        assert result.tier == "builder"
        assert result.status == "active"
        assert result.rate_limit_per_minute == 300
        assert result.jurisdictions == ["city-san-rafael"]
        assert result.stripe_customer_id == "cus_123"
        assert result.metadata == {"org": "test"}

    def test_returns_none_for_inactive_status(self):
        row = (
            "cvk_abc", "My App", "dev@test.com", "builder", "suspended",
            300, [], None, {}, None,
        )
        store, _ = self._make_store_with_mock_conn(row)
        result = store.validate_key("cvk_live_somekey")
        assert result is None

    def test_returns_none_for_revoked_status(self):
        row = (
            "cvk_abc", "My App", "dev@test.com", "builder", "revoked",
            300, [], None, {}, None,
        )
        store, _ = self._make_store_with_mock_conn(row)
        result = store.validate_key("cvk_live_somekey")
        assert result is None

    def test_returns_none_for_expired_key(self):
        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        row = (
            "cvk_abc", "My App", "dev@test.com", "builder", "active",
            300, [], None, {}, expired,
        )
        store, _ = self._make_store_with_mock_conn(row)
        result = store.validate_key("cvk_live_somekey")
        assert result is None

    def test_returns_info_when_not_yet_expired(self):
        future = datetime.now(timezone.utc) + timedelta(hours=24)
        row = (
            "cvk_abc", "My App", "dev@test.com", "free", "active",
            60, [], None, {}, future,
        )
        store, _ = self._make_store_with_mock_conn(row)
        result = store.validate_key("cvk_live_somekey")
        assert result.key_id == "cvk_abc"
        assert result.tier == "free"

    def test_returns_none_when_key_not_found(self):
        store, _ = self._make_store_with_mock_conn(None)
        result = store.validate_key("cvk_live_unknown")
        assert result is None

    def test_returns_none_when_no_db_connection(self):
        store = ApiKeyStore(database_url=None)
        store._database_url = None
        result = store.validate_key("cvk_live_any")
        assert result is None

    def test_hashes_key_before_lookup(self):
        row = None  # Not found is fine — we're checking the SQL param
        store, mock_cursor = self._make_store_with_mock_conn(row)
        raw_key = "cvk_live_testkey123"
        store.validate_key(raw_key)
        expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        call_args = mock_cursor.execute.call_args
        assert call_args[0][1] == (expected_hash,)

    def test_null_jurisdictions_becomes_empty_list(self):
        row = (
            "cvk_abc", "n", "e", "free", "active",
            60, None, None, None, None,
        )
        store, _ = self._make_store_with_mock_conn(row)
        result = store.validate_key("cvk_live_somekey")
        assert result.jurisdictions == []

    def test_null_metadata_becomes_empty_dict(self):
        row = (
            "cvk_abc", "n", "e", "free", "active",
            60, [], None, None, None,
        )
        store, _ = self._make_store_with_mock_conn(row)
        result = store.validate_key("cvk_live_somekey")
        assert result.metadata == {}


# ---------------------------------------------------------------------------
# ApiKeyStore.create_key
# ---------------------------------------------------------------------------

class TestCreateKey:
    def _make_store(self):
        store = ApiKeyStore(database_url="postgresql://test")
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        store._pool = mock_pool
        return store, mock_cursor, mock_conn

    def test_returns_key_id_and_raw_key(self):
        store, _, _ = self._make_store()
        result = store.create_key(name="Test App", email="test@test.com")
        assert result is not None
        key_id, raw_key = result
        assert key_id.startswith("cvk_")
        assert raw_key.startswith("cvk_live_")

    def test_uses_correct_rate_limit_for_builder_tier(self):
        store, mock_cursor, _ = self._make_store()
        store.create_key(name="Test", email="e", tier="builder")
        insert_args = mock_cursor.execute.call_args[0][1]
        # rate_limit_per_minute is the 9th param (index 8)
        assert insert_args[8] == 300

    def test_uses_correct_rate_limit_for_admin_tier(self):
        store, mock_cursor, _ = self._make_store()
        store.create_key(name="Test", email="e", tier="admin")
        insert_args = mock_cursor.execute.call_args[0][1]
        assert insert_args[8] == 1000

    def test_defaults_to_free_tier(self):
        store, mock_cursor, _ = self._make_store()
        store.create_key(name="Test", email="e")
        insert_args = mock_cursor.execute.call_args[0][1]
        # tier is the 5th param (index 4)
        assert insert_args[4] == "free"
        # free tier rate limit
        assert insert_args[8] == 60

    def test_commits_on_success(self):
        store, _, mock_conn = self._make_store()
        store.create_key(name="Test", email="e")
        mock_conn.commit.assert_called_once()

    def test_returns_none_when_no_db(self):
        store = ApiKeyStore(database_url=None)
        store._database_url = None
        result = store.create_key(name="Test", email="e")
        assert result is None

    def test_rollback_on_db_error(self):
        store, mock_cursor, mock_conn = self._make_store()
        mock_cursor.execute.side_effect = Exception("DB error")
        result = store.create_key(name="Test", email="e")
        assert result is None
        mock_conn.rollback.assert_called_once()

    def test_unknown_tier_uses_free_rate_limit(self):
        store, mock_cursor, _ = self._make_store()
        store.create_key(name="Test", email="e", tier="nonexistent")
        insert_args = mock_cursor.execute.call_args[0][1]
        # Should fall back to free tier rate limit
        assert insert_args[8] == TIER_CONFIG["free"]["rate_limit_per_minute"]


# ---------------------------------------------------------------------------
# ApiKeyStore.suspend_key / revoke_key
# ---------------------------------------------------------------------------

class TestKeyStatusChanges:
    def _make_store(self, rowcount=1):
        store = ApiKeyStore(database_url="postgresql://test")
        mock_cursor = MagicMock()
        mock_cursor.rowcount = rowcount
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        store._pool = mock_pool
        return store, mock_cursor

    def test_suspend_key_sets_suspended_status(self):
        store, mock_cursor = self._make_store(rowcount=1)
        result = store.suspend_key("cvk_abc")
        assert result is True
        sql_params = mock_cursor.execute.call_args[0][1]
        assert sql_params == ("suspended", "cvk_abc")

    def test_revoke_key_sets_revoked_status(self):
        store, mock_cursor = self._make_store(rowcount=1)
        result = store.revoke_key("cvk_abc")
        assert result is True
        sql_params = mock_cursor.execute.call_args[0][1]
        assert sql_params == ("revoked", "cvk_abc")

    def test_returns_false_when_key_not_found(self):
        store, _ = self._make_store(rowcount=0)
        result = store.suspend_key("cvk_nonexistent")
        assert result is False

    def test_returns_false_when_no_db(self):
        store = ApiKeyStore(database_url=None)
        store._database_url = None
        assert store.suspend_key("cvk_abc") is False
        assert store.revoke_key("cvk_abc") is False


# ---------------------------------------------------------------------------
# ApiKeyStore.list_keys
# ---------------------------------------------------------------------------

class TestListKeys:
    def _make_store(self, rows):
        store = ApiKeyStore(database_url="postgresql://test")
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        store._pool = mock_pool
        return store

    def test_returns_formatted_key_dicts(self):
        created = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        used = datetime(2026, 4, 1, 12, 30, 0, tzinfo=timezone.utc)
        rows = [
            ("cvk_abc", "My App", "dev@test.com", "builder", "active",
             300, created, used, "cus_123", ["city-san-rafael"]),
        ]
        store = self._make_store(rows)
        result = store.list_keys()
        assert len(result) == 1
        key = result[0]
        assert key["key_id"] == "cvk_abc"
        assert key["name"] == "My App"
        assert key["email"] == "dev@test.com"
        assert key["tier"] == "builder"
        assert key["status"] == "active"
        assert key["rate_limit_per_minute"] == 300
        assert key["created_at"] == "2026-01-15T10:00:00+00:00"
        assert key["last_used_at"] == "2026-04-01T12:30:00+00:00"
        assert key["stripe_customer_id"] == "cus_123"
        assert key["jurisdictions"] == ["city-san-rafael"]

    def test_handles_null_timestamps(self):
        rows = [
            ("cvk_abc", "n", "e", "free", "active", 60, None, None, None, None),
        ]
        store = self._make_store(rows)
        result = store.list_keys()
        assert result[0]["created_at"] is None
        assert result[0]["last_used_at"] is None
        assert result[0]["jurisdictions"] == []

    def test_returns_empty_list_when_no_db(self):
        store = ApiKeyStore(database_url=None)
        store._database_url = None
        assert store.list_keys() == []

    def test_returns_empty_list_on_db_error(self):
        store = ApiKeyStore(database_url="postgresql://test")
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.side_effect = Exception("DB error")
        mock_pool.getconn.return_value = mock_conn
        store._pool = mock_pool
        assert store.list_keys() == []


# ---------------------------------------------------------------------------
# ApiKeyStore.get_usage_stats
# ---------------------------------------------------------------------------

class TestGetUsageStats:
    def _make_store(self, agg_row, endpoint_rows):
        store = ApiKeyStore(database_url="postgresql://test")
        mock_cursor = MagicMock()
        # First fetchone for aggregates, then fetchall for endpoints
        mock_cursor.fetchone.return_value = agg_row
        mock_cursor.fetchall.return_value = endpoint_rows
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        store._pool = mock_pool
        return store

    def test_returns_usage_stats_with_defaults(self):
        store = self._make_store(
            agg_row=(150, 5, 95),
            endpoint_rows=[("/search", 100), ("/context", 50)],
        )
        result = store.get_usage_stats("cvk_abc")
        assert result.key_id == "cvk_abc"
        assert result.total_requests == 150
        assert result.error_count == 5
        assert result.avg_response_ms == 95
        assert result.by_endpoint == {"/search": 100, "/context": 50}
        assert result.period_start == "last_30_days"

    def test_uses_since_parameter_as_period_start(self):
        store = self._make_store(
            agg_row=(10, 0, 50),
            endpoint_rows=[],
        )
        result = store.get_usage_stats("cvk_abc", since="2026-03-01")
        assert result.period_start == "2026-03-01"

    def test_handles_null_aggregates(self):
        store = self._make_store(
            agg_row=(None, None, None),
            endpoint_rows=[],
        )
        result = store.get_usage_stats("cvk_abc")
        assert result.total_requests == 0
        assert result.error_count == 0
        assert result.avg_response_ms is None
        assert result.by_endpoint == {}

    def test_returns_none_when_no_db(self):
        store = ApiKeyStore(database_url=None)
        store._database_url = None
        result = store.get_usage_stats("cvk_abc")
        assert result is None


# ---------------------------------------------------------------------------
# ApiKeyStore.get_key_by_stripe_customer
# ---------------------------------------------------------------------------

class TestGetKeyByStripeCustomer:
    def _make_store(self, row):
        store = ApiKeyStore(database_url="postgresql://test")
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = row
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        store._pool = mock_pool
        return store

    def test_returns_key_dict(self):
        store = self._make_store(("cvk_abc", "My App", "dev@test.com", "builder", "active"))
        result = store.get_key_by_stripe_customer("cus_123")
        assert result["key_id"] == "cvk_abc"
        assert result["name"] == "My App"
        assert result["email"] == "dev@test.com"
        assert result["tier"] == "builder"
        assert result["status"] == "active"

    def test_returns_none_when_not_found(self):
        store = self._make_store(None)
        result = store.get_key_by_stripe_customer("cus_unknown")
        assert result is None

    def test_returns_none_when_no_db(self):
        store = ApiKeyStore(database_url=None)
        store._database_url = None
        result = store.get_key_by_stripe_customer("cus_123")
        assert result is None


# ---------------------------------------------------------------------------
# ApiKeyStore.update_key_stripe
# ---------------------------------------------------------------------------

class TestUpdateKeyStripe:
    def _make_store(self, rowcount=1):
        store = ApiKeyStore(database_url="postgresql://test")
        mock_cursor = MagicMock()
        mock_cursor.rowcount = rowcount
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        store._pool = mock_pool
        return store, mock_cursor

    def test_updates_stripe_customer_id(self):
        store, mock_cursor = self._make_store()
        result = store.update_key_stripe("cvk_abc", stripe_customer_id="cus_new")
        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        assert "stripe_customer_id" in sql
        params = mock_cursor.execute.call_args[0][1]
        assert "cus_new" in params

    def test_updates_tier_and_rate_limit_together(self):
        store, mock_cursor = self._make_store()
        result = store.update_key_stripe("cvk_abc", tier="admin")
        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        assert "tier" in sql
        assert "rate_limit_per_minute" in sql
        params = mock_cursor.execute.call_args[0][1]
        assert "admin" in params
        assert 1000 in params  # admin rate limit

    def test_returns_false_when_no_fields_provided(self):
        store, _ = self._make_store()
        result = store.update_key_stripe("cvk_abc")
        assert result is False

    def test_returns_false_when_key_not_found(self):
        store, _ = self._make_store(rowcount=0)
        result = store.update_key_stripe("cvk_abc", stripe_customer_id="cus_new")
        assert result is False

    def test_returns_false_when_no_db(self):
        store = ApiKeyStore(database_url=None)
        store._database_url = None
        result = store.update_key_stripe("cvk_abc", tier="builder")
        assert result is False

    def test_unknown_tier_uses_free_rate_limit(self):
        store, mock_cursor = self._make_store()
        store.update_key_stripe("cvk_abc", tier="nonexistent")
        params = mock_cursor.execute.call_args[0][1]
        assert TIER_CONFIG["free"]["rate_limit_per_minute"] in params

    def test_updates_multiple_fields_at_once(self):
        store, mock_cursor = self._make_store()
        result = store.update_key_stripe(
            "cvk_abc",
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_456",
            tier="builder",
        )
        assert result is True
        sql = mock_cursor.execute.call_args[0][0]
        assert "stripe_customer_id" in sql
        assert "stripe_subscription_id" in sql
        assert "tier" in sql


# ---------------------------------------------------------------------------
# ApiKeyStore.log_usage / update_last_used
# ---------------------------------------------------------------------------

class TestLogUsage:
    def _make_store(self):
        store = ApiKeyStore(database_url="postgresql://test")
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        store._pool = mock_pool
        return store, mock_cursor, mock_conn

    def test_log_usage_inserts_correct_params(self):
        store, mock_cursor, mock_conn = self._make_store()
        store.log_usage(
            key_id="cvk_abc",
            endpoint="/api/v2/civic/search",
            method="POST",
            status_code=200,
            response_time_ms=120,
            jurisdiction="city-san-rafael",
        )
        insert_params = mock_cursor.execute.call_args[0][1]
        assert insert_params == (
            "cvk_abc", "/api/v2/civic/search", "POST", 200, 120, "city-san-rafael",
        )
        mock_conn.commit.assert_called_once()

    def test_log_usage_accepts_none_key_id(self):
        store, mock_cursor, _ = self._make_store()
        store.log_usage(key_id=None, endpoint="/health")
        insert_params = mock_cursor.execute.call_args[0][1]
        assert insert_params[0] is None

    def test_log_usage_does_not_raise_on_db_error(self):
        store, mock_cursor, _ = self._make_store()
        mock_cursor.execute.side_effect = Exception("DB error")
        # Should not raise
        store.log_usage(key_id="cvk_abc", endpoint="/test")

    def test_log_usage_noop_without_db(self):
        store = ApiKeyStore(database_url=None)
        store._database_url = None
        # Should not raise
        store.log_usage(key_id="cvk_abc", endpoint="/test")

    def test_update_last_used_commits(self):
        store, mock_cursor, mock_conn = self._make_store()
        store.update_last_used("cvk_abc")
        assert mock_cursor.execute.called
        params = mock_cursor.execute.call_args[0][1]
        assert params == ("cvk_abc",)
        mock_conn.commit.assert_called_once()

    def test_update_last_used_noop_without_db(self):
        store = ApiKeyStore(database_url=None)
        store._database_url = None
        # Should not raise
        store.update_last_used("cvk_abc")


# ---------------------------------------------------------------------------
# ApiKeyStore.get_all_usage_summary
# ---------------------------------------------------------------------------

class TestGetAllUsageSummary:
    def _make_store(self, rows):
        store = ApiKeyStore(database_url="postgresql://test")
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        store._pool = mock_pool
        return store

    def test_returns_summary_list(self):
        rows = [
            ("cvk_abc", "My App", "builder", 500, 10, 85),
            ("cvk_def", "Other", "free", 200, 3, 120),
        ]
        store = self._make_store(rows)
        result = store.get_all_usage_summary()
        assert len(result) == 2
        assert result[0]["key_id"] == "cvk_abc"
        assert result[0]["request_count"] == 500
        assert result[0]["error_count"] == 10
        assert result[0]["avg_response_ms"] == 85
        assert result[1]["key_id"] == "cvk_def"
        assert result[1]["request_count"] == 200

    def test_returns_empty_list_when_no_db(self):
        store = ApiKeyStore(database_url=None)
        store._database_url = None
        assert store.get_all_usage_summary() == []

    def test_returns_empty_list_on_error(self):
        store = ApiKeyStore(database_url="postgresql://test")
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.side_effect = Exception("DB error")
        mock_pool.getconn.return_value = mock_conn
        store._pool = mock_pool
        assert store.get_all_usage_summary() == []


# ---------------------------------------------------------------------------
# get_api_key_store singleton
# ---------------------------------------------------------------------------

class TestGetApiKeyStore:
    def test_returns_api_key_store_instance(self):
        # Reset the module-level singleton
        import civicos_services.core.api_keys as mod
        original = mod._store
        mod._store = None
        try:
            store = get_api_key_store()
            # Verify it's a real ApiKeyStore with expected initial state
            assert store._pool is None
            assert store.available is False  # No DB configured in test env
        finally:
            mod._store = original

    def test_returns_same_instance_on_second_call(self):
        import civicos_services.core.api_keys as mod
        original = mod._store
        mod._store = None
        try:
            s1 = get_api_key_store()
            s2 = get_api_key_store()
            assert s1 is s2
        finally:
            mod._store = original
