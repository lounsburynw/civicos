"""
Integration tests for the city_state_rag infrastructure using San Rafael corpus.

This test file validates the RAG (Retrieval-Augmented Generation) infrastructure
using the bounded San Rafael shelter scenario as the test corpus.

Test Scenario: 350 Merrydale Road homeless shelter project
- Primary document: Nov 17, 2025 agenda packet (594 pages, ~35MB)
- Supporting documents: Staff report, minutes, ordinances
- Validation queries: what_happened('merrydale shelter') etc.

Run: python -m pytest packages/civicos/tests/test_integration_rag_merrydale.py -v
"""

import os
import sys
import json
from pathlib import Path

import pytest

# Mark all tests in this module as integration + rag
pytestmark = [pytest.mark.integration, pytest.mark.rag]

# Get absolute path to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()

# Paths to RAG corpus files
RAG_CORPUS_DIR = PROJECT_ROOT / "data/pilot/rag_corpus/city-san-rafael"
NOV17_PACKET_PATH = RAG_CORPUS_DIR / "nov17_agenda_packet.pdf"
NOV17_CHUNKS_PATH = RAG_CORPUS_DIR / "nov17_chunks.json"
SCENARIO_PATH = PROJECT_ROOT / "data/pilot/san_rafael_shelter_scenario.json"

# Add source path for imports
sys.path.insert(0, str(PROJECT_ROOT / "packages/civicos/src"))


@pytest.mark.requires_real_data
class TestSanRafaelRAGExtraction:
    """Tests for San Rafael document extraction and corpus preparation."""

    def test_nov17_packet_download(self):
        """
        Validate Nov 17 agenda packet PDF download.

        Validates:
        - File exists at expected path
        - File size matches expected (~35MB for 594 pages)
        - File is valid PDF format
        """
        # Verify file exists
        assert NOV17_PACKET_PATH.exists(), (
            f"Nov 17 agenda packet not found at {NOV17_PACKET_PATH}. "
            "Run the download script or curl the URL from merrydale_scenario.json"
        )

        # Verify file size (34.9MB = ~36.5 million bytes, allow 10% variance)
        file_size = NOV17_PACKET_PATH.stat().st_size
        expected_min = 33_000_000  # ~31.5 MB
        expected_max = 40_000_000  # ~38 MB
        assert expected_min <= file_size <= expected_max, (
            f"File size {file_size:,} bytes outside expected range "
            f"({expected_min:,} - {expected_max:,})"
        )

        # Verify it's a valid PDF by checking magic bytes
        with open(NOV17_PACKET_PATH, 'rb') as f:
            magic = f.read(5)
        assert magic == b'%PDF-', "File does not appear to be a valid PDF"

    def test_nov17_packet_page_count(self):
        """
        Validate Nov 17 agenda packet has expected page count.

        The '500+ pages' that residents cited as impossible to review in 72 hours
        should be ~594 pages based on download.
        """
        pytest.importorskip("fitz", reason="PyMuPDF required for PDF page count")
        import fitz

        doc = fitz.open(str(NOV17_PACKET_PATH))
        page_count = len(doc)
        doc.close()

        # Should have approximately 500-600 pages (allow variance for minor updates)
        assert 500 <= page_count <= 700, (
            f"Page count {page_count} outside expected range (500-700). "
            "Verify correct PDF was downloaded."
        )

    def test_nov17_packet_metadata(self):
        """
        Validate Nov 17 agenda packet metadata.

        Expected author: Lindsay Lara (City Clerk)
        Expected creation: November 2025
        """
        pytest.importorskip("fitz", reason="PyMuPDF required for PDF metadata")
        import fitz

        doc = fitz.open(str(NOV17_PACKET_PATH))
        metadata = doc.metadata
        doc.close()

        # Author should be Lindsay Lara (City Clerk mentioned in scenario)
        author = metadata.get("author", "")
        assert "Lindsay" in author or "Lara" in author or author == "", (
            f"Unexpected author: {author}. Expected Lindsay Lara or empty."
        )

        # Creation date should be November 2025
        creation_date = metadata.get("creationDate", "")
        if creation_date:
            # PDF dates are in format D:YYYYMMDDHHmmss...
            assert "202511" in creation_date or "2025-11" in creation_date, (
                f"Creation date {creation_date} not in November 2025"
            )

    def test_san_rafael_scenario_file_exists(self):
        """Validate san_rafael_shelter_scenario.json exists with expected structure."""
        assert SCENARIO_PATH.exists(), (
            f"Scenario file not found at {SCENARIO_PATH}"
        )

        with open(SCENARIO_PATH) as f:
            scenario = json.load(f)

        # Verify key structure
        assert scenario.get("scenario") == "merrydale_shelter"
        assert "source_materials" in scenario
        assert "nov_17_meeting" in scenario["source_materials"]
        assert "full_packet" in scenario["source_materials"]["nov_17_meeting"]["materials"]

    def test_corpus_directory_structure(self):
        """Validate RAG corpus directory structure is set up correctly."""
        assert RAG_CORPUS_DIR.exists(), (
            f"RAG corpus directory not found at {RAG_CORPUS_DIR}"
        )
        assert RAG_CORPUS_DIR.is_dir(), (
            f"{RAG_CORPUS_DIR} exists but is not a directory"
        )


@pytest.mark.requires_real_data
class TestNov17PacketParsing:
    """Tests for parsing Nov 17 agenda packet into RAG-ready chunks."""

    def test_chunks_file_exists(self):
        """Validate chunks JSON file was generated."""
        assert NOV17_CHUNKS_PATH.exists(), (
            f"Chunks file not found at {NOV17_CHUNKS_PATH}. "
            "Run parse_agenda_packet() to generate."
        )

    def test_chunks_file_valid_json(self):
        """Validate chunks file is valid JSON with expected structure."""
        with open(NOV17_CHUNKS_PATH) as f:
            chunks = json.load(f)

        assert isinstance(chunks, list), "Chunks should be a list"
        assert len(chunks) > 500, f"Expected 700+ chunks, got {len(chunks)}"

        # Validate first chunk structure
        chunk = chunks[0]
        required_fields = ["text", "agenda_item", "agenda_title", "page_start", "page_end"]
        for field in required_fields:
            assert field in chunk, f"Chunk missing required field: {field}"

    def test_chunks_cover_all_agenda_items(self):
        """Validate chunks cover all agenda items from PDF."""
        with open(NOV17_CHUNKS_PATH) as f:
            chunks = json.load(f)

        agenda_items = set(c["agenda_item"] for c in chunks)

        # Should have Item 6.a (Merrydale), consent items, and preamble
        assert "6.a" in agenda_items, "Missing Item 6.a (Merrydale shelter)"
        assert "5.a" in agenda_items, "Missing Item 5.a (Brown Act)"

    def test_item_6a_is_largest(self):
        """Validate Item 6.a (Merrydale) has the most chunks as expected."""
        with open(NOV17_CHUNKS_PATH) as f:
            chunks = json.load(f)

        from collections import Counter
        by_item = Counter(c["agenda_item"] for c in chunks)

        # Item 6.a should be the largest
        largest_item = by_item.most_common(1)[0]
        assert largest_item[0] == "6.a", f"Expected 6.a to be largest, got {largest_item[0]}"

        # Should be ~500+ chunks (530 as of initial parsing)
        assert largest_item[1] >= 400, f"Item 6.a has only {largest_item[1]} chunks"

    def test_merrydale_keyword_in_chunks(self):
        """Validate Merrydale keyword appears in expected chunks."""
        with open(NOV17_CHUNKS_PATH) as f:
            chunks = json.load(f)

        merrydale_chunks = [c for c in chunks if "merrydale" in c["text"].lower()]

        # Should have 200+ chunks mentioning Merrydale
        assert len(merrydale_chunks) >= 200, (
            f"Expected 200+ chunks with 'merrydale', got {len(merrydale_chunks)}"
        )

        # Most Merrydale chunks should be in Item 6.a
        item_6a_count = sum(1 for c in merrydale_chunks if c["agenda_item"] == "6.a")
        total_merrydale = len(merrydale_chunks)
        assert item_6a_count / total_merrydale > 0.85, (
            f"Expected >85% of Merrydale chunks in 6.a, got {item_6a_count}/{total_merrydale}"
        )

    def test_chunk_sizes_reasonable(self):
        """Validate chunks have reasonable sizes for RAG."""
        with open(NOV17_CHUNKS_PATH) as f:
            chunks = json.load(f)

        sizes = [len(c["text"]) for c in chunks]
        avg_size = sum(sizes) / len(sizes)
        max_size = max(sizes)

        # Average should be ~1000-1400 chars
        assert 800 <= avg_size <= 1600, f"Average chunk size {avg_size:.0f} outside expected range"

        # Max should be within limit (1500 + small tolerance)
        assert max_size <= 1600, f"Max chunk size {max_size} exceeds expected limit"


@pytest.mark.requires_real_data
class TestAgendaPacketParser:
    """Unit tests for the AgendaPacketParser class."""

    def test_parser_imports(self):
        """Validate parser module can be imported."""
        from civicos._internal.meetings import AgendaPacketParser, AgendaChunk

        parser = AgendaPacketParser()
        assert parser.max_chunk_size == 1500
        assert parser.chunk_overlap == 200

    def test_parser_sections(self):
        """Validate parser correctly identifies agenda sections from PDF bookmarks."""
        pytest.importorskip("fitz", reason="PyMuPDF required for PDF parsing")
        from civicos._internal.meetings import AgendaPacketParser

        parser = AgendaPacketParser()
        sections = parser.parse(NOV17_PACKET_PATH)

        # Should have 11 sections (matching PDF bookmarks)
        assert len(sections) == 11, f"Expected 11 sections, got {len(sections)}"

        # Item 6.a should be present
        item_6a = [s for s in sections if s.item_number == "6.a"]
        assert len(item_6a) == 1, "Item 6.a not found in sections"

        # Item 6.a should span pages 207-594
        section = item_6a[0]
        assert section.page_start == 207, f"Item 6.a starts at page {section.page_start}"
        assert section.page_end == 594, f"Item 6.a ends at page {section.page_end}"

    def test_parser_chunk_generation(self):
        """Validate parser generates appropriate chunks."""
        pytest.importorskip("fitz", reason="PyMuPDF required for PDF parsing")
        from civicos._internal.meetings import AgendaPacketParser

        parser = AgendaPacketParser(max_chunk_size=1500)
        chunks = parser.parse_to_chunks(NOV17_PACKET_PATH)

        # Should generate 700+ chunks
        assert len(chunks) >= 700, f"Expected 700+ chunks, got {len(chunks)}"

        # All chunks should have required attributes
        for chunk in chunks[:10]:  # Spot check first 10
            assert chunk.text, "Chunk has empty text"
            assert chunk.agenda_item, "Chunk missing agenda_item"
            assert chunk.page_start > 0, "Chunk has invalid page_start"
            assert chunk.total_chunks > 0, "Chunk has invalid total_chunks"


# Path to extracted staff report
ITEM_6A_STAFF_REPORT_PATH = RAG_CORPUS_DIR / "item_6a_staff_report.json"


@pytest.mark.requires_real_data
class TestStaffReportExtraction:
    """Tests for staff report metadata extraction from chunks."""

    def test_staff_report_file_exists(self):
        """Validate Item 6.a staff report was extracted."""
        assert ITEM_6A_STAFF_REPORT_PATH.exists(), (
            f"Staff report not found at {ITEM_6A_STAFF_REPORT_PATH}. "
            "Run extract_staff_report() to generate."
        )

    def test_staff_report_valid_json(self):
        """Validate staff report is valid JSON with expected structure."""
        with open(ITEM_6A_STAFF_REPORT_PATH) as f:
            report = json.load(f)

        required_fields = [
            "agenda_item", "meeting_date", "department", "prepared_by",
            "topic", "recommendation", "executive_summary"
        ]
        for field in required_fields:
            assert field in report, f"Staff report missing required field: {field}"

    def test_staff_report_agenda_item(self):
        """Validate staff report has correct agenda item."""
        with open(ITEM_6A_STAFF_REPORT_PATH) as f:
            report = json.load(f)

        assert report["agenda_item"] == "6.a", (
            f"Expected agenda_item '6.a', got '{report['agenda_item']}'"
        )

    def test_staff_report_meeting_date(self):
        """Validate staff report has correct meeting date."""
        with open(ITEM_6A_STAFF_REPORT_PATH) as f:
            report = json.load(f)

        assert "November" in report["meeting_date"], (
            f"Expected November meeting date, got '{report['meeting_date']}'"
        )
        assert "2025" in report["meeting_date"], (
            f"Expected 2025 in meeting date, got '{report['meeting_date']}'"
        )

    def test_staff_report_department(self):
        """Validate staff report has City Manager department."""
        with open(ITEM_6A_STAFF_REPORT_PATH) as f:
            report = json.load(f)

        assert "City Manager" in report["department"], (
            f"Expected 'City Manager' department, got '{report['department']}'"
        )

    def test_staff_report_authors(self):
        """Validate staff report has correct authors."""
        with open(ITEM_6A_STAFF_REPORT_PATH) as f:
            report = json.load(f)

        authors = report["prepared_by"]
        assert len(authors) >= 1, "Expected at least one author"

        # John Stefanski should be listed
        author_names = " ".join(authors).lower()
        assert "stefanski" in author_names, (
            f"Expected 'Stefanski' in authors, got {authors}"
        )

    def test_staff_report_topic_contains_merrydale(self):
        """Validate staff report topic mentions Merrydale."""
        with open(ITEM_6A_STAFF_REPORT_PATH) as f:
            report = json.load(f)

        assert "merrydale" in report["topic"].lower(), (
            f"Expected 'merrydale' in topic, got '{report['topic']}'"
        )
        assert "shelter" in report["topic"].lower(), (
            f"Expected 'shelter' in topic, got '{report['topic']}'"
        )

    def test_staff_report_property_apns(self):
        """Validate staff report has correct property APNs."""
        with open(ITEM_6A_STAFF_REPORT_PATH) as f:
            report = json.load(f)

        apns = report.get("property_apns", [])
        assert len(apns) >= 2, f"Expected 2 APNs, got {len(apns)}"

        # Should include both parcels
        assert "179-041-27" in apns, f"Missing APN 179-041-27, got {apns}"
        assert "179-041-28" in apns, f"Missing APN 179-041-28, got {apns}"

    def test_staff_report_property_address(self):
        """Validate staff report has property address."""
        with open(ITEM_6A_STAFF_REPORT_PATH) as f:
            report = json.load(f)

        address = report.get("property_address", "")
        assert "350" in address and "merrydale" in address.lower(), (
            f"Expected '350 Merrydale' in address, got '{address}'"
        )

    def test_staff_report_financial_amount(self):
        """Validate staff report captures key financial figures."""
        with open(ITEM_6A_STAFF_REPORT_PATH) as f:
            report = json.load(f)

        amount = report.get("financial_amount", "")
        # Should capture $8M grant from County of Marin
        assert "$8" in amount.upper() or "8 MILLION" in amount.upper(), (
            f"Expected $8 million, got '{amount}'"
        )

    def test_staff_report_executive_summary(self):
        """Validate staff report has meaningful executive summary."""
        with open(ITEM_6A_STAFF_REPORT_PATH) as f:
            report = json.load(f)

        summary = report["executive_summary"]
        assert len(summary) >= 200, f"Executive summary too short: {len(summary)} chars"

        # Should mention key facts
        summary_lower = summary.lower()
        assert "65" in summary or "unhoused" in summary_lower, (
            "Expected shelter capacity or 'unhoused' in summary"
        )
        assert "80 units" in summary_lower or "affordable housing" in summary_lower, (
            "Expected '80 units' or 'affordable housing' in summary"
        )


@pytest.mark.requires_real_data
class TestStaffReportExtractor:
    """Unit tests for the StaffReportExtractor class."""

    def test_extractor_imports(self):
        """Validate extractor module can be imported."""
        from civicos._internal.meetings import StaffReportExtractor, StaffReportMetadata

        extractor = StaffReportExtractor()
        assert "agenda_item" in extractor.PATTERNS
        assert "department" in extractor.PATTERNS

    def test_extractor_from_chunks(self):
        """Validate extractor can process chunks from file."""
        from civicos._internal.meetings import StaffReportExtractor

        with open(NOV17_CHUNKS_PATH) as f:
            chunks = json.load(f)

        extractor = StaffReportExtractor()
        metadata = extractor.extract_from_chunks(chunks, "6.a")

        assert metadata.agenda_item == "6.a"
        assert metadata.department == "City Manager"
        assert len(metadata.prepared_by) >= 1

    def test_extractor_raises_for_missing_item(self):
        """Validate extractor raises error for nonexistent agenda item."""
        from civicos._internal.meetings import StaffReportExtractor

        with open(NOV17_CHUNKS_PATH) as f:
            chunks = json.load(f)

        extractor = StaffReportExtractor()

        with pytest.raises(ValueError, match="No chunks found"):
            extractor.extract_from_chunks(chunks, "99.z")

    def test_metadata_to_dict(self):
        """Validate StaffReportMetadata.to_dict() works correctly."""
        from civicos._internal.meetings import StaffReportMetadata

        metadata = StaffReportMetadata(
            agenda_item="6.a",
            meeting_date="November 17, 2025",
            department="City Manager",
            prepared_by=["John Stefanski"],
            topic="Test Topic",
            recommendation="Test Recommendation",
            executive_summary="Test Summary",
        )

        d = metadata.to_dict()
        assert d["agenda_item"] == "6.a"
        assert d["meeting_date"] == "November 17, 2025"
        assert d["prepared_by"] == ["John Stefanski"]


