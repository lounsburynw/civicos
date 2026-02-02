"""
Nostr cryptographic operations.

Implements secp256k1 Schnorr signatures (BIP-340) and Nostr event ID calculation
as specified in NIP-01.

References:
- NIP-01: https://github.com/nostr-protocol/nips/blob/master/01.md
- BIP-340: https://github.com/bitcoin/bips/blob/master/bip-0340.mediawiki
"""

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any

import coincurve
from coincurve import PrivateKey, PublicKey, PublicKeyXOnly


@dataclass
class NostrKeyPair:
    """
    secp256k1 keypair for Nostr event signing.

    Nostr uses 32-byte x-only public keys (BIP-340 format).
    Private keys are 32-byte random scalars.
    """

    _private_key: PrivateKey

    @classmethod
    def generate(cls) -> "NostrKeyPair":
        """Generate a new random keypair."""
        secret = secrets.token_bytes(32)
        return cls(_private_key=PrivateKey(secret))

    @classmethod
    def from_nsec(cls, nsec: str) -> "NostrKeyPair":
        """
        Import from bech32-encoded nsec format.

        Note: Full bech32 decoding not implemented yet.
        Use from_hex for raw hex import.
        """
        raise NotImplementedError("bech32 nsec import not yet implemented")

    @classmethod
    def from_hex(cls, secret_hex: str) -> "NostrKeyPair":
        """Import from hex-encoded 32-byte secret."""
        if len(secret_hex) != 64:
            raise ValueError("Private key must be 32 bytes (64 hex chars)")
        secret = bytes.fromhex(secret_hex)
        return cls(_private_key=PrivateKey(secret))

    @property
    def secret_hex(self) -> str:
        """Get secret key as hex string (32 bytes)."""
        return self._private_key.secret.hex()

    @property
    def public_key_hex(self) -> str:
        """
        Get x-only public key as hex string (32 bytes).

        Nostr uses x-only pubkeys (BIP-340): just the x-coordinate,
        with the y-coordinate implicitly even.
        """
        # coincurve gives us 33-byte compressed pubkey (02/03 prefix + 32 bytes x)
        # We need just the x-coordinate (32 bytes) for Nostr
        compressed = self._private_key.public_key.format(compressed=True)
        return compressed[1:].hex()  # Skip the 02/03 prefix byte

    def sign_id(self, event_id: str) -> str:
        """
        Sign a Nostr event ID using Schnorr (BIP-340).

        Args:
            event_id: 32-byte hex-encoded event ID (SHA256 hash)

        Returns:
            64-byte hex-encoded Schnorr signature
        """
        if len(event_id) != 64:
            raise ValueError("Event ID must be 32 bytes (64 hex chars)")

        message = bytes.fromhex(event_id)
        # coincurve's sign_schnorr uses BIP-340 tagged hash internally
        signature = self._private_key.sign_schnorr(message)
        return signature.hex()


def serialize_event_for_id(
    pubkey: str,
    created_at: int,
    kind: int,
    tags: list[list[str]],
    content: str,
) -> str:
    """
    Serialize event data for ID calculation per NIP-01.

    The serialization format is:
    [0, pubkey, created_at, kind, tags, content]

    This is then SHA256 hashed to produce the event ID.
    """
    # NIP-01 specifies this exact serialization
    serialized = json.dumps(
        [0, pubkey, created_at, kind, tags, content],
        separators=(",", ":"),  # No spaces
        ensure_ascii=False,
    )
    return serialized


def compute_event_id(
    pubkey: str,
    created_at: int,
    kind: int,
    tags: list[list[str]],
    content: str,
) -> str:
    """
    Calculate event ID as SHA256 of serialized event data.

    Returns:
        32-byte hex-encoded event ID
    """
    serialized = serialize_event_for_id(pubkey, created_at, kind, tags, content)
    digest = hashlib.sha256(serialized.encode("utf-8")).digest()
    return digest.hex()


def sign_event(
    keypair: NostrKeyPair,
    created_at: int,
    kind: int,
    tags: list[list[str]],
    content: str,
) -> tuple[str, str, str]:
    """
    Create a signed Nostr event.

    Returns:
        Tuple of (event_id, pubkey, signature)
    """
    pubkey = keypair.public_key_hex
    event_id = compute_event_id(pubkey, created_at, kind, tags, content)
    sig = keypair.sign_id(event_id)
    return event_id, pubkey, sig


def verify_event_id(
    event_id: str,
    pubkey: str,
    created_at: int,
    kind: int,
    tags: list[list[str]],
    content: str,
) -> bool:
    """
    Verify that event ID matches the event data.

    Returns:
        True if event ID is correctly computed
    """
    computed = compute_event_id(pubkey, created_at, kind, tags, content)
    return event_id == computed


def verify_event_signature(
    event_id: str,
    pubkey: str,
    sig: str,
) -> bool:
    """
    Verify Schnorr signature on event ID.

    Args:
        event_id: 32-byte hex event ID
        pubkey: 32-byte hex x-only public key
        sig: 64-byte hex Schnorr signature

    Returns:
        True if signature is valid
    """
    try:
        if len(event_id) != 64 or len(pubkey) != 64 or len(sig) != 128:
            return False

        message = bytes.fromhex(event_id)
        signature = bytes.fromhex(sig)
        pubkey_bytes = bytes.fromhex(pubkey)

        # Create x-only public key for Schnorr verification
        # coincurve's PublicKeyXOnly handles BIP-340 verification
        public_key = PublicKeyXOnly(pubkey_bytes)

        # Verify using BIP-340 Schnorr
        return public_key.verify(signature, message)

    except Exception:
        return False


def verify_event(
    event_id: str,
    pubkey: str,
    created_at: int,
    kind: int,
    tags: list[list[str]],
    content: str,
    sig: str,
) -> bool:
    """
    Fully verify a Nostr event (ID and signature).

    Returns:
        True if both event ID and signature are valid
    """
    if not verify_event_id(event_id, pubkey, created_at, kind, tags, content):
        return False
    return verify_event_signature(event_id, pubkey, sig)
