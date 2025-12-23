"""
Data Path Resolver - Centralized file path management for Civic platform.

This module provides a single source of truth for all data file paths,
supporting both local development and containerized deployment.

Environment Variables:
    CIVIC_DATA_ROOT: Single root for all data (development default: "data")
    CIVIC_BUNDLED_DATA_DIR: Read-only reference data (production: /app/bundled-data)
    CIVIC_USER_DATA_DIR: Persistent user data (production: /app/user-data)

Priority (highest to lowest):
    1. CIVIC_BUNDLED_DATA_DIR / CIVIC_USER_DATA_DIR (production separation)
    2. CIVIC_DATA_ROOT (unified directory for development)
    3. Default: "data" relative to working directory

Usage:
    from civic.paths import get_data_path, get_state_db_path, get_vectors_dir

    # Generic paths
    path = get_data_path("pilot", "vectors", "city-san-rafael")

    # Convenience methods
    db_path = get_state_db_path()           # data/civic_state.db
    vectors = get_vectors_dir("san-rafael") # data/pilot/vectors/city-san-rafael
    checkpoints = get_checkpoints_dir()     # data/checkpoints

    # With custom resolver (for testing)
    resolver = DataPathResolver(root="/tmp/test-data")
    path = resolver.state_db()
"""

import os
from pathlib import Path
from typing import Optional, Union


