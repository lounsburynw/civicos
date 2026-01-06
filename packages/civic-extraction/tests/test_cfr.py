"""Tests for CFR parser."""

import pytest
from pathlib import Path


@pytest.fixture
def sample_cfr_xml(tmp_path):
    """Create a minimal CFR XML file for testing."""
    xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<CFRDOC>
    <FMTR>
        <TITLEPG>
            <TITLENUM>Title 99</TITLENUM>
            <SUBJECT>Test Regulations</SUBJECT>
            <PARTS>Parts 1 to 99</PARTS>
        </TITLEPG>
    </FMTR>
    <TITLE>
        <PART>
            <HD SOURCE="HED">PART 1—TEST REQUIREMENTS</HD>
            <AUTH>
                <HD SOURCE="HED">Authority:</HD>
                <P>42 U.S.C. 123.</P>
            </AUTH>
            <SOURCE>
                <HD SOURCE="HED">Source:</HD>
                <P>88 FR 12345, Jan. 1, 2024.</P>
            </SOURCE>
            <SECTION>
                <SECTNO>§ 1.1</SECTNO>
                <SUBJECT>Purpose.</SUBJECT>
                <P>This part establishes requirements for testing.</P>
                <P>Additional paragraph with more details about testing requirements.</P>
            </SECTION>
            <SECTION>
                <SECTNO>§ 1.2</SECTNO>
                <SUBJECT>Definitions.</SUBJECT>
                <P>For purposes of this part:</P>
                <P>(a) Test means a verification procedure.</P>
                <P>(b) Requirement means a mandatory condition.</P>
            </SECTION>
        </PART>
        <PART>
            <HD SOURCE="HED">PART 2—ADVANCED TESTING</HD>
            <SECTION>
                <SECTNO>§ 2.1</SECTNO>
                <SUBJECT>Scope.</SUBJECT>
                <P>This part applies to advanced testing scenarios.</P>
            </SECTION>
        </PART>
    </TITLE>
</CFRDOC>'''

    xml_file = tmp_path / "test-cfr.xml"
    xml_file.write_text(xml_content)
    return xml_file


def test_cfr_parser_loads_title_info(sample_cfr_xml):
    """Test that parser correctly extracts title information."""
    from civic_extraction.cfr import CFRParser

    parser = CFRParser(sample_cfr_xml)
    parser._load()

    assert parser.title_number == 99
    assert parser.title_name == "Test Regulations"


def test_cfr_parser_parses_sections(sample_cfr_xml):
    """Test that parser correctly parses sections."""
    from civic_extraction.cfr import CFRParser

    parser = CFRParser(sample_cfr_xml)
    sections = list(parser.parse_sections())

    assert len(sections) == 3

    # Check first section
    s1 = sections[0]
    assert s1.citation == "99 CFR 1.1"
    assert s1.section_number == "1.1"
    assert s1.heading == "Purpose."
    assert "establishes requirements" in s1.text
    assert s1.part_number == "1"


def test_cfr_parser_section_to_dict(sample_cfr_xml):
    """Test that section to_dict works correctly."""
    from civic_extraction.cfr import CFRParser

    parser = CFRParser(sample_cfr_xml)
    sections = list(parser.parse_sections())

    d = sections[0].to_dict()

    assert d["citation"] == "99 CFR 1.1"
    assert d["title_number"] == 99
    assert d["title_name"] == "Test Regulations"
    assert d["section_number"] == "1.1"
    assert d["identifier"] == "cfr/t99/s1.1"


def test_cfr_parser_part_filter(sample_cfr_xml):
    """Test that part filter works."""
    from civic_extraction.cfr import CFRParser

    parser = CFRParser(sample_cfr_xml)

    # Filter to Part 1 only
    part1_sections = list(parser.parse_sections(part_filter="1"))
    assert len(part1_sections) == 2
    assert all(s.part_number == "1" for s in part1_sections)

    # Filter to Part 2
    part2_sections = list(parser.parse_sections(part_filter="2"))
    assert len(part2_sections) == 1
    assert part2_sections[0].section_number == "2.1"


def test_cfr_parser_stats(sample_cfr_xml):
    """Test that get_stats returns correct statistics."""
    from civic_extraction.cfr import CFRParser

    parser = CFRParser(sample_cfr_xml)
    stats = parser.get_stats()

    assert stats["title_number"] == 99
    assert stats["total_sections"] == 3
    assert stats["parts"] == 2
    assert stats["sections_by_part"]["1"] == 2
    assert stats["sections_by_part"]["2"] == 1


def test_cfr_parser_file_not_found():
    """Test that parser raises error for missing file."""
    from civic_extraction.cfr import CFRParser

    with pytest.raises(FileNotFoundError):
        CFRParser("/nonexistent/path/to/cfr.xml")


@pytest.mark.skipif(
    not Path("data/cfr/CFR-2024-title24-vol1.xml").exists(),
    reason="Real CFR data not available"
)
def test_cfr_parser_real_data():
    """Test with real CFR data if available (skipped in CI)."""
    from civic_extraction.cfr import CFRParser

    parser = CFRParser("data/cfr/CFR-2024-title24-vol1.xml")
    stats = parser.get_stats()

    assert stats["title_number"] == 24
    assert stats["title_name"] == "Housing and Urban Development"
    assert stats["total_sections"] > 1000  # Title 24 has ~1200 sections
