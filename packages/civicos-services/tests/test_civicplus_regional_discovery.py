"""
Tests for civicplus_regional_discovery.py — Bay Area CivicPlus scaling tool.

Tests cover:
- Target-registry constants (expected keys, URL format)
- detect_civicplus_calendar_urls (mocked HTTP, real URL construction + matching)
- batch_civicplus_discovery (mocked CMS detector + calendar helper, real filtering/scoring)
- generate_deployment_plan (pure logic, real inputs)
- update_automated_civic_refresh (pure logic, real inputs)

To run:
    pytest packages/civicos-services/tests/test_civicplus_regional_discovery.py -q --override-ini="addopts="
"""

from unittest.mock import MagicMock, patch

import pytest

from civicos_services.clients.civicplus_regional_discovery import (
    PRIORITY_CIVICPLUS_TARGETS,
    SECONDARY_CIVICPLUS_TARGETS,
    batch_civicplus_discovery,
    detect_civicplus_calendar_urls,
    generate_deployment_plan,
    update_automated_civic_refresh,
)


# ---------------------------------------------------------------------------
# Target registries
# ---------------------------------------------------------------------------


class TestPriorityCivicPlusTargets:
    def test_contains_antioch_with_expected_url(self):
        assert PRIORITY_CIVICPLUS_TARGETS["antioch"] == "https://www.ci.antioch.ca.us/"

    def test_contains_fremont_with_expected_url(self):
        assert PRIORITY_CIVICPLUS_TARGETS["fremont"] == "https://www.fremont.gov/"

    def test_contains_vallejo_with_expected_url(self):
        assert PRIORITY_CIVICPLUS_TARGETS["vallejo"] == "https://www.cityofvallejo.net/"

    def test_contains_concord_with_expected_url(self):
        assert PRIORITY_CIVICPLUS_TARGETS["concord"] == "https://www.cityofconcord.org/"

    def test_registry_size_is_36(self):
        # 8 Contra Costa + 7 Alameda + 8 Santa Clara + 8 San Mateo + 5 Solano
        assert len(PRIORITY_CIVICPLUS_TARGETS) == 36

    def test_all_urls_are_https(self):
        for city, url in PRIORITY_CIVICPLUS_TARGETS.items():
            assert url.startswith("https://"), f"{city} should use https"

    def test_all_urls_end_with_slash(self):
        for city, url in PRIORITY_CIVICPLUS_TARGETS.items():
            assert url.endswith("/"), f"{city} URL should end with '/'"


class TestSecondaryCivicPlusTargets:
    def test_contains_daly_city_with_expected_url(self):
        assert SECONDARY_CIVICPLUS_TARGETS["daly_city"] == "https://www.dalycity.org/"

    def test_contains_palo_alto_with_expected_url(self):
        assert SECONDARY_CIVICPLUS_TARGETS["palo_alto"] == "https://www.cityofpaloalto.org/"

    def test_contains_mountain_view_with_expected_url(self):
        assert SECONDARY_CIVICPLUS_TARGETS["mountain_view"] == "https://www.mountainview.gov/"

    def test_registry_size_is_22(self):
        # 10 Contra Costa small + 8 Peninsula + 4 South Bay
        assert len(SECONDARY_CIVICPLUS_TARGETS) == 22

    def test_primary_and_secondary_are_disjoint(self):
        overlap = set(PRIORITY_CIVICPLUS_TARGETS) & set(SECONDARY_CIVICPLUS_TARGETS)
        assert overlap == set()


# ---------------------------------------------------------------------------
# detect_civicplus_calendar_urls
# ---------------------------------------------------------------------------


def _mock_session_with_responses(response_map):
    """
    Build a fake requests.Session whose .get(url, ...) returns pre-canned
    MagicMock responses based on the exact URL requested.

    response_map: dict of url -> (status_code, text) or (status_code, text, raise_exc)
    """
    session = MagicMock()

    def fake_get(url, **_kwargs):
        if url not in response_map:
            # Unexpected URL — return a 404
            resp = MagicMock()
            resp.status_code = 404
            resp.text = ""
            return resp
        entry = response_map[url]
        if len(entry) == 3 and entry[2] is not None:
            raise entry[2]
        resp = MagicMock()
        resp.status_code = entry[0]
        resp.text = entry[1]
        return resp

    session.get.side_effect = fake_get
    session.headers = MagicMock()
    return session


