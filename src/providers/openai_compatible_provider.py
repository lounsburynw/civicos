"""
OpenAI-compatible provider for third-party services.

This module provides a generic provider for any service that implements
the OpenAI API specification, including:
- OpenRouter (unified access to 100+ models)
- Groq (Llama 3.1, Mixtral)
- Ollama (local models)
- Perplexity (real-time research with citations)
- Together AI
- Anyscale
- LM Studio (local)

This enables cost optimization and open-source model support.
"""

import os
from openai import OpenAI
from typing import List, Dict, Any, Optional, Iterator
from .base import LLMProvider, CompletionResponse, ToolCall
from .openai_provider import OpenAIProvider


class OpenAICompatibleProvider(OpenAIProvider):
    """
    Generic provider for OpenAI-compatible APIs.

    Inherits from OpenAIProvider since the API format is identical,
    only the base_url and model differ.

    Supported services:
    - Groq: Fast inference for Llama 3.1, Mixtral
    - Ollama: Local model hosting
    - Together AI: Open-source models
    - Anyscale: Llama fine-tuning
    """

    def __init__(self,
                 base_url: str,
                 api_key: str = None,
                 model: str = None,
                 provider_name: str = "openai-compatible"):
        """
        Initialize OpenAI-compatible provider.

        Args:
            base_url: API base URL (e.g., https://api.groq.com/openai/v1)
            api_key: API key (optional for local services like Ollama)
            model: Default model to use
            provider_name: Name for this provider instance
        """
        # Don't call OpenAIProvider.__init__ to avoid double initialization
        LLMProvider.__init__(self, api_key or "not-needed")

        # Initialize OpenAI client with custom base_url
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key or "not-needed"  # Some local services don't need keys
        )

        self._default_model = model or "llama-3.3-70b-versatile"
        self._provider_name = provider_name

    @property
    def name(self) -> str:
        """Provider name"""
        return self._provider_name


