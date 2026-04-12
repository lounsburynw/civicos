"""
Tests for heuristic-based federal rule relevance scoring.

Covers: agency scoring, geographic matching, CFR matching, composite scoring.
"""

import pytest
import re

from civicos._internal.legal.relevance import (
    AGENCY_WEIGHT,
    GEO_WEIGHT,
    CFR_WEIGHT,
    AGENCY_TOPIC_MAP,
    RELEVANT_CFR_TITLES,
    CFR_PATTERN,
    build_jurisdiction_config,
    score_agency_relevance,
    score_geographic_relevance,
    score_cfr_relevance,
    score_federal_rule,
)


# ---------- Constants ----------

class TestWeights:
    """Weight constants should sum to 1.0."""

    def test_weights_sum_to_one(self):
        assert AGENCY_WEIGHT + GEO_WEIGHT + CFR_WEIGHT == pytest.approx(1.0)

    def test_all_weights_positive(self):
        assert AGENCY_WEIGHT > 0
        assert GEO_WEIGHT > 0
        assert CFR_WEIGHT > 0


class TestCFRPattern:
    """CFR_PATTERN regex extracts title numbers correctly."""

    def test_standard_format(self):
        assert CFR_PATTERN.findall("40 CFR Part 122") == ["40"]

    def test_no_space(self):
        assert CFR_PATTERN.findall("40CFR") == ["40"]

    def test_lowercase(self):
        assert CFR_PATTERN.findall("40 cfr") == ["40"]

    def test_multiple_titles(self):
        assert CFR_PATTERN.findall("40 CFR and 23 CFR") == ["40", "23"]

    def test_no_match(self):
        assert CFR_PATTERN.findall("no regulation here") == []


# ---------- build_jurisdiction_config ----------

class TestBuildJurisdictionConfig:

    def test_returns_required_keys_with_valid_values(self):
        config = build_jurisdiction_config("city-san-rafael")
        assert config["jurisdiction_id"] == "city-san-rafael"
        assert len(config["active_topics"]) >= 10
        assert len(config["geo_terms"]) >= 5

    def test_jurisdiction_id_passthrough(self):
        config = build_jurisdiction_config("city-berkeley")
        assert config["jurisdiction_id"] == "city-berkeley"

    def test_active_topics_contains_expected_domains(self):
        config = build_jurisdiction_config("city-san-rafael")
        topics = config["active_topics"]
        assert isinstance(topics, set)
        # Must include key local government domains
        for domain in ["housing", "zoning", "transportation", "environment", "public_safety"]:
            assert domain in topics, f"Expected '{domain}' in active_topics"
        assert len(topics) >= 10

    def test_geo_terms_have_valid_structure(self):
        config = build_jurisdiction_config("city-san-rafael")
        geo_terms = config["geo_terms"]
        assert len(geo_terms) >= 5  # At least city, county, region, state
        for pattern, weight, label in geo_terms:
            assert isinstance(pattern, re.Pattern)
            assert 0.0 < weight <= 1.0, f"Weight {weight} for '{label}' out of range"
            assert len(label) > 0

    def test_geo_terms_match_expected_locations(self):
        """Geo patterns should match their labeled locations."""
        config = build_jurisdiction_config("city-san-rafael")
        labels = [label for _, _, label in config["geo_terms"]]
        assert "San Rafael" in labels
        assert "Marin County" in labels
        assert "California" in labels

    def test_geo_terms_city_weighted_higher_than_state(self):
        config = build_jurisdiction_config("city-san-rafael")
        weights_by_label = {label: w for _, w, label in config["geo_terms"]}
        assert weights_by_label["San Rafael"] > weights_by_label["California"]


# ---------- score_agency_relevance ----------

