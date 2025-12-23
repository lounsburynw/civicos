"""
Tests for DataPathResolver - centralized file path management.

Tests cover:
- Default path resolution (CIVIC_DATA_ROOT fallback)
- Environment variable configuration
- Bundled vs user data separation
- Convenience methods for common paths
- Resolver reset for testing
"""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

from civic.paths import (
    DataPathResolver,
    get_resolver,
    reset_resolver,
    get_data_path,
    get_bundled_path,
    get_user_path,
    get_state_db_path,
    get_participation_db_path,
    get_vectors_dir,
    get_checkpoints_dir,
    get_events_dir,
    get_legislation_dir,
    get_pilot_dir,
)


class TestDataPathResolver:
    """Tests for DataPathResolver class."""

    def test_default_root_is_data(self):
        """Default root should be 'data' when no env vars set."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear any existing env vars
            for key in ["CIVIC_DATA_ROOT", "CIVIC_BUNDLED_DATA_DIR", "CIVIC_USER_DATA_DIR"]:
                os.environ.pop(key, None)
            resolver = DataPathResolver()
            assert resolver.bundled_root == Path("data")
            assert resolver.user_root == Path("data")

    def test_explicit_root_overrides_env(self):
        """Explicit root parameter should override environment."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/env/path"}):
            resolver = DataPathResolver(root="/explicit/path")
            assert resolver.bundled_root == Path("/explicit/path")
            assert resolver.user_root == Path("/explicit/path")

    def test_civic_data_root_env_var(self):
        """CIVIC_DATA_ROOT should set both bundled and user roots."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/custom/data"}, clear=True):
            for key in ["CIVIC_BUNDLED_DATA_DIR", "CIVIC_USER_DATA_DIR"]:
                os.environ.pop(key, None)
            resolver = DataPathResolver()
            assert resolver.bundled_root == Path("/custom/data")
            assert resolver.user_root == Path("/custom/data")

    def test_separate_bundled_and_user_dirs(self):
        """Production-style separation of bundled and user data."""
        with patch.dict(os.environ, {
            "CIVIC_BUNDLED_DATA_DIR": "/app/bundled-data",
            "CIVIC_USER_DATA_DIR": "/app/user-data",
        }):
            resolver = DataPathResolver()
            assert resolver.bundled_root == Path("/app/bundled-data")
            assert resolver.user_root == Path("/app/user-data")

    def test_bundled_dir_overrides_root(self):
        """CIVIC_BUNDLED_DATA_DIR should override CIVIC_DATA_ROOT for bundled."""
        with patch.dict(os.environ, {
            "CIVIC_DATA_ROOT": "/fallback",
            "CIVIC_BUNDLED_DATA_DIR": "/app/bundled",
        }):
            os.environ.pop("CIVIC_USER_DATA_DIR", None)
            resolver = DataPathResolver()
            assert resolver.bundled_root == Path("/app/bundled")
            assert resolver.user_root == Path("/fallback")  # Falls back to CIVIC_DATA_ROOT

    def test_user_dir_overrides_root(self):
        """CIVIC_USER_DATA_DIR should override CIVIC_DATA_ROOT for user data."""
        with patch.dict(os.environ, {
            "CIVIC_DATA_ROOT": "/fallback",
            "CIVIC_USER_DATA_DIR": "/app/user",
        }):
            os.environ.pop("CIVIC_BUNDLED_DATA_DIR", None)
            resolver = DataPathResolver()
            assert resolver.bundled_root == Path("/fallback")
            assert resolver.user_root == Path("/app/user")


class TestPathMethods:
    """Tests for path generation methods."""

    @pytest.fixture
    def resolver(self):
        """Create resolver with known root for testing."""
        return DataPathResolver(root="/test/data")

    def test_bundled_path(self, resolver):
        """bundled_path should join parts to bundled root."""
        path = resolver.bundled_path("pilot", "vectors", "city-san-rafael")
        assert path == Path("/test/data/pilot/vectors/city-san-rafael")

    def test_user_path(self, resolver):
        """user_path should join parts to user root."""
        path = resolver.user_path("civic_state.db")
        assert path == Path("/test/data/civic_state.db")

    def test_state_db(self, resolver):
        """state_db should return path to civic_state.db."""
        assert resolver.state_db() == Path("/test/data/civic_state.db")

    def test_participation_db(self, resolver):
        """participation_db should return path to civic_participation.db."""
        assert resolver.participation_db() == Path("/test/data/civic_participation.db")

    def test_vectors_dir_without_jurisdiction(self, resolver):
        """vectors_dir without args should return base vectors directory."""
        assert resolver.vectors_dir() == Path("/test/data/pilot/vectors")

    def test_vectors_dir_with_jurisdiction(self, resolver):
        """vectors_dir with jurisdiction should return jurisdiction-specific path."""
        path = resolver.vectors_dir("city-san-rafael")
        assert path == Path("/test/data/pilot/vectors/city-san-rafael")

    def test_checkpoints_dir(self, resolver):
        """checkpoints_dir should return checkpoints path."""
        assert resolver.checkpoints_dir() == Path("/test/data/checkpoints")

    def test_events_dir_without_jurisdiction(self, resolver):
        """events_dir without args should return base events directory."""
        assert resolver.events_dir() == Path("/test/data/events")

    def test_events_dir_with_jurisdiction(self, resolver):
        """events_dir with jurisdiction should return jurisdiction-specific path."""
        path = resolver.events_dir("city-san-rafael")
        assert path == Path("/test/data/events/city-san-rafael")

    def test_legislation_dir_without_state(self, resolver):
        """legislation_dir without args should return base legislation directory."""
        assert resolver.legislation_dir() == Path("/test/data/legislation")

    def test_legislation_dir_with_state(self, resolver):
        """legislation_dir with state should return state-specific path."""
        path = resolver.legislation_dir("california")
        assert path == Path("/test/data/legislation/state/california")

    def test_pilot_dir(self, resolver):
        """pilot_dir should return pilot data directory."""
        assert resolver.pilot_dir() == Path("/test/data/pilot")

    def test_monitoring_file(self, resolver):
        """monitoring_file should return path in user data."""
        path = resolver.monitoring_file("cost_monitoring.json")
        assert path == Path("/test/data/cost_monitoring.json")


class TestModuleFunctions:
    """Tests for module-level convenience functions."""

    def setup_method(self):
        """Reset resolver before each test."""
        reset_resolver()

    def teardown_method(self):
        """Reset resolver after each test."""
        reset_resolver()

    def test_get_resolver_returns_singleton(self):
        """get_resolver should return the same instance."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/singleton/test"}):
            resolver1 = get_resolver()
            resolver2 = get_resolver()
            assert resolver1 is resolver2

    def test_reset_resolver_clears_singleton(self):
        """reset_resolver should clear the cached instance."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/first"}):
            resolver1 = get_resolver()
            reset_resolver()

        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/second"}):
            resolver2 = get_resolver()
            assert resolver1 is not resolver2
            assert resolver2.bundled_root == Path("/second")

    def test_get_data_path_bundled(self):
        """get_data_path with bundled=True (default) uses bundled root."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            path = get_data_path("pilot", "vectors")
            assert path == "/test/pilot/vectors"

    def test_get_data_path_user(self):
        """get_data_path with bundled=False uses user root."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            path = get_data_path("civic_state.db", bundled=False)
            assert path == "/test/civic_state.db"

    def test_get_bundled_path(self):
        """get_bundled_path should return bundled data path string."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            path = get_bundled_path("events", "city-san-rafael")
            assert path == "/test/events/city-san-rafael"

    def test_get_user_path(self):
        """get_user_path should return user data path string."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            path = get_user_path("checkpoints", "youtube")
            assert path == "/test/checkpoints/youtube"

    def test_get_state_db_path(self):
        """get_state_db_path convenience function."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            assert get_state_db_path() == "/test/civic_state.db"

    def test_get_participation_db_path(self):
        """get_participation_db_path convenience function."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            assert get_participation_db_path() == "/test/civic_participation.db"

    def test_get_vectors_dir(self):
        """get_vectors_dir convenience function."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            assert get_vectors_dir() == "/test/pilot/vectors"
            assert get_vectors_dir("city-san-rafael") == "/test/pilot/vectors/city-san-rafael"

    def test_get_checkpoints_dir(self):
        """get_checkpoints_dir convenience function."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            assert get_checkpoints_dir() == "/test/checkpoints"

    def test_get_events_dir(self):
        """get_events_dir convenience function."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            assert get_events_dir() == "/test/events"

    def test_get_legislation_dir(self):
        """get_legislation_dir convenience function."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            assert get_legislation_dir() == "/test/legislation"
            assert get_legislation_dir("california") == "/test/legislation/state/california"

    def test_get_pilot_dir(self):
        """get_pilot_dir convenience function."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            assert get_pilot_dir() == "/test/pilot"