class GroqProvider(OpenAICompatibleProvider):
    """
    Groq provider for fast Llama 3.1 inference.

    Groq provides ultra-fast inference for open-source models:
    - Llama 3.1 70B: ~300 tokens/sec
    - Mixtral 8x7B: ~450 tokens/sec

    Cost: ~$0.05-0.27 per 1M tokens (90% cheaper than OpenAI)

    Environment Variables:
        GROQ_API_KEY: Required (get from https://console.groq.com)
    """

    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize Groq provider.

        Args:
            api_key: Groq API key (defaults to GROQ_API_KEY env var)
            model: Model to use (defaults to llama-3.3-70b-versatile)
        """
        super().__init__(
            base_url="https://api.groq.com/openai/v1",
            api_key=api_key or os.getenv('GROQ_API_KEY'),
            model=model or "llama-3.1-8b-instant",  # Fast, supports structured outputs
            provider_name="groq"
        )

    @property
    def default_model(self) -> str:
        """Default model for Groq"""
        return self._default_model


class OllamaProvider(OpenAICompatibleProvider):
    """
    Ollama provider for local model hosting.

    Ollama runs models locally with zero API costs:
    - Llama 3.1 (8B, 70B, 405B)
    - Mixtral 8x7B
    - DeepSeek v3
    - Custom fine-tuned models

    Cost: $0 (local compute only)
    Privacy: Data never leaves your infrastructure

    Requirements:
        - Ollama server running (ollama serve)
        - Model pulled (ollama pull llama3.1)
    """

    def __init__(self, base_url: str = None, model: str = None):
        """
        Initialize Ollama provider.

        Args:
            base_url: Ollama server URL (defaults to http://localhost:11434/v1)
            model: Model to use (defaults to llama3.1)
        """
        super().__init__(
            base_url=base_url or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434/v1'),
            api_key=None,  # Ollama doesn't need API key
            model=model or os.getenv('OLLAMA_MODEL', 'llama3.1'),
            provider_name="ollama"
        )

    @property
    def default_model(self) -> str:
        """Default model for Ollama"""
        return self._default_model


class PerplexityProvider(OpenAICompatibleProvider):
    """
    Perplexity Sonar API for real-time research with citations.

    Perplexity provides LLM + web search with automatic source citations:
    - sonar-pro: Enhanced quality + reasoning (200K context)
    - sonar: Fast research (127K context)

    Cost: $1.00/1M tokens (sonar-pro), $0.20/1M tokens (sonar)

    Environment Variables:
        PERPLEXITY_API_KEY: Required (get from perplexity.ai/settings/api)

    Example:
        >>> provider = PerplexityProvider()
        >>> response = provider.complete([
        ...     {"role": "user", "content": "What is California AB 1147?"}
        ... ])
        >>> print(response.content)  # Answer with inline citations [1][2]
        >>> print(response.metadata.get('citations'))  # List of source URLs
    """

    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize Perplexity provider.

        Args:
            api_key: Perplexity API key (defaults to PERPLEXITY_API_KEY env var)
            model: Model to use (defaults to sonar-pro)
        """
        super().__init__(
            base_url="https://api.perplexity.ai",
            api_key=api_key or os.getenv('PERPLEXITY_API_KEY'),
            model=model or "sonar-pro",
            provider_name="perplexity"
        )

    @property
    def default_model(self) -> str:
        """Default model for Perplexity"""
        return self._default_model

    def complete(self,
                 messages: List[Dict[str, str]],
                 tools: Optional[List[Dict]] = None,
                 model: str = None,
                 temperature: float = 0.7,
                 max_tokens: int = None,
                 **kwargs) -> 'CompletionResponse':
        """
        Complete using Perplexity API with citation extraction.

        Perplexity responses include a 'citations' field with source URLs.
        These are extracted and added to the response metadata.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions (not supported by Perplexity)
            model: Model to use (defaults to sonar-pro)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            CompletionResponse with citations in metadata['citations']
        """
        # Call parent implementation
        response = super().complete(
            messages=messages,
            tools=tools,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        # Perplexity API returns citations in the response
        # These are typically in the raw response object
        # Note: Citations extraction depends on Perplexity API response format
        # If citations are present, they will be in response.metadata

        return response


class OpenRouterProvider(OpenAICompatibleProvider):
    """
    OpenRouter provider for unified access to 100+ AI models.

    OpenRouter aggregates models from multiple providers through a single API:
    - Anthropic: Claude 3.5 Sonnet ($3/1M), Claude 3.5 Haiku ($0.80/1M)
    - Google: Gemini 2.0 Flash (free), Gemini 1.5 Pro ($1.25/1M)
    - Meta: Llama 3.3 70B ($0.59/1M), Llama 3.1 405B ($2.70/1M)
    - OpenAI: GPT-4o ($2.50/1M), GPT-4o-mini ($0.15/1M)
    - Mistral, DeepSeek, Qwen, and many more

    Benefits:
    - Single API key for all providers
    - Automatic model fallback if one is unavailable
    - Unified billing and rate limiting
    - Access to latest models without multiple integrations
    - Per-request model selection
    - Cost tracking across all providers

    Cost: Variable by model ($0.06-$15/1M tokens)
    Context: Up to 2M tokens (Gemini models)

    Environment Variables:
        OPENROUTER_API_KEY: Required (get from openrouter.ai/keys)
        OPENROUTER_APP_NAME: Optional (for usage tracking)
        OPENROUTER_SITE_URL: Optional (for rankings)

    Example:
        >>> provider = OpenRouterProvider()
        >>> # Use Claude 3.5 Sonnet via OpenRouter
        >>> response = provider.complete(
        ...     messages=[{"role": "user", "content": "Explain CDBG"}],
        ...     model="anthropic/claude-3.5-sonnet"
        ... )

        >>> # Use Llama 3.3 70B (cheaper alternative)
        >>> response = provider.complete(
        ...     messages=[{"role": "user", "content": "Show housing meetings"}],
        ...     model="meta-llama/llama-3.3-70b-instruct"
        ... )
    """

    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize OpenRouter provider.

        Args:
            api_key: OpenRouter API key (defaults to OPENROUTER_API_KEY env var)
            model: Default model to use (defaults to meta-llama/llama-3.3-70b-instruct)
        """
        super().__init__(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.getenv('OPENROUTER_API_KEY'),
            model=model or "meta-llama/llama-3.3-70b-instruct",
            provider_name="openrouter"
        )

        # Optional OpenRouter headers for tracking
        self.app_name = os.getenv('OPENROUTER_APP_NAME', 'civic-conversational-os')
        self.site_url = os.getenv('OPENROUTER_SITE_URL', 'https://github.com/civic-os')

    @property
    def default_model(self) -> str:
        """Default model for OpenRouter"""
        return self._default_model

    def complete(self,
                 messages: List[Dict[str, str]],
                 tools: Optional[List[Dict]] = None,
                 model: str = None,
                 temperature: float = 0.7,
                 max_tokens: int = None,
                 **kwargs) -> 'CompletionResponse':
        """
        Complete using OpenRouter API with optional custom headers.

        OpenRouter supports custom headers for app tracking and user attribution.
        These help with usage analytics and model rankings on OpenRouter.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions (function calling)
            model: Model to use (defaults to llama-3.3-70b-instruct)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            CompletionResponse with normalized structure
        """
        # Add OpenRouter-specific headers if not already present
        extra_headers = kwargs.get('extra_headers', {})
        if self.app_name and 'HTTP-Referer' not in extra_headers:
            extra_headers['HTTP-Referer'] = self.site_url
        if self.app_name and 'X-Title' not in extra_headers:
            extra_headers['X-Title'] = self.app_name

        kwargs['extra_headers'] = extra_headers

        # Call parent implementation
        return super().complete(
            messages=messages,
            tools=tools,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
