"""
Billing router: Stripe checkout and webhook endpoints.

Endpoints:
- POST /checkout - Create a Stripe Checkout session
- POST /webhook - Stripe webhook receiver
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr

from .dependencies import verify_auth

logger = logging.getLogger(__name__)

router = APIRouter()


class CheckoutRequest(BaseModel):
    """Request to create a checkout session."""

    tier: str  # journalist, organization, city, api
    email: str
    success_url: str = "https://civicos.org/billing/success"
    cancel_url: str = "https://civicos.org/billing/cancel"


class CheckoutResponse(BaseModel):
    """Response with checkout session URL."""

    checkout_url: str
    tier: str


@router.post("/billing/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    token: str = Depends(verify_auth),
):
    """Create a Stripe Checkout session for a subscription.

    Returns a URL to redirect the customer to Stripe's hosted checkout page.
    Requires admin authentication.
    """
    valid_tiers = ("journalist", "organization", "city", "api")
    if request.tier not in valid_tiers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{request.tier}'. Must be one of: {', '.join(valid_tiers)}",
        )

    try:
        from ...core.stripe_billing import create_checkout_session

        checkout_url = create_checkout_session(
            tier=request.tier,
            email=request.email,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )
        return CheckoutResponse(checkout_url=checkout_url, tier=request.tier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Checkout session creation failed: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@router.post("/billing/webhook")
async def stripe_webhook(request: Request):
    """Stripe webhook receiver.

    Processes events:
    - checkout.session.completed -> provisions API key
    - customer.subscription.deleted -> suspends key
    - customer.subscription.updated -> updates tier
    - invoice.payment_failed -> logs for follow-up

    No authentication (Stripe signature verification is used instead).
    """
    payload = await request.body()
    signature = request.headers.get("Stripe-Signature", "")

    if not signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")

    try:
        from ...core.stripe_billing import handle_webhook

        result = handle_webhook(payload, signature)
        logger.info("Webhook processed: %s", result)
        return {"status": "ok", **result}
    except ValueError as e:
        logger.warning("Webhook signature verification failed: %s", e)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Webhook processing failed: %s", e)
        raise HTTPException(status_code=500, detail="Webhook processing failed")
