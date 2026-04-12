"""Tests for municipal code pattern inference (title, section, chapter fallback).

Validates that _infer_title_pattern, _infer_section_pattern, and the chapter
fallback correctly handle non-standard municipal code structures.
"""

import re
import pytest
from civicos._internal.legal.corpus.municipal import MunicipalCodeCorpus


class TestTitlePatternInference:
    """Test the _infer_title_pattern method with various TOC structures."""

    def _make_corpus(self):
        """Create a MunicipalCodeCorpus without connecting to Municode API."""
        corpus = MunicipalCodeCorpus.__new__(MunicipalCodeCorpus)
        corpus.jurisdiction_id = "test-city"
        corpus._title_pattern = re.compile(MunicipalCodeCorpus.DEFAULT_TITLE_PATTERN)
        return corpus

    def test_standard_title_pattern_still_inferred(self):
        """Standard 'Title N - NAME' headings still match an alternative pattern."""
        corpus = self._make_corpus()
        headings = [
            "Title 1 - GENERAL PROVISIONS",
            "Title 2 - ADMINISTRATION",
            "Title 3 - FINANCE AND TAXATION",
        ]
        result = corpus._infer_title_pattern(headings)
        # All 3 headings match the case-insensitive TITLE pattern
        assert result is not None
        m = result.match("Title 1 - GENERAL PROVISIONS")
        assert m is not None
        assert m.group(1) == "1"
        assert m.group(2) == "GENERAL PROVISIONS"

    def test_roman_numeral_chapters(self):
        """Alameda-style 'CHAPTER I - NAME' should match."""
        corpus = self._make_corpus()
        headings = [
            "CHAPTER I - GENERAL",
            "CHAPTER II - ADMINISTRATION",
            "CHAPTER III - FINANCE AND TAXATION",
            "CHAPTER IV - OFFENSES AND PUBLIC SAFETY",
            "CHAPTER V - LICENSES AND PERMITS",
        ]
        result = corpus._infer_title_pattern(headings)
        assert result is not None
        m = result.match("CHAPTER I - GENERAL")
        assert m is not None
        assert m.group(1) == "I"
        assert m.group(2) == "GENERAL"

    def test_article_pattern(self):
        """'ARTICLE I - NAME' pattern should match."""
        corpus = self._make_corpus()
        headings = [
            "ARTICLE I - GENERAL PROVISIONS",
            "ARTICLE II - DEFINITIONS",
            "ARTICLE III - ADMINISTRATION",
            "ARTICLE IV - ENFORCEMENT",
        ]
        result = corpus._infer_title_pattern(headings)
        assert result is not None
        m = result.match("ARTICLE II - DEFINITIONS")
        assert m is not None
        assert m.group(1) == "II"

    def test_arabic_chapter_pattern(self):
        """'Chapter 1 - NAME' with arabic numerals should match."""
        corpus = self._make_corpus()
        headings = [
            "Chapter 1 - General Provisions",
            "Chapter 2 - Administration",
            "Chapter 3 - Revenue and Finance",
            "Chapter 4 - Public Safety",
        ]
        result = corpus._infer_title_pattern(headings)
        assert result is not None
        m = result.match("Chapter 2 - Administration")
        assert m is not None
        assert m.group(1) == "2"

    def test_em_dash_separator(self):
        """Patterns should work with em-dash (—) separators."""
        corpus = self._make_corpus()
        headings = [
            "CHAPTER I — GENERAL",
            "CHAPTER II — ADMINISTRATION",
            "CHAPTER III — FINANCE",
            "CHAPTER IV — PUBLIC SAFETY",
        ]
        result = corpus._infer_title_pattern(headings)
        assert result is not None
        m = result.match("CHAPTER I — GENERAL")
        assert m is not None
        assert m.group(1) == "I"
        assert m.group(2) == "GENERAL"

    def test_en_dash_separator(self):
        """Patterns should work with en-dash (–) separators."""
        corpus = self._make_corpus()
        headings = [
            "CHAPTER I – GENERAL",
            "CHAPTER II – ADMINISTRATION",
            "CHAPTER III – FINANCE",
            "CHAPTER IV – PUBLIC SAFETY",
        ]
        result = corpus._infer_title_pattern(headings)
        assert result is not None
        m = result.match("CHAPTER III – FINANCE")
        assert m is not None
        assert m.group(1) == "III"
        assert m.group(2) == "FINANCE"

    def test_empty_headings(self):
        """Empty headings list should return None."""
        corpus = self._make_corpus()
        result = corpus._infer_title_pattern([])
        assert result is None

    def test_unrecognized_pattern_returns_none(self):
        """Headings that don't match any known pattern return None."""
        corpus = self._make_corpus()
        headings = [
            "Some Random Heading",
            "Another Heading",
            "Yet Another",
        ]
        result = corpus._infer_title_pattern(headings)
        assert result is None

    def test_minimum_match_threshold(self):
        """Pattern must match at least 3 headings to be accepted."""
        corpus = self._make_corpus()
        # Only 2 matching headings - below threshold
        headings = [
            "CHAPTER I - GENERAL",
            "CHAPTER II - ADMIN",
            "Random non-matching",
            "Another non-matching",
            "More non-matching",
        ]
        result = corpus._infer_title_pattern(headings)
        # Should still return None since only 2 match CHAPTER pattern
        # but 3 is the threshold and we have 2 CHAPTER matches
        # Actually 2 < 3 so it should return None
        # Wait, need to check - the threshold is >= 3
        assert result is None

    def test_three_matches_sufficient(self):
        """Exactly 3 matching headings should be accepted."""
        corpus = self._make_corpus()
        headings = [
            "CHAPTER I - GENERAL",
            "CHAPTER II - ADMIN",
            "CHAPTER III - FINANCE",
            "Random non-matching",
        ]
        result = corpus._infer_title_pattern(headings)
        assert result is not None
        m = result.match("CHAPTER II - ADMIN")
        assert m is not None
        assert m.group(1) == "II"
        assert m.group(2) == "ADMIN"

    def test_division_pattern(self):
        """'Division N - NAME' pattern should match."""
        corpus = self._make_corpus()
        headings = [
            "Division 1 - General Provisions",
            "Division 2 - Administration",
            "Division 3 - Public Works",
            "Division 4 - Planning",
        ]
        result = corpus._infer_title_pattern(headings)
        assert result is not None
        m = result.match("Division 1 - General Provisions")
        assert m is not None
        assert m.group(1) == "1"

    def test_austin_style_title_with_period(self):
        """Austin-style 'TITLE 1. - NAME' (period after number) should match."""
        corpus = self._make_corpus()
        headings = [
            "TITLE 1. - GENERAL PROVISIONS.",
            "TITLE 2. - ADMINISTRATION.",
            "TITLE 3. - ANIMAL REGULATION.",
            "TITLE 4. - BUSINESS REGULATION AND PERMIT REQUIREMENTS.",
        ]
        result = corpus._infer_title_pattern(headings)
        assert result is not None
        m = result.match("TITLE 1. - GENERAL PROVISIONS.")
        assert m is not None
        assert m.group(2).startswith("GENERAL")

    def test_salem_style_mixed_case_roman(self):
        """Salem-style mixed 'Title I' / 'TITLE II' with roman numerals."""
        corpus = self._make_corpus()
        headings = [
            "Title I - GOVERNMENT",
            "TITLE II - ASSESSMENT, LIENS AND CONNECTION FEES",
            "TITLE III - BUSINESSES AND VOCATIONS",
            "TITLE IV - HEALTH AND SANITATION",
        ]
        result = corpus._infer_title_pattern(headings)
        assert result is not None
        m = result.match("TITLE II - ASSESSMENT, LIENS AND CONNECTION FEES")
        assert m is not None
        # Should capture roman numeral
        assert m.group(1) == "II"

    def test_title_without_period(self):
        """'TITLE 1 - NAME' without period should also match flexible pattern."""
        corpus = self._make_corpus()
        headings = [
            "TITLE 1 - GENERAL PROVISIONS",
            "TITLE 2 - ADMINISTRATION",
            "TITLE 3 - ANIMAL REGULATION",
            "TITLE 4 - BUSINESS REGULATION",
        ]
        result = corpus._infer_title_pattern(headings)
        assert result is not None
        m = result.match("TITLE 3 - ANIMAL REGULATION")
        assert m is not None
        assert m.group(1) == "3"
        assert m.group(2) == "ANIMAL REGULATION"


