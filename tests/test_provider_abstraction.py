"""
Test suite for LLM provider abstraction layer.

Validates backward compatibility, feature flags, and provider functionality.
"""

import unittest
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.llm_provider import get_provider, list_available_providers, get_provider_for_task
from src.providers.base import CompletionResponse


class TestProviderAbstraction(unittest.TestCase):
    """Test provider abstraction layer"""

    def setUp(self):
        """Set up test environment"""
        # Save original env vars
        self.original_provider = os.getenv('LLM_PROVIDER')
        self.original_enable_anthropic = os.getenv('ENABLE_ANTHROPIC')

    def tearDown(self):
        """Restore original env vars"""
        if self.original_provider:
            os.environ['LLM_PROVIDER'] = self.original_provider
        elif 'LLM_PROVIDER' in os.environ:
            del os.environ['LLM_PROVIDER']

        if self.original_enable_anthropic:
            os.environ['ENABLE_ANTHROPIC'] = self.original_enable_anthropic
        elif 'ENABLE_ANTHROPIC' in os.environ:
            del os.environ['ENABLE_ANTHROPIC']

    def test_default_provider_is_openai(self):
        """Default provider should be OpenAI"""
        provider = get_provider()
        self.assertEqual(provider.name, 'openai')
        self.assertEqual(provider.default_model, 'gpt-4o-mini')

    def test_openai_completion(self):
        """OpenAI provider should complete simple request"""
        provider = get_provider('openai')

        response = provider.complete([
            {"role": "user", "content": "Say hello"}
        ])

        self.assertIsInstance(response, CompletionResponse)
        self.assertIsInstance(response.content, str)
        self.assertGreater(len(response.content), 0)
        self.assertIsInstance(response.usage, dict)
        self.assertIn('total_tokens', response.usage)

    def test_openai_tool_calling(self):
        """OpenAI provider should handle tool calls"""
        provider = get_provider('openai')

        tools = [{
            "name": "get_weather",
            "description": "Get weather for location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name"}
                },
                "required": ["location"]
            }
        }]

        response = provider.complete([
            {"role": "user", "content": "What's the weather in Oakland?"}
        ], tools=tools)

        # Should either return content or tool call
        self.assertTrue(
            len(response.content) > 0 or len(response.tool_calls) > 0
        )

    def test_anthropic_provider_requires_flag(self):
        """Anthropic provider should require ENABLE_ANTHROPIC=true"""
        # Disable flag
        os.environ['ENABLE_ANTHROPIC'] = 'false'

        with self.assertRaises(ValueError) as context:
            get_provider('anthropic')

        self.assertIn('not enabled', str(context.exception))

    def test_anthropic_completion_when_enabled(self):
        """Anthropic provider should work when enabled"""
        # Skip if no API key
        if not os.getenv('ANTHROPIC_API_KEY'):
            self.skipTest("No Anthropic API key")

        # Enable flag
        os.environ['ENABLE_ANTHROPIC'] = 'true'

        provider = get_provider('anthropic')

        response = provider.complete([
            {"role": "user", "content": "Say hello"}
        ])

        self.assertIsInstance(response, CompletionResponse)
        self.assertGreater(len(response.content), 0)

    def test_backward_compatibility_default_behavior(self):
        """With default flags, behavior should be identical to before"""
        # Reset flags to defaults
        os.environ['LLM_PROVIDER'] = 'openai'
        os.environ['ENABLE_ANTHROPIC'] = 'false'

        # Get default provider
        provider = get_provider()

        # Should be OpenAI
        self.assertEqual(provider.name, 'openai')
        self.assertEqual(provider.default_model, 'gpt-4o-mini')

    def test_list_available_providers(self):
        """Should list only enabled providers"""
        # Default: OpenAI and Ollama (always available)
        os.environ['ENABLE_ANTHROPIC'] = 'false'
        providers = list_available_providers()
        self.assertIn('openai', providers)
        self.assertIn('ollama', providers)  # Ollama is always listed

        # With Anthropic enabled
        os.environ['ENABLE_ANTHROPIC'] = 'true'
        providers = list_available_providers()
        self.assertIn('openai', providers)
        self.assertIn('ollama', providers)
        self.assertIn('anthropic', providers)

    def test_get_provider_for_task(self):
        """Task-based provider selection should work"""
        # Smart routing based on available API keys
        nav_provider = get_provider_for_task('navigation')
        research_provider = get_provider_for_task('research')

        # Navigation prefers Google > Groq > OpenAI
        if os.getenv('GOOGLE_API_KEY'):
            self.assertEqual(nav_provider.name, 'google')
        elif os.getenv('GROQ_API_KEY'):
            self.assertEqual(nav_provider.name, 'groq')
        else:
            self.assertEqual(nav_provider.name, 'openai')

        # Research prefers Google > Claude > OpenAI
        if os.getenv('GOOGLE_API_KEY'):
            self.assertEqual(research_provider.name, 'google')
        elif os.getenv('ENABLE_ANTHROPIC', 'false').lower() == 'true':
            self.assertEqual(research_provider.name, 'anthropic')
        else:
            self.assertEqual(research_provider.name, 'openai')

    def test_unknown_provider_raises_error(self):
        """Unknown provider name should raise ValueError"""
        with self.assertRaises(ValueError) as context:
            get_provider('unknown_provider')

        self.assertIn('Unknown provider', str(context.exception))

    def test_tool_call_parsing(self):
        """Tool call parsing should work correctly"""
        provider = get_provider('openai')

        tools = [{
            "name": "search_events",
            "description": "Search for events",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                }
            }
        }]

        response = provider.complete([
            {"role": "user", "content": "Find housing meetings in Berkeley"}
        ], tools=tools)

        # Response should have structure
        self.assertIsInstance(response, CompletionResponse)
        self.assertIsInstance(response.tool_calls, list)

    def test_streaming_support(self):
        """Provider should support streaming"""
        provider = get_provider('openai')

        chunks = list(provider.stream_complete([
            {"role": "user", "content": "Count to 3"}
        ]))

        # Should receive multiple chunks
        self.assertGreater(len(chunks), 0)
        # All chunks should be strings
        self.assertTrue(all(isinstance(chunk, str) for chunk in chunks))

    def test_temperature_parameter(self):
        """Provider should accept temperature parameter"""
        provider = get_provider('openai')

        # Low temperature (more deterministic)
        response1 = provider.complete([
            {"role": "user", "content": "Say hello"}
        ], temperature=0.1)

        # High temperature (more creative)
        response2 = provider.complete([
            {"role": "user", "content": "Say hello"}
        ], temperature=0.9)

        # Both should complete
        self.assertIsInstance(response1, CompletionResponse)
        self.assertIsInstance(response2, CompletionResponse)

    def test_groq_provider_initialization(self):
        """Groq provider should initialize correctly"""
        provider = get_provider('groq')
        self.assertEqual(provider.name, 'groq')
        self.assertEqual(provider.default_model, 'llama-3.3-70b-versatile')

    def test_groq_completion_when_api_key_available(self):
        """Groq provider should work when API key available"""
        if not os.getenv('GROQ_API_KEY'):
            self.skipTest("No Groq API key")

        provider = get_provider('groq')

        response = provider.complete([
            {"role": "user", "content": "Say hello"}
        ])

        self.assertIsInstance(response, CompletionResponse)
        self.assertGreater(len(response.content), 0)

    def test_groq_tool_calling(self):
        """Groq provider should support tool calling"""
        if not os.getenv('GROQ_API_KEY'):
            self.skipTest("No Groq API key")

        provider = get_provider('groq')

        tools = [{
            "name": "get_weather",
            "description": "Get weather for location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                },
                "required": ["location"]
            }
        }]

        response = provider.complete([
            {"role": "user", "content": "What's the weather in Oakland?"}
        ], tools=tools)

        # Should have response
        self.assertIsInstance(response, CompletionResponse)

    def test_ollama_provider_initialization(self):
        """Ollama provider should initialize correctly"""
        provider = get_provider('ollama')
        self.assertEqual(provider.name, 'ollama')
        # Default model should be llama3.1
        self.assertIn('llama', provider.default_model.lower())

    def test_smart_routing_for_navigation(self):
        """Navigation tasks should route to Google when available, fallback to Groq"""
        # Navigation prefers Google > Groq > OpenAI
        provider = get_provider_for_task('navigation')

        if os.getenv('GOOGLE_API_KEY'):
            self.assertEqual(provider.name, 'google')
        elif os.getenv('GROQ_API_KEY'):
            self.assertEqual(provider.name, 'groq')
        else:
            self.assertEqual(provider.name, 'openai')

    def test_smart_routing_for_research(self):
        """Research tasks should route to Google when available, fallback to Claude/OpenAI"""
        # Research prefers Google > Claude > OpenAI
        provider = get_provider_for_task('research')

        if os.getenv('GOOGLE_API_KEY'):
            self.assertEqual(provider.name, 'google')
        elif os.getenv('ENABLE_ANTHROPIC', 'false').lower() == 'true':
            self.assertEqual(provider.name, 'anthropic')
        else:
            self.assertEqual(provider.name, 'openai')

    def test_smart_routing_fallback(self):
        """Tasks should fallback to OpenAI when preferred provider unavailable"""
        # Save original keys
        original_google = os.getenv('GOOGLE_API_KEY')
        original_groq = os.getenv('GROQ_API_KEY')

        # Disable all special providers
        os.environ['ENABLE_ANTHROPIC'] = 'false'
        if 'GOOGLE_API_KEY' in os.environ:
            del os.environ['GOOGLE_API_KEY']
        if 'GROQ_API_KEY' in os.environ:
            del os.environ['GROQ_API_KEY']

        try:
            # Navigation should fallback to OpenAI
            nav_provider = get_provider_for_task('navigation')
            self.assertEqual(nav_provider.name, 'openai')

            # Research should fallback to OpenAI
            research_provider = get_provider_for_task('research')
            self.assertEqual(research_provider.name, 'openai')
        finally:
            # Restore original keys
            if original_google:
                os.environ['GOOGLE_API_KEY'] = original_google
            if original_groq:
                os.environ['GROQ_API_KEY'] = original_groq

    def test_list_providers_includes_groq(self):
        """List should include Groq when API key available"""
        if not os.getenv('GROQ_API_KEY'):
            self.skipTest("No Groq API key")

        providers = list_available_providers()
        self.assertIn('groq', providers)

    def test_list_providers_includes_ollama(self):
        """List should always include Ollama (opt-in)"""
        providers = list_available_providers()
        self.assertIn('ollama', providers)

    def test_google_provider_initialization(self):
        """Google/Gemini provider should initialize correctly"""
        provider = get_provider('google')
        self.assertEqual(provider.name, 'google')
        self.assertEqual(provider.default_model, 'gemini-2.0-flash-exp')

    def test_google_provider_alias(self):
        """'gemini' should work as alias for 'google'"""
        provider = get_provider('gemini')
        self.assertEqual(provider.name, 'google')

    def test_google_completion_when_api_key_available(self):
        """Google provider should work when API key available"""
        if not os.getenv('GOOGLE_API_KEY'):
            self.skipTest("No Google API key")

        provider = get_provider('google')

        response = provider.complete([
            {"role": "user", "content": "Say hello"}
        ])

        self.assertIsInstance(response, CompletionResponse)
        self.assertGreater(len(response.content), 0)

    def test_google_tool_calling(self):
        """Google provider should support function calling"""
        if not os.getenv('GOOGLE_API_KEY'):
            self.skipTest("No Google API key")

        provider = get_provider('google')

        tools = [{
            "name": "get_weather",
            "description": "Get weather for location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"}
                },
                "required": ["location"]
            }
        }]

        response = provider.complete([
            {"role": "user", "content": "What's the weather in Oakland?"}
        ], tools=tools)

        # Should have response
        self.assertIsInstance(response, CompletionResponse)

    def test_smart_routing_prefers_gemini_for_navigation(self):
        """Navigation should prefer Gemini when available"""
        if not os.getenv('GOOGLE_API_KEY'):
            self.skipTest("No Google API key")

        provider = get_provider_for_task('navigation')
        self.assertEqual(provider.name, 'google')

    def test_smart_routing_prefers_gemini_for_research(self):
        """Research should prefer Gemini when available"""
        if not os.getenv('GOOGLE_API_KEY'):
            self.skipTest("No Google API key")

        provider = get_provider_for_task('research')
        self.assertEqual(provider.name, 'google')

    def test_long_document_routing_uses_gemini_pro(self):
        """Long document tasks should use Gemini Pro 1.5 for 2M context"""
        if not os.getenv('GOOGLE_API_KEY'):
            self.skipTest("No Google API key")

        provider = get_provider_for_task('long_document')
        self.assertEqual(provider.name, 'google')
        self.assertEqual(provider.default_model, 'gemini-1.5-pro-latest')

    def test_list_providers_includes_google(self):
        """List should include Google when API key available"""
        if not os.getenv('GOOGLE_API_KEY'):
            self.skipTest("No Google API key")

        providers = list_available_providers()
        self.assertIn('google', providers)

    def test_perplexity_provider_initialization(self):
        """Perplexity provider should initialize correctly"""
        provider = get_provider('perplexity')
        self.assertEqual(provider.name, 'perplexity')
        self.assertIn('sonar', provider.default_model)

    def test_perplexity_completion_when_api_key_available(self):
        """Perplexity provider should work when API key available"""
        if not os.getenv('PERPLEXITY_API_KEY'):
            self.skipTest("No Perplexity API key")

        provider = get_provider('perplexity')

        response = provider.complete([
            {"role": "user", "content": "What is the capital of California?"}
        ])

        self.assertIsInstance(response, CompletionResponse)
        self.assertGreater(len(response.content), 0)

    def test_realtime_research_task_routing(self):
        """realtime_research task should route to Perplexity if available"""
        if os.getenv('PERPLEXITY_API_KEY'):
            provider = get_provider_for_task('realtime_research')
            self.assertEqual(provider.name, 'perplexity')
        else:
            # Should fallback to Google or OpenAI
            provider = get_provider_for_task('realtime_research')
            self.assertIn(provider.name, ['google', 'openai'])

    def test_list_providers_includes_perplexity(self):
        """List should include Perplexity when API key available"""
        if not os.getenv('PERPLEXITY_API_KEY'):
            self.skipTest("No Perplexity API key")

        providers = list_available_providers()
        self.assertIn('perplexity', providers)


if __name__ == '__main__':
    unittest.main()
