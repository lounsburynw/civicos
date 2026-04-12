"""
Tests for JurisdictionRegistry - centralized jurisdiction configuration.
Tests for normalize_jurisdiction - strict jurisdiction ID validation.
"""

import pytest
from civicos.jurisdiction import (
    JurisdictionRegistry,
    JurisdictionConfig,
    GranicusConfig,
    CITY_CONFIGS,
)
from civicos._internal.jurisdiction import (
    JurisdictionError,
    normalize_jurisdiction,
    display_jurisdiction,
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
        assert len(configs) >= 40  # 29 hardcoded + auto-loaded from config files

    def test_all_jurisdiction_ids(self):
        """Get all registered jurisdiction IDs."""
        ids = JurisdictionRegistry.all_jurisdiction_ids()
        assert isinstance(ids, list)
        assert len(ids) >= 40  # 29 hardcoded + auto-loaded from config files
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
        assert len(CITY_CONFIGS) >= 29  # At least the 29 hardcoded entries

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


class TestNormalizeJurisdiction:
    """Test normalize_jurisdiction strict validation (Session 372)."""

    # ─────────── Valid jurisdiction tests ───────────

    def test_normalize_valid_alias(self):
        """Known aliases normalize correctly."""
        assert normalize_jurisdiction("san-rafael") == "city-san-rafael"
        assert normalize_jurisdiction("berkeley") == "city-berkeley"

    def test_normalize_canonical_format(self):
        """Already-canonical IDs are idempotent."""
        assert normalize_jurisdiction("city-san-rafael") == "city-san-rafael"
        assert normalize_jurisdiction("city-oakland") == "city-oakland"

    def test_normalize_with_state_suffix(self):
        """State suffixes are stripped correctly."""
        assert normalize_jurisdiction("san-rafael-ca") == "city-san-rafael"
        assert normalize_jurisdiction("berkeley-ca") == "city-berkeley"

    def test_normalize_case_insensitive(self):
        """Normalization is case-insensitive."""
        assert normalize_jurisdiction("SAN-RAFAEL") == "city-san-rafael"
        assert normalize_jurisdiction("City-San-Rafael") == "city-san-rafael"

    def test_normalize_registered_cities(self):
        """All registered jurisdiction IDs normalize correctly."""
        for jid in JurisdictionRegistry.all_jurisdiction_ids():
            result = normalize_jurisdiction(jid)
            assert result == jid, f"Canonical ID should be idempotent: {jid}"

    def test_normalize_special_ids(self):
        """Special IDs without city- prefix work (e.g., bart)."""
        assert normalize_jurisdiction("bart") == "bart"

    # ─────────── Invalid jurisdiction tests (strict mode) ───────────

    def test_reject_unknown_jurisdiction(self):
        """Unknown jurisdiction IDs raise JurisdictionError in strict mode."""
        with pytest.raises(JurisdictionError) as exc_info:
            normalize_jurisdiction("bogus-city")
        assert "Unknown jurisdiction ID" in str(exc_info.value)
        assert "bogus-city" in str(exc_info.value)

    def test_reject_typo_in_known_city(self):
        """Typos in known city names are rejected."""
        with pytest.raises(JurisdictionError):
            normalize_jurisdiction("san-rafeal")  # typo: rafeal vs rafael

    def test_reject_unknown_with_city_prefix(self):
        """Unknown IDs with city- prefix are still rejected."""
        with pytest.raises(JurisdictionError):
            normalize_jurisdiction("city-atlantis")

    def test_reject_unknown_with_state_suffix(self):
        """Unknown IDs with state suffix are rejected."""
        with pytest.raises(JurisdictionError):
            normalize_jurisdiction("atlantis-ca")

    def test_error_message_includes_valid_ids(self):
        """Error message includes examples of valid IDs."""
        with pytest.raises(JurisdictionError) as exc_info:
            normalize_jurisdiction("invalid-city")
        error_msg = str(exc_info.value)
        assert "Valid IDs:" in error_msg
        # Should include some real IDs
        assert "city-" in error_msg or "bart" in error_msg

    # ─────────── Non-strict mode tests ───────────

    def test_nonstrict_allows_unknown(self):
        """Non-strict mode returns unknown IDs with city- prefix (legacy behavior)."""
        result = normalize_jurisdiction("bogus-city", strict=False)
        assert result == "city-bogus-city"

    def test_nonstrict_still_normalizes_valid(self):
        """Non-strict mode still normalizes valid IDs correctly."""
        assert normalize_jurisdiction("san-rafael", strict=False) == "city-san-rafael"
        assert normalize_jurisdiction("city-oakland", strict=False) == "city-oakland"

    # ─────────── Edge cases ───────────

    def test_empty_string_passthrough(self):
        """Empty string returns empty string."""
        assert normalize_jurisdiction("") == ""

    def test_whitespace_handling(self):
        """Whitespace is trimmed."""
        assert normalize_jurisdiction("  san-rafael  ") == "city-san-rafael"


class TestDisplayJurisdiction:
    """Test display_jurisdiction formatting."""

    def test_display_known_jurisdiction(self):
        """Known jurisdictions have proper display names."""
        assert display_jurisdiction("city-san-rafael") == "San Rafael"

    def test_display_generates_name_from_id(self):
        """Display names are generated from canonical IDs."""
        assert display_jurisdiction("city-oakland") == "Oakland"
        assert display_jurisdiction("county-sonoma") == "Sonoma County"

    def test_display_bart(self):
        """BART displays as all caps."""
        assert display_jurisdiction("bart") == "BART"

    def test_display_multi_word_cities(self):
        """Multi-word cities display correctly."""
        assert display_jurisdiction("city-el-cerrito") == "El Cerrito"
        assert display_jurisdiction("city-los-altos") == "Los Altos"
        assert display_jurisdiction("city-daly-city") == "Daly City"


class TestJurisdictionRegistryAliases:
    """Test comprehensive alias coverage (Session 373)."""

    # ─────────── Underscore to hyphen conversion ───────────

    def test_underscore_normalization(self):
        """Underscores are converted to hyphens."""
        assert normalize_jurisdiction("san_rafael") == "city-san-rafael"
        assert normalize_jurisdiction("el_cerrito") == "city-el-cerrito"
        assert normalize_jurisdiction("daly_city") == "city-daly-city"
        assert normalize_jurisdiction("los_altos") == "city-los-altos"

    def test_underscore_with_prefix(self):
        """Underscores work with city- prefix too."""
        assert normalize_jurisdiction("city_san_rafael") == "city-san-rafael"
        assert normalize_jurisdiction("city_oakland") == "city-oakland"

    # ─────────── Special entity aliases ───────────

    def test_sonoma_alias(self):
        """'sonoma' normalizes to 'county-sonoma' (not city-sonoma)."""
        assert normalize_jurisdiction("sonoma") == "county-sonoma"
        assert normalize_jurisdiction("sonoma-ca") == "county-sonoma"
        assert normalize_jurisdiction("sonoma-county") == "county-sonoma"

    def test_bart_aliases(self):
        """BART has multiple alias forms."""
        assert normalize_jurisdiction("bart") == "bart"
        assert normalize_jurisdiction("sf-bart") == "bart"
        assert normalize_jurisdiction("bay-area-rapid-transit") == "bart"
        assert normalize_jurisdiction("BART") == "bart"

    # ─────────── Multi-word city aliases ───────────

    def test_multi_word_city_aliases(self):
        """Multi-word cities have explicit aliases."""
        # These are covered by explicit aliases
        assert normalize_jurisdiction("los-altos") == "city-los-altos"
        assert normalize_jurisdiction("los-altos-hills") == "city-los-altos-hills"
        assert normalize_jurisdiction("el-cerrito") == "city-el-cerrito"
        assert normalize_jurisdiction("daly-city") == "city-daly-city"
        assert normalize_jurisdiction("union-city") == "city-union-city"

    # ─────────── Combined format variations ───────────

    def test_all_format_variations_san_rafael(self):
        """San Rafael works in all input formats."""
        expected = "city-san-rafael"
        assert normalize_jurisdiction("san-rafael") == expected
        assert normalize_jurisdiction("san_rafael") == expected
        assert normalize_jurisdiction("sanrafael") == expected
        assert normalize_jurisdiction("san-rafael-ca") == expected
        assert normalize_jurisdiction("city-san-rafael") == expected
        assert normalize_jurisdiction("SAN-RAFAEL") == expected
        assert normalize_jurisdiction("SAN_RAFAEL") == expected

    def test_all_registered_cities_normalize(self):
        """All registered jurisdictions can be normalized from short form."""
        # Get all city keys and test normalization
        for city_key, config in JurisdictionRegistry.all_configs().items():
            # Test hyphenated form of city key
            hyphenated = city_key.replace("_", "-")
            result = normalize_jurisdiction(hyphenated)
            assert result == config.jurisdiction_id, f"Failed for {city_key}"


class TestAutoLoadedRegistry:
    """Test that jurisdictions are auto-loaded from config files."""

    def test_extraction_json_jurisdictions_registered(self):
        """Jurisdictions with extraction JSON configs are auto-registered."""
        # These have extraction JSONs but were NOT in the hardcoded registry
        auto_loaded = [
            "school-kentfield",
            "school-novato",
            "school-tamalpais",
            "college-marin",
            "city-sacramento",
            "city-national-city",
            "county-yolo",
            "county-alameda",
            "county-travis",
            "state-california",
        ]
        for jid in auto_loaded:
            assert JurisdictionRegistry.has_jurisdiction(jid), (
                f"{jid} should be auto-registered from extraction config"
            )

    def test_auto_loaded_timezone_derived_from_state(self):
        """Auto-loaded CA jurisdictions get America/Los_Angeles timezone."""
        ca_jurisdictions = [
            "school-kentfield",
            "college-marin",
            "county-yolo",
        ]
        for jid in ca_jurisdictions:
            tz = JurisdictionRegistry.get_timezone(jid)
            assert tz == "America/Los_Angeles", (
                f"{jid} should have CA timezone, got {tz}"
            )

    def test_auto_loaded_display_name_derived(self):
        """Auto-loaded jurisdictions have derived display names."""
        cases = {
            "school-kentfield": "Kentfield",
            "county-yolo": "Yolo County",
            "college-marin": "Marin",
            "city-sacramento": "Sacramento",
        }
        for jid, expected in cases.items():
            dn = JurisdictionRegistry.get_display_name(jid)
            assert dn == expected, f"{jid}: expected '{expected}', got '{dn}'"

    def test_hardcoded_entries_preserved(self):
        """Hardcoded entries retain their exact values after merge."""
        sr = JurisdictionRegistry.get("san_rafael")
        assert sr.agent_type == "san_rafael_cms"
        assert sr.wiki_files  # non-empty tuple from hardcoded
        assert "cityofsanrafael.org" in sr.domains

        dublin = JurisdictionRegistry.get("dublin")
        assert dublin.granicus_config is not None
        assert dublin.granicus_config.subdomain == "dublin"
        assert dublin.granicus_config.view_id == 1

    def test_hardcoded_count_preserved(self):
        """All 29 hardcoded jurisdictions are still present."""
        hardcoded_ids = [
            "city-san-rafael", "school-san-rafael", "city-berkeley",
            "city-mill-valley", "city-san-anselmo", "county-marin",
            "city-santa-rosa", "city-hayward", "city-oakland",
            "county-sonoma", "city-napa", "bart",
        ]
        for jid in hardcoded_ids:
            assert JurisdictionRegistry.has_jurisdiction(jid), (
                f"Hardcoded {jid} should still be registered"
            )

    def test_normalize_auto_loaded_jurisdictions(self):
        """Auto-loaded jurisdictions pass normalize_jurisdiction."""
        # These previously failed with JurisdictionError
        assert normalize_jurisdiction("school-kentfield") == "school-kentfield"
        assert normalize_jurisdiction("college-marin") == "college-marin"
        assert normalize_jurisdiction("county-yolo") == "county-yolo"
        assert normalize_jurisdiction("city-national-city") == "city-national-city"