class TestScoreAgencyRelevance:

    @pytest.fixture
    def active_topics(self):
        return build_jurisdiction_config("city-san-rafael")["active_topics"]

    def test_empty_agencies(self, active_topics):
        score, reasons = score_agency_relevance([], active_topics)
        assert score == 0.0
        assert reasons == []

    def test_epa_matches_environment(self, active_topics):
        score, reasons = score_agency_relevance(
            ["Environmental Protection Agency"], active_topics
        )
        assert score > 0.0
        reason_topics = [r.split(":")[1] for r in reasons]
        assert "environment" in reason_topics

    def test_hud_matches_housing(self, active_topics):
        score, reasons = score_agency_relevance(
            ["Department of Housing and Urban Development"], active_topics
        )
        assert score > 0.0
        reason_topics = [r.split(":")[1] for r in reasons]
        assert "housing" in reason_topics

    def test_case_insensitive_matching(self, active_topics):
        """Agency matching is case-insensitive."""
        score, reasons = score_agency_relevance(
            ["environmental protection agency"], active_topics
        )
        assert score > 0.0

    def test_multiple_agencies_boost_score(self, active_topics):
        """Multiple relevant agencies should produce higher score."""
        single_score, _ = score_agency_relevance(
            ["Environmental Protection Agency"], active_topics
        )
        multi_score, _ = score_agency_relevance(
            ["Environmental Protection Agency", "Department of Transportation"],
            active_topics,
        )
        assert multi_score >= single_score

    def test_unrecognized_agency_scores_zero(self, active_topics):
        score, reasons = score_agency_relevance(
            ["Bureau of Fictional Affairs"], active_topics
        )
        assert score == 0.0
        assert reasons == []

    def test_score_capped_at_one(self, active_topics):
        """Even with many matching agencies, score should not exceed 1.0."""
        all_agencies = list(AGENCY_TOPIC_MAP.keys())
        score, _ = score_agency_relevance(all_agencies, active_topics)
        assert score <= 1.0

    def test_inactive_topics_ignored(self):
        """Topics not in active_topics shouldn't count."""
        limited_topics = {"housing"}  # Only housing is active
        score, reasons = score_agency_relevance(
            ["Department of Education"], limited_topics
        )
        assert score == 0.0  # education not in limited_topics


# ---------- score_geographic_relevance ----------

class TestScoreGeographicRelevance:

    @pytest.fixture
    def geo_terms(self):
        return build_jurisdiction_config("city-san-rafael")["geo_terms"]

    def test_empty_text(self, geo_terms):
        score, reasons = score_geographic_relevance("", "", geo_terms)
        assert score == 0.0
        assert reasons == []

    def test_none_text(self, geo_terms):
        score, reasons = score_geographic_relevance(None, None, geo_terms)
        assert score == 0.0

    def test_direct_city_mention(self, geo_terms):
        score, reasons = score_geographic_relevance(
            "San Rafael stormwater permit", "", geo_terms
        )
        assert score >= 0.9
        assert any("San Rafael" in r for r in reasons)

    def test_county_mention(self, geo_terms):
        score, reasons = score_geographic_relevance(
            "Marin County flood zone", "", geo_terms
        )
        assert score >= 0.9

    def test_state_mention_lower_score(self, geo_terms):
        score, reasons = score_geographic_relevance(
            "California emissions standards", "", geo_terms
        )
        assert 0.0 < score < 0.5  # State mention gives partial credit

    def test_no_geo_match(self, geo_terms):
        score, reasons = score_geographic_relevance(
            "New York City housing regulation", "", geo_terms
        )
        assert score == 0.0

    def test_multiple_tiers_bonus(self, geo_terms):
        """Mentioning both city and state should boost score."""
        single_score, _ = score_geographic_relevance(
            "California regulation", "", geo_terms
        )
        multi_score, _ = score_geographic_relevance(
            "San Rafael, California regulation", "", geo_terms
        )
        assert multi_score > single_score

    def test_abstract_also_searched(self, geo_terms):
        """Geographic terms in abstract should also match."""
        score, reasons = score_geographic_relevance(
            "Regulation about something",
            "This applies to Marin County jurisdictions",
            geo_terms,
        )
        assert score > 0.0


# ---------- score_cfr_relevance ----------

class TestScoreCFRRelevance:

    @pytest.fixture
    def active_topics(self):
        return build_jurisdiction_config("city-san-rafael")["active_topics"]

    def test_empty_regulation_ids(self, active_topics):
        score, reasons = score_cfr_relevance([], active_topics)
        assert score == 0.0
        assert reasons == []

    def test_environment_cfr_title(self, active_topics):
        """CFR title 40 (Environment) should match."""
        score, reasons = score_cfr_relevance(
            ["40 CFR Part 122"], active_topics
        )
        assert score > 0.0
        assert any("cfr:40" in r for r in reasons)

    def test_transportation_cfr_title(self, active_topics):
        """CFR title 23 (Highways) should match."""
        score, reasons = score_cfr_relevance(
            ["23 CFR Part 450"], active_topics
        )
        assert score > 0.0

    def test_irrelevant_cfr_title(self, active_topics):
        """CFR title not in RELEVANT_CFR_TITLES should score zero."""
        score, reasons = score_cfr_relevance(
            ["15 CFR Part 100"], active_topics  # 15 = Commerce — not mapped
        )
        assert score == 0.0

    def test_multiple_cfr_titles(self, active_topics):
        """Multiple relevant CFR titles should boost score."""
        single_score, _ = score_cfr_relevance(
            ["40 CFR Part 122"], active_topics
        )
        multi_score, _ = score_cfr_relevance(
            ["40 CFR Part 122", "23 CFR Part 450"], active_topics
        )
        assert multi_score >= single_score

    def test_score_capped_at_one(self, active_topics):
        """Score shouldn't exceed 1.0 even with many matching titles."""
        all_regs = [f"{t} CFR Part 1" for t in RELEVANT_CFR_TITLES.keys()]
        score, _ = score_cfr_relevance(all_regs, active_topics)
        assert score <= 1.0

    def test_non_string_regulation_ids_skipped(self, active_topics):
        """Non-string entries should be safely skipped."""
        score, reasons = score_cfr_relevance(
            [None, 123, "40 CFR Part 122"], active_topics
        )
        assert score > 0.0  # Still picks up the valid entry

    def test_inactive_topics_ignored(self):
        """CFR titles mapping to inactive topics shouldn't score."""
        limited_topics = {"housing"}  # Only housing active
        # CFR 40 maps to environment/water/climate — none are housing
        score, reasons = score_cfr_relevance(
            ["40 CFR Part 122"], limited_topics
        )
        assert score == 0.0


