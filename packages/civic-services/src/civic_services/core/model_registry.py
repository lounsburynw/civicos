"""
Model Registry for centralized model metadata and capabilities.

Session 74: Implements model-first architecture where provider is
implementation detail and model is primary abstraction.

Key Design Principles:
- Provider is implementation detail - users think in terms of models
- Capabilities drive selection - explicit requirements, not implicit assumptions
- Cost-aware by default - optimize for foundation budget (<$7/month)
- Future-proof - easy to add new models/providers
"""

import os
from typing import Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load .env file to ensure API keys are available
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

# Model Registry - Single source of truth for all LLM models
MODEL_REGISTRY: Dict[str, dict] = {
    'gpt-4o-mini': {
        'provider': 'openai',
        'capabilities': ['structured_outputs', 'function_calling', 'json_mode'],
        'cost_per_1m_tokens': 0.60,  # Combined input/output cost estimate
        'context_window': 128000,
        'speed': 'fast',
        'description': 'Reliable structured outputs, good for navigation and function calling'
    },
    'gpt-4o': {
        'provider': 'openai',
        'capabilities': ['structured_outputs', 'function_calling', 'json_mode', 'vision'],
        'cost_per_1m_tokens': 5.00,
        'context_window': 128000,
        'speed': 'medium',
        'description': 'Premium model with best structured output reliability'
    },
    'gemini-2.0-flash-exp': {
        'provider': 'google',
        'capabilities': ['structured_outputs', 'function_calling'],
        'cost_per_1m_tokens': 0.075,
        'context_window': 1000000,
        'speed': 'very_fast',
        'description': 'Fast and cheap, good for simple tasks but less reliable structured outputs'
    },
    'gemini-2.5-pro': {
        'provider': 'google',
        'capabilities': ['long_context', 'structured_outputs', 'function_calling', 'vision'],
        'cost_per_1m_tokens': 1.25,
        'context_window': 2000000,
        'speed': 'fast',
        'description': 'Latest Gemini Pro with 2M context, improved reasoning and quality'
    },
    'gemini-1.5-pro-latest': {
        'provider': 'google',
        'capabilities': ['long_context', 'structured_outputs', 'function_calling'],
        'cost_per_1m_tokens': 1.25,
        'context_window': 2000000,
        'speed': 'medium',
        'description': 'Best for long documents with 2M context window'
    },
    'claude-sonnet-4': {
        'provider': 'anthropic',
        'capabilities': ['function_calling', 'citations', 'thinking', 'long_context'],
        'cost_per_1m_tokens': 3.00,
        'context_window': 200000,
        'speed': 'medium',
        'description': 'High quality analysis with citations and extended thinking'
    },
    'llama-3.1-8b-instant': {
        'provider': 'groq',
        'capabilities': ['function_calling', 'structured_outputs'],
        'cost_per_1m_tokens': 0.05,
        'context_window': 128000,
        'speed': 'ultra_fast',
        'description': 'Cheapest option, ultra-fast inference via Groq'
    },
    'llama-3.3-70b-versatile': {
        'provider': 'groq',
        'capabilities': ['function_calling', 'structured_outputs', 'json_mode'],
        'cost_per_1m_tokens': 0.59,
        'context_window': 128000,
        'speed': 'very_fast',
        'description': 'Groq Responses API with structured outputs, faster than OpenAI'
    },
    'sonar-pro': {
        'provider': 'perplexity',
        'capabilities': ['web_search', 'citations', 'structured_outputs'],
        'cost_per_1m_tokens': 1.00,
        'context_window': 200000,
        'speed': 'medium',
        'description': 'Perplexity search with citations, best for research queries'
    },
    'sonar': {
        'provider': 'perplexity',
        'capabilities': ['web_search', 'citations', 'structured_outputs'],
        'cost_per_1m_tokens': 0.20,
        'context_window': 127000,
        'speed': 'fast',
        'description': 'Cheaper Perplexity search, good for simple research'
    },
    # OpenRouter models - unified access to multiple providers
    'anthropic/claude-3.5-sonnet': {
        'provider': 'openrouter',
        'capabilities': ['function_calling', 'citations', 'thinking', 'long_context', 'structured_outputs'],
        'cost_per_1m_tokens': 3.00,
        'context_window': 200000,
        'speed': 'medium',
        'description': 'Claude 3.5 Sonnet via OpenRouter - high quality analysis with citations'
    },
    'anthropic/claude-3-5-haiku': {
        'provider': 'openrouter',
        'capabilities': ['function_calling', 'structured_outputs', 'json_mode'],
        'cost_per_1m_tokens': 0.80,
        'context_window': 200000,
        'speed': 'fast',
        'description': 'Claude 3.5 Haiku via OpenRouter - fast and affordable, good balance'
    },
    'meta-llama/llama-3.3-70b-instruct': {
        'provider': 'openrouter',
        'capabilities': ['function_calling', 'structured_outputs', 'json_mode'],
        'cost_per_1m_tokens': 0.59,
        'context_window': 128000,
        'speed': 'fast',
        'description': 'Llama 3.3 70B via OpenRouter - excellent quality at low cost'
    },
    'google/gemini-2.0-flash-exp:free': {
        'provider': 'openrouter',
        'capabilities': ['structured_outputs', 'function_calling', 'long_context'],
        'cost_per_1m_tokens': 0.00,
        'context_window': 1000000,
        'speed': 'very_fast',
        'description': 'Gemini 2.0 Flash free tier via OpenRouter - zero cost for development'
    },
    'openai/gpt-4o-mini': {
        'provider': 'openrouter',
        'capabilities': ['structured_outputs', 'function_calling', 'json_mode'],
        'cost_per_1m_tokens': 0.15,
        'context_window': 128000,
        'speed': 'fast',
        'description': 'GPT-4o-mini via OpenRouter - reliable structured outputs (cheaper than direct)'
    },
    'deepseek/deepseek-r1': {
        'provider': 'openrouter',
        'capabilities': ['function_calling', 'structured_outputs', 'thinking', 'long_context'],
        'cost_per_1m_tokens': 0.55,
        'context_window': 128000,
        'speed': 'medium',
        'description': 'DeepSeek R1 via OpenRouter - advanced reasoning with extended thinking'
    },
    'deepseek/deepseek-chat': {
        'provider': 'openrouter',
        'capabilities': ['function_calling', 'structured_outputs', 'json_mode'],
        'cost_per_1m_tokens': 0.27,
        'context_window': 64000,
        'speed': 'fast',
        'description': 'DeepSeek Chat via OpenRouter - fast and affordable chat model'
    },
    'moonshotai/kimi-k2-thinking': {
        'provider': 'openrouter',
        'capabilities': ['function_calling', 'structured_outputs', 'thinking', 'long_context'],
        'cost_per_1m_tokens': 2.00,
        'context_window': 128000,
        'speed': 'medium',
        'description': 'Moonshot Kimi K2 via OpenRouter - advanced thinking and reasoning model'
    }
}