class TestDetectCivicPlusCalendarUrls:
    def test_finds_calendar_when_first_url_matches(self):
        session = _mock_session_with_responses({
            "https://example.com/Calendar.aspx": (200, "<html>Calendar.aspx content</html>"),
        })
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.requests.Session",
            return_value=session,
        ):
            urls = detect_civicplus_calendar_urls("https://example.com")
        assert urls == ["https://example.com/Calendar.aspx"]

    def test_stops_after_first_match_does_not_test_remaining(self):
        """The function breaks after first successful match — verify via call count."""
        session = _mock_session_with_responses({
            "https://example.com/Calendar.aspx": (200, "Has calendar.aspx link"),
            "https://example.com/calendar.aspx": (200, "should not be reached"),
        })
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.requests.Session",
            return_value=session,
        ):
            urls = detect_civicplus_calendar_urls("https://example.com")
        assert urls == ["https://example.com/Calendar.aspx"]
        assert session.get.call_count == 1

    def test_eventdetails_indicator_matches(self):
        session = _mock_session_with_responses({
            "https://example.com/Calendar.aspx": (200, "<a>EventDetails?ID=1</a>"),
        })
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.requests.Session",
            return_value=session,
        ):
            urls = detect_civicplus_calendar_urls("https://example.com")
        assert urls == ["https://example.com/Calendar.aspx"]

    def test_civicplus_indicator_matches(self):
        session = _mock_session_with_responses({
            "https://example.com/Calendar.aspx": (200, "Powered by CivicPlus"),
        })
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.requests.Session",
            return_value=session,
        ):
            urls = detect_civicplus_calendar_urls("https://example.com")
        assert urls == ["https://example.com/Calendar.aspx"]

    def test_content_without_indicators_not_returned(self):
        """200 response but no matching indicators → skipped, next URL tried."""
        session = _mock_session_with_responses({
            "https://example.com/Calendar.aspx": (200, "<html>Unrelated content</html>"),
            "https://example.com/calendar.aspx": (404, ""),
            "https://example.com/calendar/": (404, ""),
            "https://example.com/events/": (404, ""),
            "https://example.com/meetings/": (404, ""),
        })
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.requests.Session",
            return_value=session,
        ):
            urls = detect_civicplus_calendar_urls("https://example.com")
        assert urls == []
        # All 5 candidate URLs should have been tried
        assert session.get.call_count == 5

    def test_non_200_status_skipped(self):
        session = _mock_session_with_responses({
            "https://example.com/Calendar.aspx": (404, "calendar.aspx in 404 body"),
        })
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.requests.Session",
            return_value=session,
        ):
            urls = detect_civicplus_calendar_urls("https://example.com")
        assert urls == []

    def test_exception_on_one_url_continues_to_next(self):
        session = _mock_session_with_responses({
            "https://example.com/Calendar.aspx": (200, "", ConnectionError("boom")),
            "https://example.com/calendar.aspx": (200, "civicplus footer"),
        })
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.requests.Session",
            return_value=session,
        ):
            urls = detect_civicplus_calendar_urls("https://example.com")
        assert urls == ["https://example.com/calendar.aspx"]

    def test_all_urls_exception_returns_empty(self):
        session = MagicMock()
        session.get.side_effect = ConnectionError("network down")
        session.headers = MagicMock()
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.requests.Session",
            return_value=session,
        ):
            urls = detect_civicplus_calendar_urls("https://example.com")
        assert urls == []
        # All 5 candidates attempted
        assert session.get.call_count == 5

    def test_trailing_slash_stripped_before_url_construction(self):
        session = _mock_session_with_responses({
            "https://example.com/Calendar.aspx": (200, "calendar.aspx here"),
        })
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.requests.Session",
            return_value=session,
        ):
            urls = detect_civicplus_calendar_urls("https://example.com/")
        # Exactly one slash, not "https://example.com//Calendar.aspx"
        assert urls == ["https://example.com/Calendar.aspx"]

    def test_user_agent_header_applied(self):
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=404, text="")
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.requests.Session",
            return_value=session,
        ):
            urls = detect_civicplus_calendar_urls("https://example.com")
        # With all 404s, no URLs should be returned
        assert urls == []
        # headers.update is called with a dict containing a CivicBot user-agent
        ua_dict = session.headers.update.call_args[0][0]
        assert "CivicBot" in ua_dict["User-Agent"]
        assert "Mozilla/5.0" in ua_dict["User-Agent"]

    def test_timeout_argument_passed_to_get(self):
        session = MagicMock()
        session.get.return_value = MagicMock(status_code=200, text="calendar.aspx match")
        session.headers = MagicMock()
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.requests.Session",
            return_value=session,
        ):
            urls = detect_civicplus_calendar_urls("https://example.com")
        # Function should return the first (matching) candidate URL
        assert urls == ["https://example.com/Calendar.aspx"]
        # And the get() call for it should have carried timeout=10 and allow_redirects=True
        first_call = session.get.call_args_list[0]
        assert first_call.kwargs.get("timeout") == 10
        assert first_call.kwargs.get("allow_redirects") is True


