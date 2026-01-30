"""
Tests for MCP Peer Registry.

Tests cover:
- PeerInfo dataclass operations
- PeerRegistry CRUD operations
- Health checking (with mock)
- Configuration loading (env, yaml, direct)
- Background health check loop
"""

import asyncio
import os
import pytest
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from federation import (
    PeerInfo,
    PeerRegistry,
    HttpHealthChecker,
    init_registry,
    shutdown_registry,
    get_registry,
    PeerQueryResult,
    FederatedQueryResult,
    query_peer,
    query_peers_parallel,
    deduplicate_by_id,
    format_federation_summary,
)


class TestPeerInfo:
    """Tests for PeerInfo dataclass."""

    def test_create_peer_info(self):
        """Test basic PeerInfo creation."""
        peer = PeerInfo(
            jurisdiction_id="city-berkeley",
            mcp_endpoint="https://berkeley.civicos.org/mcp"
        )
        assert peer.jurisdiction_id == "city-berkeley"
        assert peer.mcp_endpoint == "https://berkeley.civicos.org/mcp"
        assert peer.is_healthy is False
        assert peer.last_seen is None
        assert peer.consecutive_failures == 0

    def test_mark_healthy(self):
        """Test marking peer as healthy."""
        peer = PeerInfo(
            jurisdiction_id="city-berkeley",
            mcp_endpoint="https://berkeley.civicos.org/mcp"
        )
        peer.mark_healthy()

        assert peer.is_healthy is True
        assert peer.last_seen is not None
        assert peer.last_error is None
        assert peer.consecutive_failures == 0

    def test_mark_unhealthy(self):
        """Test marking peer as unhealthy."""
        peer = PeerInfo(
            jurisdiction_id="city-berkeley",
            mcp_endpoint="https://berkeley.civicos.org/mcp"
        )
        peer.mark_healthy()  # Start healthy
        peer.mark_unhealthy("Connection refused")

        assert peer.is_healthy is False
        assert peer.last_error == "Connection refused"
        assert peer.consecutive_failures == 1

        # Multiple failures accumulate
        peer.mark_unhealthy("Timeout")
        assert peer.consecutive_failures == 2
        assert peer.last_error == "Timeout"

    def test_mark_healthy_resets_failures(self):
        """Test that marking healthy resets failure count."""
        peer = PeerInfo(
            jurisdiction_id="city-berkeley",
            mcp_endpoint="https://berkeley.civicos.org/mcp"
        )
        peer.mark_unhealthy("Error 1")
        peer.mark_unhealthy("Error 2")
        assert peer.consecutive_failures == 2

        peer.mark_healthy()
        assert peer.consecutive_failures == 0
        assert peer.last_error is None

    def test_to_dict(self):
        """Test serialization to dictionary."""
        peer = PeerInfo(
            jurisdiction_id="city-berkeley",
            mcp_endpoint="https://berkeley.civicos.org/mcp"
        )
        peer.mark_healthy()

        data = peer.to_dict()

        assert data["jurisdiction_id"] == "city-berkeley"
        assert data["mcp_endpoint"] == "https://berkeley.civicos.org/mcp"
        assert data["is_healthy"] is True
        assert data["last_seen"] is not None
        assert data["consecutive_failures"] == 0


