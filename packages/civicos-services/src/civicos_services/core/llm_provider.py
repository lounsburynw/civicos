"""
LLM Provider Factory for Civic Conversational OS.

This module provides factory functions to instantiate the appropriate
LLM provider based on environment configuration.

Environment Variables:
    LLM_PROVIDER: Default provider ('openai', 'anthropic', 'groq', 'google', 'ollama')
    ENABLE_ANTHROPIC: Must be 'true' to use Anthropic provider
    OPENAI_API_KEY: OpenAI API key
    ANTHROPIC_API_KEY: Anthropic API key
    GROQ_API_KEY: Groq API key
    GOOGLE_API_KEY: Google API key (Gemini)
    OLLAMA_BASE_URL: Ollama server URL (default: http://localhost:11434/v1)
    OLLAMA_MODEL: Ollama model name (default: llama3.1)

Usage:
    from llm_provider import get_provider

    # Get default provider (OpenAI)
    provider = get_provider()

    # Get specific provider
    provider = get_provider('google')  # Cheapest, 2M context
    provider = get_provider('groq')  # Fast Llama 3.1
    provider = get_provider('anthropic')  # High-quality Claude
    provider = get_provider('ollama')  # Local, private

    # Get optimal provider for task (smart routing)
    provider = get_provider_for_task('navigation')  # Uses Gemini (cheapest)
    provider = get_provider_for_task('research')  # Uses Gemini Pro (2M context)
"""

import os
from typing import Optional, List
from ..providers.base import LLMProvider
from ..providers.openai_provider import OpenAIProvider
from ..providers.openai_compatible_provider import (
    GroqProvider,
    OllamaProvider,
    PerplexityProvider,
    OpenRouterProvider
)
from ..providers.google_provider import GoogleProvider
from ..providers.groq_responses_provider import GroqResponsesProvider
# Lazy import for optional providers that require extra dependencies
# from ..providers.anthropic_provider import AnthropicProvider  # Only import when needed

# Import model registry for model-first architecture (Session 74)
from .model_registry import (
    MODEL_REGISTRY,
    get_model_info,
    find_models_by_capabilities,
    is_model_available as is_model_available_in_registry,
    get_cheapest_model,
    resolve_model_name,
)


def get_provider(provider_name: Optional[str] = None) -> LLMProvider:
    """
    Get LLM provider instance based on configuration.

    Args:
        provider_name: Override provider (default: from LLM_PROVIDER env var)

    Returns:
        LLMProvider instance

    Raises:
        ValueError: If provider unknown or not enabled

    Examples:
        >>> provider = get_provider()  # Uses default (OpenAI)
        >>> provider = get_provider('openai')  # Explicit OpenAI
        >>> provider = get_provider('google')  # Gemini (requires GOOGLE_API_KEY)
        >>> provider = get_provider('groq')  # Fast Llama 3.1 (requires GROQ_API_KEY)
        >>> provider = get_provider('anthropic')  # Requires ENABLE_ANTHROPIC=true
        >>> provider = get_provider('ollama')  # Local models
    """
    # Get provider name from parameter or environment
    provider_name = provider_name or os.getenv('LLM_PROVIDER', 'openai')
    provider_name = provider_name.lower()

    # Route to appropriate provider
    if provider_name == 'openai':
        return OpenAIProvider()

    elif provider_name == 'google' or provider_name == 'gemini':
        return GoogleProvider()

    elif provider_name == 'groq':
        return GroqProvider()

    elif provider_name == 'groq-responses':
        # Groq Responses API for structured outputs (beta)
        return GroqResponsesProvider()

    elif provider_name == 'ollama':
        return OllamaProvider()

    elif provider_name == 'perplexity':
        return PerplexityProvider()

    elif provider_name == 'openrouter':
        return OpenRouterProvider()

    elif provider_name == 'anthropic':
        # Check feature flag
        if os.getenv('ENABLE_ANTHROPIC', 'false').lower() != 'true':
            raise ValueError(
                "Anthropic provider not enabled. "
                "Set ENABLE_ANTHROPIC=true to enable."
            )
        # Lazy import to avoid requiring anthropic SDK if not used
        from providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider()

    else:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Supported: openai, google, groq, ollama, perplexity, openrouter, anthropic"
        )