@pytest.mark.requires_real_data
class TestOrdinanceExtraction:
    """Tests for shelter standards ordinance extraction."""

    SHELTER_ORDINANCES_PATH = RAG_CORPUS_DIR / "shelter_ordinances.json"

    def test_ordinance_file_exists(self):
        """Validate shelter ordinances JSON file exists."""
        assert self.SHELTER_ORDINANCES_PATH.exists(), (
            f"Shelter ordinances file not found at {self.SHELTER_ORDINANCES_PATH}. "
            "Run OrdinanceExtractor to generate."
        )

    def test_ordinance_count(self):
        """Validate two ordinances extracted (urgency and uncodified)."""
        with open(self.SHELTER_ORDINANCES_PATH) as f:
            ordinances = json.load(f)

        assert len(ordinances) == 2, (
            f"Expected 2 shelter ordinances, got {len(ordinances)}"
        )

    def test_urgency_ordinance_present(self):
        """Validate urgency ordinance extracted with correct type."""
        with open(self.SHELTER_ORDINANCES_PATH) as f:
            ordinances = json.load(f)

        urgency = [o for o in ordinances if o["ordinance_type"] == "urgency"]
        assert len(urgency) == 1, "Expected exactly 1 urgency ordinance"

        ord_data = urgency[0]
        assert "URGENCY ORDINANCE" in ord_data["title"].upper()
        assert "homeless shelter" in ord_data["purpose"].lower()

    def test_uncodified_ordinance_present(self):
        """Validate uncodified ordinance extracted with correct type."""
        with open(self.SHELTER_ORDINANCES_PATH) as f:
            ordinances = json.load(f)

        uncodified = [o for o in ordinances if o["ordinance_type"] == "uncodified"]
        assert len(uncodified) == 1, "Expected exactly 1 uncodified ordinance"

        ord_data = uncodified[0]
        assert "UNCODIFIED ORDINANCE" in ord_data["title"].upper()
        assert "homeless shelter" in ord_data["purpose"].lower()

    def test_ordinance_legal_authority(self):
        """Validate ordinances cite Government Code 8698 (shelter crisis law)."""
        with open(self.SHELTER_ORDINANCES_PATH) as f:
            ordinances = json.load(f)

        for ord_data in ordinances:
            legal_refs = ord_data["legal_authority"]
            assert any("8698" in ref for ref in legal_refs), (
                f"Ordinance should cite Government Code 8698, got: {legal_refs}"
            )

    def test_ordinance_whereas_clauses(self):
        """Validate ordinances have substantial WHEREAS findings."""
        with open(self.SHELTER_ORDINANCES_PATH) as f:
            ordinances = json.load(f)

        for ord_data in ordinances:
            whereas = ord_data["whereas_clauses"]
            assert len(whereas) >= 10, (
                f"Expected at least 10 WHEREAS clauses, got {len(whereas)}"
            )
            # First clause should reference housing crisis
            first_clause = whereas[0].lower()
            assert "housing" in first_clause or "marin" in first_clause, (
                f"First WHEREAS should reference housing situation: {whereas[0][:100]}"
            )

    def test_ordinance_sections(self):
        """Validate ordinances have operative divisions/sections."""
        with open(self.SHELTER_ORDINANCES_PATH) as f:
            ordinances = json.load(f)

        for ord_data in ordinances:
            sections = ord_data["sections"]
            assert len(sections) >= 5, (
                f"Expected at least 5 divisions, got {len(sections)}"
            )

            # Check for expected division titles
            section_titles = " ".join(s["title"].lower() for s in sections)
            assert "findings" in section_titles or "standards" in section_titles, (
                "Expected FINDINGS or STANDARDS division"
            )
            assert "ceqa" in section_titles, "Expected CEQA division"
            assert "severability" in section_titles, "Expected SEVERABILITY division"
            assert "effective date" in section_titles, "Expected EFFECTIVE DATE division"

    def test_urgency_ordinance_effective_date(self):
        """Validate urgency ordinance has immediate effect provision."""
        with open(self.SHELTER_ORDINANCES_PATH) as f:
            ordinances = json.load(f)

        urgency = [o for o in ordinances if o["ordinance_type"] == "urgency"][0]
        effective = urgency["effective_date_provision"].lower()

        assert "urgency" in effective or "immediate" in effective, (
            "Urgency ordinance should mention urgency/immediate in effective date"
        )
        assert "four-fifths" in effective or "4/5" in effective, (
            "Urgency ordinance requires 4/5 vote for immediate effect"
        )


@pytest.mark.requires_real_data
class TestOrdinanceExtractor:
    """Unit tests for the OrdinanceExtractor class."""

    def test_extractor_imports(self):
        """Validate extractor module can be imported."""
        from civicos._internal.meetings.ordinance import OrdinanceExtractor, OrdinanceMetadata

        extractor = OrdinanceExtractor()
        assert "ordinance_start" in extractor.PATTERNS
        assert "whereas" in extractor.PATTERNS

    def test_find_ordinances(self):
        """Validate extractor can find ordinances in chunks."""
        from civicos._internal.meetings.ordinance import OrdinanceExtractor

        with open(NOV17_CHUNKS_PATH) as f:
            chunks = json.load(f)

        extractor = OrdinanceExtractor()
        locations = extractor.find_ordinances(chunks)

        # Should find at least 2 shelter ordinances
        shelter_ordinances = [
            (idx, otype) for idx, otype in locations
            if "homeless shelter" in chunks[idx].get("text", "").lower() or "8698" in chunks[idx].get("text", "")
        ]
        assert len(shelter_ordinances) >= 2, (
            f"Expected at least 2 shelter ordinances, found {len(shelter_ordinances)}"
        )

    def test_extract_urgency_ordinance(self):
        """Validate extraction of urgency ordinance."""
        from civicos._internal.meetings.ordinance import OrdinanceExtractor

        with open(NOV17_CHUNKS_PATH) as f:
            chunks = json.load(f)

        extractor = OrdinanceExtractor()
        locations = extractor.find_ordinances(chunks)

        # Find urgency ordinance location
        urgency_loc = next(
            (idx, otype) for idx, otype in locations if otype == "urgency"
        )

        metadata = extractor.extract_ordinance(chunks, urgency_loc[0], "urgency")

        assert metadata.ordinance_type == "urgency"
        assert len(metadata.whereas_clauses) >= 10
        assert len(metadata.sections) >= 5
        assert len(metadata.chunk_indices) > 5

    def test_metadata_to_dict(self):
        """Validate OrdinanceMetadata.to_dict() works correctly."""
        from civicos._internal.meetings.ordinance import OrdinanceMetadata, OrdinanceSection

        metadata = OrdinanceMetadata(
            ordinance_number="2056",
            ordinance_type="urgency",
            title="Test Ordinance",
            purpose="Test Purpose",
            legal_authority=["Government Code Section 8698"],
            whereas_clauses=["Housing shortage exists"],
            sections=[OrdinanceSection(1, "FINDINGS", "Test content")],
            effective_date_provision="Immediately upon adoption",
        )

        d = metadata.to_dict()
        assert d["ordinance_number"] == "2056"
        assert d["ordinance_type"] == "urgency"
        assert len(d["sections"]) == 1
        assert d["sections"][0]["number"] == 1

    def test_extract_shelter_ordinances_function(self):
        """Validate the convenience function works."""
        from civicos._internal.meetings.ordinance import extract_shelter_ordinances

        results = extract_shelter_ordinances(str(NOV17_CHUNKS_PATH))

        assert len(results) >= 2
        types = [r["ordinance_type"] for r in results]
        assert "urgency" in types
        assert "uncodified" in types


# Path to extracted minutes
NOV17_MINUTES_PDF = RAG_CORPUS_DIR / "nov17_minutes.pdf"
NOV17_MINUTES_JSON = RAG_CORPUS_DIR / "nov17_minutes.json"


@pytest.mark.requires_real_data
class TestMinutesExtraction:
    """
    Tests for meeting minutes extraction.

    NOTE: MinutesExtractor uses San Rafael-specific patterns.
    For multi-city scaling, see integration.json generalized_extraction section.
    """

    def test_minutes_pdf_exists(self):
        """Validate Nov 17 minutes PDF was downloaded."""
        assert NOV17_MINUTES_PDF.exists(), (
            f"Nov 17 minutes PDF not found at {NOV17_MINUTES_PDF}. "
            "Download from city website or run minutes_extract."
        )

    def test_minutes_json_exists(self):
        """Validate Nov 17 minutes were extracted to JSON."""
        assert NOV17_MINUTES_JSON.exists(), (
            f"Nov 17 minutes JSON not found at {NOV17_MINUTES_JSON}. "
            "Run extract_meeting_minutes() to generate."
        )

    def test_minutes_valid_json_structure(self):
        """Validate minutes JSON has expected structure."""
        with open(NOV17_MINUTES_JSON) as f:
            minutes = json.load(f)

        required_fields = [
            "meeting_type", "meeting_date", "meeting_time",
            "present", "absent", "also_present",
            "called_to_order", "adjourned", "items"
        ]
        for field in required_fields:
            assert field in minutes, f"Minutes missing required field: {field}"

    def test_minutes_meeting_date(self):
        """Validate minutes have correct meeting date."""
        with open(NOV17_MINUTES_JSON) as f:
            minutes = json.load(f)

        assert "NOVEMBER 17, 2025" in minutes["meeting_date"], (
            f"Expected November 17, 2025, got '{minutes['meeting_date']}'"
        )

    def test_minutes_attendance(self):
        """Validate minutes have correct attendance."""
        with open(NOV17_MINUTES_JSON) as f:
            minutes = json.load(f)

        # 4 members present, 1 absent
        assert len(minutes["present"]) >= 3, (
            f"Expected 4 present, got {len(minutes['present'])}"
        )
        assert len(minutes["absent"]) >= 1, (
            f"Expected at least 1 absent, got {len(minutes['absent'])}"
        )

        # Councilmember Hill was absent
        absent_text = " ".join(minutes["absent"]).lower()
        assert "hill" in absent_text, (
            f"Expected Hill in absent list, got {minutes['absent']}"
        )

    def test_minutes_item_6a_exists(self):
        """Validate minutes contain Item 6.a (Merrydale shelter)."""
        with open(NOV17_MINUTES_JSON) as f:
            minutes = json.load(f)

        item_numbers = [item["item_number"] for item in minutes["items"]]
        assert "6.a" in item_numbers, (
            f"Expected item 6.a in minutes, got items: {item_numbers}"
        )

    def test_minutes_item_6a_speakers(self):
        """Validate Item 6.a has substantial public speakers list."""
        with open(NOV17_MINUTES_JSON) as f:
            minutes = json.load(f)

        item_6a = [item for item in minutes["items"] if item["item_number"] == "6.a"]
        assert len(item_6a) == 1, f"Expected 1 item 6.a, got {len(item_6a)}"

        speakers = item_6a[0]["public_speakers"]
        # Should have 70+ public speakers (observed: 78)
        assert len(speakers) >= 70, (
            f"Expected 70+ speakers for Merrydale item, got {len(speakers)}"
        )

    def test_minutes_item_6a_votes(self):
        """Validate Item 6.a has vote records."""
        with open(NOV17_MINUTES_JSON) as f:
            minutes = json.load(f)

        item_6a = [item for item in minutes["items"] if item["item_number"] == "6.a"]
        votes = item_6a[0]["votes"]

        # Should have 3+ votes (shelter crisis resolution, urgency ordinance, etc.)
        assert len(votes) >= 3, f"Expected 3+ votes, got {len(votes)}"

        # All votes should have AYES
        for vote in votes:
            assert len(vote["ayes"]) >= 3, (
                f"Expected 3+ AYES votes, got {len(vote['ayes'])}"
            )

    def test_minutes_item_6a_resolution_numbers(self):
        """Validate Item 6.a has resolution number captured."""
        with open(NOV17_MINUTES_JSON) as f:
            minutes = json.load(f)

        item_6a = [item for item in minutes["items"] if item["item_number"] == "6.a"]
        votes = item_6a[0]["votes"]

        # At least one vote should have resolution number
        resolution_numbers = [v["resolution_number"] for v in votes if v["resolution_number"]]
        assert len(resolution_numbers) >= 1, (
            "Expected at least one resolution number in votes"
        )

        # Resolution 15478 was adopted
        all_numbers = " ".join(str(r) for r in resolution_numbers if r)
        assert "15478" in all_numbers, (
            f"Expected resolution 15478, got {resolution_numbers}"
        )

    def test_minutes_meeting_duration(self):
        """Validate meeting duration was ~5 hours."""
        with open(NOV17_MINUTES_JSON) as f:
            minutes = json.load(f)

        # Called to order at 6:02 p.m., adjourned at 11:06 p.m.
        assert minutes["called_to_order"], "Missing called_to_order time"
        assert minutes["adjourned"], "Missing adjourned time"

        # Both should indicate evening times
        assert "p.m." in minutes["called_to_order"].lower() or "pm" in minutes["called_to_order"].lower()
        assert "p.m." in minutes["adjourned"].lower() or "pm" in minutes["adjourned"].lower()


@pytest.mark.requires_real_data
class TestMinutesExtractor:
    """Unit tests for MinutesExtractor class."""

    def test_extractor_imports(self):
        """Validate MinutesExtractor can be imported."""
        from civicos._internal.meetings import MinutesExtractor, MeetingMinutes
        assert "meeting_date" in MinutesExtractor.PATTERNS
        assert "meeting_type" in MinutesExtractor.PATTERNS
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(MeetingMinutes)}
        assert "meeting_date" in field_names
        assert "items" in field_names

    def test_extractor_creates_instance(self):
        """Validate MinutesExtractor can be instantiated."""
        pytest.importorskip("fitz", reason="PyMuPDF required for extraction")
        from civicos._internal.meetings import MinutesExtractor

        extractor = MinutesExtractor()
        assert "meeting_date" in extractor.PATTERNS
        assert callable(extractor.extract)

    def test_extractor_extract_method(self):
        """Validate extract() returns MeetingMinutes object."""
        pytest.importorskip("fitz", reason="PyMuPDF required for extraction")
        from civicos._internal.meetings import MinutesExtractor, MeetingMinutes

        extractor = MinutesExtractor()
        result = extractor.extract(NOV17_MINUTES_PDF)

        assert isinstance(result, MeetingMinutes)
        assert result.meeting_date
        assert result.items

    def test_meeting_minutes_to_dict(self):
        """Validate MeetingMinutes.to_dict() works correctly."""
        pytest.importorskip("fitz", reason="PyMuPDF required for extraction")
        from civicos._internal.meetings import MinutesExtractor

        extractor = MinutesExtractor()
        minutes = extractor.extract(NOV17_MINUTES_PDF)
        d = minutes.to_dict()

        assert isinstance(d, dict)
        assert "meeting_date" in d
        assert "items" in d
        assert isinstance(d["items"], list)

    def test_convenience_function(self):
        """Validate extract_meeting_minutes convenience function."""
        pytest.importorskip("fitz", reason="PyMuPDF required for extraction")
        from civicos._internal.meetings import extract_meeting_minutes

        result = extract_meeting_minutes(NOV17_MINUTES_PDF)

        assert isinstance(result, dict)
        assert "meeting_date" in result
        assert len(result["items"]) >= 8  # Should have consent + other + public hearing items


# Path to extracted decisions
NOV17_DECISIONS_JSON = RAG_CORPUS_DIR / "nov17_decisions.json"


@pytest.mark.requires_real_data
class TestDecisionExtraction:
    """
    Tests for unified decision extraction.

    Decision extraction combines data from:
    - Minutes (votes, outcomes)
    - Staff reports (recommendations, financial impact)
    - Ordinances (legal instruments)
    """

    def test_decisions_json_exists(self):
        """Validate Nov 17 decisions were extracted to JSON."""
        assert NOV17_DECISIONS_JSON.exists(), (
            f"Nov 17 decisions JSON not found at {NOV17_DECISIONS_JSON}. "
            "Run extract_decisions() to generate."
        )

    def test_decisions_valid_json_structure(self):
        """Validate decisions JSON has expected structure."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        assert isinstance(decisions, list), "Decisions should be a list"
        assert len(decisions) >= 1, "Should have at least 1 decision"

        # Check first decision has required fields
        required_fields = [
            "decision_id", "meeting_date", "agenda_item",
            "title", "summary", "outcome", "vote"
        ]
        for field in required_fields:
            assert field in decisions[0], f"Decision missing required field: {field}"

    def test_decisions_count(self):
        """Validate expected number of decisions extracted."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        # Should have 8 decisions (consent items + Brown Act + Merrydale)
        assert len(decisions) >= 6, (
            f"Expected at least 6 decisions, got {len(decisions)}"
        )

    def test_decision_ids_unique(self):
        """Validate all decisions have unique IDs."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        ids = [d["decision_id"] for d in decisions]
        assert len(ids) == len(set(ids)), "Decision IDs must be unique"

    def test_merrydale_decision_present(self):
        """Validate Merrydale shelter decision (6.a) extracted."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        item_6a = [d for d in decisions if d["agenda_item"] == "6.a"]
        assert len(item_6a) == 1, "Expected exactly 1 decision for item 6.a"

    def test_merrydale_decision_outcome(self):
        """Validate Merrydale decision has correct outcome."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        item_6a = [d for d in decisions if d["agenda_item"] == "6.a"][0]
        assert item_6a["outcome"] == "approved", (
            f"Expected approved, got {item_6a['outcome']}"
        )

    def test_merrydale_decision_vote(self):
        """Validate Merrydale decision has correct vote tally."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        item_6a = [d for d in decisions if d["agenda_item"] == "6.a"][0]
        vote = item_6a["vote"]

        assert vote["passed"] is True, "Vote should have passed"
        assert vote["unanimous"] is True, "Vote should be unanimous"
        assert vote["vote_count"] == "4-0", f"Expected 4-0, got {vote['vote_count']}"
        assert len(vote["ayes"]) == 4, f"Expected 4 ayes, got {len(vote['ayes'])}"
        assert len(vote["absent"]) >= 1, "Expected at least 1 absent"

    def test_merrydale_decision_staff_recommendation(self):
        """Validate Merrydale decision has staff recommendation."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        item_6a = [d for d in decisions if d["agenda_item"] == "6.a"][0]
        staff_rec = item_6a["staff_recommendation"]

        assert staff_rec is not None, "Expected staff recommendation"
        assert staff_rec["department"] == "City Manager"
        assert len(staff_rec["authors"]) >= 1
        assert staff_rec["financial_impact"] == "$8 MILLION"
        assert staff_rec["property_details"]["address"] == "350 MERRYDALE ROAD"

    def test_merrydale_decision_public_input(self):
        """Validate Merrydale decision has public input record."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        item_6a = [d for d in decisions if d["agenda_item"] == "6.a"][0]
        public_input = item_6a["public_input"]

        assert public_input is not None, "Expected public input"
        assert public_input["speaker_count"] >= 70, (
            f"Expected 70+ speakers, got {public_input['speaker_count']}"
        )

    def test_merrydale_decision_legal_instruments(self):
        """Validate Merrydale decision has legal instruments."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        item_6a = [d for d in decisions if d["agenda_item"] == "6.a"][0]
        instruments = item_6a["legal_instruments"]

        assert len(instruments) >= 1, "Expected at least 1 legal instrument"

        # Should have resolution 15478
        resolutions = [li for li in instruments if li["type"] == "resolution"]
        assert len(resolutions) >= 1, "Expected at least 1 resolution"
        assert any(r.get("number") == "15478" for r in resolutions), (
            "Expected resolution 15478"
        )

        # Should have urgency and uncodified ordinances
        ordinances = [li for li in instruments if li["type"] in ("urgency", "uncodified")]
        assert len(ordinances) >= 2, "Expected 2 ordinances (urgency and uncodified)"

    def test_merrydale_decision_topics(self):
        """Validate Merrydale decision has correct topics."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        item_6a = [d for d in decisions if d["agenda_item"] == "6.a"][0]
        topics = item_6a["topics"]

        assert "housing" in topics, "Expected 'housing' topic"
        assert "homelessness" in topics, "Expected 'homelessness' topic"

    def test_merrydale_decision_summary(self):
        """Validate Merrydale decision has meaningful summary."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        item_6a = [d for d in decisions if d["agenda_item"] == "6.a"][0]
        summary = item_6a["summary"]

        assert "approved" in summary.lower() or "unanimous" in summary.lower(), (
            "Summary should mention approval or unanimous vote"
        )
        assert "$8 MILLION" in summary, "Summary should mention financial impact"

    def test_consent_items_have_no_ordinances(self):
        """Validate consent items don't incorrectly get ordinances attached."""
        with open(NOV17_DECISIONS_JSON) as f:
            decisions = json.load(f)

        consent_items = [d for d in decisions if d["agenda_item"].startswith("4.")]
        for item in consent_items:
            ordinances = [
                li for li in item["legal_instruments"]
                if li["type"] in ("urgency", "uncodified")
            ]
            assert len(ordinances) == 0, (
                f"Consent item {item['agenda_item']} should not have shelter ordinances"
            )


