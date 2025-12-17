"""
History Module - what_happened() implementation

Searches past decisions using civic-state.
Supports semantic search via embeddings for jurisdictions with vector indexes.
"""

import json
import os
from typing import Optional, List, Tuple
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
class UnifiedSearchResult:
    """
    A unified search result that can represent content from any corpus.

    This is the canonical result type for cross-corpus queries, supporting
    results from: decisions, chunks (PDF), transcripts (video), issues
    (SeeClickFix), municipal_code, and legislation.

    The source_type field indicates which corpus the result came from, and
    source-specific fields are populated accordingly (others are None/default).

    Source Types:
        - "decision": City council decision/agenda item
        - "pdf": PDF chunk from agenda packet or staff report
        - "transcript": Video transcript chunk from meeting recording
        - "issue": SeeClickFix community issue report
        - "municipal_code": Municipal code section
        - "state_legislation": State bill (e.g., CA SB-35)
        - "federal_program": Federal grant program (e.g., CDBG)

    Example:
        >>> results = civic.search_all("homeless shelter")
        >>> for r in results:
        ...     if r.source_type == "decision":
        ...         print(f"Decision: {r.title} ({r.outcome})")
        ...     elif r.source_type == "transcript":
        ...         print(f"Video @{r.start_timestamp}: {r.speaker}: {r.text[:50]}")
        ...     elif r.source_type == "issue":
        ...         print(f"Issue: {r.title} at {r.address}")
        ...     elif r.source_type == "state_legislation":
        ...         print(f"Bill: {r.bill_id} - {r.title} (topic: {r.topic})")
        ...     elif r.source_type == "federal_program":
        ...         print(f"Program: {r.program_id} - {r.title}")
    """
    # Core fields (present for all source types)
    id: str
    text: str
    source_type: str  # "decision", "pdf", "transcript", "issue", "municipal_code"
    score: float

    # Decision-specific fields
    title: Optional[str] = None
    date: Optional[str] = None  # ISO format date
    outcome: Optional[str] = None
    body: Optional[str] = None  # Meeting body (e.g., "City Council")
    votes: Optional[dict] = None

    # PDF chunk-specific fields
    agenda_item: Optional[str] = None
    page_start: Optional[int] = None
    page_end: Optional[int] = None

    # Transcript-specific fields
    speaker: Optional[str] = None
    speaker_role: Optional[str] = None  # "council", "staff", "public"
    speaker_name: Optional[str] = None
    video_id: Optional[str] = None
    start_timestamp: Optional[str] = None  # HH:MM:SS format
    end_timestamp: Optional[str] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    is_public_comment: bool = False

    # Issue-specific fields (SeeClickFix)
    issue_type: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: Optional[str] = None  # "open", "acknowledged", "closed"

    # Municipal code-specific fields
    section_number: Optional[str] = None
    chapter: Optional[str] = None
    title_number: Optional[str] = None

    # Legislation-specific fields (state bills + federal programs)
    topic: Optional[str] = None  # e.g., "housing", "transportation"
    official_url: Optional[str] = None  # Link to official source

    # State legislation fields
    bill_id: Optional[str] = None  # e.g., "ca-sb-35"
    enacted: Optional[str] = None  # e.g., "2017"
    local_deadline: Optional[str] = None  # Compliance deadline
    local_implementation_required: bool = False

    # Federal program fields
    program_id: Optional[str] = None  # e.g., "cdbg"
    administering_agency: Optional[str] = None  # e.g., "HUD"
    local_compliance_required: bool = False
    annual_reporting: bool = False

    @property
    def video_url(self) -> Optional[str]:
        """Generate YouTube URL with timestamp if video_id is available."""
        if not self.video_id or not self.start_ms:
            return None
        seconds = self.start_ms // 1000
        return f"https://www.youtube.com/watch?v={self.video_id}&t={seconds}s"

    @classmethod
    def from_decision(cls, decision: "Decision", score: float = 1.0) -> "UnifiedSearchResult":
        """Create UnifiedSearchResult from a Decision object."""
        return cls(
            id=decision.id,
            text=decision.title,
            source_type="decision",
            score=score,
            title=decision.title,
            date=decision.date.isoformat() if decision.date else None,
            outcome=decision.outcome,
            body=decision.body,
            votes=decision.votes,
        )

    @classmethod
    def from_transcript_result(
        cls, result: "TranscriptSearchResult"
    ) -> "UnifiedSearchResult":
        """Create UnifiedSearchResult from a TranscriptSearchResult."""
        return cls(
            id=result.id,
            text=result.text,
            source_type="transcript",
            score=result.score,
            speaker=result.speaker,
            speaker_role=result.speaker_role,
            speaker_name=result.speaker_name,
            video_id=result.video_id,
            start_timestamp=result.start_timestamp,
            end_timestamp=result.end_timestamp,
            start_ms=result.start_ms,
            end_ms=result.end_ms,
            is_public_comment=result.is_public_comment,
        )

    @classmethod
    def from_embeddings_result(
        cls, result, source_type: str
    ) -> "UnifiedSearchResult":
        """
        Create UnifiedSearchResult from a CivicEmbeddings SearchResult.

        Args:
            result: SearchResult from CivicEmbeddings.search_*()
            source_type: One of "decision", "pdf", "transcript", "issue",
                        "municipal_code", "state_legislation", "federal_program"

        Returns:
            UnifiedSearchResult with appropriate fields populated
        """
        metadata = result.metadata or {}

        base_kwargs = {
            "id": result.document_id,
            "text": result.text,
            "source_type": source_type,
            "score": result.score,
        }

        if source_type == "decision":
            base_kwargs.update({
                "title": metadata.get("title"),
                "date": metadata.get("meeting_date"),
                "outcome": metadata.get("outcome"),
                "votes": {
                    "vote_count": metadata.get("vote_count"),
                    "passed": metadata.get("vote_passed"),
                    "unanimous": metadata.get("vote_unanimous"),
                } if metadata.get("vote_count") else None,
            })
        elif source_type == "pdf":
            base_kwargs.update({
                "agenda_item": metadata.get("agenda_item"),
                "page_start": metadata.get("page_start"),
                "page_end": metadata.get("page_end"),
            })
        elif source_type == "transcript":
            base_kwargs.update({
                "speaker": metadata.get("speaker"),
                "speaker_role": metadata.get("speaker_role"),
                "speaker_name": metadata.get("speaker_name"),
                "video_id": metadata.get("video_id"),
                "start_timestamp": metadata.get("start_timestamp"),
                "end_timestamp": metadata.get("end_timestamp"),
                "start_ms": metadata.get("start_ms"),
                "end_ms": metadata.get("end_ms"),
                "is_public_comment": metadata.get("is_public_comment", False),
            })
        elif source_type == "issue":
            base_kwargs.update({
                "title": metadata.get("title"),
                "issue_type": metadata.get("issue_type"),
                "address": metadata.get("address"),
                "latitude": metadata.get("latitude"),
                "longitude": metadata.get("longitude"),
                "status": metadata.get("status"),
            })
        elif source_type == "municipal_code":
            base_kwargs.update({
                "title": metadata.get("title"),
                "section_number": metadata.get("section_number"),
                "chapter": metadata.get("chapter"),
                "title_number": metadata.get("title_number"),
            })
        elif source_type == "state_legislation":
            base_kwargs.update({
                "title": metadata.get("bill_name"),
                "bill_id": metadata.get("bill_id"),
                "topic": metadata.get("topic"),
                "status": metadata.get("status"),
                "enacted": metadata.get("enacted"),
                "local_deadline": metadata.get("local_deadline"),
                "local_implementation_required": metadata.get("local_implementation_required", False),
                "official_url": metadata.get("official_url"),
            })
        elif source_type == "federal_program":
            base_kwargs.update({
                "title": metadata.get("program_name"),
                "program_id": metadata.get("program_id"),
                "topic": metadata.get("topic"),
                "administering_agency": metadata.get("administering_agency"),
                "local_compliance_required": metadata.get("local_compliance_required", False),
                "annual_reporting": metadata.get("annual_reporting", False),
                "official_url": metadata.get("official_url"),
            })

        return cls(**base_kwargs)


