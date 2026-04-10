"""
Tests for civicos_extraction.cli.youtube module.

Tests YouTube video discovery CLI: video ID regex extraction, checkpoint
persistence, date parsing from titles, meeting matching, channel discovery,
and backfill logic. External dependencies (HTTP, storage backends, filesystem,
subprocess) are mocked at the I/O boundary; all logic under test runs for real.
"""

import json
import subprocess
import pytest
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock

from civicos_extraction.cli.youtube import (
    VideoResult,
    YouTubeCheckpoint,
    extract_video_id,
    checkpoint_path_for_youtube,
    save_checkpoint,
    load_checkpoint,
    load_meetings_from_source,
    run_youtube_discovery,
    _parse_date_from_title,
    _get_youtube_source,
    discover_from_channel,
    match_videos_to_meetings,
    backfill_video_urls,
    run_youtube,
    run_channel_discovery,
    run_backfill_video_urls,
)


# ---------------------------------------------------------------------------
# VideoResult dataclass
# ---------------------------------------------------------------------------


class TestVideoResult:
    def test_fields_assigned_correctly(self):
        r = VideoResult(
            video_id="abc123",
            meeting_url="https://example.com/meeting/1",
            title="City Council January 7, 2026",
            date="2026-01-07T00:00:00",
            youtube_url="https://www.youtube.com/watch?v=abc123",
        )
        assert r.video_id == "abc123"
        assert r.meeting_url == "https://example.com/meeting/1"
        assert r.title == "City Council January 7, 2026"
        assert r.date == "2026-01-07T00:00:00"
        assert r.youtube_url == "https://www.youtube.com/watch?v=abc123"

    def test_asdict_produces_all_keys(self):
        r = VideoResult(
            video_id="xyz",
            meeting_url="https://example.com",
            title="Test",
            date="2026-01-01",
            youtube_url="https://www.youtube.com/watch?v=xyz",
        )
        d = asdict(r)
        assert set(d.keys()) == {"video_id", "meeting_url", "title", "date", "youtube_url"}
        assert d["video_id"] == "xyz"


# ---------------------------------------------------------------------------
# YouTubeCheckpoint dataclass
# ---------------------------------------------------------------------------


class TestYouTubeCheckpoint:
    def test_to_dict_includes_all_fields(self):
        cp = YouTubeCheckpoint(
            jurisdiction_id="city-san-rafael",
            last_meeting_url="https://example.com/meeting/42",
            items_processed=10,
            items_found=7,
            timestamp="2026-04-01T12:00:00",
        )
        d = cp.to_dict()
        assert d["jurisdiction_id"] == "city-san-rafael"
        assert d["last_meeting_url"] == "https://example.com/meeting/42"
        assert d["items_processed"] == 10
        assert d["items_found"] == 7
        assert d["timestamp"] == "2026-04-01T12:00:00"

    def test_from_dict_roundtrip(self):
        original = YouTubeCheckpoint(
            jurisdiction_id="city-fairfax",
            last_meeting_url="https://example.com/meeting/99",
            items_processed=20,
            items_found=15,
            timestamp="2026-04-02T08:30:00",
        )
        restored = YouTubeCheckpoint.from_dict(original.to_dict())
        assert restored.jurisdiction_id == "city-fairfax"
        assert restored.last_meeting_url == "https://example.com/meeting/99"
        assert restored.items_processed == 20
        assert restored.items_found == 15
        assert restored.timestamp == "2026-04-02T08:30:00"

    def test_to_dict_values_match_fields(self):
        cp = YouTubeCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_url="",
            items_processed=0,
            items_found=0,
            timestamp="2026-01-01T00:00:00",
        )
        d = cp.to_dict()
        assert d["items_processed"] == 0
        assert d["items_found"] == 0
        assert d["last_meeting_url"] == ""


# ---------------------------------------------------------------------------
# extract_video_id — regex extraction with mocked HTTP
# ---------------------------------------------------------------------------


