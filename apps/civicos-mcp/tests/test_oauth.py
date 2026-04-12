"""
Tests for MCP OAuth 2.1 provider.

Tests the complete OAuth flow: metadata discovery, dynamic client registration,
authorization with PKCE, token exchange, refresh tokens, and token validation.
Also tests per-session rate limiting for the OAuth free tier.
"""

import base64
import hashlib
import secrets
import sys
import time
from unittest.mock import patch

import pytest

sys.path.insert(0, "apps/civicos-mcp")

from oauth import (
    _clients,
    _verify_pkce,
    _verify_signed,
    _sign_payload,
    create_oauth_router,
    verify_oauth_token,
    _issue_tokens,
    _issue_auth_code,
    _verify_auth_code,
    _verify_refresh_token,
    TOKEN_TTL,
    CODE_TTL,
)


@pytest.fixture(autouse=True)
def clean_client_cache():
    """Clear the (non-critical) client registration cache between tests."""
    _clients.clear()
    yield
    _clients.clear()


# ─────────── PKCE verification ───────────

class TestPKCE:
    def _make_pkce(self):
        """Generate a valid PKCE pair."""
        verifier = secrets.token_urlsafe(32)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()
        return verifier, challenge

    def test_valid_pkce(self):
        verifier, challenge = self._make_pkce()
        assert _verify_pkce(verifier, challenge, "S256") is True

    def test_wrong_verifier(self):
        _, challenge = self._make_pkce()
        assert _verify_pkce("wrong_verifier", challenge, "S256") is False

    def test_wrong_challenge(self):
        verifier, _ = self._make_pkce()
        assert _verify_pkce(verifier, "wrong_challenge", "S256") is False

    def test_unsupported_method(self):
        verifier, challenge = self._make_pkce()
        assert _verify_pkce(verifier, challenge, "plain") is False


# ─────────── Token issuance and verification ───────────

class TestTokens:
    def test_issue_tokens(self):
        result = _issue_tokens("test-client")
        assert result["access_token"].startswith("cos_")
        assert result["refresh_token"].startswith("cosr_")
        assert result["token_type"] == "bearer"
        assert result["expires_in"] == TOKEN_TTL
        assert result["scope"] == "mcp"

    def test_verify_valid_token(self):
        result = _issue_tokens("test-client")
        info = verify_oauth_token(result["access_token"])
        assert info is not None
        assert info["client_id"] == "test-client"

    def test_verify_invalid_token(self):
        assert verify_oauth_token("cos_nonexistent") is None

    def test_verify_expired_token(self):
        # Build an expired signed access token directly
        now = int(time.time())
        payload = {
            "sub": "test-client",
            "typ": "at",
            "iat": now - TOKEN_TTL - 100,
            "exp": now - 1,  # already expired
            "scope": "mcp",
        }
        expired_token = f"cos_{_sign_payload(payload)}"
        assert verify_oauth_token(expired_token) is None

    def test_verify_tampered_token(self):
        """Tokens with a tampered payload or signature must not verify."""
        result = _issue_tokens("test-client")
        token = result["access_token"]
        # Flip a character in the signature portion
        body = token[4:]  # strip cos_
        payload_b64, sig_b64 = body.split(".", 1)
        tampered = f"cos_{payload_b64}.{sig_b64[:-3]}xxx"
        assert verify_oauth_token(tampered) is None

    def test_verify_token_wrong_type(self):
        """A signed token with typ != 'at' must not verify as access token."""
        now = int(time.time())
        payload = {
            "sub": "test-client",
            "typ": "rt",  # refresh token, not access
            "iat": now,
            "exp": now + 3600,
        }
        token = f"cos_{_sign_payload(payload)}"
        assert verify_oauth_token(token) is None

    def test_multiple_tokens_independent(self):
        r1 = _issue_tokens("client-a")
        r2 = _issue_tokens("client-b")
        assert verify_oauth_token(r1["access_token"])["client_id"] == "client-a"
        assert verify_oauth_token(r2["access_token"])["client_id"] == "client-b"

    def test_tokens_verify_without_shared_state(self):
        """Critical: stateless tokens must verify even after clearing any cache.

        This is the property we need for multi-container Modal deployments.
        If this test passes, a token issued by container A will still verify
        on container B as long as they share the same signing secret.
        """
        result = _issue_tokens("test-client")
        token = result["access_token"]
        # Simulate a fresh container: wipe the only mutable state we keep
        _clients.clear()
        # Token still verifies
        info = verify_oauth_token(token)
        assert info is not None
        assert info["client_id"] == "test-client"


