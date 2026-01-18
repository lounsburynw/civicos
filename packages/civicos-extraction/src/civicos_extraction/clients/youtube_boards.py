"""
YouTube Boards Client for extracting school board meeting videos.

Uses YouTube Data API v3 to extract meeting metadata from public playlists.
Designed for school boards that upload meetings to YouTube (e.g., SRCS).

API Quota Notes:
- Free tier: 10,000 units/day
- playlistItems.list: 1 unit per 50 items
- videos.list: 1 unit per 50 items
- Typical daily usage: ~4-10 units (well within limits)

Usage:
    client = YouTubeBoardsClient(
        playlist_id="PLyH9MVpaxhEJFfW0jWIbd5wGVQYUEZDcH",
        jurisdiction_id="school-san-rafael",
        api_key=os.getenv("YOUTUBE_API_KEY"),
    )
    meetings = client.get_meetings()

Or via config:
    source = YouTubeBoardsSource.from_jurisdiction("school-san-rafael")
    meetings = source.get_meetings()
"""

import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from civicos_extraction.clients.base import (
    DataSource,
    ExtractionConfig,
    HealthStatus,
    Meeting,
    ValidationResult,
)

logger = logging.getLogger(__name__)


@dataclass
class YouTubeVideo:
    """Raw YouTube video metadata before normalization."""

    video_id: str
    title: str
    description: str
    published_at: datetime
    duration_seconds: int
    thumbnail_url: Optional[str] = None
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None

    @property
    def watch_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