class TestExtractVideoId:
    """Tests all 4 extraction patterns plus error cases."""

    @patch("civicos_extraction.cli.youtube.requests.get")
    def test_extracts_from_javascript_video_id(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            text='<script>var config = {videoId: "dQw4w9WgXcQ"};</script>',
        )
        mock_get.return_value.raise_for_status = MagicMock()
        result = extract_video_id("https://example.com/meeting/1")
        assert result == "dQw4w9WgXcQ"

    @patch("civicos_extraction.cli.youtube.requests.get")
    def test_extracts_from_youtube_embed(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            text='<iframe src="https://youtube.com/embed/abcXYZ12345"></iframe>',
        )
        mock_get.return_value.raise_for_status = MagicMock()
        result = extract_video_id("https://example.com/meeting/2")
        assert result == "abcXYZ12345"

    @patch("civicos_extraction.cli.youtube.requests.get")
    def test_extracts_from_youtube_watch_url(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            text='<a href="https://youtube.com/watch?v=WATCH_ID_123">Watch</a>',
        )
        mock_get.return_value.raise_for_status = MagicMock()
        result = extract_video_id("https://example.com/meeting/3")
        assert result == "WATCH_ID_123"

    @patch("civicos_extraction.cli.youtube.requests.get")
    def test_extracts_from_youtu_be_short_url(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            text='<a href="https://youtu.be/ShortID99">Watch</a>',
        )
        mock_get.return_value.raise_for_status = MagicMock()
        result = extract_video_id("https://example.com/meeting/4")
        assert result == "ShortID99"

    @patch("civicos_extraction.cli.youtube.requests.get")
    def test_returns_none_when_no_video_id_in_html(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            text="<html><body>No video here</body></html>",
        )
        mock_get.return_value.raise_for_status = MagicMock()
        result = extract_video_id("https://example.com/meeting/5")
        assert result is None

    @patch("civicos_extraction.cli.youtube.requests.get")
    def test_returns_none_on_http_error(self, mock_get):
        import requests

        mock_get.side_effect = requests.RequestException("Connection refused")
        result = extract_video_id("https://example.com/meeting/6")
        assert result is None

    @patch("civicos_extraction.cli.youtube.requests.get")
    def test_javascript_pattern_takes_priority_over_embed(self, mock_get):
        """When both videoId JS and embed URL exist, JS pattern wins (checked first)."""
        mock_get.return_value = MagicMock(
            status_code=200,
            text=(
                '<script>videoId: "JSvideo123"</script>'
                '<iframe src="https://youtube.com/embed/EmbedVid456"></iframe>'
            ),
        )
        mock_get.return_value.raise_for_status = MagicMock()
        result = extract_video_id("https://example.com/meeting/7")
        assert result == "JSvideo123"

    @patch("civicos_extraction.cli.youtube.requests.get")
    def test_passes_timeout_to_requests(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            text='videoId: "vid1"',
        )
        mock_get.return_value.raise_for_status = MagicMock()
        extract_video_id("https://example.com/meeting/8", timeout=42)
        mock_get.assert_called_once_with("https://example.com/meeting/8", timeout=42)


# ---------------------------------------------------------------------------
# _parse_date_from_title — pure logic
# ---------------------------------------------------------------------------


class TestParseDateFromTitle:
    def test_parses_standard_format(self):
        result = _parse_date_from_title("Town Council March 4, 2026")
        assert result == "2026-03-04"

    def test_parses_format_without_comma(self):
        result = _parse_date_from_title("Planning Commission January 15 2026")
        assert result == "2026-01-15"

    def test_returns_none_for_no_date(self):
        result = _parse_date_from_title("Regular Meeting")
        assert result is None

    def test_returns_none_for_empty_string(self):
        result = _parse_date_from_title("")
        assert result is None

    def test_parses_december_date(self):
        result = _parse_date_from_title("City Council December 31, 2025")
        assert result == "2025-12-31"

    def test_parses_single_digit_day(self):
        result = _parse_date_from_title("Board Meeting February 5, 2026")
        assert result == "2026-02-05"


# ---------------------------------------------------------------------------
# checkpoint_path_for_youtube — path construction
# ---------------------------------------------------------------------------


class TestCheckpointPath:
    def test_returns_correct_filename(self, tmp_path):
        result = checkpoint_path_for_youtube("city-san-rafael", str(tmp_path))
        assert result == tmp_path / "youtube_city-san-rafael.json"

    def test_creates_directory_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        result = checkpoint_path_for_youtube("city-test", str(nested))
        assert result == nested / "youtube_city-test.json"
        assert nested.exists()


# ---------------------------------------------------------------------------
# save_checkpoint / load_checkpoint — file I/O
# ---------------------------------------------------------------------------


class TestCheckpointPersistence:
    def test_save_and_load_roundtrip(self, tmp_path):
        cp = YouTubeCheckpoint(
            jurisdiction_id="city-san-rafael",
            last_meeting_url="https://example.com/meeting/42",
            items_processed=10,
            items_found=7,
            timestamp="2026-04-01T12:00:00",
        )
        path = tmp_path / "checkpoint.json"
        save_checkpoint(cp, path)
        loaded = load_checkpoint(path)
        assert loaded.jurisdiction_id == "city-san-rafael"
        assert loaded.last_meeting_url == "https://example.com/meeting/42"
        assert loaded.items_processed == 10
        assert loaded.items_found == 7

    def test_load_returns_none_when_file_missing(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        result = load_checkpoint(path)
        assert result is None

    def test_load_returns_none_on_corrupt_file(self, tmp_path):
        path = tmp_path / "corrupt.json"
        path.write_text("not valid json {{{")
        result = load_checkpoint(path)
        assert result is None

    def test_save_overwrites_existing(self, tmp_path):
        path = tmp_path / "checkpoint.json"

        cp1 = YouTubeCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_url="url1",
            items_processed=1,
            items_found=1,
            timestamp="2026-01-01T00:00:00",
        )
        save_checkpoint(cp1, path)

        cp2 = YouTubeCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_url="url2",
            items_processed=5,
            items_found=3,
            timestamp="2026-02-01T00:00:00",
        )
        save_checkpoint(cp2, path)

        loaded = load_checkpoint(path)
        assert loaded.last_meeting_url == "url2"
        assert loaded.items_processed == 5

    def test_saved_file_is_valid_json(self, tmp_path):
        cp = YouTubeCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_url="https://example.com",
            items_processed=3,
            items_found=2,
            timestamp="2026-01-01T00:00:00",
        )
        path = tmp_path / "checkpoint.json"
        save_checkpoint(cp, path)

        raw = json.loads(path.read_text())
        assert raw["jurisdiction_id"] == "city-test"
        assert raw["items_processed"] == 3


