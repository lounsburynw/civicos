"""Tests for require_created_at_on_writes security fix.

Verifies that:
1. All write endpoints require created_at (not Optional)
2. Requests without created_at are rejected (422 from Pydantic)
3. Clock skew validation rejects stale/future timestamps
4. ActionService.verify() includes created_at in canonical message
5. Voice and Comment models require created_at
"""

import time
import pytest

from pydantic import ValidationError

from civicos_relay.voice.models import Voice, Comment, Action, Stance, ActionType
from civicos_relay.voice.action_service import ActionService
from civicos_relay.voice.crypto import KeyPair, sign_voice, sign_message, verify_voice
from civicos_relay.storage.memory import InMemoryStorage


class TestModelsRequireCreatedAt:
    """Models reject construction without created_at."""

    def test_voice_requires_created_at(self):
        """Voice model rejects construction without created_at."""
        with pytest.raises(ValidationError, match="created_at"):
            Voice(
                entity="test:entity",
                stance=Stance.SUPPORT,
                public_key="a" * 64,
                signature="b" * 128,
            )

    def test_comment_requires_created_at(self):
        """Comment model rejects construction without created_at."""
        with pytest.raises(ValidationError, match="created_at"):
            Comment(
                entity="test:entity",
                comment_text="Test comment",
                public_key="a" * 64,
                signature="b" * 128,
            )

    def test_action_requires_created_at(self):
        """Action model rejects construction without created_at."""
        with pytest.raises(ValidationError, match="created_at"):
            Action(
                action_id="action:test",
                action_type=ActionType.COMMITMENT,
                public_key="a" * 64,
                signature="b" * 128,
            )

    def test_voice_accepts_created_at(self):
        """Voice model accepts valid created_at."""
        now = int(time.time())
        v = Voice(
            entity="test:entity",
            stance=Stance.SUPPORT,
            public_key="a" * 64,
            signature="b" * 128,
            created_at=now,
        )
        assert v.created_at == now
        assert v.entity == "test:entity"
        assert v.stance == Stance.SUPPORT

    def test_action_accepts_created_at(self):
        """Action model accepts valid created_at."""
        now = int(time.time())
        a = Action(
            action_id="action:test",
            action_type=ActionType.COMMITMENT,
            public_key="a" * 64,
            signature="b" * 128,
            created_at=now,
        )
        assert a.created_at == now
        assert a.action_id == "action:test"
        assert a.action_type == ActionType.COMMITMENT


class TestRequestSchemasRequireCreatedAt:
    """API request schemas reject missing created_at at Pydantic level."""

    def test_commit_action_request_requires_created_at(self):
        """CommitActionRequest rejects missing created_at."""
        from civicos_relay.server.coordination import CommitActionRequest
        with pytest.raises(ValidationError, match="created_at"):
            CommitActionRequest(
                action_id="action:test",
                public_key="a" * 64,
                signature="b" * 128,
            )

    def test_complete_action_request_requires_created_at(self):
        """CompleteActionRequest rejects missing created_at."""
        from civicos_relay.server.coordination import CompleteActionRequest
        with pytest.raises(ValidationError, match="created_at"):
            CompleteActionRequest(
                action_id="action:test",
                public_key="a" * 64,
                signature="b" * 128,
            )

    def test_cast_voice_request_requires_created_at(self):
        """CastVoiceRequest rejects missing created_at."""
        from civicos_relay.server.coordination import CastVoiceRequest
        with pytest.raises(ValidationError, match="created_at"):
            CastVoiceRequest(
                entity="test:entity",
                stance="support",
                public_key="a" * 64,
                signature="b" * 128,
            )

    def test_submit_comment_request_requires_created_at(self):
        """SubmitCommentRequest rejects missing created_at."""
        from civicos_relay.server.coordination import SubmitCommentRequest
        with pytest.raises(ValidationError, match="created_at"):
            SubmitCommentRequest(
                entity="test:entity",
                comment_text="Test",
                public_key="a" * 64,
                signature="b" * 128,
            )

    def test_create_initiative_request_requires_created_at(self):
        """CreateInitiativeRequest rejects missing created_at."""
        from civicos_relay.server.coordination import CreateInitiativeRequest
        with pytest.raises(ValidationError, match="created_at"):
            CreateInitiativeRequest(
                jurisdiction="city-test",
                topic="test",
                title="Test",
                description="Test initiative",
                public_key="a" * 64,
                signature="b" * 128,
            )


