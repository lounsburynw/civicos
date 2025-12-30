"""
Tests for content integrity utilities.

Verifies:
1. Content hashing produces consistent results
2. Tiny changes produce different hashes
3. Hash functions handle edge cases (empty, None)
4. Verification works correctly
"""

import pytest

from civic.storage.integrity import (
    compute_content_hash,
    compute_transcript_hash,
    compute_chunk_hash,
    compute_decision_hash,
    verify_content_hash,
)


class TestComputeContentHash:
    """Tests for the base compute_content_hash function."""

    def test_string_hashing_consistency(self):
        """Same string always produces same hash."""
        content = "Hello, World!"
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters

    def test_string_hashing_sensitivity(self):
        """Tiny change produces different hash."""
        hash1 = compute_content_hash("Hello, World!")
        hash2 = compute_content_hash("Hello, World")  # Missing !
        assert hash1 != hash2

    def test_bytes_hashing(self):
        """Bytes can be hashed directly."""
        content = b"binary data"
        hash_result = compute_content_hash(content)
        assert len(hash_result) == 64

    def test_dict_hashing_consistency(self):
        """Dicts produce consistent hashes regardless of key order."""
        dict1 = {"b": 2, "a": 1, "c": 3}
        dict2 = {"a": 1, "b": 2, "c": 3}  # Different order
        hash1 = compute_content_hash(dict1)
        hash2 = compute_content_hash(dict2)
        assert hash1 == hash2

    def test_dict_hashing_sensitivity(self):
        """Different dict values produce different hashes."""
        hash1 = compute_content_hash({"key": "value1"})
        hash2 = compute_content_hash({"key": "value2"})
        assert hash1 != hash2

    def test_list_hashing(self):
        """Lists can be hashed."""
        content = [1, 2, 3, "four"]
        hash_result = compute_content_hash(content)
        assert len(hash_result) == 64

    def test_nested_structure_hashing(self):
        """Nested structures produce consistent hashes."""
        content = {
            "outer": {
                "inner": [1, 2, {"deep": True}]
            }
        }
        hash1 = compute_content_hash(content)
        hash2 = compute_content_hash(content)
        assert hash1 == hash2

    def test_unicode_support(self):
        """Unicode characters are handled correctly."""
        content = "Hello, \u4e16\u754c!"  # Hello, World! in Japanese
        hash_result = compute_content_hash(content)
        assert len(hash_result) == 64

    def test_invalid_type_raises(self):
        """Non-supported types raise TypeError."""
        with pytest.raises(TypeError):
            compute_content_hash(12345)

        with pytest.raises(TypeError):
            compute_content_hash(None)


class TestComputeTranscriptHash:
    """Tests for transcript-specific hashing."""

    def test_transcript_with_utterances(self):
        """Transcript with utterances produces valid hash."""
        transcript = {
            "video_id": "abc123",
            "utterances": [
                {"speaker": "A", "text": "Hello", "start": 0, "end": 1000},
                {"speaker": "B", "text": "World", "start": 1000, "end": 2000},
            ]
        }
        hash_result = compute_transcript_hash(transcript)
        assert hash_result is not None
        assert len(hash_result) == 64

    def test_transcript_hash_consistency(self):
        """Same transcript always produces same hash."""
        transcript = {
            "video_id": "abc123",
            "utterances": [
                {"speaker": "A", "text": "Test", "start": 0, "end": 1000},
            ]
        }
        hash1 = compute_transcript_hash(transcript)
        hash2 = compute_transcript_hash(transcript)
        assert hash1 == hash2

    def test_transcript_hash_sensitivity(self):
        """Changed utterance text produces different hash."""
        transcript1 = {
            "video_id": "abc123",
            "utterances": [{"speaker": "A", "text": "Original", "start": 0, "end": 1000}]
        }
        transcript2 = {
            "video_id": "abc123",
            "utterances": [{"speaker": "A", "text": "Modified", "start": 0, "end": 1000}]
        }
        hash1 = compute_transcript_hash(transcript1)
        hash2 = compute_transcript_hash(transcript2)
        assert hash1 != hash2

    def test_empty_transcript_returns_none(self):
        """Empty dict returns None."""
        assert compute_transcript_hash({}) is None

    def test_none_transcript_returns_none(self):
        """None input returns None."""
        assert compute_transcript_hash(None) is None


