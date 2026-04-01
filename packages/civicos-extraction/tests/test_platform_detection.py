"""
Tests for platform detection helper.

Uses mocked HTTP responses to test detection logic without real API calls.
"""

import pytest
from unittest.mock import patch, MagicMock
import requests

from civicos_extraction.platform_detection import (
    DetectionResult,
    detect_platform,
    detect_platform_batch,
    discover_granicus_subdomain,
    discover_legistar_client,
    discover_civicclerk_subdomain,
    discover_escribe_instance,
    discover_simbli_instance,
    discover_platform,
    _extract_client_name,
    _detect_legistar,
    _detect_civicclerk,
    _detect_escribe,
    _detect_simbli,
    _detect_proudcity,
)


class TestExtractClientName:
    """Test URL to client name extraction."""

    def test_cityof_pattern(self):
        """Test cityof{name}.{tld} pattern."""
        assert _extract_client_name("https://www.cityofberkeley.info") == "berkeley"
        assert _extract_client_name("https://www.cityofsanrafael.org") == "sanrafael"
        assert _extract_client_name("https://cityofoakland.org") == "oakland"

    def test_gov_pattern(self):
        """Test {name}.gov pattern."""
        assert _extract_client_name("https://elcerrito.ca.gov") == "elcerrito"
        assert _extract_client_name("https://sanfrancisco.gov") == "sanfrancisco"

    def test_org_pattern(self):
        """Test {name}.org pattern."""
        assert _extract_client_name("https://richmond.org") == "richmond"

    def test_www_removal(self):
        """Test www prefix is removed."""
        assert _extract_client_name("https://www.berkeley.org") == "berkeley"


class TestDetectionResult:
    """Test DetectionResult dataclass."""

    def test_creation(self):
        """Test basic creation."""
        result = DetectionResult(
            source_type="legistar",
            source_id="legistar-berkeley",
            platform_name="Legistar",
            confidence=0.95
        )
        assert result.source_type == "legistar"
        assert result.confidence == 0.95
        assert result.errors == []

    def test_to_dict(self):
        """Test serialization."""
        result = DetectionResult(
            source_type="civicclerk",
            source_id="civicclerk-elcerrito",
            platform_name="CivicClerk",
            confidence=0.90,
            detection_time_ms=150.5,
            metadata={"test": True},
            errors=[]
        )
        d = result.to_dict()
        assert d["source_type"] == "civicclerk"
        assert d["confidence"] == 0.90
        assert d["detection_time_ms"] == 150.5
        assert d["metadata"]["test"] is True

    def test_not_detected(self):
        """Test not-detected result."""
        result = DetectionResult(
            source_type=None,
            source_id=None,
            platform_name=None,
            confidence=0.0,
            errors=["No platform detected"]
        )
        assert result.source_type is None
        assert result.confidence == 0.0
        assert "No platform detected" in result.errors


class TestDetectLegistar:
    """Test Legistar detection strategy."""

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_legistar_detected(self, mock_get):
        """Test successful Legistar detection."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"BodyId": 1, "BodyName": "City Council"},
            {"BodyId": 2, "BodyName": "Planning Commission"}
        ]
        mock_get.return_value = mock_response

        confidence, metadata = _detect_legistar("berkeley", timeout=5)

        assert confidence == 0.95
        assert metadata["body_count"] == 2
        assert metadata["status_code"] == 200

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_legistar_not_found(self, mock_get):
        """Test Legistar 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        confidence, metadata = _detect_legistar("nonexistent", timeout=5)

        assert confidence == 0.0
        assert metadata["status_code"] == 404

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_legistar_timeout(self, mock_get):
        """Test Legistar timeout handling."""
        mock_get.side_effect = requests.exceptions.Timeout()

        confidence, metadata = _detect_legistar("berkeley", timeout=5)

        assert confidence == 0.0
        assert metadata["error"] == "Timeout"

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_legistar_invalid_json(self, mock_get):
        """Test Legistar invalid JSON response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        confidence, metadata = _detect_legistar("berkeley", timeout=5)

        assert confidence == 0.0
        assert "Invalid JSON" in metadata["error"]


class TestDetectCivicClerk:
    """Test CivicClerk detection strategy."""

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_civicclerk_detected_odata(self, mock_get):
        """Test successful CivicClerk detection with OData format."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {"BoardId": 1, "BoardName": "City Council"}
            ]
        }
        mock_get.return_value = mock_response

        confidence, metadata = _detect_civicclerk("elcerritoca", timeout=5)

        assert confidence == 0.95
        assert metadata["board_count"] == 1

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_civicclerk_detected_list(self, mock_get):
        """Test CivicClerk detection with direct list response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"BoardId": 1, "BoardName": "City Council"}
        ]
        mock_get.return_value = mock_response

        confidence, metadata = _detect_civicclerk("hayward", timeout=5)

        # Slightly lower confidence for non-OData format
        assert confidence == 0.90
        assert metadata["board_count"] == 1

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_civicclerk_not_found(self, mock_get):
        """Test CivicClerk 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        confidence, metadata = _detect_civicclerk("nonexistent", timeout=5)

        assert confidence == 0.0


