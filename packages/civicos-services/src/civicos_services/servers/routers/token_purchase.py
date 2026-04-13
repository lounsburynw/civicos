"""
Token purchase router: public endpoints for buying blinded tokens via Stripe.

Endpoints:
- POST /tokens/checkout - Create a Stripe Checkout session for token purchase
- GET /tokens/status/{session_id} - Check payment status of a checkout session

Security: the checkout endpoint returns a claim_secret that the extension
must present on all subsequent status checks. This proves session ownership
without requiring full identity auth.
"""

import logging

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter()


class TokenCheckoutRequest(BaseModel):
    """Request to create a token purchase checkout session."""

    count: Optional[int] = None  # Defaults to CIVICOS_TOKEN_BUNDLE_SIZE
    success_url: Optional[str] = None  # Defaults to CIVICOS_TOKEN_SUCCESS_URL
    cancel_url: Optional[str] = None  # Defaults to CIVICOS_TOKEN_CANCEL_URL


class TokenCheckoutResponse(BaseModel):
    """Response with checkout URL and session info."""

    checkout_url: str
    session_id: str
    token_count: int
    claim_secret: str


class TokenStatusResponse(BaseModel):
    """Response with payment status."""

    status: str  # pending, paid, expired
    token_count: int
    claimed: bool
    voucher: Optional[str] = None


@router.post("/tokens/checkout", response_model=TokenCheckoutResponse)
async def create_token_checkout(request: TokenCheckoutRequest):
    """Create a Stripe Checkout session for a one-time token purchase.

    Public endpoint — no identity auth required.
    Returns a claim_secret that must be presented on status checks.
    """
    try:
        from ...core.token_checkout import create_token_checkout as _create

        result = _create(
            count=request.count,
            success_url=request.success_url,
            cancel_url=request.cancel_url,
        )
        return TokenCheckoutResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Token checkout creation failed: %s", e)
        raise HTTPException(
            status_code=500, detail="Failed to create checkout session"
        )


@router.get("/tokens/status/{session_id}", response_model=TokenStatusResponse)
async def check_token_status(
    session_id: str,
    x_claim_secret: str = Header(..., alias="X-Claim-Secret"),
):
    """Check payment status of a token checkout session.

    Requires X-Claim-Secret header (returned at checkout creation).
    The extension polls this after redirecting the user to Stripe.
    """
    try:
        from ...core.token_checkout import (
            check_token_checkout_status,
            mark_claimed,
        )

        result = check_token_checkout_status(session_id, x_claim_secret)

        # Auto-mark as claimed when status is paid and not yet claimed
        if result["status"] == "paid" and not result["claimed"]:
            mark_claimed(session_id)
            result["claimed"] = True

        return TokenStatusResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Token status check failed: %s", e)
        raise HTTPException(
            status_code=500, detail="Failed to check checkout status"
        )
