"""
Tests for logging_config.py — correlation IDs, JSON/human-readable formatting,
environment-aware configuration, and convenience logging functions.

Mocks: os.environ (for env-based config), sys.stdout.isatty (for color detection),
       filesystem (via tmp_path for log dirs).
Real: all formatters, correlation ID context vars, log level parsing, all convenience functions.

To run:
    pytest packages/civicos-services/tests/test_logging_config.py -q --override-ini="addopts="
"""

import json
import logging
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

from civicos_services.core.logging_config import (
    get_correlation_id,
    set_correlation_id,
    clear_correlation_id,
    with_correlation_id,
    JSONFormatter,
    HumanReadableFormatter,
    get_log_level,
    is_development,
    configure_logging,
    get_logger,
    log_request_start,
    log_request_complete,
    log_error,
    log_audit,
    ensure_configured,
    _correlation_id,
)
import civicos_services.core.logging_config as lc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_correlation_id():
    """Ensure correlation ID is cleared between tests."""
    _correlation_id.set(None)
    yield
    _correlation_id.set(None)


@pytest.fixture(autouse=True)
def _reset_configured_flag():
    """Reset the module-level _configured flag between tests."""
    original = lc._configured
    lc._configured = False
    yield
    lc._configured = original


@pytest.fixture
def log_record():
    """Create a basic log record for formatter tests."""
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=42,
        msg="test_message",
        args=(),
        exc_info=None,
    )
    return record


@pytest.fixture
def log_record_with_extra():
    """Create a log record with extra fields."""
    record = logging.LogRecord(
        name="test_logger",
        level=logging.WARNING,
        pathname="test.py",
        lineno=10,
        msg="something happened",
        args=(),
        exc_info=None,
    )
    record.user_id = "u123"
    record.path = "/api/test"
    return record


# ---------------------------------------------------------------------------
# Correlation ID management
# ---------------------------------------------------------------------------


class TestCorrelationId:
    def test_default_is_none(self):
        assert get_correlation_id() is None

    def test_set_generates_8_char_id(self):
        cid = set_correlation_id()
        assert len(cid) == 8
        assert get_correlation_id() == cid

    def test_set_with_custom_value(self):
        cid = set_correlation_id("custom123")
        assert cid == "custom123"
        assert get_correlation_id() == "custom123"

    def test_clear_resets_to_none(self):
        set_correlation_id("abc")
        clear_correlation_id()
        assert get_correlation_id() is None

    def test_set_returns_generated_id(self):
        cid = set_correlation_id()
        # Must be a valid UUID prefix (hex chars + hyphens)
        assert all(c in "0123456789abcdef-" for c in cid)


class TestWithCorrelationId:
    def test_sets_id_within_context(self):
        with with_correlation_id() as cid:
            assert get_correlation_id() == cid
            assert len(cid) == 8

    def test_restores_none_after_exit(self):
        with with_correlation_id():
            pass
        assert get_correlation_id() is None

    def test_restores_previous_id_after_exit(self):
        set_correlation_id("outer")
        with with_correlation_id("inner"):
            assert get_correlation_id() == "inner"
        assert get_correlation_id() == "outer"

    def test_uses_provided_id(self):
        with with_correlation_id("my-req-id") as cid:
            assert cid == "my-req-id"
            assert get_correlation_id() == "my-req-id"

    def test_generates_8_char_id_when_none_provided(self):
        with with_correlation_id() as cid:
            assert len(cid) == 8


# ---------------------------------------------------------------------------
# JSONFormatter
# ---------------------------------------------------------------------------


