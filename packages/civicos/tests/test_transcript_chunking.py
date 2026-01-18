"""
Tests for video transcript chunking.

Tests the TranscriptChunker class that converts AssemblyAI diarized transcripts
into semantic chunks preserving speaker attribution and timestamps.

Run: python -m pytest packages/civicos/tests/test_transcript_chunking.py -v
"""

import sys
from pathlib import Path

import pytest

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()

# Add source path for imports
sys.path.insert(0, str(PROJECT_ROOT / "packages/civicos/src"))

# Paths to testimony files
TESTIMONY_DIR = PROJECT_ROOT / "data/testimony"


class TestTranscriptUtterance:
    """Tests for TranscriptUtterance dataclass."""

    def test_utterance_creation(self):
        """Test basic utterance creation."""
        from civicos._internal.meetings.transcript import TranscriptUtterance

        utt = TranscriptUtterance(
            speaker="A",
            text="Hello, welcome to the meeting.",
            start_ms=1000,
            end_ms=3000,
        )

        assert utt.speaker == "A"
        assert utt.text == "Hello, welcome to the meeting."
        assert utt.start_ms == 1000
        assert utt.end_ms == 3000

    def test_utterance_duration(self):
        """Test duration calculation."""
        from civicos._internal.meetings.transcript import TranscriptUtterance

        utt = TranscriptUtterance(
            speaker="B",
            text="Test",
            start_ms=5000,
            end_ms=8500,
        )

        assert utt.duration_ms == 3500

    def test_utterance_to_dict(self):
        """Test serialization to dictionary."""
        from civicos._internal.meetings.transcript import TranscriptUtterance

        utt = TranscriptUtterance(
            speaker="C",
            text="This is a test.",
            start_ms=10000,
            end_ms=12000,
        )

        result = utt.to_dict()

        assert result["speaker"] == "C"
        assert result["text"] == "This is a test."
        assert result["start_ms"] == 10000
        assert result["end_ms"] == 12000


class TestTranscriptChunk:
    """Tests for TranscriptChunk dataclass."""

    def test_chunk_creation(self):
        """Test basic chunk creation."""
        from civicos._internal.meetings.transcript import TranscriptChunk

        chunk = TranscriptChunk(
            text="[A] Welcome everyone. Let's begin the meeting.",
            speaker="A",
            speakers=["A"],
            start_ms=1000,
            end_ms=5000,
            chunk_index=0,
            total_chunks=10,
            utterance_count=1,
        )

        assert chunk.speaker == "A"
        assert chunk.speakers == ["A"]
        assert chunk.chunk_index == 0
        assert chunk.total_chunks == 10

    def test_chunk_duration_seconds(self):
        """Test duration in seconds."""
        from civicos._internal.meetings.transcript import TranscriptChunk

        chunk = TranscriptChunk(
            text="Test",
            speaker="A",
            speakers=["A"],
            start_ms=0,
            end_ms=90000,  # 90 seconds
            chunk_index=0,
            total_chunks=1,
            utterance_count=1,
        )

        assert chunk.duration_seconds == 90.0

    def test_chunk_timestamps(self):
        """Test human-readable timestamp generation."""
        from civicos._internal.meetings.transcript import TranscriptChunk

        # Test at 1 hour, 23 minutes, 45 seconds
        chunk = TranscriptChunk(
            text="Test",
            speaker="A",
            speakers=["A"],
            start_ms=5025000,  # 1:23:45
            end_ms=5085000,    # 1:24:45
            chunk_index=0,
            total_chunks=1,
            utterance_count=1,
        )

        assert chunk.start_timestamp == "01:23:45"
        assert chunk.end_timestamp == "01:24:45"

    def test_chunk_to_dict(self):
        """Test serialization to dictionary."""
        from civicos._internal.meetings.transcript import TranscriptChunk

        chunk = TranscriptChunk(
            text="[A] Hello [B] Hi there",
            speaker="multiple",
            speakers=["A", "B"],
            start_ms=1000,
            end_ms=5000,
            chunk_index=3,
            total_chunks=20,
            utterance_count=2,
            metadata={"video_id": "test123"},
        )

        result = chunk.to_dict()

        assert result["speaker"] == "multiple"
        assert result["speakers"] == ["A", "B"]
        assert result["chunk_index"] == 3
        assert result["total_chunks"] == 20
        assert result["utterance_count"] == 2
        assert result["metadata"]["video_id"] == "test123"
        assert "start_timestamp" in result
        assert "end_timestamp" in result

    def test_chunk_to_embedding_text(self):
        """Test embedding text generation."""
        from civicos._internal.meetings.transcript import TranscriptChunk

        # Single speaker
        chunk1 = TranscriptChunk(
            text="This is the mayor speaking.",
            speaker="A",
            speakers=["A"],
            start_ms=0,
            end_ms=1000,
            chunk_index=0,
            total_chunks=1,
            utterance_count=1,
        )
        assert chunk1.to_embedding_text() == "[Speaker A] This is the mayor speaking."

        # Multiple speakers
        chunk2 = TranscriptChunk(
            text="Discussion between council members.",
            speaker="multiple",
            speakers=["A", "B"],
            start_ms=0,
            end_ms=1000,
            chunk_index=0,
            total_chunks=1,
            utterance_count=2,
        )
        assert chunk2.to_embedding_text() == "[Multiple speakers] Discussion between council members."


