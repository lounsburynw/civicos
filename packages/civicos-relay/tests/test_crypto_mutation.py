"""
Mutation-hardening tests for civicos_relay.voice.crypto.

These tests target the 90% mutation testing threshold for P1-security paths.
Every verify_* function in crypto.py must have:
- Positive-path coverage (valid signature verifies)
- Tampering coverage (each signed field produces a distinct failure)
- Length/format coverage (wrong hex lengths return False without raising)
- Exception-path coverage (malformed hex returns False, not True)
- Field-pinning coverage (sign_* outputs have exact expected field values)

Where the function is self-consistent (sign+verify use the same helper),
we pin the expected Nostr event structure and hash via an *independent*
json + hashlib computation so a mutation to the shared helper still fails.
"""

import hashlib
import json
import pytest
from datetime import datetime
from typing import Optional

from coincurve import PrivateKey

from civicos_relay.voice.crypto import (
    KeyPair,
    _check_key_sig,
    _compute_nostr_event_id,
    _schnorr_verify,
    _voice_message,
    sign_voice,
    sign_message,
    sign_attestation_event,
    verify_voice,
    verify_comment,
    verify_feedback,
    verify_initiative,
    verify_commitment,
    verify_completion,
    verify_withdrawal,
    verify_action_event,
    verify_attestation_request,
    verify_attestation_proof,
    verify_code_batch,
    verify_signature,
)
from civicos_relay.voice.models import Voice, Stance, Comment, Feedback


# -----------------------------------------------------------------------------
# Test helpers
# -----------------------------------------------------------------------------


