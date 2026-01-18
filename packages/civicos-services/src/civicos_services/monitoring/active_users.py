"""
Active users metrics for Civic platform.

Tracks unique users per time window based on client identifiers.
Works with the structured JSON logs from logging_config.py.

Features:
- Reads request events from logs/civic.json.log
- Tracks unique users by client IP (and Bearer token when available)
- Calculates daily active users (DAU) and users per time window
- Integrates with /health endpoint for monitoring

Usage:
    from civicos_services.monitoring.active_users import ActiveUsersManager

    # Get current active users metrics (for /health endpoint)
    manager = ActiveUsersManager()
    metrics = manager.get_active_users()

Session 297: Initial active users tracking implementation
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ActiveUsersMetrics:
    """Active users metrics for a time window."""
    window_minutes: int
    unique_users: int
    active_users_per_hour: float
    timestamp: str

    # Breakdown by authentication type
    authenticated_users: int  # Users with Bearer token
    anonymous_users: int  # IP-only users

    # Daily metrics (24h window)
    daily_active_users: int


class ActiveUsersCollector:
    """
    Collects active user metrics from structured JSON logs.

    Reads the civic.json.log file and tracks unique users
    based on client IP addresses and authentication tokens.
    """

    def __init__(self, log_file: str = "logs/civic.json.log"):
        self.log_file = Path(log_file)

    def get_user_identifiers(self, minutes: int = 5) -> Dict[str, Set[str]]:
        """
        Get unique user identifiers from the last N minutes.

        Args:
            minutes: Time window in minutes

        Returns:
            Dictionary with 'authenticated' and 'anonymous' sets of user IDs
        """
        if not self.log_file.exists():
            logger.debug(f"Log file not found: {self.log_file}")
            return {'authenticated': set(), 'anonymous': set()}

        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        authenticated: Set[str] = set()
        anonymous: Set[str] = set()

        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)

                        # Process both request_start (has client_ip) and request_complete
                        message = entry.get('message', '')
                        if message not in ('request_start', 'request_complete'):
                            continue

                        # Parse timestamp
                        timestamp_str = entry.get('timestamp', '')
                        try:
                            entry_time = datetime.fromisoformat(
                                timestamp_str.replace('Z', '+00:00')
                            )
                        except ValueError:
                            continue

                        # Filter by time window
                        if entry_time < cutoff_time:
                            continue

                        extra = entry.get('extra', {})

                        # Try to get user identifier
                        # Priority: user_id (authenticated) > client_ip (anonymous)
                        user_id = extra.get('user_id')
                        client_ip = extra.get('client_ip')

                        if user_id:
                            authenticated.add(user_id)
                        elif client_ip:
                            anonymous.add(client_ip)

                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Error reading log file: {e}")
            return {'authenticated': set(), 'anonymous': set()}

        return {'authenticated': authenticated, 'anonymous': anonymous}

    def calculate_metrics(self, minutes: int = 5) -> ActiveUsersMetrics:
        """
        Calculate active user metrics for the given time window.

        Args:
            minutes: Time window in minutes

        Returns:
            ActiveUsersMetrics object with calculated statistics
        """
        users = self.get_user_identifiers(minutes)
        authenticated_count = len(users['authenticated'])
        anonymous_count = len(users['anonymous'])
        total_unique = authenticated_count + anonymous_count

        # Calculate users per hour rate
        if minutes > 0:
            users_per_hour = (total_unique / minutes) * 60
        else:
            users_per_hour = 0.0

        # Get daily active users (24h = 1440 minutes)
        daily_users = self.get_user_identifiers(1440)
        daily_active = len(daily_users['authenticated']) + len(daily_users['anonymous'])

        return ActiveUsersMetrics(
            window_minutes=minutes,
            unique_users=total_unique,
            active_users_per_hour=round(users_per_hour, 2),
            timestamp=datetime.now(timezone.utc).isoformat(),
            authenticated_users=authenticated_count,
            anonymous_users=anonymous_count,
            daily_active_users=daily_active
        )


class ActiveUsersManager:
    """
    Manages active user metrics collection and reporting.

    Provides a high-level interface for retrieving active user metrics,
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
        self.collector = ActiveUsersCollector(log_file)
        self.window_minutes = window_minutes

    def get_active_users(self, window_minutes: Optional[int] = None) -> Dict[str, Any]:
        """
        Get current active user metrics for external consumption (e.g., /health endpoint).

        Args:
            window_minutes: Optional override for time window

        Returns:
            Dictionary with active user metrics suitable for JSON serialization
        """
        minutes = window_minutes or self.window_minutes
        metrics = self.collector.calculate_metrics(minutes)
        return asdict(metrics)

    def get_unique_users_count(self, window_minutes: Optional[int] = None) -> int:
        """
        Get unique user count for the time window.

        Args:
            window_minutes: Optional override for time window

        Returns:
            Total number of unique users
        """
        minutes = window_minutes or self.window_minutes
        metrics = self.collector.calculate_metrics(minutes)
        return metrics.unique_users

    def get_daily_active_users(self) -> int:
        """
        Get daily active users count (24h window).

        Returns:
            Number of unique users in last 24 hours
        """
        metrics = self.collector.calculate_metrics(self.window_minutes)
        return metrics.daily_active_users


# Module-level singleton for easy access
_active_users_manager: Optional[ActiveUsersManager] = None


def get_active_users_manager() -> ActiveUsersManager:
    """
    Get the singleton ActiveUsersManager instance.

    Returns:
        ActiveUsersManager instance
    """
    global _active_users_manager
    if _active_users_manager is None:
        _active_users_manager = ActiveUsersManager()
    return _active_users_manager


if __name__ == "__main__":
    # CLI for quick metrics check
    import argparse

    parser = argparse.ArgumentParser(description="Civic Active Users Metrics")
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

    manager = ActiveUsersManager(window_minutes=args.window)
    metrics = manager.get_active_users()

    if args.json:
        print(json.dumps(metrics, indent=2))
    else:
        print(f"\n=== Active Users Metrics (last {args.window} min) ===")
        print(f"Unique users: {metrics['unique_users']}")
        print(f"Users/hour: {metrics['active_users_per_hour']}")
        print(f"\nBy authentication:")
        print(f"  Authenticated: {metrics['authenticated_users']}")
        print(f"  Anonymous (IP-only): {metrics['anonymous_users']}")
        print(f"\nDaily active users (24h): {metrics['daily_active_users']}")