# =============================================================================
# Provider Routing Configuration
# =============================================================================
# Centralized configuration for task-based provider routing.
# Each task type specifies:
#   - priority: Ordered list of providers to try (supports "provider:model" notation)
#   - reason: Why this routing strategy is chosen
#   - fallback_model: Safe fallback if all providers unavailable

TASK_PROVIDER_CONFIG = {
    'navigation': {
        'priority': ['openai', 'google', 'groq-responses'],
        'reason': 'OpenAI has reliable structured outputs for complex schemas (Session 73)',
        'fallback_model': 'openai'
    },
    'explain': {
        'priority': ['openai', 'google', 'groq-responses'],
        'reason': 'Same as navigation - structured output reliability',
        'fallback_model': 'openai'
    },
    'research': {
        'priority': ['google', 'anthropic', 'openai'],
        'reason': 'Gemini Flash is 85% cheaper for simple formatting tasks',
        'fallback_model': 'openai'
    },
    'long_document': {
        'priority': ['google:gemini-1.5-pro-latest', 'anthropic', 'openai'],
        'reason': 'Need 2M context window for large agenda PDFs',
        'fallback_model': 'openai'
    },
    'draft': {
        'priority': ['openai'],
        'reason': 'Proven quality for civic comment drafting',
        'fallback_model': 'openai'
    },
    'conversational': {
        'priority': ['anthropic', 'openai', 'google'],
        'reason': 'Quality priority for function calling (Session 71)',
        'fallback_model': 'openai'
    },
    'realtime_research': {
        'priority': ['perplexity', 'google', 'openai'],
        'reason': 'Perplexity has built-in web search and citations',
        'fallback_model': 'openai'
    }
}


# =============================================================================
# Model-First Architecture (Session 74)
# =============================================================================
# New configuration that thinks in terms of models, not providers.
# Provider becomes implementation detail - model is primary abstraction.
#
# Each task type specifies:
#   - model_priority: Ordered list of models to try (or use strategy)
#   - strategy: 'explicit' (use priority list) or 'cost_optimized' (auto-select cheapest)
#   - required_capabilities: What the model must support
#   - reason: Why this configuration is chosen
#   - Additional constraints: max_cost, min_context, speed

