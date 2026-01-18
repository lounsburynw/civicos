"""
Tests for configuration validation.

Tests the CivicConfig.validate_environment() method and related
configuration validation functionality.

Run with:
    pytest packages/civic/tests/test_config_validation.py -v
"""

import os
from unittest.mock import patch

import pytest

from civicos_services.core.config import CivicConfig, ValidationResult, validate_config


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_default_values(self):
        """ValidationResult should have sensible defaults."""
        result = ValidationResult(environment="test")
        assert result.environment == "test"
        assert result.passed is False
        assert result.errors == []
        assert result.warnings == []
        assert result.suggestions == {}
        assert result.checked_at is None

    def test_format_errors_with_all_sections(self):
        """format_errors should include all sections when present."""
        result = ValidationResult(
            environment="production",
            errors=["Missing CIVICOS_WEB_KEY", "Missing OPENAI_API_KEY"],
            warnings=["CIVICOS_ENV not set"],
            suggestions={"CIVICOS_WEB_KEY": "Generate with: openssl rand -hex 32"},
        )
        formatted = result.format_errors()

        assert "production" in formatted
        assert "ERRORS (must fix):" in formatted
        assert "Missing CIVICOS_WEB_KEY" in formatted
        assert "Missing OPENAI_API_KEY" in formatted
        assert "WARNINGS (should address):" in formatted
        assert "CIVICOS_ENV not set" in formatted
        assert "SUGGESTIONS:" in formatted
        assert "Generate with: openssl rand -hex 32" in formatted

    def test_format_summary(self):
        """format_summary should return concise status."""
        result = ValidationResult(
            environment="development", passed=True, errors=[], warnings=["minor issue"]
        )
        summary = result.format_summary()

        assert "PASSED" in summary
        assert "development" in summary
        assert "Errors: 0" in summary
        assert "Warnings: 1" in summary

    def test_to_dict(self):
        """to_dict should return serializable dictionary."""
        result = ValidationResult(
            environment="staging",
            passed=True,
            errors=[],
            warnings=["test warning"],
            suggestions={"key": "value"},
        )
        d = result.to_dict()

        assert d["environment"] == "staging"
        assert d["passed"] is True
        assert d["errors"] == []
        assert d["warnings"] == ["test warning"]
        assert d["suggestions"] == {"key": "value"}