def _direct_event_id(pubkey: str, created_at: int, kind: int, tags: list, content: str) -> str:
    """Ground-truth Nostr event ID (independent of crypto._compute_nostr_event_id).

    Intentionally written inline so mutations to crypto.py cannot change it.
    """
    serialized = json.dumps(
        [0, pubkey, created_at, kind, tags, content],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _sign_hex(kp: KeyPair, event_id_hex: str) -> str:
    pk = PrivateKey(bytes.fromhex(kp.private_key_hex))
    return pk.sign_schnorr(bytes.fromhex(event_id_hex)).hex()


def _sign_for(kp: KeyPair, kind: int, tags: list, content: str, created_at: Optional[int] = None):
    """Build and sign a Nostr event using ground-truth id. Returns (sig_hex, created_at)."""
    if created_at is None:
        created_at = 1_700_000_000
    eid = _direct_event_id(kp.public_key_hex, created_at, kind, tags, content)
    return _sign_hex(kp, eid), created_at


# =============================================================================
# _compute_nostr_event_id — pin exact NIP-01 serialization
# =============================================================================


class TestComputeNostrEventId:
    """Pin the event-id contract against an independent json/sha256 computation."""

    def test_matches_direct_sha256_ascii(self):
        pubkey = "01" * 32
        created_at = 1_738_464_000
        kind = 30800
        tags = [["d", "agenda:item-1"], ["j", "city-san-rafael"]]
        content = "hello world"
        expected = _direct_event_id(pubkey, created_at, kind, tags, content)
        assert _compute_nostr_event_id(pubkey, created_at, kind, tags, content) == expected

    def test_prefix_byte_is_literal_zero(self):
        """NIP-01 requires the first element of the serialized array to be 0."""
        pubkey = "02" * 32
        tags = [["t", "test"]]
        content = "x"
        correct = hashlib.sha256(
            f'[0,"{pubkey}",1,1,[["t","test"]],"x"]'.encode("utf-8")
        ).hexdigest()
        wrong_prefix = hashlib.sha256(
            f'[1,"{pubkey}",1,1,[["t","test"]],"x"]'.encode("utf-8")
        ).hexdigest()
        result = _compute_nostr_event_id(pubkey, 1, 1, tags, content)
        assert result == correct
        assert result != wrong_prefix

    def test_no_whitespace_between_items(self):
        """Must use (',', ':') separators — default (', ', ': ') would differ.

        Note: the key-value separator only matters for dict serialization; Nostr
        events serialize to JSON arrays only, so mutations to the second tuple
        element are equivalent mutants and not asserted here.
        """
        pubkey = "03" * 32
        correct = hashlib.sha256(
            json.dumps(
                [0, pubkey, 1, 1, [], ""],
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        with_default = hashlib.sha256(
            json.dumps([0, pubkey, 1, 1, [], ""], ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        with_space_item = hashlib.sha256(
            json.dumps(
                [0, pubkey, 1, 1, [], ""],
                separators=(", ", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        result = _compute_nostr_event_id(pubkey, 1, 1, [], "")
        assert result == correct
        assert result != with_default
        assert result != with_space_item

    def test_non_ascii_content_not_escaped(self):
        """ensure_ascii must be False so non-ASCII content hashes as UTF-8 bytes."""
        pubkey = "04" * 32
        content = "Hello 世界"
        expected_serialized = f'[0,"{pubkey}",1,1,[],"Hello 世界"]'
        expected = hashlib.sha256(expected_serialized.encode("utf-8")).hexdigest()
        escaped_serialized = f'[0,"{pubkey}",1,1,[],"Hello \\u4e16\\u754c"]'
        escaped = hashlib.sha256(escaped_serialized.encode("utf-8")).hexdigest()
        result = _compute_nostr_event_id(pubkey, 1, 1, [], content)
        assert result == expected
        assert result != escaped

    def test_tags_affect_hash(self):
        pubkey = "05" * 32
        without = _compute_nostr_event_id(pubkey, 1, 1, [], "x")
        with_tag = _compute_nostr_event_id(pubkey, 1, 1, [["d", "v"]], "x")
        assert without != with_tag

    def test_kind_affects_hash(self):
        pubkey = "06" * 32
        k1 = _compute_nostr_event_id(pubkey, 1, 1, [], "")
        k2 = _compute_nostr_event_id(pubkey, 1, 2, [], "")
        assert k1 != k2

    def test_created_at_affects_hash(self):
        pubkey = "07" * 32
        a = _compute_nostr_event_id(pubkey, 100, 1, [], "")
        b = _compute_nostr_event_id(pubkey, 101, 1, [], "")
        assert a != b

    def test_pubkey_affects_hash(self):
        a = _compute_nostr_event_id("08" * 32, 1, 1, [], "")
        b = _compute_nostr_event_id("09" * 32, 1, 1, [], "")
        assert a != b

    def test_content_affects_hash(self):
        pubkey = "0a" * 32
        a = _compute_nostr_event_id(pubkey, 1, 1, [], "one")
        b = _compute_nostr_event_id(pubkey, 1, 1, [], "two")
        assert a != b

    def test_returns_64_hex_chars(self):
        out = _compute_nostr_event_id("0b" * 32, 1, 1, [], "")
        assert len(out) == 64
        int(out, 16)  # parseable as hex


# =============================================================================
# _voice_message — canonical string format
# =============================================================================


class TestVoiceMessage:
    def test_format_is_exact(self):
        assert _voice_message("entity-x", Stance.SUPPORT) == "civicos:voice:v1:entity-x:support"

    def test_oppose_value(self):
        assert _voice_message("e", Stance.OPPOSE) == "civicos:voice:v1:e:oppose"

    def test_watching_value(self):
        assert _voice_message("e", Stance.WATCHING) == "civicos:voice:v1:e:watching"


# =============================================================================
# sign_voice — pin output fields (kills field-value mutations)
# =============================================================================


class TestSignVoiceOutput:
    def test_fields_match_inputs(self):
        kp = KeyPair.generate()
        voice = sign_voice(kp, "agenda:item", Stance.SUPPORT, jurisdiction="city-san-rafael")
        assert voice.entity == "agenda:item"
        assert voice.stance == Stance.SUPPORT
        assert voice.public_key == kp.public_key_hex
        assert voice.jurisdiction == "city-san-rafael"
        assert isinstance(voice.timestamp, datetime)
        assert isinstance(voice.created_at, int)
        assert voice.created_at > 0
        # Timestamp and created_at should describe the same instant (within a second)
        assert abs(int(voice.timestamp.timestamp()) - voice.created_at) <= 1
        assert len(voice.signature) == 128

    def test_jurisdiction_none_is_preserved(self):
        kp = KeyPair.generate()
        voice = sign_voice(kp, "e", Stance.OPPOSE)
        assert voice.jurisdiction is None
        assert voice.stance == Stance.OPPOSE

    def test_jurisdiction_nondefault_not_overwritten(self):
        """Kill mutations that drop jurisdiction or replace with None."""
        kp = KeyPair.generate()
        voice = sign_voice(kp, "e", Stance.SUPPORT, jurisdiction="city-berkeley")
        assert voice.jurisdiction == "city-berkeley"
        assert verify_voice(voice) is True

    def test_signature_over_correct_event_id(self):
        """Signature must match a Nostr event built from (30800, canonical tags, content)."""
        kp = KeyPair.generate()
        voice = sign_voice(kp, "agenda:x", Stance.SUPPORT, jurisdiction="j")
        content = f"civicos:voice:v1:agenda:x:support:{voice.created_at}"
        tags = [["d", "agenda:x"], ["j", "j"], ["stance", "support"]]
        eid = _direct_event_id(voice.public_key, voice.created_at, 30800, tags, content)
        assert _schnorr_verify(voice.public_key, voice.signature, eid) is True


# =============================================================================
# verify_voice — edge cases
# =============================================================================


class TestVerifyVoiceEdgeCases:
    def _valid(self) -> Voice:
        kp = KeyPair.generate()
        return sign_voice(kp, "e", Stance.SUPPORT, jurisdiction="j")

    def test_empty_pubkey_returns_false(self):
        v = self._valid()
        tampered = Voice(
            entity=v.entity,
            stance=v.stance,
            public_key="",
            signature=v.signature,
            timestamp=v.timestamp,
            created_at=v.created_at,
            jurisdiction=v.jurisdiction,
        )
        assert verify_voice(tampered) is False

    def test_empty_sig_returns_false(self):
        v = self._valid()
        tampered = Voice(
            entity=v.entity,
            stance=v.stance,
            public_key=v.public_key,
            signature="",
            timestamp=v.timestamp,
            created_at=v.created_at,
            jurisdiction=v.jurisdiction,
        )
        assert verify_voice(tampered) is False

    def test_wrong_pubkey_length_returns_false(self):
        """Kill `len(pubkey)!=64 or len(sig)!=128` → `and` mutation."""
        v = self._valid()
        tampered = Voice(
            entity=v.entity,
            stance=v.stance,
            public_key="ab" * 30,  # 60 hex chars, not 64
            signature=v.signature,
            timestamp=v.timestamp,
            created_at=v.created_at,
            jurisdiction=v.jurisdiction,
        )
        assert verify_voice(tampered) is False

    def test_wrong_sig_length_returns_false(self):
        v = self._valid()
        tampered = Voice(
            entity=v.entity,
            stance=v.stance,
            public_key=v.public_key,
            signature="cd" * 60,  # 120 hex chars, not 128
            timestamp=v.timestamp,
            created_at=v.created_at,
            jurisdiction=v.jurisdiction,
        )
        assert verify_voice(tampered) is False

    def test_invalid_hex_in_pubkey_returns_false(self):
        """Exception path — bytes.fromhex should raise, caught by `except`."""
        v = self._valid()
        tampered = Voice(
            entity=v.entity,
            stance=v.stance,
            public_key="Z" * 64,
            signature=v.signature,
            timestamp=v.timestamp,
            created_at=v.created_at,
            jurisdiction=v.jurisdiction,
        )
        assert verify_voice(tampered) is False

    def test_invalid_hex_in_signature_returns_false(self):
        v = self._valid()
        tampered = Voice(
            entity=v.entity,
            stance=v.stance,
            public_key=v.public_key,
            signature="Z" * 128,
            timestamp=v.timestamp,
            created_at=v.created_at,
            jurisdiction=v.jurisdiction,
        )
        assert verify_voice(tampered) is False

    def test_wrong_created_at_returns_false(self):
        v = self._valid()
        tampered = Voice(
            entity=v.entity,
            stance=v.stance,
            public_key=v.public_key,
            signature=v.signature,
            timestamp=v.timestamp,
            created_at=v.created_at + 1,
            jurisdiction=v.jurisdiction,
        )
        assert verify_voice(tampered) is False

    def test_wrong_jurisdiction_returns_false(self):
        v = self._valid()
        tampered = Voice(
            entity=v.entity,
            stance=v.stance,
            public_key=v.public_key,
            signature=v.signature,
            timestamp=v.timestamp,
            created_at=v.created_at,
            jurisdiction="city-other",
        )
        assert verify_voice(tampered) is False

    def test_none_created_at_returns_false(self):
        """Bypass pydantic validation to reach the `voice.created_at is None` branch."""
        v = self._valid()
        payload = v.model_dump()
        payload["created_at"] = None
        tampered = Voice.model_construct(**payload)
        assert verify_voice(tampered) is False

    def test_exception_path_returns_false(self):
        """Force an AttributeError inside the try block to exercise `except: return False`."""
        v = self._valid()
        payload = v.model_dump()
        payload["stance"] = None  # voice.stance.value will raise AttributeError
        tampered = Voice.model_construct(**payload)
        assert verify_voice(tampered) is False


# =============================================================================
# verify_comment — full coverage
# =============================================================================


class TestVerifyComment:
    def _signed_comment(self, kp, *, entity="agenda:1", text="Great idea", jurisdiction="j", stance=None, created_at=1_700_000_000):
        tags = [["d", entity], ["j", jurisdiction]]
        if stance:
            tags.append(["stance", stance])
        eid = _direct_event_id(kp.public_key_hex, created_at, 30803, tags, text)
        sig = _sign_hex(kp, eid)
        return Comment(
            entity=entity,
            comment_text=text,
            public_key=kp.public_key_hex,
            signature=sig,
            jurisdiction=jurisdiction,
            stance=stance,
            created_at=created_at,
        )

    def test_valid_comment_without_stance_verifies(self):
        kp = KeyPair.generate()
        c = self._signed_comment(kp)
        assert verify_comment(c) is True

    def test_valid_comment_with_stance_verifies(self):
        kp = KeyPair.generate()
        c = self._signed_comment(kp, stance="support")
        assert verify_comment(c) is True

    def test_tampered_text_fails(self):
        kp = KeyPair.generate()
        c = self._signed_comment(kp)
        tampered = Comment(
            entity=c.entity,
            comment_text="Different text",
            public_key=c.public_key,
            signature=c.signature,
            jurisdiction=c.jurisdiction,
            stance=c.stance,
            created_at=c.created_at,
        )
        assert verify_comment(tampered) is False

    def test_tampered_entity_fails(self):
        kp = KeyPair.generate()
        c = self._signed_comment(kp, entity="agenda:original")
        tampered = Comment(
            entity="agenda:changed",
            comment_text=c.comment_text,
            public_key=c.public_key,
            signature=c.signature,
            jurisdiction=c.jurisdiction,
            stance=c.stance,
            created_at=c.created_at,
        )
        assert verify_comment(tampered) is False

    def test_tampered_jurisdiction_fails(self):
        kp = KeyPair.generate()
        c = self._signed_comment(kp, jurisdiction="city-a")
        tampered = Comment(
            entity=c.entity,
            comment_text=c.comment_text,
            public_key=c.public_key,
            signature=c.signature,
            jurisdiction="city-b",
            stance=c.stance,
            created_at=c.created_at,
        )
        assert verify_comment(tampered) is False

    def test_stance_present_but_was_absent_fails(self):
        """Adding a stance tag after signing without stance should fail."""
        kp = KeyPair.generate()
        c = self._signed_comment(kp, stance=None)
        tampered = Comment(
            entity=c.entity,
            comment_text=c.comment_text,
            public_key=c.public_key,
            signature=c.signature,
            jurisdiction=c.jurisdiction,
            stance="support",
            created_at=c.created_at,
        )
        assert verify_comment(tampered) is False

    def test_empty_pubkey_returns_false(self):
        kp = KeyPair.generate()
        c = self._signed_comment(kp)
        tampered = Comment(
            entity=c.entity,
            comment_text=c.comment_text,
            public_key="",
            signature=c.signature,
            jurisdiction=c.jurisdiction,
            stance=c.stance,
            created_at=c.created_at,
        )
        assert verify_comment(tampered) is False

    def test_empty_sig_returns_false(self):
        kp = KeyPair.generate()
        c = self._signed_comment(kp)
        tampered = Comment(
            entity=c.entity,
            comment_text=c.comment_text,
            public_key=c.public_key,
            signature="",
            jurisdiction=c.jurisdiction,
            stance=c.stance,
            created_at=c.created_at,
        )
        assert verify_comment(tampered) is False

    def test_short_pubkey_returns_false(self):
        kp = KeyPair.generate()
        c = self._signed_comment(kp)
        tampered = Comment(
            entity=c.entity,
            comment_text=c.comment_text,
            public_key="ab" * 30,
            signature=c.signature,
            jurisdiction=c.jurisdiction,
            stance=c.stance,
            created_at=c.created_at,
        )
        assert verify_comment(tampered) is False

    def test_short_sig_returns_false(self):
        kp = KeyPair.generate()
        c = self._signed_comment(kp)
        tampered = Comment(
            entity=c.entity,
            comment_text=c.comment_text,
            public_key=c.public_key,
            signature="ab" * 60,
            jurisdiction=c.jurisdiction,
            stance=c.stance,
            created_at=c.created_at,
        )
        assert verify_comment(tampered) is False

    def test_none_created_at_returns_false(self):
        kp = KeyPair.generate()
        c = self._signed_comment(kp)
        payload = c.model_dump()
        payload["created_at"] = None
        tampered = Comment.model_construct(**payload)
        assert verify_comment(tampered) is False

    def test_invalid_hex_pubkey_returns_false(self):
        """Exception path — must not raise."""
        kp = KeyPair.generate()
        c = self._signed_comment(kp)
        tampered = Comment(
            entity=c.entity,
            comment_text=c.comment_text,
            public_key="Z" * 64,
            signature=c.signature,
            jurisdiction=c.jurisdiction,
            stance=c.stance,
            created_at=c.created_at,
        )
        assert verify_comment(tampered) is False

    def test_uses_kind_30803(self):
        """A comment signed under the wrong kind must not verify."""
        kp = KeyPair.generate()
        tags = [["d", "e"], ["j", "j"]]
        # Sign under kind 1 instead of 30803
        wrong_eid = _direct_event_id(kp.public_key_hex, 1_700_000_000, 1, tags, "hi")
        wrong_sig = _sign_hex(kp, wrong_eid)
        bogus = Comment(
            entity="e",
            comment_text="hi",
            public_key=kp.public_key_hex,
            signature=wrong_sig,
            jurisdiction="j",
            stance=None,
            created_at=1_700_000_000,
        )
        assert verify_comment(bogus) is False

    def test_exception_path_returns_false(self):
        """Force an AttributeError inside the try block via bypassed validation."""
        kp = KeyPair.generate()
        c = self._signed_comment(kp)
        payload = c.model_dump()
        payload["entity"] = 12345  # int has no tags-compatible behavior; raises on json serialization path? no - covered by integer branch
        # Use a non-JSON-serializable entity via a plain object to trigger TypeError in json.dumps
        class _Opaque:
            pass
        payload["entity"] = _Opaque()
        tampered = Comment.model_construct(**payload)
        assert verify_comment(tampered) is False


# =============================================================================
# verify_feedback — full coverage
# =============================================================================


class TestVerifyFeedback:
    def _signed_feedback(self, kp, *, ftype="bug", jurisdiction="j", content="broken", created_at=1_700_000_000):
        tags = [["t", ftype], ["j", jurisdiction], ["v", "1"]]
        eid = _direct_event_id(kp.public_key_hex, created_at, 1804, tags, content)
        sig = _sign_hex(kp, eid)
        return Feedback(
            feedback_type=ftype,
            content=content,
            public_key=kp.public_key_hex,
            signature=sig,
            jurisdiction=jurisdiction,
            created_at=created_at,
        )

    def test_valid_feedback_verifies(self):
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp)
        assert verify_feedback(fb) is True

    def test_tampered_content_fails(self):
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp)
        tampered = Feedback(
            feedback_type=fb.feedback_type,
            content="different",
            public_key=fb.public_key,
            signature=fb.signature,
            jurisdiction=fb.jurisdiction,
            created_at=fb.created_at,
        )
        assert verify_feedback(tampered) is False

    def test_tampered_type_fails(self):
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp, ftype="bug")
        tampered = Feedback(
            feedback_type="feature",
            content=fb.content,
            public_key=fb.public_key,
            signature=fb.signature,
            jurisdiction=fb.jurisdiction,
            created_at=fb.created_at,
        )
        assert verify_feedback(tampered) is False

    def test_tampered_jurisdiction_fails(self):
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp, jurisdiction="city-a")
        tampered = Feedback(
            feedback_type=fb.feedback_type,
            content=fb.content,
            public_key=fb.public_key,
            signature=fb.signature,
            jurisdiction="city-b",
            created_at=fb.created_at,
        )
        assert verify_feedback(tampered) is False

    def test_tampered_created_at_fails(self):
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp)
        tampered = Feedback(
            feedback_type=fb.feedback_type,
            content=fb.content,
            public_key=fb.public_key,
            signature=fb.signature,
            jurisdiction=fb.jurisdiction,
            created_at=fb.created_at + 1,
        )
        assert verify_feedback(tampered) is False

    def test_empty_pubkey_returns_false(self):
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp)
        tampered = Feedback(
            feedback_type=fb.feedback_type,
            content=fb.content,
            public_key="",
            signature=fb.signature,
            jurisdiction=fb.jurisdiction,
            created_at=fb.created_at,
        )
        assert verify_feedback(tampered) is False

    def test_empty_sig_returns_false(self):
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp)
        tampered = Feedback(
            feedback_type=fb.feedback_type,
            content=fb.content,
            public_key=fb.public_key,
            signature="",
            jurisdiction=fb.jurisdiction,
            created_at=fb.created_at,
        )
        assert verify_feedback(tampered) is False

    def test_short_pubkey_returns_false(self):
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp)
        tampered = Feedback(
            feedback_type=fb.feedback_type,
            content=fb.content,
            public_key="ab" * 30,
            signature=fb.signature,
            jurisdiction=fb.jurisdiction,
            created_at=fb.created_at,
        )
        assert verify_feedback(tampered) is False

    def test_short_sig_returns_false(self):
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp)
        tampered = Feedback(
            feedback_type=fb.feedback_type,
            content=fb.content,
            public_key=fb.public_key,
            signature="ab" * 60,
            jurisdiction=fb.jurisdiction,
            created_at=fb.created_at,
        )
        assert verify_feedback(tampered) is False

    def test_none_created_at_returns_false(self):
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp)
        payload = fb.model_dump()
        payload["created_at"] = None
        tampered = Feedback.model_construct(**payload)
        assert verify_feedback(tampered) is False

    def test_invalid_hex_returns_false(self):
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp)
        tampered = Feedback(
            feedback_type=fb.feedback_type,
            content=fb.content,
            public_key="Z" * 64,
            signature=fb.signature,
            jurisdiction=fb.jurisdiction,
            created_at=fb.created_at,
        )
        assert verify_feedback(tampered) is False

    def test_uses_kind_1804(self):
        """Feedback signed under a wrong kind must not verify."""
        kp = KeyPair.generate()
        ftype, jurisdiction, content, created_at = "bug", "j", "x", 1_700_000_000
        tags = [["t", ftype], ["j", jurisdiction], ["v", "1"]]
        wrong_eid = _direct_event_id(kp.public_key_hex, created_at, 1805, tags, content)
        wrong_sig = _sign_hex(kp, wrong_eid)
        bogus = Feedback(
            feedback_type=ftype,
            content=content,
            public_key=kp.public_key_hex,
            signature=wrong_sig,
            jurisdiction=jurisdiction,
            created_at=created_at,
        )
        assert verify_feedback(bogus) is False

    def test_exception_path_returns_false(self):
        """Non-JSON-serializable feedback_type triggers TypeError inside the try."""
        kp = KeyPair.generate()
        fb = self._signed_feedback(kp)
        payload = fb.model_dump()

        class _Opaque:
            pass

        payload["feedback_type"] = _Opaque()
        tampered = Feedback.model_construct(**payload)
        assert verify_feedback(tampered) is False


