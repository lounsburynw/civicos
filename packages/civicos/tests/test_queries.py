"""
Tests for query modules.

Tests context, history, calendar, and community modules.
"""

import pytest
from datetime import datetime, timedelta


class TestContextModule:
    """Test context.py (what_applies)."""

    def test_get_regulatory_context_import(self):
        """Can import get_regulatory_context."""
        from civicos.context import get_regulatory_context, RegulatoryStack
        assert callable(get_regulatory_context)

    def test_get_regulatory_context_returns_stack(self):
        """get_regulatory_context returns RegulatoryStack."""
        from civicos.context import get_regulatory_context
        result = get_regulatory_context("san-rafael-ca", "housing")
        assert result.topic == "housing"
        assert result.jurisdiction == "san-rafael-ca"


class TestHistoryModule:
    """Test history.py (what_happened)."""

    def test_search_decisions_import(self):
        """Can import search_decisions."""
        from civicos.history import search_decisions, Decision
        assert callable(search_decisions)

    def test_search_decisions_with_context_import(self):
        """Can import search_decisions_with_context and related types."""
        from civicos.history import (
            search_decisions_with_context,
            DecisionWithContext,
            TranscriptLink,
        )
        assert callable(search_decisions_with_context)

    def test_decision_with_context_dataclass(self):
        """DecisionWithContext has expected fields and properties."""
        from civicos.history import DecisionWithContext, Decision, TranscriptLink

        decision = Decision(
            id="test-1",
            title="Test Decision",
            date=datetime.now(),
            outcome="passed",
            body="City Council",
        )

        # No transcript links
        result = DecisionWithContext(
            decision=decision,
            transcript_links=[],
            link_confidence=0.0,
            link_type="none",
        )

        assert result.decision.title == "Test Decision"
        assert result.has_transcript is False
        assert result.public_comments == []
        assert result.staff_discussion == []
        assert result.council_discussion == []

    def test_decision_with_context_categorizes_links(self):
        """DecisionWithContext properly categorizes transcript links."""
        from civicos.history import DecisionWithContext, Decision, TranscriptLink

        decision = Decision(
            id="test-1",
            title="Test Decision",
            date=datetime.now(),
            outcome="passed",
            body="City Council",
        )

        links = [
            TranscriptLink(
                chunk_id="chunk-1",
                text="Public comment about traffic...",
                speaker="A",
                speaker_role="public",
                is_public_comment=True,
                confidence=0.8,
            ),
            TranscriptLink(
                chunk_id="chunk-2",
                text="Staff presentation on budget...",
                speaker="B",
                speaker_role="staff",
                is_public_comment=False,
                confidence=0.7,
            ),
            TranscriptLink(
                chunk_id="chunk-3",
                text="Council member discussion...",
                speaker="C",
                speaker_role="council",
                is_public_comment=False,
                confidence=0.9,
            ),
        ]

        result = DecisionWithContext(
            decision=decision,
            transcript_links=links,
            link_confidence=0.8,
            link_type="high_confidence",
        )

        assert result.has_transcript is True
        assert len(result.public_comments) == 1
        assert len(result.staff_discussion) == 1
        assert len(result.council_discussion) == 1
        assert result.public_comments[0].chunk_id == "chunk-1"
        assert result.staff_discussion[0].chunk_id == "chunk-2"
        assert result.council_discussion[0].chunk_id == "chunk-3"

    def test_transcript_link_video_url(self):
        """TranscriptLink generates correct video URL."""
        from civicos.history import TranscriptLink

        link = TranscriptLink(
            chunk_id="chunk-1",
            text="Some discussion",
            speaker="A",
            video_id="abc123",
            start_ms=90000,  # 90 seconds
            confidence=0.8,
        )

        assert link.video_url == "https://www.youtube.com/watch?v=abc123&t=90s"

        # No video_id -> None
        link_no_video = TranscriptLink(
            chunk_id="chunk-2",
            text="Some text",
            speaker="B",
            confidence=0.5,
        )
        assert link_no_video.video_url is None


class TestCalendarModule:
    """Test calendar.py (whats_next)."""

    def test_get_upcoming_meetings_import(self):
        """Can import get_upcoming_meetings."""
        from civicos.calendar import get_upcoming_meetings, Meeting
        assert callable(get_upcoming_meetings)