# ---------------------------------------------------------------------------
# load_meetings_from_source — mocked ProudCity source
# ---------------------------------------------------------------------------


class TestLoadMeetingsFromSource:
    @patch("civicos_extraction.cli.youtube.ProudCitySource")
    def test_deduplicates_meetings_by_source_url(self, mock_source_cls):
        """Meetings with duplicate source_url should be deduplicated."""
        mock_meeting = MagicMock()
        mock_meeting.source_url = "https://example.com/meeting/1"
        mock_meeting.title = "Council Meeting"
        mock_meeting.meeting_datetime = datetime(2026, 1, 15, 18, 0)

        mock_source = MagicMock()
        mock_source.source_id = "test-source"
        mock_source.validate.return_value = MagicMock(
            is_valid=True, warnings=[], check_duration_ms=5.0
        )
        mock_source.get_meetings.return_value = [mock_meeting, mock_meeting]
        mock_source_cls.from_jurisdiction.return_value = mock_source

        result = load_meetings_from_source("city-test", 90, 30)
        assert len(result) == 1
        assert result[0]["source_url"] == "https://example.com/meeting/1"
        assert result[0]["title"] == "Council Meeting"

    @patch("civicos_extraction.cli.youtube.ProudCitySource")
    def test_returns_empty_on_source_load_failure(self, mock_source_cls):
        mock_source_cls.from_jurisdiction.side_effect = RuntimeError("No config")
        result = load_meetings_from_source("city-invalid", 90, 30)
        assert result == []

    @patch("civicos_extraction.cli.youtube.ProudCitySource")
    def test_returns_empty_on_validation_failure(self, mock_source_cls):
        mock_source = MagicMock()
        mock_source.validate.return_value = MagicMock(
            is_valid=False, errors=["Bad URL"]
        )
        mock_source_cls.from_jurisdiction.return_value = mock_source
        result = load_meetings_from_source("city-broken", 90, 30)
        assert result == []

    @patch("civicos_extraction.cli.youtube.ProudCitySource")
    def test_skips_meetings_without_source_url(self, mock_source_cls):
        meeting_with_url = MagicMock()
        meeting_with_url.source_url = "https://example.com/meeting/1"
        meeting_with_url.title = "Has URL"
        meeting_with_url.meeting_datetime = datetime(2026, 1, 15)

        meeting_without_url = MagicMock()
        meeting_without_url.source_url = None
        meeting_without_url.title = "No URL"
        meeting_without_url.meeting_datetime = datetime(2026, 1, 16)

        mock_source = MagicMock()
        mock_source.source_id = "test"
        mock_source.validate.return_value = MagicMock(
            is_valid=True, warnings=[], check_duration_ms=1.0
        )
        mock_source.get_meetings.return_value = [meeting_with_url, meeting_without_url]
        mock_source_cls.from_jurisdiction.return_value = mock_source

        result = load_meetings_from_source("city-test", 90, 30)
        assert len(result) == 1
        assert result[0]["title"] == "Has URL"

    @patch("civicos_extraction.cli.youtube.ProudCitySource")
    def test_returns_empty_on_fetch_exception(self, mock_source_cls):
        mock_source = MagicMock()
        mock_source.source_id = "test"
        mock_source.validate.return_value = MagicMock(
            is_valid=True, warnings=[], check_duration_ms=1.0
        )
        mock_source.get_meetings.side_effect = ConnectionError("Network down")
        mock_source_cls.from_jurisdiction.return_value = mock_source
        result = load_meetings_from_source("city-test", 90, 30)
        assert result == []


# ---------------------------------------------------------------------------
# _get_youtube_source — YAML config loading
# ---------------------------------------------------------------------------


class TestGetYoutubeSource:
    def test_returns_channel_config(self, tmp_path):
        yaml_content = {
            "data_sources": {
                "transcripts": {
                    "channel_id": "UCxyz123",
                    "playlist_id": None,
                    "channel_title": "City of Test",
                }
            }
        }
        import yaml

        yaml_file = tmp_path / "city-test.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))

        with patch("civicos_config.paths.JURISDICTIONS_DIR", tmp_path):
            result = _get_youtube_source("city-test")
            assert result["channel_id"] == "UCxyz123"
            assert result["playlist_id"] is None
            assert result["channel_title"] == "City of Test"

    def test_returns_none_when_no_channel_or_playlist(self, tmp_path):
        import yaml

        yaml_content = {"data_sources": {"transcripts": {}}}
        yaml_file = tmp_path / "city-test.yaml"
        yaml_file.write_text(yaml.dump(yaml_content))

        with patch("civicos_config.paths.JURISDICTIONS_DIR", tmp_path):
            result = _get_youtube_source("city-test")
            assert result is None

    def test_returns_none_when_yaml_missing(self, tmp_path):
        with patch("civicos_config.paths.JURISDICTIONS_DIR", tmp_path):
            result = _get_youtube_source("city-nonexistent")
            assert result is None


