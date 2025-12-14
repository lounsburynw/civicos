"""
Base extractor protocol and common types.

Defines the interface that all platform clients should implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any, Protocol, runtime_checkable


@dataclass
class Meeting:
    """
    Normalized meeting data structure.

    This is the common format that all extractors should produce,
    compatible with civic-app-schema.json.
    """
    id: str
    title: str
    meeting_datetime: datetime
    jurisdiction_id: str
    meeting_type: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    virtual_url: Optional[str] = None
    agenda_url: Optional[str] = None
    minutes_url: Optional[str] = None
    video_url: Optional[str] = None
    source_platform: str = "unknown"
    source_url: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "meeting_datetime": self.meeting_datetime.isoformat() if self.meeting_datetime else None,
            "jurisdiction_id": self.jurisdiction_id,
            "meeting_type": self.meeting_type,
            "status": self.status,
            "location": self.location,
            "virtual_url": self.virtual_url,
            "agenda_url": self.agenda_url,
            "minutes_url": self.minutes_url,
            "video_url": self.video_url,
            "source_platform": self.source_platform,
            "source_url": self.source_url,
        }


@runtime_checkable
class Extractor(Protocol):
    """
    Protocol defining the interface for platform extractors.

    All platform clients should implement this interface.
    """

    def get_events(
        self,
        days_ahead: int = 90,
        days_past: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Extract events/meetings from the platform.

        Args:
            days_ahead: Number of days into the future to fetch
            days_past: Number of days into the past to fetch

        Returns:
            List of event dictionaries in platform-native format
        """
        ...

    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """
        Normalize a platform-native event to the Meeting format.

        Args:
            event: Event dictionary from get_events()

        Returns:
            Normalized Meeting object
        """
        ...


class BaseExtractor(ABC):
    """
    Abstract base class for platform extractors.

    Provides common functionality like throttling, retries, and error handling.
    """

    def __init__(self, jurisdiction_id: str):
        """
        Initialize the extractor.

        Args:
            jurisdiction_id: Identifier for the jurisdiction (e.g., "city-berkeley")
        """
        self.jurisdiction_id = jurisdiction_id

    @abstractmethod
    def get_events(
        self,
        days_ahead: int = 90,
        days_past: int = 0
    ) -> List[Dict[str, Any]]:
        """Extract events from the platform."""
        pass

    @abstractmethod
    def normalize_event(self, event: Dict[str, Any]) -> Meeting:
        """Normalize event to Meeting format."""
        pass

    def get_meetings(
        self,
        days_ahead: int = 90,
        days_past: int = 0
    ) -> List[Meeting]:
        """
        Get normalized meetings.

        Convenience method that extracts and normalizes in one call.

        Args:
            days_ahead: Days into future
            days_past: Days into past

        Returns:
            List of normalized Meeting objects
        """
        events = self.get_events(days_ahead=days_ahead, days_past=days_past)
        return [self.normalize_event(e) for e in events]

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the platform name (e.g., 'legistar', 'civicclerk')."""
        pass