class TestTranscriptChunkerBasic:
    """Basic tests for TranscriptChunker without real files."""

    def test_chunker_initialization(self):
        """Test chunker initialization with defaults."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker()
        assert chunker.max_chunk_size == 1500
        assert chunker.min_chunk_size == 200

    def test_chunker_custom_sizes(self):
        """Test chunker with custom sizes."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker(
            max_chunk_size=2000,
            min_chunk_size=100,
            chunk_overlap=2,
        )
        assert chunker.max_chunk_size == 2000
        assert chunker.min_chunk_size == 100
        assert chunker.chunk_overlap == 2

    def test_parse_utterances(self):
        """Test parsing utterances from dictionary data."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker()
        data = {
            "video_id": "test",
            "utterances": [
                {"speaker": "A", "text": "Hello", "start": 1000, "end": 2000},
                {"speaker": "B", "text": "Hi there", "start": 2000, "end": 3000},
            ]
        }

        utterances = chunker.parse_utterances(data)

        assert len(utterances) == 2
        assert utterances[0].speaker == "A"
        assert utterances[0].text == "Hello"
        assert utterances[1].speaker == "B"
        assert utterances[1].text == "Hi there"

    def test_chunk_empty_list(self):
        """Test chunking empty utterance list."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker()
        chunks = chunker.chunk([])

        assert chunks == []

    def test_chunk_single_utterance(self):
        """Test chunking a single utterance."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker()
        utterances = [
            TranscriptUtterance(
                speaker="A",
                text="Welcome to the San Rafael City Council meeting.",
                start_ms=1000,
                end_ms=5000,
            )
        ]

        chunks = chunker.chunk(utterances)

        assert len(chunks) == 1
        assert chunks[0].speaker == "A"
        assert "Welcome to the San Rafael City Council meeting" in chunks[0].text
        assert chunks[0].total_chunks == 1
        assert chunks[0].chunk_index == 0

    def test_chunk_same_speaker_grouping(self):
        """Test that consecutive utterances from same speaker are grouped."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker(max_chunk_size=500)
        utterances = [
            TranscriptUtterance(speaker="A", text="First sentence.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="A", text="Second sentence.", start_ms=2000, end_ms=3000),
            TranscriptUtterance(speaker="A", text="Third sentence.", start_ms=3000, end_ms=4000),
        ]

        chunks = chunker.chunk(utterances)

        # Should be grouped into a single chunk
        assert len(chunks) == 1
        assert chunks[0].speaker == "A"
        assert chunks[0].utterance_count == 3
        assert "First sentence" in chunks[0].text
        assert "Third sentence" in chunks[0].text

    def test_chunk_speaker_change_splits(self):
        """Test that speaker changes cause chunk splits after min size."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker(max_chunk_size=1000, min_chunk_size=50)
        utterances = [
            TranscriptUtterance(speaker="A", text="This is a fairly long statement from speaker A that should exceed the minimum chunk size.", start_ms=1000, end_ms=5000),
            TranscriptUtterance(speaker="B", text="And this is speaker B responding.", start_ms=5000, end_ms=8000),
        ]

        chunks = chunker.chunk(utterances)

        # Should split on speaker change (A's text > min_chunk_size)
        assert len(chunks) == 2
        assert chunks[0].speaker == "A"
        assert chunks[1].speaker == "B"

    def test_chunk_max_size_enforcement(self):
        """Test that chunks don't exceed max size."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker(max_chunk_size=100, min_chunk_size=20)

        # Create utterances that together exceed max size
        long_text = "This is a test sentence that is fairly long. " * 5  # ~220 chars
        utterances = [
            TranscriptUtterance(speaker="A", text=long_text, start_ms=1000, end_ms=10000),
            TranscriptUtterance(speaker="A", text=long_text, start_ms=10000, end_ms=20000),
        ]

        chunks = chunker.chunk(utterances)

        # Should split into multiple chunks
        assert len(chunks) >= 2
        for chunk in chunks:
            # Allow some tolerance since we split at utterance boundaries
            assert len(chunk.text) <= chunker.max_chunk_size + len(long_text)

    def test_chunk_timestamps_preserved(self):
        """Test that timestamps are correctly preserved in chunks."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker()
        utterances = [
            TranscriptUtterance(speaker="A", text="First", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="A", text="Second", start_ms=2000, end_ms=3000),
            TranscriptUtterance(speaker="A", text="Third", start_ms=3000, end_ms=4000),
        ]

        chunks = chunker.chunk(utterances)

        assert len(chunks) == 1
        assert chunks[0].start_ms == 1000  # First utterance start
        assert chunks[0].end_ms == 4000    # Last utterance end

    def test_chunk_multiple_speakers_labeled(self):
        """Test that chunks with multiple speakers are labeled correctly."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        # Create a scenario where multiple speakers end up in one chunk
        # (speaker B's response is too short to warrant its own chunk)
        chunker = TranscriptChunker(max_chunk_size=1000, min_chunk_size=200)
        utterances = [
            TranscriptUtterance(speaker="A", text="Short", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="B", text="Also short", start_ms=2000, end_ms=3000),
        ]

        chunks = chunker.chunk(utterances)

        # Both should be in one chunk since neither exceeds min_chunk_size
        assert len(chunks) == 1
        assert set(chunks[0].speakers) == {"A", "B"}

    def test_chunk_empty_utterances_skipped(self):
        """Test that empty utterances are skipped."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker()
        utterances = [
            TranscriptUtterance(speaker="A", text="Real content", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="A", text="", start_ms=2000, end_ms=3000),
            TranscriptUtterance(speaker="A", text="   ", start_ms=3000, end_ms=4000),
            TranscriptUtterance(speaker="A", text="More content", start_ms=4000, end_ms=5000),
        ]

        chunks = chunker.chunk(utterances)

        assert len(chunks) == 1
        assert chunks[0].utterance_count == 2  # Only non-empty
        assert "Real content" in chunks[0].text
        assert "More content" in chunks[0].text

    def test_chunk_metadata_preserved(self):
        """Test that source metadata is preserved in chunks."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker()
        utterances = [
            TranscriptUtterance(speaker="A", text="Content", start_ms=1000, end_ms=2000),
        ]

        chunks = chunker.chunk(utterances, source_metadata={
            "video_id": "test123",
            "meeting_date": "2025-11-17",
        })

        assert chunks[0].metadata["video_id"] == "test123"
        assert chunks[0].metadata["meeting_date"] == "2025-11-17"

    def test_split_long_utterance(self):
        """Test that very long utterances are split at sentence boundaries."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker(max_chunk_size=200)

        # Create a very long utterance
        long_text = "This is sentence one. " * 20  # ~440 chars
        utterances = [
            TranscriptUtterance(
                speaker="A",
                text=long_text.strip(),
                start_ms=0,
                end_ms=60000,  # 1 minute
            ),
        ]

        chunks = chunker.chunk(utterances)

        # Should be split into multiple chunks
        assert len(chunks) >= 2
        # No chunk should exceed max_chunk_size by too much
        for chunk in chunks:
            assert len(chunk.text) <= chunker.max_chunk_size + 50  # Allow small tolerance for speaker label

    def test_split_preserves_timestamps_proportionally(self):
        """Test that split utterances have proportional timestamps."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker(max_chunk_size=100)

        # Create a long utterance
        long_text = "Word " * 100  # 500 chars
        utterances = [
            TranscriptUtterance(
                speaker="A",
                text=long_text.strip(),
                start_ms=0,
                end_ms=100000,  # 100 seconds
            ),
        ]

        chunks = chunker.chunk(utterances)

        # First chunk should start at 0
        assert chunks[0].start_ms == 0
        # Last chunk should end at 100000
        assert chunks[-1].end_ms == 100000
        # Chunks should be in order
        for i in range(1, len(chunks)):
            assert chunks[i].start_ms >= chunks[i-1].start_ms


class TestTranscriptChunkerWithRealData:
    """Tests using real testimony files from data/testimony/."""

    @pytest.fixture
    def testimony_file(self):
        """Get a real testimony file for testing."""
        if not TESTIMONY_DIR.exists():
            pytest.skip(f"Testimony directory not found: {TESTIMONY_DIR}")

        # Look for a testimony file
        files = list(TESTIMONY_DIR.glob("testimony_*.json"))
        if not files:
            pytest.skip("No testimony files found")

        # Use 725AYRBl9DA (Nov 3 meeting) as it's well-formatted
        preferred = TESTIMONY_DIR / "testimony_725AYRBl9DA.json"
        if preferred.exists():
            return preferred

        return files[0]

    def test_load_real_transcript(self, testimony_file):
        """Test loading a real AssemblyAI transcript."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker()
        utterances = chunker.load_transcript(testimony_file)

        # Should have substantial utterances
        assert len(utterances) > 50, f"Expected >50 utterances, got {len(utterances)}"

        # All utterances should have required fields
        for utt in utterances[:10]:  # Check first 10
            assert utt.speaker, "Missing speaker"
            assert utt.text, "Missing text"
            assert utt.start_ms >= 0, "Invalid start_ms"
            assert utt.end_ms >= utt.start_ms, "end_ms < start_ms"

    def test_chunk_real_transcript(self, testimony_file):
        """Test chunking a real transcript."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker(max_chunk_size=1500)
        chunks = chunker.chunk_file(testimony_file)

        # Should produce reasonable number of chunks
        assert len(chunks) > 10, f"Expected >10 chunks, got {len(chunks)}"

        # Check chunk properties
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.total_chunks == len(chunks)
            assert chunk.speaker in ["A", "B", "C", "D", "E", "F", "G", "multiple"] or chunk.speaker.isalpha()
            assert chunk.start_ms < chunk.end_ms
            assert len(chunk.text) > 0

    def test_chunk_size_distribution(self, testimony_file):
        """Test that chunks have reasonable size distribution."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker(max_chunk_size=1500, min_chunk_size=200)
        chunks = chunker.chunk_file(testimony_file)

        sizes = [len(c.text) for c in chunks]

        # Most chunks should be reasonably sized
        avg_size = sum(sizes) / len(sizes)
        assert 300 < avg_size < 1500, f"Average chunk size {avg_size} is outside expected range"

        # No chunk should be excessively large
        max_size = max(sizes)
        assert max_size < 3000, f"Max chunk size {max_size} is too large"

    def test_no_data_loss(self, testimony_file):
        """Test that chunking preserves all utterance text content."""
        from civicos._internal.meetings.transcript import TranscriptChunker
        import json

        chunker = TranscriptChunker()
        chunks = chunker.chunk_file(testimony_file)

        # Load original data
        with open(testimony_file) as f:
            original = json.load(f)

        # Get all original text (concatenated)
        original_text = " ".join(
            u.get("text", "").strip()
            for u in original.get("utterances", [])
            if u.get("text", "").strip()
        )

        # Get all chunk text (strip speaker labels for comparison)
        import re
        chunk_text = " ".join(
            re.sub(r'\[[A-Z]\] ', '', c.text)
            for c in chunks
        )

        # All original words should appear in chunks (allow for whitespace normalization)
        original_words = set(original_text.split())
        chunk_words = set(chunk_text.split())

        # Check coverage - all original words should be in chunks
        missing_words = original_words - chunk_words
        # Allow small tolerance for edge cases
        coverage = 1 - (len(missing_words) / len(original_words)) if original_words else 1
        assert coverage > 0.99, (
            f"Text coverage too low: {coverage:.2%}. Missing {len(missing_words)} words."
        )

    def test_speaker_attribution_preserved(self, testimony_file):
        """Test that speaker attribution is preserved in chunks."""
        from civicos._internal.meetings.transcript import TranscriptChunker
        import json

        chunker = TranscriptChunker()
        chunks = chunker.chunk_file(testimony_file)

        # Load original to get speaker set
        with open(testimony_file) as f:
            original = json.load(f)

        original_speakers = set(u.get("speaker") for u in original.get("utterances", []))

        # All original speakers should appear in chunks
        chunk_speakers = set()
        for chunk in chunks:
            chunk_speakers.update(chunk.speakers)

        assert original_speakers <= chunk_speakers, (
            f"Missing speakers: {original_speakers - chunk_speakers}"
        )

    def test_timestamp_continuity(self, testimony_file):
        """Test that chunk timestamps are continuous (no gaps/overlaps)."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker()
        chunks = chunker.chunk_file(testimony_file)

        # Chunks should be in chronological order
        for i in range(1, len(chunks)):
            prev_end = chunks[i - 1].end_ms
            curr_start = chunks[i].start_ms
            # Next chunk should start at or after previous chunk ends
            assert curr_start >= prev_end - 1000, (  # Allow 1 second overlap for utterance boundaries
                f"Chunk {i} starts at {curr_start} but chunk {i-1} ends at {prev_end}"
            )


class TestConvenienceFunction:
    """Tests for the chunk_transcript convenience function."""

    def test_chunk_transcript_function(self):
        """Test the convenience function."""
        from civicos._internal.meetings.transcript import chunk_transcript

        # Skip if no testimony files
        if not TESTIMONY_DIR.exists():
            pytest.skip("Testimony directory not found")

        files = list(TESTIMONY_DIR.glob("testimony_*.json"))
        if not files:
            pytest.skip("No testimony files found")

        # Use preferred file or first available
        test_file = TESTIMONY_DIR / "testimony_725AYRBl9DA.json"
        if not test_file.exists():
            test_file = files[0]

        result = chunk_transcript(test_file)

        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(c, dict) for c in result)
        assert all("text" in c for c in result)
        assert all("speaker" in c for c in result)
        assert all("start_ms" in c for c in result)