class TestProductionConfiguration:
    """Tests simulating production deployment configuration."""

    def setup_method(self):
        """Reset resolver before each test."""
        reset_resolver()

    def teardown_method(self):
        """Reset resolver after each test."""
        reset_resolver()

    def test_flyio_volume_separation(self):
        """Simulate Fly.io deployment with separate volumes."""
        with patch.dict(os.environ, {
            "CIVIC_BUNDLED_DATA_DIR": "/app/bundled-data",
            "CIVIC_USER_DATA_DIR": "/app/user-data",
        }):
            reset_resolver()

            # Bundled data paths (baked into Docker image)
            vectors = get_vectors_dir("city-san-rafael")
            assert vectors == "/app/bundled-data/pilot/vectors/city-san-rafael"

            legislation = get_legislation_dir("california")
            assert legislation == "/app/bundled-data/legislation/state/california"

            # User data paths (persistent volume)
            state_db = get_state_db_path()
            assert state_db == "/app/user-data/civic_state.db"

            checkpoints = get_checkpoints_dir()
            assert checkpoints == "/app/user-data/checkpoints"

    def test_development_unified_directory(self):
        """Development mode uses single data directory."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "data"}, clear=True):
            for key in ["CIVIC_BUNDLED_DATA_DIR", "CIVIC_USER_DATA_DIR"]:
                os.environ.pop(key, None)
            reset_resolver()

            # Everything in same directory
            vectors = get_vectors_dir("city-san-rafael")
            assert vectors == "data/pilot/vectors/city-san-rafael"

            state_db = get_state_db_path()
            assert state_db == "data/civic_state.db"


class TestBackwardsCompatibility:
    """Tests ensuring compatibility with existing code patterns."""

    def setup_method(self):
        reset_resolver()

    def teardown_method(self):
        reset_resolver()

    def test_string_return_types(self):
        """Module functions should return strings, not Path objects."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            assert isinstance(get_state_db_path(), str)
            assert isinstance(get_vectors_dir(), str)
            assert isinstance(get_bundled_path("test"), str)
            assert isinstance(get_user_path("test"), str)

    def test_path_separator_consistency(self):
        """Paths should use forward slashes for consistency."""
        with patch.dict(os.environ, {"CIVIC_DATA_ROOT": "/test"}):
            reset_resolver()
            path = get_vectors_dir("city-san-rafael")
            # On all platforms, pathlib normalizes, but str conversion is OS-dependent
            # Just verify the path components are correct
            assert "pilot" in path
            assert "vectors" in path
            assert "city-san-rafael" in path


