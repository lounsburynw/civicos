"""
LLM Provider abstraction layer for Civic Conversational OS.

This package provides a provider-agnostic interface for interacting with
various LLM providers (OpenAI, Anthropic, Google, Groq, Ollama, etc.).
"""

from .base import LLMProvider, CompletionResponse, ToolCall
from .openai_provider import OpenAIProvider
# Note: AnthropicProvider uses lazy import to avoid requiring anthropic SDK if not used
from .google_provider import GoogleProvider
from .openai_compatible_provider import GroqProvider, OllamaProvider, OpenAICompatibleProvider

__all__ = [
    'LLMProvider',
    'CompletionResponse',
    'ToolCall',
    'OpenAIProvider',
    'GoogleProvider',
    'GroqProvider',
    'OllamaProvider',
    'OpenAICompatibleProvider'
]
