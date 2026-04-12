"""
Content integrity utilities for data verification.

Provides SHA-256 content hashing for transcripts, chunks, and decisions
to enable verification that content hasn't been modified.

Part of data_integrity pilot items:
- transcript_content_hash
- chunk_content_hash
- decision_content_hash
"""

import hashlib
import json
from typing import Any, Dict, List, Optional, Union


def compute_content_hash(
    content: Union[str, bytes, Dict[str, Any], List[Any]],
    encoding: str = "utf-8"
) -> str:
    """
    Compute SHA-256 hash of content for verification.

    Args:
        content: Content to hash. Can be:
            - str: Hashed directly
            - bytes: Hashed directly
            - dict/list: JSON-serialized then hashed (sorted keys for consistency)
        encoding: String encoding for str content (default: utf-8)

    Returns:
        Lowercase hex SHA-256 hash string

    Examples:
        >>> compute_content_hash("hello world")
        'b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9'

        >>> compute_content_hash({"key": "value"})
        '... consistent hash ...'
    """
    if isinstance(content, bytes):
        data = content
    elif isinstance(content, str):
        data = content.encode(encoding)
    elif isinstance(content, (dict, list)):
        # JSON serialize with sorted keys for consistent hashing
        json_str = json.dumps(content, sort_keys=True, ensure_ascii=False)
        data = json_str.encode(encoding)
    else:
        raise TypeError(f"Cannot hash content of type {type(content)}")

    return hashlib.sha256(data).hexdigest()


def compute_transcript_hash(transcript: Dict[str, Any]) -> Optional[str]:
    """
    Compute content hash for a transcript record.

    Hashes the full transcript JSON (which contains utterances).
    This enables verification that the transcript content hasn't been modified.

    Args:
        transcript: Transcript dictionary with utterances, video_id, etc.

    Returns:
        SHA-256 hash string, or None if transcript is empty/invalid
    """
    if not transcript:
        return None

    # Hash the full transcript dict (utterances + metadata)
    return compute_content_hash(transcript)


def compute_chunk_hash(text: str) -> Optional[str]:
    """
    Compute content hash for a chunk's text.

    Hashes the extracted text content from PDF/document chunks.
    This enables verification that extraction results haven't changed.

    Args:
        text: The chunk text content

    Returns:
        SHA-256 hash string, or None if text is empty
    """
    if not text:
        return None

    return compute_content_hash(text)


def compute_decision_hash(decision: Dict[str, Any]) -> Optional[str]:
    """
    Compute content hash for a decision record.

    Hashes key decision fields to enable verification.
    Uses a canonical subset of fields that represent the decision content
    (excludes metadata like extracted_at, valid_from, etc.).

    Args:
        decision: Decision dictionary with title, summary, outcome, vote, etc.

    Returns:
        SHA-256 hash string, or None if decision is empty/invalid
    """
    if not decision:
        return None

    # Extract canonical content fields (excluding temporal/metadata fields)
    content_fields = {
        'title': decision.get('title'),
        'summary': decision.get('summary'),
        'outcome': decision.get('outcome'),
        'agenda_item': decision.get('agenda_item'),
        'meeting_date': decision.get('meeting_date'),
        'vote': decision.get('vote'),
        'staff_recommendation': decision.get('staff_recommendation'),
        'public_input': decision.get('public_input'),
        'legal_instruments': decision.get('legal_instruments'),
        'topics': decision.get('topics'),
    }

    return compute_content_hash(content_fields)


