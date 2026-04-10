"""Tests for retrospective decision analysis module.

Tests HighStakesDecision dataclass (financial_impact_cents, to_dict, mutable defaults),
RetrospectiveAnalyzer logic (URL priority, meeting type inference, budget scanning,
extraction gap detection, agenda splitting, stakes filtering, batch aggregation),
and AgendaDownloadError.

External I/O (HTTP, LLM) is mocked; logic under test runs for real.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from civicos_extraction.processing.retrospective_analyzer import (
    AgendaDownloadError,
    HighStakesDecision,
    RetrospectiveAnalyzer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_analyzer():
    """Create a RetrospectiveAnalyzer with a mock LLM provider."""
    provider = MagicMock()
    provider.default_model = "test-model"
    return RetrospectiveAnalyzer(provider=provider)


def _make_event(**overrides):
    """Build a minimal event dict, merging overrides."""
    base = {
        "title": "City Council Meeting",
        "when_iso": "2025-10-15T18:30:00",
        "when_human": "October 15, 2025 6:30 PM",
        "participation_mechanisms": [],
    }
    base.update(overrides)
    return base


def _make_decision(**overrides):
    """Build a HighStakesDecision with sensible defaults, merging overrides."""
    defaults = dict(
        item_ref="5.a",
        title="Budget Approval",
        description="Approve supplemental budget",
        meeting_date="2025-10-15",
        meeting_type="city_council",
        is_high_stakes=True,
        stakes_score=8,
        decision_type="budget",
        budget_amount=500000.0,
        budget_description="supplemental appropriation",
        affected_population_estimate=60000,
        geographic_scope="citywide",
        project_size_units=None,
        project_location=None,
        project_types=["budget"],
        keywords_for_matching=["budget", "appropriation"],
        participation_mechanisms=[],
        agenda_url="https://example.gov/agenda.pdf",
        staff_report_url=None,
    )
    defaults.update(overrides)
    return HighStakesDecision(**defaults)


# ===========================================================================
# AgendaDownloadError
# ===========================================================================

class TestAgendaDownloadError:

    def test_is_exception(self):
        err = AgendaDownloadError("download failed")
        assert str(err) == "download failed"

    def test_can_be_raised_and_caught(self):
        with pytest.raises(AgendaDownloadError, match="PDF not found"):
            raise AgendaDownloadError("PDF not found")


# ===========================================================================
# HighStakesDecision dataclass
# ===========================================================================

class TestHighStakesDecisionMutableDefaults:

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

    def test_mutable_defaults_are_independent(self):
        """Two instances should not share the same list/dict."""
        d1 = _make_decision()
        d2 = _make_decision()
        d1.speaker_names.append("Charlie")
        d1.vote_results["yes"] = 5
        assert d2.speaker_names == []
        assert d2.vote_results == {}


class TestFinancialImpactCents:

    def test_none_budget_returns_none(self):
        d = _make_decision(budget_amount=None)
        assert d.financial_impact_cents is None

    def test_integer_budget(self):
        d = _make_decision(budget_amount=500000.0)
        assert d.financial_impact_cents == 50000000

    def test_fractional_budget(self):
        d = _make_decision(budget_amount=1234567.89)
        assert d.financial_impact_cents == 123456789

    def test_small_budget(self):
        d = _make_decision(budget_amount=0.01)
        assert d.financial_impact_cents == 1

    def test_zero_budget(self):
        d = _make_decision(budget_amount=0.0)
        assert d.financial_impact_cents == 0

    def test_large_budget_millions(self):
        d = _make_decision(budget_amount=4_400_000.0)
        assert d.financial_impact_cents == 440_000_000


class TestToDict:

    def test_includes_all_fields(self):
        d = _make_decision(budget_amount=250000.0)
        result = d.to_dict()
        assert result["item_ref"] == "5.a"
        assert result["title"] == "Budget Approval"
        assert result["budget_amount"] == 250000.0
        assert result["is_high_stakes"] is True
        assert result["stakes_score"] == 8
        assert result["decision_type"] == "budget"

    def test_includes_computed_financial_impact_cents(self):
        d = _make_decision(budget_amount=250000.0)
        result = d.to_dict()
        assert result["financial_impact_cents"] == 25000000

    def test_none_budget_in_dict(self):
        d = _make_decision(budget_amount=None)
        result = d.to_dict()
        assert result["financial_impact_cents"] is None
        assert result["budget_amount"] is None

    def test_optional_fields_in_dict(self):
        d = _make_decision(
            item_number="5.a",
            extracted_outcome="approved",
            passed=True,
        )
        result = d.to_dict()
        assert result["item_number"] == "5.a"
        assert result["extracted_outcome"] == "approved"
        assert result["passed"] is True


# ===========================================================================
# RetrospectiveAnalyzer._get_agenda_url
# ===========================================================================

class TestGetAgendaUrl:

    def test_prefers_minutes_url(self):
        analyzer = _make_analyzer()
        event = _make_event(
            minutes_url="https://example.gov/minutes.pdf",
            agenda_url="https://example.gov/agenda.pdf",
        )
        assert analyzer._get_agenda_url(event) == "https://example.gov/minutes.pdf"

    def test_falls_back_to_agenda_url(self):
        analyzer = _make_analyzer()
        event = _make_event(agenda_url="https://example.gov/agenda.pdf")
        assert analyzer._get_agenda_url(event) == "https://example.gov/agenda.pdf"

    def test_agenda_expansion_source_url(self):
        analyzer = _make_analyzer()
        event = _make_event(
            agenda_expansion={"source_url": "https://example.gov/expanded.pdf"},
        )
        assert analyzer._get_agenda_url(event) == "https://example.gov/expanded.pdf"

    def test_legistar_metadata(self):
        analyzer = _make_analyzer()
        event = _make_event(
            _legistar_metadata={"agenda_url": "https://legistar.gov/agenda.pdf"},
        )
        assert analyzer._get_agenda_url(event) == "https://legistar.gov/agenda.pdf"

    def test_civicclerk_metadata(self):
        analyzer = _make_analyzer()
        event = _make_event(
            _civicclerk_metadata={"agenda_url": "https://civicclerk.gov/agenda.pdf"},
        )
        assert analyzer._get_agenda_url(event) == "https://civicclerk.gov/agenda.pdf"

    def test_participation_mechanism_with_agenda_type(self):
        analyzer = _make_analyzer()
        event = _make_event(
            participation_mechanisms=[
                {"type": "agenda", "url": "https://example.gov/participate-agenda.pdf"},
            ],
        )
        assert analyzer._get_agenda_url(event) == "https://example.gov/participate-agenda.pdf"

    def test_participation_mechanism_non_agenda_type_skipped(self):
        analyzer = _make_analyzer()
        event = _make_event(
            participation_mechanisms=[
                {"type": "email", "url": "https://example.gov/comment"},
            ],
        )
        assert analyzer._get_agenda_url(event) is None

    def test_no_url_found(self):
        analyzer = _make_analyzer()
        event = _make_event()
        assert analyzer._get_agenda_url(event) is None

    def test_priority_order_minutes_over_legistar(self):
        """Minutes should be preferred over all platform-specific metadata."""
        analyzer = _make_analyzer()
        event = _make_event(
            minutes_url="https://example.gov/minutes.pdf",
            _legistar_metadata={"agenda_url": "https://legistar.gov/agenda.pdf"},
        )
        assert analyzer._get_agenda_url(event) == "https://example.gov/minutes.pdf"


# ===========================================================================
# RetrospectiveAnalyzer._infer_meeting_type
# ===========================================================================

class TestInferMeetingType:

    def test_planning_commission(self):
        analyzer = _make_analyzer()
        assert analyzer._infer_meeting_type({"title": "Planning Commission Meeting"}) == "planning_commission"

    def test_tax_oversight(self):
        analyzer = _make_analyzer()
        assert analyzer._infer_meeting_type({"title": "Tax Oversight Committee"}) == "tax_oversight"

    def test_voter_approved_tax(self):
        analyzer = _make_analyzer()
        assert analyzer._infer_meeting_type({"title": "Voter-Approved Tax Board"}) == "tax_oversight"

    def test_city_council(self):
        analyzer = _make_analyzer()
        assert analyzer._infer_meeting_type({"title": "City Council Regular Meeting"}) == "city_council"

    def test_council_meeting(self):
        analyzer = _make_analyzer()
        assert analyzer._infer_meeting_type({"title": "Regular Council Meeting"}) == "city_council"

    def test_zoning_administrator(self):
        analyzer = _make_analyzer()
        assert analyzer._infer_meeting_type({"title": "Zoning Administrator Hearing"}) == "zoning_administrator"

    def test_fire_commission(self):
        analyzer = _make_analyzer()
        assert analyzer._infer_meeting_type({"title": "Fire Commission Regular"}) == "fire_commission"

    def test_subcommittee(self):
        analyzer = _make_analyzer()
        assert analyzer._infer_meeting_type({"title": "Finance Subcommittee"}) == "council_subcommittee"

    def test_unknown_type(self):
        analyzer = _make_analyzer()
        assert analyzer._infer_meeting_type({"title": "Board of Directors"}) == "unknown"

    def test_empty_title(self):
        analyzer = _make_analyzer()
        assert analyzer._infer_meeting_type({}) == "unknown"

    def test_case_insensitive(self):
        analyzer = _make_analyzer()
        assert analyzer._infer_meeting_type({"title": "PLANNING commission"}) == "planning_commission"


# ===========================================================================
# RetrospectiveAnalyzer._scan_for_budget_amounts
# ===========================================================================

class TestScanForBudgetAmounts:

    def test_standard_dollar_format(self):
        analyzer = _make_analyzer()
        text = "The project costs $500,000 for infrastructure."
        results = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(results) == 1
        assert results[0][0] == 500000.0

    def test_multiple_amounts(self):
        analyzer = _make_analyzer()
        text = "Phase 1: $200,000. Phase 2: $300,000. Total: $500,000."
        results = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        amounts = [r[0] for r in results]
        assert 200000.0 in amounts
        assert 300000.0 in amounts
        assert 500000.0 in amounts
        assert len(results) == 3

    def test_millions_shorthand_M(self):
        analyzer = _make_analyzer()
        text = "The budget allocation is $4.4M for capital projects."
        results = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(results) == 1
        assert results[0][0] == 4400000.0

    def test_millions_written_out(self):
        analyzer = _make_analyzer()
        text = "The project requires $25 million in funding."
        results = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(results) == 1
        assert results[0][0] == 25000000.0

    def test_below_min_budget_excluded(self):
        analyzer = _make_analyzer()
        text = "Small purchase of $50,000 and major purchase of $200,000."
        results = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        amounts = [r[0] for r in results]
        assert 200000.0 in amounts
        assert 50000.0 not in amounts

    def test_deduplication(self):
        analyzer = _make_analyzer()
        text = "Budget: $500,000. As mentioned, the $500,000 allocation..."
        results = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(results) == 1
        assert results[0][0] == 500000.0

    def test_sorted_descending(self):
        analyzer = _make_analyzer()
        text = "Items: $200,000 and $1,000,000 and $500,000."
        results = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        amounts = [r[0] for r in results]
        assert amounts == sorted(amounts, reverse=True)

    def test_empty_text(self):
        analyzer = _make_analyzer()
        results = analyzer._scan_for_budget_amounts("", min_budget=100000)
        assert results == []

    def test_no_amounts(self):
        analyzer = _make_analyzer()
        results = analyzer._scan_for_budget_amounts("No dollar amounts here.", min_budget=100000)
        assert results == []

    def test_context_captured(self):
        analyzer = _make_analyzer()
        text = "The council approved $500,000 for park renovation project."
        results = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(results) == 1
        # Context should contain surrounding text
        assert "park renovation" in results[0][1]

    def test_amount_with_cents(self):
        analyzer = _make_analyzer()
        text = "Contract for $235,224.50 awarded to vendor."
        results = analyzer._scan_for_budget_amounts(text, min_budget=100000)
        assert len(results) == 1
        assert results[0][0] == 235224.50


# ===========================================================================
# RetrospectiveAnalyzer._detect_extraction_gaps
# ===========================================================================

class TestDetectExtractionGaps:

    def test_no_gaps_when_all_extracted(self):
        analyzer = _make_analyzer()
        decisions = [
            _make_decision(budget_amount=500000.0),
            _make_decision(budget_amount=200000.0),
        ]
        scanned = [(500000.0, "context1"), (200000.0, "context2")]
        gaps = analyzer._detect_extraction_gaps(decisions, scanned)
        assert gaps == []

    def test_detects_missing_amount(self):
        analyzer = _make_analyzer()
        decisions = [_make_decision(budget_amount=500000.0)]
        scanned = [(500000.0, "context1"), (300000.0, "context2")]
        gaps = analyzer._detect_extraction_gaps(decisions, scanned)
        assert len(gaps) == 1
        assert gaps[0][0] == 300000.0

    def test_tolerance_within_10_percent(self):
        """Amounts within 10% tolerance should not be flagged as gaps."""
        analyzer = _make_analyzer()
        decisions = [_make_decision(budget_amount=500000.0)]
        # 505000 is 1% off from 500000 — within default 10% tolerance
        scanned = [(505000.0, "context")]
        gaps = analyzer._detect_extraction_gaps(decisions, scanned)
        assert gaps == []

    def test_tolerance_exceeded(self):
        """Amounts differing by more than tolerance should be flagged."""
        analyzer = _make_analyzer()
        decisions = [_make_decision(budget_amount=500000.0)]
        # 600000 is 20% off from 500000 — exceeds default 10% tolerance
        scanned = [(600000.0, "context")]
        gaps = analyzer._detect_extraction_gaps(decisions, scanned)
        assert len(gaps) == 1
        assert gaps[0][0] == 600000.0

    def test_no_extracted_budgets(self):
        analyzer = _make_analyzer()
        decisions = [_make_decision(budget_amount=None)]
        scanned = [(300000.0, "context")]
        gaps = analyzer._detect_extraction_gaps(decisions, scanned)
        assert len(gaps) == 1
        assert gaps[0][0] == 300000.0

    def test_empty_inputs(self):
        analyzer = _make_analyzer()
        gaps = analyzer._detect_extraction_gaps([], [])
        assert gaps == []


# ===========================================================================
# RetrospectiveAnalyzer._split_agenda_into_items
# ===========================================================================

class TestSplitAgendaIntoItems:

    def test_letter_dot_format(self):
        """Regex pattern: letter followed by dot and spaces (consent calendar)."""
        analyzer = _make_analyzer()
        # Format: "\na.  " — letter + dot + spaces
        text = "\na.  First consent item\nb.  Second consent item\nc.  Third consent item"
        items = analyzer._split_agenda_into_items(text)
        assert len(items) == 3
        refs = [ref for ref, _ in items]
        assert refs == ["a", "b", "c"]

    def test_section_letter_dot_format(self):
        """Regex pattern: section.letter.spaces (e.g. '5.a.  ')."""
        analyzer = _make_analyzer()
        # Format: "\n5.a.  " — section + letter + dot + spaces
        text = "\n5.a.  Approve budget amendment\n5.b.  Housing development review"
        items = analyzer._split_agenda_into_items(text)
        assert len(items) == 2
        refs = [ref for ref, _ in items]
        assert refs == ["5.a", "5.b"]

    def test_no_items_returns_whole_text(self):
        analyzer = _make_analyzer()
        text = "This is a meeting without any agenda item markers."
        items = analyzer._split_agenda_into_items(text)
        assert len(items) == 1
        assert items[0][0] == "unknown"
        assert items[0][1] == text

    def test_item_text_contains_content_between_items(self):
        analyzer = _make_analyzer()
        text = "\na.  First item content here\nMore details about first\nb.  Second item"
        items = analyzer._split_agenda_into_items(text)
        assert len(items) == 2
        # First item should contain its content up to the start of next
        assert "First item content here" in items[0][1]
        assert "More details about first" in items[0][1]

    def test_case_insensitive_item_prefix(self):
        analyzer = _make_analyzer()
        text = "\nItem a.  Discussion topic\nITEM b.  Another topic"
        items = analyzer._split_agenda_into_items(text)
        assert len(items) == 2


# ===========================================================================
# RetrospectiveAnalyzer.extract_high_stakes_decisions (orchestration)
# ===========================================================================

class TestExtractHighStakesDecisions:

    def test_text_override_skips_download(self):
        """When text_override is provided, no download should occur."""
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "item_label": "Budget Item",
                "item_number": "5.a",
                "title": "Supplemental Budget",
                "description": "Approve supplemental budget of $500K",
                "is_high_stakes": True,
                "stakes_score": 8,
                "decision_type": "budget",
                "item_type": "action",
                "outcome": "approved",
                "budget_amount": 500000,
                "budget_description": "supplemental",
                "geographic_scope": "citywide",
                "project_types": ["budget"],
                "keywords_for_matching": ["budget"],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        event = _make_event()
        results = analyzer.extract_high_stakes_decisions(event, text_override="agenda text here")

        assert len(results) == 1
        assert results[0].title == "Supplemental Budget"
        assert results[0].budget_amount == 500000
        assert results[0].stakes_score == 8
        assert results[0].passed is True  # approved → True

    def test_filters_by_min_stakes_score(self):
        """Items below min_stakes_score should be filtered out."""
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [
                {
                    "item_label": "High Stakes",
                    "title": "Major Project",
                    "description": "Big project",
                    "is_high_stakes": True,
                    "stakes_score": 8,
                    "decision_type": "budget",
                    "item_type": "action",
                    "budget_amount": 500000,
                    "budget_description": "capital",
                    "geographic_scope": "citywide",
                    "project_types": ["budget"],
                    "keywords_for_matching": ["budget"],
                },
                {
                    "item_label": "Low Stakes",
                    "title": "Minor Item",
                    "description": "Small item",
                    "is_high_stakes": True,
                    "stakes_score": 4,
                    "decision_type": "policy",
                    "item_type": "consent",
                    "budget_amount": None,
                    "budget_description": "",
                    "geographic_scope": "neighborhood",
                    "project_types": ["governance"],
                    "keywords_for_matching": [],
                },
            ]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        event = _make_event()
        results = analyzer.extract_high_stakes_decisions(
            event, text_override="text", min_stakes_score=6
        )

        assert len(results) == 1
        assert results[0].title == "Major Project"

    def test_no_agenda_url_returns_empty(self):
        """When no text_override and no agenda URL, return empty list."""
        analyzer = _make_analyzer()
        event = _make_event()  # No URLs
        results = analyzer.extract_high_stakes_decisions(event)
        assert results == []

    def test_download_failure_raises_error(self):
        """When download fails, should raise AgendaDownloadError."""
        analyzer = _make_analyzer()
        event = _make_event(agenda_url="https://example.gov/agenda.pdf")
        analyzer._download_and_extract_agenda = MagicMock(return_value=None)

        with pytest.raises(AgendaDownloadError, match="Failed to download"):
            analyzer.extract_high_stakes_decisions(event)

    def test_presentation_item_passed_is_none(self):
        """Presentation items should have passed=None."""
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "item_label": "Staff Report",
                "title": "Budget Presentation",
                "description": "Staff presented the budget",
                "is_high_stakes": True,
                "stakes_score": 7,
                "decision_type": "budget",
                "item_type": "presentation",
                "outcome": "received",
                "budget_amount": 1000000,
                "budget_description": "city budget",
                "geographic_scope": "citywide",
                "project_types": ["budget"],
                "keywords_for_matching": ["budget"],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        event = _make_event()
        results = analyzer.extract_high_stakes_decisions(event, text_override="text")
        assert len(results) == 1
        assert results[0].passed is None
        assert results[0].item_type == "presentation"
        assert results[0].extracted_outcome == "received"

    def test_denied_item_passed_is_false(self):
        """Denied action items should have passed=False."""
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "item_label": "Rezoning",
                "title": "Rezone Parcel 123",
                "description": "Rezoning request denied",
                "is_high_stakes": True,
                "stakes_score": 7,
                "decision_type": "development",
                "item_type": "hearing",
                "outcome": "denied",
                "budget_amount": None,
                "budget_description": "",
                "geographic_scope": "neighborhood",
                "project_types": ["development"],
                "keywords_for_matching": ["zoning"],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        event = _make_event()
        results = analyzer.extract_high_stakes_decisions(event, text_override="text")
        assert len(results) == 1
        assert results[0].passed is False

    def test_non_high_stakes_items_excluded(self):
        """Items with is_high_stakes=False should be excluded."""
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "item_label": "Minutes",
                "title": "Approve Minutes",
                "description": "Routine approval",
                "is_high_stakes": False,
                "stakes_score": 2,
                "decision_type": "policy",
                "item_type": "consent",
                "budget_amount": None,
                "budget_description": "",
                "geographic_scope": "citywide",
                "project_types": ["governance"],
                "keywords_for_matching": [],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        event = _make_event()
        results = analyzer.extract_high_stakes_decisions(
            event, text_override="text", min_stakes_score=1
        )
        assert results == []

    def test_gap_detection_triggers_targeted_extraction(self):
        """When budget scan finds amounts not in LLM results, targeted extraction runs."""
        analyzer = _make_analyzer()

        # First LLM call returns one item
        first_response = {
            "items": [{
                "item_label": "Road Project",
                "title": "Road Repair",
                "description": "Fix potholes",
                "is_high_stakes": True,
                "stakes_score": 7,
                "decision_type": "budget",
                "item_type": "action",
                "outcome": "approved",
                "budget_amount": 500000,
                "budget_description": "road repair",
                "geographic_scope": "citywide",
                "project_types": ["transportation"],
                "keywords_for_matching": ["road"],
            }]
        }
        # Targeted extraction returns additional item
        second_response = {
            "items": [{
                "item_label": "Park Budget",
                "title": "Park Renovation",
                "description": "Renovate park",
                "is_high_stakes": True,
                "stakes_score": 7,
                "decision_type": "budget",
                "item_type": "consent",
                "outcome": "approved",
                "budget_amount": 300000,
                "budget_description": "park renovation",
                "geographic_scope": "neighborhood",
                "project_types": ["environment"],
                "keywords_for_matching": ["park"],
            }]
        }

        call_count = [0]
        def mock_call_llm(prompt, max_tokens=1500):
            call_count[0] += 1
            if call_count[0] == 1:
                return json.dumps(first_response)
            return json.dumps(second_response)

        parse_count = [0]
        def mock_safe_parse(text):
            parse_count[0] += 1
            if parse_count[0] == 1:
                return first_response
            return second_response

        analyzer._call_llm = mock_call_llm
        analyzer._safe_json_parse = mock_safe_parse

        # Text has both $500K and $300K
        text = "Road repair project $500,000 approved. Park renovation $300,000 approved."
        event = _make_event()
        results = analyzer.extract_high_stakes_decisions(event, text_override=text)

        assert len(results) == 2
        titles = [r.title for r in results]
        assert "Road Repair" in titles
        assert "Park Renovation" in titles


# ===========================================================================
# RetrospectiveAnalyzer.analyze_meeting_batch
# ===========================================================================

class TestAnalyzeMeetingBatch:

    def test_aggregates_decisions_across_meetings(self):
        analyzer = _make_analyzer()

        def mock_extract(event, min_budget=100000, min_stakes_score=6):
            title = event.get("title", "")
            if "Council" in title:
                return [
                    _make_decision(
                        decision_type="budget",
                        meeting_type="city_council",
                        budget_amount=500000.0,
                    )
                ]
            elif "Planning" in title:
                return [
                    _make_decision(
                        decision_type="development",
                        meeting_type="planning_commission",
                        budget_amount=200000.0,
                    )
                ]
            return []

        analyzer.extract_high_stakes_decisions = mock_extract

        events = [
            _make_event(title="City Council Meeting"),
            _make_event(title="Planning Commission"),
            _make_event(title="Study Session"),
        ]
        result = analyzer.analyze_meeting_batch(events)

        assert result["meetings_analyzed"] == 3
        assert result["decision_count"] == 2
        assert result["total_budget_amount"] == 700000.0
        assert result["decision_types_breakdown"]["budget"] == 1
        assert result["decision_types_breakdown"]["development"] == 1
        assert result["by_meeting_type"]["city_council"] == 1
        assert result["by_meeting_type"]["planning_commission"] == 1

    def test_empty_events_list(self):
        analyzer = _make_analyzer()
        result = analyzer.analyze_meeting_batch([])
        assert result["meetings_analyzed"] == 0
        assert result["decision_count"] == 0
        assert result["total_budget_amount"] == 0.0
        assert result["high_stakes_decisions"] == []

    def test_no_decisions_found(self):
        analyzer = _make_analyzer()
        analyzer.extract_high_stakes_decisions = MagicMock(return_value=[])

        events = [_make_event(title="Routine Meeting")]
        result = analyzer.analyze_meeting_batch(events)

        assert result["meetings_analyzed"] == 1
        assert result["decision_count"] == 0
        assert result["total_budget_amount"] == 0.0

    def test_none_budget_amounts_not_summed(self):
        """Decisions with None budget should not affect total."""
        analyzer = _make_analyzer()

        analyzer.extract_high_stakes_decisions = MagicMock(return_value=[
            _make_decision(budget_amount=500000.0),
            _make_decision(budget_amount=None),
        ])

        events = [_make_event()]
        result = analyzer.analyze_meeting_batch(events)

        assert result["total_budget_amount"] == 500000.0
        assert result["decision_count"] == 2

    def test_result_contains_timestamp(self):
        analyzer = _make_analyzer()
        analyzer.extract_high_stakes_decisions = MagicMock(return_value=[])

        result = analyzer.analyze_meeting_batch([_make_event()])
        assert "extraction_timestamp" in result
        # Timestamp should be a valid ISO format string
        assert "T" in result["extraction_timestamp"]

    def test_decisions_serialized_as_dicts(self):
        analyzer = _make_analyzer()
        decision = _make_decision(title="Test Decision", budget_amount=100000.0)
        analyzer.extract_high_stakes_decisions = MagicMock(return_value=[decision])

        result = analyzer.analyze_meeting_batch([_make_event()])
        assert len(result["high_stakes_decisions"]) == 1
        # Should be dict (from to_dict()), not HighStakesDecision object
        assert isinstance(result["high_stakes_decisions"][0], dict)
        assert result["high_stakes_decisions"][0]["title"] == "Test Decision"
        assert result["high_stakes_decisions"][0]["financial_impact_cents"] == 10000000


# ===========================================================================
# RetrospectiveAnalyzer._resolve_minutes_url
# ===========================================================================

class TestResolveMinutesUrl:

    def test_non_minutes_viewer_url_returned_unchanged(self):
        analyzer = _make_analyzer()
        url = "https://example.gov/agenda.pdf"
        assert analyzer._resolve_minutes_url(url) == url

    def test_minutes_viewer_follows_redirect_to_pdf(self):
        analyzer = _make_analyzer()
        url = "https://example.gov/MinutesViewer.php?id=123"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.content = b"%PDF-1.4"
        analyzer.session = MagicMock()
        analyzer.session.get.return_value = mock_response

        result = analyzer._resolve_minutes_url(url)
        assert result == url  # Landed on PDF at same URL

    def test_minutes_viewer_follows_redirect_with_embedded_url(self):
        analyzer = _make_analyzer()
        url = "https://example.gov/MinutesViewer.php?id=123"
        redirect_url = "https://docs.google.com/gview?url=https://storage.example.com/minutes.pdf"

        mock_redirect = MagicMock()
        mock_redirect.status_code = 302
        mock_redirect.headers = {"location": redirect_url}
        analyzer.session = MagicMock()
        analyzer.session.get.return_value = mock_redirect

        result = analyzer._resolve_minutes_url(url)
        assert result == "https://storage.example.com/minutes.pdf"

    def test_minutes_viewer_exception_returns_original(self):
        """If redirect resolution fails, return original URL."""
        analyzer = _make_analyzer()
        url = "https://example.gov/MinutesViewer.php?id=123"
        analyzer.session = MagicMock()
        analyzer.session.get.side_effect = Exception("connection error")

        result = analyzer._resolve_minutes_url(url)
        assert result == url


# ===========================================================================
# Passed-value logic edge cases
# ===========================================================================

class TestPassedValueLogic:

    def test_approved_action_is_true(self):
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "item_label": "Test",
                "title": "Test",
                "description": "Test",
                "is_high_stakes": True,
                "stakes_score": 8,
                "decision_type": "budget",
                "item_type": "action",
                "outcome": "approved",
                "budget_amount": 100000,
                "budget_description": "test",
                "geographic_scope": "citywide",
                "project_types": ["budget"],
                "keywords_for_matching": [],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        results = analyzer.extract_high_stakes_decisions(_make_event(), text_override="t")
        assert results[0].passed is True

    def test_adopted_hearing_is_true(self):
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "item_label": "Test",
                "title": "Test",
                "description": "Test",
                "is_high_stakes": True,
                "stakes_score": 8,
                "decision_type": "policy",
                "item_type": "hearing",
                "outcome": "adopted",
                "budget_amount": None,
                "budget_description": "",
                "geographic_scope": "citywide",
                "project_types": ["governance"],
                "keywords_for_matching": [],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        results = analyzer.extract_high_stakes_decisions(_make_event(), text_override="t")
        assert results[0].passed is True

    def test_continued_action_is_false(self):
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "item_label": "Test",
                "title": "Test",
                "description": "Test",
                "is_high_stakes": True,
                "stakes_score": 8,
                "decision_type": "policy",
                "item_type": "action",
                "outcome": "continued",
                "budget_amount": None,
                "budget_description": "",
                "geographic_scope": "citywide",
                "project_types": ["governance"],
                "keywords_for_matching": [],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        results = analyzer.extract_high_stakes_decisions(_make_event(), text_override="t")
        assert results[0].passed is False

    def test_no_outcome_passed_is_none(self):
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "item_label": "Test",
                "title": "Test",
                "description": "Test",
                "is_high_stakes": True,
                "stakes_score": 8,
                "decision_type": "policy",
                "item_type": "action",
                "budget_amount": None,
                "budget_description": "",
                "geographic_scope": "citywide",
                "project_types": ["governance"],
                "keywords_for_matching": [],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        results = analyzer.extract_high_stakes_decisions(_make_event(), text_override="t")
        assert results[0].passed is None

    def test_discussion_type_passed_is_none_regardless_of_outcome(self):
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "item_label": "Test",
                "title": "Test",
                "description": "Test",
                "is_high_stakes": True,
                "stakes_score": 8,
                "decision_type": "policy",
                "item_type": "discussion",
                "outcome": "approved",
                "budget_amount": None,
                "budget_description": "",
                "geographic_scope": "citywide",
                "project_types": ["governance"],
                "keywords_for_matching": [],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        results = analyzer.extract_high_stakes_decisions(_make_event(), text_override="t")
        assert results[0].passed is None


# ===========================================================================
# Item ref resolution
# ===========================================================================

class TestItemRefResolution:

    def test_item_label_preferred_over_item_number(self):
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "item_label": "Housing Ordinance",
                "item_number": "5.a",
                "title": "Test",
                "description": "Test",
                "is_high_stakes": True,
                "stakes_score": 8,
                "decision_type": "development",
                "item_type": "action",
                "budget_amount": None,
                "budget_description": "",
                "geographic_scope": "citywide",
                "project_types": ["housing"],
                "keywords_for_matching": [],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        results = analyzer.extract_high_stakes_decisions(_make_event(), text_override="t")
        assert results[0].item_ref == "Housing Ordinance"
        assert results[0].item_number == "5.a"

    def test_item_number_used_when_no_label(self):
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "item_number": "7",
                "title": "Test",
                "description": "Test",
                "is_high_stakes": True,
                "stakes_score": 8,
                "decision_type": "policy",
                "item_type": "action",
                "budget_amount": None,
                "budget_description": "",
                "geographic_scope": "citywide",
                "project_types": ["governance"],
                "keywords_for_matching": [],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        results = analyzer.extract_high_stakes_decisions(_make_event(), text_override="t")
        assert results[0].item_ref == "7"

    def test_fallback_to_unknown(self):
        analyzer = _make_analyzer()
        llm_response = json.dumps({
            "items": [{
                "title": "Test",
                "description": "Test",
                "is_high_stakes": True,
                "stakes_score": 8,
                "decision_type": "policy",
                "item_type": "action",
                "budget_amount": None,
                "budget_description": "",
                "geographic_scope": "citywide",
                "project_types": ["governance"],
                "keywords_for_matching": [],
            }]
        })
        analyzer._call_llm = MagicMock(return_value=llm_response)
        analyzer._safe_json_parse = MagicMock(return_value=json.loads(llm_response))

        results = analyzer.extract_high_stakes_decisions(_make_event(), text_override="t")
        assert results[0].item_ref == "unknown"


# ===========================================================================
# LLM failure handling
# ===========================================================================

class TestLlmFailureHandling:

    def test_auth_error_propagated(self):
        """Authentication errors should NOT be swallowed."""
        analyzer = _make_analyzer()

        class AuthenticationError(Exception):
            pass

        analyzer._call_llm = MagicMock(side_effect=AuthenticationError("bad key"))

        event = _make_event()
        with pytest.raises(AuthenticationError, match="bad key"):
            analyzer.extract_high_stakes_decisions(event, text_override="text")

    def test_generic_llm_error_returns_empty(self):
        """Non-auth LLM errors should return empty list, not crash."""
        analyzer = _make_analyzer()
        analyzer._call_llm = MagicMock(side_effect=ValueError("model overloaded"))

        event = _make_event()
        results = analyzer.extract_high_stakes_decisions(event, text_override="text")
        assert results == []

    def test_malformed_json_returns_empty(self):
        """Invalid JSON from LLM should return empty list."""
        analyzer = _make_analyzer()
        analyzer._call_llm = MagicMock(return_value="not json at all")
        analyzer._safe_json_parse = MagicMock(return_value=None)

        event = _make_event()
        results = analyzer.extract_high_stakes_decisions(event, text_override="text")
        assert results == []

    def test_empty_items_array_returns_empty(self):
        analyzer = _make_analyzer()
        analyzer._call_llm = MagicMock(return_value='{"items": []}')
        analyzer._safe_json_parse = MagicMock(return_value={"items": []})

        event = _make_event()
        results = analyzer.extract_high_stakes_decisions(event, text_override="text")
        assert results == []
