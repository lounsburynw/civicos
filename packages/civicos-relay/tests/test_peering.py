"""Tests for peer configuration and health checking."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from civicos_relay import RelayIdentity
from civicos_relay.identity import PeerConfig, RelayConfig
from civicos_relay.sync import SyncService
from civicos_relay.storage import InMemoryStorage
from civicos_relay.storage.memory import InMemoryPeerHealthStorage


class TestPeerConfig:
    """Tests for PeerConfig model."""

    def test_peer_config_defaults(self):
        """PeerConfig has sensible defaults."""
        peer = PeerConfig(url="https://relay.example.org", namespaces=["*"])

        assert peer.url == "https://relay.example.org"
        assert peer.namespaces == ["*"]
        assert peer.sync_interval == 300
        assert peer.enabled is True
        assert peer.healthy is True
        assert peer.consecutive_failures == 0
        assert peer.last_health_check is None
        assert peer.last_successful_sync is None

    def test_peer_config_with_health_state(self):
        """PeerConfig can be created with health state."""
        now = datetime.utcnow()
        peer = PeerConfig(
            url="https://relay.example.org",
            namespaces=["city-san-rafael:*"],
            healthy=False,
            consecutive_failures=3,
            last_health_check=now,
        )

        assert peer.healthy is False
        assert peer.consecutive_failures == 3
        assert peer.last_health_check == now


class TestRelayConfig:
    """Tests for RelayConfig model."""

    def test_relay_config_health_settings(self):
        """RelayConfig includes health check settings."""
        config = RelayConfig(
            relay_id="relay.test.org/local",
            health_check_timeout=15,
            health_check_interval=120,
            max_consecutive_failures=5,
        )

        assert config.health_check_timeout == 15
        assert config.health_check_interval == 120
        assert config.max_consecutive_failures == 5

    def test_relay_config_health_defaults(self):
        """RelayConfig has default health settings."""
        config = RelayConfig(relay_id="relay.test.org/local")

        assert config.health_check_timeout == 10
        assert config.health_check_interval == 60
        assert config.max_consecutive_failures == 3

    def test_relay_config_from_yaml(self, tmp_path):
        """RelayConfig can load from YAML with peers."""
        yaml_content = """
relay:
  relay_id: relay.marin.org/san-rafael
  namespaces:
    - city-san-rafael:*
  peers:
    - url: https://relay.civicos.org
      namespaces:
        - "city-*"
      sync_interval: 600
    - url: https://peer.example.org
      namespaces:
        - county-marin:*
      enabled: false
  health_check_timeout: 15
  max_consecutive_failures: 5
