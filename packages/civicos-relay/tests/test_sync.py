"""Tests for sync module."""

import pytest
from datetime import datetime, timedelta

from civicos_relay import (
    KeyPair,
    Stance,
    VoiceService,
    RelayIdentity,
)
from civicos_relay.sync import SyncService, SyncProtocol
from civicos_relay.sync.protocol import SyncRequest, VoiceImportRequest
from civicos_relay.storage import InMemoryStorage


class TestSyncProtocol:
    """Tests for sync protocol constants and message formats."""

    def test_voice_message_format(self):
        """Voice message has correct format."""
        message = SyncProtocol.voice_message("agenda:2026-02-03:item-6a", "support")
        assert message == b"civicos:voice:v1:agenda:2026-02-03:item-6a:support"

    def test_event_message_format(self):
        """Event message has correct format."""
        ts = datetime(2026, 2, 3, 10, 0, 0)
        message = SyncProtocol.event_message(
            "relay.test.org", "agenda_published", "meeting:123", ts
        )
        assert b"civicos:event:v1" in message
        assert b"relay.test.org" in message

    def test_sync_message_format(self):
        """Sync message has correct format."""
        message = SyncProtocol.sync_message("relay.test.org", "abc123", "cursor1")
        assert message == b"civicos:sync:v1:relay.test.org:abc123:cursor1"


class TestSyncService:
    """Tests for sync service."""

    def test_export_voices(self):
        """Can export voices for peer sync."""
        storage = InMemoryStorage()
        identity = RelayIdentity.generate("relay.test.org/test")
        sync = SyncService(identity, storage.sync, [])

        # Add some voices
        voice_service = VoiceService(storage.voices)
        kp = KeyPair.generate()
        voice_service.cast_voice(kp, "agenda:2026-02-03:item-6a", Stance.SUPPORT)

        # Export
        request = SyncRequest(limit=100)
        response = sync.export_voices(request)

        assert len(response.voices) == 1
        assert response.relay_id == "relay.test.org/test"
        assert response.relay_signature  # Has signature

    def test_import_voices(self):
        """Can import voices from peer."""
        storage = InMemoryStorage()
        identity = RelayIdentity.generate("relay.test.org/test")
        sync = SyncService(identity, storage.sync, [])

        # Create a valid signed voice
        kp = KeyPair.generate()
        from civicos_relay.voice.crypto import sign_voice
        voice = sign_voice(kp, "agenda:2026-02-03:item-6a", Stance.SUPPORT)

        # Import
        request = VoiceImportRequest(
            voices=[voice],
            source_relay="peer.example.org",
            signature="test",
        )
        response = sync.import_voices(request)

        assert response.accepted == 1
        assert response.rejected == 0
        assert response.duplicates == 0

    def test_import_rejects_invalid_signature(self):
        """Import rejects voices with invalid signatures."""
        storage = InMemoryStorage()
        identity = RelayIdentity.generate("relay.test.org/test")
        sync = SyncService(identity, storage.sync, [])

        # Create voice with tampered signature
        from civicos_relay.voice.models import Voice
        voice = Voice(
            entity="agenda:2026-02-03:item-6a",
            stance=Stance.SUPPORT,
            public_key="02" + "ab" * 32,  # Fake key
            signature="invalid",
        )

        request = VoiceImportRequest(
            voices=[voice],
            source_relay="peer.example.org",
            signature="test",
        )
        response = sync.import_voices(request)

        assert response.accepted == 0
        assert response.rejected == 1

    def test_import_deduplicates(self):
        """Import deduplicates existing voices."""
        storage = InMemoryStorage()
        identity = RelayIdentity.generate("relay.test.org/test")
        sync = SyncService(identity, storage.sync, [])

        # Create and import a voice
        kp = KeyPair.generate()
        from civicos_relay.voice.crypto import sign_voice
        voice = sign_voice(kp, "agenda:2026-02-03:item-6a", Stance.SUPPORT)

        request = VoiceImportRequest(
            voices=[voice],
            source_relay="peer.example.org",
            signature="test",
        )

        # First import
        response1 = sync.import_voices(request)
        assert response1.accepted == 1

        # Second import (same voice)
        response2 = sync.import_voices(request)
        assert response2.duplicates == 1
        assert response2.accepted == 0


class TestMultiRelaySync:
    """Tests for syncing between multiple relays."""

    def test_voice_propagates_between_relays(self):
        """Voice cast on relay A appears on relay B after sync."""
        # Set up two relays
        storage_a = InMemoryStorage()
        storage_b = InMemoryStorage()

        identity_a = RelayIdentity.generate("relay-a.test.org")
        identity_b = RelayIdentity.generate("relay-b.test.org")

        sync_a = SyncService(identity_a, storage_a.sync, [])
        sync_b = SyncService(identity_b, storage_b.sync, [])

        # Cast voice on relay A
        voice_service_a = VoiceService(storage_a.voices)
        kp = KeyPair.generate()
        voice_service_a.cast_voice(kp, "agenda:2026-02-03:item-6a", Stance.SUPPORT)

        # Export from A
        export_request = SyncRequest(limit=100)
        export_response = sync_a.export_voices(export_request)

        # Import to B
        import_request = VoiceImportRequest(
            voices=export_response.voices,
            source_relay=export_response.relay_id,
            signature=export_response.relay_signature,
        )
        sync_b.import_voices(import_request)

        # Verify voice is on relay B
        voice_service_b = VoiceService(storage_b.voices)
        counts_b = voice_service_b.get_counts("agenda:2026-02-03:item-6a")

        assert counts_b.support == 1

    def test_voice_counts_consistent_across_relays(self):
        """Voice counts are consistent after sync."""
        # Set up three relays
        storages = [InMemoryStorage() for _ in range(3)]
        identities = [
            RelayIdentity.generate(f"relay-{i}.test.org")
            for i in range(3)
        ]
        syncs = [
            SyncService(identities[i], storages[i].sync, [])
            for i in range(3)
        ]
        voice_services = [VoiceService(s.voices) for s in storages]

        # Cast voices on different relays
        entity = "initiative:san-rafael:bike-lane"

        for i in range(3):
            kp = KeyPair.generate()
            voice_services[i].cast_voice(kp, entity, Stance.SUPPORT)

        # Sync all pairs
        for i in range(3):
            export = syncs[i].export_voices(SyncRequest(limit=100))
            for j in range(3):
                if i != j:
                    syncs[j].import_voices(VoiceImportRequest(
                        voices=export.voices,
                        source_relay=export.relay_id,
                        signature=export.relay_signature,
                    ))

        # All relays should have 3 voices
        for vs in voice_services:
            counts = vs.get_counts(entity)
            assert counts.support == 3
