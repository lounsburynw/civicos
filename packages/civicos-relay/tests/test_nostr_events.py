"""
Tests for Nostr event models.

Verifies:
- Base NostrEvent validation and methods
- Civic event type models (Voice, Entity, etc.)
- Tag parsing and building
- Event creation with signing
- Event parsing by kind
"""

import json
import pytest
from civicos_relay.nostr import (
    NostrKeyPair,
    NostrEvent,
    CivicVoiceEvent,
    CivicEntityEvent,
    CivicSubscriptionEvent,
    CivicProvenanceEvent,
    CivicVouchEvent,
    CivicEventNotificationEvent,
    KeyLinkAttestationEvent,
    Stance,
    EntityType,
    Outcome,
    parse_event,
    build_tags,
    CIVIC_VOICE,
    CIVIC_ENTITY,
    CIVIC_SUBSCRIPTION,
    CIVIC_PROVENANCE,
    CIVIC_VOUCH,
    CIVIC_EVENT_NOTIFICATION,
    KEY_LINK_ATTESTATION,
    is_addressable,
    is_replaceable,
    is_civic_kind,
    sign_event,
)


class TestNostrEvent:
    """Tests for base NostrEvent model."""

    def test_create_valid_event(self):
        """Can create a valid NostrEvent."""
        kp = NostrKeyPair.generate()
        event_id, pubkey, sig = sign_event(kp, 1000, 1, [], "test")

        event = NostrEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=1,
            tags=[],
            content="test",
            sig=sig,
        )

        assert event.id == event_id
        assert event.pubkey == pubkey
        assert event.kind == 1
        assert event.verify()

    def test_invalid_id_length(self):
        """Rejects invalid ID length."""
        with pytest.raises(ValueError, match="64 hex chars"):
            NostrEvent(
                id="abc",
                pubkey="a" * 64,
                created_at=1000,
                kind=1,
                tags=[],
                content="",
                sig="b" * 128,
            )

    def test_invalid_pubkey_length(self):
        """Rejects invalid pubkey length."""
        with pytest.raises(ValueError, match="64 hex chars"):
            NostrEvent(
                id="a" * 64,
                pubkey="abc",
                created_at=1000,
                kind=1,
                tags=[],
                content="",
                sig="b" * 128,
            )

    def test_invalid_sig_length(self):
        """Rejects invalid signature length."""
        with pytest.raises(ValueError, match="128 hex chars"):
            NostrEvent(
                id="a" * 64,
                pubkey="b" * 64,
                created_at=1000,
                kind=1,
                tags=[],
                content="",
                sig="abc",
            )

    def test_invalid_hex(self):
        """Rejects invalid hex characters."""
        with pytest.raises(ValueError, match="valid hex"):
            NostrEvent(
                id="g" * 64,  # 'g' is not hex
                pubkey="a" * 64,
                created_at=1000,
                kind=1,
                tags=[],
                content="",
                sig="b" * 128,
            )

    def test_negative_timestamp(self):
        """Rejects negative timestamp."""
        with pytest.raises(ValueError, match="non-negative"):
            NostrEvent(
                id="a" * 64,
                pubkey="b" * 64,
                created_at=-1,
                kind=1,
                tags=[],
                content="",
                sig="c" * 128,
            )

    def test_get_tag(self):
        """Can retrieve tags by name."""
        kp = NostrKeyPair.generate()
        tags = [["d", "entity-id"], ["j", "city-sr"], ["t", "housing"]]
        event_id, pubkey, sig = sign_event(kp, 1000, 30800, tags, "")

        event = NostrEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=30800,
            tags=tags,
            content="",
            sig=sig,
        )

        assert event.get_tag("d") == "entity-id"
        assert event.get_tag("j") == "city-sr"
        assert event.get_tag("missing") is None

    def test_get_tags_multiple(self):
        """Can retrieve multiple tags with same name."""
        kp = NostrKeyPair.generate()
        tags = [["t", "housing"], ["t", "zoning"], ["t", "transit"]]
        event_id, pubkey, sig = sign_event(kp, 1000, 1, tags, "")

        event = NostrEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=1,
            tags=tags,
            content="",
            sig=sig,
        )

        assert event.get_tags("t") == ["housing", "zoning", "transit"]
        assert event.get_tags("missing") == []

    def test_to_dict_roundtrip(self):
        """to_dict produces valid JSON-serializable dict."""
        kp = NostrKeyPair.generate()
        event_id, pubkey, sig = sign_event(kp, 1000, 1, [["t", "test"]], "hello")

        event = NostrEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=1,
            tags=[["t", "test"]],
            content="hello",
            sig=sig,
        )

        d = event.to_dict()
        json_str = json.dumps(d)  # Should be serializable
        event2 = NostrEvent.from_dict(json.loads(json_str))

        assert event2.id == event.id
        assert event2.verify()


