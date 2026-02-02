"""
Key link attestation and migration for CivicOS.

Handles the migration from old SECP256R1 (CivicOS v1) keys to new secp256k1 (Nostr) keys.
The key link attestation (kind 1802) proves ownership of both keys.

Migration flow:
1. User has old SECP256R1 key with provenance history
2. User generates new Nostr (secp256k1) key
3. Old key signs message: "civicos:link:v1:<new_pubkey>"
4. User publishes kind 1802 event with both signatures
5. Relay validates both signatures, links keys
6. Provenance is accessible via the new key
"""

import logging
from datetime import datetime
from typing import Callable, Awaitable

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidSignature

from civicos_relay.nostr.models import (
    NostrEvent,
    KeyLinkAttestationEvent,
    parse_event,
)
from civicos_relay.nostr.kinds import KEY_LINK_ATTESTATION, TAG_OLD_KEY, TAG_OLD_SIG
from civicos_relay.nostr.storage import NostrEventStorage, NostrKeyLinkStorage

logger = logging.getLogger(__name__)


# =============================================================================
# Old Key Verification (SECP256R1/ECDSA)
# =============================================================================


def build_link_message(new_pubkey: str) -> str:
    """
    Build the message that old key must sign.

    Args:
        new_pubkey: 32-byte hex Nostr pubkey

    Returns:
        Message string: "civicos:link:v1:<new_pubkey>"
    """
    return f"civicos:link:v1:{new_pubkey}"


def verify_old_key_signature(
    old_pubkey_hex: str,
    signature_hex: str,
    new_pubkey_hex: str,
) -> bool:
    """
    Verify ECDSA signature from old SECP256R1 key.

    The old key signs: "civicos:link:v1:<new_pubkey>"

    Args:
        old_pubkey_hex: Old SECP256R1 compressed pubkey (33 bytes = 66 hex chars)
        signature_hex: ECDSA signature (DER encoded)
        new_pubkey_hex: New Nostr pubkey (32 bytes = 64 hex chars)

    Returns:
        True if signature is valid
    """
    try:
        # Validate input lengths
        if len(new_pubkey_hex) != 64:
            return False

        # Old key can be 33 bytes (compressed) or 65 bytes (uncompressed)
        old_pubkey_bytes = bytes.fromhex(old_pubkey_hex)
        if len(old_pubkey_bytes) not in (33, 65):
            return False

        # Reconstruct old public key
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), old_pubkey_bytes
        )

        # Build and verify message
        message = build_link_message(new_pubkey_hex).encode("utf-8")
        signature = bytes.fromhex(signature_hex)

        public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        return True

    except (InvalidSignature, ValueError, Exception) as e:
        logger.debug(f"Old key signature verification failed: {e}")
        return False


# =============================================================================
# Key Link Attestation Service
# =============================================================================


class KeyLinkService:
    """
    Service for handling key link attestations.

    Validates dual signatures and manages key link storage.
    """

    def __init__(
        self,
        event_storage: NostrEventStorage,
        key_link_storage: NostrKeyLinkStorage,
    ):
        self._events = event_storage
        self._links = key_link_storage

    def validate_attestation(self, event: KeyLinkAttestationEvent) -> tuple[bool, str]:
        """
        Validate a key link attestation event.

        Checks:
        1. Event has valid Nostr signature (new key signs event)
        2. Old key signature is valid (old key signs link message)
        3. Old key hasn't already been linked

        Args:
            event: The key link attestation event

        Returns:
            Tuple of (valid, message)
        """
        # Check Nostr signature (new key)
        if not event.verify():
            return False, "Invalid Nostr event signature"

        # Get old key and signature from tags
        old_key = event.old_key
        old_sig = event.old_signature
        new_key = event.pubkey

        # Verify old key signature
        if not verify_old_key_signature(old_key, old_sig, new_key):
            return False, "Invalid old key signature"

        # Check if old key is already linked
        existing_link = self._links.get_linked_key(old_key)
        if existing_link:
            if existing_link == new_key:
                return False, "Key already linked to this Nostr key"
            return False, "Old key already linked to a different Nostr key"

        return True, "Valid attestation"

    def process_attestation(
        self, event: KeyLinkAttestationEvent
    ) -> tuple[bool, str]:
        """
        Process and store a key link attestation.

        Args:
            event: The key link attestation event

        Returns:
            Tuple of (success, message)
        """
        # Validate
        valid, message = self.validate_attestation(event)
        if not valid:
            return False, message

        # Store the event
        success, store_msg = self._events.save_event(event)
        if not success:
            return False, f"Failed to store event: {store_msg}"

        # Create key link
        old_key = event.old_key
        new_key = event.pubkey
        link_saved = self._links.save_key_link(old_key, new_key, event.id)

        if not link_saved:
            return False, "Failed to save key link (race condition?)"

        logger.info(f"Key linked: {old_key[:16]}... -> {new_key[:16]}...")
        return True, "Key link created successfully"

    def get_linked_nostr_key(self, old_key: str) -> str | None:
        """Get the Nostr key linked to an old CivicOS key."""
        return self._links.get_linked_key(old_key)

    def get_old_keys(self, nostr_key: str) -> list[str]:
        """Get all old CivicOS keys linked to a Nostr key."""
        return self._links.get_old_keys(nostr_key)


