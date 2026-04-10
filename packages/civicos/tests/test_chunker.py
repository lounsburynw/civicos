"""
Tests for legal-aware document chunking.

Tests the LegalChunker class and expand_*_to_chunks functions that split
legal documents into chunks for vector embedding while preserving
section structure.

Run: pytest packages/civicos/tests/test_chunker.py -q --override-ini="addopts="
"""

import pytest

from civicos._internal.legal.embeddings.chunker import (
    Chunk,
    LegalChunker,
    expand_codified_law_to_chunks,
    expand_executive_orders_to_chunks,
    expand_federal_rules_to_chunks,
    expand_legislation_to_chunks,
    expand_municipal_code_to_chunks,
)


# ---------------------------------------------------------------------------
# LegalChunker: section header detection
# ---------------------------------------------------------------------------

class TestSectionHeaderDetection:
    """Tests for _detect_section_header identifying legal patterns."""

    def setup_method(self):
        self.chunker = LegalChunker()

    def test_detects_sec_dot_number(self):
        result = self.chunker._detect_section_header("SEC. 101")
        assert result == "section_101"

    def test_detects_section_word_number(self):
        result = self.chunker._detect_section_header("SECTION 42")
        assert result == "section_42"

    def test_detects_section_dotted_number(self):
        result = self.chunker._detect_section_header("SEC. 1.2")
        assert result == "section_1.2"

    def test_detects_article_roman_numeral(self):
        result = self.chunker._detect_section_header("Article IV")
        assert result == "section_IV"

    def test_detects_article_arabic_number(self):
        result = self.chunker._detect_section_header("Article 5")
        assert result == "section_5"

    def test_detects_chapter_number(self):
        result = self.chunker._detect_section_header("Chapter 3")
        assert result == "section_3"

    def test_detects_chapter_dotted_number(self):
        result = self.chunker._detect_section_header("Chapter 1.5")
        assert result == "section_1.5"

    def test_returns_none_for_plain_text(self):
        result = self.chunker._detect_section_header("This is just a paragraph.")
        assert result is None

    def test_returns_none_for_empty_line(self):
        result = self.chunker._detect_section_header("")
        assert result is None

    def test_case_insensitive_section(self):
        result = self.chunker._detect_section_header("section 99")
        assert result == "section_99"


# ---------------------------------------------------------------------------
# LegalChunker: _iter_lines_with_pos
# ---------------------------------------------------------------------------

class TestIterLinesWithPos:

    def test_tracks_character_positions(self):
        chunker = LegalChunker()
        text = "abc\ndef\nghi"
        lines = list(chunker._iter_lines_with_pos(text))
        assert lines == [(0, "abc"), (4, "def"), (8, "ghi")]

    def test_single_line_starts_at_zero(self):
        chunker = LegalChunker()
        lines = list(chunker._iter_lines_with_pos("hello"))
        assert lines == [(0, "hello")]

    def test_empty_string_yields_one_empty_line(self):
        chunker = LegalChunker()
        lines = list(chunker._iter_lines_with_pos(""))
        assert lines == [(0, "")]


# ---------------------------------------------------------------------------
# LegalChunker: _detect_sections
# ---------------------------------------------------------------------------

class TestDetectSections:

    def test_preamble_only_when_no_headers(self):
        chunker = LegalChunker()
        text = "Paragraph one.\nParagraph two."
        sections = chunker._detect_sections(text)
        assert len(sections) == 1
        assert sections[0][0] == "preamble"
        assert sections[0][1] == "Paragraph one.\nParagraph two."
        assert sections[0][2] == 0

    def test_splits_on_section_headers(self):
        chunker = LegalChunker()
        text = "Preamble text.\nSEC. 1 Purpose\nFirst section body.\nSEC. 2 Scope\nSecond section body."
        sections = chunker._detect_sections(text)
        assert len(sections) == 3
        assert sections[0][0] == "preamble"
        assert sections[1][0] == "section_1"
        assert sections[2][0] == "section_2"
        assert "First section body." in sections[1][1]
        assert "Second section body." in sections[2][1]

    def test_section_start_positions_are_character_offsets(self):
        chunker = LegalChunker()
        text = "Preamble.\nSEC. 5 Title\nBody."
        sections = chunker._detect_sections(text)
        assert sections[0][2] == 0  # preamble starts at 0
        assert sections[1][2] == 10  # "SEC. 5..." starts at char 10


