"""
Stripe billing integration for CivicOS.

Handles checkout session creation and webhook processing.
On successful payment, provisions a new API key automatically.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Tier mapping: Stripe price ID -> CivicOS tier
# Configured via environment variables (STRIPE_PRICE_JOURNALIST, etc.)
_PRICE_TO_TIER: Optional[dict] = None


def _get_price_to_tier() -> dict:
    """Lazily build price-to-tier mapping from env vars."""
    global _PRICE_TO_TIER
    if _PRICE_TO_TIER is not None:
        return _PRICE_TO_TIER
    _PRICE_TO_TIER = {}
    for tier in ("journalist", "organization", "city", "api"):
        price_id = os.getenv(f"STRIPE_PRICE_{tier.upper()}")
        if price_id:
            _PRICE_TO_TIER[price_id] = tier
    return _PRICE_TO_TIER


def _get_stripe():
    """Lazily import and configure stripe."""
    import stripe

    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        raise RuntimeError("STRIPE_SECRET_KEY not configured")
    return stripe


def create_checkout_session(
    tier: str,
    email: str,
    success_url: str = "https://civicos.org/billing/success",
    cancel_url: str = "https://civicos.org/billing/cancel",
) -> str:
    """Create a Stripe Checkout session for a subscription.

    Args:
        tier: One of journalist, organization, city, api.
        email: Customer email for the checkout session.
        success_url: Redirect URL on successful payment.
        cancel_url: Redirect URL on cancellation.

    Returns:
        Stripe Checkout session URL.

    Raises:
        ValueError: If tier has no configured price.
        RuntimeError: If Stripe is not configured.
    """
    stripe = _get_stripe()

    price_id = os.getenv(f"STRIPE_PRICE_{tier.upper()}")
    if not price_id:
        raise ValueError(f"No Stripe price configured for tier '{tier}'. Set STRIPE_PRICE_{tier.upper()}")

    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        customer_email=email,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"tier": tier},
    )

    logger.info("Created Stripe checkout session for %s (tier=%s)", email, tier)
    return session.url


def handle_webhook(payload: bytes, signature: str) -> dict:
    """Process a Stripe webhook event.

    Args:
        payload: Raw request body bytes.
        signature: Stripe-Signature header value.

    Returns:
        Dict with action taken (for logging).

    Raises:
        ValueError: If signature verification fails.
    """
    stripe = _get_stripe()

    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET not configured")

    event = stripe.Webhook.construct_event(payload, signature, webhook_secret)

    event_type = event["type"]
    logger.info("Processing Stripe webhook: %s", event_type)

    if event_type == "checkout.session.completed":
        return _handle_checkout_completed(event["data"]["object"])
    elif event_type == "customer.subscription.deleted":
        return _handle_subscription_deleted(event["data"]["object"])
    elif event_type == "customer.subscription.updated":
        return _handle_subscription_updated(event["data"]["object"])
    elif event_type == "invoice.payment_failed":
        return _handle_payment_failed(event["data"]["object"])
    else:
        logger.debug("Unhandled Stripe event: %s", event_type)
        return {"action": "ignored", "event_type": event_type}


def _handle_checkout_completed(session: dict) -> dict:
    """Checkout completed -> create API key for the customer."""
    from .api_keys import get_api_key_store

    store = get_api_key_store()

    customer_id = session.get("customer")
    customer_email = session.get("customer_email") or session.get("customer_details", {}).get("email", "")
    subscription_id = session.get("subscription")
    tier = session.get("metadata", {}).get("tier", "journalist")

    # Check if this customer already has a key
    existing = store.get_key_by_stripe_customer(customer_id)
    if existing:
        logger.info("Customer %s already has key %s, updating", customer_id, existing["key_id"])
        store.update_key_stripe(
            existing["key_id"],
            stripe_subscription_id=subscription_id,
            tier=tier,
        )
        store._set_status(existing["key_id"], "active")
        return {"action": "reactivated", "key_id": existing["key_id"], "tier": tier}

    # Create a new API key
    result = store.create_key(
        name=customer_email.split("@")[0] if customer_email else "Customer",
        email=customer_email,
        tier=tier,
        stripe_customer_id=customer_id,
        stripe_subscription_id=subscription_id,
    )

    if result:
        key_id, raw_key = result
        logger.info("Provisioned key %s for Stripe customer %s (tier=%s)", key_id, customer_id, tier)
        # Note: raw_key delivery is manual for now (admin sends via email)
        # The key_id is logged for admin reference
        return {"action": "key_created", "key_id": key_id, "tier": tier, "email": customer_email}
    else:
        logger.error("Failed to create key for Stripe customer %s", customer_id)
        return {"action": "key_creation_failed", "customer_id": customer_id}


def _handle_subscription_deleted(subscription: dict) -> dict:
    """Subscription cancelled -> suspend the API key."""
    from .api_keys import get_api_key_store

    store = get_api_key_store()
    customer_id = subscription.get("customer")

    existing = store.get_key_by_stripe_customer(customer_id)
    if existing:
        store.suspend_key(existing["key_id"])
        logger.info("Suspended key %s (subscription cancelled)", existing["key_id"])
        return {"action": "key_suspended", "key_id": existing["key_id"]}
    return {"action": "no_key_found", "customer_id": customer_id}


def _handle_subscription_updated(subscription: dict) -> dict:
    """Subscription updated -> update tier/limits if plan changed."""
    from .api_keys import get_api_key_store

    store = get_api_key_store()
    customer_id = subscription.get("customer")

    existing = store.get_key_by_stripe_customer(customer_id)
    if not existing:
        return {"action": "no_key_found", "customer_id": customer_id}

    # Check if the price changed (tier change)
    items = subscription.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id")
        price_to_tier = _get_price_to_tier()
        new_tier = price_to_tier.get(price_id)
        if new_tier and new_tier != existing.get("tier"):
            store.update_key_stripe(existing["key_id"], tier=new_tier)
            logger.info("Updated key %s tier to %s", existing["key_id"], new_tier)
            return {"action": "tier_updated", "key_id": existing["key_id"], "new_tier": new_tier}

    return {"action": "no_change", "key_id": existing["key_id"]}


def _handle_payment_failed(invoice: dict) -> dict:
    """Payment failed -> log for follow-up (don't auto-suspend yet)."""
    customer_id = invoice.get("customer")
    logger.warning(
        "Payment failed for Stripe customer %s (invoice %s). Manual follow-up needed.",
        customer_id,
        invoice.get("id"),
    )
    return {"action": "payment_failed_logged", "customer_id": customer_id}