# =============================================================================
# verify_initiative
# =============================================================================


class TestVerifyInitiative:
    def _args(self, kp, *, jurisdiction="city-san-rafael", topic="housing", created_at=1_700_000_000):
        tags = [["d", f"initiative:{jurisdiction}:{topic}"], ["j", jurisdiction]]
        content = f"civicos:initiative:v1:{jurisdiction}:{topic}:{created_at}"
        eid = _direct_event_id(kp.public_key_hex, created_at, 30800, tags, content)
        sig = _sign_hex(kp, eid)
        return kp.public_key_hex, sig, jurisdiction, topic, created_at

    def test_valid_initiative_verifies(self):
        kp = KeyPair.generate()
        assert verify_initiative(*self._args(kp)) is True

    def test_tampered_topic_fails(self):
        kp = KeyPair.generate()
        pk, sig, j, _topic, ts = self._args(kp, topic="housing")
        assert verify_initiative(pk, sig, j, "parks", ts) is False

    def test_tampered_jurisdiction_fails(self):
        kp = KeyPair.generate()
        pk, sig, _j, topic, ts = self._args(kp, jurisdiction="city-a")
        assert verify_initiative(pk, sig, "city-b", topic, ts) is False

    def test_tampered_created_at_fails(self):
        kp = KeyPair.generate()
        pk, sig, j, topic, ts = self._args(kp)
        assert verify_initiative(pk, sig, j, topic, ts + 1) is False

    def test_empty_pubkey_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, j, topic, ts = self._args(kp)
        assert verify_initiative("", sig, j, topic, ts) is False

    def test_empty_signature_returns_false(self):
        kp = KeyPair.generate()
        pk, _sig, j, topic, ts = self._args(kp)
        assert verify_initiative(pk, "", j, topic, ts) is False

    def test_short_pubkey_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, j, topic, ts = self._args(kp)
        assert verify_initiative("ab" * 30, sig, j, topic, ts) is False

    def test_short_signature_returns_false(self):
        kp = KeyPair.generate()
        pk, _sig, j, topic, ts = self._args(kp)
        assert verify_initiative(pk, "ab" * 60, j, topic, ts) is False

    def test_invalid_hex_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, j, topic, ts = self._args(kp)
        assert verify_initiative("Z" * 64, sig, j, topic, ts) is False

    def test_wrong_key_pair_returns_false(self):
        kp = KeyPair.generate()
        other = KeyPair.generate()
        _pk, sig, j, topic, ts = self._args(kp)
        assert verify_initiative(other.public_key_hex, sig, j, topic, ts) is False

    def test_exception_path_returns_false(self):
        """Non-JSON-serializable created_at triggers TypeError in json.dumps, caught by except."""
        kp = KeyPair.generate()
        bad_ts = datetime.utcnow()  # datetime is not JSON-serializable
        assert verify_initiative(kp.public_key_hex, "b" * 128, "j", "topic", bad_ts) is False


