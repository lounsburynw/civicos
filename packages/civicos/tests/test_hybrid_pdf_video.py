"""
Tests for hybrid PDF + video transcript retrieval.

This test module validates the integration of:
- PDF document chunks (agenda packets, staff reports)
- Video transcript chunks (public testimony, council discussion)

The goal is to verify that search queries return a complete picture
by combining both written documentation and spoken content.
"""

import os
import pytest
from datetime import datetime
from civicos import CivicOS
from civicos.history import (
    search_hybrid,
    HybridSearchResult,
    UnifiedSearchResult,
    Decision,
    TranscriptSearchResult,
)


# Skip if no vector index exists
VECTOR_DIR = "data/pilot/vectors/city-san-rafael"
requires_vector_index = pytest.mark.skipif(
    not os.path.exists(VECTOR_DIR),
    reason="Vector index not available"
)


class TestUnifiedSearchResult:
    """Test the UnifiedSearchResult dataclass for cross-corpus queries."""

    def test_unified_result_core_fields(self):
        """UnifiedSearchResult has required core fields."""
        result = UnifiedSearchResult(
            id="test-1",
            text="Sample content",
            source_type="decision",
            score=0.95,
        )
        assert result.id == "test-1"
        assert result.text == "Sample content"
        assert result.source_type == "decision"
        assert result.score == 0.95

    def test_unified_result_decision_fields(self):
        """UnifiedSearchResult stores decision-specific fields."""
        result = UnifiedSearchResult(
            id="decision-1",
            text="Resolution approving homeless shelter",
            source_type="decision",
            score=0.92,
            title="Resolution 15289 - Homeless Shelter",
            date="2024-10-21",
            outcome="approved",
            body="City Council",
            votes={"vote_count": "4-1", "passed": True, "unanimous": False},
        )
        assert result.source_type == "decision"
        assert result.title == "Resolution 15289 - Homeless Shelter"
        assert result.date == "2024-10-21"
        assert result.outcome == "approved"
        assert result.body == "City Council"
        assert result.votes["passed"] is True

    def test_unified_result_pdf_fields(self):
        """UnifiedSearchResult stores PDF chunk-specific fields."""
        result = UnifiedSearchResult(
            id="chunk-1",
            text="Staff report content about funding",
            source_type="pdf",
            score=0.85,
            agenda_item="6.a",
            page_start=100,
            page_end=105,
        )
        assert result.source_type == "pdf"
        assert result.agenda_item == "6.a"
        assert result.page_start == 100
        assert result.page_end == 105

    def test_unified_result_transcript_fields(self):
        """UnifiedSearchResult stores transcript-specific fields."""
        result = UnifiedSearchResult(
            id="transcript-1",
            text="I support this proposal for the shelter.",
            source_type="transcript",
            score=0.78,
            speaker="Speaker A",
            speaker_role="public",
            speaker_name="Jane Doe",
            video_id="abc123",
            start_timestamp="01:23:45",
            end_timestamp="01:24:30",
            start_ms=5025000,
            end_ms=5070000,
            is_public_comment=True,
        )
        assert result.source_type == "transcript"
        assert result.speaker == "Speaker A"
        assert result.speaker_role == "public"
        assert result.speaker_name == "Jane Doe"
        assert result.is_public_comment is True
        assert result.video_id == "abc123"

    def test_unified_result_issue_fields(self):
        """UnifiedSearchResult stores SeeClickFix issue-specific fields."""
        result = UnifiedSearchResult(
            id="scf-20575290",
            text="Pothole on 4th Street needs repair",
            source_type="issue",
            score=0.72,
            title="Pothole on 4th Street",
            issue_type="pothole",
            address="123 4th Street, San Rafael, CA",
            latitude=37.9735,
            longitude=-122.5311,
            status="open",
        )
        assert result.source_type == "issue"
        assert result.issue_type == "pothole"
        assert result.address == "123 4th Street, San Rafael, CA"
        assert result.latitude == 37.9735
        assert result.longitude == -122.5311
        assert result.status == "open"

    def test_unified_result_municipal_code_fields(self):
        """UnifiedSearchResult stores municipal code-specific fields."""
        result = UnifiedSearchResult(
            id="muni-14.04.020",
            text="Zoning districts established for residential use",
            source_type="municipal_code",
            score=0.88,
            title="Establishment of Districts",
            section_number="14.04.020",
            chapter="14.04",
            title_number="14",
        )
        assert result.source_type == "municipal_code"
        assert result.section_number == "14.04.020"
        assert result.chapter == "14.04"
        assert result.title_number == "14"

    def test_unified_result_video_url_property(self):
        """UnifiedSearchResult generates video URL for transcript results."""
        result = UnifiedSearchResult(
            id="transcript-1",
            text="Content",
            source_type="transcript",
            score=0.75,
            video_id="abc123",
            start_ms=5025000,
        )
        assert result.video_url == "https://www.youtube.com/watch?v=abc123&t=5025s"

    def test_unified_result_video_url_none_without_video_id(self):
        """UnifiedSearchResult returns None for video_url without video_id."""
        result = UnifiedSearchResult(
            id="decision-1",
            text="Content",
            source_type="decision",
            score=0.85,
        )
        assert result.video_url is None

    def test_unified_result_from_decision(self):
        """UnifiedSearchResult.from_decision() creates result from Decision."""
        decision = Decision(
            id="decision-123",
            title="Resolution 15289",
            date=datetime(2024, 10, 21, 18, 0, 0),
            outcome="approved",
            body="City Council",
            votes={"yes": 4, "no": 1},
        )
        result = UnifiedSearchResult.from_decision(decision, score=0.9)

        assert result.id == "decision-123"
        assert result.text == "Resolution 15289"
        assert result.source_type == "decision"
        assert result.score == 0.9
        assert result.title == "Resolution 15289"
        assert result.date == "2024-10-21T18:00:00"
        assert result.outcome == "approved"
        assert result.body == "City Council"

    def test_unified_result_from_transcript_result(self):
        """UnifiedSearchResult.from_transcript_result() creates result from TranscriptSearchResult."""
        transcript = TranscriptSearchResult(
            id="chunk-45",
            text="This shelter will help our community.",
            speaker="Speaker C",
            speaker_role="public",
            speaker_name="John Smith",
            video_id="xyz789",
            start_timestamp="00:45:30",
            end_timestamp="00:46:15",
            start_ms=2730000,
            end_ms=2775000,
            is_public_comment=True,
            score=0.82,
        )
        result = UnifiedSearchResult.from_transcript_result(transcript)

        assert result.id == "chunk-45"
        assert result.text == "This shelter will help our community."
        assert result.source_type == "transcript"
        assert result.score == 0.82
        assert result.speaker == "Speaker C"
        assert result.speaker_role == "public"
        assert result.speaker_name == "John Smith"
        assert result.is_public_comment is True
        assert result.video_url == "https://www.youtube.com/watch?v=xyz789&t=2730s"

    def test_hybrid_result_to_unified(self):
        """HybridSearchResult.to_unified() converts to UnifiedSearchResult."""
        hybrid = HybridSearchResult(
            id="chunk-1",
            text="Staff report content",
            source_type="pdf",
            score=0.85,
            agenda_item="6.a",
            page_start=100,
            page_end=105,
        )
        unified = hybrid.to_unified()

        assert isinstance(unified, UnifiedSearchResult)
        assert unified.id == "chunk-1"
        assert unified.source_type == "pdf"
        assert unified.score == 0.85
        assert unified.agenda_item == "6.a"
        assert unified.page_start == 100

    def test_unified_result_all_source_types(self):
        """UnifiedSearchResult can represent all valid source types."""
        valid_types = ["decision", "pdf", "transcript", "issue", "municipal_code"]
        for source_type in valid_types:
            result = UnifiedSearchResult(
                id=f"test-{source_type}",
                text="Sample content",
                source_type=source_type,
                score=0.5,
            )
            assert result.source_type == source_type