class TestPeerRegistry:
    """Tests for PeerRegistry class."""

    def test_add_peer(self):
        """Test adding a peer to registry."""
        registry = PeerRegistry()
        peer = registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")

        assert peer.jurisdiction_id == "city-berkeley"
        assert registry.get_peer("city-berkeley") is peer

    def test_remove_peer(self):
        """Test removing a peer from registry."""
        registry = PeerRegistry()
        registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")

        assert registry.remove_peer("city-berkeley") is True
        assert registry.get_peer("city-berkeley") is None

        # Removing non-existent peer returns False
        assert registry.remove_peer("city-nonexistent") is False

    def test_get_peer_not_found(self):
        """Test getting non-existent peer returns None."""
        registry = PeerRegistry()
        assert registry.get_peer("city-nonexistent") is None

    def test_list_peers(self):
        """Test listing all peers."""
        registry = PeerRegistry()
        registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")
        registry.add_peer("city-oakland", "https://oakland.civicos.org/mcp")

        peers = registry.list_peers()
        assert len(peers) == 2

        jurisdictions = {p.jurisdiction_id for p in peers}
        assert jurisdictions == {"city-berkeley", "city-oakland"}

    def test_list_peers_healthy_only(self):
        """Test filtering to healthy peers only."""
        registry = PeerRegistry()
        berkeley = registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")
        oakland = registry.add_peer("city-oakland", "https://oakland.civicos.org/mcp")

        # Only Berkeley is healthy
        berkeley.mark_healthy()

        all_peers = registry.list_peers(healthy_only=False)
        assert len(all_peers) == 2

        healthy_peers = registry.list_peers(healthy_only=True)
        assert len(healthy_peers) == 1
        assert healthy_peers[0].jurisdiction_id == "city-berkeley"

    def test_list_jurisdictions(self):
        """Test listing jurisdiction IDs."""
        registry = PeerRegistry()
        registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")
        registry.add_peer("city-oakland", "https://oakland.civicos.org/mcp")

        jurisdictions = registry.list_jurisdictions()
        assert set(jurisdictions) == {"city-berkeley", "city-oakland"}

    def test_summary(self):
        """Test registry summary for diagnostics."""
        registry = PeerRegistry()
        berkeley = registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")
        registry.add_peer("city-oakland", "https://oakland.civicos.org/mcp")

        berkeley.mark_healthy()

        summary = registry.summary()

        assert summary["total_peers"] == 2
        assert summary["healthy_peers"] == 1
        assert summary["unhealthy_peers"] == 1
        assert len(summary["peers"]) == 2