class TestDetectProudCity:
    """Test ProudCity detection strategy."""

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_proudcity_detected_many_types(self, mock_get):
        """Test ProudCity detection with many meeting types."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"""
        <html>
        <body>
            <a href="/city-council-meetings/">City Council</a>
            <a href="/planning-commission-meetings/">Planning</a>
            <a href="/fire-commission-meetings/">Fire</a>
            <a href="/library-board-meetings/">Library</a>
            <a href="/zoning-administrator-hearings/">Zoning</a>
            <a href="/ada-committee-meetings/">ADA</a>
        </body>
        </html>
        """
        mock_get.return_value = mock_response

        confidence, metadata = _detect_proudcity("https://www.cityofsanrafael.org", timeout=5)

        assert confidence == 0.90
        assert metadata["meeting_type_count"] >= 5
        assert "city-council" in metadata["discovered_meeting_types"]

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_proudcity_detected_few_types(self, mock_get):
        """Test ProudCity detection with 2-4 meeting types."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"""
        <html>
        <body>
            <a href="/city-council-meetings/">City Council</a>
            <a href="/planning-commission-meetings/">Planning</a>
        </body>
        </html>
        """
        mock_get.return_value = mock_response

        confidence, metadata = _detect_proudcity("https://example.org", timeout=5)

        assert confidence == 0.75
        assert metadata["meeting_type_count"] == 2

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_proudcity_detected_one_type(self, mock_get):
        """Test ProudCity detection with only one meeting type."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"""
        <html>
        <body>
            <a href="/city-council-meetings/">City Council</a>
        </body>
        </html>
        """
        mock_get.return_value = mock_response

        confidence, metadata = _detect_proudcity("https://example.org", timeout=5)

        assert confidence == 0.50
        assert metadata["meeting_type_count"] == 1

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_proudcity_not_detected(self, mock_get):
        """Test ProudCity not detected when no archives found."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><body>No meeting links here</body></html>"
        mock_get.return_value = mock_response

        confidence, metadata = _detect_proudcity("https://example.org", timeout=5)

        assert confidence == 0.0
        assert metadata["meeting_type_count"] == 0

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_proudcity_page_not_found(self, mock_get):
        """Test ProudCity with 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        confidence, metadata = _detect_proudcity("https://example.org", timeout=5)

        assert confidence == 0.0
        assert "Status 404" in metadata["error"]


class TestDetectPlatform:
    """Test main detect_platform function."""

    @patch('civicos_extraction.platform_detection._detect_legistar')
    @patch('civicos_extraction.platform_detection._detect_civicclerk')
    @patch('civicos_extraction.platform_detection._detect_proudcity')
    def test_detects_legistar(self, mock_pc, mock_cc, mock_leg):
        """Test Legistar is detected when API responds."""
        mock_leg.return_value = (0.95, {"body_count": 5})
        mock_cc.return_value = (0.0, {})
        mock_pc.return_value = (0.0, {})

        result = detect_platform("https://www.cityofberkeley.info")

        assert result.source_type == "legistar"
        assert result.confidence == 0.95
        assert result.platform_name == "Legistar"

    @patch('civicos_extraction.platform_detection._detect_legistar')
    @patch('civicos_extraction.platform_detection._detect_civicclerk')
    @patch('civicos_extraction.platform_detection._detect_proudcity')
    def test_detects_civicclerk(self, mock_pc, mock_cc, mock_leg):
        """Test CivicClerk is detected when API responds."""
        mock_leg.return_value = (0.0, {})
        mock_cc.return_value = (0.95, {"board_count": 3})
        mock_pc.return_value = (0.0, {})

        result = detect_platform("https://elcerrito.ca.gov")

        assert result.source_type == "civicclerk"
        assert result.confidence == 0.95

    @patch('civicos_extraction.platform_detection._detect_legistar')
    @patch('civicos_extraction.platform_detection._detect_civicclerk')
    @patch('civicos_extraction.platform_detection._detect_proudcity')
    def test_detects_proudcity(self, mock_pc, mock_cc, mock_leg):
        """Test ProudCity is detected when scraping finds archives."""
        mock_leg.return_value = (0.0, {})
        mock_cc.return_value = (0.0, {})
        mock_pc.return_value = (0.90, {"meeting_type_count": 6})

        result = detect_platform("https://www.cityofsanrafael.org")

        assert result.source_type == "proudcity"
        assert result.confidence == 0.90

    @patch('civicos_extraction.platform_detection._detect_legistar')
    @patch('civicos_extraction.platform_detection._detect_civicclerk')
    @patch('civicos_extraction.platform_detection._detect_proudcity')
    def test_no_platform_detected(self, mock_pc, mock_cc, mock_leg):
        """Test no platform detected returns appropriate result."""
        mock_leg.return_value = (0.0, {})
        mock_cc.return_value = (0.0, {})
        mock_pc.return_value = (0.0, {})

        result = detect_platform("https://unknown-city.org")

        assert result.source_type is None
        assert result.confidence == 0.0
        assert "No platform detected" in result.errors

    @patch('civicos_extraction.platform_detection._detect_legistar')
    @patch('civicos_extraction.platform_detection._detect_civicclerk')
    @patch('civicos_extraction.platform_detection._detect_proudcity')
    def test_highest_confidence_wins(self, mock_pc, mock_cc, mock_leg):
        """Test highest confidence platform is selected."""
        mock_leg.return_value = (0.50, {})  # Low confidence
        mock_cc.return_value = (0.0, {})
        mock_pc.return_value = (0.90, {"meeting_type_count": 6})  # High confidence

        result = detect_platform("https://www.cityofsanrafael.org")

        # ProudCity should win with 0.90 > 0.50
        assert result.source_type == "proudcity"
        assert result.confidence == 0.90

    @patch('civicos_extraction.platform_detection._detect_legistar')
    @patch('civicos_extraction.platform_detection._detect_civicclerk')
    @patch('civicos_extraction.platform_detection._detect_proudcity')
    def test_custom_jurisdiction_id(self, mock_pc, mock_cc, mock_leg):
        """Test custom jurisdiction_id is used."""
        mock_leg.return_value = (0.0, {})
        mock_cc.return_value = (0.0, {})
        mock_pc.return_value = (0.85, {})

        result = detect_platform(
            "https://www.cityofsanrafael.org",
            jurisdiction_id="custom-san-rafael"
        )

        assert result.source_id == "proudcity-custom-san-rafael"


class TestDetectPlatformBatch:
    """Test batch platform detection."""

    @patch('civicos_extraction.platform_detection.detect_platform')
    def test_batch_detection(self, mock_detect):
        """Test batch detection calls detect_platform for each URL."""
        mock_detect.side_effect = [
            DetectionResult("legistar", "legistar-berkeley", "Legistar", 0.95),
            DetectionResult("civicclerk", "civicclerk-elcerrito", "CivicClerk", 0.95),
        ]

        results = detect_platform_batch([
            "https://www.cityofberkeley.info",
            "https://elcerrito.ca.gov"
        ])

        assert len(results) == 2
        assert results["https://www.cityofberkeley.info"].source_type == "legistar"
        assert results["https://elcerrito.ca.gov"].source_type == "civicclerk"

    @patch('civicos_extraction.platform_detection.detect_platform')
    def test_batch_handles_errors(self, mock_detect):
        """Test batch detection handles errors gracefully."""
        mock_detect.side_effect = [
            DetectionResult("legistar", "legistar-berkeley", "Legistar", 0.95),
            Exception("Network error"),
        ]

        results = detect_platform_batch([
            "https://www.cityofberkeley.info",
            "https://broken.org"
        ])

        assert len(results) == 2
        assert results["https://www.cityofberkeley.info"].source_type == "legistar"
        assert results["https://broken.org"].source_type is None
        assert "Network error" in results["https://broken.org"].errors


class TestDiscoverGranicusSubdomain:
    """Test Granicus subdomain auto-discovery."""

    @patch('civicos_extraction.platform_detection.requests.get')
    @patch('civicos_extraction.platform_detection.requests.head')
    def test_discovers_simple_slug(self, mock_head, mock_get):
        """Test discovery with simple city slug (e.g., dublin)."""
        # Root page check succeeds for first pattern
        mock_head.return_value = MagicMock(status_code=200, url="https://dublin.granicus.com/")

        # ViewPublisher returns table HTML
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><body><table><tr><td>Meeting</td></tr></table></body></html>'
        mock_get.return_value = mock_response

        result = discover_granicus_subdomain("Dublin")
        assert result is not None
        assert result["subdomain"] == "dublin"
        assert result["view_id"] == 1
        assert result["table_count"] == 1

    @patch('civicos_extraction.platform_detection.requests.get')
    @patch('civicos_extraction.platform_detection.requests.head')
    def test_discovers_cityof_pattern(self, mock_head, mock_get):
        """Test discovery with cityof prefix pattern."""
        # First pattern fails, second succeeds
        def head_side_effect(url, **kwargs):
            resp = MagicMock()
            if "cityofmillvalley" in url:
                resp.status_code = 200
            else:
                resp.status_code = 404
            return resp

        mock_head.side_effect = head_side_effect

        # view_id=1 returns no tables, view_id=2 returns tables
        call_count = [0]
        def get_side_effect(url, **kwargs):
            call_count[0] += 1
            resp = MagicMock()
            if "view_id=2" in url:
                resp.status_code = 200
                resp.text = '<html><body><table><tr><td>Meeting</td></tr></table></body></html>'
            else:
                resp.status_code = 200
                resp.text = '<html><body>No tables</body></html>'
            return resp

        mock_get.side_effect = get_side_effect

        result = discover_granicus_subdomain("Mill Valley")
        assert result is not None
        assert result["subdomain"] == "cityofmillvalley"
        assert result["view_id"] == 2

    @patch('civicos_extraction.platform_detection.requests.head')
    def test_returns_none_when_not_found(self, mock_head):
        """Test returns None when no Granicus instance found."""
        mock_head.return_value = MagicMock(status_code=404)

        result = discover_granicus_subdomain("Nonexistent City")
        assert result is None

    def test_slug_generation(self):
        """Test city name to slug conversion."""
        # Test indirectly via candidate generation
        import re
        city_name = "San Anselmo"
        slug = re.sub(r"[\s\-]+", "", city_name.lower().strip())
        assert slug == "sananselmo"

        city_name = "Mill Valley"
        slug = re.sub(r"[\s\-]+", "", city_name.lower().strip())
        assert slug == "millvalley"


class TestDiscoverLegistarClient:
    """Test Legistar client auto-discovery."""

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_discovers_simple_slug(self, mock_get):
        """Test discovery with simple city slug (e.g., berkeley)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"BodyId": 1, "BodyName": "City Council"},
            {"BodyId": 2, "BodyName": "Planning Commission"},
        ]
        mock_get.return_value = mock_response

        result = discover_legistar_client("Berkeley")
        assert result is not None
        assert result["client_name"] == "berkeley"
        assert result["body_count"] == 2

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_discovers_cityof_pattern(self, mock_get):
        """Test discovery with cityof prefix (first two patterns fail)."""
        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "cityofberkeley" in url:
                resp.status_code = 200
                resp.json.return_value = [{"BodyId": 1, "BodyName": "Council"}]
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError()
            return resp

        mock_get.side_effect = get_side_effect

        result = discover_legistar_client("Berkeley")
        assert result is not None
        assert result["client_name"] == "cityofberkeley"

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_returns_none_when_not_found(self, mock_get):
        """Test returns None when no Legistar instance found."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = discover_legistar_client("Nonexistent City")
        assert result is None

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_skips_empty_body_list(self, mock_get):
        """Test skips responses with empty body list."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        result = discover_legistar_client("EmptyCity")
        assert result is None


