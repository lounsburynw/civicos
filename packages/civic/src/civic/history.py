"""
History Module - what_happened() implementation

Searches past decisions using civic-state.
Supports semantic search via embeddings for jurisdictions with vector indexes.
"""

import json
import os
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime

from civic._internal.state import StateManager
from civic._internal.jurisdiction import normalize_jurisdiction


@dataclass
class Decision:
    """A past decision."""
    id: str
    title: str
    date: datetime
    outcome: str
    body: str
    votes: Optional[dict] = None


@dataclass
class TranscriptSearchResult:
    """A video transcript search result."""
    id: str
    text: str
    speaker: str
    speaker_role: Optional[str] = None
    speaker_name: Optional[str] = None
    video_id: str = ""
    start_timestamp: str = ""
    end_timestamp: str = ""
    start_ms: int = 0
    end_ms: int = 0
    is_public_comment: bool = False
    score: float = 0.0


@dataclass
class HybridSearchResult:
    """
    A combined search result from both PDF and video transcript sources.

    Links official documents (staff reports, agenda packets) with meeting
    discussion (public testimony, council deliberation) for complete context.
    """
    id: str
    text: str
    source_type: str  # "pdf" or "transcript"
    score: float

    # PDF-specific fields
    agenda_item: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None

    # Transcript-specific fields
    speaker: Optional[str] = None
    speaker_role: Optional[str] = None
    speaker_name: Optional[str] = None
    video_id: Optional[str] = None
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    is_public_comment: bool = False

    @property
    def video_url(self) -> Optional[str]:
        """Generate YouTube URL with timestamp if video_id is available."""
        if not self.video_id or not self.start_ms:
            return None
        seconds = self.start_ms // 1000
        return f"https://www.youtube.com/watch?v={self.video_id}&t={seconds}s"


def _jurisdiction_has_embeddings(jurisdiction: str) -> bool:
    """
    Check if a jurisdiction has a vector index available.

    Args:
        jurisdiction: Jurisdiction ID (e.g., "city-san-rafael" or "san-rafael")

    Returns:
        True if vector index exists for this jurisdiction
    """
    # Normalize jurisdiction ID to canonical format
    jurisdiction = normalize_jurisdiction(jurisdiction)

    # Check for path: data/pilot/vectors/{jurisdiction}/
    path = f"data/pilot/vectors/{jurisdiction}"
    return os.path.exists(path)


def _get_embeddings_path(jurisdiction: str) -> Optional[str]:
    """
    Get the embeddings path for a jurisdiction.

    Args:
        jurisdiction: Jurisdiction ID (e.g., "city-san-rafael" or "san-rafael")

    Returns:
        Path to vector index, or None if not available
    """
    # Normalize jurisdiction ID to canonical format
    jurisdiction = normalize_jurisdiction(jurisdiction)

    # Check for path: data/pilot/vectors/{jurisdiction}/
    path = f"data/pilot/vectors/{jurisdiction}"
    if os.path.exists(path):
        return path

    return None


