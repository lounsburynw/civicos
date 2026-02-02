"""
Tests for key link attestation and migration.

Verifies:
- Old key signature verification (SECP256R1/ECDSA)
- Key link attestation validation
- Key link service operations
- Provenance aggregation across linked keys
"""

import pytest
from unittest.mock import MagicMock, patch

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from civicos_relay.nostr import (
    NostrKeyPair,
    KeyLinkAttestationEvent,
    KEY_LINK_ATTESTATION,
)
from civicos_relay.nostr.migration import (
    build_link_message,
    verify_old_key_signature,
    KeyLinkService,
    LinkedProvenanceService,
)
from civicos_relay.nostr.crypto import sign_event
from civicos_relay.nostr.models import NostrEvent


def generate_old_keypair():
    """Generate an old-style SECP256R1 keypair."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


def get_old_pubkey_hex(public_key: ec.EllipticCurvePublicKey) -> str:
    """Get compressed pubkey hex for old key."""
    return public_key.public_bytes(
        Encoding.X962, PublicFormat.CompressedPoint
    ).hex()


def sign_with_old_key(
    private_key: ec.EllipticCurvePrivateKey, message: str
) -> str:
    """Sign a message with old SECP256R1 key."""
    signature = private_key.sign(
        message.encode("utf-8"),
        ec.ECDSA(hashes.SHA256())
    )
    return signature.hex()


class TestBuildLinkMessage:
    """Tests for link message construction."""

    def test_build_link_message_format(self):
        """Message has correct format."""
        new_pubkey = "a" * 64
        message = build_link_message(new_pubkey)
        assert message == f"civicos:link:v1:{'a' * 64}"

    def test_build_link_message_deterministic(self):
        """Same input produces same message."""
        pubkey = "b" * 64
        assert build_link_message(pubkey) == build_link_message(pubkey)


class TestVerifyOldKeySignature:
    """Tests for SECP256R1 signature verification."""

    def test_verify_valid_signature(self):
        """Valid signature passes verification."""
        # Generate old keypair
        old_private, old_public = generate_old_keypair()
        old_pubkey_hex = get_old_pubkey_hex(old_public)

        # Generate new Nostr key
        new_key = NostrKeyPair.generate()
        new_pubkey_hex = new_key.public_key_hex

        # Sign the link message with old key
        message = build_link_message(new_pubkey_hex)
        signature_hex = sign_with_old_key(old_private, message)

        # Verify
        assert verify_old_key_signature(
            old_pubkey_hex, signature_hex, new_pubkey_hex
        )

    def test_verify_invalid_signature(self):
        """Invalid signature fails verification."""
        old_private, old_public = generate_old_keypair()
        old_pubkey_hex = get_old_pubkey_hex(old_public)
        new_key = NostrKeyPair.generate()

        # Sign wrong message
        wrong_signature = sign_with_old_key(old_private, "wrong message")

        assert not verify_old_key_signature(
            old_pubkey_hex, wrong_signature, new_key.public_key_hex
        )

    def test_verify_wrong_pubkey(self):
        """Signature with wrong pubkey fails."""
        old_private1, old_public1 = generate_old_keypair()
        old_private2, old_public2 = generate_old_keypair()

        new_key = NostrKeyPair.generate()
        message = build_link_message(new_key.public_key_hex)

        # Sign with key 1, verify with key 2
        signature = sign_with_old_key(old_private1, message)

        assert not verify_old_key_signature(
            get_old_pubkey_hex(old_public2),  # Wrong pubkey
            signature,
            new_key.public_key_hex
        )

    def test_verify_invalid_new_pubkey_length(self):
        """Rejects invalid new pubkey length."""
        old_private, old_public = generate_old_keypair()
        old_pubkey_hex = get_old_pubkey_hex(old_public)

        assert not verify_old_key_signature(
            old_pubkey_hex,
            "a" * 128,
            "short"  # Invalid length
        )

    def test_verify_invalid_old_pubkey_length(self):
        """Rejects invalid old pubkey length."""
        new_key = NostrKeyPair.generate()

        assert not verify_old_key_signature(
            "ab",  # Too short
            "c" * 128,
            new_key.public_key_hex
        )


class TestKeyLinkService:
    """Tests for KeyLinkService."""

    @pytest.fixture
    def mock_event_storage(self):
        storage = MagicMock()
        storage.save_event.return_value = (True, "accepted")
        return storage

    @pytest.fixture
    def mock_link_storage(self):
        storage = MagicMock()
        storage.get_linked_key.return_value = None
        storage.save_key_link.return_value = True
        return storage

    @pytest.fixture
    def service(self, mock_event_storage, mock_link_storage):
        return KeyLinkService(mock_event_storage, mock_link_storage)

    def test_validate_valid_attestation(self, service):
        """Valid attestation passes validation."""
        # Create keys
        old_private, old_public = generate_old_keypair()
        old_pubkey_hex = get_old_pubkey_hex(old_public)
        new_key = NostrKeyPair.generate()

        # Sign link message with old key
        message = build_link_message(new_key.public_key_hex)
        old_sig = sign_with_old_key(old_private, message)

        # Create attestation event
        tags = [["old-key", old_pubkey_hex], ["old-sig", old_sig]]
        content = "Key migration attestation"
        event_id, pubkey, sig = sign_event(
            new_key, 1000, KEY_LINK_ATTESTATION, tags, content
        )

        attestation = KeyLinkAttestationEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=KEY_LINK_ATTESTATION,
            tags=tags,
            content=content,
            sig=sig,
        )

        valid, message = service.validate_attestation(attestation)
        assert valid, message

    def test_validate_invalid_nostr_signature(self, service):
        """Attestation with invalid Nostr signature fails."""
        old_private, old_public = generate_old_keypair()
        old_pubkey_hex = get_old_pubkey_hex(old_public)
        new_key = NostrKeyPair.generate()

        message = build_link_message(new_key.public_key_hex)
        old_sig = sign_with_old_key(old_private, message)

        tags = [["old-key", old_pubkey_hex], ["old-sig", old_sig]]
        event_id, pubkey, sig = sign_event(
            new_key, 1000, KEY_LINK_ATTESTATION, tags, "original"
        )

        # Tamper with content
        attestation = KeyLinkAttestationEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=KEY_LINK_ATTESTATION,
            tags=tags,
            content="tampered",  # Different content
            sig=sig,
        )

        valid, msg = service.validate_attestation(attestation)
        assert not valid
        assert "Invalid Nostr event signature" in msg

    def test_validate_invalid_old_key_signature(self, service):
        """Attestation with invalid old key signature fails."""
        old_private, old_public = generate_old_keypair()
        old_pubkey_hex = get_old_pubkey_hex(old_public)
        new_key = NostrKeyPair.generate()

        # Wrong signature (doesn't match message)
        wrong_sig = sign_with_old_key(old_private, "wrong message")

        tags = [["old-key", old_pubkey_hex], ["old-sig", wrong_sig]]
        content = "Key migration"
        event_id, pubkey, sig = sign_event(
            new_key, 1000, KEY_LINK_ATTESTATION, tags, content
        )

        attestation = KeyLinkAttestationEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=KEY_LINK_ATTESTATION,
            tags=tags,
            content=content,
            sig=sig,
        )

        valid, msg = service.validate_attestation(attestation)
        assert not valid
        assert "Invalid old key signature" in msg

    def test_validate_already_linked(self, service, mock_link_storage):
        """Attestation fails if old key already linked."""
        # Set up mock to return existing link
        mock_link_storage.get_linked_key.return_value = "other_key_hex"

        old_private, old_public = generate_old_keypair()
        old_pubkey_hex = get_old_pubkey_hex(old_public)
        new_key = NostrKeyPair.generate()

        message = build_link_message(new_key.public_key_hex)
        old_sig = sign_with_old_key(old_private, message)

        tags = [["old-key", old_pubkey_hex], ["old-sig", old_sig]]
        content = "Key migration"
        event_id, pubkey, sig = sign_event(
            new_key, 1000, KEY_LINK_ATTESTATION, tags, content
        )

        attestation = KeyLinkAttestationEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=KEY_LINK_ATTESTATION,
            tags=tags,
            content=content,
            sig=sig,
        )

        valid, msg = service.validate_attestation(attestation)
        assert not valid
        assert "already linked" in msg

    def test_process_attestation_success(
        self, service, mock_event_storage, mock_link_storage
    ):
        """Process stores event and creates link."""
        old_private, old_public = generate_old_keypair()
        old_pubkey_hex = get_old_pubkey_hex(old_public)
        new_key = NostrKeyPair.generate()

        message = build_link_message(new_key.public_key_hex)
        old_sig = sign_with_old_key(old_private, message)

        tags = [["old-key", old_pubkey_hex], ["old-sig", old_sig]]
        content = "Key migration"
        event_id, pubkey, sig = sign_event(
            new_key, 1000, KEY_LINK_ATTESTATION, tags, content
        )

        attestation = KeyLinkAttestationEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=KEY_LINK_ATTESTATION,
            tags=tags,
            content=content,
            sig=sig,
        )

        success, msg = service.process_attestation(attestation)
        assert success
        assert "successfully" in msg

        # Verify storage was called
        mock_event_storage.save_event.assert_called_once()
        mock_link_storage.save_key_link.assert_called_once_with(
            old_pubkey_hex, pubkey, event_id
        )


class TestLinkedProvenanceService:
    """Tests for LinkedProvenanceService."""

    @pytest.fixture
    def mock_link_storage(self):
        storage = MagicMock()
        storage.get_old_keys.return_value = []
        return storage

    @pytest.fixture
    def service(self, mock_link_storage):
        return LinkedProvenanceService(mock_link_storage)

    def test_get_all_keys_no_links(self, service, mock_link_storage):
        """With no links, returns just the Nostr key."""
        mock_link_storage.get_old_keys.return_value = []

        keys = service.get_all_keys_for_identity("nostr_pubkey")
        assert keys == ["nostr_pubkey"]

    def test_get_all_keys_with_links(self, service, mock_link_storage):
        """With links, returns Nostr key plus old keys."""
        mock_link_storage.get_old_keys.return_value = ["old_key_1", "old_key_2"]

        keys = service.get_all_keys_for_identity("nostr_pubkey")
        assert keys == ["nostr_pubkey", "old_key_1", "old_key_2"]

    def test_aggregated_provenance_no_legacy(self, service, mock_link_storage):
        """Without legacy storage, returns basic info."""
        mock_link_storage.get_old_keys.return_value = ["old_key"]

        result = service.get_aggregated_provenance("nostr_pubkey")

        assert result["nostr_key"] == "nostr_pubkey"
        assert result["linked_old_keys"] == ["old_key"]


class TestEndToEndMigration:
    """End-to-end tests for the full migration flow."""

    def test_full_migration_flow(self):
        """Complete flow from key generation to attestation."""
        # Step 1: Generate old key (simulating existing CivicOS user)
        old_private, old_public = generate_old_keypair()
        old_pubkey_hex = get_old_pubkey_hex(old_public)

        # Step 2: Generate new Nostr key
        new_key = NostrKeyPair.generate()

        # Step 3: Old key signs link message
        link_message = build_link_message(new_key.public_key_hex)
        old_signature = sign_with_old_key(old_private, link_message)

        # Step 4: Create and sign attestation event
        tags = [
            ["old-key", old_pubkey_hex],
            ["old-sig", old_signature],
        ]
        content = "Key migration attestation: I control both keys"

        event_id, pubkey, sig = sign_event(
            new_key, 1000, KEY_LINK_ATTESTATION, tags, content
        )

        attestation = KeyLinkAttestationEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=KEY_LINK_ATTESTATION,
            tags=tags,
            content=content,
            sig=sig,
        )

        # Step 5: Verify both signatures are valid
        # Nostr signature (handled by model)
        assert attestation.verify(), "Nostr signature should be valid"

        # Old key signature
        assert verify_old_key_signature(
            old_pubkey_hex,
            old_signature,
            new_key.public_key_hex
        ), "Old key signature should be valid"

        # Step 6: Validate via service (mocked storage)
        mock_events = MagicMock()
        mock_events.save_event.return_value = (True, "accepted")
        mock_links = MagicMock()
        mock_links.get_linked_key.return_value = None
        mock_links.save_key_link.return_value = True

        service = KeyLinkService(mock_events, mock_links)
        success, msg = service.process_attestation(attestation)

        assert success, f"Migration should succeed: {msg}"
