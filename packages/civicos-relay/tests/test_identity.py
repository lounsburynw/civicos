"""Tests for relay identity module."""

import pytest
import tempfile
from pathlib import Path

from civicos_relay.identity import RelayIdentity, RelayConfig, PeerConfig


class TestRelayIdentity:
    """Tests for relay identity and signing."""

    def test_generate_identity(self):
        """Can generate a new relay identity."""
        identity = RelayIdentity.generate("relay.test.org/test")
        assert identity.relay_id == "relay.test.org/test"
        # Verify keys form a valid signing pair (not just existence)
        sig = identity.sign(b"keygen-check")
        assert RelayIdentity.verify(b"keygen-check", sig, identity.public_key_hex)

    def test_public_key_hex(self):
        """Public key can be serialized to hex."""
        identity = RelayIdentity.generate("relay.test.org/test")
        hex_key = identity.public_key_hex
        # Compressed SECP256R1 key: 1-byte prefix (02/03) + 32-byte x-coord = 66 hex chars
        assert len(hex_key) == 66
        assert hex_key[:2] in ("02", "03")
        bytes.fromhex(hex_key)  # Validates it's valid hex

    def test_sign_and_verify(self):
        """Can sign and verify messages."""
        identity = RelayIdentity.generate("relay.test.org/test")
        message = b"test message"
        signature = identity.sign(message)

        assert RelayIdentity.verify(message, signature, identity.public_key_hex)

    def test_verify_tampered_message(self):
        """Tampered message fails verification."""
        identity = RelayIdentity.generate("relay.test.org/test")
        message = b"test message"
        signature = identity.sign(message)

        tampered = b"tampered message"
        assert not RelayIdentity.verify(tampered, signature, identity.public_key_hex)

    def test_save_and_load(self):
        """Can save and load identity from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "relay.key"

            # Generate and save
            identity1 = RelayIdentity.generate("relay.test.org/test")
            identity1.save(str(key_path))

            # Load
            identity2 = RelayIdentity.load("relay.test.org/test", str(key_path))

            # Should have same public key
            assert identity1.public_key_hex == identity2.public_key_hex

    def test_load_or_generate_creates_new(self):
        """load_or_generate creates new identity if file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = Path(tmpdir) / "relay.key"

            identity = RelayIdentity.load_or_generate(
                "relay.test.org/test", str(key_path)
            )

            assert identity.relay_id == "relay.test.org/test"
            assert key_path.exists()


class TestRelayConfig:
    """Tests for relay configuration."""

    def test_peer_config(self):
        """Can create peer config."""
        peer = PeerConfig(
            url="https://relay.example.org",
            namespaces=["city-san-rafael:*"],
            sync_interval=300,
        )
        assert peer.url == "https://relay.example.org"
        assert peer.namespaces == ["city-san-rafael:*"]
        assert peer.sync_interval == 300
        assert peer.enabled is True

    def test_relay_config(self):
        """Can create relay config."""
        config = RelayConfig(
            relay_id="relay.test.org/test",
            namespaces=["city-san-rafael:*"],
            peers=[
                PeerConfig(
                    url="https://peer.example.org",
                    namespaces=["county-marin:*"],
                )
            ],
        )
        assert config.relay_id == "relay.test.org/test"
        assert config.namespaces == ["city-san-rafael:*"]
        assert len(config.peers) == 1
        assert config.peers[0].url == "https://peer.example.org"
        assert config.peers[0].namespaces == ["county-marin:*"]