class TestClockSkewValidation:
    """Clock skew check rejects timestamps too far from server time."""

    def test_check_created_at_valid(self):
        """Current timestamp passes clock skew check."""
        from civicos_relay.server.coordination import _check_created_at
        # Returns None on success; any raise would fail the test
        assert _check_created_at(int(time.time())) is None

    def test_check_created_at_future(self):
        """Timestamp 10 minutes in the future fails."""
        from fastapi import HTTPException
        from civicos_relay.server.coordination import _check_created_at
        with pytest.raises(HTTPException) as exc_info:
            _check_created_at(int(time.time()) + 600)
        assert exc_info.value.status_code == 400

    def test_check_created_at_past(self):
        """Timestamp 10 minutes in the past fails."""
        from fastapi import HTTPException
        from civicos_relay.server.coordination import _check_created_at
        with pytest.raises(HTTPException) as exc_info:
            _check_created_at(int(time.time()) - 600)
        assert exc_info.value.status_code == 400

    def test_check_created_at_within_tolerance(self):
        """Timestamp 4 minutes off passes (within 5-minute tolerance)."""
        from civicos_relay.server.coordination import _check_created_at
        # 4 minutes in the past — should pass
        assert _check_created_at(int(time.time()) - 240) is None
        # 4 minutes in the future — should pass
        assert _check_created_at(int(time.time()) + 240) is None


class TestActionServiceVerifyIncludesCreatedAt:
    """ActionService.verify() includes created_at in the canonical message."""

    def test_verify_includes_created_at(self):
        """Signature must cover created_at — changing created_at breaks verification."""
        kp = KeyPair.generate()
        now = int(time.time())

        # Sign with current timestamp
        message = f"civicos:action:v1:action:test:commitment:{now}"
        sig = sign_message(kp, message)

        action = Action(
            action_id="action:test",
            action_type=ActionType.COMMITMENT,
            public_key=kp.public_key_hex,
            signature=sig,
            created_at=now,
        )

        storage = InMemoryStorage()
        service = ActionService(storage.actions)
        assert service.verify(action) is True

    def test_verify_rejects_different_created_at(self):
        """Changing created_at on the action breaks verification (replay protection)."""
        kp = KeyPair.generate()
        now = int(time.time())

        # Sign with current timestamp
        message = f"civicos:action:v1:action:test:commitment:{now}"
        sig = sign_message(kp, message)

        # Try to verify with different timestamp (replay attempt)
        action = Action(
            action_id="action:test",
            action_type=ActionType.COMMITMENT,
            public_key=kp.public_key_hex,
            signature=sig,
            created_at=now + 100,  # Different timestamp
        )

        storage = InMemoryStorage()
        service = ActionService(storage.actions)
        assert service.verify(action) is False

    def test_verify_rejects_old_format_without_created_at(self):
        """Old-format signatures (without created_at in message) fail verification."""
        kp = KeyPair.generate()
        now = int(time.time())

        # Sign with OLD format (no created_at) — this is what an attacker would try
        old_message = "civicos:action:v1:action:test:commitment"
        sig = sign_message(kp, old_message)

        action = Action(
            action_id="action:test",
            action_type=ActionType.COMMITMENT,
            public_key=kp.public_key_hex,
            signature=sig,
            created_at=now,
        )

        storage = InMemoryStorage()
        service = ActionService(storage.actions)
        assert service.verify(action) is False


class TestActionServiceRecordWithCreatedAt:
    """ActionService record methods pass created_at through."""

    def test_record_commitment_preserves_created_at(self):
        """record_commitment stores created_at on the Action."""
        kp = KeyPair.generate()
        now = int(time.time())
        storage = InMemoryStorage()
        service = ActionService(storage.actions)

        action = service.record_commitment(
            action_id="action:test",
            public_key=kp.public_key_hex,
            signature="a" * 128,
            created_at=now,
        )
        assert action.created_at == now

    def test_record_completion_preserves_created_at(self):
        """record_completion stores created_at on the Action."""
        kp = KeyPair.generate()
        now = int(time.time())
        storage = InMemoryStorage()
        service = ActionService(storage.actions)

        action = service.record_completion(
            action_id="action:test",
            public_key=kp.public_key_hex,
            signature="a" * 128,
            created_at=now,
            evidence_url="https://example.com",
        )
        assert action.created_at == now


class TestVoiceSignatureStillWorks:
    """Voice signing/verification still works with required created_at."""

    def test_sign_and_verify_voice(self):
        """sign_voice produces valid voices with created_at set."""
        kp = KeyPair.generate()
        voice = sign_voice(kp, "decision:test:item-1", Stance.SUPPORT)

        # created_at must be a recent epoch timestamp (> Jan 2024),
        # not 0 or a far-past default value
        assert voice.created_at > 1_700_000_000
        assert voice.entity == "decision:test:item-1"
        assert voice.stance == Stance.SUPPORT
        assert voice.public_key == kp.public_key_hex
        assert verify_voice(voice) is True