# =============================================================================
# Relay Integration
# =============================================================================


def create_key_link_handler(service: KeyLinkService):
    """
    Create a callback handler for key link attestation events.

    Use this with NostrRelay's on_voice_event callback pattern.
    """

    async def handler(event: NostrEvent) -> None:
        if event.kind != KEY_LINK_ATTESTATION:
            return

        try:
            attestation = KeyLinkAttestationEvent(**event.to_dict())
            success, message = service.process_attestation(attestation)
            if success:
                logger.info(f"Processed key link attestation: {event.id}")
            else:
                logger.warning(f"Key link attestation rejected: {message}")
        except Exception as e:
            logger.exception(f"Error processing key link attestation: {e}")

    return handler


# =============================================================================
# Provenance Queries with Key Links
# =============================================================================


class LinkedProvenanceService:
    """
    Provenance queries that follow key links.

    When querying provenance for a Nostr key, this service also
    aggregates provenance from any linked old keys.
    """

    def __init__(
        self,
        key_link_storage: NostrKeyLinkStorage,
        # These would be the old storage classes
        legacy_provenance_storage=None,
    ):
        self._links = key_link_storage
        self._legacy = legacy_provenance_storage

    def get_all_keys_for_identity(self, nostr_key: str) -> list[str]:
        """
        Get all keys (old and new) belonging to an identity.

        Returns:
            List starting with nostr_key, followed by any linked old keys
        """
        all_keys = [nostr_key]
        old_keys = self._links.get_old_keys(nostr_key)
        all_keys.extend(old_keys)
        return all_keys

    def get_aggregated_provenance(self, nostr_key: str) -> dict:
        """
        Get aggregated provenance across all linked keys.

        This merges provenance from:
        - The Nostr key's own activity
        - Any linked old CivicOS keys

        Returns:
            Dict with aggregated provenance data
        """
        all_keys = self.get_all_keys_for_identity(nostr_key)

        # Start with empty aggregation
        aggregated = {
            "nostr_key": nostr_key,
            "linked_old_keys": all_keys[1:] if len(all_keys) > 1 else [],
            "first_voice_date": None,
            "total_voices": 0,
            "entities_touched": set(),
            "jurisdictions": set(),
        }

        # If we have legacy storage, query old provenance
        if self._legacy:
            for old_key in all_keys[1:]:
                try:
                    prov = self._legacy.get_provenance(old_key)
                    if prov:
                        # Merge provenance
                        if prov.first_voice_at:
                            if (
                                aggregated["first_voice_date"] is None
                                or prov.first_voice_at < aggregated["first_voice_date"]
                            ):
                                aggregated["first_voice_date"] = prov.first_voice_at

                        aggregated["total_voices"] += prov.total_voices
                        aggregated["entities_touched"].add(prov.entities_touched)
                        for j in prov.jurisdictions:
                            aggregated["jurisdictions"].add(j)
                except Exception as e:
                    logger.warning(f"Error fetching legacy provenance for {old_key}: {e}")

        # Convert sets to lists for JSON serialization
        aggregated["jurisdictions"] = list(aggregated["jurisdictions"])
        aggregated["entities_touched"] = sum(aggregated["entities_touched"]) if aggregated["entities_touched"] else 0

        return aggregated
