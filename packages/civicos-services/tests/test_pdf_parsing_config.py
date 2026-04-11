"""
Tests for pdf_parsing_config.py — PDF parsing tier configuration, environment-based
API key loading, auto-detection of the best available tier, and config validation
warnings for missing keys / libraries.

Mocks: os.environ (for API key env vars), sys.modules (to simulate presence/absence
of optional libraries like docling and llama_parse).
Real: all dataclass instantiation, enum values, tier selection logic, warning
generation. No subject-under-test mocking.

To run:
    pytest packages/civicos-services/tests/test_pdf_parsing_config.py -q --override-ini="addopts="
"""

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from civicos_services.config.pdf_parsing_config import (
    ConfigManager,
    DEPLOYMENT_CONFIGS,
    PDFParsingConfig,
    PDFParsingTier,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _with_libs(docling: bool = False, llama_parse: bool = False):
    """Return a patch.dict context manager for sys.modules that simulates
    the presence (MagicMock) or absence (None -> ImportError) of optional libs.

    Setting sys.modules[name] = None causes `import name` to raise
    ModuleNotFoundError, which is exactly the state we want to simulate when
    pretending a library is not installed.
    """
    mods = {
        "docling": MagicMock() if docling else None,
        "llama_parse": MagicMock() if llama_parse else None,
    }
    return patch.dict(sys.modules, mods)


# ---------------------------------------------------------------------------
# PDFParsingTier enum
# ---------------------------------------------------------------------------

class TestPDFParsingTier:
    def test_basic_value_is_basic(self):
        assert PDFParsingTier.BASIC.value == "basic"

    def test_professional_value_is_pro(self):
        # Specifically "pro", not "professional"
        assert PDFParsingTier.PROFESSIONAL.value == "pro"

    def test_enterprise_value_is_enterprise(self):
        assert PDFParsingTier.ENTERPRISE.value == "enterprise"

    def test_research_value_is_research(self):
        assert PDFParsingTier.RESEARCH.value == "research"

    def test_has_exactly_four_tiers(self):
        assert len(list(PDFParsingTier)) == 4

    def test_tier_members_are_distinct(self):
        values = {t.value for t in PDFParsingTier}
        assert values == {"basic", "pro", "enterprise", "research"}


# ---------------------------------------------------------------------------
# PDFParsingConfig dataclass
# ---------------------------------------------------------------------------

class TestPDFParsingConfig:
    def test_default_safety_flags_are_true(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.BASIC,
            api_keys={},
            cost_limit_monthly=0.0,
        )
        assert config.enable_circuit_breakers is True
        assert config.enable_cost_tracking is True
        assert config.fallback_to_pypdf is True

    def test_required_fields_stored_verbatim(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.PROFESSIONAL,
            api_keys={"LLAMAPARSE_API_KEY": "abc"},
            cost_limit_monthly=42.5,
        )
        assert config.tier is PDFParsingTier.PROFESSIONAL
        assert config.api_keys == {"LLAMAPARSE_API_KEY": "abc"}
        assert config.cost_limit_monthly == 42.5

    def test_safety_flags_can_be_overridden_to_false(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.ENTERPRISE,
            api_keys={},
            cost_limit_monthly=100.0,
            enable_circuit_breakers=False,
            enable_cost_tracking=False,
            fallback_to_pypdf=False,
        )
        assert config.enable_circuit_breakers is False
        assert config.enable_cost_tracking is False
        assert config.fallback_to_pypdf is False


# ---------------------------------------------------------------------------
# ConfigManager.get_foundation_config
# ---------------------------------------------------------------------------

class TestGetFoundationConfig:
    def test_tier_is_basic(self):
        config = ConfigManager.get_foundation_config()
        assert config.tier is PDFParsingTier.BASIC

    def test_cost_limit_is_zero(self):
        config = ConfigManager.get_foundation_config()
        assert config.cost_limit_monthly == 0.0

    def test_api_keys_is_empty_dict(self):
        config = ConfigManager.get_foundation_config()
        assert config.api_keys == {}

    def test_circuit_breakers_enabled(self):
        config = ConfigManager.get_foundation_config()
        assert config.enable_circuit_breakers is True

    def test_cost_tracking_enabled(self):
        config = ConfigManager.get_foundation_config()
        assert config.enable_cost_tracking is True

    def test_fallback_to_pypdf_enabled(self):
        config = ConfigManager.get_foundation_config()
        assert config.fallback_to_pypdf is True


# ---------------------------------------------------------------------------
# ConfigManager.get_professional_config
# ---------------------------------------------------------------------------

class TestGetProfessionalConfig:
    def test_tier_is_professional(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_professional_config()
        assert config.tier is PDFParsingTier.PROFESSIONAL

    def test_cost_limit_is_50(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_professional_config()
        assert config.cost_limit_monthly == 50.0

    def test_reads_llamaparse_key_from_env(self):
        with patch.dict(
            os.environ, {"LLAMAPARSE_API_KEY": "secret-llama-123"}, clear=True
        ):
            config = ConfigManager.get_professional_config()
        assert config.api_keys["LLAMAPARSE_API_KEY"] == "secret-llama-123"

    def test_uses_empty_string_when_env_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_professional_config()
        assert config.api_keys["LLAMAPARSE_API_KEY"] == ""

    def test_only_contains_llamaparse_key(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_professional_config()
        assert list(config.api_keys.keys()) == ["LLAMAPARSE_API_KEY"]

    def test_fallback_to_pypdf_enabled(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_professional_config()
        assert config.fallback_to_pypdf is True


# ---------------------------------------------------------------------------
# ConfigManager.get_enterprise_config
# ---------------------------------------------------------------------------

class TestGetEnterpriseConfig:
    def test_tier_is_enterprise(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_enterprise_config()
        assert config.tier is PDFParsingTier.ENTERPRISE

    def test_cost_limit_is_200(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_enterprise_config()
        assert config.cost_limit_monthly == 200.0

    def test_api_keys_include_azure_and_llamaparse(self):
        env = {
            "LLAMAPARSE_API_KEY": "llama-k",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": "azure-k",
            "AZURE_ENDPOINT": "https://example.cognitive.azure.com",
        }
        with patch.dict(os.environ, env, clear=True):
            config = ConfigManager.get_enterprise_config()
        assert config.api_keys["LLAMAPARSE_API_KEY"] == "llama-k"
        assert config.api_keys["AZURE_DOCUMENT_INTELLIGENCE_KEY"] == "azure-k"
        assert (
            config.api_keys["AZURE_ENDPOINT"]
            == "https://example.cognitive.azure.com"
        )

    def test_missing_env_vars_become_empty_strings(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_enterprise_config()
        assert config.api_keys["LLAMAPARSE_API_KEY"] == ""
        assert config.api_keys["AZURE_DOCUMENT_INTELLIGENCE_KEY"] == ""
        assert config.api_keys["AZURE_ENDPOINT"] == ""

    def test_has_exactly_three_api_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_enterprise_config()
        assert set(config.api_keys.keys()) == {
            "LLAMAPARSE_API_KEY",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY",
            "AZURE_ENDPOINT",
        }

    def test_does_not_include_mistral_key(self):
        env = {"MISTRAL_API_KEY": "should-be-ignored"}
        with patch.dict(os.environ, env, clear=True):
            config = ConfigManager.get_enterprise_config()
        assert "MISTRAL_API_KEY" not in config.api_keys


# ---------------------------------------------------------------------------
# ConfigManager.get_research_config
# ---------------------------------------------------------------------------

class TestGetResearchConfig:
    def test_tier_is_research(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_research_config()
        assert config.tier is PDFParsingTier.RESEARCH

    def test_cost_limit_is_500(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_research_config()
        assert config.cost_limit_monthly == 500.0

    def test_reads_all_four_keys_from_env(self):
        env = {
            "LLAMAPARSE_API_KEY": "l",
            "MISTRAL_API_KEY": "m",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": "a",
            "AZURE_ENDPOINT": "e",
        }
        with patch.dict(os.environ, env, clear=True):
            config = ConfigManager.get_research_config()
        assert config.api_keys["LLAMAPARSE_API_KEY"] == "l"
        assert config.api_keys["MISTRAL_API_KEY"] == "m"
        assert config.api_keys["AZURE_DOCUMENT_INTELLIGENCE_KEY"] == "a"
        assert config.api_keys["AZURE_ENDPOINT"] == "e"

    def test_has_exactly_four_api_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_research_config()
        assert set(config.api_keys.keys()) == {
            "LLAMAPARSE_API_KEY",
            "MISTRAL_API_KEY",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY",
            "AZURE_ENDPOINT",
        }

    def test_missing_env_vars_become_empty_strings(self):
        with patch.dict(os.environ, {}, clear=True):
            config = ConfigManager.get_research_config()
        assert config.api_keys["MISTRAL_API_KEY"] == ""


# ---------------------------------------------------------------------------
# ConfigManager.auto_detect_config — tier selection branching
# ---------------------------------------------------------------------------

class TestAutoDetectConfig:
    def test_no_env_no_libs_returns_foundation(self):
        with patch.dict(os.environ, {}, clear=True), _with_libs(
            docling=False, llama_parse=False
        ):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.BASIC
        assert config.cost_limit_monthly == 0.0

    def test_llamaparse_env_without_lib_falls_back_to_foundation(self):
        """Professional requires BOTH env var AND llama_parse lib."""
        with patch.dict(
            os.environ, {"LLAMAPARSE_API_KEY": "k"}, clear=True
        ), _with_libs(docling=False, llama_parse=False):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.BASIC

    def test_llamaparse_lib_without_env_returns_foundation(self):
        """llama_parse lib alone is not enough — env var is required."""
        with patch.dict(os.environ, {}, clear=True), _with_libs(
            docling=False, llama_parse=True
        ):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.BASIC

    def test_llamaparse_env_plus_lib_returns_professional(self):
        with patch.dict(
            os.environ, {"LLAMAPARSE_API_KEY": "k"}, clear=True
        ), _with_libs(docling=False, llama_parse=True):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.PROFESSIONAL
        assert config.cost_limit_monthly == 50.0

    def test_azure_and_llamaparse_env_returns_enterprise(self):
        env = {
            "LLAMAPARSE_API_KEY": "l",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": "a",
        }
        with patch.dict(os.environ, env, clear=True), _with_libs(
            docling=False, llama_parse=True
        ):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.ENTERPRISE
        assert config.cost_limit_monthly == 200.0

    def test_docling_lib_plus_llamaparse_env_returns_enterprise(self):
        """Enterprise can be reached via docling lib even without Azure env."""
        with patch.dict(
            os.environ, {"LLAMAPARSE_API_KEY": "l"}, clear=True
        ), _with_libs(docling=True, llama_parse=True):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.ENTERPRISE

    def test_docling_alone_not_enough_for_enterprise(self):
        """Enterprise still requires the LLAMAPARSE env var."""
        with patch.dict(os.environ, {}, clear=True), _with_libs(
            docling=True, llama_parse=True
        ):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.BASIC

    def test_all_three_env_vars_return_research(self):
        env = {
            "LLAMAPARSE_API_KEY": "l",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": "a",
            "MISTRAL_API_KEY": "m",
        }
        with patch.dict(os.environ, env, clear=True), _with_libs(
            docling=True, llama_parse=True
        ):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.RESEARCH
        assert config.cost_limit_monthly == 500.0

    def test_research_priority_over_enterprise_even_without_libs(self):
        """With all three env vars set, research wins even when libs missing."""
        env = {
            "LLAMAPARSE_API_KEY": "l",
            "AZURE_DOCUMENT_INTELLIGENCE_KEY": "a",
            "MISTRAL_API_KEY": "m",
        }
        with patch.dict(os.environ, env, clear=True), _with_libs(
            docling=False, llama_parse=False
        ):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.RESEARCH

    def test_mistral_alone_returns_foundation(self):
        with patch.dict(
            os.environ, {"MISTRAL_API_KEY": "m"}, clear=True
        ), _with_libs(docling=False, llama_parse=False):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.BASIC

    def test_azure_alone_returns_foundation(self):
        with patch.dict(
            os.environ, {"AZURE_DOCUMENT_INTELLIGENCE_KEY": "a"}, clear=True
        ), _with_libs(docling=False, llama_parse=False):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.BASIC

    def test_mistral_plus_llamaparse_without_azure_returns_professional(self):
        """Research needs azure too — otherwise it falls through."""
        env = {
            "LLAMAPARSE_API_KEY": "l",
            "MISTRAL_API_KEY": "m",
        }
        with patch.dict(os.environ, env, clear=True), _with_libs(
            docling=False, llama_parse=True
        ):
            config = ConfigManager.auto_detect_config()
        assert config.tier is PDFParsingTier.PROFESSIONAL


# ---------------------------------------------------------------------------
# ConfigManager.validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:
    def test_foundation_produces_no_warnings(self):
        config = ConfigManager.get_foundation_config()
        warnings = ConfigManager.validate_config(config)
        assert warnings == []

    def test_foundation_does_not_import_llama_parse(self):
        """BASIC tier should not warn even when libs are missing."""
        config = ConfigManager.get_foundation_config()
        with _with_libs(docling=False, llama_parse=False):
            warnings = ConfigManager.validate_config(config)
        assert warnings == []

    def test_professional_missing_key_warns_specifically(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.PROFESSIONAL,
            api_keys={},
            cost_limit_monthly=50.0,
        )
        with _with_libs(llama_parse=True):
            warnings = ConfigManager.validate_config(config)
        assert "Professional tier requires LLAMAPARSE_API_KEY" in warnings

    def test_professional_empty_key_warns(self):
        """Empty string is treated as missing (falsy)."""
        config = PDFParsingConfig(
            tier=PDFParsingTier.PROFESSIONAL,
            api_keys={"LLAMAPARSE_API_KEY": ""},
            cost_limit_monthly=50.0,
        )
        with _with_libs(llama_parse=True):
            warnings = ConfigManager.validate_config(config)
        assert "Professional tier requires LLAMAPARSE_API_KEY" in warnings

    def test_professional_with_key_and_lib_has_no_warnings(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.PROFESSIONAL,
            api_keys={"LLAMAPARSE_API_KEY": "k"},
            cost_limit_monthly=50.0,
        )
        with _with_libs(llama_parse=True):
            warnings = ConfigManager.validate_config(config)
        assert warnings == []

    def test_professional_missing_llamaparse_lib_warns(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.PROFESSIONAL,
            api_keys={"LLAMAPARSE_API_KEY": "k"},
            cost_limit_monthly=50.0,
        )
        with _with_libs(llama_parse=False):
            warnings = ConfigManager.validate_config(config)
        assert "Advanced tiers require 'pip install llama-parse'" in warnings

    def test_enterprise_missing_both_keys_warns_twice(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.ENTERPRISE,
            api_keys={},
            cost_limit_monthly=200.0,
        )
        with _with_libs(docling=True, llama_parse=True):
            warnings = ConfigManager.validate_config(config)
        assert "Enterprise tier should have LLAMAPARSE_API_KEY" in warnings
        assert (
            "Enterprise tier should have AZURE_DOCUMENT_INTELLIGENCE_KEY"
            in warnings
        )

    def test_enterprise_missing_only_azure_warns_once(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.ENTERPRISE,
            api_keys={"LLAMAPARSE_API_KEY": "l"},
            cost_limit_monthly=200.0,
        )
        with _with_libs(docling=True, llama_parse=True):
            warnings = ConfigManager.validate_config(config)
        assert (
            "Enterprise tier should have AZURE_DOCUMENT_INTELLIGENCE_KEY"
            in warnings
        )
        assert "Enterprise tier should have LLAMAPARSE_API_KEY" not in warnings

    def test_enterprise_missing_docling_lib_warns(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.ENTERPRISE,
            api_keys={
                "LLAMAPARSE_API_KEY": "l",
                "AZURE_DOCUMENT_INTELLIGENCE_KEY": "a",
            },
            cost_limit_monthly=200.0,
        )
        with _with_libs(docling=False, llama_parse=True):
            warnings = ConfigManager.validate_config(config)
        assert (
            "Enterprise/Research tiers recommend 'pip install docling'"
            in warnings
        )

    def test_enterprise_with_all_keys_and_libs_no_warnings(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.ENTERPRISE,
            api_keys={
                "LLAMAPARSE_API_KEY": "l",
                "AZURE_DOCUMENT_INTELLIGENCE_KEY": "a",
                "AZURE_ENDPOINT": "e",
            },
            cost_limit_monthly=200.0,
        )
        with _with_libs(docling=True, llama_parse=True):
            warnings = ConfigManager.validate_config(config)
        assert warnings == []

    def test_research_missing_llamaparse_and_mistral_warns(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.RESEARCH,
            api_keys={"AZURE_DOCUMENT_INTELLIGENCE_KEY": "a"},
            cost_limit_monthly=500.0,
        )
        with _with_libs(docling=True, llama_parse=True):
            warnings = ConfigManager.validate_config(config)
        assert "Research tier should have LLAMAPARSE_API_KEY" in warnings
        assert "Research tier should have MISTRAL_API_KEY" in warnings

    def test_research_missing_only_mistral_warns_once(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.RESEARCH,
            api_keys={
                "LLAMAPARSE_API_KEY": "l",
                "AZURE_DOCUMENT_INTELLIGENCE_KEY": "a",
            },
            cost_limit_monthly=500.0,
        )
        with _with_libs(docling=True, llama_parse=True):
            warnings = ConfigManager.validate_config(config)
        assert "Research tier should have MISTRAL_API_KEY" in warnings
        assert "Research tier should have LLAMAPARSE_API_KEY" not in warnings

    def test_research_with_all_keys_and_libs_no_warnings(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.RESEARCH,
            api_keys={
                "LLAMAPARSE_API_KEY": "l",
                "MISTRAL_API_KEY": "m",
                "AZURE_DOCUMENT_INTELLIGENCE_KEY": "a",
                "AZURE_ENDPOINT": "e",
            },
            cost_limit_monthly=500.0,
        )
        with _with_libs(docling=True, llama_parse=True):
            warnings = ConfigManager.validate_config(config)
        assert warnings == []

    def test_research_without_libs_warns_about_both(self):
        config = PDFParsingConfig(
            tier=PDFParsingTier.RESEARCH,
            api_keys={
                "LLAMAPARSE_API_KEY": "l",
                "MISTRAL_API_KEY": "m",
                "AZURE_DOCUMENT_INTELLIGENCE_KEY": "a",
                "AZURE_ENDPOINT": "e",
            },
            cost_limit_monthly=500.0,
        )
        with _with_libs(docling=False, llama_parse=False):
            warnings = ConfigManager.validate_config(config)
        assert "Advanced tiers require 'pip install llama-parse'" in warnings
        assert (
            "Enterprise/Research tiers recommend 'pip install docling'"
            in warnings
        )

    def test_validate_returns_mutable_list(self):
        """Callers mutate this list downstream; must be a mutable list, not a tuple."""
        config = ConfigManager.get_foundation_config()
        warnings = ConfigManager.validate_config(config)
        # A list supports append; a tuple would raise AttributeError.
        warnings.append("caller-added warning")
        assert warnings == ["caller-added warning"]


# ---------------------------------------------------------------------------
# DEPLOYMENT_CONFIGS module-level dict
# ---------------------------------------------------------------------------

class TestDeploymentConfigs:
    def test_contains_all_five_keys(self):
        assert set(DEPLOYMENT_CONFIGS.keys()) == {
            "foundation",
            "professional",
            "enterprise",
            "research",
            "auto",
        }

    def test_foundation_key_maps_to_basic_tier(self):
        assert DEPLOYMENT_CONFIGS["foundation"].tier is PDFParsingTier.BASIC

    def test_professional_key_maps_to_professional_tier(self):
        assert (
            DEPLOYMENT_CONFIGS["professional"].tier
            is PDFParsingTier.PROFESSIONAL
        )

    def test_enterprise_key_maps_to_enterprise_tier(self):
        assert DEPLOYMENT_CONFIGS["enterprise"].tier is PDFParsingTier.ENTERPRISE

    def test_research_key_maps_to_research_tier(self):
        assert DEPLOYMENT_CONFIGS["research"].tier is PDFParsingTier.RESEARCH

    def test_cost_limits_are_ordered(self):
        """Foundation < Professional < Enterprise < Research."""
        assert (
            DEPLOYMENT_CONFIGS["foundation"].cost_limit_monthly
            < DEPLOYMENT_CONFIGS["professional"].cost_limit_monthly
            < DEPLOYMENT_CONFIGS["enterprise"].cost_limit_monthly
            < DEPLOYMENT_CONFIGS["research"].cost_limit_monthly
        )

    def test_foundation_cost_is_zero(self):
        assert DEPLOYMENT_CONFIGS["foundation"].cost_limit_monthly == 0.0

    def test_professional_cost_is_50(self):
        assert DEPLOYMENT_CONFIGS["professional"].cost_limit_monthly == 50.0

    def test_enterprise_cost_is_200(self):
        assert DEPLOYMENT_CONFIGS["enterprise"].cost_limit_monthly == 200.0

    def test_research_cost_is_500(self):
        assert DEPLOYMENT_CONFIGS["research"].cost_limit_monthly == 500.0

    def test_auto_entry_tier_and_cost_are_consistent(self):
        """The `auto` entry is produced by auto_detect_config() at import time.

        Whatever tier was auto-detected, its cost_limit_monthly must match
        the canonical cost for that tier, and safety flags must always be on.
        A mutation that, for example, mis-wired a tier's cost would be caught
        here regardless of which tier happens to be selected in the test env.
        """
        auto = DEPLOYMENT_CONFIGS["auto"]
        assert isinstance(auto, PDFParsingConfig)
        expected_cost_for_tier = {
            PDFParsingTier.BASIC: 0.0,
            PDFParsingTier.PROFESSIONAL: 50.0,
            PDFParsingTier.ENTERPRISE: 200.0,
            PDFParsingTier.RESEARCH: 500.0,
        }
        assert auto.cost_limit_monthly == expected_cost_for_tier[auto.tier]
        # Safety flags are unconditionally enabled by every config factory.
        assert auto.enable_circuit_breakers is True
        assert auto.enable_cost_tracking is True
        assert auto.fallback_to_pypdf is True
