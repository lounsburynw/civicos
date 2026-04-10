"""Tests for relay configuration models (identity/config.py)."""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from civicos_relay.identity.config import PeerConfig, RelayConfig


class TestPeerConfig:
    """Tests for PeerConfig model."""

    def test_required_fields_only(self):
        """PeerConfig with only required fields gets correct defaults."""
        peer = PeerConfig(url="https://peer.example.org", namespaces=["city-san-rafael:*"])
        assert peer.url == "https://peer.example.org"
        assert peer.namespaces == ["city-san-rafael:*"]
        assert peer.sync_interval == 300
        assert peer.public_key is None
        assert peer.enabled is True

    def test_health_tracking_defaults(self):
        """Health tracking fields initialize to healthy/no-history state."""
        peer = PeerConfig(url="https://peer.example.org", namespaces=["*"])
        assert peer.healthy is True
        assert peer.consecutive_failures == 0
        assert peer.last_health_check is None
        assert peer.last_successful_sync is None

    def test_custom_sync_interval(self):
        """Custom sync_interval overrides the 300s default."""
        peer = PeerConfig(url="https://peer.example.org", namespaces=["*"], sync_interval=60)
        assert peer.sync_interval == 60

    def test_disabled_peer(self):
        """Peer can be created in disabled state."""
        peer = PeerConfig(url="https://peer.example.org", namespaces=["*"], enabled=False)
        assert peer.enabled is False

    def test_public_key_set(self):
        """Public key can be set for signature verification."""
        peer = PeerConfig(
            url="https://peer.example.org",
            namespaces=["*"],
            public_key="abcdef1234567890",
        )
        assert peer.public_key == "abcdef1234567890"

    def test_multiple_namespaces(self):
        """Peer can sync multiple namespaces."""
        namespaces = ["city-san-rafael:*", "county-marin:*", "city-mill-valley:*"]
        peer = PeerConfig(url="https://peer.example.org", namespaces=namespaces)
        assert peer.namespaces == ["city-san-rafael:*", "county-marin:*", "city-mill-valley:*"]
        assert len(peer.namespaces) == 3

    def test_health_tracking_with_timestamps(self):
        """Health tracking fields accept datetime values."""
        now = datetime(2026, 4, 10, 12, 0, 0)
        peer = PeerConfig(
            url="https://peer.example.org",
            namespaces=["*"],
            healthy=False,
            consecutive_failures=3,
            last_health_check=now,
            last_successful_sync=datetime(2026, 4, 10, 11, 0, 0),
        )
        assert peer.healthy is False
        assert peer.consecutive_failures == 3
        assert peer.last_health_check == now
        assert peer.last_successful_sync == datetime(2026, 4, 10, 11, 0, 0)


