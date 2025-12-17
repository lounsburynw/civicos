"""
Request volume metrics for Civic platform.

Monitors API request counts, response times, and traffic patterns.
Works with the structured JSON logs from logging_config.py.

Features:
- Reads request_complete events from logs/civic.json.log
- Calculates request counts over configurable time windows
- Provides response time percentiles (p50, p95, p99)
- Tracks requests by endpoint, method, and status code
- Integrates with /health endpoint for monitoring

Usage:
    from civic_services.monitoring.request_metrics import RequestMetricsManager

    # Get current request metrics (for /health endpoint)
    metrics_manager = RequestMetricsManager()
    metrics = metrics_manager.get_request_metrics()

Session 296: Initial request metrics implementation
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RequestMetrics:
    """Request volume metrics for a time window."""
    window_minutes: int
    total_requests: int
    requests_per_minute: float
    timestamp: str

    # By status code category
    success_count: int  # 2xx
    redirect_count: int  # 3xx
    client_error_count: int  # 4xx
    server_error_count: int  # 5xx

    # Response time percentiles (milliseconds)
    response_time_p50: Optional[float]
    response_time_p95: Optional[float]
    response_time_p99: Optional[float]
    response_time_avg: Optional[float]

    # Top endpoints by request count
    top_endpoints: List[Dict[str, Any]]

    # By HTTP method
    requests_by_method: Dict[str, int]


class RequestMetricsCollector:
    """
    Collects request metrics from structured JSON logs.

    Reads the civic.json.log file and calculates request volume
    and response time statistics over configurable time windows.
    """

    def __init__(self, log_file: str = "logs/civic.json.log"):
        self.log_file = Path(log_file)

    def get_recent_requests(self, minutes: int = 5) -> List[Dict[str, Any]]:
        """
        Get request completion events from the last N minutes.

        Args:
            minutes: Time window in minutes

        Returns:
            List of request_complete log entries
        """
        if not self.log_file.exists():
            logger.debug(f"Log file not found: {self.log_file}")
            return []

        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        requests = []

        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        # Only process request_complete events
                        if entry.get('message') != 'request_complete':
                            continue

                        # Parse timestamp
                        timestamp_str = entry.get('timestamp', '')
                        try:
                            entry_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        except ValueError:
                            continue

                        # Filter by time window
                        if entry_time >= cutoff_time:
                            requests.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Error reading log file: {e}")
            return []

        return requests

    def calculate_metrics(self, minutes: int = 5) -> RequestMetrics:
        """
        Calculate request metrics for the given time window.

        Args:
            minutes: Time window in minutes

        Returns:
            RequestMetrics object with calculated statistics
        """
        requests = self.get_recent_requests(minutes)

        total = len(requests)
        success_count = 0  # 2xx
        redirect_count = 0  # 3xx
        client_error_count = 0  # 4xx
        server_error_count = 0  # 5xx

        endpoint_counts: Dict[str, int] = {}
        method_counts: Dict[str, int] = {}
        response_times: List[float] = []

        for req in requests:
            extra = req.get('extra', {})
            status_code = extra.get('status_code', 0)
            path = extra.get('path', 'unknown')
            method = extra.get('method', 'unknown')
            duration_ms = extra.get('duration_ms')

            # Count by status category
            if 200 <= status_code < 300:
                success_count += 1
            elif 300 <= status_code < 400:
                redirect_count += 1
            elif 400 <= status_code < 500:
                client_error_count += 1
            elif 500 <= status_code < 600:
                server_error_count += 1

            # Count by endpoint (normalize path by removing query strings and IDs)
            normalized_path = self._normalize_path(path)
            endpoint_counts[normalized_path] = endpoint_counts.get(normalized_path, 0) + 1

            # Count by method
            method_counts[method] = method_counts.get(method, 0) + 1

            # Collect response times
            if duration_ms is not None:
                response_times.append(float(duration_ms))

        # Calculate requests per minute
        requests_per_minute = total / minutes if minutes > 0 else 0.0

        # Calculate response time percentiles
        p50, p95, p99, avg = self._calculate_percentiles(response_times)

        # Get top endpoints
        top_endpoints = sorted(
            endpoint_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        return RequestMetrics(
            window_minutes=minutes,
            total_requests=total,
            requests_per_minute=round(requests_per_minute, 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
            success_count=success_count,
            redirect_count=redirect_count,
            client_error_count=client_error_count,
            server_error_count=server_error_count,
            response_time_p50=p50,
            response_time_p95=p95,
            response_time_p99=p99,
            response_time_avg=avg,
            top_endpoints=[
                {"path": path, "count": count}
                for path, count in top_endpoints
            ],
            requests_by_method=method_counts
        )

    def _normalize_path(self, path: str) -> str:
        """
        Normalize path for aggregation by removing query strings and IDs.

        Examples:
            /api/events?limit=10 -> /api/events
            /api/issues/123 -> /api/issues/{id}
            /api/users/abc-def/profile -> /api/users/{id}/profile
        """
        # Remove query string
        if '?' in path:
            path = path.split('?')[0]

        # Replace UUID-like segments with {id}
        parts = path.split('/')
        normalized_parts = []
        for part in parts:
            # Check if part looks like an ID (numeric, UUID, or alphanumeric with dashes)
            if part and (
                part.isdigit() or
                (len(part) >= 8 and '-' in part) or
                (len(part) >= 32 and part.isalnum())
            ):
                normalized_parts.append('{id}')
            else:
                normalized_parts.append(part)

        return '/'.join(normalized_parts)

    def _calculate_percentiles(self, values: List[float]) -> tuple:
        """
        Calculate p50, p95, p99, and average for a list of values.

        Returns:
            Tuple of (p50, p95, p99, avg) or (None, None, None, None) if no values
        """
        if not values:
            return None, None, None, None

        sorted_values = sorted(values)
        n = len(sorted_values)

        def percentile(p: float) -> float:
            idx = int(n * p / 100)
            idx = min(idx, n - 1)
            return round(sorted_values[idx], 2)

        avg = round(sum(values) / n, 2)

        return percentile(50), percentile(95), percentile(99), avg


class RequestMetricsManager:
    """
    Manages request metrics collection and reporting.

    Provides a high-level interface for retrieving request metrics,
    suitable for integration with the /health endpoint.
    """

    def __init__(
        self,
        log_file: str = "logs/civic.json.log",
        window_minutes: int = 5
    ):
        """
        Initialize metrics manager.

        Args:
            log_file: Path to JSON log file
            window_minutes: Default time window for metrics calculation
        """
        self.collector = RequestMetricsCollector(log_file)
        self.window_minutes = window_minutes

    def get_request_metrics(self, window_minutes: Optional[int] = None) -> Dict[str, Any]:
        """
        Get current request metrics for external consumption (e.g., /health endpoint).

        Args:
            window_minutes: Optional override for time window

        Returns:
            Dictionary with request metrics suitable for JSON serialization
        """
        minutes = window_minutes or self.window_minutes
        metrics = self.collector.calculate_metrics(minutes)
        return asdict(metrics)

    def get_request_count(self, window_minutes: Optional[int] = None) -> int:
        """
        Get total request count for the time window.

        Args:
            window_minutes: Optional override for time window

        Returns:
            Total number of requests
        """
        minutes = window_minutes or self.window_minutes
        metrics = self.collector.calculate_metrics(minutes)
        return metrics.total_requests

    def get_requests_per_minute(self, window_minutes: Optional[int] = None) -> float:
        """
        Get requests per minute rate.

        Args:
            window_minutes: Optional override for time window

        Returns:
            Requests per minute as float
        """
        minutes = window_minutes or self.window_minutes
        metrics = self.collector.calculate_metrics(minutes)
        return metrics.requests_per_minute


# Module-level singleton for easy access
_request_metrics_manager: Optional[RequestMetricsManager] = None


def get_request_metrics_manager() -> RequestMetricsManager:
    """
    Get the singleton RequestMetricsManager instance.

    Returns:
        RequestMetricsManager instance
    """
    global _request_metrics_manager
    if _request_metrics_manager is None:
        _request_metrics_manager = RequestMetricsManager()
    return _request_metrics_manager


if __name__ == "__main__":
    # CLI for quick metrics check
    import argparse

    parser = argparse.ArgumentParser(description="Civic Request Metrics")
    parser.add_argument(
        "--window", "-w",
        type=int,
        default=5,
        help="Time window in minutes (default: 5)"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    args = parser.parse_args()

    manager = RequestMetricsManager(window_minutes=args.window)
    metrics = manager.get_request_metrics()

    if args.json:
        print(json.dumps(metrics, indent=2))
    else:
        print(f"\n=== Request Metrics (last {args.window} min) ===")
        print(f"Total requests: {metrics['total_requests']}")
        print(f"Requests/min: {metrics['requests_per_minute']}")
        print(f"\nBy status:")
        print(f"  2xx (success): {metrics['success_count']}")
        print(f"  3xx (redirect): {metrics['redirect_count']}")
        print(f"  4xx (client error): {metrics['client_error_count']}")
        print(f"  5xx (server error): {metrics['server_error_count']}")
        print(f"\nResponse times:")
        if metrics['response_time_avg'] is not None:
            print(f"  Average: {metrics['response_time_avg']}ms")
            print(f"  P50: {metrics['response_time_p50']}ms")
            print(f"  P95: {metrics['response_time_p95']}ms")
            print(f"  P99: {metrics['response_time_p99']}ms")
        else:
            print("  No response time data")
        print(f"\nBy method: {metrics['requests_by_method']}")
        print(f"\nTop endpoints:")
        for ep in metrics['top_endpoints'][:5]:
            print(f"  {ep['path']}: {ep['count']}")