class TestDiscoverCivicClerkSubdomain:
    """Test CivicClerk subdomain auto-discovery."""

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_discovers_slug_state_pattern(self, mock_get):
        """Test discovery with slug+state pattern (e.g., elcerritoca)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "value": [
                {"BoardId": 1, "BoardName": "City Council"},
            ]
        }
        mock_get.return_value = mock_response

        result = discover_civicclerk_subdomain("El Cerrito", state="ca")
        assert result is not None
        assert result["subdomain"] == "elcerritoca"
        assert result["board_count"] == 1

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_discovers_plain_slug(self, mock_get):
        """Test discovery with plain slug (first pattern fails)."""
        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "elcerritoca" in url:
                resp.status_code = 404
                resp.json.side_effect = ValueError()
            elif "elcerrito.api" in url:
                resp.status_code = 200
                resp.json.return_value = {"value": [{"BoardId": 1}]}
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError()
            return resp

        mock_get.side_effect = get_side_effect

        result = discover_civicclerk_subdomain("El Cerrito")
        assert result is not None
        assert result["subdomain"] == "elcerrito"

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_returns_none_when_not_found(self, mock_get):
        """Test returns None when no CivicClerk instance found."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = discover_civicclerk_subdomain("Nonexistent City")
        assert result is None

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_handles_list_response(self, mock_get):
        """Test handles direct list response (non-OData)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"BoardId": 1, "BoardName": "Council"}]
        mock_get.return_value = mock_response

        result = discover_civicclerk_subdomain("Hayward")
        assert result is not None
        assert result["board_count"] == 1


class TestDiscoverPlatform:
    """Test the unified discover_platform orchestrator."""

    @patch('civicos_extraction.platform_detection.discover_legistar_client')
    def test_discovers_legistar(self, mock_legistar):
        """Test returns Legistar when API responds."""
        mock_legistar.return_value = {
            "client_name": "berkeley",
            "body_count": 5,
            "url": "https://webapi.legistar.com/v1/berkeley/bodies",
        }

        result = discover_platform("Berkeley", "ca")
        assert result is not None
        assert result["platform"] == "legistar"
        assert result["confidence"] == 0.95
        assert result["details"]["client_name"] == "berkeley"

    @patch('civicos_extraction.platform_detection.discover_legistar_client')
    @patch('civicos_extraction.platform_detection.discover_civicclerk_subdomain')
    def test_discovers_civicclerk(self, mock_cc, mock_leg):
        """Test falls through to CivicClerk when Legistar fails."""
        mock_leg.return_value = None
        mock_cc.return_value = {
            "subdomain": "elcerritoca",
            "board_count": 3,
            "url": "https://elcerritoca.api.civicclerk.com/v1/Boards",
        }

        result = discover_platform("El Cerrito", "ca")
        assert result is not None
        assert result["platform"] == "civicclerk"

    @patch('civicos_extraction.platform_detection.discover_legistar_client')
    @patch('civicos_extraction.platform_detection.discover_civicclerk_subdomain')
    @patch('civicos_extraction.platform_detection.discover_granicus_subdomain')
    def test_discovers_granicus(self, mock_gran, mock_cc, mock_leg):
        """Test falls through to Granicus when Legistar+CivicClerk fail."""
        mock_leg.return_value = None
        mock_cc.return_value = None
        mock_gran.return_value = {
            "subdomain": "dublin",
            "view_id": 1,
            "url": "https://dublin.granicus.com/ViewPublisher.php?view_id=1",
            "table_count": 3,
        }

        result = discover_platform("Dublin", "ca")
        assert result is not None
        assert result["platform"] == "granicus"

    @patch('civicos_extraction.platform_detection.discover_legistar_client')
    @patch('civicos_extraction.platform_detection.discover_civicclerk_subdomain')
    @patch('civicos_extraction.platform_detection.discover_granicus_subdomain')
    @patch('civicos_extraction.platform_detection._detect_proudcity')
    def test_discovers_proudcity(self, mock_pc, mock_gran, mock_cc, mock_leg):
        """Test falls through to ProudCity website guessing."""
        mock_leg.return_value = None
        mock_cc.return_value = None
        mock_gran.return_value = None
        mock_pc.return_value = (0.90, {"meeting_type_count": 6, "discovered_meeting_types": ["city-council"]})

        result = discover_platform("San Rafael", "ca")
        assert result is not None
        assert result["platform"] == "proudcity"

    @patch('civicos_extraction.platform_detection.discover_legistar_client')
    @patch('civicos_extraction.platform_detection.discover_civicclerk_subdomain')
    @patch('civicos_extraction.platform_detection.discover_granicus_subdomain')
    @patch('civicos_extraction.platform_detection._detect_proudcity')
    def test_returns_none_when_nothing_found(self, mock_pc, mock_gran, mock_cc, mock_leg):
        """Test returns None when no platform found."""
        mock_leg.return_value = None
        mock_cc.return_value = None
        mock_gran.return_value = None
        mock_pc.return_value = (0.0, {"meeting_type_count": 0})

        result = discover_platform("Unknown City", "ca")
        assert result is None


# ── Geocoding & State Slug Tests ──────────────────────────────────


from civicos_extraction.onboard import geocode_city, _state_abbrev_to_slug


class TestStateAbbrevToSlug:
    """Test state abbreviation to jurisdiction slug conversion."""

    def test_california(self):
        assert _state_abbrev_to_slug("CA") == "california"

    def test_texas(self):
        assert _state_abbrev_to_slug("TX") == "texas"

    def test_new_york(self):
        assert _state_abbrev_to_slug("NY") == "new-york"

    def test_north_carolina(self):
        assert _state_abbrev_to_slug("NC") == "north-carolina"

    def test_dc(self):
        assert _state_abbrev_to_slug("DC") == "district-of-columbia"

    def test_lowercase_input(self):
        assert _state_abbrev_to_slug("or") == "oregon"

    def test_unknown_abbrev(self):
        assert _state_abbrev_to_slug("ZZ") == "zz"

    def test_uk_england(self):
        assert _state_abbrev_to_slug("ENG") == "england"

    def test_uk_scotland(self):
        assert _state_abbrev_to_slug("SCT") == "scotland"


def _mock_geocode_response(city, county, state_long, state_abbrev, zip_code):
    """Build a mock Google Maps geocoding API response."""
    components = [
        {"long_name": city, "short_name": city, "types": ["locality"]},
        {"long_name": state_long, "short_name": state_abbrev, "types": ["administrative_area_level_1"]},
        {"long_name": zip_code, "short_name": zip_code, "types": ["postal_code"]},
        {"long_name": "United States", "short_name": "US", "types": ["country"]},
    ]
    if county:
        components.insert(1, {"long_name": county, "short_name": county, "types": ["administrative_area_level_2"]})
    return {
        "status": "OK",
        "results": [{"address_components": components}],
    }


class TestGeocodeCity:
    """Test geocode_city() with mocked API responses."""

    @patch("civicos_extraction.onboard.requests.get")
    def test_california_city(self, mock_get):
        """Berkeley, CA should get state-california parent."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_geocode_response(
            "Berkeley", "Alameda County", "California", "CA", "94704"
        )
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = geocode_city("Berkeley", "CA", api_key="test-key")
        assert result is not None
        assert result["parent_jurisdictions"] == [
            "county-alameda", "state-california", "country-united-states"
        ]

    @patch("civicos_extraction.onboard.requests.get")
    def test_texas_city(self, mock_get):
        """Austin, TX should get state-texas parent, not state-california."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_geocode_response(
            "Austin", "Travis County", "Texas", "TX", "78701"
        )
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = geocode_city("Austin", "TX", api_key="test-key")
        assert result is not None
        assert result["parent_jurisdictions"] == [
            "county-travis", "state-texas", "country-united-states"
        ]
        assert result["state"] == "Texas"
        assert result["state_abbrev"] == "TX"

    @patch("civicos_extraction.onboard.requests.get")
    def test_new_york_no_county(self, mock_get):
        """New York City has no county in geocoding response."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_geocode_response(
            "New York", "", "New York", "NY", "10001"
        )
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = geocode_city("New York", "NY", api_key="test-key")
        assert result is not None
        assert result["parent_jurisdictions"] == [
            "state-new-york", "country-united-states"
        ]

    def test_no_api_key(self):
        """Should return None when no API key is available."""
        with patch.dict("os.environ", {}, clear=True):
            result = geocode_city("Berkeley", "CA", api_key=None)
        assert result is None

    @patch("civicos_extraction.onboard.requests.get")
    def test_api_failure(self, mock_get):
        """Should return None on API failure."""
        mock_get.side_effect = requests.RequestException("timeout")
        result = geocode_city("Berkeley", "CA", api_key="test-key")
        assert result is None

    @patch("civicos_extraction.onboard.requests.get")
    def test_multi_word_state(self, mock_get):
        """West Virginia should become state-west-virginia."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = _mock_geocode_response(
            "Charleston", "Kanawha County", "West Virginia", "WV", "25301"
        )
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = geocode_city("Charleston", "WV", api_key="test-key")
        assert result is not None
        assert "state-west-virginia" in result["parent_jurisdictions"]

    @patch("civicos_extraction.onboard.requests.get")
    def test_canadian_city(self, mock_get):
        """Toronto, ON should get province-ontario → country-canada chain."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": "OK",
            "results": [{
                "address_components": [
                    {"long_name": "Toronto", "short_name": "Toronto", "types": ["locality"]},
                    {"long_name": "Ontario", "short_name": "ON", "types": ["administrative_area_level_1"]},
                    {"long_name": "M5V", "short_name": "M5V", "types": ["postal_code"]},
                    {"long_name": "Canada", "short_name": "CA", "types": ["country"]},
                ],
            }],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = geocode_city("Toronto", "ON", api_key="test-key")
        assert result is not None
        assert result["parent_jurisdictions"] == [
            "province-ontario", "country-canada"
        ]
        assert result["country"] == "Canada"

    @patch("civicos_extraction.onboard.requests.get")
    def test_uk_city(self, mock_get):
        """Manchester, UK should get country-united-kingdom (flat)."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "status": "OK",
            "results": [{
                "address_components": [
                    {"long_name": "Manchester", "short_name": "Manchester", "types": ["locality"]},
                    {"long_name": "Greater Manchester", "short_name": "Greater Manchester", "types": ["administrative_area_level_2"]},
                    {"long_name": "England", "short_name": "England", "types": ["administrative_area_level_1"]},
                    {"long_name": "M1", "short_name": "M1", "types": ["postal_code"]},
                    {"long_name": "United Kingdom", "short_name": "GB", "types": ["country"]},
                ],
            }],
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = geocode_city("Manchester", "UK", api_key="test-key")
        assert result is not None
        assert result["parent_jurisdictions"] == ["country-united-kingdom"]
        assert result["country"] == "United Kingdom"


# ── Track A: Platform Discovery Hardening Tests ─────────────────


class TestDiscoverCivicClerkMultiState:
    """Test CivicClerk discovery with non-CA states."""

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_discovers_tx_subdomain(self, mock_get):
        """Texas city uses slug+tx pattern (e.g., austintx)."""
        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "austintx.api.civicclerk.com" in url:
                resp.status_code = 200
                resp.json.return_value = {"value": [{"BoardId": 1}]}
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError()
            return resp

        mock_get.side_effect = get_side_effect

        result = discover_civicclerk_subdomain("Austin", state="tx")
        assert result is not None
        assert result["subdomain"] == "austintx"

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_discovers_townof_pattern(self, mock_get):
        """Town-of pattern works for small municipalities."""
        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "townofelcerrito.api.civicclerk.com" in url:
                resp.status_code = 200
                resp.json.return_value = {"value": [{"BoardId": 1}]}
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError()
            return resp

        mock_get.side_effect = get_side_effect

        result = discover_civicclerk_subdomain("El Cerrito", state="ca")
        assert result is not None
        assert result["subdomain"] == "townofelcerrito"


class TestDiscoverLegistarCounty:
    """Test Legistar discovery with county/town patterns."""

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_discovers_countyof_pattern(self, mock_get):
        """County-of pattern matches (e.g., countyofmarin)."""
        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "countyofmarin" in url:
                resp.status_code = 200
                resp.json.return_value = [{"BodyId": 1, "BodyName": "BOS"}]
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError()
            return resp

        mock_get.side_effect = get_side_effect

        result = discover_legistar_client("Marin", state="ca")
        assert result is not None
        assert result["client_name"] == "countyofmarin"

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_discovers_townof_pattern(self, mock_get):
        """Town-of pattern matches."""
        def get_side_effect(url, **kwargs):
            resp = MagicMock()
            if "townofsananselmo" in url:
                resp.status_code = 200
                resp.json.return_value = [{"BodyId": 1, "BodyName": "TC"}]
            else:
                resp.status_code = 404
                resp.json.side_effect = ValueError()
            return resp

        mock_get.side_effect = get_side_effect

        result = discover_legistar_client("San Anselmo", state="ca")
        assert result is not None
        assert result["client_name"] == "townofsananselmo"


class TestDiscoverPlatformProudCityGov:
    """Test ProudCity discovery with .gov TLDs."""

    @patch('civicos_extraction.platform_detection.discover_legistar_client')
    @patch('civicos_extraction.platform_detection.discover_civicclerk_subdomain')
    @patch('civicos_extraction.platform_detection.discover_granicus_subdomain')
    @patch('civicos_extraction.platform_detection._detect_proudcity')
    def test_discovers_gov_url(self, mock_pc, mock_gran, mock_cc, mock_leg):
        """ProudCity discovery tries .gov URLs."""
        mock_leg.return_value = None
        mock_cc.return_value = None
        mock_gran.return_value = None

        def pc_side_effect(url, **kwargs):
            if url.endswith(".gov"):
                return (0.90, {"meeting_type_count": 5})
            return (0.0, {"meeting_type_count": 0})

        mock_pc.side_effect = pc_side_effect

        result = discover_platform("Test City", "ca")
        assert result is not None
        assert result["platform"] == "proudcity"
        assert ".gov" in result["details"]["url"]


# ── Track B: Body Discovery Tests ───────────────────────────────


class TestDiscoverLegistarBodies:
    """Test Legistar body discovery via _discover_legistar."""

    def test_discovers_bodies(self):
        """Bodies are extracted and keyed correctly."""
        from civicos_extraction.onboard import _discover_legistar

        mock_client = MagicMock()
        mock_client.get_bodies.return_value = [
            {"BodyId": 1, "BodyName": "City Council"},
            {"BodyId": 2, "BodyName": "Planning Commission"},
            {"BodyId": 3, "BodyName": "Zoning Board of Appeals"},
        ]

        with patch("civicos_extraction.clients.legistar.LegistarClient", return_value=mock_client):
            result = _discover_legistar("berkeley", "city-berkeley")

        assert result["discovered_bodies"]["city_council"] == "1"
        assert result["discovered_bodies"]["planning_commission"] == "2"
        assert result["discovered_bodies"]["zoning_board_of_appeals"] == "3"
        assert result["config"]["source_type"] == "legistar"
        assert result["config"]["archives"] == result["discovered_bodies"]


class TestDiscoverCivicClerkBoards:
    """Test CivicClerk board discovery via _discover_civicclerk."""

    def test_discovers_boards(self):
        """Boards are extracted and keyed correctly."""
        from civicos_extraction.onboard import _discover_civicclerk

        mock_client = MagicMock()
        mock_client.get_boards.return_value = [
            {"BoardId": 10, "BoardName": "City Council"},
            {"BoardId": 20, "BoardName": "Design Review Board"},
        ]

        with patch("civicos_extraction.clients.civicclerk.CivicClerkClient", return_value=mock_client):
            result = _discover_civicclerk("elcerritoca", "city-el-cerrito")

        assert result["discovered_bodies"]["city_council"] == "10"
        assert result["discovered_bodies"]["design_review_board"] == "20"
        assert result["config"]["source_type"] == "civicclerk"


# ── Track C: International Support Tests ─────────────────────────


from civicos_extraction.onboard import _CANADIAN_PROVINCES


class TestCanadianProvinces:
    """Test Canadian province support."""

    def test_ontario_slug(self):
        assert _state_abbrev_to_slug("ON") == "ontario"

    def test_british_columbia_slug(self):
        assert _state_abbrev_to_slug("BC") == "british-columbia"

    def test_quebec_slug(self):
        assert _state_abbrev_to_slug("QC") == "quebec"

    def test_us_states_still_work(self):
        """US states are checked first and still work."""
        assert _state_abbrev_to_slug("CA") == "california"
        assert _state_abbrev_to_slug("TX") == "texas"


# ── State=None Behavior Tests ──────────────────────────────────


class TestStateNoneBehavior:
    """Test that discovery functions work with state=None."""

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_legistar_discovers_without_state(self, mock_get):
        """Legistar discovery works without state (fewer candidates)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"BodyId": 1, "BodyName": "City Council"},
        ]
        mock_get.return_value = mock_response

        result = discover_legistar_client("Berkeley", state=None)
        assert result is not None
        assert result["client_name"] == "berkeley"

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_civicclerk_discovers_without_state(self, mock_get):
        """CivicClerk discovery works without state."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"value": [{"BoardId": 1}]}
        mock_get.return_value = mock_response

        result = discover_civicclerk_subdomain("Hayward", state=None)
        assert result is not None
        assert result["subdomain"] == "hayward"

    @patch('civicos_extraction.platform_detection.requests.get')
    @patch('civicos_extraction.platform_detection.requests.head')
    def test_granicus_discovers_without_state(self, mock_head, mock_get):
        """Granicus discovery works without state (no state-suffix candidates)."""
        mock_head.return_value = MagicMock(status_code=200)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html><body><table><tr><td>Meeting</td></tr></table></body></html>'
        mock_get.return_value = mock_response

        result = discover_granicus_subdomain("Dublin", state=None)
        assert result is not None
        assert result["subdomain"] == "dublin"

    def test_onboard_requires_state_with_city_name(self):
        """onboard_jurisdiction errors when city_name given without state."""
        from civicos_extraction.onboard import onboard_jurisdiction
        result = onboard_jurisdiction("", city_name="Berkeley", state=None)
        assert not result.success
        assert "state is required" in result.errors[0]


# ── International Support Tests ──────────────────────────────────


class TestInternationalErrorMessages:
    """Test international city handling."""

    @patch('civicos_extraction.platform_detection.discover_legistar_client')
    @patch('civicos_extraction.platform_detection.discover_civicclerk_subdomain')
    @patch('civicos_extraction.platform_detection.discover_granicus_subdomain')
    @patch('civicos_extraction.platform_detection._detect_proudcity')
    def test_intl_city_returns_none(self, mock_pc, mock_gran, mock_cc, mock_leg):
        """International city with no US platform returns None."""
        mock_leg.return_value = None
        mock_cc.return_value = None
        mock_gran.return_value = None
        mock_pc.return_value = (0.0, {"meeting_type_count": 0})

        result = discover_platform("Manchester", state="ENG")
        assert result is None


# ── Source Factory Tests ─────────────────────────────────────────


class TestSourceFactory:
    """Test create_source factory from clients.factory."""

    def test_granicus_source(self):
        """Factory creates GranicusSource for granicus type."""
        from civicos_extraction.clients.factory import create_source
        from civicos_extraction.clients.base import ExtractionConfig

        config = ExtractionConfig(
            source_id="granicus-test",
            source_type="granicus",
            jurisdiction_id="city-test",
            base_url="https://test.granicus.com",
            metadata={"granicus_domain": "test"},
        )
        source = create_source(config)
        assert source is not None

    def test_unsupported_type_raises(self):
        """Factory raises ValueError for unsupported source_type."""
        from civicos_extraction.clients.factory import create_source
        from civicos_extraction.clients.base import ExtractionConfig

        config = ExtractionConfig(
            source_id="unknown-test",
            source_type="unknown_platform",
            jurisdiction_id="city-test",
            base_url="https://example.com",
        )
        with pytest.raises(ValueError, match="Unsupported source_type"):
            create_source(config)


# ── Pipeline Handoff Tests ───────────────────────────────────────


class TestOnboardPipelineHandoff:
    """Test run_pipeline parameter in onboard_jurisdiction."""

    def test_progress_callback_invoked(self):
        """Progress callback is called during onboarding."""
        from civicos_extraction.onboard import onboard_jurisdiction

        steps = []

        def on_progress(step, message):
            steps.append(step)

        with patch("civicos_extraction.onboard.detect_platform") as mock_detect:
            mock_detect.return_value = MagicMock(
                source_type="proudcity",
                source_id="proudcity-city-test",
                confidence=0.9,
                platform_name="ProudCity",
                metadata={},
                to_dict=lambda: {"source_type": "proudcity", "confidence": 0.9},
            )
            with patch("civicos_extraction.onboard._discover_proudcity") as mock_disc:
                mock_disc.return_value = {
                    "config": {
                        "source_id": "proudcity-city-test",
                        "source_type": "proudcity",
                        "jurisdiction_id": "city-test",
                        "base_url": "https://test.org",
                        "archives": {"council": "/council-meetings/"},
                    },
                    "discovered_bodies": {"council": "/council-meetings/"},
                }
                result = onboard_jurisdiction(
                    url="https://test.org",
                    jurisdiction_id="city-test",
                    on_progress=on_progress,
                )
                assert result.success
                assert "discover" in steps
                assert "save" in steps


# ── Onboard Robustness Tests ────────────────────────────────────


class TestOnboardRobustness:
    """Test onboard robustness fixes: empty archives, level passthrough, self-ref filtering."""

    def test_empty_archives_returns_failure(self):
        """Empty discovered_bodies should return success=False."""
        from civicos_extraction.onboard import onboard_jurisdiction

        with patch("civicos_extraction.onboard.detect_platform") as mock_detect:
            mock_detect.return_value = MagicMock(
                source_type="proudcity",
                source_id="proudcity-city-ghost",
                confidence=0.9,
                platform_name="ProudCity",
                metadata={},
                to_dict=lambda: {"source_type": "proudcity", "confidence": 0.9},
            )
            with patch("civicos_extraction.onboard._discover_proudcity") as mock_disc:
                mock_disc.return_value = {
                    "config": {
                        "source_id": "proudcity-city-ghost",
                        "source_type": "proudcity",
                        "jurisdiction_id": "city-ghost",
                        "base_url": "https://ghost.org",
                        "archives": {},
                    },
                    "discovered_bodies": {},
                }
                result = onboard_jurisdiction(
                    url="https://ghost.org",
                    jurisdiction_id="city-ghost",
                    validate=0,
                )
                assert not result.success
                assert any("No meeting bodies" in e for e in result.errors)

    def test_county_level_passthrough_to_yaml(self):
        """Level='county' should appear in generated YAML, not hardcoded 'city'."""
        from civicos_extraction.onboard import _generate_jurisdiction_yaml

        yaml_content = _generate_jurisdiction_yaml(
            jurisdiction_id="county-alameda",
            display_name="Alameda County",
            config={"source_type": "granicus", "base_url": "https://alamedacounty.granicus.com", "archives": {"view_2": "2"}},
            level="county",
            state_abbrev="CA",
        )
        assert "level: county" in yaml_content
        assert "level: city" not in yaml_content

    def test_self_reference_filtered_from_parents(self):
        """_generate_jurisdiction_yaml should filter self-references from parent_jurisdictions."""
        from civicos_extraction.onboard import _generate_jurisdiction_yaml
        import yaml

        # Geocoding returns county-alameda in parents — the generator should strip it
        yaml_content = _generate_jurisdiction_yaml(
            jurisdiction_id="county-alameda",
            display_name="Alameda County",
            config={"source_type": "granicus", "base_url": "https://alamedacounty.granicus.com", "archives": {"view_2": "2"}},
            parent_jurisdictions=["county-alameda", "state-california", "country-united-states"],
            level="county",
            state_abbrev="CA",
        )
        doc = yaml.safe_load(yaml_content)
        assert "county-alameda" not in doc["parent_jurisdictions"]
        assert "state-california" in doc["parent_jurisdictions"]
        assert "country-united-states" in doc["parent_jurisdictions"]

    def test_state_level_fallback_parents(self):
        """State-level jurisdictions should only have country as parent in fallback."""
        from civicos_extraction.onboard import _generate_jurisdiction_yaml
        import yaml

        yaml_content = _generate_jurisdiction_yaml(
            jurisdiction_id="state-california",
            display_name="California",
            config={"source_type": "granicus", "base_url": "https://ca.granicus.com", "archives": {"v": "1"}},
            level="state",
            state_abbrev="CA",
        )
        doc = yaml.safe_load(yaml_content)
        assert doc["parent_jurisdictions"] == ["country-united-states"]

    def test_county_level_omits_county_field_and_zip(self):
        """County YAML should not have redundant county in financial or zip in contact."""
        from civicos_extraction.onboard import _generate_jurisdiction_yaml
        import yaml

        yaml_content = _generate_jurisdiction_yaml(
            jurisdiction_id="county-alameda",
            display_name="Alameda County",
            config={"source_type": "granicus", "base_url": "https://alamedacounty.granicus.com", "archives": {"v": "1"}},
            level="county",
            county="Alameda County",
            zip_code="94501",
            state_abbrev="CA",
        )
        doc = yaml.safe_load(yaml_content)
        assert "county" not in doc["financial"]

    def test_canadian_province_fallback(self):
        """Canadian province should fallback to country-canada, not country-united-states."""
        from civicos_extraction.onboard import _generate_jurisdiction_yaml
        import yaml

        doc = yaml.safe_load(_generate_jurisdiction_yaml(
            jurisdiction_id="province-ontario",
            display_name="Ontario",
            config={"source_type": "granicus", "base_url": "https://on.granicus.com", "archives": {"v": "1"}},
            level="province",
            state_abbrev="ON",
            country="Canada",
        ))
        assert doc["parent_jurisdictions"] == ["country-canada"]

    def test_canadian_city_fallback(self):
        """Canadian city fallback should use province- prefix and country-canada."""
        from civicos_extraction.onboard import _generate_jurisdiction_yaml
        import yaml

        doc = yaml.safe_load(_generate_jurisdiction_yaml(
            jurisdiction_id="city-toronto",
            display_name="Toronto",
            config={"source_type": "granicus", "base_url": "https://toronto.granicus.com", "archives": {"v": "1"}},
            level="city",
            state_abbrev="ON",
            country="Canada",
        ))
        assert doc["parent_jurisdictions"] == ["province-ontario", "country-canada"]

    def test_uk_council_fallback(self):
        """UK council fallback should use country-united-kingdom."""
        from civicos_extraction.onboard import _generate_jurisdiction_yaml
        import yaml

        doc = yaml.safe_load(_generate_jurisdiction_yaml(
            jurisdiction_id="council-camden",
            display_name="Camden Council",
            config={"source_type": "standard", "base_url": "https://camden.gov.uk", "archives": {"v": "1"}},
            level="council",
            state_abbrev="",
            country="United Kingdom",
        ))
        assert doc["parent_jurisdictions"] == ["country-united-kingdom"]
        # zip_codes is a top-level list, not in contact_info
        assert doc.get("zip_codes", []) == []

    def test_jurisdiction_id_strips_level_suffix_from_city_name(self):
        """'Alameda County' with level=county should produce county-alameda, not county-alameda-county."""
        from civicos_extraction.onboard import onboard_jurisdiction

        with patch("civicos_extraction.platform_detection.discover_platform", return_value={
            "platform": "granicus", "details": {"url": "https://alamedacounty.granicus.com"}, "confidence": 0.95,
        }), patch("civicos_extraction.onboard._discover_granicus") as mock_disc:
            mock_disc.return_value = {
                "config": {"source_id": "granicus-county-alameda", "source_type": "granicus",
                           "jurisdiction_id": "county-alameda", "base_url": "https://alamedacounty.granicus.com",
                           "archives": {"board": "1"}, "metadata": {"granicus_domain": "alamedacounty"}},
                "discovered_bodies": {"board": "1"},
            }
            result = onboard_jurisdiction(
                url="", city_name="Alameda County", state="CA", level="county", validate=0,
            )
            assert result.success
            assert result.jurisdiction_id == "county-alameda"

    def test_jurisdiction_id_strips_level_suffix_from_url(self):
        """URL-inferred 'traviscounty' with level=county should produce county-travis."""
        from civicos_extraction.onboard import onboard_jurisdiction

        with patch("civicos_extraction.onboard.detect_platform") as mock_detect, \
             patch("civicos_extraction.onboard._discover_granicus") as mock_disc:
            mock_detect.return_value = MagicMock(
                source_type="granicus", source_id="granicus-county-travis",
                confidence=0.95, platform_name="Granicus", metadata={},
                to_dict=lambda: {"source_type": "granicus", "confidence": 0.95, "metadata": {}},
            )
            mock_disc.return_value = {
                "config": {"source_id": "granicus-county-travis", "source_type": "granicus",
                           "jurisdiction_id": "county-travis", "base_url": "https://traviscounty.granicus.com",
                           "archives": {"board": "1"}, "metadata": {"granicus_domain": "traviscounty"}},
                "discovered_bodies": {"board": "1"},
            }
            result = onboard_jurisdiction(
                url="https://traviscounty.granicus.com", level="county", validate=0,
            )
            assert result.success
            assert result.jurisdiction_id == "county-travis"

    def test_display_name_strips_level_prefix(self):
        """Display name for county-alameda should be 'Alameda', not 'County Alameda'."""
        import re
        # This tests the regex used at the call site
        test_cases = [
            ("county-alameda", "Alameda"),
            ("state-california", "California"),
            ("city-san-rafael", "San Rafael"),
            ("province-ontario", "Ontario"),
            ("council-camden", "Camden"),
        ]
        for jid, expected in test_cases:
            display = re.sub(r"^(city|county|town|district|state|province|council)-", "", jid).replace("-", " ").title()
            assert display == expected, f"{jid}: expected '{expected}', got '{display}'"

    def test_upfront_api_key_warnings(self):
        """Missing API keys should trigger progress warnings before network work."""
        from civicos_extraction.onboard import onboard_jurisdiction

        steps = []
        def on_progress(step, msg):
            steps.append((step, msg))

        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "GOOGLE_MAPS_API_KEY": ""}, clear=False), \
             patch("civicos_extraction.onboard.detect_platform") as mock_detect:
            mock_detect.return_value = MagicMock(
                source_type="proudcity",
                source_id="proudcity-city-warn",
                confidence=0.9,
                platform_name="ProudCity",
                metadata={},
                to_dict=lambda: {"source_type": "proudcity", "confidence": 0.9},
            )
            with patch("civicos_extraction.onboard._discover_proudcity") as mock_disc:
                mock_disc.return_value = {
                    "config": {
                        "source_id": "proudcity-city-warn",
                        "source_type": "proudcity",
                        "jurisdiction_id": "city-warn",
                        "base_url": "https://warn.org",
                        "archives": {"council": "/council/"},
                    },
                    "discovered_bodies": {"council": "/council/"},
                }
                result = onboard_jurisdiction(
                    url="https://warn.org",
                    jurisdiction_id="city-warn",
                    generate_yaml=True,
                    validate=0,
                    on_progress=on_progress,
                )
            warn_steps = [s for s, _ in steps if s == "warn"]
            assert len(warn_steps) >= 2  # OPENAI + GOOGLE warnings

    def test_validate_defaults_to_one(self):
        """Default validate parameter should be 1, not 0."""
        import inspect
        from civicos_extraction.onboard import onboard_jurisdiction
        sig = inspect.signature(onboard_jurisdiction)
        assert sig.parameters["validate"].default == 1


# ── CLI Onboard Tests ────────────────────────────────────────────


class TestOnboardCLI:
    """Test onboard CLI argument parsing."""

    def test_city_without_state_errors(self):
        """--city without --state should return error."""
        from civicos_extraction.cli.onboard_cli import add_onboard_parser, run_onboard
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_onboard_parser(subparsers)

        args = parser.parse_args(["onboard", "--city", "Berkeley"])
        assert run_onboard(args) == 1

    def test_neither_url_nor_city_errors(self):
        """Neither --url nor --city should return error."""
        from civicos_extraction.cli.onboard_cli import add_onboard_parser, run_onboard
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_onboard_parser(subparsers)

        args = parser.parse_args(["onboard"])
        assert run_onboard(args) == 1

    def test_dry_run_returns_zero(self):
        """--dry-run should succeed without network calls."""
        from civicos_extraction.cli.onboard_cli import add_onboard_parser, run_onboard
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        add_onboard_parser(subparsers)

        args = parser.parse_args(["onboard", "--city", "Berkeley", "--state", "CA", "--dry-run"])
        assert run_onboard(args) == 0


class TestDetectEScribe:
    """Test eScribe detection strategy."""

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_escribe_detected(self, mock_get):
        """Test successful eScribe detection."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html>escribemeetings GetCalendarMeetings</html>'
        mock_get.return_value = mock_response

        confidence, metadata = _detect_escribe("nationalcity", timeout=5)

        assert confidence == 0.95
        assert metadata["instance_name"] == "nationalcity"
        assert metadata["confirmed"] is True

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_escribe_not_found(self, mock_get):
        """Test eScribe 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        confidence, metadata = _detect_escribe("nonexistent", timeout=5)

        assert confidence == 0.0

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_escribe_timeout(self, mock_get):
        """Test eScribe timeout handling."""
        mock_get.side_effect = requests.exceptions.Timeout()

        confidence, metadata = _detect_escribe("nationalcity", timeout=5)

        assert confidence == 0.0
        assert metadata["error"] == "Timeout"

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_escribe_page_exists_but_not_escribe(self, mock_get):
        """Test page exists but doesn't look like eScribe."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html>Some other page</html>'
        mock_get.return_value = mock_response

        confidence, metadata = _detect_escribe("something", timeout=5)

        assert confidence == 0.60
        assert metadata["confirmed"] is False