class TestSectionPatternInference:
    """Test _infer_section_pattern for non-standard section numbering."""

    def _make_corpus(self):
        corpus = MunicipalCodeCorpus.__new__(MunicipalCodeCorpus)
        corpus.jurisdiction_id = "test-city"
        corpus._section_pattern = re.compile(MunicipalCodeCorpus.DEFAULT_SECTION_PATTERN)
        return corpus

    def test_alameda_style_dash_sections(self):
        """Alameda-style '1-3.1 - Name' sections should match."""
        corpus = self._make_corpus()
        headings = [
            "1-1 - SHORT TITLE, REFERENCE TO CODE.",
            "1-2 - DEFINITIONS.",
            "1-3 - RULES OF CONSTRUCTION.",
            "1-3.1 - Applicability to Code and Ordinances.",
            "1-3.2 - Rules To Be Observed.",
        ]
        result = corpus._infer_section_pattern(headings)
        assert result is not None
        m = result.match("1-3.1 - Applicability to Code and Ordinances.")
        assert m is not None
        assert m.group(1) == "1-3.1"
        assert "Applicability" in m.group(2)

    def test_dash_sections_without_subsection(self):
        """'2-6 - Name' without decimal subsection should match."""
        corpus = self._make_corpus()
        headings = [
            "2-1 - THE CITY COUNCIL.",
            "2-5 - APPLICABILITY OF SUNSHINE ORDINANCE",
            "2-6 - PUBLIC UTILITIES BOARD.",
            "2-7 - CIVIL SERVICE BOARD.",
        ]
        result = corpus._infer_section_pattern(headings)
        assert result is not None
        m = result.match("2-6 - PUBLIC UTILITIES BOARD.")
        assert m is not None
        assert m.group(1) == "2-6"

    def test_standard_pattern_not_inferred(self):
        """Standard '1.04.010 - Name' doesn't need inference."""
        corpus = self._make_corpus()
        headings = [
            "1.04.010 - Title.",
            "1.04.015 - Fees.",
            "1.04.020 - Authority.",
        ]
        # These already match DEFAULT_SECTION_PATTERN
        for h in headings:
            assert corpus._section_pattern.match(h) is not None

    def test_empty_headings(self):
        corpus = self._make_corpus()
        assert corpus._infer_section_pattern([]) is None

    def test_unrecognized_headings(self):
        corpus = self._make_corpus()
        headings = ["Foo", "Bar", "Baz"]
        assert corpus._infer_section_pattern(headings) is None

    def test_em_dash_separators(self):
        """Section patterns with em-dash should match."""
        corpus = self._make_corpus()
        headings = [
            "1-1 — SHORT TITLE",
            "1-2 — DEFINITIONS",
            "1-3 — RULES OF CONSTRUCTION",
            "1-4 — GENERAL PROVISIONS",
        ]
        result = corpus._infer_section_pattern(headings)
        assert result is not None
        m = result.match("1-2 — DEFINITIONS")
        assert m is not None
        assert m.group(1) == "1-2"
        assert m.group(2) == "DEFINITIONS"


