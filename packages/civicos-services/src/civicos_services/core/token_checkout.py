"""
Token purchase checkout — Stripe one-time payments for blinded token bundles.

Creates Stripe Checkout sessions in `payment` mode (not subscription).
Uses the Stripe session as source of truth — no new DB tables needed.
The extension polls `check_status` after redirect, then requests tokens
from the relay via the existing blind signing protocol.

Security:
- claim_secret: random token returned to the extension at checkout creation,
  its SHA-256 hash stored in Stripe session metadata. Required for all
  subsequent status checks — acts as a bearer token proving session ownership.
- Double-claim prevention: persisted in Stripe metadata (survives restarts,
  works across instances).
"""

import hashlib
import logging
import os
import secrets
from typing import Optional

import stripe

from .voucher import generate_voucher

logger = logging.getLogger(__name__)


def _configure_stripe() -> None:
    """Set Stripe API key from environment. Raises if not configured."""
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")


def _get_session_attr(session: object, key: str, default: object = "") -> object:
    """Extract an attribute from a Stripe session object consistently.

    Stripe SDK returns object instances with attributes, but mocks and
    raw dicts use key access. This helper handles both uniformly.
    """
    if isinstance(session, dict):
        return session.get(key, default)
    return getattr(session, key, default)


def get_bundle_size() -> int:
    """Number of tokens per purchase bundle."""
    return int(os.getenv("CIVICOS_TOKEN_BUNDLE_SIZE", "50"))


def _get_success_url() -> str:
    """Token checkout success redirect URL from environment."""
    return os.getenv("CIVICOS_TOKEN_SUCCESS_URL", "https://civicos.org/tokens/success")


def _get_cancel_url() -> str:
    """Token checkout cancel redirect URL from environment."""
    return os.getenv("CIVICOS_TOKEN_CANCEL_URL", "https://civicos.org/tokens/cancel")


def create_token_checkout(
    count: Optional[int] = None,
    success_url: Optional[str] = None,
    cancel_url: Optional[str] = None,
) -> dict:
    """Create a Stripe Checkout session for a one-time token purchase.

    Args:
        count: Number of tokens to purchase. Defaults to bundle size.
        success_url: Redirect URL on successful payment. Defaults to env var.
        cancel_url: Redirect URL on cancellation. Defaults to env var.

    Returns:
        Dict with checkout_url, session_id, token_count, and claim_secret.
        The claim_secret must be stored by the caller and presented when
        checking status — it proves session ownership.

    Raises:
        ValueError: If STRIPE_PRICE_TOKENS is not configured.
        RuntimeError: If Stripe is not configured.
    """
    _configure_stripe()

    price_id = os.getenv("STRIPE_PRICE_TOKENS")
    if not price_id:
        raise ValueError(
            "No Stripe price configured for tokens. Set STRIPE_PRICE_TOKENS"
        )

    token_count = count or get_bundle_size()
    claim_secret = secrets.token_urlsafe(32)
    claim_secret_hash = hashlib.sha256(claim_secret.encode()).hexdigest()

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url or _get_success_url(),
        cancel_url=cancel_url or _get_cancel_url(),
        metadata={
            "type": "token_purchase",
            "token_count": str(token_count),
            "claim_secret_hash": claim_secret_hash,
            "claimed": "false",
        },
    )

    logger.info(
        "Created token checkout session %s (count=%d)", session.id, token_count
    )
    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "token_count": token_count,
        "claim_secret": claim_secret,
    }


def check_token_checkout_status(session_id: str, claim_secret: str) -> dict:
    """Check whether a token checkout session has been paid.

    Args:
        session_id: Stripe Checkout session ID.
        claim_secret: Secret returned at checkout creation. Proves ownership.

    Returns:
        Dict with status ('pending', 'paid', 'expired'), token_count, and claimed flag.

    Raises:
        RuntimeError: If Stripe is not configured.
        ValueError: If the session is not a token purchase, not found,
                     or claim_secret doesn't match.
    """
    _configure_stripe()

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.InvalidRequestError as e:
        raise ValueError(f"Could not retrieve checkout session: {e}")

    metadata = _get_session_attr(session, "metadata", {})

    # Verify this is a token purchase session
    if metadata.get("type") != "token_purchase":
        raise ValueError("Session is not a token purchase")

    # Verify claim_secret ownership
    expected_hash = metadata.get("claim_secret_hash", "")
    provided_hash = hashlib.sha256(claim_secret.encode()).hexdigest()
    if not expected_hash or provided_hash != expected_hash:
        raise ValueError("Invalid claim secret")

    token_count = int(metadata.get("token_count", get_bundle_size()))

    # Map Stripe payment_status to our status
    payment_status = _get_session_attr(session, "payment_status")
    status_val = _get_session_attr(session, "status")

    if payment_status == "paid":
        status = "paid"
    elif status_val == "expired":
        status = "expired"
    else:
        status = "pending"

    # Generate voucher for paid, unclaimed sessions
    voucher = None
    claimed = metadata.get("claimed") == "true"
    if status == "paid" and not claimed:
        try:
            voucher = generate_voucher(session_id, token_count)
        except RuntimeError:
            logger.warning(
                "VOUCHER_HMAC_SECRET not configured — paid session %s "
                "will not receive a voucher. Token acquisition will fail "
                "if the relay requires voucher auth.",
                session_id,
            )

    return {
        "status": status,
        "token_count": token_count,
        "claimed": claimed,
        "voucher": voucher,
    }


def mark_claimed(session_id: str) -> None:
    """Mark a checkout session as claimed (tokens acquired).

    Persists the claim flag in Stripe session metadata so it survives
    server restarts and works across multiple instances.
    """
    _configure_stripe()
    stripe.checkout.Session.modify(session_id, metadata={"claimed": "true"})
    logger.info("Marked token checkout %s as claimed", session_id)
