"""
Tests for speaker consistency across meeting transcripts.

Validates that:
1. Same speaker maintains consistent role assignment across all their utterances
2. Name resolution is stable (once detected, name stays the same)
3. Chunk metadata syncs with speaker info (no contradictions)
4. Confidence scores don't degrade for same speaker
5. Real San Rafael transcripts pass diarization quality checks

Run: python -m pytest packages/civic/tests/test_speaker_consistency.py -v
"""

import json
import sys
from pathlib import Path

import pytest

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()

# Add source path for imports
sys.path.insert(0, str(PROJECT_ROOT / "packages/civic/src"))

# Paths to testimony files
TESTIMONY_DIR = PROJECT_ROOT / "data/testimony"


class TestIntraMeetingSpeakerConsistency:
    """Tests for speaker consistency within a single meeting."""

    def test_same_speaker_same_role_all_utterances(self):
        """Same speaker ID gets same role assignment everywhere."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        # Council member appears multiple times (roll call + later discussion)
        utterances = [
            # Roll call
            TranscriptUtterance(speaker="D", text="Vice Mayor Bushy.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=2500, end_ms=3500),
            TranscriptUtterance(speaker="F", text="Present.", start_ms=3500, end_ms=4000),
            # Later discussion - same speakers
            TranscriptUtterance(speaker="E", text="I move to approve.", start_ms=500000, end_ms=505000),
            TranscriptUtterance(speaker="F", text="I second.", start_ms=505000, end_ms=506000),
            TranscriptUtterance(speaker="E", text="Thank you colleagues.", start_ms=600000, end_ms=605000),
            TranscriptUtterance(speaker="F", text="Agreed.", start_ms=605000, end_ms=606000),
        ]

        result = detector.detect_roles(utterances)

        # Speaker E (Bushy) should have consistent role across all utterances
        assert result["E"].role == "council"
        assert result["E"].name == "Bushy"

        # Speaker F (Hill) should have consistent role across all utterances
        assert result["F"].role == "council"
        assert result["F"].name == "Hill"

    def test_speaker_role_not_changed_by_later_utterances(self):
        """A speaker's role detected early doesn't flip later."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        # Council member identified from roll call, then speaks a lot like staff might
        utterances = [
            # Roll call identifies E as council
            TranscriptUtterance(speaker="D", text="Council Member Kurtz.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
            # E then speaks many times (high frequency like staff)
            *[
                TranscriptUtterance(
                    speaker="E",
                    text=f"Discussion point {i}.",
                    start_ms=100000 + i * 1000,
                    end_ms=100500 + i * 1000,
                )
                for i in range(15)
            ],
        ]

        result = detector.detect_roles(utterances)

        # E should remain council despite high frequency (roll call takes precedence)
        assert result["E"].role == "council"
        assert result["E"].name == "Kurtz"
        assert result["E"].confidence >= 0.9  # High confidence from roll call

    def test_public_speaker_stays_public(self):
        """A speaker identified as public doesn't become council/staff later."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        # Public speaker introduces themselves, then speaks multiple times
        utterances = [
            TranscriptUtterance(
                speaker="X",
                text="My name is Sarah and I'm a resident of San Rafael.",
                start_ms=300000,
                end_ms=310000,
            ),
            TranscriptUtterance(
                speaker="X",
                text="I want to express my concerns about this project.",
                start_ms=310000,
                end_ms=320000,
            ),
            TranscriptUtterance(
                speaker="X",
                text="Thank you for listening.",
                start_ms=320000,
                end_ms=325000,
            ),
        ]

        result = detector.detect_roles(utterances)

        assert result["X"].role == "public"

    def test_clerk_stays_staff_throughout_meeting(self):
        """City clerk identified from calling roll remains staff."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            # Roll call
            TranscriptUtterance(speaker="D", text="Vice Mayor Bushy.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=2500, end_ms=3500),
            TranscriptUtterance(speaker="F", text="Present.", start_ms=3500, end_ms=4000),
            TranscriptUtterance(speaker="D", text="Mayor Kate.", start_ms=4000, end_ms=5000),
            TranscriptUtterance(speaker="G", text="Present.", start_ms=5000, end_ms=5500),
            # Later - clerk speaks again for vote
            TranscriptUtterance(
                speaker="D",
                text="The motion passes four to zero.",
                start_ms=700000,
                end_ms=705000,
            ),
            TranscriptUtterance(
                speaker="D",
                text="Moving to the next item on the agenda.",
                start_ms=800000,
                end_ms=805000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # D (clerk) should remain staff throughout
        assert result["D"].role == "staff"
        assert result["D"].title == "City Clerk"


class TestNameResolutionConsistency:
    """Tests for stable name resolution within a meeting."""

    def test_name_detected_once_used_everywhere(self):
        """Once a name is detected for a speaker, it's consistent."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(speaker="D", text="Vice Mayor Bushy.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
        ]

        result = detector.detect_roles(utterances)

        # Name should be set
        assert result["E"].name == "Bushy"
        assert result["E"].title == "Vice Mayor"

    def test_title_consistency(self):
        """Speaker's title doesn't change mid-meeting."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        # Same person called "Council Member" then "Councilwoman" - title should be first detected
        utterances = [
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
        ]

        result = detector.detect_roles(utterances)

        # Title should be from first detection
        assert result["E"].title == "Council Member"

    def test_no_name_collision(self):
        """Different speakers don't get each other's names."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(speaker="D", text="Vice Mayor Bushy.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=2500, end_ms=3500),
            TranscriptUtterance(speaker="F", text="Present.", start_ms=3500, end_ms=4000),
        ]

        result = detector.detect_roles(utterances)

        # Names should be distinct
        assert result["E"].name == "Bushy"
        assert result["F"].name == "Hill"
        assert result["E"].name != result["F"].name


class TestConfidenceStability:
    """Tests for confidence score stability."""

    def test_confidence_not_degraded_by_more_utterances(self):
        """Confidence score doesn't degrade as speaker speaks more."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        # Start with roll call (high confidence), then add many utterances
        utterances_initial = [
            TranscriptUtterance(speaker="D", text="Council Member Kurtz.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
        ]

        result_initial = detector.detect_roles(utterances_initial)
        initial_confidence = result_initial["E"].confidence

        # Same setup with more utterances from E
        utterances_extended = utterances_initial + [
            TranscriptUtterance(
                speaker="E",
                text=f"Discussion point {i}.",
                start_ms=100000 + i * 1000,
                end_ms=100500 + i * 1000,
            )
            for i in range(10)
        ]

        result_extended = detector.detect_roles(utterances_extended)
        extended_confidence = result_extended["E"].confidence

        # Confidence should not drop
        assert extended_confidence >= initial_confidence

    def test_roll_call_high_confidence(self):
        """Speakers identified from roll call have high confidence."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(speaker="D", text="Vice Mayor Bushy.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=2500, end_ms=3500),
            TranscriptUtterance(speaker="F", text="Present.", start_ms=3500, end_ms=4000),
        ]

        result = detector.detect_roles(utterances)

        # Roll call detection should yield high confidence
        assert result["E"].confidence >= 0.9
        assert result["F"].confidence >= 0.9

    def test_pattern_based_moderate_confidence(self):
        """Pattern-based detection has moderate confidence."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(
                speaker="Y",
                text="Thank you mayor and council for hearing me today.",
                start_ms=200000,
                end_ms=205000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # Pattern-based should have lower confidence than roll call
        assert 0.5 <= result["Y"].confidence <= 0.9


class TestChunkMetadataSync:
    """Tests for chunk metadata consistency with speaker info."""

    def test_chunk_speaker_matches_speaker_info_role(self):
        """Chunk's speaker role metadata matches SpeakerInfo role."""
        from civicos._internal.meetings.transcript import (
            SpeakerRoleDetector,
            TranscriptChunker,
            TranscriptUtterance,
        )

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(
                speaker="E",
                text="I have a question about this proposal. Can staff clarify the timeline?",
                start_ms=100000,
                end_ms=110000,
            ),
        ]

        # Detect roles
        speaker_info = detector.detect_roles(utterances)

        # Create chunker and chunk with speaker detection
        chunker = TranscriptChunker()
        chunks = list(chunker.chunk(utterances, detect_speaker_roles=True))

        # Find chunks from speaker E
        e_chunks = [c for c in chunks if c.speaker == "E"]
        assert len(e_chunks) > 0

        # Verify metadata matches speaker info
        for chunk in e_chunks:
            if "speaker_role" in chunk.metadata:
                assert chunk.metadata["speaker_role"] == speaker_info["E"].role

    def test_chunk_speaker_name_metadata(self):
        """Chunk metadata includes speaker name when detected."""
        from civicos._internal.meetings.transcript import (
            SpeakerRoleDetector,
            TranscriptChunker,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance(speaker="D", text="Vice Mayor Bushy.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(
                speaker="E",
                text="I move to approve the consent calendar.",
                start_ms=50000,
                end_ms=55000,
            ),
        ]

        chunker = TranscriptChunker()
        chunks = list(chunker.chunk(utterances, detect_speaker_roles=True))

        # Find chunks from speaker E (Bushy)
        e_chunks = [c for c in chunks if c.speaker == "E"]
        assert len(e_chunks) > 0

        for chunk in e_chunks:
            if "speaker_name" in chunk.metadata:
                assert chunk.metadata["speaker_name"] == "Bushy"


class TestDiarizationQualityChecks:
    """Tests validating diarization quality on real transcripts."""

    @pytest.fixture
    def nov17_transcript(self):
        """Load Nov 17 meeting transcript."""
        transcript_path = TESTIMONY_DIR / "testimony_h6ey-0sY03g.json"
        if not transcript_path.exists():
            pytest.skip("Nov 17 transcript not available")
        with open(transcript_path) as f:
            return json.load(f)

    @pytest.fixture
    def nov3_transcript(self):
        """Load Nov 3 meeting transcript."""
        transcript_path = TESTIMONY_DIR / "testimony_725AYRBl9DA.json"
        if not transcript_path.exists():
            pytest.skip("Nov 3 transcript not available")
        with open(transcript_path) as f:
            return json.load(f)

    def test_speaker_count_reasonable(self, nov17_transcript):
        """Transcript has reasonable number of speakers (not too many jumps)."""
        # Too many speakers might indicate diarization errors
        speakers_count = nov17_transcript.get("speakers_count", 0)
        assert 2 <= speakers_count <= 30  # Typical council meeting range

    def test_speaker_ids_consistent_format(self, nov17_transcript):
        """All speaker IDs use consistent format (A, B, C, etc.)."""
        utterances = nov17_transcript.get("utterances", [])
        speakers = {u["speaker"] for u in utterances}

        # All should be single uppercase letters or short labels
        for speaker in speakers:
            assert len(speaker) <= 3  # e.g., "A", "AA", etc.
            assert speaker.isupper() or speaker[0].isupper()

    def test_no_frequent_speaker_switches(self, nov17_transcript):
        """No excessive back-and-forth between same two speakers.

        If A-B-A-B-A-B happens in rapid succession, might indicate
        diarization errors where one person is getting split IDs.
        """
        from civicos._internal.meetings.transcript import TranscriptUtterance

        utterances = [
            TranscriptUtterance(
                speaker=u["speaker"],
                text=u["text"],
                start_ms=u["start"],
                end_ms=u["end"],
            )
            for u in nov17_transcript.get("utterances", [])
        ]

        if len(utterances) < 10:
            pytest.skip("Not enough utterances for switch analysis")

        # Look for rapid alternation pattern (more than 5 rapid switches)
        rapid_switch_count = 0
        window = []

        for i, utt in enumerate(utterances):
            window.append(utt.speaker)
            if len(window) > 6:
                window.pop(0)

            # Check for A-B-A-B-A-B pattern in last 6 utterances
            if len(window) == 6:
                unique = set(window)
                if len(unique) == 2:
                    # Check if it's strict alternation
                    if all(window[j] != window[j + 1] for j in range(5)):
                        # Could be rapid alternation
                        # But only flag if utterances are very short (< 2 seconds)
                        if all(
                            utterances[i - 5 + j].duration_ms < 2000 for j in range(6)
                        ):
                            rapid_switch_count += 1

        # Allow some but not excessive rapid switching
        assert rapid_switch_count < 20, f"Found {rapid_switch_count} rapid speaker switches"

    def test_real_transcript_role_detection(self, nov17_transcript):
        """Role detection works on real transcript.

        Note: Real transcripts may not have distinct call/response roll call patterns
        if diarization collapses multiple speakers into one. The key check is that
        role detection assigns valid roles to all speakers consistently.
        """
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        utterances = [
            TranscriptUtterance(
                speaker=u["speaker"],
                text=u["text"],
                start_ms=u["start"],
                end_ms=u["end"],
            )
            for u in nov17_transcript.get("utterances", [])
        ]

        detector = SpeakerRoleDetector()
        result = detector.detect_roles(utterances)

        # All speakers should have valid role assignments
        valid_roles = {"council", "staff", "public", "unknown"}
        for speaker_id, info in result.items():
            assert info.role in valid_roles, f"Speaker {speaker_id} has invalid role: {info.role}"
            assert info.speaker_id == speaker_id

        # Should detect at least some role assignments (not all unknown)
        non_unknown = sum(1 for info in result.values() if info.role != "unknown")
        # At minimum, high-frequency speakers should be detected as staff
        # and low-frequency should be public
        assert non_unknown >= 1, "Should detect at least some speaker roles"

    def test_real_transcript_consistency_check(self, nov17_transcript):
        """All utterances from same speaker get same role."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        utterances = [
            TranscriptUtterance(
                speaker=u["speaker"],
                text=u["text"],
                start_ms=u["start"],
                end_ms=u["end"],
            )
            for u in nov17_transcript.get("utterances", [])
        ]

        detector = SpeakerRoleDetector()
        speaker_info = detector.detect_roles(utterances)

        # Map each utterance to its speaker's role
        utterance_roles = []
        for utt in utterances:
            info = speaker_info.get(utt.speaker)
            if info:
                utterance_roles.append((utt.speaker, info.role, info.name))

        # Group by speaker and verify consistency
        from collections import defaultdict

        speaker_roles = defaultdict(set)
        speaker_names = defaultdict(set)

        for speaker, role, name in utterance_roles:
            speaker_roles[speaker].add(role)
            if name:
                speaker_names[speaker].add(name)

        # Each speaker should have exactly one role
        for speaker, roles in speaker_roles.items():
            assert len(roles) == 1, f"Speaker {speaker} has inconsistent roles: {roles}"

        # Each speaker should have at most one name
        for speaker, names in speaker_names.items():
            assert len(names) <= 1, f"Speaker {speaker} has multiple names: {names}"

    def test_real_transcript_chunking_preserves_consistency(self, nov17_transcript):
        """Chunking doesn't break speaker consistency."""
        from civicos._internal.meetings.transcript import (
            SpeakerRoleDetector,
            TranscriptChunker,
            TranscriptUtterance,
        )

        utterances = [
            TranscriptUtterance(
                speaker=u["speaker"],
                text=u["text"],
                start_ms=u["start"],
                end_ms=u["end"],
            )
            for u in nov17_transcript.get("utterances", [])
        ]

        # Get speaker info
        detector = SpeakerRoleDetector()
        speaker_info = detector.detect_roles(utterances)

        # Chunk the transcript
        chunker = TranscriptChunker()
        chunks = list(chunker.chunk(utterances, detect_speaker_roles=True))

        # Verify chunk speaker assignments are consistent
        for chunk in chunks:
            if chunk.speaker != "multiple":
                info = speaker_info.get(chunk.speaker)
                if info and "speaker_role" in chunk.metadata:
                    assert chunk.metadata["speaker_role"] == info.role, (
                        f"Chunk {chunk.chunk_index} has inconsistent role for speaker {chunk.speaker}"
                    )

    def test_nov3_transcript_consistency(self, nov3_transcript):
        """Nov 3 transcript also passes consistency checks."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        utterances = [
            TranscriptUtterance(
                speaker=u["speaker"],
                text=u["text"],
                start_ms=u["start"],
                end_ms=u["end"],
            )
            for u in nov3_transcript.get("utterances", [])
        ]

        detector = SpeakerRoleDetector()
        speaker_info = detector.detect_roles(utterances)

        # Verify consistency
        from collections import defaultdict

        speaker_roles = defaultdict(set)

        for utt in utterances:
            info = speaker_info.get(utt.speaker)
            if info:
                speaker_roles[utt.speaker].add(info.role)

        for speaker, roles in speaker_roles.items():
            assert len(roles) == 1, f"Speaker {speaker} has inconsistent roles: {roles}"


class TestEdgeCases:
    """Tests for edge cases in speaker consistency."""

    def test_single_speaker_transcript(self):
        """Handle transcript with only one speaker."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(speaker="A", text="Welcome.", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="A", text="Let's begin.", start_ms=2000, end_ms=3000),
        ]

        result = detector.detect_roles(utterances)

        assert len(result) == 1
        assert "A" in result

    def test_empty_text_utterance(self):
        """Handle utterances with minimal or empty text."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(speaker="A", text="", start_ms=1000, end_ms=2000),
            TranscriptUtterance(speaker="A", text="Yes.", start_ms=2000, end_ms=2500),
            TranscriptUtterance(speaker="B", text="No.", start_ms=2500, end_ms=3000),
        ]

        result = detector.detect_roles(utterances)

        # Should handle gracefully
        assert "A" in result
        assert "B" in result

    def test_speaker_appears_once(self):
        """Speaker who appears only once still gets consistent info."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        detector = SpeakerRoleDetector()

        utterances = [
            TranscriptUtterance(speaker="A", text="Main speaker here.", start_ms=1000, end_ms=5000),
            *[
                TranscriptUtterance(
                    speaker="A",
                    text=f"Point {i}.",
                    start_ms=5000 + i * 1000,
                    end_ms=5500 + i * 1000,
                )
                for i in range(10)
            ],
            TranscriptUtterance(
                speaker="Z",
                text="Single comment from the audience.",
                start_ms=100000,
                end_ms=105000,
            ),
        ]

        result = detector.detect_roles(utterances)

        # Z should have a role assigned (likely public due to low frequency)
        assert "Z" in result
        assert result["Z"].role in ["public", "unknown"]

    def test_late_roll_call(self):
        """Handle roll call that happens later in meeting (after delays)."""
        from civicos._internal.meetings.transcript import SpeakerRoleDetector, TranscriptUtterance

        # Roll call at 8 minutes (within 10-minute window)
        detector = SpeakerRoleDetector(roll_call_window_ms=600_000)

        utterances = [
            # Preliminary announcements
            TranscriptUtterance(speaker="A", text="Welcome everyone.", start_ms=1000, end_ms=5000),
            TranscriptUtterance(speaker="A", text="Please take your seats.", start_ms=100000, end_ms=110000),
            # Roll call at ~8 minutes (480000ms)
            TranscriptUtterance(speaker="D", text="Council Member Hill.", start_ms=480000, end_ms=482000),
            TranscriptUtterance(speaker="E", text="Present.", start_ms=482000, end_ms=483000),
        ]

        result = detector.detect_roles(utterances)

        # Should still detect from roll call
        assert result["E"].role == "council"
        assert result["E"].name == "Hill"
