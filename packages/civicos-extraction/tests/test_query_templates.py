"""
Tests for municipal funding research query templates.

Tests QueryTemplate construction, template formatting with placeholder
substitution, priority filtering, sorting, and topic-based lookup.
"""

from datetime import datetime
from unittest.mock import patch

import pytest

from civicos_extraction.research.municipal.query_templates import (
    HOUSING_QUERY_TEMPLATES,
    QUERY_TEMPLATES_BY_TOPIC,
    QueryTemplate,
    build_queries_from_templates,
    format_template,
    get_templates_for_topic,
)


class TestQueryTemplate:
    """QueryTemplate dataclass construction and defaults."""

    def test_construction_with_defaults(self):
        """Priority defaults to 1 when not specified."""
        qt = QueryTemplate(
            key="test_key",
            template="{municipality} {state} test",
            description="Test query",
            program_type="test_program",
        )
        assert qt.key == "test_key"
        assert qt.template == "{municipality} {state} test"
        assert qt.description == "Test query"
        assert qt.program_type == "test_program"
        assert qt.priority == 1

    def test_explicit_priority_overrides_default(self):
        """Explicit priority replaces the default of 1."""
        qt = QueryTemplate(
            key="low",
            template="test",
            description="low priority",
            program_type="tp",
            priority=3,
        )
        assert qt.priority == 3

    def test_priority_zero(self):
        """Priority 0 is accepted (no minimum enforced)."""
        qt = QueryTemplate(
            key="urgent", template="t", description="d", program_type="p", priority=0,
        )
        assert qt.priority == 0


class TestHousingQueryTemplates:
    """Validate the built-in HOUSING_QUERY_TEMPLATES list."""

    def test_template_count(self):
        """There are exactly 8 housing query templates."""
        assert len(HOUSING_QUERY_TEMPLATES) == 8

    def test_all_keys_unique(self):
        """Every template key is distinct."""
        keys = [t.key for t in HOUSING_QUERY_TEMPLATES]
        assert len(keys) == len(set(keys))

    def test_known_keys_present(self):
        """Expected keys exist in the template list."""
        keys = {t.key for t in HOUSING_QUERY_TEMPLATES}
        assert "trust_fund" in keys
        assert "inclusionary_fees" in keys
        assert "commercial_linkage" in keys
        assert "ballot_measures" in keys
        assert "cdbg_home" in keys
        assert "bmr_rental" in keys
        assert "housing_element" in keys
        assert "inclusionary_ordinance" in keys

    def test_trust_fund_template_content(self):
        """trust_fund template contains expected placeholders and keywords."""
        trust_fund = next(t for t in HOUSING_QUERY_TEMPLATES if t.key == "trust_fund")
        assert "{municipality}" in trust_fund.template
        assert "{state}" in trust_fund.template
        assert "affordable housing trust fund" in trust_fund.template
        assert trust_fund.program_type == "affordable_housing_trust_fund"
        assert trust_fund.priority == 1

    def test_housing_element_is_low_priority(self):
        """housing_element is priority 3 (lowest)."""
        he = next(t for t in HOUSING_QUERY_TEMPLATES if t.key == "housing_element")
        assert he.priority == 3

    def test_inclusionary_ordinance_is_priority_2(self):
        """inclusionary_ordinance is priority 2."""
        io = next(t for t in HOUSING_QUERY_TEMPLATES if t.key == "inclusionary_ordinance")
        assert io.priority == 2

    def test_bmr_rental_is_priority_2(self):
        """bmr_rental is priority 2."""
        bmr = next(t for t in HOUSING_QUERY_TEMPLATES if t.key == "bmr_rental")
        assert bmr.priority == 2

    def test_all_templates_have_municipality_placeholder(self):
        """Every template uses {municipality}."""
        for t in HOUSING_QUERY_TEMPLATES:
            assert "{municipality}" in t.template, f"{t.key} missing {{municipality}}"

    def test_all_templates_have_state_placeholder(self):
        """Every template uses {state}."""
        for t in HOUSING_QUERY_TEMPLATES:
            assert "{state}" in t.template, f"{t.key} missing {{state}}"

    def test_ballot_measures_uses_year_range(self):
        """ballot_measures template uses {year_range}."""
        bm = next(t for t in HOUSING_QUERY_TEMPLATES if t.key == "ballot_measures")
        assert "{year_range}" in bm.template

    def test_housing_element_uses_year(self):
        """housing_element template uses {year}."""
        he = next(t for t in HOUSING_QUERY_TEMPLATES if t.key == "housing_element")
        assert "{year}" in he.template