class TestJSONFormatter:
    def test_output_is_valid_json(self, log_record):
        formatter = JSONFormatter()
        output = formatter.format(log_record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test_logger"
        assert parsed["message"] == "test_message"

    def test_timestamp_is_utc_iso_format(self, log_record):
        formatter = JSONFormatter()
        output = formatter.format(log_record)
        parsed = json.loads(output)
        # UTC timestamps end with +00:00
        assert "+00:00" in parsed["timestamp"]

    def test_includes_correlation_id_when_set(self, log_record):
        set_correlation_id("req-abc")
        formatter = JSONFormatter()
        parsed = json.loads(formatter.format(log_record))
        assert parsed["correlation_id"] == "req-abc"

    def test_excludes_correlation_id_when_not_set(self, log_record):
        formatter = JSONFormatter()
        parsed = json.loads(formatter.format(log_record))
        assert "correlation_id" not in parsed

    def test_includes_location_when_enabled(self):
        record = logging.LogRecord(
            name="test_logger", level=logging.INFO, pathname="test.py",
            lineno=42, msg="test_message", args=(), exc_info=None,
            func="my_function",
        )
        formatter = JSONFormatter(include_location=True)
        parsed = json.loads(formatter.format(record))
        assert parsed["location"]["file"] == "test.py"
        assert parsed["location"]["line"] == 42
        assert parsed["location"]["function"] == "my_function"

    def test_excludes_location_when_disabled(self, log_record):
        formatter = JSONFormatter(include_location=False)
        parsed = json.loads(formatter.format(log_record))
        assert "location" not in parsed

    def test_extracts_extra_fields(self, log_record_with_extra):
        formatter = JSONFormatter()
        parsed = json.loads(formatter.format(log_record_with_extra))
        assert parsed["extra"]["user_id"] == "u123"
        assert parsed["extra"]["path"] == "/api/test"

    def test_no_extra_key_when_no_extra_fields(self, log_record):
        formatter = JSONFormatter()
        parsed = json.loads(formatter.format(log_record))
        assert "extra" not in parsed

    def test_non_serializable_extra_converted_to_string(self):
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg="msg", args=(), exc_info=None,
        )
        record.unserializable = object()
        formatter = JSONFormatter()
        parsed = json.loads(formatter.format(record))
        # The object should be converted to its str representation
        assert "object" in parsed["extra"]["unserializable"]

    def test_exception_info_included(self):
        try:
            raise ValueError("bad value")
        except ValueError:
            import sys
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1, msg="error occurred", args=(), exc_info=exc_info,
        )
        formatter = JSONFormatter()
        parsed = json.loads(formatter.format(record))
        assert parsed["exception"]["type"] == "ValueError"
        assert parsed["exception"]["message"] == "bad value"
        assert "traceback" in parsed["exception"]
        assert "ValueError" in parsed["exception"]["traceback"]

    def test_level_matches_record_level(self):
        for level_name, level_no in [("DEBUG", logging.DEBUG), ("ERROR", logging.ERROR), ("CRITICAL", logging.CRITICAL)]:
            record = logging.LogRecord(
                name="test", level=level_no, pathname="test.py",
                lineno=1, msg="msg", args=(), exc_info=None,
            )
            formatter = JSONFormatter()
            parsed = json.loads(formatter.format(record))
            assert parsed["level"] == level_name


# ---------------------------------------------------------------------------
# HumanReadableFormatter
# ---------------------------------------------------------------------------


class TestHumanReadableFormatter:
    def test_contains_timestamp_level_name_message(self, log_record):
        formatter = HumanReadableFormatter(use_colors=False)
        output = formatter.format(log_record)
        assert "[INFO]" in output
        assert "test_logger" in output
        assert "test_message" in output
        # Timestamp pattern: YYYY-MM-DD HH:MM:SS
        assert len(output.split(" ")[0]) == 10  # date part

    def test_includes_correlation_id_in_brackets(self, log_record):
        set_correlation_id("xyz789")
        formatter = HumanReadableFormatter(use_colors=False)
        output = formatter.format(log_record)
        assert "[xyz789]" in output

    def test_excludes_correlation_id_when_not_set(self, log_record):
        formatter = HumanReadableFormatter(use_colors=False)
        output = formatter.format(log_record)
        # No bracket-enclosed ID
        assert "[INFO]" in output
        # Check no other brackets besides level
        parts_with_brackets = [p for p in output.split() if p.startswith("[") and p != "[INFO]"]
        assert len(parts_with_brackets) == 0

    def test_extra_fields_appear_as_key_value(self, log_record_with_extra):
        formatter = HumanReadableFormatter(use_colors=False)
        output = formatter.format(log_record_with_extra)
        assert "user_id=u123" in output
        assert "path=/api/test" in output

    def test_no_ansi_codes_when_colors_disabled(self, log_record):
        formatter = HumanReadableFormatter(use_colors=False)
        output = formatter.format(log_record)
        assert "\033[" not in output

    def test_exception_info_appended(self):
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test", level=logging.ERROR, pathname="test.py",
            lineno=1, msg="failure", args=(), exc_info=exc_info,
        )
        formatter = HumanReadableFormatter(use_colors=False)
        output = formatter.format(record)
        assert "RuntimeError: boom" in output

    def test_colors_disabled_when_not_tty(self):
        with patch.object(sys.stdout, "isatty", return_value=False):
            formatter = HumanReadableFormatter(use_colors=True)
        assert formatter.use_colors is False

    def test_warning_level_formatted(self):
        record = logging.LogRecord(
            name="test", level=logging.WARNING, pathname="test.py",
            lineno=1, msg="warn msg", args=(), exc_info=None,
        )
        formatter = HumanReadableFormatter(use_colors=False)
        output = formatter.format(record)
        assert "[WARNING]" in output
        assert "warn msg" in output