# ---------------------------------------------------------------------------
# LegalChunker: _chunk_by_size
# ---------------------------------------------------------------------------

class TestChunkBySize:

    def test_short_text_yields_single_chunk(self):
        chunker = LegalChunker(max_chunk_size=100, overlap=10)
        chunks = list(chunker._chunk_by_size("Short text.", "doc-1", {}))
        assert len(chunks) == 1
        assert chunks[0].text == "Short text."
        assert chunks[0].source_id == "doc-1"
        assert chunks[0].chunk_index == 0
        assert chunks[0].start_char == 0

    def test_long_text_produces_multiple_chunks(self):
        chunker = LegalChunker(max_chunk_size=50, overlap=10)
        text = "A" * 120
        chunks = list(chunker._chunk_by_size(text, "doc-2", {}))
        assert len(chunks) > 1
        # Every chunk except possibly the last should be close to max_chunk_size
        assert len(chunks[0].text) <= 50

    def test_overlap_creates_shared_content(self):
        chunker = LegalChunker(max_chunk_size=30, overlap=10)
        text = "A" * 60
        chunks = list(chunker._chunk_by_size(text, "doc-3", {}))
        # With overlap=10, the end of one chunk should overlap with the start of the next
        assert len(chunks) >= 2
        # Check that chunk start positions respect overlap
        assert chunks[1].start_char == chunks[0].end_char - 10

    def test_breaks_at_sentence_boundary_when_possible(self):
        chunker = LegalChunker(max_chunk_size=80, overlap=0)
        text = "First sentence here. Second sentence is here for padding purposes and stuff."
        chunks = list(chunker._chunk_by_size(text, "doc-4", {}))
        # Should break at the ". " boundary
        assert chunks[0].text.endswith(".")

    def test_empty_text_yields_no_chunks(self):
        chunker = LegalChunker(max_chunk_size=100, overlap=10)
        chunks = list(chunker._chunk_by_size("", "doc-5", {}))
        assert chunks == []

    def test_whitespace_only_text_yields_no_chunks(self):
        chunker = LegalChunker(max_chunk_size=100, overlap=10)
        chunks = list(chunker._chunk_by_size("   \n  \n  ", "doc-6", {}))
        assert chunks == []

    def test_base_offset_shifts_character_positions(self):
        chunker = LegalChunker(max_chunk_size=100, overlap=10)
        chunks = list(chunker._chunk_by_size("Hello.", "doc-7", {}, base_offset=500))
        assert chunks[0].start_char == 500
        # end_char = base_offset + start + max_chunk_size (capped by text length in the slice)
        assert chunks[0].end_char == 600

    def test_section_name_propagates(self):
        chunker = LegalChunker(max_chunk_size=100, overlap=10)
        chunks = list(chunker._chunk_by_size("Content.", "doc-8", {}, section="sec_42"))
        assert chunks[0].section == "sec_42"

    def test_default_section_is_unknown(self):
        chunker = LegalChunker(max_chunk_size=100, overlap=10)
        chunks = list(chunker._chunk_by_size("Content.", "doc-9", {}))
        assert chunks[0].section == "unknown"


# ---------------------------------------------------------------------------
# LegalChunker: chunk_document (integration)
# ---------------------------------------------------------------------------

