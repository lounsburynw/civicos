"""
Tests for Nostr cryptographic operations.

Verifies:
- Key generation and serialization
- Event ID calculation (NIP-01)
- Schnorr signing and verification (BIP-340)
- Cross-compatibility with known test vectors
"""

import json
import pytest
from civicos_relay.nostr.crypto import (
    NostrKeyPair,
    compute_event_id,
    sign_event,
    verify_event_signature,
    verify_event_id,
    verify_event,
    serialize_event_for_id,
)


class TestNostrKeyPair:
    """Tests for NostrKeyPair generation and operations."""

    def test_generate_creates_valid_keypair(self):
        """Generated keypairs have correct format."""
        kp = NostrKeyPair.generate()

        # Private key is 32 bytes (64 hex chars)
        assert len(kp.secret_hex) == 64
        assert all(c in "0123456789abcdef" for c in kp.secret_hex)

        # Public key is 32 bytes (64 hex chars) - x-only format
        assert len(kp.public_key_hex) == 64
        assert all(c in "0123456789abcdef" for c in kp.public_key_hex)

    def test_generate_unique_keys(self):
        """Each generation produces unique keys."""
        kp1 = NostrKeyPair.generate()
        kp2 = NostrKeyPair.generate()

        assert kp1.secret_hex != kp2.secret_hex
        assert kp1.public_key_hex != kp2.public_key_hex

    def test_from_hex_roundtrip(self):
        """Can import/export via hex."""
        kp1 = NostrKeyPair.generate()
        secret = kp1.secret_hex

        kp2 = NostrKeyPair.from_hex(secret)
        assert kp2.secret_hex == secret
        assert kp2.public_key_hex == kp1.public_key_hex

    def test_from_hex_known_value(self):
        """Import from known hex value produces expected pubkey."""
        # Known test vector - this secret produces a specific pubkey
        secret = "0000000000000000000000000000000000000000000000000000000000000001"
        kp = NostrKeyPair.from_hex(secret)

        # secp256k1 generator point G's x-coordinate
        expected_pubkey = "79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
        assert kp.public_key_hex == expected_pubkey

    def test_from_hex_invalid_length(self):
        """Rejects invalid hex length."""
        with pytest.raises(ValueError, match="32 bytes"):
            NostrKeyPair.from_hex("abcd")

    def test_from_nsec_not_implemented(self):
        """nsec import raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            NostrKeyPair.from_nsec("nsec1...")


class TestEventIdCalculation:
    """Tests for NIP-01 event ID calculation."""

    def test_serialize_event_format(self):
        """Serialization matches NIP-01 format."""
        pubkey = "a" * 64
        created_at = 1234567890
        kind = 1
        tags = [["p", "b" * 64], ["e", "c" * 64]]
        content = "Hello, Nostr!"

        serialized = serialize_event_for_id(pubkey, created_at, kind, tags, content)

        # Should be valid JSON array starting with 0
        parsed = json.loads(serialized)
        assert parsed[0] == 0
        assert parsed[1] == pubkey
        assert parsed[2] == created_at
        assert parsed[3] == kind
        assert parsed[4] == tags
        assert parsed[5] == content

    def test_serialize_no_whitespace(self):
        """Serialization has no extra whitespace (NIP-01 requirement)."""
        serialized = serialize_event_for_id("a" * 64, 1000, 1, [], "test")
        assert " " not in serialized

    def test_compute_event_id_deterministic(self):
        """Same inputs produce same event ID."""
        args = ("a" * 64, 1234567890, 1, [["t", "test"]], "Hello")

        id1 = compute_event_id(*args)
        id2 = compute_event_id(*args)

        assert id1 == id2
        assert len(id1) == 64  # SHA256 = 32 bytes = 64 hex chars

    def test_compute_event_id_changes_with_input(self):
        """Different inputs produce different IDs."""
        base_args = ("a" * 64, 1234567890, 1, [], "Hello")

        id1 = compute_event_id(*base_args)
        id2 = compute_event_id("b" * 64, 1234567890, 1, [], "Hello")  # Different pubkey
        id3 = compute_event_id("a" * 64, 1234567891, 1, [], "Hello")  # Different time
        id4 = compute_event_id("a" * 64, 1234567890, 2, [], "Hello")  # Different kind
        id5 = compute_event_id("a" * 64, 1234567890, 1, [["t", "x"]], "Hello")  # Different tags
        id6 = compute_event_id("a" * 64, 1234567890, 1, [], "World")  # Different content

        assert len({id1, id2, id3, id4, id5, id6}) == 6  # All unique

    def test_verify_event_id_success(self):
        """verify_event_id returns True for matching ID."""
        pubkey = "a" * 64
        created_at = 1234567890
        kind = 1
        tags = [["t", "test"]]
        content = "Hello"

        event_id = compute_event_id(pubkey, created_at, kind, tags, content)
        assert verify_event_id(event_id, pubkey, created_at, kind, tags, content)

    def test_verify_event_id_failure(self):
        """verify_event_id returns False for tampered data."""
        pubkey = "a" * 64
        created_at = 1234567890
        kind = 1
        tags = [["t", "test"]]
        content = "Hello"

        event_id = compute_event_id(pubkey, created_at, kind, tags, content)

        # Tamper with content
        assert not verify_event_id(event_id, pubkey, created_at, kind, tags, "Tampered")


class TestSchnorrSigning:
    """Tests for BIP-340 Schnorr signature operations."""

    def test_sign_and_verify_roundtrip(self):
        """Can sign and verify our own signatures."""
        kp = NostrKeyPair.generate()
        created_at = 1234567890
        kind = 1
        tags = [["t", "civic"]]
        content = "My civic voice"

        event_id, pubkey, sig = sign_event(kp, created_at, kind, tags, content)

        assert pubkey == kp.public_key_hex
        assert len(event_id) == 64
        assert len(sig) == 128  # 64-byte Schnorr signature

        # Verify the signature
        assert verify_event_signature(event_id, pubkey, sig)

    def test_signature_invalid_for_different_message(self):
        """Signature doesn't verify for different event ID."""
        kp = NostrKeyPair.generate()

        event_id1, _, sig = sign_event(kp, 1000, 1, [], "Message 1")
        event_id2 = compute_event_id(kp.public_key_hex, 1000, 1, [], "Message 2")

        # Signature for event_id1 shouldn't verify for event_id2
        assert not verify_event_signature(event_id2, kp.public_key_hex, sig)

    def test_signature_invalid_for_different_key(self):
        """Signature doesn't verify with wrong public key."""
        kp1 = NostrKeyPair.generate()
        kp2 = NostrKeyPair.generate()

        event_id, _, sig = sign_event(kp1, 1000, 1, [], "Hello")

        # Verify with wrong pubkey fails
        assert not verify_event_signature(event_id, kp2.public_key_hex, sig)

    def test_verify_signature_rejects_invalid_lengths(self):
        """verify_event_signature rejects malformed inputs."""
        assert not verify_event_signature("short", "a" * 64, "b" * 128)
        assert not verify_event_signature("a" * 64, "short", "b" * 128)
        assert not verify_event_signature("a" * 64, "b" * 64, "short")

    def test_verify_signature_handles_exceptions(self):
        """verify_event_signature returns False on crypto errors."""
        # Invalid hex
        assert not verify_event_signature("g" * 64, "a" * 64, "b" * 128)


