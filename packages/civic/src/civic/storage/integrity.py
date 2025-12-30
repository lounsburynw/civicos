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
