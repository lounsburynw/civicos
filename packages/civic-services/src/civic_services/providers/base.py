"""
Base classes for LLM provider abstraction.

This module defines the abstract interface that all LLM providers must implement,
ensuring consistent behavior across different AI providers (OpenAI, Anthropic, etc.).
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Iterator
from dataclasses import dataclass


@dataclass
class ToolCall:
    """
    Normalized tool call structure across providers.

    Attributes:
        id: Unique identifier for this tool call
        name: Name of the tool/function being called
        arguments: Dictionary of arguments to pass to the tool
    """
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class CompletionResponse:
    """
    Normalized completion response across providers.

    Attributes:
        content: Text content of the response
        tool_calls: List of tool calls requested by the model
        finish_reason: Why the model stopped generating (e.g., 'stop', 'tool_calls')
        usage: Token usage statistics
        raw_response: Provider-specific response object (for debugging)
        provider_name: Name of provider that generated this response (optional)
        model: Model name that generated this response (optional)
    """
    content: str
    tool_calls: List[ToolCall]
    finish_reason: str
    usage: Dict[str, int]
    raw_response: Any
    provider_name: Optional[str] = None
    model: Optional[str] = None


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.

    All LLM providers (OpenAI, Anthropic, etc.) must implement this interface
    to ensure consistent behavior across the application.
    """

    def __init__(self, api_key: str):
        """
        Initialize provider with API key.

        Args:
            api_key: API key for the provider
        """
        self.api_key = api_key

    @abstractmethod
    def complete(self,
                 messages: List[Dict[str, str]],
                 tools: Optional[List[Dict]] = None,
                 **kwargs) -> CompletionResponse:
        """
        Send completion request to provider.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions (provider-agnostic format)
            **kwargs: Provider-specific parameters

        Returns:
            CompletionResponse with normalized structure
        """
        pass

    @abstractmethod
    def stream_complete(self,
                       messages: List[Dict[str, str]],
                       tools: Optional[List[Dict]] = None,
                       **kwargs) -> Iterator[str]:
        """
        Stream completion from provider.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions (provider-agnostic format)
            **kwargs: Provider-specific parameters

        Yields:
            str: Content chunks as they arrive
        """
        pass

    @abstractmethod
    def parse_tool_calls(self, response: Any) -> List[ToolCall]:
        """
        Extract tool calls from provider-specific response format.

        Args:
            response: Provider-specific response object

        Returns:
            List of normalized ToolCall objects
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'openai', 'anthropic')"""
        pass

    @property
    @abstractmethod
    def default_model(self) -> str:
        """Default model for this provider"""
        pass

    def chat(self,
             messages: List[Dict[str, str]],
             tools: Optional[List[Dict]] = None,
             response_format: Optional[str] = None,
             **kwargs) -> str:
        """
        Convenience method for simple chat completions that returns just the text content.

        This is a wrapper around complete() for cases where you just want the text response
        without dealing with the full CompletionResponse structure.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            response_format: Optional response format hint (e.g., "json_object")
            **kwargs: Provider-specific parameters

        Returns:
            str: Just the text content of the response

        Example:
            >>> provider = get_provider()
            >>> response = provider.chat([{"role": "user", "content": "Hello!"}])
            >>> print(response)  # Just the string response
        """
        # Handle response_format parameter (common in OpenAI API)
        if response_format:
            # Convert string shorthand to proper format
            if isinstance(response_format, str) and response_format == "json_object":
                kwargs['response_format'] = {"type": "json_object"}
            else:
                kwargs['response_format'] = response_format

        completion = self.complete(messages=messages, tools=tools, **kwargs)
        return completion.content