class TestFullEventVerification:
    """Tests for complete event verification."""

    def test_verify_event_success(self):
        """verify_event returns True for valid event."""
        kp = NostrKeyPair.generate()
        created_at = 1234567890
        kind = 30800  # Civic voice kind
        tags = [["d", "entity:id"], ["j", "city-san-rafael"], ["stance", "support"]]
        content = ""

        event_id, pubkey, sig = sign_event(kp, created_at, kind, tags, content)

        assert verify_event(event_id, pubkey, created_at, kind, tags, content, sig)

    def test_verify_event_fails_bad_id(self):
        """verify_event returns False for wrong event ID."""
        kp = NostrKeyPair.generate()
        created_at = 1234567890
        kind = 1
        tags = []
        content = "Hello"

        _, pubkey, sig = sign_event(kp, created_at, kind, tags, content)
        fake_id = "0" * 64

        assert not verify_event(fake_id, pubkey, created_at, kind, tags, content, sig)

    def test_verify_event_fails_bad_sig(self):
        """verify_event returns False for wrong signature."""
        kp = NostrKeyPair.generate()
        created_at = 1234567890
        kind = 1
        tags = []
        content = "Hello"

        event_id, pubkey, _ = sign_event(kp, created_at, kind, tags, content)
        fake_sig = "0" * 128

        assert not verify_event(event_id, pubkey, created_at, kind, tags, content, fake_sig)

    def test_verify_event_fails_tampered_content(self):
        """verify_event returns False if content was tampered."""
        kp = NostrKeyPair.generate()
        created_at = 1234567890
        kind = 1
        tags = []
        content = "Original"

        event_id, pubkey, sig = sign_event(kp, created_at, kind, tags, content)

        # Try to verify with tampered content
        assert not verify_event(event_id, pubkey, created_at, kind, tags, "Tampered", sig)


