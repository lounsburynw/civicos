"""
Tests for transcript duration validation (SESSION 496).

Validates that transcripts don't exceed YouTube video duration,
detecting corrupted audio downloads (playlist/concatenation bugs).
"""

import pytest
from unittest.mock import patch, MagicMock
import sys

# Add src to path for imports
sys.path.insert(0, "packages/civic-extraction/src")

from civicos_extraction.cli.transcribe import (
    validate_transcript_duration,
    get_youtube_video_duration,
    DURATION_TOLERANCE_PERCENT,
    MIN_DURATION_FOR_VALIDATION,
)


class TestValidateTranscriptDuration:
    """Tests for validate_transcript_duration function."""

    def test_valid_duration_within_tolerance(self):
        """Duration within 10% tolerance should be valid."""
        youtube_duration = 3600  # 1 hour
        assemblyai_duration = 3700  # 1 hour + 100 seconds (2.8% over)

        is_valid, error, _ = validate_transcript_duration(
            "test_video", assemblyai_duration, youtube_duration
        )

        assert is_valid is True
        assert error is None

    def test_invalid_duration_exceeds_tolerance(self):
        """Duration exceeding 10% tolerance should be invalid."""
        youtube_duration = 3600  # 1 hour
        assemblyai_duration = 5000  # ~1.4 hours (38.9% over)

        is_valid, error, _ = validate_transcript_duration(
            "test_video", assemblyai_duration, youtube_duration
        )

        assert is_valid is False
        assert error is not None
        assert "exceeds" in error
        assert "corrupted audio" in error.lower()

    def test_skip_validation_for_short_clips(self):
        """Clips under 60 seconds should skip validation."""
        youtube_duration = 30
        assemblyai_duration = 50  # Much longer, but clip is short

        is_valid, error, _ = validate_transcript_duration(
            "test_video", assemblyai_duration, youtube_duration
        )

        # Should pass because validation is skipped for short clips
        assert is_valid is True
        assert error is None

    def test_no_youtube_duration_returns_valid(self):
        """Missing YouTube duration should return valid (can't validate)."""
        assemblyai_duration = 10000

        is_valid, error, returned_duration = validate_transcript_duration(
            "test_video", assemblyai_duration, None
        )

        assert is_valid is True
        assert error is None
        assert returned_duration is None

    def test_exact_match_duration(self):
        """Exact match should be valid."""
        youtube_duration = 3600
        assemblyai_duration = 3600

        is_valid, error, _ = validate_transcript_duration(
            "test_video", assemblyai_duration, youtube_duration
        )

        assert is_valid is True
        assert error is None

    def test_tolerance_boundary_valid(self):
        """Duration exactly at tolerance boundary should be valid."""
        youtube_duration = 1000
        # 10% tolerance = 1100 max
        assemblyai_duration = 1099  # Just under 10%

        is_valid, error, _ = validate_transcript_duration(
            "test_video", assemblyai_duration, youtube_duration
        )

        assert is_valid is True
        assert error is None

    def test_tolerance_boundary_invalid(self):
        """Duration just over tolerance boundary should be invalid."""
        youtube_duration = 1000
        # 10% tolerance = 1100 max
        assemblyai_duration = 1101  # Just over 10%

        is_valid, error, _ = validate_transcript_duration(
            "test_video", assemblyai_duration, youtube_duration
        )

        assert is_valid is False
        assert error is not None


class TestGetYouTubeDuration:
    """Tests for get_youtube_video_duration function."""

    def test_no_api_key_returns_none(self):
        """Missing API key should return None gracefully."""
        # Clear env vars and test that function handles missing keys
        import os
        old_google = os.environ.pop("GOOGLE_API_KEY", None)
        old_youtube = os.environ.pop("YOUTUBE_API_KEY", None)
        try:
            # Function should return None without crashing
            result = get_youtube_video_duration("test_video")
            # Result is None because no API key
            assert result is None
        finally:
            # Restore env vars
            if old_google:
                os.environ["GOOGLE_API_KEY"] = old_google
            if old_youtube:
                os.environ["YOUTUBE_API_KEY"] = old_youtube

    def test_invalid_video_id_returns_none(self):
        """Invalid/nonexistent video ID should return None."""
        import os
        from dotenv import load_dotenv

        load_dotenv()
        key = os.getenv("GOOGLE_API_KEY") or os.getenv("YOUTUBE_API_KEY")
        if not key:
            pytest.skip("YouTube API key not available")

        # Test with an obviously invalid video ID
        result = get_youtube_video_duration("INVALID_VIDEO_12345")
        assert result is None


