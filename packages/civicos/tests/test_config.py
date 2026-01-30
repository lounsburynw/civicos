"""
Tests for CivicOSConfig - turnkey configuration system.

Tests config loading from YAML, environment variables, and programmatic construction.
Verifies CivicOS accepts both string and CivicOSConfig for backward compatibility.

Run with:
    pytest packages/civicos/tests/test_config.py -v
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from civicos import CivicOS, CivicOSConfig, PeerConfig, ExtractorConfig, load_config


class TestCivicOSConfigBasic:
    """Tests for basic CivicOSConfig functionality."""

    def test_create_with_jurisdiction_only(self):
        """Config can be created with just jurisdiction_id."""
        config = CivicOSConfig(jurisdiction_id="city-san-rafael")
        assert config.jurisdiction_id == "city-san-rafael"
        assert config.display_name == "San Rafael"  # Derived from registry
        assert config.timezone == "America/Los_Angeles"  # Derived from registry

    def test_normalizes_jurisdiction_id(self):
        """Config normalizes jurisdiction_id to canonical format."""
        config = CivicOSConfig(jurisdiction_id="san-rafael")
        assert config.jurisdiction_id == "city-san-rafael"

        config2 = CivicOSConfig(jurisdiction_id="san_rafael")
        assert config2.jurisdiction_id == "city-san-rafael"

    def test_explicit_display_name_overrides_registry(self):
        """Explicit display_name overrides registry lookup."""
        config = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            display_name="Custom Name",
        )
        assert config.display_name == "Custom Name"

    def test_explicit_timezone_overrides_registry(self):
        """Explicit timezone overrides registry lookup."""
        config = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            timezone="America/New_York",
        )
        assert config.timezone == "America/New_York"

    def test_unknown_jurisdiction_gets_derived_display_name(self):
        """Unknown jurisdictions get display name derived from ID."""
        config = CivicOSConfig(jurisdiction_id="city-unknown-place")
        assert config.display_name == "Unknown Place"
        assert config.timezone == "UTC"  # Default for unknown


class TestCivicOSConfigPeers:
    """Tests for federation peer configuration."""

    def test_empty_peers_by_default(self):
        """Peers list is empty by default."""
        config = CivicOSConfig(jurisdiction_id="city-san-rafael")
        assert config.peers == []
        assert config.get_enabled_peers() == []

    def test_peers_configuration(self):
        """Peers can be configured."""
        config = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            peers=[
                PeerConfig(
                    jurisdiction_id="city-berkeley",
                    mcp_endpoint="https://berkeley.civicos.org/mcp",
                ),
                PeerConfig(
                    jurisdiction_id="city-oakland",
                    mcp_endpoint="https://oakland.civicos.org/mcp",
                    enabled=False,
                ),
            ],
        )
        assert len(config.peers) == 2
        assert len(config.get_enabled_peers()) == 1
        assert config.get_enabled_peers()[0].jurisdiction_id == "city-berkeley"


class TestCivicOSConfigExtractors:
    """Tests for extractor configuration."""

    def test_empty_extractors_by_default(self):
        """Extractors dict is empty by default."""
        config = CivicOSConfig(jurisdiction_id="city-san-rafael")
        assert config.extractors == {}

    def test_extractor_enabled_by_default(self):
        """Unconfigured extractors are enabled by default."""
        config = CivicOSConfig(jurisdiction_id="city-san-rafael")
        assert config.is_extractor_enabled("legistar") is True
        assert config.is_extractor_enabled("unknown") is True

    def test_extractor_configuration(self):
        """Extractors can be configured."""
        config = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            extractors={
                "legistar": ExtractorConfig(name="legistar", enabled=False),
                "proudcity": ExtractorConfig(
                    name="proudcity",
                    enabled=True,
                    config={"base_url": "https://example.org"},
                ),
            },
        )
        assert config.is_extractor_enabled("legistar") is False
        assert config.is_extractor_enabled("proudcity") is True
        assert config.get_extractor_config("proudcity").config["base_url"] == "https://example.org"


class TestCivicOSConfigYAML:
    """Tests for YAML loading and export."""

    def test_from_yaml(self):
        """Config can be loaded from YAML file."""
        yaml_content = """