class TestComputeChunkHash:
    """Tests for chunk-specific hashing."""

    def test_chunk_text_hash(self):
        """Chunk text produces valid hash."""
        text = "This is extracted PDF content about city planning."
        hash_result = compute_chunk_hash(text)
        assert hash_result is not None
        assert len(hash_result) == 64

    def test_chunk_hash_consistency(self):
        """Same text always produces same hash."""
        text = "Meeting agenda item regarding zoning changes."
        hash1 = compute_chunk_hash(text)
        hash2 = compute_chunk_hash(text)
        assert hash1 == hash2

    def test_chunk_hash_sensitivity(self):
        """Whitespace changes produce different hash."""
        text1 = "Meeting agenda item."
        text2 = "Meeting  agenda item."  # Extra space
        hash1 = compute_chunk_hash(text1)
        hash2 = compute_chunk_hash(text2)
        assert hash1 != hash2

    def test_empty_text_returns_none(self):
        """Empty string returns None."""
        assert compute_chunk_hash("") is None

    def test_none_text_returns_none(self):
        """None input returns None."""
        assert compute_chunk_hash(None) is None


class TestComputeDecisionHash:
    """Tests for decision-specific hashing."""

    def test_full_decision_hash(self):
        """Complete decision produces valid hash."""
        decision = {
            "title": "Approve Rezoning Request",
            "summary": "Council approved rezoning for residential development",
            "outcome": "approved",
            "agenda_item": "5.A",
            "meeting_date": "2025-01-15",
            "vote": {"ayes": 4, "nays": 1, "abstain": 0},
            "staff_recommendation": {"action": "approve"},
            "public_input": {"comments": 5, "speakers": 3},
            "legal_instruments": [{"type": "resolution", "number": "2025-001"}],
            "topics": ["zoning", "housing"],
        }
        hash_result = compute_decision_hash(decision)
        assert hash_result is not None
        assert len(hash_result) == 64

    def test_decision_hash_consistency(self):
        """Same decision always produces same hash."""
        decision = {
            "title": "Test Decision",
            "summary": "Test summary",
            "outcome": "approved",
        }
        hash1 = compute_decision_hash(decision)
        hash2 = compute_decision_hash(decision)
        assert hash1 == hash2

    def test_decision_hash_ignores_metadata(self):
        """Hash ignores non-content fields like extracted_at."""
        decision1 = {
            "title": "Test",
            "summary": "Summary",
            "outcome": "approved",
            "extracted_at": "2025-01-01T10:00:00",  # Should be ignored
        }
        decision2 = {
            "title": "Test",
            "summary": "Summary",
            "outcome": "approved",
            "extracted_at": "2025-12-31T23:59:59",  # Different time
        }
        hash1 = compute_decision_hash(decision1)
        hash2 = compute_decision_hash(decision2)
        assert hash1 == hash2

    def test_decision_hash_sensitivity_to_content(self):
        """Changed content fields produce different hash."""
        decision1 = {"title": "Approve Project", "outcome": "approved"}
        decision2 = {"title": "Deny Project", "outcome": "denied"}
        hash1 = compute_decision_hash(decision1)
        hash2 = compute_decision_hash(decision2)
        assert hash1 != hash2

    def test_empty_decision_returns_none(self):
        """Empty dict returns None."""
        assert compute_decision_hash({}) is None

    def test_none_decision_returns_none(self):
        """None input returns None."""
        assert compute_decision_hash(None) is None


class TestVerifyContentHash:
    """Tests for hash verification."""

    def test_verify_matching_hash(self):
        """Verification succeeds for matching hash."""
        content = "Test content"
        hash_value = compute_content_hash(content)
        assert verify_content_hash(content, hash_value) is True

    def test_verify_mismatched_hash(self):
        """Verification fails for mismatched hash."""
        content = "Test content"
        wrong_hash = "a" * 64  # Wrong hash
        assert verify_content_hash(content, wrong_hash) is False

    def test_verify_case_insensitive(self):
        """Verification is case-insensitive for hex hashes."""
        content = "Test content"
        hash_value = compute_content_hash(content)
        uppercase_hash = hash_value.upper()
        assert verify_content_hash(content, uppercase_hash) is True

    def test_verify_empty_hash_returns_false(self):
        """Empty expected hash returns False."""
        assert verify_content_hash("content", "") is False

    def test_verify_none_hash_returns_false(self):
        """None expected hash returns False."""
        assert verify_content_hash("content", None) is False

    def test_verify_dict_content(self):
        """Verification works for dict content."""
        content = {"key": "value", "number": 42}
        hash_value = compute_content_hash(content)
        assert verify_content_hash(content, hash_value) is True

    def test_verify_modified_content_fails(self):
        """Verification fails when content is modified."""
        original = {"key": "value"}
        hash_value = compute_content_hash(original)
        modified = {"key": "different"}
        assert verify_content_hash(modified, hash_value) is False
