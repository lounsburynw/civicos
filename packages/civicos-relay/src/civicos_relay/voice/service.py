"""Voice service - manages voice creation, storage, and counting."""

from typing import Optional, Protocol

from civicos_relay.voice.models import Voice, VoiceCount, Stance
from civicos_relay.voice.crypto import KeyPair, sign_voice, verify_voice


class VoiceStorage(Protocol):
    """Protocol for voice persistence."""

    def save_voice(self, voice: Voice) -> None:
        """Store a voice record."""
        ...

    def get_voice(self, public_key: str, entity: str) -> Optional[Voice]:
        """Get existing voice for key+entity pair."""
        ...

    def get_voices_for_entity(self, entity: str) -> list[Voice]:
        """Get all voices for an entity."""
        ...

    def revoke_voice(self, public_key: str, entity: str) -> bool:
        """Revoke a voice. Returns True if voice existed."""
        ...


class VoiceService:
    """
    Service for managing civic voices.

    Handles voice creation, verification, storage, and aggregation.
    """

    def __init__(self, storage: VoiceStorage):
        self._storage = storage

    def cast_voice(
        self, keypair: KeyPair, entity: str, stance: Stance
    ) -> Voice:
        """
        Cast a voice on an entity.

        If the key has already voiced on this entity, the old voice is
        revoked and replaced.
        """
        # Check for existing voice
        existing = self._storage.get_voice(keypair.public_key_hex, entity)
        if existing and not existing.revoked:
            self._storage.revoke_voice(keypair.public_key_hex, entity)

        # Create and sign new voice
        voice = sign_voice(keypair, entity, stance)
        self._storage.save_voice(voice)
        return voice

    def get_counts(self, entity: str) -> VoiceCount:
        """Get aggregated voice counts for an entity."""
        voices = self._storage.get_voices_for_entity(entity)
        counts = VoiceCount(entity=entity)

        for voice in voices:
            if voice.revoked:
                continue
            if voice.stance == Stance.SUPPORT:
                counts.support += 1
            elif voice.stance == Stance.OPPOSE:
                counts.oppose += 1
            elif voice.stance == Stance.WATCHING:
                counts.watching += 1

        return counts

    def verify(self, voice: Voice) -> bool:
        """Verify a voice signature is valid."""
        return verify_voice(voice)