class TestChunkDocument:

    def test_preserve_sections_uses_section_chunking(self):
        chunker = LegalChunker(max_chunk_size=500, preserve_sections=True)
        text = "Preamble.\nSEC. 1 Title\nBody of section one."
        chunks = list(chunker.chunk_document(text, "bill-1"))
        sections_found = {c.section for c in chunks}
        assert "preamble" in sections_found
        assert "section_1" in sections_found

    def test_no_preserve_sections_uses_size_chunking(self):
        chunker = LegalChunker(max_chunk_size=500, preserve_sections=False)
        text = "Preamble.\nSEC. 1 Title\nBody of section one."
        chunks = list(chunker.chunk_document(text, "bill-2"))
        # Without section preservation, all chunks get "unknown" section
        assert all(c.section == "unknown" for c in chunks)

    def test_metadata_defaults_to_empty_dict(self):
        chunker = LegalChunker(max_chunk_size=500)
        chunks = list(chunker.chunk_document("Some text.", "doc-10"))
        assert chunks[0].metadata == {}

    def test_metadata_propagates_to_all_chunks(self):
        chunker = LegalChunker(max_chunk_size=20, overlap=0)
        meta = {"bill_id": "AB-123", "status": "active"}
        text = "A" * 50
        chunks = list(chunker.chunk_document(text, "doc-11", metadata=meta))
        assert len(chunks) >= 2
        for c in chunks:
            assert c.metadata == meta

    def test_large_section_gets_sub_chunked(self):
        chunker = LegalChunker(max_chunk_size=50, overlap=5)
        # Create a section larger than max_chunk_size
        text = "Preamble.\nSEC. 1 Title\n" + "X" * 150
        chunks = list(chunker.chunk_document(text, "bill-3"))
        sec1_chunks = [c for c in chunks if c.section == "section_1"]
        assert len(sec1_chunks) > 1

    def test_chunk_indices_are_sequential(self):
        chunker = LegalChunker(max_chunk_size=50, overlap=5)
        text = "Preamble.\nSEC. 1 First\n" + "A" * 150 + "\nSEC. 2 Second\nShort."
        chunks = list(chunker.chunk_document(text, "bill-4"))
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_empty_document_yields_single_empty_preamble(self):
        chunker = LegalChunker(max_chunk_size=500)
        chunks = list(chunker.chunk_document("", "doc-empty"))
        # Section detection finds a preamble even for empty text
        assert len(chunks) == 1
        assert chunks[0].section == "preamble"
        assert chunks[0].text == ""


# ---------------------------------------------------------------------------
# expand_municipal_code_to_chunks
# ---------------------------------------------------------------------------

class TestExpandMunicipalCodeToChunks:

    def test_single_short_section(self):
        sections = [{
            "section_number": "14.01",
            "section_name": "Zoning",
            "chapter": "14",
            "full_text": "All zones shall be classified.",
        }]
        chunks = expand_municipal_code_to_chunks(sections)
        assert len(chunks) == 1
        assert chunks[0]["id"] == "mc-14.01-0"
        assert chunks[0]["section_number"] == "14.01"
        assert chunks[0]["section_name"] == "Zoning"
        assert chunks[0]["chapter"] == "14"
        assert "Section 14.01: Zoning (Chapter 14)" in chunks[0]["text"]
        assert "All zones shall be classified." in chunks[0]["text"]
        assert chunks[0]["chunk_index"] == 0
        assert chunks[0]["total_chunks"] == 1

    def test_skips_section_without_section_number(self):
        sections = [{"full_text": "Some text without a section number."}]
        chunks = expand_municipal_code_to_chunks(sections)
        assert chunks == []

    def test_skips_section_without_text(self):
        sections = [{"section_number": "1.01"}]
        chunks = expand_municipal_code_to_chunks(sections)
        assert chunks == []

    def test_falls_back_to_content_field(self):
        sections = [{
            "section_number": "2.01",
            "content": "Fallback content field.",
        }]
        chunks = expand_municipal_code_to_chunks(sections)
        assert len(chunks) == 1
        assert "Fallback content field." in chunks[0]["text"]

    def test_long_section_produces_multiple_chunks(self):
        sections = [{
            "section_number": "3.01",
            "section_name": "Regulations",
            "full_text": "X" * 3000,
        }]
        chunks = expand_municipal_code_to_chunks(sections, max_chunk_size=500)
        assert len(chunks) > 1
        # First chunk has plain header, subsequent have "[... continued]"
        assert chunks[0]["text"].startswith("Section 3.01: Regulations")
        assert "[Section 3.01: Regulations continued]" in chunks[1]["text"]
        # All chunks share the same section_number
        assert all(c["section_number"] == "3.01" for c in chunks)

    def test_metadata_includes_db_id(self):
        sections = [{
            "id": "uuid-abc-123",
            "section_number": "5.01",
            "full_text": "Text.",
        }]
        chunks = expand_municipal_code_to_chunks(sections)
        assert chunks[0]["metadata"]["db_id"] == "uuid-abc-123"

    def test_chunk_id_uses_section_number_not_db_id(self):
        sections = [{
            "id": "uuid-will-change",
            "section_number": "9.99",
            "full_text": "Stable ID test.",
        }]
        chunks = expand_municipal_code_to_chunks(sections)
        assert chunks[0]["id"] == "mc-9.99-0"
        assert "uuid-will-change" not in chunks[0]["id"]

    def test_empty_input_returns_empty_list(self):
        assert expand_municipal_code_to_chunks([]) == []

    def test_multiple_sections_produce_ordered_chunks(self):
        sections = [
            {"section_number": "1.01", "full_text": "First."},
            {"section_number": "1.02", "full_text": "Second."},
        ]
        chunks = expand_municipal_code_to_chunks(sections)
        assert len(chunks) == 2
        assert chunks[0]["id"] == "mc-1.01-0"
        assert chunks[1]["id"] == "mc-1.02-0"