class TestRelayConfig:
    """Tests for RelayConfig model."""

    def test_minimal_config(self):
        """RelayConfig with only relay_id gets correct defaults."""
        config = RelayConfig(relay_id="relay.local")
        assert config.relay_id == "relay.local"
        assert config.private_key_path is None
        assert config.namespaces == []
        assert config.peers == []
        assert config.host == "0.0.0.0"
        assert config.port == 8003
        assert config.database_url is None
        assert config.sync_enabled is True
        assert config.sync_batch_size == 100
        assert config.acceptance_policy_enabled is True
        assert config.jurisdiction_id is None

    def test_health_check_defaults(self):
        """Health check settings have correct defaults."""
        config = RelayConfig(relay_id="relay.local")
        assert config.health_check_timeout == 10
        assert config.health_check_interval == 60
        assert config.max_consecutive_failures == 3

    def test_full_config(self):
        """RelayConfig with all fields explicitly set."""
        peer = PeerConfig(url="https://peer.example.org", namespaces=["county-marin:*"])
        config = RelayConfig(
            relay_id="relay.civicos.org/san-rafael",
            private_key_path="/etc/relay/key.pem",
            namespaces=["city-san-rafael:*"],
            peers=[peer],
            host="127.0.0.1",
            port=9000,
            database_url="postgresql://localhost/relay",
            sync_enabled=False,
            sync_batch_size=50,
            acceptance_policy_enabled=False,
            jurisdiction_id="city-san-rafael",
            health_check_timeout=5,
            health_check_interval=30,
            max_consecutive_failures=5,
        )
        assert config.relay_id == "relay.civicos.org/san-rafael"
        assert config.private_key_path == "/etc/relay/key.pem"
        assert config.namespaces == ["city-san-rafael:*"]
        assert len(config.peers) == 1
        assert config.peers[0].url == "https://peer.example.org"
        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.database_url == "postgresql://localhost/relay"
        assert config.sync_enabled is False
        assert config.sync_batch_size == 50
        assert config.acceptance_policy_enabled is False
        assert config.jurisdiction_id == "city-san-rafael"
        assert config.health_check_timeout == 5
        assert config.health_check_interval == 30
        assert config.max_consecutive_failures == 5

    def test_namespaces_default_factory_isolation(self):
        """Each config gets its own namespaces list (not shared mutable default)."""
        config1 = RelayConfig(relay_id="relay1")
        config2 = RelayConfig(relay_id="relay2")
        config1.namespaces.append("city-san-rafael:*")
        assert config2.namespaces == []

    def test_peers_default_factory_isolation(self):
        """Each config gets its own peers list (not shared mutable default)."""
        config1 = RelayConfig(relay_id="relay1")
        config2 = RelayConfig(relay_id="relay2")
        config1.peers.append(PeerConfig(url="https://peer.example.org", namespaces=["*"]))
        assert config2.peers == []