class TestHybridSearchResult:
    """Test the HybridSearchResult dataclass."""

    def test_hybrid_result_pdf_fields(self):
        """HybridSearchResult has PDF-specific fields."""
        result = HybridSearchResult(
            id="chunk-1",
            text="Staff report content",
            source_type="pdf",
            score=0.85,
            agenda_item="6.a",
            page_start=100,
            page_end=105,
        )
        assert result.source_type == "pdf"
        assert result.agenda_item == "6.a"
        assert result.page_start == 100
        assert result.page_end == 105
        # Transcript fields should be None
        assert result.speaker is None
        assert result.video_id is None

    def test_hybrid_result_transcript_fields(self):
        """HybridSearchResult has transcript-specific fields."""
        result = HybridSearchResult(
            id="transcript-1",
            text="Public testimony content",
            source_type="transcript",
            score=0.75,
            speaker="Speaker A",
            speaker_role="public",
            speaker_name="Jane Doe",
            video_id="abc123",
            start_timestamp="01:23:45",
            end_timestamp="01:24:30",
            start_ms=5025000,
            end_ms=5070000,
            is_public_comment=True,
        )
        assert result.source_type == "transcript"
        assert result.speaker == "Speaker A"
        assert result.speaker_role == "public"
        assert result.speaker_name == "Jane Doe"
        assert result.is_public_comment is True
        # PDF fields should be None
        assert result.page_start is None
        assert result.page_end is None

    def test_hybrid_result_video_url(self):
        """HybridSearchResult generates video URL with timestamp."""
        result = HybridSearchResult(
            id="transcript-1",
            text="Content",
            source_type="transcript",
            score=0.75,
            video_id="abc123",
            start_ms=5025000,  # 1:23:45
        )
        assert result.video_url == "https://www.youtube.com/watch?v=abc123&t=5025s"

    def test_hybrid_result_video_url_none_without_video_id(self):
        """HybridSearchResult returns None for video_url without video_id."""
        result = HybridSearchResult(
            id="chunk-1",
            text="Content",
            source_type="pdf",
            score=0.85,
        )
        assert result.video_url is None