def _search_semantic_decisions(
    jurisdiction: str,
    query: str,
    top_k: int = 10,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
) -> List[Decision]:
    """
    Search decisions using vector embeddings for a jurisdiction.

    Args:
        jurisdiction: Jurisdiction ID (e.g., "city-san-rafael")
        query: Search query
        top_k: Maximum number of results
        since: Optional minimum meeting date
        until: Optional maximum meeting date

    Returns:
        List of Decision objects from semantic search
    """
    try:
        from civic._internal.meetings.embeddings import CivicEmbeddings
    except ImportError:
        return []

    # Get the embeddings path for this jurisdiction
    persist_directory = _get_embeddings_path(jurisdiction)
    if persist_directory is None:
        return []

    # Convert dates to Unix timestamps for ChromaDB filtering
    since_ts = int(since.timestamp()) if since else None
    until_ts = int(until.timestamp()) if until else None

    try:
        embedder = CivicEmbeddings(
            jurisdiction_id=jurisdiction,
            persist_directory=persist_directory,
        )
        results = embedder.search_decisions(
            query, top_k=top_k, since_ts=since_ts, until_ts=until_ts
        )
    except Exception:
        # Index may not exist or other error
        return []

    decisions = []
    for r in results:
        # Parse meeting date from metadata
        meeting_date_str = r.metadata.get("meeting_date", "")
        try:
            meeting_date = datetime.fromisoformat(meeting_date_str)
        except (ValueError, TypeError):
            meeting_date = datetime.now()

        # Extract vote info from metadata
        votes = None
        if r.metadata.get("vote_count"):
            votes = {
                "vote_count": r.metadata.get("vote_count"),
                "passed": r.metadata.get("vote_passed"),
                "unanimous": r.metadata.get("vote_unanimous"),
            }

        decisions.append(Decision(
            id=r.document_id,
            title=r.metadata.get("title", ""),
            date=meeting_date,
            outcome=r.metadata.get("outcome", "unknown"),
            body="City Council",
            votes=votes,
        ))

    # Sort by date (most recent first for timeline)
    decisions.sort(key=lambda d: d.date, reverse=True)

    return decisions


def _search_transcripts(
    jurisdiction: str,
    query: str,
    top_k: int = 5,
    speaker_role: Optional[str] = None,
    public_comment_only: bool = False,
) -> List[TranscriptSearchResult]:
    """
    Search video transcripts using vector embeddings for a jurisdiction.

    Args:
        jurisdiction: Jurisdiction ID (e.g., "city-san-rafael")
        query: Search query
        top_k: Maximum number of results
        speaker_role: Filter by speaker role (e.g., "council", "staff", "public")
        public_comment_only: If True, only return chunks from public comment sections

    Returns:
        List of TranscriptSearchResult objects
    """
    try:
        from civic._internal.meetings.embeddings import CivicEmbeddings
    except ImportError:
        return []

    # Get the embeddings path for this jurisdiction
    persist_directory = _get_embeddings_path(jurisdiction)
    if persist_directory is None:
        return []

    try:
        embedder = CivicEmbeddings(
            jurisdiction_id=jurisdiction,
            persist_directory=persist_directory,
        )

        # Check if transcripts are available
        if not embedder.has_transcripts():
            return []

        results = embedder.search_transcripts(
            query,
            top_k=top_k,
            speaker_role=speaker_role,
            public_comment_only=public_comment_only,
        )
    except Exception:
        # Index may not exist or other error
        return []

    transcript_results = []
    for r in results:
        transcript_results.append(TranscriptSearchResult(
            id=r.document_id,
            text=r.text,
            speaker=r.metadata.get("speaker", "?"),
            speaker_role=r.metadata.get("speaker_role"),
            speaker_name=r.metadata.get("speaker_name"),
            video_id=r.metadata.get("video_id", ""),
            start_timestamp=r.metadata.get("start_timestamp", "00:00:00"),
            end_timestamp=r.metadata.get("end_timestamp", ""),
            start_ms=r.metadata.get("start_ms", 0),
            end_ms=r.metadata.get("end_ms", 0),
            is_public_comment=r.metadata.get("is_public_comment", False),
            score=r.score,
        ))

    return transcript_results


# Legacy alias for backward compatibility
def _search_merrydale_decisions(query: str, top_k: int = 10) -> List[Decision]:
    """
    DEPRECATED: Search Merrydale decisions using vector embeddings.

    This function is maintained for backward compatibility.
    Use _search_semantic_decisions("city-san-rafael", query) instead.
    """
    return _search_semantic_decisions("city-san-rafael", query, top_k)