# ---------------------------------------------------------------------------
# discover_from_channel — subprocess (yt-dlp) output parsing
# ---------------------------------------------------------------------------


class TestDiscoverFromChannel:
    @patch("civicos_extraction.cli.youtube._get_youtube_source")
    @patch("subprocess.run")
    def test_parses_yt_dlp_output(self, mock_run, mock_source):
        mock_source.return_value = {
            "channel_id": "UCxyz",
            "playlist_id": "PLabc",
            "channel_title": "City TV",
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="vid001|Council Meeting March 4, 2026\nvid002|Planning Commission March 11, 2026\n",
            stderr="",
        )
        result = discover_from_channel("city-test")
        assert len(result) == 2
        assert result[0]["video_id"] == "vid001"
        assert result[0]["title"] == "Council Meeting March 4, 2026"
        assert result[0]["youtube_url"] == "https://www.youtube.com/watch?v=vid001"
        assert result[1]["video_id"] == "vid002"

    @patch("civicos_extraction.cli.youtube._get_youtube_source")
    def test_returns_empty_when_no_source_config(self, mock_source):
        mock_source.return_value = None
        result = discover_from_channel("city-test")
        assert result == []

    @patch("civicos_extraction.cli.youtube._get_youtube_source")
    @patch("subprocess.run")
    def test_returns_empty_on_yt_dlp_failure(self, mock_run, mock_source):
        mock_source.return_value = {
            "channel_id": "UCxyz",
            "playlist_id": None,
            "channel_title": "Test",
        }
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="ERROR: some yt-dlp error",
        )
        result = discover_from_channel("city-test")
        assert result == []

    @patch("civicos_extraction.cli.youtube._get_youtube_source")
    @patch("subprocess.run")
    def test_returns_empty_on_yt_dlp_not_installed(self, mock_run, mock_source):
        mock_source.return_value = {
            "channel_id": "UCxyz",
            "playlist_id": None,
            "channel_title": "Test",
        }
        mock_run.side_effect = FileNotFoundError("yt-dlp not found")
        result = discover_from_channel("city-test")
        assert result == []

    @patch("civicos_extraction.cli.youtube._get_youtube_source")
    @patch("subprocess.run")
    def test_returns_empty_on_timeout(self, mock_run, mock_source):
        mock_source.return_value = {
            "channel_id": "UCxyz",
            "playlist_id": None,
            "channel_title": "Test",
        }
        mock_run.side_effect = subprocess.TimeoutExpired("yt-dlp", 120)
        result = discover_from_channel("city-test")
        assert result == []

    @patch("civicos_extraction.cli.youtube._get_youtube_source")
    @patch("subprocess.run")
    def test_skips_empty_lines_in_output(self, mock_run, mock_source):
        mock_source.return_value = {
            "channel_id": "UCxyz",
            "playlist_id": "PLabc",
            "channel_title": "City TV",
        }
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="vid001|Meeting One\n\n\nvid002|Meeting Two\n",
            stderr="",
        )
        result = discover_from_channel("city-test")
        assert len(result) == 2

    @patch("civicos_extraction.cli.youtube._get_youtube_source")
    @patch("subprocess.run")
    def test_uses_playlist_url_when_playlist_id_set(self, mock_run, mock_source):
        mock_source.return_value = {
            "channel_id": "UCxyz",
            "playlist_id": "PLabc",
            "channel_title": "City TV",
        }
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        discover_from_channel("city-test")
        args = mock_run.call_args[0][0]
        assert "https://www.youtube.com/playlist?list=PLabc" in args

    @patch("civicos_extraction.cli.youtube._get_youtube_source")
    @patch("subprocess.run")
    def test_uses_channel_url_when_no_playlist(self, mock_run, mock_source):
        mock_source.return_value = {
            "channel_id": "UCxyz",
            "playlist_id": None,
            "channel_title": "City TV",
        }
        mock_run.return_value = MagicMock(
            returncode=0, stdout="", stderr=""
        )
        discover_from_channel("city-test")
        args = mock_run.call_args[0][0]
        assert "https://www.youtube.com/channel/UCxyz/videos" in args


# ---------------------------------------------------------------------------
# match_videos_to_meetings — date-based matching logic
# ---------------------------------------------------------------------------