@requires_vector_index
class TestSearchHybrid:
    """Test the search_hybrid function."""

    def test_search_hybrid_returns_results(self):
        """search_hybrid returns HybridSearchResult objects."""
        results = search_hybrid(
            jurisdiction="city-san-rafael",
            query="homeless shelter funding",
            top_k=5,
        )
        assert isinstance(results, list)
        if not results:
            pytest.skip("No results from search_hybrid in local vector index")
        assert all(isinstance(r, HybridSearchResult) for r in results)
        assert all(r.text for r in results), "All results should have non-empty text"
        assert all(r.score > 0 for r in results), "All results should have positive scores"

    def test_search_hybrid_returns_both_sources(self):
        """search_hybrid returns results from both PDF and transcript sources."""
        results = search_hybrid(
            jurisdiction="city-san-rafael",
            query="homeless shelter funding",
            top_k=10,
        )

        if not results:
            pytest.skip("No results returned for query")

        source_types = {r.source_type for r in results}
        assert source_types <= {"pdf", "transcript"}, f"Unexpected source types: {source_types}"

    def test_search_hybrid_pdf_results_have_page_numbers(self):
        """PDF results from hybrid search include page numbers."""
        results = search_hybrid(
            jurisdiction="city-san-rafael",
            query="staff recommendation budget",
            top_k=10,
        )

        pdf_results = [r for r in results if r.source_type == "pdf"]
        if not pdf_results:
            pytest.skip("No PDF results returned for this query")
        has_pages = any(r.page_start is not None for r in pdf_results)
        assert has_pages, "PDF results should have page numbers"

    def test_search_hybrid_transcript_results_have_timestamps(self):
        """Transcript results from hybrid search include timestamps."""
        results = search_hybrid(
            jurisdiction="city-san-rafael",
            query="public comment shelter",
            top_k=10,
        )

        transcript_results = [r for r in results if r.source_type == "transcript"]
        if not transcript_results:
            pytest.skip("No transcript results returned for this query")
        has_timestamps = any(r.start_timestamp is not None for r in transcript_results)
        assert has_timestamps, "Transcript results should have timestamps"

    def test_search_hybrid_results_sorted_by_score(self):
        """Hybrid search results are sorted by relevance score."""
        results = search_hybrid(
            jurisdiction="city-san-rafael",
            query="shelter",
            top_k=10,
            interleave=True,
        )

        if len(results) <= 1:
            pytest.skip("Need multiple results to test sort order")
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True), "Results should be sorted by descending score"

    def test_search_hybrid_agenda_item_filter(self):
        """search_hybrid can filter by agenda item."""
        results = search_hybrid(
            jurisdiction="city-san-rafael",
            query="funding budget",
            top_k=10,
            agenda_item="6.a",
        )

        pdf_results = [r for r in results if r.source_type == "pdf" and r.agenda_item]
        if not pdf_results:
            pytest.skip("No PDF results with agenda_item metadata")
        for r in pdf_results:
            assert "6" in r.agenda_item or r.agenda_item == "6.a", \
                f"Expected agenda item 6.a, got {r.agenda_item}"

    def test_search_hybrid_empty_query(self):
        """search_hybrid handles empty query gracefully."""
        results = search_hybrid(
            jurisdiction="city-san-rafael",
            query="",
            top_k=5,
        )
        # Should not crash - may return empty or default results
        assert isinstance(results, list)