# ─────────── Stateless auth codes ───────────

class TestAuthCodes:
    def test_issue_and_verify(self):
        code = _issue_auth_code(
            client_id="test-client",
            redirect_uri="https://example.com/cb",
            code_challenge="abc",
            code_challenge_method="S256",
        )
        assert code.startswith("cosc_")
        payload = _verify_auth_code(code)
        assert payload is not None
        assert payload["sub"] == "test-client"
        assert payload["ru"] == "https://example.com/cb"
        assert payload["cc"] == "abc"
        assert payload["ccm"] == "S256"

    def test_expired_code_rejected(self):
        now = int(time.time())
        payload = {
            "sub": "test",
            "typ": "ac",
            "iat": now - CODE_TTL - 100,
            "exp": now - 1,
            "ru": "https://example.com",
            "cc": "x", "ccm": "S256",
            "nonce": "abc",
        }
        expired = f"cosc_{_sign_payload(payload)}"
        assert _verify_auth_code(expired) is None

    def test_tampered_code_rejected(self):
        code = _issue_auth_code("test", "https://example.com", "x", "S256")
        tampered = code[:-3] + "xxx"
        assert _verify_auth_code(tampered) is None


# ─────────── Stateless refresh tokens ───────────

class TestRefreshTokens:
    def test_refresh_token_verifies(self):
        result = _issue_tokens("test-client")
        payload = _verify_refresh_token(result["refresh_token"])
        assert payload is not None
        assert payload["sub"] == "test-client"
        assert payload["typ"] == "rt"

    def test_refresh_token_wrong_type(self):
        """An access token must not verify as a refresh token."""
        result = _issue_tokens("test-client")
        # Access token is cos_*, not cosr_* — won't match
        assert _verify_refresh_token(result["access_token"]) is None


# ─────────── FastAPI router integration tests ───────────

