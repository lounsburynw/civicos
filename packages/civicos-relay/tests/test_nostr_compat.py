"""
Tests for REST compatibility layer.

Verifies:
- Legacy voice count retrieval
- Legacy voice listing
- Deprecation headers
- Migration error messages
"""

import pytest
from unittest.mock import MagicMock
from datetime import datetime

from civicos_relay.nostr import (
    NostrKeyPair,
    CivicVoiceEvent,
    Stance,
    CIVIC_VOICE,
)
from civicos_relay.nostr.compat import (
    NostrCompatAdapter,
    LegacyVoice,
    LegacyVoiceCount,
    LegacyVoiceRequest,
    nostr_event_to_legacy_voice,
    legacy_voice_to_nostr_tags,
)
from civicos_relay.nostr.storage import VoiceCounts


class TestLegacyModels:
    """Tests for legacy API models."""

    def test_legacy_voice_request(self):
        """Can create legacy voice request."""
        request = LegacyVoiceRequest(
            entity="decision:city-sr:2026-02-03:item-1",
            stance="support",
            public_key="a" * 64,
            signature="b" * 128,
        )
        assert request.entity == "decision:city-sr:2026-02-03:item-1"
        assert request.stance == "support"

    def test_legacy_voice(self):
        """Can create legacy voice response."""
        voice = LegacyVoice(
            entity="decision:test",
            stance="oppose",
            public_key="a" * 64,
            signature="b" * 128,
            timestamp=datetime.now(),
            revoked=False,
        )
        assert voice.stance == "oppose"
        assert not voice.revoked

    def test_legacy_voice_count(self):
        """Can create legacy voice count."""
        counts = LegacyVoiceCount(
            entity="test-entity",
            support=10,
            oppose=3,
            watching=5,
            total=18,
        )
        assert counts.total == 18