class TestDiscoverEScribeInstance:
    """Test eScribe instance discovery."""

    @patch('civicos_extraction.platform_detection._detect_escribe')
    def test_discover_escribe_slug(self, mock_detect):
        """Test discovery with simple slug."""
        mock_detect.return_value = (0.95, {"instance_name": "ottawa", "confirmed": True})

        result = discover_escribe_instance("Ottawa", state="ON")

        assert result is not None
        assert result["instance_name"] == "ottawa"
        assert "escribemeetings.com" in result["url"]

    @patch('civicos_extraction.platform_detection._detect_escribe')
    def test_discover_escribe_not_found(self, mock_detect):
        """Test discovery fails when no instance found."""
        mock_detect.return_value = (0.0, {"error": "Not found"})

        result = discover_escribe_instance("Nonexistent City", state="CA")

        assert result is None

    @patch('civicos_extraction.platform_detection._detect_escribe')
    def test_discover_escribe_multi_word_city(self, mock_detect):
        """Test discovery with multi-word city name."""
        # First candidate (slug) fails, second (hyphenated) succeeds
        mock_detect.side_effect = [
            (0.0, {}),  # nationalcity
            (0.0, {}),  # nationalcityca
            (0.0, {}),  # national-city
            (0.95, {"instance_name": "cityofnationalcity", "confirmed": True}),
        ]

        result = discover_escribe_instance("National City", state="CA")

        assert result is not None


