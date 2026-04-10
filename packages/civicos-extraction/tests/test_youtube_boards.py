"""
Tests for YouTubeBoardsClient, YouTubeBoardsSource, and factory functions.

All tests mock the YouTube Data API — no live network calls.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from civicos_extraction.clients.base import ExtractionConfig, Meeting
from civicos_extraction.clients.youtube_boards import (
    YouTubeBoardsClient,
    YouTubeBoardsSource,
    YouTubeVideo,
    create_srcs_youtube_client,
    create_srcs_youtube_source,
)


# ============================================================================
# Fixtures / Helpers
# ============================================================================


def make_video(
    video_id="abc123",
    title="Board Meeting - January 15, 2026",
    description="Regular school board meeting",
    published_at=None,
    duration_seconds=3600,
    thumbnail_url="https://i.ytimg.com/vi/abc123/maxresdefault.jpg",
    channel_id="UC_test",
    channel_title="SRCS Communications",
):
    """Create a YouTubeVideo with sensible defaults."""
    return YouTubeVideo(
        video_id=video_id,
        title=title,
        description=description,
        published_at=published_at or datetime(2026, 1, 15, 18, 0, 0),
        duration_seconds=duration_seconds,
        thumbnail_url=thumbnail_url,
        channel_id=channel_id,
        channel_title=channel_title,
    )


@pytest.fixture
def client():
    """YouTubeBoardsClient with a fake API key (no real API calls)."""
    return YouTubeBoardsClient(
        playlist_id="PLtestplaylist1234567890",
        jurisdiction_id="school-san-rafael",
        api_key="fake-api-key-for-tests",
        meeting_types=["school_board", "special_meeting"],
    )


@pytest.fixture
def config():
    """ExtractionConfig for a YouTube-based school board."""
    return ExtractionConfig(
        source_id="youtube-school-san-rafael",
        source_type="youtube_boards",
        jurisdiction_id="school-san-rafael",
        base_url="https://www.youtube.com",
        metadata={
            "youtube_playlist": "PLtestplaylist1234567890",
            "youtube_channel": "@srcscommunications5656",
            "meeting_types": ["school_board", "workshop"],
        },
    )


def _mock_youtube_service(playlist_items_response, video_details_response=None):
    """Build a mock YouTube API service with chained method calls."""
    service = MagicMock()

    # playlistItems().list().execute()
    pi_request = MagicMock()
    pi_request.execute.return_value = playlist_items_response
    service.playlistItems.return_value.list.return_value = pi_request

    # videos().list().execute()
    if video_details_response:
        v_request = MagicMock()
        v_request.execute.return_value = video_details_response
        service.videos.return_value.list.return_value = v_request

    # playlists().list().execute() — for health checks
    pl_request = MagicMock()
    pl_request.execute.return_value = {
        "items": [
            {
                "snippet": {
                    "title": "SRCS Board Meetings",
                    "channelTitle": "SRCS Communications",
                },
                "contentDetails": {"itemCount": 25},
            }
        ]
    }
    service.playlists.return_value.list.return_value = pl_request

    return service


# ============================================================================
# YouTubeVideo
# ============================================================================


class TestYouTubeVideo:
    def test_watch_url_format(self):
        video = make_video(video_id="dQw4w9WgXcQ")
        assert video.watch_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_watch_url_uses_video_id(self):
        video = make_video(video_id="xyz789")
        assert "xyz789" in video.watch_url
        assert video.watch_url.startswith("https://www.youtube.com/watch?v=")


# ============================================================================
# YouTubeBoardsClient — Properties
# ============================================================================


class TestClientProperties:
    def test_source_id(self, client):
        assert client.source_id == "youtube-school-san-rafael"

    def test_source_type(self, client):
        assert client.source_type == "youtube_boards"

    def test_platform_name(self, client):
        assert client.platform_name == "YouTube"


# ============================================================================
# YouTubeBoardsClient — Init / API Key
# ============================================================================


class TestClientInit:
    def test_api_key_from_constructor(self):
        c = YouTubeBoardsClient(
            playlist_id="PL123",
            jurisdiction_id="school-test",
            api_key="explicit-key",
        )
        assert c._api_key == "explicit-key"

    def test_api_key_from_youtube_env(self):
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": "yt-key"}, clear=False):
            c = YouTubeBoardsClient(
                playlist_id="PL123",
                jurisdiction_id="school-test",
            )
            assert c._api_key == "yt-key"

    def test_api_key_falls_back_to_google_env(self):
        with patch.dict(
            "os.environ",
            {"GOOGLE_API_KEY": "google-key"},
            clear=False,
        ):
            with patch.dict("os.environ", {}, clear=False):
                # Remove YOUTUBE_API_KEY if it exists
                import os
                orig = os.environ.pop("YOUTUBE_API_KEY", None)
                try:
                    c = YouTubeBoardsClient(
                        playlist_id="PL123",
                        jurisdiction_id="school-test",
                    )
                    assert c._api_key == "google-key"
                finally:
                    if orig is not None:
                        os.environ["YOUTUBE_API_KEY"] = orig

    def test_default_meeting_types(self):
        c = YouTubeBoardsClient(
            playlist_id="PL123",
            jurisdiction_id="school-test",
            api_key="key",
        )
        assert c._meeting_types == ["school_board"]

    def test_custom_meeting_types(self):
        c = YouTubeBoardsClient(
            playlist_id="PL123",
            jurisdiction_id="school-test",
            api_key="key",
            meeting_types=["workshop", "special_meeting"],
        )
        assert c._meeting_types == ["workshop", "special_meeting"]

    def test_get_service_raises_without_api_key(self):
        c = YouTubeBoardsClient(
            playlist_id="PL123",
            jurisdiction_id="school-test",
            api_key=None,
        )
        # Clear env vars
        with patch.dict("os.environ", {}, clear=True):
            c._api_key = None
            with pytest.raises(ValueError, match="YOUTUBE_API_KEY not set"):
                c._get_service()


# ============================================================================
# YouTubeBoardsClient — _parse_duration
# ============================================================================


class TestParseDuration:
    def test_hours_minutes_seconds(self, client):
        assert client._parse_duration("PT1H30M45S") == 5445

    def test_minutes_only(self, client):
        assert client._parse_duration("PT45M") == 2700

    def test_seconds_only(self, client):
        assert client._parse_duration("PT30S") == 30

    def test_hours_only(self, client):
        assert client._parse_duration("PT2H") == 7200

    def test_hours_and_seconds(self, client):
        assert client._parse_duration("PT1H15S") == 3615

    def test_zero_duration(self, client):
        assert client._parse_duration("PT0S") == 0

    def test_invalid_format_returns_zero(self, client):
        assert client._parse_duration("not-a-duration") == 0

    def test_empty_string_returns_zero(self, client):
        assert client._parse_duration("") == 0


# ============================================================================
# YouTubeBoardsClient — _extract_meeting_date
# ============================================================================


class TestExtractMeetingDate:
    def test_full_month_name_with_comma(self, client):
        video = make_video(title="Board Meeting - January 15, 2026")
        result = client._extract_meeting_date(video)
        assert result == datetime(2026, 1, 15)

    def test_abbreviated_month(self, client):
        video = make_video(title="Board Meeting - Feb 3, 2026")
        result = client._extract_meeting_date(video)
        assert result == datetime(2026, 2, 3)

    def test_full_month_no_comma(self, client):
        video = make_video(title="Meeting March 10 2026")
        result = client._extract_meeting_date(video)
        assert result == datetime(2026, 3, 10)

    def test_mm_dd_yyyy_slash(self, client):
        video = make_video(title="Meeting", description="Recorded 01/15/2026")
        result = client._extract_meeting_date(video)
        assert result == datetime(2026, 1, 15)

    def test_yyyy_mm_dd_dash(self, client):
        video = make_video(title="Meeting", description="Date: 2026-03-20")
        result = client._extract_meeting_date(video)
        assert result == datetime(2026, 3, 20)

    def test_date_in_description_not_title(self, client):
        video = make_video(
            title="School Board Meeting",
            description="Held on December 5, 2025",
        )
        result = client._extract_meeting_date(video)
        assert result == datetime(2025, 12, 5)

    def test_falls_back_to_published_at(self, client):
        published = datetime(2026, 6, 1, 12, 0, 0)
        video = make_video(
            title="Untitled Video",
            description="No date here",
            published_at=published,
        )
        result = client._extract_meeting_date(video)
        assert result == published

    def test_month_pattern_takes_priority_over_slash(self, client):
        video = make_video(title="Board Meeting - April 20, 2026 (recorded 04/19/2026)")
        result = client._extract_meeting_date(video)
        assert result == datetime(2026, 4, 20)


# ============================================================================
# YouTubeBoardsClient — _extract_meeting_type
# ============================================================================


class TestExtractMeetingType:
    def test_special_meeting(self, client):
        assert client._extract_meeting_type("Special Board Meeting") == "special_meeting"

    def test_workshop(self, client):
        assert client._extract_meeting_type("Budget Workshop") == "workshop"

    def test_study_session(self, client):
        assert client._extract_meeting_type("Study Session on Policy") == "study_session"

    def test_public_hearing(self, client):
        assert client._extract_meeting_type("Public Hearing - Zoning") == "public_hearing"

    def test_board_meeting(self, client):
        assert client._extract_meeting_type("Board Meeting - January") == "school_board"

    def test_board_keyword(self, client):
        assert client._extract_meeting_type("School Board") == "school_board"

    def test_default_to_first_meeting_type(self, client):
        # client has meeting_types=["school_board", "special_meeting"]
        assert client._extract_meeting_type("Random Title") == "school_board"

    def test_default_with_custom_meeting_types(self):
        c = YouTubeBoardsClient(
            playlist_id="PL123",
            jurisdiction_id="school-test",
            api_key="key",
            meeting_types=["workshop"],
        )
        assert c._extract_meeting_type("Generic Video Title") == "workshop"

    def test_case_insensitive(self, client):
        assert client._extract_meeting_type("SPECIAL BOARD MEETING") == "special_meeting"
        assert client._extract_meeting_type("WORKSHOP") == "workshop"

    def test_special_takes_priority_over_board(self, client):
        # "special" is checked before "board"
        assert client._extract_meeting_type("Special Board Meeting") == "special_meeting"


# ============================================================================
# YouTubeBoardsClient — video_to_meeting
# ============================================================================


class TestVideoToMeeting:
    def test_converts_to_meeting_dataclass(self, client):
        video = make_video(video_id="abc123", title="Board Meeting - January 15, 2026")
        meeting = client.video_to_meeting(video)

        assert isinstance(meeting, Meeting)
        assert meeting.id == "school-san-rafael-youtube-abc123"
        assert meeting.title == "Board Meeting - January 15, 2026"
        assert meeting.jurisdiction_id == "school-san-rafael"
        assert meeting.meeting_type == "school_board"
        assert meeting.status == "completed"
        assert meeting.source_platform == "youtube"

    def test_video_url_is_watch_url(self, client):
        video = make_video(video_id="xyz789")
        meeting = client.video_to_meeting(video)
        assert meeting.video_url == "https://www.youtube.com/watch?v=xyz789"
        assert meeting.source_url == "https://www.youtube.com/watch?v=xyz789"

    def test_meeting_date_extracted_from_title(self, client):
        video = make_video(title="Board Meeting - March 10, 2026")
        meeting = client.video_to_meeting(video)
        assert meeting.meeting_datetime == datetime(2026, 3, 10)

    def test_raw_data_includes_video_metadata(self, client):
        video = make_video(
            video_id="v123",
            duration_seconds=5400,
            channel_id="UC_test",
            channel_title="SRCS",
            thumbnail_url="https://example.com/thumb.jpg",
        )
        meeting = client.video_to_meeting(video)

        assert meeting.raw_data["video_id"] == "v123"
        assert meeting.raw_data["duration_seconds"] == 5400
        assert meeting.raw_data["channel_id"] == "UC_test"
        assert meeting.raw_data["channel_title"] == "SRCS"
        assert meeting.raw_data["thumbnail_url"] == "https://example.com/thumb.jpg"

    def test_special_meeting_type(self, client):
        video = make_video(title="Special Meeting - Budget Review")
        meeting = client.video_to_meeting(video)
        assert meeting.meeting_type == "special_meeting"

    def test_location_and_agenda_are_none(self, client):
        video = make_video()
        meeting = client.video_to_meeting(video)
        assert meeting.location is None
        assert meeting.agenda_url is None
        assert meeting.minutes_url is None
        assert meeting.virtual_url is None


# ============================================================================
# YouTubeBoardsClient — get_playlist_items (pagination)
# ============================================================================


class TestGetPlaylistItems:
    def test_single_page(self, client):
        service = MagicMock()
        request = MagicMock()
        request.execute.return_value = {
            "items": [{"contentDetails": {"videoId": "v1"}}],
            "nextPageToken": None,
        }
        service.playlistItems.return_value.list.return_value = request
        client._youtube_service = service

        items = client.get_playlist_items()
        assert len(items) == 1
        assert items[0]["contentDetails"]["videoId"] == "v1"

    def test_multiple_pages(self, client):
        service = MagicMock()

        page1 = MagicMock()
        page1.execute.return_value = {
            "items": [{"contentDetails": {"videoId": "v1"}}],
            "nextPageToken": "page2token",
        }
        page2 = MagicMock()
        page2.execute.return_value = {
            "items": [{"contentDetails": {"videoId": "v2"}}],
            "nextPageToken": None,
        }
        service.playlistItems.return_value.list.side_effect = [page1, page2]
        client._youtube_service = service

        items = client.get_playlist_items()
        assert len(items) == 2
        assert items[0]["contentDetails"]["videoId"] == "v1"
        assert items[1]["contentDetails"]["videoId"] == "v2"

    def test_empty_playlist(self, client):
        service = MagicMock()
        request = MagicMock()
        request.execute.return_value = {"items": [], "nextPageToken": None}
        service.playlistItems.return_value.list.return_value = request
        client._youtube_service = service

        items = client.get_playlist_items()
        assert items == []


# ============================================================================
# YouTubeBoardsClient — get_video_details (batching)
# ============================================================================


class TestGetVideoDetails:
    def test_single_batch(self, client):
        service = MagicMock()
        request = MagicMock()
        request.execute.return_value = {
            "items": [{"id": "v1", "snippet": {"title": "Video 1"}}]
        }
        service.videos.return_value.list.return_value = request
        client._youtube_service = service

        details = client.get_video_details(["v1"])
        assert len(details) == 1
        assert details[0]["id"] == "v1"

    def test_batches_at_50(self, client):
        service = MagicMock()
        # 60 video IDs → 2 batches (50 + 10)
        batch1_response = MagicMock()
        batch1_response.execute.return_value = {
            "items": [{"id": f"v{i}"} for i in range(50)]
        }
        batch2_response = MagicMock()
        batch2_response.execute.return_value = {
            "items": [{"id": f"v{i}"} for i in range(50, 60)]
        }
        service.videos.return_value.list.side_effect = [batch1_response, batch2_response]
        client._youtube_service = service

        video_ids = [f"v{i}" for i in range(60)]
        details = client.get_video_details(video_ids)
        assert len(details) == 60

    def test_empty_list(self, client):
        service = MagicMock()
        client._youtube_service = service

        details = client.get_video_details([])
        assert details == []


# ============================================================================
# YouTubeBoardsClient — get_videos (integration of playlist + details)
# ============================================================================


class TestGetVideos:
    def test_combines_playlist_and_details(self, client):
        playlist_response = {
            "items": [
                {"contentDetails": {"videoId": "v1"}, "snippet": {"title": "Item 1"}},
                {"contentDetails": {"videoId": "v2"}, "snippet": {"title": "Item 2"}},
            ],
            "nextPageToken": None,
        }
        video_details_response = {
            "items": [
                {
                    "id": "v1",
                    "snippet": {
                        "title": "Board Meeting - January 15, 2026",
                        "description": "Regular meeting",
                        "publishedAt": "2026-01-15T20:00:00Z",
                        "channelId": "UC_test",
                        "channelTitle": "SRCS",
                        "thumbnails": {
                            "high": {"url": "https://img/high.jpg"},
                            "default": {"url": "https://img/default.jpg"},
                        },
                    },
                    "contentDetails": {"duration": "PT1H30M"},
                },
                {
                    "id": "v2",
                    "snippet": {
                        "title": "Special Meeting - February 1, 2026",
                        "description": "",
                        "publishedAt": "2026-02-01T18:00:00Z",
                        "channelId": "UC_test",
                        "channelTitle": "SRCS",
                        "thumbnails": {},
                    },
                    "contentDetails": {"duration": "PT45M"},
                },
            ]
        }

        service = _mock_youtube_service(playlist_response, video_details_response)
        client._youtube_service = service

        videos = client.get_videos()

        assert len(videos) == 2

        assert videos[0].video_id == "v1"
        assert videos[0].title == "Board Meeting - January 15, 2026"
        assert videos[0].duration_seconds == 5400  # 1h30m
        assert videos[0].thumbnail_url == "https://img/high.jpg"
        assert videos[0].channel_title == "SRCS"

        assert videos[1].video_id == "v2"
        assert videos[1].title == "Special Meeting - February 1, 2026"
        assert videos[1].duration_seconds == 2700  # 45m
        assert videos[1].thumbnail_url is None  # No thumbnails available

    def test_empty_playlist_returns_empty(self, client):
        service = _mock_youtube_service(
            {"items": [], "nextPageToken": None}
        )
        client._youtube_service = service

        videos = client.get_videos()
        assert videos == []

    def test_skips_items_missing_video_id(self, client):
        playlist_response = {
            "items": [
                {"contentDetails": {"videoId": "v1"}},
                {"contentDetails": {}},  # Missing videoId
            ],
            "nextPageToken": None,
        }
        video_details_response = {
            "items": [
                {
                    "id": "v1",
                    "snippet": {
                        "title": "Meeting",
                        "description": "",
                        "publishedAt": "2026-01-01T00:00:00Z",
                        "thumbnails": {},
                    },
                    "contentDetails": {"duration": "PT1H"},
                },
            ]
        }

        service = _mock_youtube_service(playlist_response, video_details_response)
        client._youtube_service = service

        videos = client.get_videos()
        assert len(videos) == 1
        assert videos[0].video_id == "v1"

    def test_thumbnail_priority_maxres_first(self, client):
        playlist_response = {
            "items": [{"contentDetails": {"videoId": "v1"}}],
            "nextPageToken": None,
        }
        video_details_response = {
            "items": [
                {
                    "id": "v1",
                    "snippet": {
                        "title": "Meeting",
                        "description": "",
                        "publishedAt": "2026-01-01T00:00:00Z",
                        "thumbnails": {
                            "maxres": {"url": "https://img/maxres.jpg"},
                            "high": {"url": "https://img/high.jpg"},
                            "default": {"url": "https://img/default.jpg"},
                        },
                    },
                    "contentDetails": {"duration": "PT1H"},
                },
            ]
        }

        service = _mock_youtube_service(playlist_response, video_details_response)
        client._youtube_service = service

        videos = client.get_videos()
        assert videos[0].thumbnail_url == "https://img/maxres.jpg"

    def test_published_at_z_suffix_parsed(self, client):
        playlist_response = {
            "items": [{"contentDetails": {"videoId": "v1"}}],
            "nextPageToken": None,
        }
        video_details_response = {
            "items": [
                {
                    "id": "v1",
                    "snippet": {
                        "title": "No Date Title",
                        "description": "",
                        "publishedAt": "2026-03-15T10:30:00Z",
                        "thumbnails": {},
                    },
                    "contentDetails": {"duration": "PT1H"},
                },
            ]
        }

        service = _mock_youtube_service(playlist_response, video_details_response)
        client._youtube_service = service

        videos = client.get_videos()
        assert videos[0].published_at.year == 2026
        assert videos[0].published_at.month == 3
        assert videos[0].published_at.day == 15


# ============================================================================
# YouTubeBoardsClient — get_meetings (filtering and sorting)
# ============================================================================


class TestGetMeetings:
    def test_returns_meetings_sorted_newest_first(self, client):
        videos = [
            make_video(video_id="old", title="Board Meeting - January 1, 2026"),
            make_video(video_id="new", title="Board Meeting - March 1, 2026"),
            make_video(video_id="mid", title="Board Meeting - February 1, 2026"),
        ]

        with patch.object(client, "get_videos", return_value=videos):
            meetings = client.get_meetings()

        assert len(meetings) == 3
        assert meetings[0].id.endswith("new")
        assert meetings[1].id.endswith("mid")
        assert meetings[2].id.endswith("old")

    def test_filters_by_days_past(self, client):
        recent = make_video(
            video_id="recent",
            title="Recent",
            published_at=datetime.now() - timedelta(days=10),
        )
        old = make_video(
            video_id="old",
            title="Old",
            published_at=datetime.now() - timedelta(days=400),
        )
        # These videos have no date in title, so they'll fall back to published_at
        recent_video = make_video(
            video_id="recent", title="Meeting Recent", description="",
            published_at=datetime.now() - timedelta(days=10),
        )
        old_video = make_video(
            video_id="old", title="Meeting Old", description="",
            published_at=datetime.now() - timedelta(days=400),
        )

        with patch.object(client, "get_videos", return_value=[recent_video, old_video]):
            meetings = client.get_meetings(days_past=365)

        # Only the recent meeting should pass the 365-day filter
        meeting_ids = [m.id for m in meetings]
        assert any("recent" in mid for mid in meeting_ids)
        assert not any("old" in mid for mid in meeting_ids)

    def test_empty_videos_returns_empty(self, client):
        with patch.object(client, "get_videos", return_value=[]):
            meetings = client.get_meetings()

        assert meetings == []


# ============================================================================
# YouTubeBoardsClient — health
# ============================================================================


class TestHealth:
    def test_health_success(self, client):
        service = MagicMock()
        pl_request = MagicMock()
        pl_request.execute.return_value = {
            "items": [
                {
                    "snippet": {
                        "title": "SRCS Board Meetings",
                        "channelTitle": "SRCS Communications",
                    },
                    "contentDetails": {"itemCount": 42},
                }
            ]
        }
        service.playlists.return_value.list.return_value = pl_request
        client._youtube_service = service

        health = client.health()

        assert health.is_available is True
        assert health.available_count == 42
        assert health.source_id == "youtube-school-san-rafael"
        assert health.source_type == "youtube_boards"
        assert health.jurisdiction_id == "school-san-rafael"
        assert health.metadata["playlist_title"] == "SRCS Board Meetings"
        assert health.metadata["channel_title"] == "SRCS Communications"
        assert health.errors == []
        assert health.check_duration_ms >= 0

    def test_health_playlist_not_found(self, client):
        service = MagicMock()
        pl_request = MagicMock()
        pl_request.execute.return_value = {"items": []}
        service.playlists.return_value.list.return_value = pl_request
        client._youtube_service = service

        health = client.health()

        assert health.is_available is False
        assert health.available_count == 0
        assert "Playlist not found" in health.errors[0]

    def test_health_no_api_key(self):
        c = YouTubeBoardsClient(
            playlist_id="PL123",
            jurisdiction_id="school-test",
            api_key=None,
        )
        with patch.dict("os.environ", {}, clear=True):
            c._api_key = None
            health = c.health()

        assert health.is_available is False
        assert "YOUTUBE_API_KEY not set" in health.errors[0]

    def test_health_http_403_error(self, client):
        from googleapiclient.errors import HttpError

        resp = MagicMock()
        resp.status = 403
        error = HttpError(resp, b"Forbidden")
        error.reason = "API key blocked"

        service = MagicMock()
        service.playlists.return_value.list.return_value.execute.side_effect = error
        client._youtube_service = service

        health = client.health()

        assert health.is_available is False
        assert "Enable YouTube Data API v3" in health.errors[0]

    def test_health_generic_http_error(self, client):
        from googleapiclient.errors import HttpError

        resp = MagicMock()
        resp.status = 500
        error = HttpError(resp, b"Server Error")
        error.reason = "Internal server error"

        service = MagicMock()
        service.playlists.return_value.list.return_value.execute.side_effect = error
        client._youtube_service = service

        health = client.health()

        assert health.is_available is False
        assert "Internal server error" in health.errors[0]
        assert "Enable YouTube Data API v3" not in health.errors[0]


# ============================================================================
# YouTubeBoardsClient — validate
# ============================================================================


class TestValidate:
    def test_valid_config_and_api(self, client):
        service = _mock_youtube_service(
            {"items": [], "nextPageToken": None}
        )
        client._youtube_service = service

        result = client.validate()

        assert result.config_valid is True
        assert result.api_reachable is True
        assert result.is_valid is True
        assert result.errors == []

    def test_missing_api_key(self):
        c = YouTubeBoardsClient(
            playlist_id="PL_valid_id_1234567890",
            jurisdiction_id="school-test",
            api_key=None,
        )
        with patch.dict("os.environ", {}, clear=True):
            c._api_key = None
            result = c.validate()

        assert result.config_valid is False
        assert "YOUTUBE_API_KEY" in result.errors[0]

    def test_invalid_playlist_id(self):
        c = YouTubeBoardsClient(
            playlist_id="short",  # < 10 chars
            jurisdiction_id="school-test",
            api_key="key",
        )
        result = c.validate()
        assert result.config_valid is False
        assert "Invalid playlist ID" in result.errors[0]

    def test_empty_playlist_id(self):
        c = YouTubeBoardsClient(
            playlist_id="",
            jurisdiction_id="school-test",
            api_key="key",
        )
        result = c.validate()
        assert result.config_valid is False

    def test_missing_jurisdiction_id(self):
        c = YouTubeBoardsClient(
            playlist_id="PLtestplaylist1234567890",
            jurisdiction_id="",
            api_key="key",
        )
        result = c.validate()
        assert result.config_valid is False
        assert "jurisdiction_id" in result.errors[0]

    def test_empty_playlist_warning(self, client):
        service = MagicMock()
        pl_request = MagicMock()
        pl_request.execute.return_value = {
            "items": [
                {
                    "snippet": {"title": "Empty Playlist", "channelTitle": "Test"},
                    "contentDetails": {"itemCount": 0},
                }
            ]
        }
        service.playlists.return_value.list.return_value = pl_request
        client._youtube_service = service

        result = client.validate()
        assert "Playlist is empty" in result.warnings[0]


# ============================================================================
# YouTubeBoardsSource
# ============================================================================


class TestYouTubeBoardsSource:
    def test_init_from_config(self, config):
        source = YouTubeBoardsSource(config, api_key="test-key")

        assert source.source_id == "youtube-school-san-rafael"
        assert source.source_type == "youtube_boards"
        assert source.client._playlist_id == "PLtestplaylist1234567890"
        assert source.client._meeting_types == ["school_board", "workshop"]
        assert source.config is config

    def test_missing_youtube_playlist_raises(self):
        config = ExtractionConfig(
            source_id="test",
            source_type="youtube_boards",
            jurisdiction_id="school-test",
            base_url="https://youtube.com",
            metadata={},  # No youtube_playlist
        )
        with pytest.raises(ValueError, match="youtube_playlist not found"):
            YouTubeBoardsSource(config, api_key="key")

    def test_get_meetings_delegates_to_client(self, config):
        source = YouTubeBoardsSource(config, api_key="test-key")
        mock_meeting = Meeting(
            id="test-id",
            title="Test Meeting",
            meeting_datetime=datetime(2026, 1, 1),
            jurisdiction_id="school-san-rafael",
        )

        with patch.object(source.client, "get_meetings", return_value=[mock_meeting]) as mock:
            meetings = source.get_meetings(days_ahead=0, days_past=30)

        assert len(meetings) == 1
        assert meetings[0].id == "test-id"
        mock.assert_called_once_with(days_ahead=0, days_past=30)

    def test_validate_checks_config_fields(self):
        config = ExtractionConfig(
            source_id="test",
            source_type="youtube_boards",
            jurisdiction_id="",  # Empty
            base_url="https://youtube.com",
            metadata={"youtube_playlist": "PLtest1234567890"},
        )
        source = YouTubeBoardsSource(config, api_key="key")
        result = source.validate()

        assert result.config_valid is False
        assert "jurisdiction_id" in result.errors[0]

    def test_validate_missing_playlist_in_config(self):
        # Construct source manually to bypass __init__ check
        config = ExtractionConfig(
            source_id="test",
            source_type="youtube_boards",
            jurisdiction_id="school-test",
            base_url="https://youtube.com",
            metadata={"youtube_playlist": "PLtest1234567890"},
        )
        source = YouTubeBoardsSource(config, api_key="key")
        # Remove the playlist from config after construction
        source._config.metadata.pop("youtube_playlist")

        result = source.validate()
        assert result.config_valid is False
        assert "youtube_playlist" in result.errors[0]

    def test_health_delegates_to_client(self, config):
        source = YouTubeBoardsSource(config, api_key="test-key")

        service = MagicMock()
        pl_request = MagicMock()
        pl_request.execute.return_value = {
            "items": [
                {
                    "snippet": {"title": "Test", "channelTitle": "Test"},
                    "contentDetails": {"itemCount": 5},
                }
            ]
        }
        service.playlists.return_value.list.return_value = pl_request
        source.client._youtube_service = service

        health = source.health()
        assert health.is_available is True
        assert health.available_count == 5


# ============================================================================
# Factory Functions
# ============================================================================


class TestFactoryFunctions:
    def test_create_srcs_youtube_client(self):
        client = create_srcs_youtube_client(api_key="test-key")

        assert client._playlist_id == "PLyH9MVpaxhEJFfW0jWIbd5wGVQYUEZDcH"
        assert client._jurisdiction_id == "school-san-rafael"
        assert client._meeting_types == ["school_board", "special_meeting", "workshop"]
        assert client._channel_id == "@srcscommunications5656"
        assert client._api_key == "test-key"

    def test_create_srcs_youtube_source(self):
        with patch.object(ExtractionConfig, "from_jurisdiction") as mock_from_config:
            mock_from_config.return_value = ExtractionConfig(
                source_id="youtube-school-san-rafael",
                source_type="youtube_boards",
                jurisdiction_id="school-san-rafael",
                base_url="https://www.youtube.com",
                metadata={
                    "youtube_playlist": "PLyH9MVpaxhEJFfW0jWIbd5wGVQYUEZDcH",
                    "youtube_channel": "@srcscommunications5656",
                    "meeting_types": ["school_board", "special_meeting", "workshop"],
                },
            )
            result = create_srcs_youtube_source(api_key="test-key")

        assert result.source_id == "youtube-school-san-rafael"
        assert result.client._playlist_id == "PLyH9MVpaxhEJFfW0jWIbd5wGVQYUEZDcH"
        assert result.client._jurisdiction_id == "school-san-rafael"
        assert result.client._api_key == "test-key"
        assert result.client._meeting_types == ["school_board", "special_meeting", "workshop"]
