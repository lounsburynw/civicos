"""Tests for AI proxy endpoint.

Tests signature verification, rate limiting, and Anthropic forwarding.
Uses mocked Anthropic client (no real API calls).

To run:
    pytest packages/civicos-services/tests/test_ai_proxy.py -v --override-ini="addopts="
"""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from civicos_relay.voice.crypto import KeyPair, _compute_nostr_event_id, sign_message


AI_DRAFT_KIND = 24242


def _sign_ai_request(keypair: KeyPair) -> dict:
    """Create a signed AI draft request payload."""
    created_at = int(time.time())
    tags = [["action", "ai_draft"]]
    content = f"civicos:ai:v1:{keypair.public_key_hex}:{created_at}"
    event_id = _compute_nostr_event_id(
        keypair.public_key_hex, created_at, AI_DRAFT_KIND, tags, content
    )

    from coincurve import PrivateKey
    pk = PrivateKey(bytes.fromhex(keypair.private_key_hex))
    sig = pk.sign_schnorr(bytes.fromhex(event_id))

    return {
        "public_key": keypair.public_key_hex,
        "signature": sig.hex(),
        "created_at": created_at,
    }


@pytest.fixture(scope="module")
def client():
    """Create FastAPI test client."""
    from civicos_services.servers.api import create_app
    app = create_app()
    return TestClient(app)


@pytest.fixture
def keypair():
    """Generate a test keypair."""
    return KeyPair.generate()


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset in-memory rate limits between tests."""
    from civicos_services.servers.routers.ai_proxy import _rate_limits, _global_cost
    _rate_limits.clear()
    _global_cost["total"] = 0.0
    _global_cost["reset_date"] = ""
    yield
    _rate_limits.clear()
    _global_cost["total"] = 0.0
    _global_cost["reset_date"] = ""


def _mock_anthropic_response(text: str = "Draft response"):
    """Create a mock Anthropic messages.create response."""
    mock_content = MagicMock()
    mock_content.text = text
    mock_content.type = "text"

    mock_response = MagicMock()
    mock_response.content = [mock_content]
    return mock_response


class TestAIDraft:
    """Tests for POST /api/ai/draft."""

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_success(self, mock_anthropic_cls, client, keypair):
        """Valid signed request returns AI draft."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response("Here is your draft.")
        mock_anthropic_cls.return_value = mock_client

        sig_data = _sign_ai_request(keypair)
        response = client.post("/api/ai/draft", json={
            "prompt": "Draft a comment about housing",
            "system_prompt": "You are a civic engagement assistant.",
            **sig_data,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["text"] == "Here is your draft."
        assert data["provider"] == "civicos"

    def test_invalid_signature(self, client, keypair):
        """Invalid signature returns 401."""
        response = client.post("/api/ai/draft", json={
            "prompt": "Test",
            "public_key": keypair.public_key_hex,
            "signature": "deadbeef" * 16,
            "created_at": int(time.time()),
        })

        assert response.status_code == 401

    def test_expired_timestamp(self, client, keypair):
        """Old timestamp returns 400."""
        # Sign with a timestamp 10 minutes ago (beyond 5-minute window)
        old_created_at = int(time.time()) - 600
        tags = [["action", "ai_draft"]]
        content = f"civicos:ai:v1:{keypair.public_key_hex}:{old_created_at}"
        event_id = _compute_nostr_event_id(
            keypair.public_key_hex, old_created_at, AI_DRAFT_KIND, tags, content
        )
        from coincurve import PrivateKey
        pk = PrivateKey(bytes.fromhex(keypair.private_key_hex))
        sig = pk.sign_schnorr(bytes.fromhex(event_id))

        response = client.post("/api/ai/draft", json={
            "prompt": "Test",
            "public_key": keypair.public_key_hex,
            "signature": sig.hex(),
            "created_at": old_created_at,
        })

        assert response.status_code == 400

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_rate_limit_per_npub(self, mock_anthropic_cls, client, keypair):
        """21st request from same npub returns 429."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        for i in range(20):
            sig_data = _sign_ai_request(keypair)
            resp = client.post("/api/ai/draft", json={"prompt": f"Draft {i}", **sig_data})
            assert resp.status_code == 200, f"Request {i} failed: {resp.json()}"

        # 21st should be rate limited
        sig_data = _sign_ai_request(keypair)
        resp = client.post("/api/ai/draft", json={"prompt": "Draft 20", **sig_data})
        assert resp.status_code == 429

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_different_npubs_independent(self, mock_anthropic_cls, client):
        """Different npubs have independent rate limits."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response()
        mock_anthropic_cls.return_value = mock_client

        kp1 = KeyPair.generate()
        kp2 = KeyPair.generate()

        sig1 = _sign_ai_request(kp1)
        sig2 = _sign_ai_request(kp2)

        resp1 = client.post("/api/ai/draft", json={"prompt": "Test", **sig1})
        resp2 = client.post("/api/ai/draft", json={"prompt": "Test", **sig2})

        assert resp1.status_code == 200
        assert resp2.status_code == 200

    @patch.dict("os.environ", {}, clear=True)
    def test_no_api_key_configured(self, client, keypair):
        """Returns 503 when ANTHROPIC_API_KEY is not set."""
        # Remove ANTHROPIC_API_KEY from environment
        import os
        old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            sig_data = _sign_ai_request(keypair)
            response = client.post("/api/ai/draft", json={
                "prompt": "Test",
                **sig_data,
            })
            assert response.status_code == 503
        finally:
            if old_key:
                os.environ["ANTHROPIC_API_KEY"] = old_key

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_with_system_prompt(self, mock_anthropic_cls, client, keypair):
        """System prompt is forwarded to Anthropic."""
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _mock_anthropic_response("Response")
        mock_anthropic_cls.return_value = mock_client

        sig_data = _sign_ai_request(keypair)
        response = client.post("/api/ai/draft", json={
            "prompt": "Draft about housing",
            "system_prompt": "You are a civic assistant.",
            **sig_data,
        })

        assert response.status_code == 200
        # Verify system prompt was passed to Anthropic
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs.get("system") == "You are a civic assistant."