TASK_MODEL_CONFIG = {
    'navigation': {
        'strategy': 'explicit',
        'model_priority': [
            'gemini-2.0-flash-exp',  # $0.075/1M (most navigation is simple, reliable)
            'deepseek/deepseek-chat',  # Via OpenRouter ($0.27/1M, reliable function calling)
            'meta-llama/llama-3.3-70b-instruct',  # Via OpenRouter ($0.59/1M)
            'gpt-4o-mini',  # $0.60/1M (proven fallback)
            'openai/gpt-4o-mini',  # Via OpenRouter ($0.15/1M, alternative)
            'google/gemini-2.0-flash-exp:free'  # Via OpenRouter (free but rate-limited, last resort)
        ],
        'required_capabilities': ['structured_outputs', 'function_calling'],
        'reason': 'Cost-optimized: Cheap reliable models first, free tier last resort (rate-limited)',
        'fallback_model': 'gpt-4o-mini'
    },
    'explain': {
        'strategy': 'explicit',
        'model_priority': [
            'gpt-4o-mini',  # $0.60/1M (better at following context instructions than gemini flash)
            'deepseek/deepseek-chat',  # Via OpenRouter ($0.27/1M, reliable)
            'gemini-2.0-flash-exp',  # $0.075/1M (fallback)
            'meta-llama/llama-3.3-70b-instruct',  # Via OpenRouter ($0.59/1M)
            'google/gemini-2.0-flash-exp:free'  # Via OpenRouter (free but rate-limited, last resort)
        ],
        'required_capabilities': ['structured_outputs', 'function_calling'],
        'reason': 'Focus mode needs better instruction following for context awareness - gpt-4o-mini more reliable',
        'fallback_model': 'gpt-4o-mini'
    },
    'research': {
        'strategy': 'cost_optimized',
        'required_capabilities': ['structured_outputs'],
        'max_cost_per_1m': 0.10,
        'reason': 'Simple formatting - optimize for cost (includes free OpenRouter Gemini tier)',
        'fallback_model': 'gpt-4o-mini'
    },
    'long_document': {
        'strategy': 'explicit',
        'model_priority': [
            'gemini-2.0-flash-exp',  # $0.075/1M (1M context, fastest, works!)
            'gpt-4o',  # $2.50/1M (128K context, reliable fallback)
            'anthropic/claude-3.5-sonnet',  # Via OpenRouter ($3.00/1M)
            'claude-sonnet-4',  # $3.00/1M
            'google/gemini-2.0-flash-exp:free'  # Free tier (1M context, rate-limited)
        ],
        'required_capabilities': ['long_context'],
        'min_context_window': 500000,
        'reason': 'Need 500K+ context for agenda PDFs, Gemini 2.0 Flash best value',
        'fallback_model': 'gpt-4o'
    },
    'draft': {
        'strategy': 'explicit',
        'model_priority': [
            'anthropic/claude-3-5-haiku',  # Via OpenRouter (best civic writing quality, $0.80/1M)
            'gpt-4o-mini',  # Fallback (proven, $0.60/1M)
            'meta-llama/llama-3.3-70b-instruct'  # Via OpenRouter (cost-effective backup)
        ],
        'required_capabilities': ['structured_outputs'],
        'reason': 'Claude Haiku excels at persuasive civic writing (+$0.20/1M worth it for quality)',
        'fallback_model': 'gpt-4o-mini'
    },
    'conversational': {
        'strategy': 'explicit',
        'model_priority': [
            'gemini-2.0-flash-exp',  # $0.075/1M (most conversations are simple, reliable)
            'deepseek/deepseek-chat',  # Via OpenRouter ($0.27/1M, fast & affordable)
            'meta-llama/llama-3.3-70b-instruct',  # Via OpenRouter ($0.59/1M, good quality)
            'anthropic/claude-3.5-sonnet',  # Via OpenRouter ($3.00/1M, reserve for complex multi-turn)
            'claude-sonnet-4',  # $3.00/1M (complex reasoning)
            'moonshotai/kimi-k2-thinking',  # Via OpenRouter ($2.00/1M, advanced reasoning)
            'deepseek/deepseek-r1',  # Via OpenRouter ($0.55/1M, advanced reasoning)
            'gpt-4o',
            'google/gemini-2.0-flash-exp:free'  # Via OpenRouter (free but rate-limited, last resort)
        ],
        'required_capabilities': ['function_calling'],
        'reason': 'Cost-optimized: Cheap reliable models first, free tier last resort (rate-limited). TODO: implement complexity detection for expensive models',
        'fallback_model': 'gpt-4o-mini'
    },
    'query_planning': {
        'strategy': 'explicit',
        'model_priority': [
            'deepseek/deepseek-chat',  # Via OpenRouter ($0.27/1M - cheap + reliable)
            'openai/gpt-4o-mini',  # Via OpenRouter ($0.15/1M - cheaper than direct)
            'gemini-2.0-flash-exp',  # $0.075/1M (reliable)
            'llama-3.1-8b-instant',
            'gpt-4o-mini',
            'google/gemini-2.0-flash-exp:free'  # Via OpenRouter (free but rate-limited, last resort)
        ],
        'required_capabilities': ['structured_outputs'],
        'reason': 'DeepSeek Chat via OpenRouter (cheap + reliable), free tier as last resort',
        'fallback_model': 'gpt-4o-mini'
    },
    'realtime_research': {
        'strategy': 'explicit',
        'model_priority': [
            'sonar',  # $0.20/1M (5x cheaper than sonar-pro, sufficient for most research)
            'sonar-pro',  # $1.00/1M (reserve for complex research requiring higher quality)
            'gemini-2.0-flash-exp',  # $0.075/1M (fallback without web search)
            'gpt-4o-mini',
            'google/gemini-2.0-flash-exp:free'  # Free but rate-limited, last resort
        ],
        'required_capabilities': ['web_search', 'citations'],
        'reason': 'Perplexity has built-in web search and citations, cheaper sonar sufficient for most queries',
        'fallback_model': 'gpt-4o-mini'
    },
    'agenda_parsing': {
        'strategy': 'explicit',
        'model_priority': [
            'gemini-1.5-pro-latest',  # $1.25/1M (2M context for full meeting packets)
            'anthropic/claude-3.5-sonnet',  # Via OpenRouter ($3.00/1M, excellent reasoning)
            'claude-sonnet-4',
            'google/gemini-2.0-flash-exp:free'  # Free tier via OpenRouter (1M context, rate-limited)
        ],
        'required_capabilities': ['long_context'],
        'min_context_window': 500000,
        'reason': 'Agenda PDFs need 500K+ context, Gemini Pro best value for long documents',
        'fallback_model': 'gemini-1.5-pro-latest'
    },
    'legislative_validation': {
        'strategy': 'explicit',
        'model_priority': [
            'gpt-4o-mini',  # $0.60/1M (structured validation, factual accuracy)
            'openai/gpt-4o-mini',  # Via OpenRouter ($0.15/1M, cheaper)
            'meta-llama/llama-3.3-70b-instruct'  # Via OpenRouter ($0.59/1M)
        ],
        'required_capabilities': ['structured_outputs', 'json_mode'],
        'reason': 'Legislative reference validation requires factual accuracy and structured outputs (99.99% accuracy critical)',
        'fallback_model': 'gpt-4o-mini'
    },
    'personalization': {
        'strategy': 'cost_optimized',
        'required_capabilities': ['structured_outputs'],
        'max_cost_per_1m': 0.10,
        'reason': 'Simple behavioral inference and profile management, optimize for cost (free OpenRouter tier ideal)',
        'fallback_model': 'gpt-4o-mini'
    }
}


