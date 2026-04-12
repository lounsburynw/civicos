"""Tests for voice module."""

import pytest
from datetime import datetime, timedelta

from civicos_relay.voice.models import Voice, Stance, VoiceCount
from civicos_relay.voice.crypto import (
    KeyPair,
    _schnorr_verify,
    sign_voice,
    verify_voice,
    sign_attestation_event,
    verify_attestation_proof,
)


class TestKeyPair:
    """Tests for keypair generation."""

    def test_generate_keypair(self):
        """Can generate a new keypair."""
        kp = KeyPair.generate()
        assert len(kp.private_key_hex) == 64  # 32-byte key = 64 hex chars
        assert len(kp.public_key_hex) == 64

    def test_public_key_hex(self):
        """Public key is a 32-byte x-only secp256k1 key (64 hex chars)."""
        kp = KeyPair.generate()
        hex_key = kp.public_key_hex
        assert isinstance(hex_key, str)
        assert len(hex_key) == 64

    def test_keypairs_are_unique(self):
        """Each generated keypair is unique."""
        kp1 = KeyPair.generate()
        kp2 = KeyPair.generate()
        assert kp1.public_key_hex != kp2.public_key_hex


class TestVoiceSigning:
    """Tests for voice signing and verification."""

    def test_sign_voice(self):
        """Can sign a voice."""
        kp = KeyPair.generate()
        voice = sign_voice(kp, "agenda:2026-02-03:item-6a", Stance.SUPPORT)

        assert voice.entity == "agenda:2026-02-03:item-6a"
        assert voice.stance == Stance.SUPPORT
        assert voice.public_key == kp.public_key_hex
        assert len(voice.signature) == 128  # 64-byte Schnorr sig = 128 hex chars

    def test_verify_voice_valid(self):
        """Valid voice signature verifies."""
        kp = KeyPair.generate()
        voice = sign_voice(kp, "agenda:2026-02-03:item-6a", Stance.SUPPORT)

        assert verify_voice(voice) is True

    def test_verify_voice_tampered_entity(self):
        """Tampered entity fails verification."""
        kp = KeyPair.generate()
        voice = sign_voice(kp, "agenda:2026-02-03:item-6a", Stance.SUPPORT)

        # Tamper with entity — signature won't match new event ID
        tampered = Voice(
            entity="agenda:2026-02-03:item-6b",  # Changed
            stance=voice.stance,
            public_key=voice.public_key,
            signature=voice.signature,
            timestamp=voice.timestamp,
            created_at=voice.created_at,
            jurisdiction=voice.jurisdiction,
        )

        assert verify_voice(tampered) is False

    def test_verify_voice_tampered_stance(self):
        """Tampered stance fails verification."""
        kp = KeyPair.generate()
        voice = sign_voice(kp, "agenda:2026-02-03:item-6a", Stance.SUPPORT)

        tampered = Voice(
            entity=voice.entity,
            stance=Stance.OPPOSE,  # Changed
            public_key=voice.public_key,
            signature=voice.signature,
            timestamp=voice.timestamp,
            created_at=voice.created_at,
            jurisdiction=voice.jurisdiction,
        )

        assert verify_voice(tampered) is False


