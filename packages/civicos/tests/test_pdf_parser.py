"""
Tests for agenda packet PDF parser.

Covers: AgendaChunk/AgendaSection dataclasses, item number extraction,
title extraction, chunking logic, pattern-based parsing.
Uses mock fitz (PyMuPDF) to avoid real PDF dependencies in tests.
"""

import pytest
import re
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

from civicos._internal.meetings.pdf_parser import (
    AgendaChunk,
    AgendaSection,
    AgendaPacketParser,
    parse_agenda_packet,
)


# ---------- AgendaChunk ----------

class TestAgendaChunk:

    def test_to_dict(self):
        chunk = AgendaChunk(
            text="Some agenda text",
            agenda_item="6.a",
            agenda_title="Shelter Crisis Declaration",
            page_start=5,
            page_end=8,
            chunk_index=0,
            total_chunks=3,
            metadata={"source_file": "packet.pdf"},
        )
        d = chunk.to_dict()
        assert d["text"] == "Some agenda text"
        assert d["agenda_item"] == "6.a"
        assert d["agenda_title"] == "Shelter Crisis Declaration"
        assert d["page_start"] == 5
        assert d["page_end"] == 8
        assert d["chunk_index"] == 0
        assert d["total_chunks"] == 3
        assert d["metadata"] == {"source_file": "packet.pdf"}

    def test_default_metadata(self):
        chunk = AgendaChunk(
            text="text", agenda_item="1", agenda_title="Title",
            page_start=1, page_end=1, chunk_index=0, total_chunks=1,
        )
        assert chunk.metadata == {}

    def test_metadata_independent_per_instance(self):
        c1 = AgendaChunk("a", "1", "T", 1, 1, 0, 1)
        c2 = AgendaChunk("b", "2", "T", 1, 1, 0, 1)
        c1.metadata["key"] = "val"
        assert "key" not in c2.metadata


# ---------- AgendaSection ----------

class TestAgendaSection:

    def test_fields(self):
        section = AgendaSection(
            item_number="6.a",
            title="Shelter Crisis",
            page_start=5,
            page_end=8,
            text="Full section text here",
        )
        assert section.item_number == "6.a"
        assert section.title == "Shelter Crisis"
        assert section.text == "Full section text here"


# ---------- AgendaPacketParser._extract_item_number ----------

class TestExtractItemNumber:

    @pytest.fixture
    def parser(self):
        with patch("civicos._internal.meetings.pdf_parser.fitz", MagicMock()):
            return AgendaPacketParser()

    def test_dotted_format(self, parser):
        assert parser._extract_item_number("4.a Housing Report") == "4.a"

    def test_dotted_with_sub(self, parser):
        assert parser._extract_item_number("4.a.i Subitem") == "4.a.i"

    def test_letter_suffix(self, parser):
        assert parser._extract_item_number("5b Budget Amendment") == "5b"

    def test_item_prefix(self, parser):
        assert parser._extract_item_number("Item 4 Discussion") == "4"

    def test_no_match(self, parser):
        assert parser._extract_item_number("General Discussion") is None

    def test_case_insensitive(self, parser):
        assert parser._extract_item_number("ITEM 7 Resolution") == "7"


# ---------- AgendaPacketParser._extract_title_around_match ----------

class TestExtractTitleAroundMatch:

    @pytest.fixture
    def parser(self):
        with patch("civicos._internal.meetings.pdf_parser.fitz", MagicMock()):
            return AgendaPacketParser()

    def test_extracts_text_after_match(self, parser):
        text = "Agenda Item No. 6 Housing Element Update\nMore text"
        match = re.search(r'Agenda\s+Item\s+No[.:]\s*(\d+)', text, re.IGNORECASE)
        title = parser._extract_title_around_match(text, match)
        assert "Housing Element Update" in title

    def test_strips_leading_colons(self, parser):
        text = "Agenda Item No. 6: Budget Amendment\nDetails"
        match = re.search(r'Agenda\s+Item\s+No[.:]\s*(\d+)', text, re.IGNORECASE)
        title = parser._extract_title_around_match(text, match)
        assert not title.startswith(":")
        assert "Budget Amendment" in title

    def test_truncates_long_titles(self, parser):
        text = "Agenda Item No. 6 " + "A" * 300 + "\nEnd"
        match = re.search(r'Agenda\s+Item\s+No[.:]\s*(\d+)', text, re.IGNORECASE)
        title = parser._extract_title_around_match(text, match)
        assert len(title) <= 150


# ---------- AgendaPacketParser._chunk_section ----------

