"""
Centralized logging configuration for Civic platform.

Provides structured JSON logging with:
- Correlation IDs for request tracing
- Consistent log format across all modules
- Environment-aware configuration (dev vs prod)
- File and console handlers

Usage:
    from logging_config import get_logger, with_correlation_id

    logger = get_logger(__name__)
    logger.info("message", extra={"key": "value"})

    # In request handlers:
    with with_correlation_id() as correlation_id:
        logger.info("request_start", extra={"path": "/api/meetings"})

Session 246: Initial structured logging implementation
"""

import json
import logging
import os
import sys
import threading
import traceback
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Context variable for correlation ID (thread-safe)
_correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID for this request/context."""
    return _correlation_id.get()


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set or generate a new correlation ID. Returns the ID."""
    cid = correlation_id or str(uuid.uuid4())[:8]
    _correlation_id.set(cid)
    return cid


def clear_correlation_id() -> None:
    """Clear the correlation ID after request completes."""
    _correlation_id.set(None)


class with_correlation_id:
    """Context manager for correlation ID scoping."""

    def __init__(self, correlation_id: Optional[str] = None):
        self.correlation_id = correlation_id
        self._token = None

    def __enter__(self) -> str:
        cid = self.correlation_id or str(uuid.uuid4())[:8]
        self._token = _correlation_id.set(cid)
        return cid

    def __exit__(self, *args):
        if self._token is not None:
            _correlation_id.reset(self._token)


class JSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Output format:
    {
        "timestamp": "2025-01-15T10:30:00.000Z",
        "level": "INFO",
        "logger": "civic_api",
        "message": "request_start",
        "correlation_id": "abc12345",
        "extra": {"path": "/api/meetings", "method": "GET"}
    }
    """

    # Fields that are part of the standard log record (not extra data)
    RESERVED_ATTRS = {
        'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
        'module', 'lineno', 'funcName', 'created', 'thread', 'threadName',
        'process', 'processName', 'exc_info', 'exc_text', 'stack_info',
        'message', 'msecs', 'relativeCreated', 'taskName'
    }

    def __init__(self, include_location: bool = False):
        """
        Initialize formatter.

        Args:
            include_location: Include file/line info in logs (useful for debugging)
        """
        super().__init__()
        self.include_location = include_location

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        # Base log structure
        log_dict: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if available
        correlation_id = get_correlation_id()
        if correlation_id:
            log_dict["correlation_id"] = correlation_id

        # Add location info if enabled
        if self.include_location:
            log_dict["location"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName
            }

        # Extract extra fields from record
        extra = {}
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and not key.startswith('_'):
                # Handle non-serializable objects
                try:
                    json.dumps(value)
                    extra[key] = value
                except (TypeError, ValueError):
                    extra[key] = str(value)

        if extra:
            log_dict["extra"] = extra

        # Add exception info if present
        if record.exc_info:
            log_dict["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info[1] else None
            }

        return json.dumps(log_dict, default=str)


class HumanReadableFormatter(logging.Formatter):
    """
    Human-readable formatter for development console output.

    Output format:
    2025-01-15 10:30:00 [INFO] civic_api [abc12345] request_start path=/api/meetings
    """

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'
    }

    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors and sys.stdout.isatty()

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record for human readability."""
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        level = record.levelname

        # Color the level if enabled
        if self.use_colors:
            color = self.COLORS.get(level, '')
            reset = self.COLORS['RESET']
            level_str = f"{color}[{level}]{reset}"
        else:
            level_str = f"[{level}]"

        # Build message parts
        parts = [timestamp, level_str, record.name]

        # Add correlation ID if available
        correlation_id = get_correlation_id()
        if correlation_id:
            parts.append(f"[{correlation_id}]")

        parts.append(record.getMessage())

        # Add extra fields as key=value
        extra_parts = []
        for key, value in record.__dict__.items():
            if key not in JSONFormatter.RESERVED_ATTRS and not key.startswith('_'):
                extra_parts.append(f"{key}={value}")

        if extra_parts:
            parts.append(' '.join(extra_parts))

        message = ' '.join(parts)

        # Add exception info if present
        if record.exc_info:
            message += '\n' + self.formatException(record.exc_info)

        return message