# ---------------------------------------------------------------------------
# batch_civicplus_discovery
# ---------------------------------------------------------------------------


class TestBatchCivicPlusDiscovery:
    def test_civicplus_with_calendar_included_in_results(self):
        targets = {"fremont": "https://www.fremont.gov/"}
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.CMSPlatformDetector"
        ) as mock_cls, patch(
            "civicos_services.clients.civicplus_regional_discovery.detect_civicplus_calendar_urls"
        ) as mock_detect_cal:
            mock_cls.return_value.detect_cms_platform.return_value = {
                "platform": "civicplus",
                "confidence": 0.95,
            }
            mock_detect_cal.return_value = ["https://www.fremont.gov/Calendar.aspx"]
            result = batch_civicplus_discovery(targets)

        assert "fremont" in result
        entry = result["fremont"]
        assert entry["platform"] == "civicplus"
        assert entry["confidence"] == 0.95
        assert entry["calendar_urls"] == ["https://www.fremont.gov/Calendar.aspx"]
        assert entry["status"] == "ready_for_deployment"
        assert entry["cost_efficiency_prediction"] == 0.048
        assert entry["agent_type"] == "civicplus_cms"
        assert entry["base_url"] == "https://www.fremont.gov/"

    def test_fremont_gets_population_tier_1(self):
        targets = {"fremont": "https://www.fremont.gov/"}
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.CMSPlatformDetector"
        ) as mock_cls, patch(
            "civicos_services.clients.civicplus_regional_discovery.detect_civicplus_calendar_urls",
            return_value=["https://www.fremont.gov/Calendar.aspx"],
        ):
            mock_cls.return_value.detect_cms_platform.return_value = {
                "platform": "civicplus",
                "confidence": 0.95,
            }
            result = batch_civicplus_discovery(targets)
        assert result["fremont"]["population_tier"] == 1
        assert result["fremont"]["implementation_priority"] == 1

    def test_concord_gets_population_tier_1(self):
        targets = {"concord": "https://www.cityofconcord.org/"}
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.CMSPlatformDetector"
        ) as mock_cls, patch(
            "civicos_services.clients.civicplus_regional_discovery.detect_civicplus_calendar_urls",
            return_value=["https://www.cityofconcord.org/Calendar.aspx"],
        ):
            mock_cls.return_value.detect_cms_platform.return_value = {
                "platform": "civicplus",
                "confidence": 0.90,
            }
            result = batch_civicplus_discovery(targets)
        assert result["concord"]["population_tier"] == 1

    def test_non_tier_1_city_gets_tier_2(self):
        targets = {"campbell": "https://www.ci.campbell.ca.us/"}
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.CMSPlatformDetector"
        ) as mock_cls, patch(
            "civicos_services.clients.civicplus_regional_discovery.detect_civicplus_calendar_urls",
            return_value=["https://www.ci.campbell.ca.us/Calendar.aspx"],
        ):
            mock_cls.return_value.detect_cms_platform.return_value = {
                "platform": "civicplus",
                "confidence": 0.95,
            }
            result = batch_civicplus_discovery(targets)
        assert result["campbell"]["population_tier"] == 2
        assert result["campbell"]["implementation_priority"] == 2

    def test_low_confidence_civicplus_excluded(self):
        """confidence must be strictly > 0.8 to qualify."""
        targets = {"campbell": "https://www.ci.campbell.ca.us/"}
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.CMSPlatformDetector"
        ) as mock_cls, patch(
            "civicos_services.clients.civicplus_regional_discovery.detect_civicplus_calendar_urls"
        ) as mock_detect_cal:
            mock_cls.return_value.detect_cms_platform.return_value = {
                "platform": "civicplus",
                "confidence": 0.80,  # exactly at threshold → excluded
            }
            result = batch_civicplus_discovery(targets)
        assert result == {}
        # Calendar detection should NOT have been attempted
        mock_detect_cal.assert_not_called()

    def test_non_civicplus_platform_excluded(self):
        targets = {"campbell": "https://www.ci.campbell.ca.us/"}
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.CMSPlatformDetector"
        ) as mock_cls, patch(
            "civicos_services.clients.civicplus_regional_discovery.detect_civicplus_calendar_urls"
        ) as mock_detect_cal:
            mock_cls.return_value.detect_cms_platform.return_value = {
                "platform": "drupal",
                "confidence": 0.99,
            }
            result = batch_civicplus_discovery(targets)
        assert result == {}
        mock_detect_cal.assert_not_called()

    def test_civicplus_without_calendar_urls_excluded(self):
        targets = {"fremont": "https://www.fremont.gov/"}
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.CMSPlatformDetector"
        ) as mock_cls, patch(
            "civicos_services.clients.civicplus_regional_discovery.detect_civicplus_calendar_urls",
            return_value=[],
        ):
            mock_cls.return_value.detect_cms_platform.return_value = {
                "platform": "civicplus",
                "confidence": 0.95,
            }
            result = batch_civicplus_discovery(targets)
        assert result == {}

    def test_exception_during_detection_skips_city(self):
        targets = {
            "antioch": "https://www.ci.antioch.ca.us/",
            "fremont": "https://www.fremont.gov/",
        }
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.CMSPlatformDetector"
        ) as mock_cls, patch(
            "civicos_services.clients.civicplus_regional_discovery.detect_civicplus_calendar_urls",
            return_value=["https://www.fremont.gov/Calendar.aspx"],
        ):
            def fake_detect(url):
                if "antioch" in url:
                    raise RuntimeError("network explosion")
                return {"platform": "civicplus", "confidence": 0.95}

            mock_cls.return_value.detect_cms_platform.side_effect = fake_detect
            result = batch_civicplus_discovery(targets)

        # antioch skipped, fremont still processed
        assert "antioch" not in result
        assert "fremont" in result

    def test_empty_targets_returns_empty_dict(self):
        result = batch_civicplus_discovery({})
        assert result == {}

    def test_error_platform_does_not_crash(self):
        targets = {"campbell": "https://www.ci.campbell.ca.us/"}
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.CMSPlatformDetector"
        ) as mock_cls:
            mock_cls.return_value.detect_cms_platform.return_value = {
                "platform": "error",
                "confidence": 0.0,
            }
            result = batch_civicplus_discovery(targets)
        assert result == {}

    def test_multiple_cities_all_succeed(self):
        targets = {
            "fremont": "https://www.fremont.gov/",
            "campbell": "https://www.ci.campbell.ca.us/",
        }
        with patch(
            "civicos_services.clients.civicplus_regional_discovery.CMSPlatformDetector"
        ) as mock_cls, patch(
            "civicos_services.clients.civicplus_regional_discovery.detect_civicplus_calendar_urls"
        ) as mock_detect_cal:
            mock_cls.return_value.detect_cms_platform.return_value = {
                "platform": "civicplus",
                "confidence": 0.95,
            }
            mock_detect_cal.side_effect = lambda base: [f"{base.rstrip('/')}/Calendar.aspx"]
            result = batch_civicplus_discovery(targets)
        assert set(result.keys()) == {"fremont", "campbell"}
        assert result["fremont"]["population_tier"] == 1
        assert result["campbell"]["population_tier"] == 2