# =============================================================================
# verify_commitment
# =============================================================================


class TestVerifyCommitment:
    def _args(self, kp, *, action_id="action:x", jurisdiction="j", created_at=1_700_000_000):
        tags = [["d", action_id], ["j", jurisdiction], ["action", "commitment"]]
        content = f"civicos:action:v1:{action_id}:commitment:{created_at}"
        eid = _direct_event_id(kp.public_key_hex, created_at, 30811, tags, content)
        sig = _sign_hex(kp, eid)
        return kp.public_key_hex, sig, action_id, jurisdiction, created_at

    def test_valid_commitment_verifies(self):
        kp = KeyPair.generate()
        assert verify_commitment(*self._args(kp)) is True

    def test_tampered_action_id_fails(self):
        kp = KeyPair.generate()
        pk, sig, _aid, j, ts = self._args(kp, action_id="action:a")
        assert verify_commitment(pk, sig, "action:b", j, ts) is False

    def test_tampered_jurisdiction_fails(self):
        kp = KeyPair.generate()
        pk, sig, aid, _j, ts = self._args(kp, jurisdiction="city-a")
        assert verify_commitment(pk, sig, aid, "city-b", ts) is False

    def test_tampered_created_at_fails(self):
        kp = KeyPair.generate()
        pk, sig, aid, j, ts = self._args(kp)
        assert verify_commitment(pk, sig, aid, j, ts + 1) is False

    def test_empty_pubkey_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, aid, j, ts = self._args(kp)
        assert verify_commitment("", sig, aid, j, ts) is False

    def test_empty_sig_returns_false(self):
        kp = KeyPair.generate()
        pk, _sig, aid, j, ts = self._args(kp)
        assert verify_commitment(pk, "", aid, j, ts) is False

    def test_short_lengths_return_false(self):
        kp = KeyPair.generate()
        pk, sig, aid, j, ts = self._args(kp)
        assert verify_commitment("ab" * 30, sig, aid, j, ts) is False
        assert verify_commitment(pk, "ab" * 60, aid, j, ts) is False

    def test_invalid_hex_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, aid, j, ts = self._args(kp)
        assert verify_commitment("Z" * 64, sig, aid, j, ts) is False

    def test_exception_path_returns_false(self):
        kp = KeyPair.generate()
        bad_ts = datetime.utcnow()
        assert verify_commitment(kp.public_key_hex, "b" * 128, "aid", "j", bad_ts) is False


