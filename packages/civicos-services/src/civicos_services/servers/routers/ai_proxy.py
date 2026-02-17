"""AI proxy endpoint for zero-config AI drafting.

Authenticates via Nostr-signed requests (reusing existing identity),
forwards to Anthropic with server-side API key. Users get AI drafting
with zero configuration — no API key needed.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

# Rate limits
DAILY_LIMIT_PER_NPUB = 20
DAILY_COST_CAP = 5.0  # $5/day global cap
COST_PER_REQUEST = 0.01  # ~$0.01 per Sonnet request
MAX_AGE_SECONDS = 300  # 5-minute replay window
AI_DRAFT_KIND = 24242  # Custom Nostr kind for AI proxy auth

# In-memory rate tracking (resets on container restart, fine for pilot)
_rate_limits: dict[str, dict] = {}
_global_cost: dict[str, float | str] = {"total": 0.0, "reset_date": ""}


class AIDraftRequest(BaseModel):
    prompt: str
    system_prompt: Optional[str] = None
    public_key: str
    signature: str
    created_at: int


class AIDraftResponse(BaseModel):
    success: bool
    text: Optional[str] = None
    error: Optional[str] = None
    provider: str = "civicos"


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _check_rate_limit(public_key: str) -> tuple[bool, Optional[str]]:
    """Check per-npub and global rate limits."""
    today = _today_str()

    # Reset global cost if new day
    if _global_cost.get("reset_date") != today:
        _global_cost["total"] = 0.0
        _global_cost["reset_date"] = today

    # Global cost cap
    if float(_global_cost["total"]) >= DAILY_COST_CAP:
        return False, "Service temporarily unavailable — daily capacity reached. Try again tomorrow."

    # Per-npub daily limit
    entry = _rate_limits.get(public_key)
    if not entry or entry.get("reset_date") != today:
        _rate_limits[public_key] = {"count": 0, "reset_date": today}

    if _rate_limits[public_key]["count"] >= DAILY_LIMIT_PER_NPUB:
        return False, f"Rate limit exceeded — {DAILY_LIMIT_PER_NPUB} drafts per day. Try again tomorrow."

    return True, None


def _record_usage(public_key: str) -> None:
    """Record a successful request for rate limiting."""
    today = _today_str()
    if public_key not in _rate_limits or _rate_limits[public_key].get("reset_date") != today:
        _rate_limits[public_key] = {"count": 0, "reset_date": today}
    _rate_limits[public_key]["count"] += 1
    _global_cost["total"] = float(_global_cost.get("total", 0.0)) + COST_PER_REQUEST


def _verify_ai_signature(public_key: str, signature: str, created_at: int) -> bool:
    """Verify Nostr event signature for AI proxy auth.

    The extension signs a Nostr event (kind 24242) with:
      content = "civicos:ai:v1:{public_key}:{created_at}"
      tags = [["action", "ai_draft"]]
    The signature is over the event ID (SHA-256 of serialized event).
    """
    try:
        from civicos_relay.voice.crypto import (
            _check_key_sig,
            _compute_nostr_event_id,
            _schnorr_verify,
        )

        if not _check_key_sig(public_key, signature):
            return False

        tags = [["action", "ai_draft"]]
        content = f"civicos:ai:v1:{public_key}:{created_at}"
        event_id = _compute_nostr_event_id(public_key, created_at, AI_DRAFT_KIND, tags, content)
        return _schnorr_verify(public_key, signature, event_id)
    except Exception:
        logger.exception("Signature verification error")
        return False


@router.post("/ai/draft", response_model=AIDraftResponse)
async def ai_draft(request: AIDraftRequest):
    """Generate an AI draft using the CivicOS proxy.

    Authenticates via Nostr signature, rate-limits per npub,
    and forwards to Anthropic's Claude API.
    """
    # 1. Replay protection — reject stale timestamps
    now = int(time.time())
    if abs(now - request.created_at) > MAX_AGE_SECONDS:
        raise HTTPException(status_code=400, detail="Request expired — timestamp too old")

    # 2. Verify Nostr signature
    if not _verify_ai_signature(request.public_key, request.signature, request.created_at):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. Rate limits
    allowed, error_msg = _check_rate_limit(request.public_key)
    if not allowed:
        raise HTTPException(status_code=429, detail=error_msg)

    # 4. Forward to Anthropic
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI service not configured")

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        kwargs: dict = {
            "model": "claude-sonnet-4-5-20250929",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system_prompt:
            kwargs["system"] = request.system_prompt

        response = client.messages.create(**kwargs)
        text = response.content[0].text if response.content else None

        if not text:
            return AIDraftResponse(success=False, error="AI returned empty response")

        _record_usage(request.public_key)
        logger.info("ai_draft_success", extra={"npub_prefix": request.public_key[:8]})
        return AIDraftResponse(success=True, text=text)

    except anthropic.RateLimitError:
        return AIDraftResponse(success=False, error="AI service is busy — please try again in a moment")
    except Exception as e:
        logger.exception("AI draft error")
        return AIDraftResponse(success=False, error=f"AI service error: {str(e)[:200]}")