def get_model_info(model_name: str) -> Optional[dict]:
    """
    Get metadata for specific model.

    Args:
        model_name: Name of the model (e.g., 'gpt-4o-mini')

    Returns:
        Model metadata dictionary or None if not found

    Example:
        >>> info = get_model_info('gpt-4o-mini')
        >>> print(info['provider'])  # 'openai'
        >>> print(info['cost_per_1m_tokens'])  # 0.60
    """
    return MODEL_REGISTRY.get(model_name)


def find_models_by_capabilities(
    required: List[str],
    max_cost: Optional[float] = None,
    min_context: Optional[int] = None,
    speed: Optional[str] = None
) -> List[str]:
    """
    Find all models meeting specified requirements.

    Args:
        required: List of required capabilities (e.g., ['structured_outputs', 'function_calling'])
        max_cost: Maximum cost per 1M tokens (optional)
        min_context: Minimum context window size (optional)
        speed: Required speed tier: 'ultra_fast', 'very_fast', 'fast', 'medium' (optional)

    Returns:
        List of model names sorted by cost (cheapest first)

    Example:
        >>> # Find cheapest models with structured outputs under $0.10/1M
        >>> models = find_models_by_capabilities(
        ...     required=['structured_outputs'],
        ...     max_cost=0.10
        ... )
        >>> print(models)  # ['llama-3.1-8b-instant', 'gemini-2.0-flash-exp']

        >>> # Find models with 500K+ context window
        >>> models = find_models_by_capabilities(
        ...     required=['long_context'],
        ...     min_context=500000
        ... )
        >>> print(models)  # ['gemini-1.5-pro-latest', 'claude-sonnet-4']
    """
    speed_order = {'ultra_fast': 4, 'very_fast': 3, 'fast': 2, 'medium': 1}

    candidates = []
    for model_name, info in MODEL_REGISTRY.items():
        # Check required capabilities
        if not all(cap in info['capabilities'] for cap in required):
            continue

        # Check cost constraint
        if max_cost is not None and info['cost_per_1m_tokens'] > max_cost:
            continue

        # Check context window constraint
        if min_context is not None and info['context_window'] < min_context:
            continue

        # Check speed constraint
        if speed is not None:
            required_speed_level = speed_order.get(speed, 0)
            model_speed_level = speed_order.get(info['speed'], 0)
            if model_speed_level < required_speed_level:
                continue

        candidates.append(model_name)

    # Sort by cost (cheapest first)
    candidates.sort(key=lambda m: MODEL_REGISTRY[m]['cost_per_1m_tokens'])
    return candidates