def get_model(model_name: str) -> LLMProvider:
    """
    Get provider instance for specific model (model-first architecture).

    Args:
        model_name: Model name from MODEL_REGISTRY (e.g., 'gpt-4o-mini')

    Returns:
        LLMProvider instance configured with specified model

    Raises:
        ValueError: If model not found in registry

    Examples:
        >>> provider = get_model('gpt-4o-mini')
        >>> provider.default_model
        'gpt-4o-mini'

        >>> provider = get_model('gemini-1.5-pro-latest')
        >>> provider.name
        'google'
    """
    info = get_model_info(model_name)
    if not info:
        raise ValueError(
            f"Unknown model: {model_name}. "
            f"Check MODEL_REGISTRY in model_registry.py for available models."
        )

    provider_name = info['provider']
    # Resolve alias to get canonical model name for the provider (Session 530)
    canonical_model = resolve_model_name(model_name)
    return get_provider_with_model(provider_name, canonical_model)


def get_model_for_task(task_type: str, use_model_config: bool = True) -> LLMProvider:
    """
    Get optimal model for specific task type using model-first architecture.

    This is the NEW model-first routing function (Session 74). It thinks in terms
    of models, not providers. Provider becomes implementation detail.

    Args:
        task_type: Task type identifier (see TASK_MODEL_CONFIG for options)
        use_model_config: If True, use TASK_MODEL_CONFIG; if False, use legacy TASK_PROVIDER_CONFIG

    Returns:
        LLMProvider instance configured with optimal model for task

    Strategies:
        - 'explicit': Try models in priority order until one is available
        - 'cost_optimized': Automatically select cheapest model meeting requirements

    Examples:
        >>> # Navigation uses gpt-4o-mini (most reliable structured outputs)
        >>> provider = get_model_for_task('navigation')
        >>> provider.default_model
        'gpt-4o-mini'

        >>> # Research uses cheapest model with structured outputs (<$0.10/1M)
        >>> provider = get_model_for_task('research')
        >>> provider.default_model  # Could be llama-3.1-8b-instant or gemini-2.0-flash-exp
        'gemini-2.0-flash-exp'

        >>> # Long documents use high-context model (500K+ tokens)
        >>> provider = get_model_for_task('long_document')
        >>> provider.default_model
        'gemini-1.5-pro-latest'  # 2M context window
    """
    # Fall back to legacy provider-based routing if requested
    if not use_model_config:
        return get_provider_for_task(task_type)

    # Get configuration for this task type
    config = TASK_MODEL_CONFIG.get(task_type)
    if not config:
        # Unknown task type - use safe default
        return get_model('gpt-4o-mini')

    strategy = config.get('strategy', 'explicit')

    # Strategy 1: Cost-optimized - auto-select cheapest model meeting requirements
    if strategy == 'cost_optimized':
        required_caps = config.get('required_capabilities', [])
        max_cost = config.get('max_cost_per_1m')
        min_context = config.get('min_context_window')

        # Find all models meeting requirements
        candidates = find_models_by_capabilities(
            required=required_caps,
            max_cost=max_cost,
            min_context=min_context
        )

        # Try candidates in cost order (cheapest first)
        for model_name in candidates:
            if is_model_available_in_registry(model_name):
                return get_model(model_name)

    # Strategy 2: Explicit priority - try models in specified order
    else:
        model_priority = config.get('model_priority', [])
        for model_name in model_priority:
            if is_model_available_in_registry(model_name):
                return get_model(model_name)

    # All models unavailable - use fallback
    fallback = config.get('fallback_model', 'gpt-4o-mini')
    return get_model(fallback)