class YouTubeBoardsClient:
    """
    Client for extracting school board meetings from YouTube playlists.

    Implements DataSource protocol for unified health monitoring.
    """

    def __init__(
        self,
        playlist_id: str,
        jurisdiction_id: str,
        api_key: Optional[str] = None,
        meeting_types: Optional[List[str]] = None,
        channel_id: Optional[str] = None,
    ):
        """
        Initialize YouTube Boards client.

        Args:
            playlist_id: YouTube playlist ID (e.g., "PLyH9MVpaxhEJFfW0jWIbd5wGVQYUEZDcH")
            jurisdiction_id: Civic jurisdiction ID (e.g., "school-san-rafael")
            api_key: YouTube Data API v3 key (defaults to YOUTUBE_API_KEY env var)
            meeting_types: List of meeting types to tag (default: ["school_board"])
            channel_id: Optional channel ID for additional metadata
        """
        self._playlist_id = playlist_id
        self._jurisdiction_id = jurisdiction_id
        # Check YOUTUBE_API_KEY first, fall back to GOOGLE_API_KEY
        self._api_key = api_key or os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")
        self._meeting_types = meeting_types or ["school_board"]
        self._channel_id = channel_id
        self._youtube_service = None

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return f"youtube-{self._jurisdiction_id}"

    @property
    def source_type(self) -> str:
        """Type of source."""
        return "youtube_boards"

    @property
    def platform_name(self) -> str:
        """Human-readable platform name."""
        return "YouTube"

    def _get_service(self):
        """Get or create YouTube API service (lazy initialization)."""
        if self._youtube_service is None:
            if not self._api_key:
                raise ValueError(
                    "YOUTUBE_API_KEY not set. "
                    "Get a key from Google Cloud Console and add to .env"
                )
            self._youtube_service = build(
                "youtube", "v3", developerKey=self._api_key, cache_discovery=False
            )
        return self._youtube_service

    def health(self) -> HealthStatus:
        """
        Check source availability and return standardized status.

        Tests API connectivity by fetching playlist metadata.
        """
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        try:
            service = self._get_service()

            # Fetch playlist info to verify connectivity
            playlist_response = (
                service.playlists()
                .list(part="snippet,contentDetails", id=self._playlist_id)
                .execute()
            )

            if playlist_response.get("items"):
                playlist = playlist_response["items"][0]
                is_available = True
                available_count = playlist["contentDetails"]["itemCount"]
                metadata["playlist_title"] = playlist["snippet"]["title"]
                metadata["channel_title"] = playlist["snippet"]["channelTitle"]
            else:
                errors.append(f"Playlist not found: {self._playlist_id}")

        except HttpError as e:
            if "blocked" in str(e.reason).lower() or e.resp.status == 403:
                errors.append(
                    f"YouTube API error: {e.reason}. "
                    "Enable YouTube Data API v3 in Google Cloud Console for your API key."
                )
            else:
                errors.append(f"YouTube API error: {e.reason}")
        except ValueError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(f"Connection error: {str(e)}")

        check_duration_ms = (time.time() - start_time) * 1000

        return HealthStatus(
            source_id=self.source_id,
            source_type=self.source_type,
            jurisdiction_id=self._jurisdiction_id,
            is_available=is_available,
            available_count=available_count,
            last_checked=datetime.now(),
            check_duration_ms=round(check_duration_ms, 2),
            errors=errors,
            last_successful=datetime.now() if is_available else None,
            metadata=metadata,
        )

    def validate(self) -> ValidationResult:
        """
        Validate source configuration and API access before running pipeline.

        Preflight check for:
        - API key configuration
        - Playlist accessibility
        - Video availability
        """
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False
        metadata: Dict[str, Any] = {}

        # Check API key
        if not self._api_key:
            errors.append(
                "YOUTUBE_API_KEY not configured. "
                "Get a key from Google Cloud Console (YouTube Data API v3)"
            )
            config_valid = False

        # Check playlist ID format
        if not self._playlist_id or len(self._playlist_id) < 10:
            errors.append(f"Invalid playlist ID: {self._playlist_id}")
            config_valid = False

        # Check jurisdiction ID
        if not self._jurisdiction_id:
            errors.append("jurisdiction_id is required")
            config_valid = False

        # Test API reachability (only if config is valid)
        if config_valid:
            try:
                health = self.health()
                api_reachable = health.is_available
                metadata["video_count"] = health.available_count
                metadata.update(health.metadata)

                if not api_reachable:
                    errors.extend(health.errors)

                if health.available_count == 0:
                    warnings.append("Playlist is empty - no videos to extract")

            except Exception as e:
                errors.append(f"API check failed: {str(e)}")

        check_duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=config_valid,
            api_reachable=api_reachable,
            errors=errors,
            warnings=warnings,
            check_duration_ms=round(check_duration_ms, 2),
            metadata=metadata,
        )

    def get_playlist_items(self, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch all video IDs from the playlist.

        Args:
            max_results: Max items per API request (default 50, max allowed)

        Returns:
            List of playlist item dicts with video IDs and positions
        """
        service = self._get_service()
        items = []
        next_page_token = None

        while True:
            request = service.playlistItems().list(
                part="snippet,contentDetails",
                playlistId=self._playlist_id,
                maxResults=max_results,
                pageToken=next_page_token,
            )
            response = request.execute()

            items.extend(response.get("items", []))

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        logger.info(f"Fetched {len(items)} playlist items from {self._playlist_id}")
        return items

    def get_video_details(self, video_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch detailed metadata for videos (duration, etc.).

        Args:
            video_ids: List of video IDs to fetch

        Returns:
            List of video detail dicts
        """
        service = self._get_service()
        videos = []

        # API allows up to 50 video IDs per request
        for i in range(0, len(video_ids), 50):
            batch_ids = video_ids[i : i + 50]
            request = service.videos().list(
                part="snippet,contentDetails,statistics", id=",".join(batch_ids)
            )
            response = request.execute()
            videos.extend(response.get("items", []))

        return videos

    def _parse_duration(self, duration_str: str) -> int:
        """
        Parse ISO 8601 duration to seconds.

        Examples:
            PT1H30M45S -> 5445 seconds
            PT45M -> 2700 seconds
            PT30S -> 30 seconds
        """
        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration_str)
        if not match:
            return 0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return hours * 3600 + minutes * 60 + seconds

    def get_videos(self) -> List[YouTubeVideo]:
        """
        Fetch all videos from the playlist with full metadata.

        Returns:
            List of YouTubeVideo dataclass instances
        """
        # Get playlist items (just video IDs and basic info)
        playlist_items = self.get_playlist_items()

        if not playlist_items:
            return []

        # Extract video IDs
        video_ids = [
            item["contentDetails"]["videoId"]
            for item in playlist_items
            if "videoId" in item.get("contentDetails", {})
        ]

        # Get full video details (duration, etc.)
        video_details = self.get_video_details(video_ids)

        # Create a lookup by video ID
        details_map = {v["id"]: v for v in video_details}

        videos = []
        for item in playlist_items:
            video_id = item["contentDetails"].get("videoId")
            if not video_id or video_id not in details_map:
                continue

            detail = details_map[video_id]
            snippet = detail["snippet"]
            content = detail["contentDetails"]

            # Parse published date
            published_str = snippet.get("publishedAt", "")
            try:
                published_at = datetime.fromisoformat(
                    published_str.replace("Z", "+00:00")
                )
            except ValueError:
                published_at = datetime.now()

            # Parse duration
            duration_seconds = self._parse_duration(content.get("duration", "PT0S"))

            # Get best thumbnail
            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = (
                thumbnails.get("maxres", {}).get("url")
                or thumbnails.get("high", {}).get("url")
                or thumbnails.get("default", {}).get("url")
            )

            videos.append(
                YouTubeVideo(
                    video_id=video_id,
                    title=snippet.get("title", ""),
                    description=snippet.get("description", ""),
                    published_at=published_at,
                    duration_seconds=duration_seconds,
                    thumbnail_url=thumbnail_url,
                    channel_id=snippet.get("channelId"),
                    channel_title=snippet.get("channelTitle"),
                )
            )

        logger.info(f"Fetched {len(videos)} videos with full metadata")
        return videos

    def _extract_meeting_date(self, video: YouTubeVideo) -> Optional[datetime]:
        """
        Extract meeting date from video title or description.

        Patterns recognized:
        - "Board Meeting - January 15, 2026"
        - "01/15/2026"
        - "January 15, 2026"
        - Falls back to video publish date

        Args:
            video: YouTubeVideo with title and description

        Returns:
            Extracted meeting datetime or None
        """
        text = f"{video.title} {video.description}"

        # Pattern 1: "January 15, 2026" or "Jan 15, 2026"
        month_patterns = [
            r"(January|February|March|April|May|June|July|August|September|October|November|December|"
            r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s*(\d{4})",
        ]

        for pattern in month_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    date_str = f"{match.group(1)} {match.group(2)}, {match.group(3)}"
                    # Try full month name first
                    for fmt in ["%B %d, %Y", "%b %d, %Y"]:
                        try:
                            return datetime.strptime(date_str, fmt)
                        except ValueError:
                            continue
                except ValueError:
                    pass

        # Pattern 2: MM/DD/YYYY
        match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if match:
            try:
                return datetime.strptime(
                    f"{match.group(1)}/{match.group(2)}/{match.group(3)}", "%m/%d/%Y"
                )
            except ValueError:
                pass

        # Pattern 3: YYYY-MM-DD
        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if match:
            try:
                return datetime.strptime(
                    f"{match.group(1)}-{match.group(2)}-{match.group(3)}", "%Y-%m-%d"
                )
            except ValueError:
                pass

        # Fall back to publish date
        return video.published_at

    def _extract_meeting_type(self, title: str) -> str:
        """
        Extract meeting type from video title.

        Args:
            title: Video title

        Returns:
            Meeting type string (e.g., "school_board", "special_meeting")
        """
        title_lower = title.lower()

        if "special" in title_lower:
            return "special_meeting"
        if "workshop" in title_lower:
            return "workshop"
        if "study session" in title_lower:
            return "study_session"
        if "public hearing" in title_lower:
            return "public_hearing"
        if "board meeting" in title_lower or "board" in title_lower:
            return "school_board"

        # Default to first configured meeting type
        return self._meeting_types[0] if self._meeting_types else "school_board"

    def video_to_meeting(self, video: YouTubeVideo) -> Meeting:
        """
        Convert YouTubeVideo to normalized Meeting dataclass.

        Args:
            video: YouTubeVideo instance

        Returns:
            Meeting dataclass compatible with civic storage
        """
        meeting_date = self._extract_meeting_date(video)
        meeting_type = self._extract_meeting_type(video.title)

        # Generate stable meeting ID from video ID
        meeting_id = f"{self._jurisdiction_id}-youtube-{video.video_id}"

        return Meeting(
            id=meeting_id,
            title=video.title,
            meeting_datetime=meeting_date,
            jurisdiction_id=self._jurisdiction_id,
            meeting_type=meeting_type,
            status="completed",  # YouTube videos are recordings of past meetings
            location=None,
            virtual_url=None,
            agenda_url=None,
            minutes_url=None,
            video_url=video.watch_url,
            source_platform="youtube",
            source_url=video.watch_url,
            raw_data={
                "video_id": video.video_id,
                "description": video.description,
                "duration_seconds": video.duration_seconds,
                "published_at": video.published_at.isoformat(),
                "thumbnail_url": video.thumbnail_url,
                "channel_id": video.channel_id,
                "channel_title": video.channel_title,
            },
        )

    def get_meetings(
        self, days_ahead: int = 0, days_past: int = 365
    ) -> List[Meeting]:
        """
        Get normalized meetings from YouTube playlist.

        Args:
            days_ahead: Not used (YouTube has past meetings only)
            days_past: Only return meetings from the last N days

        Returns:
            List of Meeting dataclass instances
        """
        videos = self.get_videos()

        # Convert to meetings
        meetings = [self.video_to_meeting(video) for video in videos]

        # Filter by date range if specified
        if days_past > 0:
            cutoff = datetime.now().replace(tzinfo=None) - timedelta(days=days_past)
            meetings = [
                m
                for m in meetings
                if m.meeting_datetime and m.meeting_datetime.replace(tzinfo=None) >= cutoff
            ]

        # Sort by date descending (most recent first)
        # Normalize to naive datetime for comparison
        def sort_key(m):
            if m.meeting_datetime is None:
                return datetime.min
            dt = m.meeting_datetime
            return dt.replace(tzinfo=None) if dt.tzinfo else dt

        meetings.sort(key=sort_key, reverse=True)

        logger.info(
            f"Extracted {len(meetings)} meetings from YouTube playlist {self._playlist_id}"
        )
        return meetings


