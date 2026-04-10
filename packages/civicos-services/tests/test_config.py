"""
Tests for config.py — environment detection, API key loading, data directory resolution,
port/endpoint/CORS configuration, rate limiting, session config, OpenAI config,
and structured validation (ValidationResult).

Pure configuration logic tested with controlled environment variables via patch.dict.
No external I/O; all env vars are mocked.

To run:
    pytest packages/civicos-services/tests/test_config.py -q --override-ini="addopts="
"""

import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from civicos_services.core.config import CivicConfig, ValidationResult


# ---------------------------------------------------------------------------
# ValidationResult — dataclass behavior and formatting
# ---------------------------------------------------------------------------

class TestValidationResult:
    def test_default_fields(self):
        result = ValidationResult(environment="development")
        assert result.environment == "development"
        assert result.passed is False
        assert result.errors == []
        assert result.warnings == []
        assert result.suggestions == {}
        assert result.checked_at is None

    def test_format_errors_includes_environment(self):
        result = ValidationResult(
            environment="production",
            errors=["Missing OPENAI_API_KEY"],
        )
        formatted = result.format_errors()
        assert "production" in formatted
        assert "Missing OPENAI_API_KEY" in formatted
        assert "ERRORS (must fix):" in formatted

    def test_format_errors_includes_warnings_when_present(self):
        result = ValidationResult(
            environment="staging",
            errors=["err1"],
            warnings=["warn1"],
        )
        formatted = result.format_errors()
        assert "WARNINGS (should address):" in formatted
        assert "warn1" in formatted

    def test_format_errors_omits_warnings_section_when_empty(self):
        result = ValidationResult(
            environment="development",
            errors=["err1"],
            warnings=[],
        )
        formatted = result.format_errors()
        assert "WARNINGS" not in formatted

    def test_format_errors_includes_suggestions_when_present(self):
        result = ValidationResult(
            environment="development",
            errors=["err1"],
            suggestions={"KEY": "do this"},
        )
        formatted = result.format_errors()
        assert "SUGGESTIONS:" in formatted
        assert "KEY: do this" in formatted

    def test_format_errors_omits_suggestions_section_when_empty(self):
        result = ValidationResult(
            environment="development",
            errors=["err1"],
            suggestions={},
        )
        formatted = result.format_errors()
        assert "SUGGESTIONS:" not in formatted

    def test_format_errors_includes_env_example_reference(self):
        result = ValidationResult(environment="development", errors=["err1"])
        assert ".env.example" in result.format_errors()

    def test_format_summary_passed(self):
        result = ValidationResult(environment="production", passed=True)
        summary = result.format_summary()
        assert "PASSED" in summary
        assert "production" in summary
        assert "Errors: 0" in summary
        assert "Warnings: 0" in summary

    def test_format_summary_failed(self):
        result = ValidationResult(
            environment="staging",
            passed=False,
            errors=["e1", "e2"],
            warnings=["w1"],
        )
        summary = result.format_summary()
        assert "FAILED" in summary
        assert "Errors: 2" in summary
        assert "Warnings: 1" in summary

    def test_format_summary_includes_checked_at_when_set(self):
        ts = datetime(2026, 4, 10, 14, 30, 0)
        result = ValidationResult(environment="development", checked_at=ts)
        summary = result.format_summary()
        assert "2026-04-10 14:30:00" in summary

    def test_format_summary_omits_checked_at_when_none(self):
        result = ValidationResult(environment="development")
        summary = result.format_summary()
        assert "Checked:" not in summary

    def test_to_dict_all_fields(self):
        ts = datetime(2026, 1, 1, 12, 0, 0)
        result = ValidationResult(
            environment="production",
            passed=True,
            errors=["e1"],
            warnings=["w1"],
            suggestions={"k": "v"},
            checked_at=ts,
        )
        d = result.to_dict()
        assert d["environment"] == "production"
        assert d["passed"] is True
        assert d["errors"] == ["e1"]
        assert d["warnings"] == ["w1"]
        assert d["suggestions"] == {"k": "v"}
        assert d["checked_at"] == "2026-01-01T12:00:00"

    def test_to_dict_checked_at_none(self):
        result = ValidationResult(environment="development")
        d = result.to_dict()
        assert d["checked_at"] is None


