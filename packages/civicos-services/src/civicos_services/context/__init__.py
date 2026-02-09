"""
Context Assembly API — surface-agnostic context layer for CivicOS.

Given any civic item, returns a rich context bundle that any consumer
(Open WebUI, browser extension, MCP, widget) can pass to an LLM.
"""

from .assembler import (
    assemble_context,
    ItemNotFoundError,
    RelayUnavailableError,
    SectionTimeoutError,
)
from .models import (
    ContextBundle,
    ContextDepth,
    ContextItem,
    ContextMetadata,
    ContextSections,
    ItemType,
)

__all__ = [
    "assemble_context",
    "ItemNotFoundError",
    "RelayUnavailableError",
    "SectionTimeoutError",
    "ContextBundle",
    "ContextDepth",
    "ContextItem",
    "ContextMetadata",
    "ContextSections",
    "ItemType",
]
