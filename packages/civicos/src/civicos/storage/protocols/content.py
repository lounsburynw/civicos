"""
ContentStorage protocol for meeting-related content.

Handles meetings, decisions, chunks (PDF segments), agenda items,
transcripts, and videos. This is the core content for civic data.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ContentStorage(Protocol):
    """
    Protocol for meeting-related content storage.

    Covers the core content types for civic meetings:
    - Meetings: City council, planning commission, etc.
    - Decisions: Votes and outcomes from meetings
    - Chunks: PDF text segments from agenda packets
    - Agenda Items: Structured entries from meeting agendas
    - Transcripts: AssemblyAI-processed meeting audio
    - Videos: YouTube recordings of meetings

    All methods use temporal versioning with as_of parameter.
    """

    # ========== Meeting Methods ==========

    def store_meetings(
        self,
        jurisdiction_id: str,
        meetings: List[Any],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store meetings with temporal versioning (upsert pattern)."""
        ...

    def get_meetings(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve meetings with optional temporal query."""
        ...

    def update_meeting(
        self,
        jurisdiction_id: str,
        meeting_id: str,
        updates: Dict[str, Any],
    ) -> bool:
        """Update specific fields on a meeting record."""
        ...

    def delete_meetings(
        self,
        jurisdiction_id: str,
        meeting_ids: Optional[List[str]] = None,
    ) -> int:
        """Delete meetings (soft delete with temporal versioning)."""
        ...

    # ========== Decision Methods ==========

    def store_decisions(
        self,
        jurisdiction_id: str,
        decisions: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store decisions with temporal versioning."""
        ...

    def get_decisions(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve decisions with optional filtering."""
        ...

    def get_decision_count(self, jurisdiction_id: str) -> int:
        """Get count of current decisions for a jurisdiction."""
        ...

    # ========== Chunk Methods ==========

    def store_chunks(
        self,
        jurisdiction_id: str,
        chunks: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
        meeting_id: Optional[str] = None,
    ) -> int:
        """Store PDF chunks with temporal versioning."""
        ...

    def get_chunks(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        meeting_id: Optional[str] = None,
        agenda_item: Optional[str] = None,
        source_type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve chunks with optional filtering."""
        ...

    def get_chunk_count(self, jurisdiction_id: str) -> int:
        """Get count of current chunks for a jurisdiction."""
        ...

    # ========== Agenda Item Methods ==========

    def store_agenda_items(
        self,
        meeting_id: str,
        agenda_items: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store agenda items with temporal versioning."""
        ...

    def get_agenda_items(
        self,
        meeting_id: Optional[str] = None,
        jurisdiction_id: Optional[str] = None,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve agenda items with optional filtering."""
        ...

    def get_agenda_item_count(self, jurisdiction_id: Optional[str] = None) -> int:
        """Get count of current agenda items."""
        ...

    # ========== Transcript Methods ==========

    def store_transcripts(
        self,
        jurisdiction_id: str,
        transcripts: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store AssemblyAI transcripts with temporal versioning."""
        ...

    def get_transcripts(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve transcripts with temporal filtering."""
        ...

    def get_transcript(
        self,
        video_id: str,
        as_of: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get specific transcript by video_id."""
        ...

    def get_transcript_count(self, jurisdiction_id: str) -> int:
        """Get count of current transcripts for a jurisdiction."""
        ...

    # ========== Video Methods ==========

    def store_videos(
        self,
        jurisdiction_id: str,
        videos: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store YouTube video metadata with temporal versioning."""
        ...

    def get_videos(
        self,
        jurisdiction_id: str,
        as_of: Optional[datetime] = None,
        limit: Optional[int] = None,
        meeting_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve videos with temporal filtering.

        Args:
            jurisdiction_id: Source jurisdiction
            as_of: Point-in-time query (for temporal versioning)
            limit: Maximum number of videos to return
            meeting_type: Filter by meeting type (joins with meetings table via meeting_id)
        """
        ...

    def get_video_count(self, jurisdiction_id: str) -> int:
        """Get count of current videos for a jurisdiction."""
        ...

    def get_video_meeting_mapping(
        self,
        jurisdiction_id: str,
    ) -> Dict[str, str]:
        """
        Get mapping of video IDs to meeting IDs.

        Used by vector indexing to resolve transcript video_ids to meeting_ids.
        Only returns videos that have a linked meeting_id.

        Args:
            jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")

        Returns:
            Dict mapping video_id -> meeting_id for videos with meeting links
        """
        ...