class TestEScribeClient:
    """Test EScribeClient normalization and structure."""

    def test_client_instantiation(self):
        """Test client creates with correct properties."""
        from civicos_extraction.clients.escribe import EScribeClient

        client = EScribeClient("nationalcity", "city-national-city")
        assert client.platform_name == "escribe"
        assert client.source_id == "escribe-nationalcity"
        assert client.source_type == "escribe"
        assert "escribemeetings.com" in client.base_url

    def test_normalize_event(self):
        """Test event normalization to Meeting dataclass."""
        from civicos_extraction.clients.escribe import EScribeClient

        client = EScribeClient("nationalcity", "city-national-city")

        event = {
            "ID": "abc-123",
            "MeetingName": "City Council Meeting",
            "StartDate": "2026/03/03 16:00:00",
            "Location": "City Hall",
            "MeetingPassed": False,
            "HasAgenda": True,
            "Url": "/Meeting?Id=abc-123",
            "MeetingDocumentLink": [
                {"Type": "Agenda", "Title": "Agenda (PDF)", "Url": "/FileStream.ashx?DocumentId=100"},
            ],
        }

        meeting = client.normalize_event(event)
        assert meeting.title == "City Council Meeting"
        assert meeting.meeting_type == "city_council"
        assert meeting.status == "scheduled"
        assert meeting.source_platform == "escribe"
        assert meeting.jurisdiction_id == "city-national-city"
        assert "FileStream.ashx" in meeting.agenda_url
        assert meeting.location == "City Hall"
        assert meeting.meeting_datetime.tzinfo is not None, "datetime must be timezone-aware"
        assert meeting.meeting_datetime.year == 2026
        assert meeting.meeting_datetime.hour == 16

    def test_normalize_completed_meeting(self):
        """Test completed meeting has correct status."""
        from civicos_extraction.clients.escribe import EScribeClient

        client = EScribeClient("ottawa", "city-ottawa")

        event = {
            "MeetingName": "Planning Commission",
            "StartDate": "2025/01/15 10:00:00",
            "MeetingPassed": True,
            "MeetingDocumentLink": [],
        }

        meeting = client.normalize_event(event)
        assert meeting.status == "completed"
        assert meeting.meeting_type == "planning_commission"
        assert meeting.meeting_datetime.tzinfo is not None, "datetime must be timezone-aware"

    def test_factory_creates_escribe(self):
        """Test factory dispatches escribe correctly."""
        from civicos_extraction.clients.factory import create_source
        from civicos_extraction.clients.base import ExtractionConfig

        config = ExtractionConfig(
            source_id="escribe-city-ottawa",
            source_type="escribe",
            jurisdiction_id="city-ottawa",
            base_url="https://pub-ottawa.escribemeetings.com",
            metadata={"instance_name": "ottawa"},
        )
        source = create_source(config)
        assert source.platform_name == "escribe"
        assert source.source_type == "escribe"

    def test_infer_jurisdiction_from_escribe_url(self):
        """Test jurisdiction inference from eScribe URLs."""
        from civicos_extraction.onboard import _infer_jurisdiction_id

        jid = _infer_jurisdiction_id("https://pub-nationalcity.escribemeetings.com")
        assert jid == "nationalcity"

        jid = _infer_jurisdiction_id("https://pub-ottawa.escribemeetings.com")
        assert jid == "ottawa"

    def test_meeting_type_inference(self):
        """Test meeting type inference from title strings."""
        from civicos_extraction.clients.escribe import EScribeClient

        client = EScribeClient("test", "city-test")

        assert client._infer_meeting_type("City Council Meeting") == "city_council"
        assert client._infer_meeting_type("Planning Commission") == "planning_commission"
        assert client._infer_meeting_type("Zoning Board of Appeals") == "zoning_board"
        assert client._infer_meeting_type("Finance Committee") == "committee"
        assert client._infer_meeting_type("Library Board") == "board"
        assert client._infer_meeting_type("Special Session") == "other"


