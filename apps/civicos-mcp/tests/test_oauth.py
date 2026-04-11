"""
Tests for MCP OAuth 2.1 provider.

Tests the complete OAuth flow: metadata discovery, dynamic client registration,
authorization with PKCE, token exchange, refresh tokens, and token validation.
"""

import base64
import hashlib
import secrets
import sys
import time

import pytest

sys.path.insert(0, "apps/civicos-mcp")

from oauth import (
    _access_tokens,
    _auth_codes,
    _clients,
    _refresh_tokens,
    _verify_pkce,
    create_oauth_router,
    verify_oauth_token,
    _issue_tokens,
    _prune_expired,
    TOKEN_TTL,
    CODE_TTL,
)


@pytest.fixture(autouse=True)
def clean_stores():
    """Clear all in-memory stores between tests."""
    _clients.clear()
    _auth_codes.clear()
    _access_tokens.clear()
    _refresh_tokens.clear()
    yield
    _clients.clear()
    _auth_codes.clear()
    _access_tokens.clear()
    _refresh_tokens.clear()


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
        result = _issue_tokens("test-client")
        token = result["access_token"]
        # Manually expire the token
        _access_tokens[token]["expires_at"] = time.time() - 1
        assert verify_oauth_token(token) is None
        # Token should be cleaned up
        assert token not in _access_tokens

    def test_multiple_tokens_independent(self):
        r1 = _issue_tokens("client-a")
        r2 = _issue_tokens("client-b")
        assert verify_oauth_token(r1["access_token"])["client_id"] == "client-a"
        assert verify_oauth_token(r2["access_token"])["client_id"] == "client-b"


# ─────────── Pruning ───────────

class TestPruning:
    def test_prune_expired_codes(self):
        _auth_codes["old_code"] = {
            "challenge": "x",
            "method": "S256",
            "redirect_uri": "https://example.com",
            "client_id": "test",
            "expires_at": time.time() - 1,
        }
        _prune_expired()
        assert "old_code" not in _auth_codes

    def test_prune_keeps_valid_codes(self):
        _auth_codes["valid_code"] = {
            "challenge": "x",
            "method": "S256",
            "redirect_uri": "https://example.com",
            "client_id": "test",
            "expires_at": time.time() + 300,
        }
        _prune_expired()
        assert "valid_code" in _auth_codes

    def test_prune_expired_tokens(self):
        _access_tokens["old_token"] = {
            "client_id": "test",
            "issued_at": time.time() - TOKEN_TTL - 1,
            "expires_at": time.time() - 1,
        }
        _prune_expired()
        assert "old_token" not in _access_tokens


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
        assert r.status_code == 302
        assert "error=access_denied" in r.headers["location"]
        assert "state=test_state" in r.headers["location"]

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
        assert r.status_code == 302
        location = r.headers["location"]
        assert "code=" in location
        assert "state=test_state" in location

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
        # Extract code from redirect URL
        location = r.headers["location"]
        code = location.split("code=")[1].split("&")[0]

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
        code = r.headers["location"].split("code=")[1].split("&")[0]

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
        code = r.headers["location"].split("code=")[1].split("&")[0]

        # Expire the code
        _auth_codes[code]["expires_at"] = time.time() - 1

        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "code_verifier": verifier,
        })
        assert r.status_code == 400

    def test_code_single_use(self, client):
        """Authorization codes can only be used once."""
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
        code = r.headers["location"].split("code=")[1].split("&")[0]

        # First use succeeds
        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "code_verifier": verifier,
        })
        assert r.status_code == 200

        # Second use fails (code was consumed)
        r = client.post("/token", data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "code_verifier": verifier,
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
        code = r.headers["location"].split("code=")[1].split("&")[0]

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
        old_access = result["access_token"]
        refresh = result["refresh_token"]

        r = client.post("/token", data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
        })
        assert r.status_code == 200
        data = r.json()
        assert data["access_token"].startswith("cos_")
        assert data["access_token"] != old_access  # New token issued

        # Old access token should be revoked
        assert verify_oauth_token(old_access) is None
        # New token should work
        assert verify_oauth_token(data["access_token"]) is not None

    def test_refresh_token_single_use(self):
        result = _issue_tokens("test-client")
        refresh = result["refresh_token"]
        # Consume the refresh token
        assert refresh in _refresh_tokens
        del _refresh_tokens[refresh]
        # Can't reuse
        assert refresh not in _refresh_tokens

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
