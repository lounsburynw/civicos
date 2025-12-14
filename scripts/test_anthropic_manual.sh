#!/bin/bash
# Manual test commands for Anthropic integration
# Usage: bash scripts/test_anthropic_manual.sh

echo "============================================================"
echo "ANTHROPIC CLAUDE - MANUAL TESTING GUIDE"
echo "============================================================"
echo ""

# Check environment
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "❌ ANTHROPIC_API_KEY not set"
    echo "   Please add to .env file: ANTHROPIC_API_KEY=your_key_here"
    exit 1
fi

if [ "$ENABLE_ANTHROPIC" != "true" ]; then
    echo "❌ ENABLE_ANTHROPIC not set to 'true'"
    echo "   Please add to .env file: ENABLE_ANTHROPIC=true"
    exit 1
fi

echo "✓ Environment configured"
echo ""

echo "============================================================"
echo "TEST 1: Basic Provider Test (Python)"
echo "============================================================"
echo ""
echo "python -c \""
echo "from llm_provider import get_provider"
echo "provider = get_provider('anthropic')"
echo "print(f'Provider: {provider.name}')"
echo "print(f'Model: {provider.default_model}')"
echo "\""
echo ""
python -c "
from llm_provider import get_provider
provider = get_provider('anthropic')
print(f'✓ Provider: {provider.name}')
print(f'✓ Model: {provider.default_model}')
"
echo ""

echo "============================================================"
echo "TEST 2: Simple Chat Completion"
echo "============================================================"
echo ""
python -c "
from llm_provider import get_provider
provider = get_provider('anthropic')
response = provider.complete(
    messages=[{'role': 'user', 'content': 'Say hello in one word'}],
    temperature=0.1
)
print(f'✓ Response: {response.content}')
print(f'✓ Provider: {response.provider_name}')
print(f'✓ Model: {response.model}')
print(f'✓ Tokens: {response.usage.get(\"total_tokens\", 0)}')
"
echo ""

echo "============================================================"
echo "TEST 3: Via Chat Router (Override LLM_PROVIDER)"
echo "============================================================"
echo ""
echo "To test Anthropic in the full app:"
echo ""
echo "1. Temporarily override LLM_PROVIDER:"
echo "   export LLM_PROVIDER=anthropic"
echo ""
echo "2. Restart the backend:"
echo "   python src/civic_api_integrated.py"
echo ""
echo "3. Test conversational queries in the frontend"
echo ""
echo "4. Check logs for provider usage:"
echo "   grep 'anthropic' <backend_logs>"
echo ""

echo "============================================================"
echo "TEST 4: Smart Routing Override"
echo "============================================================"
echo ""
echo "To test Anthropic for specific task types, modify:"
echo "src/llm_provider.py -> get_provider_for_task()"
echo ""
echo "Example - use Anthropic for research:"
echo "  elif task_type == 'research':"
echo "      # Try providers in priority order"
echo "      for provider_name in ['anthropic', 'google', 'openai']:"
echo ""

echo "============================================================"
echo "SUMMARY"
echo "============================================================"
echo ""
echo "Anthropic integration supports:"
echo "  ✓ Basic chat completions"
echo "  ✓ Tool calling (function calling)"
echo "  ✓ Structured outputs (JSON schema)"
echo "  ✓ Smart routing integration"
echo ""
echo "Current routing (as of Session 70):"
echo "  - Navigation: Gemini Flash"
echo "  - Conversational: OpenAI"
echo "  - Research: Gemini"
echo "  - Long documents: Gemini Pro"
echo ""
echo "To make Anthropic default for a task type:"
echo "  1. Edit src/llm_provider.py"
echo "  2. Modify get_provider_for_task() priority order"
echo "  3. Restart backend"
echo ""
