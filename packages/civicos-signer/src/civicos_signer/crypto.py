"""Attestation signing primitives.

Extracted from civicos-relay's crypto module. This is the complete
cryptographic surface for attestation issuance — no relay dependency needed.

Uses BIP-340 Schnorr signatures on secp256k1 (Nostr-compatible).
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class IssuerKeyPair:
    """secp256k1 keypair for attestation signing."""

    public_key_hex: str
    private_key_hex: str

    @classmethod
    def generate(cls) -> "IssuerKeyPair":
        """Generate a new issuer keypair."""
        from coincurve import PublicKeyXOnly

        private_key = os.urandom(32)
        xonly_pk = PublicKeyXOnly.from_valid_secret(private_key)
        return cls(
            private_key_hex=private_key.hex(),
            public_key_hex=xonly_pk.format().hex(),
        )

    @classmethod
    def from_private_key(cls, private_key_hex: str) -> "IssuerKeyPair":
        """Load keypair from an existing private key."""
        from coincurve import PublicKeyXOnly

        xonly_pk = PublicKeyXOnly.from_valid_secret(bytes.fromhex(private_key_hex))
        return cls(
            private_key_hex=private_key_hex,
            public_key_hex=xonly_pk.format().hex(),
        )


def _compute_nostr_event_id(
    pubkey: str, created_at: int, kind: int, tags: list, content: str
) -> str:
    """Compute a Nostr event ID per NIP-01."""
    serialized = json.dumps(
        [0, pubkey, created_at, kind, tags, content],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def sign_attestation(
    issuer: IssuerKeyPair,
    subject_pubkey: str,
    jurisdiction: str,
    attestation_type: str = "physical",
) -> dict:
    """Sign a kind-30850 attestation event.

    Returns a full signed Nostr event dict that the subject stores as proof.
    The event is signed by this issuer's key — identifying this organization
    as the attestation authority.
    """
    from coincurve import PrivateKey

    created_at = int(datetime.now(timezone.utc).timestamp())
    tags = [
        ["d", f"attest:{jurisdiction}:{subject_pubkey}"],
        ["p", subject_pubkey],
        ["j", jurisdiction],
        ["type", attestation_type],
    ]
    content = f"civicos:attestation:v1:{jurisdiction}:{attestation_type}:{created_at}"

    event_id = _compute_nostr_event_id(
        issuer.public_key_hex, created_at, 30850, tags, content
    )

    pk = PrivateKey(bytes.fromhex(issuer.private_key_hex))
    sig = pk.sign_schnorr(bytes.fromhex(event_id))

    return {
        "id": event_id,
        "pubkey": issuer.public_key_hex,
        "created_at": created_at,
        "kind": 30850,
        "tags": tags,
        "content": content,
        "sig": sig.hex(),
    }


def verify_attestation(
    proof: dict, subject_pubkey: str, jurisdiction: str, issuer_pubkey: str
) -> bool:
    """Verify a kind-30850 attestation proof.

    The six checks:
    1. Kind is 30850
    2. Signed by the expected issuer
    3. d-tag matches attest:{jurisdiction}:{subject_pubkey}
    4. Has required p and j tags
    5. Event ID matches recomputed hash
    6. Schnorr signature is valid
    """
    try:
        from coincurve import PublicKeyXOnly

        if not isinstance(proof, dict):
            return False
        if proof.get("kind") != 30850:
            return False
        if proof.get("pubkey") != issuer_pubkey:
            return False

        tags = proof.get("tags", [])
        expected_d = f"attest:{jurisdiction}:{subject_pubkey}"
        if not any(t[0] == "d" and t[1] == expected_d for t in tags if len(t) >= 2):
            return False
        if not any(
            t[0] == "p" and t[1] == subject_pubkey for t in tags if len(t) >= 2
        ):
            return False
        if not any(t[0] == "j" and t[1] == jurisdiction for t in tags if len(t) >= 2):
            return False

        computed_id = _compute_nostr_event_id(
            proof["pubkey"], proof["created_at"], 30850, tags, proof.get("content", "")
        )
        if computed_id != proof.get("id"):
            return False

        pk = PublicKeyXOnly(bytes.fromhex(proof["pubkey"]))
        return pk.verify(bytes.fromhex(proof["sig"]), bytes.fromhex(proof["id"]))
    except (KeyError, TypeError, ValueError, Exception):
        return False
