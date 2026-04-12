"""Integration tests for coordination API endpoints.

These tests verify the coordination router endpoints work with a real PostgreSQL database.
They are skipped if RELAY_DATABASE_URL is not set.

To run:
    RELAY_DATABASE_URL=postgresql://... pytest packages/civicos-services/tests/test_coordination_api.py -v --override-ini="addopts="
"""

import os
import pytest
from datetime import datetime
from fastapi.testclient import TestClient

# Skip all tests if RELAY_DATABASE_URL not set
RELAY_DATABASE_URL = os.environ.get("RELAY_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not RELAY_DATABASE_URL,
    reason="RELAY_DATABASE_URL not set - skipping coordination API integration tests"
)


@pytest.fixture(scope="module")
def client():
    """Create FastAPI test client."""
    # Import here to avoid issues if RELAY_DATABASE_URL not set
    from civicos_services.servers.api import create_app
    app = create_app()
    return TestClient(app)


@pytest.fixture
def keypair():
    """Generate a test keypair."""
    from civicos_relay.voice.crypto import KeyPair
    return KeyPair.generate()


class TestVoiceEndpoints:
    """Tests for /api/coordination/voice endpoints."""

    def test_cast_voice_success(self, client, keypair):
        """Can cast a valid signed voice."""
        from civicos_relay.voice.crypto import sign_voice
        from civicos_relay.voice.models import Stance

        entity = f"test:api:voice-{datetime.utcnow().timestamp()}"
        voice = sign_voice(keypair, entity, Stance.SUPPORT)

        response = client.post(
            "/api/coordination/voice",
            json={
                "entity": entity,
                "stance": "support",
                "public_key": voice.public_key,
                "signature": voice.signature,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entity"] == entity
        assert data["stance"] == "support"
        assert data["public_key"] == voice.public_key
        assert data["revoked"] is False

    def test_cast_voice_invalid_signature(self, client, keypair):
        """Rejects voice with invalid signature."""
        entity = f"test:api:invalid-sig-{datetime.utcnow().timestamp()}"

        response = client.post(
            "/api/coordination/voice",
            json={
                "entity": entity,
                "stance": "support",
                "public_key": keypair.public_key_hex,
                "signature": "deadbeef" * 16,  # Invalid signature
            }
        )

        assert response.status_code == 400
        assert "Invalid voice signature" in response.json()["detail"]

    def test_cast_voice_invalid_stance(self, client, keypair):
        """Rejects voice with invalid stance."""
        entity = f"test:api:invalid-stance-{datetime.utcnow().timestamp()}"

        response = client.post(
            "/api/coordination/voice",
            json={
                "entity": entity,
                "stance": "maybe",  # Invalid stance
                "public_key": keypair.public_key_hex,
                "signature": "dummy",
            }
        )

        assert response.status_code == 400
        assert "Invalid stance" in response.json()["detail"]

    def test_get_voice_counts(self, client, keypair):
        """Can get voice counts for an entity."""
        from civicos_relay.voice.crypto import sign_voice
        from civicos_relay.voice.models import Stance

        entity = f"test:api:counts-{datetime.utcnow().timestamp()}"
        voice = sign_voice(keypair, entity, Stance.SUPPORT)

        # Cast a voice first
        client.post(
            "/api/coordination/voice",
            json={
                "entity": entity,
                "stance": "support",
                "public_key": voice.public_key,
                "signature": voice.signature,
            }
        )

        # Get counts
        response = client.get(f"/api/coordination/voice/counts/{entity}")

        assert response.status_code == 200
        data = response.json()
        assert data["entity"] == entity
        assert data["support"] >= 1
        assert data["oppose"] == 0  # No oppose voices cast for this entity
        assert data["watching"] == 0  # No watching voices cast for this entity
        assert data["total"] >= 1

    def test_list_voices(self, client, keypair):
        """Can list voices for an entity."""
        from civicos_relay.voice.crypto import sign_voice
        from civicos_relay.voice.models import Stance

        entity = f"test:api:list-{datetime.utcnow().timestamp()}"
        voice = sign_voice(keypair, entity, Stance.WATCHING)

        # Cast a voice first
        client.post(
            "/api/coordination/voice",
            json={
                "entity": entity,
                "stance": "watching",
                "public_key": voice.public_key,
                "signature": voice.signature,
            }
        )

        # List voices
        response = client.get(f"/api/coordination/voice/{entity}")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(v["public_key"] == voice.public_key for v in data)


class TestSubscriptionEndpoints:
    """Tests for /api/coordination/subscribe endpoints."""

    def test_subscribe_with_email(self, client):
        """Can create a subscription with email delivery."""
        response = client.post(
            "/api/coordination/subscribe",
            json={
                "jurisdiction": "city-test-api",
                "topics": ["housing", "transportation"],
                "email": "test@example.com",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"].startswith("sub_")
        assert data["jurisdiction"] == "city-test-api"
        assert data["delivery_method"] == "email"
        assert data["delivery_address"] == "test@example.com"
        assert data["active"] is True

        # Clean up
        client.delete(f"/api/coordination/subscribe/{data['id']}")

    def test_subscribe_with_webhook(self, client):
        """Can create a subscription with webhook delivery."""
        response = client.post(
            "/api/coordination/subscribe",
            json={
                "jurisdiction": "city-test-api",
                "webhook_url": "https://example.com/webhook",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["delivery_method"] == "webhook"
        assert data["delivery_address"] == "https://example.com/webhook"

        # Clean up
        client.delete(f"/api/coordination/subscribe/{data['id']}")

    def test_subscribe_without_delivery(self, client):
        """Rejects subscription without email or webhook."""
        response = client.post(
            "/api/coordination/subscribe",
            json={
                "jurisdiction": "city-test-api",
                "topics": ["housing"],
            }
        )

        assert response.status_code == 400
        assert "email or webhook" in response.json()["detail"].lower()

    def test_unsubscribe(self, client):
        """Can deactivate a subscription."""
        # Create subscription
        create_response = client.post(
            "/api/coordination/subscribe",
            json={
                "jurisdiction": "city-test-api",
                "email": "unsubscribe-test@example.com",
            }
        )
        sub_id = create_response.json()["id"]

        # Unsubscribe
        response = client.delete(f"/api/coordination/subscribe/{sub_id}")

        assert response.status_code == 200
        assert response.json()["status"] == "unsubscribed"

    def test_unsubscribe_not_found(self, client):
        """Returns 404 for unknown subscription."""
        response = client.delete("/api/coordination/subscribe/sub_nonexistent")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestProvenanceEndpoints:
    """Tests for /api/coordination/provenance endpoints."""

    def test_get_provenance_after_voice(self, client, keypair):
        """Can get provenance after casting a voice."""
        from civicos_relay.voice.crypto import sign_voice
        from civicos_relay.voice.models import Stance

        entity = f"test:api:provenance-{datetime.utcnow().timestamp()}"
        voice = sign_voice(keypair, entity, Stance.OPPOSE)

        # Cast a voice to create provenance
        client.post(
            "/api/coordination/voice",
            json={
                "entity": entity,
                "stance": "oppose",
                "public_key": voice.public_key,
                "signature": voice.signature,
            }
        )

        # Get provenance
        response = client.get(f"/api/coordination/provenance/{keypair.public_key_hex}")

        assert response.status_code == 200
        data = response.json()
        assert data["public_key"] == keypair.public_key_hex
        assert data["total_voices"] >= 1
        assert data["entities_touched"] >= 1

    def test_get_provenance_not_found(self, client):
        """Returns 404 for unknown key."""
        fake_key = "03" + "00" * 32  # Valid-looking but nonexistent key

        response = client.get(f"/api/coordination/provenance/{fake_key}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestActionEndpoints:
    """Tests for /api/coordination/action endpoints."""

    def test_commit_action_success(self, client, keypair):
        """Can commit to an action with valid signature."""
        from civicos_relay.voice.crypto import sign_message

        action_id = f"action:test:commit-{datetime.utcnow().timestamp()}"
        message = f"civicos:action:v1:{action_id}:commitment"
        signature = sign_message(keypair, message)

        response = client.post(
            "/api/coordination/action/commit",
            json={
                "action_id": action_id,
                "public_key": keypair.public_key_hex,
                "signature": signature,
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["action_id"] == action_id
        assert data["action_type"] == "commitment"
        assert data["public_key"] == keypair.public_key_hex
        assert data["revoked"] is False

    def test_commit_action_invalid_signature(self, client, keypair):
        """Rejects commitment with invalid signature."""
        action_id = f"action:test:invalid-commit-{datetime.utcnow().timestamp()}"

        response = client.post(
            "/api/coordination/action/commit",
            json={
                "action_id": action_id,
                "public_key": keypair.public_key_hex,
                "signature": "deadbeef" * 16,  # Invalid signature
            }
        )

        assert response.status_code == 400
        assert "Invalid commitment signature" in response.json()["detail"]

    def test_complete_action_success(self, client, keypair):
        """Can complete an action with valid signature and evidence."""
        from civicos_relay.voice.crypto import sign_message

        action_id = f"action:test:complete-{datetime.utcnow().timestamp()}"
        message = f"civicos:action:v1:{action_id}:completion"
        signature = sign_message(keypair, message)

        response = client.post(
            "/api/coordination/action/complete",
            json={
                "action_id": action_id,
                "public_key": keypair.public_key_hex,
                "signature": signature,
                "evidence_url": "https://example.com/proof",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["action_id"] == action_id
        assert data["action_type"] == "completion"
        assert data["evidence_url"] == "https://example.com/proof"
        assert data["revoked"] is False

    def test_complete_action_invalid_signature(self, client, keypair):
        """Rejects completion with invalid signature."""
        action_id = f"action:test:invalid-complete-{datetime.utcnow().timestamp()}"

        response = client.post(
            "/api/coordination/action/complete",
            json={
                "action_id": action_id,
                "public_key": keypair.public_key_hex,
                "signature": "deadbeef" * 16,
            }
        )

        assert response.status_code == 400
        assert "Invalid completion signature" in response.json()["detail"]

    def test_get_action_counts(self, client, keypair):
        """Can get action counts after committing."""
        from civicos_relay.voice.crypto import sign_message

        action_id = f"action:test:counts-{datetime.utcnow().timestamp()}"
        message = f"civicos:action:v1:{action_id}:commitment"
        signature = sign_message(keypair, message)

        # Commit first
        client.post(
            "/api/coordination/action/commit",
            json={
                "action_id": action_id,
                "public_key": keypair.public_key_hex,
                "signature": signature,
            }
        )

        # Get counts
        response = client.get(f"/api/coordination/action/counts/{action_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["action_id"] == action_id
        assert data["commitments"] >= 1
        assert data["completions"] == 0  # No completions for this action yet

    def test_get_action_counts_with_target(self, client, keypair):
        """Can get action counts with target parameter."""
        action_id = f"action:test:target-{datetime.utcnow().timestamp()}"

        response = client.get(
            f"/api/coordination/action/counts/{action_id}",
            params={"target": 10}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["target"] == 10

    def test_list_commitments(self, client, keypair):
        """Can list commitments for an action."""
        from civicos_relay.voice.crypto import sign_message

        action_id = f"action:test:list-commits-{datetime.utcnow().timestamp()}"
        message = f"civicos:action:v1:{action_id}:commitment"
        signature = sign_message(keypair, message)

        # Commit first
        client.post(
            "/api/coordination/action/commit",
            json={
                "action_id": action_id,
                "public_key": keypair.public_key_hex,
                "signature": signature,
            }
        )

        # List commitments
        response = client.get(f"/api/coordination/action/commitments/{action_id}")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(c["public_key"] == keypair.public_key_hex for c in data)

    def test_list_completions(self, client, keypair):
        """Can list completions for an action."""
        from civicos_relay.voice.crypto import sign_message

        action_id = f"action:test:list-complete-{datetime.utcnow().timestamp()}"
        message = f"civicos:action:v1:{action_id}:completion"
        signature = sign_message(keypair, message)

        # Complete first
        client.post(
            "/api/coordination/action/complete",
            json={
                "action_id": action_id,
                "public_key": keypair.public_key_hex,
                "signature": signature,
            }
        )

        # List completions
        response = client.get(f"/api/coordination/action/completions/{action_id}")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(c["public_key"] == keypair.public_key_hex for c in data)

    def test_recommit_replaces_previous(self, client, keypair):
        """Re-committing revokes previous commitment."""
        from civicos_relay.voice.crypto import sign_message

        action_id = f"action:test:recommit-{datetime.utcnow().timestamp()}"
        message = f"civicos:action:v1:{action_id}:commitment"
        signature = sign_message(keypair, message)

        # Commit twice
        client.post(
            "/api/coordination/action/commit",
            json={
                "action_id": action_id,
                "public_key": keypair.public_key_hex,
                "signature": signature,
            }
        )
        # Commit again (should replace)
        response = client.post(
            "/api/coordination/action/commit",
            json={
                "action_id": action_id,
                "public_key": keypair.public_key_hex,
                "signature": signature,
            }
        )

        assert response.status_code == 200

        # Should still only have 1 commitment
        list_response = client.get(f"/api/coordination/action/commitments/{action_id}")
        data = list_response.json()
        assert len(data) == 1


class TestServiceUnavailable:
    """Tests for behavior when RELAY_DATABASE_URL is not set."""

    def test_voice_without_config(self, client, monkeypatch):
        """Returns 503 when coordination service not configured."""
        # Clear the cached storage instances
        from civicos_services.servers.routers import coordination
        coordination._storage_instances.clear()

        # Temporarily unset the env var
        original = os.environ.get("RELAY_DATABASE_URL")
        if original:
            monkeypatch.delenv("RELAY_DATABASE_URL")

        try:
            response = client.post(
                "/api/coordination/voice",
                json={
                    "entity": "test:entity",
                    "stance": "support",
                    "public_key": "test",
                    "signature": "test",
                }
            )

            assert response.status_code == 503
            assert "not configured" in response.json()["detail"].lower()
        finally:
            # Restore
            if original:
                os.environ["RELAY_DATABASE_URL"] = original
            coordination._storage_instances.clear()
