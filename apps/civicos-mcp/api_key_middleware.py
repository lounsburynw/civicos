"""
API key middleware for MCP REST endpoints.

Provides optional API key authentication with rate limiting:
- No key: public rate limit (60 req/min per IP)
- Valid key: tier-based rate limit (up to 1000 req/min)
- Invalid key: 401 Unauthorized
- No Platform DB: graceful pass-through (all requests allowed at public rate)
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request

from civicos_services.core.api_keys import ApiKeyStore, ApiKeyInfo, TIER_CONFIG, resolve_tier

logger = logging.getLogger(__name__)

# Default public rate limit (requests per minute)
PUBLIC_RATE_LIMIT = 60

# OAuth free tier limits
OAUTH_DAILY_QUOTA = 50          # queries per UTC day per session
OAUTH_PER_MINUTE = 10           # burst limit per minute per session


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter.

    Tracks request timestamps per key. Evicts expired entries on each check.
    Suitable for single-container deployments.
    """

    def __init__(self, window_seconds: int = 60):
        self._window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, limit: int, cost: int = 1) -> tuple[bool, int]:
        """Check if request is allowed. Returns (allowed, remaining).

        Args:
            key: Rate limit key (e.g., "ip:1.2.3.4" or "key:abc")
            limit: Max units per window
            cost: Number of units this request costs (default 1).
                  Multi-corpus v2 queries use cost=len(corpus).
        """
        now = time.monotonic()
        cutoff = now - self._window

        # Evict old entries
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if t > cutoff]

        count = len(self._requests[key])
        if count + cost > limit:
            return False, max(0, limit - count)

        # Record `cost` entries so multi-corpus queries consume proportionally
        self._requests[key].extend([now] * cost)
        return True, limit - count - cost


class DailyQuotaLimiter:
    """In-memory daily quota tracker.

    Tracks request counts per key per UTC day. Resets automatically at day boundary.
    Suitable for single-container deployments (Modal containers restart frequently).
    """

    def __init__(self):
        self._counts: dict[str, tuple[str, int]] = {}  # key -> (date_str, count)

    def check(self, key: str, limit: int) -> tuple[bool, int]:
        """Check if request is within daily quota. Returns (allowed, remaining)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        date_str, count = self._counts.get(key, (today, 0))
        if date_str != today:
            count = 0

        if count >= limit:
            return False, 0

        self._counts[key] = (today, count + 1)
        return True, limit - count - 1

    def get_count(self, key: str) -> int:
        """Return current day's count for a key (for logging/diagnostics)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        date_str, count = self._counts.get(key, (today, 0))
        return count if date_str == today else 0


# Module-level singletons
_rate_limiter = SlidingWindowRateLimiter()
_daily_limiter = DailyQuotaLimiter()
_api_key_store: Optional[ApiKeyStore] = None
_store_initialized = False


def charge_query_units(request: Request, extra_cost: int) -> None:
    """Charge additional rate limit units for multi-corpus v2 queries.

    The middleware already charges 1 unit. Call this from v2 endpoints
    to charge (corpus_count - 1) additional units so a 5-corpus search
    costs 5 units total.

    Args:
        request: The FastAPI request (to extract rate limit key)
        extra_cost: Additional units beyond the 1 already charged
    """
    if extra_cost <= 0:
        return

    key_info = getattr(request.state, "api_key_info", None)
    if key_info:
        rate_key = f"key:{key_info.key_id}"
    else:
        client_ip = request.client.host if request.client else "unknown"
        rate_key = f"ip:{client_ip}"

    # Add extra entries to the sliding window (units already consumed)
    now = time.monotonic()
    _rate_limiter._requests[rate_key].extend([now] * extra_cost)


def _get_store() -> Optional[ApiKeyStore]:
    """Lazy-initialize the ApiKeyStore singleton."""
    global _api_key_store, _store_initialized
    if not _store_initialized:
        _store_initialized = True
        _api_key_store = ApiKeyStore()
        if _api_key_store.available:
            logger.info("Platform DB connected — API key authentication enabled")
        else:
            logger.info("Platform DB not configured — API key authentication disabled (pass-through)")
            _api_key_store = None
    return _api_key_store