# ---------------------------------------------------------------------------
# generate_deployment_plan
# ---------------------------------------------------------------------------


def _make_discovery(calendar_urls=None, population_tier=2, status="ready_for_deployment"):
    return {
        "base_url": "https://example.com/",
        "platform": "civicplus",
        "confidence": 0.95,
        "calendar_urls": calendar_urls or ["https://example.com/Calendar.aspx"],
        "status": status,
        "population_tier": population_tier,
        "cost_efficiency_prediction": 0.048,
        "implementation_priority": population_tier,
        "agent_type": "civicplus_cms",
    }


class TestGenerateDeploymentPlan:
    def test_empty_discoveries(self):
        plan = generate_deployment_plan({})
        assert plan["total_discoveries"] == 0
        assert plan["tier_1_cities"] == []
        assert plan["tier_2_cities"] == []
        assert plan["deployment_phases"]["phase_1"] == []
        assert plan["deployment_phases"]["phase_2"] == []
        assert plan["deployment_phases"]["phase_3"] == []
        assert plan["cost_analysis"]["estimated_monthly_cost"] == 0.0

    def test_total_discoveries_counts_entries(self):
        discoveries = {
            "fremont": _make_discovery(population_tier=1),
            "campbell": _make_discovery(population_tier=2),
            "antioch": _make_discovery(population_tier=1),
        }
        plan = generate_deployment_plan(discoveries)
        assert plan["total_discoveries"] == 3

    def test_tier_1_and_tier_2_partition(self):
        discoveries = {
            "fremont": _make_discovery(population_tier=1),
            "antioch": _make_discovery(population_tier=1),
            "campbell": _make_discovery(population_tier=2),
            "saratoga": _make_discovery(population_tier=2),
        }
        plan = generate_deployment_plan(discoveries)
        assert set(plan["tier_1_cities"]) == {"fremont", "antioch"}
        assert set(plan["tier_2_cities"]) == {"campbell", "saratoga"}

    def test_monthly_cost_rounds_to_two_decimals(self):
        # 2 cities * 3 events/city * $0.048 = $0.288 → rounds to 0.29
        discoveries = {
            "a": _make_discovery(),
            "b": _make_discovery(),
        }
        plan = generate_deployment_plan(discoveries)
        assert plan["cost_analysis"]["estimated_monthly_cost"] == 0.29

    def test_cost_per_city_is_fixed_value(self):
        plan = generate_deployment_plan({"a": _make_discovery()})
        # 0.048 * 3 = 0.144
        assert plan["cost_analysis"]["cost_per_city"] == pytest.approx(0.144)

    def test_roi_string_format(self):
        plan = generate_deployment_plan({})
        roi = plan["cost_analysis"]["roi_vs_standard"]
        # (0.15 - 0.048) / 0.15 * 100 = 68.0
        assert roi == "68% cost reduction vs standard parsing"

    def test_phase_1_capped_at_five_tier_1(self):
        discoveries = {
            f"tier1_{i}": _make_discovery(population_tier=1) for i in range(7)
        }
        plan = generate_deployment_plan(discoveries)
        assert len(plan["deployment_phases"]["phase_1"]) == 5

    def test_phase_1_contains_fewer_when_less_tier_1(self):
        discoveries = {
            "a": _make_discovery(population_tier=1),
            "b": _make_discovery(population_tier=1),
            "c": _make_discovery(population_tier=2),
        }
        plan = generate_deployment_plan(discoveries)
        assert set(plan["deployment_phases"]["phase_1"]) == {"a", "b"}

    def test_phase_2_capped_at_ten_tier_2(self):
        discoveries = {
            f"tier2_{i}": _make_discovery(population_tier=2) for i in range(14)
        }
        plan = generate_deployment_plan(discoveries)
        assert len(plan["deployment_phases"]["phase_2"]) == 10

    def test_phase_3_contains_cities_after_index_15(self):
        # 18 cities total, phase_3 = list(discoveries.keys())[15:] → 3 entries
        discoveries = {f"city_{i:02d}": _make_discovery(population_tier=2) for i in range(18)}
        plan = generate_deployment_plan(discoveries)
        assert plan["deployment_phases"]["phase_3"] == [
            "city_15",
            "city_16",
            "city_17",
        ]

    def test_phase_3_empty_when_under_16_discoveries(self):
        discoveries = {f"city_{i}": _make_discovery(population_tier=2) for i in range(10)}
        plan = generate_deployment_plan(discoveries)
        assert plan["deployment_phases"]["phase_3"] == []

    def test_implementation_timeline_has_all_four_milestones(self):
        plan = generate_deployment_plan({})
        timeline = plan["implementation_timeline"]
        assert timeline["week_1"] == "Deploy top 3 tier-1 cities"
        assert timeline["week_2"] == "Validate cost efficiency, deploy next 2 tier-1"
        assert timeline["week_3"] == "Begin tier-2 deployment if phase 1 successful"
        assert timeline["month_2"] == "Complete regional CivicPlus coverage"