class DataPathResolver:
    """
    Centralized path resolution for Civic data files.

    Supports environment-based configuration for deployment flexibility:
    - Development: All data in single directory (CIVIC_DATA_ROOT or "data")
    - Production: Separate bundled (read-only) and user (persistent) data

    Attributes:
        bundled_root: Path to bundled/read-only data (vectors, events, legislation)
        user_root: Path to user/persistent data (databases, checkpoints, sessions)
    """

    def __init__(
        self,
        root: Optional[Union[str, Path]] = None,
        bundled_root: Optional[Union[str, Path]] = None,
        user_root: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize path resolver.

        Args:
            root: Single root for all data (overrides env vars if set)
            bundled_root: Explicit bundled data root (overrides root for bundled)
            user_root: Explicit user data root (overrides root for user)

        If no args provided, reads from environment:
            - CIVIC_BUNDLED_DATA_DIR for bundled data
            - CIVIC_USER_DATA_DIR for user data
            - CIVIC_DATA_ROOT as fallback for both
            - "data" as final default
        """
        if root is not None:
            # Explicit root overrides everything
            self._bundled_root = Path(root)
            self._user_root = Path(root)
        else:
            # Check environment variables
            env_bundled = os.environ.get("CIVIC_BUNDLED_DATA_DIR")
            env_user = os.environ.get("CIVIC_USER_DATA_DIR")
            env_root = os.environ.get("CIVIC_DATA_ROOT", "data")

            self._bundled_root = Path(bundled_root or env_bundled or env_root)
            self._user_root = Path(user_root or env_user or env_root)

    @property
    def bundled_root(self) -> Path:
        """Root directory for bundled (read-only) data."""
        return self._bundled_root

    @property
    def user_root(self) -> Path:
        """Root directory for user (persistent) data."""
        return self._user_root

    # =========================================================================
    # Generic path methods
    # =========================================================================

    def bundled_path(self, *parts: str) -> Path:
        """
        Get path within bundled data directory.

        Bundled data is read-only reference data:
        - Events, meetings, agenda items
        - Vector embeddings
        - Legislative context
        - Funding opportunities

        Args:
            *parts: Path components relative to bundled root

        Returns:
            Absolute path to the file/directory

        Example:
            resolver.bundled_path("pilot", "vectors", "city-san-rafael")
            # -> Path("data/pilot/vectors/city-san-rafael")
        """
        return self._bundled_root.joinpath(*parts)

    def user_path(self, *parts: str) -> Path:
        """
        Get path within user data directory.

        User data is persistent data that survives deploys:
        - State database (civic_state.db)
        - Participation database (civic_participation.db)
        - Checkpoints for resumable extraction
        - Session data

        Args:
            *parts: Path components relative to user root

        Returns:
            Absolute path to the file/directory

        Example:
            resolver.user_path("civic_state.db")
            # -> Path("data/civic_state.db")
        """
        return self._user_root.joinpath(*parts)

    # =========================================================================
    # Convenience methods for common paths
    # =========================================================================

    def state_db(self) -> Path:
        """
        Path to main state database (civic_state.db).

        Contains: meetings, agenda items, decisions, voices, initiatives
        """
        return self.user_path("civic_state.db")

    def participation_db(self) -> Path:
        """
        Path to participation database (civic_participation.db).

        Contains: user sessions, participation metrics, feedback
        """
        return self.user_path("civic_participation.db")

    def vectors_dir(self, jurisdiction: Optional[str] = None) -> Path:
        """
        Path to vector embeddings directory.

        Args:
            jurisdiction: Optional jurisdiction ID (e.g., "city-san-rafael")
                         If provided, returns jurisdiction-specific vectors dir

        Returns:
            Base vectors dir or jurisdiction-specific dir

        Example:
            resolver.vectors_dir()  # data/pilot/vectors
            resolver.vectors_dir("city-san-rafael")  # data/pilot/vectors/city-san-rafael
        """
        base = self.bundled_path("pilot", "vectors")
        if jurisdiction:
            return base / jurisdiction
        return base

    def checkpoints_dir(self) -> Path:
        """
        Path to extraction checkpoints directory.

        Contains: Pipeline state for resumable extraction jobs
        """
        return self.user_path("checkpoints")

    def events_dir(self, jurisdiction: Optional[str] = None) -> Path:
        """
        Path to events data directory.

        Args:
            jurisdiction: Optional jurisdiction ID

        Example:
            resolver.events_dir()  # data/events
            resolver.events_dir("city-san-rafael")  # data/events/city-san-rafael
        """
        base = self.bundled_path("events")
        if jurisdiction:
            return base / jurisdiction
        return base

    def legislation_dir(self, state: Optional[str] = None) -> Path:
        """
        Path to legislation data directory.

        Args:
            state: Optional state name (e.g., "california")

        Example:
            resolver.legislation_dir()  # data/legislation
            resolver.legislation_dir("california")  # data/legislation/state/california
        """
        base = self.bundled_path("legislation")
        if state:
            return base / "state" / state
        return base

    def pilot_dir(self) -> Path:
        """Path to pilot data directory (data/pilot)."""
        return self.bundled_path("pilot")

    def monitoring_file(self, filename: str) -> Path:
        """
        Path to monitoring/metrics file.

        Args:
            filename: e.g., "cost_monitoring.json", "system_failures.json"
        """
        return self.user_path(filename)


# =============================================================================
# Module-level default resolver and convenience functions
# =============================================================================

_default_resolver: Optional[DataPathResolver] = None


def get_resolver() -> DataPathResolver:
    """
    Get the default path resolver instance.

    Creates resolver on first call using environment configuration.
    Thread-safe for read access after initialization.

    Returns:
        Singleton DataPathResolver instance
    """
    global _default_resolver
    if _default_resolver is None:
        _default_resolver = DataPathResolver()
    return _default_resolver


def reset_resolver() -> None:
    """
    Reset the default resolver (useful for testing).

    After calling this, get_resolver() will create a new instance
    with current environment variables.
    """
    global _default_resolver
    _default_resolver = None


def get_data_path(*parts: str, bundled: bool = True) -> str:
    """
    Get path to a data file as a string.

    Args:
        *parts: Path components relative to data root
        bundled: If True, use bundled data dir; if False, use user data dir

    Returns:
        Absolute path string

    Example:
        get_data_path("pilot", "vectors", "city-san-rafael")
        # -> "data/pilot/vectors/city-san-rafael"

        get_data_path("civic_state.db", bundled=False)
        # -> "data/civic_state.db"
    """
    resolver = get_resolver()
    if bundled:
        return str(resolver.bundled_path(*parts))
    return str(resolver.user_path(*parts))


def get_bundled_path(*parts: str) -> str:
    """
    Get path within bundled (read-only) data directory.

    Convenience function matching civic-services config.py interface.

    Args:
        *parts: Path components

    Returns:
        Absolute path string
    """
    return str(get_resolver().bundled_path(*parts))


def get_user_path(*parts: str) -> str:
    """
    Get path within user (persistent) data directory.

    Convenience function matching civic-services config.py interface.

    Args:
        *parts: Path components

    Returns:
        Absolute path string
    """
    return str(get_resolver().user_path(*parts))


# =============================================================================
# Typed convenience functions for common paths
# =============================================================================


def get_state_db_path() -> str:
    """Get path to main state database (civic_state.db)."""
    return str(get_resolver().state_db())


def get_participation_db_path() -> str:
    """Get path to participation database (civic_participation.db)."""
    return str(get_resolver().participation_db())


def get_vectors_dir(jurisdiction: Optional[str] = None) -> str:
    """
    Get path to vectors directory.

    Args:
        jurisdiction: Optional jurisdiction ID for jurisdiction-specific vectors
    """
    return str(get_resolver().vectors_dir(jurisdiction))


def get_checkpoints_dir() -> str:
    """Get path to checkpoints directory."""
    return str(get_resolver().checkpoints_dir())


def get_events_dir(jurisdiction: Optional[str] = None) -> str:
    """Get path to events directory."""
    return str(get_resolver().events_dir(jurisdiction))


def get_legislation_dir(state: Optional[str] = None) -> str:
    """Get path to legislation directory."""
    return str(get_resolver().legislation_dir(state))


def get_pilot_dir() -> str:
    """Get path to pilot data directory."""
    return str(get_resolver().pilot_dir())
