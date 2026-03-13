"""Shared pytest configuration for civicos-services tests."""

import os

import pytest

# Load .env early so DATABASE_URL is available during test collection.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: Integration tests requiring real/semi-real data"
    )
    config.addinivalue_line(
        "markers", "requires_pgvector: Tests requiring pgvector database (DATABASE_URL must be set)"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip tests based on environment."""
    has_database_url = bool(os.environ.get("DATABASE_URL"))

    skip_pgvector = pytest.mark.skip(
        reason="DATABASE_URL not set - pgvector tests require database connection"
    )

    for item in items:
        if not has_database_url and "requires_pgvector" in item.keywords:
            item.add_marker(skip_pgvector)
