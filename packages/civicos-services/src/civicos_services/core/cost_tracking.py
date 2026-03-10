"""
Cost Tracking for Civic Platform.

Unified cost logging for all external services to the operating_costs table.

Instrumented services:
- OpenAI / Google (LLM): log_llm_cost(), log_completion_cost()
- Modal (compute): log_modal_cost()
- AssemblyAI (transcription): log_assemblyai_cost()
- Cloudflare R2 (blob storage): log_r2_cost()
- Supabase (database): log_supabase_cost()

Key Features:
- Calculates LLM costs from token usage using model_registry pricing
- Calculates Modal costs from memory, time, and GPU usage
- Tracks AssemblyAI transcription costs from audio duration
- Tracks R2 storage operations (Class A writes, Class B reads)
- Records Supabase fixed monthly costs
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
_blob_hook_registered = False


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
        _cost_storage = c.storage
        logger.info("Cost tracking enabled - connected to PostgreSQL")

        # Register blob cost hook so R2Backend can log costs without
        # importing from the services layer (preserves layer boundaries)
        _register_blob_cost_hook()

        return _cost_storage
    except Exception as e:
        logger.warning(f"Cost tracking initialization failed: {e}")
        return None


def _register_blob_cost_hook() -> None:
    """Wire up R2Backend cost tracking via the blob module's callback hook."""
    global _blob_hook_registered
    if _blob_hook_registered:
        return
    _blob_hook_registered = True
    try:
        from civicos.storage.blob import set_blob_cost_hook
        set_blob_cost_hook(log_r2_cost)
        logger.debug("Blob cost hook registered")
    except Exception as e:
        logger.debug(f"Blob cost hook registration skipped: {e}")


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


# AssemblyAI pricing
# Source: https://www.assemblyai.com/pricing (as of Mar 2026)
ASSEMBLYAI_RATE_PER_HOUR = 0.21      # Universal-3 Pro
ASSEMBLYAI_DIARIZATION_PER_HOUR = 0.02  # Speaker diarization add-on


