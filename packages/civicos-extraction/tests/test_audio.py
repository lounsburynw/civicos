"""
Tests for civicos_extraction.cli.audio — audio download pipeline.

Tests the audio download logic: video loading, checkpoint management,
Granicus URL resolution, R2 key lookup, and download orchestration.
External I/O (HTTP, yt-dlp, filesystem, cloud storage) is mocked;
all logic under test runs for real.
"""

import argparse
import json
import os
import pytest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

from civicos_extraction.cli.audio import (
    AUDIO_CODEC,
    AUDIO_CONTENT_TYPE,
    AUDIO_EXT,
    AUDIO_QUALITY,
    AudioCheckpoint,
    DownloadResult,
    checkpoint_path_for_audio,
    download_audio,
    find_audio_r2_key,
    load_checkpoint,
    load_videos,
    run_audio,
    run_audio_download,
    save_checkpoint,
    _resolve_granicus_mp3_url,
    _resolve_granicus_player_url,
)


# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

class TestModuleConstants:
    def test_audio_codec_is_opus(self):
        assert AUDIO_CODEC == "opus"

    def test_audio_ext_is_opus(self):
        assert AUDIO_EXT == "opus"

    def test_audio_quality_is_48(self):
        assert AUDIO_QUALITY == "48"

    def test_audio_content_type_is_ogg(self):
        assert AUDIO_CONTENT_TYPE == "audio/ogg"


# ---------------------------------------------------------------------------
# DownloadResult dataclass
# ---------------------------------------------------------------------------

class TestDownloadResult:
    def test_success_result_has_all_fields(self):
        r = DownloadResult(
            video_id="abc123",
            status="success",
            file_path="/tmp/abc123.opus",
            file_size_mb=5.2,
            duration_minutes=45,
        )
        assert r.video_id == "abc123"
        assert r.status == "success"
        assert r.file_path == "/tmp/abc123.opus"
        assert r.file_size_mb == 5.2
        assert r.duration_minutes == 45
        assert r.error is None
        assert r.r2_key is None

    def test_error_result_carries_message(self):
        r = DownloadResult(video_id="bad", status="error", error="network timeout")
        assert r.status == "error"
        assert r.error == "network timeout"
        assert r.file_path is None

    def test_skipped_result_with_r2_key(self):
        r = DownloadResult(video_id="xyz", status="skipped", r2_key="audio/city-sr/xyz.opus")
        assert r.status == "skipped"
        assert r.r2_key == "audio/city-sr/xyz.opus"


# ---------------------------------------------------------------------------
# AudioCheckpoint dataclass
# ---------------------------------------------------------------------------

class TestAudioCheckpoint:
    def test_round_trip_to_dict_from_dict(self):
        cp = AudioCheckpoint(
            jurisdiction_id="city-san-rafael",
            last_video_id="vid_99",
            items_processed=10,
            items_downloaded=7,
            items_skipped=2,
            items_failed=1,
            timestamp="2026-04-09T12:00:00",
        )
        d = cp.to_dict()
        restored = AudioCheckpoint.from_dict(d)
        assert restored.jurisdiction_id == "city-san-rafael"
        assert restored.last_video_id == "vid_99"
        assert restored.items_processed == 10
        assert restored.items_downloaded == 7
        assert restored.items_skipped == 2
        assert restored.items_failed == 1
        assert restored.timestamp == "2026-04-09T12:00:00"

    def test_to_dict_keys_match_fields(self):
        cp = AudioCheckpoint(
            jurisdiction_id="j",
            last_video_id="v",
            items_processed=0,
            items_downloaded=0,
            items_skipped=0,
            items_failed=0,
            timestamp="t",
        )
        d = cp.to_dict()
        expected_keys = {
            "jurisdiction_id",
            "last_video_id",
            "items_processed",
            "items_downloaded",
            "items_skipped",
            "items_failed",
            "timestamp",
        }
        assert set(d.keys()) == expected_keys


# ---------------------------------------------------------------------------
# find_audio_r2_key
# ---------------------------------------------------------------------------