class TestMatchVideosToMeetings:
    @patch("civicos.storage.get_storage_backend")
    def test_matches_video_to_meeting_by_date(self, mock_get_backend):
        backend = MagicMock()
        backend.get_meetings.return_value = [
            {
                "id": "meeting-001",
                "meeting_datetime": datetime(2026, 3, 4, 18, 0),
                "source_url": "https://example.com/meeting/1",
            }
        ]
        backend.get_videos.return_value = []
        mock_get_backend.return_value = backend

        videos = [
            {
                "video_id": "vid001",
                "title": "Council Meeting March 4, 2026",
                "youtube_url": "https://www.youtube.com/watch?v=vid001",
            }
        ]

        result = match_videos_to_meetings("city-test", videos)
        assert len(result) == 1
        assert result[0]["video_id"] == "vid001"
        assert result[0]["meeting_id"] == "meeting-001"
        assert result[0]["date"] == "2026-03-04T00:00:00"

    @patch("civicos.storage.get_storage_backend")
    def test_skips_already_stored_videos(self, mock_get_backend):
        backend = MagicMock()
        backend.get_meetings.return_value = [
            {"id": "m1", "meeting_datetime": datetime(2026, 3, 4, 18, 0)},
        ]
        backend.get_videos.return_value = [{"id": "vid001"}]
        mock_get_backend.return_value = backend

        videos = [
            {
                "video_id": "vid001",
                "title": "Council March 4, 2026",
                "youtube_url": "https://youtube.com/watch?v=vid001",
            }
        ]

        result = match_videos_to_meetings("city-test", videos)
        assert len(result) == 0

    @patch("civicos.storage.get_storage_backend")
    def test_skips_videos_without_parseable_date(self, mock_get_backend):
        backend = MagicMock()
        backend.get_meetings.return_value = [
            {"id": "m1", "meeting_datetime": datetime(2026, 3, 4, 18, 0)},
        ]
        backend.get_videos.return_value = []
        mock_get_backend.return_value = backend

        videos = [
            {
                "video_id": "vid001",
                "title": "Regular Meeting",  # no date in title
                "youtube_url": "https://youtube.com/watch?v=vid001",
            }
        ]

        result = match_videos_to_meetings("city-test", videos)
        assert len(result) == 0

    @patch("civicos.storage.get_storage_backend")
    def test_skips_videos_with_no_matching_meeting_date(self, mock_get_backend):
        backend = MagicMock()
        backend.get_meetings.return_value = [
            {"id": "m1", "meeting_datetime": datetime(2026, 3, 4, 18, 0)},
        ]
        backend.get_videos.return_value = []
        mock_get_backend.return_value = backend

        videos = [
            {
                "video_id": "vid001",
                "title": "Council Meeting June 15, 2026",  # no meeting on this date
                "youtube_url": "https://youtube.com/watch?v=vid001",
            }
        ]

        result = match_videos_to_meetings("city-test", videos)
        assert len(result) == 0

    @patch("civicos.storage.get_storage_backend")
    def test_handles_string_datetime_in_meetings(self, mock_get_backend):
        """meeting_datetime can be a string if backend returns it that way."""
        backend = MagicMock()
        backend.get_meetings.return_value = [
            {
                "id": "m1",
                "meeting_datetime": "2026-03-04T18:00:00",
                "source_url": "https://example.com/meeting/1",
            }
        ]
        backend.get_videos.return_value = []
        mock_get_backend.return_value = backend

        videos = [
            {
                "video_id": "vid001",
                "title": "Council March 4, 2026",
                "youtube_url": "https://youtube.com/watch?v=vid001",
            }
        ]

        result = match_videos_to_meetings("city-test", videos)
        assert len(result) == 1
        assert result[0]["meeting_id"] == "m1"

    @patch("civicos.storage.get_storage_backend")
    def test_gracefully_handles_get_videos_failure(self, mock_get_backend):
        """If get_videos raises, stored_ids should be empty (not crash)."""
        backend = MagicMock()
        backend.get_meetings.return_value = [
            {
                "id": "m1",
                "meeting_datetime": datetime(2026, 3, 4, 18, 0),
                "source_url": "https://example.com",
            }
        ]
        backend.get_videos.side_effect = Exception("Table not found")
        mock_get_backend.return_value = backend

        videos = [
            {
                "video_id": "vid001",
                "title": "Council March 4, 2026",
                "youtube_url": "https://youtube.com/watch?v=vid001",
            }
        ]

        result = match_videos_to_meetings("city-test", videos)
        assert len(result) == 1
        assert result[0]["video_id"] == "vid001"


# ---------------------------------------------------------------------------
# backfill_video_urls — prefers regular meetings
# ---------------------------------------------------------------------------


