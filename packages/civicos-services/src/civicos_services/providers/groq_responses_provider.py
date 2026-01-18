"""
Groq Responses API provider for structured outputs and advanced features.

The Responses API is Groq's beta API that supports:
- Structured outputs (json_schema)
- Built-in tools (browser search, code execution)
- Reasoning mode
- MCP integration

This is different from the standard Chat Completions API and provides
better performance for structured outputs.

Pricing (GPT-OSS 20B):
- Input: $0.075 per 1M tokens
- Output: $0.30 per 1M tokens
- Speed: ~1000 tokens/second (12x faster than Gemini)

Environment Variables:
    GROQ_API_KEY: Required (get from https://console.groq.com)
"""

import os
import json
from typing import List, Dict, Any, Optional, Iterator
import requests
from .base import LLMProvider, CompletionResponse, ToolCall


class GroqResponsesProvider(LLMProvider):
    """
    Groq Responses API provider for structured outputs.

    Uses GPT-OSS 20B for fast, cost-effective structured outputs.
    Supports json_schema format for navigation mode.
    """

    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize Groq Responses API provider.

        Args:
            api_key: Groq API key (defaults to GROQ_API_KEY env var)
            model: Model to use (defaults to openai/gpt-oss-20b)
        """
        super().__init__(api_key or os.getenv('GROQ_API_KEY'))
        self.base_url = "https://api.groq.com/openai/v1"
        self._default_model = model or "openai/gpt-oss-20b"

    @property
    def name(self) -> str:
        """Provider name"""
        return "groq-responses"

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
                 response_format: Optional[Dict] = None,
                 **kwargs) -> CompletionResponse:
        """
        Complete using Groq Responses API.

        The Responses API uses a different format than Chat Completions:
        - Uses 'input' instead of 'messages'
        - Uses 'text.format' for structured outputs
        - Returns 'output' array instead of 'choices'

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions (not used for structured outputs)
            model: Model to use (defaults to openai/gpt-oss-20b)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            response_format: OpenAI-style response_format for structured outputs
            **kwargs: Additional parameters

        Returns:
            CompletionResponse with normalized structure
        """
        # Build request body
        request_body = {
            "model": model or self.default_model,
            "input": messages,  # Responses API uses 'input' not 'messages'
            "temperature": temperature,
            # Note: Don't include 'reasoning' by default - it auto-enables
            # Users can add it via kwargs if needed
        }

        if max_tokens:
            request_body["max_output_tokens"] = max_tokens

        # Convert OpenAI response_format to Groq Responses API format
        if response_format:
            request_body["text"] = self._convert_response_format(response_format)

        # Add any additional parameters
        if kwargs:
            request_body.update(kwargs)

        # Make API request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            f"{self.base_url}/responses",
            headers=headers,
            json=request_body,
            timeout=30
        )

        if response.status_code != 200:
            raise Exception(f"Groq Responses API error: {response.status_code} - {response.text}")

        result = response.json()

        # Extract content from output array
        content = self._extract_content(result)

        # Extract usage information
        usage = result.get("usage", {})

        return CompletionResponse(
            content=content,
            tool_calls=[],  # Responses API doesn't use tool_calls for structured outputs
            finish_reason=result.get("status", "completed"),
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0)
            },
            raw_response=result,
            provider_name=self.name,
            model=result.get("model", self.default_model)
        )

    def stream_complete(self,
                       messages: List[Dict[str, str]],
                       tools: Optional[List[Dict]] = None,
                       model: str = None,
                       temperature: float = 0.7,
                       max_tokens: int = 2000,
                       **kwargs) -> Iterator[str]:
        """
        Stream completion from Groq Responses API.

        Note: Streaming may not preserve structured output format perfectly.
        Prefer non-streaming for structured outputs.

        Args:
            messages: List of message dicts
            tools: Optional tool definitions
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            **kwargs: Additional parameters

        Yields:
            str: Content chunks as they arrive
        """
        # Falls back to non-streaming (Groq Responses API doesn't support streaming yet)
        response = self.complete(
            messages=messages,
            tools=tools,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        yield response.content

    def parse_tool_calls(self, response: Any) -> List[ToolCall]:
        """
        Extract tool calls from Groq Responses API response.

        Note: Responses API uses structured outputs differently than tool calls.
        This method is mainly for compatibility.

        Args:
            response: Groq Responses API response object

        Returns:
            List of normalized ToolCall objects (usually empty)
        """
        return []

    def _convert_response_format(self, response_format: Dict) -> Dict:
        """
        Convert OpenAI response_format to Groq Responses API text.format.

        OpenAI format:
        {
            "type": "json_schema",
            "json_schema": {
                "name": "schema_name",
                "schema": {...}
            }
        }

        Groq Responses API format:
        {
            "format": {
                "type": "json_schema",
                "name": "schema_name",
                "schema": {...}
            }
        }

        Args:
            response_format: OpenAI-style response_format

        Returns:
            Groq Responses API text format
        """
        if response_format.get("type") == "json_schema":
            json_schema = response_format.get("json_schema", {})
            return {
                "format": {
                    "type": "json_schema",
                    "name": json_schema.get("name", "response"),
                    "schema": json_schema.get("schema", {})
                }
            }

        # Fallback for simple json type
        if response_format.get("type") == "json_object":
            return {
                "format": {
                    "type": "json_object"
                }
            }

        # Default to text
        return {
            "format": {
                "type": "text"
            }
        }

    def _extract_content(self, result: Dict) -> str:
        """
        Extract content from Groq Responses API output array.

        The output array contains different types:
        - "message" type with "content" array
        - "reasoning" type (for reasoning mode)

        Args:
            result: Groq Responses API result

        Returns:
            Extracted content string
        """
        output = result.get("output", [])

        # Find the message output
        for item in output:
            if item.get("type") == "message":
                content_array = item.get("content", [])
                # Extract text from content array
                for content_item in content_array:
                    if content_item.get("type") == "output_text":
                        return content_item.get("text", "")

        # Fallback: return empty string
        return ""