class TestFindAudioR2Key:
    def test_returns_opus_key_when_opus_exists(self):
        blob = MagicMock()
        blob.exists.side_effect = lambda k: k.endswith(".opus")
        key = find_audio_r2_key(blob, "city-sr", "vid1")
        assert key == "audio/city-sr/vid1.opus"

    def test_falls_back_to_mp3_when_opus_missing(self):
        blob = MagicMock()
        blob.exists.side_effect = lambda k: k.endswith(".mp3")
        key = find_audio_r2_key(blob, "city-sr", "vid1")
        assert key == "audio/city-sr/vid1.mp3"

    def test_returns_none_when_neither_format_exists(self):
        blob = MagicMock()
        blob.exists.return_value = False
        key = find_audio_r2_key(blob, "city-sr", "vid1")
        assert key is None

    def test_prefers_opus_over_mp3(self):
        """When both exist, opus is returned (checked first)."""
        blob = MagicMock()
        blob.exists.return_value = True
        key = find_audio_r2_key(blob, "city-sr", "vid1")
        assert key == "audio/city-sr/vid1.opus"


# ---------------------------------------------------------------------------
# checkpoint_path_for_audio
# ---------------------------------------------------------------------------

class TestCheckpointPath:
    def test_returns_expected_path(self, tmp_path):
        cp = checkpoint_path_for_audio("city-san-rafael", str(tmp_path / "ckpts"))
        assert cp == tmp_path / "ckpts" / "audio_city-san-rafael.json"

    def test_creates_directory(self, tmp_path):
        target = tmp_path / "new_dir"
        checkpoint_path_for_audio("city-x", str(target))
        assert target.is_dir()


# ---------------------------------------------------------------------------
# save_checkpoint / load_checkpoint
# ---------------------------------------------------------------------------