class TestCivicEventScenarios:
    """Tests simulating real civic coordination use cases."""

    def test_civic_voice_event(self):
        """Create and verify a civic voice event."""
        kp = NostrKeyPair.generate()
        created_at = 1738464000  # 2025-02-02

        # Kind 30800: Civic Voice (addressable)
        kind = 30800
        tags = [
            ["d", "decision:city-san-rafael:2026-02-03:item-6a"],
            ["j", "city-san-rafael"],
            ["stance", "support"],
            ["t", "housing"],
        ]
        content = ""  # Voice content is optional

        event_id, pubkey, sig = sign_event(kp, created_at, kind, tags, content)

        # Verify the complete event
        assert verify_event(event_id, pubkey, created_at, kind, tags, content, sig)

        # Check tag extraction would work
        d_tag = next((t[1] for t in tags if t[0] == "d"), None)
        assert d_tag == "decision:city-san-rafael:2026-02-03:item-6a"

        stance = next((t[1] for t in tags if t[0] == "stance"), None)
        assert stance == "support"

    def test_civic_entity_event(self):
        """Create and verify a civic entity event."""
        jurisdiction_key = NostrKeyPair.generate()
        created_at = 1738464000

        # Kind 30801: Civic Entity
        kind = 30801
        tags = [
            ["d", "decision:city-san-rafael:2026-02-03:item-6a"],
            ["j", "city-san-rafael"],
            ["type", "decision"],
            ["title", "4th Street Rezoning"],
            ["t", "housing"],
            ["t", "zoning"],
        ]
        content = json.dumps({
            "description": "Proposal to rezone 4th Street for mixed-use development",
            "outcome": "pending",
        })

        event_id, pubkey, sig = sign_event(jurisdiction_key, created_at, kind, tags, content)
        assert verify_event(event_id, pubkey, created_at, kind, tags, content, sig)

    def test_key_link_attestation(self):
        """Simulate kind 1802 key link attestation."""
        new_key = NostrKeyPair.generate()
        old_key_hex = "c" * 64  # Simulated old SECP256R1 pubkey

        created_at = 1738464000

        # Kind 1802: Key Link Attestation
        kind = 1802
        tags = [
            ["old-key", old_key_hex],
            ["old-sig", "d" * 128],  # Simulated ECDSA signature
        ]
        content = "Key migration attestation: I control both keys"

        event_id, pubkey, sig = sign_event(new_key, created_at, kind, tags, content)

        # New key signs the Nostr event normally
        assert verify_event(event_id, pubkey, created_at, kind, tags, content, sig)
        assert pubkey == new_key.public_key_hex


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_content(self):
        """Events with empty content work correctly."""
        kp = NostrKeyPair.generate()
        event_id, _, sig = sign_event(kp, 1000, 1, [], "")
        assert verify_event(event_id, kp.public_key_hex, 1000, 1, [], "", sig)

    def test_unicode_content(self):
        """Unicode content is handled correctly."""
        kp = NostrKeyPair.generate()
        content = "Hello 世界 🌍 émojis"
        event_id, _, sig = sign_event(kp, 1000, 1, [], content)
        assert verify_event(event_id, kp.public_key_hex, 1000, 1, [], content, sig)

    def test_special_characters_in_tags(self):
        """Special characters in tags work correctly."""
        kp = NostrKeyPair.generate()
        tags = [["d", "entity:with:colons:and/slashes"]]
        event_id, _, sig = sign_event(kp, 1000, 30800, tags, "")
        assert verify_event(event_id, kp.public_key_hex, 1000, 30800, tags, "", sig)

    def test_large_tag_list(self):
        """Many tags are handled correctly."""
        kp = NostrKeyPair.generate()
        tags = [["t", f"tag{i}"] for i in range(100)]
        event_id, _, sig = sign_event(kp, 1000, 1, tags, "")
        assert verify_event(event_id, kp.public_key_hex, 1000, 1, tags, "", sig)

    def test_zero_timestamp(self):
        """Zero timestamp works (epoch time)."""
        kp = NostrKeyPair.generate()
        event_id, _, sig = sign_event(kp, 0, 1, [], "Genesis")
        assert verify_event(event_id, kp.public_key_hex, 0, 1, [], "Genesis", sig)
