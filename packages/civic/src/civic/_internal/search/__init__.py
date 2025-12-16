"""
Unified search module for cross-corpus semantic search.

This module provides the UnifiedSearch class that queries multiple vector
corpora (decisions, chunks, transcripts, issues, municipal_code) and
returns unified results.
"""

from civic._internal.search.unified import UnifiedSearch

__all__ = ["UnifiedSearch"]