def compute_stable_decision_id(
    *,
    jurisdiction_id: str,
    meeting_ref: str,
    item_ref: Optional[str] = None,
    title: Optional[str] = None,
    item_type: Optional[str] = None,
    outcome: Optional[str] = None,
    budget_amount: Optional[float] = None,
    source_item_id: Optional[str] = None,
) -> str:
    """
    Compute a stable, content-derived decision ID for upsert idempotency.

    Format: ``decision:{jurisdiction_id}:{meeting_ref}:{12-char hex}``

    The hex digest is derived from the LLM-stable subset of decision fields,
    so re-extracting the same meeting produces identical IDs even if the LLM
    returns decisions in a different order across runs. This is the key the
    temporal-versioning UPDATE in ``store_decisions()`` matches against.

    When ``source_item_id`` is provided (a platform-internal ID like Legistar
    MatterId), it is included in the hash key for ground-truth dedup. This is
    stronger than the synthetic fields alone, since the platform ID is
    deterministic across extractions. When absent, the hash falls back to the
    synthetic fields for backwards compatibility.

    Why these specific fields:
        - ``source_item_id``: platform-internal ID (strongest signal when available)
        - ``item_ref``: stable agenda item label (parsed from PDF, deterministic)
        - ``title``: stable formal label (drifts very rarely across LLM runs)
        - ``item_type``: stable enum (action/consent/hearing/discussion/presentation)
        - ``outcome``: stable enum (approved/denied/continued/withdrawn/...)
        - ``budget_amount``: deterministic if extracted (rounded to dollars)

    Why NOT ``summary`` / ``description``: those are LLM prose and drift across
    runs, which is exactly the instability that ``compute_decision_hash`` is
    designed to *detect*. We want the opposite for an ID — narrow stability.

    Why ``item_type`` and ``outcome`` are included as disambiguators:
        Two decisions in the same meeting can legitimately share an item_ref
        and title (e.g., the same hearing approved vs. continued, or a consent
        item with the same label as an action item). Including item_type and
        outcome resolves these collisions without needing a platform source ID.

    Args:
        jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
        meeting_ref: Stable meeting reference (meeting_id when available, else
            meeting_date for legacy/transcript-only paths)
        item_ref: Agenda item label (item_number or item_ref from analyzer)
        title: Decision title
        item_type: Item type enum
        outcome: Outcome enum
        budget_amount: Budget impact in dollars (rounded to nearest dollar)
        source_item_id: Platform-internal item ID (Legistar MatterId, etc.)
            When present, included in the hash for ground-truth dedup.

    Returns:
        Namespaced ID string. If both item_ref and title are empty, the digest
        falls back to a UUID-like marker so callers can detect and warn — the
        ID is still well-formed and unique (within the meeting) but won't be
        stable across reruns. Callers should log a warning in that case.
    """
    norm_item_ref = (item_ref or "").strip().lower()
    norm_title = " ".join((title or "").lower().split())
    norm_item_type = (item_type or "action").strip().lower()
    norm_outcome = (outcome or "").strip().lower()
    norm_budget = (
        str(int(round(budget_amount))) if budget_amount else ""
    )
    norm_source_id = (source_item_id or "").strip()

    key = f"{norm_item_ref}|{norm_title}|{norm_item_type}|{norm_outcome}|{norm_budget}"
    if norm_source_id:
        key = f"{norm_source_id}|{key}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    return f"decision:{jurisdiction_id}:{meeting_ref}:{digest}"


def has_stable_decision_id_inputs(
    item_ref: Optional[str], title: Optional[str]
) -> bool:
    """
    Return True if a decision has enough content to produce a stable ID.

    Used by callers to detect the rare edge case where both item_ref and title
    are empty — in which case ``compute_stable_decision_id`` still returns a
    well-formed ID, but it's not meaningfully stable across reruns and the
    caller should log a warning so the upstream extractor can be improved.
    """
    return bool((item_ref or "").strip()) or bool((title or "").strip())


def compute_audio_hash(audio_data: bytes) -> Optional[str]:
    """
    Compute SHA-256 hash of audio file bytes for provenance tracking.

    This enables verification that a transcript came from a specific audio source.
    Store alongside transcripts to prove provenance and detect tampering.

    Args:
        audio_data: Raw audio file bytes (e.g., MP3 content)

    Returns:
        SHA-256 hex string, or None if audio_data is empty/None
    """
    if not audio_data:
        return None

    return compute_content_hash(audio_data)


def verify_audio_hash(audio_data: bytes, expected_hash: str) -> bool:
    """
    Verify audio file against an expected hash.

    Args:
        audio_data: Raw audio file bytes
        expected_hash: Expected SHA-256 hash (lowercase hex)

    Returns:
        True if hash matches, False otherwise
    """
    if not expected_hash or not audio_data:
        return False

    actual_hash = compute_audio_hash(audio_data)
    return actual_hash == expected_hash.lower()


def compute_pdf_hash(pdf_data: bytes) -> Optional[str]:
    """
    Compute SHA-256 hash of PDF file bytes for provenance tracking.

    This enables verification that chunks came from a specific PDF source.
    Store alongside chunks to prove provenance and detect tampering.

    Args:
        pdf_data: Raw PDF file bytes

    Returns:
        SHA-256 hex string, or None if pdf_data is empty/None
    """
    if not pdf_data:
        return None

    return compute_content_hash(pdf_data)


def verify_pdf_hash(pdf_data: bytes, expected_hash: str) -> bool:
    """
    Verify PDF file against an expected hash.

    Args:
        pdf_data: Raw PDF file bytes
        expected_hash: Expected SHA-256 hash (lowercase hex)

    Returns:
        True if hash matches, False otherwise
    """
    if not expected_hash or not pdf_data:
        return False

    actual_hash = compute_pdf_hash(pdf_data)
    return actual_hash == expected_hash.lower()


def verify_content_hash(
    content: Union[str, bytes, Dict[str, Any], List[Any]],
    expected_hash: str
) -> bool:
    """
    Verify content against an expected hash.

    Args:
        content: Content to verify
        expected_hash: Expected SHA-256 hash (lowercase hex)

    Returns:
        True if hash matches, False otherwise
    """
    if not expected_hash:
        return False

    actual_hash = compute_content_hash(content)
    return actual_hash == expected_hash.lower()