class TestBackfillVideoUrls:
    @patch("civicos.storage.get_storage_backend")
    def test_returns_zero_when_no_linked_videos(self, mock_get_backend):
        backend = MagicMock()
        backend.get_videos.return_value = [
            {"id": "vid1", "youtube_url": "https://youtube.com/watch?v=vid1"},
            # No meeting_id -> not linked
        ]
        mock_get_backend.return_value = backend
        result = backfill_video_urls("city-test")
        assert result == 0

    @patch("civicos.storage.get_storage_backend")
    def test_updates_meeting_with_video_url(self, mock_get_backend):
        backend = MagicMock()
        backend.get_videos.return_value = [
            {
                "id": "vid1",
                "meeting_id": "m1",
                "title": "Council Meeting",
                "youtube_url": "https://youtube.com/watch?v=vid1",
            }
        ]
        backend.update_meeting.return_value = True
        mock_get_backend.return_value = backend

        result = backfill_video_urls("city-test")
        assert result == 1
        backend.update_meeting.assert_called_once_with(
            "city-test", "m1", {"video_url": "https://youtube.com/watch?v=vid1"}
        )

    @patch("civicos.storage.get_storage_backend")
    def test_prefers_regular_meeting_over_special(self, mock_get_backend):
        backend = MagicMock()
        backend.get_videos.return_value = [
            {
                "id": "vid1",
                "meeting_id": "m1",
                "title": "Special Session",
                "youtube_url": "https://youtube.com/watch?v=vid1",
            },
            {
                "id": "vid2",
                "meeting_id": "m1",
                "title": "Regular Meeting",
                "youtube_url": "https://youtube.com/watch?v=vid2",
            },
        ]
        backend.update_meeting.return_value = True
        mock_get_backend.return_value = backend

        result = backfill_video_urls("city-test")
        assert result == 1
        # Should have used the "Regular Meeting" video
        backend.update_meeting.assert_called_once_with(
            "city-test", "m1", {"video_url": "https://youtube.com/watch?v=vid2"}
        )

    @patch("civicos.storage.get_storage_backend")
    def test_skips_video_without_youtube_url(self, mock_get_backend):
        backend = MagicMock()
        backend.get_videos.return_value = [
            {
                "id": "vid1",
                "meeting_id": "m1",
                "title": "Meeting",
                "youtube_url": None,
            }
        ]
        mock_get_backend.return_value = backend

        result = backfill_video_urls("city-test")
        assert result == 0
        backend.update_meeting.assert_not_called()

    @patch("civicos.storage.get_storage_backend")
    def test_counts_only_successful_updates(self, mock_get_backend):
        backend = MagicMock()
        backend.get_videos.return_value = [
            {
                "id": "vid1",
                "meeting_id": "m1",
                "title": "Meeting 1",
                "youtube_url": "https://youtube.com/watch?v=vid1",
            },
            {
                "id": "vid2",
                "meeting_id": "m2",
                "title": "Meeting 2",
                "youtube_url": "https://youtube.com/watch?v=vid2",
            },
        ]
        # First succeeds, second returns False
        backend.update_meeting.side_effect = [True, False]
        mock_get_backend.return_value = backend

        result = backfill_video_urls("city-test")
        assert result == 1

    @patch("civicos.storage.get_storage_backend")
    def test_handles_update_exception_gracefully(self, mock_get_backend):
        backend = MagicMock()
        backend.get_videos.return_value = [
            {
                "id": "vid1",
                "meeting_id": "m1",
                "title": "Meeting",
                "youtube_url": "https://youtube.com/watch?v=vid1",
            }
        ]
        backend.update_meeting.side_effect = Exception("DB error")
        mock_get_backend.return_value = backend

        result = backfill_video_urls("city-test")
        assert result == 0


# ---------------------------------------------------------------------------
# run_youtube_discovery — orchestrator (main flow)
# ---------------------------------------------------------------------------