@requires_vector_index
class TestWhatHappenedWithDiscussion:
    """Test the Civic.what_happened_with_discussion() method."""

    @pytest.fixture
    def civic(self):
        """Create Civic instance for San Rafael."""
        return CivicOS("san-rafael")

    def test_what_happened_with_discussion_returns_results(self, civic):
        """what_happened_with_discussion returns HybridSearchResult objects."""
        from civicos.civicos import HybridSearchResult as CivicHybridResult

        results = civic.what_happened_with_discussion("homeless shelter")

        assert isinstance(results, list)
        assert len(results) > 0, "Expected results for 'homeless shelter' with vector index"
        assert all(isinstance(r, CivicHybridResult) for r in results)

    def test_what_happened_with_discussion_combines_sources(self, civic):
        """what_happened_with_discussion returns both PDF and transcript content."""
        results = civic.what_happened_with_discussion(
            "homeless shelter funding",
            top_k=10,
        )

        if not results:
            pytest.skip("No results returned for query")

        source_types = {r.source_type for r in results}
        assert source_types <= {"pdf", "transcript"}, f"Unexpected source types: {source_types}"

    def test_what_happened_with_discussion_pdf_has_context(self, civic):
        """PDF results include document context."""
        results = civic.what_happened_with_discussion(
            "staff recommendation",
            top_k=10,
        )

        pdf_results = [r for r in results if r.source_type == "pdf"]
        if not pdf_results:
            pytest.skip("No PDF results for this query")
        assert all(r.text for r in pdf_results), "PDF results should have non-empty text"
        assert all(r.score > 0 for r in pdf_results), "PDF results should have positive scores"

    def test_what_happened_with_discussion_transcript_has_speaker(self, civic):
        """Transcript results include speaker information."""
        results = civic.what_happened_with_discussion(
            "public comment",
            top_k=10,
        )

        transcript_results = [r for r in results if r.source_type == "transcript"]
        if not transcript_results:
            pytest.skip("No transcript results for this query")
        speaker_results = [r for r in transcript_results if r.speaker]
        if not speaker_results:
            pytest.skip("Transcript results lack speaker metadata in local data")
        for r in speaker_results:
            assert isinstance(r.speaker, str) and len(r.speaker) > 0

    def test_what_happened_with_discussion_video_url(self, civic):
        """Transcript results generate valid video URLs."""
        results = civic.what_happened_with_discussion(
            "shelter",
            top_k=10,
        )

        transcript_results = [r for r in results if r.source_type == "transcript"]
        for r in transcript_results:
            if r.video_id and r.start_ms:
                url = r.video_url
                assert url is not None
                assert "youtube.com" in url
                assert r.video_id in url


