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
