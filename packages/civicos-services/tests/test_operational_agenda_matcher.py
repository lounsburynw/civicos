"""
Tests for operational_agenda_matcher.py — keyword and LLM-based matching
between operational SeeClickFix complaints and municipal agenda items.

Pure logic (keyword scoring) tested with real inputs and specific expected
outputs.  LLM path tested by mocking the external provider, asserting on
return values produced by the matcher's own logic.

To run:
    pytest packages/civicos-services/tests/test_operational_agenda_matcher.py -q --override-ini="addopts="
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.processing.operational_agenda_matcher import (
    OperationalAgendaMatcher,
)


# ---------------------------------------------------------------------------
# Helpers — reusable issue/agenda factories
# ---------------------------------------------------------------------------

def _issue(title="", description="", category="", issue_id="scf-1"):
    return {
        "id": issue_id,
        "title": title,
        "description": description,
        "category": category,
    }


def _agenda(title="", description="", project_type="", agenda_id="ag-1"):
    return {
        "id": agenda_id,
        "title": title,
        "description": description,
        "project_type": project_type,
    }


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestInit:
    def test_keyword_only_mode_disables_llm(self):
        m = OperationalAgendaMatcher(use_llm=False)
        assert m.use_llm is False

    def test_llm_mode_sets_flag_true(self):
        """When LLM import fails, llm_available becomes False but use_llm stays True."""
        m = OperationalAgendaMatcher(use_llm=True)
        assert m.use_llm is True
        # LLM provider may or may not be available depending on env,
        # but the flag should reflect what was requested.


# ---------------------------------------------------------------------------
# _extract_issue_text
# ---------------------------------------------------------------------------

class TestExtractIssueText:
    def setup_method(self):
        self.m = OperationalAgendaMatcher(use_llm=False)

    def test_combines_title_description_category(self):
        issue = _issue(title="Pothole", description="On Main St", category="Roads")
        result = self.m._extract_issue_text(issue)
        assert result == "pothole on main st roads"

    def test_missing_fields_skipped_without_extra_spaces(self):
        issue = _issue(title="Pothole", description="", category="")
        result = self.m._extract_issue_text(issue)
        assert result == "pothole"

    def test_all_empty_returns_empty_string(self):
        result = self.m._extract_issue_text({})
        assert result == ""

    def test_output_is_lowercased(self):
        issue = _issue(title="POTHOLE", description="MAIN ST", category="ROADS")
        result = self.m._extract_issue_text(issue)
        assert result == "pothole main st roads"


# ---------------------------------------------------------------------------
# _extract_agenda_text
# ---------------------------------------------------------------------------

class TestExtractAgendaText:
    def setup_method(self):
        self.m = OperationalAgendaMatcher(use_llm=False)

    def test_combines_title_description_project_type(self):
        agenda = _agenda(title="Street Budget", description="Annual repair", project_type="transportation")
        result = self.m._extract_agenda_text(agenda)
        assert result == "street budget annual repair transportation"

    def test_missing_fields_skipped(self):
        agenda = _agenda(title="Budget")
        result = self.m._extract_agenda_text(agenda)
        assert result == "budget"

    def test_all_empty_returns_empty_string(self):
        result = self.m._extract_agenda_text({})
        assert result == ""


# ---------------------------------------------------------------------------
# _keyword_match_confidence — the core scoring engine
# ---------------------------------------------------------------------------

class TestKeywordMatchConfidence:
    def setup_method(self):
        self.m = OperationalAgendaMatcher(use_llm=False)

    def test_no_category_match_returns_zero(self):
        # "wifi" is not a recognized category
        score = self.m._keyword_match_confidence("wifi problem", "wifi", "network upgrade", "")
        assert score == 0.0

    def test_category_match_but_no_keyword_hits_returns_zero(self):
        # "pothole" category recognized, but agenda has no related keywords
        score = self.m._keyword_match_confidence("pothole on elm", "pothole", "zoning variance hearing", "")
        assert score == 0.0

    def test_single_keyword_hit_scores_20(self):
        # "pothole" category → keywords include "road"; agenda has "road"
        score = self.m._keyword_match_confidence("pothole on elm", "pothole", "road closure notice", "")
        assert score == 20.0

    def test_two_keyword_hits_score_40(self):
        # "pothole" → keywords include "road" and "repair"
        score = self.m._keyword_match_confidence("pothole on elm", "pothole", "road repair schedule", "")
        assert score == 40.0

    def test_three_keyword_hits_cap_at_60(self):
        # "pothole" → "road", "repair", "maintenance"
        score = self.m._keyword_match_confidence(
            "pothole on elm", "pothole",
            "road repair and maintenance plan", ""
        )
        assert score == 60.0

    def test_four_keyword_hits_still_cap_at_60_base(self):
        # More than 3 keyword hits shouldn't exceed the 60-point cap for base
        score = self.m._keyword_match_confidence(
            "pothole on elm", "pothole",
            "road repair maintenance infrastructure plan", ""
        )
        # 60 (capped base) — no category-in-agenda bonus, no type bonus
        assert score == 60.0

    def test_direct_category_in_agenda_adds_20_bonus(self):
        # "pothole" in agenda text triggers +20 bonus
        score = self.m._keyword_match_confidence(
            "pothole on elm", "pothole",
            "pothole repair program", ""
        )
        # 1 hit ("repair") = 20 base + 20 (category bonus) = 40
        assert score == 40.0

    def test_transportation_agenda_type_adds_10_bonus(self):
        score = self.m._keyword_match_confidence(
            "pothole on elm", "pothole",
            "road closure", "transportation"
        )
        # 1 hit ("road") = 20 base + 10 (type bonus) = 30
        assert score == 30.0

    def test_infrastructure_agenda_type_adds_10_bonus(self):
        score = self.m._keyword_match_confidence(
            "pothole on elm", "pothole",
            "road closure", "infrastructure"
        )
        assert score == 30.0

    def test_housing_agenda_type_adds_10_bonus(self):
        score = self.m._keyword_match_confidence(
            "sidewalk crack", "sidewalk",
            "pedestrian pathway improvements", "housing"
        )
        # "pedestrian" + "path" (substring of "pathway") = 40 base + 10 (housing type) = 50
        assert score == 50.0

    def test_environment_agenda_type_adds_10_bonus(self):
        score = self.m._keyword_match_confidence(
            "tree down", "tree",
            "urban forestry management", "environment"
        )
        # "urban" + "forestry" = 40 base + 10 (type) = 50
        assert score == 50.0

    def test_unrecognized_agenda_type_no_bonus(self):
        score = self.m._keyword_match_confidence(
            "pothole on elm", "pothole",
            "road closure", "zoning"
        )
        # 1 hit = 20, no type bonus
        assert score == 20.0

    def test_all_bonuses_combined_capped_at_100(self):
        # Max possible: 60 (3+ hits) + 20 (category in text) + 10 (type) = 90
        score = self.m._keyword_match_confidence(
            "pothole on elm", "pothole",
            "pothole road repair maintenance budget", "transportation"
        )
        assert score == 90.0

    def test_stormwater_category_matches(self):
        score = self.m._keyword_match_confidence(
            "stormwater flooding", "stormwater",
            "flood prevention and drainage infrastructure", ""
        )
        # "drainage" + "flood" + "infrastructure" = 60 base
        assert score == 60.0

    def test_traffic_category_matches(self):
        score = self.m._keyword_match_confidence(
            "traffic speeding cars", "traffic",
            "pedestrian safety and speed calming", ""
        )
        # "speed" + "calming" + "safety" + "pedestrian" = 60 (capped)
        assert score == 60.0

    def test_category_matched_from_issue_text_not_just_category_field(self):
        # "pothole" is in issue_text even though issue_category is empty
        score = self.m._keyword_match_confidence(
            "pothole on elm street", "",
            "road repair", ""
        )
        # category "pothole" found in issue_text → "road" + "repair" = 40
        assert score == 40.0

    def test_graffiti_category(self):
        score = self.m._keyword_match_confidence(
            "graffiti on wall", "graffiti",
            "blight cleanup and beautification", ""
        )
        # "blight" + "cleanup" + "beautification" = 60
        assert score == 60.0

    def test_lighting_category(self):
        # Avoid "street" in issue_text — "tree" is a substring of "street"
        # and would match the "tree" category first (dict iteration order).
        score = self.m._keyword_match_confidence(
            "broken lighting fixture", "lighting",
            "crime prevention safety visibility", ""
        )
        # lighting keywords: 'street light', 'safety', 'visibility', 'crime prevention'
        # "safety" + "visibility" + "crime prevention" = 60 (3 hits capped)
        assert score == 60.0


# ---------------------------------------------------------------------------
# _match_single_pair — keyword-only path
# ---------------------------------------------------------------------------

class TestMatchSinglePairKeywordOnly:
    def setup_method(self):
        self.m = OperationalAgendaMatcher(use_llm=False)

    def test_returns_none_when_keyword_confidence_below_10(self):
        issue = _issue(title="WiFi outage", category="Connectivity")
        agenda = _agenda(title="Zoning Variance")
        result = self.m._match_single_pair(issue, agenda)
        assert result is None

    def test_returns_none_when_keyword_confidence_between_10_and_20(self):
        """Keyword match >= 10 but < 20 → not returned as match."""
        # Need a scenario where confidence is exactly 10-19.
        # That's impossible with current scoring (minimum non-zero is 20).
        # So any non-zero keyword match that passes the <10 gate will be >= 20.
        # Test that scores of exactly 20 produce a match.
        issue = _issue(title="Pothole", category="pothole")
        agenda = _agenda(title="Road work ahead")  # "road" → 20 points
        result = self.m._match_single_pair(issue, agenda)
        assert result is not None
        assert result["confidence"] == 20.0
        assert result["connection_type"] == "thematic"

    def test_returns_match_dict_with_expected_fields(self):
        issue = _issue(title="Pothole", category="pothole")
        agenda = _agenda(title="Road repair budget", project_type="transportation")
        result = self.m._match_single_pair(issue, agenda)
        assert result["agenda_item"] is agenda
        # agenda_text = "road repair budget transportation"
        # pothole keywords: road + repair + transportation = 60 base + 10 type bonus = 70
        assert result["confidence"] == 70.0
        assert result["connection_type"] == "thematic"
        assert "keyword" in result["reasoning"].lower()

    def test_high_confidence_match(self):
        issue = _issue(title="Pothole on Main St", category="pothole", description="Large pothole needs repair")
        agenda = _agenda(
            title="Street Repair and Maintenance Budget",
            description="Annual pothole repair and road maintenance allocation",
            project_type="transportation",
        )
        result = self.m._match_single_pair(issue, agenda)
        # "street" + "repair" + "road" + "maintenance" → 60 cap
        # + "pothole" in agenda text → +20 bonus
        # + transportation type → +10 bonus
        # = 90
        assert result["confidence"] == 90.0


# ---------------------------------------------------------------------------
# match_issue_to_agendas — filtering and sorting
# ---------------------------------------------------------------------------

class TestMatchIssueToAgendas:
    def setup_method(self):
        self.m = OperationalAgendaMatcher(use_llm=False)

    def test_empty_agenda_list_returns_empty(self):
        issue = _issue(title="Pothole", category="pothole")
        result = self.m.match_issue_to_agendas(issue, [])
        assert result == []

    def test_no_matching_agendas_returns_empty(self):
        issue = _issue(title="WiFi problem", category="connectivity")
        agendas = [_agenda(title="Zoning hearing"), _agenda(title="Personnel matters")]
        result = self.m.match_issue_to_agendas(issue, agendas)
        assert result == []

    def test_results_sorted_by_confidence_descending(self):
        issue = _issue(title="Pothole on road", category="pothole")
        agendas = [
            _agenda(title="Road closure", agenda_id="low"),  # road → 20
            _agenda(title="Road repair and maintenance pothole fix", project_type="transportation", agenda_id="high"),
        ]
        result = self.m.match_issue_to_agendas(issue, agendas, min_confidence=15)
        assert len(result) == 2
        assert result[0]["confidence"] > result[1]["confidence"]
        assert result[0]["agenda_item"]["id"] == "high"
        assert result[1]["agenda_item"]["id"] == "low"

    def test_min_confidence_filters_low_matches(self):
        issue = _issue(title="Pothole on road", category="pothole")
        agendas = [
            _agenda(title="Road closure", agenda_id="low"),  # road → 20
            _agenda(title="Road repair maintenance budget", project_type="transportation", agenda_id="high"),
        ]
        result = self.m.match_issue_to_agendas(issue, agendas, min_confidence=50)
        # Only "high" should survive (road+repair+maintenance = 60 + 10 type = 70)
        assert len(result) == 1
        assert result[0]["agenda_item"]["id"] == "high"

    def test_default_min_confidence_is_20(self):
        issue = _issue(title="Pothole", category="pothole")
        agendas = [_agenda(title="Road work")]  # road → 20
        result = self.m.match_issue_to_agendas(issue, agendas)
        assert len(result) == 1
        assert result[0]["confidence"] == 20.0


# ---------------------------------------------------------------------------
# match_issues_batch
# ---------------------------------------------------------------------------

class TestMatchIssuesBatch:
    def setup_method(self):
        self.m = OperationalAgendaMatcher(use_llm=False)

    def test_empty_issues_returns_empty_dict(self):
        result = self.m.match_issues_batch([], [_agenda(title="Road repair")])
        assert result == {}

    def test_empty_agendas_returns_empty_dict(self):
        issues = [_issue(title="Pothole", category="pothole", issue_id="scf-1")]
        result = self.m.match_issues_batch(issues, [])
        assert result == {}

    def test_matched_issues_keyed_by_id(self):
        issues = [
            _issue(title="Pothole", category="pothole", issue_id="scf-1"),
            _issue(title="Graffiti", category="graffiti", issue_id="scf-2"),
        ]
        agendas = [
            _agenda(title="Road repair budget"),
            _agenda(title="Blight cleanup program"),
        ]
        result = self.m.match_issues_batch(issues, agendas)
        assert "scf-1" in result
        assert "scf-2" in result
        # pothole → "road" + "repair" = 40; graffiti → "blight" + "cleanup" = 40
        assert result["scf-1"][0]["confidence"] == 40.0
        assert result["scf-2"][0]["confidence"] == 40.0

    def test_unmatched_issues_excluded_from_results(self):
        issues = [
            _issue(title="Pothole", category="pothole", issue_id="scf-1"),
            _issue(title="WiFi problem", category="connectivity", issue_id="scf-2"),
        ]
        agendas = [_agenda(title="Road repair budget")]
        result = self.m.match_issues_batch(issues, agendas)
        assert "scf-1" in result
        assert "scf-2" not in result

    def test_min_confidence_passed_through(self):
        issues = [_issue(title="Pothole", category="pothole", issue_id="scf-1")]
        agendas = [_agenda(title="Road work")]  # road → 20
        result = self.m.match_issues_batch(issues, agendas, min_confidence=50)
        assert result == {}  # 20 < 50 → excluded


# ---------------------------------------------------------------------------
# get_match_statistics
# ---------------------------------------------------------------------------

class TestGetMatchStatistics:
    def setup_method(self):
        self.m = OperationalAgendaMatcher(use_llm=False)

    def test_empty_issues_returns_zero_stats(self):
        stats = self.m.get_match_statistics([], [])
        assert stats["total_issues"] == 0
        assert stats["total_agenda_items"] == 0
        assert stats["matched_issues"] == 0
        assert stats["match_rate"] == 0
        assert stats["avg_confidence"] == 0
        assert stats["by_category"] == {}

    def test_no_matches_returns_zero_rate(self):
        issues = [_issue(title="WiFi", category="connectivity", issue_id="scf-1")]
        agendas = [_agenda(title="Zoning hearing")]
        stats = self.m.get_match_statistics(issues, agendas)
        assert stats["total_issues"] == 1
        assert stats["total_agenda_items"] == 1
        assert stats["matched_issues"] == 0
        assert stats["match_rate"] == 0
        assert stats["avg_confidence"] == 0

    def test_all_issues_matched(self):
        issues = [
            _issue(title="Pothole", category="pothole", issue_id="scf-1"),
            _issue(title="Graffiti", category="graffiti", issue_id="scf-2"),
        ]
        agendas = [
            _agenda(title="Road repair budget"),
            _agenda(title="Blight cleanup program"),
        ]
        stats = self.m.get_match_statistics(issues, agendas)
        assert stats["total_issues"] == 2
        assert stats["total_agenda_items"] == 2
        assert stats["matched_issues"] == 2
        assert stats["match_rate"] == 1.0

    def test_partial_match_rate(self):
        issues = [
            _issue(title="Pothole", category="pothole", issue_id="scf-1"),
            _issue(title="WiFi", category="connectivity", issue_id="scf-2"),
        ]
        agendas = [_agenda(title="Road repair budget")]
        stats = self.m.get_match_statistics(issues, agendas)
        assert stats["total_issues"] == 2
        assert stats["matched_issues"] == 1
        assert stats["match_rate"] == 0.5

    def test_avg_confidence_uses_top_match_per_issue(self):
        issues = [_issue(title="Pothole", category="pothole", issue_id="scf-1")]
        agendas = [
            _agenda(title="Road repair budget"),  # road(20)+repair(20) = 40
            _agenda(title="Road work"),  # road → 20
        ]
        stats = self.m.get_match_statistics(issues, agendas)
        # Top match for scf-1 is 40 (road repair)
        assert stats["avg_confidence"] == 40.0

    def test_by_category_counts_total_and_matched(self):
        issues = [
            _issue(title="Pothole", category="Roads", issue_id="scf-1"),
            _issue(title="Another pothole", category="Roads", issue_id="scf-2"),
            _issue(title="WiFi", category="Tech", issue_id="scf-3"),
        ]
        # Only pothole issues have "pothole" in text for keyword matching, but
        # category is "Roads" (not a recognized keyword category).
        # Let's use recognizable categories:
        issues = [
            _issue(title="Pothole on elm", category="pothole", issue_id="scf-1"),
            _issue(title="Pothole on oak", category="pothole", issue_id="scf-2"),
            _issue(title="WiFi", category="Tech", issue_id="scf-3"),
        ]
        agendas = [_agenda(title="Road repair budget")]
        stats = self.m.get_match_statistics(issues, agendas)

        assert stats["by_category"]["pothole"]["total"] == 2
        assert stats["by_category"]["pothole"]["matched"] == 2
        assert stats["by_category"]["Tech"]["total"] == 1
        assert stats["by_category"]["Tech"]["matched"] == 0

    def test_avg_confidence_rounded_to_one_decimal(self):
        issues = [
            _issue(title="Pothole", category="pothole", issue_id="scf-1"),
            _issue(title="Graffiti", category="graffiti", issue_id="scf-2"),
        ]
        agendas = [
            _agenda(title="Road repair maintenance budget", project_type="transportation"),
            _agenda(title="Blight cleanup"),
        ]
        stats = self.m.get_match_statistics(issues, agendas)
        # scf-1 top match: road+repair+maintenance = 60 + 10 type = 70
        # scf-2 top match: blight+cleanup = 40
        # avg = (70 + 40) / 2 = 55.0
        assert stats["avg_confidence"] == 55.0
        # Verify it's a float with at most one decimal
        assert stats["avg_confidence"] == round(stats["avg_confidence"], 1)


# ---------------------------------------------------------------------------
# LLM semantic matching path
# ---------------------------------------------------------------------------

class TestLLMSemanticMatch:
    def test_llm_result_used_when_related_true(self):
        m = OperationalAgendaMatcher(use_llm=False)
        m.use_llm = True
        m.llm_available = True

        mock_provider = MagicMock()
        mock_provider.generate.return_value = json.dumps({
            "related": True,
            "confidence": 85,
            "reasoning": "Both concern road infrastructure",
            "connection_type": "direct",
        })
        m.llm_provider = MagicMock(return_value=mock_provider)

        issue = _issue(title="Pothole", category="pothole")
        agenda = _agenda(title="Road repair", description="street maintenance")

        result = m._llm_semantic_match(issue, agenda, keyword_confidence=30.0)
        assert result is not None
        assert result["confidence"] == 85
        assert result["reasoning"] == "Both concern road infrastructure"
        assert result["connection_type"] == "direct"
        assert result["agenda_item"] is agenda

    def test_llm_result_none_when_not_related(self):
        m = OperationalAgendaMatcher(use_llm=False)
        m.use_llm = True
        m.llm_available = True

        mock_provider = MagicMock()
        mock_provider.generate.return_value = json.dumps({
            "related": False,
            "confidence": 5,
            "reasoning": "Unrelated topics",
            "connection_type": "thematic",
        })
        m.llm_provider = MagicMock(return_value=mock_provider)

        result = m._llm_semantic_match(
            _issue(title="WiFi"), _agenda(title="Zoning"), keyword_confidence=15.0
        )
        assert result is None

    def test_llm_confidence_capped_at_100(self):
        m = OperationalAgendaMatcher(use_llm=False)
        m.use_llm = True
        m.llm_available = True

        mock_provider = MagicMock()
        mock_provider.generate.return_value = json.dumps({
            "related": True,
            "confidence": 150,  # Overshoot
            "reasoning": "Strongly related",
            "connection_type": "direct",
        })
        m.llm_provider = MagicMock(return_value=mock_provider)

        result = m._llm_semantic_match(
            _issue(title="Pothole"), _agenda(title="Road"), keyword_confidence=30.0
        )
        assert result["confidence"] == 100

    def test_llm_exception_returns_none_gracefully(self):
        m = OperationalAgendaMatcher(use_llm=False)
        m.use_llm = True
        m.llm_available = True

        mock_provider = MagicMock()
        mock_provider.generate.side_effect = RuntimeError("API down")
        m.llm_provider = MagicMock(return_value=mock_provider)

        result = m._llm_semantic_match(
            _issue(title="Pothole"), _agenda(title="Road"), keyword_confidence=30.0
        )
        assert result is None

    def test_llm_invalid_json_returns_none(self):
        m = OperationalAgendaMatcher(use_llm=False)
        m.use_llm = True
        m.llm_available = True

        mock_provider = MagicMock()
        mock_provider.generate.return_value = "not valid json at all"
        m.llm_provider = MagicMock(return_value=mock_provider)

        result = m._llm_semantic_match(
            _issue(title="Pothole"), _agenda(title="Road"), keyword_confidence=30.0
        )
        assert result is None

    def test_llm_not_available_returns_none(self):
        m = OperationalAgendaMatcher(use_llm=False)
        m.llm_available = False
        result = m._llm_semantic_match(
            _issue(title="Pothole"), _agenda(title="Road"), keyword_confidence=30.0
        )
        assert result is None

    def test_llm_missing_fields_use_defaults(self):
        m = OperationalAgendaMatcher(use_llm=False)
        m.use_llm = True
        m.llm_available = True

        mock_provider = MagicMock()
        mock_provider.generate.return_value = json.dumps({
            "related": True,
            # No confidence, reasoning, or connection_type
        })
        m.llm_provider = MagicMock(return_value=mock_provider)

        result = m._llm_semantic_match(
            _issue(title="Pothole"), _agenda(title="Road"), keyword_confidence=30.0
        )
        assert result is not None
        assert result["confidence"] == 30.0  # Falls back to keyword_confidence
        assert result["reasoning"] == "LLM detected semantic relationship"
        assert result["connection_type"] == "thematic"


# ---------------------------------------------------------------------------
# Integration: _match_single_pair with LLM enabled
# ---------------------------------------------------------------------------

class TestMatchSinglePairWithLLM:
    def test_llm_result_preferred_over_keyword_when_available(self):
        m = OperationalAgendaMatcher(use_llm=False)
        m.use_llm = True
        m.llm_available = True

        mock_provider = MagicMock()
        mock_provider.generate.return_value = json.dumps({
            "related": True,
            "confidence": 92,
            "reasoning": "Direct infrastructure connection",
            "connection_type": "direct",
        })
        m.llm_provider = MagicMock(return_value=mock_provider)

        issue = _issue(title="Pothole on elm", category="pothole")
        agenda = _agenda(title="Road repair budget")

        result = m._match_single_pair(issue, agenda)
        assert result["confidence"] == 92
        assert result["connection_type"] == "direct"

    def test_keyword_fallback_when_llm_fails(self):
        m = OperationalAgendaMatcher(use_llm=False)
        m.use_llm = True
        m.llm_available = True

        mock_provider = MagicMock()
        mock_provider.generate.side_effect = RuntimeError("API timeout")
        m.llm_provider = MagicMock(return_value=mock_provider)

        issue = _issue(title="Pothole on elm", category="pothole")
        agenda = _agenda(title="Road repair budget")

        result = m._match_single_pair(issue, agenda)
        # Falls back to keyword: road(20) + repair(20) = 40
        assert result["confidence"] == 40.0
        assert result["connection_type"] == "thematic"

    def test_skips_llm_when_keyword_confidence_below_10(self):
        m = OperationalAgendaMatcher(use_llm=False)
        m.use_llm = True
        m.llm_available = True
        m.llm_provider = MagicMock()

        issue = _issue(title="WiFi issue", category="connectivity")
        agenda = _agenda(title="Zoning variance")

        result = m._match_single_pair(issue, agenda)
        assert result is None
        # LLM should NOT have been called
        m.llm_provider.assert_not_called()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def setup_method(self):
        self.m = OperationalAgendaMatcher(use_llm=False)

    def test_issue_with_none_category_raises(self):
        """Source code calls .lower() on category — None crashes."""
        issue = {"id": "scf-1", "title": "Test", "description": "desc", "category": None}
        agenda = _agenda(title="Road repair")
        with pytest.raises(AttributeError):
            self.m.match_issue_to_agendas(issue, [agenda])

    def test_agenda_with_none_project_type_raises(self):
        """Source code calls .lower() on project_type — None crashes."""
        issue = _issue(title="Pothole", category="pothole")
        agenda = {"id": "ag-1", "title": "Road repair", "description": "fix roads", "project_type": None}
        with pytest.raises(AttributeError):
            self.m.match_issue_to_agendas(issue, [agenda])

    def test_issue_with_empty_strings_returns_no_match(self):
        issue = {"id": "scf-1", "title": "", "description": "", "category": ""}
        agenda = _agenda(title="Road repair")
        result = self.m.match_issue_to_agendas(issue, [agenda])
        assert result == []

    def test_agenda_with_empty_strings_returns_no_match(self):
        issue = _issue(title="Pothole", category="pothole")
        agenda = {"id": "ag-1", "title": "", "description": "", "project_type": ""}
        result = self.m.match_issue_to_agendas(issue, [agenda])
        assert result == []

    def test_batch_with_missing_issue_id(self):
        issues = [{"title": "Pothole", "category": "pothole"}]  # No 'id' key
        agendas = [_agenda(title="Road repair")]
        result = self.m.match_issues_batch(issues, agendas)
        # id will be None, which is still a valid dict key
        assert None in result
        # pothole → "road" + "repair" = 40
        assert result[None][0]["confidence"] == 40.0

    def test_multiple_categories_first_match_wins(self):
        """Category matching iterates CATEGORY_KEYWORDS in order; first match is used."""
        # "traffic sign" contains both "traffic" and "sign" — first alphabetical match wins
        # (dict ordering in Python 3.7+ is insertion order)
        issue = _issue(title="traffic sign broken", category="traffic sign")
        agenda = _agenda(title="speed calming safety pedestrian crossing")
        result = self.m._match_single_pair(issue, agenda)
        # "traffic" comes before "sign" in CATEGORY_KEYWORDS (pothole, stormwater, dumping, traffic, sign...)
        # traffic keywords: speed, calming, safety, pedestrian → 4 hits → 60 base
        assert result is not None
        assert result["confidence"] == 60.0

    def test_description_truncation_in_llm_prompt(self):
        """LLM prompt truncates description to 200 chars — verify long descriptions don't crash."""
        m = OperationalAgendaMatcher(use_llm=False)
        m.use_llm = True
        m.llm_available = True

        mock_provider = MagicMock()
        mock_provider.generate.return_value = json.dumps({
            "related": True,
            "confidence": 50,
            "reasoning": "Related",
            "connection_type": "thematic",
        })
        m.llm_provider = MagicMock(return_value=mock_provider)

        long_desc = "x" * 500
        issue = _issue(title="Pothole", category="pothole", description=long_desc)
        agenda = _agenda(title="Road repair", description=long_desc)

        result = m._llm_semantic_match(issue, agenda, keyword_confidence=20.0)
        assert result is not None
        assert result["confidence"] == 50

    def test_statistics_with_unknown_category(self):
        """Issues with unrecognized categories are still counted in by_category."""
        issues = [_issue(title="mystery problem", category="Unknown", issue_id="scf-1")]
        agendas = [_agenda(title="Zoning hearing")]
        stats = self.m.get_match_statistics(issues, agendas)
        assert stats["by_category"]["Unknown"]["total"] == 1
        assert stats["by_category"]["Unknown"]["matched"] == 0
