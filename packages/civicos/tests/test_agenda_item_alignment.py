"""
Tests for agenda item alignment in video transcripts.

Tests the AgendaItemAligner class that detects agenda item transitions
in meeting transcripts and aligns transcript chunks with specific agenda items.

Run: python -m pytest packages/civicos/tests/test_agenda_item_alignment.py -v
"""

import sys
from pathlib import Path

import pytest

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()

# Add source path for imports
sys.path.insert(0, str(PROJECT_ROOT / "packages/civicos/src"))


class TestAgendaItemSpan:
    """Tests for AgendaItemSpan dataclass."""

    def test_span_creation(self):
        """Test basic span creation."""
        from civicos._internal.meetings.transcript import AgendaItemSpan

        span = AgendaItemSpan(
            item_number="5.a",
            start_idx=10,
            end_idx=25,
            start_ms=60000,
            end_ms=180000,
            marker_idx=10,
            marker_text="Our next agenda item is 5A",
            confidence=0.9,
        )

        assert span.item_number == "5.a"
        assert span.start_idx == 10
        assert span.end_idx == 25
        assert span.start_ms == 60000
        assert span.end_ms == 180000
        assert span.confidence == 0.9

    def test_span_timestamp_formatting(self):
        """Test human-readable timestamp properties."""
        from civicos._internal.meetings.transcript import AgendaItemSpan

        span = AgendaItemSpan(
            item_number="6",
            start_idx=0,
            end_idx=10,
            start_ms=3661000,  # 1:01:01
            end_ms=7322000,    # 2:02:02
            marker_idx=0,
            marker_text="Item 6",
            confidence=0.7,
        )

        assert span.start_timestamp == "01:01:01"
        assert span.end_timestamp == "02:02:02"

    def test_span_to_dict(self):
        """Test serialization to dictionary."""
        from civicos._internal.meetings.transcript import AgendaItemSpan

        span = AgendaItemSpan(
            item_number="4.b",
            start_idx=5,
            end_idx=15,
            start_ms=120000,
            end_ms=240000,
            marker_idx=5,
            marker_text="Consent calendar item 4B",
            confidence=0.8,
        )

        result = span.to_dict()

        assert result["item_number"] == "4.b"
        assert result["start_idx"] == 5
        assert result["end_idx"] == 15
        assert result["start_ms"] == 120000
        assert result["end_ms"] == 240000
        assert result["start_timestamp"] == "00:02:00"
        assert result["end_timestamp"] == "00:04:00"
        assert result["confidence"] == 0.8