class TestNostrCompatAdapter:
    """Tests for compatibility adapter."""

    @pytest.fixture
    def mock_storage(self):
        storage = MagicMock()
        return storage

    @pytest.fixture
    def adapter(self, mock_storage):
        return NostrCompatAdapter(mock_storage, jurisdiction="city-san-rafael")

    def test_get_voice_counts_with_data(self, adapter, mock_storage):
        """Returns voice counts from storage."""
        mock_storage.get_voice_counts.return_value = VoiceCounts(
            entity_id="decision:test",
            jurisdiction="city-san-rafael",
            support_count=10,
            oppose_count=3,
            watching_count=5,
            total_count=18,
            last_voice_at=1000,
        )

        result = adapter.get_voice_counts("decision:test")

        assert isinstance(result, LegacyVoiceCount)
        assert result.entity == "decision:test"
        assert result.support == 10
        assert result.oppose == 3
        assert result.watching == 5
        assert result.total == 18

    def test_get_voice_counts_no_data(self, adapter, mock_storage):
        """Returns zeros when no data exists."""
        mock_storage.get_voice_counts.return_value = None

        result = adapter.get_voice_counts("unknown-entity")

        assert result.support == 0
        assert result.oppose == 0
        assert result.watching == 0
        assert result.total == 0

    def test_list_voices(self, adapter, mock_storage):
        """Returns voices in legacy format."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="decision:test",
            jurisdiction="city-sr",
            stance=Stance.SUPPORT,
            created_at=1000,
        )

        mock_storage.get_voices_for_entity.return_value = [voice]

        result = adapter.list_voices("decision:test")

        assert len(result) == 1
        assert isinstance(result[0], LegacyVoice)
        assert result[0].entity == "decision:test"
        assert result[0].stance == "support"
        assert result[0].public_key == kp.public_key_hex

    def test_cast_voice_raises_migration_error(self, adapter):
        """cast_voice raises NotImplementedError suggesting migration."""
        request = LegacyVoiceRequest(
            entity="decision:city-sr:test",
            stance="support",
            public_key="a" * 64,
            signature="b" * 128,
        )

        with pytest.raises(NotImplementedError) as exc_info:
            adapter.cast_voice(request)

        assert "migration" in str(exc_info.value).lower()
        assert "WebSocket" in str(exc_info.value)


class TestConversionHelpers:
    """Tests for conversion helper functions."""

    def test_nostr_event_to_legacy_voice(self):
        """Converts Nostr event to legacy format."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="decision:test:item-1",
            jurisdiction="city-sr",
            stance=Stance.OPPOSE,
            created_at=1000,
        )

        result = nostr_event_to_legacy_voice(voice)

        assert result["entity"] == "decision:test:item-1"
        assert result["stance"] == "oppose"
        assert result["public_key"] == kp.public_key_hex
        assert result["signature"] == voice.sig
        assert not result["revoked"]

    def test_nostr_event_to_legacy_voice_revoked(self):
        """Handles revoked voices."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="decision:test",
            jurisdiction="city-sr",
            stance=Stance.SUPPORT,
            content="revoked",  # Marks as revoked
        )

        result = nostr_event_to_legacy_voice(voice)
        assert result["revoked"]

    def test_legacy_voice_to_nostr_tags_basic(self):
        """Converts legacy params to Nostr tags."""
        tags = legacy_voice_to_nostr_tags(
            entity="decision:test:item-1",
            stance="support",
            jurisdiction="city-san-rafael",
        )

        assert ["d", "decision:test:item-1"] in tags
        assert ["j", "city-san-rafael"] in tags
        assert ["stance", "support"] in tags

    def test_legacy_voice_to_nostr_tags_with_topics(self):
        """Includes topic tags."""
        tags = legacy_voice_to_nostr_tags(
            entity="decision:test",
            stance="oppose",
            jurisdiction="city-sr",
            topics=["housing", "zoning"],
        )

        assert ["t", "housing"] in tags
        assert ["t", "zoning"] in tags


class TestCompatRouterIntegration:
    """Tests for the FastAPI compatibility router."""

    @pytest.fixture
    def mock_storage(self):
        storage = MagicMock()
        storage.get_voice_counts.return_value = VoiceCounts(
            entity_id="test",
            jurisdiction="test-j",
            support_count=5,
            oppose_count=2,
            watching_count=1,
            total_count=8,
            last_voice_at=1000,
        )
        storage.get_voices_for_entity.return_value = []
        return storage

    def test_create_compat_router(self, mock_storage):
        """Can create compatibility router."""
        from civicos_relay.nostr.compat import create_compat_router

        router = create_compat_router(mock_storage)

        # Check routes exist
        routes = [r.path for r in router.routes]
        assert "/voice" in routes
        assert "/voice/counts/{entity:path}" in routes
        assert "/voice/{entity:path}" in routes

    @pytest.mark.asyncio
    async def test_voice_counts_endpoint(self, mock_storage):
        """Voice counts endpoint returns data with deprecation headers."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from civicos_relay.nostr.compat import create_compat_router

        app = FastAPI()
        app.include_router(create_compat_router(mock_storage))

        with TestClient(app) as client:
            response = client.get("/voice/counts/decision:test:item-1")

            assert response.status_code == 200

            # Check deprecation headers
            assert response.headers.get("Deprecation") == "true"
            assert "Sunset" in response.headers
            assert "Link" in response.headers

            # Check data
            data = response.json()
            assert data["support"] == 5
            assert data["oppose"] == 2

    @pytest.mark.asyncio
    async def test_cast_voice_returns_error(self, mock_storage):
        """Cast voice returns migration error."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from civicos_relay.nostr.compat import create_compat_router

        app = FastAPI()
        app.include_router(create_compat_router(mock_storage))

        with TestClient(app) as client:
            response = client.post(
                "/voice",
                json={
                    "entity": "decision:test",
                    "stance": "support",
                    "public_key": "a" * 64,
                    "signature": "b" * 128,
                },
            )

            assert response.status_code == 400
            assert "migration" in response.json()["detail"].lower()
