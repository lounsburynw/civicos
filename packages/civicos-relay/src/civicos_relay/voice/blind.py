"""Schnorr blind signature primitives for privacy-preserving token issuance.

Uses secp256k1 (via coincurve) to implement a blind signature scheme where:
- An issuer signs tokens without seeing the message (unlinkability)
- A relay verifies tokens without knowing which payment session produced them
- Spent tokens are tracked by hash to prevent double-spending

Protocol overview:
  1. Issuer generates a nonce (k, R=kG) and sends R to user
  2. User blinds: picks random α,β; computes R'=R+αG+βP, e'=H(R'||P||m),
     e=e'+β; sends blinded challenge e to issuer
  3. Issuer signs: s = k + e·d mod n; sends s to user
  4. User unblinds: s' = s + α mod n; token is (m, R'||s')
  5. Relay verifies: s'·G == R' + H(R'||P||m)·P (standard Schnorr check)

coincurve is a hard dependency — import fails fast if missing.
"""

import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional, Protocol, Tuple

from coincurve import PrivateKey, PublicKey

# secp256k1 group order
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


@dataclass(frozen=True)
class BlindingContext:
    """User-side blinding state, kept secret until unblinding."""

    alpha: bytes  # 32-byte blinding scalar
    beta: bytes  # 32-byte blinding scalar
    blinded_nonce: bytes  # R' compressed pubkey (33 bytes)
    message: bytes  # the message being signed


@dataclass(frozen=True)
class SpendableToken:
    """Unblinded token held by user, submitted to relay for a single write.

    Attributes:
        message: Unique nonce (hex). Each token has a distinct message.
        signature: R' || s' (hex, 33 + 32 = 65 bytes). Schnorr signature.
        issuer_pubkey: Compressed public key of the issuer (hex, 33 bytes).
    """

    message: str
    signature: str
    issuer_pubkey: str

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "signature": self.signature,
            "issuer_pubkey": self.issuer_pubkey,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpendableToken":
        return cls(
            message=d["message"],
            signature=d["signature"],
            issuer_pubkey=d["issuer_pubkey"],
        )


class SpentTokenStorage(Protocol):
    """Protocol for tracking spent tokens to prevent double-spending.

    Implementations must guarantee that check_and_mark_spent is atomic:
    concurrent calls with the same token_hash must result in exactly one
    returning True (the winner) and all others returning False.
    """

    def check_and_mark_spent(
        self, token_hash: str, relay_write_id: Optional[str] = None
    ) -> bool:
        """Atomically check if a token is unspent and mark it as spent.

        Returns True if the token was successfully marked (was NOT already spent).
        Returns False if the token was already spent (double-spend attempt).
        """
        ...

    def is_spent(self, token_hash: str) -> bool:
        """Check whether a token has been spent, without marking it."""
        ...


def generate_token_message() -> bytes:
    """Generate a unique random message (nonce) for a new token."""
    return secrets.token_bytes(32)


def generate_nonce() -> Tuple[bytes, bytes]:
    """Issuer generates a signing nonce.

    Returns:
        (nonce_secret, nonce_point): 32-byte secret scalar and 33-byte
        compressed public key point R = k·G.
    """
    k = PrivateKey()
    return k.secret, k.public_key.format(compressed=True)


def blind(
    message: bytes, issuer_pubkey: bytes, nonce_point: bytes
) -> Tuple[bytes, BlindingContext]:
    """User blinds a message for the issuer to sign.

    Args:
        message: The token message (32 bytes, from generate_token_message).
        issuer_pubkey: Issuer's compressed public key (33 bytes).
        nonce_point: Issuer's nonce point R (33 bytes compressed).

    Returns:
        (blinded_challenge, blinding_context): The 32-byte blinded challenge
        is sent to the issuer. The BlindingContext is kept secret by the user.
    """
    alpha_int = secrets.randbelow(N - 1) + 1
    beta_int = secrets.randbelow(N - 1) + 1
    alpha = alpha_int.to_bytes(32, "big")
    beta = beta_int.to_bytes(32, "big")

    R = PublicKey(nonce_point)
    P = PublicKey(issuer_pubkey)

    # R' = R + α·G + β·P
    alpha_G = PrivateKey(alpha).public_key
    beta_P = P.multiply(beta)
    R_prime = PublicKey.combine_keys([R, alpha_G, beta_P])
    R_prime_bytes = R_prime.format(compressed=True)

    # e' = SHA-256(R' || P || m) mod n
    h = hashlib.sha256(R_prime_bytes + issuer_pubkey + message).digest()
    e_prime = int.from_bytes(h, "big") % N

    # Blinded challenge: e = e' + β mod n
    e = (e_prime + beta_int) % N

    ctx = BlindingContext(
        alpha=alpha,
        beta=beta,
        blinded_nonce=R_prime_bytes,
        message=message,
    )
    return e.to_bytes(32, "big"), ctx