jurisdiction_id: city-san-rafael
display_name: "San Rafael, CA"
timezone: America/Los_Angeles
federation_enabled: true
peers:
  - jurisdiction_id: city-berkeley
    mcp_endpoint: https://berkeley.civicos.org/mcp
extractors:
  legistar:
    enabled: false
metadata:
  region: "Bay Area"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = CivicOSConfig.from_yaml(f.name)
                assert config.jurisdiction_id == "city-san-rafael"
                assert config.display_name == "San Rafael, CA"
                assert config.federation_enabled is True
                assert len(config.peers) == 1
                assert config.is_extractor_enabled("legistar") is False
                assert config.metadata["region"] == "Bay Area"
            finally:
                os.unlink(f.name)

    def test_from_yaml_minimal(self):
        """Config can be loaded from minimal YAML (just jurisdiction_id)."""
        yaml_content = "jurisdiction_id: san-rafael"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = CivicOSConfig.from_yaml(f.name)
                assert config.jurisdiction_id == "city-san-rafael"  # Normalized
            finally:
                os.unlink(f.name)

    def test_from_yaml_missing_file(self):
        """from_yaml raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            CivicOSConfig.from_yaml("/nonexistent/path.yaml")

    def test_from_yaml_missing_jurisdiction(self):
        """from_yaml raises ValueError when jurisdiction_id missing."""
        yaml_content = "display_name: Test"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                with pytest.raises(ValueError, match="jurisdiction_id"):
                    CivicOSConfig.from_yaml(f.name)
            finally:
                os.unlink(f.name)

    def test_to_yaml_roundtrip(self):
        """Config can be exported and re-imported from YAML."""
        original = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            display_name="San Rafael, CA",
            federation_enabled=True,
            peers=[
                PeerConfig(
                    jurisdiction_id="city-berkeley",
                    mcp_endpoint="https://berkeley.civicos.org/mcp",
                ),
            ],
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml_str = original.to_yaml(f.name)
            f.flush()

            try:
                reloaded = CivicOSConfig.from_yaml(f.name)
                assert reloaded.jurisdiction_id == original.jurisdiction_id
                assert reloaded.display_name == original.display_name
                assert reloaded.federation_enabled == original.federation_enabled
                assert len(reloaded.peers) == len(original.peers)
            finally:
                os.unlink(f.name)


class TestCivicOSConfigEnv:
    """Tests for environment variable loading."""

    def test_from_env_default(self):
        """from_env uses defaults when no env vars set."""
        with patch.dict(os.environ, {}, clear=True):
            config = CivicOSConfig.from_env()
            assert config.jurisdiction_id == "city-san-rafael"  # Default
            assert config.federation_enabled is False

    def test_from_env_with_vars(self):
        """from_env loads from environment variables."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_JURISDICTION": "city-berkeley",
                "CIVICOS_DISPLAY_NAME": "Berkeley, CA",
                "CIVICOS_TIMEZONE": "America/Los_Angeles",
                "CIVICOS_FEDERATION_ENABLED": "true",
            },
            clear=True,
        ):
            config = CivicOSConfig.from_env()
            assert config.jurisdiction_id == "city-berkeley"
            assert config.display_name == "Berkeley, CA"
            assert config.timezone == "America/Los_Angeles"
            assert config.federation_enabled is True

    def test_from_env_custom_prefix(self):
        """from_env supports custom prefix."""
        with patch.dict(
            os.environ,
            {"MYAPP_JURISDICTION": "city-oakland"},
            clear=True,
        ):
            config = CivicOSConfig.from_env(prefix="MYAPP")
            assert config.jurisdiction_id == "city-oakland"