# ---------------------------------------------------------------------------
# expand_legislation_to_chunks
# ---------------------------------------------------------------------------

class TestExpandLegislationToChunks:

    def test_single_short_bill(self):
        bills = [{
            "bill_id": "ca-AB-123",
            "bill_number": "AB 123",
            "bill_name": "Housing Act",
            "full_text": "Be it enacted.",
            "topic": "housing",
            "status": "introduced",
        }]
        chunks = expand_legislation_to_chunks(bills)
        assert len(chunks) == 1
        assert chunks[0]["id"] == "leg-ca-AB-123-0"
        assert chunks[0]["bill_id"] == "ca-AB-123"
        assert chunks[0]["bill_number"] == "AB 123"
        assert chunks[0]["topic"] == "housing"
        assert chunks[0]["status"] == "introduced"
        assert "Bill AB 123: Housing Act" in chunks[0]["text"]
        assert "Be it enacted." in chunks[0]["text"]

    def test_skips_bill_without_bill_id(self):
        bills = [{"full_text": "Text without ID."}]
        assert expand_legislation_to_chunks(bills) == []

    def test_skips_bill_without_full_text(self):
        bills = [{"bill_id": "AB-1"}]
        assert expand_legislation_to_chunks(bills) == []

    def test_bill_header_fallback_when_no_number(self):
        bills = [{
            "bill_id": "orphan-bill",
            "full_text": "Short text.",
        }]
        chunks = expand_legislation_to_chunks(bills)
        assert chunks[0]["text"].startswith("Bill orphan-bill")

    def test_long_bill_produces_continued_headers(self):
        bills = [{
            "bill_id": "big-1",
            "bill_number": "SB 999",
            "full_text": "Y" * 4000,
        }]
        chunks = expand_legislation_to_chunks(bills, max_chunk_size=500)
        assert len(chunks) > 1
        assert chunks[0]["text"].startswith("Bill SB 999")
        assert "[Bill SB 999 continued]" in chunks[1]["text"]

    def test_metadata_preserved_across_chunks(self):
        bills = [{
            "bill_id": "meta-1",
            "bill_number": "HB 1",
            "bill_name": "Test",
            "full_text": "Z" * 3000,
            "leverage_point": "high",
            "keywords": ["test"],
        }]
        chunks = expand_legislation_to_chunks(bills, max_chunk_size=500)
        for c in chunks:
            assert c["metadata"]["leverage_point"] == "high"
            assert c["metadata"]["keywords"] == ["test"]

    def test_empty_input_returns_empty_list(self):
        assert expand_legislation_to_chunks([]) == []


# ---------------------------------------------------------------------------
# expand_codified_law_to_chunks
# ---------------------------------------------------------------------------

