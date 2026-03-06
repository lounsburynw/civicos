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
from typing import Optional

from fastapi import Depends, HTTPException, Request

from civicos_services.core.api_keys import ApiKeyStore, ApiKeyInfo, TIER_CONFIG

logger = logging.getLogger(__name__)

# Default public rate limit (requests per minute)
PUBLIC_RATE_LIMIT = 60


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter.

    Tracks request timestamps per key. Evicts expired entries on each check.
    Suitable for single-container deployments.
    """

    def __init__(self, window_seconds: int = 60):
        self._window = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, limit: int) -> tuple[bool, int]:
        """Check if request is allowed. Returns (allowed, remaining)."""
        now = time.monotonic()
        cutoff = now - self._window

        # Evict old entries
        timestamps = self._requests[key]
        self._requests[key] = [t for t in timestamps if t > cutoff]

        count = len(self._requests[key])
        if count >= limit:
            return False, 0

        self._requests[key].append(now)
        return True, limit - count - 1


# Module-level singletons
_rate_limiter = SlidingWindowRateLimiter()
_api_key_store: Optional[ApiKeyStore] = None
_store_initialized = False


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

        # Stash for usage logging
        request.state.api_key_info = key_info
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

    request.state.api_key_info = None
    return None