def is_provider_available(provider_name: str) -> bool:
    """
    Check if provider is configured and available.

    Args:
        provider_name: Provider identifier (e.g., 'openai', 'google', 'anthropic')

    Returns:
        True if provider has required API keys/configuration

    Examples:
        >>> is_provider_available('openai')  # True if OPENAI_API_KEY set
        >>> is_provider_available('anthropic')  # True if ENABLE_ANTHROPIC=true
    """
    availability_map = {
        'openai': lambda: bool(os.getenv('OPENAI_API_KEY')),
        'google': lambda: bool(os.getenv('GOOGLE_API_KEY')),
        'groq': lambda: bool(os.getenv('GROQ_API_KEY')),
        'groq-responses': lambda: bool(os.getenv('GROQ_API_KEY')),
        'anthropic': lambda: os.getenv('ENABLE_ANTHROPIC', 'false').lower() == 'true',
        'perplexity': lambda: bool(os.getenv('PERPLEXITY_API_KEY')),
        'openrouter': lambda: bool(os.getenv('OPENROUTER_API_KEY')),
        'ollama': lambda: True  # Always available (local)
    }

    checker = availability_map.get(provider_name)
    return checker() if checker else False


def get_provider_with_model(provider_name: str, model: str) -> LLMProvider:
    """
    Get provider instance with specific model override.

    Args:
        provider_name: Provider identifier
        model: Model name to use

    Returns:
        LLMProvider instance configured with specified model

    Examples:
        >>> provider = get_provider_with_model('google', 'gemini-1.5-pro-latest')
        >>> provider.default_model
        'gemini-1.5-pro-latest'
    """
    if provider_name == 'openai':
        provider = OpenAIProvider()
        provider._default_model = model  # Set private attribute
        return provider
    elif provider_name == 'google' or provider_name == 'gemini':
        return GoogleProvider(model=model)
    elif provider_name == 'groq':
        return GroqProvider(model=model)
    elif provider_name == 'groq-responses':
        provider = GroqResponsesProvider()
        provider.default_model = model
        return provider
    elif provider_name == 'ollama':
        return OllamaProvider(model=model)
    elif provider_name == 'perplexity':
        return PerplexityProvider(model=model)
    elif provider_name == 'openrouter':
        return OpenRouterProvider(model=model)
    else:
        # For providers that don't support model parameter in constructor,
        # just return the default provider
        return get_provider(provider_name)