# =============================================================================
# verify_completion
# =============================================================================


class TestVerifyCompletion:
    def _args(self, kp, *, action_id="action:x", jurisdiction="j", created_at=1_700_000_000, evidence_url=None):
        tags = [["d", action_id], ["j", jurisdiction], ["action", "completion"]]
        if evidence_url:
            tags.append(["evidence", evidence_url])
        base = f"civicos:action:v1:{action_id}:completion:{created_at}"
        content = f"{base}:{evidence_url}" if evidence_url else base
        eid = _direct_event_id(kp.public_key_hex, created_at, 30812, tags, content)
        sig = _sign_hex(kp, eid)
        return kp.public_key_hex, sig, action_id, jurisdiction, created_at, evidence_url

    def test_valid_completion_without_evidence_verifies(self):
        kp = KeyPair.generate()
        pk, sig, aid, j, ts, evidence = self._args(kp)
        assert verify_completion(pk, sig, aid, j, ts, evidence) is True

    def test_valid_completion_with_evidence_verifies(self):
        kp = KeyPair.generate()
        pk, sig, aid, j, ts, evidence = self._args(kp, evidence_url="https://x.test/proof")
        assert verify_completion(pk, sig, aid, j, ts, evidence) is True

    def test_completion_without_evidence_rejects_evidence_at_verify(self):
        """If the signed content was base-only, adding an evidence URL at verify must fail."""
        kp = KeyPair.generate()
        pk, sig, aid, j, ts, _ev = self._args(kp, evidence_url=None)
        assert verify_completion(pk, sig, aid, j, ts, "https://x.test/unexpected") is False

    def test_completion_with_evidence_rejects_missing_evidence_at_verify(self):
        kp = KeyPair.generate()
        pk, sig, aid, j, ts, _ev = self._args(kp, evidence_url="https://x.test/p")
        assert verify_completion(pk, sig, aid, j, ts, None) is False

    def test_tampered_action_id_fails(self):
        kp = KeyPair.generate()
        pk, sig, _aid, j, ts, ev = self._args(kp, action_id="a:1")
        assert verify_completion(pk, sig, "a:2", j, ts, ev) is False

    def test_tampered_jurisdiction_fails(self):
        kp = KeyPair.generate()
        pk, sig, aid, _j, ts, ev = self._args(kp, jurisdiction="c-a")
        assert verify_completion(pk, sig, aid, "c-b", ts, ev) is False

    def test_tampered_evidence_url_fails(self):
        kp = KeyPair.generate()
        pk, sig, aid, j, ts, _ev = self._args(kp, evidence_url="https://x.test/a")
        assert verify_completion(pk, sig, aid, j, ts, "https://x.test/b") is False

    def test_empty_pubkey_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, aid, j, ts, ev = self._args(kp)
        assert verify_completion("", sig, aid, j, ts, ev) is False

    def test_empty_sig_returns_false(self):
        kp = KeyPair.generate()
        pk, _sig, aid, j, ts, ev = self._args(kp)
        assert verify_completion(pk, "", aid, j, ts, ev) is False

    def test_short_lengths_return_false(self):
        kp = KeyPair.generate()
        pk, sig, aid, j, ts, ev = self._args(kp)
        assert verify_completion("ab" * 30, sig, aid, j, ts, ev) is False
        assert verify_completion(pk, "ab" * 60, aid, j, ts, ev) is False

    def test_invalid_hex_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, aid, j, ts, ev = self._args(kp)
        assert verify_completion("Z" * 64, sig, aid, j, ts, ev) is False

    def test_exception_path_returns_false(self):
        kp = KeyPair.generate()
        bad_ts = datetime.utcnow()
        assert verify_completion(kp.public_key_hex, "b" * 128, "aid", "j", bad_ts) is False


# =============================================================================
# verify_withdrawal
# =============================================================================


class TestVerifyWithdrawal:
    def _args(self, kp, *, action_id="action:x", created_at=1_700_000_000):
        tags = [["d", action_id], ["action", "withdraw"]]
        content = f"civicos:withdraw:v1:{action_id}:{created_at}"
        eid = _direct_event_id(kp.public_key_hex, created_at, 30811, tags, content)
        sig = _sign_hex(kp, eid)
        return kp.public_key_hex, sig, action_id, created_at

    def test_valid_withdrawal_verifies(self):
        kp = KeyPair.generate()
        assert verify_withdrawal(*self._args(kp)) is True

    def test_tampered_action_id_fails(self):
        kp = KeyPair.generate()
        pk, sig, _aid, ts = self._args(kp, action_id="a:1")
        assert verify_withdrawal(pk, sig, "a:2", ts) is False

    def test_tampered_created_at_fails(self):
        kp = KeyPair.generate()
        pk, sig, aid, ts = self._args(kp)
        assert verify_withdrawal(pk, sig, aid, ts + 1) is False

    def test_empty_pubkey_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, aid, ts = self._args(kp)
        assert verify_withdrawal("", sig, aid, ts) is False

    def test_empty_sig_returns_false(self):
        kp = KeyPair.generate()
        pk, _sig, aid, ts = self._args(kp)
        assert verify_withdrawal(pk, "", aid, ts) is False

    def test_short_lengths_return_false(self):
        kp = KeyPair.generate()
        pk, sig, aid, ts = self._args(kp)
        assert verify_withdrawal("ab" * 30, sig, aid, ts) is False
        assert verify_withdrawal(pk, "ab" * 60, aid, ts) is False

    def test_invalid_hex_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, aid, ts = self._args(kp)
        assert verify_withdrawal("Z" * 64, sig, aid, ts) is False

    def test_withdrawal_is_distinct_from_commitment(self):
        """A commitment signature must not verify as a withdrawal."""
        kp = KeyPair.generate()
        # Sign a commitment
        commit_tags = [["d", "a"], ["j", "j"], ["action", "commitment"]]
        commit_content = f"civicos:action:v1:a:commitment:{1_700_000_000}"
        commit_eid = _direct_event_id(kp.public_key_hex, 1_700_000_000, 30811, commit_tags, commit_content)
        commit_sig = _sign_hex(kp, commit_eid)
        assert verify_withdrawal(kp.public_key_hex, commit_sig, "a", 1_700_000_000) is False

    def test_exception_path_returns_false(self):
        kp = KeyPair.generate()
        bad_ts = datetime.utcnow()
        assert verify_withdrawal(kp.public_key_hex, "b" * 128, "aid", bad_ts) is False