def _extract_api_key(request: Request) -> Optional[str]:
    """Extract API key from Authorization header (Bearer token)."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        if token.startswith("cvk_live_"):
            return token
    return None


async def require_api_key_or_rate_limit(request: Request) -> Optional[ApiKeyInfo]:
    """FastAPI dependency that enforces API key auth + rate limiting.

    Returns ApiKeyInfo if authenticated, None if unauthenticated (public).
    Raises HTTPException(401) for invalid keys, HTTPException(429) for rate limits.
    """
    store = _get_store()
    raw_key = _extract_api_key(request)

    if raw_key:
        # Key provided — validate it
        if store is None:
            # No Platform DB but key provided — can't validate, reject
            raise HTTPException(
                status_code=503,
                detail="API key validation unavailable. Remove the Authorization header for public access.",
            )

        key_info = store.validate_key(raw_key)
        if key_info is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired API key.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Rate limit by key_id
        rate_limit = key_info.rate_limit_per_minute
        allowed, remaining = _rate_limiter.check(f"key:{key_info.key_id}", rate_limit)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({rate_limit} req/min for {key_info.tier} tier).",
                headers={"Retry-After": "60"},
            )

        # Update last_used (fire-and-forget)
        store.update_last_used(key_info.key_id)

        # Stash tier and key info for downstream access control
        request.state.auth_tier = resolve_tier(key_info.tier)
        request.state.api_key_info = key_info

        # Jurisdiction scoping: reject if key is restricted to specific jurisdictions
        if key_info.jurisdictions:
            server_jurisdiction = getattr(request.app.state, "jurisdiction", None)
            if server_jurisdiction and server_jurisdiction not in key_info.jurisdictions:
                raise HTTPException(
                    status_code=403,
                    detail=f"API key not authorized for jurisdiction '{server_jurisdiction}'. "
                           f"Allowed: {', '.join(key_info.jurisdictions)}",
                )

        return key_info

    # No key provided — public access with IP-based rate limit
    client_ip = request.client.host if request.client else "unknown"
    allowed, remaining = _rate_limiter.check(f"ip:{client_ip}", PUBLIC_RATE_LIMIT)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({PUBLIC_RATE_LIMIT} req/min). Provide an API key for higher limits.",
            headers={"Retry-After": "60"},
        )

    request.state.auth_tier = "open"
    request.state.api_key_info = None
    return None


def check_oauth_rate_limit(key_id: str) -> dict:
    """Check per-minute burst and daily quota for an OAuth session.

    Args:
        key_id: The OAuth key identifier (e.g., "oauth:civic_abc123").

    Returns:
        dict with keys:
            allowed (bool): Whether the request should proceed.
            error (str|None): Error type if blocked ("daily_quota_exceeded" or "rate_limit_exceeded").
            remaining_daily (int): Remaining daily quota.
            remaining_minute (int): Remaining per-minute allowance.
            retry_after (int|None): Seconds to wait before retrying, if blocked.
    """
    # Per-minute burst check
    minute_allowed, remaining_minute = _rate_limiter.check(
        f"mcp:{key_id}", OAUTH_PER_MINUTE
    )
    if not minute_allowed:
        return {
            "allowed": False,
            "error": "rate_limit_exceeded",
            "remaining_daily": _daily_limiter.get_count(key_id),
            "remaining_minute": 0,
            "retry_after": 60,
        }

    # Daily quota check
    daily_allowed, remaining_daily = _daily_limiter.check(key_id, OAUTH_DAILY_QUOTA)

    # Log when approaching daily quota (80% threshold)
    if daily_allowed and remaining_daily <= int(OAUTH_DAILY_QUOTA * 0.2):
        logger.info(
            "OAuth session %s approaching daily quota: %d/%d used",
            key_id, OAUTH_DAILY_QUOTA - remaining_daily, OAUTH_DAILY_QUOTA,
        )

    if not daily_allowed:
        # Seconds until midnight UTC
        now = datetime.now(timezone.utc)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_until_reset = int((midnight.timestamp() + 86400) - now.timestamp())
        return {
            "allowed": False,
            "error": "daily_quota_exceeded",
            "remaining_daily": 0,
            "remaining_minute": remaining_minute,
            "retry_after": seconds_until_reset,
        }

    return {
        "allowed": True,
        "error": None,
        "remaining_daily": remaining_daily,
        "remaining_minute": remaining_minute,
        "retry_after": None,
    }
