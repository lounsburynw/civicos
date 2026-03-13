"""Tests for issuer registry and code batch HTTP endpoints."""

import json
import os
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI

from civicos_relay.voice.crypto import KeyPair, _compute_nostr_event_id


# --- Test App Setup ---


def _create_test_app():
    """Create a test FastAPI app with coordination router and in-memory storage."""
    # Set admin key before importing router (it reads env at call time)
    os.environ["CIVICOS_ADMIN_API_KEY"] = "test-admin-key"
    # Clear cached storage instances so in-memory is used
    from civicos_relay.server import coordination
    coordination._storage_instances.clear()

    app = FastAPI()
    app.include_router(coordination.router)
    return app


@pytest.fixture
def client():
    app = _create_test_app()
    return TestClient(app)


@pytest.fixture
def admin_key():
    return "test-admin-key"


@pytest.fixture
def issuer_keypair():
    """Generate a test issuer keypair."""
    from coincurve import PrivateKey
    pk = PrivateKey()
    from coincurve import PublicKeyXOnly
    xonly = PublicKeyXOnly.from_valid_secret(pk.secret)
    return KeyPair(
        public_key_hex=xonly.format().hex(),
        private_key_hex=pk.secret.hex(),
    )


# --- Issuer Registration Tests ---


class TestRegisterIssuer:
    def test_register_issuer_success(self, client, admin_key, issuer_keypair):
        resp = client.post(
            "/coordination/issuers/register",
            params={"api_key": admin_key},
            json={
                "issuer_pubkey": issuer_keypair.public_key_hex,
                "jurisdiction": "city-mill-valley",
                "organization": "Mill Valley Library",
                "signing_url": "https://signer.mill-valley.example.com",
                "bearer_token": "test-bearer-token",
                "allowed_types": ["physical"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["issuer_id"] == "issuer:city-mill-valley:mill-valley-library"
        assert data["status"] == "pending_verification"
        assert data["organization"] == "Mill Valley Library"

    def test_register_issuer_via_bearer_header(self, client, admin_key, issuer_keypair):
        resp = client.post(
            "/coordination/issuers/register",
            headers={"Authorization": f"Bearer {admin_key}"},
            json={
                "issuer_pubkey": issuer_keypair.public_key_hex,
                "jurisdiction": "city-san-anselmo",
                "organization": "San Anselmo Town Council",
                "signing_url": "https://signer.san-anselmo.example.com",
                "bearer_token": "test-bearer-token",
                "allowed_types": ["physical"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["issuer_id"] == "issuer:city-san-anselmo:san-anselmo-town-council"

    def test_register_issuer_no_auth(self, client, issuer_keypair):
        resp = client.post(
            "/coordination/issuers/register",
            json={
                "issuer_pubkey": issuer_keypair.public_key_hex,
                "jurisdiction": "city-mill-valley",
                "organization": "Mill Valley Library",
                "signing_url": "https://signer.example.com",
                "bearer_token": "token",
            },
        )
        assert resp.status_code == 403

    def test_register_issuer_bad_pubkey(self, client, admin_key):
        resp = client.post(
            "/coordination/issuers/register",
            params={"api_key": admin_key},
            json={
                "issuer_pubkey": "not-a-valid-hex-key",
                "jurisdiction": "city-mill-valley",
                "organization": "Test Org",
                "signing_url": "https://signer.example.com",
                "bearer_token": "token",
            },
        )
        assert resp.status_code == 400

    def test_register_issuer_duplicate(self, client, admin_key, issuer_keypair):
        payload = {
            "issuer_pubkey": issuer_keypair.public_key_hex,
            "jurisdiction": "city-mill-valley",
            "organization": "Mill Valley Library",
            "signing_url": "https://signer.example.com",
            "bearer_token": "token",
        }
        resp1 = client.post(
            "/coordination/issuers/register",
            params={"api_key": admin_key},
            json=payload,
        )
        assert resp1.status_code == 200

        resp2 = client.post(
            "/coordination/issuers/register",
            params={"api_key": admin_key},
            json=payload,
        )
        assert resp2.status_code == 400
        assert "already registered" in resp2.json()["detail"]


# --- Issuer Verification Tests ---


class TestVerifyIssuer:
    def test_verify_issuer(self, client, admin_key, issuer_keypair):
        # Register first
        client.post(
            "/coordination/issuers/register",
            params={"api_key": admin_key},
            json={
                "issuer_pubkey": issuer_keypair.public_key_hex,
                "jurisdiction": "city-mill-valley",
                "organization": "Mill Valley Library",
                "signing_url": "https://signer.example.com",
                "bearer_token": "token",
            },
        )

        # Verify
        resp = client.post(
            "/coordination/admin/issuer/issuer:city-mill-valley:mill-valley-library/verify",
            params={"api_key": admin_key},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "verified"

    def test_verify_issuer_not_found(self, client, admin_key):
        resp = client.post(
            "/coordination/admin/issuer/issuer:nonexistent/verify",
            params={"api_key": admin_key},
        )
        assert resp.status_code == 404

    def test_verify_no_auth(self, client):
        resp = client.post(
            "/coordination/admin/issuer/issuer:test/verify",
        )
        assert resp.status_code == 403


# --- Revoke Issuer Tests ---


class TestRevokeIssuer:
    def test_revoke_issuer(self, client, admin_key, issuer_keypair):
        # Register + verify
        client.post(
            "/coordination/issuers/register",
            params={"api_key": admin_key},
            json={
                "issuer_pubkey": issuer_keypair.public_key_hex,
                "jurisdiction": "city-mill-valley",
                "organization": "Test Org",
                "signing_url": "https://signer.example.com",
                "bearer_token": "token",
            },
        )
        client.post(
            "/coordination/admin/issuer/issuer:city-mill-valley:test-org/verify",
            params={"api_key": admin_key},
        )

        # Revoke
        resp = client.post(
            "/coordination/admin/issuer/issuer:city-mill-valley:test-org/revoke",
            params={"api_key": admin_key},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"


# --- List Issuers Tests ---


class TestListIssuers:
    def test_list_issuers_empty(self, client):
        resp = client.get("/coordination/issuers/city-mill-valley")
        assert resp.status_code == 200
        assert resp.json()["issuers"] == []

    def test_list_issuers_after_register(self, client, admin_key, issuer_keypair):
        client.post(
            "/coordination/issuers/register",
            params={"api_key": admin_key},
            json={
                "issuer_pubkey": issuer_keypair.public_key_hex,
                "jurisdiction": "city-mill-valley",
                "organization": "Mill Valley Library",
                "signing_url": "https://signer.example.com",
                "bearer_token": "token",
            },
        )

        resp = client.get("/coordination/issuers/city-mill-valley")
        assert resp.status_code == 200
        issuers = resp.json()["issuers"]
        assert len(issuers) == 1
        assert issuers[0]["organization"] == "Mill Valley Library"
        # bearer_token should be stripped
        assert "bearer_token" not in issuers[0]


# --- Code Batch Tests ---


class TestCodeBatch:
    def _make_signed_code_batch(self, keypair, jurisdiction, codes, batch_id):
        """Create a kind-30851 signed code batch event."""
        from coincurve import PrivateKey

        created_at = int(time.time())
        tags = [
            ["j", jurisdiction],
            ["batch", batch_id],
            ["count", str(len(codes))],
        ]
        content = json.dumps(codes)
        event_id = _compute_nostr_event_id(
            keypair.public_key_hex, created_at, 30851, tags, content
        )

        pk = PrivateKey(bytes.fromhex(keypair.private_key_hex))
        sig = pk.sign_schnorr(bytes.fromhex(event_id))

        return {
            "id": event_id,
            "pubkey": keypair.public_key_hex,
            "created_at": created_at,
            "kind": 30851,
            "tags": tags,
            "content": content,
            "sig": sig.hex(),
        }

    def test_accept_code_batch(self, client, admin_key, issuer_keypair):
        # Register + verify issuer first
        client.post(
            "/coordination/issuers/register",
            params={"api_key": admin_key},
            json={
                "issuer_pubkey": issuer_keypair.public_key_hex,
                "jurisdiction": "city-mill-valley",
                "organization": "Mill Valley Library",
                "signing_url": "https://signer.example.com",
                "bearer_token": "token",
            },
        )
        client.post(
            "/coordination/admin/issuer/issuer:city-mill-valley:mill-valley-library/verify",
            params={"api_key": admin_key},
        )

        # Create signed code batch
        codes = ["MV-2026-03-AAAA", "MV-2026-03-BBBB", "MV-2026-03-CCCC"]
        signed_event = self._make_signed_code_batch(
            issuer_keypair, "city-mill-valley", codes, "test-batch-1"
        )

        resp = client.post(
            "/coordination/codes/batch",
            params={"api_key": admin_key},
            json={"signed_event": signed_event},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 3
        assert data["batch_id"] == "test-batch-1"
        assert data["jurisdiction"] == "city-mill-valley"

    def test_accept_code_batch_unverified_issuer(self, client, admin_key, issuer_keypair):
        # Register but don't verify
        client.post(
            "/coordination/issuers/register",
            params={"api_key": admin_key},
            json={
                "issuer_pubkey": issuer_keypair.public_key_hex,
                "jurisdiction": "city-mill-valley",
                "organization": "Mill Valley Library",
                "signing_url": "https://signer.example.com",
                "bearer_token": "token",
            },
        )

        codes = ["MV-2026-03-AAAA"]
        signed_event = self._make_signed_code_batch(
            issuer_keypair, "city-mill-valley", codes, "test-batch-2"
        )

        resp = client.post(
            "/coordination/codes/batch",
            params={"api_key": admin_key},
            json={"signed_event": signed_event},
        )
        assert resp.status_code == 400
        assert "not verified" in resp.json()["detail"]

    def test_accept_code_batch_no_auth(self, client, issuer_keypair):
        codes = ["MV-2026-03-AAAA"]
        signed_event = self._make_signed_code_batch(
            issuer_keypair, "city-mill-valley", codes, "test-batch-3"
        )

        resp = client.post(
            "/coordination/codes/batch",
            json={"signed_event": signed_event},
        )
        assert resp.status_code == 403