# =============================================================================
# verify_action_event
# =============================================================================


class TestVerifyActionEvent:
    def _args(self, kp, *, initiative_id="init:1", action_type="written_comment", created_at=1_700_000_000):
        d_tag = f"action:{initiative_id}:{action_type}"
        tags = [["d", d_tag], ["initiative", initiative_id]]
        content = f"civicos:action:v1:{initiative_id}:{action_type}:{created_at}"
        eid = _direct_event_id(kp.public_key_hex, created_at, 30810, tags, content)
        sig = _sign_hex(kp, eid)
        return kp.public_key_hex, sig, initiative_id, action_type, created_at

    def test_valid_action_event_verifies(self):
        kp = KeyPair.generate()
        assert verify_action_event(*self._args(kp)) is True

    def test_tampered_initiative_fails(self):
        kp = KeyPair.generate()
        pk, sig, _iid, at, ts = self._args(kp, initiative_id="init:a")
        assert verify_action_event(pk, sig, "init:b", at, ts) is False

    def test_tampered_action_type_fails(self):
        kp = KeyPair.generate()
        pk, sig, iid, _at, ts = self._args(kp, action_type="written_comment")
        assert verify_action_event(pk, sig, iid, "attend_meeting", ts) is False

    def test_tampered_created_at_fails(self):
        kp = KeyPair.generate()
        pk, sig, iid, at, ts = self._args(kp)
        assert verify_action_event(pk, sig, iid, at, ts + 1) is False

    def test_empty_pubkey_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, iid, at, ts = self._args(kp)
        assert verify_action_event("", sig, iid, at, ts) is False

    def test_empty_sig_returns_false(self):
        kp = KeyPair.generate()
        pk, _sig, iid, at, ts = self._args(kp)
        assert verify_action_event(pk, "", iid, at, ts) is False

    def test_short_lengths_return_false(self):
        kp = KeyPair.generate()
        pk, sig, iid, at, ts = self._args(kp)
        assert verify_action_event("ab" * 30, sig, iid, at, ts) is False
        assert verify_action_event(pk, "ab" * 60, iid, at, ts) is False

    def test_invalid_hex_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, iid, at, ts = self._args(kp)
        assert verify_action_event("Z" * 64, sig, iid, at, ts) is False

    def test_exception_path_returns_false(self):
        kp = KeyPair.generate()
        bad_ts = datetime.utcnow()
        assert verify_action_event(kp.public_key_hex, "b" * 128, "iid", "at", bad_ts) is False


# =============================================================================
# verify_attestation_request
# =============================================================================


class TestVerifyAttestationRequest:
    def _args(self, kp, *, code="CODE-123", created_at=1_700_000_000):
        tags = [["action", "attest"], ["code", code]]
        content = f"civicos:attest:v1:{kp.public_key_hex}:{code}:{created_at}"
        eid = _direct_event_id(kp.public_key_hex, created_at, 24242, tags, content)
        sig = _sign_hex(kp, eid)
        return kp.public_key_hex, sig, code, created_at

    def test_valid_request_verifies(self):
        kp = KeyPair.generate()
        assert verify_attestation_request(*self._args(kp)) is True

    def test_tampered_code_fails(self):
        kp = KeyPair.generate()
        pk, sig, _code, ts = self._args(kp, code="A")
        assert verify_attestation_request(pk, sig, "B", ts) is False

    def test_tampered_created_at_fails(self):
        kp = KeyPair.generate()
        pk, sig, code, ts = self._args(kp)
        assert verify_attestation_request(pk, sig, code, ts + 1) is False

    def test_empty_pubkey_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, code, ts = self._args(kp)
        assert verify_attestation_request("", sig, code, ts) is False

    def test_empty_sig_returns_false(self):
        kp = KeyPair.generate()
        pk, _sig, code, ts = self._args(kp)
        assert verify_attestation_request(pk, "", code, ts) is False

    def test_short_lengths_return_false(self):
        kp = KeyPair.generate()
        pk, sig, code, ts = self._args(kp)
        assert verify_attestation_request("ab" * 30, sig, code, ts) is False
        assert verify_attestation_request(pk, "ab" * 60, code, ts) is False

    def test_invalid_hex_returns_false(self):
        kp = KeyPair.generate()
        _pk, sig, code, ts = self._args(kp)
        assert verify_attestation_request("Z" * 64, sig, code, ts) is False

    def test_different_pubkey_in_content_fails(self):
        """Content includes the requester's pubkey — swapping pubkeys must fail."""
        kp = KeyPair.generate()
        other = KeyPair.generate()
        _pk, sig, code, ts = self._args(kp)
        assert verify_attestation_request(other.public_key_hex, sig, code, ts) is False

    def test_exception_path_returns_false(self):
        kp = KeyPair.generate()
        bad_ts = datetime.utcnow()
        assert verify_attestation_request(kp.public_key_hex, "b" * 128, "code", bad_ts) is False


# =============================================================================
# sign_attestation_event — pin output dict
# =============================================================================


class TestSignAttestationEventOutput:
    def test_default_attestation_type_is_physical(self):
        issuer = KeyPair.generate()
        subject = KeyPair.generate()
        event = sign_attestation_event(issuer, subject.public_key_hex, "city-x")
        # Pin the default exactly — kills string-value mutations on the default
        type_tags = [t for t in event["tags"] if t[0] == "type"]
        assert type_tags == [["type", "physical"]]

    def test_custom_attestation_type_reflected_in_tag_and_content(self):
        issuer = KeyPair.generate()
        subject = KeyPair.generate()
        event = sign_attestation_event(
            issuer, subject.public_key_hex, "city-x", attestation_type="digital"
        )
        type_tags = [t for t in event["tags"] if t[0] == "type"]
        assert type_tags == [["type", "digital"]]
        assert ":digital:" in event["content"]

    def test_output_fields_are_exact(self):
        issuer = KeyPair.generate()
        subject = KeyPair.generate()
        event = sign_attestation_event(issuer, subject.public_key_hex, "city-y")
        assert event["kind"] == 30850
        assert event["pubkey"] == issuer.public_key_hex
        assert isinstance(event["created_at"], int)
        assert event["created_at"] > 0
        # Tag structure: d, p, j, type in this exact order
        assert event["tags"][0] == ["d", f"attest:city-y:{subject.public_key_hex}"]
        assert event["tags"][1] == ["p", subject.public_key_hex]
        assert event["tags"][2] == ["j", "city-y"]
        assert event["tags"][3] == ["type", "physical"]
        # Content format is exact
        expected_content = (
            f"civicos:attestation:v1:city-y:physical:{event['created_at']}"
        )
        assert event["content"] == expected_content
        # id must match ground-truth hash
        expected_id = _direct_event_id(
            issuer.public_key_hex, event["created_at"], 30850, event["tags"], event["content"]
        )
        assert event["id"] == expected_id
        # sig must verify under the issuer
        assert _schnorr_verify(issuer.public_key_hex, event["sig"], event["id"]) is True


