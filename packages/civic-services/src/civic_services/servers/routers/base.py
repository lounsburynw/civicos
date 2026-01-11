"""
Base router class for Civic API domain routers.

Provides shared functionality for:
- Path matching and route registration
- Response helpers (send_json, send_error)
- CORS handling
- Rate limit headers
"""

import json
import time
import logging
from typing import Optional, Dict, Any, List, Callable, Tuple
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler
from abc import ABC, abstractmethod

# Import from parent package
from ...core.config import config
from ...core.rate_limiter import rate_limiter

# Get logger
try:
    from ...core.logging_config import get_logger, log_request_complete
    logger = get_logger('civic_router')
except ImportError:
    logger = logging.getLogger('civic_router')
    logging.basicConfig(level=logging.INFO)
    log_request_complete = None


class Route:
    """Represents a registered route with its handler."""

    def __init__(
        self,
        path_pattern: str,
        method: str,
        handler: Callable,
        is_prefix: bool = False,
        path_params: Optional[List[str]] = None
    ):
        """
        Args:
            path_pattern: URL path pattern (e.g., '/api/events' or '/api/events/{id}')
            method: HTTP method (GET, POST, PUT, DELETE)
            handler: Handler function to call
            is_prefix: If True, matches any path starting with path_pattern
            path_params: List of path parameter names extracted from pattern
        """
        self.path_pattern = path_pattern
        self.method = method
        self.handler = handler
        self.is_prefix = is_prefix
        self.path_params = path_params or []

    def matches(self, path: str, method: str) -> Tuple[bool, Dict[str, str]]:
        """
        Check if this route matches the given path and method.

        Returns:
            Tuple of (matches: bool, path_params: dict)
        """
        if self.method != method:
            return False, {}

        if self.is_prefix:
            return path.startswith(self.path_pattern), {}

        if not self.path_params:
            return path == self.path_pattern, {}

        # Handle parameterized paths like /api/events/{id}
        path_parts = path.rstrip('/').split('/')
        pattern_parts = self.path_pattern.rstrip('/').split('/')

        if len(path_parts) != len(pattern_parts):
            return False, {}

        params = {}
        for path_part, pattern_part in zip(path_parts, pattern_parts):
            if pattern_part.startswith('{') and pattern_part.endswith('}'):
                param_name = pattern_part[1:-1]
                params[param_name] = path_part
            elif path_part != pattern_part:
                return False, {}

        return True, params