class TestQueryTemplatesByTopic:
    """Validate the QUERY_TEMPLATES_BY_TOPIC registry."""

    def test_housing_key_maps_to_housing_templates(self):
        """'housing' key resolves to the HOUSING_QUERY_TEMPLATES list."""
        assert QUERY_TEMPLATES_BY_TOPIC["housing"] is HOUSING_QUERY_TEMPLATES

    def test_only_housing_registered(self):
        """Only 'housing' is currently registered."""
        assert list(QUERY_TEMPLATES_BY_TOPIC.keys()) == ["housing"]


class TestGetTemplatesForTopic:
    """get_templates_for_topic() topic lookup with fallback."""

    def test_known_topic_returns_correct_templates(self):
        """'housing' returns the housing templates."""
        result = get_templates_for_topic("housing")
        assert result is HOUSING_QUERY_TEMPLATES

    def test_unknown_topic_falls_back_to_housing(self):
        """Unknown topic defaults to HOUSING_QUERY_TEMPLATES."""
        result = get_templates_for_topic("transportation")
        assert result is HOUSING_QUERY_TEMPLATES

    def test_empty_string_topic_falls_back(self):
        """Empty string is not a registered topic — falls back."""
        result = get_templates_for_topic("")
        assert result is HOUSING_QUERY_TEMPLATES

    def test_fallback_returns_same_object(self):
        """Fallback returns the same list object as the housing constant."""
        result = get_templates_for_topic("nonexistent")
        assert result is HOUSING_QUERY_TEMPLATES
        assert len(result) == 8


