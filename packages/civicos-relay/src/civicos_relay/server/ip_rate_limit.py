"""HTTP-level per-IP rate limiting middleware.

Runs before request body parsing or crypto verification as a coarse
first line of defense against brute-force spam.  Only applies to
POST requests on write endpoints (``/coordination/*``).

Uses an in-memory counter (no database) — IPs are ephemeral and this
layer is intentionally lightweight.
"""

import logging
import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Default: 100 POST requests per IP per window on write endpoints
DEFAULT_IP_RATE_LIMIT = 100
# Default window: 1 hour (seconds)
DEFAULT_IP_RATE_WINDOW = 3600


class InMemoryIPRateLimiter:
    """Sliding-window counter per IP address.

    Tracks request timestamps per IP within a configurable window.
    Periodically cleans up expired entries.
    """

    def __init__(self, max_requests: int = DEFAULT_IP_RATE_LIMIT,
                 window_seconds: int = DEFAULT_IP_RATE_WINDOW):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # {ip: [timestamp, ...]}
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()
        self._cleanup_interval = 300  # cleanup every 5 minutes

    def is_allowed(self, ip: str) -> bool:
        """Check if a request from this IP is allowed. Increments counter if so."""
        now = time.monotonic()

        # Periodic cleanup of stale IPs
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup(now)

        # Trim expired timestamps for this IP
        cutoff = now - self.window_seconds
        timestamps = self._requests[ip]
        # Remove timestamps older than window
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)

        if len(timestamps) >= self.max_requests:
            return False

        timestamps.append(now)
        return True

    def _cleanup(self, now: float):
        """Remove IPs with no recent requests."""
        cutoff = now - self.window_seconds
        empty_ips = []
        for ip, timestamps in self._requests.items():
            # Trim old timestamps
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)
            if not timestamps:
                empty_ips.append(ip)
        for ip in empty_ips:
            del self._requests[ip]
        self._last_cleanup = now

    def get_count(self, ip: str) -> int:
        """Current request count for an IP (for diagnostics)."""
        now = time.monotonic()
        cutoff = now - self.window_seconds
        timestamps = self._requests.get(ip, [])
        return sum(1 for t in timestamps if t >= cutoff)


class IPRateLimitMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that enforces per-IP rate limits on write endpoints.

    Only applies to POST requests whose path starts with ``/coordination/``.
    GET/OPTIONS/HEAD requests pass through unconditionally.
    """

    def __init__(self, app, max_requests: int = DEFAULT_IP_RATE_LIMIT,
                 window_seconds: int = DEFAULT_IP_RATE_WINDOW):
        super().__init__(app)
        self._limiter = InMemoryIPRateLimiter(
            max_requests=max_requests,
            window_seconds=window_seconds,
        )
        logger.info(
            "IP rate limiting enabled: %d requests per %ds window on write endpoints",
            max_requests, window_seconds,
        )

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract real client IP, respecting proxy headers."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        return request.client.host if request.client else "unknown"

    async def dispatch(self, request: Request, call_next):
        # Only rate-limit POST requests to coordination write endpoints
        if request.method == "POST" and request.url.path.startswith("/coordination/"):
            client_ip = self._get_client_ip(request)
            if not self._limiter.is_allowed(client_ip):
                logger.warning("IP rate limit exceeded: %s on %s", client_ip, request.url.path)
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Too many requests from this IP address. Please try again later.",
                        "retry_after_seconds": self._limiter.window_seconds,
                    },
                )

        return await call_next(request)
