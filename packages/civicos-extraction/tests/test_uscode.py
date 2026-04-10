"""Tests for U.S. Code XML parser."""

import pytest
from pathlib import Path

from civicos_extraction.uscode import USCodeSection, USCodeParser, USLM_NS


NS = "http://xml.house.gov/schemas/uslm/1.0"


def _make_xml(
    title_number: int = 42,
    title_name: str = "The Public Health and Welfare",
    sections_xml: str = "",
    include_meta: bool = True,
    include_main: bool = True,
    include_title: bool = True,
) -> str:
    """Build a USLM XML document from parts."""
    meta = ""
    if include_meta:
        meta = f"""<uslm:meta>
            <uslm:docNumber>{title_number}</uslm:docNumber>
        </uslm:meta>"""

    title_heading = f"<uslm:heading>{title_name}</uslm:heading>"
    title_body = f"<uslm:title>{title_heading}\n{sections_xml}</uslm:title>" if include_title else ""
    main = f"<uslm:main>{title_body}</uslm:main>" if include_main else ""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<uslm:usc xmlns:uslm="{NS}">
    {meta}
    {main}
</uslm:usc>"""


ACTIVE_SECTION_XML = """
<uslm:chapter>
    <uslm:heading>Chapter 8—Low-Income Housing</uslm:heading>
    <uslm:subchapter>
        <uslm:heading>Subchapter I—General Program</uslm:heading>
        <uslm:section identifier="/us/usc/t42/s1437">
            <uslm:num value="1437"/>
            <uslm:heading>Declaration of Policy</uslm:heading>
            <uslm:content>It is the policy of the United States to promote the general welfare of the nation.</uslm:content>
            <uslm:subsection>This includes ensuring decent housing for all citizens across the country.</uslm:subsection>
        </uslm:section>
    </uslm:subchapter>
    <uslm:section identifier="/us/usc/t42/s1438">
        <uslm:num value="1438"/>
        <uslm:heading>Definitions</uslm:heading>
        <uslm:content>For purposes of this chapter the following definitions apply to all sections.</uslm:content>
        <uslm:paragraph>The term agency means any federal department.</uslm:paragraph>
    </uslm:section>
</uslm:chapter>
"""

REPEALED_SECTION_XML = """
<uslm:section identifier="/us/usc/t42/s1439" status="repealed">
    <uslm:num value="1439"/>
    <uslm:heading>Repealed Provision</uslm:heading>
    <uslm:content>This section was repealed by Pub. L. 110-234.</uslm:content>
</uslm:section>
"""

OMITTED_SECTION_XML = """
<uslm:section identifier="/us/usc/t42/s1440" status="omitted">
    <uslm:num value="1440"/>
    <uslm:heading>Omitted Provision</uslm:heading>
    <uslm:content>This section was omitted from the code as obsolete.</uslm:content>
</uslm:section>
"""

SHORT_TEXT_SECTION_XML = """
<uslm:section identifier="/us/usc/t42/s1441">
    <uslm:num value="1441"/>
    <uslm:heading>Stub</uslm:heading>
    <uslm:content>Short.</uslm:content>
</uslm:section>
"""

TWO_CHAPTERS_XML = """
<uslm:chapter>
    <uslm:heading>Chapter 8—Low-Income Housing</uslm:heading>
    <uslm:section identifier="/us/usc/t42/s1437">
        <uslm:num value="1437"/>
        <uslm:heading>Declaration of Policy</uslm:heading>
        <uslm:content>It is the policy of the United States to promote the general welfare of the nation.</uslm:content>
    </uslm:section>
</uslm:chapter>
<uslm:chapter>
    <uslm:heading>Chapter 9—Housing Authorities</uslm:heading>
    <uslm:section identifier="/us/usc/t42/s1450">
        <uslm:num value="1450"/>
        <uslm:heading>Authority Establishment</uslm:heading>
        <uslm:content>Each state may establish housing authorities for the purpose of providing affordable housing.</uslm:content>
    </uslm:section>
</uslm:chapter>
"""

NOTES_AND_SOURCE_CREDIT_XML = """
<uslm:section identifier="/us/usc/t42/s1442">
    <uslm:num value="1442"/>
    <uslm:heading>Section with Notes</uslm:heading>
    <uslm:content>Main content of the section describing federal housing standards and regulations.</uslm:content>
    <uslm:notes>These are editorial notes that should be excluded from the text.</uslm:notes>
    <uslm:sourceCredit>Pub. L. 99-100, 1999</uslm:sourceCredit>
    <uslm:statutoryNote>Statutory note that should be excluded from text content.</uslm:statutoryNote>
