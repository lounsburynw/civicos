"""Relay identity and signing."""

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    PrivateFormat,
    NoEncryption,
    load_pem_private_key,
)
from cryptography.exceptions import InvalidSignature


@dataclass
class RelayIdentity:
    """
    Identity for a relay instance.

    Each relay has a keypair used to:
    - Sign events it emits
    - Sign sync responses
    - Authenticate to peer relays
    """

    relay_id: str
    private_key: ec.EllipticCurvePrivateKey
    public_key: ec.EllipticCurvePublicKey

    @classmethod
    def generate(cls, relay_id: str) -> "RelayIdentity":
        """Generate a new relay identity."""
        private_key = ec.generate_private_key(ec.SECP256R1())
        return cls(
            relay_id=relay_id,
            private_key=private_key,
            public_key=private_key.public_key(),
        )

    @classmethod
    def load(cls, relay_id: str, private_key_path: str) -> "RelayIdentity":
        """Load relay identity from PEM file."""
        path = Path(private_key_path)
        if not path.exists():
            raise FileNotFoundError(f"Relay private key not found: {private_key_path}")

        with open(path, "rb") as f:
            private_key = load_pem_private_key(f.read(), password=None)

        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise ValueError("Expected ECDSA private key")

        return cls(
            relay_id=relay_id,
            private_key=private_key,
            public_key=private_key.public_key(),
        )

    @classmethod
    def load_or_generate(
        cls, relay_id: str, private_key_path: Optional[str] = None
    ) -> "RelayIdentity":
        """Load from file if exists, otherwise generate new identity."""
        if private_key_path and Path(private_key_path).exists():
            return cls.load(relay_id, private_key_path)

        identity = cls.generate(relay_id)

        # Save if path provided
        if private_key_path:
            identity.save(private_key_path)

        return identity

    def save(self, private_key_path: str) -> None:
        """Save private key to PEM file."""
        path = Path(private_key_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        pem = self.private_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )
        with open(path, "wb") as f:
            f.write(pem)

        # Restrict permissions
        os.chmod(path, 0o600)

    @property
    def public_key_hex(self) -> str:
        """Get public key as hex string for sharing with peers."""
        return self.public_key.public_bytes(
            Encoding.X962, PublicFormat.CompressedPoint
        ).hex()

    def sign(self, message: bytes) -> str:
        """Sign a message, return hex-encoded signature."""
        signature = self.private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        return signature.hex()

    def sign_event(self, event_type: str, entity: str, timestamp: datetime) -> str:
        """Sign an event for emission."""
        message = f"civicos:event:v1:{self.relay_id}:{event_type}:{entity}:{timestamp.isoformat()}".encode()
        return self.sign(message)

    def sign_sync_response(self, data_hash: str, cursor: str) -> str:
        """Sign a sync response for peer verification."""
        message = f"civicos:sync:v1:{self.relay_id}:{data_hash}:{cursor}".encode()
        return self.sign(message)

    @staticmethod
    def verify(
        message: bytes, signature_hex: str, public_key_hex: str
    ) -> bool:
        """Verify a signature from another relay."""
        try:
            public_key_bytes = bytes.fromhex(public_key_hex)
            public_key = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256R1(), public_key_bytes
            )
            signature = bytes.fromhex(signature_hex)
            public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
            return True
        except (InvalidSignature, ValueError):
            return False