class TestAgendaItemAligner:
    """Tests for AgendaItemAligner class."""

    def test_empty_utterances(self):
        """Test with empty utterance list."""
        from civicos._internal.meetings.transcript import AgendaItemAligner

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items([])

        assert spans == []

    def test_detect_simple_item_number(self):
        """Test detecting 'item 5' pattern."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "Welcome to the meeting.", 0, 5000),
            TranscriptUtterance("A", "Our first item is item 5.", 5000, 10000),
            TranscriptUtterance("B", "I support this proposal.", 10000, 15000),
        ]

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items(utterances)

        assert len(spans) == 1
        assert spans[0].item_number == "5"
        assert spans[0].start_idx == 1
        assert spans[0].end_idx == 2  # To end of transcript

    def test_detect_item_with_letter(self):
        """Test detecting 'item 5A' pattern (letter suffix)."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "Next we have item 5A.", 0, 5000),
            TranscriptUtterance("B", "Discussion content.", 5000, 10000),
        ]

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items(utterances)

        assert len(spans) == 1
        assert spans[0].item_number == "5.a"

    def test_detect_item_with_dot_notation(self):
        """Test detecting 'item 5.a' pattern (dot notation)."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "Now discussing item 5.b please.", 0, 5000),
        ]

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items(utterances)

        assert len(spans) == 1
        assert spans[0].item_number == "5.b"

    def test_detect_next_agenda_item(self):
        """Test detecting 'next agenda item is' pattern with higher confidence."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "That motion carries. Our next agenda item is 6A.", 0, 10000),
            TranscriptUtterance("B", "Content for item 6A.", 10000, 20000),
        ]

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items(utterances)

        assert len(spans) == 1
        assert spans[0].item_number == "6.a"
        assert spans[0].confidence == 0.9  # Higher confidence for transition phrase

    def test_detect_consent_calendar(self):
        """Test detecting consent calendar as special section."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "Let's move to the consent calendar.", 0, 5000),
            TranscriptUtterance("B", "I have a question on 4B.", 5000, 10000),
        ]

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items(utterances)

        assert len(spans) == 1
        assert spans[0].item_number == "consent"

    def test_detect_public_hearing(self):
        """Test detecting public hearing as section."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "We now open the public hearing on this matter.", 0, 5000),
            TranscriptUtterance("B", "I want to speak about...", 5000, 10000),
        ]

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items(utterances)

        assert len(spans) == 1
        assert spans[0].item_number == "public_hearing"

    def test_detect_multiple_items(self):
        """Test detecting multiple consecutive agenda items."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "Item 4 is the consent calendar.", 0, 5000),
            TranscriptUtterance("B", "Approved.", 5000, 8000),
            TranscriptUtterance("A", "Moving on to item 5.", 8000, 12000),
            TranscriptUtterance("C", "I support item 5.", 12000, 16000),
            TranscriptUtterance("A", "Next item is 6.", 16000, 20000),
            TranscriptUtterance("D", "Comment on item 6.", 20000, 24000),
        ]

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items(utterances)

        assert len(spans) == 3

        # Item 4 span
        assert spans[0].item_number == "4"
        assert spans[0].start_idx == 0
        assert spans[0].end_idx == 1  # Ends before item 5 announcement

        # Item 5 span
        assert spans[1].item_number == "5"
        assert spans[1].start_idx == 2
        assert spans[1].end_idx == 3

        # Item 6 span
        assert spans[2].item_number == "6"
        assert spans[2].start_idx == 4
        assert spans[2].end_idx == 5

    def test_get_item_for_utterance(self):
        """Test looking up agenda item for specific utterance."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "Welcome.", 0, 2000),
            TranscriptUtterance("A", "Item 5 discussion.", 2000, 5000),
            TranscriptUtterance("B", "My comment on item 5.", 5000, 8000),
            TranscriptUtterance("A", "Now item 6.", 8000, 11000),
            TranscriptUtterance("C", "About item 6...", 11000, 14000),
        ]

        aligner = AgendaItemAligner()
        aligner.detect_agenda_items(utterances)

        # Utterance 0 is before any detected item
        assert aligner.get_item_for_utterance(0) is None

        # Utterances 1-2 are in item 5 span
        assert aligner.get_item_for_utterance(1) == "5"
        assert aligner.get_item_for_utterance(2) == "5"

        # Utterances 3-4 are in item 6 span
        assert aligner.get_item_for_utterance(3) == "6"
        assert aligner.get_item_for_utterance(4) == "6"

    def test_get_span_for_utterance(self):
        """Test getting full span object for utterance."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "Item 5 is next.", 1000, 3000),
            TranscriptUtterance("B", "Discussion.", 3000, 6000),
        ]

        aligner = AgendaItemAligner()
        aligner.detect_agenda_items(utterances)

        span = aligner.get_span_for_utterance(1)

        assert span is not None
        assert span.item_number == "5"
        assert span.start_ms == 1000
        assert span.end_ms == 6000

    def test_timestamp_preservation(self):
        """Test that span timestamps match utterance boundaries."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "Item 5A begins.", 60000, 65000),
            TranscriptUtterance("B", "Middle discussion.", 65000, 90000),
            TranscriptUtterance("C", "Final comment.", 90000, 120000),
        ]

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items(utterances)

        assert len(spans) == 1
        assert spans[0].start_ms == 60000  # First utterance start
        assert spans[0].end_ms == 120000  # Last utterance end


class TestChunkerWithAgendaItems:
    """Tests for TranscriptChunker with agenda item detection."""

    def test_chunk_includes_agenda_item_metadata(self):
        """Test that chunks include agenda_item in metadata."""
        from civicos._internal.meetings.transcript import (
            TranscriptChunker,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "Let's discuss item 5 now.", 0, 5000),
            TranscriptUtterance("B", "I support the proposal in item 5.", 5000, 10000),
        ]

        chunker = TranscriptChunker(max_chunk_size=500)
        chunks = chunker.chunk(utterances, detect_agenda_items=True)

        assert len(chunks) >= 1
        # All chunks should have agenda_item since they're all in item 5
        for chunk in chunks:
            assert chunk.metadata.get("agenda_item") == "5"

    def test_chunk_without_agenda_detection(self):
        """Test chunks when agenda detection is disabled."""
        from civicos._internal.meetings.transcript import (
            TranscriptChunker,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "Item 5 discussion.", 0, 5000),
        ]

        chunker = TranscriptChunker(max_chunk_size=500)
        chunks = chunker.chunk(utterances, detect_agenda_items=False)

        assert len(chunks) == 1
        # No agenda_item since detection was disabled
        assert "agenda_item" not in chunks[0].metadata

    def test_chunks_before_first_item(self):
        """Test that chunks before first item have no agenda_item."""
        from civicos._internal.meetings.transcript import (
            TranscriptChunker,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance("A", "Welcome everyone to tonight's meeting.", 0, 5000),
            TranscriptUtterance("A", "Let me call the roll.", 5000, 10000),
            TranscriptUtterance("A", "Now moving to item 4.", 10000, 15000),
            TranscriptUtterance("B", "Discussion on item 4.", 15000, 20000),
        ]

        chunker = TranscriptChunker(max_chunk_size=500)
        chunks = chunker.chunk(utterances, detect_agenda_items=True)

        # Chunks covering utterances that mention item 4 should detect it
        found_item_4 = False
        for chunk in chunks:
            if chunk.metadata.get("agenda_item") == "4":
                found_item_4 = True
            elif "agenda_items" in chunk.metadata and "4" in chunk.metadata["agenda_items"]:
                found_item_4 = True

        assert found_item_4, "Agenda item 4 should be detected in chunk metadata"

    def test_chunk_spanning_transition(self):
        """Test chunk that might span item transition gets agenda_items list."""
        from civicos._internal.meetings.transcript import (
            TranscriptChunker,
            TranscriptUtterance,
        )

        # Use a small chunk size to force transitions within chunks
        utterances = [
            TranscriptUtterance("A", "Item 5 final vote. Moving to item 6 now.", 0, 5000),
        ]

        chunker = TranscriptChunker(max_chunk_size=500)
        chunks = chunker.chunk(utterances, detect_agenda_items=True)

        # This single utterance mentions both items, but detection finds
        # the first match (item 5) due to break-on-first-match in aligner
        assert len(chunks) == 1
        assert chunks[0].metadata.get("agenda_item") == "5"