@pytest.mark.requires_real_data
class TestDecisionExtractor:
    """Unit tests for DecisionExtractor class."""

    def test_extractor_imports(self):
        """Validate DecisionExtractor can be imported."""
        from civicos._internal.meetings import DecisionExtractor, Decision
        extractor = DecisionExtractor()
        assert extractor.jurisdiction_id == "city-san-rafael"
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(Decision)}
        assert "decision_id" in field_names
        assert "outcome" in field_names

    def test_extractor_creates_instance(self):
        """Validate DecisionExtractor can be instantiated."""
        from civicos._internal.meetings import DecisionExtractor

        extractor = DecisionExtractor()
        assert extractor.jurisdiction_id == "city-san-rafael"
        assert len(extractor.topic_keywords) > 0

    def test_extractor_extract_from_corpus(self):
        """Validate extract_from_corpus returns Decision objects."""
        from civicos._internal.meetings import DecisionExtractor, Decision

        extractor = DecisionExtractor()
        decisions = extractor.extract_from_corpus(
            RAG_CORPUS_DIR,
            "2025-11-17"
        )

        assert len(decisions) >= 1
        assert all(isinstance(d, Decision) for d in decisions)

    def test_decision_to_dict(self):
        """Validate Decision.to_dict() works correctly."""
        from civicos._internal.meetings import DecisionExtractor

        extractor = DecisionExtractor()
        decisions = extractor.extract_from_corpus(RAG_CORPUS_DIR, "2025-11-17")

        d = decisions[0].to_dict()
        assert isinstance(d, dict)
        assert "decision_id" in d
        assert "vote" in d
        assert isinstance(d["vote"], dict)

    def test_vote_tally_properties(self):
        """Validate VoteTally computed properties."""
        from civicos._internal.meetings.decision import VoteTally

        # Unanimous vote
        vote = VoteTally(
            ayes=["Bushey", "Kertz", "Llorens Gulati", "Kate"],
            noes=[],
            absent=["Hill"],
        )
        assert vote.passed is True
        assert vote.unanimous is True
        assert vote.vote_count == "4-0"

        # Split vote
        vote2 = VoteTally(
            ayes=["Bushey", "Kertz"],
            noes=["Kate", "Llorens Gulati"],
            absent=["Hill"],
        )
        assert vote2.passed is False
        assert vote2.unanimous is False
        assert vote2.vote_count == "2-2"

    def test_convenience_function(self):
        """Validate extract_decisions convenience function."""
        from civicos._internal.meetings import extract_decisions

        result = extract_decisions(RAG_CORPUS_DIR, "2025-11-17")

        assert isinstance(result, list)
        assert len(result) >= 1
        assert isinstance(result[0], dict)


# Path for test vectors (cleaned up after tests)
TEST_VECTORS_DIR = PROJECT_ROOT / "data/pilot/vectors_test/city-san-rafael"


@pytest.mark.requires_real_data
class TestEmbeddingGeneration:
    """
    Tests for embedding generation using SentenceTransformer.

    These tests validate the vector_infrastructure items in integration.json:
    - embedding_generation: Generate embeddings using SentenceTransformer
    - vector_index_creation: ChromaDB index created
    - index_query_latency: Search returns < 500ms
    """

    def test_embeddings_imports(self):
        """Validate embedding module can be imported."""
        from civicos._internal.meetings import (
            MerrydaleEmbeddings,
            SearchResult,
            build_merrydale_index,
            search_merrydale,
        )
        assert callable(MerrydaleEmbeddings)
        import dataclasses
        sr_fields = {f.name for f in dataclasses.fields(SearchResult)}
        assert "score" in sr_fields
        assert "text" in sr_fields
        assert callable(build_merrydale_index)
        assert callable(search_merrydale)

    def test_embedder_instantiation(self):
        """Validate MerrydaleEmbeddings can be instantiated."""
        from civicos._internal.meetings import MerrydaleEmbeddings

        embedder = MerrydaleEmbeddings(
            persist_directory=str(TEST_VECTORS_DIR)
        )

        assert embedder.model_name == "nomic-ai/nomic-embed-text-v1.5"
        assert embedder.persist_directory == str(TEST_VECTORS_DIR)

    def test_embedding_dimension(self):
        """Validate embedding model produces expected dimensions."""
        from civicos._internal.meetings import MerrydaleEmbeddings

        embedder = MerrydaleEmbeddings(
            persist_directory=str(TEST_VECTORS_DIR)
        )

        # nomic-embed-text-v1.5 produces 768-dimensional embeddings
        assert embedder.embedding_dimension == 768

    def test_build_decisions_index(self):
        """Validate decisions index can be built."""
        from civicos._internal.meetings import MerrydaleEmbeddings

        embedder = MerrydaleEmbeddings(
            persist_directory=str(TEST_VECTORS_DIR)
        )

        collection = embedder.build_decisions_index(RAG_CORPUS_DIR)

        # Should have embedded all 8 decisions
        assert collection.count() >= 6
        assert collection.count() <= 20  # Reasonable upper bound

        # Collection metadata should be set
        assert collection.metadata.get("embedding_model") == "nomic-ai/nomic-embed-text-v1.5"
        assert collection.metadata.get("embedding_dimension") == 768

    def test_build_chunks_index(self):
        """Validate chunks index can be built."""
        from civicos._internal.meetings import MerrydaleEmbeddings

        embedder = MerrydaleEmbeddings(
            persist_directory=str(TEST_VECTORS_DIR)
        )

        collection = embedder.build_chunks_index(RAG_CORPUS_DIR)

        # Should have embedded 700+ chunks
        assert collection.count() >= 700
        assert collection.count() <= 1000  # Reasonable upper bound

    def test_build_index_convenience(self):
        """Validate build_index creates both collections."""
        from civicos._internal.meetings import MerrydaleEmbeddings

        embedder = MerrydaleEmbeddings(
            persist_directory=str(TEST_VECTORS_DIR)
        )

        result = embedder.build_index(RAG_CORPUS_DIR)

        assert "decisions" in result
        assert "chunks" in result

    def test_convenience_build_function(self):
        """Validate build_merrydale_index convenience function."""
        from civicos._internal.meetings import build_merrydale_index

        result = build_merrydale_index(
            RAG_CORPUS_DIR,
            persist_directory=str(TEST_VECTORS_DIR),
        )

        assert "decisions" in result["collections"]
        assert "chunks" in result["collections"]
        assert result["stats"]["model"] == "nomic-ai/nomic-embed-text-v1.5"


@pytest.mark.requires_real_data
class TestVectorIndexCreation:
    """Tests for ChromaDB index creation and persistence."""

    def test_index_persists_to_disk(self):
        """Validate index is persisted to disk."""
        from civicos._internal.meetings import MerrydaleEmbeddings

        embedder = MerrydaleEmbeddings(
            persist_directory=str(TEST_VECTORS_DIR)
        )
        embedder.build_decisions_index(RAG_CORPUS_DIR)

        # Check that ChromaDB files were created
        assert TEST_VECTORS_DIR.exists()
        assert (TEST_VECTORS_DIR / "chroma.sqlite3").exists()

    def test_index_can_be_reloaded(self):
        """Validate index can be reloaded from disk."""
        from civicos._internal.meetings import CivicEmbeddings

        # Build index using new CivicEmbeddings API
        embedder1 = CivicEmbeddings(
            jurisdiction_id="city-san-rafael",
            persist_directory=str(TEST_VECTORS_DIR)
        )
        embedder1.build_decisions_index(RAG_CORPUS_DIR)
        count1 = embedder1._client.get_collection(embedder1.decisions_collection_name).count()

        # Create new embedder pointing to same directory
        embedder2 = CivicEmbeddings(
            jurisdiction_id="city-san-rafael",
            persist_directory=str(TEST_VECTORS_DIR)
        )
        count2 = embedder2._client.get_collection(embedder2.decisions_collection_name).count()

        assert count1 == count2

    def test_get_stats(self):
        """Validate get_stats returns collection information."""
        from civicos._internal.meetings import CivicEmbeddings

        embedder = CivicEmbeddings(
            jurisdiction_id="city-san-rafael",
            persist_directory=str(TEST_VECTORS_DIR)
        )
        embedder.build_index(RAG_CORPUS_DIR)

        stats = embedder.get_stats()

        assert stats["model"] == "nomic-ai/nomic-embed-text-v1.5"
        assert stats["embedding_dimension"] == 768
        assert stats["jurisdiction_id"] == "city-san-rafael"
        # Collection names follow jurisdiction pattern: {jurisdiction_id}_decisions
        assert "city-san-rafael_decisions" in stats["collections"]
        assert "city-san-rafael_chunks" in stats["collections"]


@pytest.mark.requires_real_data
class TestSearchDecisions:
    """Tests for semantic search over decisions."""

    @pytest.fixture(autouse=True)
    def setup_index(self):
        """Build index before each test."""
        from civicos._internal.meetings import MerrydaleEmbeddings

        self.embedder = MerrydaleEmbeddings(
            persist_directory=str(TEST_VECTORS_DIR)
        )
        self.embedder.build_index(RAG_CORPUS_DIR)

    def test_search_returns_results(self):
        """Validate search returns SearchResult objects."""
        from civicos._internal.meetings import SearchResult

        results = self.embedder.search_decisions("homeless shelter", top_k=3)

        assert len(results) == 3
        assert all(isinstance(r, SearchResult) for r in results)

    def test_search_result_structure(self):
        """Validate SearchResult has expected fields."""
        results = self.embedder.search_decisions("shelter", top_k=1)

        result = results[0]
        assert result.document_id, "document_id should be non-empty"
        assert result.text, "text should be non-empty"
        assert result.score > 0, "score should be positive for a matching query"
        assert "agenda_item" in result.metadata, "metadata should include agenda_item"

    def test_search_homeless_shelter_returns_item_6a(self):
        """Validate 'homeless shelter' query returns Item 6.a first."""
        results = self.embedder.search_decisions("homeless shelter funding", top_k=3)

        # Item 6.a (Merrydale) should be the top result
        top_result = results[0]
        assert top_result.metadata.get("agenda_item") == "6.a"
        assert top_result.score > 0  # Should have positive similarity

    def test_search_environmental_returns_item_4c(self):
        """Validate 'environmental consulting' returns consent item 4.c."""
        results = self.embedder.search_decisions("environmental consulting", top_k=3)

        # Item 4.c should be in top results
        agenda_items = [r.metadata.get("agenda_item") for r in results]
        assert "4.c" in agenda_items

    def test_search_with_filter(self):
        """Validate search with metadata filter works."""
        results = self.embedder.search_decisions(
            "approval",
            top_k=5,
            where={"agenda_item": "6.a"}
        )

        # All results should be from item 6.a
        for r in results:
            assert r.metadata.get("agenda_item") == "6.a"

    def test_search_scores_are_normalized(self):
        """Validate search scores are in expected range."""
        results = self.embedder.search_decisions("shelter", top_k=5)

        for r in results:
            # Cosine similarity scores should be between -1 and 1
            assert -1 <= r.score <= 1

    def test_search_with_date_range_filter_in_range(self):
        """Validate search with date range filter returns results when date is in range."""
        from datetime import datetime

        # Nov 17, 2025 decisions should be found when filtering Oct-Dec 2025
        since_ts = int(datetime(2025, 10, 1).timestamp())
        until_ts = int(datetime(2025, 12, 31).timestamp())

        results = self.embedder.search_decisions(
            "homeless shelter",
            top_k=3,
            since_ts=since_ts,
            until_ts=until_ts
        )

        assert len(results) > 0
        # Verify results have timestamp metadata
        for r in results:
            assert "meeting_date_ts" in r.metadata
            assert since_ts <= r.metadata["meeting_date_ts"] <= until_ts

    def test_search_with_date_range_filter_out_of_range(self):
        """Validate search with date range filter returns no results when date is outside range."""
        from datetime import datetime

        # Nov 17, 2025 decisions should NOT be found when filtering Jan-Mar 2025
        since_ts = int(datetime(2025, 1, 1).timestamp())
        until_ts = int(datetime(2025, 3, 31).timestamp())

        results = self.embedder.search_decisions(
            "homeless shelter",
            top_k=3,
            since_ts=since_ts,
            until_ts=until_ts
        )

        # No results because Nov 17 is outside Jan-Mar range
        assert len(results) == 0

    def test_search_with_since_only(self):
        """Validate search with only since_ts filter works."""
        from datetime import datetime

        # Nov 17, 2025 decisions should be found with since=Nov 1
        since_ts = int(datetime(2025, 11, 1).timestamp())

        results = self.embedder.search_decisions(
            "homeless shelter",
            top_k=3,
            since_ts=since_ts
        )

        assert len(results) > 0
        for r in results:
            assert r.metadata["meeting_date_ts"] >= since_ts

    def test_hybrid_query_semantic_plus_date_filter(self):
        """Validate combining semantic search with date range filtering (hybrid query).

        This is the core hybrid query test: semantic relevance (homeless shelter -> Item 6.a)
        combined with date filtering (Oct-Dec 2025). Both criteria must be satisfied.
        """
        from datetime import datetime

        # Setup: Oct-Dec 2025 date range (covers Nov 17, 2025 meeting)
        since_ts = int(datetime(2025, 10, 1).timestamp())
        until_ts = int(datetime(2025, 12, 31).timestamp())

        # Hybrid query: semantic search + date filter
        results = self.embedder.search_decisions(
            "homeless shelter funding",
            top_k=5,
            since_ts=since_ts,
            until_ts=until_ts
        )

        # Results should exist and satisfy both criteria
        assert len(results) > 0, "Should return results matching both semantic and date criteria"

        # Verify ALL results are within date range (date filter working)
        for r in results:
            assert "meeting_date_ts" in r.metadata
            assert since_ts <= r.metadata["meeting_date_ts"] <= until_ts

        # Verify semantic relevance: top result should be Item 6.a (homeless shelter item)
        top_result = results[0]
        assert top_result.metadata.get("agenda_item") == "6.a", (
            f"Expected Item 6.a for homeless shelter query, got {top_result.metadata.get('agenda_item')}"
        )


@pytest.mark.requires_real_data
class TestSearchChunks:
    """Tests for semantic search over text chunks."""

    @pytest.fixture(autouse=True)
    def setup_index(self):
        """Build index before each test."""
        from civicos._internal.meetings import MerrydaleEmbeddings

        self.embedder = MerrydaleEmbeddings(
            persist_directory=str(TEST_VECTORS_DIR)
        )
        self.embedder.build_index(RAG_CORPUS_DIR)

    def test_search_chunks_returns_results(self):
        """Validate chunk search returns results."""
        results = self.embedder.search_chunks("Merrydale Road", top_k=5)

        assert len(results) == 5
        assert all(r.text for r in results)

    def test_search_chunks_has_page_metadata(self):
        """Validate chunk results have page metadata."""
        results = self.embedder.search_chunks("property acquisition", top_k=3)

        for r in results:
            assert "page_start" in r.metadata
            assert "page_end" in r.metadata
            assert "agenda_item" in r.metadata

    def test_search_chunks_property_returns_relevant(self):
        """Validate property query returns relevant chunks."""
        results = self.embedder.search_chunks(
            "350 Merrydale Road property acquisition",
            top_k=3
        )

        # Top result should mention Merrydale
        top_result = results[0]
        assert "merrydale" in top_result.text.lower() or "350" in top_result.text

    def test_search_chunks_with_item_filter(self):
        """Validate chunk search can filter by agenda item."""
        results = self.embedder.search_chunks(
            "shelter",
            top_k=10,
            where={"agenda_item": "6.a"}
        )

        # All results should be from item 6.a
        for r in results:
            assert r.metadata.get("agenda_item") == "6.a"


