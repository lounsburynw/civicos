"""
Tests for cms_platform_detector.py — Municipal CMS platform detection.

Covers:
- CMSPlatformDetector._detect_drupal / _detect_civicplus / _detect_granicus
  (pure regex-scoring logic — no mocks)
- CMSPlatformDetector.detect_cms_platform (HTTP + classification + fallback,
  mocks only the HTTP session, never the subject under test)
- detect_drupal_cities_batch (orchestration layer — patches the detector
  collaborator, asserts on real return structure)
- generate_scaling_recommendations (pure aggregation logic — no mocks)

To run:
    pytest packages/civicos-services/tests/test_cms_platform_detector.py -q --override-ini="addopts="
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from civicos_services.clients.cms_platform_detector import (
    CMSPlatformDetector,
    detect_drupal_cities_batch,
    generate_scaling_recommendations,
)


# ---------------------------------------------------------------------------
# _detect_drupal — pure logic, no mocks
# ---------------------------------------------------------------------------


class TestDetectDrupal:
    def test_empty_html_returns_zero_confidence_and_no_indicators(self):
        detector = CMSPlatformDetector()
        result = detector._detect_drupal("")
        assert result == {"confidence": 0, "indicators": []}

    def test_unrelated_html_returns_zero(self):
        detector = CMSPlatformDetector()
        result = detector._detect_drupal("<html><body>Main Street Cafe</body></html>")
        assert result == {"confidence": 0, "indicators": []}

    def test_generator_meta_alone_gives_confidence_0_5(self):
        detector = CMSPlatformDetector()
        html = '<meta name="generator" content="Drupal 9" />'
        result = detector._detect_drupal(html)
        assert result["confidence"] == pytest.approx(0.5)
        assert result["indicators"] == ["Drupal meta generator"]

    def test_jquery_extend_drupal_settings_gives_confidence_0_4(self):
        detector = CMSPlatformDetector()
        html = "jQuery.extend(Drupal.settings, {});"
        result = detector._detect_drupal(html)
        assert result["confidence"] == pytest.approx(0.4)
        assert result["indicators"] == ["Drupal.settings object"]

    def test_sites_all_themes_path_gives_confidence_0_3(self):
        detector = CMSPlatformDetector()
        html = '<link href="/sites/all/themes/bartik/style.css" />'
        result = detector._detect_drupal(html)
        assert result["confidence"] == pytest.approx(0.3)
        assert result["indicators"] == ["Drupal file structure"]

    def test_sites_all_modules_path_gives_confidence_0_3(self):
        detector = CMSPlatformDetector()
        html = '<script src="/sites/all/modules/custom/app.js"></script>'
        result = detector._detect_drupal(html)
        assert result["confidence"] == pytest.approx(0.3)
        assert result["indicators"] == ["Drupal modules path"]

    def test_drupal_behaviors_gives_confidence_0_3(self):
        detector = CMSPlatformDetector()
        html = "Drupal.behaviors.myModule = { attach: function() {} };"
        result = detector._detect_drupal(html)
        assert result["confidence"] == pytest.approx(0.3)
        assert result["indicators"] == ["Drupal behaviors"]

    def test_confidence_capped_at_1_even_when_raw_points_exceed(self):
        detector = CMSPlatformDetector()
        # Stack every Drupal pattern (raw total = 2.6, cap = 1.0)
        html = (
            '<meta name="generator" content="Drupal 9" />'  # 0.5
            "jQuery.extend(Drupal.settings, {});"           # 0.4
            "/sites/all/themes/bartik/"                      # 0.3
            "/sites/all/modules/custom/"                     # 0.3
            "Drupal.behaviors.x = 1;"                        # 0.3
            "drupal.js"                                       # 0.2
            ".views-row"                                      # 0.2
            ".panels-item"                                    # 0.2
            "jquery_update"                                   # 0.2
        )
        result = detector._detect_drupal(html)
        assert result["confidence"] == 1.0
        # Must surface all 9 distinct indicators (mutation: dropping a pattern would make this fail)
        assert len(result["indicators"]) == 9
        assert set(result["indicators"]) == {
            "Drupal.settings object",
            "Drupal file structure",
            "Drupal modules path",
            "Drupal behaviors",
            "Drupal core JS",
            "Views module classes",
            "Panels module classes",
            "jQuery Update module",
            "Drupal meta generator",
        }

    def test_pattern_matching_is_case_insensitive(self):
        detector = CMSPlatformDetector()
        html = "GENERATOR META DRUPAL 9"
        result = detector._detect_drupal(html)
        assert result["confidence"] == pytest.approx(0.5)
        assert result["indicators"] == ["Drupal meta generator"]

    def test_drupal_settings_plus_themes_path_sums_to_0_7(self):
        """Two stacked indicators add precisely — guards against scoring drift."""
        detector = CMSPlatformDetector()
        html = (
            "jQuery.extend(Drupal.settings, {});"  # 0.4
            "/sites/all/themes/"                    # 0.3
        )
        result = detector._detect_drupal(html)
        assert result["confidence"] == pytest.approx(0.7)
        assert "Drupal.settings object" in result["indicators"]
        assert "Drupal file structure" in result["indicators"]


# ---------------------------------------------------------------------------
# _detect_civicplus — pure logic
# ---------------------------------------------------------------------------


class TestDetectCivicPlus:
    def test_empty_html_returns_zero_confidence(self):
        detector = CMSPlatformDetector()
        result = detector._detect_civicplus("")
        assert result == {"confidence": 0, "indicators": []}

    def test_unrelated_html_returns_zero(self):
        detector = CMSPlatformDetector()
        result = detector._detect_civicplus("<html>Hello world</html>")
        assert result == {"confidence": 0, "indicators": []}

    def test_civicplus_footer_alone_gives_confidence_0_9(self):
        detector = CMSPlatformDetector()
        html = "<footer>Government Websites by CivicPlus</footer>"
        result = detector._detect_civicplus(html)
        assert result["confidence"] == pytest.approx(0.9)
        assert result["indicators"] == ["CivicPlus footer"]

    def test_window_pages_object_alone_gives_confidence_0_4(self):
        detector = CMSPlatformDetector()
        html = "window.Pages = {home:true};"
        result = detector._detect_civicplus(html)
        assert result["confidence"] == pytest.approx(0.4)
        assert result["indicators"] == ["CivicPlus Pages object"]

    def test_calendar_aspx_url_alone_gives_confidence_0_3(self):
        detector = CMSPlatformDetector()
        html = '<a href="/Calendar.aspx">Calendar</a>'
        result = detector._detect_civicplus(html)
        assert result["confidence"] == pytest.approx(0.3)
        assert result["indicators"] == ["CivicPlus calendar URLs"]

    def test_civic_alerts_aspx_url_alone_gives_confidence_0_3(self):
        detector = CMSPlatformDetector()
        html = '<a href="/CivicAlerts.aspx">Alerts</a>'
        result = detector._detect_civicplus(html)
        assert result["confidence"] == pytest.approx(0.3)
        assert result["indicators"] == ["CivicPlus alerts URLs"]

    def test_all_civicplus_patterns_cap_at_one(self):
        detector = CMSPlatformDetector()
        # Raw total: 0.9 + 0.4 + 0.3 + 0.3 + 0.2 + 0.3 + 0.3 = 2.7
        html = (
            "Government Websites by CivicPlus"  # 0.9
            "window.Pages"                       # 0.4
            ".widgetSearch"                      # 0.3
            ".InfoAdvanced"                      # 0.3
            ".fancyButton"                       # 0.2
            "/Calendar.aspx"                     # 0.3
            "/CivicAlerts.aspx"                  # 0.3
        )
        result = detector._detect_civicplus(html)
        assert result["confidence"] == 1.0
        assert len(result["indicators"]) == 7
        assert set(result["indicators"]) == {
            "CivicPlus footer",
            "CivicPlus Pages object",
            "CivicPlus widget classes",
            "CivicPlus info classes",
            "CivicPlus button classes",
            "CivicPlus calendar URLs",
            "CivicPlus alerts URLs",
        }


# ---------------------------------------------------------------------------
# _detect_granicus — pure logic
# ---------------------------------------------------------------------------


class TestDetectGranicus:
    def test_empty_html_returns_zero_confidence(self):
        detector = CMSPlatformDetector()
        result = detector._detect_granicus("")
        assert result == {"confidence": 0, "indicators": []}

    def test_unrelated_html_returns_zero(self):
        detector = CMSPlatformDetector()
        result = detector._detect_granicus("<html>Nothing here</html>")
        assert result == {"confidence": 0, "indicators": []}

    def test_powered_by_granicus_alone_gives_confidence_0_9(self):
        detector = CMSPlatformDetector()
        html = "<footer>Powered by Granicus</footer>"
        result = detector._detect_granicus(html)
        assert result["confidence"] == pytest.approx(0.9)
        assert result["indicators"] == ["Granicus footer"]

    def test_opencities_namespace_alone_gives_confidence_0_5(self):
        detector = CMSPlatformDetector()
        html = "var OpenCities = OpenCities || {};"
        result = detector._detect_granicus(html)
        assert result["confidence"] == pytest.approx(0.5)
        assert result["indicators"] == ["OpenCities namespace"]

    def test_opencities_namespace_with_extra_whitespace_still_matches(self):
        """Whitespace around '=' should not affect the namespace match."""
        detector = CMSPlatformDetector()
        html = "OpenCities=OpenCities;"
        result = detector._detect_granicus(html)
        assert result["confidence"] == pytest.approx(0.5)

    def test_opencities_paths_alone_gives_confidence_0_4(self):
        detector = CMSPlatformDetector()
        html = "OpenCities.Paths.basePath = '/';"
        result = detector._detect_granicus(html)
        assert result["confidence"] == pytest.approx(0.4)
        assert result["indicators"] == ["OpenCities configuration"]

    def test_files_templates_path_alone_gives_confidence_0_3(self):
        detector = CMSPlatformDetector()
        html = '<link href="/files/templates/main.css" />'
        result = detector._detect_granicus(html)
        assert result["confidence"] == pytest.approx(0.3)
        assert result["indicators"] == ["Granicus file structure"]

    def test_all_granicus_patterns_cap_at_one(self):
        detector = CMSPlatformDetector()
        # Raw total: 0.9 + 0.5 + 0.4 + 0.3 + 0.3 + 0.2 + 0.2 = 2.8
        html = (
            "Powered by Granicus"              # 0.9
            "OpenCities = OpenCities"           # 0.5
            "OpenCities.Paths"                  # 0.4
            "/files/templates/"                 # 0.3
            "/files/assets/"                    # 0.3
            ".background-container"             # 0.2
            ".sc-size-mini"                     # 0.2
        )
        result = detector._detect_granicus(html)
        assert result["confidence"] == 1.0
        assert len(result["indicators"]) == 7
        assert set(result["indicators"]) == {
            "Granicus footer",
            "OpenCities namespace",
            "OpenCities configuration",
            "Granicus file structure",
            "Granicus assets path",
            "Granicus container classes",
            "Granicus responsive classes",
        }


# ---------------------------------------------------------------------------
# detect_cms_platform — mocks HTTP layer, tests real classification logic
# ---------------------------------------------------------------------------


def _build_detector_with_response(html, status=200, raise_exc=None):
    """Build a CMSPlatformDetector whose session returns a canned HTML response.

    Only the HTTP layer is mocked — the classification logic runs for real.
    """
    detector = CMSPlatformDetector()
    fake_response = MagicMock()
    fake_response.text = html
    fake_response.status_code = status
    if raise_exc is not None:
        fake_response.raise_for_status.side_effect = raise_exc
    else:
        fake_response.raise_for_status.return_value = None
    detector.session = MagicMock()
    detector.session.get.return_value = fake_response
    return detector


class TestDetectCMSPlatform:
    def test_high_confidence_drupal_returns_berkeley_profile(self):
        html = (
            '<meta name="generator" content="Drupal 9" />'  # 0.5
            "jQuery.extend(Drupal.settings, {});"            # 0.4
        )
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://berkeleyca.gov/")
        assert result["url"] == "https://berkeleyca.gov/"
        assert result["platform"] == "drupal"
        assert result["confidence"] == pytest.approx(0.9)
        assert result["cost_efficiency_prediction"] == "high"
        assert result["recommended_extraction_method"] == "berkeley_cms"
        assert result["similar_to"] == "berkeley"
        assert "Drupal meta generator" in result["indicators"]
        assert "Drupal.settings object" in result["indicators"]

    def test_high_confidence_civicplus_returns_richmond_profile(self):
        html = "<footer>Government Websites by CivicPlus</footer>"  # 0.9
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://www.ci.richmond.ca.us/")
        assert result["platform"] == "civicplus"
        assert result["confidence"] == pytest.approx(0.9)
        assert result["cost_efficiency_prediction"] == "medium"
        assert result["recommended_extraction_method"] == "standard"
        assert result["similar_to"] == "richmond"
        assert result["indicators"] == ["CivicPlus footer"]

    def test_high_confidence_granicus_returns_albany_profile(self):
        html = "<footer>Powered by Granicus</footer>"  # 0.9
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://www.albanyca.gov/")
        assert result["platform"] == "granicus"
        assert result["confidence"] == pytest.approx(0.9)
        assert result["cost_efficiency_prediction"] == "medium"
        assert result["recommended_extraction_method"] == "standard"
        assert result["similar_to"] == "albany"
        assert result["indicators"] == ["Granicus footer"]

    def test_drupal_wins_over_civicplus_when_both_present(self):
        """Drupal is evaluated first — a qualifying Drupal score short-circuits."""
        html = (
            '<meta name="generator" content="Drupal 9" />'  # drupal 0.5
            "jQuery.extend(Drupal.settings, {});"            # drupal 0.4
            "Government Websites by CivicPlus"               # civicplus 0.9
        )
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://mixed.example.com/")
        assert result["platform"] == "drupal"
        assert result["similar_to"] == "berkeley"
        assert result["cost_efficiency_prediction"] == "high"

    # NOTE on fallback-band behavior:
    # The fallback block in detect_cms_platform (roughly lines 93-109) builds
    # a platform_map using dict instances as keys, which is unhashable and raises
    # TypeError. The outer try/except catches this and returns platform="error".
    # As a result, any detection score in the "fallback band" (above 0.3 but
    # at-or-below the platform's gate) collapses to an error result. The tests
    # below pin down that real (currently broken) behavior so a future fix to
    # the fallback block will also update these tests intentionally.

    def test_drupal_at_exactly_0_7_misses_gate_and_triggers_broken_fallback(self):
        """Drupal gate is strictly > 0.7; at 0.7 the fallback path runs and errors out."""
        html = (
            "jQuery.extend(Drupal.settings, {});"  # 0.4
            "/sites/all/themes/"                    # 0.3
        )  # total = 0.7
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://boundary.example.com/")
        assert result["platform"] == "error"
        assert result["error"] == "unhashable type: 'dict'"
        assert result["indicators"] == ["Error: unhashable type: 'dict'"]
        assert result["confidence"] == 0

    def test_civicplus_at_exactly_0_8_misses_gate_and_triggers_broken_fallback(self):
        """CivicPlus gate is strictly > 0.8; at 0.8 the fallback path runs and errors out."""
        # 0.3 (.widgetSearch) + 0.3 (/Calendar.aspx) + 0.2 (.fancyButton) = 0.8
        html = ".widgetSearch/Calendar.aspx.fancyButton"
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://edge.example.com/")
        assert result["platform"] == "error"
        assert result["error"] == "unhashable type: 'dict'"
        assert result["url"] == "https://edge.example.com/"

    def test_granicus_at_exactly_0_8_misses_gate_and_triggers_broken_fallback(self):
        """Granicus gate is strictly > 0.8; at 0.8 the fallback path runs and errors out."""
        # 0.5 (OpenCities namespace) + 0.3 (/files/templates/) = 0.8
        html = "OpenCities = OpenCities/files/templates/"
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://g-edge.example.com/")
        assert result["platform"] == "error"
        assert result["error"] == "unhashable type: 'dict'"

    def test_weak_drupal_signal_hits_broken_fallback(self):
        """Drupal at 0.5 misses the 0.7 gate → fallback runs → broken → error."""
        html = '<meta name="generator" content="Drupal 9" />'  # 0.5
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://weak-drupal.example.com/")
        assert result["platform"] == "error"
        assert result["error"] == "unhashable type: 'dict'"

    def test_drupal_just_above_threshold_0_71_avoids_broken_fallback(self):
        """Drupal just above 0.7 uses the gate path and gets a proper berkeley classification.

        0.5 (generator) + 0.2 (.views-) + 0.2 (.panels-) = 0.9 → gate passes.
        This test guards that the gate at > 0.7 works, distinct from the broken fallback.
        """
        html = (
            '<meta name="generator" content="Drupal 9" />'  # 0.5
            ".views-row"                                      # 0.2
            ".panels-item"                                    # 0.2
        )  # total = 0.9, above 0.7 gate
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://above.example.com/")
        assert result["platform"] == "drupal"
        assert result["confidence"] == pytest.approx(0.9)
        assert result["similar_to"] == "berkeley"
        assert result["cost_efficiency_prediction"] == "high"

    def test_confidence_at_or_below_0_3_stays_unknown(self):
        """Fallback requires strictly > 0.3; 0.2 does not promote."""
        html = "drupal.js"  # 0.2
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://tiny.example.com/")
        assert result["platform"] == "unknown"
        assert result["confidence"] == 0
        assert result["indicators"] == []
        assert result["cost_efficiency_prediction"] == "unknown"
        assert result["recommended_extraction_method"] == "standard"
        assert result["similar_to"] is None

    def test_no_matching_indicators_returns_unknown_platform(self):
        html = "<html><body>Plain content, no CMS fingerprints.</body></html>"
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://plain.example.com/")
        assert result["platform"] == "unknown"
        assert result["confidence"] == 0
        assert result["indicators"] == []
        assert result["url"] == "https://plain.example.com/"

    def test_connection_error_returns_error_result(self):
        detector = CMSPlatformDetector()
        detector.session = MagicMock()
        detector.session.get.side_effect = requests.ConnectionError("network down")
        result = detector.detect_cms_platform("https://down.example.com/")
        assert result["platform"] == "error"
        assert result["confidence"] == 0
        assert result["url"] == "https://down.example.com/"
        assert result["error"] == "network down"
        assert result["indicators"] == ["Error: network down"]
        assert result["cost_efficiency_prediction"] == "unknown"
        assert result["recommended_extraction_method"] == "standard"

    def test_http_500_via_raise_for_status_returns_error_result(self):
        detector = _build_detector_with_response(
            "", status=500, raise_exc=requests.HTTPError("500 Server Error")
        )
        result = detector.detect_cms_platform("https://broken.example.com/")
        assert result["platform"] == "error"
        assert result["error"] == "500 Server Error"
        assert result["indicators"] == ["Error: 500 Server Error"]
        assert result["confidence"] == 0

    def test_session_get_called_with_timeout_10(self):
        detector = _build_detector_with_response("<html></html>")
        result = detector.detect_cms_platform("https://example.com/")
        # Observable behavior: empty HTML yields an "unknown" detection echoing the URL.
        assert result["platform"] == "unknown"
        assert result["confidence"] == 0
        assert result["url"] == "https://example.com/"
        # And the HTTP layer was called exactly once with the configured 10-second timeout
        # and the base URL as the positional argument.
        assert detector.session.get.call_count == 1
        call_kwargs = detector.session.get.call_args.kwargs
        assert call_kwargs.get("timeout") == 10
        assert detector.session.get.call_args.args == ("https://example.com/",)

    def test_user_agent_set_on_session_construction(self):
        detector = CMSPlatformDetector()
        user_agent = detector.session.headers.get("User-Agent", "")
        assert "CivicBot" in user_agent
        assert "Mozilla/5.0" in user_agent
        assert "civic@example.com" in user_agent

    def test_url_field_echoes_input_base_url(self):
        detector = _build_detector_with_response("<html></html>")
        result = detector.detect_cms_platform("https://test.example.com/some/path")
        assert result["url"] == "https://test.example.com/some/path"

    def test_drupal_wins_over_granicus_when_both_present(self):
        """When Drupal > 0.7 and Granicus > 0.8, Drupal still short-circuits first."""
        html = (
            '<meta name="generator" content="Drupal 9" />'  # drupal 0.5
            "jQuery.extend(Drupal.settings, {});"            # drupal 0.4
            "Powered by Granicus"                            # granicus 0.9
        )
        detector = _build_detector_with_response(html)
        result = detector.detect_cms_platform("https://mixed2.example.com/")
        assert result["platform"] == "drupal"
        assert result["similar_to"] == "berkeley"


# ---------------------------------------------------------------------------
# detect_drupal_cities_batch — orchestration layer
# ---------------------------------------------------------------------------


class TestDetectDrupalCitiesBatch:
    def test_returns_per_city_detection_results(self):
        drupal_result = {
            "url": "https://a.example/",
            "platform": "drupal",
            "confidence": 0.95,
            "indicators": ["Drupal.settings object"],
            "cost_efficiency_prediction": "high",
            "recommended_extraction_method": "berkeley_cms",
            "similar_to": "berkeley",
        }
        civicplus_result = {
            "url": "https://b.example/",
            "platform": "civicplus",
            "confidence": 0.9,
            "indicators": ["CivicPlus footer"],
            "cost_efficiency_prediction": "medium",
            "recommended_extraction_method": "standard",
            "similar_to": "richmond",
        }

        def fake_detect(url):
            if url == "https://a.example/":
                return drupal_result
            return civicplus_result

        with patch.object(
            CMSPlatformDetector, "detect_cms_platform", side_effect=fake_detect
        ):
            results = detect_drupal_cities_batch({
                "alpha": "https://a.example/",
                "beta": "https://b.example/",
            })

        assert set(results.keys()) == {"alpha", "beta"}
        assert results["alpha"] == drupal_result
        assert results["beta"] == civicplus_result
        assert results["alpha"]["platform"] == "drupal"
        assert results["beta"]["platform"] == "civicplus"

    def test_empty_city_dict_returns_empty_dict_without_invoking_detector(self):
        with patch.object(CMSPlatformDetector, "detect_cms_platform") as mock_detect:
            results = detect_drupal_cities_batch({})
        assert results == {}
        assert mock_detect.call_count == 0

    def test_preserves_city_name_as_result_key(self):
        canned = {
            "url": "https://x/",
            "platform": "unknown",
            "confidence": 0,
            "indicators": [],
            "cost_efficiency_prediction": "unknown",
            "recommended_extraction_method": "standard",
            "similar_to": None,
        }
        with patch.object(
            CMSPlatformDetector, "detect_cms_platform", return_value=canned
        ):
            results = detect_drupal_cities_batch({"gotham_city": "https://x/"})
        assert list(results.keys()) == ["gotham_city"]
        assert results["gotham_city"] == canned


# ---------------------------------------------------------------------------
# generate_scaling_recommendations — pure aggregation logic
# ---------------------------------------------------------------------------


class TestGenerateScalingRecommendations:
    def test_high_confidence_drupal_added_to_scaling_opportunities(self):
        detections = {
            "berkeley": {"platform": "drupal", "confidence": 0.95},
        }
        result = generate_scaling_recommendations(detections)
        assert len(result["drupal_scaling_opportunities"]) == 1
        opp = result["drupal_scaling_opportunities"][0]
        assert opp["city"] == "berkeley"
        assert opp["confidence"] == 0.95
        assert opp["cost_efficiency_prediction"] == "high"
        assert opp["implementation_priority"] == 1
        assert result["other_platforms"] == {}

    def test_drupal_at_exactly_0_7_goes_to_other_platforms(self):
        """Threshold is strictly > 0.7; exactly 0.7 is not a scaling opportunity."""
        detections = {"marginal": {"platform": "drupal", "confidence": 0.7}}
        result = generate_scaling_recommendations(detections)
        assert result["drupal_scaling_opportunities"] == []
        assert result["other_platforms"] == {"drupal": ["marginal"]}

    def test_drupal_just_above_0_7_promotes_to_scaling(self):
        detections = {"good": {"platform": "drupal", "confidence": 0.71}}
        result = generate_scaling_recommendations(detections)
        assert len(result["drupal_scaling_opportunities"]) == 1
        assert result["drupal_scaling_opportunities"][0]["city"] == "good"
        assert result["other_platforms"] == {}

    def test_low_confidence_drupal_drops_into_other_platforms(self):
        detections = {"weak": {"platform": "drupal", "confidence": 0.5}}
        result = generate_scaling_recommendations(detections)
        assert result["drupal_scaling_opportunities"] == []
        assert result["other_platforms"] == {"drupal": ["weak"]}

    def test_non_drupal_platforms_grouped_by_platform_name(self):
        detections = {
            "richmond": {"platform": "civicplus", "confidence": 0.9},
            "el_cerrito": {"platform": "civicplus", "confidence": 0.9},
            "albany": {"platform": "granicus", "confidence": 0.9},
            "mystery": {"platform": "unknown", "confidence": 0},
        }
        result = generate_scaling_recommendations(detections)
        assert result["drupal_scaling_opportunities"] == []
        assert result["other_platforms"]["civicplus"] == ["richmond", "el_cerrito"]
        assert result["other_platforms"]["granicus"] == ["albany"]
        assert result["other_platforms"]["unknown"] == ["mystery"]

    def test_mixed_results_separate_drupal_from_other(self):
        detections = {
            "berkeley": {"platform": "drupal", "confidence": 0.95},
            "hayward": {"platform": "drupal", "confidence": 0.85},
            "richmond": {"platform": "civicplus", "confidence": 0.9},
        }
        result = generate_scaling_recommendations(detections)
        drupal_cities = [x["city"] for x in result["drupal_scaling_opportunities"]]
        assert set(drupal_cities) == {"berkeley", "hayward"}
        assert result["other_platforms"] == {"civicplus": ["richmond"]}

    def test_cost_savings_scales_linearly_with_drupal_count(self):
        detections = {
            f"city{i}": {"platform": "drupal", "confidence": 0.9}
            for i in range(3)
        }
        result = generate_scaling_recommendations(detections)
        steps = result["recommended_next_steps"]
        assert steps["immediate"] == "Implement berkeley_cms extraction for 3 Drupal cities"
        assert steps["cost_savings_potential"] == "$0.45/month if scaled to Berkeley efficiency"
        assert steps["efficiency_multiplier"] == "3x Berkeley model scaling"

    def test_zero_drupal_cities_produces_zero_savings_string(self):
        detections = {
            "richmond": {"platform": "civicplus", "confidence": 0.9},
        }
        result = generate_scaling_recommendations(detections)
        steps = result["recommended_next_steps"]
        assert steps["immediate"] == "Implement berkeley_cms extraction for 0 Drupal cities"
        assert steps["cost_savings_potential"] == "$0.00/month if scaled to Berkeley efficiency"
        assert steps["efficiency_multiplier"] == "0x Berkeley model scaling"

    def test_empty_detections_produces_fully_empty_recommendations(self):
        result = generate_scaling_recommendations({})
        assert result["drupal_scaling_opportunities"] == []
        assert result["other_platforms"] == {}
        steps = result["recommended_next_steps"]
        assert steps["immediate"] == "Implement berkeley_cms extraction for 0 Drupal cities"
        assert steps["cost_savings_potential"] == "$0.00/month if scaled to Berkeley efficiency"
        assert steps["efficiency_multiplier"] == "0x Berkeley model scaling"

    def test_savings_formula_uses_15_cents_per_drupal_city(self):
        """Guards the 0.15 multiplier — mutation to 0.10 or 0.20 should break this."""
        detections = {
            f"c{i}": {"platform": "drupal", "confidence": 0.9}
            for i in range(10)
        }
        result = generate_scaling_recommendations(detections)
        # 10 * 0.15 = 1.50
        assert (
            result["recommended_next_steps"]["cost_savings_potential"]
            == "$1.50/month if scaled to Berkeley efficiency"
        )