class TestChunkSection:

    @pytest.fixture
    def parser(self):
        with patch("civicos._internal.meetings.pdf_parser.fitz", MagicMock()):
            return AgendaPacketParser(max_chunk_size=100, chunk_overlap=20)

    def test_empty_text_yields_nothing(self, parser):
        section = AgendaSection("1", "Title", 1, 1, "   ")
        chunks = list(parser._chunk_section(section, {}))
        assert chunks == []

    def test_short_text_single_chunk(self, parser):
        section = AgendaSection("1", "Title", 1, 1, "Short text.")
        chunks = list(parser._chunk_section(section, {}))
        assert len(chunks) == 1
        assert chunks[0].text == "Short text."
        assert chunks[0].agenda_item == "1"

    def test_long_text_splits_into_bounded_chunks(self, parser):
        # 300 chars > max_chunk_size of 100
        text = "Word " * 60  # 300 chars
        section = AgendaSection("2", "Long Item", 1, 3, text)
        chunks = list(parser._chunk_section(section, {}))
        assert len(chunks) >= 3  # 300 chars / 100 max = at least 3
        # Each chunk should be within bounds (allowing some flex for break points)
        for chunk in chunks:
            assert len(chunk.text) <= 120  # max_chunk_size + tolerance
            assert len(chunk.text) > 0
        # All chunks should carry the section's agenda item
        for chunk in chunks:
            assert chunk.agenda_item == "2"
            assert chunk.agenda_title == "Long Item"

    def test_chunks_have_correct_metadata(self, parser):
        section = AgendaSection("3", "Test", 5, 7, "Some content here.")
        chunks = list(parser._chunk_section(section, {"source": "test.pdf"}))
        for chunk in chunks:
            assert chunk.page_start == 5
            assert chunk.page_end == 7
            assert chunk.metadata == {"source": "test.pdf"}

    def test_metadata_copies_are_independent(self, parser):
        section = AgendaSection("1", "T", 1, 1, "Text content.")
        base_meta = {"key": "val"}
        chunks = list(parser._chunk_section(section, base_meta))
        chunks[0].metadata["extra"] = True
        assert "extra" not in base_meta

    def test_prefers_paragraph_breaks(self, parser):
        """Chunker should prefer breaking at paragraph boundaries."""
        with patch("civicos._internal.meetings.pdf_parser.fitz", MagicMock()):
            p = AgendaPacketParser(max_chunk_size=200, chunk_overlap=20)

        text = "First paragraph. " * 5 + "\n\n" + "Second paragraph. " * 5
        section = AgendaSection("1", "T", 1, 1, text)
        chunks = list(p._chunk_section(section, {}))
        if len(chunks) > 1:
            # First chunk should end near the paragraph break
            assert chunks[0].text.rstrip().endswith("paragraph.")

    def test_chunk_index_increments(self, parser):
        section = AgendaSection("1", "T", 1, 1, "Word " * 60)
        chunks = list(parser._chunk_section(section, {}))
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))


# ---------- AgendaPacketParser.parse ----------

