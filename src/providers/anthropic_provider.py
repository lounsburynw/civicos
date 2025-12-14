"""
Anthropic Claude provider implementation for LLM abstraction layer.

This module implements Claude Sonnet 4 support for research mode
with tool use capabilities.
"""

import os
import json
from anthropic import Anthropic
from typing import List, Dict, Any, Optional, Iterator
from .base import LLMProvider, CompletionResponse, ToolCall


class AnthropicProvider(LLMProvider):
    """
    Anthropic Claude provider implementation.

    Uses Claude Sonnet 4 for high-quality research and analysis tasks.
    Supports tool use (Anthropic's version of function calling).
    """

    def __init__(self, api_key: str = None):
        """
        Initialize Anthropic provider.

        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        super().__init__(api_key or os.getenv('ANTHROPIC_API_KEY'))
        self.client = Anthropic(api_key=self.api_key)
        self._default_model = "claude-sonnet-4-20250514"

    @property
    def name(self) -> str:
        """Provider name"""
        return "anthropic"

    @property
    def default_model(self) -> str:
        """Default model for this provider"""
        return self._default_model

    def complete(self,
                 messages: List[Dict[str, str]],
                 tools: Optional[List[Dict]] = None,
                 model: str = None,
                 temperature: float = 0.7,
                 max_tokens: int = 2000,
                 **kwargs) -> CompletionResponse:
        """
        Complete using Anthropic API.

        NOTE: Anthropic requires system message separate from messages array.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions (provider-agnostic format)
            model: Model to use (defaults to claude-sonnet-4-20250514)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional Anthropic-specific parameters

        Returns:
            CompletionResponse with normalized structure
        """
        # Extract system messages if present (Session 76 fix: concatenate multiple)
        system_messages = []
        user_messages = []

        for msg in messages:
            if msg['role'] == 'system':
                system_messages.append(msg['content'])
            else:
                # Session 76 fix: Convert OpenAI format to Anthropic format
                converted_msg = self._convert_message_format(msg)
                user_messages.append(converted_msg)

        # Concatenate all system messages with double newline separator
        system_message = "\n\n".join(system_messages) if system_messages else None

        # Build request parameters
        request_params = {
            "model": model or self.default_model,
            "messages": user_messages,
            "max_tokens": max_tokens,
            "temperature": temperature
        }

        # Add system message if present
        if system_message:
            request_params["system"] = system_message

        # Add tools if provided
        if tools:
            request_params["tools"] = self._convert_tools_to_anthropic_format(tools)

        # Convert tool_choice format if provided (OpenAI → Anthropic)
        if 'tool_choice' in kwargs:
            request_params['tool_choice'] = self._convert_tool_choice_to_anthropic_format(kwargs['tool_choice'])
            kwargs = {k: v for k, v in kwargs.items() if k != 'tool_choice'}

        # Additional Anthropic-specific params
        if kwargs:
            request_params.update(kwargs)

        # Make API call
        response = self.client.messages.create(**request_params)

        # Extract content
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return CompletionResponse(
            content=content,
            tool_calls=self.parse_tool_calls(response),
            finish_reason=response.stop_reason,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens
            },
            raw_response=response
        )

    def stream_complete(self,
                       messages: List[Dict[str, str]],
                       tools: Optional[List[Dict]] = None,
                       model: str = None,
                       temperature: float = 0.7,
                       max_tokens: int = 2000,
                       **kwargs) -> Iterator[str]:
        """
        Stream completion from Anthropic.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            model: Model to use (defaults to claude-sonnet-4-20250514)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional Anthropic-specific parameters

        Yields:
            str: Content chunks as they arrive
        """
        # Extract system message
        system_message = None
        user_messages = []

        for msg in messages:
            if msg['role'] == 'system':
                system_message = msg['content']
            else:
                user_messages.append(msg)

        request_params = {
            "model": model or self.default_model,
            "messages": user_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True
        }

        if system_message:
            request_params["system"] = system_message

        if tools:
            request_params["tools"] = self._convert_tools_to_anthropic_format(tools)

        # Convert tool_choice format if provided (OpenAI → Anthropic)
        if 'tool_choice' in kwargs:
            request_params['tool_choice'] = self._convert_tool_choice_to_anthropic_format(kwargs['tool_choice'])
            kwargs = {k: v for k, v in kwargs.items() if k != 'tool_choice'}

        if kwargs:
            request_params.update(kwargs)

        with self.client.messages.stream(**request_params) as stream:
            for text in stream.text_stream:
                yield text

    def parse_tool_calls(self, response: Any) -> List[ToolCall]:
        """
        Extract tool calls from Anthropic response.

        Args:
            response: Anthropic Message response object

        Returns:
            List of normalized ToolCall objects
        """
        tool_calls = []

        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input
                ))

        return tool_calls

    def _convert_tools_to_anthropic_format(self, tools: List[Dict]) -> List[Dict]:
        """
        Convert provider-agnostic tool format to Anthropic tool use format.

        Provider-agnostic format:
        {
            "name": "search_events",
            "description": "Search civic events",
            "parameters": {...}  # JSON Schema
        }

        Anthropic format:
        {
            "name": "search_events",
            "description": "Search civic events",
            "input_schema": {...}  # JSON Schema
        }

        Args:
            tools: List of provider-agnostic tool definitions

        Returns:
            List of Anthropic-formatted tool definitions
        """
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["parameters"]
            }
            for tool in tools
        ]

    def _convert_message_format(self, msg: Dict) -> Dict:
        """
        Convert OpenAI-style message format to Anthropic format (Session 76 fix).

        OpenAI format (conversation history):
        {
            "role": "assistant",
            "content": "Response text",
            "function_call": {"name": "...", "arguments": "{...}"}
        }

        Anthropic format:
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Response text"},
                {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
            ]
        }

        Args:
            msg: Message in OpenAI format

        Returns:
            Message in Anthropic format
        """
        # If message already has content as a list, it's in Anthropic format
        if isinstance(msg.get('content'), list):
            return msg

        # Convert OpenAI format to Anthropic format
        content_blocks = []

        # Add text content if present
        if msg.get('content'):
            content_blocks.append({
                "type": "text",
                "text": msg['content']
            })

        # Session 76 fix: Don't include function_call in conversation history
        # Anthropic requires tool_result blocks after tool_use, which we don't have
        # The conversational text is sufficient for context
        # (Function calls are metadata, not needed for conversation flow)

        # Return converted message (just the text content, no tool_use blocks)
        # Ensure content is never empty - use placeholder if needed
        if content_blocks:
            return {
                "role": msg['role'],
                "content": content_blocks
            }
        else:
            # If no content blocks, provide a minimal text response
            # This happens when message has only function_call and no text
            return {
                "role": msg['role'],
                "content": "[Function called]"  # Placeholder for function-only messages
            }

    def _convert_tool_choice_to_anthropic_format(self, tool_choice) -> Dict:
        """
        Convert OpenAI tool_choice format to Anthropic tool_choice format.

        OpenAI format:
        {
            "type": "function",
            "function": {"name": "tool_name"}
        }

        Anthropic format:
        {
            "type": "tool",
            "name": "tool_name"
        }

        Args:
            tool_choice: OpenAI-formatted tool_choice or string ("auto")

        Returns:
            Anthropic-formatted tool_choice
        """
        # Handle string shortcuts
        if isinstance(tool_choice, str):
            if tool_choice == "auto":
                return {"type": "auto"}
            elif tool_choice == "none":
                return {"type": "none"}
            # If unknown string, pass through
            return tool_choice

        # Handle dict format
        if isinstance(tool_choice, dict):
            # OpenAI format: {"type": "function", "function": {"name": "tool_name"}}
            if tool_choice.get("type") == "function" and "function" in tool_choice:
                tool_name = tool_choice["function"].get("name")
                return {"type": "tool", "name": tool_name}

            # Already Anthropic format: {"type": "tool", "name": "tool_name"}
            if tool_choice.get("type") == "tool" and "name" in tool_choice:
                return tool_choice

            # Unknown format - pass through
            return tool_choice

        # Unknown type - pass through
        return tool_choice