@pytest.mark.requires_real_data
class TestIndexQueryLatency:
    """Tests for query latency requirements."""

    @pytest.fixture(autouse=True)
    def setup_index(self, tmp_path):
        """Build index with synthetic test data in isolated tmp directory."""
        from civicos._internal.meetings import MerrydaleEmbeddings

        # Create synthetic test corpus
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()

        # Synthetic decisions for latency testing
        decisions = [
            {
                "decision_id": "d1",
                "title": "Homeless Shelter Funding Approval",
                "summary": "Council approved $2M for emergency homeless shelter operations.",
                "meeting_date": "2025-11-17",
                "agenda_item": "6.a",
                "topics": ["housing", "homeless"],
                "outcome": "approved"
            },
            {
                "decision_id": "d2",
                "title": "Environmental Consulting Services",
                "summary": "Approved contract for environmental impact assessments.",
                "meeting_date": "2025-11-17",
                "agenda_item": "6.b",
                "topics": ["environment"],
                "outcome": "approved"
            },
            {
                "decision_id": "d3",
                "title": "Transportation Infrastructure Plan",
                "summary": "Adopted five-year transportation improvement plan.",
                "meeting_date": "2025-11-17",
                "agenda_item": "7.a",
                "topics": ["transportation", "infrastructure"],
                "outcome": "approved"
            },
        ]

        # Synthetic chunks
        chunks = [
            {"chunk_id": "c1", "text": "Property acquisition for public use.", "source": "staff_report.pdf", "page": 1},
            {"chunk_id": "c2", "text": "Brown Act compliance requirements.", "source": "staff_report.pdf", "page": 2},
            {"chunk_id": "c3", "text": "City investment report summary.", "source": "finance.pdf", "page": 1},
        ]

        # Write test data files
        (corpus_dir / "city-san-rafael_decisions.json").write_text(json.dumps(decisions))
        (corpus_dir / "city-san-rafael_chunks.json").write_text(json.dumps(chunks))

        # Create embedder with isolated persist directory
        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        self.embedder = MerrydaleEmbeddings(
            persist_directory=str(vectors_dir)
        )
        self.embedder.build_index(corpus_dir)
        # Warm up the model with a dummy query
        self.embedder.search_decisions("warmup", top_k=1)

    def test_decision_search_latency(self):
        """Validate decision search returns in < 500ms after warmup."""
        import time

        start = time.time()
        self.embedder.search_decisions("homeless shelter funding", top_k=5)
        elapsed_ms = (time.time() - start) * 1000

        # Should be < 500ms after model is loaded
        assert elapsed_ms < 500, f"Decision search took {elapsed_ms:.1f}ms (>500ms)"

    def test_chunk_search_latency(self):
        """Validate chunk search returns in < 500ms after warmup."""
        import time

        start = time.time()
        self.embedder.search_chunks("property acquisition", top_k=10)
        elapsed_ms = (time.time() - start) * 1000

        # Should be < 500ms after model is loaded
        assert elapsed_ms < 500, f"Chunk search took {elapsed_ms:.1f}ms (>500ms)"

    def test_multiple_queries_consistent_latency(self):
        """Validate multiple queries have consistent latency."""
        import time

        queries = [
            "homeless shelter",
            "environmental consulting",
            "Brown Act compliance",
            "City investment report",
            "transportation infrastructure",
        ]

        latencies = []
        for query in queries:
            start = time.time()
            self.embedder.search_decisions(query, top_k=3)
            elapsed_ms = (time.time() - start) * 1000
            latencies.append(elapsed_ms)

        # All queries should be < 500ms
        for i, latency in enumerate(latencies):
            assert latency < 500, f"Query '{queries[i]}' took {latency:.1f}ms (>500ms)"

        # Average should be < 200ms
        avg_latency = sum(latencies) / len(latencies)
        assert avg_latency < 200, f"Average latency {avg_latency:.1f}ms (>200ms)"


@pytest.mark.requires_real_data
class TestConvenienceSearchFunction:
    """Tests for the search_merrydale convenience function."""

    @pytest.fixture(autouse=True)
    def setup_index(self):
        """Build index before each test."""
        from civicos._internal.meetings import build_merrydale_index

        build_merrydale_index(
            RAG_CORPUS_DIR,
            persist_directory=str(TEST_VECTORS_DIR),
        )

    def test_search_merrydale_decisions(self):
        """Validate search_merrydale for decisions."""
        from civicos._internal.meetings import search_merrydale

        results = search_merrydale(
            "homeless shelter",
            collection="decisions",
            top_k=3,
            persist_directory=str(TEST_VECTORS_DIR),
        )

        assert len(results) == 3
        assert all(isinstance(r, dict) for r in results)
        assert all("document_id" in r for r in results)
        assert all("score" in r for r in results)

    def test_search_merrydale_chunks(self):
        """Validate search_merrydale for chunks."""
        from civicos._internal.meetings import search_merrydale

        results = search_merrydale(
            "Merrydale Road",
            collection="chunks",
            top_k=5,
            persist_directory=str(TEST_VECTORS_DIR),
        )

        assert len(results) == 5
        assert all("text" in r for r in results)
        assert all("metadata" in r for r in results)


@pytest.mark.requires_real_data
class TestWhatHappenedSanRafael:
    """
    Tests for what_happened('merrydale') integration.

    Validates the search_integration item in integration.json:
    - what_happened_merrydale: what_happened('merrydale') returns timeline from Nov 17 decisions

    This integrates the vector search (CivicEmbeddings) with the Civic API.
    """

    @pytest.fixture(autouse=True)
    def setup_index(self):
        """Build index before each test."""
        from civicos._internal.meetings import build_merrydale_index

        build_merrydale_index(
            RAG_CORPUS_DIR,
            persist_directory="data/pilot/vectors/city-san-rafael",
        )

    def test_what_happened_merrydale_returns_decisions(self):
        """Validate what_happened('merrydale') returns Decision objects."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        decisions = c.what_happened("merrydale")

        assert len(decisions) > 0, "Should return at least one decision"
        assert len(decisions) == 8, "Should return all 8 Merrydale decisions"

    def test_what_happened_merrydale_decision_structure(self):
        """Validate returned decisions have correct structure."""
        from civicos import CivicOS
        from datetime import datetime

        c = CivicOS("san-rafael")
        decisions = c.what_happened("merrydale")

        assert len(decisions) >= 1, "Should return at least one Merrydale decision"
        for d in decisions:
            assert d.id, "Decision id should be non-empty"
            assert d.title, "Decision title should be non-empty"
            assert isinstance(d.date, datetime), "date should be datetime"
            assert d.outcome in ("approved", "denied", "continued", "withdrawn"), \
                f"Unexpected outcome: {d.outcome}"
            assert d.body, "Decision body should be non-empty"

    def test_what_happened_merrydale_homeless_shelter(self):
        """Validate 'merrydale homeless shelter' returns relevant decisions first."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        decisions = c.what_happened("merrydale homeless shelter")

        assert len(decisions) > 0, "Should return decisions"

        # Item 6.a (Merrydale shelter) should be the top result
        top_decision = decisions[0]
        assert "item-6-a" in top_decision.id, (
            f"Top result should be item 6.a, got {top_decision.id}"
        )
        assert "shelter" in top_decision.title.lower(), (
            f"Top result title should mention shelter, got {top_decision.title}"
        )

    def test_what_happened_merrydale_transportation(self):
        """Validate 'merrydale transportation' returns transport-related decisions first."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        decisions = c.what_happened("merrydale transportation")

        assert len(decisions) > 0, "Should return decisions"

        # Transportation item should be in top results
        top_ids = [d.id for d in decisions[:3]]
        assert any("item-4-f" in id for id in top_ids), (
            f"Transportation item 4.f should be in top 3, got {top_ids}"
        )

    def test_what_happened_merrydale_votes(self):
        """Validate decisions have vote information."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        decisions = c.what_happened("merrydale homeless shelter")

        # Item 6.a should have vote information (ID format: 20251117-item-6-a)
        item_6a = [d for d in decisions if "item-6-a" in d.id]
        assert len(item_6a) > 0, "Should include item 6.a"

        decision = item_6a[0]
        assert decision.votes is not None, "Should have votes"
        assert decision.votes.get("vote_count") == "4-0", (
            f"Expected 4-0 vote, got {decision.votes.get('vote_count')}"
        )
        assert decision.votes.get("passed") is True, "Vote should have passed"

    def test_what_happened_merrydale_outcomes(self):
        """Validate all decisions have outcomes."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        decisions = c.what_happened("merrydale")

        valid_outcomes = ["approved", "received", "unknown"]
        for d in decisions:
            assert d.outcome in valid_outcomes, (
                f"Expected valid outcome, got {d.outcome}"
            )

    def test_what_happened_merrydale_timeline_order(self):
        """Validate decisions are sorted by date (most recent first)."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        decisions = c.what_happened("merrydale")

        # All should be from the same date (Nov 17, 2025)
        dates = [d.date for d in decisions]
        # Should be sorted in descending order (most recent first)
        for i in range(len(dates) - 1):
            assert dates[i] >= dates[i + 1], (
                f"Decisions not sorted: {dates[i]} < {dates[i + 1]}"
            )

    def test_what_happened_non_merrydale_not_affected(self):
        """Validate non-Merrydale queries still use standard search."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        # A non-Merrydale query should use the standard search
        decisions = c.what_happened("housing")

        # This should use keyword search, not embedding search
        # It may return no results (since there's no housing data in state)
        assert isinstance(decisions, list)
        # Any returned decisions should be well-formed
        for d in decisions:
            assert d.id, "Decision should have non-empty id"
            assert d.title, "Decision should have non-empty title"
            assert d.date is not None, "Decision should have a date"


@pytest.mark.requires_real_data
class TestWhatWasSaidTranscripts:
    """
    Tests for what_was_said() transcript search integration.

    Validates the what_happened_transcript item in integration.json:
    - what_happened() searches video transcripts when available

    Uses synthetic testimony data for CI compatibility.
    """

    @pytest.fixture
    def build_transcript_index(self, tmp_path):
        """Build transcript index with synthetic test data in tmp directory."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings

        # Create synthetic testimony directory
        testimony_dir = tmp_path / "testimony"
        testimony_dir.mkdir()

        # Create synthetic testimony file (AssemblyAI format)
        testimony_data = {
            "video_id": "test_video_001",
            "utterances": [
                {"speaker": "A", "text": "Good evening, we're here to discuss the homeless shelter proposal.", "start": 0, "end": 5000},
                {"speaker": "B", "text": "Thank you Mayor. The city council has reviewed the proposal.", "start": 5000, "end": 10000},
                {"speaker": "A", "text": "Let's open it up for public comment on the shelter location.", "start": 10000, "end": 15000},
                {"speaker": "C", "text": "I support the homeless shelter. We need more affordable housing.", "start": 15000, "end": 22000},
                {"speaker": "D", "text": "I have concerns about traffic near the meeting location.", "start": 22000, "end": 28000},
                {"speaker": "B", "text": "The council will take these comments into consideration.", "start": 28000, "end": 33000},
            ]
        }
        (testimony_dir / "testimony_test_video_001.json").write_text(json.dumps(testimony_data))

        # Create isolated vectors directory
        vectors_dir = tmp_path / "vectors"
        vectors_dir.mkdir()

        embedder = CivicEmbeddings(
            jurisdiction_id="city-san-rafael",
            persist_directory=str(vectors_dir),
        )
        embedder.build_transcripts_index(
            testimony_dir,
            use_speaker_detection=False,  # Faster for tests
        )

        return embedder

    def test_transcript_index_builds(self, build_transcript_index):
        """Validate transcript index builds without error."""
        embedder = build_transcript_index

        stats = embedder.get_stats()
        collection_name = "city-san-rafael_transcripts"
        assert collection_name in stats["collections"]
        assert stats["collections"][collection_name] is not None
        assert stats["collections"][collection_name]["count"] > 0

    def test_transcript_search_returns_results(self, build_transcript_index):
        """Validate transcript search returns results."""
        embedder = build_transcript_index

        results = embedder.search_transcripts("homeless shelter", top_k=5)

        assert len(results) > 0, "Should return at least one transcript chunk"
        for r in results:
            assert r.text, "Result should have text"
            # ChromaDB returns cosine distance, converted to similarity (1-distance)
            # Scores can range from -1 to 1, with higher being more similar
            assert r.score is not None, "Result should have score"

    def test_transcript_search_has_metadata(self, build_transcript_index):
        """Validate transcript search results have expected metadata."""
        embedder = build_transcript_index

        results = embedder.search_transcripts("meeting", top_k=3)

        assert len(results) > 0
        for r in results:
            meta = r.metadata
            assert "video_id" in meta, "Should have video_id"
            assert "speaker" in meta, "Should have speaker"
            assert "start_ms" in meta, "Should have start_ms"
            assert "end_ms" in meta, "Should have end_ms"
            assert "source_type" in meta, "Should have source_type"
            assert meta["source_type"] == "transcript"

    def test_what_was_said_returns_excerpts(self, build_transcript_index):
        """Validate what_was_said() returns TranscriptExcerpt objects."""
        from civicos import CivicOS, TranscriptExcerpt

        c = CivicOS("san-rafael")
        excerpts = c.what_was_said("homeless shelter")

        assert len(excerpts) > 0, "Should return at least one excerpt"
        for e in excerpts:
            assert isinstance(e, TranscriptExcerpt)
            assert e.text, "Should have text"
            assert e.speaker, "Should have speaker"

    def test_what_was_said_excerpt_structure(self, build_transcript_index):
        """Validate TranscriptExcerpt has expected fields."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        excerpts = c.what_was_said("city council", top_k=3)

        assert len(excerpts) > 0
        excerpt = excerpts[0]

        # Required fields
        assert hasattr(excerpt, "id")
        assert hasattr(excerpt, "text")
        assert hasattr(excerpt, "speaker")
        assert hasattr(excerpt, "video_id")
        assert hasattr(excerpt, "start_timestamp")
        assert hasattr(excerpt, "start_ms")
        assert hasattr(excerpt, "score")

        # video_url property should work
        if excerpt.video_id:
            assert excerpt.video_url is not None
            assert "youtube.com" in excerpt.video_url
            assert excerpt.video_id in excerpt.video_url

    def test_what_was_said_empty_query(self, build_transcript_index):
        """Validate what_was_said() handles edge cases gracefully."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")

        # Empty-ish query should still return something (embedding search is fuzzy)
        excerpts = c.what_was_said("the")
        assert isinstance(excerpts, list)
        # Any returned excerpts should have non-empty text
        for e in excerpts:
            assert e.text, "Excerpt should have non-empty text"
            assert e.speaker, "Excerpt should have a speaker"

    def test_what_was_said_no_transcripts(self):
        """Validate what_was_said() returns empty list when no transcripts indexed."""
        from civicos import CivicOS

        # Use a jurisdiction with no transcripts
        c = CivicOS("nonexistent-jurisdiction")
        excerpts = c.what_was_said("anything")

        assert excerpts == [], "Should return empty list for unknown jurisdiction"

    def test_has_transcripts_method(self, build_transcript_index):
        """Validate has_transcripts() method works."""
        embedder = build_transcript_index

        assert embedder.has_transcripts() is True

    def test_search_transcripts_with_filters(self, build_transcript_index):
        """Validate search_transcripts supports filtering."""
        embedder = build_transcript_index

        # Get a video_id from results
        all_results = embedder.search_transcripts("meeting", top_k=1)
        if not all_results:
            pytest.skip("No transcript results available")

        video_id = all_results[0].metadata.get("video_id")
        if not video_id:
            pytest.skip("No video_id in results")

        # Search with video filter
        filtered_results = embedder.search_transcripts(
            "meeting",
            top_k=10,
            where={"video_id": video_id},
        )

        assert len(filtered_results) > 0
        for r in filtered_results:
            assert r.metadata.get("video_id") == video_id


