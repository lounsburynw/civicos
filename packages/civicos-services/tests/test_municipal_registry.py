"""
Tests for municipal_registry — the hardcoded registry of city data collection
status, target cities, platform strategies, and the derived helper functions.

The module has two surfaces:

1. Static dicts (MUNICIPAL_REGISTRY, TARGET_CITIES_PHASE1, PLATFORM_STRATEGIES,
   SCALING_STRATEGY) which encode institutional knowledge. Tests pin specific
   values so refactors don't silently drop fields.

2. Helper functions (get_city_info, add_test_result, get_working_cities,
   get_priority_targets, make_strategic_decision) which contain real logic
   (case normalization, filtering, sorting, threshold branching).

The helpers mutate MUNICIPAL_REGISTRY, so tests that add entries use a
snapshot fixture that restores the module-global before/after.

To run:
    pytest packages/civicos-services/tests/test_municipal_registry.py -q --override-ini="addopts="
"""

import copy
from datetime import datetime
from unittest.mock import patch

import pytest

from civicos_services.core import municipal_registry
from civicos_services.core.municipal_registry import (
    MUNICIPAL_REGISTRY,
    PLATFORM_STRATEGIES,
    SCALING_STRATEGY,
    TARGET_CITIES_PHASE1,
    add_test_result,
    get_city_info,
    get_priority_targets,
    get_working_cities,
    make_strategic_decision,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry_snapshot():
    """Snapshot MUNICIPAL_REGISTRY before the test and restore afterwards.

    Several helpers (add_test_result, make_strategic_decision) read/write
    the module-global registry. Without isolation, tests would pollute each
    other. We replace the dict's contents in-place so module-level references
    stay valid.
    """
    original = copy.deepcopy(municipal_registry.MUNICIPAL_REGISTRY)
    yield
    municipal_registry.MUNICIPAL_REGISTRY.clear()
    municipal_registry.MUNICIPAL_REGISTRY.update(original)


# ---------------------------------------------------------------------------
# MUNICIPAL_REGISTRY — pinned values for known cities
# ---------------------------------------------------------------------------


class TestMunicipalRegistryContents:
    def test_san_rafael_is_production_granicus(self):
        entry = MUNICIPAL_REGISTRY["san_rafael"]
        assert entry["status"] == "production"
        assert entry["platform"] == "granicus_based"
        assert entry["success_rate"] == 95
        assert entry["html_parsing"] == "success"
        assert entry["gpt4o_compatibility"] == "excellent"

    def test_san_rafael_has_no_confirmed_legistar_api(self):
        # api_access is explicitly None to mean "no Legistar API confirmed"
        assert MUNICIPAL_REGISTRY["san_rafael"]["api_access"] is None

    def test_berkeley_is_failed_due_to_pdf_complexity(self):
        entry = MUNICIPAL_REGISTRY["berkeley"]
        assert entry["status"] == "failed_pdf_complexity"
        assert entry["success_rate"] == 0
        assert entry["html_parsing"] == "failed"
        assert "PDFs" in entry["failure_reason"]

    def test_oakland_is_legistar_production_ready(self):
        entry = MUNICIPAL_REGISTRY["oakland"]
        assert entry["status"] == "legistar_production_ready"
        assert entry["platform"] == "legistar"
        assert entry["success_rate"] == 95
        assert entry["legistar_client"] == "oakland"
        assert entry["cost_per_session"] == 0.05

    def test_marin_county_is_broken_all_sources(self):
        entry = MUNICIPAL_REGISTRY["marin_county"]
        assert entry["status"] == "broken_all_sources_inaccessible"
        assert entry["platform"] == "none"
        assert entry["html_parsing"] == "failed"
        # Exactly three failure reasons were documented
        assert len(entry["failure_reasons"]) == 3

    def test_el_cerrito_civicclerk_subdomain_matches_jurisdiction(self):
        entry = MUNICIPAL_REGISTRY["el_cerrito"]
        assert entry["platform"] == "civicclerk"
        assert entry["civicclerk_subdomain"] == "elcerritoca"
        assert entry["jurisdiction_id"] == "city-el-cerrito"
        assert entry["api_url"] == "https://elcerritoca.api.civicclerk.com/v1"

    def test_los_altos_has_highest_agenda_availability(self):
        entry = MUNICIPAL_REGISTRY["los_altos"]
        # 86% agenda availability is the documented differentiator
        assert entry["success_rate"] == 86
        assert entry["civicclerk_subdomain"] == "losaltosca"
        assert entry["jurisdiction_id"] == "city-los-altos"

    def test_registry_contains_expected_cities(self):
        expected = {
            "san_rafael",
            "berkeley",
            "san_francisco",
            "oakland",
            "santa_rosa",
            "sonoma_county",
            "marin_county",
            "hayward",
            "el_cerrito",
            "los_altos",
        }
        assert expected.issubset(set(MUNICIPAL_REGISTRY.keys()))

    def test_registry_has_exactly_ten_entries(self):
        # Guardrail: if an entry is added/removed, update this count and
        # the relevant tests.
        assert len(MUNICIPAL_REGISTRY) == 10


# ---------------------------------------------------------------------------
# TARGET_CITIES_PHASE1 — phase 1 targets and priorities
# ---------------------------------------------------------------------------


class TestTargetCitiesPhase1:
    def test_petaluma_is_priority_one_granicus(self):
        entry = TARGET_CITIES_PHASE1["petaluma"]
        assert entry["priority"] == 1
        assert entry["expected_platform"] == "granicus"
        assert entry["expected_success"] == "high"

    def test_mill_valley_is_priority_one(self):
        entry = TARGET_CITIES_PHASE1["mill_valley"]
        assert entry["priority"] == 1
        assert entry["expected_success"] == "high"

    def test_novato_is_priority_two_medium(self):
        entry = TARGET_CITIES_PHASE1["novato"]
        assert entry["priority"] == 2
        assert entry["expected_success"] == "medium"
        assert entry["expected_platform"] == "standard_municipal"

    def test_santa_rosa_target_has_srcity_url(self):
        entry = TARGET_CITIES_PHASE1["santa_rosa"]
        assert entry["priority"] == 2
        assert any("srcity.org" in url for url in entry["test_urls"])

    def test_contains_exactly_four_phase_one_targets(self):
        assert set(TARGET_CITIES_PHASE1.keys()) == {
            "petaluma",
            "mill_valley",
            "novato",
            "santa_rosa",
        }


# ---------------------------------------------------------------------------
# PLATFORM_STRATEGIES — strategy per platform
# ---------------------------------------------------------------------------


class TestPlatformStrategies:
    def test_granicus_uses_html_parsing_gpt4o(self):
        entry = PLATFORM_STRATEGIES["granicus"]
        assert entry["approach"] == "html_parsing_gpt4o"
        assert entry["expected_success_rate"] == 85

    def test_legistar_is_html_first_api_future(self):
        entry = PLATFORM_STRATEGIES["legistar"]
        assert entry["approach"] == "html_first_api_future"
        assert entry["expected_success_rate"] == 70

    def test_standard_municipal_has_lower_success_rate_than_granicus(self):
        assert (
            PLATFORM_STRATEGIES["standard_municipal"]["expected_success_rate"]
            < PLATFORM_STRATEGIES["granicus"]["expected_success_rate"]
        )
        assert PLATFORM_STRATEGIES["standard_municipal"]["expected_success_rate"] == 60

    def test_pdf_heavy_is_avoided(self):
        entry = PLATFORM_STRATEGIES["pdf_heavy"]
        assert entry["approach"] == "avoid"
        assert entry["expected_success_rate"] == 5

    def test_pdf_heavy_has_lowest_expected_success(self):
        rates = {
            name: s["expected_success_rate"] for name, s in PLATFORM_STRATEGIES.items()
        }
        assert min(rates, key=rates.get) == "pdf_heavy"

    def test_all_expected_platforms_present(self):
        assert set(PLATFORM_STRATEGIES.keys()) == {
            "granicus",
            "legistar",
            "standard_municipal",
            "pdf_heavy",
        }


# ---------------------------------------------------------------------------
# SCALING_STRATEGY — constants that downstream code reads
# ---------------------------------------------------------------------------


class TestScalingStrategy:
    def test_phase_one_approach_is_html_first(self):
        assert SCALING_STRATEGY["phase_1_approach"] == "html_first_gpt4o_universal"

    def test_api_integration_is_enhancement_not_requirement(self):
        assert SCALING_STRATEGY["api_integration"] == "enhancement_not_requirement"

    def test_complexity_budget_is_500_lines(self):
        assert SCALING_STRATEGY["complexity_budget"] == 500

    def test_success_threshold_is_three(self):
        # make_strategic_decision depends on this matching its hardcoded 3
        assert SCALING_STRATEGY["success_threshold"] == 3

    def test_fallback_strategy_always_gpt4o_universal(self):
        assert (
            SCALING_STRATEGY["fallback_strategy"]
            == "always_maintain_gpt4o_universal_parsing"
        )


# ---------------------------------------------------------------------------
# get_city_info
# ---------------------------------------------------------------------------


class TestGetCityInfo:
    def test_returns_entry_for_known_lowercase_city(self):
        info = get_city_info("san_rafael")
        assert info is not None
        assert info["status"] == "production"
        assert info["success_rate"] == 95

    def test_lowercases_input_before_lookup(self):
        # Registry keys are stored lowercase; the function must normalize.
        info = get_city_info("SAN_RAFAEL")
        assert info is not None
        assert info["platform"] == "granicus_based"

    def test_lowercases_mixed_case_input(self):
        info = get_city_info("San_Rafael")
        assert info is not None
        assert info["status"] == "production"

    def test_returns_none_for_unknown_city(self):
        assert get_city_info("atlantis") is None

    def test_returns_none_for_empty_string(self):
        assert get_city_info("") is None

    def test_returns_exact_registry_reference_not_copy(self):
        # The current implementation returns the dict directly (no copy).
        # This behavior is load-bearing for add_test_result, which assumes
        # subsequent .update() on the returned dict is visible globally.
        info = get_city_info("oakland")
        assert info is MUNICIPAL_REGISTRY["oakland"]


# ---------------------------------------------------------------------------
# add_test_result
# ---------------------------------------------------------------------------


class TestAddTestResult:
    def test_merges_fields_into_existing_city(self, registry_snapshot):
        add_test_result("san_rafael", {"success_rate": 99, "new_field": "x"})
        updated = MUNICIPAL_REGISTRY["san_rafael"]
        assert updated["success_rate"] == 99
        assert updated["new_field"] == "x"
        # Existing fields are preserved via dict.update semantics
        assert updated["platform"] == "granicus_based"

    def test_creates_new_entry_for_unknown_city(self, registry_snapshot):
        add_test_result("new_town", {"status": "testing", "platform": "custom"})
        assert "new_town" in MUNICIPAL_REGISTRY
        assert MUNICIPAL_REGISTRY["new_town"]["status"] == "testing"
        assert MUNICIPAL_REGISTRY["new_town"]["platform"] == "custom"

    def test_stamps_last_tested_with_today(self, registry_snapshot):
        # Freeze the clock so we can assert a specific date string
        fixed = datetime(2026, 4, 10, 12, 0, 0)

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed

        with patch.object(municipal_registry, "datetime", FrozenDateTime):
            add_test_result("oakland", {"success_rate": 97})

        assert MUNICIPAL_REGISTRY["oakland"]["last_tested"] == "2026-04-10"
        assert MUNICIPAL_REGISTRY["oakland"]["success_rate"] == 97

    def test_lowercases_city_name_when_storing(self, registry_snapshot):
        add_test_result("NEW_CITY", {"status": "testing"})
        assert "new_city" in MUNICIPAL_REGISTRY
        assert "NEW_CITY" not in MUNICIPAL_REGISTRY

    def test_overwrites_last_tested_even_if_caller_provided_one(
        self, registry_snapshot
    ):
        # The function assigns last_tested AFTER .update(), so a caller-provided
        # last_tested gets overwritten with today. Pin this behavior.
        fixed = datetime(2026, 4, 10)

        class FrozenDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed

        with patch.object(municipal_registry, "datetime", FrozenDateTime):
            add_test_result(
                "san_rafael", {"last_tested": "1999-01-01", "note": "stale"}
            )

        assert MUNICIPAL_REGISTRY["san_rafael"]["last_tested"] == "2026-04-10"
        assert MUNICIPAL_REGISTRY["san_rafael"]["note"] == "stale"

    def test_does_not_delete_unrelated_fields(self, registry_snapshot):
        original_notes = MUNICIPAL_REGISTRY["san_rafael"]["notes"]
        add_test_result("san_rafael", {"success_rate": 100})
        assert MUNICIPAL_REGISTRY["san_rafael"]["notes"] == original_notes


# ---------------------------------------------------------------------------
# get_working_cities
# ---------------------------------------------------------------------------


class TestGetWorkingCities:
    def test_returns_baseline_working_cities_from_default_registry(self):
        # With the default registry, these are the four cities that qualify:
        # - san_rafael: status == 'production'
        # - oakland: success_rate 95 (> 70)
        # - el_cerrito: success_rate 95 (> 70)
        # - los_altos: success_rate 86 (> 70)
        result = get_working_cities()
        assert set(result) == {"san_rafael", "oakland", "el_cerrito", "los_altos"}

    def test_excludes_cities_with_failed_status(self):
        assert "berkeley" not in get_working_cities()

    def test_excludes_cities_with_success_rate_zero(self):
        # berkeley has success_rate 0 — below the > 70 threshold
        assert "berkeley" not in get_working_cities()

    def test_excludes_cities_without_success_rate_and_non_production_status(self):
        # hayward and san_francisco are legistar entries without success_rate;
        # get("success_rate", 0) defaults to 0, which fails > 70.
        working = get_working_cities()
        assert "hayward" not in working
        assert "san_francisco" not in working

    def test_includes_city_when_success_rate_just_above_threshold(
        self, registry_snapshot
    ):
        municipal_registry.MUNICIPAL_REGISTRY["threshold_plus"] = {
            "status": "testing",
            "success_rate": 71,
        }
        assert "threshold_plus" in get_working_cities()

    def test_excludes_city_when_success_rate_equals_threshold(
        self, registry_snapshot
    ):
        # The condition is `success_rate > 70`, strictly greater than.
        # Pinning this kills the `> 70` vs `>= 70` mutant.
        municipal_registry.MUNICIPAL_REGISTRY["threshold_exact"] = {
            "status": "testing",
            "success_rate": 70,
        }
        assert "threshold_exact" not in get_working_cities()

    def test_excludes_city_when_success_rate_just_below_threshold(
        self, registry_snapshot
    ):
        municipal_registry.MUNICIPAL_REGISTRY["threshold_minus"] = {
            "status": "testing",
            "success_rate": 69,
        }
        assert "threshold_minus" not in get_working_cities()

    def test_includes_production_city_even_without_success_rate(
        self, registry_snapshot
    ):
        # status == 'production' short-circuits the success_rate check
        municipal_registry.MUNICIPAL_REGISTRY["prod_only"] = {"status": "production"}
        assert "prod_only" in get_working_cities()

    def test_includes_production_city_with_low_success_rate(self, registry_snapshot):
        # 'production' OR success_rate > 70 — production wins regardless
        municipal_registry.MUNICIPAL_REGISTRY["prod_low"] = {
            "status": "production",
            "success_rate": 10,
        }
        assert "prod_low" in get_working_cities()

    def test_returns_empty_list_when_no_cities_qualify(self, registry_snapshot):
        municipal_registry.MUNICIPAL_REGISTRY.clear()
        municipal_registry.MUNICIPAL_REGISTRY["dud"] = {
            "status": "failed",
            "success_rate": 0,
        }
        assert get_working_cities() == []

    def test_returns_list_type_not_generator(self):
        # Pin list-ness (not a generator) so callers can iterate multiple
        # times and take len(). A bare isinstance check would pass even if
        # the function returned an empty list for every input, so also pin
        # the default-registry count and idempotent re-iteration.
        result = get_working_cities()
        assert isinstance(result, list)
        assert len(result) == 4
        # Generators would be exhausted after one iteration; a list is not.
        assert list(result) == result
        assert len(list(result)) == 4


# ---------------------------------------------------------------------------
# get_priority_targets
# ---------------------------------------------------------------------------


class TestGetPriorityTargets:
    def test_returns_priority_one_cities_before_priority_two(self):
        # petaluma(1), mill_valley(1), novato(2), santa_rosa(2)
        result = get_priority_targets()
        # Priority 1 cities must come before priority 2 cities
        p1_indices = [result.index(c) for c in ("petaluma", "mill_valley")]
        p2_indices = [result.index(c) for c in ("novato", "santa_rosa")]
        assert max(p1_indices) < min(p2_indices)

    def test_returns_all_phase_one_targets(self):
        result = get_priority_targets()
        assert set(result) == {"petaluma", "mill_valley", "novato", "santa_rosa"}
        assert len(result) == 4

    def test_returns_list(self):
        # Pin list-ness (not a generator) — get_priority_targets is consumed
        # by callers that index into it. Combined with a length check so the
        # assertion is not existence-only.
        result = get_priority_targets()
        assert isinstance(result, list)
        assert len(result) == 4
        # A list supports repeated iteration; a generator would not.
        assert list(result) == result


# ---------------------------------------------------------------------------
# make_strategic_decision
# ---------------------------------------------------------------------------


class TestMakeStrategicDecision:
    def test_default_registry_yields_scale_html_approach(self):
        # The real registry has 4 working cities (>= 3), so scale.
        assert make_strategic_decision() == "scale_html_approach"

    def test_returns_scale_html_when_three_working_cities(self, registry_snapshot):
        municipal_registry.MUNICIPAL_REGISTRY.clear()
        # Three production cities → exactly at the threshold
        municipal_registry.MUNICIPAL_REGISTRY.update(
            {
                "a": {"status": "production"},
                "b": {"status": "production"},
                "c": {"status": "production"},
            }
        )
        assert make_strategic_decision() == "scale_html_approach"

    def test_returns_continue_testing_when_two_working_cities(
        self, registry_snapshot
    ):
        municipal_registry.MUNICIPAL_REGISTRY.clear()
        municipal_registry.MUNICIPAL_REGISTRY.update(
            {
                "a": {"status": "production"},
                "b": {"status": "production"},
            }
        )
        assert make_strategic_decision() == "continue_testing"

    def test_returns_explore_api_first_when_many_legistar_few_working(
        self, registry_snapshot
    ):
        municipal_registry.MUNICIPAL_REGISTRY.clear()
        # Zero working cities, three legistar → explore API branch
        municipal_registry.MUNICIPAL_REGISTRY.update(
            {
                "a": {"platform": "legistar"},
                "b": {"platform": "legistar"},
                "c": {"platform": "legistar"},
            }
        )
        assert make_strategic_decision() == "explore_api_first"

    def test_returns_continue_testing_when_two_legistar_zero_working(
        self, registry_snapshot
    ):
        municipal_registry.MUNICIPAL_REGISTRY.clear()
        municipal_registry.MUNICIPAL_REGISTRY.update(
            {
                "a": {"platform": "legistar"},
                "b": {"platform": "legistar"},
            }
        )
        assert make_strategic_decision() == "continue_testing"

    def test_returns_continue_testing_on_empty_registry(self, registry_snapshot):
        municipal_registry.MUNICIPAL_REGISTRY.clear()
        assert make_strategic_decision() == "continue_testing"

    def test_working_cities_branch_beats_legistar_branch(self, registry_snapshot):
        # When both conditions are true, scale_html_approach wins because
        # `if/elif` evaluates the working-cities branch first.
        municipal_registry.MUNICIPAL_REGISTRY.clear()
        municipal_registry.MUNICIPAL_REGISTRY.update(
            {
                "a": {"status": "production", "platform": "legistar"},
                "b": {"status": "production", "platform": "legistar"},
                "c": {"status": "production", "platform": "legistar"},
            }
        )
        assert make_strategic_decision() == "scale_html_approach"

    def test_success_rate_qualifier_counts_toward_working_cities(
        self, registry_snapshot
    ):
        # Three cities qualifying via success_rate > 70 (no 'production' status)
        # should still trigger scale_html_approach.
        municipal_registry.MUNICIPAL_REGISTRY.clear()
        municipal_registry.MUNICIPAL_REGISTRY.update(
            {
                "a": {"status": "legistar_production_ready", "success_rate": 95},
                "b": {"status": "legistar_production_ready", "success_rate": 95},
                "c": {"status": "legistar_production_ready", "success_rate": 86},
            }
        )
        assert make_strategic_decision() == "scale_html_approach"