class TestAttestationProof:
    """Tests for verify_attestation_proof()."""

    def test_valid_proof(self):
        """Valid attestation proof verifies."""
        issuer = KeyPair.generate()
        subject = KeyPair.generate()
        jurisdiction = "city-san-rafael"

        proof = sign_attestation_event(issuer, subject.public_key_hex, jurisdiction)

        assert verify_attestation_proof(
            proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex
        ) is True

    def test_wrong_issuer_pubkey(self):
        """Proof signed by different issuer fails."""
        issuer = KeyPair.generate()
        wrong_issuer = KeyPair.generate()
        subject = KeyPair.generate()
        jurisdiction = "city-san-rafael"

        proof = sign_attestation_event(issuer, subject.public_key_hex, jurisdiction)

        assert verify_attestation_proof(
            proof, subject.public_key_hex, jurisdiction, wrong_issuer.public_key_hex
        ) is False

    def test_wrong_subject(self):
        """Proof for different subject fails d-tag and p-tag checks."""
        issuer = KeyPair.generate()
        subject = KeyPair.generate()
        other_subject = KeyPair.generate()
        jurisdiction = "city-san-rafael"

        proof = sign_attestation_event(issuer, subject.public_key_hex, jurisdiction)

        assert verify_attestation_proof(
            proof, other_subject.public_key_hex, jurisdiction, issuer.public_key_hex
        ) is False

    def test_wrong_jurisdiction(self):
        """Proof for different jurisdiction fails d-tag and j-tag checks."""
        issuer = KeyPair.generate()
        subject = KeyPair.generate()

        proof = sign_attestation_event(issuer, subject.public_key_hex, "city-san-rafael")

        assert verify_attestation_proof(
            proof, subject.public_key_hex, "city-berkeley", issuer.public_key_hex
        ) is False

    def test_tampered_signature(self):
        """Tampered signature fails verification."""
        issuer = KeyPair.generate()
        subject = KeyPair.generate()
        jurisdiction = "city-san-rafael"

        proof = sign_attestation_event(issuer, subject.public_key_hex, jurisdiction)
        proof["sig"] = "00" * 64  # Tampered

        assert verify_attestation_proof(
            proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex
        ) is False

    def test_tampered_event_id(self):
        """Tampered event ID fails recomputation check."""
        issuer = KeyPair.generate()
        subject = KeyPair.generate()
        jurisdiction = "city-san-rafael"

        proof = sign_attestation_event(issuer, subject.public_key_hex, jurisdiction)
        proof["id"] = "00" * 32  # Tampered

        assert verify_attestation_proof(
            proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex
        ) is False

    def test_wrong_kind(self):
        """Non-30850 kind fails."""
        issuer = KeyPair.generate()
        subject = KeyPair.generate()
        jurisdiction = "city-san-rafael"

        proof = sign_attestation_event(issuer, subject.public_key_hex, jurisdiction)
        proof["kind"] = 30800  # Wrong kind

        assert verify_attestation_proof(
            proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex
        ) is False

    def test_none_proof(self):
        """None proof returns False."""
        assert verify_attestation_proof(None, "abc", "j", "def") is False

    def test_empty_dict(self):
        """Empty dict returns False."""
        assert verify_attestation_proof({}, "abc", "j", "def") is False


class TestCoincurveHardDependency:
    """Tests that coincurve is a hard dependency — no silent bypass."""

    def test_module_imports_coincurve_at_top_level(self):
        """crypto module imports coincurve at module level (fails fast if missing)."""
        import civicos_relay.voice.crypto as crypto_mod
        # Verify PublicKeyXOnly is available as a module-level name
        assert hasattr(crypto_mod, 'PublicKeyXOnly')

    def test_no_allow_unsigned_bypass(self):
        """CIVICOS_ALLOW_UNSIGNED env var does NOT bypass verification."""
        import os
        old = os.environ.get("CIVICOS_ALLOW_UNSIGNED")
        try:
            os.environ["CIVICOS_ALLOW_UNSIGNED"] = "1"
            # Invalid signature should still return False, not True
            fake_pubkey = "a" * 64
            fake_sig = "b" * 128
            fake_msg = "c" * 64
            assert _schnorr_verify(fake_pubkey, fake_sig, fake_msg) is False
        finally:
            if old is None:
                os.environ.pop("CIVICOS_ALLOW_UNSIGNED", None)
            else:
                os.environ["CIVICOS_ALLOW_UNSIGNED"] = old

    def test_invalid_signature_returns_false(self):
        """Invalid signature data returns False (not an exception)."""
        kp = KeyPair.generate()
        assert _schnorr_verify(kp.public_key_hex, "00" * 64, "00" * 32) is False

    def test_invalid_pubkey_returns_false(self):
        """Invalid pubkey returns False."""
        assert _schnorr_verify("00" * 32, "00" * 64, "00" * 32) is False


class TestVoiceCount:
    """Tests for voice count aggregation."""

    def test_voice_count_total(self):
        """Total is sum of all stances."""
        count = VoiceCount(entity="test", support=10, oppose=3, watching=5)
        assert count.total == 18

    def test_voice_count_empty(self):
        """Empty count has zero total."""
        count = VoiceCount(entity="test")
        assert count.total == 0