class TestYieldSectionsFromDocs:
    """Test _yield_sections_from_docs with section pattern inference."""

    def _make_corpus(self):
        corpus = MunicipalCodeCorpus.__new__(MunicipalCodeCorpus)
        corpus.jurisdiction_id = "test-city"
        corpus._section_pattern = re.compile(MunicipalCodeCorpus.DEFAULT_SECTION_PATTERN)
        return corpus

    def test_standard_sections(self):
        """Standard section numbers yield correctly."""
        corpus = self._make_corpus()
        docs = [
            {"Id": "1", "Title": "1.04.010 - Title.", "Content": "<p>text</p>"},
            {"Id": "2", "Title": "1.04.020 - Authority.", "Content": "<p>more</p>"},
            {"Id": "3", "Title": "1.04.030 - Fees.", "Content": "<p>fees</p>"},
            {"Id": "h", "Title": "Chapter 1.04 - ADOPTION", "Content": ""},
        ]
        sections = list(corpus._yield_sections_from_docs(
            docs, "1.04", "ADOPTION", "1", "GENERAL"
        ))
        assert len(sections) == 3
        assert sections[0].section_number == "1.04.010"
        assert sections[0].chapter == "1.04"
        assert sections[0].title_number == "1"

    def test_non_standard_sections_with_inference(self):
        """Non-standard section numbers trigger inference."""
        corpus = self._make_corpus()
        docs = [
            {"Id": "h", "Title": "CHAPTER I - GENERAL", "Content": ""},
            {"Id": "1", "Title": "1-1 - SHORT TITLE.", "Content": "<p>title</p>"},
            {"Id": "2", "Title": "1-2 - DEFINITIONS.", "Content": "<p>defs</p>"},
            {"Id": "3", "Title": "1-3 - RULES.", "Content": "<p>rules</p>"},
            {"Id": "4", "Title": "1-3.1 - Applicability.", "Content": "<p>app</p>"},
        ]
        sections = list(corpus._yield_sections_from_docs(
            docs, "", "CHAPTER I - GENERAL", "I", "GENERAL"
        ))
        assert len(sections) == 4
        assert sections[0].section_number == "1-1"
        assert sections[1].section_number == "1-2"
        assert sections[3].section_number == "1-3.1"