def sign_blinded(
    blinded_challenge: bytes, issuer_secret: bytes, nonce_secret: bytes
) -> bytes:
    """Issuer signs a blinded challenge.

    Args:
        blinded_challenge: 32-byte blinded challenge from the user.
        issuer_secret: Issuer's 32-byte secret key.
        nonce_secret: 32-byte nonce secret (from generate_nonce).

    Returns:
        32-byte blind signature scalar: s = k + e·d mod n.
    """
    k = int.from_bytes(nonce_secret, "big")
    e = int.from_bytes(blinded_challenge, "big")
    d = int.from_bytes(issuer_secret, "big")

    s = (k + e * d) % N
    return s.to_bytes(32, "big")


def unblind(
    blind_sig: bytes, ctx: BlindingContext, issuer_pubkey: bytes
) -> SpendableToken:
    """User unblinds the issuer's signature to produce a spendable token.

    Args:
        blind_sig: 32-byte blind signature from issuer.
        ctx: BlindingContext from the blind() call.
        issuer_pubkey: Issuer's compressed public key (33 bytes).

    Returns:
        SpendableToken ready to submit to a relay.
    """
    s = int.from_bytes(blind_sig, "big")
    alpha_int = int.from_bytes(ctx.alpha, "big")

    # s' = s + α mod n
    s_prime = (s + alpha_int) % N
    sig_bytes = ctx.blinded_nonce + s_prime.to_bytes(32, "big")

    return SpendableToken(
        message=ctx.message.hex(),
        signature=sig_bytes.hex(),
        issuer_pubkey=issuer_pubkey.hex(),
    )


def verify_token(token: SpendableToken) -> bool:
    """Verify a token's Schnorr signature against the issuer's public key.

    Checks: s'·G == R' + H(R'||P||m)·P

    Args:
        token: SpendableToken to verify.

    Returns:
        True if the signature is valid.
    """
    try:
        sig_bytes = bytes.fromhex(token.signature)
        if len(sig_bytes) != 65:
            return False

        R_prime_bytes = sig_bytes[:33]
        s_prime_bytes = sig_bytes[33:65]
        issuer_pubkey_bytes = bytes.fromhex(token.issuer_pubkey)
        message_bytes = bytes.fromhex(token.message)

        # Reject zero scalar (invalid signature)
        s_prime_int = int.from_bytes(s_prime_bytes, "big")
        if s_prime_int == 0 or s_prime_int >= N:
            return False

        P = PublicKey(issuer_pubkey_bytes)

        # e' = SHA-256(R' || P || m) mod n
        h = hashlib.sha256(
            R_prime_bytes + issuer_pubkey_bytes + message_bytes
        ).digest()
        e_prime = int.from_bytes(h, "big") % N

        # Left: s'·G
        lhs = PrivateKey(s_prime_bytes).public_key

        # Right: R' + e'·P
        e_prime_P = P.multiply(e_prime.to_bytes(32, "big"))
        R_prime_key = PublicKey(R_prime_bytes)
        rhs = PublicKey.combine_keys([R_prime_key, e_prime_P])

        return lhs.format(compressed=True) == rhs.format(compressed=True)
    except Exception:
        return False


def compute_token_hash(token: SpendableToken) -> str:
    """Compute SHA-256 hash of a token for spent-token tracking.

    The hash covers both message and signature, so it uniquely identifies
    a specific token instance. Used as the primary key in the spent_tokens table.
    """
    data = bytes.fromhex(token.message) + bytes.fromhex(token.signature)
    return hashlib.sha256(data).hexdigest()