class TestRelayConfigFromEnv:
    """Tests for RelayConfig.from_env() environment variable loading."""

    def test_defaults_when_no_env_vars(self):
        """from_env returns sensible defaults when no env vars are set."""
        with patch.dict(os.environ, {}, clear=True):
            config = RelayConfig.from_env()
        assert config.relay_id == "relay.local"
        assert config.private_key_path is None
        assert config.namespaces == ["*"]
        assert config.peers == []
        assert config.host == "0.0.0.0"
        assert config.port == 8003
        assert config.database_url is None
        assert config.sync_enabled is True
        assert config.acceptance_policy_enabled is True
        assert config.jurisdiction_id is None

    def test_relay_id_from_env(self):
        """RELAY_ID env var sets relay_id."""
        env = {"RELAY_ID": "relay.civicos.org/san-rafael"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.relay_id == "relay.civicos.org/san-rafael"

    def test_private_key_path_from_env(self):
        """RELAY_PRIVATE_KEY_PATH env var sets private_key_path."""
        env = {"RELAY_PRIVATE_KEY_PATH": "/etc/relay/key.pem"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.private_key_path == "/etc/relay/key.pem"

    def test_namespaces_single(self):
        """RELAY_NAMESPACES with a single namespace."""
        env = {"RELAY_NAMESPACES": "city-san-rafael:*"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.namespaces == ["city-san-rafael:*"]

    def test_namespaces_multiple(self):
        """RELAY_NAMESPACES splits comma-separated namespaces."""
        env = {"RELAY_NAMESPACES": "city-san-rafael:*,county-marin:*"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.namespaces == ["city-san-rafael:*", "county-marin:*"]

    def test_host_and_port(self):
        """RELAY_HOST and RELAY_PORT set server settings."""
        env = {"RELAY_HOST": "127.0.0.1", "RELAY_PORT": "9000"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.host == "127.0.0.1"
        assert config.port == 9000

    def test_database_url_from_env(self):
        """DATABASE_URL env var sets database_url."""
        env = {"DATABASE_URL": "postgresql://localhost/relay"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.database_url == "postgresql://localhost/relay"

    def test_sync_enabled_true(self):
        """RELAY_SYNC_ENABLED=true enables sync."""
        env = {"RELAY_SYNC_ENABLED": "true"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.sync_enabled is True

    def test_sync_enabled_false(self):
        """RELAY_SYNC_ENABLED=false disables sync."""
        env = {"RELAY_SYNC_ENABLED": "false"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.sync_enabled is False

    def test_sync_enabled_case_insensitive(self):
        """RELAY_SYNC_ENABLED parsing is case-insensitive."""
        env = {"RELAY_SYNC_ENABLED": "TRUE"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.sync_enabled is True

    def test_sync_enabled_non_true_is_false(self):
        """RELAY_SYNC_ENABLED with non-'true' value results in False."""
        env = {"RELAY_SYNC_ENABLED": "yes"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.sync_enabled is False

    def test_acceptance_policy_enabled_default(self):
        """Acceptance policy defaults to enabled."""
        with patch.dict(os.environ, {}, clear=True):
            config = RelayConfig.from_env()
        assert config.acceptance_policy_enabled is True

    def test_acceptance_policy_disabled(self):
        """RELAY_ACCEPTANCE_POLICY=false disables acceptance policy."""
        env = {"RELAY_ACCEPTANCE_POLICY": "false"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.acceptance_policy_enabled is False

    def test_jurisdiction_id_from_env(self):
        """RELAY_JURISDICTION env var sets jurisdiction_id."""
        env = {"RELAY_JURISDICTION": "city-san-rafael"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.jurisdiction_id == "city-san-rafael"

    def test_single_peer(self):
        """RELAY_PEERS with one URL creates one peer."""
        env = {"RELAY_PEERS": "https://peer1.example.org"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert len(config.peers) == 1
        assert config.peers[0].url == "https://peer1.example.org"
        assert config.peers[0].namespaces == ["*"]
        assert config.peers[0].sync_interval == 300

    def test_multiple_peers(self):
        """RELAY_PEERS with comma-separated URLs creates multiple peers."""
        env = {"RELAY_PEERS": "https://peer1.example.org,https://peer2.example.org"}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert len(config.peers) == 2
        assert config.peers[0].url == "https://peer1.example.org"
        assert config.peers[1].url == "https://peer2.example.org"

    def test_peers_with_whitespace(self):
        """RELAY_PEERS trims whitespace around URLs."""
        env = {"RELAY_PEERS": "  https://peer1.example.org , https://peer2.example.org  "}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert len(config.peers) == 2
        assert config.peers[0].url == "https://peer1.example.org"
        assert config.peers[1].url == "https://peer2.example.org"

    def test_peers_empty_string(self):
        """RELAY_PEERS empty string produces no peers."""
        env = {"RELAY_PEERS": ""}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.peers == []

    def test_peers_only_commas_and_whitespace(self):
        """RELAY_PEERS with only commas/whitespace produces no peers."""
        env = {"RELAY_PEERS": " , , "}
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.peers == []

    def test_peer_sync_interval_from_env(self):
        """RELAY_SYNC_INTERVAL sets sync_interval on peers."""
        env = {
            "RELAY_PEERS": "https://peer1.example.org",
            "RELAY_SYNC_INTERVAL": "120",
        }
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.peers[0].sync_interval == 120

    def test_full_env_config(self):
        """All env vars set together produce correct config."""
        env = {
            "RELAY_ID": "relay.civicos.org/test",
            "RELAY_PRIVATE_KEY_PATH": "/keys/relay.pem",
            "RELAY_NAMESPACES": "city-san-rafael:*,county-marin:*",
            "RELAY_PEERS": "https://peer1.example.org",
            "RELAY_SYNC_INTERVAL": "60",
            "RELAY_HOST": "0.0.0.0",
            "RELAY_PORT": "8080",
            "DATABASE_URL": "postgresql://db/relay",
            "RELAY_SYNC_ENABLED": "false",
            "RELAY_ACCEPTANCE_POLICY": "false",
            "RELAY_JURISDICTION": "city-san-rafael",
        }
        with patch.dict(os.environ, env, clear=True):
            config = RelayConfig.from_env()
        assert config.relay_id == "relay.civicos.org/test"
        assert config.private_key_path == "/keys/relay.pem"
        assert config.namespaces == ["city-san-rafael:*", "county-marin:*"]
        assert len(config.peers) == 1
        assert config.peers[0].sync_interval == 60
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.database_url == "postgresql://db/relay"
        assert config.sync_enabled is False
        assert config.acceptance_policy_enabled is False
        assert config.jurisdiction_id == "city-san-rafael"


class TestRelayConfigFromYaml:
    """Tests for RelayConfig.from_yaml() YAML file loading."""

    def test_minimal_yaml(self):
        """Load config from YAML with minimal fields."""
        data = {"relay_id": "relay.test.org"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            config = RelayConfig.from_yaml(f.name)
        os.unlink(f.name)
        assert config.relay_id == "relay.test.org"
        assert config.peers == []
        assert config.namespaces == []

    def test_full_yaml(self):
        """Load config from YAML with all fields."""
        data = {
            "relay_id": "relay.civicos.org/san-rafael",
            "private_key_path": "/keys/relay.pem",
            "namespaces": ["city-san-rafael:*"],
            "host": "127.0.0.1",
            "port": 9000,
            "database_url": "postgresql://localhost/relay",
            "sync_enabled": False,
            "sync_batch_size": 50,
            "acceptance_policy_enabled": False,
            "jurisdiction_id": "city-san-rafael",
            "health_check_timeout": 5,
            "health_check_interval": 30,
            "max_consecutive_failures": 5,
            "peers": [
                {
                    "url": "https://peer.example.org",
                    "namespaces": ["county-marin:*"],
                    "sync_interval": 120,
                }
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            config = RelayConfig.from_yaml(f.name)
        os.unlink(f.name)
        assert config.relay_id == "relay.civicos.org/san-rafael"
        assert config.private_key_path == "/keys/relay.pem"
        assert config.namespaces == ["city-san-rafael:*"]
        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.database_url == "postgresql://localhost/relay"
        assert config.sync_enabled is False
        assert config.sync_batch_size == 50
        assert config.acceptance_policy_enabled is False
        assert config.jurisdiction_id == "city-san-rafael"
        assert config.health_check_timeout == 5
        assert config.health_check_interval == 30
        assert config.max_consecutive_failures == 5
        assert len(config.peers) == 1
        assert config.peers[0].url == "https://peer.example.org"
        assert config.peers[0].namespaces == ["county-marin:*"]
        assert config.peers[0].sync_interval == 120

    def test_yaml_with_relay_wrapper(self):
        """YAML with a top-level 'relay' key unwraps correctly."""
        data = {
            "relay": {
                "relay_id": "relay.civicos.org/wrapped",
                "namespaces": ["city-san-rafael:*"],
                "port": 7000,
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            config = RelayConfig.from_yaml(f.name)
        os.unlink(f.name)
        assert config.relay_id == "relay.civicos.org/wrapped"
        assert config.namespaces == ["city-san-rafael:*"]
        assert config.port == 7000

    def test_yaml_without_relay_wrapper(self):
        """YAML without 'relay' key uses top-level dict directly."""
        data = {
            "relay_id": "relay.civicos.org/flat",
            "port": 8888,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            config = RelayConfig.from_yaml(f.name)
        os.unlink(f.name)
        assert config.relay_id == "relay.civicos.org/flat"
        assert config.port == 8888

    def test_yaml_file_not_found(self):
        """from_yaml raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            RelayConfig.from_yaml("/nonexistent/path/config.yaml")

    def test_yaml_with_peers(self):
        """YAML peers are parsed into PeerConfig objects."""
        data = {
            "relay_id": "relay.test.org",
            "peers": [
                {"url": "https://peer1.example.org", "namespaces": ["*"], "enabled": True},
                {"url": "https://peer2.example.org", "namespaces": ["city-mill-valley:*"], "enabled": False},
            ],
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(data, f)
            f.flush()
            config = RelayConfig.from_yaml(f.name)
        os.unlink(f.name)
        assert len(config.peers) == 2
        assert config.peers[0].url == "https://peer1.example.org"
        assert config.peers[0].enabled is True
        assert config.peers[1].url == "https://peer2.example.org"
        assert config.peers[1].namespaces == ["city-mill-valley:*"]
        assert config.peers[1].enabled is False
