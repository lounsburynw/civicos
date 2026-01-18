"""
Modal compute cost logging for Civic Platform.

Session 508: Lightweight cost logging for Modal serverless functions.
This module is available in the Modal image (unlike civic-services).

Usage in Modal functions:
    from civicos.cost import log_modal_cost

    @app.function(memory=65536, gpu="T4", ...)
    def my_function():
        start = time.time()
        # ... do work ...
        elapsed = time.time() - start

        log_modal_cost(
            function_name="my_function",
            elapsed_seconds=elapsed,
            memory_gb=64,
            gpu="T4",
            jurisdiction_id="city-san-rafael",
        )
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

# Modal compute pricing (per second)
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
    storage_backend=None,
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
        storage_backend: Optional storage backend (auto-detected from DATABASE_URL if not provided)

    Returns:
        Cost record ID if successfully logged, None otherwise
    """
    # Get storage backend if not provided
    if storage_backend is None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            logger.debug("Cost tracking disabled - DATABASE_URL not set")
            return None

        try:
            from civicos.storage import get_storage_backend
            storage_backend = get_storage_backend(database_url)
        except Exception as e:
            logger.warning(f"Failed to get storage backend: {e}")
            return None

    # Check if storage backend supports cost logging
    if not hasattr(storage_backend, 'store_operating_cost'):
        logger.debug("Storage backend does not support cost logging")
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
        cost_id = storage_backend.store_operating_cost(
            service='modal',
            category='compute',
            amount_usd=total_cost,
            jurisdiction_id=jurisdiction_id,
            metadata=cost_metadata,
        )

        logger.info(
            f"Modal cost logged: ${total_cost:.4f} for {function_name} "
            f"({elapsed_seconds:.0f}s, {memory_gb}GB, gpu={gpu}, id={cost_id})"
        )

        return cost_id

    except Exception as e:
        # Never fail the caller on cost tracking errors
        logger.warning(f"Failed to log Modal cost: {e}")
        return None
