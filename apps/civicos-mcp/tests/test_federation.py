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
from unittest.mock import AsyncMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from federation import (
    PeerInfo,
    PeerRegistry,
    HttpHealthChecker,
    init_registry,
    shutdown_registry,
    get_registry,
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