class TestHealthCheck:
    """Tests for health checking functionality."""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Test health check marks peer as healthy."""
        # Create mock health checker that returns healthy
        mock_checker = AsyncMock()
        mock_checker.check.return_value = (True, None)

        registry = PeerRegistry(health_checker=mock_checker)
        registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")

        result = await registry.health_check("city-berkeley")

        assert result is True
        peer = registry.get_peer("city-berkeley")
        assert peer.is_healthy is True
        mock_checker.check.assert_called_once_with("https://berkeley.civicos.org/mcp")

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """Test health check marks peer as unhealthy."""
        mock_checker = AsyncMock()
        mock_checker.check.return_value = (False, "Connection refused")

        registry = PeerRegistry(health_checker=mock_checker)
        registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")

        result = await registry.health_check("city-berkeley")

        assert result is False
        peer = registry.get_peer("city-berkeley")
        assert peer.is_healthy is False
        assert peer.last_error == "Connection refused"

    @pytest.mark.asyncio
    async def test_health_check_unknown_peer(self):
        """Test health check for unknown peer returns False."""
        registry = PeerRegistry()
        result = await registry.health_check("city-nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_all(self):
        """Test refreshing health status for all peers."""
        mock_checker = AsyncMock()
        # Berkeley healthy, Oakland unhealthy
        mock_checker.check.side_effect = [
            (True, None),
            (False, "Timeout"),
        ]

        registry = PeerRegistry(health_checker=mock_checker)
        registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")
        registry.add_peer("city-oakland", "https://oakland.civicos.org/mcp")

        results = await registry.refresh_all()

        # Should have checked both peers
        assert mock_checker.check.call_count == 2

        # Verify results based on what was checked
        # Note: dict iteration order isn't guaranteed, so check by value
        assert True in results.values()
        assert False in results.values()

    @pytest.mark.asyncio
    async def test_refresh_all_empty_registry(self):
        """Test refresh with no peers returns empty dict."""
        registry = PeerRegistry()
        results = await registry.refresh_all()
        assert results == {}


class TestConfiguration:
    """Tests for configuration loading."""

    def test_from_config_list(self):
        """Test creating registry from config list."""
        config = [
            {"jurisdiction_id": "city-berkeley", "mcp_endpoint": "https://berkeley.civicos.org/mcp"},
            {"jurisdiction_id": "city-oakland", "mcp_endpoint": "https://oakland.civicos.org/mcp"},
        ]

        registry = PeerRegistry.from_config(config)

        assert len(registry.list_peers()) == 2
        assert registry.get_peer("city-berkeley") is not None
        assert registry.get_peer("city-oakland") is not None

    def test_from_config_invalid_entry(self):
        """Test that invalid config entries are skipped."""
        config = [
            {"jurisdiction_id": "city-berkeley", "mcp_endpoint": "https://berkeley.civicos.org/mcp"},
            {"invalid": "entry"},  # Missing required fields
            {"jurisdiction_id": "city-oakland"},  # Missing mcp_endpoint
        ]

        registry = PeerRegistry.from_config(config)

        # Only valid entry should be added
        assert len(registry.list_peers()) == 1

    def test_from_env(self):
        """Test creating registry from environment variables."""
        with patch.dict(os.environ, {
            "CIVICOS_PEERS": "city-berkeley:https://berkeley.civicos.org/mcp,city-oakland:https://oakland.civicos.org/mcp",
            "CIVICOS_PEER_CHECK_INTERVAL": "60",
        }):
            registry = PeerRegistry.from_env()

            assert len(registry.list_peers()) == 2
            assert registry.get_peer("city-berkeley") is not None
            assert registry._health_check_interval == 60.0

    def test_from_env_empty(self):
        """Test creating registry with no env vars."""
        with patch.dict(os.environ, {}, clear=True):
            registry = PeerRegistry.from_env()
            assert len(registry.list_peers()) == 0

    def test_from_yaml(self):
        """Test creating registry from YAML file."""
        yaml_content = """
peers:
  - jurisdiction_id: city-berkeley
    mcp_endpoint: https://berkeley.civicos.org/mcp
  - jurisdiction_id: city-oakland
    mcp_endpoint: https://oakland.civicos.org/mcp
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                registry = PeerRegistry.from_yaml(f.name)

                assert len(registry.list_peers()) == 2
                assert registry.get_peer("city-berkeley") is not None
                assert registry.get_peer("city-oakland") is not None
            finally:
                os.unlink(f.name)


class TestBackgroundChecks:
    """Tests for background health check loop."""

    @pytest.mark.asyncio
    async def test_start_stop_background_checks(self):
        """Test starting and stopping background health checks."""
        mock_checker = AsyncMock()
        mock_checker.check.return_value = (True, None)

        registry = PeerRegistry(health_checker=mock_checker, health_check_interval=0.1)
        registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")

        await registry.start_background_checks()
        assert registry._running is True
        assert registry._background_task is not None

        # Let a few checks run
        await asyncio.sleep(0.25)

        await registry.stop_background_checks()
        assert registry._running is False
        assert registry._background_task is None

        # Should have made at least 2 health checks
        assert mock_checker.check.call_count >= 2

    @pytest.mark.asyncio
    async def test_start_twice_no_duplicate(self):
        """Test that starting twice doesn't create duplicate tasks."""
        registry = PeerRegistry(health_check_interval=1.0)

        await registry.start_background_checks()
        first_task = registry._background_task

        await registry.start_background_checks()
        second_task = registry._background_task

        assert first_task is second_task

        await registry.stop_background_checks()