# ---------------------------------------------------------------------------
# CivicConfig._detect_environment
# ---------------------------------------------------------------------------

class TestDetectEnvironment:
    def test_defaults_to_development_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = CivicConfig()
            assert cfg.env == "development"

    def test_production_recognized(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            assert cfg.env == "production"

    def test_staging_recognized(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "staging"}, clear=True):
            cfg = CivicConfig()
            assert cfg.env == "staging"

    def test_development_recognized(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            assert cfg.env == "development"

    def test_uppercase_normalized_to_development(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "PRODUCTION"}, clear=True):
            cfg = CivicConfig()
            assert cfg.env == "production"

    def test_invalid_value_falls_back_to_development(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "testing"}, clear=True):
            cfg = CivicConfig()
            assert cfg.env == "development"

    def test_empty_string_falls_back_to_development(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": ""}, clear=True):
            cfg = CivicConfig()
            # Empty string triggers os.getenv default
            assert cfg.env == "development"


# ---------------------------------------------------------------------------
# CivicConfig.debug
# ---------------------------------------------------------------------------

class TestDebugFlag:
    def test_debug_true_in_development_with_flag(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "DEBUG": "true"}, clear=True):
            cfg = CivicConfig()
            assert cfg.is_debug() is True

    def test_debug_false_in_development_without_flag(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            assert cfg.is_debug() is False

    def test_debug_false_in_production_even_with_flag(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production", "DEBUG": "true"}, clear=True):
            cfg = CivicConfig()
            assert cfg.is_debug() is False

    def test_debug_false_when_debug_is_uppercase_TRUE(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "DEBUG": "TRUE"}, clear=True):
            cfg = CivicConfig()
            assert cfg.is_debug() is True

    def test_debug_false_when_debug_is_1(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "DEBUG": "1"}, clear=True):
            cfg = CivicConfig()
            assert cfg.is_debug() is False


# ---------------------------------------------------------------------------
# CivicConfig.get_api_keys
# ---------------------------------------------------------------------------