class TestSpeakerInfo:
    """Tests for SpeakerInfo dataclass."""

    def test_speaker_info_creation(self):
        """Test basic SpeakerInfo creation."""
        from civicos._internal.meetings.transcript import SpeakerInfo

        info = SpeakerInfo(
            speaker_id="A",
            role="council",
            name="Hill",
            title="Council Member",
            confidence=0.9,
            evidence=["Responded 'present' to roll call"],
        )

        assert info.speaker_id == "A"
        assert info.role == "council"
        assert info.name == "Hill"
        assert info.title == "Council Member"
        assert info.confidence == 0.9
        assert len(info.evidence) == 1

    def test_speaker_info_defaults(self):
        """Test SpeakerInfo default values."""
        from civicos._internal.meetings.transcript import SpeakerInfo

        info = SpeakerInfo(speaker_id="B", role="unknown")

        assert info.name is None
        assert info.title is None
        assert info.confidence == 0.0
        assert info.evidence == []

    def test_speaker_info_to_dict(self):
        """Test SpeakerInfo serialization."""
        from civicos._internal.meetings.transcript import SpeakerInfo

        info = SpeakerInfo(
            speaker_id="C",
            role="staff",
            name="Clerk",
            title="City Clerk",
            confidence=0.7,
            evidence=["Called 3 names during roll call"],
        )

        result = info.to_dict()

        assert result["speaker_id"] == "C"
        assert result["role"] == "staff"
        assert result["name"] == "Clerk"
        assert result["title"] == "City Clerk"
        assert result["confidence"] == 0.7
        assert "Called 3 names" in result["evidence"][0]


