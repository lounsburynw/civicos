"""Integration tests for sync API endpoints.

These tests verify the sync endpoints for relay-to-relay federation.
They use in-memory storage for unit testing and can optionally test with
PostgreSQL when RELAY_DATABASE_URL is set.

To run:
    pytest packages/civicos-services/tests/test_sync_api.py -v --override-ini="addopts="
"""

import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock


class TestSyncEndpointsUnit:
    """Unit tests for sync endpoints using mocked storage."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock sync storage."""
        from civicos_relay.storage.memory import InMemoryStorage
        return InMemoryStorage()

    @pytest.fixture
    def mock_identity(self):
        """Create mock relay identity."""
        from civicos_relay.identity import RelayIdentity
        return RelayIdentity.generate("relay.test.org/unit")

    @pytest.fixture
    def client(self, mock_storage, mock_identity):
        """Create FastAPI test client with mocked storage."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import create_app
        from civicos_services.servers.routers import coordination

        app = create_app()

        # Patch storage getters to use in-memory storage
        original_instances = coordination._storage_instances.copy()
        coordination._storage_instances["sync"] = mock_storage.sync
        coordination._storage_instances["voice"] = mock_storage.voices
        coordination._storage_instances["identity"] = mock_identity

        client = TestClient(app)
        yield client

        # Restore
        coordination._storage_instances.clear()
        coordination._storage_instances.update(original_instances)

    @pytest.fixture
    def keypair(self):
        """Generate a test keypair."""
        from civicos_relay.voice.crypto import KeyPair
        return KeyPair.generate()

    def test_export_voices_empty(self, client):
        """Export returns empty list when no voices."""
        response = client.get("/api/coordination/sync/voices")

        assert response.status_code == 200
        data = response.json()
        assert data["voices"] == []
        assert data["cursor"] is None
        assert data["relay_id"] == "relay.test.org/unit"
        assert data["relay_signature"]  # Has signature

    def test_export_voices_with_data(self, client, mock_storage, keypair):
        """Export returns voices with signed response."""
        from civicos_relay.voice.crypto import sign_voice
        from civicos_relay.voice.models import Stance

        # Add a voice to storage
        voice = sign_voice(keypair, "test:sync:export", Stance.SUPPORT)
        mock_storage.voices.save_voice(voice)

        response = client.get("/api/coordination/sync/voices")

        assert response.status_code == 200
        data = response.json()
        assert len(data["voices"]) == 1
        assert data["voices"][0]["entity"] == "test:sync:export"
        assert data["voices"][0]["stance"] == "support"
        assert data["relay_signature"]

    def test_export_with_namespace_filter(self, client, mock_storage, keypair):
        """Export filters by namespace prefix."""
        from civicos_relay.voice.crypto import sign_voice
        from civicos_relay.voice.models import Stance

        # Add voices in different namespaces
        voice1 = sign_voice(keypair, "city-san-rafael:decision:123", Stance.SUPPORT)
        voice2 = sign_voice(keypair, "city-oakland:decision:456", Stance.OPPOSE)
        mock_storage.voices.save_voice(voice1)
        mock_storage.voices.save_voice(voice2)

        response = client.get(
            "/api/coordination/sync/voices",
            params={"namespace": "city-san-rafael:*"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["voices"]) == 1
        assert data["voices"][0]["entity"] == "city-san-rafael:decision:123"

    def test_export_with_since_filter(self, client, mock_storage, keypair):
        """Export filters by timestamp."""
        from civicos_relay.voice.crypto import sign_voice
        from civicos_relay.voice.models import Voice, Stance

        kp2 = type(keypair).generate()

        # Add old voice
        old_voice = sign_voice(keypair, "test:sync:old", Stance.SUPPORT)
        old_voice = Voice(
            entity=old_voice.entity,
            stance=old_voice.stance,
            public_key=old_voice.public_key,
            signature=old_voice.signature,
            timestamp=datetime.utcnow() - timedelta(hours=2),
        )
        mock_storage.voices.save_voice(old_voice)

        # Add new voice
        new_voice = sign_voice(kp2, "test:sync:new", Stance.OPPOSE)
        mock_storage.voices.save_voice(new_voice)

        # Export since 1 hour ago
        since = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        response = client.get(
            "/api/coordination/sync/voices",
            params={"since": since}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["voices"]) == 1
        assert data["voices"][0]["entity"] == "test:sync:new"

    def test_import_voices_success(self, client, keypair):
        """Import accepts valid signed voices."""
        from civicos_relay.voice.crypto import sign_voice
        from civicos_relay.voice.models import Stance

        voice = sign_voice(keypair, "test:sync:import", Stance.WATCHING)

        response = client.post(
            "/api/coordination/sync/voices",
            json={
                "voices": [
                    {
                        "entity": voice.entity,
                        "stance": "watching",
                        "public_key": voice.public_key,
                        "signature": voice.signature,
                        "timestamp": voice.timestamp.isoformat(),
                        "revoked": False,
                    }
                ],
                "source_relay": "peer.example.org",
                "signature": "test_signature",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] == 1
        assert data["rejected"] == 0
        assert data["duplicates"] == 0

    def test_import_rejects_invalid_signature(self, client, keypair):
        """Import rejects voices with invalid signatures."""
        response = client.post(
            "/api/coordination/sync/voices",
            json={
                "voices": [
                    {
                        "entity": "test:sync:invalid",
                        "stance": "support",
                        "public_key": keypair.public_key_hex,
                        "signature": "deadbeef" * 16,  # Invalid
                        "timestamp": datetime.utcnow().isoformat(),
                        "revoked": False,
                    }
                ],
                "source_relay": "peer.example.org",
                "signature": "test_signature",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] == 0
        assert data["rejected"] == 1

    def test_import_deduplicates(self, client, keypair):
        """Import deduplicates existing voices."""
        from civicos_relay.voice.crypto import sign_voice
        from civicos_relay.voice.models import Stance

        voice = sign_voice(keypair, "test:sync:dedupe", Stance.SUPPORT)
        voice_data = {
            "entity": voice.entity,
            "stance": "support",
            "public_key": voice.public_key,
            "signature": voice.signature,
            "timestamp": voice.timestamp.isoformat(),
            "revoked": False,
        }

        # First import
        response1 = client.post(
            "/api/coordination/sync/voices",
            json={
                "voices": [voice_data],
                "source_relay": "peer.example.org",
                "signature": "test_signature",
            }
        )
        assert response1.json()["accepted"] == 1

        # Second import (same voice)
        response2 = client.post(
            "/api/coordination/sync/voices",
            json={
                "voices": [voice_data],
                "source_relay": "peer.example.org",
                "signature": "test_signature",
            }
        )
        assert response2.json()["duplicates"] == 1
        assert response2.json()["accepted"] == 0


class TestTwoRelaySync:
    """Integration tests simulating two-relay sync."""

    def test_voice_propagates_via_api(self):
        """Voice cast on relay A can be synced to relay B via API."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import create_app
        from civicos_services.servers.routers import coordination
        from civicos_relay.storage.memory import InMemoryStorage
        from civicos_relay.identity import RelayIdentity
        from civicos_relay.voice.crypto import KeyPair, sign_voice
        from civicos_relay.voice.models import Stance

        # Create relay A
        storage_a = InMemoryStorage()
        identity_a = RelayIdentity.generate("relay-a.test.org")

        # Create relay B
        storage_b = InMemoryStorage()
        identity_b = RelayIdentity.generate("relay-b.test.org")

        app = create_app()
        original = coordination._storage_instances.copy()

        try:
            # Cast voice on relay A
            keypair = KeyPair.generate()
            voice = sign_voice(keypair, "test:sync:propagate", Stance.SUPPORT)
            storage_a.voices.save_voice(voice)

            # Configure client A
            coordination._storage_instances.clear()
            coordination._storage_instances["sync"] = storage_a.sync
            coordination._storage_instances["voice"] = storage_a.voices
            coordination._storage_instances["identity"] = identity_a
            client_a = TestClient(app)

            # Export from relay A
            export_response = client_a.get("/api/coordination/sync/voices")
            assert export_response.status_code == 200
            export_data = export_response.json()
            assert len(export_data["voices"]) == 1

            # Configure client B
            coordination._storage_instances.clear()
            coordination._storage_instances["sync"] = storage_b.sync
            coordination._storage_instances["voice"] = storage_b.voices
            coordination._storage_instances["identity"] = identity_b
            client_b = TestClient(app)

            # Import to relay B
            import_response = client_b.post(
                "/api/coordination/sync/voices",
                json={
                    "voices": export_data["voices"],
                    "source_relay": export_data["relay_id"],
                    "signature": export_data["relay_signature"],
                }
            )
            assert import_response.status_code == 200
            assert import_response.json()["accepted"] == 1

            # Verify voice is on relay B
            verify_response = client_b.get("/api/coordination/sync/voices")
            assert len(verify_response.json()["voices"]) == 1
            assert verify_response.json()["voices"][0]["entity"] == "test:sync:propagate"

        finally:
            coordination._storage_instances.clear()
            coordination._storage_instances.update(original)


