"""
LLM Provider abstraction layer for Civic Conversational OS.

This package provides a provider-agnostic interface for interacting with
various LLM providers (OpenAI, Anthropic, Google, Groq, Ollama, etc.).

Providers with optional dependencies (openai, anthropic) use lazy imports
so this package can be imported without those packages installed.
"""

from .base import LLMProvider, CompletionResponse, ToolCall
from .google_provider import GoogleProvider

# Lazy imports for providers requiring optional packages:
# - OpenAIProvider, GroqProvider, OllamaProvider, OpenAICompatibleProvider → require `openai`
# - AnthropicProvider → requires `anthropic`
# Import them directly when needed:
#   from civicos_services.providers.openai_provider import OpenAIProvider

__all__ = [
    'LLMProvider',
    'CompletionResponse',
    'ToolCall',
    'GoogleProvider',
]