def search_transcripts(
    jurisdiction: str,
    query: str,
    top_k: int = 5,
    speaker_role: Optional[str] = None,
    public_comment_only: bool = False,
) -> List[TranscriptSearchResult]:
    """
    Search video transcripts for a jurisdiction.

    Public API for searching video transcripts. Returns TranscriptSearchResult
    objects with speaker info, timestamps, and video links.

    Args:
        jurisdiction: City/jurisdiction ID (e.g., "city-san-rafael")
        query: Search query
        top_k: Maximum number of results
        speaker_role: Filter by speaker role (e.g., "council", "staff", "public")
        public_comment_only: If True, only return chunks from public comment sections

    Returns:
        List of TranscriptSearchResult objects
    """
    return _search_transcripts(
        jurisdiction,
        query,
        top_k,
        speaker_role=speaker_role,
        public_comment_only=public_comment_only,
    )


def _search_hybrid(
    jurisdiction: str,
    query: str,
    top_k: int = 10,
    agenda_item: Optional[str] = None,
    interleave: bool = True,
) -> List[HybridSearchResult]:
    """
    Search both PDF chunks and video transcripts for a jurisdiction.

    Internal implementation that combines results from agenda packet/staff
    report chunks (PDF source) and meeting transcript chunks (video source).

    Args:
        jurisdiction: Jurisdiction ID (e.g., "city-san-rafael")
        query: Search query
        top_k: Maximum total results to return
        agenda_item: Optional agenda item filter (e.g., "6.a")
        interleave: If True (default), interleave results by score

    Returns:
        List of HybridSearchResult objects
    """
    try:
        from civic._internal.meetings.embeddings import CivicEmbeddings
    except ImportError:
        return []

    # Get the embeddings path for this jurisdiction
    persist_directory = _get_embeddings_path(jurisdiction)
    if persist_directory is None:
        return []

    try:
        embedder = CivicEmbeddings(
            jurisdiction_id=jurisdiction,
            persist_directory=persist_directory,
        )
        results = embedder.search_hybrid_pdf_video(
            query,
            top_k=top_k,
            agenda_item=agenda_item,
            interleave=interleave,
        )
    except Exception:
        return []

    hybrid_results = []
    for r in results:
        source_type = r.metadata.get("source_type", "pdf")

        hybrid_results.append(HybridSearchResult(
            id=r.document_id,
            text=r.text,
            source_type=source_type,
            score=r.score,
            # PDF fields
            agenda_item=r.metadata.get("agenda_item"),
            page_start=r.metadata.get("page_start"),
            page_end=r.metadata.get("page_end"),
            # Transcript fields
            speaker=r.metadata.get("speaker"),
            speaker_role=r.metadata.get("speaker_role"),
            speaker_name=r.metadata.get("speaker_name"),
            video_id=r.metadata.get("video_id"),
            start_timestamp=r.metadata.get("start_timestamp"),
            end_timestamp=r.metadata.get("end_timestamp"),
            start_ms=r.metadata.get("start_ms"),
            end_ms=r.metadata.get("end_ms"),
            is_public_comment=r.metadata.get("is_public_comment", False),
        ))

    return hybrid_results


def search_hybrid(
    jurisdiction: str,
    query: str,
    top_k: int = 10,
    agenda_item: Optional[str] = None,
    interleave: bool = True,
) -> List[HybridSearchResult]:
    """
    Search both PDF documents and video transcripts for a jurisdiction.

    Combines results from official documents (agenda packets, staff reports)
    and meeting transcripts (public testimony, council discussion) to provide
    a complete picture of what was written AND what was said.

    Args:
        jurisdiction: City/jurisdiction ID (e.g., "city-san-rafael")
        query: Search query (e.g., "homeless shelter funding")
        top_k: Maximum number of results (default 10)
        agenda_item: Optional agenda item filter (e.g., "6.a") to get
                    related content from both PDFs and transcripts
        interleave: If True (default), interleave PDF and transcript results
                   by relevance score. If False, group by source type.

    Returns:
        List of HybridSearchResult objects with source attribution

    Example:
        >>> from civic.history import search_hybrid
        >>> results = search_hybrid("city-san-rafael", "shelter funding", top_k=5)
        >>> for r in results:
        ...     if r.source_type == "pdf":
        ...         print(f"[PDF p{r.page_start}] {r.text[:100]}")
        ...     else:
        ...         print(f"[Video @{r.start_timestamp}] {r.speaker}: {r.text[:100]}")
    """
    return _search_hybrid(
        jurisdiction,
        query,
        top_k=top_k,
        agenda_item=agenda_item,
        interleave=interleave,
    )


