"""Provenance service - tracks and evaluates key trust signals."""

from datetime import datetime
from typing import Optional, Protocol

from civicos_relay.provenance.models import KeyProvenance, ProvenanceSummary
from civicos_relay.voice.models import Voice


class ProvenanceStorage(Protocol):
    """Protocol for provenance persistence."""

    def get_provenance(self, public_key: str) -> Optional[KeyProvenance]:
        """Get provenance record for a key."""
        ...

    def save_provenance(self, provenance: KeyProvenance) -> None:
        """Store/update a provenance record."""
        ...

    def get_provenance_for_entity(self, entity: str) -> list[KeyProvenance]:
        """Get provenance for all keys that voiced on an entity."""
        ...


class ProvenanceService:
    """
    Service for managing key provenance.

    Tracks trust signals for voice quality assessment.
    """

    def __init__(self, storage: ProvenanceStorage):
        self._storage = storage

    def record_voice(self, voice: Voice) -> KeyProvenance:
        """
        Update provenance when a voice is cast.

        Creates provenance record if key is new.
        """
        existing = self._storage.get_provenance(voice.public_key)

        if existing:
            # Update existing provenance
            provenance = KeyProvenance(
                public_key=voice.public_key,
                created_at=existing.created_at,
                total_voices=existing.total_voices + 1,
                entities_touched=existing.entities_touched + 1,  # Simplified
                first_voice_at=existing.first_voice_at or voice.timestamp,
                last_voice_at=voice.timestamp,
                jurisdictions=existing.jurisdictions,  # TODO: extract from entity
            )
        else:
            # New key
            provenance = KeyProvenance(
                public_key=voice.public_key,
                created_at=voice.timestamp,
                total_voices=1,
                entities_touched=1,
                first_voice_at=voice.timestamp,
                last_voice_at=voice.timestamp,
                jurisdictions=[],  # TODO: extract from entity
            )

        self._storage.save_provenance(provenance)
        return provenance

    def get_for_key(self, public_key: str) -> Optional[KeyProvenance]:
        """Get provenance for a specific key."""
        return self._storage.get_provenance(public_key)

    def summarize_entity(self, entity: str) -> ProvenanceSummary:
        """
        Get provenance summary for all voices on an entity.

        Useful for assessing voice quality on an initiative or agenda item.
        """
        provenances = self._storage.get_provenance_for_entity(entity)

        total = len(provenances)
        high_quality = sum(1 for p in provenances if p.age_days >= 30)
        new_keys = sum(1 for p in provenances if p.is_new_key)

        return ProvenanceSummary(
            total_voices=total,
            high_quality_voices=high_quality,
            new_key_voices=new_keys,
            attested_voices=0,  # Future
        )
