"""
Token purchase checkout — Stripe one-time payments for blinded token bundles.

Creates Stripe Checkout sessions in `payment` mode (not subscription).
Uses the Stripe session as source of truth — no new DB tables needed.
The extension polls `check_status` after redirect, then requests tokens
from the relay via the existing blind signing protocol.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory double-claim guard. Prevents the same checkout session from
# being used to acquire tokens more than once. For production scale,
# replace with a DB-backed set.
_claimed_sessions: set[str] = set()


def _get_stripe():
    """Lazily import and configure stripe."""
    import stripe

    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    return stripe


def get_bundle_size() -> int:
    """Number of tokens per purchase bundle."""
    return int(os.getenv("CIVICOS_TOKEN_BUNDLE_SIZE", "50"))


def create_token_checkout(
    count: Optional[int] = None,
    success_url: str = "https://civicos.org/tokens/success",
    cancel_url: str = "https://civicos.org/tokens/cancel",
) -> dict:
    """Create a Stripe Checkout session for a one-time token purchase.

    Args:
        count: Number of tokens to purchase. Defaults to bundle size.
        success_url: Redirect URL on successful payment.
        cancel_url: Redirect URL on cancellation.

    Returns:
        Dict with checkout_url, session_id, and token_count.

    Raises:
        ValueError: If STRIPE_PRICE_TOKENS is not configured.
        RuntimeError: If Stripe is not configured.
    """
    stripe = _get_stripe()

    price_id = os.getenv("STRIPE_PRICE_TOKENS")
    if not price_id:
        raise ValueError(
            "No Stripe price configured for tokens. Set STRIPE_PRICE_TOKENS"
        )

    token_count = count or get_bundle_size()

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "type": "token_purchase",
            "token_count": str(token_count),
        },
    )

    logger.info(
        "Created token checkout session %s (count=%d)", session.id, token_count
    )
    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "token_count": token_count,
    }


def check_token_checkout_status(session_id: str) -> dict:
    """Check whether a token checkout session has been paid.

    Args:
        session_id: Stripe Checkout session ID.

    Returns:
        Dict with status ('pending', 'paid', 'expired'), token_count, and claimed flag.

    Raises:
        RuntimeError: If Stripe is not configured.
        ValueError: If the session is not a token purchase or not found.
    """
    stripe = _get_stripe()

    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except Exception as e:
        raise ValueError(f"Could not retrieve checkout session: {e}")

    # Verify this is a token purchase session
    metadata = session.get("metadata", {}) if isinstance(session, dict) else getattr(session, "metadata", {})
    if metadata.get("type") != "token_purchase":
        raise ValueError("Session is not a token purchase")

    token_count = int(metadata.get("token_count", get_bundle_size()))

    # Map Stripe payment_status to our status
    payment_status = session.get("payment_status", "") if isinstance(session, dict) else getattr(session, "payment_status", "")
    status_val = session.get("status", "") if isinstance(session, dict) else getattr(session, "status", "")

    if payment_status == "paid":
        status = "paid"
    elif status_val == "expired":
        status = "expired"
    else:
        status = "pending"

    return {
        "status": status,
        "token_count": token_count,
        "claimed": session_id in _claimed_sessions,
    }


def mark_claimed(session_id: str) -> None:
    """Mark a checkout session as claimed (tokens acquired)."""
    _claimed_sessions.add(session_id)
    logger.info("Marked token checkout %s as claimed", session_id)
