"""
OpenAI provider implementation for LLM abstraction layer.

This module wraps existing OpenAI GPT-4 logic from civic_chat_router.py
to ensure 100% backward compatibility with the provider interface.
"""

import os
import json
from openai import OpenAI
from typing import List, Dict, Any, Optional, Iterator
from .base import LLMProvider, CompletionResponse, ToolCall


class OpenAIProvider(LLMProvider):
    """
    OpenAI GPT-4 provider implementation.

    Wraps existing OpenAI chat completions API with provider-agnostic interface.
    Supports function calling (tools) and streaming.
    """

    def __init__(self, api_key: str = None):
        """
        Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
        """
        super().__init__(api_key or os.getenv('OPENAI_API_KEY'))
        self.client = OpenAI(api_key=self.api_key)
        self._default_model = "gpt-4o-mini"

    @property
    def name(self) -> str:
        """Provider name"""
        return "openai"

    @property
    def default_model(self) -> str:
        """Default model for this provider"""
        return self._default_model

    def complete(self,
                 messages: List[Dict[str, str]],
                 tools: Optional[List[Dict]] = None,
                 model: str = None,
                 temperature: float = 0.7,
                 max_tokens: int = None,
                 **kwargs) -> CompletionResponse:
        """
        Complete using OpenAI API.

        NOTE: This wraps existing logic from civic_chat_router.py
        to ensure 100% backward compatibility.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions (provider-agnostic format)
            model: Model to use (defaults to gpt-4o-mini)
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional OpenAI-specific parameters

        Returns:
            CompletionResponse with normalized structure
        """
        # Build request parameters
        request_params = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature
        }

        # Add max_tokens if specified
        if max_tokens:
            request_params["max_tokens"] = max_tokens

        # Add tools if provided (function calling)
        if tools:
            request_params["tools"] = self._convert_tools_to_openai_format(tools)

        # Additional OpenAI-specific params
        if kwargs:
            request_params.update(kwargs)

        # Make API call
        response = self.client.chat.completions.create(**request_params)

        # Parse response
        message = response.choices[0].message

        return CompletionResponse(
            content=message.content or "",
            tool_calls=self.parse_tool_calls(response),
            finish_reason=response.choices[0].finish_reason,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            },
            raw_response=response
        )

    def stream_complete(self,
                       messages: List[Dict[str, str]],
                       tools: Optional[List[Dict]] = None,
                       model: str = None,
                       temperature: float = 0.7,
                       **kwargs) -> Iterator[str]:
        """
        Stream completion from OpenAI.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            model: Model to use (defaults to gpt-4o-mini)
            temperature: Sampling temperature (0-2)
            **kwargs: Additional OpenAI-specific parameters

        Yields:
            str: Content chunks as they arrive
        """
        request_params = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }

        if tools:
            request_params["tools"] = self._convert_tools_to_openai_format(tools)

        if kwargs:
            request_params.update(kwargs)

        response = self.client.chat.completions.create(**request_params)

        for chunk in response:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def parse_tool_calls(self, response: Any) -> List[ToolCall]:
        """
        Extract tool calls from OpenAI response.

        Args:
            response: OpenAI ChatCompletion response object

        Returns:
            List of normalized ToolCall objects
        """
        message = response.choices[0].message

        if not hasattr(message, 'tool_calls') or not message.tool_calls:
            return []

        return [
            ToolCall(
                id=tc.id,
                name=tc.function.name,
                arguments=json.loads(tc.function.arguments)
            )
            for tc in message.tool_calls
        ]

    def _convert_tools_to_openai_format(self, tools: List[Dict]) -> List[Dict]:
        """
        Convert provider-agnostic tool format to OpenAI function calling format.

        Provider-agnostic format:
        {
            "name": "search_events",
            "description": "Search civic events",
            "parameters": {...}  # JSON Schema
        }

        OpenAI format:
        {
            "type": "function",
            "function": {
                "name": "search_events",
                "description": "Search civic events",
                "parameters": {...}
            }
        }

        Args:
            tools: List of provider-agnostic tool definitions

        Returns:
            List of OpenAI-formatted tool definitions
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["parameters"]
                }
            }
            for tool in tools
        ]