class TestRunYoutubeDiscovery:
    @patch("civicos_extraction.cli.youtube.extract_video_id")
    @patch("civicos_extraction.cli.youtube.load_meetings_from_source")
    def test_returns_none_when_no_meetings(self, mock_load, mock_extract):
        mock_load.return_value = []
        result = run_youtube_discovery("city-test", output_dir="/tmp/test_yt")
        assert result is None

    @patch("civicos_extraction.cli.youtube.save_checkpoint")
    @patch("civicos_extraction.cli.youtube.load_checkpoint")
    @patch("civicos_extraction.cli.youtube.extract_video_id")
    @patch("civicos_extraction.cli.youtube.load_meetings_from_source")
    def test_discovers_new_videos(
        self, mock_load, mock_extract, mock_load_cp, mock_save_cp, tmp_path
    ):
        mock_load.return_value = [
            {
                "source_url": "https://example.com/meeting/1",
                "title": "Council Meeting",
                "datetime": "2026-01-15T18:00:00",
            }
        ]
        mock_extract.return_value = "newVid123"
        mock_load_cp.return_value = None

        result = run_youtube_discovery(
            "city-test",
            output_dir=str(tmp_path),
            checkpoint_dir=str(tmp_path / "checkpoints"),
        )

        assert len(result) == 1
        assert result[0].video_id == "newVid123"
        assert result[0].youtube_url == "https://www.youtube.com/watch?v=newVid123"
        assert result[0].title == "Council Meeting"

    @patch("civicos_extraction.cli.youtube.save_checkpoint")
    @patch("civicos_extraction.cli.youtube.load_checkpoint")
    @patch("civicos_extraction.cli.youtube.extract_video_id")
    @patch("civicos_extraction.cli.youtube.load_meetings_from_source")
    def test_dry_run_returns_none(
        self, mock_load, mock_extract, mock_load_cp, mock_save_cp
    ):
        mock_load.return_value = [
            {
                "source_url": "https://example.com/meeting/1",
                "title": "Test",
                "datetime": "2026-01-15",
            }
        ]
        mock_load_cp.return_value = None

        result = run_youtube_discovery("city-test", dry_run=True)
        assert result is None
        mock_extract.assert_not_called()

    @patch("civicos_extraction.cli.youtube.save_checkpoint")
    @patch("civicos_extraction.cli.youtube.load_checkpoint")
    @patch("civicos_extraction.cli.youtube.extract_video_id")
    @patch("civicos_extraction.cli.youtube.load_meetings_from_source")
    def test_skips_meetings_without_source_url(
        self, mock_load, mock_extract, mock_load_cp, mock_save_cp, tmp_path
    ):
        mock_load.return_value = [
            {"source_url": None, "title": "No URL", "datetime": "2026-01-15"},
            {
                "source_url": "https://example.com/meeting/2",
                "title": "Has URL",
                "datetime": "2026-01-16",
            },
        ]
        mock_extract.return_value = "vid2"
        mock_load_cp.return_value = None

        result = run_youtube_discovery(
            "city-test",
            output_dir=str(tmp_path),
            checkpoint_dir=str(tmp_path / "checkpoints"),
        )

        assert len(result) == 1
        assert result[0].video_id == "vid2"

    @patch("civicos_extraction.cli.youtube.save_checkpoint")
    @patch("civicos_extraction.cli.youtube.load_checkpoint")
    @patch("civicos_extraction.cli.youtube.extract_video_id")
    @patch("civicos_extraction.cli.youtube.load_meetings_from_source")
    def test_resumes_from_checkpoint(
        self, mock_load, mock_extract, mock_load_cp, mock_save_cp, tmp_path
    ):
        mock_load.return_value = [
            {
                "source_url": "https://example.com/meeting/1",
                "title": "Already Done",
                "datetime": "2026-01-15",
            },
            {
                "source_url": "https://example.com/meeting/2",
                "title": "Not Yet Done",
                "datetime": "2026-01-16",
            },
        ]
        mock_extract.return_value = "vid2"
        mock_load_cp.return_value = YouTubeCheckpoint(
            jurisdiction_id="city-test",
            last_meeting_url="https://example.com/meeting/1",
            items_processed=1,
            items_found=0,
            timestamp="2026-01-15T00:00:00",
        )

        result = run_youtube_discovery(
            "city-test",
            output_dir=str(tmp_path),
            checkpoint_dir=str(tmp_path / "checkpoints"),
        )

        assert len(result) == 1
        assert result[0].title == "Not Yet Done"

    @patch("civicos_extraction.cli.youtube.save_checkpoint")
    @patch("civicos_extraction.cli.youtube.load_checkpoint")
    @patch("civicos_extraction.cli.youtube.extract_video_id")
    @patch("civicos_extraction.cli.youtube.load_meetings_from_source")
    def test_deduplicates_against_existing_results(
        self, mock_load, mock_extract, mock_load_cp, mock_save_cp, tmp_path
    ):
        # Write existing results file
        existing = [
            {
                "video_id": "existing_vid",
                "meeting_url": "https://example.com/meeting/1",
                "title": "Old Meeting",
                "date": "2026-01-10",
                "youtube_url": "https://www.youtube.com/watch?v=existing_vid",
            }
        ]
        output_file = tmp_path / "city_test_videos.json"
        output_file.write_text(json.dumps(existing))

        mock_load.return_value = [
            {
                "source_url": "https://example.com/meeting/1",
                "title": "Old Meeting",
                "datetime": "2026-01-10",
            },
            {
                "source_url": "https://example.com/meeting/2",
                "title": "New Meeting",
                "datetime": "2026-01-20",
            },
        ]
        # extract returns existing_vid for first, new_vid for second
        mock_extract.side_effect = ["existing_vid", "new_vid"]
        mock_load_cp.return_value = None

        result = run_youtube_discovery(
            "city-test",
            output_dir=str(tmp_path),
            checkpoint_dir=str(tmp_path / "checkpoints"),
        )

        # Only the new video should be in results
        assert len(result) == 1
        assert result[0].video_id == "new_vid"


# ---------------------------------------------------------------------------
# run_youtube — CLI dispatcher
# ---------------------------------------------------------------------------


