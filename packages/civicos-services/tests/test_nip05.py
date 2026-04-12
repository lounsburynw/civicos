"""Tests for NIP-05 verification endpoint.

These tests verify the /.well-known/nostr.json endpoint for Nostr identity verification.

To run:
    pytest packages/civicos-services/tests/test_nip05.py -v --override-ini="addopts="
"""

import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Create FastAPI test client."""
    from civicos_services.servers.api import create_app
    app = create_app()
    return TestClient(app)


class TestNIP05Endpoint:
    """Tests for /.well-known/nostr.json endpoint."""

    def test_nip05_no_pubkey_configured(self, client):
        """Returns empty response when no pubkey is configured."""
        with patch.dict(os.environ, {"NOSTR_RELAY_PUBKEY": ""}, clear=False):
            response = client.get("/.well-known/nostr.json")

        assert response.status_code == 200
        data = response.json()
        assert data == {"names": {}, "relays": {}}

    def test_nip05_with_pubkey_configured(self, client):
        """Returns pubkey when configured via environment."""
        test_pubkey = "a" * 64  # Valid 64-char hex pubkey
        test_relay = "wss://test.relay.example"

        with patch.dict(os.environ, {
            "NOSTR_RELAY_PUBKEY": test_pubkey,
            "NOSTR_RELAY_URL": test_relay,
        }, clear=False):
            response = client.get("/.well-known/nostr.json")

        assert response.status_code == 200
        data = response.json()

        # Should have civicos and _ (wildcard) names
        assert "civicos" in data["names"]
        assert "_" in data["names"]
        assert data["names"]["civicos"] == test_pubkey
        assert data["names"]["_"] == test_pubkey

        # Should have relay hints
        assert test_pubkey in data["relays"]
        assert test_relay in data["relays"][test_pubkey]

    def test_nip05_name_lookup(self, client):
        """Can look up specific name."""
        test_pubkey = "b" * 64

        with patch.dict(os.environ, {
            "NOSTR_RELAY_PUBKEY": test_pubkey,
        }, clear=False):
            response = client.get("/.well-known/nostr.json?name=civicos")

        assert response.status_code == 200
        data = response.json()

        # Should only have the requested name
        assert "civicos" in data["names"]
        assert "_" not in data["names"]  # Not requested
        assert data["names"]["civicos"] == test_pubkey

    def test_nip05_unknown_name_lookup(self, client):
        """Unknown name returns empty names dict."""
        test_pubkey = "c" * 64

        with patch.dict(os.environ, {
            "NOSTR_RELAY_PUBKEY": test_pubkey,
        }, clear=False):
            response = client.get("/.well-known/nostr.json?name=unknown")

        assert response.status_code == 200
        data = response.json()

        # Should have empty names (name not found)
        assert data["names"] == {}

    def test_nip05_invalid_pubkey_ignored(self, client):
        """Invalid pubkey (wrong length) is ignored."""
        with patch.dict(os.environ, {
            "NOSTR_RELAY_PUBKEY": "tooshort",
        }, clear=False):
            response = client.get("/.well-known/nostr.json")

        assert response.status_code == 200
        data = response.json()
        assert data == {"names": {}, "relays": {}}

    def test_nip05_cors_headers(self, client):
        """Response includes CORS headers for cross-origin requests."""
        test_pubkey = "d" * 64

        with patch.dict(os.environ, {
            "NOSTR_RELAY_PUBKEY": test_pubkey,
        }, clear=False):
            response = client.get("/.well-known/nostr.json")

        assert response.status_code == 200
        assert response.headers.get("Access-Control-Allow-Origin") == "*"
        assert response.headers.get("Cache-Control") == "max-age=3600"

    def test_nip05_default_relay_url(self, client):
        """Uses default relay URL when not configured."""
        test_pubkey = "e" * 64

        with patch.dict(os.environ, {
            "NOSTR_RELAY_PUBKEY": test_pubkey,
            "NOSTR_RELAY_URL": "",  # Empty, should use default
        }, clear=False):
            # Remove NOSTR_RELAY_URL entirely
            env_copy = os.environ.copy()
            if "NOSTR_RELAY_URL" in env_copy:
                del env_copy["NOSTR_RELAY_URL"]

            with patch.dict(os.environ, env_copy, clear=True):
                # Re-add the pubkey
                os.environ["NOSTR_RELAY_PUBKEY"] = test_pubkey
                response = client.get("/.well-known/nostr.json")

        assert response.status_code == 200
        data = response.json()

        # Should use default relay URL
        assert test_pubkey in data["relays"]
        assert "wss://relay.civicos.org" in data["relays"][test_pubkey]