def get_provider_for_task(task_type: str) -> LLMProvider:
    """
    DEPRECATED: Use get_model_for_task() instead (Session 74).

    Get optimal provider for specific task type using centralized configuration.

    This function implements smart routing based on task complexity, cost, and
    context needs. Provider priorities are defined in TASK_PROVIDER_CONFIG.

    DEPRECATION NOTICE:
        This function uses the old provider-first approach. Please migrate to
        get_model_for_task() which uses model-first architecture where provider
        is an implementation detail. This function is kept for backward compatibility
        during the migration period.

        Old way (provider-first):
            provider = get_provider_for_task('navigation')  # Which provider? Unclear model

        New way (model-first):
            provider = get_model_for_task('navigation')  # Returns gpt-4o-mini explicitly

    Args:
        task_type: Task type identifier
            - 'navigation': Chat navigation (simple queries)
            - 'explain': Event explanation (medium complexity)
            - 'research': Research queries with cache lookups
            - 'realtime_research': Real-time news/web search
            - 'draft': Comment drafting (quality-critical)
            - 'conversational': Conversational queries with function calling
            - 'long_document': Analyze large PDFs/documents (needs 2M context)

    Returns:
        LLMProvider instance

    Cost comparison (per 1M tokens):
        - Gemini Flash 2.0: $0.075 (85% cheaper than OpenAI)
        - Groq Llama 3.1: $0.05-0.27 (90% cheaper than OpenAI)
        - OpenAI gpt-4o-mini: $0.60
        - Claude Sonnet 4: $3.00 (high quality, citations)
        - Gemini Pro 1.5: $1.25 (2M context window)

    Examples:
        >>> provider = get_provider_for_task('navigation')
        >>> provider.name
        'openai'  # Assuming OPENAI_API_KEY is set
    """
    # Get configuration for this task type
    config = TASK_PROVIDER_CONFIG.get(task_type)
    if not config:
        # Unknown task type - use safe default
        return get_provider('openai')

    # Try each provider in priority order
    for provider_spec in config['priority']:
        # Handle provider:model notation (e.g., "google:gemini-1.5-pro-latest")
        if ':' in provider_spec:
            provider_name, model = provider_spec.split(':', 1)
        else:
            provider_name, model = provider_spec, None

        # Check if provider is available
        if is_provider_available(provider_name):
            if model:
                return get_provider_with_model(provider_name, model)
            else:
                return get_provider(provider_name)

    # All providers unavailable - use fallback
    return get_provider(config['fallback_model'])


def list_available_providers() -> list[str]:
    """
    List all available and enabled providers.

    Returns:
        List of provider names that can be used

    Examples:
        >>> providers = list_available_providers()
        >>> print(providers)  # ['openai', 'google', 'groq'] or more
    """
    available = ['openai']  # Always available

    # Google/Gemini is available if API key is set
    if os.getenv('GOOGLE_API_KEY'):
        available.append('google')

    # Groq is available if API key is set
    if os.getenv('GROQ_API_KEY'):
        available.append('groq')

    # Ollama is available (assumes local server running)
    # Note: We always list it as available since it's opt-in
    available.append('ollama')

    # Perplexity is available if API key is set
    if os.getenv('PERPLEXITY_API_KEY'):
        available.append('perplexity')

    # OpenRouter is available if API key is set
    if os.getenv('OPENROUTER_API_KEY'):
        available.append('openrouter')

    # Anthropic requires explicit feature flag
    if os.getenv('ENABLE_ANTHROPIC', 'false').lower() == 'true':
        available.append('anthropic')

    return available
