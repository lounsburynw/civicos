"""
Tests for MCP who_represents_me tool.

Tests the civic_who_represents_me tool definition and handler logic.
Mocks geocoding API calls and storage backend.
"""

import pytest
import sys
import asyncio
from unittest.mock import patch, MagicMock

# Add paths for imports
sys.path.insert(0, "apps/civicos-mcp")


class TestWhoRepresentsMeToolDefinition:
    """Test civic_who_represents_me tool is properly registered."""

    def test_tool_in_v2_definitions(self):
        """Tool is listed in v2 tool definitions."""
        from server import _get_v2_tool_definitions

        tools = _get_v2_tool_definitions()
        names = [t["name"] for t in tools]
        assert "civic_who_represents_me" in names

    def test_tool_schema(self):
        """Tool has correct input schema."""
        from server import _get_v2_tool_definitions

        tools = _get_v2_tool_definitions()
        tool = next(t for t in tools if t["name"] == "civic_who_represents_me")

        schema = tool["inputSchema"]
        assert "address" in schema["properties"]
        assert "jurisdiction" in schema["properties"]
        # Neither field is required — both are optional
        assert "required" not in schema or "address" not in schema.get("required", [])

    def test_tool_description_mentions_geocoding(self):
        """Description explains what the tool does."""
        from server import _get_v2_tool_definitions

        tools = _get_v2_tool_definitions()
        tool = next(t for t in tools if t["name"] == "civic_who_represents_me")

        assert "address" in tool["description"].lower()
        assert "officials" in tool["description"].lower()


