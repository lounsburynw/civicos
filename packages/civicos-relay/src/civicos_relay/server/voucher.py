"""
Voucher verification and tracking for token issuance gate.

The relay verifies HMAC-signed vouchers issued by the services API
before allowing blind token signing. A VoucherTracker enforces the
token count limit per session.

Voucher format: base64url(payload).hmac_hex
  payload: session_id:token_count:expires_at_unix
  signature: HMAC-SHA256(secret, payload)
"""

import base64
import hashlib
import hmac as hmac_mod
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class VoucherClaims:
    """Parsed and verified voucher contents."""

    session_id: str
    token_count: int
    expires_at: int


def verify_voucher(voucher: str, hmac_secret: bytes) -> VoucherClaims:
    """Verify an HMAC-signed voucher and extract its claims.

    Args:
        voucher: The voucher string (base64url.hmac_hex).
        hmac_secret: Shared HMAC secret.

    Returns:
        VoucherClaims with session_id, token_count, expires_at.

    Raises:
        ValueError: If the voucher is malformed, tampered, or expired.
    """
    parts = voucher.split(".")
    if len(parts) != 2:
        raise ValueError("Malformed voucher: expected payload.signature")

    payload_b64, provided_sig = parts

    # Decode payload
    try:
        payload = base64.urlsafe_b64decode(payload_b64).decode()
    except Exception:
        raise ValueError("Malformed voucher: invalid base64 payload")

    # Verify HMAC
    expected_sig = hmac_mod.new(
        hmac_secret, payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac_mod.compare_digest(expected_sig, provided_sig):
        raise ValueError("Invalid voucher signature")

    # Parse payload
    fields = payload.split(":")
    if len(fields) != 3:
        raise ValueError("Malformed voucher payload")

    try:
        session_id = fields[0]
        token_count = int(fields[1])
        expires_at = int(fields[2])
    except (ValueError, IndexError):
        raise ValueError("Malformed voucher payload fields")

    # Check expiry
    if time.time() > expires_at:
        raise ValueError("Voucher expired")

    return VoucherClaims(
        session_id=session_id,
        token_count=token_count,
        expires_at=expires_at,
    )


class VoucherTracker:
    """Tracks how many tokens have been issued per voucher session.

    In-memory counter. If the relay restarts mid-acquisition, the counter
    resets and the user can re-acquire (acceptable for MVP — the window
    between payment and acquisition is typically seconds).
    """

    def __init__(self) -> None:
        self._remaining: dict[str, int] = {}

    def try_decrement(self, session_id: str, token_count: int) -> bool:
        """Attempt to claim one token from a session's allowance.

        On first call for a session_id, initializes the counter to token_count.
        Returns True if a token can be issued, False if the allowance is exhausted.
        """
        if session_id not in self._remaining:
            self._remaining[session_id] = token_count

        if self._remaining[session_id] <= 0:
            return False

        self._remaining[session_id] -= 1
        return True

    def remaining(self, session_id: str) -> int:
        """How many tokens remain for this session."""
        return self._remaining.get(session_id, 0)
