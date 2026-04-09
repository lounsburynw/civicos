"""
Regression test for decisions_adapter_crashes_on_empty_vectors.

When DecisionsAdapter.search() calls search_decisions(state_manager=None, ...),
and both the explicit vector backend and auto-detect return empty results,
search_decisions must return [] instead of crashing with:
  AttributeError: 'NoneType' object has no attribute 'get_city_state'
"""

from unittest.mock import patch

from civicos.history import search_decisions


class EmptyVectorBackend:
    """A vector backend that always returns empty results."""
    backend_type = "mock_empty"

    def search(self, *args, **kwargs):
        return []

    def search_similar(self, *args, **kwargs):
        return []


@patch("civicos.history._jurisdiction_has_embeddings", return_value=False)
def test_search_decisions_none_state_manager_returns_empty(_mock):
    """search_decisions(state_manager=None) should return [] when all vector paths are empty."""
    result = search_decisions(
        state_manager=None,
        jurisdiction="city-tiburon",
        query="housing",
        vector_backend=EmptyVectorBackend(),
        storage_backend=None,
    )
    assert result == []


@patch("civicos.history._jurisdiction_has_embeddings", return_value=True)
@patch("civicos.history._search_semantic_decisions", return_value=[])
def test_search_decisions_none_state_manager_empty_semantic(_mock_semantic, _mock_has):
    """When both explicit and auto-detect vectors return empty, return [] with state_manager=None."""
    result = search_decisions(
        state_manager=None,
        jurisdiction="city-tiburon",
        query="housing",
        vector_backend=EmptyVectorBackend(),
        storage_backend=None,
    )
    assert result == []


def test_search_decisions_none_state_manager_no_vector_backend():
    """search_decisions(state_manager=None, vector_backend=None) for unknown jurisdiction returns []."""
    result = search_decisions(
        state_manager=None,
        jurisdiction="city-nonexistent",
        query="housing",
        vector_backend=None,
        storage_backend=None,
    )
    assert result == []