# ---------------------------------------------------------------------------
# update_automated_civic_refresh
# ---------------------------------------------------------------------------


class TestUpdateAutomatedCivicRefresh:
    def test_empty_discoveries_returns_empty_list(self):
        assert update_automated_civic_refresh({}) == []

    def test_ready_city_produces_one_entry(self):
        discoveries = {
            "fremont": _make_discovery(
                calendar_urls=["https://www.fremont.gov/Calendar.aspx"],
                population_tier=1,
            ),
        }
        entries = update_automated_civic_refresh(discoveries)
        assert len(entries) == 1
        entry = entries[0]
        assert '"fremont":' in entry
        assert '"jurisdiction_id": "city-fremont"' in entry
        assert '"agent_type": "civicplus_cms"' in entry
        assert "https://www.fremont.gov/Calendar.aspx" in entry
        assert '"contact_email": "clerk@fremont.gov"' in entry
        assert '"timezone": "America/Los_Angeles"' in entry
        assert '"cost_efficiency_target": 0.048' in entry

    def test_non_ready_discoveries_excluded(self):
        discoveries = {
            "fremont": _make_discovery(status="ready_for_deployment"),
            "concord": _make_discovery(status="pending"),
            "antioch": _make_discovery(status="needs_review"),
        }
        entries = update_automated_civic_refresh(discoveries)
        assert len(entries) == 1
        assert '"fremont":' in entries[0]

    def test_underscore_in_city_name_becomes_dash_in_jurisdiction_id(self):
        discoveries = {
            "san_leandro": _make_discovery(
                calendar_urls=["https://www.sanleandro.org/Calendar.aspx"],
            ),
        }
        entries = update_automated_civic_refresh(discoveries)
        assert '"jurisdiction_id": "city-san-leandro"' in entries[0]

    def test_contact_email_strips_underscores_entirely(self):
        discoveries = {
            "san_leandro": _make_discovery(),
        }
        entries = update_automated_civic_refresh(discoveries)
        # underscore removed (not replaced with dash) for email
        assert '"contact_email": "clerk@sanleandro.gov"' in entries[0]
        assert "clerk@san_leandro.gov" not in entries[0]
        assert "clerk@san-leandro.gov" not in entries[0]

    def test_multiple_ready_cities_produce_multiple_entries(self):
        discoveries = {
            "a": _make_discovery(),
            "b": _make_discovery(),
            "c": _make_discovery(),
        }
        entries = update_automated_civic_refresh(discoveries)
        assert len(entries) == 3

    def test_all_ready_entries_use_civicplus_cms_agent(self):
        discoveries = {
            "a": _make_discovery(),
            "b": _make_discovery(),
        }
        entries = update_automated_civic_refresh(discoveries)
        for entry in entries:
            assert '"agent_type": "civicplus_cms"' in entry

    def test_calendar_urls_embedded_as_python_list_repr(self):
        discoveries = {
            "fremont": _make_discovery(
                calendar_urls=[
                    "https://www.fremont.gov/Calendar.aspx",
                    "https://www.fremont.gov/events/",
                ],
            ),
        }
        entries = update_automated_civic_refresh(discoveries)
        # Python repr of the list should be present
        assert (
            "['https://www.fremont.gov/Calendar.aspx', 'https://www.fremont.gov/events/']"
            in entries[0]
        )