</uslm:section>
"""


@pytest.fixture
def xml_file(tmp_path):
    """Create a USLM XML file with active sections."""
    content = _make_xml(sections_xml=ACTIVE_SECTION_XML)
    path = tmp_path / "usc42.xml"
    path.write_text(content)
    return path


@pytest.fixture
def full_xml_file(tmp_path):
    """Create a USLM XML with active, repealed, omitted, and short sections."""
    sections = ACTIVE_SECTION_XML + REPEALED_SECTION_XML + OMITTED_SECTION_XML + SHORT_TEXT_SECTION_XML
    content = _make_xml(sections_xml=sections)
    path = tmp_path / "usc42_full.xml"
    path.write_text(content)
    return path


@pytest.fixture
def two_chapter_xml(tmp_path):
    """Create a USLM XML with two chapters."""
    content = _make_xml(sections_xml=TWO_CHAPTERS_XML)
    path = tmp_path / "usc42_chapters.xml"
    path.write_text(content)
    return path


# ──────────────────────────────────────────────
# USCodeSection dataclass
# ──────────────────────────────────────────────

class TestUSCodeSection:
    def _make_section(self, **overrides) -> USCodeSection:
        defaults = dict(
            title_number=42,
            title_name="The Public Health and Welfare",
            section_number="1437",
            heading="Declaration of Policy",
            text="It is the policy of the United States.",
            citation="42 U.S.C. § 1437",
            identifier="/us/usc/t42/s1437",
        )
        defaults.update(overrides)
        return USCodeSection(**defaults)

    def test_to_dict_returns_all_fields(self):
        section = self._make_section(chapter="Chapter 8", subchapter="Subchapter I")
        d = section.to_dict()

        assert d["title_number"] == 42
        assert d["title_name"] == "The Public Health and Welfare"
        assert d["section_number"] == "1437"
        assert d["heading"] == "Declaration of Policy"
        assert d["text"] == "It is the policy of the United States."
        assert d["citation"] == "42 U.S.C. § 1437"
        assert d["identifier"] == "/us/usc/t42/s1437"
        assert d["status"] is None
        assert d["chapter"] == "Chapter 8"
        assert d["subchapter"] == "Subchapter I"

    def test_is_active_when_status_is_none(self):
        section = self._make_section(status=None)
        assert section.is_active() is True

    def test_is_not_active_when_repealed(self):
        section = self._make_section(status="repealed")
        assert section.is_active() is False

    def test_is_not_active_when_omitted(self):
        section = self._make_section(status="omitted")
        assert section.is_active() is False

    def test_to_dict_round_trips_all_keys(self):
        section = self._make_section(status="repealed", chapter="Ch1", subchapter="Sub1")
        d = section.to_dict()
        expected_keys = {
            "title_number", "title_name", "section_number", "heading",
            "text", "citation", "identifier", "status", "chapter", "subchapter",
        }
        assert set(d.keys()) == expected_keys


# ──────────────────────────────────────────────
# USCodeParser initialization
# ──────────────────────────────────────────────

class TestParserInit:
    def test_raises_file_not_found_for_missing_path(self):
        with pytest.raises(FileNotFoundError, match="U.S. Code XML not found"):
            USCodeParser("/nonexistent/path/usc99.xml")

    def test_accepts_path_as_string(self, xml_file):
        parser = USCodeParser(str(xml_file))
        assert parser.xml_path == xml_file

    def test_accepts_path_object(self, xml_file):
        parser = USCodeParser(xml_file)
        assert parser.xml_path == xml_file

    def test_tree_not_loaded_until_needed(self, xml_file):
        parser = USCodeParser(xml_file)
        assert parser.tree is None
        assert parser.root is None
        assert parser.title_number is None
        assert parser.title_name is None


# ──────────────────────────────────────────────
# USCodeParser._load
# ──────────────────────────────────────────────

class TestParserLoad:
    def test_extracts_title_number(self, xml_file):
        parser = USCodeParser(xml_file)
        parser._load()
        assert parser.title_number == 42

    def test_extracts_title_name(self, xml_file):
        parser = USCodeParser(xml_file)
        parser._load()
        assert parser.title_name == "The Public Health and Welfare"

    def test_idempotent_double_load(self, xml_file):
        parser = USCodeParser(xml_file)
        parser._load()
        first_tree = parser.tree
        parser._load()
        assert parser.tree is first_tree  # Same object, not re-parsed

    def test_no_meta_element_leaves_title_number_none(self, tmp_path):
        content = _make_xml(include_meta=False)
        path = tmp_path / "no_meta.xml"
        path.write_text(content)
        parser = USCodeParser(path)
        parser._load()
        assert parser.title_number is None

    def test_no_main_element_leaves_title_name_none(self, tmp_path):
        content = _make_xml(include_main=False)
        path = tmp_path / "no_main.xml"
        path.write_text(content)
        parser = USCodeParser(path)
        parser._load()
        assert parser.title_name is None


# ──────────────────────────────────────────────
# USCodeParser._get_text
# ──────────────────────────────────────────────

class TestGetText:
    def test_returns_empty_for_none(self, xml_file):
        parser = USCodeParser(xml_file)
        assert parser._get_text(None) == ""

    def test_extracts_plain_text(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        elem = ET.fromstring(f'<p xmlns="{NS}">Hello world</p>')
        assert parser._get_text(elem) == "Hello world"

    def test_extracts_nested_text(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        xml_str = f'<p xmlns="{NS}">Before <b>bold</b> after</p>'
        elem = ET.fromstring(xml_str)
        result = parser._get_text(elem)
        assert "Before" in result
        assert "bold" in result
        assert "after" in result

    def test_skips_notes_element(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        xml_str = f'<p xmlns="{NS}">Main text <notes>should be skipped</notes></p>'
        elem = ET.fromstring(xml_str)
        result = parser._get_text(elem)
        assert "Main text" in result
        assert "should be skipped" not in result

    def test_skips_toc_element(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        xml_str = f'<p xmlns="{NS}">Content <toc>table of contents</toc></p>'
        elem = ET.fromstring(xml_str)
        result = parser._get_text(elem)
        assert "Content" in result
        assert "table of contents" not in result

    def test_skips_source_credit_element(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        xml_str = f'<p xmlns="{NS}">Content <sourceCredit>Pub. L. 99-100</sourceCredit></p>'
        elem = ET.fromstring(xml_str)
        result = parser._get_text(elem)
        assert "Content" in result
        assert "Pub. L. 99-100" not in result

    def test_skips_statutory_note_element(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        xml_str = f'<p xmlns="{NS}">Content <statutoryNote>A note</statutoryNote></p>'
        elem = ET.fromstring(xml_str)
        result = parser._get_text(elem)
        assert "Content" in result
        assert "A note" not in result

    def test_collapses_whitespace(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        xml_str = f'<p xmlns="{NS}">  lots   of   spaces  </p>'
        elem = ET.fromstring(xml_str)
        result = parser._get_text(elem)
        assert result == "lots of spaces"

    def test_handles_tail_text(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        xml_str = f'<p xmlns="{NS}">Before <b>inner</b> tail text</p>'
        elem = ET.fromstring(xml_str)
        result = parser._get_text(elem)
        assert "tail text" in result


# ──────────────────────────────────────────────
# USCodeParser._extract_section_text
# ──────────────────────────────────────────────

class TestExtractSectionText:
    def test_returns_empty_for_repealed(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        section = ET.fromstring(
            f'<section xmlns="{NS}" status="repealed">'
            f'<content>Some content here that is long enough to pass.</content>'
            f'</section>'
        )
        assert parser._extract_section_text(section) == ""

    def test_returns_empty_for_omitted(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        section = ET.fromstring(
            f'<section xmlns="{NS}" status="omitted">'
            f'<content>Some content here that is long enough to pass.</content>'
            f'</section>'
        )
        assert parser._extract_section_text(section) == ""

    def test_extracts_content_elements(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        section = ET.fromstring(
            f'<section xmlns="{NS}">'
            f'<num value="100"/>'
            f'<heading>Test Heading</heading>'
            f'<content>Main content of this section.</content>'
            f'<subsection>Additional subsection text here.</subsection>'
            f'</section>'
        )
        text = parser._extract_section_text(section)
        assert "Main content of this section" in text
        assert "Additional subsection text" in text

    def test_skips_num_and_heading(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        section = ET.fromstring(
            f'<section xmlns="{NS}">'
            f'<num value="999"/>'
            f'<heading>Should Not Appear</heading>'
            f'<content>Actual section content text here.</content>'
            f'</section>'
        )
        text = parser._extract_section_text(section)
        assert "Should Not Appear" not in text
        assert "999" not in text
        assert "Actual section content" in text

    def test_skips_notes_within_section(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        section = ET.fromstring(
            f'<section xmlns="{NS}">'
            f'<content>Main text of this particular section here.</content>'
            f'<notes>Editorial note to exclude.</notes>'
            f'</section>'
        )
        text = parser._extract_section_text(section)
        assert "Main text" in text
        assert "Editorial note" not in text

    def test_extracts_unknown_elements_text(self, xml_file):
        import xml.etree.ElementTree as ET
        parser = USCodeParser(xml_file)
        section = ET.fromstring(
            f'<section xmlns="{NS}">'
            f'<unknowntag>Text from an unrecognized element type here.</unknowntag>'
            f'</section>'
        )
        text = parser._extract_section_text(section)
        assert "Text from an unrecognized element" in text


# ──────────────────────────────────────────────
# USCodeParser.parse_sections
# ──────────────────────────────────────────────

class TestParseSections:
    def test_yields_sections_with_correct_fields(self, xml_file):
        parser = USCodeParser(xml_file)
        sections = list(parser.parse_sections())

        assert len(sections) == 2

        s = sections[0]
        assert s.title_number == 42
        assert s.title_name == "The Public Health and Welfare"
        assert s.section_number == "1437"
        assert s.heading == "Declaration of Policy"
        assert s.citation == "42 U.S.C. § 1437"
        assert s.identifier == "/us/usc/t42/s1437"
        assert s.status is None
        assert s.chapter == "Chapter 8—Low-Income Housing"
        assert s.subchapter == "Subchapter I—General Program"

    def test_second_section_outside_subchapter(self, xml_file):
        parser = USCodeParser(xml_file)
        sections = list(parser.parse_sections())

        s2 = sections[1]
        assert s2.section_number == "1438"
        assert s2.heading == "Definitions"
        assert s2.chapter == "Chapter 8—Low-Income Housing"
        # subchapter resets when a new chapter-level section appears
        # But since it's still under the same chapter element, subchapter
        # stays as the last seen. Let's check the actual text
        assert "definitions apply" in s2.text

    def test_skips_inactive_by_default(self, full_xml_file):
        parser = USCodeParser(full_xml_file)
        sections = list(parser.parse_sections())
        statuses = [s.status for s in sections]
        assert "repealed" not in statuses
        assert "omitted" not in statuses

    def test_include_inactive_bypasses_status_filter(self, full_xml_file):
        """include_inactive=True bypasses the status check, but repealed/omitted
        sections still get skipped because _extract_section_text returns empty text
        for them, and the len(text) < 20 guard filters them out."""
        parser = USCodeParser(full_xml_file)
        sections_default = list(parser.parse_sections(include_inactive=False))
        sections_all = list(parser.parse_sections(include_inactive=True))
        # Both return the same set because repealed/omitted produce empty text
        default_numbers = {s.section_number for s in sections_default}
        all_numbers = {s.section_number for s in sections_all}
        assert default_numbers == all_numbers
        assert "1439" not in all_numbers  # repealed - empty text
        assert "1440" not in all_numbers  # omitted - empty text

    def test_skips_sections_with_short_text(self, full_xml_file):
        parser = USCodeParser(full_xml_file)
        sections = list(parser.parse_sections())
        section_numbers = [s.section_number for s in sections]
        # Section 1441 has text "Short." which is < 20 chars
        assert "1441" not in section_numbers

    def test_chapter_filter_includes_matching(self, two_chapter_xml):
        parser = USCodeParser(two_chapter_xml)
        sections = list(parser.parse_sections(chapter_filter="Low-Income"))
        assert len(sections) == 1
        assert sections[0].section_number == "1437"

    def test_chapter_filter_excludes_non_matching(self, two_chapter_xml):
        parser = USCodeParser(two_chapter_xml)
        sections = list(parser.parse_sections(chapter_filter="Authorities"))
        assert len(sections) == 1
        assert sections[0].section_number == "1450"

    def test_chapter_filter_case_insensitive(self, two_chapter_xml):
        parser = USCodeParser(two_chapter_xml)
        sections = list(parser.parse_sections(chapter_filter="low-income"))
        assert len(sections) == 1
        assert sections[0].section_number == "1437"

    def test_chapter_filter_no_match_returns_empty(self, two_chapter_xml):
        parser = USCodeParser(two_chapter_xml)
        sections = list(parser.parse_sections(chapter_filter="Nonexistent"))
        assert sections == []

    def test_no_main_element_returns_empty(self, tmp_path):
        content = _make_xml(include_main=False)
        path = tmp_path / "no_main.xml"
        path.write_text(content)
        parser = USCodeParser(path)
        sections = list(parser.parse_sections())
        assert sections == []

    def test_no_title_element_returns_empty(self, tmp_path):
        content = _make_xml(include_title=False)
        path = tmp_path / "no_title.xml"
        path.write_text(content)
        parser = USCodeParser(path)
        sections = list(parser.parse_sections())
        assert sections == []

    def test_section_text_content_includes_subsections(self, xml_file):
        parser = USCodeParser(xml_file)
        sections = list(parser.parse_sections())
        s = sections[0]
        assert "general welfare" in s.text
        assert "decent housing" in s.text

    def test_notes_excluded_but_source_credit_included(self, tmp_path):
        """notes elements are skipped at section level, but sourceCredit and
        statutoryNote fall to the else branch in _extract_section_text and
        get included (they're only skipped as children inside _get_text)."""
        content = _make_xml(sections_xml=NOTES_AND_SOURCE_CREDIT_XML)
        path = tmp_path / "notes.xml"
        path.write_text(content)
        parser = USCodeParser(path)
        sections = list(parser.parse_sections())
        assert len(sections) == 1
        assert "federal housing standards" in sections[0].text
        # notes are skipped at section level
        assert "editorial notes" not in sections[0].text.lower()
        # sourceCredit and statutoryNote fall to else branch — they ARE included
        assert "Pub. L." in sections[0].text
        assert "excluded from text content" in sections[0].text

    def test_chapter_context_resets_subchapter(self, two_chapter_xml):
        parser = USCodeParser(two_chapter_xml)
        sections = list(parser.parse_sections())
        # Chapter 9 section should not inherit subchapter from Chapter 8
        ch9_section = [s for s in sections if s.section_number == "1450"][0]
        assert ch9_section.chapter == "Chapter 9—Housing Authorities"
        assert ch9_section.subchapter is None


# ──────────────────────────────────────────────
# USCodeParser.get_stats
# ──────────────────────────────────────────────

class TestGetStats:
    def test_returns_correct_counts(self, full_xml_file):
        parser = USCodeParser(full_xml_file)
        stats = parser.get_stats()

        assert stats["title_number"] == 42
        assert stats["title_name"] == "The Public Health and Welfare"
        # Only 1437 and 1438 are yielded: 1439 (repealed) and 1440 (omitted)
        # produce empty text from _extract_section_text, 1441 has text < 20 chars.
        assert stats["total_sections"] == 2
        assert stats["active_sections"] == 2
        assert stats["repealed_sections"] == 0
        assert stats["omitted_sections"] == 0

    def test_sections_grouped_by_chapter(self, two_chapter_xml):
        parser = USCodeParser(two_chapter_xml)
        stats = parser.get_stats()

        assert stats["chapters"] == 2
        assert stats["sections_by_chapter"]["Chapter 8—Low-Income Housing"] == 1
        assert stats["sections_by_chapter"]["Chapter 9—Housing Authorities"] == 1

    def test_stats_title_info(self, xml_file):
        parser = USCodeParser(xml_file)
        stats = parser.get_stats()
        assert stats["title_number"] == 42
        assert stats["title_name"] == "The Public Health and Welfare"


# ──────────────────────────────────────────────
# Integration: different title numbers
# ──────────────────────────────────────────────

class TestDifferentTitles:
    def test_title_26_citation_format(self, tmp_path):
        section_xml = """
        <uslm:section identifier="/us/usc/t26/s501">
            <uslm:num value="501"/>
            <uslm:heading>Exemption from tax on corporations</uslm:heading>
            <uslm:content>Organizations described in subsection c are exempt from taxation under this subtitle.</uslm:content>
        </uslm:section>
        """
        content = _make_xml(title_number=26, title_name="Internal Revenue Code", sections_xml=section_xml)
        path = tmp_path / "usc26.xml"
        path.write_text(content)
        parser = USCodeParser(path)
        sections = list(parser.parse_sections())
        assert len(sections) == 1
        assert sections[0].citation == "26 U.S.C. § 501"
        assert sections[0].title_number == 26
        assert sections[0].title_name == "Internal Revenue Code"