class TestCoreConfigValidation:
    """Tests for core configuration validation."""

    def test_validates_civic_env_warning_when_missing(self):
        """Should warn when CIVICOS_ENV is not set."""
        with patch.dict(os.environ, {}, clear=True):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        # Check for the warning about CIVICOS_ENV
        env_warnings = [w for w in result.warnings if "CIVICOS_ENV" in w]
        assert len(env_warnings) >= 1

    def test_validates_civic_env_warning_for_invalid_value(self):
        """Should warn when CIVICOS_ENV has invalid value."""
        with patch.dict(os.environ, {"CIVICOS_ENV": "invalid_env"}, clear=True):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        env_warnings = [w for w in result.warnings if "non-standard" in w]
        assert len(env_warnings) >= 1

    def test_validates_port_invalid_string(self):
        """Should error when CIVICOS_API_PORT is not a valid integer."""
        with patch.dict(
            os.environ,
            {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true", "CIVICOS_API_PORT": "not_a_number"},
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        port_errors = [e for e in result.errors if "CIVICOS_API_PORT" in e]
        assert len(port_errors) >= 1


class TestSecurityConfigValidation:
    """Tests for security configuration validation."""

    def test_development_requires_auth_method(self):
        """Development environment requires at least one auth method."""
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        # Should fail because no auth method
        assert not result.passed
        auth_errors = [
            e for e in result.errors if "CIVICOS_WEB_KEY" in e or "CIVICOS_DEV_MODE" in e
        ]
        assert len(auth_errors) >= 1

    def test_development_passes_with_dev_mode(self):
        """Development should pass with CIVICOS_DEV_MODE=true."""
        with patch.dict(
            os.environ, {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true"}, clear=True
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        # Security errors should be resolved
        auth_errors = [
            e for e in result.errors if "CIVICOS_WEB_KEY" in e or "CIVICOS_DEV_MODE" in e
        ]
        assert len(auth_errors) == 0

    def test_development_passes_with_web_key(self):
        """Development should pass with CIVICOS_WEB_KEY set."""
        with patch.dict(
            os.environ, {"CIVICOS_ENV": "development", "CIVICOS_WEB_KEY": "dev_key_local"}, clear=True
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        auth_errors = [
            e for e in result.errors if "CIVICOS_WEB_KEY" in e or "CIVICOS_DEV_MODE" in e
        ]
        assert len(auth_errors) == 0

    def test_production_requires_web_key(self):
        """Production environment requires CIVICOS_WEB_KEY."""
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        assert not result.passed
        key_errors = [e for e in result.errors if "CIVICOS_WEB_KEY" in e]
        assert len(key_errors) >= 1

    def test_production_rejects_dev_key(self):
        """Production should reject dev_key_local as CIVICOS_WEB_KEY."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_ENV": "production",
                "CIVICOS_WEB_KEY": "dev_key_local",
                "CIVICOS_CORS_ORIGINS": "https://example.com",
                "OPENAI_API_KEY": "sk-real-key-here-12345678901234567890",
            },
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        assert not result.passed
        dev_key_errors = [e for e in result.errors if "dev_key_local" in e]
        assert len(dev_key_errors) >= 1

    def test_production_requires_cors_origins(self):
        """Production environment requires CIVICOS_CORS_ORIGINS."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_ENV": "production",
                "CIVICOS_WEB_KEY": "secure_key_12345678901234567890123456",
                "OPENAI_API_KEY": "sk-real-key-here-12345678901234567890",
            },
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        cors_errors = [e for e in result.errors if "CIVICOS_CORS_ORIGINS" in e]
        assert len(cors_errors) >= 1

    def test_production_rejects_wildcard_cors(self):
        """Production should reject '*' in CORS origins."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_ENV": "production",
                "CIVICOS_WEB_KEY": "secure_key_12345678901234567890123456",
                "CIVICOS_CORS_ORIGINS": "*",
                "OPENAI_API_KEY": "sk-real-key-here-12345678901234567890",
            },
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        wildcard_errors = [e for e in result.errors if "*" in e]
        assert len(wildcard_errors) >= 1


class TestLLMConfigValidation:
    """Tests for LLM configuration validation."""

    def test_production_requires_openai_key(self):
        """Production environment requires OPENAI_API_KEY."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_ENV": "production",
                "CIVICOS_WEB_KEY": "secure_key_12345678901234567890123456",
                "CIVICOS_CORS_ORIGINS": "https://example.com",
            },
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        openai_errors = [e for e in result.errors if "OPENAI_API_KEY" in e]
        assert len(openai_errors) >= 1

    def test_production_rejects_placeholder_key(self):
        """Production should reject placeholder OPENAI_API_KEY."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_ENV": "production",
                "CIVICOS_WEB_KEY": "secure_key_12345678901234567890123456",
                "CIVICOS_CORS_ORIGINS": "https://example.com",
                "OPENAI_API_KEY": "sk-proj-...",
            },
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        placeholder_errors = [e for e in result.errors if "placeholder" in e.lower()]
        assert len(placeholder_errors) >= 1

    def test_development_warns_missing_openai_key(self):
        """Development should warn but not error when OPENAI_API_KEY missing."""
        with patch.dict(
            os.environ, {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true"}, clear=True
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        # Should be a warning, not an error
        openai_warnings = [w for w in result.warnings if "OPENAI_API_KEY" in w]
        openai_errors = [e for e in result.errors if "OPENAI_API_KEY" in e]
        assert len(openai_warnings) >= 1
        assert len(openai_errors) == 0

    def test_warns_for_unknown_model(self):
        """Should warn when OPENAI_MODEL is not a known model."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_ENV": "development",
                "CIVICOS_DEV_MODE": "true",
                "OPENAI_MODEL": "unknown-model-xyz",
            },
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        model_warnings = [w for w in result.warnings if "OPENAI_MODEL" in w]
        assert len(model_warnings) >= 1


class TestExternalServicesValidation:
    """Tests for external services validation."""

    def test_warns_for_placeholder_google_maps_key(self):
        """Should warn when GOOGLE_MAPS_API_KEY is a placeholder."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_ENV": "development",
                "CIVICOS_DEV_MODE": "true",
                "GOOGLE_MAPS_API_KEY": "AIza...",
            },
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        maps_warnings = [w for w in result.warnings if "GOOGLE_MAPS_API_KEY" in w]
        assert len(maps_warnings) >= 1

    def test_warns_for_placeholder_api_keys(self):
        """Should warn when any API key contains placeholder patterns."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_ENV": "development",
                "CIVICOS_DEV_MODE": "true",
                "LEGISCAN_API_KEY": "your-legiscan-api-key",
            },
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        placeholder_warnings = [w for w in result.warnings if "LEGISCAN_API_KEY" in w]
        assert len(placeholder_warnings) >= 1


class TestValidateEnvironmentBehavior:
    """Tests for validate_environment() behavior."""

    def test_raises_on_error_by_default(self):
        """validate_environment should raise RuntimeError by default on failure."""
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            config = CivicConfig()
            with pytest.raises(RuntimeError) as exc_info:
                config.validate_environment()

        assert "validation failed" in str(exc_info.value).lower()

    def test_returns_result_when_raise_disabled(self):
        """validate_environment should return ValidationResult when raise_on_error=False."""
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        assert isinstance(result, ValidationResult)
        assert not result.passed

    def test_passes_for_valid_production_config(self):
        """Should pass for fully configured production environment."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_ENV": "production",
                "CIVICOS_WEB_KEY": "secure_key_12345678901234567890123456",
                "CIVICOS_CORS_ORIGINS": "https://example.com",
                "OPENAI_API_KEY": "sk-real-key-here-12345678901234567890",
                "CIVICOS_BUNDLED_DATA_DIR": "/tmp",  # Exists for test
                "CIVICOS_USER_DATA_DIR": "/tmp",  # Exists for test
            },
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        # Should pass (may have warnings but no errors)
        assert result.passed, f"Expected pass but got errors: {result.errors}"


class TestValidateConfigFunction:
    """Tests for the validate_config convenience function."""

    def test_returns_validation_result(self):
        """validate_config should return a ValidationResult."""
        with patch.dict(
            os.environ, {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true"}, clear=True
        ):
            # Need to reimport to pick up env changes
            from civicos_services.core import config as config_module

            config_module.config = CivicConfig()
            result = validate_config()

        assert isinstance(result, ValidationResult)


class TestDataPathValidation:
    """Tests for data path validation."""

    def test_production_errors_on_missing_bundled_dir(self):
        """Production should error when bundled data directory doesn't exist."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_ENV": "production",
                "CIVICOS_WEB_KEY": "secure_key_12345678901234567890123456",
                "CIVICOS_CORS_ORIGINS": "https://example.com",
                "OPENAI_API_KEY": "sk-real-key-here-12345678901234567890",
                "CIVICOS_BUNDLED_DATA_DIR": "/nonexistent/path/bundled",
                "CIVICOS_USER_DATA_DIR": "/tmp",
            },
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        bundled_errors = [e for e in result.errors if "bundled" in e.lower() or "Bundled" in e]
        assert len(bundled_errors) >= 1

    def test_development_warns_on_missing_bundled_dir(self):
        """Development should warn (not error) when bundled data missing."""
        with patch.dict(
            os.environ,
            {
                "CIVICOS_ENV": "development",
                "CIVICOS_DEV_MODE": "true",
                "CIVICOS_BUNDLED_DATA_DIR": "/nonexistent/path/bundled",
            },
            clear=True,
        ):
            config = CivicConfig()
            result = config.validate_environment(raise_on_error=False)

        # Should be warning, not error for development
        bundled_warnings = [w for w in result.warnings if "bundled" in w.lower() or "Bundled" in w]
        bundled_errors = [e for e in result.errors if "bundled" in e.lower() or "Bundled" in e]
        assert len(bundled_warnings) >= 1
        assert len(bundled_errors) == 0