# =============================================================================
# verify_attestation_proof — edge cases
# =============================================================================


class TestVerifyAttestationProofEdges:
    def _proof(self):
        issuer = KeyPair.generate()
        subject = KeyPair.generate()
        jurisdiction = "city-san-rafael"
        proof = sign_attestation_event(issuer, subject.public_key_hex, jurisdiction)
        return issuer, subject, jurisdiction, proof

    def test_missing_tags_key_returns_false(self):
        """Kill the `proof.get("tags", [])` → `None` mutation."""
        issuer, subject, jurisdiction, proof = self._proof()
        proof.pop("tags")
        assert (
            verify_attestation_proof(proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex)
            is False
        )

    def test_missing_content_key_returns_false(self):
        """Removing content should fail the id-recomputation check."""
        issuer, subject, jurisdiction, proof = self._proof()
        proof.pop("content")
        assert (
            verify_attestation_proof(proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex)
            is False
        )

    def test_wrong_d_tag_value_returns_false(self):
        """Kill `t[0]=="d" and t[1]==expected` → `or` mutation."""
        issuer, subject, jurisdiction, proof = self._proof()
        # Replace the d-tag value so the tag key matches but the value does not
        new_tags = []
        for t in proof["tags"]:
            if t[0] == "d":
                new_tags.append(["d", "attest:wrong:wrong"])
            else:
                new_tags.append(t)
        proof["tags"] = new_tags
        # Recompute id so the id check passes and we exclusively exercise the d-tag check
        proof["id"] = _direct_event_id(
            proof["pubkey"], proof["created_at"], 30850, proof["tags"], proof["content"]
        )
        proof["sig"] = _sign_hex(issuer, proof["id"])
        assert (
            verify_attestation_proof(proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex)
            is False
        )

    def test_wrong_p_tag_value_returns_false(self):
        """Kill `t[0]=="p" and t[1]==subject` → `or` mutation."""
        issuer, subject, jurisdiction, proof = self._proof()
        new_tags = []
        for t in proof["tags"]:
            if t[0] == "p":
                new_tags.append(["p", "aa" * 32])
            else:
                new_tags.append(t)
        proof["tags"] = new_tags
        proof["id"] = _direct_event_id(
            proof["pubkey"], proof["created_at"], 30850, proof["tags"], proof["content"]
        )
        proof["sig"] = _sign_hex(issuer, proof["id"])
        assert (
            verify_attestation_proof(proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex)
            is False
        )

    def test_wrong_j_tag_value_returns_false(self):
        """Kill `t[0]=="j" and t[1]==jurisdiction` → `or` mutation."""
        issuer, subject, jurisdiction, proof = self._proof()
        new_tags = []
        for t in proof["tags"]:
            if t[0] == "j":
                new_tags.append(["j", "city-unrelated"])
            else:
                new_tags.append(t)
        proof["tags"] = new_tags
        proof["id"] = _direct_event_id(
            proof["pubkey"], proof["created_at"], 30850, proof["tags"], proof["content"]
        )
        proof["sig"] = _sign_hex(issuer, proof["id"])
        assert (
            verify_attestation_proof(proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex)
            is False
        )

    def test_missing_only_p_tag_returns_false(self):
        """Kill `not has_p or not has_j` → `and` mutation."""
        issuer, subject, jurisdiction, proof = self._proof()
        proof["tags"] = [t for t in proof["tags"] if t[0] != "p"]
        proof["id"] = _direct_event_id(
            proof["pubkey"], proof["created_at"], 30850, proof["tags"], proof["content"]
        )
        proof["sig"] = _sign_hex(issuer, proof["id"])
        assert (
            verify_attestation_proof(proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex)
            is False
        )

    def test_missing_only_j_tag_returns_false(self):
        issuer, subject, jurisdiction, proof = self._proof()
        proof["tags"] = [t for t in proof["tags"] if t[0] != "j"]
        proof["id"] = _direct_event_id(
            proof["pubkey"], proof["created_at"], 30850, proof["tags"], proof["content"]
        )
        proof["sig"] = _sign_hex(issuer, proof["id"])
        assert (
            verify_attestation_proof(proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex)
            is False
        )

    def test_missing_created_at_after_tag_checks_returns_false(self):
        """Remove created_at AFTER the tag checks pass — reaches `proof["created_at"]` KeyError."""
        issuer, subject, jurisdiction, proof = self._proof()
        proof.pop("created_at")
        assert (
            verify_attestation_proof(proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex)
            is False
        )

    def test_missing_pubkey_returns_false(self):
        """Pubkey missing → pubkey check short-circuits OR raises KeyError — both return False."""
        issuer, subject, jurisdiction, proof = self._proof()
        proof.pop("pubkey")
        assert (
            verify_attestation_proof(proof, subject.public_key_hex, jurisdiction, issuer.public_key_hex)
            is False
        )

    def test_string_proof_returns_false(self):
        assert verify_attestation_proof("not-a-dict", "a" * 64, "j", "b" * 64) is False


# =============================================================================
# verify_code_batch
# =============================================================================


