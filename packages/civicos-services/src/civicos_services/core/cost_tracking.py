"""
Cost Tracking for Civic Platform.

Session 507: Implements automatic cost logging for LLM calls to the
operating_costs table for unified cost monitoring.

Session 508: Extended with Modal compute cost logging for serverless
function execution tracking.

Key Features:
- Calculates LLM costs from token usage using model_registry pricing
- Calculates Modal costs from memory, time, and GPU usage
- Logs to PostgreSQL operating_costs table (no-op in SQLite dev mode)
- Thread-safe singleton storage connection
- Graceful degradation - never fails the caller on cost tracking errors
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from .model_registry import calculate_cost, get_model_info

logger = logging.getLogger(__name__)

# Module-level storage instance (lazy initialization)
_cost_storage = None
_storage_initialized = False


def _get_storage():
    """
    Get or create storage backend for cost logging.

    Lazily initializes connection to avoid startup overhead.
    Returns None if PostgreSQL is not configured (local dev mode).
    """
    global _cost_storage, _storage_initialized

    if _storage_initialized:
        return _cost_storage

    _storage_initialized = True

    # Only initialize if DATABASE_URL is set (PostgreSQL mode)
    if not os.getenv('DATABASE_URL'):
        logger.debug("Cost tracking disabled - DATABASE_URL not set (local dev mode)")
        return None

    try:
        from dotenv import load_dotenv
        load_dotenv()

        from civicos import CivicOS
        # Use a default jurisdiction for storage access
        c = CivicOS("city-san-rafael")
        _cost_storage = c._storage
        logger.info("Cost tracking enabled - connected to PostgreSQL")
        return _cost_storage
    except Exception as e:
        logger.warning(f"Cost tracking initialization failed: {e}")
        return None


def log_llm_cost(
    model: str,
    usage: Dict[str, int],
    provider: Optional[str] = None,
    task: Optional[str] = None,
    jurisdiction_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """
    Log LLM call cost to operating_costs table.

    Calculates cost from token usage and stores with full metadata.
    Never raises exceptions - logs errors and returns None on failure.

    Args:
        model: Model name from MODEL_REGISTRY (e.g., 'gpt-4o-mini')
        usage: Token usage dict with 'total_tokens' or 'prompt_tokens'/'completion_tokens'
        provider: Provider name override (auto-detected from model if not provided)
        task: Task type for categorization (e.g., 'navigation', 'query_planning')
        jurisdiction_id: Optional jurisdiction for city-specific cost attribution
        metadata: Additional metadata to store with cost record

    Returns:
        Cost record ID if successfully logged, None otherwise

    Example:
        >>> response = provider.complete(messages=[...])
        >>> log_llm_cost(
        ...     model='gpt-4o-mini',
        ...     usage=response.usage,
        ...     task='mode_detection',
        ...     jurisdiction_id='city-san-rafael'
        ... )
    """
    if not usage:
        return None

    storage = _get_storage()
    if not storage:
        # SQLite mode or initialization failed - silently skip
        return None

    try:
        # Calculate cost using model registry pricing
        cost_usd = calculate_cost(model, usage)

        if cost_usd == 0.0:
            # Zero cost (free tier or unknown model) - still log for tracking
            logger.debug(f"Zero cost LLM call: {model}, {usage.get('total_tokens', 0)} tokens")

        # Auto-detect provider from model registry if not provided
        if not provider:
            model_info = get_model_info(model)
            provider = model_info.get('provider', 'unknown') if model_info else 'unknown'

        # Build metadata
        cost_metadata = {
            'model': model,
            'prompt_tokens': usage.get('prompt_tokens', 0),
            'completion_tokens': usage.get('completion_tokens', 0),
            'total_tokens': usage.get('total_tokens', 0),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        if task:
            cost_metadata['task'] = task

        if metadata:
            cost_metadata.update(metadata)

        # Store cost record
        cost_id = storage.store_operating_cost(
            service=provider,
            category='llm',
            amount_usd=cost_usd,
            jurisdiction_id=jurisdiction_id,
            metadata=cost_metadata,
        )

        logger.debug(
            f"LLM cost logged: ${cost_usd:.6f} for {model} "
            f"({usage.get('total_tokens', 0)} tokens, id={cost_id})"
        )

        return cost_id

    except Exception as e:
        # Never fail the caller on cost tracking errors
        logger.warning(f"Failed to log LLM cost: {e}")
        return None


def log_completion_cost(
    response,
    model: str,
    task: Optional[str] = None,
    jurisdiction_id: Optional[str] = None,
) -> Optional[int]:
    """
    Convenience function to log cost from a CompletionResponse object.

    Args:
        response: CompletionResponse from provider.complete()
        model: Model name used for the call
        task: Task type for categorization
        jurisdiction_id: Optional jurisdiction for cost attribution

    Returns:
        Cost record ID if successfully logged, None otherwise

    Example:
        >>> response = provider.complete(messages=[...])
        >>> log_completion_cost(response, provider.default_model, task='navigation')
    """
    if not response or not hasattr(response, 'usage') or not response.usage:
        return None

    # Extract provider name from response if available
    provider = getattr(response, 'provider_name', None)

    return log_llm_cost(
        model=model,
        usage=response.usage,
        provider=provider,
        task=task,
        jurisdiction_id=jurisdiction_id,
    )


# Modal compute pricing (per GB-second)
# Source: https://modal.com/pricing (as of Jan 2026)
MODAL_CPU_RATE = 0.000463  # $/GB-second for CPU/memory
MODAL_GPU_RATES = {
    'T4': 0.000164,    # ~$0.59/hour
    'A10G': 0.000306,  # ~$1.10/hour
    'A100': 0.001389,  # ~$5.00/hour (40GB)
    'H100': 0.003472,  # ~$12.50/hour
}


def log_modal_cost(
    function_name: str,
    elapsed_seconds: float,
    memory_gb: float,
    gpu: Optional[str] = None,
    jurisdiction_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """
    Log Modal compute cost to operating_costs table.

    Calculates cost from memory, time, and optional GPU usage.
    Never raises exceptions - logs errors and returns None on failure.

    Args:
        function_name: Name of the Modal function (e.g., 'index_corpus')
        elapsed_seconds: Execution time in seconds
        memory_gb: Memory allocation in GB
        gpu: GPU type if used (e.g., 'T4', 'A10G')
        jurisdiction_id: Optional jurisdiction for city-specific cost attribution
        metadata: Additional metadata to store with cost record

    Returns:
        Cost record ID if successfully logged, None otherwise

    Example:
        >>> start = time.time()
        >>> # ... do work ...
        >>> elapsed = time.time() - start
        >>> log_modal_cost(
        ...     function_name='index_corpus',
        ...     elapsed_seconds=elapsed,
        ...     memory_gb=64,
        ...     gpu='T4',
        ...     jurisdiction_id='city-san-rafael',
        ...     metadata={'corpus': 'chunks', 'documents': 5000}
        ... )
    """
    storage = _get_storage()
    if not storage:
        # SQLite mode or initialization failed - silently skip
        return None

    try:
        # Calculate CPU/memory cost
        gb_seconds = memory_gb * elapsed_seconds
        cpu_cost = gb_seconds * MODAL_CPU_RATE

        # Calculate GPU cost if applicable
        gpu_cost = 0.0
        if gpu and gpu in MODAL_GPU_RATES:
            gpu_cost = elapsed_seconds * MODAL_GPU_RATES[gpu]

        total_cost = cpu_cost + gpu_cost

        # Build metadata
        cost_metadata = {
            'function': function_name,
            'elapsed_seconds': round(elapsed_seconds, 2),
            'memory_gb': memory_gb,
            'gb_seconds': round(gb_seconds, 2),
            'cpu_cost_usd': round(cpu_cost, 6),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        if gpu:
            cost_metadata['gpu'] = gpu
            cost_metadata['gpu_cost_usd'] = round(gpu_cost, 6)

        if metadata:
            cost_metadata.update(metadata)

        # Store cost record
        cost_id = storage.store_operating_cost(
            service='modal',
            category='compute',
            amount_usd=total_cost,
            jurisdiction_id=jurisdiction_id,
            metadata=cost_metadata,
        )

        logger.debug(
            f"Modal cost logged: ${total_cost:.4f} for {function_name} "
            f"({elapsed_seconds:.0f}s, {memory_gb}GB, gpu={gpu}, id={cost_id})"
        )

        return cost_id

    except Exception as e:
        # Never fail the caller on cost tracking errors
        logger.warning(f"Failed to log Modal cost: {e}")
        return None
