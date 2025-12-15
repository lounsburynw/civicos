"""
Shared pytest fixtures for civic tests.

This conftest.py provides session-scoped fixtures for expensive resources
that can be shared across test workers when running with pytest-xdist.

Usage:
    pytest -n auto --dist loadscope  # Run tests in parallel
"""

import os
import tempfile
from pathlib import Path

import pytest


# ============================================================================
# Session-scoped fixtures for expensive resources
# ============================================================================

@pytest.fixture(scope="session")
def sentence_transformer_model():
    """
    Session-scoped SentenceTransformer model to avoid reloading for each test.

    This fixture loads the model once per worker process and reuses it.
    The model is ~90MB and takes ~2-3s to load, so caching significantly
    speeds up tests that use embeddings.
    """
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        pytest.skip("sentence-transformers not installed")


@pytest.fixture(scope="session")
def embedding_provider_cached():
    """
    Session-scoped embedding provider for RAG tests.

    Uses the cached SentenceTransformer model to avoid reloading.
    """
    try:
        from civic._internal.rag.embedding_provider import SentenceTransformerProvider
        return SentenceTransformerProvider()
    except ImportError:
        pytest.skip("embedding provider not available")


# ============================================================================
# Worker-isolated fixtures for database access
# ============================================================================

@pytest.fixture
def isolated_db_path(tmp_path):
    """
    Provide an isolated database path for tests that need database access.

    Uses pytest's tmp_path fixture to ensure each test gets its own
    temporary directory, avoiding conflicts in parallel execution.
    """
    db_path = tmp_path / "civic_test.db"
    return str(db_path)


@pytest.fixture
def isolated_vector_dir(tmp_path):
    """
    Provide an isolated directory for ChromaDB collections.

    Each test gets its own vector store directory to avoid conflicts
    when running tests in parallel.
    """
    vector_dir = tmp_path / "vectors"
    vector_dir.mkdir(exist_ok=True)
    return str(vector_dir)


@pytest.fixture
def collection_suffix(request):
    """
    Generate a unique collection suffix for test isolation.

    This suffix can be passed to CivicEmbeddings(collection_suffix=...) to ensure
    each test uses unique collection names, preventing conflicts when multiple
    tests run in parallel against a shared ChromaDB persist_directory.

    The suffix combines:
    - pytest-xdist worker ID (if running in parallel)
    - Test node ID (unique per test)
    """
    # Get xdist worker ID if available
    if hasattr(request.config, "workerinput"):
        worker = request.config.workerinput["workerid"]
    else:
        worker = "main"

    # Create unique suffix from worker + test name hash
    test_id = hash(request.node.nodeid) % 100000
    return f"_{worker}_{test_id}"


@pytest.fixture
def isolated_chroma_config(isolated_vector_dir, collection_suffix):
    """
    Provide complete isolation config for ChromaDB-based tests.

    Returns a dict with:
    - persist_directory: Isolated temp directory for this test
    - collection_suffix: Unique suffix to append to collection names

    Usage:
        def test_embeddings(isolated_chroma_config):
            embedder = CivicEmbeddings(
                jurisdiction_id="city-san-rafael",
                persist_directory=isolated_chroma_config["persist_directory"],
                collection_suffix=isolated_chroma_config["collection_suffix"],
            )
    """
    return {
        "persist_directory": isolated_vector_dir,
        "collection_suffix": collection_suffix,
    }


# ============================================================================
# pytest-xdist worker identification
# ============================================================================

@pytest.fixture(scope="session")
def worker_id(request):
    """
    Return the xdist worker id, or 'master' if not running under xdist.

    Useful for tests that need worker-specific resource naming.
    """
    if hasattr(request.config, "workerinput"):
        return request.config.workerinput["workerid"]
    return "master"


@pytest.fixture(scope="session")
def tmp_path_factory_session(tmp_path_factory, worker_id):
    """
    Session-scoped temporary directory unique to each worker.

    Use this for session-scoped resources that need file system isolation
    between parallel workers.
    """
    return tmp_path_factory.mktemp(f"civic_session_{worker_id}")


# ============================================================================
# Test markers configuration
# ============================================================================

def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "fast: Quick unit tests for local development (< 1s each)"
    )
    config.addinivalue_line(
        "markers", "slow: Load tests and performance benchmarks (skip in local dev, CI-only)"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests requiring real/semi-real data"
    )
    config.addinivalue_line(
        "markers", "concurrent: Tests for concurrent access patterns"
    )
    config.addinivalue_line(
        "markers", "rag: RAG infrastructure tests (embeddings, vector search)"
    )
    config.addinivalue_line(
        "markers", "websocket: Real-time WebSocket integration tests"
    )
    config.addinivalue_line(
        "markers", "requires_real_data: Tests requiring gitignored real data files (skip in CI)"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests marked with requires_real_data when running in CI."""
    # Check if running in CI environment
    in_ci = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"

    if not in_ci:
        return

    skip_real_data = pytest.mark.skip(
        reason="Skipped in CI: requires gitignored real data files"
    )
    for item in items:
        if "requires_real_data" in item.keywords:
            item.add_marker(skip_real_data)
