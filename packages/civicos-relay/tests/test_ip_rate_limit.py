"""Tests for HTTP-level per-IP rate limiting middleware."""

import pytest
import sys
import time
from unittest.mock import MagicMock, AsyncMock, patch

# Import directly from the module to avoid pulling in the full server __init__
# which has heavy dependencies (attestation, crypto, etc.)
import importlib
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "civicos_relay.server.ip_rate_limit",
    "packages/civicos-relay/src/civicos_relay/server/ip_rate_limit.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

InMemoryIPRateLimiter = _mod.InMemoryIPRateLimiter
IPRateLimitMiddleware = _mod.IPRateLimitMiddleware

from starlette.testclient import TestClient
from fastapi import FastAPI


class TestInMemoryIPRateLimiter:
    def test_under_limit_allowed(self):
        limiter = InMemoryIPRateLimiter(max_requests=5, window_seconds=60)
        for _ in range(5):
            assert limiter.is_allowed("192.168.1.1")

    def test_over_limit_blocked(self):
        limiter = InMemoryIPRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            assert limiter.is_allowed("192.168.1.1")
        assert not limiter.is_allowed("192.168.1.1")

    def test_different_ips_independent(self):
        limiter = InMemoryIPRateLimiter(max_requests=2, window_seconds=60)
        for _ in range(2):
            limiter.is_allowed("192.168.1.1")
        assert not limiter.is_allowed("192.168.1.1")
        # Different IP should still have quota
        assert limiter.is_allowed("192.168.1.2")

    def test_window_expiry(self):
        limiter = InMemoryIPRateLimiter(max_requests=2, window_seconds=1)
        for _ in range(2):
            limiter.is_allowed("10.0.0.1")
        assert not limiter.is_allowed("10.0.0.1")
        # Simulate time passing beyond window
        limiter._requests["10.0.0.1"] = [time.monotonic() - 2]
        assert limiter.is_allowed("10.0.0.1")

    def test_get_count(self):
        limiter = InMemoryIPRateLimiter(max_requests=10, window_seconds=60)
        limiter.is_allowed("10.0.0.1")
        limiter.is_allowed("10.0.0.1")
        assert limiter.get_count("10.0.0.1") == 2
        assert limiter.get_count("10.0.0.2") == 0

    def test_cleanup_removes_stale_ips(self):
        limiter = InMemoryIPRateLimiter(max_requests=10, window_seconds=1)
        limiter.is_allowed("stale-ip")
        # Make timestamps old
        limiter._requests["stale-ip"] = [time.monotonic() - 5]
        limiter._cleanup(time.monotonic())
        assert "stale-ip" not in limiter._requests


class TestIPRateLimitMiddleware:
    """Test the middleware using a real FastAPI test client."""

    def _make_app(self, max_requests=3, window_seconds=3600):
        """Create a minimal FastAPI app with IP rate limit middleware."""
        app = FastAPI()
        app.add_middleware(IPRateLimitMiddleware, max_requests=max_requests, window_seconds=window_seconds)

        @app.get("/health")
        async def health():
            return {"status": "ok"}

        @app.post("/coordination/voice")
        async def post_voice():
            return {"status": "accepted"}

        @app.get("/coordination/voice/counts/test")
        async def get_counts():
            return {"count": 0}

        @app.post("/other/endpoint")
        async def other_post():
            return {"status": "ok"}

        return app

    def test_get_requests_not_rate_limited(self):
        app = self._make_app(max_requests=1)
        client = TestClient(app)
        # GETs should never be rate-limited
        for _ in range(5):
            resp = client.get("/coordination/voice/counts/test")
            assert resp.status_code == 200

    def test_post_to_coordination_rate_limited(self):
        app = self._make_app(max_requests=3)
        client = TestClient(app)
        for _ in range(3):
            resp = client.post("/coordination/voice", json={})
            assert resp.status_code == 200
        # 4th request should be 429
        resp = client.post("/coordination/voice", json={})
        assert resp.status_code == 429
        body = resp.json()
        assert "Too many requests" in body["detail"]
        assert "retry_after_seconds" in body

    def test_post_to_non_coordination_not_limited(self):
        app = self._make_app(max_requests=1)
        client = TestClient(app)
        # First POST exhausts limit for coordination
        client.post("/coordination/voice", json={})
        # POST to non-coordination path should still work
        resp = client.post("/other/endpoint", json={})
        assert resp.status_code == 200

    def test_health_endpoint_not_limited(self):
        app = self._make_app(max_requests=1)
        client = TestClient(app)
        for _ in range(5):
            resp = client.get("/health")
            assert resp.status_code == 200

    def test_429_response_format(self):
        app = self._make_app(max_requests=1, window_seconds=7200)
        client = TestClient(app)
        client.post("/coordination/voice", json={})
        resp = client.post("/coordination/voice", json={})
        assert resp.status_code == 429
        body = resp.json()
        assert body["retry_after_seconds"] == 7200