class TestDetectSimbli:
    """Test Simbli detection strategy."""

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_simbli_detected(self, mock_get):
        """Test successful Simbli detection."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html>simbli eboardsolutions meeting board</html>'
        mock_get.return_value = mock_response

        confidence, metadata = _detect_simbli(
            "https://srcs.simbli.com/index.php", timeout=5
        )

        assert confidence == 0.95
        assert metadata["confirmed"] is True

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_simbli_waf_blocked(self, mock_get):
        """Test Simbli WAF blocking (403) still detects platform."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_get.return_value = mock_response

        confidence, metadata = _detect_simbli(
            "https://srcs.simbli.com/index.php", timeout=5
        )

        assert confidence == 0.70
        assert metadata["waf_blocked"] is True

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_simbli_incapsula_challenge(self, mock_get):
        """Test Simbli WAF challenge page still detects platform."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html>Incapsula incident checking your browser</html>'
        mock_get.return_value = mock_response

        confidence, metadata = _detect_simbli(
            "https://srcs.simbli.com/index.php", timeout=5
        )

        assert confidence == 0.80
        assert metadata["confirmed"] == "waf_detected"

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_simbli_not_found(self, mock_get):
        """Test non-Simbli URL."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '<html>Welcome to Example Corp</html>'
        mock_get.return_value = mock_response

        confidence, metadata = _detect_simbli(
            "https://example.com", timeout=5
        )

        assert confidence == 0.0

    @patch('civicos_extraction.platform_detection.requests.get')
    def test_simbli_timeout(self, mock_get):
        """Test Simbli timeout handling."""
        mock_get.side_effect = requests.exceptions.Timeout()

        confidence, metadata = _detect_simbli(
            "https://srcs.simbli.com/index.php", timeout=5
        )

        assert confidence == 0.0
        assert metadata["error"] == "Timeout"