class TestFormatTemplate:
    """format_template() placeholder substitution and defaults."""

    def _make_template(self, template_str: str) -> QueryTemplate:
        return QueryTemplate(
            key="test", template=template_str, description="d", program_type="p",
        )

    def test_basic_substitution(self):
        """municipality and state are substituted into the template."""
        qt = self._make_template("{municipality} {state} housing")
        result = format_template(qt, "San Rafael", "California", year=2025)
        assert result == "San Rafael California housing"

    def test_year_substitution(self):
        """Explicit year replaces {year} placeholder."""
        qt = self._make_template("{municipality} housing {year}")
        result = format_template(qt, "San Rafael", "California", year=2025)
        assert result == "San Rafael housing 2025"

    def test_year_range_substitution(self):
        """Explicit year_range replaces {year_range} placeholder."""
        qt = self._make_template("{municipality} measures {year_range}")
        result = format_template(qt, "Mill Valley", "California", year=2025, year_range="2022-2025")
        assert result == "Mill Valley measures 2022-2025"

    def test_default_year_uses_current_year(self):
        """Omitting year uses datetime.now().year."""
        qt = self._make_template("data {year}")
        with patch("civicos_extraction.research.municipal.query_templates.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 10)
            result = format_template(qt, "Fairfax", "California")
        assert result == "data 2026"

    def test_default_year_range_derived_from_year(self):
        """Omitting year_range produces '2020-{year}'."""
        qt = self._make_template("ballot {year_range}")
        result = format_template(qt, "Ross", "California", year=2025)
        assert result == "ballot 2020-2025"

    def test_default_year_range_derives_from_default_year(self):
        """When both year and year_range are omitted, year_range uses the current year."""
        qt = self._make_template("{year_range}")
        with patch("civicos_extraction.research.municipal.query_templates.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2030, 1, 1)
            result = format_template(qt, "Test", "CA")
        assert result == "2020-2030"

    def test_all_placeholders_together(self):
        """Template with all four placeholders formats correctly."""
        qt = self._make_template("{municipality} {state} {year} {year_range}")
        result = format_template(qt, "Larkspur", "California", year=2025, year_range="2021-2025")
        assert result == "Larkspur California 2025 2021-2025"

    def test_template_with_no_placeholders(self):
        """Literal template with no placeholders is returned as-is."""
        qt = self._make_template("static query text")
        result = format_template(qt, "Anywhere", "AnyState", year=2025)
        assert result == "static query text"

    def test_municipality_with_spaces(self):
        """Multi-word municipality name substitutes correctly."""
        qt = self._make_template("{municipality} zoning")
        result = format_template(qt, "San Anselmo", "California", year=2025)
        assert result == "San Anselmo zoning"

    def test_explicit_year_range_overrides_default(self):
        """Providing year_range explicitly prevents the 2020-{year} default."""
        qt = self._make_template("{year_range}")
        result = format_template(qt, "X", "Y", year=2025, year_range="2018-2024")
        assert result == "2018-2024"


class TestBuildQueriesFromTemplates:
    """build_queries_from_templates() filtering, sorting, and formatting."""

    def _templates(self) -> list[QueryTemplate]:
        """Three templates with distinct priorities for testing."""
        return [
            QueryTemplate(key="high", template="{municipality} {state} high", description="d", program_type="p", priority=1),
            QueryTemplate(key="med", template="{municipality} {state} med", description="d", program_type="p", priority=2),
            QueryTemplate(key="low", template="{municipality} {state} low", description="d", program_type="p", priority=3),
        ]

    def test_default_max_priority_includes_all(self):
        """Default max_priority=3 includes all three priority levels."""
        result = build_queries_from_templates(self._templates(), "City", "State")
        assert len(result) == 3

    def test_returns_formatted_query_strings(self):
        """Query strings contain substituted municipality and state."""
        result = build_queries_from_templates(self._templates(), "Berkeley", "California")
        queries = [q for q, _ in result]
        assert "Berkeley California high" in queries
        assert "Berkeley California med" in queries
        assert "Berkeley California low" in queries

    def test_tuples_pair_query_with_template(self):
        """Each tuple pairs the formatted string with its source template."""
        result = build_queries_from_templates(self._templates(), "X", "Y")
        for query_str, template in result:
            assert template.key in query_str

    def test_sorted_by_priority_ascending(self):
        """Results are sorted by priority (1 first, 3 last)."""
        result = build_queries_from_templates(self._templates(), "X", "Y")
        priorities = [t.priority for _, t in result]
        assert priorities == [1, 2, 3]

    def test_max_priority_1_filters_to_high_only(self):
        """max_priority=1 includes only priority-1 templates."""
        result = build_queries_from_templates(self._templates(), "X", "Y", max_priority=1)
        assert len(result) == 1
        assert result[0][1].key == "high"

    def test_max_priority_2_filters_out_low(self):
        """max_priority=2 excludes priority-3 templates."""
        result = build_queries_from_templates(self._templates(), "X", "Y", max_priority=2)
        assert len(result) == 2
        keys = [t.key for _, t in result]
        assert "high" in keys
        assert "med" in keys
        assert "low" not in keys

    def test_max_priority_0_returns_empty(self):
        """max_priority=0 excludes all templates (all have priority >= 1)."""
        result = build_queries_from_templates(self._templates(), "X", "Y", max_priority=0)
        assert result == []

    def test_empty_template_list_returns_empty(self):
        """Empty input list produces empty output."""
        result = build_queries_from_templates([], "City", "State")
        assert result == []

    def test_sort_stability_for_equal_priorities(self):
        """Templates with the same priority preserve their original order."""
        same_priority = [
            QueryTemplate(key="a", template="{municipality} a", description="d", program_type="p", priority=1),
            QueryTemplate(key="b", template="{municipality} b", description="d", program_type="p", priority=1),
            QueryTemplate(key="c", template="{municipality} c", description="d", program_type="p", priority=1),
        ]
        result = build_queries_from_templates(same_priority, "X", "Y")
        keys = [t.key for _, t in result]
        assert keys == ["a", "b", "c"]

    def test_with_housing_templates(self):
        """Integration: build_queries works with the real HOUSING_QUERY_TEMPLATES."""
        result = build_queries_from_templates(
            HOUSING_QUERY_TEMPLATES, "San Rafael", "California", max_priority=3,
        )
        assert len(result) == 8
        # First results should be priority 1
        assert result[0][1].priority == 1
        # Last result should be priority 3 (housing_element)
        assert result[-1][1].priority == 3
        # All queries should contain the municipality
        for query_str, _ in result:
            assert "San Rafael" in query_str
            assert "California" in query_str

    def test_priority_filter_with_housing_templates(self):
        """Priority 1 filter on real templates returns only high-priority items."""
        result = build_queries_from_templates(
            HOUSING_QUERY_TEMPLATES, "Test", "CA", max_priority=1,
        )
        # priority-1 items: trust_fund, inclusionary_fees, commercial_linkage,
        #   ballot_measures, cdbg_home = 5
        assert len(result) == 5
        for _, t in result:
            assert t.priority == 1

    def test_formatted_query_includes_year_defaults(self):
        """Queries that use {year} or {year_range} get default values."""
        templates = [
            QueryTemplate(
                key="yr", template="{municipality} {year} {year_range}",
                description="d", program_type="p",
            ),
        ]
        with patch("civicos_extraction.research.municipal.query_templates.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 1)
            result = build_queries_from_templates(templates, "City", "State")
        assert len(result) == 1
        assert result[0][0] == "City 2026 2020-2026"
