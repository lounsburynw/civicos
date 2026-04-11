"""
Tests for legislative_enrichment.py — enrichment of civic opportunities with
state/federal legislative context.

The subject under test has two layers:
  1. Pure-logic helpers (extract_state_from_jurisdiction, passes_timing_test,
     find_relevant_bills, find_relevant_programs, generate_relevance_summary):
     tested with real inputs and pinned outputs — no mocks.
  2. Orchestration functions (enrich_opportunity, enrich_opportunities_batch):
     tested by patching the legislative_cache boundary only. The functions
     themselves are real and their scoring/selection behavior is pinned.

To run:
    pytest packages/civicos-services/tests/test_legislative_enrichment.py -q --override-ini="addopts="
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from civicos_services.legislative.legislative_enrichment import (
    enrich_opportunities_batch,
    enrich_opportunity,
    extract_state_from_jurisdiction,
    find_relevant_bills,
    find_relevant_programs,
    generate_relevance_summary,
    passes_timing_test,
)


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

# Sentinel expired deadline — disables the +10 timing bonus so scoring tests
# can isolate keyword/leverage/local-impl contributions.
EXPIRED = "2000-01-01T00:00:00Z"


HOUSING_OPPORTUNITY = {
    "id": "opp-1",
    "project_types": ["housing"],
    "jurisdiction": {"id": "city-san-rafael"},
    "title": "Housing Element Update",
    "description": "Rezoning to allow more affordable housing near transit.",
    "impact_summary": "RHNA allocation discussion",
}

TRANSIT_OPPORTUNITY = {
    "id": "opp-2",
    "project_type": "transit",  # old-format string
    "jurisdiction": {"id": "city-berkeley"},
    "title": "Bus Rapid Transit Expansion",
    "description": "Funding for new transit corridor",
    "impact_summary": "",
}

BILLS_FIXTURE = {
    "CA-SB-9": {
        "bill": "SB 9",
        "keywords": ["housing", "rezoning", "affordable"],
        "local_implementation_required": True,
        "leverage_point": "City councils adopt local ordinances implementing lot splits.",
        "local_deadline": "2099-01-01T00:00:00Z",
    },
    "CA-SB-35": {
        "bill": "SB 35",
        "keywords": ["transit"],
        "local_implementation_required": False,
        "leverage_point": "Streamlined ministerial approval for affordable projects.",
        "local_deadline": "Ongoing",
    },
    "CA-AB-ZERO": {
        "bill": "AB 0",
        "keywords": ["education"],  # will not match housing opportunity
        "local_implementation_required": False,
        "leverage_point": None,
    },
}

PROGRAMS_FIXTURE = {
    "HUD-CDBG": {
        "program_name": "Community Development Block Grant",
        "keywords": ["community development", "affordable housing"],
        "leverage_point": "City decides how to allocate CDBG funds across projects.",
    },
    "HUD-HOME": {
        "program_name": "HOME Investment Partnerships",
        "keywords": ["housing"],
        "local_control_point": "Cities choose which affordable housing projects to fund.",
    },
    "DOT-NONE": {
        "program_name": "Irrelevant Program",
        "keywords": ["spaceflight"],
    },
}


# ---------------------------------------------------------------------------
# extract_state_from_jurisdiction
# ---------------------------------------------------------------------------

class TestExtractStateFromJurisdiction:
    def test_city_prefix_returns_california(self):
        assert extract_state_from_jurisdiction("city-berkeley") == "california"

    def test_county_prefix_returns_california(self):
        assert extract_state_from_jurisdiction("county-marin") == "california"

    def test_hyphenated_city_name(self):
        assert extract_state_from_jurisdiction("city-san-rafael") == "california"

    def test_empty_string_returns_none(self):
        assert extract_state_from_jurisdiction("") is None

    def test_none_returns_none(self):
        assert extract_state_from_jurisdiction(None) is None

    def test_state_prefix_not_supported(self):
        # Only city-/county- prefixes are recognized today.
        assert extract_state_from_jurisdiction("state-california") is None

    def test_unknown_prefix_returns_none(self):
        assert extract_state_from_jurisdiction("jurisdiction-123") is None

    def test_bare_name_without_prefix_returns_none(self):
        assert extract_state_from_jurisdiction("berkeley") is None


# ---------------------------------------------------------------------------
# passes_timing_test
# ---------------------------------------------------------------------------

class TestPassesTimingTest:
    def test_no_deadline_is_always_relevant(self):
        assert passes_timing_test({}) is True

    def test_missing_deadline_key_is_relevant(self):
        assert passes_timing_test({"bill": "SB 9"}) is True

    def test_ongoing_deadline_passes(self):
        assert passes_timing_test({"local_deadline": "Ongoing"}) is True

    def test_pending_deadline_passes(self):
        assert passes_timing_test({"local_deadline": "Pending"}) is True

    def test_pending_enactment_deadline_passes(self):
        assert passes_timing_test({"local_deadline": "Pending enactment"}) is True

    def test_future_utc_deadline_passes(self):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        assert passes_timing_test({"local_deadline": future}) is True

    def test_past_utc_deadline_fails(self):
        past = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        assert passes_timing_test({"local_deadline": past}) is False

    def test_z_suffix_is_parsed_as_utc(self):
        # Far future Z-suffixed timestamp — should be considered relevant.
        assert passes_timing_test({"local_deadline": "2099-01-01T00:00:00Z"}) is True

    def test_z_suffix_past_date_fails(self):
        assert passes_timing_test({"local_deadline": "1999-01-01T00:00:00Z"}) is False

    def test_naive_datetime_assumed_utc_future(self):
        future_naive = (datetime.now(timezone.utc) + timedelta(days=10)).replace(tzinfo=None).isoformat()
        assert passes_timing_test({"local_deadline": future_naive}) is True

    def test_naive_datetime_assumed_utc_past(self):
        past_naive = (datetime.now(timezone.utc) - timedelta(days=10)).replace(tzinfo=None).isoformat()
        assert passes_timing_test({"local_deadline": past_naive}) is False

    def test_malformed_date_string_assumed_relevant(self):
        assert passes_timing_test({"local_deadline": "not-a-date"}) is True

    def test_non_string_deadline_assumed_relevant(self):
        # 12345 will raise AttributeError on .replace() — should fall through to True.
        assert passes_timing_test({"local_deadline": 12345}) is True


# ---------------------------------------------------------------------------
# find_relevant_bills
# ---------------------------------------------------------------------------

class TestFindRelevantBills:
    def test_empty_legislative_data_returns_empty(self):
        assert find_relevant_bills({}, HOUSING_OPPORTUNITY) == []

    def test_missing_state_legislation_key_returns_empty(self):
        assert find_relevant_bills({"federal_programs": {}}, HOUSING_OPPORTUNITY) == []

    def test_keyword_matches_score_ten_each(self):
        data = {
            "state_legislation": {
                "BILL-1": {
                    "bill": "B1",
                    "keywords": ["housing", "affordable"],
                    "local_deadline": EXPIRED,  # no timing bonus
                },
            }
        }
        results = find_relevant_bills(data, HOUSING_OPPORTUNITY)
        assert len(results) == 1
        # Two keyword matches * 10 = 20, timing bonus disabled via EXPIRED.
        assert results[0]["score"] == 20
        assert results[0]["id"] == "BILL-1"

    def test_local_implementation_adds_twenty(self):
        data = {
            "state_legislation": {
                "B1": {
                    "keywords": ["housing"],
                    "local_implementation_required": True,
                    "local_deadline": EXPIRED,
                },
            }
        }
        results = find_relevant_bills(data, HOUSING_OPPORTUNITY)
        # 1 keyword * 10 + 20 local_impl = 30 (timing disabled)
        assert results[0]["score"] == 30

    def test_short_leverage_point_adds_fifteen(self):
        data = {
            "state_legislation": {
                "B1": {
                    "keywords": ["housing"],
                    "leverage_point": "Short and actionable.",  # < 150 chars
                    "local_deadline": EXPIRED,
                },
            }
        }
        results = find_relevant_bills(data, HOUSING_OPPORTUNITY)
        # 1 keyword * 10 + 15 leverage = 25 (timing disabled)
        assert results[0]["score"] == 25

    def test_long_leverage_point_no_bonus(self):
        long_leverage = "x" * 200  # well over 150
        data = {
            "state_legislation": {
                "B1": {
                    "keywords": ["housing"],
                    "leverage_point": long_leverage,
                    "local_deadline": EXPIRED,
                },
            }
        }
        results = find_relevant_bills(data, HOUSING_OPPORTUNITY)
        assert results[0]["score"] == 10  # only the keyword match

    def test_leverage_point_at_150_chars_no_bonus(self):
        # Boundary: < 150 strict, so exactly 150 chars does NOT add bonus.
        lev_150 = "x" * 150
        data = {
            "state_legislation": {
                "B1": {
                    "keywords": ["housing"],
                    "leverage_point": lev_150,
                    "local_deadline": EXPIRED,
                },
            }
        }
        results = find_relevant_bills(data, HOUSING_OPPORTUNITY)
        assert results[0]["score"] == 10

    def test_timing_relevant_bill_adds_ten(self):
        data = {
            "state_legislation": {
                "B1": {"keywords": ["housing"], "local_deadline": "Ongoing"},
            }
        }
        results = find_relevant_bills(data, HOUSING_OPPORTUNITY)
        # 1 keyword + 10 timing = 20
        assert results[0]["score"] == 20

    def test_expired_bill_no_timing_bonus(self):
        past = "2000-01-01T00:00:00Z"
        data = {
            "state_legislation": {
                "B1": {"keywords": ["housing"], "local_deadline": past},
            }
        }
        results = find_relevant_bills(data, HOUSING_OPPORTUNITY)
        assert results[0]["score"] == 10  # keyword only

    def test_zero_score_bill_excluded(self):
        data = {
            "state_legislation": {
                # No keyword match AND expired deadline -> total score 0.
                "B1": {"keywords": ["spaceflight"], "local_deadline": EXPIRED},
            }
        }
        results = find_relevant_bills(data, HOUSING_OPPORTUNITY)
        assert results == []

    def test_returns_top_two_sorted_by_score(self):
        data = {
            "state_legislation": {
                # 1 kw + 10 timing (no deadline = relevant) = 20
                "LOW": {"keywords": ["housing"]},
                # 3 kw + 20 local + 15 lev + 10 timing = 75
                "HIGH": {
                    "keywords": ["housing", "affordable", "rezoning"],
                    "local_implementation_required": True,
                    "leverage_point": "Short leverage.",
                    "local_deadline": "Ongoing",
                },
                # 1 kw + 20 local + 10 timing = 40
                "MID": {
                    "keywords": ["housing"],
                    "local_implementation_required": True,
                },
            }
        }
        results = find_relevant_bills(data, HOUSING_OPPORTUNITY)
        assert len(results) == 2
        assert results[0]["id"] == "HIGH"
        assert results[0]["score"] == 75
        assert results[1]["id"] == "MID"
        assert results[1]["score"] == 40

    def test_bill_data_merged_into_result(self):
        data = {
            "state_legislation": {
                "B1": {"bill": "AB 1234", "keywords": ["housing"]},
            }
        }
        results = find_relevant_bills(data, HOUSING_OPPORTUNITY)
        # Bill data should be spread into result dict alongside id/score.
        assert results[0]["bill"] == "AB 1234"
        assert results[0]["keywords"] == ["housing"]

    def test_case_insensitive_keyword_matching(self):
        data = {
            "state_legislation": {
                "B1": {
                    "keywords": ["HOUSING", "Affordable"],
                    "local_deadline": EXPIRED,
                },
            }
        }
        results = find_relevant_bills(data, HOUSING_OPPORTUNITY)
        assert results[0]["score"] == 20  # both keywords matched case-insensitively

    def test_matches_across_title_description_impact(self):
        opp = {
            "title": "Alpha",
            "description": "Beta",
            "impact_summary": "gamma",
        }
        data = {
            "state_legislation": {
                "B1": {
                    "keywords": ["alpha", "beta", "gamma"],
                    "local_deadline": EXPIRED,
                },
            }
        }
        results = find_relevant_bills(data, opp)
        assert results[0]["score"] == 30  # all three matched


# ---------------------------------------------------------------------------
# find_relevant_programs
# ---------------------------------------------------------------------------

class TestFindRelevantPrograms:
    def test_empty_legislative_data_returns_empty(self):
        assert find_relevant_programs({}, HOUSING_OPPORTUNITY) == []

    def test_missing_federal_programs_key_returns_empty(self):
        assert find_relevant_programs({"state_legislation": {}}, HOUSING_OPPORTUNITY) == []

    def test_keyword_match_scores_ten(self):
        data = {
            "federal_programs": {
                "P1": {"keywords": ["housing"]},
            }
        }
        # Opportunity has project_type from "project_types" list — it won't
        # read project_type (singular), so the topic-match bonus does NOT fire.
        opp = {"title": "Housing", "description": "", "impact_summary": ""}
        results = find_relevant_programs(data, opp)
        assert len(results) == 1
        assert results[0]["score"] == 10

    def test_leverage_point_adds_fifteen(self):
        data = {
            "federal_programs": {
                "P1": {"keywords": ["housing"], "leverage_point": "City allocates funds."},
            }
        }
        opp = {"title": "Housing", "description": "", "impact_summary": ""}
        results = find_relevant_programs(data, opp)
        assert results[0]["score"] == 25  # 10 + 15

    def test_local_control_point_adds_fifteen(self):
        data = {
            "federal_programs": {
                "P1": {"keywords": ["housing"], "local_control_point": "City picks projects."},
            }
        }
        opp = {"title": "Housing", "description": "", "impact_summary": ""}
        results = find_relevant_programs(data, opp)
        assert results[0]["score"] == 25

    def test_topic_match_bonus_requires_singular_project_type(self):
        """Topic-match bonus reads opportunity['project_type'] (singular)."""
        data = {
            "federal_programs": {
                "P1": {"keywords": ["affordable housing"]},
            }
        }
        opp = {
            "project_type": "housing",  # singular triggers topic bonus
            "title": "",
            "description": "",
            "impact_summary": "",
        }
        results = find_relevant_programs(data, opp)
        # No keyword match against empty text, but topic match fires: +20.
        assert len(results) == 1
        assert results[0]["score"] == 20

    def test_topic_match_bonus_for_zoning(self):
        data = {
            "federal_programs": {
                "P1": {"keywords": ["community development"]},
            }
        }
        opp = {"project_type": "zoning", "title": "", "description": "", "impact_summary": ""}
        results = find_relevant_programs(data, opp)
        assert results[0]["score"] == 20

    def test_topic_match_skipped_for_non_housing_project(self):
        data = {
            "federal_programs": {
                "P1": {"keywords": ["affordable housing"]},
            }
        }
        opp = {"project_type": "transit", "title": "", "description": "", "impact_summary": ""}
        results = find_relevant_programs(data, opp)
        # No keyword match, no topic match (transit not in housing/zoning) -> excluded.
        assert results == []

    def test_topic_match_skipped_when_keywords_unrelated(self):
        data = {
            "federal_programs": {
                "P1": {"keywords": ["spaceflight", "research"]},
            }
        }
        opp = {"project_type": "housing", "title": "", "description": "", "impact_summary": ""}
        results = find_relevant_programs(data, opp)
        assert results == []

    def test_returns_top_two_sorted_by_score(self):
        data = {
            "federal_programs": {
                "LOW": {"keywords": ["housing"]},  # 10
                "HIGH": {
                    "keywords": ["housing", "affordable housing"],
                    "leverage_point": "City decides.",
                },  # 20 + 15 + 20 (topic) = 55
                "MID": {
                    "keywords": ["affordable housing"],
                    "local_control_point": "City chooses.",
                },  # 10 + 15 + 20 (topic) = 45
            }
        }
        opp = {
            "project_type": "housing",
            "title": "Affordable housing plan",
            "description": "housing",
            "impact_summary": "",
        }
        results = find_relevant_programs(data, opp)
        assert len(results) == 2
        assert results[0]["id"] == "HIGH"
        assert results[0]["score"] == 55
        assert results[1]["id"] == "MID"
        assert results[1]["score"] == 45

    def test_zero_score_program_excluded(self):
        data = {
            "federal_programs": {
                "P1": {"keywords": ["spaceflight"]},
            }
        }
        opp = {"title": "Housing", "description": "", "impact_summary": ""}
        results = find_relevant_programs(data, opp)
        assert results == []

    def test_program_data_merged_into_result(self):
        data = {
            "federal_programs": {
                "HUD-CDBG": {
                    "program_name": "CDBG",
                    "keywords": ["housing"],
                },
            }
        }
        opp = {"title": "Housing", "description": "", "impact_summary": ""}
        results = find_relevant_programs(data, opp)
        assert results[0]["id"] == "HUD-CDBG"
        assert results[0]["program_name"] == "CDBG"


# ---------------------------------------------------------------------------
# generate_relevance_summary
# ---------------------------------------------------------------------------

class TestGenerateRelevanceSummary:
    def test_no_bills_or_programs_returns_empty_string(self):
        assert generate_relevance_summary([], [], HOUSING_OPPORTUNITY) == ""

    def test_bill_only_summary(self):
        bills = [{"bill": "SB 9", "leverage_point": "City adopts ordinance."}]
        result = generate_relevance_summary(bills, [], HOUSING_OPPORTUNITY)
        assert result == "Related to SB 9: City adopts ordinance."

    def test_program_only_summary_uses_leverage_point(self):
        programs = [{"program_name": "CDBG", "leverage_point": "City allocates funds."}]
        result = generate_relevance_summary([], programs, HOUSING_OPPORTUNITY)
        assert result == "CDBG: City allocates funds."

    def test_program_only_summary_falls_back_to_local_control_point(self):
        programs = [{"program_name": "HOME", "local_control_point": "City picks recipients."}]
        result = generate_relevance_summary([], programs, HOUSING_OPPORTUNITY)
        assert result == "HOME: City picks recipients."

    def test_leverage_point_preferred_over_local_control_point(self):
        programs = [{
            "program_name": "P",
            "leverage_point": "from_leverage",
            "local_control_point": "from_lcp",
        }]
        result = generate_relevance_summary([], programs, HOUSING_OPPORTUNITY)
        assert "from_leverage" in result
        assert "from_lcp" not in result

    def test_bill_and_program_combined(self):
        bills = [{"bill": "SB 9", "leverage_point": "City adopts ordinance."}]
        programs = [{"program_name": "CDBG", "leverage_point": "City allocates funds."}]
        result = generate_relevance_summary(bills, programs, HOUSING_OPPORTUNITY)
        assert result == "Related to SB 9: City adopts ordinance. CDBG: City allocates funds."

    def test_missing_bill_name_uses_default(self):
        bills = [{"leverage_point": "City implements."}]
        result = generate_relevance_summary(bills, [], HOUSING_OPPORTUNITY)
        assert result == "Related to state legislation: City implements."

    def test_missing_leverage_uses_default(self):
        bills = [{"bill": "SB 9"}]
        result = generate_relevance_summary(bills, [], HOUSING_OPPORTUNITY)
        assert result == "Related to SB 9: local implementation"

    def test_long_program_control_truncated_to_80_chars(self):
        long_control = "x" * 100
        programs = [{"program_name": "P", "leverage_point": long_control}]
        result = generate_relevance_summary([], programs, HOUSING_OPPORTUNITY)
        # Truncated to 77 chars + "..." = 80 chars of text after "P: "
        assert "P: " + ("x" * 77) + "..." == result

    def test_control_exactly_80_not_truncated(self):
        # Boundary: condition is `len(control) > 80`, so exactly 80 is preserved.
        control_80 = "y" * 80
        programs = [{"program_name": "P", "leverage_point": control_80}]
        result = generate_relevance_summary([], programs, HOUSING_OPPORTUNITY)
        assert result == f"P: {control_80}"

    def test_control_81_is_truncated(self):
        control_81 = "z" * 81
        programs = [{"program_name": "P", "leverage_point": control_81}]
        result = generate_relevance_summary([], programs, HOUSING_OPPORTUNITY)
        # 77 chars then "..."
        assert result == "P: " + ("z" * 77) + "..."

    def test_first_bill_used_when_multiple(self):
        bills = [
            {"bill": "FIRST", "leverage_point": "first lev"},
            {"bill": "SECOND", "leverage_point": "second lev"},
        ]
        result = generate_relevance_summary(bills, [], HOUSING_OPPORTUNITY)
        assert "FIRST" in result
        assert "SECOND" not in result


# ---------------------------------------------------------------------------
# enrich_opportunity — orchestration, mocks legislative_cache only
# ---------------------------------------------------------------------------

ENRICHMENT_MODULE = "civicos_services.legislative.legislative_enrichment"


class TestEnrichOpportunity:
    def test_returns_none_for_non_enrichable_project_type(self):
        opp = {
            "id": "opp-1",
            "project_types": ["public_safety"],  # enrich: False
            "jurisdiction": {"id": "city-san-rafael"},
        }
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            result = enrich_opportunity(opp)
            mock_cache.get.assert_not_called()
        assert result is None

    def test_returns_none_for_unknown_project_type(self):
        opp = {
            "id": "opp-1",
            "project_types": ["fictional_category"],
            "jurisdiction": {"id": "city-san-rafael"},
        }
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            result = enrich_opportunity(opp)
            mock_cache.get.assert_not_called()
        assert result is None

    def test_returns_none_when_project_types_empty(self):
        opp = {
            "id": "opp-1",
            "project_types": [],
            "jurisdiction": {"id": "city-san-rafael"},
        }
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            result = enrich_opportunity(opp)
            mock_cache.get.assert_not_called()
        assert result is None

    def test_string_project_type_coerced_to_list(self):
        """Old-format `project_type: str` should still enrich."""
        opp = {
            "id": "opp-str",
            "project_type": "housing",
            "jurisdiction": {"id": "city-san-rafael"},
            "title": "Housing plan",
            "description": "",
            "impact_summary": "",
        }
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": {
                    "CA-SB-9": {"bill": "SB 9", "keywords": ["housing"]},
                },
                "federal_programs": {},
            }
            result = enrich_opportunity(opp)

        # Cache is keyed by ("california", "housing") and the coerced string
        # produces a working enrichment payload.
        mock_cache.get.assert_called_once_with("california", "housing")
        assert result["state_legislation_refs"] == ["CA-SB-9"]
        assert result["federal_program_refs"] == []
        assert "SB 9" in result["relevance_summary"]

    def test_first_enrichable_type_wins_over_later_types(self):
        """If multiple project_types, the first enrichable one drives lookup."""
        opp = {
            "id": "multi",
            "project_types": ["public_safety", "transit", "housing"],
            "jurisdiction": {"id": "city-berkeley"},
            "title": "transit improvements",
            "description": "",
            "impact_summary": "",
        }
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": {
                    "B1": {"bill": "SB 1", "keywords": ["transit"]},
                },
                "federal_programs": {},
            }
            result = enrich_opportunity(opp)
            # state_key for "transit" = "transportation"
            mock_cache.get.assert_called_once_with("california", "transportation")

        assert result is not None
        assert result["state_legislation_refs"] == ["B1"]

    def test_zoning_maps_to_housing_state_key(self):
        """zoning project type should look up the 'housing' cache bucket."""
        opp = {
            "id": "z",
            "project_types": ["zoning"],
            "jurisdiction": {"id": "city-san-rafael"},
            "title": "Zoning reform",
            "description": "",
            "impact_summary": "",
        }

        captured_keys = []

        def fake_get(state, topic):
            captured_keys.append((state, topic))
            # Return housing-keyed data so the enrichment succeeds.
            return {
                "state_legislation": {
                    "CA-SB-9": {"bill": "SB 9", "keywords": ["zoning"]},
                },
                "federal_programs": {},
            }

        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.side_effect = fake_get
            result = enrich_opportunity(opp)

        assert captured_keys == [("california", "housing")]
        assert result["state_legislation_refs"] == ["CA-SB-9"]

    def test_unknown_jurisdiction_returns_none(self):
        opp = {
            "id": "opp",
            "project_types": ["housing"],
            "jurisdiction": {"id": "state-nowhere"},
        }
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            result = enrich_opportunity(opp)
            # State extraction fails before cache hit.
            mock_cache.get.assert_not_called()
        assert result is None

    def test_missing_jurisdiction_dict_returns_none(self):
        opp = {"id": "opp", "project_types": ["housing"]}
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            result = enrich_opportunity(opp)
            mock_cache.get.assert_not_called()
        assert result is None

    def test_cache_miss_returns_none(self):
        opp = {
            "id": "opp",
            "project_types": ["housing"],
            "jurisdiction": {"id": "city-san-rafael"},
            "title": "x", "description": "", "impact_summary": "",
        }
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = None
            result = enrich_opportunity(opp)
        assert result is None

    def test_empty_legislative_data_returns_none(self):
        """Cache hit but no bills/programs in the result -> None."""
        opp = {
            "id": "opp",
            "project_types": ["housing"],
            "jurisdiction": {"id": "city-san-rafael"},
            "title": "Housing",
            "description": "",
            "impact_summary": "",
        }
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {"state_legislation": {}, "federal_programs": {}}
            result = enrich_opportunity(opp)
        assert result is None

    def test_no_scoring_matches_returns_none(self):
        """Cache has data but nothing scores above 0."""
        opp = {
            "id": "opp",
            "project_types": ["housing"],
            "jurisdiction": {"id": "city-san-rafael"},
            "title": "Zzz",
            "description": "Zzz",
            "impact_summary": "Zzz",
        }
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                # Expired deadline disables the +10 timing bonus so score = 0.
                "state_legislation": {
                    "B1": {"keywords": ["spaceflight"], "local_deadline": EXPIRED},
                },
                "federal_programs": {"P1": {"keywords": ["spaceflight"]}},
            }
            result = enrich_opportunity(opp)
        assert result is None

    def test_successful_enrichment_shape(self):
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": BILLS_FIXTURE,
                "federal_programs": PROGRAMS_FIXTURE,
            }
            result = enrich_opportunity(HOUSING_OPPORTUNITY)

        assert result is not None
        assert set(result.keys()) == {
            "state_legislation_refs",
            "federal_program_refs",
            "relevance_summary",
        }

    def test_successful_enrichment_refs_are_ids(self):
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": BILLS_FIXTURE,
                "federal_programs": PROGRAMS_FIXTURE,
            }
            result = enrich_opportunity(HOUSING_OPPORTUNITY)

        # CA-SB-9 has 3 kw matches (housing, rezoning, affordable) + local_impl + short leverage + ongoing future = high
        # CA-SB-35 has 0 keyword matches in title/desc, so excluded.
        assert "CA-SB-9" in result["state_legislation_refs"]
        assert "CA-AB-ZERO" not in result["state_legislation_refs"]
        # At most 2 bills
        assert len(result["state_legislation_refs"]) <= 2

    def test_successful_enrichment_includes_federal_program(self):
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": BILLS_FIXTURE,
                "federal_programs": PROGRAMS_FIXTURE,
            }
            result = enrich_opportunity(HOUSING_OPPORTUNITY)

        # HUD-CDBG keywords "community development" doesn't match the title
        # but "affordable housing" does. HUD-CDBG also has a leverage_point
        # bonus (+15).  HOUSING_OPPORTUNITY uses project_types (plural), so
        # topic bonus does NOT fire — that's fine, keyword match is enough.
        assert "HUD-CDBG" in result["federal_program_refs"]
        assert "DOT-NONE" not in result["federal_program_refs"]

    def test_successful_enrichment_summary_includes_bill_name(self):
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": BILLS_FIXTURE,
                "federal_programs": PROGRAMS_FIXTURE,
            }
            result = enrich_opportunity(HOUSING_OPPORTUNITY)

        assert "SB 9" in result["relevance_summary"]

    def test_only_bills_no_programs(self):
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": {
                    "B1": {"bill": "SB 1", "keywords": ["housing"], "leverage_point": "lev"},
                },
                "federal_programs": {},
            }
            result = enrich_opportunity(HOUSING_OPPORTUNITY)

        assert result["state_legislation_refs"] == ["B1"]
        assert result["federal_program_refs"] == []
        assert "SB 1" in result["relevance_summary"]

    def test_only_programs_no_bills(self):
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": {},
                "federal_programs": {
                    "P1": {"program_name": "HOME", "keywords": ["housing"]},
                },
            }
            result = enrich_opportunity(HOUSING_OPPORTUNITY)

        assert result["state_legislation_refs"] == []
        assert result["federal_program_refs"] == ["P1"]
        assert "HOME" in result["relevance_summary"]


# ---------------------------------------------------------------------------
# enrich_opportunities_batch
# ---------------------------------------------------------------------------

class TestEnrichOpportunitiesBatch:
    def test_empty_list_returns_empty_list(self):
        assert enrich_opportunities_batch([]) == []

    def test_skipped_opportunity_passed_through_unchanged(self):
        opp = {
            "id": "opp",
            "project_types": ["public_safety"],  # non-enrichable
            "jurisdiction": {"id": "city-san-rafael"},
        }
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache"):
            result = enrich_opportunities_batch([opp])

        assert len(result) == 1
        assert result[0] is opp  # same object, not a copy
        assert "legislative_context" not in result[0]

    def test_enriched_opportunity_has_context_field(self):
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": {
                    "B1": {"bill": "SB 1", "keywords": ["housing"]},
                },
                "federal_programs": {},
            }
            result = enrich_opportunities_batch([HOUSING_OPPORTUNITY])

        assert len(result) == 1
        assert "legislative_context" in result[0]
        assert result[0]["legislative_context"]["state_legislation_refs"] == ["B1"]
        # Original preserved
        assert result[0]["id"] == "opp-1"

    def test_original_opportunity_not_mutated(self):
        original = dict(HOUSING_OPPORTUNITY)
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": {"B1": {"bill": "SB 1", "keywords": ["housing"]}},
                "federal_programs": {},
            }
            enrich_opportunities_batch([original])
        # Original dict should not have gained the legislative_context key.
        assert "legislative_context" not in original

    def test_mixed_batch_enriched_and_skipped(self):
        enrichable = dict(HOUSING_OPPORTUNITY)
        skipped = {
            "id": "skip",
            "project_types": ["public_safety"],
            "jurisdiction": {"id": "city-san-rafael"},
        }

        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": {"B1": {"bill": "SB 1", "keywords": ["housing"]}},
                "federal_programs": {},
            }
            result = enrich_opportunities_batch([enrichable, skipped])

        assert len(result) == 2
        # First enriched
        assert "legislative_context" in result[0]
        assert result[0]["id"] == "opp-1"
        # Second passed through
        assert "legislative_context" not in result[1]
        assert result[1]["id"] == "skip"

    def test_exception_in_enrich_keeps_batch_running(self):
        """A real exception inside enrich_opportunity must not abort the batch."""
        good = dict(HOUSING_OPPORTUNITY)
        # jurisdiction=None triggers AttributeError on `.get("id", "")` inside
        # enrich_opportunity — a real exception, not a mocked one.
        bad = {
            "id": "bad",
            "project_types": ["housing"],
            "jurisdiction": None,
        }

        with patch(f"{ENRICHMENT_MODULE}.legislative_cache") as mock_cache:
            mock_cache.get.return_value = {
                "state_legislation": {
                    "B1": {"bill": "SB 1", "keywords": ["housing"]},
                },
                "federal_programs": {},
            }
            result = enrich_opportunities_batch([good, bad])

        assert len(result) == 2
        # Good opportunity was enriched.
        assert result[0]["id"] == "opp-1"
        assert result[0]["legislative_context"]["state_legislation_refs"] == ["B1"]
        # Bad opportunity survives the exception and is passed through unchanged.
        assert result[1]["id"] == "bad"
        assert "legislative_context" not in result[1]

    def test_order_preserved(self):
        opps = [
            {"id": f"opp-{i}", "project_types": ["public_safety"],
             "jurisdiction": {"id": "city-san-rafael"}}
            for i in range(5)
        ]
        with patch(f"{ENRICHMENT_MODULE}.legislative_cache"):
            result = enrich_opportunities_batch(opps)
        assert [r["id"] for r in result] == ["opp-0", "opp-1", "opp-2", "opp-3", "opp-4"]