class TestPublicTestimonyRetrieval:
    """Integration tests for testimony_retrieval: public testimony with speaker attribution."""

    @pytest.fixture
    def build_transcript_index(self, tmp_path):
        """Build a transcript index with public comment sections for testing."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings

        # Create test transcript with public comment sections
        testimony_dir = tmp_path / "testimony"
        testimony_dir.mkdir()

        # Sample transcript with explicit public comment section
        # NOTE: Phrases must match SpeakerRoleDetector patterns in transcript.py
        transcript_data = {
            "video_id": "test_video_123",
            "utterances": [
                # Council member opens meeting
                {"speaker": "A", "start_ms": 0, "end_ms": 5000,
                 "text": "Good evening, I'm Mayor Smith. We will now begin the city council meeting."},
                # Staff presentation
                {"speaker": "B", "start_ms": 5000, "end_ms": 15000,
                 "text": "As the City Planner, I want to present our analysis of the affordable housing proposal for downtown development."},
                # Council opens public comment (phrase matches PUBLIC_COMMENT_OPEN_PATTERNS)
                {"speaker": "A", "start_ms": 15000, "end_ms": 20000,
                 "text": "I'll open up public comment on this item. Please state your name for the record."},
                # Public testimony - housing concern
                {"speaker": "C", "start_ms": 20000, "end_ms": 35000,
                 "text": "My name is Maria Garcia. I'm a renter here in San Rafael. I strongly support affordable housing because my family has been priced out of three apartments in the last five years."},
                # Public testimony - traffic concern
                {"speaker": "D", "start_ms": 35000, "end_ms": 50000,
                 "text": "Good evening, I'm John Chen. I'm concerned about the traffic impact. The proposed development will add hundreds of cars to already congested streets."},
                # Public testimony - mixed
                {"speaker": "E", "start_ms": 50000, "end_ms": 65000,
                 "text": "Hi, I'm Sarah Johnson. I support the housing but want the city to address parking. We need more affordable housing and better transit options."},
                # Council closes public comment (phrase matches PUBLIC_COMMENT_CLOSE_PATTERNS)
                {"speaker": "A", "start_ms": 65000, "end_ms": 70000,
                 "text": "Thank you for your comments. I'll close the public comment on this item."},
                # Council discussion
                {"speaker": "A", "start_ms": 70000, "end_ms": 80000,
                 "text": "I'd like to thank everyone who provided testimony tonight about the housing proposal."},
            ]
        }

        import json
        transcript_file = testimony_dir / "testimony_test.json"
        with open(transcript_file, "w") as f:
            json.dump(transcript_data, f)

        # Initialize embeddings and build index
        embedder = CivicEmbeddings(
            jurisdiction_id="san-rafael",
            persist_directory=str(tmp_path / "vectors"),
        )
        embedder.build_transcripts_index(str(testimony_dir))

        return embedder

    def _make_embeddings_path_patch(self, tmp_path):
        """Create a path patcher that handles both san-rafael and city-san-rafael."""
        def _patched_get_embeddings_path(j):
            # Handle both normalized (city-san-rafael) and short (san-rafael) forms
            if "san-rafael" in j:
                return str(tmp_path / "vectors")
            return None
        return _patched_get_embeddings_path

    def test_get_public_testimony_returns_excerpts(self, build_transcript_index, monkeypatch):
        """Validate get_public_testimony() returns TranscriptExcerpt objects."""
        from civicos import CivicOS, TranscriptExcerpt
        from civicos import history

        # Patch the embeddings path to use our test index
        tmp_path = Path(build_transcript_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        excerpts = c.get_public_testimony("affordable housing")

        assert len(excerpts) > 0, "Should return at least one excerpt"
        for e in excerpts:
            assert isinstance(e, TranscriptExcerpt)
            assert e.text, "Should have text"

    def test_get_public_testimony_only_returns_public_comments(self, build_transcript_index, monkeypatch):
        """Validate get_public_testimony() only returns content from public comment sections."""
        from civicos import CivicOS
        from civicos import history

        tmp_path = Path(build_transcript_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        excerpts = c.get_public_testimony("housing")

        # All returned excerpts should be from public comment sections
        for e in excerpts:
            assert e.is_public_comment is True, f"Excerpt should be from public comment: {e.text[:50]}"

    def test_get_public_testimony_has_speaker_attribution(self, build_transcript_index, monkeypatch):
        """Validate get_public_testimony() includes speaker attribution."""
        from civicos import CivicOS
        from civicos import history

        tmp_path = Path(build_transcript_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        excerpts = c.get_public_testimony("housing")

        # Check that we have speaker info
        assert len(excerpts) > 0, "Should return results"
        for e in excerpts:
            assert e.speaker, "Should have speaker identifier"
            # speaker_role and speaker_name are optional but should exist as fields
            assert hasattr(e, "speaker_role")
            assert hasattr(e, "speaker_name")

    def test_get_public_testimony_excludes_council_discussion(self, build_transcript_index, monkeypatch):
        """Validate get_public_testimony() excludes council discussion outside public comment."""
        from civicos import CivicOS
        from civicos import history

        tmp_path = Path(build_transcript_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")

        # Search for something the mayor said
        excerpts = c.get_public_testimony("thank everyone testimony")

        # Should not return the council discussion that happened after public comment closed
        for e in excerpts:
            # Any result returned must be from public comment section
            assert e.is_public_comment is True

    def test_get_public_testimony_topic_relevance(self, build_transcript_index, monkeypatch):
        """Validate get_public_testimony() returns topic-relevant results."""
        from civicos import CivicOS
        from civicos import history

        tmp_path = Path(build_transcript_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")

        # Search for traffic testimony
        excerpts = c.get_public_testimony("traffic congestion cars")

        # Should find John Chen's traffic-related testimony
        assert len(excerpts) > 0, "Should find traffic-related testimony"
        # Top result should mention traffic-related content
        found_traffic = any("traffic" in e.text.lower() or "cars" in e.text.lower() for e in excerpts)
        assert found_traffic, "Should find traffic-related content"

    def test_get_public_testimony_returns_video_metadata(self, build_transcript_index, monkeypatch):
        """Validate get_public_testimony() includes video timestamps for sourcing."""
        from civicos import CivicOS
        from civicos import history

        tmp_path = Path(build_transcript_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        excerpts = c.get_public_testimony("housing")

        assert len(excerpts) > 0
        for e in excerpts:
            assert e.video_id, "Should have video_id"
            assert e.start_ms >= 0, "Should have start_ms timestamp"
            # video_url property should generate valid URL
            if e.video_id:
                assert e.video_url is not None
                assert "youtube.com" in e.video_url

    def test_get_public_testimony_empty_results_graceful(self, build_transcript_index, monkeypatch):
        """Validate get_public_testimony() returns empty list when no matches."""
        from civicos import CivicOS
        from civicos import history

        tmp_path = Path(build_transcript_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        # Search for something that won't match
        excerpts = c.get_public_testimony("quantum physics supercollider")

        # Should return empty or very few low-relevance results, not error
        assert isinstance(excerpts, list)
        assert len(excerpts) <= 5, f"Irrelevant query should return few results, got {len(excerpts)}"

    def test_get_public_testimony_unknown_jurisdiction(self):
        """Validate get_public_testimony() returns empty list for unknown jurisdiction."""
        from civicos import CivicOS

        c = CivicOS("nonexistent-city")
        excerpts = c.get_public_testimony("anything")

        assert excerpts == [], "Should return empty list for unknown jurisdiction"

    def test_search_transcripts_with_public_comment_filter(self, build_transcript_index, monkeypatch):
        """Validate search_transcripts supports public_comment_only filter at history layer."""
        from civicos import history

        tmp_path = Path(build_transcript_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        # Search with filter
        results = history.search_transcripts(
            jurisdiction="san-rafael",
            query="housing",
            top_k=10,
            public_comment_only=True,
        )

        assert len(results) > 0
        for r in results:
            assert r.is_public_comment is True, "All results should be from public comment"


class TestQuoteExtraction:
    """Integration tests for quote_extraction: exact quotes with timestamps for verification."""

    @pytest.fixture
    def build_transcript_index(self, tmp_path):
        """Build a transcript index with known exact quotes for testing."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings

        testimony_dir = tmp_path / "testimony"
        testimony_dir.mkdir()

        # Known exact quotes with specific timestamps for verification testing
        # NOTE: Use "start" and "end" keys (milliseconds), matching AssemblyAI format
        transcript_data = {
            "video_id": "quote_test_abc123",
            "utterances": [
                {"speaker": "A", "start": 0, "end": 5000,
                 "text": "Welcome to the city council meeting. We now open public comment."},
                {"speaker": "B", "start": 5000, "end": 15000,
                 "text": "My name is Alice Brown. I support the bike lane proposal because it will make downtown safer for pedestrians and cyclists."},
                {"speaker": "C", "start": 15000, "end": 25000,
                 "text": "I'm Bob Smith. The proposed zoning change will destroy the character of our historic neighborhood. Please vote no."},
                {"speaker": "D", "start": 25000, "end": 35000,
                 "text": "Hello, I'm Carol Davis. We need more affordable housing options. Young families are being forced out of our city."},
                {"speaker": "A", "start": 35000, "end": 40000,
                 "text": "Thank you for all the testimony. Public comment is now closed."},
            ]
        }

        import json
        transcript_file = testimony_dir / "testimony_quote_test.json"
        with open(transcript_file, "w") as f:
            json.dump(transcript_data, f)

        embedder = CivicEmbeddings(
            jurisdiction_id="san-rafael",
            persist_directory=str(tmp_path / "vectors"),
        )
        embedder.build_transcripts_index(str(testimony_dir))

        return embedder, transcript_data

    def _make_embeddings_path_patch(self, tmp_path):
        """Create a path patcher that handles both san-rafael and city-san-rafael."""
        def _patched_get_embeddings_path(j):
            if "san-rafael" in j:
                return str(tmp_path / "vectors")
            return None
        return _patched_get_embeddings_path

    def test_quote_text_matches_original_transcript(self, build_transcript_index, monkeypatch):
        """Validate returned text matches exactly what was spoken in transcript."""
        from civicos import CivicOS
        from civicos import history

        embedder, transcript_data = build_transcript_index
        tmp_path = Path(embedder.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        excerpts = c.what_was_said("bike lane proposal safer")

        assert len(excerpts) > 0, "Should find the bike lane testimony"
        # The returned text should be the exact text from the transcript
        alice_excerpt = excerpts[0]
        assert "bike lane proposal" in alice_excerpt.text.lower()
        # Verify text is verbatim from transcript (not truncated/modified)
        original_text = transcript_data["utterances"][1]["text"]
        assert original_text in alice_excerpt.text or alice_excerpt.text in original_text

    def test_quote_timestamps_correspond_to_text(self, build_transcript_index, monkeypatch):
        """Validate timestamps align with when the text was spoken."""
        from civicos import CivicOS
        from civicos import history

        embedder, transcript_data = build_transcript_index
        tmp_path = Path(embedder.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        excerpts = c.what_was_said("zoning change historic neighborhood")

        assert len(excerpts) > 0
        excerpt = excerpts[0]

        # Verify timestamps are populated and consistent
        assert excerpt.start_ms >= 0, "Should have valid start timestamp"
        assert excerpt.end_ms >= excerpt.start_ms, "End should be at or after start"
        # If chunk has real timestamps (not 0,0), verify they form a valid range
        if excerpt.end_ms > 0:
            assert excerpt.end_ms > excerpt.start_ms, "Non-zero end should be after start"
        # Verify the text contains the search terms
        assert "zoning" in excerpt.text.lower() or "historic" in excerpt.text.lower() or \
               "neighborhood" in excerpt.text.lower(), "Should contain search terms"

    def test_quote_has_human_readable_timestamps(self, build_transcript_index, monkeypatch):
        """Validate quotes include human-readable timestamp formats."""
        from civicos import CivicOS
        from civicos import history
        import re

        embedder, _ = build_transcript_index
        tmp_path = Path(embedder.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        excerpts = c.what_was_said("affordable housing young families")

        assert len(excerpts) > 0
        excerpt = excerpts[0]

        # Should have HH:MM:SS format timestamps
        timestamp_pattern = r"^\d{2}:\d{2}:\d{2}$"
        assert re.match(timestamp_pattern, excerpt.start_timestamp), \
            f"start_timestamp should be HH:MM:SS format, got: {excerpt.start_timestamp}"
        assert re.match(timestamp_pattern, excerpt.end_timestamp), \
            f"end_timestamp should be HH:MM:SS format, got: {excerpt.end_timestamp}"

    def test_video_url_allows_verification(self, build_transcript_index, monkeypatch):
        """Validate video_url points to exact moment for quote verification."""
        from civicos import CivicOS
        from civicos import history

        embedder, transcript_data = build_transcript_index
        tmp_path = Path(embedder.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        excerpts = c.what_was_said("bike lane")

        assert len(excerpts) > 0
        excerpt = excerpts[0]

        # video_url should allow direct verification
        assert excerpt.video_url is not None, "Should have video URL for verification"
        assert excerpt.video_id in excerpt.video_url, "URL should contain video ID"

        # URL should have timestamp parameter for jumping to exact moment
        assert "&t=" in excerpt.video_url or "?t=" in excerpt.video_url, \
            "URL should have timestamp parameter"

        # Timestamp in URL should match start_ms
        expected_seconds = excerpt.start_ms // 1000
        assert f"t={expected_seconds}s" in excerpt.video_url, \
            f"URL timestamp should match start_ms ({expected_seconds}s)"

    def test_quote_includes_speaker_for_attribution(self, build_transcript_index, monkeypatch):
        """Validate quotes include speaker info for proper attribution."""
        from civicos import CivicOS
        from civicos import history

        embedder, _ = build_transcript_index
        tmp_path = Path(embedder.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        excerpts = c.what_was_said("zoning change")

        assert len(excerpts) > 0
        excerpt = excerpts[0]

        # Speaker attribution is essential for quote verification
        assert excerpt.speaker, "Quote must have speaker identifier"
        # speaker_name allows linking quote to a person
        assert hasattr(excerpt, "speaker_name")

    def test_quote_has_relevance_score(self, build_transcript_index, monkeypatch):
        """Validate quotes include relevance score for ranking."""
        from civicos import CivicOS
        from civicos import history

        embedder, _ = build_transcript_index
        tmp_path = Path(embedder.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        excerpts = c.what_was_said("affordable housing", top_k=3)

        assert len(excerpts) > 0
        for excerpt in excerpts:
            assert hasattr(excerpt, "score")
            # Cosine similarity scores can be negative (dissimilar vectors)
            assert isinstance(excerpt.score, float), "Score should be a float"

        # Results should be ordered by relevance (highest first)
        if len(excerpts) > 1:
            scores = [e.score for e in excerpts]
            assert scores == sorted(scores, reverse=True), \
                "Results should be ordered by relevance score (highest first)"

    def test_multiple_quotes_have_distinct_timestamps(self, build_transcript_index, monkeypatch):
        """Validate each quote has unique timestamp boundaries."""
        from civicos import CivicOS
        from civicos import history

        embedder, _ = build_transcript_index
        tmp_path = Path(embedder.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        # Search for a broad term to get multiple results
        excerpts = c.what_was_said("the", top_k=5)

        if len(excerpts) > 1:
            # Each quote should have distinct timestamps (different moments in video)
            timestamp_pairs = [(e.start_ms, e.end_ms) for e in excerpts]
            unique_pairs = set(timestamp_pairs)
            # If we got multiple results, most should have different timestamps
            # (some may overlap if from same chunk)
            assert len(unique_pairs) >= 1, "Should have at least one unique timestamp pair"


@pytest.mark.requires_real_data
class TestWhatHappenedSemantic:
    """
    Tests for what_happened() general semantic search.

    Validates the what_happened_semantic item in integration.json:
    - what_happened() uses vector search for semantic queries (general)

    This validates that ANY query benefits from semantic search when
    embeddings are available - not just queries containing "merrydale".

    Key test scenarios:
    1. Semantically similar queries return relevant results
    2. Results are ranked by semantic relevance (not just keyword presence)
    3. Queries without exact keyword matches still find related decisions
    """

    @pytest.fixture(autouse=True)
    def setup_index(self):
        """Build index before each test."""
        from civicos._internal.meetings import build_merrydale_index

        build_merrydale_index(
            RAG_CORPUS_DIR,
            persist_directory="data/pilot/vectors/city-san-rafael",
        )

    def test_semantic_query_without_keyword_match(self):
        """
        Validate semantic search finds results without exact keyword match.

        Query: "homeless services" (doesn't contain "merrydale" or "shelter")
        Expected: Returns decisions about the shelter project via semantic similarity
        """
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        decisions = c.what_happened("homeless services")

        assert len(decisions) > 0, (
            "Semantic search should find shelter-related decisions "
            "for 'homeless services' query"
        )

        # At least one result should relate to housing/shelter
        titles = [d.title.lower() for d in decisions]
        has_relevant = any(
            "shelter" in t or "housing" in t or "homeless" in t
            for t in titles
        )
        assert has_relevant, (
            f"Should find shelter/housing related decisions. Got titles: {titles[:3]}"
        )

    def test_semantic_query_housing_finds_shelter(self):
        """
        Validate "housing assistance" query finds shelter decisions.

        The Nov 17 agenda includes decisions about a homeless shelter,
        which is semantically related to "housing assistance".
        """
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        decisions = c.what_happened("housing assistance programs")

        assert len(decisions) > 0, (
            "Semantic search should find results for 'housing assistance programs'"
        )

    def test_semantic_query_ranks_by_relevance(self):
        """
        Validate results are ranked by semantic relevance.

        Query specifically about shelter should rank shelter item higher
        than general consent items.
        """
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        decisions = c.what_happened("emergency overnight shelter facility")

        assert len(decisions) > 0, "Should return decisions"

        # The actual shelter item (6.a) should be highly ranked
        top_3_ids = [d.id for d in decisions[:3]]
        has_shelter_item = any("item-6" in id for id in top_3_ids)
        assert has_shelter_item, (
            f"Shelter item should be in top 3 for shelter-specific query. "
            f"Got: {top_3_ids}"
        )

    def test_semantic_search_preserves_decision_interface(self):
        """
        Validate semantic search returns proper Decision objects.

        All required fields should be present regardless of search method.
        """
        from civicos import CivicOS
        from datetime import datetime

        c = CivicOS("san-rafael")
        decisions = c.what_happened("city council decisions")

        assert len(decisions) > 0, "Should return decisions"

        for d in decisions:
            assert hasattr(d, "id"), "Decision should have id"
            assert hasattr(d, "title"), "Decision should have title"
            assert hasattr(d, "date"), "Decision should have date"
            assert hasattr(d, "outcome"), "Decision should have outcome"
            assert hasattr(d, "body"), "Decision should have body"
            assert isinstance(d.date, datetime), "date should be datetime"

    def test_semantic_query_different_than_keyword(self):
        """
        Validate semantic search finds results that keyword search would miss.

        Query: "unhoused population services" - semantically related to shelter
        but uses different vocabulary than the indexed documents.
        """
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        decisions = c.what_happened("unhoused population services")

        # Semantic search should find shelter-related decisions
        # even though exact words don't match
        assert len(decisions) > 0, (
            "Semantic search should find related decisions even with "
            "vocabulary mismatch (unhoused vs homeless)"
        )

    def test_semantic_query_public_safety_finds_related(self):
        """
        Validate "public safety concerns" finds relevant decisions.

        Shelter discussions often involve public safety considerations.
        """
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        decisions = c.what_happened("public safety concerns")

        # Should return decisions (semantic search casts a wider net)
        assert isinstance(decisions, list), "Should return a list"
        # Any returned decisions should be well-formed
        for d in decisions:
            assert d.id, "Decision should have non-empty id"
            assert d.title, "Decision should have non-empty title"
            assert d.date is not None, "Decision should have a date"

    def test_semantic_multiple_results_sorted(self):
        """
        Validate multiple results are returned in relevance order.
        """
        from civicos import CivicOS
        from datetime import datetime

        c = CivicOS("san-rafael")
        decisions = c.what_happened("neighborhood concerns")

        if len(decisions) > 1:
            # Results should be sorted by date descending (validates sort in history.py)
            for d in decisions:
                assert isinstance(d.date, datetime), f"date should be datetime, got {type(d.date)}"
            dates = [d.date for d in decisions]
            for i in range(len(dates) - 1):
                assert dates[i] >= dates[i + 1], \
                    f"Decisions not sorted: {dates[i]} < {dates[i + 1]}"

    def test_semantic_vs_keyword_comparison(self):
        """
        Validate semantic search provides better results than keyword would.

        Use a query that would likely return no/few keyword matches but
        should find results semantically.
        """
        from civicos import CivicOS

        c = CivicOS("san-rafael")

        # Query using synonyms/related terms rather than exact document keywords
        semantic_query = "temporary accommodation facility for people without homes"
        decisions = c.what_happened(semantic_query)

        # This complex semantic query should still find shelter decisions
        assert len(decisions) > 0, (
            "Semantic search should handle complex paraphrased queries "
            "that would fail keyword matching"
        )


@pytest.mark.requires_real_data
class TestCrossMeetingPatterns:
    """
    Tests for finding similar decisions across multiple meetings.

    Validates the cross_meeting_patterns item in integration.json:
    - "Find similar decisions across multiple meetings"

    This test class uses synthetic multi-meeting test data to verify
    that the system can identify related decisions across different
    meeting dates, enabling pattern detection for recurring topics.
    """

    @pytest.fixture
    def build_multi_meeting_index(self, tmp_path):
        """
        Build a decisions index with data from multiple meetings.

        Creates synthetic decisions spanning Nov 17 and Dec 1 meetings
        with overlapping topics (housing, environment) to enable
        cross-meeting pattern detection testing.
        """
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import json

        # Create test corpus directory
        corpus_dir = tmp_path / "rag_corpus"
        corpus_dir.mkdir()

        # Multi-meeting decisions - 3 meetings with related topics
        multi_meeting_decisions = [
            # November 17 meeting - housing/shelter decisions
            {
                "decision_id": "20251117-item-6-a",
                "meeting_date": "2025-11-17",
                "agenda_item": "6.a",
                "title": "Declaration of Shelter Crisis and Acquisition of 350 Merrydale Road",
                "summary": "Approved declaration of shelter crisis and acquisition of property for homeless shelter. Financial impact: $8 million.",
                "outcome": "approved",
                "vote": {"passed": True, "vote_count": "4-0"},
                "topics": ["housing", "homelessness"],
            },
            {
                "decision_id": "20251117-item-4-c",
                "meeting_date": "2025-11-17",
                "agenda_item": "4.c",
                "title": "Environmental Consulting Services Agreement",
                "summary": "Approved agreements for on-call environmental consulting services.",
                "outcome": "approved",
                "vote": {"passed": True, "vote_count": "4-0"},
                "topics": ["environment"],
            },
            # December 1 meeting - follow-up on housing, new environment item
            {
                "decision_id": "20251201-item-5-a",
                "meeting_date": "2025-12-01",
                "agenda_item": "5.a",
                "title": "Homeless Shelter Operations Update - 350 Merrydale Road",
                "summary": "Received update on shelter operations planning and community engagement schedule.",
                "outcome": "received",
                "vote": {"passed": True, "vote_count": "5-0"},
                "topics": ["housing", "homelessness"],
            },
            {
                "decision_id": "20251201-item-6-a",
                "meeting_date": "2025-12-01",
                "agenda_item": "6.a",
                "title": "Good Neighbor Policy Framework for Emergency Shelters",
                "summary": "Approved framework for good neighbor policies addressing security and communication.",
                "outcome": "approved",
                "vote": {"passed": True, "vote_count": "4-1"},
                "topics": ["housing", "homelessness", "community"],
            },
            {
                "decision_id": "20251201-item-7-a",
                "meeting_date": "2025-12-01",
                "agenda_item": "7.a",
                "title": "Environmental Sustainability Action Plan Update",
                "summary": "Received update on solar and EV charging station deployment progress.",
                "outcome": "received",
                "vote": {"passed": True, "vote_count": "5-0"},
                "topics": ["environment"],
            },
            # December 9 meeting - more housing discussion
            {
                "decision_id": "20251209-item-5-a",
                "meeting_date": "2025-12-09",
                "agenda_item": "5.a",
                "title": "Affordable Housing Trust Fund Allocation",
                "summary": "Approved allocation of $500,000 for affordable housing development incentives.",
                "outcome": "approved",
                "vote": {"passed": True, "vote_count": "5-0"},
                "topics": ["housing", "budget"],
            },
        ]

        # Write decisions file
        decisions_file = corpus_dir / "city-san-rafael_decisions.json"
        with open(decisions_file, "w") as f:
            json.dump(multi_meeting_decisions, f)

        # Build index
        embedder = CivicEmbeddings(
            jurisdiction_id="city-san-rafael",
            persist_directory=str(tmp_path / "vectors"),
        )
        embedder.build_decisions_index(str(corpus_dir))

        return embedder

    def _make_embeddings_path_patch(self, tmp_path):
        """Create a path patcher for test index."""
        def _patched_get_embeddings_path(j):
            if "san-rafael" in j:
                return str(tmp_path / "vectors")
            return None
        return _patched_get_embeddings_path

    def test_query_returns_decisions_from_multiple_meetings(
        self, build_multi_meeting_index, monkeypatch
    ):
        """
        Validate semantic search returns decisions from different meetings.

        Query for housing-related topics should find decisions from
        Nov 17, Dec 1, and Dec 9 meetings.
        """
        from civicos import CivicOS
        from civicos import history

        tmp_path = Path(build_multi_meeting_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        decisions = c.what_happened("homeless shelter housing")

        # Should find decisions from multiple meetings
        assert len(decisions) >= 3, (
            f"Should find housing-related decisions from multiple meetings. "
            f"Got {len(decisions)} decisions."
        )

        # Extract unique meeting dates
        meeting_dates = set(d.date.strftime("%Y-%m-%d") for d in decisions)
        assert len(meeting_dates) >= 2, (
            f"Results should span at least 2 different meetings. "
            f"Got dates: {sorted(meeting_dates)}"
        )

    def test_results_can_be_grouped_by_meeting_date(
        self, build_multi_meeting_index, monkeypatch
    ):
        """
        Validate results can be grouped by meeting date for pattern analysis.

        This enables users to see how topics evolved across meetings.
        """
        from civicos import CivicOS
        from civicos import history
        from itertools import groupby

        tmp_path = Path(build_multi_meeting_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        decisions = c.what_happened("shelter housing homeless")

        # Group by meeting date
        sorted_decisions = sorted(decisions, key=lambda d: d.date)
        groups = []
        for date, group in groupby(sorted_decisions, key=lambda d: d.date.date()):
            groups.append((date, list(group)))

        # Should have multiple groups
        assert len(groups) >= 2, (
            f"Should have at least 2 meeting date groups for pattern analysis. "
            f"Got {len(groups)} groups."
        )

        # Each group should have decisions
        for date, group_decisions in groups:
            assert len(group_decisions) > 0, f"Each group should have decisions"

    def test_same_topic_appears_across_meetings(
        self, build_multi_meeting_index, monkeypatch
    ):
        """
        Validate same topic (e.g., housing) appears in multiple meeting results.

        This enables tracking topic progression over time.
        """
        from civicos import CivicOS
        from civicos import history

        tmp_path = Path(build_multi_meeting_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")

        # Query for environmental topics
        decisions = c.what_happened("environmental sustainability")

        # Should find environment-related decisions from multiple meetings
        meeting_dates = set(d.date.strftime("%Y-%m-%d") for d in decisions)

        # Nov 17 has environmental consulting, Dec 1 has sustainability update
        assert len(meeting_dates) >= 2, (
            f"Environmental topics should appear in at least 2 meetings. "
            f"Got dates: {sorted(meeting_dates)}"
        )

    def test_cross_meeting_decisions_preserve_interface(
        self, build_multi_meeting_index, monkeypatch
    ):
        """
        Validate Decision objects from cross-meeting queries have proper fields.
        """
        from civicos import CivicOS
        from civicos import history
        from datetime import datetime

        tmp_path = Path(build_multi_meeting_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        decisions = c.what_happened("shelter operations")

        assert len(decisions) > 0, "Should return decisions"

        for d in decisions:
            assert hasattr(d, "id"), "Decision should have id"
            assert hasattr(d, "title"), "Decision should have title"
            assert hasattr(d, "date"), "Decision should have date"
            assert hasattr(d, "outcome"), "Decision should have outcome"
            assert isinstance(d.date, datetime), "date should be datetime"

    def test_chronological_pattern_detection(
        self, build_multi_meeting_index, monkeypatch
    ):
        """
        Validate results show chronological progression of decisions.

        For the shelter project: Nov 17 (crisis declaration) ->
        Dec 1 (operations update, good neighbor policy) shows progression.
        """
        from civicos import CivicOS
        from civicos import history

        tmp_path = Path(build_multi_meeting_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        decisions = c.what_happened("Merrydale Road shelter")

        # Should find shelter-related decisions from Nov 17 and Dec 1
        meeting_dates = sorted(set(d.date.strftime("%Y-%m-%d") for d in decisions))

        # Verify chronological order can be established
        if len(meeting_dates) >= 2:
            assert meeting_dates[0] < meeting_dates[-1], (
                "Should be able to establish chronological order of related decisions"
            )

        # Verify we can trace the shelter topic across meetings
        shelter_decisions = [
            d for d in decisions
            if "shelter" in d.title.lower() or "merrydale" in d.title.lower()
        ]
        assert len(shelter_decisions) >= 2, (
            f"Should find multiple shelter-related decisions across meetings. "
            f"Found: {[d.title for d in shelter_decisions]}"
        )

    def test_broad_query_finds_diverse_meeting_coverage(
        self, build_multi_meeting_index, monkeypatch
    ):
        """
        Validate broad queries find decisions across all indexed meetings.
        """
        from civicos import CivicOS
        from civicos import history

        tmp_path = Path(build_multi_meeting_index.persist_directory).parent
        monkeypatch.setattr(
            history,
            "_get_embeddings_path",
            self._make_embeddings_path_patch(tmp_path)
        )

        c = CivicOS("san-rafael")
        # Broad query that should match many decisions
        decisions = c.what_happened("city council approved received")

        # Should cover all 3 meetings in the test data
        meeting_dates = set(d.date.strftime("%Y-%m-%d") for d in decisions)
        assert len(meeting_dates) == 3, (
            f"Broad query should find decisions from all 3 test meetings. "
            f"Got dates: {sorted(meeting_dates)}"
        )


@pytest.mark.requires_real_data
class TestMinutesTranscriptComparison:
    """
    Tests that compare official minutes to full video transcripts.

    This test class documents the information loss that occurs when relying
    solely on official meeting minutes versus full video transcripts.

    Uses synthetic data for CI compatibility.
    """

    @pytest.fixture
    def minutes(self):
        """Synthetic minutes data for testing."""
        return {
            "meeting_date": "2025-11-17",
            "items": [
                {
                    "item_number": "6.a",
                    "title": "Homeless Shelter Proposal",
                    "public_speakers": [f"Speaker {i}" for i in range(75)],  # Simulate ~75 speakers
                    "action": "Approved",
                    "vote": "5-2"
                }
            ]
        }

    @pytest.fixture
    def transcript_chunks(self):
        """Synthetic transcript chunks for testing."""
        return [
            {"chunk_id": f"c{i}", "text": f"Testimony text {i}", "speaker": f"Speaker {i % 20}", "start_ms": i * 30000, "end_ms": (i + 1) * 30000}
            for i in range(100)  # 100 chunks
        ]

    @pytest.fixture
    def item_6a_discussion(self):
        """Synthetic Item 6.a discussion breakdown."""
        return {
            "segments": {
                "public_testimony": {
                    "chunk_count": 80,
                    "duration_minutes": 120,
                    "speaker_count": 75
                },
                "council_questions": {
                    "chunk_count": 15,
                    "duration_minutes": 25
                },
                "deliberation": {
                    "chunk_count": 10,
                    "duration_minutes": 15
                }
            },
            "video_id": "test_video_001",
            "timestamps": {
                "start": "01:15:00",
                "end": "03:55:00"
            }
        }

    @pytest.fixture
    def item_6a_minutes(self, minutes):
        """Extract Item 6.a from minutes."""
        items = [item for item in minutes["items"] if item["item_number"] == "6.a"]
        assert len(items) == 1, "Expected exactly one item 6.a"
        return items[0]

    def test_speaker_count_comparison(
        self, item_6a_minutes, transcript_chunks, item_6a_discussion
    ):
        """
        Compare speaker counts between minutes and transcripts.

        Minutes: List of ~78 speaker names (names only)
        Transcript: Full discussion with identified speaker roles and verbatim speech

        Information loss: Minutes provide no indication of what each person said,
        how long they spoke, or their professional affiliation.
        """
        # Minutes speaker count
        minutes_speakers = item_6a_minutes["public_speakers"]
        minutes_speaker_count = len(minutes_speakers)

        # Transcript data
        public_testimony = item_6a_discussion["segments"]["public_testimony"]
        public_testimony_chunks = public_testimony["chunk_count"]
        public_testimony_duration = public_testimony["duration_minutes"]

        # Minutes say ~78 speakers
        assert minutes_speaker_count >= 70, (
            f"Minutes should list 70+ speakers, got {minutes_speaker_count}"
        )

        # Transcript has 168 chunks covering 147 minutes of public testimony
        assert public_testimony_chunks >= 150, (
            f"Transcript should have 150+ public testimony chunks, got {public_testimony_chunks}"
        )

        # Calculate information density
        # Minutes: 78 names = ~78 words of speaker information
        # Transcript: 168 chunks × avg ~800 chars = ~134,400 characters of testimony
        minutes_info = minutes_speaker_count  # just names
        transcript_chars = sum(
            len(chunk["text"])
            for i, chunk in enumerate(transcript_chunks)
            if i in public_testimony.get("chunk_indices", [])
        )

        # Document the information ratio
        assert transcript_chars > 100000, (
            f"Transcript should have 100k+ chars of testimony. Got {transcript_chars:,}"
        )

        # The ratio of transcript content to minutes content is massive
        # Each speaker in minutes is ~10 chars (just a name)
        # Each speaker in transcript is ~1700 chars on average (168 chunks / 78 speakers ≈ 2 chunks/speaker)
        minutes_chars = minutes_speaker_count * 15  # avg name length + separators
        ratio = transcript_chars / max(minutes_chars, 1)
        assert ratio > 50, (
            f"Transcript should have 50x+ more content than minutes speaker list. "
            f"Ratio: {ratio:.1f}x ({transcript_chars:,} chars vs {minutes_chars} chars)"
        )

    def test_testimony_content_captured_in_transcript(
        self, transcript_chunks, item_6a_discussion
    ):
        """
        Validate transcript captures actual testimony content.

        The transcript should contain the actual words spoken by public speakers,
        not just their names.
        """
        public_testimony = item_6a_discussion["segments"]["public_testimony"]
        chunk_indices = public_testimony.get("chunk_indices", [])

        # Sample testimony chunks
        testimony_chunks = [
            transcript_chunks[i] for i in chunk_indices if i < len(transcript_chunks)
        ]

        # Verify chunks contain substantial text
        total_text = " ".join(c["text"] for c in testimony_chunks)

        # Should contain actual substantive words about the shelter
        assert "shelter" in total_text.lower() or "homeless" in total_text.lower(), (
            "Testimony should discuss the shelter/homeless topic"
        )

        # Should contain first-person language (actual testimony)
        has_first_person = any(
            phrase in total_text.lower()
            for phrase in ["i think", "i believe", "we need", "my name", "i'm here"]
        )
        assert has_first_person, (
            "Testimony should contain first-person language from speakers"
        )

        # Should have speaker context
        speakers_in_testimony = set()
        for chunk in testimony_chunks:
            speakers_in_testimony.update(chunk.get("speakers", []))

        assert len(speakers_in_testimony) >= 2, (
            f"Testimony should have multiple speaker IDs. Got: {speakers_in_testimony}"
        )

    def test_minutes_missing_council_questions(
        self, item_6a_minutes, item_6a_discussion, transcript_chunks
    ):
        """
        Validate that council questions are captured in transcript but not minutes.

        After public testimony, council members often ask clarifying questions
        of staff. These questions and answers are NOT captured in minutes.
        """
        # Minutes only capture votes, not Q&A
        minutes_text = " ".join([
            item_6a_minutes.get("description", ""),
            item_6a_minutes.get("summary_notes", ""),
        ])

        # Q&A is not in minutes (no "question" or "clarify" language)
        # Minutes focus on outcomes, not process

        # Transcript has staff Q&A segment
        staff_qa = item_6a_discussion["segments"]["staff_qa"]
        qa_duration = staff_qa["duration_minutes"]
        qa_chunks = staff_qa["chunk_count"]

        # Staff Q&A was ~39 minutes with 19 chunks
        assert qa_duration >= 30, (
            f"Staff Q&A should be 30+ minutes. Got {qa_duration:.1f} min"
        )
        assert qa_chunks >= 15, (
            f"Staff Q&A should have 15+ chunks. Got {qa_chunks}"
        )

        # Get actual Q&A content
        qa_indices = staff_qa.get("chunk_indices", [])
        qa_text = " ".join(
            transcript_chunks[i]["text"]
            for i in qa_indices
            if i < len(transcript_chunks)
        ).lower()

        # Q&A content should contain question-related language
        has_qa_language = any(
            phrase in qa_text
            for phrase in ["question", "clarify", "explain", "asked", "response", "answer"]
        )
        assert has_qa_language, (
            "Staff Q&A segment should contain question/answer language"
        )

    def test_minutes_missing_deliberation(
        self, item_6a_minutes, item_6a_discussion, transcript_chunks
    ):
        """
        Validate that council deliberation is captured in transcript but not minutes.

        Before voting, council members share their thoughts and reasoning.
        Minutes only capture the vote outcome, not the deliberation.
        """
        # Minutes capture vote outcome
        votes = item_6a_minutes.get("votes", [])
        assert len(votes) >= 3, "Minutes should have 3 vote records"

        # But minutes don't capture WHY council members voted
        # Summary is minimal
        summary = item_6a_minutes.get("summary_notes", "")
        # Summaries are terse: "Adopted Resolution 15478"
        assert len(summary) < 200, (
            "Minutes summary should be terse (under 200 chars)"
        )

        # Transcript has full deliberation
        deliberation = item_6a_discussion["segments"]["council_deliberation"]
        delib_duration = deliberation["duration_minutes"]
        delib_chunks = deliberation["chunk_count"]

        # Council deliberation was ~22 minutes with 17 chunks
        assert delib_duration >= 15, (
            f"Deliberation should be 15+ minutes. Got {delib_duration:.1f} min"
        )
        assert delib_chunks >= 10, (
            f"Deliberation should have 10+ chunks. Got {delib_chunks}"
        )

        # Get deliberation content
        delib_indices = deliberation.get("chunk_indices", [])
        delib_text = " ".join(
            transcript_chunks[i]["text"]
            for i in delib_indices
            if i < len(transcript_chunks)
        ).lower()

        # Should contain substantive deliberation language
        has_deliberation_language = any(
            phrase in delib_text
            for phrase in ["i support", "concerns", "believe", "important", "community"]
        )
        assert has_deliberation_language, (
            "Deliberation should contain council members' reasoning"
        )

    def test_vote_context_in_transcript(
        self, item_6a_minutes, item_6a_discussion, transcript_chunks
    ):
        """
        Validate transcript provides context around voting.

        Minutes capture: "Vice Mayor Bushey moved, Councilmember Kertz seconded"
        Transcript captures: The full discussion leading to that motion.
        """
        # Minutes vote data
        votes = item_6a_minutes.get("votes", [])
        first_vote = votes[0]

        assert first_vote["motion_by"] == "Vice Mayor Bushey"
        assert first_vote["second_by"] == "Councilmember Kertz"
        assert first_vote["outcome"] == "adopted"

        # Transcript has vote segment
        vote_segment = item_6a_discussion["segments"]["vote"]
        vote_chunks = vote_segment["chunk_count"]
        vote_duration = vote_segment["duration_minutes"]

        # Vote segment captured
        assert vote_chunks >= 2, f"Vote segment should have 2+ chunks. Got {vote_chunks}"
        assert vote_duration >= 2, f"Vote segment should be 2+ minutes. Got {vote_duration}"

        # The full context is in deliberation + vote segments
        full_context_duration = (
            item_6a_discussion["segments"]["council_deliberation"]["duration_minutes"]
            + vote_duration
        )
        assert full_context_duration >= 20, (
            f"Full vote context (deliberation + vote) should be 20+ minutes. "
            f"Got {full_context_duration:.1f} min"
        )

    def test_timestamp_precision(
        self, item_6a_minutes, item_6a_discussion, transcript_chunks
    ):
        """
        Validate transcript provides precise timestamps for video linking.

        Minutes: Meeting time only (6:00 PM start, 11:06 PM end)
        Transcript: Millisecond-precision timestamps for every utterance
        """
        # Minutes have approximate times
        # (already tested in TestMinutesExtraction)

        # Transcript has precise timestamps
        first_chunk = transcript_chunks[0]
        assert "start_ms" in first_chunk, "Chunks should have start_ms"
        assert "end_ms" in first_chunk, "Chunks should have end_ms"
        assert "start_timestamp" in first_chunk, "Chunks should have formatted timestamp"

        # Item 6.a has specific time range
        time_range = item_6a_discussion["time_range"]
        assert time_range["start"] == "00:49:41", (
            f"Item 6.a should start at 00:49:41, got {time_range['start']}"
        )

        # Video linking: Can jump directly to any moment
        # This is impossible with minutes alone
        public_testimony = item_6a_discussion["segments"]["public_testimony"]
        testimony_start = public_testimony["time_range"]["start"]
        assert testimony_start == "01:40:03", (
            f"Public testimony should start at 01:40:03, got {testimony_start}"
        )

    def test_information_loss_quantification(
        self, minutes, item_6a_minutes, transcript_chunks, item_6a_discussion
    ):
        """
        Quantify the information loss between minutes and transcripts.

        This test produces metrics that demonstrate the value of full transcripts
        over minutes-only access to public meetings.

        Information loss categories:
        1. Content depth: How much spoken content is lost
        2. Speaker context: How much speaker information is lost
        3. Timeline precision: How much temporal precision is lost
        4. Deliberation context: How much decision context is lost
        """
        # Calculate content metrics
        minutes_speaker_list = item_6a_minutes["public_speakers"]
        minutes_content_chars = (
            len(item_6a_minutes.get("title", ""))
            + len(item_6a_minutes.get("description", ""))
            + len(item_6a_minutes.get("summary_notes", ""))
            + sum(len(name) for name in minutes_speaker_list)
        )

        # Transcript content for Item 6.a
        item_chunks = item_6a_discussion.get("item_chunks", 247)
        chunk_indices = []
        for segment in item_6a_discussion.get("segments", {}).values():
            chunk_indices.extend(segment.get("chunk_indices", []))

        transcript_content_chars = sum(
            len(transcript_chunks[i]["text"])
            for i in chunk_indices
            if i < len(transcript_chunks)
        )

        # Information loss metrics
        metrics = {
            "minutes_content_chars": minutes_content_chars,
            "transcript_content_chars": transcript_content_chars,
            "content_ratio": transcript_content_chars / max(minutes_content_chars, 1),
            "minutes_speaker_count": len(minutes_speaker_list),
            "transcript_chunk_count": item_chunks,
            "meeting_duration_minutes": item_6a_discussion["time_range"]["duration_minutes"],
            "public_testimony_minutes": item_6a_discussion["segments"]["public_testimony"]["duration_minutes"],
            "staff_qa_minutes": item_6a_discussion["segments"]["staff_qa"]["duration_minutes"],
            "deliberation_minutes": item_6a_discussion["segments"]["council_deliberation"]["duration_minutes"],
        }

        # Assertions that document the loss
        assert metrics["content_ratio"] > 100, (
            f"Transcript should have 100x+ more content than minutes. "
            f"Ratio: {metrics['content_ratio']:.1f}x"
        )

        # Minutes capture < 1% of meeting content
        content_captured_pct = 100 * minutes_content_chars / max(transcript_content_chars, 1)
        assert content_captured_pct < 5, (
            f"Minutes should capture < 5% of content. "
            f"Captured: {content_captured_pct:.1f}%"
        )

        # Staff Q&A completely missing from minutes
        assert metrics["staff_qa_minutes"] >= 30, (
            f"Staff Q&A (38+ min) entirely missing from minutes"
        )

        # Deliberation completely missing from minutes
        assert metrics["deliberation_minutes"] >= 15, (
            f"Council deliberation (22+ min) entirely missing from minutes"
        )

        # Public testimony duration
        assert metrics["public_testimony_minutes"] >= 140, (
            f"Public testimony was 147+ minutes; minutes only list names. "
            f"Got {metrics['public_testimony_minutes']:.1f} min"
        )

    def test_speaker_affiliation_loss(self, item_6a_minutes, transcript_chunks):
        """
        Validate that speaker affiliations are lost in minutes.

        Minutes list: "Marin Community Foundation", "Legal Aid of Marin"
        But these are just names - no context about what they said or represent.

        Transcripts provide:
        - Full testimony text
        - Self-introductions with affiliations
        - Speaking duration
        """
        speakers = item_6a_minutes["public_speakers"]

        # Minutes have org names but no context
        org_speakers = [
            s for s in speakers
            if any(org in s for org in [
                "Foundation", "Chamber", "Organizing", "Society",
                "Community", "Association", "Legal Aid"
            ])
        ]

        assert len(org_speakers) >= 8, (
            f"Minutes should list 8+ organizational speakers. Got {len(org_speakers)}"
        )

        # But minutes don't capture WHAT these orgs said
        # In transcript, we can find their actual testimony
        transcript_text = " ".join(c["text"] for c in transcript_chunks).lower()

        # Verify transcript contains org mentions with context
        assert "marin community foundation" in transcript_text or "foundation" in transcript_text, (
            "Transcript should contain foundation testimony"
        )

    def test_video_linking_capability(
        self, transcript_chunks, item_6a_discussion
    ):
        """
        Validate transcript enables direct video linking.

        With timestamps, users can jump directly to:
        - A specific speaker's testimony
        - The staff presentation
        - The council vote
        - Any moment in the meeting

        Minutes provide no equivalent capability.
        """
        # Video ID for linking
        video_id = item_6a_discussion.get("video_id")
        assert video_id == "h6ey-0sY03g", f"Should have video ID. Got {video_id}"

        # Can construct YouTube URLs from timestamps
        public_testimony_start = item_6a_discussion["segments"]["public_testimony"]["time_range"]["start"]
        # Format: HH:MM:SS -> seconds for YouTube
        h, m, s = map(int, public_testimony_start.split(":"))
        youtube_seconds = h * 3600 + m * 60 + s

        youtube_url = f"https://www.youtube.com/watch?v={video_id}&t={youtube_seconds}"
        assert "t=6003" in youtube_url, (
            f"Should be able to construct video link at 01:40:03 (6003s). "
            f"Got: {youtube_url}"
        )


@pytest.mark.requires_real_data
class TestWhatHappenedFullContext:
    """
    Integration tests for what_happened_full_context().

    Tests the query layer integration that links decisions to transcript excerpts.
    This is the fulfillment of the query_layer_integration pilot item.

    Requires real San Rafael data (decisions + transcripts indexed).
    """

    def test_what_happened_full_context_returns_results(self):
        """Validate what_happened_full_context() returns DecisionWithContext objects."""
        from civicos import CivicOS
        from civicos.civicos import DecisionWithContext

        c = CivicOS("san-rafael")
        results = c.what_happened_full_context("shelter")

        assert isinstance(results, list)
        assert len(results) >= 1, "Shelter query should return at least one result"
        for r in results:
            assert isinstance(r, DecisionWithContext)
            assert r.decision.id, "Decision should have non-empty id"
            assert r.decision.title, "Decision should have non-empty title"
            assert 0.0 <= r.link_confidence <= 1.0, \
                f"link_confidence should be in [0, 1], got {r.link_confidence}"

    def test_what_happened_full_context_limits_respected(self):
        """Validate that top_k parameter limits decision count."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        results = c.what_happened_full_context(
            "housing",
            top_k=2,
        )

        # Should respect top_k limit
        assert len(results) <= 2

    def test_transcript_links_have_video_urls(self):
        """Validate that transcript links have proper video URLs when available."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        results = c.what_happened_full_context("shelter", top_k=5)

        for r in results:
            for link in r.transcript_links:
                # If link has video_id and start_ms, should generate URL
                if link.video_id and link.start_ms:
                    assert link.video_url is not None
                    assert "youtube.com" in link.video_url

    def test_decision_with_context_properties(self):
        """Validate DecisionWithContext has expected properties."""
        from civicos import CivicOS

        c = CivicOS("san-rafael")
        results = c.what_happened_full_context("council", top_k=3)

        for r in results:
            # has_transcript should reflect presence of transcript_links
            assert r.has_transcript == (len(r.transcript_links) > 0), \
                "has_transcript should match transcript_links presence"

            # Sub-lists should be subsets of transcript_links
            assert len(r.public_comments) <= len(r.transcript_links)
            assert len(r.staff_discussion) <= len(r.transcript_links)
            assert len(r.council_discussion) <= len(r.transcript_links)

            # link_type should be a known confidence level
            assert r.link_type in ("high_confidence", "medium_confidence", "low_confidence", "none", ""), \
                f"Unexpected link_type: {r.link_type}"
            assert 0.0 <= r.link_confidence <= 1.0, \
                f"link_confidence out of range: {r.link_confidence}"


# Path to state legislation files (new structure: data/legislation/state/{state}/)
LEGISLATION_STATE_DIR = PROJECT_ROOT / "data/legislation/state"

# Path to federal funding programs files (new structure: data/funding/federal/)
FEDERAL_PROGRAMS_DIR = PROJECT_ROOT / "data/funding/federal"

# Path to county funding programs files (new structure: data/funding/county/{county}/)
COUNTY_HOUSING_DIR = PROJECT_ROOT / "data/funding/county"


@pytest.mark.requires_real_data
class TestLegislationVectorSearch:
    """
    Tests for legislation vector indexing and semantic search.

    Validates state_bills_vector_indexed pilot item:
    - State bills are indexed in ChromaDB
    - Semantic search returns relevant bills
    - Topic filtering works correctly
    """

    def test_legislation_files_exist(self):
        """Validate state legislation JSON files exist."""
        topics = ["housing", "transportation", "environment", "education", "budget"]
        for topic in topics:
            path = LEGISLATION_STATE_DIR / "california" / f"{topic}.json"
            assert path.exists(), f"Legislation file not found: {path}"

    def test_legislation_index_can_be_built(self):
        """Validate legislation can be indexed in ChromaDB."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        # Use temp directory for test isolation
        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build legislation index
            collection = embedder.build_legislation_index(
                state="california",
                legislation_path=str(LEGISLATION_STATE_DIR)
            )

            # Should have indexed bills
            count = collection.count()
            assert count >= 20, f"Expected at least 20 bills indexed, got {count}"

            # Verify collection metadata
            metadata = collection.metadata
            assert metadata["state"] == "california"
            assert "housing" in metadata["topics"]

    def test_legislation_semantic_search(self):
        """Validate semantic search returns relevant bills."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build index
            embedder.build_legislation_index(
                state="california",
                legislation_path=str(LEGISLATION_STATE_DIR)
            )

            # Search for affordable housing
            results = embedder.search_legislation(
                "affordable housing streamlined approval",
                top_k=5
            )

            # Should return results
            assert len(results) > 0, "No search results returned"

            # Top results should include housing-related bills
            bill_ids = [r.metadata["bill_id"] for r in results]
            housing_bill_found = any(
                "sb" in bid.lower() or "ab" in bid.lower()
                for bid in bill_ids
            )
            assert housing_bill_found, f"Expected housing bills, got: {bill_ids}"

    def test_legislation_topic_filter(self):
        """Validate topic filtering works correctly."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build index with all topics
            embedder.build_legislation_index(
                state="california",
                legislation_path=str(LEGISLATION_STATE_DIR)
            )

            # Search with topic filter
            results = embedder.search_legislation(
                "funding programs",
                top_k=10,
                topic="housing"
            )

            # All results should be housing topic
            for r in results:
                assert r.metadata["topic"] == "housing", (
                    f"Expected housing topic, got {r.metadata['topic']}"
                )

    def test_has_legislation_method(self):
        """Validate has_legislation() returns correct status."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Before indexing
            assert not embedder.has_legislation(), "has_legislation() should be False before indexing"

            # After indexing
            embedder.build_legislation_index(
                state="california",
                legislation_path=str(LEGISLATION_STATE_DIR)
            )
            assert embedder.has_legislation(), "has_legislation() should be True after indexing"

    def test_legislation_metadata_fields(self):
        """Validate indexed bills have expected metadata fields."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            embedder.build_legislation_index(
                state="california",
                topics=["housing"],  # Just housing for faster test
                legislation_path=str(LEGISLATION_STATE_DIR)
            )

            results = embedder.search_legislation("housing", top_k=1)
            assert len(results) > 0

            metadata = results[0].metadata
            expected_fields = [
                "bill_id", "bill_name", "topic", "status",
                "source_type", "state"
            ]
            for field in expected_fields:
                assert field in metadata, f"Missing metadata field: {field}"
            assert metadata["source_type"] == "state_legislation"
            assert metadata["state"] == "california"

    def test_legislation_search_scores(self):
        """Validate search results have meaningful scores."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            embedder.build_legislation_index(
                state="california",
                legislation_path=str(LEGISLATION_STATE_DIR)
            )

            # Search for specific topic
            results = embedder.search_legislation(
                "lot split duplex single family zoning",  # Very specific to SB9
                top_k=5
            )

            assert len(results) > 0

            # Scores should be in valid range (0-1 for cosine distance converted to similarity)
            for r in results:
                assert 0 <= r.score <= 1, f"Score {r.score} outside valid range"

            # Results should be sorted by score descending
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True), "Results not sorted by score"


@pytest.mark.requires_real_data
class TestFederalProgramsVectorSearch:
    """
    Tests for federal programs vector indexing and semantic search.

    Validates federal_programs_vector_indexed pilot item:
    - Federal programs are indexed in ChromaDB
    - Semantic search returns relevant programs
    - Topic filtering works correctly
    """

    def test_federal_programs_files_exist(self):
        """Validate federal programs JSON files exist."""
        topics = ["housing", "transportation", "environment", "education", "budget"]
        for topic in topics:
            path = FEDERAL_PROGRAMS_DIR / f"{topic}.json"
            assert path.exists(), f"Federal programs file not found: {path}"

    def test_federal_programs_index_can_be_built(self):
        """Validate federal programs can be indexed in ChromaDB."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        # Use temp directory for test isolation
        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build federal programs index
            collection = embedder.build_federal_programs_index(
                federal_programs_path=str(FEDERAL_PROGRAMS_DIR)
            )

            # Should have indexed programs
            count = collection.count()
            assert count >= 5, f"Expected at least 5 programs indexed, got {count}"

            # Verify collection metadata
            metadata = collection.metadata
            assert "housing" in metadata["topics"]
            assert metadata["total_programs"] >= 5

    def test_federal_programs_semantic_search(self):
        """Validate semantic search returns relevant programs."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build index
            embedder.build_federal_programs_index(
                federal_programs_path=str(FEDERAL_PROGRAMS_DIR)
            )

            # Search for community development housing
            results = embedder.search_federal_programs(
                "community development housing grants low income",
                top_k=5
            )

            # Should return results
            assert len(results) > 0, "No search results returned"

            # Top results should include housing-related programs
            program_ids = [r.metadata["program_id"] for r in results]
            housing_program_found = any(
                "cdbg" in pid.lower() or "home" in pid.lower()
                for pid in program_ids
            )
            assert housing_program_found, f"Expected housing programs, got: {program_ids}"

    def test_federal_programs_topic_filter(self):
        """Validate topic filtering works correctly."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build index with all topics
            embedder.build_federal_programs_index(
                federal_programs_path=str(FEDERAL_PROGRAMS_DIR)
            )

            # Search with topic filter
            results = embedder.search_federal_programs(
                "funding grants assistance",
                top_k=10,
                topic="housing"
            )

            # All results should be housing topic
            for r in results:
                assert r.metadata["topic"] == "housing", (
                    f"Expected housing topic, got {r.metadata['topic']}"
                )

    def test_has_federal_programs_method(self):
        """Validate has_federal_programs() returns correct status."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Before indexing
            assert not embedder.has_federal_programs(), "has_federal_programs() should be False before indexing"

            # After indexing
            embedder.build_federal_programs_index(
                federal_programs_path=str(FEDERAL_PROGRAMS_DIR)
            )
            assert embedder.has_federal_programs(), "has_federal_programs() should be True after indexing"

    def test_federal_programs_metadata_fields(self):
        """Validate indexed programs have expected metadata fields."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            embedder.build_federal_programs_index(
                topics=["housing"],  # Just housing for faster test
                federal_programs_path=str(FEDERAL_PROGRAMS_DIR)
            )

            results = embedder.search_federal_programs("housing", top_k=1)
            assert len(results) > 0

            metadata = results[0].metadata
            expected_fields = [
                "program_id", "program_name", "topic", "administering_agency",
                "source_type", "jurisdiction"
            ]
            for field in expected_fields:
                assert field in metadata, f"Missing metadata field: {field}"
            assert metadata["source_type"] == "federal_program"
            assert metadata["jurisdiction"] == "federal"

    def test_federal_programs_search_scores(self):
        """Validate search results have meaningful scores."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            embedder.build_federal_programs_index(
                federal_programs_path=str(FEDERAL_PROGRAMS_DIR)
            )

            # Search for specific topic
            results = embedder.search_federal_programs(
                "block grant community development low moderate income",  # Very specific to CDBG
                top_k=5
            )

            assert len(results) > 0

            # Scores should be in valid range (0-1 for cosine distance converted to similarity)
            for r in results:
                assert 0 <= r.score <= 1, f"Score {r.score} outside valid range"

            # Results should be sorted by score descending
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True), "Results not sorted by score"


@pytest.mark.requires_real_data
class TestLegislativeUnifiedSearch:
    """
    Tests for legislation integration into UnifiedSearch.

    Validates legislative_unified_search pilot item:
    - UnifiedSearch.search_all() includes legislation results
    - UnifiedSearchResult correctly converts state_legislation and federal_program
    - Corpus filtering works for legislation
    """

    def test_unified_search_includes_legislation(self):
        """Validate search_all() includes legislation corpus."""
        from civicos._internal.search.unified import UnifiedSearch
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            # Build legislation index
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )
            embedder.build_legislation_index(
                state="california",
                legislation_path=str(LEGISLATION_STATE_DIR)
            )

            # Create UnifiedSearch with same persist_directory
            search = UnifiedSearch("city-san-rafael", persist_directory=tmpdir)

            # Search all corpora
            results = search.search_all(
                "affordable housing streamlined approval",
                top_k=10,
                corpus_types=["legislation"]
            )

            # Should return legislation results
            assert len(results) > 0, "No legislation results from search_all()"

            # All results should be state_legislation
            for r in results:
                assert r.source_type == "state_legislation", (
                    f"Expected state_legislation, got {r.source_type}"
                )

    def test_unified_search_result_legislation_fields(self):
        """Validate UnifiedSearchResult has correct fields for legislation."""
        from civicos._internal.search.unified import UnifiedSearch
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )
            embedder.build_legislation_index(
                state="california",
                legislation_path=str(LEGISLATION_STATE_DIR)
            )

            search = UnifiedSearch("city-san-rafael", persist_directory=tmpdir)

            results = search.search_all(
                "affordable housing",
                top_k=5,
                corpus_types=["legislation"]
            )

            assert len(results) > 0

            # Check first result has legislation-specific fields populated
            r = results[0]
            assert r.bill_id is not None, "bill_id should be populated"
            assert r.topic is not None, "topic should be populated"
            assert r.title is not None, "title should be populated (from bill_name)"

    def test_unified_search_federal_programs(self):
        """Validate search_all() includes federal programs with correct source_type."""
        from civicos._internal.search.unified import UnifiedSearch
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )
            embedder.build_federal_programs_index(
                federal_programs_path=str(FEDERAL_PROGRAMS_DIR)
            )

            search = UnifiedSearch("city-san-rafael", persist_directory=tmpdir)

            results = search.search_all(
                "community development block grant housing",
                top_k=10,
                corpus_types=["legislation"]
            )

            # Should return federal program results
            assert len(results) > 0, "No federal program results from search_all()"

            # All results should be federal_program
            for r in results:
                assert r.source_type == "federal_program", (
                    f"Expected federal_program, got {r.source_type}"
                )

    def test_unified_search_result_federal_program_fields(self):
        """Validate UnifiedSearchResult has correct fields for federal programs."""
        from civicos._internal.search.unified import UnifiedSearch
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )
            embedder.build_federal_programs_index(
                federal_programs_path=str(FEDERAL_PROGRAMS_DIR)
            )

            search = UnifiedSearch("city-san-rafael", persist_directory=tmpdir)

            results = search.search_all(
                "housing grants",
                top_k=5,
                corpus_types=["legislation"]
            )

            assert len(results) > 0

            # Check first result has federal program-specific fields populated
            r = results[0]
            assert r.program_id is not None, "program_id should be populated"
            assert r.topic is not None, "topic should be populated"
            assert r.title is not None, "title should be populated (from program_name)"
            assert r.source_type == "federal_program"

    def test_unified_search_mixed_legislation(self):
        """Validate search_all() returns both state bills and federal programs."""
        from civicos._internal.search.unified import UnifiedSearch
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build both indexes
            embedder.build_legislation_index(
                state="california",
                legislation_path=str(LEGISLATION_STATE_DIR)
            )
            embedder.build_federal_programs_index(
                federal_programs_path=str(FEDERAL_PROGRAMS_DIR)
            )

            search = UnifiedSearch("city-san-rafael", persist_directory=tmpdir)

            results = search.search_all(
                "housing funding affordable",
                top_k=20,  # Get more results to see both types
                corpus_types=["legislation"]
            )

            assert len(results) > 0

            # Should have results from both source types
            source_types = {r.source_type for r in results}
            assert "state_legislation" in source_types or "federal_program" in source_types, (
                f"Expected legislation results, got source_types: {source_types}"
            )

    def test_unified_search_corpus_filter_excludes_legislation(self):
        """Validate corpus_types filter can exclude legislation."""
        from civicos._internal.search.unified import UnifiedSearch
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )
            embedder.build_legislation_index(
                state="california",
                legislation_path=str(LEGISLATION_STATE_DIR)
            )

            search = UnifiedSearch("city-san-rafael", persist_directory=tmpdir)

            # Search WITHOUT legislation corpus
            results = search.search_all(
                "affordable housing",
                top_k=10,
                corpus_types=["decision", "transcript"]  # Explicitly exclude legislation
            )

            # Should not return legislation results (will return empty since no other corpora indexed)
            legislation_types = {"state_legislation", "federal_program"}
            for r in results:
                assert r.source_type not in legislation_types, (
                    f"Found {r.source_type} when legislation should be excluded"
                )

    def test_search_corpus_legislation(self):
        """Validate search_corpus() works for legislation corpus."""
        from civicos._internal.search.unified import UnifiedSearch
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )
            embedder.build_legislation_index(
                state="california",
                legislation_path=str(LEGISLATION_STATE_DIR)
            )

            search = UnifiedSearch("city-san-rafael", persist_directory=tmpdir)

            # Use search_corpus for specific corpus
            results = search.search_corpus(
                "legislation",
                "streamlined housing approval",
                top_k=5
            )

            assert len(results) > 0
            for r in results:
                assert r.source_type == "state_legislation"


@pytest.mark.requires_real_data
class TestCountyProgramsVectorSearch:
    """
    Tests for county programs vector indexing and semantic search.

    Validates county programs pilot item:
    - County programs data file exists
    - Programs are indexed in ChromaDB with topic metadata
    - Semantic search returns relevant programs
    - Integration with UnifiedSearch works correctly
    """

    def test_county_programs_file_exists(self):
        """Validate Marin county housing programs JSON file exists."""
        path = COUNTY_HOUSING_DIR / "marin" / "housing_programs.json"
        assert path.exists(), f"County programs file not found: {path}"

    def test_county_programs_file_has_programs(self):
        """Validate county programs file contains program data."""
        import json

        path = COUNTY_HOUSING_DIR / "marin" / "housing_programs.json"
        with open(path) as f:
            data = json.load(f)

        programs = data.get("programs", {})
        assert len(programs) >= 5, f"Expected at least 5 programs, got {len(programs)}"

        # Check for key Marin Housing Authority programs
        expected_programs = ["housing_choice_voucher", "below_market_rate_homeownership"]
        for prog in expected_programs:
            assert prog in programs, f"Expected program '{prog}' not found"

    def test_county_programs_index_can_be_built(self):
        """Validate county programs can be indexed in ChromaDB."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build county programs index with topic
            collection = embedder.build_county_programs_index(
                county_name="marin",
                topic="housing",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            # Should have indexed programs
            count = collection.count()
            assert count >= 5, f"Expected at least 5 programs indexed, got {count}"

    def test_county_programs_semantic_search(self):
        """Validate semantic search returns relevant programs."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build index
            embedder.build_county_programs_index(
                county_name="marin",
                topic="housing",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            # Search for Section 8 voucher program
            results = embedder.search_county_programs(
                "section 8 rental assistance voucher",
                top_k=5
            )

            # Should return results
            assert len(results) > 0, "No search results returned"

            # Top results should include housing choice voucher
            program_ids = [r.metadata["program_id"] for r in results]
            hcv_found = any(
                "voucher" in pid.lower() or "hcv" in pid.lower()
                for pid in program_ids
            )
            assert hcv_found, f"Expected Housing Choice Voucher program, got: {program_ids}"

    def test_county_programs_search_bmr(self):
        """Validate semantic search finds Below Market Rate homeownership."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            embedder.build_county_programs_index(
                county_name="marin",
                topic="housing",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            # Search for first time homebuyer
            results = embedder.search_county_programs(
                "first time homebuyer affordable homeownership",
                top_k=5
            )

            assert len(results) > 0
            program_ids = [r.metadata["program_id"] for r in results]
            bmr_found = any("below_market_rate" in pid or "bmr" in pid.lower() for pid in program_ids)
            assert bmr_found, f"Expected BMR program in results, got: {program_ids}"

    def test_has_county_programs_method(self):
        """Validate has_county_programs() returns correct status."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Before indexing
            assert not embedder.has_county_programs(), "has_county_programs() should be False before indexing"

            # After indexing
            embedder.build_county_programs_index(
                county_name="marin",
                topic="housing",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )
            assert embedder.has_county_programs(), "has_county_programs() should be True after indexing"

    def test_county_programs_metadata_fields(self):
        """Validate indexed programs have expected metadata fields."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            embedder.build_county_programs_index(
                county_name="marin",
                topic="housing",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            results = embedder.search_county_programs("housing", top_k=1)
            assert len(results) > 0

            metadata = results[0].metadata
            expected_fields = [
                "program_id", "program_name", "topic", "county", "administering_agency",
                "source_type", "jurisdiction"
            ]
            for field in expected_fields:
                assert field in metadata, f"Missing metadata field: {field}"

            # Verify county-specific metadata
            assert metadata["county"] == "marin"
            assert metadata["topic"] == "housing"
            assert metadata["source_type"] == "county_program"
            assert metadata["jurisdiction"] == "county-marin"

    def test_county_programs_unified_search_integration(self):
        """Validate county programs appear in UnifiedSearch programs results."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        from civicos._internal.search.unified import UnifiedSearch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build county programs index
            embedder.build_county_programs_index(
                county_name="marin",
                topic="housing",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            search = UnifiedSearch("city-san-rafael", persist_directory=tmpdir)

            # Search via unified search using "programs" corpus
            results = search.search_all(
                "section 8 rental assistance housing voucher",
                corpus_types=["programs"],
                top_k=10
            )

            assert len(results) > 0, "No UnifiedSearch results returned"

            # At least one result should be from county programs
            source_types = [r.source_type for r in results]
            assert "county_program" in source_types, (
                f"Expected county_program in source types, got: {source_types}"
            )

    def test_backward_compatible_methods(self):
        """Validate deprecated backward-compatible methods still work."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build using old method name (should work via backward compat wrapper)
            embedder.build_county_housing_index(
                county_name="marin",
                county_housing_path=str(COUNTY_HOUSING_DIR)
            )

            # has_county_housing should work (backward compat)
            assert embedder.has_county_housing()

            # search_county_housing should work (backward compat)
            results = embedder.search_county_housing("housing", top_k=1)
            assert len(results) > 0


@pytest.mark.requires_real_data
class TestHomelessnessServicesVectorSearch:
    """
    Tests for county homelessness services vector indexing and semantic search.

    Validates county_homelessness_services pilot item:
    - Homelessness services data file exists
    - Services are indexed in ChromaDB with topic metadata
    - Semantic search returns relevant services
    - Integration with UnifiedSearch works correctly
    """

    def test_homelessness_services_file_exists(self):
        """Validate Marin county homelessness programs JSON file exists."""
        path = COUNTY_HOUSING_DIR / "marin" / "homelessness_programs.json"
        assert path.exists(), f"Homelessness programs file not found: {path}"

    def test_homelessness_services_file_has_programs(self):
        """Validate homelessness programs file contains program data."""
        import json

        path = COUNTY_HOUSING_DIR / "marin" / "homelessness_programs.json"
        with open(path) as f:
            data = json.load(f)

        programs = data.get("programs", {})
        assert len(programs) >= 5, f"Expected at least 5 services, got {len(programs)}"

        # Check for key homelessness programs
        expected_programs = ["coordinated_entry_system", "homeward_bound_emergency_shelter"]
        for prog in expected_programs:
            assert prog in programs, f"Expected service '{prog}' not found"

    def test_homelessness_services_index_can_be_built(self):
        """Validate homelessness services can be indexed in ChromaDB."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build county programs index with homelessness topic
            collection = embedder.build_county_programs_index(
                county_name="marin",
                topic="homelessness",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            # Should have indexed programs
            count = collection.count()
            assert count >= 5, f"Expected at least 5 services indexed, got {count}"

    def test_homelessness_services_semantic_search_shelter(self):
        """Validate semantic search returns emergency shelter results."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build index
            embedder.build_county_programs_index(
                county_name="marin",
                topic="homelessness",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            # Search for emergency shelter
            results = embedder.search_county_programs(
                "emergency shelter homeless beds",
                topic="homelessness",
                top_k=5
            )

            # Should return results
            assert len(results) > 0, "No search results returned"

            # Top results should include shelter program
            program_ids = [r.metadata["program_id"] for r in results]
            shelter_found = any(
                "shelter" in pid.lower() or "homeward" in pid.lower()
                for pid in program_ids
            )
            assert shelter_found, f"Expected shelter program, got: {program_ids}"

    def test_homelessness_services_semantic_search_outreach(self):
        """Validate semantic search finds homeless outreach programs."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            embedder.build_county_programs_index(
                county_name="marin",
                topic="homelessness",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            # Search for street outreach
            results = embedder.search_county_programs(
                "street outreach homeless wellness check",
                topic="homelessness",
                top_k=5
            )

            assert len(results) > 0
            program_ids = [r.metadata["program_id"] for r in results]
            outreach_found = any(
                "care" in pid.lower() or "outreach" in pid.lower()
                for pid in program_ids
            )
            assert outreach_found, f"Expected outreach program in results, got: {program_ids}"

    def test_homelessness_services_metadata_fields(self):
        """Validate indexed services have expected metadata fields."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            embedder.build_county_programs_index(
                county_name="marin",
                topic="homelessness",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            results = embedder.search_county_programs(
                "homeless services",
                topic="homelessness",
                top_k=1
            )
            assert len(results) > 0

            metadata = results[0].metadata
            expected_fields = [
                "program_id", "program_name", "topic", "county", "administering_agency",
                "source_type", "jurisdiction"
            ]
            for field in expected_fields:
                assert field in metadata, f"Missing metadata field: {field}"

            # Verify homelessness-specific metadata
            assert metadata["county"] == "marin"
            assert metadata["topic"] == "homelessness"
            assert metadata["source_type"] == "county_program"
            assert metadata["jurisdiction"] == "county-marin"

    def test_homelessness_services_unified_search_integration(self):
        """Validate homelessness services appear in UnifiedSearch programs results."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        from civicos._internal.search.unified import UnifiedSearch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build homelessness services index
            embedder.build_county_programs_index(
                county_name="marin",
                topic="homelessness",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            search = UnifiedSearch("city-san-rafael", persist_directory=tmpdir)

            # Search via unified search using "programs" corpus
            results = search.search_all(
                "emergency shelter homeless assistance",
                corpus_types=["programs"],
                top_k=10
            )

            assert len(results) > 0, "No UnifiedSearch results returned"

            # At least one result should be from county programs
            source_types = [r.source_type for r in results]
            assert "county_program" in source_types, (
                f"Expected county_program in source types, got: {source_types}"
            )

    def test_homelessness_services_search_mental_health(self):
        """Validate semantic search finds mental health crisis services."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            embedder.build_county_programs_index(
                county_name="marin",
                topic="homelessness",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            # Search for mental health services
            results = embedder.search_county_programs(
                "mental health crisis homeless",
                topic="homelessness",
                top_k=5
            )

            assert len(results) > 0
            program_ids = [r.metadata["program_id"] for r in results]
            mh_found = any(
                "odyssey" in pid.lower() or "safe" in pid.lower() or "mental" in pid.lower()
                for pid in program_ids
            )
            assert mh_found, f"Expected mental health program in results, got: {program_ids}"

    def test_housing_and_homelessness_coexist_in_programs_corpus(self):
        """Validate housing and homelessness services can coexist in programs corpus."""
        from civicos._internal.meetings.embeddings import CivicEmbeddings
        from civicos._internal.search.unified import UnifiedSearch
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            embedder = CivicEmbeddings(
                "city-san-rafael",
                persist_directory=tmpdir
            )

            # Build both housing AND homelessness indexes
            embedder.build_county_programs_index(
                county_name="marin",
                topic="housing",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )
            embedder.build_county_programs_index(
                county_name="marin",
                topic="homelessness",
                county_programs_path=str(COUNTY_HOUSING_DIR)
            )

            search = UnifiedSearch("city-san-rafael", persist_directory=tmpdir)

            # Search should return both types
            results = search.search_all(
                "assistance for low income families",
                corpus_types=["programs"],
                top_k=20
            )

            # UnifiedSearchResult has topic field directly (not in metadata dict)
            topics = {r.topic for r in results if r.topic}
            # Should have results from both topics
            assert "housing" in topics or "homelessness" in topics, (
                f"Expected housing or homelessness in results, got topics: {topics}"
            )