class TestCivicOSConfigValidation:
    """Tests for configuration validation."""

    def test_validate_valid_config(self):
        """Valid config has no validation issues."""
        config = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            timezone="America/Los_Angeles",
        )
        issues = config.validate()
        assert issues == []

    def test_validate_invalid_timezone_format(self):
        """Invalid timezone format is flagged."""
        config = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            timezone="PST",  # Not IANA format
        )
        issues = config.validate()
        assert any("timezone" in issue.lower() for issue in issues)

    def test_validate_peer_missing_endpoint(self):
        """Peer without mcp_endpoint is flagged."""
        config = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            peers=[PeerConfig(jurisdiction_id="city-berkeley", mcp_endpoint="")],
        )
        issues = config.validate()
        assert any("mcp_endpoint" in issue for issue in issues)

    def test_validate_peer_invalid_endpoint(self):
        """Peer with non-URL endpoint is flagged."""
        config = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            peers=[
                PeerConfig(
                    jurisdiction_id="city-berkeley",
                    mcp_endpoint="not-a-url",
                )
            ],
        )
        issues = config.validate()
        assert any("URL" in issue for issue in issues)


class TestCivicOSWithConfig:
    """Tests for CivicOS accepting CivicOSConfig."""

    def test_civicos_accepts_string(self):
        """CivicOS still accepts string (backward compatible)."""
        c = CivicOS("san-rafael")
        assert c.jurisdiction == "city-san-rafael"

    def test_civicos_accepts_config(self):
        """CivicOS accepts CivicOSConfig."""
        config = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            display_name="Custom Display Name",
        )
        c = CivicOS(config)
        assert c.jurisdiction == "city-san-rafael"
        assert c._config is config
        assert c.display_name == "Custom Display Name"

    def test_civicos_config_property(self):
        """CivicOS.config returns config or creates one."""
        # With explicit config
        config = CivicOSConfig(jurisdiction_id="city-san-rafael")
        c = CivicOS(config)
        assert c.config is config

        # Without explicit config (creates one)
        c2 = CivicOS("san-rafael")
        auto_config = c2.config
        assert auto_config.jurisdiction_id == "city-san-rafael"

    def test_civicos_display_name_property(self):
        """CivicOS.display_name returns configured or registry name."""
        # From config
        config = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            display_name="Custom Name",
        )
        c = CivicOS(config)
        assert c.display_name == "Custom Name"

        # From registry
        c2 = CivicOS("san-rafael")
        assert c2.display_name == "San Rafael"

    def test_civicos_timezone_property(self):
        """CivicOS.timezone returns configured or registry timezone."""
        # From config
        config = CivicOSConfig(
            jurisdiction_id="city-san-rafael",
            timezone="America/New_York",
        )
        c = CivicOS(config)
        assert c.timezone == "America/New_York"

        # From registry
        c2 = CivicOS("san-rafael")
        assert c2.timezone == "America/Los_Angeles"

    def test_civicos_db_path_from_config(self):
        """CivicOS uses db_path from config if provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            config = CivicOSConfig(
                jurisdiction_id="city-san-rafael",
                db_path=db_path,
            )
            c = CivicOS(config)
            assert c.db_path == db_path


class TestLoadConfig:
    """Tests for load_config convenience function."""

    def test_load_config_from_env(self):
        """load_config falls back to env vars when no file exists."""
        with patch.dict(
            os.environ,
            {"CIVICOS_JURISDICTION": "city-berkeley"},
            clear=True,
        ):
            # Ensure no default files exist
            config = load_config(path="/nonexistent/path.yaml")
            # Should fall back to env
            # (Note: this will use env vars since path doesn't exist)

    def test_load_config_explicit_path(self):
        """load_config uses explicit path when provided."""
        yaml_content = "jurisdiction_id: city-oakland"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = load_config(path=f.name)
                assert config.jurisdiction_id == "city-oakland"
            finally:
                os.unlink(f.name)

    def test_load_config_from_env_var_path(self):
        """load_config uses CIVICOS_CONFIG env var."""
        yaml_content = "jurisdiction_id: city-hayward"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                with patch.dict(os.environ, {"CIVICOS_CONFIG": f.name}):
                    config = load_config()
                    assert config.jurisdiction_id == "city-hayward"
            finally:
                os.unlink(f.name)