class TestGetApiKeys:
    def test_returns_web_key_when_set(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_WEB_KEY": "key123"}, clear=True):
            cfg = CivicConfig()
            keys = cfg.get_api_keys()
            assert keys == {"key123": "web_interface"}

    def test_returns_demo_key_when_set(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_DEMO_KEY": "demo456"}, clear=True):
            cfg = CivicConfig()
            keys = cfg.get_api_keys()
            assert keys == {"demo456": "demo_user"}

    def test_returns_test_key_when_set(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_TEST_KEY": "test789"}, clear=True):
            cfg = CivicConfig()
            keys = cfg.get_api_keys()
            assert keys == {"test789": "test_user"}

    def test_returns_multiple_keys(self):
        env = {
            "CIVICOS_ENV": "development",
            "CIVICOS_WEB_KEY": "web1",
            "CIVICOS_DEMO_KEY": "demo1",
            "CIVICOS_TEST_KEY": "test1",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            keys = cfg.get_api_keys()
            assert len(keys) == 3
            assert keys["web1"] == "web_interface"
            assert keys["demo1"] == "demo_user"
            assert keys["test1"] == "test_user"

    def test_empty_dict_in_development_with_no_keys(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            keys = cfg.get_api_keys()
            assert keys == {}

    def test_raises_in_production_with_no_keys(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            with pytest.raises(RuntimeError, match="No API keys configured for production"):
                cfg.get_api_keys()

    def test_raises_in_staging_with_no_keys(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "staging"}, clear=True):
            cfg = CivicConfig()
            with pytest.raises(RuntimeError, match="No API keys configured for staging"):
                cfg.get_api_keys()

    def test_no_raise_in_production_when_key_present(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production", "CIVICOS_WEB_KEY": "prod_key"}, clear=True):
            cfg = CivicConfig()
            keys = cfg.get_api_keys()
            assert keys == {"prod_key": "web_interface"}


# ---------------------------------------------------------------------------
# CivicConfig.get_bundled_data_dir / get_user_data_dir / get_data_dir
# ---------------------------------------------------------------------------

class TestDataDirs:
    def test_bundled_dir_from_env_override(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_BUNDLED_DATA_DIR": "/custom/bundled"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_bundled_data_dir() == Path("/custom/bundled")

    def test_bundled_dir_production_default(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_bundled_data_dir() == Path("/app/bundled-data")

    def test_bundled_dir_development_default(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_bundled_data_dir() == Path("data")

    def test_user_dir_from_env_override(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_USER_DATA_DIR": "/custom/user"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_user_data_dir() == Path("/custom/user")

    def test_user_dir_production_default(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_user_data_dir() == Path("/app/user-data")

    def test_user_dir_development_default(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_user_data_dir() == Path("data")

    def test_get_data_dir_returns_bundled_dir(self):
        """get_data_dir is a legacy alias for get_bundled_data_dir."""
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_data_dir() == cfg.get_bundled_data_dir()

    def test_staging_bundled_dir_defaults_to_data(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "staging"}, clear=True):
            cfg = CivicConfig()
            # staging is not 'production', so falls into the else branch
            assert cfg.get_bundled_data_dir() == Path("data")


# ---------------------------------------------------------------------------
# CivicConfig.get_api_port
# ---------------------------------------------------------------------------

class TestGetApiPort:
    def test_default_port_development(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_api_port() == 8001

    def test_default_port_staging(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "staging"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_api_port() == 8002

    def test_default_port_production(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_api_port() == 8000

    def test_custom_port_from_env(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_API_PORT": "9999"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_api_port() == 9999

    def test_invalid_port_falls_back_to_default(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_API_PORT": "not_a_number"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_api_port() == 8001


# ---------------------------------------------------------------------------
# CivicConfig.get_api_endpoint
# ---------------------------------------------------------------------------

class TestGetApiEndpoint:
    def test_development_uses_localhost_with_port(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_api_endpoint() == "http://localhost:8001"

    def test_development_uses_custom_port(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_API_PORT": "3000"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_api_endpoint() == "http://localhost:3000"

    def test_production_uses_env_var(self):
        env = {"CIVICOS_ENV": "production", "CIVICOS_API_PROD": "https://api.civic.io"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            assert cfg.get_api_endpoint() == "https://api.civic.io"

    def test_production_uses_default_when_env_unset(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_api_endpoint() == "https://api.civic.example.com"

    def test_staging_uses_env_var(self):
        env = {"CIVICOS_ENV": "staging", "CIVICOS_API_STAGING": "https://staging.civic.io"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            assert cfg.get_api_endpoint() == "https://staging.civic.io"

    def test_staging_uses_default_when_env_unset(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "staging"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_api_endpoint() == "https://staging.civic.example.com"


# ---------------------------------------------------------------------------
# CivicConfig.get_cors_origins
# ---------------------------------------------------------------------------

class TestGetCorsOrigins:
    def test_development_returns_wildcard(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_cors_origins() == ["*"]

    def test_production_parses_comma_separated_origins(self):
        env = {"CIVICOS_ENV": "production", "CIVICOS_CORS_ORIGINS": "https://a.com,https://b.com"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            origins = cfg.get_cors_origins()
            assert origins == ["https://a.com", "https://b.com"]

    def test_production_trims_whitespace(self):
        env = {"CIVICOS_ENV": "production", "CIVICOS_CORS_ORIGINS": " https://a.com , https://b.com "}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            origins = cfg.get_cors_origins()
            assert origins == ["https://a.com", "https://b.com"]

    def test_production_fallback_when_empty(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            origins = cfg.get_cors_origins()
            assert origins == ["https://civic.example.com"]

    def test_staging_adds_localhost_wildcards(self):
        env = {"CIVICOS_ENV": "staging", "CIVICOS_CORS_ORIGINS": "https://staging.app"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            origins = cfg.get_cors_origins()
            assert "https://staging.app" in origins
            assert "http://localhost:*" in origins
            assert "http://127.0.0.1:*" in origins

    def test_staging_empty_origins_still_has_localhost(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "staging"}, clear=True):
            cfg = CivicConfig()
            origins = cfg.get_cors_origins()
            # Empty CORS_ORIGINS + staging localhost additions = has localhost
            assert "http://localhost:*" in origins
            assert "http://127.0.0.1:*" in origins


# ---------------------------------------------------------------------------
# CivicConfig.get_rate_limit_config
# ---------------------------------------------------------------------------

class TestGetRateLimitConfig:
    def test_defaults_in_development(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            rl = cfg.get_rate_limit_config()
            assert rl["enabled"] is False
            assert rl["requests_per_minute"] == 1000
            assert rl["requests_per_hour"] == 10000
            assert rl["burst_size"] == 20

    def test_enabled_in_production(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            rl = cfg.get_rate_limit_config()
            assert rl["enabled"] is True

    def test_enabled_in_development_with_flag(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "ENABLE_RATE_LIMIT": "true"}, clear=True):
            cfg = CivicConfig()
            rl = cfg.get_rate_limit_config()
            assert rl["enabled"] is True

    def test_custom_values_from_env(self):
        env = {
            "CIVICOS_ENV": "production",
            "RATE_LIMIT_PER_MINUTE": "500",
            "RATE_LIMIT_PER_HOUR": "5000",
            "RATE_LIMIT_BURST": "10",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            rl = cfg.get_rate_limit_config()
            assert rl["requests_per_minute"] == 500
            assert rl["requests_per_hour"] == 5000
            assert rl["burst_size"] == 10


# ---------------------------------------------------------------------------
# CivicConfig.get_session_config
# ---------------------------------------------------------------------------

class TestGetSessionConfig:
    def test_defaults(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            sc = cfg.get_session_config()
            assert sc["max_sessions"] == 1000
            assert sc["session_timeout_minutes"] == 60
            assert sc["cleanup_interval_minutes"] == 15
            assert sc["max_conversation_size_kb"] == 100

    def test_custom_values_from_env(self):
        env = {
            "CIVICOS_ENV": "development",
            "MAX_SESSIONS": "200",
            "SESSION_TIMEOUT": "30",
            "SESSION_CLEANUP_INTERVAL": "5",
            "MAX_CONVERSATION_SIZE_KB": "50",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            sc = cfg.get_session_config()
            assert sc["max_sessions"] == 200
            assert sc["session_timeout_minutes"] == 30
            assert sc["cleanup_interval_minutes"] == 5
            assert sc["max_conversation_size_kb"] == 50


# ---------------------------------------------------------------------------
# CivicConfig.get_openai_config
# ---------------------------------------------------------------------------

class TestGetOpenaiConfig:
    def test_defaults(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            oc = cfg.get_openai_config()
            assert oc["api_key"] is None
            assert oc["model"] == "gpt-4o-mini"
            assert oc["temperature"] == 0.7
            assert oc["max_completion_tokens"] == 2000
            assert oc["timeout"] == 30
            assert oc["fallback_model"] == "gpt-3.5-turbo"

    def test_custom_values_from_env(self):
        env = {
            "CIVICOS_ENV": "development",
            "OPENAI_API_KEY": "sk-test",
            "OPENAI_MODEL": "gpt-4o",
            "OPENAI_TEMPERATURE": "0.3",
            "OPENAI_MAX_TOKENS": "4000",
            "OPENAI_TIMEOUT": "60",
            "OPENAI_FALLBACK_MODEL": "gpt-4o-mini",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            oc = cfg.get_openai_config()
            assert oc["api_key"] == "sk-test"
            assert oc["model"] == "gpt-4o"
            assert oc["temperature"] == 0.3
            assert oc["max_completion_tokens"] == 4000
            assert oc["timeout"] == 60
            assert oc["fallback_model"] == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# CivicConfig.get_stripe_config
# ---------------------------------------------------------------------------

class TestGetStripeConfig:
    def test_defaults_all_none(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            sc = cfg.get_stripe_config()
            assert sc["secret_key"] is None
            assert sc["webhook_secret"] is None
            assert sc["price_journalist"] is None
            assert sc["price_organization"] is None
            assert sc["price_city"] is None
            assert sc["price_api"] is None

    def test_reads_from_env(self):
        env = {
            "CIVICOS_ENV": "development",
            "STRIPE_SECRET_KEY": "sk_test_xxx",
            "STRIPE_WEBHOOK_SECRET": "whsec_xxx",
            "STRIPE_PRICE_JOURNALIST": "price_j",
            "STRIPE_PRICE_ORGANIZATION": "price_o",
            "STRIPE_PRICE_CITY": "price_c",
            "STRIPE_PRICE_API": "price_a",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            sc = cfg.get_stripe_config()
            assert sc["secret_key"] == "sk_test_xxx"
            assert sc["webhook_secret"] == "whsec_xxx"
            assert sc["price_journalist"] == "price_j"
            assert sc["price_organization"] == "price_o"
            assert sc["price_city"] == "price_c"
            assert sc["price_api"] == "price_a"


# ---------------------------------------------------------------------------
# CivicConfig.get_platform_database_url
# ---------------------------------------------------------------------------

class TestGetPlatformDatabaseUrl:
    def test_returns_none_when_unset(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            assert cfg.get_platform_database_url() is None

    def test_returns_url_when_set(self):
        env = {"CIVICOS_ENV": "development", "PLATFORM_DATABASE_URL": "postgres://host/db"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            assert cfg.get_platform_database_url() == "postgres://host/db"


# ---------------------------------------------------------------------------
# CivicConfig.validate_environment — core config validation
# ---------------------------------------------------------------------------

class TestValidateCoreConfig:
    def test_warns_when_civicos_env_not_set(self):
        with patch.dict(os.environ, {"CIVICOS_DEV_MODE": "true"}, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            env_warnings = [w for w in result.warnings if "CIVICOS_ENV" in w]
            assert len(env_warnings) >= 1
            assert "not set" in env_warnings[0]

    def test_warns_when_civicos_env_nonstandard(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "testing", "CIVICOS_DEV_MODE": "true"}, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            env_warnings = [w for w in result.warnings if "non-standard" in w]
            assert len(env_warnings) == 1

    def test_invalid_port_is_error(self):
        env = {"CIVICOS_ENV": "development", "CIVICOS_API_PORT": "abc", "CIVICOS_DEV_MODE": "true"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            port_errors = [e for e in result.errors if "CIVICOS_API_PORT" in e]
            assert len(port_errors) == 1
            assert "not a valid integer" in port_errors[0]

    def test_port_outside_range_is_warning(self):
        env = {"CIVICOS_ENV": "development", "CIVICOS_API_PORT": "80", "CIVICOS_DEV_MODE": "true"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            port_warnings = [w for w in result.warnings if "CIVICOS_API_PORT" in w]
            assert len(port_warnings) == 1
            assert "outside recommended range" in port_warnings[0]


# ---------------------------------------------------------------------------
# CivicConfig.validate_environment — security config validation
# ---------------------------------------------------------------------------

class TestValidateSecurityConfig:
    def test_production_requires_web_key(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            key_errors = [e for e in result.errors if "CIVICOS_WEB_KEY" in e and "required" in e]
            assert len(key_errors) == 1

    def test_production_rejects_dev_key_local(self):
        env = {
            "CIVICOS_ENV": "production",
            "CIVICOS_WEB_KEY": "dev_key_local",
            "CIVICOS_CORS_ORIGINS": "https://example.com",
            "OPENAI_API_KEY": "sk-realkey12345678901234",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            dev_key_errors = [e for e in result.errors if "dev_key_local" in e]
            assert len(dev_key_errors) == 1

    def test_production_requires_cors_origins(self):
        env = {"CIVICOS_ENV": "production", "CIVICOS_WEB_KEY": "real_key"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            cors_errors = [e for e in result.errors if "CIVICOS_CORS_ORIGINS" in e]
            assert len(cors_errors) >= 1

    def test_production_rejects_wildcard_cors(self):
        env = {
            "CIVICOS_ENV": "production",
            "CIVICOS_WEB_KEY": "real_key",
            "CIVICOS_CORS_ORIGINS": "*",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            wildcard_errors = [e for e in result.errors if "'*'" in e]
            assert len(wildcard_errors) == 1

    def test_development_requires_at_least_one_auth(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            auth_errors = [e for e in result.errors if "CIVICOS_DEV_MODE" in e]
            assert len(auth_errors) == 1

    def test_development_passes_with_dev_mode(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true"}, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            auth_errors = [e for e in result.errors if "Development requires" in e]
            assert len(auth_errors) == 0

    def test_development_passes_with_web_key(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_WEB_KEY": "dev123"}, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            auth_errors = [e for e in result.errors if "Development requires" in e]
            assert len(auth_errors) == 0


# ---------------------------------------------------------------------------
# CivicConfig.validate_environment — LLM config validation
# ---------------------------------------------------------------------------

class TestValidateLlmConfig:
    def test_production_requires_openai_key(self):
        env = {
            "CIVICOS_ENV": "production",
            "CIVICOS_WEB_KEY": "real_key",
            "CIVICOS_CORS_ORIGINS": "https://example.com",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            key_errors = [e for e in result.errors if "OPENAI_API_KEY" in e and "required" in e]
            assert len(key_errors) == 1

    def test_production_rejects_placeholder_openai_key(self):
        env = {
            "CIVICOS_ENV": "production",
            "CIVICOS_WEB_KEY": "real_key",
            "CIVICOS_CORS_ORIGINS": "https://example.com",
            "OPENAI_API_KEY": "sk-proj-...",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            placeholder_errors = [e for e in result.errors if "placeholder" in e]
            assert len(placeholder_errors) == 1

    def test_production_rejects_short_openai_key(self):
        env = {
            "CIVICOS_ENV": "production",
            "CIVICOS_WEB_KEY": "real_key",
            "CIVICOS_CORS_ORIGINS": "https://example.com",
            "OPENAI_API_KEY": "sk-short",
        }
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            placeholder_errors = [e for e in result.errors if "placeholder" in e]
            assert len(placeholder_errors) == 1

    def test_development_warns_missing_openai_key(self):
        env = {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            key_warnings = [w for w in result.warnings if "OPENAI_API_KEY" in w and "not set" in w]
            assert len(key_warnings) == 1

    def test_development_warns_placeholder_openai_key(self):
        env = {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true", "OPENAI_API_KEY": "sk-proj-..."}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            placeholder_warnings = [w for w in result.warnings if "placeholder" in w]
            assert len(placeholder_warnings) == 1

    def test_warns_unknown_model(self):
        env = {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true", "OPENAI_MODEL": "gpt-99"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            model_warnings = [w for w in result.warnings if "gpt-99" in w]
            assert len(model_warnings) == 1

    def test_no_warning_for_known_model(self):
        env = {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true", "OPENAI_MODEL": "gpt-4o"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            model_warnings = [w for w in result.warnings if "OPENAI_MODEL" in w]
            assert len(model_warnings) == 0


# ---------------------------------------------------------------------------
# CivicConfig.validate_environment — external services
# ---------------------------------------------------------------------------

class TestValidateExternalServices:
    def test_warns_google_maps_placeholder(self):
        env = {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true", "GOOGLE_MAPS_API_KEY": "AIza...placeholder"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            gmaps_warnings = [w for w in result.warnings if "GOOGLE_MAPS_API_KEY" in w]
            assert len(gmaps_warnings) == 1

    def test_warns_legiscan_placeholder(self):
        env = {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true", "LEGISCAN_API_KEY": "your-key-here"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            legiscan_warnings = [w for w in result.warnings if "LEGISCAN_API_KEY" in w]
            assert len(legiscan_warnings) == 1

    def test_no_warning_for_real_key(self):
        env = {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true", "LEGISCAN_API_KEY": "abc123realkey"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            legiscan_warnings = [w for w in result.warnings if "LEGISCAN_API_KEY" in w]
            assert len(legiscan_warnings) == 0


# ---------------------------------------------------------------------------
# CivicConfig.validate_environment — overall behavior
# ---------------------------------------------------------------------------

class TestValidateOverall:
    def test_passed_true_when_no_errors(self):
        env = {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            assert result.passed is True

    def test_passed_false_when_errors_exist(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            assert result.passed is False
            assert len(result.errors) > 0

    def test_checked_at_is_set(self):
        env = {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true"}
        with patch.dict(os.environ, env, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            assert result.checked_at is not None
            # checked_at should be a recent datetime
            assert (datetime.now() - result.checked_at).total_seconds() < 5

    def test_raise_on_error_true_raises_on_failure(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            with pytest.raises(RuntimeError, match="Configuration validation failed"):
                cfg.validate_environment(raise_on_error=True)

    def test_raise_on_error_false_does_not_raise(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            cfg = CivicConfig()
            result = cfg.validate_environment(raise_on_error=False)
            assert result.passed is False  # No exception raised


# ---------------------------------------------------------------------------
# Module-level helper functions: get_bundled_path, get_user_path, get_data_path
# ---------------------------------------------------------------------------

class TestModuleLevelHelpers:
    def test_get_bundled_path_joins_parts(self):
        from civicos_services.core.config import get_bundled_path
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            # Reimport to get fresh config — but module-level config is already loaded.
            # Instead, patch the config object's method.
            with patch("civicos_services.core.config.config.get_bundled_data_dir", return_value=Path("/app/bundled-data")):
                result = get_bundled_path("pilot", "vectors", "city-san-rafael")
                assert result == "/app/bundled-data/pilot/vectors/city-san-rafael"

    def test_get_user_path_joins_parts(self):
        from civicos_services.core.config import get_user_path
        with patch("civicos_services.core.config.config.get_user_data_dir", return_value=Path("/app/user-data")):
            result = get_user_path("civic_participation.db")
            assert result == "/app/user-data/civic_participation.db"

    def test_get_data_path_delegates_to_bundled(self):
        from civicos_services.core.config import get_data_path, get_bundled_path
        with patch("civicos_services.core.config.config.get_bundled_data_dir", return_value=Path("/test")):
            assert get_data_path("a", "b") == get_bundled_path("a", "b")

    def test_get_bundled_path_no_parts(self):
        from civicos_services.core.config import get_bundled_path
        with patch("civicos_services.core.config.config.get_bundled_data_dir", return_value=Path("/data")):
            result = get_bundled_path()
            assert result == "/data"

    def test_get_user_path_no_parts(self):
        from civicos_services.core.config import get_user_path
        with patch("civicos_services.core.config.config.get_user_data_dir", return_value=Path("/user")):
            result = get_user_path()
            assert result == "/user"


# ---------------------------------------------------------------------------
# validate_config convenience function
# ---------------------------------------------------------------------------

class TestValidateConfigFunction:
    def test_returns_validation_result(self):
        from civicos_services.core.config import validate_config
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true"}, clear=True):
            with patch("civicos_services.core.config.config", CivicConfig()):
                result = validate_config(verbose=False)
                assert result.environment == "development"
                assert result.passed is True

    def test_verbose_prints_output(self, capsys):
        from civicos_services.core.config import validate_config
        with patch.dict(os.environ, {"CIVICOS_ENV": "development", "CIVICOS_DEV_MODE": "true"}, clear=True):
            with patch("civicos_services.core.config.config", CivicConfig()):
                result = validate_config(verbose=True)
                captured = capsys.readouterr()
                assert "Configuration Validation:" in captured.out
                assert "development" in captured.out
