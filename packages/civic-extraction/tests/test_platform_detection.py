"""
Tests for platform detection helper.

Uses mocked HTTP responses to test detection logic without real API calls.
"""

import pytest
from unittest.mock import patch, MagicMock
import requests

from civic_extraction.platform_detection import (
    DetectionResult,
    detect_platform,
    detect_platform_batch,
    _extract_client_name,
    _detect_legistar,
    _detect_civicclerk,
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

    @patch('civic_extraction.platform_detection.requests.get')
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

    @patch('civic_extraction.platform_detection.requests.get')
    def test_legistar_not_found(self, mock_get):
        """Test Legistar 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        confidence, metadata = _detect_legistar("nonexistent", timeout=5)

        assert confidence == 0.0
        assert metadata["status_code"] == 404

    @patch('civic_extraction.platform_detection.requests.get')
    def test_legistar_timeout(self, mock_get):
        """Test Legistar timeout handling."""
        mock_get.side_effect = requests.exceptions.Timeout()

        confidence, metadata = _detect_legistar("berkeley", timeout=5)

        assert confidence == 0.0
        assert metadata["error"] == "Timeout"

    @patch('civic_extraction.platform_detection.requests.get')
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

    @patch('civic_extraction.platform_detection.requests.get')
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

    @patch('civic_extraction.platform_detection.requests.get')
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

    @patch('civic_extraction.platform_detection.requests.get')
    def test_civicclerk_not_found(self, mock_get):
        """Test CivicClerk 404 response."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        confidence, metadata = _detect_civicclerk("nonexistent", timeout=5)

        assert confidence == 0.0


class TestDetectProudCity:
    """Test ProudCity detection strategy."""

    @patch('civic_extraction.platform_detection.requests.get')
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

    @patch('civic_extraction.platform_detection.requests.get')
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

    @patch('civic_extraction.platform_detection.requests.get')
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

    @patch('civic_extraction.platform_detection.requests.get')
    def test_proudcity_not_detected(self, mock_get):
        """Test ProudCity not detected when no archives found."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"<html><body>No meeting links here</body></html>"
        mock_get.return_value = mock_response

        confidence, metadata = _detect_proudcity("https://example.org", timeout=5)

        assert confidence == 0.0
        assert metadata["meeting_type_count"] == 0

    @patch('civic_extraction.platform_detection.requests.get')
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

    @patch('civic_extraction.platform_detection._detect_legistar')
    @patch('civic_extraction.platform_detection._detect_civicclerk')
    @patch('civic_extraction.platform_detection._detect_proudcity')
    def test_detects_legistar(self, mock_pc, mock_cc, mock_leg):
        """Test Legistar is detected when API responds."""
        mock_leg.return_value = (0.95, {"body_count": 5})
        mock_cc.return_value = (0.0, {})
        mock_pc.return_value = (0.0, {})

        result = detect_platform("https://www.cityofberkeley.info")

        assert result.source_type == "legistar"
        assert result.confidence == 0.95
        assert result.platform_name == "Legistar"

    @patch('civic_extraction.platform_detection._detect_legistar')
    @patch('civic_extraction.platform_detection._detect_civicclerk')
    @patch('civic_extraction.platform_detection._detect_proudcity')
    def test_detects_civicclerk(self, mock_pc, mock_cc, mock_leg):
        """Test CivicClerk is detected when API responds."""
        mock_leg.return_value = (0.0, {})
        mock_cc.return_value = (0.95, {"board_count": 3})
        mock_pc.return_value = (0.0, {})

        result = detect_platform("https://elcerrito.ca.gov")

        assert result.source_type == "civicclerk"
        assert result.confidence == 0.95

    @patch('civic_extraction.platform_detection._detect_legistar')
    @patch('civic_extraction.platform_detection._detect_civicclerk')
    @patch('civic_extraction.platform_detection._detect_proudcity')
    def test_detects_proudcity(self, mock_pc, mock_cc, mock_leg):
        """Test ProudCity is detected when scraping finds archives."""
        mock_leg.return_value = (0.0, {})
        mock_cc.return_value = (0.0, {})
        mock_pc.return_value = (0.90, {"meeting_type_count": 6})

        result = detect_platform("https://www.cityofsanrafael.org")

        assert result.source_type == "proudcity"
        assert result.confidence == 0.90

    @patch('civic_extraction.platform_detection._detect_legistar')
    @patch('civic_extraction.platform_detection._detect_civicclerk')
    @patch('civic_extraction.platform_detection._detect_proudcity')
    def test_no_platform_detected(self, mock_pc, mock_cc, mock_leg):
        """Test no platform detected returns appropriate result."""
        mock_leg.return_value = (0.0, {})
        mock_cc.return_value = (0.0, {})
        mock_pc.return_value = (0.0, {})

        result = detect_platform("https://unknown-city.org")

        assert result.source_type is None
        assert result.confidence == 0.0
        assert "No platform detected" in result.errors

    @patch('civic_extraction.platform_detection._detect_legistar')
    @patch('civic_extraction.platform_detection._detect_civicclerk')
    @patch('civic_extraction.platform_detection._detect_proudcity')
    def test_highest_confidence_wins(self, mock_pc, mock_cc, mock_leg):
        """Test highest confidence platform is selected."""
        mock_leg.return_value = (0.50, {})  # Low confidence
        mock_cc.return_value = (0.0, {})
        mock_pc.return_value = (0.90, {"meeting_type_count": 6})  # High confidence

        result = detect_platform("https://www.cityofsanrafael.org")

        # ProudCity should win with 0.90 > 0.50
        assert result.source_type == "proudcity"
        assert result.confidence == 0.90

    @patch('civic_extraction.platform_detection._detect_legistar')
    @patch('civic_extraction.platform_detection._detect_civicclerk')
    @patch('civic_extraction.platform_detection._detect_proudcity')
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

    @patch('civic_extraction.platform_detection.detect_platform')
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

    @patch('civic_extraction.platform_detection.detect_platform')
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