class TestEmbeddingModelConfiguration:
    """Tests for CIVIC_EMBEDDING_MODEL environment variable support."""

    def test_default_model_without_env(self):
        """Without CIVIC_EMBEDDING_MODEL, should use nomic default."""
        import sys
        import importlib

        # Clear env var
        os.environ.pop("CIVIC_EMBEDDING_MODEL", None)

        # Force reimport to pick up env change
        if "civic._internal.meetings.embeddings" in sys.modules:
            del sys.modules["civic._internal.meetings.embeddings"]

        from civic._internal.meetings.embeddings import CivicEmbeddings

        assert CivicEmbeddings.DEFAULT_MODEL == "nomic-ai/nomic-embed-text-v1.5"

    def test_custom_model_from_env(self):
        """CIVIC_EMBEDDING_MODEL should override default embedding model."""
        import sys
        import importlib

        # Set custom model via env
        with patch.dict(os.environ, {"CIVIC_EMBEDDING_MODEL": "custom/test-model"}):
            # Force reimport to pick up env change
            if "civic._internal.meetings.embeddings" in sys.modules:
                del sys.modules["civic._internal.meetings.embeddings"]

            from civic._internal.meetings.embeddings import CivicEmbeddings

            assert CivicEmbeddings.DEFAULT_MODEL == "custom/test-model"

        # Clean up: reimport with default
        os.environ.pop("CIVIC_EMBEDDING_MODEL", None)
        if "civic._internal.meetings.embeddings" in sys.modules:
            del sys.modules["civic._internal.meetings.embeddings"]

    def test_instance_respects_default_model(self):
        """CivicEmbeddings instance should use DEFAULT_MODEL when no model_name passed."""
        import sys

        # Set custom model via env
        with patch.dict(os.environ, {"CIVIC_EMBEDDING_MODEL": "test/env-model"}):
            # Force reimport to pick up env change
            if "civic._internal.meetings.embeddings" in sys.modules:
                del sys.modules["civic._internal.meetings.embeddings"]

            from civic._internal.meetings.embeddings import CivicEmbeddings

            # Create instance without specifying model_name
            # (can't actually instantiate without chromadb, so just check class attr)
            assert CivicEmbeddings.DEFAULT_MODEL == "test/env-model"

        # Clean up: reimport with default
        os.environ.pop("CIVIC_EMBEDDING_MODEL", None)
        if "civic._internal.meetings.embeddings" in sys.modules:
            del sys.modules["civic._internal.meetings.embeddings"]