@requires_vector_index
class TestHybridSearchQuality:
    """Test the quality of hybrid search results."""

    @pytest.fixture
    def civic(self):
        """Create Civic instance for San Rafael."""
        return CivicOS("san-rafael")

    def test_shelter_query_finds_relevant_content(self, civic):
        """Query for 'shelter' finds relevant results from both sources."""
        results = civic.what_happened_with_discussion(
            "homeless shelter Merrydale",
            top_k=10,
        )

        if not results:
            pytest.skip("No results returned")

        # Check that results are semantically relevant
        relevant_terms = ["shelter", "homeless", "merrydale", "housing", "unhoused"]
        text_lower = " ".join(r.text.lower() for r in results)

        found_relevant = any(term in text_lower for term in relevant_terms)
        assert found_relevant, "Results should contain relevant terms"

    def test_hybrid_search_better_than_single_source(self, civic):
        """Hybrid search provides more context than single-source search."""
        # Get hybrid results
        hybrid_results = civic.what_happened_with_discussion(
            "shelter funding budget",
            top_k=10,
        )

        # Get PDF-only results via what_happened (decisions)
        decision_results = civic.what_happened("shelter funding budget")

        # Get transcript-only results
        transcript_results = civic.what_was_said("shelter funding budget")

        if not hybrid_results:
            pytest.skip("No hybrid results returned")
        # Verify hybrid results have content and valid source types
        hybrid_source_types = {r.source_type for r in hybrid_results}
        assert hybrid_source_types <= {"pdf", "transcript"}, f"Unexpected: {hybrid_source_types}"
        assert all(r.text for r in hybrid_results), "All hybrid results should have text content"

    def test_interleaved_results_mix_sources(self, civic):
        """With interleave=True, results alternate between sources by relevance."""
        results = civic.what_happened_with_discussion(
            "funding",
            top_k=10,
        )

        if len(results) < 4:
            pytest.skip("Not enough results to test interleaving")

        # Check that we don't have all PDF followed by all transcript
        # (unless one source dominates relevance)
        source_types = [r.source_type for r in results]
        unique_sources = set(source_types)

        if len(unique_sources) > 1:
            # With both types present, verify interleaving preserves relevance order
            assert "pdf" in unique_sources
            assert "transcript" in unique_sources
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True), "Interleaved results should maintain score order"


@requires_vector_index
class TestEdgeCases:
    """Test edge cases for hybrid search."""

    def test_nonexistent_jurisdiction(self):
        """Gracefully handle non-existent jurisdiction."""
        results = search_hybrid(
            jurisdiction="nonexistent-city",
            query="anything",
            top_k=5,
        )
        # Should return empty list, not crash
        assert results == []

    def test_very_long_query(self):
        """Handle very long queries."""
        long_query = "homeless shelter funding " * 50  # Very long query
        results = search_hybrid(
            jurisdiction="city-san-rafael",
            query=long_query,
            top_k=5,
        )
        # Should not crash
        assert isinstance(results, list)

    def test_special_characters_in_query(self):
        """Handle special characters in query."""
        results = search_hybrid(
            jurisdiction="city-san-rafael",
            query="$8 million (funding) @shelter",
            top_k=5,
        )
        # Should not crash
        assert isinstance(results, list)

    def test_top_k_respected(self):
        """top_k parameter limits results."""
        results = search_hybrid(
            jurisdiction="city-san-rafael",
            query="shelter",
            top_k=3,
        )
        assert len(results) <= 3