class TestExpandCodifiedLawToChunks:

    def test_single_section_with_citation(self):
        sections = [{
            "id": "cl-uuid-1",
            "citation": "42 U.S.C. § 1983",
            "title_number": 42,
            "title_name": "Public Health",
            "section_number": "1983",
            "heading": "Civil rights",
            "text": "Every person who...",
            "jurisdiction_id": "federal-US",
        }]
        chunks = expand_codified_law_to_chunks(sections)
        assert len(chunks) == 1
        assert chunks[0]["id"] == "cl-cl-uuid-1-0"
        assert "42 U.S.C. § 1983: Civil rights" in chunks[0]["text"]
        assert "Every person who..." in chunks[0]["text"]
        assert chunks[0]["jurisdiction_id"] == "federal-US"
        assert chunks[0]["title_number"] == 42

    def test_header_fallback_without_citation(self):
        sections = [{
            "id": "cl-uuid-2",
            "title_number": 5,
            "section_number": "552",
            "text": "FOIA text.",
        }]
        chunks = expand_codified_law_to_chunks(sections)
        assert "5 § 552" in chunks[0]["text"]

    def test_header_fallback_without_citation_or_numbers(self):
        sections = [{
            "id": "cl-uuid-3",
            "text": "Orphan section.",
        }]
        chunks = expand_codified_law_to_chunks(sections)
        assert "Section cl-uuid-3" in chunks[0]["text"]

    def test_skips_without_id(self):
        sections = [{"text": "No id."}]
        assert expand_codified_law_to_chunks(sections) == []

    def test_skips_without_text(self):
        sections = [{"id": "cl-no-text"}]
        assert expand_codified_law_to_chunks(sections) == []

    def test_metadata_includes_all_hierarchy_fields(self):
        sections = [{
            "id": "cl-hier",
            "text": "Content.",
            "chapter": "Ch 1",
            "subchapter": "Sub A",
            "identifier": "1983-a",
        }]
        chunks = expand_codified_law_to_chunks(sections)
        meta = chunks[0]["metadata"]
        assert meta["chapter"] == "Ch 1"
        assert meta["subchapter"] == "Sub A"
        assert meta["identifier"] == "1983-a"

    def test_empty_input_returns_empty_list(self):
        assert expand_codified_law_to_chunks([]) == []


# ---------------------------------------------------------------------------
# expand_executive_orders_to_chunks
# ---------------------------------------------------------------------------

class TestExpandExecutiveOrdersToChunks:

    def test_single_short_eo(self):
        orders = [{
            "id": "eo-uuid-1",
            "eo_number": 14067,
            "title": "Responsible AI",
            "president": "Biden",
            "signing_date": "2023-10-30",
            "status": "active",
            "full_text": "By the authority vested in me.",
        }]
        chunks = expand_executive_orders_to_chunks(orders)
        assert len(chunks) == 1
        assert chunks[0]["id"] == "eo-eo-uuid-1-0"
        assert "Executive Order 14067: Responsible AI" in chunks[0]["text"]
        assert chunks[0]["eo_number"] == 14067
        assert chunks[0]["president"] == "Biden"
        assert chunks[0]["status"] == "active"

    def test_header_fallback_without_eo_number(self):
        orders = [{
            "id": "eo-orphan",
            "full_text": "Order text.",
        }]
        chunks = expand_executive_orders_to_chunks(orders)
        assert "Executive Order eo-orphan" in chunks[0]["text"]

    def test_skips_without_id(self):
        orders = [{"full_text": "No id."}]
        assert expand_executive_orders_to_chunks(orders) == []

    def test_skips_without_full_text(self):
        orders = [{"id": "eo-no-text"}]
        assert expand_executive_orders_to_chunks(orders) == []

    def test_long_eo_produces_continued_headers(self):
        orders = [{
            "id": "eo-long",
            "eo_number": 99999,
            "title": "Big Order",
            "full_text": "W" * 4000,
        }]
        chunks = expand_executive_orders_to_chunks(orders, max_chunk_size=500)
        assert len(chunks) > 1
        assert "[Executive Order 99999: Big Order continued]" in chunks[1]["text"]

    def test_empty_input_returns_empty_list(self):
        assert expand_executive_orders_to_chunks([]) == []


# ---------------------------------------------------------------------------
# expand_federal_rules_to_chunks
# ---------------------------------------------------------------------------

