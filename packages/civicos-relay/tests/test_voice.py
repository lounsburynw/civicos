"""Tests for voice module."""

import pytest
from datetime import datetime, timedelta

from civicos_relay.voice.models import Voice, Stance, VoiceCount
from civicos_relay.voice.crypto import KeyPair, sign_voice, verify_voice


class TestKeyPair:
    """Tests for keypair generation."""

    def test_generate_keypair(self):
        """Can generate a new keypair."""
        kp = KeyPair.generate()
        assert kp.private_key_hex
        assert kp.public_key_hex

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
        assert len(voice.signature) > 0

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
