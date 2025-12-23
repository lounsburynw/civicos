"""
Tests for JurisdictionRegistry - centralized jurisdiction configuration.
"""

import pytest
from civic.jurisdiction import (
    JurisdictionRegistry,
    JurisdictionConfig,
    GranicusConfig,
    CITY_CONFIGS,
)


class TestJurisdictionRegistry:
    """Test JurisdictionRegistry class methods."""

    def test_get_by_city_key(self):
        """Get jurisdiction config by city key."""
        config = JurisdictionRegistry.get("san_rafael")
        assert config is not None
        assert config.jurisdiction_id == "city-san-rafael"
        assert config.timezone == "America/Los_Angeles"
        assert config.agent_type == "san_rafael_cms"

    def test_get_returns_none_for_unknown_key(self):
        """Get returns None for unknown city key."""
        config = JurisdictionRegistry.get("unknown_city")
        assert config is None

    def test_get_by_jurisdiction_id(self):
        """Get jurisdiction config by jurisdiction ID."""
        config = JurisdictionRegistry.get_by_id("city-san-rafael")
        assert config is not None
        assert config.timezone == "America/Los_Angeles"

    def test_get_by_id_returns_none_for_unknown(self):
        """Get by ID returns None for unknown jurisdiction."""
        config = JurisdictionRegistry.get_by_id("city-unknown")
        assert config is None

    def test_get_timezone(self):
        """Get timezone for jurisdiction ID."""
        tz = JurisdictionRegistry.get_timezone("city-san-rafael")
        assert tz == "America/Los_Angeles"

    def test_get_timezone_default(self):
        """Get timezone falls back to default for unknown."""
        tz = JurisdictionRegistry.get_timezone("city-unknown", default="UTC")
        assert tz == "UTC"

    def test_get_timezone_display(self):
        """Get timezone and display abbreviation."""
        tz_name, tz_display = JurisdictionRegistry.get_timezone_display("city-san-rafael")
        assert tz_name == "America/Los_Angeles"
        assert tz_display == "PT"

    def test_get_timezone_display_unknown(self):
        """Get timezone display returns UTC for unknown."""
        tz_name, tz_display = JurisdictionRegistry.get_timezone_display("city-unknown")
        assert tz_name == "UTC"
        assert tz_display == "UTC"

    def test_has_jurisdiction(self):
        """Check if jurisdiction is registered."""
        assert JurisdictionRegistry.has_jurisdiction("city-san-rafael") is True
        assert JurisdictionRegistry.has_jurisdiction("city-unknown") is False

    def test_all_configs(self):
        """Get all jurisdiction configurations."""
        configs = JurisdictionRegistry.all_configs()
        assert isinstance(configs, dict)
        assert "san_rafael" in configs
        assert "berkeley" in configs
        assert len(configs) >= 20  # We have at least 20 cities

    def test_all_jurisdiction_ids(self):
        """Get all registered jurisdiction IDs."""
        ids = JurisdictionRegistry.all_jurisdiction_ids()
        assert isinstance(ids, list)
        assert "city-san-rafael" in ids
        assert "city-berkeley" in ids


class TestJurisdictionConfig:
    """Test JurisdictionConfig dataclass."""

    def test_config_is_frozen(self):
        """JurisdictionConfig is immutable."""
        config = JurisdictionRegistry.get("san_rafael")
        with pytest.raises(AttributeError):
            config.timezone = "America/New_York"

    def test_timezone_display_property(self):
        """Test timezone_display property."""
        config = JurisdictionConfig(
            jurisdiction_id="test",
            agent_type="test",
            meeting_urls=["http://example.com"],
            timezone="America/Los_Angeles",
        )
        assert config.timezone_display == "PT"

    def test_timezone_display_new_york(self):
        """Test timezone_display for New York."""
        config = JurisdictionConfig(
            jurisdiction_id="test",
            agent_type="test",
            meeting_urls=["http://example.com"],
            timezone="America/New_York",
        )
        assert config.timezone_display == "ET"

    def test_granicus_config(self):
        """Test Granicus config nested object."""
        config = JurisdictionRegistry.get("dublin")
        assert config is not None
        assert config.granicus_config is not None
        assert config.granicus_config.subdomain == "dublin"
        assert config.granicus_config.view_id == 1


class TestCityConfigsBackwardCompat:
    """Test CITY_CONFIGS backward compatibility dict."""

    def test_city_configs_is_dict(self):
        """CITY_CONFIGS is a dict for backward compatibility."""
        assert isinstance(CITY_CONFIGS, dict)

    def test_city_configs_has_expected_keys(self):
        """CITY_CONFIGS has expected city keys."""
        assert "san_rafael" in CITY_CONFIGS
        assert "berkeley" in CITY_CONFIGS
        assert "oakland" in CITY_CONFIGS

    def test_city_configs_has_expected_structure(self):
        """CITY_CONFIGS entries have expected structure."""
        sr = CITY_CONFIGS["san_rafael"]
        assert sr["jurisdiction_id"] == "city-san-rafael"
        assert sr["agent_type"] == "san_rafael_cms"
        assert sr["timezone"] == "America/Los_Angeles"
        assert "meeting_urls" in sr
        assert isinstance(sr["meeting_urls"], list)

    def test_city_configs_granicus_config(self):
        """CITY_CONFIGS granicus entries have nested config."""
        dublin = CITY_CONFIGS["dublin"]
        assert "granicus_config" in dublin
        assert dublin["granicus_config"]["subdomain"] == "dublin"
        assert dublin["granicus_config"]["view_id"] == 1


class TestAgentTypes:
    """Test that all agent types are correctly configured."""

    def test_legistar_cities(self):
        """Legistar cities have correct agent type."""
        legistar_cities = ["santa_rosa", "hayward", "oakland", "napa", "bart"]
        for city in legistar_cities:
            config = JurisdictionRegistry.get(city)
            assert config is not None, f"Missing config for {city}"
            assert config.agent_type == "legistar", f"{city} should use legistar"

    def test_civicclerk_cities(self):
        """CivicClerk cities have correct agent type."""
        civicclerk_cities = ["richmond", "el_cerrito", "los_altos", "daly_city"]
        for city in civicclerk_cities:
            config = JurisdictionRegistry.get(city)
            assert config is not None, f"Missing config for {city}"
            assert config.agent_type == "civicclerk", f"{city} should use civicclerk"

    def test_granicus_cities(self):
        """Granicus cities have correct agent type and config."""
        granicus_cities = ["dublin", "campbell"]
        for city in granicus_cities:
            config = JurisdictionRegistry.get(city)
            assert config is not None, f"Missing config for {city}"
            assert config.agent_type == "granicus", f"{city} should use granicus"
            assert config.granicus_config is not None, f"{city} should have granicus_config"

    def test_civicplus_cities(self):
        """CivicPlus cities have correct agent type."""
        civicplus_cities = ["union_city", "concord", "san_leandro", "pleasant_hill"]
        for city in civicplus_cities:
            config = JurisdictionRegistry.get(city)
            assert config is not None, f"Missing config for {city}"
            assert config.agent_type == "civicplus_cms", f"{city} should use civicplus_cms"