class TestCivicVoiceEvent:
    """Tests for CivicVoiceEvent (kind 30800)."""

    def test_create_voice(self):
        """Can create a civic voice event."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="decision:city-san-rafael:2026-02-03:item-6a",
            jurisdiction="city-san-rafael",
            stance=Stance.SUPPORT,
            topics=["housing", "zoning"],
        )

        assert voice.kind == CIVIC_VOICE
        assert voice.entity_id == "decision:city-san-rafael:2026-02-03:item-6a"
        assert voice.jurisdiction == "city-san-rafael"
        assert voice.stance == Stance.SUPPORT
        assert voice.topics == ["housing", "zoning"]
        assert voice.verify()

    def test_voice_with_string_stance(self):
        """Can create voice with string stance."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test-entity",
            jurisdiction="test-j",
            stance="oppose",
        )

        assert voice.stance == Stance.OPPOSE

    def test_voice_revocation(self):
        """Can revoke a voice."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test-entity",
            jurisdiction="test-j",
            stance=Stance.WATCHING,
            content="revoked",
        )

        assert voice.is_revoked

    def test_voice_missing_d_tag(self):
        """Rejects voice without d-tag."""
        kp = NostrKeyPair.generate()
        event_id, pubkey, sig = sign_event(
            kp, 1000, CIVIC_VOICE,
            [["j", "test"], ["stance", "support"]],  # Missing d-tag
            ""
        )

        with pytest.raises(ValueError, match="d-tag"):
            CivicVoiceEvent(
                id=event_id,
                pubkey=pubkey,
                created_at=1000,
                kind=CIVIC_VOICE,
                tags=[["j", "test"], ["stance", "support"]],
                content="",
                sig=sig,
            )

    def test_voice_missing_stance(self):
        """Rejects voice without stance tag."""
        kp = NostrKeyPair.generate()
        event_id, pubkey, sig = sign_event(
            kp, 1000, CIVIC_VOICE,
            [["d", "entity"], ["j", "test"]],  # Missing stance
            ""
        )

        with pytest.raises(ValueError, match="stance"):
            CivicVoiceEvent(
                id=event_id,
                pubkey=pubkey,
                created_at=1000,
                kind=CIVIC_VOICE,
                tags=[["d", "entity"], ["j", "test"]],
                content="",
                sig=sig,
            )

    def test_voice_invalid_stance(self):
        """Rejects voice with invalid stance."""
        kp = NostrKeyPair.generate()
        event_id, pubkey, sig = sign_event(
            kp, 1000, CIVIC_VOICE,
            [["d", "entity"], ["j", "test"], ["stance", "invalid"]],
            ""
        )

        with pytest.raises(ValueError, match="Invalid stance"):
            CivicVoiceEvent(
                id=event_id,
                pubkey=pubkey,
                created_at=1000,
                kind=CIVIC_VOICE,
                tags=[["d", "entity"], ["j", "test"], ["stance", "invalid"]],
                content="",
                sig=sig,
            )


class TestCivicEntityEvent:
    """Tests for CivicEntityEvent (kind 30801)."""

    def test_create_entity(self):
        """Can create a civic entity event."""
        kp = NostrKeyPair.generate()
        entity = CivicEntityEvent.create(
            keypair=kp,
            entity_id="decision:city-san-rafael:2026-02-03:item-6a",
            jurisdiction="city-san-rafael",
            entity_type=EntityType.DECISION,
            title="4th Street Rezoning",
            topics=["housing", "zoning"],
            description="Proposal to rezone 4th Street",
            outcome=Outcome.PENDING,
        )

        assert entity.kind == CIVIC_ENTITY
        assert entity.entity_id == "decision:city-san-rafael:2026-02-03:item-6a"
        assert entity.jurisdiction == "city-san-rafael"
        assert entity.entity_type == EntityType.DECISION
        assert entity.title == "4th Street Rezoning"
        assert entity.topics == ["housing", "zoning"]
        assert entity.verify()

        content = entity.parsed_content
        assert content.description == "Proposal to rezone 4th Street"
        assert content.outcome == Outcome.PENDING

    def test_entity_with_extra_content(self):
        """Can include extra content fields."""
        kp = NostrKeyPair.generate()
        entity = CivicEntityEvent.create(
            keypair=kp,
            entity_id="meeting:city-sr:2026-02-03",
            jurisdiction="city-sr",
            entity_type=EntityType.MEETING,
            title="City Council Meeting",
            extra_content={"start_time": "6:00 PM", "location": "City Hall"},
        )

        content = json.loads(entity.content)
        assert content["start_time"] == "6:00 PM"
        assert content["location"] == "City Hall"

    def test_entity_missing_type(self):
        """Rejects entity without type tag."""
        kp = NostrKeyPair.generate()
        event_id, pubkey, sig = sign_event(
            kp, 1000, CIVIC_ENTITY,
            [["d", "entity"], ["j", "test"], ["title", "Test"]],
            "{}"
        )

        with pytest.raises(ValueError, match="type tag"):
            CivicEntityEvent(
                id=event_id,
                pubkey=pubkey,
                created_at=1000,
                kind=CIVIC_ENTITY,
                tags=[["d", "entity"], ["j", "test"], ["title", "Test"]],
                content="{}",
                sig=sig,
            )


class TestCivicVouchEvent:
    """Tests for CivicVouchEvent (kind 1800)."""

    def test_create_vouch(self):
        """Can create a vouch event."""
        voucher = NostrKeyPair.generate()
        vouchee = NostrKeyPair.generate()

        vouch = CivicVouchEvent.create(
            keypair=voucher,
            vouchee_pubkey=vouchee.public_key_hex,
            jurisdiction="city-san-rafael",
            content="I know this person from neighborhood meetings",
        )

        assert vouch.kind == CIVIC_VOUCH
        assert vouch.vouchee == vouchee.public_key_hex
        assert vouch.jurisdiction == "city-san-rafael"
        assert vouch.content == "I know this person from neighborhood meetings"
        assert vouch.verify()

    def test_vouch_missing_p_tag(self):
        """Rejects vouch without p-tag."""
        kp = NostrKeyPair.generate()
        event_id, pubkey, sig = sign_event(
            kp, 1000, CIVIC_VOUCH,
            [["j", "test"]],  # Missing p-tag
            ""
        )

        with pytest.raises(ValueError, match="p-tag"):
            CivicVouchEvent(
                id=event_id,
                pubkey=pubkey,
                created_at=1000,
                kind=CIVIC_VOUCH,
                tags=[["j", "test"]],
                content="",
                sig=sig,
            )


class TestKeyLinkAttestationEvent:
    """Tests for KeyLinkAttestationEvent (kind 1802)."""

    def test_parse_key_link(self):
        """Can parse a key link attestation."""
        new_key = NostrKeyPair.generate()
        old_key_hex = "c" * 64
        old_sig_hex = "d" * 128

        tags = [
            ["old-key", old_key_hex],
            ["old-sig", old_sig_hex],
        ]
        content = "Key migration attestation"

        event_id, pubkey, sig = sign_event(
            new_key, 1000, KEY_LINK_ATTESTATION, tags, content
        )

        event = KeyLinkAttestationEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=KEY_LINK_ATTESTATION,
            tags=tags,
            content=content,
            sig=sig,
        )

        assert event.old_key == old_key_hex
        assert event.old_signature == old_sig_hex
        assert event.verify()

    def test_key_link_missing_old_key(self):
        """Rejects key link without old-key tag."""
        kp = NostrKeyPair.generate()
        event_id, pubkey, sig = sign_event(
            kp, 1000, KEY_LINK_ATTESTATION,
            [["old-sig", "a" * 128]],
            ""
        )

        with pytest.raises(ValueError, match="old-key"):
            KeyLinkAttestationEvent(
                id=event_id,
                pubkey=pubkey,
                created_at=1000,
                kind=KEY_LINK_ATTESTATION,
                tags=[["old-sig", "a" * 128]],
                content="",
                sig=sig,
            )


class TestCivicProvenanceEvent:
    """Tests for CivicProvenanceEvent (kind 10800)."""

    def test_parse_provenance(self):
        """Can parse provenance record."""
        kp = NostrKeyPair.generate()
        tags = [
            ["first-voice", "2025-09-01"],
            ["total-voices", "23"],
            ["entities-touched", "12"],
            ["j", "city-san-rafael"],
            ["attestation", "physical", "city-san-rafael", "2026-01-15"],
        ]

        event_id, pubkey, sig = sign_event(
            kp, 1000, CIVIC_PROVENANCE, tags, ""
        )

        event = CivicProvenanceEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=CIVIC_PROVENANCE,
            tags=tags,
            content="",
            sig=sig,
        )

        assert event.first_voice_date == "2025-09-01"
        assert event.total_voices == 23
        assert event.entities_touched == 12
        assert event.primary_jurisdiction == "city-san-rafael"
        assert event.attestations == [("physical", "city-san-rafael", "2026-01-15")]


class TestCivicEventNotificationEvent:
    """Tests for CivicEventNotificationEvent (kind 1801)."""

    def test_parse_notification(self):
        """Can parse notification event."""
        relay_key = NostrKeyPair.generate()
        tags = [
            ["event-type", "agenda_published"],
            ["j", "city-san-rafael"],
            ["a", "30801:abc123:meeting:city-san-rafael:2026-02-03"],
        ]
        content = json.dumps({"title": "City Council Meeting"})

        event_id, pubkey, sig = sign_event(
            relay_key, 1000, CIVIC_EVENT_NOTIFICATION, tags, content
        )

        event = CivicEventNotificationEvent(
            id=event_id,
            pubkey=pubkey,
            created_at=1000,
            kind=CIVIC_EVENT_NOTIFICATION,
            tags=tags,
            content=content,
            sig=sig,
        )

        assert event.event_type == "agenda_published"
        assert event.jurisdiction == "city-san-rafael"
        assert event.referenced_event == "30801:abc123:meeting:city-san-rafael:2026-02-03"


class TestBuildTags:
    """Tests for build_tags helper."""

    def test_build_basic_tags(self):
        """Can build basic tag list."""
        tags = build_tags(
            d_tag="entity-id",
            jurisdiction="city-sr",
            topics=["housing", "zoning"],
        )

        assert ["d", "entity-id"] in tags
        assert ["j", "city-sr"] in tags
        assert ["t", "housing"] in tags
        assert ["t", "zoning"] in tags

    def test_build_with_kwargs(self):
        """Can add arbitrary tags via kwargs."""
        tags = build_tags(
            d_tag="entity",
            stance="support",
            type="decision",
        )

        assert ["d", "entity"] in tags
        assert ["stance", "support"] in tags
        assert ["type", "decision"] in tags

    def test_build_with_list_kwarg(self):
        """kwargs with list values create multiple tags."""
        tags = build_tags(custom=["a", "b", "c"])

        assert ["custom", "a"] in tags
        assert ["custom", "b"] in tags
        assert ["custom", "c"] in tags


class TestParseEvent:
    """Tests for parse_event function."""

    def test_parse_voice(self):
        """parse_event returns CivicVoiceEvent for kind 30800."""
        kp = NostrKeyPair.generate()
        voice = CivicVoiceEvent.create(
            keypair=kp,
            entity_id="test",
            jurisdiction="test-j",
            stance=Stance.SUPPORT,
        )

        parsed = parse_event(voice.to_dict())
        assert isinstance(parsed, CivicVoiceEvent)
        assert parsed.stance == Stance.SUPPORT

    def test_parse_entity(self):
        """parse_event returns CivicEntityEvent for kind 30801."""
        kp = NostrKeyPair.generate()
        entity = CivicEntityEvent.create(
            keypair=kp,
            entity_id="test",
            jurisdiction="test-j",
            entity_type=EntityType.DECISION,
            title="Test Decision",
        )

        parsed = parse_event(entity.to_dict())
        assert isinstance(parsed, CivicEntityEvent)
        assert parsed.entity_type == EntityType.DECISION

    def test_parse_unknown_kind(self):
        """parse_event returns base NostrEvent for unknown kinds."""
        kp = NostrKeyPair.generate()
        event_id, pubkey, sig = sign_event(kp, 1000, 9999, [], "test")

        parsed = parse_event({
            "id": event_id,
            "pubkey": pubkey,
            "created_at": 1000,
            "kind": 9999,
            "tags": [],
            "content": "test",
            "sig": sig,
        })

        assert type(parsed) is NostrEvent
        assert parsed.kind == 9999


class TestKindHelpers:
    """Tests for kind helper functions."""

    def test_is_addressable(self):
        """is_addressable identifies 30000-39999 range."""
        assert is_addressable(30800)  # CIVIC_VOICE
        assert is_addressable(30801)  # CIVIC_ENTITY
        assert is_addressable(30000)
        assert is_addressable(39999)
        assert not is_addressable(29999)
        assert not is_addressable(40000)
        assert not is_addressable(1)

    def test_is_replaceable(self):
        """is_replaceable identifies 10000-19999 range."""
        assert is_replaceable(10800)  # CIVIC_PROVENANCE
        assert is_replaceable(10000)
        assert is_replaceable(19999)
        assert not is_replaceable(9999)
        assert not is_replaceable(20000)
        assert not is_replaceable(30800)

    def test_is_civic_kind(self):
        """is_civic_kind identifies CivicOS kinds."""
        assert is_civic_kind(CIVIC_VOICE)
        assert is_civic_kind(CIVIC_ENTITY)
        assert is_civic_kind(CIVIC_SUBSCRIPTION)
        assert is_civic_kind(CIVIC_PROVENANCE)
        assert is_civic_kind(CIVIC_VOUCH)
        assert is_civic_kind(CIVIC_EVENT_NOTIFICATION)
        assert is_civic_kind(KEY_LINK_ATTESTATION)
        assert not is_civic_kind(1)  # Standard note
        assert not is_civic_kind(0)  # Metadata