class TestCheckpointIO:
    def _make_checkpoint(self):
        return AudioCheckpoint(
            jurisdiction_id="city-sr",
            last_video_id="v42",
            items_processed=5,
            items_downloaded=3,
            items_skipped=1,
            items_failed=1,
            timestamp="2026-04-09T10:00:00",
        )

    def test_save_then_load_round_trips(self, tmp_path):
        cp = self._make_checkpoint()
        path = tmp_path / "cp.json"
        save_checkpoint(cp, path)
        loaded = load_checkpoint(path)
        assert loaded.jurisdiction_id == "city-sr"
        assert loaded.last_video_id == "v42"
        assert loaded.items_processed == 5
        assert loaded.items_downloaded == 3
        assert loaded.items_skipped == 1
        assert loaded.items_failed == 1

    def test_load_returns_none_for_missing_file(self, tmp_path):
        result = load_checkpoint(tmp_path / "nonexistent.json")
        assert result is None

    def test_load_returns_none_for_corrupt_file(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not valid json {{{")
        result = load_checkpoint(path)
        assert result is None

    def test_save_writes_valid_json(self, tmp_path):
        cp = self._make_checkpoint()
        path = tmp_path / "cp.json"
        save_checkpoint(cp, path)
        data = json.loads(path.read_text())
        assert data["jurisdiction_id"] == "city-sr"
        assert data["items_processed"] == 5


# ---------------------------------------------------------------------------
# _resolve_granicus_player_url
# ---------------------------------------------------------------------------

class TestResolveGranicusPlayerUrl:
    def test_extracts_video_url_from_html(self):
        html = '<html><script>video_url="https://stream.example.com/live.m3u8"</script></html>'
        mock_resp = MagicMock()
        mock_resp.text = html
        with patch("httpx.get", return_value=mock_resp):
            result = _resolve_granicus_player_url("https://sanrafael.granicus.com/player/clip/123")
        assert result == "https://stream.example.com/live.m3u8"

    def test_returns_none_when_no_video_url(self):
        html = "<html><body>No video here</body></html>"
        mock_resp = MagicMock()
        mock_resp.text = html
        with patch("httpx.get", return_value=mock_resp):
            result = _resolve_granicus_player_url("https://sanrafael.granicus.com/player/clip/999")
        assert result is None

    def test_returns_none_with_empty_video_url(self):
        html = '<html><script>video_url=""</script></html>'
        mock_resp = MagicMock()
        mock_resp.text = html
        with patch("httpx.get", return_value=mock_resp):
            result = _resolve_granicus_player_url("https://sanrafael.granicus.com/player/clip/1")
        assert result is None

    def test_returns_none_on_http_error(self):
        with patch("httpx.get", side_effect=Exception("connection refused")):
            result = _resolve_granicus_player_url("https://sanrafael.granicus.com/player/clip/1")
        assert result is None


# ---------------------------------------------------------------------------
# _resolve_granicus_mp3_url
# ---------------------------------------------------------------------------

class TestResolveGranicusMp3Url:
    def test_extracts_mp3_url_from_html(self):
        html = '<html><a href="https://archive-video.granicus.com/sanrafael/sanrafael_abc.mp3">MP3</a></html>'
        mock_resp = MagicMock()
        mock_resp.text = html
        with patch("httpx.get", return_value=mock_resp):
            result = _resolve_granicus_mp3_url("https://sanrafael.granicus.com/MediaPlayer.php?view_id=10&clip_id=123")
        assert result == "https://archive-video.granicus.com/sanrafael/sanrafael_abc.mp3"

    def test_returns_none_when_no_mp3_url(self):
        html = "<html><body>No audio</body></html>"
        mock_resp = MagicMock()
        mock_resp.text = html
        with patch("httpx.get", return_value=mock_resp):
            result = _resolve_granicus_mp3_url("https://sanrafael.granicus.com/MediaPlayer.php?view_id=10&clip_id=1")
        assert result is None

    def test_converts_player_clip_url_to_mediaplayer(self):
        """player/clip/52067 should be converted to MediaPlayer.php URL."""
        html = '<html><a href="https://archive-video.granicus.com/sanrafael/sanrafael_x.mp3">MP3</a></html>'
        mock_resp = MagicMock()
        mock_resp.text = html
        with patch("httpx.get", return_value=mock_resp) as mock_get:
            _resolve_granicus_mp3_url("https://sanrafael.granicus.com/player/clip/52067")
            called_url = mock_get.call_args[0][0]
        assert called_url == "https://sanrafael.granicus.com/MediaPlayer.php?view_id=10&clip_id=52067"

    def test_returns_none_on_http_error(self):
        with patch("httpx.get", side_effect=Exception("timeout")):
            result = _resolve_granicus_mp3_url("https://sanrafael.granicus.com/player/clip/1")
        assert result is None


# ---------------------------------------------------------------------------
# load_videos — local JSON fallback
# ---------------------------------------------------------------------------

class TestLoadVideosLocal:
    """Tests for load_videos when cloud/DATABASE_URL are not set."""

    def test_loads_from_json_file(self, tmp_path):
        videos = [
            {"video_id": "v1", "title": "Meeting 1"},
            {"video_id": "v2", "title": "Meeting 2"},
        ]
        videos_file = tmp_path / "city_san_rafael_videos.json"
        videos_file.write_text(json.dumps(videos))

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            result = load_videos("city-san-rafael", str(tmp_path), cloud=False)

        assert len(result) == 2
        assert result[0]["video_id"] == "v1"
        assert result[1]["title"] == "Meeting 2"

    def test_hyphen_to_underscore_in_filename(self, tmp_path):
        """jurisdiction_id hyphens become underscores in filename."""
        videos_file = tmp_path / "city_corte_madera_videos.json"
        videos_file.write_text(json.dumps([{"video_id": "x"}]))

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            result = load_videos("city-corte-madera", str(tmp_path), cloud=False)

        assert len(result) == 1
        assert result[0]["video_id"] == "x"

    def test_returns_none_when_file_missing(self, tmp_path):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            result = load_videos("city-nonexistent", str(tmp_path), cloud=False)
        assert result is None

    def test_returns_none_on_bad_json(self, tmp_path):
        bad_file = tmp_path / "city_bad_videos.json"
        bad_file.write_text("{{{invalid json")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            result = load_videos("city-bad", str(tmp_path), cloud=False)
        assert result is None

    def test_returns_empty_list_from_empty_json_array(self, tmp_path):
        videos_file = tmp_path / "city_empty_videos.json"
        videos_file.write_text("[]")

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            result = load_videos("city-empty", str(tmp_path), cloud=False)
        # json.load returns [], which is falsy — but load_videos returns it
        assert result == []


# ---------------------------------------------------------------------------
# load_videos — cloud fallback to meetings table
# ---------------------------------------------------------------------------

class TestLoadVideosCloudFallback:
    """Tests for load_videos cloud path and meetings-table fallback."""

    def test_cloud_returns_videos_from_backend(self):
        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_videos.return_value = [
            {"video_id": "v1", "title": "City Council"},
        ]
        with patch("civicos.storage.get_storage_backend", return_value=mock_backend):
            result = load_videos("city-sr", "data", cloud=True)
        assert len(result) == 1
        assert result[0]["video_id"] == "v1"

    def test_cloud_falls_back_to_meetings_with_video_url(self):
        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_videos.return_value = []  # No videos table entries
        mock_backend.get_meetings.return_value = [
            {
                "id": "meeting/2026-04-01",
                "video_url": "https://granicus.com/player/clip/123",
                "title": "Planning Commission",
                "meeting_datetime": "2026-04-01T18:00:00",
            },
        ]
        with patch("civicos.storage.get_storage_backend", return_value=mock_backend):
            result = load_videos("city-sr", "data", cloud=True)
        assert len(result) == 1
        # Check that slashes/colons in meeting ID are replaced for safe R2 keys
        assert "/" not in result[0]["video_id"]
        assert ":" not in result[0]["video_id"]
        assert result[0]["video_url"] == "https://granicus.com/player/clip/123"
        assert result[0]["title"] == "Planning Commission"
        assert result[0]["meeting_id"] == "meeting/2026-04-01"

    def test_cloud_falls_back_to_local_when_no_videos_or_meetings(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.backend_type = "postgres"
        mock_backend.get_videos.return_value = []
        mock_backend.get_meetings.return_value = []

        videos_file = tmp_path / "city_sr_videos.json"
        videos_file.write_text(json.dumps([{"video_id": "local1"}]))

        with patch("civicos.storage.get_storage_backend", return_value=mock_backend):
            result = load_videos("city-sr", str(tmp_path), cloud=True)
        assert len(result) == 1
        assert result[0]["video_id"] == "local1"


# ---------------------------------------------------------------------------
# download_audio
# ---------------------------------------------------------------------------

class TestDownloadAudio:
    def test_returns_error_when_ytdlp_not_installed(self):
        with patch.dict("sys.modules", {"yt_dlp": None}):
            result = download_audio("vid1", "/tmp/audio")
        assert result.video_id == "vid1"
        assert result.status == "error"
        assert "yt-dlp not installed" in result.error

    def test_skips_when_already_in_cloud(self):
        mock_blob = MagicMock()
        mock_blob.exists.side_effect = lambda k: k.endswith(".opus")

        with patch.dict(os.environ, {"BLOB_STORAGE_URL": "https://r2.example.com"}, clear=False):
            with patch("civicos.storage.get_blob_storage", return_value=mock_blob):
                result = download_audio(
                    "vid1", "/tmp/audio",
                    cloud=True,
                    jurisdiction_id="city-sr",
                )
        assert result.status == "skipped"
        assert result.r2_key == "audio/city-sr/vid1.opus"

    def test_skips_when_local_file_exists(self, tmp_path):
        # Create a fake audio file
        audio_file = tmp_path / "vid1.opus"
        audio_file.write_bytes(b"\x00" * 2048)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLOB_STORAGE_URL", None)
            result = download_audio("vid1", str(tmp_path))
        assert result.status == "skipped"
        assert result.file_path == str(tmp_path / "vid1.opus")
        # 2048 bytes = 0.00195... MB
        assert result.file_size_mb == pytest.approx(2048 / (1024 * 1024), abs=0.001)

    def test_constructs_youtube_url_when_no_video_url(self):
        """Without video_url, constructs https://youtube.com/watch?v={video_id}."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"duration": 3600, "ext": "webm"}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLOB_STORAGE_URL", None)
            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
                with patch("subprocess.run") as mock_ffmpeg:
                    mock_ffmpeg.return_value = MagicMock(returncode=0, stderr="")
                    with patch("os.path.exists", side_effect=_exists_for_paths("/tmp/audio/vid1_raw.webm")):
                        with patch("os.path.getsize", return_value=1024 * 1024):
                            with patch("os.remove"):
                                result = download_audio("vid1", "/tmp/audio")

        url_arg = mock_ydl.extract_info.call_args[0][0]
        assert url_arg == "https://www.youtube.com/watch?v=vid1"
        assert result.status == "success"

    def test_uses_video_url_when_provided(self):
        """When video_url is provided, uses it directly instead of constructing YouTube URL."""
        custom_url = "https://vimeo.com/12345"
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"duration": 600, "ext": "mp4"}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLOB_STORAGE_URL", None)
            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
                with patch("subprocess.run") as mock_ffmpeg:
                    mock_ffmpeg.return_value = MagicMock(returncode=0)
                    with patch("os.path.exists", side_effect=_exists_for_paths("/tmp/audio/vid1_raw.mp4")):
                        with patch("os.path.getsize", return_value=512 * 1024):
                            with patch("os.remove"):
                                result = download_audio(
                                    "vid1", "/tmp/audio",
                                    video_url=custom_url,
                                )

        url_arg = mock_ydl.extract_info.call_args[0][0]
        assert url_arg == custom_url
        assert result.status == "success"
        assert result.duration_minutes == 10  # 600 // 60

    def test_granicus_clip_url_triggers_resolution(self):
        """Granicus player/clip URLs should trigger MP3/HLS resolution."""
        granicus_url = "https://sanrafael.granicus.com/player/clip/2509"
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"duration": 120, "ext": "mp3"}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLOB_STORAGE_URL", None)
            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
                with patch("civicos_extraction.cli.audio._resolve_granicus_mp3_url",
                           return_value="https://archive-video.granicus.com/sr/sr_abc.mp3") as mock_mp3:
                    with patch("subprocess.run") as mock_ffmpeg:
                        mock_ffmpeg.return_value = MagicMock(returncode=0)
                        with patch("os.path.exists", side_effect=_exists_for_paths("/tmp/audio/vid1_raw.mp3")):
                            with patch("os.path.getsize", return_value=256 * 1024):
                                with patch("os.remove"):
                                    result = download_audio(
                                        "vid1", "/tmp/audio",
                                        video_url=granicus_url,
                                    )

        mock_mp3.assert_called_once_with(granicus_url)
        url_arg = mock_ydl.extract_info.call_args[0][0]
        assert url_arg == "https://archive-video.granicus.com/sr/sr_abc.mp3"
        assert result.status == "success"

    def test_granicus_returns_error_when_no_video(self):
        """Granicus clip with no video_url and no MP3 returns error."""
        granicus_url = "https://sanrafael.granicus.com/player/clip/999"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLOB_STORAGE_URL", None)
            with patch("civicos_extraction.cli.audio._resolve_granicus_mp3_url", return_value=None):
                with patch("civicos_extraction.cli.audio._resolve_granicus_player_url", return_value=None):
                    result = download_audio("vid1", "/tmp/audio", video_url=granicus_url)

        assert result.status == "error"
        assert "no recording available" in result.error.lower()

    def test_ffmpeg_failure_returns_error(self):
        """If ffmpeg re-encode fails, result is error."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"duration": 60, "ext": "webm"}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLOB_STORAGE_URL", None)
            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl):
                with patch("subprocess.run") as mock_ffmpeg:
                    mock_ffmpeg.return_value = MagicMock(returncode=1, stderr="codec error")
                    with patch("os.path.exists", side_effect=_exists_for_paths("/tmp/audio/vid1_raw.webm")):
                        result = download_audio("vid1", "/tmp/audio")

        assert result.status == "error"
        assert "ffmpeg failed" in result.error

    def test_youtube_url_gets_cookies(self, tmp_path):
        """YouTube URLs should use cookies file if it exists."""
        cookies = tmp_path / "cookies.txt"
        cookies.write_text("# Netscape cookie file")

        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"duration": 60, "ext": "webm"}

        raw_file = str(tmp_path / "vid1_raw.webm")
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLOB_STORAGE_URL", None)
            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl) as mock_ytdlp_cls:
                with patch("subprocess.run") as mock_ffmpeg:
                    mock_ffmpeg.return_value = MagicMock(returncode=0)
                    with patch("os.path.exists", side_effect=_exists_for_paths(raw_file, str(cookies))):
                        with patch("os.path.getsize", return_value=1024):
                            with patch("os.remove"):
                                download_audio(
                                    "vid1", str(tmp_path),
                                    cookies_file=str(cookies),
                                )
                ydl_opts = mock_ytdlp_cls.call_args[0][0]
        assert ydl_opts["cookiefile"] == str(cookies)

    def test_non_youtube_url_skips_cookies(self, tmp_path):
        """Non-YouTube URLs should not use cookies."""
        cookies = tmp_path / "cookies.txt"
        cookies.write_text("# Netscape cookie file")

        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"duration": 60, "ext": "mp3"}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLOB_STORAGE_URL", None)
            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl) as mock_ytdlp_cls:
                with patch("subprocess.run") as mock_ffmpeg:
                    mock_ffmpeg.return_value = MagicMock(returncode=0)
                    with patch("os.path.exists", side_effect=_exists_for_paths(str(tmp_path / "vid1_raw.mp3"))):
                        with patch("os.path.getsize", return_value=1024):
                            with patch("os.remove"):
                                download_audio(
                                    "vid1", str(tmp_path),
                                    cookies_file=str(cookies),
                                    video_url="https://vimeo.com/12345",
                                )
                ydl_opts = mock_ytdlp_cls.call_args[0][0]
        assert "cookiefile" not in ydl_opts

    def test_youtube_url_gets_proxy(self):
        """YouTube URLs should use proxy when provided."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"duration": 60, "ext": "webm"}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLOB_STORAGE_URL", None)
            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl) as mock_ytdlp_cls:
                with patch("subprocess.run") as mock_ffmpeg:
                    mock_ffmpeg.return_value = MagicMock(returncode=0)
                    with patch("os.path.exists", side_effect=_exists_for_paths("/tmp/audio/vid1_raw.webm")):
                        with patch("os.path.getsize", return_value=1024):
                            with patch("os.remove"):
                                download_audio(
                                    "vid1", "/tmp/audio",
                                    proxy="http://user:pass@proxy.example.com:8080",
                                )
                ydl_opts = mock_ytdlp_cls.call_args[0][0]
        assert ydl_opts["proxy"] == "http://user:pass@proxy.example.com:8080"

    def test_non_youtube_url_skips_proxy(self):
        """Non-YouTube URLs should not use proxy (saves bandwidth quota)."""
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"duration": 60, "ext": "mp3"}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLOB_STORAGE_URL", None)
            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl) as mock_ytdlp_cls:
                with patch("subprocess.run") as mock_ffmpeg:
                    mock_ffmpeg.return_value = MagicMock(returncode=0)
                    with patch("os.path.exists", side_effect=_exists_for_paths("/tmp/audio/vid1_raw.mp3")):
                        with patch("os.path.getsize", return_value=1024):
                            with patch("os.remove"):
                                download_audio(
                                    "vid1", "/tmp/audio",
                                    proxy="http://user:pass@proxy.example.com:8080",
                                    video_url="https://archive-video.granicus.com/sr/sr.mp3",
                                )
                ydl_opts = mock_ytdlp_cls.call_args[0][0]
        assert "proxy" not in ydl_opts

    def test_hls_url_uses_ffmpeg_external_downloader(self):
        """HLS streams (Granicus) should use ffmpeg as external downloader with -vn."""
        hls_url = "https://stream.granicus.com/sanrafael/live.m3u8"
        mock_ydl = MagicMock()
        mock_ydl.__enter__ = MagicMock(return_value=mock_ydl)
        mock_ydl.__exit__ = MagicMock(return_value=False)
        mock_ydl.extract_info.return_value = {"duration": 60, "ext": "ts"}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BLOB_STORAGE_URL", None)
            with patch("yt_dlp.YoutubeDL", return_value=mock_ydl) as mock_ytdlp_cls:
                with patch("subprocess.run") as mock_ffmpeg:
                    mock_ffmpeg.return_value = MagicMock(returncode=0)
                    with patch("os.path.exists", side_effect=_exists_for_paths("/tmp/audio/vid1_raw.ts")):
                        with patch("os.path.getsize", return_value=1024):
                            with patch("os.remove"):
                                download_audio(
                                    "vid1", "/tmp/audio",
                                    video_url=hls_url,
                                )
                ydl_opts = mock_ytdlp_cls.call_args[0][0]
        assert ydl_opts["external_downloader"] == "ffmpeg"
        assert ydl_opts["external_downloader_args"] == {"ffmpeg_i": ["-vn"]}


# ---------------------------------------------------------------------------
# run_audio_download — orchestration
# ---------------------------------------------------------------------------

class TestRunAudioDownload:
    def test_returns_none_when_no_videos(self, tmp_path):
        with patch("civicos_extraction.cli.audio.load_videos", return_value=None):
            result = run_audio_download(
                "city-sr",
                input_dir=str(tmp_path),
                output_dir=str(tmp_path / "out"),
                checkpoint_dir=str(tmp_path / "ckpts"),
            )
        assert result is None

    def test_dry_run_returns_none(self, tmp_path):
        videos = [{"video_id": "v1", "title": "Meeting", "date": "2026-04-01"}]
        with patch("civicos_extraction.cli.audio.load_videos", return_value=videos):
            result = run_audio_download(
                "city-sr",
                input_dir=str(tmp_path),
                output_dir=str(tmp_path / "out"),
                checkpoint_dir=str(tmp_path / "ckpts"),
                dry_run=True,
            )
        assert result is None

    def test_limit_restricts_video_count(self, tmp_path):
        videos = [
            {"video_id": "v1", "title": "A"},
            {"video_id": "v2", "title": "B"},
            {"video_id": "v3", "title": "C"},
        ]
        download_results = []

        def fake_download(vid, out, cookies, quality, cloud, jid, proxy, worker_id):
            r = DownloadResult(video_id=vid["video_id"], status="success",
                               file_size_mb=1.0, duration_minutes=30)
            download_results.append(r)
            return r

        with patch("civicos_extraction.cli.audio.load_videos", return_value=videos):
            with patch("civicos_extraction.cli.audio._download_worker", side_effect=fake_download):
                result = run_audio_download(
                    "city-sr",
                    input_dir=str(tmp_path),
                    output_dir=str(tmp_path / "out"),
                    checkpoint_dir=str(tmp_path / "ckpts"),
                    limit=2,
                    max_workers=1,
                )
        assert len(result) == 2
        processed_ids = {r.video_id for r in result}
        assert "v1" in processed_ids
        assert "v2" in processed_ids
        assert "v3" not in processed_ids

    def test_checkpoint_resumes_from_last_video(self, tmp_path):
        videos = [
            {"video_id": "v1", "title": "A"},
            {"video_id": "v2", "title": "B"},
            {"video_id": "v3", "title": "C"},
        ]
        # Create a checkpoint that says v2 was the last processed
        ckpt_dir = tmp_path / "ckpts"
        ckpt_dir.mkdir()
        ckpt = AudioCheckpoint(
            jurisdiction_id="city-sr",
            last_video_id="v2",
            items_processed=2,
            items_downloaded=2,
            items_skipped=0,
            items_failed=0,
            timestamp="2026-04-09T10:00:00",
        )
        save_checkpoint(ckpt, ckpt_dir / "audio_city-sr.json")

        def fake_download(vid, out, cookies, quality, cloud, jid, proxy, worker_id):
            return DownloadResult(video_id=vid["video_id"], status="success",
                                  file_size_mb=1.0, duration_minutes=30)

        with patch("civicos_extraction.cli.audio.load_videos", return_value=videos):
            with patch("civicos_extraction.cli.audio._download_worker", side_effect=fake_download):
                result = run_audio_download(
                    "city-sr",
                    input_dir=str(tmp_path),
                    output_dir=str(tmp_path / "out"),
                    checkpoint_dir=str(ckpt_dir),
                    max_workers=1,
                )
        # Only v3 should have been processed (resume after v2)
        assert len(result) == 1
        assert result[0].video_id == "v3"

    def test_saves_checkpoint_after_processing(self, tmp_path):
        videos = [{"video_id": "v1", "title": "A"}]

        def fake_download(vid, out, cookies, quality, cloud, jid, proxy, worker_id):
            return DownloadResult(video_id=vid["video_id"], status="success",
                                  file_size_mb=1.0, duration_minutes=30)

        ckpt_dir = tmp_path / "ckpts"
        with patch("civicos_extraction.cli.audio.load_videos", return_value=videos):
            with patch("civicos_extraction.cli.audio._download_worker", side_effect=fake_download):
                run_audio_download(
                    "city-sr",
                    input_dir=str(tmp_path),
                    output_dir=str(tmp_path / "out"),
                    checkpoint_dir=str(ckpt_dir),
                    max_workers=1,
                )

        ckpt_file = ckpt_dir / "audio_city-sr.json"
        assert ckpt_file.exists()
        data = json.loads(ckpt_file.read_text())
        assert data["last_video_id"] == "v1"
        assert data["items_processed"] == 1
        assert data["items_downloaded"] == 1

    def test_saves_manifest_after_processing(self, tmp_path):
        videos = [{"video_id": "v1", "title": "A"}]

        def fake_download(vid, out, cookies, quality, cloud, jid, proxy, worker_id):
            return DownloadResult(video_id=vid["video_id"], status="success",
                                  file_size_mb=1.0, duration_minutes=30)

        out_dir = tmp_path / "out"
        with patch("civicos_extraction.cli.audio.load_videos", return_value=videos):
            with patch("civicos_extraction.cli.audio._download_worker", side_effect=fake_download):
                run_audio_download(
                    "city-sr",
                    input_dir=str(tmp_path),
                    output_dir=str(out_dir),
                    checkpoint_dir=str(tmp_path / "ckpts"),
                    max_workers=1,
                )

        manifest = out_dir / "city_sr_manifest.json"
        assert manifest.exists()
        data = json.loads(manifest.read_text())
        assert len(data) == 1
        assert data[0]["video_id"] == "v1"
        assert data[0]["status"] == "success"

    def test_counts_success_skip_fail(self, tmp_path):
        videos = [
            {"video_id": "v1", "title": "A"},
            {"video_id": "v2", "title": "B"},
            {"video_id": "v3", "title": "C"},
        ]
        statuses = iter(["success", "skipped", "error"])

        def fake_download(vid, out, cookies, quality, cloud, jid, proxy, worker_id):
            s = next(statuses)
            return DownloadResult(video_id=vid["video_id"], status=s,
                                  file_size_mb=1.0, duration_minutes=30,
                                  error="fail" if s == "error" else None)

        ckpt_dir = tmp_path / "ckpts"
        with patch("civicos_extraction.cli.audio.load_videos", return_value=videos):
            with patch("civicos_extraction.cli.audio._download_worker", side_effect=fake_download):
                run_audio_download(
                    "city-sr",
                    input_dir=str(tmp_path),
                    output_dir=str(tmp_path / "out"),
                    checkpoint_dir=str(ckpt_dir),
                    max_workers=1,
                )

        # Verify checkpoint has correct counts
        data = json.loads((ckpt_dir / "audio_city-sr.json").read_text())
        assert data["items_downloaded"] == 1
        assert data["items_skipped"] == 1
        assert data["items_failed"] == 1

    def test_skips_videos_without_video_id(self, tmp_path):
        """Videos without video_id should be silently skipped."""
        videos = [
            {"title": "No ID"},  # no video_id key
            {"video_id": "v1", "title": "Has ID"},
        ]

        def fake_download(vid, out, cookies, quality, cloud, jid, proxy, worker_id):
            return DownloadResult(video_id=vid["video_id"], status="success",
                                  file_size_mb=1.0, duration_minutes=30)

        with patch("civicos_extraction.cli.audio.load_videos", return_value=videos):
            with patch("civicos_extraction.cli.audio._download_worker", side_effect=fake_download):
                result = run_audio_download(
                    "city-sr",
                    input_dir=str(tmp_path),
                    output_dir=str(tmp_path / "out"),
                    checkpoint_dir=str(tmp_path / "ckpts"),
                    max_workers=1,
                )
        # Only the video with an ID was processed
        assert len(result) == 1
        assert result[0].video_id == "v1"


# ---------------------------------------------------------------------------
# run_audio (CLI entry point)
# ---------------------------------------------------------------------------

class TestRunAudio:
    def _make_args(self, **kwargs):
        defaults = {
            "verbose": False,
            "schedule": False,
            "jurisdiction": "city-sr",
            "input_dir": "data",
            "output_dir": "data/youtube_audio",
            "cookies": "~/cookies.txt",
            "checkpoint_dir": "data/checkpoints",
            "dry_run": False,
            "limit": 0,
            "quality": "48",
            "cloud": False,
            "proxy": None,
        }
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    def test_returns_zero_on_success(self):
        args = self._make_args()
        with patch("civicos_extraction.cli.audio.run_audio_download", return_value=[]):
            code = run_audio(args)
        assert code == 0

    def test_returns_one_on_failure(self):
        args = self._make_args()
        with patch("civicos_extraction.cli.audio.run_audio_download", return_value=None):
            code = run_audio(args)
        assert code == 1

    def test_dry_run_returns_zero_even_when_none(self):
        args = self._make_args(dry_run=True)
        with patch("civicos_extraction.cli.audio.run_audio_download", return_value=None):
            code = run_audio(args)
        assert code == 0

    def test_verbose_sets_debug_level(self):
        args = self._make_args(verbose=True)
        with patch("civicos_extraction.cli.audio.run_audio_download", return_value=[]):
            code = run_audio(args)
        assert code == 0
        # Verify root logger is now at DEBUG level
        import logging
        assert logging.getLogger().level == logging.DEBUG


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _exists_for_paths(*true_paths):
    """Return an os.path.exists side_effect that returns True only for specific paths."""
    def exists(path):
        return path in true_paths
    return exists
