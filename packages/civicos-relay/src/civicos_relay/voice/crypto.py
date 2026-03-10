"""Cryptographic utilities for voice signing.

Uses BIP-340 Schnorr signatures on secp256k1 (Nostr-compatible).
The Personal MCP signs Nostr events; the relay verifies them.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from civicos_relay.voice.models import Voice, Stance, Comment, Feedback


def _schnorr_verify(pubkey_hex: str, sig_hex: str, msg_hex: str) -> bool:
    """Verify a BIP-340 Schnorr signature using coincurve.

    Args:
        pubkey_hex: 32-byte x-only public key as hex (64 chars)
        sig_hex: 64-byte Schnorr signature as hex (128 chars)
        msg_hex: 32-byte message hash as hex (64 chars) — typically a Nostr event ID
    """
    try:
        from coincurve import PublicKeyXOnly
        pk = PublicKeyXOnly(bytes.fromhex(pubkey_hex))
        return pk.verify(bytes.fromhex(sig_hex), bytes.fromhex(msg_hex))
    except ImportError:
        if os.environ.get("CIVICOS_ALLOW_UNSIGNED") == "1":
            import logging
            logging.getLogger(__name__).warning(
                "coincurve not installed — BYPASSING signature verification (test only)"
            )
            return True
        raise RuntimeError("coincurve is required for signature verification")
    except Exception:
        return False


def _compute_nostr_event_id(
    pubkey: str, created_at: int, kind: int, tags: list, content: str
) -> str:
    """Compute a Nostr event ID per NIP-01: SHA-256 of [0, pubkey, created_at, kind, tags, content]."""
    serialized = json.dumps(
        [0, pubkey, created_at, kind, tags, content],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass
class KeyPair:
    """secp256k1 keypair for signing (testing only — real signing in Personal MCP)."""
    public_key_hex: str = ""
    private_key_hex: str = ""

    @classmethod
    def generate(cls) -> "KeyPair":
        """Generate a new secp256k1 keypair."""
        import os
        from coincurve import PublicKeyXOnly
        private_key = os.urandom(32)
        xonly_pk = PublicKeyXOnly.from_valid_secret(private_key)
        return cls(
            private_key_hex=private_key.hex(),
            public_key_hex=xonly_pk.format().hex(),
        )


def _voice_message(entity: str, stance: Stance) -> str:
    """Create the canonical voice message string."""
    return f"civicos:voice:v1:{entity}:{stance.value}"


def sign_voice(keypair: KeyPair, entity: str, stance: Stance, jurisdiction: Optional[str] = None) -> Voice:
    """Create a signed voice (for testing only — real signing happens in Personal MCP)."""
    from coincurve import PrivateKey
    now = datetime.utcnow()
    created_at = int(now.timestamp())

    tags = [
        ["d", entity],
        ["j", jurisdiction],
        ["stance", stance.value],
    ]
    content = f"{_voice_message(entity, stance)}:{created_at}"
    event_id_hex = _compute_nostr_event_id(keypair.public_key_hex, created_at, 30800, tags, content)
    event_id_bytes = bytes.fromhex(event_id_hex)

    pk = PrivateKey(bytes.fromhex(keypair.private_key_hex))
    sig = pk.sign_schnorr(event_id_bytes)

    return Voice(
        entity=entity,
        stance=stance,
        public_key=keypair.public_key_hex,
        signature=sig.hex(),
        timestamp=now,
        created_at=created_at,
        jurisdiction=jurisdiction,
    )


def verify_voice(voice: Voice) -> bool:
    """
    Verify a voice signature.

    Supports Nostr-style signatures from the Personal MCP:
    - pubkey: 32-byte x-only secp256k1 public key (hex)
    - signature: 64-byte BIP-340 Schnorr signature (hex)

    The signature is over the Nostr event ID, which is the SHA-256 of
    [0, pubkey, created_at, kind, tags, content].

    The voice must include `created_at` (unix timestamp) and `jurisdiction`
    so the relay can reconstruct the exact Nostr event that was signed.
    """
    try:
        pubkey = voice.public_key
        sig = voice.signature

        if not pubkey or not sig:
            return False

        # Check key/sig lengths (32-byte pubkey = 64 hex, 64-byte sig = 128 hex)
        if len(pubkey) != 64 or len(sig) != 128:
            return False

        # Need created_at to reconstruct the signed event
        if voice.created_at is None:
            return False

        created_at = voice.created_at

        # Build the Nostr event structure exactly as Personal MCP does (Kind 30800)
        tags = [
            ["d", voice.entity],
            ["j", voice.jurisdiction],
            ["stance", voice.stance.value],
        ]
        content = f"{_voice_message(voice.entity, voice.stance)}:{created_at}"

        event_id = _compute_nostr_event_id(pubkey, created_at, 30800, tags, content)
        return _schnorr_verify(pubkey, sig, event_id)
    except Exception:
        return False


def verify_comment(comment: Comment) -> bool:
    """
    Verify a comment signature.

    Comments use Nostr Kind 30803. The comment text IS the event content.
    The signature is over the Nostr event ID (SHA-256 of serialized event).
    """
    try:
        pubkey = comment.public_key
        sig = comment.signature

        if not pubkey or not sig:
            return False

        if len(pubkey) != 64 or len(sig) != 128:
            return False

        if comment.created_at is None:
            return False

        created_at = comment.created_at

        # Build tags: d (entity), j (jurisdiction), optionally stance
        tags = [
            ["d", comment.entity],
            ["j", comment.jurisdiction],
        ]
        if comment.stance:
            tags.append(["stance", comment.stance])

        # Content is the comment text itself
        content = comment.comment_text

        event_id = _compute_nostr_event_id(pubkey, created_at, 30803, tags, content)
        return _schnorr_verify(pubkey, sig, event_id)
    except Exception:
        return False


def verify_feedback(feedback: Feedback) -> bool:
    """
    Verify a feedback signature.

    Feedback uses Nostr Kind 1804 (regular, not addressable).
    The feedback content IS the event content.
    Tags: [["t", feedback_type], ["j", jurisdiction], ["v", "1"]]
    """
    try:
        pubkey = feedback.public_key
        sig = feedback.signature

        if not pubkey or not sig:
            return False

        if len(pubkey) != 64 or len(sig) != 128:
            return False

        if feedback.created_at is None:
            return False

        created_at = feedback.created_at

        tags = [
            ["t", feedback.feedback_type],
            ["j", feedback.jurisdiction],
            ["v", "1"],
        ]
        content = feedback.content

        event_id = _compute_nostr_event_id(pubkey, created_at, 1804, tags, content)
        return _schnorr_verify(pubkey, sig, event_id)
    except Exception:
        return False


def _check_key_sig(public_key: str, signature: str) -> bool:
    """Basic length check for hex-encoded key and signature."""
    return bool(public_key and signature and len(public_key) == 64 and len(signature) == 128)


def verify_initiative(
    public_key: str, signature: str, jurisdiction: str, topic: str, created_at: int
) -> bool:
    """
    Verify an initiative creation signature (Kind 30800).

    Extension signs content = "civicos:initiative:v1:{jurisdiction}:{topic}:{created_at}"
    with tags [["d", "initiative:{jurisdiction}:{topic}"], ["j", jurisdiction]].
    """
    try:
        if not _check_key_sig(public_key, signature):
            return False
        tags = [
            ["d", f"initiative:{jurisdiction}:{topic}"],
            ["j", jurisdiction],
        ]
        content = f"civicos:initiative:v1:{jurisdiction}:{topic}:{created_at}"
        event_id = _compute_nostr_event_id(public_key, created_at, 30800, tags, content)
        return _schnorr_verify(public_key, signature, event_id)
    except Exception:
        return False


def verify_commitment(
    public_key: str, signature: str, action_id: str, jurisdiction: str, created_at: int
) -> bool:
    """
    Verify an action commitment signature (Kind 30811).

    Extension signs content = "civicos:action:v1:{action_id}:commitment:{created_at}"
    with tags [["d", action_id], ["j", jurisdiction], ["action", "commitment"]].
    """
    try:
        if not _check_key_sig(public_key, signature):
            return False
        tags = [
            ["d", action_id],
            ["j", jurisdiction],
            ["action", "commitment"],
        ]
        content = f"civicos:action:v1:{action_id}:commitment:{created_at}"
        event_id = _compute_nostr_event_id(public_key, created_at, 30811, tags, content)
        return _schnorr_verify(public_key, signature, event_id)
    except Exception:
        return False


def verify_completion(
    public_key: str, signature: str, action_id: str, jurisdiction: str, created_at: int,
    evidence_url: Optional[str] = None
) -> bool:
    """
    Verify an action completion signature (Kind 30812).

    Extension signs content = "civicos:action:v1:{action_id}:completion:{created_at}"
    with tags [["d", action_id], ["j", jurisdiction], ["action", "completion"]].
    """
    try:
        if not _check_key_sig(public_key, signature):
            return False
        tags = [
            ["d", action_id],
            ["j", jurisdiction],
            ["action", "completion"],
        ]
        if evidence_url:
            tags.append(["evidence", evidence_url])
        base = f"civicos:action:v1:{action_id}:completion:{created_at}"
        content = f"{base}:{evidence_url}" if evidence_url else base
        event_id = _compute_nostr_event_id(public_key, created_at, 30812, tags, content)
        return _schnorr_verify(public_key, signature, event_id)
    except Exception:
        return False


def verify_withdrawal(
    public_key: str, signature: str, action_id: str, created_at: int
) -> bool:
    """
    Verify a withdrawal signature (Kind 30811 with withdraw action tag).

    Extension signs content = "civicos:withdraw:v1:{action_id}:{created_at}"
    with tags [["d", action_id], ["action", "withdraw"]].
    """
    try:
        if not _check_key_sig(public_key, signature):
            return False
        tags = [
            ["d", action_id],
            ["action", "withdraw"],
        ]
        content = f"civicos:withdraw:v1:{action_id}:{created_at}"
        event_id = _compute_nostr_event_id(public_key, created_at, 30811, tags, content)
        return _schnorr_verify(public_key, signature, event_id)
    except Exception:
        return False


def verify_action_event(
    public_key: str, signature: str, initiative_id: str, action_type: str, created_at: int
) -> bool:
    """
    Verify an action event creation signature (Kind 30810).

    Extension signs content = "civicos:action:v1:{initiative_id}:{action_type}:{created_at}"
    with tags [["d", "action:{initiative_id}:{action_type}"], ["initiative", initiative_id]].
    """
    try:
        if not _check_key_sig(public_key, signature):
            return False
        tags = [
            ["d", f"action:{initiative_id}:{action_type}"],
            ["initiative", initiative_id],
        ]
        content = f"civicos:action:v1:{initiative_id}:{action_type}:{created_at}"
        event_id = _compute_nostr_event_id(public_key, created_at, 30810, tags, content)
        return _schnorr_verify(public_key, signature, event_id)
    except Exception:
        return False


def verify_attestation_request(
    public_key: str, signature: str, code: str, created_at: int
) -> bool:
    """
    Verify an attestation code redemption request (Kind 24242 ephemeral auth).

    Extension signs a kind-24242 event proving pubkey ownership:
    - Tags: [["action", "attest"], ["code", code]]
    - Content: "civicos:attest:v1:{public_key}:{code}:{created_at}"
    """
    try:
        if not _check_key_sig(public_key, signature):
            return False
        tags = [
            ["action", "attest"],
            ["code", code],
        ]
        content = f"civicos:attest:v1:{public_key}:{code}:{created_at}"
        event_id = _compute_nostr_event_id(public_key, created_at, 24242, tags, content)
        return _schnorr_verify(public_key, signature, event_id)
    except Exception:
        return False


def sign_attestation_event(
    issuer_keypair: KeyPair,
    subject_pubkey: str,
    jurisdiction: str,
    attestation_type: str = "physical",
) -> dict:
    """
    Sign a kind-30850 attestation event as the CivicOS issuer.

    Returns a full signed Nostr event dict that the subject stores as proof.
    """
    from coincurve import PrivateKey

    created_at = int(datetime.utcnow().timestamp())
    tags = [
        ["d", f"attest:{jurisdiction}:{subject_pubkey}"],
        ["p", subject_pubkey],
        ["j", jurisdiction],
        ["type", attestation_type],
    ]
    content = f"civicos:attestation:v1:{jurisdiction}:{attestation_type}:{created_at}"

    event_id = _compute_nostr_event_id(
        issuer_keypair.public_key_hex, created_at, 30850, tags, content
    )

    pk = PrivateKey(bytes.fromhex(issuer_keypair.private_key_hex))
    sig = pk.sign_schnorr(bytes.fromhex(event_id))

    return {
        "id": event_id,
        "pubkey": issuer_keypair.public_key_hex,
        "created_at": created_at,
        "kind": 30850,
        "tags": tags,
        "content": content,
        "sig": sig.hex(),
    }


def verify_attestation_proof(
    proof: dict, subject_pubkey: str, jurisdiction: str, issuer_pubkey: str
) -> bool:
    """
    Verify a kind-30850 attestation proof embedded on a voice/comment event.

    Checks:
    1. Kind is 30850
    2. Signed by the jurisdiction's issuer (not the subject)
    3. d-tag matches attest:{jurisdiction}:{subject_pubkey}
    4. Has required ["p", subject_pubkey] and ["j", jurisdiction] tags
    5. Event ID matches recomputed hash
    6. Schnorr signature is valid
    """
    try:
        if not isinstance(proof, dict):
            return False

        # 1. Kind check
        if proof.get("kind") != 30850:
            return False

        # 2. Issuer check — must be signed by jurisdiction issuer, not subject
        if proof.get("pubkey") != issuer_pubkey:
            return False

        # 3. d-tag check
        tags = proof.get("tags", [])
        expected_d = f"attest:{jurisdiction}:{subject_pubkey}"
        d_tag_ok = any(
            t[0] == "d" and t[1] == expected_d for t in tags if len(t) >= 2
        )
        if not d_tag_ok:
            return False

        # 4. Required tags
        has_p = any(t[0] == "p" and t[1] == subject_pubkey for t in tags if len(t) >= 2)
        has_j = any(t[0] == "j" and t[1] == jurisdiction for t in tags if len(t) >= 2)
        if not has_p or not has_j:
            return False

        # 5. Recompute event ID
        computed_id = _compute_nostr_event_id(
            proof["pubkey"], proof["created_at"], 30850, tags, proof.get("content", "")
        )
        if computed_id != proof.get("id"):
            return False

        # 6. Verify Schnorr signature
        return _schnorr_verify(proof["pubkey"], proof["sig"], proof["id"])
    except (KeyError, TypeError, ValueError):
        return False


def verify_signature(public_key_hex: str, signature_hex: str, message: str) -> bool:
    """Verify an arbitrary Schnorr signature over a message."""
    try:
        msg_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
        return _schnorr_verify(public_key_hex, signature_hex, msg_hash)
    except Exception:
        return False


def sign_message(keypair: KeyPair, message: str) -> str:
    """Sign an arbitrary message with Schnorr (for testing only)."""
    from coincurve import PrivateKey
    msg_hash = hashlib.sha256(message.encode("utf-8")).digest()
    pk = PrivateKey(bytes.fromhex(keypair.private_key_hex))
    return pk.sign_schnorr(msg_hash).hex()