class TestOAuthRouter:
    """Test OAuth endpoints via FastAPI TestClient."""

    @pytest.fixture
    def client(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        router = create_oauth_router(
            server_url="https://test.civicosproject.org",
            display_name="Test City",
        )
        app.include_router(router)
        return TestClient(app)

    def _make_pkce(self):
        verifier = secrets.token_urlsafe(32)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()
        return verifier, challenge

    def _extract_redirect_url(self, response):
        """Extract the redirect URL from a 200 HTML-redirect response.

        The authorize POST returns 200 HTML with JS/meta redirect rather
        than a 302 (see oauth._html_redirect docstring for why).
        """
        import re
        # Prefer the meta refresh URL (most reliable to parse)
        m = re.search(r'content="0; url=([^"]+)"', response.text)
        if m:
            import html as html_mod
            return html_mod.unescape(m.group(1))
        return None

    # ── Metadata discovery ──

    def test_protected_resource_metadata(self, client):
        r = client.get("/.well-known/oauth-protected-resource")
        assert r.status_code == 200
        data = r.json()
        assert data["resource"] == "https://test.civicosproject.org/mcp"
        assert "https://test.civicosproject.org" in data["authorization_servers"]
        assert "mcp" in data["scopes_supported"]

    def test_authorization_server_metadata(self, client):
        r = client.get("/.well-known/oauth-authorization-server")
        assert r.status_code == 200
        data = r.json()
        assert data["issuer"] == "https://test.civicosproject.org"
        assert "authorization_endpoint" in data
        assert "token_endpoint" in data
        assert "registration_endpoint" in data
        assert "S256" in data["code_challenge_methods_supported"]
        assert "code" in data["response_types_supported"]

    def test_oidc_configuration_fallback(self, client):
        r = client.get("/.well-known/openid-configuration")
        assert r.status_code == 200
        data = r.json()
        assert data["issuer"] == "https://test.civicosproject.org"

    # ── Dynamic Client Registration ──

    def test_register_client(self, client):
        r = client.post("/register", json={
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["client_id"].startswith("civic_")
        assert data["client_name"] == "Claude"
        assert "https://claude.ai/api/mcp/auth_callback" in data["redirect_uris"]

    def test_register_multiple_clients(self, client):
        r1 = client.post("/register", json={"client_name": "Client A"})
        r2 = client.post("/register", json={"client_name": "Client B"})
        assert r1.json()["client_id"] != r2.json()["client_id"]

    # ── Authorization flow ──

    def test_authorize_shows_consent_page(self, client):
        # Register client first
        reg = client.post("/register", json={
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        })
        client_id = reg.json()["client_id"]

        r = client.get("/authorize", params={
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "scope": "mcp",
            "state": "test_state",
            "code_challenge": "test_challenge",
            "code_challenge_method": "S256",
        })
        assert r.status_code == 200
        assert "Claude" in r.text
        assert "Test City" in r.text
        assert "Allow" in r.text

    def test_authorize_deny(self, client):
        reg = client.post("/register", json={
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        })
        client_id = reg.json()["client_id"]

        r = client.post("/authorize", data={
            "action": "deny",
            "state": "test_state",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": client_id,
            "code_challenge": "test_challenge",
            "code_challenge_method": "S256",
        }, follow_redirects=False)
        assert r.status_code == 200
        url = self._extract_redirect_url(r)
        assert url is not None
        assert "error=access_denied" in url
        assert "state=test_state" in url

    def test_authorize_allow_issues_code(self, client):
        reg = client.post("/register", json={
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        })
        client_id = reg.json()["client_id"]
        verifier, challenge = self._make_pkce()

        r = client.post("/authorize", data={
            "action": "allow",
            "state": "test_state",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": client_id,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }, follow_redirects=False)
        assert r.status_code == 200
        url = self._extract_redirect_url(r)
        assert url is not None
        assert "code=" in url
        assert "state=test_state" in url

    def test_authorize_rejects_wrong_redirect_uri(self, client):
        reg = client.post("/register", json={
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        })
        client_id = reg.json()["client_id"]

        r = client.post("/authorize", data={
            "action": "allow",
            "state": "test_state",
            "redirect_uri": "https://evil.com/callback",
            "client_id": client_id,
            "code_challenge": "test_challenge",
            "code_challenge_method": "S256",
        })
        assert r.status_code == 400
        assert "redirect_uri" in r.json()["error_description"]

    # ── Token exchange ──

    def test_full_auth_code_flow(self, client):
        """Complete OAuth flow: register → authorize → token exchange."""
        # 1. Register
        reg = client.post("/register", json={
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        })
        client_id = reg.json()["client_id"]

        # 2. Authorize
        verifier, challenge = self._make_pkce()
        r = client.post("/authorize", data={
            "action": "allow",
            "state": "s",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": client_id,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }, follow_redirects=False)
        # Extract code from HTML redirect
        code = self._extract_redirect_url(r).split("code=")[1].split("&")[0]

        # 3. Exchange code for token
        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "code_verifier": verifier,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["access_token"].startswith("cos_")
        assert data["refresh_token"].startswith("cosr_")
        assert data["token_type"] == "bearer"

        # 4. Verify token works
        assert verify_oauth_token(data["access_token"]) is not None

    def test_token_exchange_wrong_pkce(self, client):
        reg = client.post("/register", json={
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        })
        client_id = reg.json()["client_id"]
        _, challenge = self._make_pkce()

        r = client.post("/authorize", data={
            "action": "allow",
            "state": "s",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": client_id,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }, follow_redirects=False)
        code = self._extract_redirect_url(r).split("code=")[1].split("&")[0]

        # Wrong verifier
        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "code_verifier": "wrong_verifier",
        })
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"

    def test_token_exchange_expired_code(self, client):
        """An expired auth code is rejected at the /token endpoint."""
        verifier, challenge = self._make_pkce()
        # Directly craft an expired signed code (simulating time passing)
        now = int(time.time())
        payload = {
            "sub": "test-client-xyz",
            "typ": "ac",
            "iat": now - CODE_TTL - 100,
            "exp": now - 1,
            "ru": "https://claude.ai/api/mcp/auth_callback",
            "cc": challenge,
            "ccm": "S256",
            "nonce": "abc",
        }
        expired_code = f"cosc_{_sign_payload(payload)}"

        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": expired_code,
            "client_id": "test-client-xyz",
            "code_verifier": verifier,
        })
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"

    def test_code_requires_correct_verifier(self, client):
        """Stateless codes are not enforced single-use, but PKCE verifier binding
        prevents token exchange without the verifier that matches the challenge.

        This is the primary protection against replay since codes can't be
        marked as consumed without shared storage (see oauth._issue_auth_code
        docstring for rationale).
        """
        reg = client.post("/register", json={
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        })
        client_id = reg.json()["client_id"]
        verifier, challenge = self._make_pkce()

        r = client.post("/authorize", data={
            "action": "allow",
            "state": "s",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": client_id,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }, follow_redirects=False)
        code = self._extract_redirect_url(r).split("code=")[1].split("&")[0]

        # With correct verifier → succeeds
        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "code_verifier": verifier,
        })
        assert r.status_code == 200

        # Same code + wrong verifier → rejected by PKCE check
        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "code_verifier": "wrong_" + verifier,
        })
        assert r.status_code == 400

    def test_token_exchange_wrong_client_id(self, client):
        reg = client.post("/register", json={
            "client_name": "Claude",
            "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"],
        })
        client_id = reg.json()["client_id"]
        verifier, challenge = self._make_pkce()

        r = client.post("/authorize", data={
            "action": "allow",
            "state": "s",
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": client_id,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }, follow_redirects=False)
        code = self._extract_redirect_url(r).split("code=")[1].split("&")[0]

        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": "wrong_client",
            "code_verifier": verifier,
        })
        assert r.status_code == 400

    # ── Refresh tokens ──

    def test_refresh_token_flow(self, client):
        # Get initial tokens
        result = _issue_tokens("test-client")
        refresh = result["refresh_token"]

        r = client.post("/token", data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["access_token"].startswith("cos_")
        # New token verifies
        assert verify_oauth_token(data["access_token"]) is not None
        assert verify_oauth_token(data["access_token"])["client_id"] == "test-client"

    def test_invalid_refresh_token(self, client):
        r = client.post("/token", data={
            "grant_type": "refresh_token",
            "refresh_token": "cosr_nonexistent",
        })
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_grant"

    # ── Unsupported grant types ──

    def test_unsupported_grant_type(self, client):
        r = client.post("/token", data={
            "grant_type": "client_credentials",
        })
        assert r.status_code == 400
        assert r.json()["error"] == "unsupported_grant_type"


# ─────────── OAuth free tier rate limiting ───────────

from api_key_middleware import (
    DailyQuotaLimiter,
    SlidingWindowRateLimiter,
    check_oauth_rate_limit,
    OAUTH_DAILY_QUOTA,
    OAUTH_PER_MINUTE,
    _rate_limiter,
    _daily_limiter,
)


class TestDailyQuotaLimiter:
    """Unit tests for the DailyQuotaLimiter class."""

    def test_allows_within_quota(self):
        limiter = DailyQuotaLimiter()
        allowed, remaining = limiter.check("test-key", 5)
        assert allowed is True
        assert remaining == 4

    def test_counts_down_remaining(self):
        limiter = DailyQuotaLimiter()
        for i in range(4):
            limiter.check("test-key", 5)
        allowed, remaining = limiter.check("test-key", 5)
        assert allowed is True
        assert remaining == 0

    def test_blocks_at_quota(self):
        limiter = DailyQuotaLimiter()
        for _ in range(5):
            limiter.check("test-key", 5)
        allowed, remaining = limiter.check("test-key", 5)
        assert allowed is False
        assert remaining == 0

    def test_isolates_keys(self):
        limiter = DailyQuotaLimiter()
        for _ in range(5):
            limiter.check("key-a", 5)
        # key-a is exhausted
        assert limiter.check("key-a", 5)[0] is False
        # key-b is unaffected
        assert limiter.check("key-b", 5)[0] is True

    def test_resets_on_new_day(self):
        limiter = DailyQuotaLimiter()
        # Exhaust quota
        for _ in range(3):
            limiter.check("test-key", 3)
        assert limiter.check("test-key", 3)[0] is False

        # Simulate day change by injecting a stale date
        limiter._counts["test-key"] = ("2020-01-01", 999)
        allowed, remaining = limiter.check("test-key", 3)
        assert allowed is True
        assert remaining == 2  # fresh day: 1 used, 2 remaining

    def test_get_count_current_day(self):
        limiter = DailyQuotaLimiter()
        assert limiter.get_count("test-key") == 0
        limiter.check("test-key", 10)
        limiter.check("test-key", 10)
        assert limiter.get_count("test-key") == 2

    def test_get_count_stale_day(self):
        limiter = DailyQuotaLimiter()
        limiter._counts["test-key"] = ("2020-01-01", 42)
        assert limiter.get_count("test-key") == 0


class TestOAuthRateLimit:
    """Integration tests for check_oauth_rate_limit combining burst + daily limits."""

    @pytest.fixture(autouse=True)
    def reset_limiters(self):
        """Clear rate limiter state between tests."""
        _rate_limiter._requests.clear()
        _daily_limiter._counts.clear()
        yield
        _rate_limiter._requests.clear()
        _daily_limiter._counts.clear()

    def test_allows_normal_request(self):
        result = check_oauth_rate_limit("oauth:civic_test123")
        assert result["allowed"] is True
        assert result["error"] is None
        assert result["remaining_daily"] == OAUTH_DAILY_QUOTA - 1
        assert result["retry_after"] is None

    def test_per_minute_burst_limit(self):
        key = "oauth:civic_burst"
        # Use up the per-minute allowance
        for _ in range(OAUTH_PER_MINUTE):
            result = check_oauth_rate_limit(key)
            assert result["allowed"] is True

        # Next request should be blocked by burst limit
        result = check_oauth_rate_limit(key)
        assert result["allowed"] is False
        assert result["error"] == "rate_limit_exceeded"
        assert result["retry_after"] == 60

    def test_daily_quota_enforcement(self):
        key = "oauth:civic_daily"
        # Pre-fill the per-minute limiter won't block us — we need to
        # space out calls or use a fresh limiter window each time.
        # Instead, directly fill the daily quota via the limiter.
        for i in range(OAUTH_DAILY_QUOTA):
            _daily_limiter.check(key, OAUTH_DAILY_QUOTA)

        # Per-minute is fine, but daily is exhausted
        result = check_oauth_rate_limit(key)
        # The per-minute check passes, but daily blocks
        assert result["allowed"] is False
        assert result["error"] == "daily_quota_exceeded"
        assert result["remaining_daily"] == 0
        assert result["retry_after"] is not None
        assert result["retry_after"] > 0
        assert result["retry_after"] <= 86400

    def test_session_isolation(self):
        """Different OAuth sessions have independent quotas."""
        key_a = "oauth:civic_alice"
        key_b = "oauth:civic_bob"

        # Exhaust alice's per-minute
        for _ in range(OAUTH_PER_MINUTE):
            check_oauth_rate_limit(key_a)

        # Alice is blocked
        assert check_oauth_rate_limit(key_a)["allowed"] is False

        # Bob is unaffected
        result = check_oauth_rate_limit(key_b)
        assert result["allowed"] is True

    def test_error_response_format(self):
        """Rate limit errors include all required fields with correct values."""
        key = "oauth:civic_format"
        for _ in range(OAUTH_PER_MINUTE):
            check_oauth_rate_limit(key)

        result = check_oauth_rate_limit(key)
        assert result["allowed"] is False
        assert result["error"] == "rate_limit_exceeded"
        assert 0 <= result["remaining_daily"] <= OAUTH_DAILY_QUOTA
        assert result["remaining_minute"] == 0
        assert result["retry_after"] == 60

    def test_daily_quota_approaching_logs_warning(self):
        """When session approaches 80% of daily quota, a warning is logged."""
        key = "oauth:civic_warn"
        # Fill to 80% threshold (OAUTH_DAILY_QUOTA * 0.8)
        threshold = OAUTH_DAILY_QUOTA - int(OAUTH_DAILY_QUOTA * 0.2)
        for _ in range(threshold):
            _daily_limiter.check(key, OAUTH_DAILY_QUOTA)

        # Next request crosses the 80% line — should log
        with patch("api_key_middleware.logger") as mock_logger:
            result = check_oauth_rate_limit(key)
            assert result["allowed"] is True
            mock_logger.info.assert_called_once()
            log_msg = mock_logger.info.call_args[0][0]
            assert "approaching daily quota" in log_msg