class TestParse:

    @pytest.fixture
    def parser(self):
        with patch("civicos._internal.meetings.pdf_parser.fitz", MagicMock()):
            return AgendaPacketParser()

    def test_file_not_found(self, parser):
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/path/to/file.pdf")

    def test_uses_toc_when_available(self, parser):
        """When PDF has TOC, parser should use _parse_with_toc."""
        mock_doc = MagicMock()
        mock_doc.get_toc.return_value = [
            (1, "Item 6.a Housing", 5),
            (1, "Item 7 Budget", 10),
        ]
        mock_doc.__len__ = lambda self: 15

        # Mock page text extraction
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page content here"
        mock_doc.__getitem__ = lambda self, i: mock_page

        with patch("civicos._internal.meetings.pdf_parser.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            p = AgendaPacketParser()

            with patch.object(Path, "exists", return_value=True):
                sections = p.parse("test.pdf")

        assert len(sections) == 2
        assert sections[0].title == "Item 6.a Housing"

    def test_falls_back_to_patterns(self, parser):
        """When no TOC, parser should use _parse_with_patterns."""
        mock_doc = MagicMock()
        mock_doc.get_toc.return_value = []  # No TOC
        mock_doc.__len__ = lambda self: 3

        pages = [
            MagicMock(get_text=lambda: "Introduction and roll call"),
            MagicMock(get_text=lambda: "Agenda Item No. 6 Housing Element\nDetails here"),
            MagicMock(get_text=lambda: "Continued discussion of housing"),
        ]
        mock_doc.__getitem__ = lambda self, i: pages[i]

        with patch("civicos._internal.meetings.pdf_parser.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            p = AgendaPacketParser()

            with patch.object(Path, "exists", return_value=True):
                sections = p.parse("test.pdf")

        assert len(sections) >= 1
        # Should find the agenda item marker
        item_numbers = [s.item_number for s in sections]
        assert any("6" in n for n in item_numbers)

    def test_pattern_parser_handles_numbered_bullet_format(self, parser):
        """Alameda / SF / Berkeley style agendas use "N. Title" bullets with
        no 'Agenda Item No.' prefix. Before the secondary pattern was added,
        these agendas produced zero matches and the entire document fell
        into the misleading 'closing' fallback."""
        mock_doc = MagicMock()
        mock_doc.get_toc.return_value = []  # No TOC
        mock_doc.__len__ = lambda self: 3

        pages = [
            MagicMock(get_text=lambda: "Board of Supervisors Regular Meeting header"),
            MagicMock(get_text=lambda: "1. CONSENT CALENDAR\nItems 60-63"),
            MagicMock(get_text=lambda: "2. Social Services Agency - Approve the following"),
        ]
        mock_doc.__getitem__ = lambda self, i: pages[i]

        with patch("civicos._internal.meetings.pdf_parser.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            p = AgendaPacketParser()

            with patch.object(Path, "exists", return_value=True):
                sections = p.parse("test.pdf")

        item_numbers = [s.item_number for s in sections]
        assert "1" in item_numbers, f"Expected '1' in {item_numbers}"
        assert "2" in item_numbers, f"Expected '2' in {item_numbers}"
        # No section should fall into the misleading 'closing' label
        assert "closing" not in item_numbers

    def test_pattern_parser_labels_unparsed_when_no_matches(self, parser):
        """If neither regex matches anywhere, the fallback label should be
        'unparsed' (honest about the gap) rather than 'closing' (which
        misleadingly claims the content is the closing section)."""
        mock_doc = MagicMock()
        mock_doc.get_toc.return_value = []
        mock_doc.__len__ = lambda self: 2

        pages = [
            MagicMock(get_text=lambda: "Generic preamble with no agenda markers"),
            MagicMock(get_text=lambda: "Free-form narrative text with no structure"),
        ]
        mock_doc.__getitem__ = lambda self, i: pages[i]

        with patch("civicos._internal.meetings.pdf_parser.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            p = AgendaPacketParser()

            with patch.object(Path, "exists", return_value=True):
                sections = p.parse("test.pdf")

        item_numbers = [s.item_number for s in sections]
        titles = [s.title for s in sections]
        assert "unparsed" in item_numbers
        assert "Unparsed Section" in titles
        assert "closing" not in item_numbers


# ---------- AgendaPacketParser.parse_to_chunks ----------

class TestParseToChunks:

    def test_sets_total_chunks_on_each_chunk(self):
        mock_doc = MagicMock()
        mock_doc.get_toc.return_value = [(1, "Item 1 Test", 1)]
        mock_doc.__len__ = lambda self: 2

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Word " * 100  # Enough for multiple chunks
        mock_doc.__getitem__ = lambda self, i: mock_page

        with patch("civicos._internal.meetings.pdf_parser.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            p = AgendaPacketParser(max_chunk_size=100, chunk_overlap=20)

            with patch.object(Path, "exists", return_value=True):
                chunks = p.parse_to_chunks("test.pdf")

        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.total_chunks == len(chunks)

    def test_source_metadata_applied(self):
        mock_doc = MagicMock()
        mock_doc.get_toc.return_value = [(1, "Item 1 Test", 1)]
        mock_doc.__len__ = lambda self: 1

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Short text."
        mock_doc.__getitem__ = lambda self, i: mock_page

        with patch("civicos._internal.meetings.pdf_parser.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            p = AgendaPacketParser()

            with patch.object(Path, "exists", return_value=True):
                chunks = p.parse_to_chunks("test.pdf", source_metadata={"meeting_id": "m1"})

        for chunk in chunks:
            assert chunk.metadata["meeting_id"] == "m1"

    def test_default_source_file_in_metadata(self):
        mock_doc = MagicMock()
        mock_doc.get_toc.return_value = [(1, "Item 1", 1)]
        mock_doc.__len__ = lambda self: 1

        mock_page = MagicMock()
        mock_page.get_text.return_value = "Content."
        mock_doc.__getitem__ = lambda self, i: mock_page

        with patch("civicos._internal.meetings.pdf_parser.fitz") as mock_fitz:
            mock_fitz.open.return_value = mock_doc
            p = AgendaPacketParser()

            with patch.object(Path, "exists", return_value=True):
                chunks = p.parse_to_chunks("agenda.pdf")

        assert chunks[0].metadata["source_file"] == "agenda.pdf"


# ---------- AGENDA_ITEM_PATTERN ----------

class TestAgendaItemPattern:

    def test_matches_standard_format(self):
        m = AgendaPacketParser.AGENDA_ITEM_PATTERN.search("Agenda Item No. 6")
        assert m is not None
        assert m.group(1) == "6"

    def test_matches_with_colon(self):
        m = AgendaPacketParser.AGENDA_ITEM_PATTERN.search("Agenda Item No: 6")
        assert m is not None
        assert m.group(1) == "6"

    def test_matches_with_letter_suffix(self):
        m = AgendaPacketParser.AGENDA_ITEM_PATTERN.search("Agenda Item No. 6a")
        assert m.group(1) == "6a"

    def test_matches_case_insensitive(self):
        m = AgendaPacketParser.AGENDA_ITEM_PATTERN.search("AGENDA ITEM NO. 6")
        assert m is not None
        assert m.group(1) == "6"

    def test_no_match_random_text(self):
        assert AgendaPacketParser.AGENDA_ITEM_PATTERN.search("Budget discussion") is None


# ---------- Import guard ----------

class TestImportGuard:

    def test_raises_without_fitz(self):
        with patch("civicos._internal.meetings.pdf_parser.fitz", None):
            with pytest.raises(ImportError, match="PyMuPDF"):
                AgendaPacketParser()