# ---------------------------------------------------------------------------
# get_log_level
# ---------------------------------------------------------------------------


class TestGetLogLevel:
    def test_defaults_to_info(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_log_level() == logging.INFO

    def test_reads_debug_from_env(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}):
            assert get_log_level() == logging.DEBUG

    def test_reads_warning_from_env(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}):
            assert get_log_level() == logging.WARNING

    def test_reads_error_from_env(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "ERROR"}):
            assert get_log_level() == logging.ERROR

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "debug"}):
            assert get_log_level() == logging.DEBUG

    def test_invalid_level_defaults_to_info(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "NONSENSE"}):
            assert get_log_level() == logging.INFO


# ---------------------------------------------------------------------------
# is_development
# ---------------------------------------------------------------------------


class TestIsDevelopment:
    def test_true_for_development(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            assert is_development() is True

    def test_true_for_dev(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "dev"}, clear=True):
            assert is_development() is True

    def test_true_for_local(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "local"}, clear=True):
            assert is_development() is True

    def test_false_for_production(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            assert is_development() is False

    def test_false_for_staging(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "staging"}, clear=True):
            assert is_development() is False

    def test_defaults_to_development_when_no_env(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_development() is True

    def test_falls_back_to_env_var(self):
        with patch.dict(os.environ, {"ENV": "production"}, clear=True):
            assert is_development() is False

    def test_civicos_env_takes_precedence_over_env(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production", "ENV": "development"}, clear=True):
            assert is_development() is False

    def test_case_insensitive(self):
        with patch.dict(os.environ, {"CIVICOS_ENV": "DEVELOPMENT"}, clear=True):
            assert is_development() is True


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


class TestConfigureLogging:
    def test_creates_log_directory(self, tmp_path):
        log_dir = tmp_path / "test_logs"
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            configure_logging(log_dir=str(log_dir))
        assert log_dir.exists()

    def test_creates_json_log_file(self, tmp_path):
        log_dir = tmp_path / "logs"
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            configure_logging(log_dir=str(log_dir), json_file="app.json.log")
        assert (log_dir / "app.json.log").exists()

    def test_creates_text_log_file(self, tmp_path):
        log_dir = tmp_path / "logs"
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            configure_logging(log_dir=str(log_dir), text_file="app.log")
        assert (log_dir / "app.log").exists()

    def test_sets_log_level_from_parameter(self, tmp_path):
        configure_logging(log_dir=str(tmp_path), level=logging.DEBUG)
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_production_has_two_handlers(self, tmp_path):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            configure_logging(log_dir=str(tmp_path))
        root = logging.getLogger()
        # 2 file handlers, no console in production
        assert len(root.handlers) == 2

    def test_development_has_three_handlers(self, tmp_path):
        with patch.dict(os.environ, {"CIVICOS_ENV": "development"}, clear=True):
            configure_logging(log_dir=str(tmp_path))
        root = logging.getLogger()
        # 2 file handlers + 1 console handler
        assert len(root.handlers) == 3

    def test_suppresses_noisy_loggers(self, tmp_path):
        configure_logging(log_dir=str(tmp_path))
        assert logging.getLogger("urllib3").level == logging.WARNING
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("chromadb").level == logging.WARNING
        assert logging.getLogger("sentence_transformers").level == logging.WARNING

    def test_clears_existing_handlers(self, tmp_path):
        root = logging.getLogger()
        root.addHandler(logging.StreamHandler())
        root.addHandler(logging.StreamHandler())
        initial_count = len(root.handlers)
        assert initial_count >= 2
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            configure_logging(log_dir=str(tmp_path))
        # Should have exactly 2 (json + text), not 2 + initial_count
        assert len(root.handlers) == 2

    def test_json_handler_uses_json_formatter(self, tmp_path):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            configure_logging(log_dir=str(tmp_path))
        root = logging.getLogger()
        json_handler = root.handlers[0]
        assert isinstance(json_handler.formatter, JSONFormatter)

    def test_text_handler_uses_human_formatter(self, tmp_path):
        with patch.dict(os.environ, {"CIVICOS_ENV": "production"}, clear=True):
            configure_logging(log_dir=str(tmp_path))
        root = logging.getLogger()
        text_handler = root.handlers[1]
        assert isinstance(text_handler.formatter, HumanReadableFormatter)


# ---------------------------------------------------------------------------
# get_logger
# ---------------------------------------------------------------------------


class TestGetLogger:
    def test_returns_logger_with_given_name(self):
        logger = get_logger("my.module")
        assert logger.name == "my.module"

    def test_same_name_returns_same_logger(self):
        logger1 = get_logger("shared.name")
        logger2 = get_logger("shared.name")
        assert logger1 is logger2

    def test_different_names_return_different_loggers(self):
        logger1 = get_logger("module.a")
        logger2 = get_logger("module.b")
        assert logger1 is not logger2


# ---------------------------------------------------------------------------
# Convenience logging functions
# ---------------------------------------------------------------------------


class TestLogRequestStart:
    def test_logs_at_info_level_with_fields(self):
        logger = MagicMock(spec=logging.Logger)
        log_request_start(logger, "GET", "/api/meetings", client_ip="1.2.3.4", user_id="u1")
        logger.info.assert_called_once()
        call_args = logger.info.call_args
        assert call_args[0][0] == "request_start"
        extra = call_args[1]["extra"]
        assert extra["method"] == "GET"
        assert extra["path"] == "/api/meetings"
        assert extra["client_ip"] == "1.2.3.4"
        assert extra["user_id"] == "u1"

    def test_includes_extra_kwargs(self):
        logger = MagicMock(spec=logging.Logger)
        log_request_start(logger, "POST", "/api/search", query="housing")
        extra = logger.info.call_args[1]["extra"]
        assert extra["query"] == "housing"

    def test_none_defaults_for_optional_fields(self):
        logger = MagicMock(spec=logging.Logger)
        log_request_start(logger, "GET", "/api/test")
        extra = logger.info.call_args[1]["extra"]
        assert extra["client_ip"] is None
        assert extra["user_id"] is None


class TestLogRequestComplete:
    def test_info_level_for_2xx(self):
        logger = MagicMock(spec=logging.Logger)
        log_request_complete(logger, "GET", "/api/test", status_code=200, duration_ms=45.678)
        call_args = logger.log.call_args
        assert call_args[0][0] == logging.INFO
        assert call_args[0][1] == "request_complete"
        extra = call_args[1]["extra"]
        assert extra["status_code"] == 200
        assert extra["duration_ms"] == 45.68

    def test_warning_level_for_4xx(self):
        logger = MagicMock(spec=logging.Logger)
        log_request_complete(logger, "GET", "/api/test", status_code=404, duration_ms=10.0)
        assert logger.log.call_args[0][0] == logging.WARNING

    def test_error_level_for_5xx(self):
        logger = MagicMock(spec=logging.Logger)
        log_request_complete(logger, "GET", "/api/test", status_code=500, duration_ms=10.0)
        assert logger.log.call_args[0][0] == logging.ERROR

    def test_warning_level_for_boundary_400(self):
        logger = MagicMock(spec=logging.Logger)
        log_request_complete(logger, "GET", "/", status_code=400, duration_ms=5.0)
        assert logger.log.call_args[0][0] == logging.WARNING

    def test_info_level_for_boundary_399(self):
        logger = MagicMock(spec=logging.Logger)
        log_request_complete(logger, "GET", "/", status_code=399, duration_ms=5.0)
        assert logger.log.call_args[0][0] == logging.INFO

    def test_error_level_for_boundary_500(self):
        logger = MagicMock(spec=logging.Logger)
        log_request_complete(logger, "GET", "/", status_code=500, duration_ms=5.0)
        assert logger.log.call_args[0][0] == logging.ERROR

    def test_duration_rounded_to_2_decimals(self):
        logger = MagicMock(spec=logging.Logger)
        log_request_complete(logger, "GET", "/", status_code=200, duration_ms=123.456789)
        extra = logger.log.call_args[1]["extra"]
        assert extra["duration_ms"] == 123.46

    def test_includes_extra_kwargs(self):
        logger = MagicMock(spec=logging.Logger)
        log_request_complete(logger, "GET", "/", status_code=200, duration_ms=1.0, cache_hit=True)
        extra = logger.log.call_args[1]["extra"]
        assert extra["cache_hit"] is True


class TestLogError:
    def test_logs_error_with_exception_context(self):
        logger = MagicMock(spec=logging.Logger)
        err = ValueError("bad input")
        log_error(logger, "processing failed", error=err, request_id="r1")
        call_args = logger.error.call_args
        assert call_args[0][0] == "processing failed"
        extra = call_args[1]["extra"]
        assert extra["error_type"] == "ValueError"
        assert extra["error_message"] == "bad input"
        assert extra["request_id"] == "r1"
        assert "stack_trace" in extra
        assert call_args[1]["exc_info"] is True

    def test_logs_error_without_exception(self):
        logger = MagicMock(spec=logging.Logger)
        log_error(logger, "something went wrong", context_key="val")
        call_args = logger.error.call_args
        assert call_args[0][0] == "something went wrong"
        extra = call_args[1]["extra"]
        assert extra["context_key"] == "val"
        assert "error_type" not in extra
        assert call_args[1]["exc_info"] is False


class TestLogAudit:
    def test_logs_audit_with_prefix_and_fields(self):
        logger = MagicMock(spec=logging.Logger)
        log_audit(logger, "login", user_id="u42", resource="/admin", ip="10.0.0.1")
        call_args = logger.info.call_args
        assert call_args[0][0] == "audit:login"
        extra = call_args[1]["extra"]
        assert extra["audit_action"] == "login"
        assert extra["user_id"] == "u42"
        assert extra["resource"] == "/admin"
        assert extra["ip"] == "10.0.0.1"

    def test_none_defaults_for_optional_fields(self):
        logger = MagicMock(spec=logging.Logger)
        log_audit(logger, "data_export")
        extra = logger.info.call_args[1]["extra"]
        assert extra["user_id"] is None
        assert extra["resource"] is None


# ---------------------------------------------------------------------------
# ensure_configured
# ---------------------------------------------------------------------------


class TestEnsureConfigured:
    def test_calls_configure_on_first_invocation(self, tmp_path):
        with patch("civicos_services.core.logging_config.configure_logging") as mock_conf:
            ensure_configured()
            mock_conf.assert_called_once()
            assert lc._configured is True

    def test_skips_on_second_invocation(self, tmp_path):
        with patch("civicos_services.core.logging_config.configure_logging") as mock_conf:
            ensure_configured()
            ensure_configured()
            mock_conf.assert_called_once()
            assert lc._configured is True

    def test_sets_configured_flag(self):
        with patch("civicos_services.core.logging_config.configure_logging"):
            ensure_configured()
            assert lc._configured is True


# ---------------------------------------------------------------------------
# Integration: formatter + correlation ID together
# ---------------------------------------------------------------------------


class TestFormatterCorrelationIntegration:
    def test_json_formatter_captures_context_manager_id(self, log_record):
        formatter = JSONFormatter()
        with with_correlation_id("int-test"):
            output = formatter.format(log_record)
        parsed = json.loads(output)
        assert parsed["correlation_id"] == "int-test"

    def test_json_formatter_no_id_outside_context(self, log_record):
        formatter = JSONFormatter()
        with with_correlation_id("temp"):
            pass
        parsed = json.loads(formatter.format(log_record))
        assert "correlation_id" not in parsed

    def test_human_formatter_captures_context_manager_id(self, log_record):
        formatter = HumanReadableFormatter(use_colors=False)
        with with_correlation_id("hr-test"):
            output = formatter.format(log_record)
        assert "[hr-test]" in output