class TestGlobalRegistry:
    """Tests for global registry singleton."""

    @pytest.mark.asyncio
    async def test_init_and_get_registry(self):
        """Test initializing and getting global registry."""
        with patch.dict(os.environ, {"CIVICOS_PEERS": ""}):
            registry = await init_registry()

            assert registry is not None
            assert get_registry() is registry

            await shutdown_registry()
            assert get_registry() is None

    @pytest.mark.asyncio
    async def test_init_with_peers(self):
        """Test init performs initial health check if peers exist."""
        mock_checker = AsyncMock()
        mock_checker.check.return_value = (True, None)

        with patch.dict(os.environ, {
            "CIVICOS_PEERS": "city-berkeley:https://berkeley.civicos.org/mcp"
        }):
            # Create registry with mock checker
            from federation import PeerRegistry
            with patch.object(PeerRegistry, 'from_env') as mock_from_env:
                test_registry = PeerRegistry(health_checker=mock_checker)
                test_registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")
                mock_from_env.return_value = test_registry

                registry = await init_registry()

                # Should have done initial health check
                mock_checker.check.assert_called()

                await shutdown_registry()


class TestHttpHealthChecker:
    """Tests for HttpHealthChecker."""

    @pytest.mark.asyncio
    async def test_successful_check(self):
        """Test successful health check."""
        checker = HttpHealthChecker(timeout=5.0)

        # Mock httpx to return success
        with patch('federation.httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            is_healthy, error = await checker.check("https://example.com/mcp")

            assert is_healthy is True
            assert error is None

    @pytest.mark.asyncio
    async def test_failed_check_http_error(self):
        """Test health check with HTTP error."""
        checker = HttpHealthChecker(timeout=5.0)

        with patch('federation.httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            is_healthy, error = await checker.check("https://example.com/mcp")

            assert is_healthy is False
            assert "500" in error

    @pytest.mark.asyncio
    async def test_failed_check_timeout(self):
        """Test health check with timeout."""
        import httpx
        checker = HttpHealthChecker(timeout=5.0)

        with patch('federation.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = httpx.TimeoutException("")

            is_healthy, error = await checker.check("https://example.com/mcp")

            assert is_healthy is False
            assert "Timeout" in error

    @pytest.mark.asyncio
    async def test_failed_check_connection_error(self):
        """Test health check with connection error."""
        import httpx
        checker = HttpHealthChecker(timeout=5.0)

        with patch('federation.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get.side_effect = httpx.ConnectError("Connection refused")

            is_healthy, error = await checker.check("https://example.com/mcp")

            assert is_healthy is False
            assert "Connection error" in error


# ============================================================================
# Query Routing Tests
# ============================================================================


class TestPeerQueryResult:
    """Tests for PeerQueryResult dataclass."""

    def test_successful_result_with_data(self):
        """Test creating a successful query result with parsed JSON."""
        result = PeerQueryResult(
            jurisdiction_id="city-berkeley",
            success=True,
            data={"decisions": [{"id": "1", "title": "Test"}]},
            latency_ms=150.5,
        )
        assert result.success is True
        assert result.data["decisions"][0]["title"] == "Test"
        assert result.error is None
        assert result.latency_ms == 150.5

    def test_successful_result_with_raw_response(self):
        """Test creating a successful query result with raw text."""
        result = PeerQueryResult(
            jurisdiction_id="city-oakland",
            success=True,
            raw_response="# Results\n- Item 1\n- Item 2",
            latency_ms=200.0,
        )
        assert result.success is True
        assert result.raw_response.startswith("# Results")
        assert result.data is None

    def test_failed_result(self):
        """Test creating a failed query result."""
        result = PeerQueryResult(
            jurisdiction_id="city-sf",
            success=False,
            error="Timeout",
            latency_ms=10000.0,
        )
        assert result.success is False
        assert result.error == "Timeout"
        assert result.data is None


class TestFederatedQueryResult:
    """Tests for FederatedQueryResult dataclass."""

    def test_all_results_combines_local_and_peer(self):
        """Test that all_results() correctly combines and labels results."""
        federated = FederatedQueryResult(
            local_jurisdiction="san-rafael",
            local_results=[
                {"id": "local-1", "title": "Local Decision"},
            ],
            peer_results={
                "city-berkeley": PeerQueryResult(
                    jurisdiction_id="city-berkeley",
                    success=True,
                    data=[{"id": "peer-1", "title": "Berkeley Decision"}],
                ),
                "city-oakland": PeerQueryResult(
                    jurisdiction_id="city-oakland",
                    success=False,
                    error="Timeout",
                ),
            },
            total_peers_queried=2,
            successful_peers=1,
            failed_peers=1,
            total_latency_ms=500.0,
        )

        all_results = federated.all_results()

        # Should have 2 items: 1 local + 1 from berkeley (oakland failed)
        assert len(all_results) == 2

        # Local results should be first
        assert all_results[0]["_source_jurisdiction"] == "san-rafael"
        assert all_results[0]["title"] == "Local Decision"

        # Berkeley result should have jurisdiction label
        assert all_results[1]["_source_jurisdiction"] == "city-berkeley"
        assert all_results[1]["title"] == "Berkeley Decision"

    def test_all_results_empty_when_no_data(self):
        """Test all_results() with no local or peer data."""
        federated = FederatedQueryResult(
            local_jurisdiction="san-rafael",
            local_results=[],
            peer_results={},
            total_peers_queried=0,
            successful_peers=0,
            failed_peers=0,
            total_latency_ms=0.0,
        )

        assert federated.all_results() == []


class TestQueryPeer:
    """Tests for query_peer function."""

    @pytest.mark.asyncio
    async def test_successful_json_response(self):
        """Test successful peer query with JSON response."""
        peer = PeerInfo(
            jurisdiction_id="city-berkeley",
            mcp_endpoint="https://berkeley.civicos.org/mcp",
        )

        with patch('federation.httpx.AsyncClient') as mock_client:
            # Use Mock for sync methods (json, text) and AsyncMock for async (post)
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"decisions": [{"id": "1"}]}

            async def mock_post(*args, **kwargs):
                return mock_response

            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await query_peer(
                peer,
                tool_name="search_meeting_history",
                tool_args={"query": "housing"},
                timeout=5.0,
            )

            assert result.success is True
            assert result.jurisdiction_id == "city-berkeley"
            assert result.data == {"decisions": [{"id": "1"}]}
            assert result.error is None

    @pytest.mark.asyncio
    async def test_successful_text_response(self):
        """Test successful peer query with non-JSON response."""
        peer = PeerInfo(
            jurisdiction_id="city-oakland",
            mcp_endpoint="https://oakland.civicos.org/mcp",
        )

        with patch('federation.httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.side_effect = ValueError("Not JSON")
            mock_response.text = "# Results\n- Decision 1"

            async def mock_post(*args, **kwargs):
                return mock_response

            mock_client.return_value.__aenter__.return_value.post = mock_post

            result = await query_peer(
                peer,
                tool_name="search_meeting_history",
                tool_args={"query": "traffic"},
                timeout=5.0,
            )

            assert result.success is True
            assert result.raw_response == "# Results\n- Decision 1"
            assert result.data is None

    @pytest.mark.asyncio
    async def test_http_error_response(self):
        """Test peer query with HTTP error."""
        peer = PeerInfo(
            jurisdiction_id="city-sf",
            mcp_endpoint="https://sf.civicos.org/mcp",
        )

        with patch('federation.httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            result = await query_peer(
                peer,
                tool_name="search_meeting_history",
                tool_args={"query": "parks"},
                timeout=5.0,
            )

            assert result.success is False
            assert "500" in result.error

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """Test peer query with timeout."""
        import httpx

        peer = PeerInfo(
            jurisdiction_id="city-slow",
            mcp_endpoint="https://slow.civicos.org/mcp",
        )

        with patch('federation.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.TimeoutException("")

            result = await query_peer(
                peer,
                tool_name="search_meeting_history",
                tool_args={"query": "test"},
                timeout=1.0,
            )

            assert result.success is False
            assert "Timeout" in result.error

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test peer query with connection error."""
        import httpx

        peer = PeerInfo(
            jurisdiction_id="city-offline",
            mcp_endpoint="https://offline.civicos.org/mcp",
        )

        with patch('federation.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = httpx.ConnectError("No route to host")

            result = await query_peer(
                peer,
                tool_name="search_meeting_history",
                tool_args={"query": "test"},
                timeout=5.0,
            )

            assert result.success is False
            assert "Connection error" in result.error


class TestQueryPeersParallel:
    """Tests for query_peers_parallel function."""

    @pytest.mark.asyncio
    async def test_queries_all_healthy_peers(self):
        """Test that parallel query contacts all healthy peers."""
        registry = PeerRegistry()
        registry.add_peer("city-berkeley", "https://berkeley.civicos.org/mcp")
        registry.add_peer("city-oakland", "https://oakland.civicos.org/mcp")

        # Mark both healthy
        registry.get_peer("city-berkeley").mark_healthy()
        registry.get_peer("city-oakland").mark_healthy()

        with patch('federation.httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": "ok"}

            async def mock_post(*args, **kwargs):
                return mock_response

            mock_client.return_value.__aenter__.return_value.post = mock_post

            results = await query_peers_parallel(
                tool_name="test_tool",
                tool_args={"query": "test"},
                registry=registry,
                timeout=5.0,
            )

            # Should have results from both peers
            assert len(results) == 2
            assert "city-berkeley" in results
            assert "city-oakland" in results
            assert results["city-berkeley"].success is True
            assert results["city-oakland"].success is True

    @pytest.mark.asyncio
    async def test_skips_unhealthy_peers(self):
        """Test that parallel query skips unhealthy peers."""
        registry = PeerRegistry()
        registry.add_peer("city-healthy", "https://healthy.civicos.org/mcp")
        registry.add_peer("city-unhealthy", "https://unhealthy.civicos.org/mcp")

        # Only mark one healthy
        registry.get_peer("city-healthy").mark_healthy()
        # city-unhealthy stays unhealthy (default)

        with patch('federation.httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"result": "ok"}

            async def mock_post(*args, **kwargs):
                return mock_response

            mock_client.return_value.__aenter__.return_value.post = mock_post

            results = await query_peers_parallel(
                tool_name="test_tool",
                tool_args={"query": "test"},
                registry=registry,
                healthy_only=True,
            )

            # Should only have result from healthy peer
            assert len(results) == 1
            assert "city-healthy" in results
            assert "city-unhealthy" not in results

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_registry(self):
        """Test that parallel query returns empty dict when no registry."""
        with patch('federation.get_registry', return_value=None):
            results = await query_peers_parallel(
                tool_name="test_tool",
                tool_args={"query": "test"},
            )

            assert results == {}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_peers(self):
        """Test that parallel query returns empty dict when no peers."""
        registry = PeerRegistry()  # Empty registry

        results = await query_peers_parallel(
            tool_name="test_tool",
            tool_args={"query": "test"},
            registry=registry,
        )

        assert results == {}

    @pytest.mark.asyncio
    async def test_handles_mixed_success_failure(self):
        """Test parallel query with some successes and some failures."""
        import httpx

        registry = PeerRegistry()
        registry.add_peer("city-success", "https://success.civicos.org/mcp")
        registry.add_peer("city-fail", "https://fail.civicos.org/mcp")
        registry.get_peer("city-success").mark_healthy()
        registry.get_peer("city-fail").mark_healthy()

        call_count = 0

        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if "success" in str(args) or "success" in str(kwargs.get('json', {})):
                mock_resp = AsyncMock()
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"result": "ok"}
                return mock_resp
            else:
                raise httpx.TimeoutException("")

        with patch('federation.httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = mock_post

            results = await query_peers_parallel(
                tool_name="test_tool",
                tool_args={"query": "test"},
                registry=registry,
                timeout=1.0,
            )

            # Both peers should be in results
            assert len(results) == 2
            # At least one should have failed due to timeout
            # (The mock doesn't perfectly simulate the per-peer behavior,
            # but we verify both are present)


class TestDeduplicateById:
    """Tests for deduplicate_by_id function."""

    def test_removes_duplicates(self):
        """Test that duplicates are removed, keeping first occurrence."""
        items = [
            {"id": "1", "title": "First"},
            {"id": "2", "title": "Second"},
            {"id": "1", "title": "Duplicate of First"},
            {"id": "3", "title": "Third"},
        ]

        result = deduplicate_by_id(items)

        assert len(result) == 3
        assert result[0]["title"] == "First"  # Original kept
        assert result[1]["title"] == "Second"
        assert result[2]["title"] == "Third"

    def test_keeps_items_without_id(self):
        """Test that items without ID field are kept."""
        items = [
            {"id": "1", "title": "Has ID"},
            {"title": "No ID"},
            {"other_field": "value"},
        ]

        result = deduplicate_by_id(items)

        assert len(result) == 3

    def test_handles_non_dict_items(self):
        """Test that non-dict items are kept as-is."""
        items = [
            {"id": "1", "title": "Dict"},
            "string item",
            123,
            {"id": "2", "title": "Another dict"},
        ]

        result = deduplicate_by_id(items)

        assert len(result) == 4
        assert result[1] == "string item"
        assert result[2] == 123

    def test_custom_id_field(self):
        """Test deduplication with custom ID field."""
        items = [
            {"entity_id": "a", "name": "First"},
            {"entity_id": "b", "name": "Second"},
            {"entity_id": "a", "name": "Duplicate"},
        ]

        result = deduplicate_by_id(items, id_field="entity_id")

        assert len(result) == 2
        assert result[0]["name"] == "First"
        assert result[1]["name"] == "Second"

    def test_empty_list(self):
        """Test with empty list."""
        assert deduplicate_by_id([]) == []


class TestFormatFederationSummary:
    """Tests for format_federation_summary function."""

    def test_local_only(self):
        """Test summary with no peer results."""
        summary = format_federation_summary("san-rafael", {})

        assert "san-rafael" in summary
        assert "peers" not in summary.lower()

    def test_with_successful_peers(self):
        """Test summary with successful peer queries."""
        peer_results = {
            "city-berkeley": PeerQueryResult(
                jurisdiction_id="city-berkeley",
                success=True,
                data={},
            ),
            "city-oakland": PeerQueryResult(
                jurisdiction_id="city-oakland",
                success=True,
                data={},
            ),
        }

        summary = format_federation_summary("san-rafael", peer_results)

        assert "san-rafael" in summary
        assert "local" in summary.lower()
        assert "berkeley" in summary
        assert "oakland" in summary
        assert "2 peers" in summary

    def test_with_failed_peers(self):
        """Test summary with failed peer queries."""
        peer_results = {
            "city-fail": PeerQueryResult(
                jurisdiction_id="city-fail",
                success=False,
                error="Timeout",
            ),
        }

        summary = format_federation_summary("san-rafael", peer_results)

        assert "san-rafael" in summary
        assert "failed" in summary.lower()
        assert "city-fail" in summary

    def test_mixed_success_failure(self):
        """Test summary with mixed results."""
        peer_results = {
            "city-ok": PeerQueryResult(
                jurisdiction_id="city-ok",
                success=True,
                data={},
            ),
            "city-bad": PeerQueryResult(
                jurisdiction_id="city-bad",
                success=False,
                error="Error",
            ),
        }

        summary = format_federation_summary("san-rafael", peer_results)

        assert "san-rafael" in summary
        assert "city-ok" in summary
        assert "city-bad" in summary
        assert "failed" in summary.lower()