# ---------- score_federal_rule ----------

class TestScoreFederalRule:

    def test_empty_rule(self):
        score, reasons = score_federal_rule({})
        assert score == 0.0
        assert reasons == []

    def test_highly_relevant_rule(self):
        """Rule with EPA + San Rafael mention + CFR 40 should score high."""
        rule = {
            "agency_names": ["Environmental Protection Agency"],
            "title": "San Rafael stormwater permit requirements",
            "abstract": "Applicable to Marin County jurisdictions",
            "regulation_id_numbers": ["40 CFR Part 122"],
        }
        score, reasons = score_federal_rule(rule)
        assert score > 0.5
        # All three signal types should fire
        assert any("agency_topic:" in r for r in reasons)
        assert any("geo:" in r for r in reasons)
        assert any("cfr:" in r for r in reasons)

    def test_irrelevant_rule(self):
        """Rule with no local connection should score low."""
        rule = {
            "agency_names": ["Bureau of Prisons"],
            "title": "Federal prison meal standards",
            "abstract": "Updates to federal correctional facility nutrition",
            "regulation_id_numbers": ["28 CFR Part 541"],
        }
        score, reasons = score_federal_rule(rule)
        assert score < 0.1

    def test_score_bounded_zero_to_one(self):
        """Score should always be in [0.0, 1.0]."""
        rule = {
            "agency_names": list(AGENCY_TOPIC_MAP.keys()),
            "title": "San Rafael Marin County Bay Area California",
            "abstract": "All the geographic terms",
            "regulation_id_numbers": [f"{t} CFR" for t in RELEVANT_CFR_TITLES],
        }
        score, _ = score_federal_rule(rule)
        assert 0.0 <= score <= 1.0

    def test_string_agency_names_coerced_to_list(self):
        """agency_names as string should be handled."""
        rule = {
            "agency_names": "Environmental Protection Agency",
            "title": "Test rule",
        }
        score, reasons = score_federal_rule(rule)
        assert score > 0.0

    def test_string_regulation_ids_coerced_to_list(self):
        """regulation_id_numbers as string should be handled."""
        rule = {
            "regulation_id_numbers": "40 CFR Part 122",
        }
        score, reasons = score_federal_rule(rule)
        assert score > 0.0

    def test_custom_jurisdiction_config(self):
        """Custom config should be used when provided."""
        config = build_jurisdiction_config("city-berkeley")
        rule = {
            "agency_names": ["Environmental Protection Agency"],
            "title": "Test",
        }
        score, reasons = score_federal_rule(rule, jurisdiction_config=config)
        assert score > 0.0

    def test_score_is_rounded(self):
        """Score should be rounded to 3 decimal places."""
        rule = {
            "agency_names": ["Environmental Protection Agency"],
            "title": "San Rafael water quality",
            "regulation_id_numbers": ["40 CFR Part 122"],
        }
        score, _ = score_federal_rule(rule)
        assert score == round(score, 3)

    def test_agency_only_score(self):
        """Rule with only agency signal should score ≤ AGENCY_WEIGHT."""
        rule = {
            "agency_names": ["Environmental Protection Agency"],
            "title": "Generic rule about something",
        }
        score, _ = score_federal_rule(rule)
        assert score <= AGENCY_WEIGHT + 0.001  # float tolerance

    def test_geo_only_score(self):
        """Rule with only geo signal should score ≤ GEO_WEIGHT."""
        rule = {
            "agency_names": ["Bureau of Prisons"],  # unrecognized
            "title": "San Rafael specific rule",
        }
        score, _ = score_federal_rule(rule)
        assert score <= GEO_WEIGHT + 0.001