def is_model_available(model_name: str) -> bool:
    """
    Check if model's provider is configured via environment variables.

    Args:
        model_name: Name of the model to check

    Returns:
        True if provider has required API keys configured

    Example:
        >>> is_model_available('gpt-4o-mini')  # True if OPENAI_API_KEY set
        >>> is_model_available('claude-sonnet-4')  # True if ANTHROPIC_API_KEY set
    """
    info = get_model_info(model_name)
    if not info:
        return False

    provider = info['provider']

    # Check if provider API key is configured
    if provider == 'openai':
        return bool(os.getenv('OPENAI_API_KEY'))
    elif provider == 'google':
        return bool(os.getenv('GOOGLE_API_KEY'))
    elif provider == 'anthropic':
        return bool(os.getenv('ANTHROPIC_API_KEY'))
    elif provider == 'groq':
        return bool(os.getenv('GROQ_API_KEY'))
    elif provider == 'perplexity':
        return bool(os.getenv('PERPLEXITY_API_KEY'))
    elif provider == 'openrouter':
        return bool(os.getenv('OPENROUTER_API_KEY'))

    return False


def get_available_models() -> List[str]:
    """
    Get list of all models whose providers are currently configured.

    Returns:
        List of available model names

    Example:
        >>> models = get_available_models()
        >>> print(models)  # ['gpt-4o-mini', 'gpt-4o', 'gemini-2.0-flash-exp', ...]
    """
    return [model for model in MODEL_REGISTRY.keys() if is_model_available(model)]


def get_cheapest_model(
    required_capabilities: List[str],
    max_cost: Optional[float] = None
) -> Optional[str]:
    """
    Get the cheapest available model meeting requirements.

    Args:
        required_capabilities: List of required capabilities
        max_cost: Maximum acceptable cost per 1M tokens (optional)

    Returns:
        Model name or None if no models meet requirements

    Example:
        >>> # Get cheapest model with structured outputs
        >>> model = get_cheapest_model(['structured_outputs'])
        >>> print(model)  # 'llama-3.1-8b-instant' ($0.05/1M)
    """
    candidates = find_models_by_capabilities(required_capabilities, max_cost=max_cost)

    # Filter to only available models
    available = [m for m in candidates if is_model_available(m)]

    return available[0] if available else None


