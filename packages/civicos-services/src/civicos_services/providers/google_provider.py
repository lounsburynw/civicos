"""
Google Gemini provider implementation for LLM abstraction layer.

This module implements Google's Gemini models (Flash 2.0, Pro 1.5)
with support for function calling and large context windows.
"""

import os
import json
import google.generativeai as genai
from typing import List, Dict, Any, Optional, Iterator
from .base import LLMProvider, CompletionResponse, ToolCall


class GoogleProvider(LLMProvider):
    """
    Google Gemini provider implementation.

    Supports Gemini 2.0 Flash (fastest, cheapest) and Gemini 1.5 Pro (2M context).
    Uses Google's generativeai SDK with function calling support.
    """

    def __init__(self, api_key: str = None, model: str = None):
        """
        Initialize Google Gemini provider.

        Args:
            api_key: Google API key (defaults to GOOGLE_API_KEY env var)
            model: Model to use (defaults to models/gemini-2.0-flash)
        """
        super().__init__(api_key or os.getenv('GOOGLE_API_KEY'))
        genai.configure(api_key=self.api_key)
        self._default_model = model or "models/gemini-2.0-flash"

    @property
    def name(self) -> str:
        """Provider name"""
        return "google"

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
        Complete using Google Gemini API.

        NOTE: Google uses different message format than OpenAI:
        - System messages go in system_instruction parameter
        - Messages are in chat history format

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions (provider-agnostic format)
            model: Model to use (defaults to models/gemini-2.0-flash)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional Google-specific parameters

        Returns:
            CompletionResponse with normalized structure
        """
        # Extract system instruction if present
        system_instruction = None
        chat_messages = []

        for msg in messages:
            if msg['role'] == 'system':
                system_instruction = msg['content']
            else:
                # Convert OpenAI format to Gemini format
                role = 'user' if msg['role'] == 'user' else 'model'
                chat_messages.append({
                    'role': role,
                    'parts': [msg['content']]
                })

        # Initialize model
        model_name = model or self.default_model
        generation_config = {
            'temperature': temperature,
            'max_output_tokens': max_tokens
        }

        # Handle OpenAI response_format parameter (convert to Gemini format)
        # Track if JSON response is expected for post-processing
        expects_json = False
        if 'response_format' in kwargs:
            response_format = kwargs['response_format']
            # Handle simple string format: response_format="json_object"
            if response_format == "json_object":
                generation_config['response_mime_type'] = 'application/json'
                expects_json = True
            # Handle dict format: response_format={'type': 'json_schema', ...}
            elif isinstance(response_format, dict) and response_format.get('type') == 'json_schema':
                json_schema = response_format.get('json_schema', {})
                schema = json_schema.get('schema', {})
                # Normalize schema for Gemini (convert array types to single types)
                schema = self._normalize_schema_for_gemini(schema)
                generation_config['response_mime_type'] = 'application/json'
                generation_config['response_schema'] = schema
                expects_json = True

        # Build model configuration
        model_kwargs = {
            'model_name': model_name,
            'generation_config': generation_config
        }

        if system_instruction:
            model_kwargs['system_instruction'] = system_instruction

        # Add tools if provided
        if tools:
            model_kwargs['tools'] = [self._convert_tools_to_google_format(tools)]

        gemini_model = genai.GenerativeModel(**model_kwargs)

        # Generate content
        if len(chat_messages) == 0:
            # No messages - this shouldn't happen, but handle gracefully
            response = gemini_model.generate_content("")
        elif len(chat_messages) == 1:
            # Single message - use generate_content directly
            response = gemini_model.generate_content(chat_messages[0]['parts'][0])
        else:
            # Multiple messages - use chat
            chat = gemini_model.start_chat(history=chat_messages[:-1])
            response = chat.send_message(chat_messages[-1]['parts'][0])

        # Extract content
        # Google uses .text attribute for content, but may return function calls instead
        content = ""
        try:
            if response.text:
                content = response.text
                # Strip markdown fences if JSON response expected
                # Gemini sometimes wraps JSON in ```json ... ``` even with response_mime_type set
                if expects_json and content.strip().startswith("```"):
                    content = self._strip_markdown_fences(content)
        except ValueError:
            # When function calls are returned, .text raises ValueError
            # This is expected - content will be empty and tool_calls will be populated
            pass

        # Parse tool calls
        tool_calls = self.parse_tool_calls(response)

        # Extract token usage
        usage = {
            'prompt_tokens': response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') else 0,
            'completion_tokens': response.usage_metadata.candidates_token_count if hasattr(response, 'usage_metadata') else 0,
            'total_tokens': response.usage_metadata.total_token_count if hasattr(response, 'usage_metadata') else 0
        }

        return CompletionResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=str(response.candidates[0].finish_reason) if response.candidates else 'unknown',
            usage=usage,
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
        Stream completion from Google Gemini.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions
            model: Model to use (defaults to models/gemini-2.0-flash)
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional Google-specific parameters

        Yields:
            str: Content chunks as they arrive
        """
        # Extract system instruction
        system_instruction = None
        chat_messages = []

        for msg in messages:
            if msg['role'] == 'system':
                system_instruction = msg['content']
            else:
                role = 'user' if msg['role'] == 'user' else 'model'
                chat_messages.append({
                    'role': role,
                    'parts': [msg['content']]
                })

        # Initialize model
        model_name = model or self.default_model
        generation_config = {
            'temperature': temperature,
            'max_output_tokens': max_tokens
        }

        # Handle OpenAI response_format parameter (convert to Gemini format)
        if 'response_format' in kwargs:
            response_format = kwargs['response_format']
            # Handle simple string format: response_format="json_object"
            if response_format == "json_object":
                generation_config['response_mime_type'] = 'application/json'
            # Handle dict format: response_format={'type': 'json_schema', ...}
            elif isinstance(response_format, dict) and response_format.get('type') == 'json_schema':
                json_schema = response_format.get('json_schema', {})
                schema = json_schema.get('schema', {})
                # Normalize schema for Gemini (convert array types to single types)
                schema = self._normalize_schema_for_gemini(schema)
                generation_config['response_mime_type'] = 'application/json'
                generation_config['response_schema'] = schema

        model_kwargs = {
            'model_name': model_name,
            'generation_config': generation_config
        }

        if system_instruction:
            model_kwargs['system_instruction'] = system_instruction

        if tools:
            model_kwargs['tools'] = [self._convert_tools_to_google_format(tools)]

        gemini_model = genai.GenerativeModel(**model_kwargs)

        # Stream content
        if len(chat_messages) == 1:
            response = gemini_model.generate_content(
                chat_messages[0]['parts'][0],
                stream=True
            )
        else:
            chat = gemini_model.start_chat(history=chat_messages[:-1])
            response = chat.send_message(
                chat_messages[-1]['parts'][0],
                stream=True
            )

        for chunk in response:
            if chunk.text:
                yield chunk.text

    def parse_tool_calls(self, response: Any) -> List[ToolCall]:
        """
        Extract tool calls from Google Gemini response.

        Args:
            response: Google GenerateContentResponse object

        Returns:
            List of normalized ToolCall objects
        """
        tool_calls = []

        if not response.candidates:
            return tool_calls

        for candidate in response.candidates:
            if not hasattr(candidate.content, 'parts'):
                continue

            for part in candidate.content.parts:
                if hasattr(part, 'function_call') and part.function_call:
                    fc = part.function_call
                    # Convert Google's struct args to dict
                    args_dict = {}
                    if hasattr(fc, 'args') and fc.args:
                        args_dict = dict(fc.args)

                    tool_calls.append(ToolCall(
                        id=fc.name,  # Google doesn't provide separate ID
                        name=fc.name,
                        arguments=args_dict
                    ))

        return tool_calls

    def _convert_tools_to_google_format(self, tools: List[Dict]) -> Dict:
        """
        Convert provider-agnostic tool format to Google function calling format.

        Provider-agnostic format:
        {
            "name": "search_events",
            "description": "Search civic events",
            "parameters": {...}  # JSON Schema
        }

        Google format:
        {
            "function_declarations": [{
                "name": "search_events",
                "description": "Search civic events",
                "parameters": {...}
            }]
        }

        Args:
            tools: List of provider-agnostic tool definitions

        Returns:
            Google-formatted function declarations
        """
        function_declarations = []

        for tool in tools:
            # Normalize parameters schema for Gemini compatibility
            normalized_params = self._normalize_schema_for_gemini(tool["parameters"])

            function_declarations.append({
                "name": tool["name"],
                "description": tool["description"],
                "parameters": normalized_params
            })

        return {
            "function_declarations": function_declarations
        }

    def _normalize_schema_for_gemini(self, schema: Dict) -> Dict:
        """
        Normalize JSON schema for Gemini compatibility.

        Converts array type notation (e.g., ["string", "null"]) to single type ("string")
        since Gemini doesn't support the array notation for nullable types.

        Args:
            schema: JSON schema dict

        Returns:
            Normalized schema dict
        """
        import copy
        schema = copy.deepcopy(schema)

        def normalize_recursive(obj):
            if isinstance(obj, dict):
                # Handle type field
                if 'type' in obj and isinstance(obj['type'], list):
                    # Convert ["string", "null"] to "string"
                    # Filter out "null" and take the first non-null type
                    types = [t for t in obj['type'] if t != 'null']
                    if types:
                        obj['type'] = types[0]
                    else:
                        obj['type'] = 'string'  # Default fallback

                # Remove unsupported fields (not supported by Gemini)
                if 'additionalProperties' in obj:
                    del obj['additionalProperties']
                if 'minItems' in obj:
                    del obj['minItems']
                if 'maxItems' in obj:
                    del obj['maxItems']

                # Recursively process nested objects
                for key, value in list(obj.items()):  # Use list() to avoid dict mutation issues
                    if isinstance(value, (dict, list)):
                        normalize_recursive(value)

            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, (dict, list)):
                        normalize_recursive(item)

        normalize_recursive(schema)
        return schema

    def _strip_markdown_fences(self, content: str) -> str:
        """
        Strip markdown code fences from content.

        Gemini sometimes wraps JSON responses in ```json ... ``` even when
        response_mime_type is set to 'application/json'. This method removes
        those fences to return clean JSON.

        Args:
            content: Response content that may be wrapped in markdown fences

        Returns:
            Content with markdown fences removed
        """
        content = content.strip()
        if not content.startswith("```"):
            return content

        lines = content.split("\n")
        # Skip first line (```json or ```) and last line (```)
        if lines[-1].strip() == "```":
            return "\n".join(lines[1:-1])
        else:
            # Fence not properly closed, just skip first line
            return "\n".join(lines[1:])