class TestVerifyCodeBatch:
    def _event(self, kp, *, codes=None, created_at=1_700_000_000, tags=None):
        if codes is None:
            codes = ["alpha", "beta", "gamma"]
        if tags is None:
            tags = [["d", "batch:1"]]
        content = json.dumps(codes)
        eid = _direct_event_id(kp.public_key_hex, created_at, 30851, tags, content)
        sig = _sign_hex(kp, eid)
        return {
            "id": eid,
            "pubkey": kp.public_key_hex,
            "created_at": created_at,
            "kind": 30851,
            "tags": tags,
            "content": content,
            "sig": sig,
        }

    def test_valid_event_verifies(self):
        kp = KeyPair.generate()
        ev = self._event(kp)
        assert verify_code_batch(ev, kp.public_key_hex) is True

    def test_wrong_kind_returns_false(self):
        kp = KeyPair.generate()
        ev = self._event(kp)
        ev["kind"] = 30850
        assert verify_code_batch(ev, kp.public_key_hex) is False

    def test_wrong_pubkey_returns_false(self):
        kp = KeyPair.generate()
        other = KeyPair.generate()
        ev = self._event(kp)
        assert verify_code_batch(ev, other.public_key_hex) is False

    def test_tampered_id_returns_false(self):
        kp = KeyPair.generate()
        ev = self._event(kp)
        ev["id"] = "0" * 64
        assert verify_code_batch(ev, kp.public_key_hex) is False

    def test_tampered_content_breaks_id_match(self):
        kp = KeyPair.generate()
        ev = self._event(kp)
        ev["content"] = json.dumps(["different"])
        assert verify_code_batch(ev, kp.public_key_hex) is False

    def test_tampered_signature_returns_false(self):
        kp = KeyPair.generate()
        ev = self._event(kp)
        ev["sig"] = "0" * 128
        assert verify_code_batch(ev, kp.public_key_hex) is False

    def test_content_not_json_returns_false(self):
        kp = KeyPair.generate()
        ev = self._event(kp)
        ev["content"] = "not json{"
        ev["id"] = _direct_event_id(ev["pubkey"], ev["created_at"], 30851, ev["tags"], ev["content"])
        ev["sig"] = _sign_hex(kp, ev["id"])
        assert verify_code_batch(ev, kp.public_key_hex) is False

    def test_content_not_list_returns_false(self):
        kp = KeyPair.generate()
        ev = self._event(kp)
        ev["content"] = json.dumps({"codes": ["a"]})  # dict, not list
        ev["id"] = _direct_event_id(ev["pubkey"], ev["created_at"], 30851, ev["tags"], ev["content"])
        ev["sig"] = _sign_hex(kp, ev["id"])
        assert verify_code_batch(ev, kp.public_key_hex) is False

    def test_content_list_with_non_string_returns_false(self):
        kp = KeyPair.generate()
        ev = self._event(kp)
        ev["content"] = json.dumps(["a", 42, "c"])
        ev["id"] = _direct_event_id(ev["pubkey"], ev["created_at"], 30851, ev["tags"], ev["content"])
        ev["sig"] = _sign_hex(kp, ev["id"])
        assert verify_code_batch(ev, kp.public_key_hex) is False

    def test_empty_codes_list_verifies(self):
        kp = KeyPair.generate()
        ev = self._event(kp, codes=[])
        assert verify_code_batch(ev, kp.public_key_hex) is True

    def test_missing_required_key_returns_false(self):
        kp = KeyPair.generate()
        ev = self._event(kp)
        del ev["id"]
        assert verify_code_batch(ev, kp.public_key_hex) is False

    def test_non_dict_returns_false(self):
        kp = KeyPair.generate()
        assert verify_code_batch("not-a-dict", kp.public_key_hex) is False
        assert verify_code_batch(None, kp.public_key_hex) is False
        assert verify_code_batch(42, kp.public_key_hex) is False

    def test_missing_kind_returns_false(self):
        kp = KeyPair.generate()
        ev = self._event(kp)
        del ev["kind"]
        assert verify_code_batch(ev, kp.public_key_hex) is False


# =============================================================================
# sign_message + verify_signature
# =============================================================================


class TestSignAndVerifyMessage:
    def test_sign_produces_128_hex_chars(self):
        kp = KeyPair.generate()
        sig = sign_message(kp, "hello")
        assert len(sig) == 128
        int(sig, 16)

    def test_sign_verify_roundtrip(self):
        kp = KeyPair.generate()
        sig = sign_message(kp, "hello")
        assert verify_signature(kp.public_key_hex, sig, "hello") is True

    def test_sign_hashes_message_with_sha256_utf8(self):
        """Independently hash and verify — catches mutations in sign_message's hash step."""
        kp = KeyPair.generate()
        message = "civic:voice:v1:agenda:1:support"
        sig = sign_message(kp, message)
        expected_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
        assert _schnorr_verify(kp.public_key_hex, sig, expected_hash) is True

    def test_verify_signature_uses_sha256_utf8(self):
        """Build a sig independently, then verify via verify_signature."""
        kp = KeyPair.generate()
        message = "independent message"
        msg_digest = hashlib.sha256(message.encode("utf-8")).digest()
        sig = PrivateKey(bytes.fromhex(kp.private_key_hex)).sign_schnorr(msg_digest).hex()
        assert verify_signature(kp.public_key_hex, sig, message) is True

    def test_verify_rejects_tampered_message(self):
        kp = KeyPair.generate()
        sig = sign_message(kp, "hello")
        assert verify_signature(kp.public_key_hex, sig, "hello!") is False

    def test_verify_rejects_tampered_signature(self):
        kp = KeyPair.generate()
        sign_message(kp, "hello")
        assert verify_signature(kp.public_key_hex, "0" * 128, "hello") is False

    def test_verify_rejects_wrong_pubkey(self):
        kp = KeyPair.generate()
        other = KeyPair.generate()
        sig = sign_message(kp, "hello")
        assert verify_signature(other.public_key_hex, sig, "hello") is False

    def test_verify_with_invalid_hex_returns_false(self):
        assert verify_signature("Z" * 64, "0" * 128, "hello") is False
        assert verify_signature("ab" * 32, "Z" * 128, "hello") is False

    def test_verify_with_unicode_message(self):
        kp = KeyPair.generate()
        msg = "Hello 世界 🌍"
        sig = sign_message(kp, msg)
        assert verify_signature(kp.public_key_hex, sig, msg) is True
        # Wrong encoding would produce a different hash
        wrong_hash_msg = "Hello World"
        assert verify_signature(kp.public_key_hex, sig, wrong_hash_msg) is False

    def test_verify_signature_exception_path_returns_false(self):
        """Non-string message (int has no .encode) triggers AttributeError, caught → False."""
        kp = KeyPair.generate()
        assert verify_signature(kp.public_key_hex, "0" * 128, 42) is False


# =============================================================================
# _check_key_sig — length validator
# =============================================================================


class TestCheckKeySig:
    def test_both_correct_lengths_returns_true(self):
        assert _check_key_sig("ab" * 32, "cd" * 64) is True

    def test_empty_pubkey_returns_false(self):
        assert _check_key_sig("", "cd" * 64) is False

    def test_empty_signature_returns_false(self):
        assert _check_key_sig("ab" * 32, "") is False

    def test_wrong_pubkey_length_returns_false(self):
        assert _check_key_sig("ab" * 31, "cd" * 64) is False  # 62 chars
        assert _check_key_sig("ab" * 33, "cd" * 64) is False  # 66 chars

    def test_wrong_signature_length_returns_false(self):
        assert _check_key_sig("ab" * 32, "cd" * 63) is False  # 126 chars
        assert _check_key_sig("ab" * 32, "cd" * 65) is False  # 130 chars

    def test_both_empty_returns_false(self):
        assert _check_key_sig("", "") is False

    def test_only_pubkey_wrong_length_returns_false(self):
        """Kill mutations that OR the length checks together."""
        assert _check_key_sig("a" * 63, "c" * 128) is False

    def test_only_signature_wrong_length_returns_false(self):
        assert _check_key_sig("a" * 64, "c" * 127) is False