@dataclass
class HybridSearchResult:
    """
    A combined search result from both PDF and video transcript sources.

    Links official documents (staff reports, agenda packets) with meeting
    discussion (public testimony, council deliberation) for complete context.

    Note: Consider using UnifiedSearchResult for new code. HybridSearchResult
    is maintained for backward compatibility with existing what_happened_with_discussion().
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

    def to_unified(self) -> UnifiedSearchResult:
        """Convert to UnifiedSearchResult for cross-corpus compatibility."""
        return UnifiedSearchResult(
            id=self.id,
            text=self.text,
            source_type=self.source_type,
            score=self.score,
            agenda_item=self.agenda_item,
            page_start=self.page_start,
            page_end=self.page_end,
            speaker=self.speaker,
            speaker_role=self.speaker_role,
            speaker_name=self.speaker_name,
            video_id=self.video_id,
            start_timestamp=self.start_timestamp,
            end_timestamp=self.end_timestamp,
            start_ms=self.start_ms,
            end_ms=self.end_ms,
            is_public_comment=self.is_public_comment,
        )


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


@dataclass
class TranscriptLink:
    """A link from a decision to a transcript excerpt."""
    chunk_id: str
    text: str
    speaker: str
    speaker_role: Optional[str] = None
    speaker_name: Optional[str] = None
    video_id: Optional[str] = None
    start_timestamp: Optional[str] = None
    end_timestamp: Optional[str] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    is_public_comment: bool = False
    agenda_item: Optional[str] = None
    confidence: float = 0.0

    @property
    def video_url(self) -> Optional[str]:
        """Generate YouTube URL with timestamp if video_id is available."""
        if not self.video_id or not self.start_ms:
            return None
        seconds = self.start_ms // 1000
        return f"https://www.youtube.com/watch?v={self.video_id}&t={seconds}s"


@dataclass
class DecisionWithContext:
    """
    A decision enriched with linked transcript excerpts.

    Combines the official decision (from minutes) with relevant transcript
    excerpts (from meeting video) showing what was said during discussion.

    The transcript_links are ordered by relevance and include:
    - Public testimony on the item
    - Staff presentations
    - Council deliberation

    Example:
        >>> results = civic.what_happened_full_context("bike lanes")
        >>> for r in results:
        ...     print(f"Decision: {r.decision.title} - {r.decision.outcome}")
        ...     for link in r.transcript_links:
        ...         print(f"  [{link.speaker_role}] {link.text[:80]}...")
    """
    decision: Decision
    transcript_links: List[TranscriptLink]
    link_confidence: float = 0.0  # Overall confidence of decision-transcript linking
    link_type: str = ""  # "consensus", "structural_only", "semantic_only", "none"

    @property
    def has_transcript(self) -> bool:
        """Whether any transcript excerpts were found."""
        return len(self.transcript_links) > 0

    @property
    def public_comments(self) -> List[TranscriptLink]:
        """Get only public comment excerpts."""
        return [link for link in self.transcript_links if link.is_public_comment]

    @property
    def staff_discussion(self) -> List[TranscriptLink]:
        """Get only staff presentation excerpts."""
        return [link for link in self.transcript_links if link.speaker_role == "staff"]

    @property
    def council_discussion(self) -> List[TranscriptLink]:
        """Get only council deliberation excerpts."""
        return [link for link in self.transcript_links if link.speaker_role == "council"]


def _search_decision_transcripts(
    jurisdiction: str,
    decision: Decision,
    top_k: int = 3,
) -> Tuple[List[TranscriptLink], float, str]:
    """
    Find transcript excerpts related to a specific decision.

    Uses semantic search with the decision title + agenda item to find
    relevant transcript chunks from the same meeting.

    Args:
        jurisdiction: Jurisdiction ID
        decision: The decision to find transcripts for
        top_k: Maximum number of transcript excerpts to return

    Returns:
        Tuple of (transcript_links, confidence, link_type)
    """
    try:
        from civic._internal.meetings.embeddings import CivicEmbeddings
    except ImportError:
        return [], 0.0, "none"

    persist_directory = _get_embeddings_path(jurisdiction)
    if persist_directory is None:
        return [], 0.0, "none"

    try:
        embedder = CivicEmbeddings(
            jurisdiction_id=jurisdiction,
            persist_directory=persist_directory,
        )

        if not embedder.has_transcripts():
            return [], 0.0, "none"

        # Build query from decision title
        query_text = decision.title

        # Get meeting date for filtering
        meeting_date = decision.date.strftime("%Y-%m-%d") if decision.date else None

        # Search transcripts with meeting date filter if available
        where_filter = {"meeting_date": meeting_date} if meeting_date else None

        results = embedder.search_transcripts(
            query=query_text,
            top_k=top_k * 2,  # Get more, filter by quality
            where=where_filter,
        )

        if not results:
            return [], 0.0, "none"

        # Convert to TranscriptLinks
        links = []
        total_score = 0.0

        for r in results[:top_k]:
            # Determine confidence from semantic score
            # ChromaDB returns distance, lower is better
            # Score is already converted to similarity (1 - distance) in embeddings.py
            confidence = r.score

            links.append(TranscriptLink(
                chunk_id=r.document_id,
                text=r.text,
                speaker=r.metadata.get("speaker", "?"),
                speaker_role=r.metadata.get("speaker_role"),
                speaker_name=r.metadata.get("speaker_name"),
                video_id=r.metadata.get("video_id"),
                start_timestamp=r.metadata.get("start_timestamp"),
                end_timestamp=r.metadata.get("end_timestamp"),
                start_ms=r.metadata.get("start_ms"),
                end_ms=r.metadata.get("end_ms"),
                is_public_comment=r.metadata.get("is_public_comment", False),
                agenda_item=r.metadata.get("agenda_item"),
                confidence=confidence,
            ))
            total_score += confidence

        if not links:
            return [], 0.0, "none"

        # Calculate overall confidence
        avg_confidence = total_score / len(links)

        # Determine link type based on confidence
        link_type = "semantic_only"  # We're using semantic search
        if avg_confidence >= 0.7:
            link_type = "high_confidence"
        elif avg_confidence >= 0.5:
            link_type = "medium_confidence"
        else:
            link_type = "low_confidence"

        return links, avg_confidence, link_type

    except Exception:
        return [], 0.0, "none"


def search_decisions_with_context(
    state_manager: "StateManager",
    jurisdiction: str,
    query: str,
    since: str = None,
    top_k: int = 5,
    transcript_excerpts_per_decision: int = 3,
) -> List[DecisionWithContext]:
    """
    Search past decisions with linked transcript excerpts.

    This is the "full context" query that returns both the official decision
    (from minutes) and what was actually said during the meeting (from video
    transcript). Useful for understanding:
    - What public testimony was given
    - What staff recommended and why
    - What council members discussed before voting

    Args:
        state_manager: StateManager instance
        jurisdiction: City/jurisdiction ID
        query: Search query (e.g., "bike lanes", "housing development")
        since: Optional date filter (ISO format)
        top_k: Maximum number of decisions to return
        transcript_excerpts_per_decision: Max excerpts per decision (default 3)

    Returns:
        List of DecisionWithContext objects with decisions + transcript links

    Example:
        >>> from civic.history import search_decisions_with_context
        >>> results = search_decisions_with_context(
        ...     state_manager=state_mgr,
        ...     jurisdiction="city-san-rafael",
        ...     query="homeless shelter"
        ... )
        >>> for r in results:
        ...     print(f"{r.decision.title}: {r.decision.outcome}")
        ...     if r.has_transcript:
        ...         for link in r.public_comments:
        ...             print(f"  Public: {link.text[:60]}...")
    """
    # First, get matching decisions
    decisions = search_decisions(
        state_manager=state_manager,
        jurisdiction=jurisdiction,
        query=query,
        since=since,
    )

    # Limit to top_k
    decisions = decisions[:top_k]

    # Enrich each decision with transcript context
    results = []
    for decision in decisions:
        links, confidence, link_type = _search_decision_transcripts(
            jurisdiction=jurisdiction,
            decision=decision,
            top_k=transcript_excerpts_per_decision,
        )

        results.append(DecisionWithContext(
            decision=decision,
            transcript_links=links,
            link_confidence=confidence,
            link_type=link_type,
        ))

    return results