"""
        yaml_file = tmp_path / "relay_config.yaml"
        yaml_file.write_text(yaml_content)

        config = RelayConfig.from_yaml(str(yaml_file))

        assert config.relay_id == "relay.marin.org/san-rafael"
        assert config.namespaces == ["city-san-rafael:*"]
        assert len(config.peers) == 2
        assert config.peers[0].url == "https://relay.civicos.org"
        assert config.peers[0].sync_interval == 600
        assert config.peers[1].enabled is False
        assert config.health_check_timeout == 15
        assert config.max_consecutive_failures == 5


class TestPeerHealthCheck:
    """Tests for peer health checking in SyncService."""

    @pytest.fixture
    def sync_service(self):
        """Create a SyncService with mock peers."""
        storage = InMemoryStorage()
        identity = RelayIdentity.generate("relay.test.org/local")
        peers = [
            PeerConfig(url="https://peer1.example.org", namespaces=["*"]),
            PeerConfig(url="https://peer2.example.org", namespaces=["*"]),
        ]
        return SyncService(
            identity, storage.sync, peers, max_consecutive_failures=3
        )

    @pytest.mark.asyncio
    async def test_health_check_success(self, sync_service):
        """Successful health check marks peer healthy."""
        peer = sync_service._peers["https://peer1.example.org"]

        with patch.object(sync_service._health_client, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"status": "healthy", "relay_id": "peer1"}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await sync_service.check_peer_health(peer)

        assert result is True
        assert peer.healthy is True
        assert peer.consecutive_failures == 0
        assert peer.last_health_check is not None

    @pytest.mark.asyncio
    async def test_health_check_failure_increments_count(self, sync_service):
        """Failed health check increments failure count."""
        peer = sync_service._peers["https://peer1.example.org"]

        with patch.object(sync_service._health_client, "get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection refused")

            result = await sync_service.check_peer_health(peer)

        assert result is False
        assert peer.consecutive_failures == 1
        assert peer.healthy is True  # Still healthy after 1 failure

    @pytest.mark.asyncio
    async def test_health_check_marks_unhealthy_after_threshold(self, sync_service):
        """Peer marked unhealthy after max_consecutive_failures."""
        peer = sync_service._peers["https://peer1.example.org"]

        with patch.object(sync_service._health_client, "get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection refused")

            # Simulate 3 consecutive failures
            for _ in range(3):
                await sync_service.check_peer_health(peer)

        assert peer.consecutive_failures == 3
        assert peer.healthy is False

    @pytest.mark.asyncio
    async def test_health_check_recovery(self, sync_service):
        """Peer recovers after successful health check."""
        peer = sync_service._peers["https://peer1.example.org"]
        peer.healthy = False
        peer.consecutive_failures = 3

        with patch.object(sync_service._health_client, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"status": "healthy"}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await sync_service.check_peer_health(peer)

        assert result is True
        assert peer.healthy is True
        assert peer.consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_check_all_peers_health(self, sync_service):
        """Can check health of all peers."""
        with patch.object(sync_service._health_client, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"status": "healthy"}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            results = await sync_service.check_all_peers_health()

        assert len(results) == 2
        assert results["https://peer1.example.org"] is True
        assert results["https://peer2.example.org"] is True

    def test_get_healthy_peers(self, sync_service):
        """Can filter to healthy peers only."""
        sync_service._peers["https://peer1.example.org"].healthy = False

        healthy = sync_service.get_healthy_peers()

        assert len(healthy) == 1
        assert healthy[0].url == "https://peer2.example.org"

    def test_get_unhealthy_peers(self, sync_service):
        """Can filter to unhealthy peers."""
        sync_service._peers["https://peer1.example.org"].healthy = False

        unhealthy = sync_service.get_unhealthy_peers()

        assert len(unhealthy) == 1
        assert unhealthy[0].url == "https://peer1.example.org"

    def test_reset_peer_health(self, sync_service):
        """Can manually reset peer health."""
        peer = sync_service._peers["https://peer1.example.org"]
        peer.healthy = False
        peer.consecutive_failures = 5

        result = sync_service.reset_peer_health("https://peer1.example.org")

        assert result is True
        assert peer.healthy is True
        assert peer.consecutive_failures == 0

    def test_reset_peer_health_unknown_peer(self, sync_service):
        """Reset returns False for unknown peer."""
        result = sync_service.reset_peer_health("https://unknown.example.org")
        assert result is False


class TestSyncWithUnhealthyPeers:
    """Tests for sync behavior with unhealthy peers."""

    @pytest.fixture
    def sync_service(self):
        """Create a SyncService with one healthy, one unhealthy peer."""
        storage = InMemoryStorage()
        identity = RelayIdentity.generate("relay.test.org/local")
        peers = [
            PeerConfig(url="https://healthy.example.org", namespaces=["*"]),
            PeerConfig(
                url="https://unhealthy.example.org",
                namespaces=["*"],
                healthy=False,
                consecutive_failures=3,
            ),
        ]
        return SyncService(identity, storage.sync, peers)

    def test_list_peers_includes_all(self, sync_service):
        """list_peers returns all peers regardless of health."""
        peers = sync_service.list_peers()
        assert len(peers) == 2

    def test_healthy_peer_included(self, sync_service):
        """Healthy peer is in get_healthy_peers."""
        healthy = sync_service.get_healthy_peers()
        assert len(healthy) == 1
        assert healthy[0].url == "https://healthy.example.org"

    def test_unhealthy_peer_included(self, sync_service):
        """Unhealthy peer is in get_unhealthy_peers."""
        unhealthy = sync_service.get_unhealthy_peers()
        assert len(unhealthy) == 1
        assert unhealthy[0].url == "https://unhealthy.example.org"


class TestHealthCheckHttpStatus:
    """Tests for health check HTTP response handling."""

    @pytest.fixture
    def sync_service(self):
        """Create a SyncService with a single peer."""
        storage = InMemoryStorage()
        identity = RelayIdentity.generate("relay.test.org/local")
        peers = [PeerConfig(url="https://peer.example.org", namespaces=["*"])]
        return SyncService(identity, storage.sync, peers, max_consecutive_failures=3)

    @pytest.mark.asyncio
    async def test_health_check_http_500(self, sync_service):
        """HTTP 500 from health check is treated as failure."""
        peer = sync_service._peers["https://peer.example.org"]

        with patch.object(sync_service._health_client, "get") as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "Internal Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )

            result = await sync_service.check_peer_health(peer)

        assert result is False
        assert peer.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_health_check_timeout(self, sync_service):
        """Timeout during health check is treated as failure."""
        peer = sync_service._peers["https://peer.example.org"]

        with patch.object(sync_service._health_client, "get") as mock_get:
            mock_get.side_effect = httpx.ReadTimeout("Read timed out")

            result = await sync_service.check_peer_health(peer)

        assert result is False
        assert peer.consecutive_failures == 1

    @pytest.mark.asyncio
    async def test_health_check_non_healthy_status(self, sync_service):
        """Non-'healthy' status is treated as failure."""
        peer = sync_service._peers["https://peer.example.org"]

        with patch.object(sync_service._health_client, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"status": "degraded"}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            result = await sync_service.check_peer_health(peer)

        assert result is False
        assert peer.consecutive_failures == 1


class TestPeerHealthPersistence:
    """Tests for peer health state persistence."""

    def test_health_state_persists_across_service_restart(self):
        """Peer marked unhealthy stays unhealthy after new SyncService init."""
        health_storage = InMemoryPeerHealthStorage()
        identity = RelayIdentity.generate("relay.test.org/local")

        peers = [PeerConfig(url="https://peer1.example.org", namespaces=["*"])]

        # First service instance — mark peer unhealthy
        svc1 = SyncService(
            identity, InMemoryStorage().sync, peers,
            max_consecutive_failures=3,
            peer_health_storage=health_storage,
        )
        peer = svc1._peers["https://peer1.example.org"]
        peer.healthy = False
        peer.consecutive_failures = 3
        svc1._save_peer_health(peer)

        # Second service instance — loads from storage
        peers2 = [PeerConfig(url="https://peer1.example.org", namespaces=["*"])]
        svc2 = SyncService(
            identity, InMemoryStorage().sync, peers2,
            max_consecutive_failures=3,
            peer_health_storage=health_storage,
        )

        peer2 = svc2._peers["https://peer1.example.org"]
        assert peer2.healthy is False
        assert peer2.consecutive_failures == 3

    def test_healthy_peer_loads_as_healthy(self):
        """Peer with no prior failures loads as healthy."""
        health_storage = InMemoryPeerHealthStorage()
        identity = RelayIdentity.generate("relay.test.org/local")

        peers = [PeerConfig(url="https://peer1.example.org", namespaces=["*"])]
        svc = SyncService(
            identity, InMemoryStorage().sync, peers,
            peer_health_storage=health_storage,
        )

        peer = svc._peers["https://peer1.example.org"]
        assert peer.healthy is True
        assert peer.consecutive_failures == 0

    def test_save_health_on_failure(self):
        """Recording a failure persists to storage."""
        health_storage = InMemoryPeerHealthStorage()
        identity = RelayIdentity.generate("relay.test.org/local")

        peers = [PeerConfig(url="https://peer1.example.org", namespaces=["*"])]
        svc = SyncService(
            identity, InMemoryStorage().sync, peers,
            max_consecutive_failures=3,
            peer_health_storage=health_storage,
        )

        peer = svc._peers["https://peer1.example.org"]
        svc._record_peer_failure(peer)

        # Verify persisted
        saved = health_storage.load_peer_health("https://peer1.example.org")
        assert saved is not None
        assert saved["consecutive_failures"] == 1
        assert saved["healthy"] is True  # Only 1 failure, threshold is 3

    def test_health_persisted_after_threshold(self):
        """Health marked unhealthy after threshold and persisted."""
        health_storage = InMemoryPeerHealthStorage()
        identity = RelayIdentity.generate("relay.test.org/local")

        peers = [PeerConfig(url="https://peer1.example.org", namespaces=["*"])]
        svc = SyncService(
            identity, InMemoryStorage().sync, peers,
            max_consecutive_failures=3,
            peer_health_storage=health_storage,
        )

        peer = svc._peers["https://peer1.example.org"]
        for _ in range(3):
            svc._record_peer_failure(peer)

        saved = health_storage.load_peer_health("https://peer1.example.org")
        assert saved["healthy"] is False
        assert saved["consecutive_failures"] == 3

    def test_no_storage_does_not_error(self):
        """SyncService without peer_health_storage works normally."""
        identity = RelayIdentity.generate("relay.test.org/local")
        peers = [PeerConfig(url="https://peer1.example.org", namespaces=["*"])]
        svc = SyncService(identity, InMemoryStorage().sync, peers)

        # Should not raise
        peer = svc._peers["https://peer1.example.org"]
        svc._record_peer_failure(peer)
        svc._save_peer_health(peer)
        assert peer.consecutive_failures == 1