class TestSpeakerRoleDetector:
    """Tests for SpeakerRoleDetector class."""

    def test_detector_initialization(self):
        """Test detector initialization."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector

        detector = SpeakerRoleDetector()
        assert detector.roll_call_window_ms == 600_000  # 10 minutes to handle meeting delays
        assert detector.min_utterances_for_staff == 10

    def test_detector_custom_params(self):
        """Test detector with custom parameters."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector

        detector = SpeakerRoleDetector(
            roll_call_window_ms=60_000,
            min_utterances_for_staff=5,
        )
        assert detector.roll_call_window_ms == 60_000
        assert detector.min_utterances_for_staff == 5

    def test_detect_empty_utterances(self):
        """Test detection with empty utterances."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector

        detector = SpeakerRoleDetector()
        result = detector.detect_roles([])

        assert result == {}

    def test_detect_roll_call_council_members(self):
        """Test detecting council members from roll call."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        # Simulate roll call sequence
        utterances = [
            TranscriptUtterance(speaker="D", text="Vice Mayor Bushy.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=2500, end_ms=3500),
            TranscriptUtterance(speaker="F", text="Present.", start_ms=3500, end_ms=4000),
            TranscriptUtterance(speaker="D", text="Council Member Kurtz.", start_ms=4000, end_ms=5000),
            TranscriptUtterance(speaker="G", text="Present.", start_ms=5000, end_ms=5500),
        ]

        result = detector.detect_roles(utterances)

        # Check that council members were detected
        assert result["E"].role == "council"
        assert result["E"].name == "Bushy"
        assert result["E"].title == "Vice Mayor"
        assert result["E"].confidence >= 0.9

        assert result["F"].role == "council"
        assert result["F"].name == "Hill"
        assert result["F"].title == "Council Member"

        assert result["G"].role == "council"
        assert result["G"].name == "Kurtz"

        # D should be identified as clerk (called multiple names)
        assert result["D"].role == "staff"
        assert result["D"].title == "City Clerk"

    def test_detect_mayor_from_roll_call(self):
        """Test detecting mayor from roll call."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(speaker="D", text="Mayor Kate.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="C", text="Present.", start_ms=2000, end_ms=2500),
        ]

        result = detector.detect_roles(utterances)

        assert result["C"].role == "council"
        assert result["C"].name == "Kate"
        assert result["C"].title == "Mayor"

    def test_detect_public_from_self_introduction(self):
        """Test detecting public speakers from self-introductions.

        Note: Name extraction requires LLM provider. Without LLM, role is still
        detected via patterns but name is not extracted.
        """
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(
                speaker="X",
                text="My name is Sarah Sonnett and I've been a resident of San Rafael.",
                start_ms=100000,
                end_ms=105000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # Role detected via "my name is" pattern
        assert result["X"].role == "public"
        # Name extraction requires LLM - without it, name is None
        assert result["X"].name is None
        assert result["X"].confidence >= 0.6

    def test_detect_public_from_patterns(self):
        """Test detecting public speakers from testimony patterns."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(
                speaker="Y",
                text="Thank you mayor and council members for your time.",
                start_ms=200000,
                end_ms=205000,
            ),
        ]

        result = detector.detect_roles(utterances)

        assert result["Y"].role == "public"
        assert "public testimony patterns" in result["Y"].evidence[0].lower()

    def test_detect_staff_from_frequency(self):
        """Test detecting staff from high utterance frequency."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector(min_utterances_for_staff=5)

        # Create a speaker with many utterances
        utterances = [
            TranscriptUtterance(
                speaker="H",
                text=f"Staff statement {i}.",
                start_ms=200000 + i * 1000,
                end_ms=200500 + i * 1000,
            )
            for i in range(10)
        ]

        result = detector.detect_roles(utterances)

        assert result["H"].role == "staff"
        assert "High frequency speaker" in result["H"].evidence[0]

    def test_detect_public_from_low_frequency(self):
        """Test detecting public from low utterance frequency."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(speaker="Z", text="One comment.", start_ms=300000, end_ms=301000),
            TranscriptUtterance(speaker="Z", text="Another comment.", start_ms=301000, end_ms=302000),
        ]

        result = detector.detect_roles(utterances)

        assert result["Z"].role == "public"
        assert "Low frequency speaker" in result["Z"].evidence[0]

    def test_roll_call_window_respected(self):
        """Test that roll call detection only looks at first N milliseconds."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector(roll_call_window_ms=5000)

        utterances = [
            # Inside window
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="F", text="Present.", start_ms=2000, end_ms=2500),
            # Outside window - should not be detected as council from roll call
            TranscriptUtterance(speaker="D", text="Council Member Late.", start_ms=10000, end_ms=11000),
            TranscriptUtterance(speaker="X", text="Present.", start_ms=11000, end_ms=11500),
        ]

        result = detector.detect_roles(utterances)

        assert result["F"].role == "council"
        assert result["F"].name == "Hill"
        # X should not be identified as council from roll call
        assert result["X"].role != "council" or result["X"].name != "Late"


class TestSpeakerMetadataIntegration:
    """Integration tests for speaker metadata in chunks."""

    def test_chunks_include_speaker_metadata(self):
        """Test that chunks include speaker role metadata."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker()

        # Simulate a roll call followed by content
        utterances = [
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="F", text="Present.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(speaker="F", text="I move to approve the item.", start_ms=50000, end_ms=52000),
            TranscriptUtterance(speaker="F", text="We should discuss this further.", start_ms=52000, end_ms=54000),
        ]

        chunks = chunker.chunk(utterances, detect_speaker_roles=True)

        # Find chunk with speaker F
        f_chunks = [c for c in chunks if c.speaker == "F"]
        assert len(f_chunks) > 0

        # Check metadata
        chunk = f_chunks[0]
        assert chunk.metadata.get("speaker_role") == "council"
        assert chunk.metadata.get("speaker_name") == "Hill"
        assert chunk.metadata.get("speaker_title") == "Council Member"
        assert chunk.metadata.get("role_confidence", 0) >= 0.9

    def test_chunks_include_speakers_info(self):
        """Test that chunks include per-speaker info."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker(min_chunk_size=50, max_chunk_size=500)

        utterances = [
            TranscriptUtterance(speaker="A", text="Welcome to the meeting.", start_ms=1000, end_ms=3000),
            TranscriptUtterance(speaker="B", text="Thank you mayor for having us.", start_ms=3000, end_ms=5000),
        ]

        chunks = chunker.chunk(utterances, detect_speaker_roles=True)

        # Should have speakers_info in metadata
        chunk = chunks[0]
        assert "speakers_info" in chunk.metadata

        speakers_info = chunk.metadata["speakers_info"]
        assert "A" in speakers_info or "B" in speakers_info

    def test_detect_speaker_roles_disabled(self):
        """Test that speaker role detection can be disabled."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker()

        utterances = [
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="F", text="Present.", start_ms=2000, end_ms=2500),
        ]

        chunks = chunker.chunk(utterances, detect_speaker_roles=False)

        # Should not have speaker role metadata
        assert "speaker_role" not in chunks[0].metadata
        assert "speakers_info" not in chunks[0].metadata

    def test_multiple_speakers_chunk_metadata(self):
        """Test metadata when chunk has multiple speakers."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker(min_chunk_size=500, max_chunk_size=2000)

        # Create a scenario where multiple speakers end up in one chunk
        utterances = [
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="F", text="Present.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(speaker="D", text="Council Member Kurtz.", start_ms=2500, end_ms=3500),
            TranscriptUtterance(speaker="G", text="Present.", start_ms=3500, end_ms=4000),
        ]

        chunks = chunker.chunk(utterances, detect_speaker_roles=True)

        # Find chunk with multiple speakers
        multi_chunk = None
        for chunk in chunks:
            if len(chunk.speakers) > 1:
                multi_chunk = chunk
                break

        if multi_chunk:
            # Should have speakers_info for all speakers
            speakers_info = multi_chunk.metadata.get("speakers_info", {})
            # Check that we have info for at least some speakers
            assert len(speakers_info) >= 1


@pytest.mark.requires_real_data
class TestSpeakerMetadataWithRealData:
    """Tests using real testimony files."""

    @pytest.fixture
    def testimony_file(self):
        """Get a real testimony file for testing."""
        if not TESTIMONY_DIR.exists():
            pytest.skip(f"Testimony directory not found: {TESTIMONY_DIR}")

        # Prefer the Oct 6 meeting file which has good roll call data
        preferred = TESTIMONY_DIR / "testimony_MpxrGRb16HQ_v2.json"
        if preferred.exists():
            return preferred

        files = list(TESTIMONY_DIR.glob("testimony_*.json"))
        if not files:
            pytest.skip("No testimony files found")

        return files[0]

    def test_real_transcript_speaker_detection(self, testimony_file):
        """Test speaker detection on real transcript."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker()
        chunks = chunker.chunk_file(testimony_file, detect_speaker_roles=True)

        # Should have chunks with metadata
        assert len(chunks) > 0

        # Count chunks by role
        role_counts = {}
        for chunk in chunks:
            role = chunk.metadata.get("speaker_role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1

        # Should have detected at least some council members
        assert "council" in role_counts or "staff" in role_counts, (
            f"Expected to detect council/staff roles. Got: {role_counts}"
        )

    def test_real_transcript_council_names_detected(self, testimony_file):
        """Test that council member names are detected from real data."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker()
        chunks = chunker.chunk_file(testimony_file, detect_speaker_roles=True)

        # Collect all detected names
        detected_names = set()
        for chunk in chunks:
            name = chunk.metadata.get("speaker_name")
            if name:
                detected_names.add(name)

            # Also check speakers_info
            speakers_info = chunk.metadata.get("speakers_info", {})
            for info in speakers_info.values():
                if info.get("name"):
                    detected_names.add(info["name"])

        # Should have detected some names
        assert len(detected_names) > 0, "No speaker names detected"

        # San Rafael council members - check if any are detected
        expected_names = {"Hill", "Bushy", "Kate", "Kurtz", "Curts"}
        detected_expected = detected_names & expected_names
        # Should detect at least one council member name
        assert len(detected_expected) >= 1, (
            f"Expected to detect San Rafael council names. "
            f"Detected: {detected_names}"
        )

    def test_real_transcript_public_speakers_detected(self, testimony_file):
        """Test that public speakers are detected from real data."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker()
        chunks = chunker.chunk_file(testimony_file, detect_speaker_roles=True)

        # Count public speakers
        public_count = sum(
            1 for chunk in chunks
            if chunk.metadata.get("speaker_role") == "public"
        )

        # City council meetings typically have public comment periods
        assert public_count > 0, "Expected to detect some public speakers"

    def test_real_transcript_staff_detected(self, testimony_file):
        """Test that staff members are detected from real data."""
        from civicos._internal.meetings.transcript import TranscriptChunker

        chunker = TranscriptChunker()
        chunks = chunker.chunk_file(testimony_file, detect_speaker_roles=True)

        # Count staff members and collect their titles
        staff_chunks = [
            chunk for chunk in chunks
            if chunk.metadata.get("speaker_role") == "staff"
        ]

        staff_titles = set()
        for chunk in chunks:
            speakers_info = chunk.metadata.get("speakers_info", {})
            for info in speakers_info.values():
                if info.get("role") == "staff" and info.get("title"):
                    staff_titles.add(info["title"])

        # City council meetings typically have staff (City Clerk at minimum for roll call)
        assert len(staff_chunks) > 0 or len(staff_titles) > 0, (
            f"Expected to detect some staff members. Found {len(staff_chunks)} staff chunks."
        )


class TestStaffDetection:
    """Tests for staff role detection."""

    def test_detect_city_clerk_from_roll_call_caller(self):
        """Test detecting City Clerk as the speaker who calls multiple names during roll call."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            # Clerk calls names
            TranscriptUtterance(speaker="C", text="Vice Mayor Bushy.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(speaker="C", text="Council Member Hill.", start_ms=2500, end_ms=3000),
            TranscriptUtterance(speaker="F", text="Present.", start_ms=3000, end_ms=3500),
            TranscriptUtterance(speaker="C", text="Council Member Kurtz.", start_ms=3500, end_ms=4000),
            TranscriptUtterance(speaker="G", text="Present.", start_ms=4000, end_ms=4500),
        ]

        result = detector.detect_roles(utterances)

        # Speaker C should be identified as City Clerk (called 3 names)
        assert result["C"].role == "staff"
        assert result["C"].title == "City Clerk"
        assert "Called 3 names during roll call" in result["C"].evidence[0]

    def test_detect_city_manager_from_introduction(self):
        """Test detecting City Manager when introduced by 'I'll turn to the City Manager'."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            # Mayor introduces City Manager
            TranscriptUtterance(
                speaker="B",
                text="I'll turn to the City Manager for the City Manager Report.",
                start_ms=100000,
                end_ms=102000,
            ),
            # City Manager speaks
            TranscriptUtterance(
                speaker="A",
                text="Good evening Mayor, Council members and the community. I wanted to start with an update on our project.",
                start_ms=102000,
                end_ms=106000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # Speaker A should be identified as staff (City Manager)
        assert result["A"].role == "staff"
        assert "City Manager" in (result["A"].title or "")

    def test_detect_city_attorney_from_closed_session_report(self):
        """Test detecting City Attorney from 'no reportable action in closed session' pattern."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(
                speaker="A",
                text="Thank you. Mayor Kate, no reportable action was taken in closed session.",
                start_ms=50000,
                end_ms=55000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # Speaker A should be identified as staff (City Attorney)
        assert result["A"].role == "staff"
        assert "City Attorney" in (result["A"].title or "")
        # Evidence should mention city attorney pattern
        assert any("city attorney" in e.lower() for e in result["A"].evidence)

    def test_detect_city_attorney_from_invitation(self):
        """Test detecting City Attorney when invited to report."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            # Mayor invites City Attorney
            TranscriptUtterance(
                speaker="B",
                text="I'll invite the City Attorney to report out on that.",
                start_ms=40000,
                end_ms=42000,
            ),
            # City Attorney speaks
            TranscriptUtterance(
                speaker="A",
                text="Thank you Mayor. No reportable action was taken.",
                start_ms=42000,
                end_ms=44000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # Speaker A should be identified as City Attorney
        assert result["A"].role == "staff"
        assert "City Attorney" in (result["A"].title or "")

    def test_detect_staff_from_good_evening_greeting(self):
        """Test detecting senior staff from 'Good evening Mayor, Council members and community' pattern."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(
                speaker="A",
                text="Good evening, Mayor, Council members and the community. Today I'm presenting the quarterly report.",
                start_ms=100000,
                end_ms=105000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # Speaker A should be identified as staff (City Manager pattern)
        assert result["A"].role == "staff"

    def test_staff_title_preserved_with_multiple_evidence(self):
        """Test that staff title is set correctly when multiple evidence sources exist."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            # City Attorney says closed session report
            TranscriptUtterance(
                speaker="A",
                text="No reportable action was taken in closed session.",
                start_ms=50000,
                end_ms=55000,
            ),
            # Same speaker gives long update (could be mistaken for City Manager)
            TranscriptUtterance(
                speaker="A",
                text="I also wanted to update the council on the ongoing litigation. " * 10,  # Long text
                start_ms=55000,
                end_ms=65000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # Speaker A should be City Attorney (closed session pattern has higher confidence)
        assert result["A"].role == "staff"
        assert result["A"].title == "City Attorney"

    def test_multiple_staff_roles_detected(self):
        """Test detecting multiple staff members in one transcript."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            # Clerk calls roll
            TranscriptUtterance(speaker="C", text="Vice Mayor Bushy.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(speaker="C", text="Council Member Hill.", start_ms=2500, end_ms=3000),
            TranscriptUtterance(speaker="F", text="Present.", start_ms=3000, end_ms=3500),
            # Mayor invites City Attorney
            TranscriptUtterance(
                speaker="B",
                text="I'll invite the City Attorney to report out.",
                start_ms=40000,
                end_ms=42000,
            ),
            TranscriptUtterance(
                speaker="A",
                text="Thank you. No reportable action was taken in closed session.",
                start_ms=42000,
                end_ms=45000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # Both C (Clerk) and A (City Attorney) should be detected as staff
        staff_speakers = [s for s, info in result.items() if info.role == "staff"]
        assert len(staff_speakers) >= 2, f"Expected at least 2 staff, got {staff_speakers}"

        # Check specific titles
        assert result["C"].title == "City Clerk"
        assert result["A"].title == "City Attorney"

    def test_staff_detection_does_not_override_council(self):
        """Test that staff detection doesn't override council member detection."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            # Clerk calls name
            TranscriptUtterance(speaker="C", text="Council Member Hill.", start_ms=1000, end_ms=2000),
            # Council member responds
            TranscriptUtterance(speaker="F", text="Present.", start_ms=2000, end_ms=2500),
            # Same council member uses formal greeting (could match staff pattern)
            TranscriptUtterance(
                speaker="F",
                text="Good evening, Mayor, Council members and the community. I want to make a motion.",
                start_ms=50000,
                end_ms=55000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # Speaker F should remain council (roll call detection takes precedence)
        assert result["F"].role == "council"
        assert result["F"].name == "Hill"

    def test_chief_pattern_not_falsely_triggered(self):
        """Test that 'chief of' or 'chief the' patterns don't falsely detect staff."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(
                speaker="A",
                text="The chief of police mentioned that in the report.",
                start_ms=100000,
                end_ms=105000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # Should not incorrectly identify as Chief due to "chief of" pattern
        # (role might be unknown or staff from other heuristics, but title should not be "Chief Of")
        if result["A"].title:
            assert result["A"].title.lower() not in ("chief of", "of")


class TestPublicCommentDetection:
    """Tests for public comment section detection."""

    def test_detect_public_comment_section_open_close(self):
        """Test detecting a public comment section with explicit open and close."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(
                speaker="A",  # Mayor
                text="We will now move to item 6. I'll open up public comment on this item.",
                start_ms=100000,
                end_ms=105000,
            ),
            TranscriptUtterance(
                speaker="B",  # Public
                text="Thank you. My name is John Smith and I'm here to speak about the housing proposal.",
                start_ms=106000,
                end_ms=115000,
            ),
            TranscriptUtterance(
                speaker="C",  # Another public speaker
                text="I live in the neighborhood and have concerns about traffic.",
                start_ms=116000,
                end_ms=125000,
            ),
            TranscriptUtterance(
                speaker="A",  # Mayor
                text="Not seeing any more speakers, I'll close the public comment.",
                start_ms=126000,
                end_ms=130000,
            ),
        ]

        sections = detector.detect_public_comment_sections(utterances)

        assert len(sections) == 1
        section = sections[0]
        assert section["start_idx"] == 1  # First utterance after open
        assert section["end_idx"] == 2  # Last utterance before close
        assert section["opener_speaker"] == "A"
        assert section["closer_speaker"] == "A"
        assert section["confidence"] == 0.9  # High confidence with explicit close

    def test_detect_multiple_public_comment_sections(self):
        """Test detecting multiple public comment sections for different agenda items."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(
                speaker="A",
                text="I'll open up the public comment on item 5.",
                start_ms=100000,
                end_ms=105000,
            ),
            TranscriptUtterance(
                speaker="B",
                text="My name is Jane Doe speaking about item 5.",
                start_ms=106000,
                end_ms=115000,
            ),
            TranscriptUtterance(
                speaker="A",
                text="I'll close the public comment.",
                start_ms=116000,
                end_ms=120000,
            ),
            TranscriptUtterance(
                speaker="A",
                text="Now for item 6. I'll open public comment.",
                start_ms=200000,
                end_ms=205000,
            ),
            TranscriptUtterance(
                speaker="C",
                text="Thank you for the opportunity to comment.",
                start_ms=206000,
                end_ms=215000,
            ),
            TranscriptUtterance(
                speaker="A",
                text="Not seeing any other public comment, I'll close the public comment.",
                start_ms=216000,
                end_ms=220000,
            ),
        ]

        sections = detector.detect_public_comment_sections(utterances)

        assert len(sections) == 2
        # First section
        assert sections[0]["start_idx"] == 1
        assert sections[0]["end_idx"] == 1
        # Second section
        assert sections[1]["start_idx"] == 4
        assert sections[1]["end_idx"] == 4

    def test_detect_unclosed_public_comment_section(self):
        """Test detecting a public comment section that is never explicitly closed."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(
                speaker="A",
                text="I'll open up public comment.",
                start_ms=100000,
                end_ms=105000,
            ),
            TranscriptUtterance(
                speaker="B",
                text="I'm here to speak about the project.",
                start_ms=106000,
                end_ms=115000,
            ),
            TranscriptUtterance(
                speaker="C",
                text="I have concerns about environmental impact.",
                start_ms=116000,
                end_ms=125000,
            ),
        ]

        sections = detector.detect_public_comment_sections(utterances)

        assert len(sections) == 1
        section = sections[0]
        assert section["start_idx"] == 1
        assert section["end_idx"] == 2  # To end of transcript
        assert section["closer_idx"] is None
        assert section["confidence"] == 0.5  # Lower confidence for unclosed

    def test_is_in_public_comment_section(self):
        """Test the is_in_public_comment_section helper method."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(speaker="A", text="Opening remarks.", start_ms=0, end_ms=5000),
            TranscriptUtterance(speaker="A", text="I'll open public comment.", start_ms=10000, end_ms=15000),
            TranscriptUtterance(speaker="B", text="Public speaker here.", start_ms=16000, end_ms=25000),
            TranscriptUtterance(speaker="A", text="I'll close the public comment.", start_ms=26000, end_ms=30000),
            TranscriptUtterance(speaker="A", text="Closing remarks.", start_ms=40000, end_ms=45000),
        ]

        detector.detect_public_comment_sections(utterances)

        assert detector.is_in_public_comment_section(0) is False  # Before open
        assert detector.is_in_public_comment_section(1) is False  # The open marker itself
        assert detector.is_in_public_comment_section(2) is True   # Public comment
        assert detector.is_in_public_comment_section(3) is False  # The close marker
        assert detector.is_in_public_comment_section(4) is False  # After close

    def test_public_comment_context_improves_role_detection(self):
        """Test that public comment section detection improves speaker role detection."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(speaker="A", text="Council meeting begins.", start_ms=0, end_ms=5000),
            TranscriptUtterance(speaker="A", text="I'll open public comment.", start_ms=10000, end_ms=15000),
            TranscriptUtterance(speaker="B", text="Hello there.", start_ms=16000, end_ms=20000),
            TranscriptUtterance(speaker="C", text="Hi everyone.", start_ms=21000, end_ms=25000),
            TranscriptUtterance(speaker="A", text="I'll close the public comment.", start_ms=26000, end_ms=30000),
        ]

        result = detector.detect_roles(utterances)

        # Speakers B and C only spoke in public comment section
        assert result["B"].role == "public"
        assert result["C"].role == "public"
        assert "public comment sections" in result["B"].evidence[-1].lower()
        assert "public comment sections" in result["C"].evidence[-1].lower()

    def test_chunk_metadata_includes_public_comment(self):
        """Test that chunk metadata includes public comment information."""
        from civicos._internal.meetings.transcript import TranscriptChunker, TranscriptUtterance

        chunker = TranscriptChunker()

        utterances = [
            TranscriptUtterance(speaker="A", text="I'll open public comment.", start_ms=0, end_ms=5000),
            TranscriptUtterance(speaker="B", text="I'm here to speak about housing. " * 20, start_ms=6000, end_ms=30000),
            TranscriptUtterance(speaker="A", text="I'll close the public comment.", start_ms=31000, end_ms=35000),
            TranscriptUtterance(speaker="A", text="Now for the vote. " * 20, start_ms=36000, end_ms=60000),
        ]

        chunks = chunker.chunk(utterances)

        # Should have at least one chunk with public comment flag
        public_chunks = [c for c in chunks if c.metadata.get("is_public_comment")]
        non_public_chunks = [c for c in chunks if not c.metadata.get("is_public_comment")]

        assert len(public_chunks) >= 1, "Should have at least one public comment chunk"
        assert len(non_public_chunks) >= 1, "Should have at least one non-public comment chunk"

        # Public comment chunk should have section ID
        for chunk in public_chunks:
            assert "public_comment_section_id" in chunk.metadata or "public_comment_section_ids" in chunk.metadata

    def test_welcome_public_comment_pattern(self):
        """Test detection of 'welcome public comment' opening pattern."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(
                speaker="A",
                text="We would welcome public comment on items 5a through 5g.",
                start_ms=100000,
                end_ms=105000,
            ),
            TranscriptUtterance(
                speaker="B",
                text="Thank you. I support these measures.",
                start_ms=106000,
                end_ms=115000,
            ),
            TranscriptUtterance(
                speaker="A",
                text="I'll close the public comment.",
                start_ms=116000,
                end_ms=120000,
            ),
        ]

        sections = detector.detect_public_comment_sections(utterances)

        assert len(sections) == 1
        assert sections[0]["start_idx"] == 1

    def test_not_seeing_public_comment_close_pattern(self):
        """Test detection of 'not seeing any public comment' closing pattern."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(
                speaker="A",
                text="Anyone from the public wishing to comment, now is your opportunity.",
                start_ms=100000,
                end_ms=105000,
            ),
            TranscriptUtterance(
                speaker="B",
                text="I'd like to comment on this item.",
                start_ms=106000,
                end_ms=115000,
            ),
            TranscriptUtterance(
                speaker="A",
                text="Not seeing any other public comment, we'll move to the vote.",
                start_ms=116000,
                end_ms=120000,
            ),
        ]

        sections = detector.detect_public_comment_sections(utterances)

        assert len(sections) == 1
        section = sections[0]
        assert section["confidence"] == 0.9  # Explicit close pattern found


