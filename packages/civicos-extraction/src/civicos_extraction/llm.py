"""
LLM provider helper for civicos_extraction.

Centralizes the cross-package import from civicos_services so that
extraction clients don't scatter imports across the layer boundary.

This is the ONLY file in civicos_extraction that imports from
civicos_services.core.llm_provider. All extraction clients should
import from here instead.

Long-term: the LLM abstraction should move to civicos_config or a
shared package. This module is a stepping stone.
"""

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_llm_provider(task: str = "navigation") -> Any:
    """Get an LLM provider for extraction tasks.

    Args:
        task: Task type (default "navigation" — cheapest model)

    Returns:
        Provider with .complete(messages, ...) method

    Raises:
        RuntimeError: If no LLM API key is configured
    """
    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise RuntimeError(
            "LLM API key required (OPENAI_API_KEY or GOOGLE_API_KEY). "
            "Set one in .env and retry."
        )

    try:
        from civicos_services.core.llm_provider import get_model_for_task
        return get_model_for_task(task)
    except ImportError:
        raise RuntimeError(
            "civicos_services package required for LLM features. "
            "Ensure it's installed in the environment."
        )


def llm_complete(prompt: str, task: str = "navigation", temperature: float = 0.1) -> str:
    """Convenience: send a prompt to the LLM and return the text response.

    Args:
        prompt: User message
        task: Task type for model selection
        temperature: Sampling temperature

    Returns:
        Response text (stripped)
    """
    provider = get_llm_provider(task)
    result = provider.complete(
        [{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return result.content.strip()