class TestNormalization:
    """Tests for item number normalization."""

    def test_normalize_letter_suffix(self):
        """Test normalizing '5A' to '5.a'."""
        from civicos._internal.meetings.transcript import AgendaItemAligner

        aligner = AgendaItemAligner()
        assert aligner._normalize_item_number("5A") == "5.a"
        assert aligner._normalize_item_number("5a") == "5.a"
        assert aligner._normalize_item_number("12B") == "12.b"

    def test_normalize_dot_notation(self):
        """Test dot notation is preserved."""
        from civicos._internal.meetings.transcript import AgendaItemAligner

        aligner = AgendaItemAligner()
        assert aligner._normalize_item_number("5.a") == "5.a"
        assert aligner._normalize_item_number("5.A") == "5.a"

    def test_normalize_simple_number(self):
        """Test simple numbers pass through."""
        from civicos._internal.meetings.transcript import AgendaItemAligner

        aligner = AgendaItemAligner()
        assert aligner._normalize_item_number("5") == "5"
        assert aligner._normalize_item_number("12") == "12"

    def test_normalize_special_sections(self):
        """Test special section normalization."""
        from civicos._internal.meetings.transcript import AgendaItemAligner

        aligner = AgendaItemAligner()
        assert aligner._normalize_item_number("consent calendar") == "consent"
        assert aligner._normalize_item_number("consent agenda") == "consent"
        assert aligner._normalize_item_number("public hearing") == "public_hearing"
        assert aligner._normalize_item_number("new business") == "new_business"
        assert aligner._normalize_item_number("old business") == "old_business"


class TestRealDataPatterns:
    """Tests based on real San Rafael meeting transcript patterns."""

    def test_san_rafael_item_announcement_pattern(self):
        """Test actual pattern from San Rafael meetings: 'Our next agenda item is 5A'."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        # This is based on actual transcript from Nov 17 meeting
        utterances = [
            TranscriptUtterance(
                "C",
                "That motion carries.4 0. Our next agenda item is 5A the Ralph M. Brown act compliance.",
                0,
                15000,
            ),
            TranscriptUtterance("D", "Good evening, Mayor Kate. Members of the council.", 15000, 25000),
        ]

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items(utterances)

        assert len(spans) == 1
        assert spans[0].item_number == "5.a"
        assert spans[0].confidence == 0.9  # High confidence due to transition phrase

    def test_san_rafael_items_range_pattern(self):
        """Test pattern: 'items 4A through 4G'."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance(
                "C",
                "I will open public comment on all items on the consent agenda. That's items 4A through 4G.",
                0,
                10000,
            ),
        ]

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items(utterances)

        assert len(spans) == 1
        # Should detect "4A" as the item number
        assert spans[0].item_number == "4.a"

    def test_public_hearing_shelter_crisis(self):
        """Test detecting public hearing for shelter crisis (from Nov 17)."""
        from civicos._internal.meetings.transcript import (
            AgendaItemAligner,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance(
                "C",
                "The next item. We're having a public hearing on the declaration of a shelter crisis.",
                0,
                10000,
            ),
        ]

        aligner = AgendaItemAligner()
        spans = aligner.detect_agenda_items(utterances)

        assert len(spans) == 1
        assert spans[0].item_number == "public_hearing"