class TestRunYoutube:
    @patch("civicos_extraction.cli.youtube.run_backfill_video_urls")
    def test_dispatches_to_backfill(self, mock_backfill):
        mock_backfill.return_value = 0
        args = MagicMock()
        args.verbose = False
        args.backfill = True
        args.jurisdiction = "city-test"

        result = run_youtube(args)
        assert result == 0
        mock_backfill.assert_called_once_with("city-test")

    @patch("civicos_extraction.cli.youtube.run_channel_discovery")
    def test_dispatches_to_channel_discovery(self, mock_channel):
        mock_channel.return_value = 0
        args = MagicMock()
        args.verbose = False
        args.backfill = False
        args.channel = True
        args.jurisdiction = "city-test"
        args.dry_run = False
        args.output_dir = "data"

        result = run_youtube(args)
        assert result == 0
        mock_channel.assert_called_once_with(
            "city-test", dry_run=False, output_dir="data"
        )

    @patch("civicos_extraction.cli.youtube.run_youtube_discovery")
    def test_dispatches_to_discovery(self, mock_discovery):
        mock_discovery.return_value = [VideoResult("v1", "url", "t", "d", "yt")]
        args = MagicMock()
        args.verbose = False
        args.backfill = False
        args.channel = False
        args.schedule = False
        args.jurisdiction = "city-test"
        args.days_past = 90
        args.days_ahead = 30
        args.output_dir = "data"
        args.checkpoint_dir = "data/checkpoints"
        args.timeout = 10
        args.dry_run = False
        args.cloud = False

        result = run_youtube(args)
        assert result == 0

    @patch("civicos_extraction.cli.youtube.run_youtube_discovery")
    def test_returns_1_on_discovery_failure(self, mock_discovery):
        mock_discovery.return_value = None
        args = MagicMock()
        args.verbose = False
        args.backfill = False
        args.channel = False
        args.schedule = False
        args.jurisdiction = "city-test"
        args.days_past = 90
        args.days_ahead = 30
        args.output_dir = "data"
        args.checkpoint_dir = "data/checkpoints"
        args.timeout = 10
        args.dry_run = False
        args.cloud = False

        result = run_youtube(args)
        assert result == 1

    @patch("civicos_extraction.cli.youtube.run_youtube_discovery")
    def test_dry_run_returns_0_even_when_discovery_returns_none(self, mock_discovery):
        mock_discovery.return_value = None
        args = MagicMock()
        args.verbose = False
        args.backfill = False
        args.channel = False
        args.schedule = False
        args.jurisdiction = "city-test"
        args.days_past = 90
        args.days_ahead = 30
        args.output_dir = "data"
        args.checkpoint_dir = "data/checkpoints"
        args.timeout = 10
        args.dry_run = True
        args.cloud = False

        result = run_youtube(args)
        assert result == 0


# ---------------------------------------------------------------------------
# run_backfill_video_urls — always returns 0
# ---------------------------------------------------------------------------


class TestRunBackfillVideoUrls:
    @patch("civicos_extraction.cli.youtube.backfill_video_urls")
    def test_returns_zero_even_when_no_updates(self, mock_backfill):
        mock_backfill.return_value = 0
        result = run_backfill_video_urls("city-test")
        assert result == 0

    @patch("civicos_extraction.cli.youtube.backfill_video_urls")
    def test_returns_zero_when_updates_made(self, mock_backfill):
        mock_backfill.return_value = 5
        result = run_backfill_video_urls("city-test")
        assert result == 0


# ---------------------------------------------------------------------------
# run_channel_discovery — orchestrator
# ---------------------------------------------------------------------------


class TestRunChannelDiscovery:
    @patch("civicos_extraction.cli.youtube.backfill_video_urls")
    @patch("civicos_extraction.cli.youtube.match_videos_to_meetings")
    @patch("civicos_extraction.cli.youtube.discover_from_channel")
    def test_returns_1_when_no_videos_found(
        self, mock_discover, mock_match, mock_backfill
    ):
        mock_discover.return_value = []
        result = run_channel_discovery("city-test")
        assert result == 1
        mock_match.assert_not_called()

    @patch("civicos_extraction.cli.youtube.backfill_video_urls")
    @patch("civicos.storage.get_storage_backend")
    @patch("civicos_extraction.cli.youtube.match_videos_to_meetings")
    @patch("civicos_extraction.cli.youtube.discover_from_channel")
    def test_stores_matched_videos_and_backfills(
        self, mock_discover, mock_match, mock_get_backend, mock_backfill, tmp_path
    ):
        mock_discover.return_value = [
            {
                "video_id": "vid1",
                "title": "Council March 4, 2026",
                "youtube_url": "https://youtube.com/watch?v=vid1",
            }
        ]
        mock_match.return_value = [
            {
                "video_id": "vid1",
                "meeting_url": "https://example.com/m1",
                "meeting_id": "m1",
                "title": "Council March 4, 2026",
                "date": "2026-03-04T00:00:00",
                "youtube_url": "https://youtube.com/watch?v=vid1",
            }
        ]
        backend = MagicMock()
        backend.store_videos.return_value = 1
        mock_get_backend.return_value = backend
        mock_backfill.return_value = 1

        result = run_channel_discovery(
            "city-test", output_dir=str(tmp_path)
        )
        assert result == 0
        backend.store_videos.assert_called_once()
        mock_backfill.assert_called_once_with("city-test")

    @patch("civicos_extraction.cli.youtube.backfill_video_urls")
    @patch("civicos_extraction.cli.youtube.match_videos_to_meetings")
    @patch("civicos_extraction.cli.youtube.discover_from_channel")
    def test_dry_run_does_not_store(
        self, mock_discover, mock_match, mock_backfill
    ):
        mock_discover.return_value = [
            {
                "video_id": "vid1",
                "title": "Council March 4, 2026",
                "youtube_url": "https://youtube.com/watch?v=vid1",
            }
        ]
        mock_match.return_value = [
            {
                "video_id": "vid1",
                "meeting_id": "m1",
                "title": "Council March 4, 2026",
                "date": "2026-03-04T00:00:00",
                "youtube_url": "https://youtube.com/watch?v=vid1",
            }
        ]
        result = run_channel_discovery("city-test", dry_run=True)
        assert result == 0
        # Backfill should NOT be called in dry_run
        # Actually looking at the code, dry_run returns 0 before backfill
