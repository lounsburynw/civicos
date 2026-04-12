"""
Tests for Nostr storage layer.

These tests focus on:
- EventFilter construction and parsing
- Storage logic (without database - unit tests)
- Integration tests marked with @pytest.mark.integration (require PostgreSQL)
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from civicos_relay.nostr import (
    NostrKeyPair,
    CivicVoiceEvent,
    CivicEntityEvent,
    Stance,
    EntityType,
    CIVIC_VOICE,
    CIVIC_ENTITY,
    CIVIC_PROVENANCE,
)
from civicos_relay.nostr.storage import (
    EventFilter,
    VoiceCounts,
    NostrEventStorage,
    NostrKeyLinkStorage,
)


class TestEventFilter:
    """Tests for EventFilter parsing and construction."""

    def test_from_dict_basic(self):
        """Can parse basic filter from dict."""
        data = {
            "ids": ["abc123"],
            "authors": ["pubkey1"],
            "kinds": [1, 30800],
            "since": 1000,
            "until": 2000,
            "limit": 100,
        }

        filter = EventFilter.from_dict(data)

        assert filter.ids == ["abc123"]
        assert filter.authors == ["pubkey1"]
        assert filter.kinds == [1, 30800]
        assert filter.since == 1000
        assert filter.until == 2000
        assert filter.limit == 100

    def test_from_dict_with_tag_filters(self):
        """Can parse tag filters from NIP-01 format."""
        data = {
            "kinds": [30800],
            "#d": ["entity-id-1", "entity-id-2"],
            "#j": ["city-san-rafael"],
            "#t": ["housing"],
        }

        filter = EventFilter.from_dict(data)

        assert filter.kinds == [30800]
        assert filter.tag_filters == {
            "d": ["entity-id-1", "entity-id-2"],
            "j": ["city-san-rafael"],
            "t": ["housing"],
        }

    def test_from_dict_empty(self):
        """Empty dict produces empty filter."""
        filter = EventFilter.from_dict({})

        assert filter.ids is None
        assert filter.authors is None
        assert filter.kinds is None
        assert filter.since is None
        assert filter.until is None
        assert filter.limit is None
        assert filter.tag_filters is None

    def test_from_dict_ignores_invalid_tags(self):
        """Ignores non-standard tag formats."""
        data = {
            "#d": ["valid"],
            "#xy": ["too long"],  # Tag names are single char
            "notag": ["no hash"],
        }

        filter = EventFilter.from_dict(data)

        # Only #d should be captured (single char after #)
        assert filter.tag_filters["d"] == ["valid"]
        assert "xy" not in filter.tag_filters
        assert "notag" not in filter.tag_filters


class TestVoiceCounts:
    """Tests for VoiceCounts dataclass."""

    def test_voice_counts_creation(self):
        """Can create VoiceCounts."""
        counts = VoiceCounts(
            entity_id="decision:city-sr:2026-02-03:item-1",
            jurisdiction="city-san-rafael",
            support_count=10,
            oppose_count=3,
            watching_count=5,
            total_count=18,
            last_voice_at=1738464000,
        )

        assert counts.entity_id == "decision:city-sr:2026-02-03:item-1"
        assert counts.jurisdiction == "city-san-rafael"
        assert counts.support_count == 10
        assert counts.oppose_count == 3
        assert counts.watching_count == 5
        assert counts.total_count == 18


class TestNostrEventStorageLogic:
    """Unit tests for storage logic (mocked database)."""

    def test_save_event_validates_signature(self):
        """save_event rejects events with invalid signatures."""
        storage = NostrEventStorage("postgresql://mock")

        # Create an event, then tamper with it
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test-entity",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        # Tamper with content (breaks signature)
        voice_dict = voice.to_dict()
        voice_dict["content"] = "tampered"
        tampered_voice = CivicVoiceEvent(**voice_dict)

        # Mock the connection to avoid actual DB calls
        with patch.object(storage, "_get_connection") as mock_conn:
            success, message = storage.save_event(tampered_voice)

        assert not success
        assert "invalid_signature" in message

    def test_addressable_event_requires_d_tag(self):
        """Addressable events without d-tag are rejected."""
        storage = NostrEventStorage("postgresql://mock")

        kp = NostrKeyPair.generate()

        # Create a voice event then remove the d-tag manually
        from civicos_relay.nostr.crypto import sign_event

        # Sign without d-tag (invalid for voice)
        tags = [["j", "test-j"], ["stance", "support"]]
        event_id, pubkey, sig = sign_event(kp, 1000, CIVIC_VOICE, tags, "")

        # This would fail validation at the model level, but let's test storage
        from civicos_relay.nostr.models import NostrEvent

        event = NostrEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=CIVIC_VOICE,
            tags=tags,
            content="",
            sig=sig,
        )

        # Create a proper mock that handles the connection pool
        mock_conn = MagicMock()
        mock_pool = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        storage._pool = mock_pool

        success, message = storage.save_event(event)

        assert not success
        assert "missing_d_tag" in message


class TestEventFilterQueries:
    """Tests for filter-based query building."""

    def test_filter_by_kind(self):
        """Filter can select by kind."""
        filter = EventFilter(kinds=[CIVIC_VOICE])
        assert filter.kinds == [CIVIC_VOICE]

    def test_filter_by_author(self):
        """Filter can select by author pubkey."""
        filter = EventFilter(authors=["a" * 64, "b" * 64])
        assert filter.authors == ["a" * 64, "b" * 64]

    def test_filter_by_time_range(self):
        """Filter can select by time range."""
        filter = EventFilter(since=1000, until=2000)
        assert filter.since == 1000
        assert filter.until == 2000

    def test_filter_by_tags(self):
        """Filter can select by tag values."""
        filter = EventFilter(
            kinds=[CIVIC_VOICE],
            tag_filters={
                "d": ["entity-1"],
                "j": ["city-san-rafael"],
            },
        )
        assert filter.tag_filters["d"] == ["entity-1"]
        assert filter.tag_filters["j"] == ["city-san-rafael"]


# =============================================================================
# Integration tests (require PostgreSQL)
# Mark with @pytest.mark.integration and skip if no DB available
# =============================================================================


@pytest.fixture
def db_url():
    """Get database URL from environment or skip."""
    import os

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    return url


@pytest.fixture
def nostr_storage(db_url):
    """Create storage instance for testing."""
    storage = NostrEventStorage(db_url)
    return storage


@pytest.fixture
def clean_nostr_tables(db_url):
    """Clean nostr tables before/after test."""
    import psycopg2

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM nostr_key_links")
            cur.execute("DELETE FROM nostr_events")
        conn.commit()
    finally:
        conn.close()

    yield

    # Cleanup after test
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM nostr_key_links")
            cur.execute("DELETE FROM nostr_events")
        conn.commit()
    finally:
        conn.close()


@pytest.mark.integration
class TestNostrEventStorageIntegration:
    """Integration tests requiring PostgreSQL."""

    def test_save_and_get_event(self, nostr_storage, clean_nostr_tables):
        """Can save and retrieve an event."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="decision:test:2026-02-03:item-1",
            jurisdiction="test-jurisdiction",
            stance=Stance.SUPPORT,
            topics=["housing"],
        )

        success, message = nostr_storage.save_event(voice)
        assert success
        assert message in ("accepted", "replaced")

        # Retrieve by ID
        retrieved = nostr_storage.get_event(voice.id)
        assert retrieved is not None
        assert retrieved.id == voice.id
        assert retrieved.pubkey == voice.pubkey

    def test_addressable_event_replacement(self, nostr_storage, clean_nostr_tables):
        """Newer addressable events replace older ones."""
        kp = NostrKeyPair.generate()
        entity_id = "decision:test:2026-02-03:item-1"

        # Create first voice
        voice1 = CivicVoiceEvent.create(
            keypair=kp,
            entity_id=entity_id,
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
            created_at=1000,
        )

        success1, _ = nostr_storage.save_event(voice1)
        assert success1

        # Create newer voice (same key, same entity, different stance)
        voice2 = CivicVoiceEvent.create(
            keypair=kp,
            entity_id=entity_id,
            jurisdiction="test-j",
            stance=Stance.OPPOSE,
            created_at=2000,  # Newer
        )

        success2, message2 = nostr_storage.save_event(voice2)
        assert success2
        assert message2 == "replaced"

        # Should only have the newer voice
        retrieved = nostr_storage.get_addressable_event(
            CIVIC_VOICE, kp.public_key_hex, entity_id
        )
        assert retrieved is not None
        assert retrieved.id == voice2.id

    def test_addressable_event_older_rejected(self, nostr_storage, clean_nostr_tables):
        """Older addressable events are rejected."""
        kp = NostrKeyPair.generate()
        entity_id = "decision:test:2026-02-03:item-1"

        # Create newer voice first
        voice_new = CivicVoiceEvent.create(
            keypair=kp,
            entity_id=entity_id,
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
            created_at=2000,
        )

        nostr_storage.save_event(voice_new)

        # Try to save older voice
        voice_old = CivicVoiceEvent.create(
            keypair=kp,
            entity_id=entity_id,
            jurisdiction="test-j",
            stance=Stance.OPPOSE,
            created_at=1000,  # Older
        )

        success, message = nostr_storage.save_event(voice_old)
        assert not success
        assert "older_version" in message

    def test_query_by_jurisdiction(self, nostr_storage, clean_nostr_tables):
        """Can query events by jurisdiction."""
        kp1 = NostrKeyPair.generate()
        kp2 = NostrKeyPair.generate()

        # Create voices in different jurisdictions
        voice_sr = CivicVoiceEvent.create(
            keypair=kp1,
            entity_id="decision:sr:2026-02-03:item-1",
            jurisdiction="city-san-rafael",
            stance=Stance.SUPPORT,
        )

        voice_other = CivicVoiceEvent.create(
            keypair=kp2,
            entity_id="decision:other:2026-02-03:item-1",
            jurisdiction="city-other",
            stance=Stance.SUPPORT,
        )

        nostr_storage.save_event(voice_sr)
        nostr_storage.save_event(voice_other)

        # Query San Rafael only
        results = nostr_storage.query_events(
            EventFilter(
                kinds=[CIVIC_VOICE],
                tag_filters={"j": ["city-san-rafael"]},
            )
        )

        assert len(results) == 1
        assert results[0].id == voice_sr.id

    def test_count_events(self, nostr_storage, clean_nostr_tables):
        """Can count events with filters."""
        kp = NostrKeyPair.generate()

        # Create multiple voices
        for i in range(5):
            voice = CivicVoiceEvent.create(
                keypair=NostrKeyPair.generate(),
                entity_id=f"decision:test:2026-02-03:item-{i}",
                jurisdiction="city-san-rafael",
                stance=Stance.SUPPORT,
            )
            nostr_storage.save_event(voice)

        # Count all
        total = nostr_storage.count_events()
        assert total == 5

        # Count by kind
        voice_count = nostr_storage.count_events(EventFilter(kinds=[CIVIC_VOICE]))
        assert voice_count == 5

    def test_delete_event(self, nostr_storage, clean_nostr_tables):
        """Can delete own events."""
        kp = NostrKeyPair.generate()

        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="decision:test:2026-02-03:item-1",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        nostr_storage.save_event(voice)

        # Delete
        deleted = nostr_storage.delete_event(voice.id, kp.public_key_hex)
        assert deleted

        # Verify deleted
        retrieved = nostr_storage.get_event(voice.id)
        assert retrieved is None

    def test_cannot_delete_others_events(self, nostr_storage, clean_nostr_tables):
        """Cannot delete events from other pubkeys."""
        kp1 = NostrKeyPair.generate()
        kp2 = NostrKeyPair.generate()

        voice = CivicVoiceEvent.create(
            keypair=kp1,
            entity_id="decision:test:2026-02-03:item-1",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        nostr_storage.save_event(voice)

        # Try to delete with wrong pubkey
        deleted = nostr_storage.delete_event(voice.id, kp2.public_key_hex)
        assert not deleted

        # Event should still exist
        retrieved = nostr_storage.get_event(voice.id)
        assert retrieved is not None


@pytest.mark.integration
class TestNostrKeyLinkStorageIntegration:
    """Integration tests for key link storage."""

    def test_save_and_get_key_link(self, db_url, clean_nostr_tables):
        """Can save and retrieve key links."""
        kp = NostrKeyPair.generate()
        storage = NostrKeyLinkStorage(db_url)
        event_storage = NostrEventStorage(db_url)

        # First create an attestation event
        from civicos_relay.nostr.crypto import sign_event
        from civicos_relay.nostr.kinds import KEY_LINK_ATTESTATION
        from civicos_relay.nostr.models import NostrEvent

        old_key = "a" * 64  # Simulated old key
        old_sig = "b" * 128  # Simulated signature

        tags = [["old-key", old_key], ["old-sig", old_sig]]
        event_id, pubkey, sig = sign_event(
            kp, 1000, KEY_LINK_ATTESTATION, tags, "Key migration"
        )

        attestation = NostrEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=KEY_LINK_ATTESTATION,
            tags=tags,
            content="Key migration",
            sig=sig,
        )

        event_storage.save_event(attestation)

        # Save key link
        saved = storage.save_key_link(old_key, pubkey, event_id)
        assert saved

        # Retrieve
        linked = storage.get_linked_key(old_key)
        assert linked == pubkey

        # Get old keys for new key
        old_keys = storage.get_old_keys(pubkey)
        assert old_key in old_keys

    def test_duplicate_old_key_rejected(self, db_url, clean_nostr_tables):
        """Cannot link same old key twice."""
        kp1 = NostrKeyPair.generate()
        kp2 = NostrKeyPair.generate()
        storage = NostrKeyLinkStorage(db_url)
        event_storage = NostrEventStorage(db_url)

        from civicos_relay.nostr.crypto import sign_event
        from civicos_relay.nostr.kinds import KEY_LINK_ATTESTATION
        from civicos_relay.nostr.models import NostrEvent

        old_key = "a" * 64

        # Create first attestation
        tags1 = [["old-key", old_key], ["old-sig", "b" * 128]]
        event_id1, pubkey1, sig1 = sign_event(
            kp1, 1000, KEY_LINK_ATTESTATION, tags1, ""
        )
        attestation1 = NostrEvent(
            id=event_id1,
            pubkey=pubkey1,
            created_at=1000,
            kind=KEY_LINK_ATTESTATION,
            tags=tags1,
            content="",
            sig=sig1,
        )
        event_storage.save_event(attestation1)

        # Create second attestation (different new key, same old key)
        tags2 = [["old-key", old_key], ["old-sig", "c" * 128]]
        event_id2, pubkey2, sig2 = sign_event(
            kp2, 1001, KEY_LINK_ATTESTATION, tags2, ""
        )
        attestation2 = NostrEvent(
            id=event_id2,
            pubkey=pubkey2,
            created_at=1001,
            kind=KEY_LINK_ATTESTATION,
            tags=tags2,
            content="",
            sig=sig2,
        )
        event_storage.save_event(attestation2)

        # First link succeeds
        assert storage.save_key_link(old_key, pubkey1, event_id1)

        # Second link fails (duplicate old key)
        assert not storage.save_key_link(old_key, pubkey2, event_id2)