class TestKnownMismatchedTranscripts:
    """
    Integration tests using known mismatched transcripts from Session 480.

    These tests require GOOGLE_API_KEY to fetch real YouTube durations.
    Skip if API key not available.
    """

    @pytest.fixture
    def api_key_available(self):
        """Check if YouTube API key is available."""
        import os
        from dotenv import load_dotenv

        load_dotenv()
        key = os.getenv("GOOGLE_API_KEY") or os.getenv("YOUTUBE_API_KEY")
        if not key:
            pytest.skip("YouTube API key not available")
        return True

    def test_qldoo6ovmsa_is_invalid(self, api_key_available):
        """QLDoO6OvMSA: Stored 153 min vs actual 53 min - should fail."""
        stored_duration = 9196  # 153.3 minutes from database
        is_valid, error, youtube_duration = validate_transcript_duration(
            "QLDoO6OvMSA", stored_duration
        )

        assert is_valid is False
        assert error is not None
        # YouTube video should be around 53 minutes (3188 seconds)
        assert youtube_duration is not None
        assert youtube_duration < stored_duration / 2  # Less than half the stored

    def test_iyeihdimgxe_is_invalid(self, api_key_available):
        """iYeihDimgxE: Stored 169 min vs actual 47 min - should fail."""
        stored_duration = 10159  # 169.3 minutes from database
        is_valid, error, youtube_duration = validate_transcript_duration(
            "iYeihDimgxE", stored_duration
        )

        assert is_valid is False
        assert error is not None
        # YouTube video should be around 47 minutes (2863 seconds)
        assert youtube_duration is not None
        assert youtube_duration < stored_duration / 2