def search_decisions(
    state_manager: StateManager,
    jurisdiction: str,
    query: str,
    since: str = None
) -> List[Decision]:
    """
    Search past decisions.

    Uses civic-state for meeting/decision history.
    Uses semantic search via embeddings for jurisdictions with vector indexes.

    Args:
        state_manager: StateManager instance
        jurisdiction: City/jurisdiction ID
        query: Search query
        since: Optional date filter (ISO format)

    Returns:
        List of matching decisions
    """
    # Check if jurisdiction has embeddings - use semantic search
    if _jurisdiction_has_embeddings(jurisdiction):
        # Semantic search for jurisdictions with vector indexes
        return _search_semantic_decisions(jurisdiction, query)

    # Standard search: Basic keyword matching implementation

    # Get historical state
    city_state = state_manager.get_city_state(jurisdiction)
    if not city_state:
        return []

    decisions = []
    query_lower = query.lower()

    # Search through meetings for decisions
    meetings = city_state.get("meetings", [])
    for meeting in meetings:
        # Get meeting date
        meeting_date = meeting.get("meeting_datetime") or meeting.get("date")
        if isinstance(meeting_date, str):
            try:
                meeting_date = datetime.fromisoformat(meeting_date.replace('Z', '+00:00'))
            except ValueError:
                meeting_date = datetime.now()
        elif meeting_date is None:
            meeting_date = datetime.now()

        # Apply date filter if provided
        if since:
            try:
                since_date = datetime.fromisoformat(since.replace('Z', '+00:00'))
                if meeting_date.tzinfo is None:
                    from datetime import timezone
                    meeting_date = meeting_date.replace(tzinfo=timezone.utc)
                if since_date.tzinfo is None:
                    since_date = since_date.replace(tzinfo=timezone.utc)
                if meeting_date < since_date:
                    continue
            except ValueError:
                pass  # Invalid since format, skip filter

        # Get agenda items from full_data if available
        # Handle nested full_data structure from StateManager
        full_data = meeting.get("full_data", {})
        if isinstance(full_data, str):
            try:
                full_data = json.loads(full_data)
            except (json.JSONDecodeError, TypeError):
                full_data = {}

        # Check for nested full_data (StateManager stores metadata + original full_data)
        if "full_data" in full_data and isinstance(full_data.get("full_data"), str):
            try:
                inner_full_data = json.loads(full_data["full_data"])
                agenda_items = inner_full_data.get("agenda_items", [])
            except (json.JSONDecodeError, TypeError):
                agenda_items = full_data.get("agenda_items", meeting.get("agenda_items", []))
        else:
            agenda_items = full_data.get("agenda_items", meeting.get("agenda_items", []))

        for item in agenda_items:
            title = item.get("title", "")
            description = item.get("description", "")

            # Basic keyword matching in title or description
            if query_lower in title.lower() or query_lower in description.lower():
                decisions.append(Decision(
                    id=item.get("id", item.get("item_number", "")),
                    title=title,
                    date=meeting_date,
                    outcome=item.get("outcome", "unknown"),
                    body=meeting.get("meeting_type", meeting.get("body", "")),
                    votes=item.get("votes"),
                ))

    # Sort by date descending (most recent first)
    decisions.sort(key=lambda d: d.date, reverse=True)

    return decisions