class Router(ABC):
    """
    Base class for domain-specific routers.

    Each router:
    - Registers routes for its domain
    - Provides handler methods for each endpoint
    - Shares the handler instance for response methods
    """

    def __init__(self):
        self._routes: List[Route] = []
        self._handler: Optional[BaseHTTPRequestHandler] = None
        self.register_routes()

    @property
    @abstractmethod
    def prefix(self) -> str:
        """URL prefix for this router (e.g., '/api/events')."""
        pass

    @abstractmethod
    def register_routes(self) -> None:
        """Register all routes for this router. Called in __init__."""
        pass

    def set_handler(self, handler: BaseHTTPRequestHandler) -> None:
        """Set the HTTP handler for response methods."""
        self._handler = handler

    def add_route(
        self,
        path: str,
        method: str,
        handler: Callable,
        is_prefix: bool = False,
        path_params: Optional[List[str]] = None
    ) -> None:
        """Register a route."""
        self._routes.append(Route(path, method, handler, is_prefix, path_params))

    def match(self, path: str, method: str) -> Optional[Tuple[Callable, Dict[str, str]]]:
        """
        Find a matching route for the given path and method.

        Returns:
            Tuple of (handler, path_params) if match found, else None
        """
        for route in self._routes:
            matches, params = route.matches(path, method)
            if matches:
                return route.handler, params
        return None

    def can_handle(self, path: str) -> bool:
        """Check if this router might handle the given path (based on prefix)."""
        return path.startswith(self.prefix)

    # === Response Helpers ===

    def send_json(self, data: Any, status_code: int = 200) -> None:
        """Send JSON response with CORS headers and rate limit info."""
        handler = self._handler
        if handler is None:
            raise RuntimeError("Handler not set. Call set_handler() first.")

        handler.send_response(status_code)
        handler.send_header('Content-Type', 'application/json')

        # Add rate limit headers if available
        client_id = rate_limiter.get_client_id(handler)
        _, limit_headers = rate_limiter.check_rate_limit(client_id)
        if limit_headers and isinstance(limit_headers, dict):
            for header, value in limit_headers.items():
                if header.startswith('X-RateLimit'):
                    handler.send_header(header, value)

        # CORS headers
        self._add_cors_headers(handler)

        handler.send_header('X-API-Version', '0.3.0')
        handler.send_header('X-Integration-Status', 'schema-compliant')
        handler.end_headers()
        handler.wfile.write(json.dumps(data, indent=2).encode())

        # Log request completion
        self._log_request_complete(status_code)

    def send_error(self, status_code: int, message: Optional[str] = None) -> None:
        """Send error response."""
        handler = self._handler
        if handler is None:
            raise RuntimeError("Handler not set. Call set_handler() first.")

        handler.send_response(status_code)
        handler.send_header('Content-Type', 'application/json')
        self._add_cors_headers(handler)
        handler.end_headers()

        error_messages = {
            400: 'Bad Request',
            401: 'Authentication required',
            403: 'Forbidden',
            404: 'Not Found',
            429: 'Too Many Requests',
            500: 'Internal Server Error',
        }

        error_response = {
            'error': error_messages.get(status_code, 'Error'),
            'message': message or error_messages.get(status_code, 'An error occurred'),
            'status': status_code,
        }
        handler.wfile.write(json.dumps(error_response, indent=2).encode())
        self._log_request_complete(status_code)

    def _add_cors_headers(self, handler: BaseHTTPRequestHandler) -> None:
        """Add CORS headers to response."""
        origin = handler.headers.get('Origin', '*')
        allowed_origins = config.get_cors_origins()
        if '*' in allowed_origins or origin in allowed_origins:
            handler.send_header('Access-Control-Allow-Origin', origin)
        else:
            handler.send_header('Access-Control-Allow-Origin', allowed_origins[0] if allowed_origins else '*')

    def _log_request_complete(self, status_code: int) -> None:
        """Log request completion for metrics."""
        handler = self._handler
        if handler is None:
            return

        start_time = getattr(handler, '_request_start_time', None)
        method = getattr(handler, '_request_method', 'UNKNOWN')

        if start_time is not None and log_request_complete is not None:
            duration_ms = (time.time() - start_time) * 1000
            try:
                log_request_complete(
                    logger,
                    method=method,
                    path=handler.path,
                    status_code=status_code,
                    duration_ms=duration_ms
                )
            except Exception:
                pass

    # === Request Helpers ===

    def get_query_params(self) -> Dict[str, List[str]]:
        """Get query parameters from the request."""
        if self._handler is None:
            return {}
        parsed = urlparse(self._handler.path)
        return parse_qs(parsed.query)

    def get_query_param(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Get a single query parameter value."""
        params = self.get_query_params()
        values = params.get(name, [])
        return values[0] if values else default

    def get_request_body(self) -> Optional[Dict[str, Any]]:
        """Parse JSON request body."""
        if self._handler is None:
            return None

        content_length = int(self._handler.headers.get('Content-Length', 0))
        if content_length == 0:
            return None

        try:
            body = self._handler.rfile.read(content_length)
            return json.loads(body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def get_user_id_from_token(self) -> Optional[str]:
        """
        Extract user_id from Bearer token in Authorization header.

        MVP Implementation: Token IS the user_id (simple authentication)
        """
        if self._handler is None:
            return None

        auth_header = self._handler.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None

        return auth_header.replace('Bearer ', '')

    @property
    def path(self) -> str:
        """Get the request path."""
        if self._handler is None:
            return ''
        return urlparse(self._handler.path).path

    @property
    def headers(self):
        """Get request headers."""
        if self._handler is None:
            return {}
        return self._handler.headers