def get_models_by_provider(provider: str) -> List[str]:
    """
    Get all models for a specific provider.

    Args:
        provider: Provider name ('openai', 'google', 'anthropic', 'groq')

    Returns:
        List of model names for that provider

    Example:
        >>> openai_models = get_models_by_provider('openai')
        >>> print(openai_models)  # ['gpt-4o-mini', 'gpt-4o']
    """
    return [
        model_name
        for model_name, info in MODEL_REGISTRY.items()
        if info['provider'] == provider
    ]


def calculate_cost(model: str, usage: Dict[str, int]) -> float:
    """
    Calculate cost in USD for an LLM call based on model and token usage.

    Uses the MODEL_REGISTRY pricing data (cost_per_1m_tokens) to calculate
    actual costs from token usage returned by providers.

    Args:
        model: Model name from MODEL_REGISTRY (e.g., 'gemini-2.0-flash-exp')
        usage: Token usage dict with 'total_tokens' or 'prompt_tokens'/'completion_tokens'

    Returns:
        Cost in USD (float). Returns 0.0 if model not found or usage is empty.

    Example:
        >>> usage = {'prompt_tokens': 1000, 'completion_tokens': 500, 'total_tokens': 1500}
        >>> cost = calculate_cost('gemini-2.0-flash-exp', usage)
        >>> print(f"${cost:.6f}")  # $0.000113 (1500 tokens at $0.075/1M)

        >>> # Works with just total_tokens too
        >>> cost = calculate_cost('gpt-4o-mini', {'total_tokens': 10000})
        >>> print(f"${cost:.4f}")  # $0.0060 (10K tokens at $0.60/1M)
    """
    if not usage:
        return 0.0

    info = get_model_info(model)
    if not info:
        # Model not in registry - return 0 rather than failing
        return 0.0

    cost_per_1m = info.get('cost_per_1m_tokens', 0.0)
    if cost_per_1m == 0.0:
        return 0.0

    # Get total tokens - prefer explicit total, otherwise sum prompt+completion
    total_tokens = usage.get('total_tokens', 0)
    if total_tokens == 0:
        total_tokens = usage.get('prompt_tokens', 0) + usage.get('completion_tokens', 0)

    if total_tokens == 0:
        return 0.0

    # Calculate cost: (tokens / 1,000,000) * cost_per_1m
    return (total_tokens / 1_000_000) * cost_per_1m


if __name__ == '__main__':
    # Quick tests
    print("=== Model Registry Demo ===\n")

    print("1. All registered models:")
    for model_name in MODEL_REGISTRY.keys():
        info = get_model_info(model_name)
        available = "✓" if is_model_available(model_name) else "✗"
        print(f"  {available} {model_name}: ${info['cost_per_1m_tokens']}/1M ({info['provider']})")

    print("\n2. Models with structured outputs under $0.10/1M:")
    cheap_models = find_models_by_capabilities(['structured_outputs'], max_cost=0.10)
    for model in cheap_models:
        info = get_model_info(model)
        print(f"  - {model}: ${info['cost_per_1m_tokens']}/1M")

    print("\n3. Models with 500K+ context window:")
    long_context = find_models_by_capabilities(['long_context'], min_context=500000)
    for model in long_context:
        info = get_model_info(model)
        print(f"  - {model}: {info['context_window']:,} tokens")

    print("\n4. Currently available models:")
    available = get_available_models()
    print(f"  {len(available)} models available: {', '.join(available)}")

    print("\n5. Cheapest available model with structured outputs:")
    cheapest = get_cheapest_model(['structured_outputs'])
    if cheapest:
        info = get_model_info(cheapest)
        print(f"  {cheapest}: ${info['cost_per_1m_tokens']}/1M")