def get_log_level() -> int:
    """Get log level from environment, defaulting to INFO."""
    level_name = os.environ.get('LOG_LEVEL', 'INFO').upper()
    return getattr(logging, level_name, logging.INFO)


def is_development() -> bool:
    """Check if running in development environment."""
    env = os.environ.get('CIVIC_ENV', os.environ.get('ENV', 'development'))
    return env.lower() in ('development', 'dev', 'local')


def configure_logging(
    log_dir: str = 'logs',
    json_file: str = 'civic.json.log',
    text_file: str = 'civic.log',
    level: Optional[int] = None
) -> None:
    """
    Configure logging for the entire application.

    This should be called once at application startup.

    Args:
        log_dir: Directory for log files
        json_file: Filename for JSON logs
        text_file: Filename for text logs
        level: Log level (defaults to LOG_LEVEL env var or INFO)
    """
    log_level = level or get_log_level()
    logs_path = Path(log_dir)
    logs_path.mkdir(exist_ok=True)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # JSON file handler (for machine parsing, log aggregation)
    json_handler = logging.FileHandler(logs_path / json_file)
    json_handler.setLevel(log_level)
    json_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(json_handler)

    # Text file handler (for human reading)
    text_handler = logging.FileHandler(logs_path / text_file)
    text_handler.setLevel(log_level)
    text_handler.setFormatter(HumanReadableFormatter(use_colors=False))
    root_logger.addHandler(text_handler)

    # Console handler (development only, human-readable with colors)
    if is_development():
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(HumanReadableFormatter(use_colors=True))
        root_logger.addHandler(console_handler)

    # Suppress noisy third-party loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('chromadb').setLevel(logging.WARNING)
    logging.getLogger('sentence_transformers').setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger with the given name.

    This is the primary way to get loggers in application code.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Convenience functions for common logging patterns
def log_request_start(
    logger: logging.Logger,
    method: str,
    path: str,
    client_ip: Optional[str] = None,
    user_id: Optional[str] = None,
    **extra
) -> None:
    """Log the start of an HTTP request."""
    logger.info("request_start", extra={
        "method": method,
        "path": path,
        "client_ip": client_ip,
        "user_id": user_id,
        **extra
    })


def log_request_complete(
    logger: logging.Logger,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    **extra
) -> None:
    """Log the completion of an HTTP request."""
    level = logging.INFO if status_code < 400 else logging.WARNING if status_code < 500 else logging.ERROR
    logger.log(level, "request_complete", extra={
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": round(duration_ms, 2),
        **extra
    })


def log_error(
    logger: logging.Logger,
    message: str,
    error: Optional[Exception] = None,
    **context
) -> None:
    """
    Log an error with full context and stack trace.

    Args:
        logger: Logger instance
        message: Error description
        error: Exception object (if available)
        **context: Additional context to include
    """
    extra = {**context}
    if error:
        extra["error_type"] = error.__class__.__name__
        extra["error_message"] = str(error)
        extra["stack_trace"] = traceback.format_exc()

    logger.error(message, extra=extra, exc_info=error is not None)


def log_audit(
    logger: logging.Logger,
    action: str,
    user_id: Optional[str] = None,
    resource: Optional[str] = None,
    **details
) -> None:
    """
    Log an audit event (authentication, data access, etc.).

    Args:
        logger: Logger instance
        action: Action being audited (e.g., "login", "data_export")
        user_id: User performing the action
        resource: Resource being accessed
        **details: Additional audit details
    """
    logger.info(f"audit:{action}", extra={
        "audit_action": action,
        "user_id": user_id,
        "resource": resource,
        **details
    })


# Auto-configure logging when module is imported (can be overridden)
_configured = False

def ensure_configured():
    """Ensure logging is configured. Safe to call multiple times."""
    global _configured
    if not _configured:
        configure_logging()
        _configured = True