def log_assemblyai_cost(
    audio_minutes: float,
    transcripts_processed: int = 1,
    with_diarization: bool = True,
    jurisdiction_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """
    Log AssemblyAI transcription cost to operating_costs table.

    Args:
        audio_minutes: Total audio duration in minutes
        transcripts_processed: Number of transcripts in this batch
        with_diarization: Whether speaker diarization was used
        jurisdiction_id: Optional jurisdiction for cost attribution
        metadata: Additional metadata

    Returns:
        Cost record ID if successfully logged, None otherwise
    """
    storage = _get_storage()
    if not storage:
        return None

    try:
        audio_hours = audio_minutes / 60.0
        base_cost = audio_hours * ASSEMBLYAI_RATE_PER_HOUR
        diarization_cost = audio_hours * ASSEMBLYAI_DIARIZATION_PER_HOUR if with_diarization else 0.0
        total_cost = base_cost + diarization_cost

        cost_metadata = {
            'audio_minutes': round(audio_minutes, 2),
            'audio_hours': round(audio_hours, 2),
            'transcripts_processed': transcripts_processed,
            'with_diarization': with_diarization,
            'base_cost_usd': round(base_cost, 6),
            'diarization_cost_usd': round(diarization_cost, 6),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        if metadata:
            cost_metadata.update(metadata)

        cost_id = storage.store_operating_cost(
            service='assemblyai',
            category='api',
            amount_usd=total_cost,
            jurisdiction_id=jurisdiction_id,
            metadata=cost_metadata,
        )

        logger.debug(
            f"AssemblyAI cost logged: ${total_cost:.4f} for {audio_minutes:.1f}min "
            f"({transcripts_processed} transcripts, id={cost_id})"
        )

        return cost_id

    except Exception as e:
        logger.warning(f"Failed to log AssemblyAI cost: {e}")
        return None


# Cloudflare R2 pricing
# Source: https://developers.cloudflare.com/r2/pricing/ (as of Mar 2026)
R2_CLASS_A_PER_OP = 4.50 / 1_000_000   # writes: $4.50/million
R2_CLASS_B_PER_OP = 0.36 / 1_000_000   # reads: $0.36/million
R2_STORAGE_PER_GB_MONTH = 0.015


def log_r2_cost(
    operation: str,
    bytes_transferred: int = 0,
    jurisdiction_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """
    Log Cloudflare R2 operation cost to operating_costs table.

    Args:
        operation: 'upload' (Class A) or 'download' (Class B)
        bytes_transferred: Size in bytes
        jurisdiction_id: Optional jurisdiction for cost attribution
        metadata: Additional metadata (key, content_type, etc.)

    Returns:
        Cost record ID if successfully logged, None otherwise
    """
    storage = _get_storage()
    if not storage:
        return None

    try:
        if operation == 'upload':
            op_cost = R2_CLASS_A_PER_OP
        elif operation == 'download':
            op_cost = R2_CLASS_B_PER_OP
        else:
            op_cost = 0.0

        cost_metadata = {
            'operation': operation,
            'bytes_transferred': bytes_transferred,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        if metadata:
            cost_metadata.update(metadata)

        cost_id = storage.store_operating_cost(
            service='cloudflare_r2',
            category='storage',
            amount_usd=op_cost,
            jurisdiction_id=jurisdiction_id,
            metadata=cost_metadata,
        )

        logger.debug(
            f"R2 cost logged: ${op_cost:.8f} for {operation} "
            f"({bytes_transferred} bytes, id={cost_id})"
        )

        return cost_id

    except Exception as e:
        logger.warning(f"Failed to log R2 cost: {e}")
        return None


# Supabase pricing
# Source: https://supabase.com/pricing (as of Mar 2026)
SUPABASE_PRO_BASE = 25.00  # $/month per project


def log_supabase_cost(
    project: str = 'main',
    amount_usd: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[int]:
    """
    Log Supabase monthly cost to operating_costs table.

    Called once per billing period (monthly) for each Supabase project.

    Args:
        project: 'main' (civic data) or 'relay' (coordination data)
        amount_usd: Actual billed amount. Defaults to Pro base ($25).
        metadata: Additional metadata (compute add-ons, storage overage, etc.)

    Returns:
        Cost record ID if successfully logged, None otherwise
    """
    storage = _get_storage()
    if not storage:
        return None

    try:
        cost = amount_usd if amount_usd is not None else SUPABASE_PRO_BASE

        cost_metadata = {
            'project': project,
            'plan': 'pro',
            'base_cost_usd': SUPABASE_PRO_BASE,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

        if metadata:
            cost_metadata.update(metadata)

        service_name = f'supabase_{project}' if project != 'main' else 'supabase'

        cost_id = storage.store_operating_cost(
            service=service_name,
            category='storage',
            amount_usd=cost,
            metadata=cost_metadata,
        )

        logger.debug(
            f"Supabase cost logged: ${cost:.2f} for {project} project (id={cost_id})"
        )

        return cost_id

    except Exception as e:
        logger.warning(f"Failed to log Supabase cost: {e}")
        return None


def reconcile_costs(period_days: int = 30) -> Dict[str, Any]:
    """
    Reconcile operating_costs table against cost_registry.yaml estimates.

    Pulls actual logged costs and compares with expected ranges from
    the cost registry. Identifies services with no logged costs.

    Args:
        period_days: Number of days to look back

    Returns:
        Dict with reconciliation results per service
    """
    storage = _get_storage()
    if not storage:
        return {'error': 'No storage backend available'}

    try:
        from datetime import timedelta
        since = (datetime.now(timezone.utc) - timedelta(days=period_days)).isoformat()

        summary = storage.get_operating_cost_summary(since=since)

        # Expected services from cost_registry.yaml
        expected_services = {
            'modal': {'category': 'compute', 'expected_monthly': '$0-8 (free credits)'},
            'openai': {'category': 'llm', 'expected_monthly': '<$1'},
            'google': {'category': 'llm', 'expected_monthly': '<$1'},
            'assemblyai': {'category': 'api', 'expected_monthly': '$0-10'},
            'supabase': {'category': 'storage', 'expected_monthly': '$25-50'},
            'supabase_relay': {'category': 'storage', 'expected_monthly': '$25'},
            'cloudflare_r2': {'category': 'storage', 'expected_monthly': '$0-5'},
        }

        by_service = summary.get('by_service', {})
        result = {
            'period_days': period_days,
            'since': since,
            'total_logged_usd': summary.get('total_usd', 0),
            'services': {},
        }

        for service, info in expected_services.items():
            actual = by_service.get(service, 0)
            result['services'][service] = {
                'actual_usd': round(actual, 4),
                'expected_monthly': info['expected_monthly'],
                'category': info['category'],
                'instrumented': actual > 0,
            }

        # Flag uninstrumented services
        result['uninstrumented'] = [
            s for s, d in result['services'].items() if not d['instrumented']
        ]

        return result

    except Exception as e:
        logger.warning(f"Cost reconciliation failed: {e}")
        return {'error': str(e)}