class TestWhoRepresentsMeHandler:
    """Test _handle_who_represents_me handler logic."""

    MOCK_GEO_RESULT = {
        "lat": 37.9735,
        "lng": -122.5311,
        "formatted_address": "123 Main St, San Rafael, CA 94901, USA",
        "city": "San Rafael",
        "county": "Marin County",
        "state": "California",
        "zip_code": "94901",
        "jurisdictions": {
            "city": "city-san-rafael",
            "county": "county-marin",
        },
    }

    MOCK_OFFICIALS_BY_JURISDICTION = {
        "city-san-rafael": [
            {"name": "Kate Colin", "seat": "Mayor", "term_start": "2022-12-01", "term_end": None, "candidate_id": None},
            {"name": "Maribeth Bushey", "seat": "Council Member", "term_start": "2022-12-01", "term_end": None, "candidate_id": None},
        ],
        "state-california": [
            {"name": "Gavin Newsom", "seat": "Governor", "term_start": "2023-01-01", "term_end": None, "candidate_id": None},
        ],
        "country-united-states": [
            {"name": "Adam Schiff", "seat": "U.S. Senate", "term_start": "2025-01-03", "term_end": None, "candidate_id": None},
        ],
    }

    def _mock_get_officials(self, jurisdiction_id, current_only=True):
        """Mock storage.get_elected_officials."""
        return self.MOCK_OFFICIALS_BY_JURISDICTION.get(jurisdiction_id, [])

    def _run(self, coro):
        """Run async coroutine in sync test."""
        return asyncio.get_event_loop().run_until_complete(coro)

    @patch("server._civic")
    @patch("server._jurisdiction", "city-san-rafael")
    def test_address_geocoded_to_officials(self, mock_civic):
        """Address is geocoded and officials returned per level."""
        from server import _handle_who_represents_me

        mock_civic.storage.get_elected_officials = MagicMock(side_effect=self._mock_get_officials)

        with patch(
            "civicos_services.clients.geocoding_service.GeocodingService"
        ) as MockGeo:
            instance = MockGeo.return_value
            instance.geocode_address.return_value = self.MOCK_GEO_RESULT

            with patch(
                "civicos_services.query.jurisdictions.resolve_jurisdictions",
                return_value=["city-san-rafael", "county-marin", "state-california", "country-united-states"],
            ):
                result = self._run(_handle_who_represents_me({"address": "123 Main St, San Rafael, CA"}))

        assert result["jurisdiction"] == "city-san-rafael"
        assert result["resolved_address"] == "123 Main St, San Rafael, CA 94901, USA"
        assert result["total_officials"] == 4  # 2 local + 1 state + 1 federal
        assert len(result["levels"]) == 3  # city, state, federal (county has none)

        # Verify officials are grouped by jurisdiction level
        level_jids = [lv["jurisdiction"] for lv in result["levels"]]
        assert "city-san-rafael" in level_jids
        assert "state-california" in level_jids
        assert "country-united-states" in level_jids

    @patch("server._civic")
    @patch("server._jurisdiction", "city-san-rafael")
    def test_fallback_to_jurisdiction_param(self, mock_civic):
        """When no address provided, uses jurisdiction parameter."""
        from server import _handle_who_represents_me

        mock_civic.storage.get_elected_officials = MagicMock(side_effect=self._mock_get_officials)

        with patch(
            "civicos_services.query.jurisdictions.resolve_jurisdictions",
            return_value=["city-san-rafael", "state-california", "country-united-states"],
        ):
            result = self._run(_handle_who_represents_me({"jurisdiction": "city-san-rafael"}))

        assert result["jurisdiction"] == "city-san-rafael"
        assert "resolved_address" not in result
        assert result["total_officials"] == 4

    @patch("server._civic")
    @patch("server._jurisdiction", "city-san-rafael")
    def test_fallback_to_server_default(self, mock_civic):
        """When no address and no jurisdiction, uses server default."""
        from server import _handle_who_represents_me

        mock_civic.storage.get_elected_officials = MagicMock(side_effect=self._mock_get_officials)

        with patch(
            "civicos_services.query.jurisdictions.resolve_jurisdictions",
            return_value=["city-san-rafael"],
        ):
            result = self._run(_handle_who_represents_me({}))

        assert result["jurisdiction"] == "city-san-rafael"

    @patch("server._civic")
    @patch("server._jurisdiction", "city-san-rafael")
    def test_geocoding_fails_with_fallback(self, mock_civic):
        """When geocoding fails but jurisdiction provided, uses fallback."""
        from server import _handle_who_represents_me

        mock_civic.storage.get_elected_officials = MagicMock(side_effect=self._mock_get_officials)

        with patch(
            "civicos_services.clients.geocoding_service.GeocodingService"
        ) as MockGeo:
            instance = MockGeo.return_value
            instance.geocode_address.return_value = None  # geocoding failed

            with patch(
                "civicos_services.query.jurisdictions.resolve_jurisdictions",
                return_value=["city-san-rafael"],
            ):
                result = self._run(_handle_who_represents_me({
                    "address": "bad address",
                    "jurisdiction": "city-san-rafael",
                }))

        assert result["jurisdiction"] == "city-san-rafael"
        assert "note" in result  # warns that address wasn't geocoded

    @patch("server._civic")
    @patch("server._jurisdiction", "city-san-rafael")
    def test_geocoding_fails_no_fallback(self, mock_civic):
        """When geocoding fails and no fallback jurisdiction, returns error."""
        from server import _handle_who_represents_me

        with patch(
            "civicos_services.clients.geocoding_service.GeocodingService"
        ) as MockGeo:
            instance = MockGeo.return_value
            instance.geocode_address.return_value = None

            result = self._run(_handle_who_represents_me({"address": "123 Nowhere St, Nowhere, ZZ"}))

        assert "error" in result
        assert "hint" in result

    @patch("server._civic")
    @patch("server._jurisdiction", "city-san-rafael")
    def test_no_api_key_with_jurisdiction_fallback(self, mock_civic):
        """When no API key but jurisdiction provided, still works."""
        from server import _handle_who_represents_me

        mock_civic.storage.get_elected_officials = MagicMock(return_value=[])

        with patch(
            "civicos_services.clients.geocoding_service.GeocodingService",
            side_effect=ValueError("Google Maps API key required"),
        ):
            with patch(
                "civicos_services.query.jurisdictions.resolve_jurisdictions",
                return_value=["city-san-rafael"],
            ):
                result = self._run(_handle_who_represents_me({
                    "address": "123 Main St",
                    "jurisdiction": "city-san-rafael",
                }))

        assert result["jurisdiction"] == "city-san-rafael"

    @patch("server._civic")
    @patch("server._jurisdiction", "city-san-rafael")
    def test_no_api_key_no_fallback(self, mock_civic):
        """When no API key and no jurisdiction fallback, returns error."""
        from server import _handle_who_represents_me

        with patch(
            "civicos_services.clients.geocoding_service.GeocodingService",
            side_effect=ValueError("Google Maps API key required"),
        ):
            result = self._run(_handle_who_represents_me({"address": "123 Main St"}))

        assert "error" in result

    @patch("server._civic")
    @patch("server._jurisdiction", "city-mill-valley")
    def test_mill_valley_jurisdiction(self, mock_civic):
        """Works for Mill Valley pilot jurisdiction."""
        from server import _handle_who_represents_me

        mock_civic.storage.get_elected_officials = MagicMock(return_value=[
            {"name": "Test Official", "seat": "Mayor", "term_start": "2024-01-01", "term_end": None, "candidate_id": None},
        ])

        with patch(
            "civicos_services.query.jurisdictions.resolve_jurisdictions",
            return_value=["city-mill-valley"],
        ):
            result = self._run(_handle_who_represents_me({"jurisdiction": "city-mill-valley"}))

        assert result["jurisdiction"] == "city-mill-valley"
        assert result["total_officials"] == 1

    @patch("server._civic")
    @patch("server._jurisdiction", "city-san-anselmo")
    def test_san_anselmo_jurisdiction(self, mock_civic):
        """Works for San Anselmo pilot jurisdiction."""
        from server import _handle_who_represents_me

        mock_civic.storage.get_elected_officials = MagicMock(return_value=[])

        with patch(
            "civicos_services.query.jurisdictions.resolve_jurisdictions",
            return_value=["city-san-anselmo"],
        ):
            result = self._run(_handle_who_represents_me({"jurisdiction": "city-san-anselmo"}))

        assert result["jurisdiction"] == "city-san-anselmo"
        assert result["total_officials"] == 0

    def test_official_fields_shape(self):
        """Official entries have expected fields."""
        from server import _handle_who_represents_me

        officials_data = [
            {"name": "Jane Doe", "seat": "Council", "term_start": "2024-01-01", "term_end": None, "candidate_id": "cand-123", "id": "off-1"},
        ]

        with patch("server._civic") as mock_civic, \
             patch("server._jurisdiction", "city-san-rafael"), \
             patch("civicos_services.query.jurisdictions.resolve_jurisdictions", return_value=["city-san-rafael"]):
            mock_civic.storage.get_elected_officials = MagicMock(return_value=officials_data)
            result = self._run(_handle_who_represents_me({"jurisdiction": "city-san-rafael"}))

        official = result["levels"][0]["officials"][0]
        assert official["name"] == "Jane Doe"
        assert official["seat"] == "Council"
        assert official["term_start"] == "2024-01-01"
        assert official["candidate_id"] == "cand-123"
        # Should NOT expose internal id
        assert "id" not in official


