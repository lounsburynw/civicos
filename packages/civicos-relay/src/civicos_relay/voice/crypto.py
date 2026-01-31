"""Cryptographic utilities for voice signing."""

from dataclasses import dataclass
from datetime import datetime

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    PrivateFormat,
    NoEncryption,
)
from cryptography.exceptions import InvalidSignature

from civicos_relay.voice.models import Voice, Stance


@dataclass
class KeyPair:
    """ECDSA keypair for voice signing."""

    private_key: ec.EllipticCurvePrivateKey
    public_key: ec.EllipticCurvePublicKey

    @classmethod
    def generate(cls) -> "KeyPair":
        """Generate a new keypair."""
        private_key = ec.generate_private_key(ec.SECP256R1())
        return cls(
            private_key=private_key,
            public_key=private_key.public_key(),
        )

    @property
    def public_key_hex(self) -> str:
        """Get public key as hex string."""
        return self.public_key.public_bytes(
            Encoding.X962, PublicFormat.CompressedPoint
        ).hex()

    @property
    def private_key_hex(self) -> str:
        """Get private key as hex string (for secure storage)."""
        return self.private_key.private_bytes(
            Encoding.DER, PrivateFormat.PKCS8, NoEncryption()
        ).hex()


def _voice_message(entity: str, stance: Stance) -> bytes:
    """Create the message to sign for a voice."""
    return f"civicos:voice:v1:{entity}:{stance.value}".encode("utf-8")


def sign_voice(keypair: KeyPair, entity: str, stance: Stance) -> Voice:
    """Create a signed voice."""
    message = _voice_message(entity, stance)
    signature = keypair.private_key.sign(message, ec.ECDSA(hashes.SHA256()))

    return Voice(
        entity=entity,
        stance=stance,
        public_key=keypair.public_key_hex,
        signature=signature.hex(),
        timestamp=datetime.utcnow(),
    )


def verify_voice(voice: Voice) -> bool:
    """Verify a voice signature is valid."""
    try:
        # Reconstruct public key from hex
        public_key_bytes = bytes.fromhex(voice.public_key)
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), public_key_bytes
        )

        # Verify signature
        message = _voice_message(voice.entity, voice.stance)
        signature = bytes.fromhex(voice.signature)
        public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_signature(public_key_hex: str, signature_hex: str, message: str) -> bool:
    """
    Verify an arbitrary message signature.

    Used for initiatives and other non-voice signed content.
    """
    try:
        public_key_bytes = bytes.fromhex(public_key_hex)
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), public_key_bytes
        )

        signature = bytes.fromhex(signature_hex)
        message_bytes = message.encode("utf-8")
        public_key.verify(signature, message_bytes, ec.ECDSA(hashes.SHA256()))
        return True
    except (InvalidSignature, ValueError):
        return False


def sign_message(keypair: KeyPair, message: str) -> str:
    """
    Sign an arbitrary message and return signature hex.

    Used for initiatives and other non-voice signed content.
    """
    message_bytes = message.encode("utf-8")
    signature = keypair.private_key.sign(message_bytes, ec.ECDSA(hashes.SHA256()))
    return signature.hex()