# PostgreSQL integration tests (only run if RELAY_DATABASE_URL is set)
RELAY_DATABASE_URL = os.environ.get("RELAY_DATABASE_URL")


@pytest.mark.skipif(
    not RELAY_DATABASE_URL,
    reason="RELAY_DATABASE_URL not set - skipping PostgreSQL sync tests"
)
class TestSyncEndpointsPostgres:
    """Integration tests for sync endpoints with PostgreSQL."""

    @pytest.fixture(scope="class")
    def client(self):
        """Create FastAPI test client."""
        from civicos_services.servers.api import create_app
        from civicos_services.servers.routers import coordination

        # Clear any cached instances
        coordination._storage_instances.clear()

        app = create_app()
        return TestClient(app)

    @pytest.fixture
    def keypair(self):
        """Generate a test keypair."""
        from civicos_relay.voice.crypto import KeyPair
        return KeyPair.generate()

    def test_export_postgres(self, client):
        """Export endpoint works with PostgreSQL."""
        response = client.get("/api/coordination/sync/voices")
        assert response.status_code == 200
        data = response.json()
        assert "voices" in data
        assert "relay_id" in data
        assert "relay_signature" in data

    def test_import_postgres(self, client, keypair):
        """Import endpoint works with PostgreSQL."""
        from civicos_relay.voice.crypto import sign_voice
        from civicos_relay.voice.models import Stance

        entity = f"test:postgres:sync:{datetime.utcnow().timestamp()}"
        voice = sign_voice(keypair, entity, Stance.SUPPORT)

        response = client.post(
            "/api/coordination/sync/voices",
            json={
                "voices": [
                    {
                        "entity": entity,
                        "stance": "support",
                        "public_key": voice.public_key,
                        "signature": voice.signature,
                        "timestamp": voice.timestamp.isoformat(),
                        "revoked": False,
                    }
                ],
                "source_relay": "test.sync.org",
                "signature": "test",
            }
        )

        assert response.status_code == 200
        assert response.json()["accepted"] == 1

    def test_roundtrip_postgres(self, client, keypair):
        """Can export and re-import voices with PostgreSQL."""
        from civicos_relay.voice.crypto import sign_voice
        from civicos_relay.voice.models import Stance

        entity = f"test:postgres:roundtrip:{datetime.utcnow().timestamp()}"
        voice = sign_voice(keypair, entity, Stance.OPPOSE)

        # Import
        client.post(
            "/api/coordination/sync/voices",
            json={
                "voices": [
                    {
                        "entity": entity,
                        "stance": "oppose",
                        "public_key": voice.public_key,
                        "signature": voice.signature,
                        "timestamp": voice.timestamp.isoformat(),
                        "revoked": False,
                    }
                ],
                "source_relay": "test.roundtrip.org",
                "signature": "test",
            }
        )

        # Export and verify
        since = (datetime.utcnow() - timedelta(minutes=1)).isoformat()
        export_response = client.get(
            "/api/coordination/sync/voices",
            params={"since": since}
        )

        assert export_response.status_code == 200
        voices = export_response.json()["voices"]
        matching = [v for v in voices if v["entity"] == entity]
        assert len(matching) >= 1