class TestExpandFederalRulesToChunks:

    def test_complete_rule(self):
        rules = [{
            "document_number": "2024-12345",
            "title": "Clean Air Standards",
            "abstract": "Revision of emission limits.",
            "agency_names": ["EPA"],
            "document_type": "proposed_rule",
            "publication_date": "2024-03-15",
            "comments_close_on": "2024-06-15",
            "topics": ["Air pollution"],
            "html_url": "https://example.gov/doc",
        }]
        chunks = expand_federal_rules_to_chunks(rules)
        assert len(chunks) == 1
        assert chunks[0]["id"] == "rule-2024-12345"
        assert "Agency: EPA" in chunks[0]["text"]
        assert "Type: Proposed Rule" in chunks[0]["text"]
        assert "Clean Air Standards" in chunks[0]["text"]
        assert "Revision of emission limits." in chunks[0]["text"]
        assert "Topics: Air pollution" in chunks[0]["text"]
        assert "Comments close: 2024-06-15" in chunks[0]["text"]
        assert chunks[0]["document_type"] == "proposed_rule"

    def test_skips_rule_without_document_number_or_id(self):
        rules = [{"title": "No id rule"}]
        assert expand_federal_rules_to_chunks(rules) == []

    def test_falls_back_to_id_field(self):
        rules = [{"id": "fallback-id", "title": "Rule title"}]
        chunks = expand_federal_rules_to_chunks(rules)
        assert chunks[0]["id"] == "rule-fallback-id"

    def test_agency_names_as_string_converted_to_list(self):
        rules = [{
            "document_number": "str-agency",
            "agency_names": "Department of Energy",
            "title": "Test",
        }]
        chunks = expand_federal_rules_to_chunks(rules)
        assert "Agency: Department of Energy" in chunks[0]["text"]
        assert chunks[0]["metadata"]["agency_names"] == ["Department of Energy"]

    def test_topics_as_string_converted_to_list(self):
        rules = [{
            "document_number": "str-topics",
            "topics": "Environment",
            "title": "Test",
        }]
        chunks = expand_federal_rules_to_chunks(rules)
        assert "Topics: Environment" in chunks[0]["text"]

    def test_document_type_label_mapping(self):
        for doc_type, label in [
            ("proposed_rule", "Proposed Rule"),
            ("final_rule", "Final Rule"),
            ("notice", "Notice"),
        ]:
            rules = [{"document_number": f"type-{doc_type}", "document_type": doc_type, "title": "T"}]
            chunks = expand_federal_rules_to_chunks(rules)
            assert f"Type: {label}" in chunks[0]["text"]

    def test_unknown_document_type_title_cased(self):
        rules = [{"document_number": "custom-type", "document_type": "presidential_document", "title": "T"}]
        chunks = expand_federal_rules_to_chunks(rules)
        assert "Type: Presidential Document" in chunks[0]["text"]

    def test_relevance_reasons_parsed(self):
        rules = [{
            "document_number": "rel-1",
            "title": "Test",
            "relevance_reasons": [
                "agency_topic:clean_energy",
                "geo:California",
                "cfr:42",
            ],
        }]
        chunks = expand_federal_rules_to_chunks(rules)
        text = chunks[0]["text"]
        assert "clean energy" in text
        assert "California" in text
        assert "CFR Title 42" in text

    def test_minimal_rule_gets_fallback_text(self):
        rules = [{"document_number": "min-1"}]
        chunks = expand_federal_rules_to_chunks(rules)
        assert "Federal Register Document min-1" in chunks[0]["text"]

    def test_minimal_rule_with_type_only(self):
        rules = [{"document_number": "min-2", "document_type": "notice"}]
        chunks = expand_federal_rules_to_chunks(rules)
        # Only "Type: Notice" part is present, no fallback needed since text is non-empty
        assert chunks[0]["text"] == "Type: Notice"

    def test_empty_input_returns_empty_list(self):
        assert expand_federal_rules_to_chunks([]) == []

    def test_metadata_contains_urls(self):
        rules = [{
            "document_number": "url-test",
            "title": "Test",
            "html_url": "https://example.gov/doc",
        }]
        chunks = expand_federal_rules_to_chunks(rules)
        assert chunks[0]["metadata"]["html_url"] == "https://example.gov/doc"
        assert chunks[0]["metadata"]["document_number"] == "url-test"


# ---------------------------------------------------------------------------
# LegalChunker: edge cases and constructor
# ---------------------------------------------------------------------------

class TestLegalChunkerConfig:

    def test_default_config(self):
        chunker = LegalChunker()
        assert chunker.max_chunk_size == 1000
        assert chunker.overlap == 100
        assert chunker.preserve_sections is True

    def test_custom_config(self):
        chunker = LegalChunker(max_chunk_size=500, overlap=50, preserve_sections=False)
        assert chunker.max_chunk_size == 500
        assert chunker.overlap == 50
        assert chunker.preserve_sections is False


class TestChunkDataclass:

    def test_chunk_fields(self):
        chunk = Chunk(
            text="Test text",
            source_id="src-1",
            section="section_1",
            chunk_index=3,
            start_char=100,
            end_char=200,
            metadata={"key": "value"},
        )
        assert chunk.text == "Test text"
        assert chunk.source_id == "src-1"
        assert chunk.section == "section_1"
        assert chunk.chunk_index == 3
        assert chunk.start_char == 100
        assert chunk.end_char == 200
        assert chunk.metadata == {"key": "value"}