# Import here to avoid circular dependency
from datetime import timedelta


class YouTubeBoardsSource:
    """
    Config-driven wrapper for YouTubeBoardsClient implementing DataSource protocol.

    Loads extraction configuration from JSON files and creates a properly
    configured YouTubeBoardsClient. Provides config-driven setup for school
    board onboarding.

    Usage:
        source = YouTubeBoardsSource.from_jurisdiction("school-san-rafael")
        meetings = source.get_meetings()
    """

    def __init__(self, config: ExtractionConfig, api_key: Optional[str] = None):
        """
        Initialize YouTubeBoardsSource from an ExtractionConfig.

        Args:
            config: ExtractionConfig loaded from JSON
            api_key: Optional API key override (defaults to YOUTUBE_API_KEY env var)
        """
        self._config = config
        # Check YOUTUBE_API_KEY first, fall back to GOOGLE_API_KEY
        self._api_key = api_key or os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY")

        # Extract YouTube-specific config from metadata
        playlist_id = config.metadata.get("youtube_playlist")
        if not playlist_id:
            raise ValueError(
                f"youtube_playlist not found in config metadata for {config.jurisdiction_id}"
            )

        meeting_types = config.metadata.get("meeting_types", ["school_board"])
        channel_id = config.metadata.get("youtube_channel")

        self._client = YouTubeBoardsClient(
            playlist_id=playlist_id,
            jurisdiction_id=config.jurisdiction_id,
            api_key=self._api_key,
            meeting_types=meeting_types,
            channel_id=channel_id,
        )

    @classmethod
    def from_jurisdiction(
        cls, jurisdiction_id: str, api_key: Optional[str] = None
    ) -> "YouTubeBoardsSource":
        """
        Create YouTubeBoardsSource from jurisdiction ID, loading config from file.

        Args:
            jurisdiction_id: Jurisdiction ID (e.g., "school-san-rafael")
            api_key: Optional API key override

        Returns:
            Configured YouTubeBoardsSource
        """
        config = ExtractionConfig.from_jurisdiction(jurisdiction_id)
        return cls(config, api_key=api_key)

    @classmethod
    def from_config_file(
        cls, path: str, api_key: Optional[str] = None
    ) -> "YouTubeBoardsSource":
        """
        Create YouTubeBoardsSource from a specific config file path.

        Args:
            path: Path to extraction config JSON file
            api_key: Optional API key override

        Returns:
            Configured YouTubeBoardsSource
        """
        config = ExtractionConfig.from_file(path)
        return cls(config, api_key=api_key)

    @property
    def client(self) -> YouTubeBoardsClient:
        """Get the underlying YouTubeBoardsClient."""
        return self._client

    @property
    def config(self) -> ExtractionConfig:
        """Get the extraction configuration."""
        return self._config

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return self._client.source_id

    @property
    def source_type(self) -> str:
        """Type of source."""
        return self._client.source_type

    def health(self) -> HealthStatus:
        """Check source availability via underlying client."""
        return self._client.health()

    def validate(self) -> ValidationResult:
        """Validate source configuration and API access."""
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False
        metadata: Dict[str, Any] = {}

        # Check required config fields
        if not self._config.metadata.get("youtube_playlist"):
            errors.append("youtube_playlist is required in config metadata")
            config_valid = False

        if not self._config.jurisdiction_id:
            errors.append("jurisdiction_id is required")
            config_valid = False

        # Delegate API validation to client
        if config_valid:
            client_result = self._client.validate()
            api_reachable = client_result.api_reachable
            errors.extend(client_result.errors)
            warnings.extend(client_result.warnings)
            metadata.update(client_result.metadata)

        check_duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=config_valid,
            api_reachable=api_reachable,
            errors=errors,
            warnings=warnings,
            check_duration_ms=round(check_duration_ms, 2),
            metadata=metadata,
        )

    def get_meetings(
        self, days_ahead: int = 0, days_past: int = 365
    ) -> List[Meeting]:
        """Get normalized meetings from the underlying client."""
        return self._client.get_meetings(days_ahead=days_ahead, days_past=days_past)


def create_srcs_youtube_client(api_key: Optional[str] = None) -> YouTubeBoardsClient:
    """
    Create a YouTubeBoardsClient for San Rafael City Schools.

    Convenience factory function for quick access to SRCS YouTube meetings.

    Args:
        api_key: Optional API key override (defaults to YOUTUBE_API_KEY env var)

    Returns:
        Configured YouTubeBoardsClient
    """
    return YouTubeBoardsClient(
        playlist_id="PLyH9MVpaxhEJFfW0jWIbd5wGVQYUEZDcH",
        jurisdiction_id="school-san-rafael",
        api_key=api_key,
        meeting_types=["school_board", "special_meeting", "workshop"],
        channel_id="@srcscommunications5656",
    )


def create_srcs_youtube_source(api_key: Optional[str] = None) -> YouTubeBoardsSource:
    """
    Create a YouTubeBoardsSource for San Rafael City Schools.

    Convenience factory function that loads config from file.

    Args:
        api_key: Optional API key override (defaults to YOUTUBE_API_KEY env var)

    Returns:
        Configured YouTubeBoardsSource
    """
    return YouTubeBoardsSource.from_jurisdiction("school-san-rafael", api_key=api_key)