class TestDiscoverSimbliInstance:
    """Test Simbli instance discovery."""

    @patch('civicos_extraction.platform_detection._detect_simbli')
    def test_discover_simbli_slug(self, mock_detect):
        """Test discovery with simple slug."""
        mock_detect.return_value = (0.95, {"confirmed": True})

        result = discover_simbli_instance("srcs", state="CA")

        assert result is not None
        assert result["board_url"].startswith("https://")
        assert "simbli.com" in result["board_url"]

    @patch('civicos_extraction.platform_detection._detect_simbli')
    def test_discover_simbli_not_found(self, mock_detect):
        """Test discovery fails when no instance found."""
        mock_detect.return_value = (0.0, {"error": "Not found"})

        result = discover_simbli_instance("nonexistent", state="CA")

        assert result is None


class TestSimbliClient:
    """Test SimbliClient BaseExtractor conformance."""

    def test_client_is_base_extractor(self):
        """Test SimbliClient subclasses BaseExtractor."""
        from civicos_extraction.clients.simbli import SimbliClient
        from civicos_extraction.clients.base import BaseExtractor

        client = SimbliClient(
            "https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430",
            "srcs",
        )
        assert isinstance(client, BaseExtractor)
        assert client.platform_name == "simbli"
        assert client.source_id == "simbli-srcs"
        assert client.source_type == "simbli"

    def test_normalize_event(self):
        """Test event normalization to Meeting dataclass."""
        from civicos_extraction.clients.simbli import SimbliClient

        client = SimbliClient(
            "https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430",
            "srcs",
        )

        event = {
            "id": "meeting:srcs:simbli:2026-01-15",
            "title": "Regular Board Meeting - January 15, 2026",
            "meeting_datetime": "2026-01-15T18:00:00",
            "meeting_type": "regular",
            "agenda_url": "https://simbli.eboardsolutions.com/agenda.pdf",
            "minutes_url": None,
            "location": "Board Room",
            "source_url": "https://simbli.eboardsolutions.com/...",
            "simbli_mid": "45989",
            "attachments": None,
        }

        meeting = client.normalize_event(event)
        assert meeting.title == "Regular Board Meeting - January 15, 2026"
        assert meeting.meeting_type == "regular"
        assert meeting.source_platform == "simbli"
        assert meeting.jurisdiction_id == "srcs"
        assert meeting.raw_data["simbli_mid"] == "45989"
        assert meeting.agenda_url == "https://simbli.eboardsolutions.com/agenda.pdf"

    def test_factory_creates_simbli(self):
        """Test factory dispatches simbli correctly."""
        from civicos_extraction.clients.factory import create_source
        from civicos_extraction.clients.base import ExtractionConfig

        config = ExtractionConfig(
            source_id="simbli-srcs",
            source_type="simbli",
            jurisdiction_id="srcs",
            base_url="https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430",
            metadata={"board_url": "https://simbli.eboardsolutions.com/SB_Meetings/SB_MeetingListing.aspx?S=36030430"},
        )
        source = create_source(config)
        assert source.platform_name == "simbli"
        assert source.source_type == "simbli"

    def test_infer_jurisdiction_from_simbli_url(self):
        """Test jurisdiction inference from Simbli URLs."""
        from civicos_extraction.onboard import _infer_jurisdiction_id

        jid = _infer_jurisdiction_id("https://srcs.simbli.com/index.php")
        assert jid == "srcs"