class TestPublicCommentWithRealData:
    """Integration tests for public comment detection with real San Rafael transcripts."""

    def test_real_transcript_public_comment_detection(self):
        """Test public comment detection on actual San Rafael city council transcript."""
        from pathlib import Path
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptChunker

        transcript_path = Path("data/testimony/testimony_MpxrGRb16HQ_v2.json")
        if not transcript_path.exists():
            import pytest
            pytest.skip("Real transcript data not available")

        chunker = TranscriptChunker()
        utterances = chunker.load_transcript(transcript_path)

        # Detect public comment sections
        detector = SpeakerRoleDetector()
        sections = detector.detect_public_comment_sections(utterances)

        # San Rafael Nov 3 meeting should have multiple public comment sections
        assert len(sections) >= 2, f"Expected at least 2 sections, got {len(sections)}"

        # Verify section structure
        for section in sections:
            assert "start_idx" in section
            assert "end_idx" in section
            assert "confidence" in section
            assert section["end_idx"] >= section["start_idx"]

    def test_real_transcript_chunk_metadata(self):
        """Test that chunk metadata is populated correctly for real transcript."""
        from pathlib import Path
        from civicos._internal.meetings.transcript import TranscriptChunker

        transcript_path = Path("data/testimony/testimony_MpxrGRb16HQ_v2.json")
        if not transcript_path.exists():
            import pytest
            pytest.skip("Real transcript data not available")

        chunker = TranscriptChunker()
        chunks = chunker.chunk_file(transcript_path)

        # Should have public comment chunks
        public_chunks = [c for c in chunks if c.metadata.get("is_public_comment")]
        non_public_chunks = [c for c in chunks if not c.metadata.get("is_public_comment")]

        assert len(public_chunks) > 0, "Expected some public comment chunks"
        assert len(non_public_chunks) > 0, "Expected some non-public comment chunks"

        # Verify public comment chunks have section ID
        for chunk in public_chunks:
            has_section_id = (
                "public_comment_section_id" in chunk.metadata or
                "public_comment_section_ids" in chunk.metadata
            )
            assert has_section_id, f"Chunk {chunk.chunk_index} missing section ID"

    def test_real_transcript_public_speakers_detected(self):
        """Test that speakers in public comment sections are detected as public."""
        from pathlib import Path
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptChunker

        transcript_path = Path("data/testimony/testimony_MpxrGRb16HQ_v2.json")
        if not transcript_path.exists():
            import pytest
            pytest.skip("Real transcript data not available")

        chunker = TranscriptChunker()
        utterances = chunker.load_transcript(transcript_path)

        detector = SpeakerRoleDetector()
        speaker_info = detector.detect_roles(utterances)

        # Should have detected some public speakers
        public_speakers = [s for s, info in speaker_info.items() if info.role == "public"]
        assert len(public_speakers) > 0, "Expected some public speakers to be detected"

        # Verify public speakers have evidence
        for speaker_id in public_speakers[:5]:  # Check first 5
            info = speaker_info[speaker_id]
            assert len(info.evidence) > 0, f"Speaker {speaker_id} has no evidence"
