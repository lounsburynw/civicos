"""Integration tests for event sync API endpoints.

These tests verify the event sync endpoints for relay-to-relay federation.
They use in-memory storage for unit testing and can optionally test with
PostgreSQL when RELAY_DATABASE_URL is set.

To run:
    pytest packages/civicos-services/tests/test_event_sync_api.py -v --override-ini="addopts="
"""

import pytest
from datetime import datetime, timedelta


class TestEventSyncEndpointsUnit:
    """Unit tests for event sync endpoints using mocked storage."""

    @pytest.fixture
    def mock_storage(self):
        """Create mock sync storage."""
        from civicos_relay.storage.memory import InMemoryStorage
        return InMemoryStorage()

    @pytest.fixture
    def mock_identity(self):
        """Create mock relay identity."""
        from civicos_relay.identity import RelayIdentity
        return RelayIdentity.generate("relay.test.org/events")

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

    def test_export_events_empty(self, client):
        """Export returns empty list when no events."""
        response = client.get("/api/coordination/sync/events")

        assert response.status_code == 200
        data = response.json()
        assert data["events"] == []
        assert data["cursor"] is None
        assert data["relay_id"] == "relay.test.org/events"
        assert data["relay_signature"]  # Has signature

    def test_export_events_with_data(self, client, mock_storage):
        """Export returns events with signed response."""
        from civicos_relay.relay.models import Event, EventType

        # Add an event to storage
        event = Event(
            type=EventType.DECISION_MADE,
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:decision:2026-001",
            timestamp=datetime.utcnow(),
            data={"title": "Test Decision", "outcome": "approved"},
        )
        mock_storage.events.save_event(event)

        response = client.get("/api/coordination/sync/events")

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["type"] == "decision_made"
        assert data["events"][0]["jurisdiction"] == "city-san-rafael"
        assert data["events"][0]["entity"] == "city-san-rafael:decision:2026-001"
        assert data["relay_signature"]

    def test_export_with_namespace_filter(self, client, mock_storage):
        """Export filters by namespace prefix."""
        from civicos_relay.relay.models import Event, EventType

        # Add events in different jurisdictions
        event1 = Event(
            type=EventType.MEETING_SCHEDULED,
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:meeting:2026-02-01",
            data={"title": "City Council Meeting"},
        )
        event2 = Event(
            type=EventType.MEETING_SCHEDULED,
            jurisdiction="city-oakland",
            entity="city-oakland:meeting:2026-02-01",
            data={"title": "Oakland Council Meeting"},
        )
        mock_storage.events.save_event(event1)
        mock_storage.events.save_event(event2)

        response = client.get(
            "/api/coordination/sync/events",
            params={"namespace": "city-san-rafael"}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["jurisdiction"] == "city-san-rafael"

    def test_export_with_since_filter(self, client, mock_storage):
        """Export filters by timestamp."""
        from civicos_relay.relay.models import Event, EventType

        # Add old event
        old_event = Event(
            type=EventType.AGENDA_PUBLISHED,
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:agenda:old",
            timestamp=datetime.utcnow() - timedelta(hours=2),
            data={},
        )
        mock_storage.events.save_event(old_event)

        # Add new event
        new_event = Event(
            type=EventType.AGENDA_PUBLISHED,
            jurisdiction="city-san-rafael",
            entity="city-san-rafael:agenda:new",
            timestamp=datetime.utcnow(),
            data={},
        )
        mock_storage.events.save_event(new_event)

        # Export since 1 hour ago
        since = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        response = client.get(
            "/api/coordination/sync/events",
            params={"since": since}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["entity"] == "city-san-rafael:agenda:new"

    def test_import_events_success(self, client):
        """Import accepts valid events."""
        response = client.post(
            "/api/coordination/sync/events",
            json={
                "events": [
                    {
                        "type": "decision_made",
                        "jurisdiction": "city-san-rafael",
                        "entity": "city-san-rafael:decision:import-001",
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": {"title": "Imported Decision"},
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

    def test_import_deduplicates(self, client):
        """Import deduplicates existing events."""
        timestamp = datetime.utcnow().isoformat()
        event_data = {
            "type": "initiative_created",
            "jurisdiction": "city-san-rafael",
            "entity": "city-san-rafael:initiative:dedupe-001",
            "timestamp": timestamp,
            "data": {"title": "Duplicate Test"},
        }

        # First import
        response1 = client.post(
            "/api/coordination/sync/events",
            json={
                "events": [event_data],
                "source_relay": "peer.example.org",
                "signature": "test_signature",
            }
        )
        assert response1.json()["accepted"] == 1

        # Second import (same event)
        response2 = client.post(
            "/api/coordination/sync/events",
            json={
                "events": [event_data],
                "source_relay": "peer.example.org",
                "signature": "test_signature",
            }
        )
        assert response2.json()["duplicates"] == 1
        assert response2.json()["accepted"] == 0

    def test_import_multiple_events(self, client):
        """Import handles multiple events in one request."""
        now = datetime.utcnow()
        events = [
            {
                "type": "meeting_scheduled",
                "jurisdiction": "city-san-rafael",
                "entity": f"city-san-rafael:meeting:batch-{i}",
                "timestamp": (now + timedelta(seconds=i)).isoformat(),
                "data": {"title": f"Meeting {i}"},
            }
            for i in range(5)
        ]

        response = client.post(
            "/api/coordination/sync/events",
            json={
                "events": events,
                "source_relay": "peer.example.org",
                "signature": "test_signature",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] == 5
        assert data["duplicates"] == 0

    def test_export_pagination(self, client, mock_storage):
        """Export paginates results with cursor."""
        from civicos_relay.relay.models import Event, EventType

        # Add more events than the limit
        now = datetime.utcnow()
        for i in range(15):
            event = Event(
                type=EventType.PUBLIC_COMMENT_OPENED,
                jurisdiction="city-san-rafael",
                entity=f"city-san-rafael:comment:page-{i:03d}",
                timestamp=now + timedelta(seconds=i),
                data={},
            )
            mock_storage.events.save_event(event)

        # First page
        response1 = client.get(
            "/api/coordination/sync/events",
            params={"limit": 10}
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1["events"]) == 10
        assert data1["cursor"] is not None

        # Second page using cursor
        response2 = client.get(
            "/api/coordination/sync/events",
            params={"limit": 10, "cursor": data1["cursor"]}
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2["events"]) == 5
        assert data2["cursor"] is None  # No more pages


class TestTwoRelayEventSync:
    """Integration tests simulating two-relay event sync."""

    def test_event_propagates_via_api(self):
        """Event emitted on relay A can be synced to relay B via API."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import create_app
        from civicos_services.servers.routers import coordination
        from civicos_relay.storage.memory import InMemoryStorage
        from civicos_relay.identity import RelayIdentity
        from civicos_relay.relay.models import Event, EventType

        # Create relay A
        storage_a = InMemoryStorage()
        identity_a = RelayIdentity.generate("relay-a.test.org")

        # Create relay B
        storage_b = InMemoryStorage()
        identity_b = RelayIdentity.generate("relay-b.test.org")

        app = create_app()
        original = coordination._storage_instances.copy()

        try:
            # Emit event on relay A
            event = Event(
                type=EventType.VOICE_THRESHOLD_REACHED,
                jurisdiction="city-san-rafael",
                entity="city-san-rafael:initiative:threshold-001",
                data={"voice_count": 100, "threshold": 100},
            )
            storage_a.events.save_event(event)

            # Configure client A
            coordination._storage_instances.clear()
            coordination._storage_instances["sync"] = storage_a.sync
            coordination._storage_instances["voice"] = storage_a.voices
            coordination._storage_instances["identity"] = identity_a
            client_a = TestClient(app)

            # Export from relay A
            export_response = client_a.get("/api/coordination/sync/events")
            assert export_response.status_code == 200
            export_data = export_response.json()
            assert len(export_data["events"]) == 1

            # Configure client B
            coordination._storage_instances.clear()
            coordination._storage_instances["sync"] = storage_b.sync
            coordination._storage_instances["voice"] = storage_b.voices
            coordination._storage_instances["identity"] = identity_b
            client_b = TestClient(app)

            # Import to relay B
            import_response = client_b.post(
                "/api/coordination/sync/events",
                json={
                    "events": export_data["events"],
                    "source_relay": export_data["relay_id"],
                    "signature": export_data["relay_signature"],
                }
            )
            assert import_response.status_code == 200
            assert import_response.json()["accepted"] == 1

            # Verify relay B now has the event
            verify_response = client_b.get("/api/coordination/sync/events")
            assert verify_response.status_code == 200
            assert len(verify_response.json()["events"]) == 1
            assert verify_response.json()["events"][0]["entity"] == event.entity

        finally:
            coordination._storage_instances.clear()
            coordination._storage_instances.update(original)

    def test_bidirectional_sync(self):
        """Events can sync bidirectionally between relays."""
        from fastapi.testclient import TestClient
        from civicos_services.servers.api import create_app
        from civicos_services.servers.routers import coordination
        from civicos_relay.storage.memory import InMemoryStorage
        from civicos_relay.identity import RelayIdentity
        from civicos_relay.relay.models import Event, EventType

        # Create relays
        storage_a = InMemoryStorage()
        identity_a = RelayIdentity.generate("relay-a.test.org")
        storage_b = InMemoryStorage()
        identity_b = RelayIdentity.generate("relay-b.test.org")

        app = create_app()
        original = coordination._storage_instances.copy()

        try:
            # Event on relay A
            event_a = Event(
                type=EventType.DECISION_MADE,
                jurisdiction="city-san-rafael",
                entity="city-san-rafael:decision:from-a",
                data={"source": "relay-a"},
            )
            storage_a.events.save_event(event_a)

            # Event on relay B
            event_b = Event(
                type=EventType.AGENDA_PUBLISHED,
                jurisdiction="city-san-rafael",
                entity="city-san-rafael:agenda:from-b",
                data={"source": "relay-b"},
            )
            storage_b.events.save_event(event_b)

            # Sync A -> B
            coordination._storage_instances.clear()
            coordination._storage_instances["sync"] = storage_a.sync
            coordination._storage_instances["identity"] = identity_a
            client_a = TestClient(app)
            export_a = client_a.get("/api/coordination/sync/events").json()

            coordination._storage_instances.clear()
            coordination._storage_instances["sync"] = storage_b.sync
            coordination._storage_instances["identity"] = identity_b
            client_b = TestClient(app)
            client_b.post(
                "/api/coordination/sync/events",
                json={
                    "events": export_a["events"],
                    "source_relay": export_a["relay_id"],
                    "signature": export_a["relay_signature"],
                }
            )

            # Sync B -> A
            export_b = client_b.get("/api/coordination/sync/events").json()

            coordination._storage_instances.clear()
            coordination._storage_instances["sync"] = storage_a.sync
            coordination._storage_instances["identity"] = identity_a
            client_a = TestClient(app)
            client_a.post(
                "/api/coordination/sync/events",
                json={
                    "events": export_b["events"],
                    "source_relay": export_b["relay_id"],
                    "signature": export_b["relay_signature"],
                }
            )

            # Both relays should now have both events
            events_a = client_a.get("/api/coordination/sync/events").json()["events"]
            coordination._storage_instances["sync"] = storage_b.sync
            coordination._storage_instances["identity"] = identity_b
            client_b = TestClient(app)
            events_b = client_b.get("/api/coordination/sync/events").json()["events"]

            assert len(events_a) == 2
            assert len(events_b) == 2

        finally:
            coordination._storage_instances.clear()
            coordination._storage_instances.update(original)
