"""
Issuance voucher — HMAC-SHA256-signed proof of payment for token acquisition.

After Stripe payment is confirmed, the services API generates a voucher
containing {session_id, token_count, expires_at}. The extension presents
this voucher to the relay, which verifies the HMAC signature before
issuing blinded tokens. Both services share VOUCHER_HMAC_SECRET.

Voucher format: base64url(payload).hmac_hex
  payload: session_id:token_count:expires_at_unix
  signature: HMAC-SHA256(secret, payload)
"""

import base64
import hashlib
import hmac
import os
import time

_VOUCHER_TTL_SECONDS = 300  # 5 minutes default


def _get_hmac_secret() -> bytes:
    """Read the shared HMAC secret from environment."""
    secret = os.getenv("VOUCHER_HMAC_SECRET", "")
    if not secret:
        raise RuntimeError("VOUCHER_HMAC_SECRET not configured")
    return secret.encode()


def generate_voucher(
    session_id: str,
    token_count: int,
    ttl_seconds: int = _VOUCHER_TTL_SECONDS,
) -> str:
    """Generate an HMAC-signed voucher for token issuance.

    Args:
        session_id: Stripe checkout session ID.
        token_count: Number of tokens authorized.
        ttl_seconds: Voucher validity window (default 5 minutes).

    Returns:
        Voucher string: base64url(payload).hmac_hex
    """
    secret = _get_hmac_secret()
    expires_at = int(time.time()) + ttl_seconds
    payload = f"{session_id}:{token_count}:{expires_at}"
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"
