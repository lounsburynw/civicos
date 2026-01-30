"""Integration tests for PostgreSQL relay storage.

These tests verify the relay storage classes work with a real PostgreSQL database.
They are skipped if RELAY_DATABASE_URL is not set.

To run:
    RELAY_DATABASE_URL=postgresql://... pytest tests/test_postgres_integration.py -v
"""

import os
import pytest
from datetime import datetime

# Skip all tests if RELAY_DATABASE_URL not set
RELAY_DATABASE_URL = os.environ.get("RELAY_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not RELAY_DATABASE_URL,
    reason="RELAY_DATABASE_URL not set - skipping PostgreSQL integration tests"
)


class TestPostgresVoiceStorage:
    """Integration tests for PostgresVoiceStorage."""

    def test_save_and_get_voice(self):
        """Can save and retrieve a voice."""
        from civicos_relay.storage.postgres import PostgresVoiceStorage
        from civicos_relay.voice.models import Voice, Stance
        from civicos_relay.voice.crypto import KeyPair, sign_voice

        storage = PostgresVoiceStorage(RELAY_DATABASE_URL)

        # Create and sign a voice
        kp = KeyPair.generate()
        voice = sign_voice(kp, "test:integration:voice-1", Stance.SUPPORT)

        # Save it
        storage.save_voice(voice)

        # Retrieve it
        retrieved = storage.get_voice(kp.public_key_hex, "test:integration:voice-1")
        assert retrieved is not None
        assert retrieved.entity == voice.entity
        assert retrieved.stance == voice.stance
        assert retrieved.public_key == voice.public_key
        assert retrieved.signature == voice.signature
        assert not retrieved.revoked

        # Clean up
        storage.revoke_voice(kp.public_key_hex, "test:integration:voice-1")

    def test_get_voices_for_entity(self):
        """Can get all voices for an entity."""
        from civicos_relay.storage.postgres import PostgresVoiceStorage
        from civicos_relay.voice.models import Stance
        from civicos_relay.voice.crypto import KeyPair, sign_voice

        storage = PostgresVoiceStorage(RELAY_DATABASE_URL)
        entity = "test:integration:voices-for-entity"

        # Create multiple voices from different keys
        keys = [KeyPair.generate() for _ in range(3)]
        voices = [
            sign_voice(keys[0], entity, Stance.SUPPORT),
            sign_voice(keys[1], entity, Stance.OPPOSE),
            sign_voice(keys[2], entity, Stance.WATCHING),
        ]

        for voice in voices:
            storage.save_voice(voice)

        # Get all voices
        retrieved = storage.get_voices_for_entity(entity)
        assert len(retrieved) >= 3  # May have other test data

        # Clean up
        for key in keys:
            storage.revoke_voice(key.public_key_hex, entity)

    def test_revoke_voice(self):
        """Can revoke a voice."""
        from civicos_relay.storage.postgres import PostgresVoiceStorage
        from civicos_relay.voice.models import Stance
        from civicos_relay.voice.crypto import KeyPair, sign_voice

        storage = PostgresVoiceStorage(RELAY_DATABASE_URL)

        kp = KeyPair.generate()
        voice = sign_voice(kp, "test:integration:revoke", Stance.SUPPORT)
        storage.save_voice(voice)

        # Revoke
        result = storage.revoke_voice(kp.public_key_hex, "test:integration:revoke")
        assert result is True

        # Verify it's revoked
        retrieved = storage.get_voice(kp.public_key_hex, "test:integration:revoke")
        assert retrieved.revoked is True


class TestPostgresSubscriptionStorage:
    """Integration tests for PostgresSubscriptionStorage."""

    def test_save_and_get_subscription(self):
        """Can save and retrieve a subscription."""
        from civicos_relay.storage.postgres import PostgresSubscriptionStorage
        from civicos_relay.relay.models import (
            Subscription, MatchCriteria, DeliveryConfig, DeliveryMethod
        )

        storage = PostgresSubscriptionStorage(RELAY_DATABASE_URL)

        sub = Subscription(
            id="test-sub-integration-1",
            jurisdiction="city-test",
            match=MatchCriteria(topics=["housing", "transportation"]),
            delivery=DeliveryConfig(
                method=DeliveryMethod.EMAIL,
                address="test@example.com"
            ),
        )

        storage.save_subscription(sub)

        retrieved = storage.get_subscription("test-sub-integration-1")
        assert retrieved is not None
        assert retrieved.id == sub.id
        assert retrieved.jurisdiction == sub.jurisdiction
        assert retrieved.match.topics == ["housing", "transportation"]
        assert retrieved.delivery.method == DeliveryMethod.EMAIL

        # Clean up
        storage.deactivate_subscription("test-sub-integration-1")

    def test_get_subscriptions_for_jurisdiction(self):
        """Can get all subscriptions for a jurisdiction."""
        from civicos_relay.storage.postgres import PostgresSubscriptionStorage
        from civicos_relay.relay.models import (
            Subscription, MatchCriteria, DeliveryConfig, DeliveryMethod
        )

        storage = PostgresSubscriptionStorage(RELAY_DATABASE_URL)
        jurisdiction = "city-test-jurisdiction"

        subs = [
            Subscription(
                id=f"test-sub-jur-{i}",
                jurisdiction=jurisdiction,
                match=MatchCriteria(topics=["housing"]),
                delivery=DeliveryConfig(
                    method=DeliveryMethod.EMAIL,
                    address=f"test{i}@example.com"
                ),
            )
            for i in range(2)
        ]

        for sub in subs:
            storage.save_subscription(sub)

        retrieved = storage.get_subscriptions_for_jurisdiction(jurisdiction)
        assert len(retrieved) >= 2

        # Clean up
        for sub in subs:
            storage.deactivate_subscription(sub.id)


class TestPostgresProvenanceStorage:
    """Integration tests for PostgresProvenanceStorage."""

    def test_save_and_get_provenance(self):
        """Can save and retrieve provenance."""
        from civicos_relay.storage.postgres import PostgresProvenanceStorage
        from civicos_relay.provenance.models import KeyProvenance
        from civicos_relay.voice.crypto import KeyPair

        storage = PostgresProvenanceStorage(RELAY_DATABASE_URL)

        kp = KeyPair.generate()
        now = datetime.utcnow()

        provenance = KeyProvenance(
            public_key=kp.public_key_hex,
            created_at=now,
            total_voices=5,
            entities_touched=3,
            first_voice_at=now,
            last_voice_at=now,
            jurisdictions=["city-san-rafael", "city-test"],
        )

        storage.save_provenance(provenance)

        retrieved = storage.get_provenance(kp.public_key_hex)
        assert retrieved is not None
        assert retrieved.public_key == kp.public_key_hex
        assert retrieved.total_voices == 5
        assert retrieved.entities_touched == 3
        assert "city-san-rafael" in retrieved.jurisdictions


class TestSchemaExists:
    """Verify the coordination schema exists."""

    def test_tables_exist(self):
        """All required tables exist in the database."""
        import psycopg2

        conn = psycopg2.connect(RELAY_DATABASE_URL)
        try:
            with conn.cursor() as cur:
                # Check each required table
                tables = [
                    "coordination_voices",
                    "coordination_subscriptions",
                    "coordination_provenance",
                    "coordination_events_log",
                ]
                for table in tables:
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables
                            WHERE table_name = %s
                        )
                        """,
                        (table,),
                    )
                    exists = cur.fetchone()[0]
                    assert exists, f"Table {table} does not exist"
        finally:
            conn.close()