class TestExtractCaptions:
    """Tests for YouTube caption extraction as a transcription mode."""

    def _make_snippet(self, text, start, duration):
        """Create a mock caption snippet."""
        snippet = MagicMock()
        snippet.text = text
        snippet.start = start
        snippet.duration = duration
        return snippet

    def _make_fetched(self, snippets):
        """Create a mock fetched transcript result."""
        result = MagicMock()
        result.snippets = snippets
        return result

    @patch("civicos_extraction.cli.transcribe.transcript_exists_in_cloud")
    @patch("civicos.storage.get_storage_backend")
    @patch("youtube_transcript_api.YouTubeTranscriptApi")
    def test_extract_captions_basic(self, mock_api_cls, mock_get_backend, mock_exists):
        """Caption extraction fetches captions and stores with correct schema."""
        from civicos_extraction.cli.transcribe import extract_captions

        # Mock backend
        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_videos.return_value = [
            {"video_id": "abc123", "title": "City Council Meeting"},
        ]
        mock_backend.store_transcripts.return_value = 1
        mock_get_backend.return_value = mock_backend
        mock_exists.return_value = False  # Not already transcribed

        # Mock YouTube API
        snippets = [
            self._make_snippet("Good evening everyone.", 0.5, 2.0),
            self._make_snippet("Let us begin the meeting.", 3.0, 2.5),
            self._make_snippet("First item on the agenda.", 6.0, 2.0),
        ]
        mock_api = MagicMock()
        mock_api.fetch.return_value = self._make_fetched(snippets)
        mock_api_cls.return_value = mock_api

        results = extract_captions(jurisdiction_id="city-test")

        assert len(results) == 1
        assert results[0].status == "success"
        assert results[0].video_id == "abc123"
        assert results[0].speakers_count == 0
        assert results[0].cost_usd == 0.0

        # Verify transcript stored with correct schema
        call_args = mock_backend.store_transcripts.call_args
        stored = call_args[0][1][0]  # First transcript in list
        assert stored["video_id"] == "abc123"
        assert stored["processing_service"] == "youtube_captions"
        assert stored["cost_usd"] == 0.0
        assert stored["speakers_count"] == 0
        assert stored["utterances"] == []
        assert "Good evening everyone." in stored["text"]
        assert "Let us begin the meeting." in stored["text"]
        assert stored["word_count"] > 0

    @patch("civicos_extraction.cli.transcribe.transcript_exists_in_cloud")
    @patch("civicos.storage.get_storage_backend")
    @patch("youtube_transcript_api.YouTubeTranscriptApi")
    def test_extract_captions_skips_existing(self, mock_api_cls, mock_get_backend, mock_exists):
        """Videos with existing transcripts are skipped."""
        from civicos_extraction.cli.transcribe import extract_captions

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_videos.return_value = [
            {"video_id": "existing1", "title": "Already Done"},
            {"video_id": "new1", "title": "New Meeting"},
        ]
        mock_backend.store_transcripts.return_value = 1
        mock_get_backend.return_value = mock_backend

        # First video exists, second doesn't
        mock_exists.side_effect = lambda vid: vid == "existing1"

        snippets = [self._make_snippet("Hello world.", 0.0, 1.5)]
        mock_api = MagicMock()
        mock_api.fetch.return_value = self._make_fetched(snippets)
        mock_api_cls.return_value = mock_api

        results = extract_captions(jurisdiction_id="city-test")

        assert len(results) == 1
        assert results[0].video_id == "new1"
        assert results[0].status == "success"

    @patch("civicos_extraction.cli.transcribe.transcript_exists_in_cloud")
    @patch("civicos.storage.get_storage_backend")
    @patch("youtube_transcript_api.YouTubeTranscriptApi")
    def test_extract_captions_handles_unavailable(self, mock_api_cls, mock_get_backend, mock_exists):
        """Videos without captions produce error results, don't crash."""
        from civicos_extraction.cli.transcribe import extract_captions

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_videos.return_value = [
            {"video_id": "nocaps", "title": "No Captions Available"},
        ]
        mock_get_backend.return_value = mock_backend
        mock_exists.return_value = False

        mock_api = MagicMock()
        mock_api.fetch.side_effect = Exception("No transcripts available")
        mock_api_cls.return_value = mock_api

        results = extract_captions(jurisdiction_id="city-test")

        assert len(results) == 1
        assert results[0].status == "error"
        assert results[0].video_id == "nocaps"
        assert "No transcripts available" in results[0].error

    @patch("civicos_extraction.cli.transcribe.transcript_exists_in_cloud")
    @patch("civicos.storage.get_storage_backend")
    def test_extract_captions_dry_run(self, mock_get_backend, mock_exists):
        """Dry run shows videos without processing."""
        from civicos_extraction.cli.transcribe import extract_captions

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_videos.return_value = [
            {"video_id": "vid1", "title": "Meeting 1"},
        ]
        mock_get_backend.return_value = mock_backend
        mock_exists.return_value = False

        results = extract_captions(jurisdiction_id="city-test", dry_run=True)

        assert results == []
        mock_backend.store_transcripts.assert_not_called()

    @patch("civicos_extraction.cli.transcribe.transcript_exists_in_cloud")
    @patch("civicos.storage.get_storage_backend")
    @patch("youtube_transcript_api.YouTubeTranscriptApi")
    def test_extract_captions_duration_from_timestamps(self, mock_api_cls, mock_get_backend, mock_exists):
        """Duration is estimated from the last caption's timestamp."""
        from civicos_extraction.cli.transcribe import extract_captions

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_videos.return_value = [
            {"video_id": "dur1", "title": "Duration Test"},
        ]
        mock_backend.store_transcripts.return_value = 1
        mock_get_backend.return_value = mock_backend
        mock_exists.return_value = False

        snippets = [
            self._make_snippet("Start of meeting.", 0.0, 2.0),
            self._make_snippet("End of meeting.", 7200.0, 3.0),  # 2 hours in
        ]
        mock_api = MagicMock()
        mock_api.fetch.return_value = self._make_fetched(snippets)
        mock_api_cls.return_value = mock_api

        results = extract_captions(jurisdiction_id="city-test")

        assert len(results) == 1
        assert results[0].status == "success"
        # Duration should be approximately 7203 seconds (7200 + 3)
        assert results[0].duration_minutes is not None
        assert results[0].duration_minutes == pytest.approx(7203 / 60.0, abs=1)

    @patch("civicos_extraction.cli.transcribe.transcript_exists_in_cloud")
    @patch("civicos.storage.get_storage_backend")
    @patch("youtube_transcript_api.YouTubeTranscriptApi")
    def test_extract_captions_respects_limit(self, mock_api_cls, mock_get_backend, mock_exists):
        """Limit parameter restricts number of videos processed."""
        from civicos_extraction.cli.transcribe import extract_captions

        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_videos.return_value = [
            {"video_id": f"vid{i}", "title": f"Meeting {i}"}
            for i in range(10)
        ]
        mock_backend.store_transcripts.return_value = 1
        mock_get_backend.return_value = mock_backend
        mock_exists.return_value = False

        snippets = [self._make_snippet("Hello.", 0.0, 1.0)]
        mock_api = MagicMock()
        mock_api.fetch.return_value = self._make_fetched(snippets)
        mock_api_cls.return_value = mock_api

        results = extract_captions(jurisdiction_id="city-test", limit=3)

        assert len(results) == 3
        assert mock_api.fetch.call_count == 3