class TestGeocodingServiceMappings:
    """Test that jurisdiction mappings are loaded from YAML configs."""

    def setup_method(self):
        """Clear cached mappings so each test gets a fresh load."""
        import civicos_services.clients.geocoding_service as geo_mod
        geo_mod._jurisdiction_mappings = None

    def test_san_rafael_mapped(self):
        """San Rafael is loaded from city-san-rafael.yaml."""
        from civicos_services.clients.geocoding_service import GeocodingService
        geo = GeocodingService(api_key="test-key")
        assert geo.city_to_jurisdiction["San Rafael"] == "city-san-rafael"

    def test_mill_valley_mapped(self):
        """Mill Valley is loaded from city-mill-valley.yaml."""
        from civicos_services.clients.geocoding_service import GeocodingService
        geo = GeocodingService(api_key="test-key")
        assert geo.city_to_jurisdiction["Mill Valley"] == "city-mill-valley"

    def test_san_anselmo_mapped(self):
        """San Anselmo is loaded from city-san-anselmo.yaml."""
        from civicos_services.clients.geocoding_service import GeocodingService
        geo = GeocodingService(api_key="test-key")
        assert geo.city_to_jurisdiction["San Anselmo"] == "city-san-anselmo"

    def test_marin_county_mapped(self):
        """Marin County is loaded from county-marin.yaml."""
        from civicos_services.clients.geocoding_service import GeocodingService
        geo = GeocodingService(api_key="test-key")
        assert geo.county_to_jurisdiction["Marin County"] == "county-marin"

    def test_mappings_loaded_from_yaml(self):
        """Mappings come from data/jurisdictions/ YAML files, not hardcoded."""
        from civicos_services.clients.geocoding_service import _load_jurisdiction_mappings, JURISDICTIONS_DIR
        mappings = _load_jurisdiction_mappings(JURISDICTIONS_DIR)
        # Should have at least 3 pilot cities
        assert len(mappings["city"]) >= 3
        # Should have at least 1 county
        assert len(mappings["county"]) >= 1
        # Verify mappings match YAML file contents
        assert all(v.startswith("city-") for v in mappings["city"].values())
        assert all(v.startswith("county-") for v in mappings["county"].values())

    def test_schema_yaml_excluded(self):
        """schema.yaml is not loaded as a jurisdiction."""
        from civicos_services.clients.geocoding_service import GeocodingService
        geo = GeocodingService(api_key="test-key")
        assert "string" not in geo.city_to_jurisdiction  # schema.yaml has display_name: string
