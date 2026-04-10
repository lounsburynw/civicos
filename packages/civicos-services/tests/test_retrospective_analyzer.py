"""
Tests for retrospective_analyzer.py — high-stakes decision extraction and analysis.

Covers:
- HighStakesDecision dataclass (defaults, financial_impact_cents, to_dict)
- RetrospectiveAnalyzer pure-logic methods (URL extraction, meeting type inference,
  agenda splitting, budget scanning, gap detection)
- LLM-dependent extraction paths with mocked _call_llm
- Batch analysis orchestration

To run:
    pytest packages/civicos-services/tests/test_retrospective_analyzer.py -q --override-ini="addopts="
"""

import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from civicos_services.processing.retrospective_analyzer import (
    HighStakesDecision,
    RetrospectiveAnalyzer,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def analyzer():
    """Create RetrospectiveAnalyzer with mocked LLM provider (avoids real API calls)."""
    with patch(
        "civicos_services.processing.agenda_integration.AgendaIntegrator._init_structured_clients"
    ):
        with patch(
            "civicos_services.core.llm_provider.get_model"
        ) as mock_get:
            mock_provider = MagicMock()
            mock_provider.default_model = "test-model"
            mock_get.return_value = mock_provider
            ra = RetrospectiveAnalyzer(model="test-model")
    return ra


def _make_decision(**overrides):
    """Helper to create a HighStakesDecision with sensible defaults."""
    defaults = dict(
        item_ref="5.a",
        title="Budget Appropriation",
        description="Supplemental appropriation for infrastructure",
        meeting_date="2025-10-15",
        meeting_type="city_council",
        is_high_stakes=True,
        stakes_score=8,
        decision_type="budget",
        budget_amount=500000.0,
        budget_description="supplemental appropriation",
        affected_population_estimate=10000,
        geographic_scope="citywide",
        project_size_units=None,
        project_location=None,
        project_types=["budget"],
        keywords_for_matching=["budget", "infrastructure"],
        participation_mechanisms=[],
        agenda_url="https://example.gov/agenda.pdf",
        staff_report_url=None,
    )
    defaults.update(overrides)
    return HighStakesDecision(**defaults)


# ---------------------------------------------------------------------------
# HighStakesDecision dataclass
# ---------------------------------------------------------------------------


class TestHighStakesDecisionDefaults:
    def test_speaker_names_defaults_to_empty_list(self):
        d = _make_decision()
        assert d.speaker_names == []

    def test_vote_results_defaults_to_empty_dict(self):
        d = _make_decision()
        assert d.vote_results == {}

    def test_explicit_speaker_names_preserved(self):
        d = _make_decision(speaker_names=["Alice", "Bob"])
        assert d.speaker_names == ["Alice", "Bob"]

    def test_explicit_vote_results_preserved(self):
        d = _make_decision(vote_results={"yes": 4, "no": 1, "abstain": 0})
        assert d.vote_results == {"yes": 4, "no": 1, "abstain": 0}

    def test_passed_defaults_to_true(self):
        d = _make_decision()
        assert d.passed is True

    def test_passed_false_preserved(self):
        d = _make_decision(passed=False)
        assert d.passed is False

    def test_testimony_count_defaults_to_none(self):
        d = _make_decision()
        assert d.testimony_count is None


class TestFinancialImpactCents:
    def test_converts_dollars_to_cents(self):
        d = _make_decision(budget_amount=500000.0)
        assert d.financial_impact_cents == 50000000

    def test_none_budget_returns_none(self):
        d = _make_decision(budget_amount=None)
        assert d.financial_impact_cents is None

    def test_zero_budget_returns_zero_cents(self):
        d = _make_decision(budget_amount=0.0)
        assert d.financial_impact_cents == 0

    def test_fractional_cents_rounded(self):
        d = _make_decision(budget_amount=123.456)
        assert d.financial_impact_cents == 12346

    def test_small_amount_precise(self):
        d = _make_decision(budget_amount=0.01)
        assert d.financial_impact_cents == 1

    def test_large_amount_precise(self):
        d = _make_decision(budget_amount=10_000_000.99)
        assert d.financial_impact_cents == 1_000_000_099


class TestToDict:
    def test_includes_all_fields(self):
        d = _make_decision()
        result = d.to_dict()
        assert result["item_ref"] == "5.a"
        assert result["title"] == "Budget Appropriation"
        assert result["budget_amount"] == 500000.0
        assert result["is_high_stakes"] is True

    def test_includes_computed_financial_impact_cents(self):
        d = _make_decision(budget_amount=250000.0)
        result = d.to_dict()
        assert result["financial_impact_cents"] == 25000000

    def test_none_budget_in_to_dict(self):
        d = _make_decision(budget_amount=None)
        result = d.to_dict()
        assert result["financial_impact_cents"] is None
        assert result["budget_amount"] is None

    def test_lists_serialized_correctly(self):
        d = _make_decision(
            project_types=["housing", "development"],
            keywords_for_matching=["traffic", "parking"],
        )
        result = d.to_dict()
        assert result["project_types"] == ["housing", "development"]
        assert result["keywords_for_matching"] == ["traffic", "parking"]


# ---------------------------------------------------------------------------
# _get_agenda_url
# ---------------------------------------------------------------------------


class TestGetAgendaUrl:
    def test_direct_agenda_url(self, analyzer):
        event = {"agenda_url": "https://example.gov/agenda.pdf"}
        assert analyzer._get_agenda_url(event) == "https://example.gov/agenda.pdf"

    def test_agenda_expansion_source_url(self, analyzer):
        event = {"agenda_expansion": {"source_url": "https://example.gov/expanded.pdf"}}
        assert analyzer._get_agenda_url(event) == "https://example.gov/expanded.pdf"

    def test_legistar_metadata_url(self, analyzer):
        event = {"_legistar_metadata": {"agenda_url": "https://legistar.gov/agenda.pdf"}}
        assert analyzer._get_agenda_url(event) == "https://legistar.gov/agenda.pdf"

    def test_civicclerk_metadata_url(self, analyzer):
        event = {"_civicclerk_metadata": {"agenda_url": "https://civicclerk.com/agenda.pdf"}}
        assert analyzer._get_agenda_url(event) == "https://civicclerk.com/agenda.pdf"

    def test_participation_mechanism_agenda(self, analyzer):
        event = {
            "participation_mechanisms": [
                {"type": "agenda", "url": "https://example.gov/via-mechanism.pdf"}
            ]
        }
        assert analyzer._get_agenda_url(event) == "https://example.gov/via-mechanism.pdf"

    def test_no_url_returns_none(self, analyzer):
        event = {"title": "Council Meeting"}
        assert analyzer._get_agenda_url(event) is None

    def test_empty_event_returns_none(self, analyzer):
        assert analyzer._get_agenda_url({}) is None

    def test_direct_url_takes_priority_over_expansion(self, analyzer):
        event = {
            "agenda_url": "https://direct.gov/agenda.pdf",
            "agenda_expansion": {"source_url": "https://expanded.gov/agenda.pdf"},
        }
        assert analyzer._get_agenda_url(event) == "https://direct.gov/agenda.pdf"

    def test_participation_mechanism_non_agenda_type_skipped(self, analyzer):
        event = {
            "participation_mechanisms": [
                {"type": "email", "url": "mailto:clerk@city.gov"},
                {"type": "agenda", "url": "https://example.gov/agenda.pdf"},
            ]
        }
        assert analyzer._get_agenda_url(event) == "https://example.gov/agenda.pdf"

    def test_participation_mechanism_without_url_skipped(self, analyzer):
        event = {
            "participation_mechanisms": [
                {"type": "agenda"},
            ]
        }
        assert analyzer._get_agenda_url(event) is None


# ---------------------------------------------------------------------------
# _infer_meeting_type
# ---------------------------------------------------------------------------


class TestInferMeetingType:
    def test_planning_commission(self, analyzer):
        event = {"title": "Planning Commission Regular Meeting"}
        assert analyzer._infer_meeting_type(event) == "planning_commission"

    def test_tax_oversight(self, analyzer):
        event = {"title": "Tax Oversight Committee Meeting"}
        assert analyzer._infer_meeting_type(event) == "tax_oversight"

    def test_voter_approved_tax(self, analyzer):
        event = {"title": "Voter-Approved Tax Oversight Board"}
        assert analyzer._infer_meeting_type(event) == "tax_oversight"

    def test_city_council(self, analyzer):
        event = {"title": "City Council Regular Meeting"}
        assert analyzer._infer_meeting_type(event) == "city_council"

    def test_council_meeting(self, analyzer):
        event = {"title": "Council Meeting - Special Session"}
        assert analyzer._infer_meeting_type(event) == "city_council"

    def test_zoning(self, analyzer):
        event = {"title": "Zoning Administrator Hearing"}
        assert analyzer._infer_meeting_type(event) == "zoning_administrator"

    def test_fire_commission(self, analyzer):
        event = {"title": "Fire Commission Board Meeting"}
        assert analyzer._infer_meeting_type(event) == "fire_commission"

    def test_subcommittee(self, analyzer):
        event = {"title": "Finance Subcommittee Meeting"}
        assert analyzer._infer_meeting_type(event) == "council_subcommittee"

    def test_unknown_defaults(self, analyzer):
        event = {"title": "Board of Directors Annual Review"}
        assert analyzer._infer_meeting_type(event) == "unknown"

    def test_empty_title(self, analyzer):
        event = {"title": ""}
        assert analyzer._infer_meeting_type(event) == "unknown"

    def test_no_title_key(self, analyzer):
        event = {}
        assert analyzer._infer_meeting_type(event) == "unknown"

    def test_case_insensitive(self, analyzer):
        event = {"title": "PLANNING COMMISSION MEETING"}
        assert analyzer._infer_meeting_type(event) == "planning_commission"

    def test_planning_takes_priority_over_subcommittee(self, analyzer):
        """'planning' check is first in the chain, so it wins."""
        event = {"title": "Planning Subcommittee Meeting"}
        assert analyzer._infer_meeting_type(event) == "planning_commission"


# ---------------------------------------------------------------------------
# _split_agenda_into_items
# ---------------------------------------------------------------------------


class TestSplitAgendaIntoItems:
    def test_standard_section_letter_format(self, analyzer):
        # Pattern requires letter followed by dot+space: "5.a. " not "5.a "
        text = "\n5.a.  Budget Appropriation\nDetails here\n5.b.  Housing Update\nMore details"
        items = analyzer._split_agenda_into_items(text)
        assert len(items) == 2
        assert items[0][0] == "5.a"
        assert "Budget Appropriation" in items[0][1]
        assert items[1][0] == "5.b"
        assert "Housing Update" in items[1][1]

    def test_letter_only_format(self, analyzer):
        text = "\na.  Approve minutes\nDetails\nb.  Award contract\nMore"
        items = analyzer._split_agenda_into_items(text)
        assert len(items) == 2
        assert items[0][0] == "a"
        assert items[1][0] == "b"

    def test_no_items_returns_whole_document(self, analyzer):
        text = "This is just a plain text document with no agenda items."
        items = analyzer._split_agenda_into_items(text)
        assert len(items) == 1
        assert items[0][0] == "unknown"
        assert "plain text document" in items[0][1]

    def test_item_text_spans_to_next_item(self, analyzer):
        text = "\na.  First item\nSome content here\nMore content\nb.  Second item\nShort"
        items = analyzer._split_agenda_into_items(text)
        assert len(items) == 2
        assert "Some content here" in items[0][1]
        assert "More content" in items[0][1]
        assert "Short" in items[1][1]

    def test_last_item_spans_to_end(self, analyzer):
        text = "\na.  Only item\nContent goes all the way to the end of the document."
        items = analyzer._split_agenda_into_items(text)
        assert len(items) == 1
        assert "end of the document" in items[0][1]


# ---------------------------------------------------------------------------
# _scan_for_budget_amounts
# ---------------------------------------------------------------------------


class TestScanForBudgetAmounts:
    def test_standard_dollar_format(self, analyzer):
        text = "Approve supplemental appropriation of $675,221 for infrastructure."
        result = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(result) == 1
        assert result[0][0] == 675221.0

    def test_millions_shorthand(self, analyzer):
        text = "The capital project costs $4.4M for roadway improvements."
        result = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(result) == 1
        assert result[0][0] == 4400000.0

    def test_written_millions(self, analyzer):
        text = "Grant allocation of $25 million for housing."
        result = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(result) == 1
        assert result[0][0] == 25000000.0

    def test_below_threshold_excluded(self, analyzer):
        text = "Small purchase of $5,000 for office supplies."
        result = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(result) == 0

    def test_multiple_amounts_sorted_descending(self, analyzer):
        text = "Items: $200,000 for parks, $1,500,000 for roads, $300,000 for fire."
        result = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(result) == 3
        assert result[0][0] == 1500000.0
        assert result[1][0] == 300000.0
        assert result[2][0] == 200000.0

    def test_duplicate_amounts_deduplicated(self, analyzer):
        text = "Budget: $500,000 allocated. Confirmed $500,000 expenditure."
        result = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(result) == 1
        assert result[0][0] == 500000.0

    def test_no_dollar_amounts_returns_empty(self, analyzer):
        text = "Regular meeting agenda with no financial items."
        result = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(result) == 0

    def test_context_captured(self, analyzer):
        text = "X" * 50 + "Approve $250,000 for stormwater project" + "Y" * 50
        result = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(result) == 1
        assert "stormwater" in result[0][1]

    def test_exact_threshold_included(self, analyzer):
        text = "Allocation of $100,000 for equipment."
        result = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(result) == 1
        assert result[0][0] == 100000.0

    def test_amount_with_cents(self, analyzer):
        text = "Contract award of $152,718.50 for consulting services."
        result = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(result) == 1
        assert result[0][0] == 152718.50


# ---------------------------------------------------------------------------
# _detect_extraction_gaps
# ---------------------------------------------------------------------------


class TestDetectExtractionGaps:
    def test_no_gaps_when_all_extracted(self, analyzer):
        decisions = [
            _make_decision(budget_amount=500000.0),
            _make_decision(budget_amount=200000.0),
        ]
        scanned = [(500000.0, "ctx1"), (200000.0, "ctx2")]
        gaps = analyzer._detect_extraction_gaps(decisions, scanned)
        assert len(gaps) == 0

    def test_gap_detected_for_missing_amount(self, analyzer):
        decisions = [_make_decision(budget_amount=500000.0)]
        scanned = [(500000.0, "ctx1"), (300000.0, "ctx2")]
        gaps = analyzer._detect_extraction_gaps(decisions, scanned)
        assert len(gaps) == 1
        assert gaps[0][0] == 300000.0

    def test_empty_decisions_all_scanned_are_gaps(self, analyzer):
        scanned = [(200000.0, "ctx1"), (400000.0, "ctx2")]
        gaps = analyzer._detect_extraction_gaps([], scanned)
        assert len(gaps) == 2

    def test_empty_scanned_no_gaps(self, analyzer):
        decisions = [_make_decision(budget_amount=500000.0)]
        gaps = analyzer._detect_extraction_gaps(decisions, [])
        assert len(gaps) == 0

    def test_tolerance_allows_close_amounts(self, analyzer):
        """10% tolerance: $505,000 matches $500,000 (1% diff)."""
        decisions = [_make_decision(budget_amount=505000.0)]
        scanned = [(500000.0, "ctx1")]
        gaps = analyzer._detect_extraction_gaps(decisions, scanned, tolerance=0.1)
        assert len(gaps) == 0

    def test_beyond_tolerance_is_gap(self, analyzer):
        """$600,000 vs $500,000 is 20% — beyond 10% tolerance."""
        decisions = [_make_decision(budget_amount=600000.0)]
        scanned = [(500000.0, "ctx1")]
        gaps = analyzer._detect_extraction_gaps(decisions, scanned, tolerance=0.1)
        assert len(gaps) == 1
        assert gaps[0][0] == 500000.0

    def test_none_budget_decisions_ignored(self, analyzer):
        decisions = [_make_decision(budget_amount=None)]
        scanned = [(300000.0, "ctx1")]
        gaps = analyzer._detect_extraction_gaps(decisions, scanned)
        assert len(gaps) == 1

    def test_zero_budget_decisions_ignored(self, analyzer):
        """budget_amount=0 is falsy, so it's skipped."""
        decisions = [_make_decision(budget_amount=0)]
        scanned = [(300000.0, "ctx1")]
        gaps = analyzer._detect_extraction_gaps(decisions, scanned)
        assert len(gaps) == 1


# ---------------------------------------------------------------------------
# _extract_with_high_stakes_prompt (LLM-dependent, mock _call_llm)
# ---------------------------------------------------------------------------


class TestExtractWithHighStakesPrompt:
    def test_returns_decisions_from_llm_response(self, analyzer):
        llm_response = json.dumps({
            "items": [{
                "item_ref": "5.a",
                "title": "Stormwater Infrastructure",
                "description": "Approve $675,221 for stormwater improvements",
                "is_high_stakes": True,
                "stakes_score": 8,
                "decision_type": "budget",
                "budget_amount": 675221,
                "budget_description": "stormwater infrastructure",
                "affected_population_estimate": 20000,
                "geographic_scope": "citywide",
                "project_size_units": None,
                "project_location": None,
                "project_types": ["environment", "budget"],
                "keywords_for_matching": ["stormwater", "drainage", "flooding"],
            }]
        })
        event = {
            "title": "City Council Meeting",
            "when_human": "Oct 15, 2025",
            "when_iso": "2025-10-15T18:00:00Z",
            "agenda_url": "https://example.gov/agenda.pdf",
        }
        with patch.object(analyzer, "_call_llm", return_value=llm_response):
            results = analyzer._extract_with_high_stakes_prompt(
                "Full agenda text here", event, "city_council", 100000
            )

        assert len(results) == 1
        assert results[0].title == "Stormwater Infrastructure"
        assert results[0].budget_amount == 675221
        assert results[0].stakes_score == 8
        assert results[0].decision_type == "budget"
        assert results[0].meeting_type == "city_council"
        assert "stormwater" in results[0].keywords_for_matching

    def test_non_high_stakes_items_filtered_out(self, analyzer):
        llm_response = json.dumps({
            "items": [{
                "item_ref": "1",
                "title": "Minutes Approval",
                "description": "Routine",
                "is_high_stakes": False,
                "stakes_score": 1,
                "decision_type": "policy",
            }]
        })
        event = {"title": "Meeting", "when_human": "Oct 15"}
        with patch.object(analyzer, "_call_llm", return_value=llm_response):
            results = analyzer._extract_with_high_stakes_prompt(
                "text", event, "city_council", 100000
            )
        assert len(results) == 0

    def test_empty_items_returns_empty_list(self, analyzer):
        llm_response = json.dumps({"items": []})
        event = {"title": "Meeting", "when_human": "Oct 15"}
        with patch.object(analyzer, "_call_llm", return_value=llm_response):
            results = analyzer._extract_with_high_stakes_prompt(
                "text", event, "city_council", 100000
            )
        assert results == []

    def test_llm_returns_invalid_json_returns_empty(self, analyzer):
        event = {"title": "Meeting", "when_human": "Oct 15"}
        with patch.object(analyzer, "_call_llm", return_value="not json at all"):
            results = analyzer._extract_with_high_stakes_prompt(
                "text", event, "city_council", 100000
            )
        assert results == []

    def test_llm_exception_returns_empty(self, analyzer):
        event = {"title": "Meeting", "when_human": "Oct 15"}
        with patch.object(analyzer, "_call_llm", side_effect=RuntimeError("API down")):
            results = analyzer._extract_with_high_stakes_prompt(
                "text", event, "city_council", 100000
            )
        assert results == []

    def test_multiple_items_all_returned(self, analyzer):
        llm_response = json.dumps({
            "items": [
                {
                    "item_ref": "5.a",
                    "title": "Parks Budget",
                    "description": "Parks funding",
                    "is_high_stakes": True,
                    "stakes_score": 7,
                    "decision_type": "budget",
                    "budget_amount": 200000,
                    "project_types": ["environment"],
                    "keywords_for_matching": ["parks"],
                },
                {
                    "item_ref": "5.b",
                    "title": "Housing Project",
                    "description": "30-unit development",
                    "is_high_stakes": True,
                    "stakes_score": 9,
                    "decision_type": "development",
                    "budget_amount": None,
                    "project_size_units": 30,
                    "project_types": ["housing"],
                    "keywords_for_matching": ["housing"],
                },
            ]
        })
        event = {
            "title": "City Council",
            "when_human": "Oct 15",
            "when_iso": "2025-10-15",
            "agenda_url": "https://example.gov/a.pdf",
        }
        with patch.object(analyzer, "_call_llm", return_value=llm_response):
            results = analyzer._extract_with_high_stakes_prompt(
                "text", event, "city_council", 100000
            )
        assert len(results) == 2
        assert results[0].title == "Parks Budget"
        assert results[1].title == "Housing Project"
        assert results[1].project_size_units == 30

    def test_meeting_date_from_when_iso(self, analyzer):
        llm_response = json.dumps({
            "items": [{
                "item_ref": "1",
                "title": "Test",
                "description": "Desc",
                "is_high_stakes": True,
                "stakes_score": 7,
                "decision_type": "budget",
                "budget_amount": 200000,
                "project_types": ["budget"],
                "keywords_for_matching": [],
            }]
        })
        event = {
            "title": "Meeting",
            "when_iso": "2025-10-15T18:00:00Z",
            "when_human": "Oct 15, 2025",
        }
        with patch.object(analyzer, "_call_llm", return_value=llm_response):
            results = analyzer._extract_with_high_stakes_prompt(
                "text", event, "city_council", 100000
            )
        assert results[0].meeting_date == "2025-10-15T18:00:00Z"


# ---------------------------------------------------------------------------
# _extract_targeted
# ---------------------------------------------------------------------------


class TestExtractTargeted:
    def test_empty_missed_amounts_returns_empty(self, analyzer):
        result = analyzer._extract_targeted("text", [], {}, "city_council")
        assert result == []

    def test_returns_decisions_for_missed_amounts(self, analyzer):
        llm_response = json.dumps({
            "items": [{
                "item_ref": "3.c",
                "title": "Fire Equipment",
                "description": "Replacement fire truck",
                "is_high_stakes": True,
                "stakes_score": 7,
                "decision_type": "budget",
                "budget_amount": 350000,
                "budget_description": "fire truck",
                "project_types": ["public_safety"],
                "keywords_for_matching": ["fire", "equipment"],
            }]
        })
        event = {
            "title": "Council Meeting",
            "when_human": "Oct 15",
            "when_iso": "2025-10-15",
            "agenda_url": "https://example.gov/agenda.pdf",
        }
        missed = [(350000.0, "fire truck replacement $350,000")]
        with patch.object(analyzer, "_call_llm", return_value=llm_response):
            results = analyzer._extract_targeted("text", missed, event, "city_council")
        assert len(results) == 1
        assert results[0].title == "Fire Equipment"
        assert results[0].budget_amount == 350000

    def test_llm_failure_returns_empty(self, analyzer):
        event = {"title": "Meeting", "when_human": "Oct 15"}
        with patch.object(analyzer, "_call_llm", side_effect=RuntimeError("fail")):
            results = analyzer._extract_targeted(
                "text", [(300000.0, "ctx")], event, "city_council"
            )
        assert results == []


# ---------------------------------------------------------------------------
# extract_high_stakes_decisions (orchestration)
# ---------------------------------------------------------------------------


class TestExtractHighStakesDecisions:
    def test_no_agenda_url_returns_empty(self, analyzer):
        event = {"title": "Mystery Meeting"}
        result = analyzer.extract_high_stakes_decisions(event)
        assert result == []

    def test_download_failure_returns_empty(self, analyzer):
        event = {"agenda_url": "https://example.gov/agenda.pdf", "title": "Meeting"}
        with patch.object(analyzer, "_download_and_extract_agenda", return_value=None):
            result = analyzer.extract_high_stakes_decisions(event)
        assert result == []

    def test_filters_by_min_stakes_score(self, analyzer):
        low_stakes = _make_decision(stakes_score=3, title="Low Stakes")
        high_stakes = _make_decision(stakes_score=8, title="High Stakes")

        with patch.object(analyzer, "_download_and_extract_agenda", return_value="text"):
            with patch.object(
                analyzer,
                "_extract_with_high_stakes_prompt",
                return_value=[low_stakes, high_stakes],
            ):
                with patch.object(analyzer, "_scan_for_budget_amounts", return_value=[]):
                    result = analyzer.extract_high_stakes_decisions(
                        {"agenda_url": "https://example.gov/a.pdf", "title": "Meeting"},
                        min_stakes_score=6,
                    )

        assert len(result) == 1
        assert result[0].title == "High Stakes"

    def test_gap_detection_triggers_targeted_extraction(self, analyzer):
        primary = _make_decision(budget_amount=500000.0, title="Primary")
        recovered = _make_decision(budget_amount=300000.0, title="Recovered")

        with patch.object(analyzer, "_download_and_extract_agenda", return_value="text"):
            with patch.object(
                analyzer, "_extract_with_high_stakes_prompt", return_value=[primary]
            ):
                with patch.object(
                    analyzer,
                    "_scan_for_budget_amounts",
                    return_value=[(500000.0, "ctx1"), (300000.0, "ctx2")],
                ):
                    with patch.object(
                        analyzer,
                        "_detect_extraction_gaps",
                        return_value=[(300000.0, "ctx2")],
                    ):
                        with patch.object(
                            analyzer, "_extract_targeted", return_value=[recovered]
                        ):
                            result = analyzer.extract_high_stakes_decisions(
                                {"agenda_url": "https://x.gov/a.pdf", "title": "M"},
                                min_stakes_score=1,
                            )

        assert len(result) == 2
        titles = [d.title for d in result]
        assert "Primary" in titles
        assert "Recovered" in titles


# ---------------------------------------------------------------------------
# analyze_meeting_batch
# ---------------------------------------------------------------------------


class TestAnalyzeMeetingBatch:
    def test_empty_events_returns_zero_counts(self, analyzer):
        result = analyzer.analyze_meeting_batch([])
        assert result["meetings_analyzed"] == 0
        assert result["decision_count"] == 0
        assert result["total_budget_amount"] == 0.0
        assert result["high_stakes_decisions"] == []

    def test_aggregates_decisions_across_meetings(self, analyzer):
        d1 = _make_decision(
            budget_amount=500000.0,
            decision_type="budget",
            meeting_type="city_council",
        )
        d2 = _make_decision(
            budget_amount=200000.0,
            decision_type="development",
            meeting_type="planning_commission",
        )

        with patch.object(
            analyzer,
            "extract_high_stakes_decisions",
            side_effect=[[d1], [d2]],
        ):
            result = analyzer.analyze_meeting_batch(
                [{"title": "Meeting 1"}, {"title": "Meeting 2"}]
            )

        assert result["meetings_analyzed"] == 2
        assert result["decision_count"] == 2
        assert result["total_budget_amount"] == 700000.0
        assert result["decision_types_breakdown"]["budget"] == 1
        assert result["decision_types_breakdown"]["development"] == 1
        assert result["by_meeting_type"]["city_council"] == 1
        assert result["by_meeting_type"]["planning_commission"] == 1

    def test_none_budget_not_added_to_total(self, analyzer):
        d = _make_decision(budget_amount=None, decision_type="policy")

        with patch.object(
            analyzer, "extract_high_stakes_decisions", return_value=[d]
        ):
            result = analyzer.analyze_meeting_batch([{"title": "Meeting"}])

        assert result["total_budget_amount"] == 0.0

    def test_decisions_serialized_via_to_dict(self, analyzer):
        d = _make_decision(budget_amount=250000.0)

        with patch.object(
            analyzer, "extract_high_stakes_decisions", return_value=[d]
        ):
            result = analyzer.analyze_meeting_batch([{"title": "Meeting"}])

        assert len(result["high_stakes_decisions"]) == 1
        serialized = result["high_stakes_decisions"][0]
        assert serialized["budget_amount"] == 250000.0
        assert serialized["financial_impact_cents"] == 25000000

    def test_extraction_timestamp_is_valid_iso(self, analyzer):
        with patch.object(
            analyzer, "extract_high_stakes_decisions", return_value=[]
        ):
            result = analyzer.analyze_meeting_batch([{"title": "Meeting"}])

        from datetime import datetime
        ts = datetime.fromisoformat(result["extraction_timestamp"])
        assert ts.year >= 2025

    def test_meeting_with_no_decisions_still_counted(self, analyzer):
        with patch.object(
            analyzer, "extract_high_stakes_decisions", return_value=[]
        ):
            result = analyzer.analyze_meeting_batch(
                [{"title": "M1"}, {"title": "M2"}, {"title": "M3"}]
            )

        assert result["meetings_analyzed"] == 3
        assert result["decision_count"] == 0


# ---------------------------------------------------------------------------
# _extract_from_item
# ---------------------------------------------------------------------------


class TestExtractFromItem:
    def test_returns_decision_from_llm(self, analyzer):
        llm_response = json.dumps({
            "items": [{
                "item_ref": "5.g",
                "title": "Capital Project",
                "description": "Road improvements",
                "is_high_stakes": True,
                "stakes_score": 7,
                "decision_type": "budget",
                "budget_amount": 400000,
                "project_types": ["transportation"],
                "keywords_for_matching": ["road", "paving"],
            }]
        })
        event = {
            "title": "Council",
            "when_human": "Oct 15",
            "when_iso": "2025-10-15",
            "agenda_url": "https://x.gov/a.pdf",
        }
        with patch.object(analyzer, "_call_llm", return_value=llm_response):
            results = analyzer._extract_from_item(
                "5.g", "Road improvements $400K", event, "city_council", 100000
            )
        assert len(results) == 1
        assert results[0].item_ref == "5.g"
        assert results[0].budget_amount == 400000

    def test_non_high_stakes_filtered(self, analyzer):
        llm_response = json.dumps({
            "items": [{
                "item_ref": "1",
                "title": "Minutes",
                "description": "Approve minutes",
                "is_high_stakes": False,
                "stakes_score": 1,
                "decision_type": "governance",
            }]
        })
        event = {"title": "Meeting", "when_human": "Oct 15"}
        with patch.object(analyzer, "_call_llm", return_value=llm_response):
            results = analyzer._extract_from_item(
                "1", "Approve minutes", event, "city_council", 100000
            )
        assert results == []

    def test_exception_returns_empty(self, analyzer):
        event = {"title": "Meeting", "when_human": "Oct 15"}
        with patch.object(analyzer, "_call_llm", side_effect=RuntimeError("fail")):
            results = analyzer._extract_from_item(
                "1", "text", event, "city_council", 100000
            )
        assert results == []


# ---------------------------------------------------------------------------
# RetrospectiveAnalyzer __init__
# ---------------------------------------------------------------------------


class TestRetrospectiveAnalyzerInit:
    def test_default_model_is_gemini_flash(self):
        """When no model is provided, default is gemini-2.0-flash-exp."""
        with patch(
            "civicos_services.processing.agenda_integration.AgendaIntegrator._init_structured_clients"
        ):
            with patch(
                "civicos_services.core.llm_provider.get_model"
            ) as mock_get_model:
                mock_provider = MagicMock()
                mock_provider.default_model = "gemini-2.0-flash-exp"
                mock_get_model.return_value = mock_provider
                ra = RetrospectiveAnalyzer()

        # Should call get_model with the default model name
        mock_get_model.assert_called_once_with("gemini-2.0-flash-exp")

    def test_custom_model_overrides_default(self):
        with patch(
            "civicos_services.processing.agenda_integration.AgendaIntegrator._init_structured_clients"
        ):
            with patch(
                "civicos_services.core.llm_provider.get_model"
            ) as mock_get_model:
                mock_provider = MagicMock()
                mock_provider.default_model = "custom-model"
                mock_get_model.return_value = mock_provider
                ra = RetrospectiveAnalyzer(model="custom-model")

        mock_get_model.assert_called_once_with("custom-model")
