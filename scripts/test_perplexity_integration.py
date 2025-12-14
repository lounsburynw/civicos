"""
Test suite for Perplexity integration (Session 75).

This test suite validates that Perplexity models are properly registered
and can be used for real-time civic research with web search and citations.

Tests:
1. Model registry includes Perplexity models
2. PerplexityProvider initialization
3. Task routing selects Perplexity for realtime_research
4. API call to Perplexity (requires PERPLEXITY_API_KEY)
5. Citation parsing

Usage:
    python scripts/test_perplexity_integration.py
"""

import os
import sys

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from model_registry import MODEL_REGISTRY, get_model_info, is_model_available
from llm_provider import get_model, get_model_for_task, get_provider
from providers.openai_compatible_provider import PerplexityProvider


def test_perplexity_models_in_registry():
    """Test 1: Perplexity models in MODEL_REGISTRY"""
    print("\n" + "="*70)
    print("Test 1: Perplexity models in MODEL_REGISTRY")
    print("="*70)

    assert 'sonar-pro' in MODEL_REGISTRY, "sonar-pro not found in MODEL_REGISTRY"
    assert 'sonar' in MODEL_REGISTRY, "sonar not found in MODEL_REGISTRY"

    sonar_pro = MODEL_REGISTRY['sonar-pro']
    sonar = MODEL_REGISTRY['sonar']

    assert sonar_pro['provider'] == 'perplexity', "sonar-pro provider should be 'perplexity'"
    assert sonar['provider'] == 'perplexity', "sonar provider should be 'perplexity'"

    assert 'web_search' in sonar_pro['capabilities'], "sonar-pro should have web_search capability"
    assert 'citations' in sonar_pro['capabilities'], "sonar-pro should have citations capability"
    assert 'web_search' in sonar['capabilities'], "sonar should have web_search capability"
    assert 'citations' in sonar['capabilities'], "sonar should have citations capability"

    print(f"✓ sonar-pro registered:")
    print(f"  - Provider: {sonar_pro['provider']}")
    print(f"  - Cost: ${sonar_pro['cost_per_1m_tokens']}/1M tokens")
    print(f"  - Context: {sonar_pro['context_window']:,} tokens")
    print(f"  - Capabilities: {', '.join(sonar_pro['capabilities'])}")

    print(f"\n✓ sonar registered:")
    print(f"  - Provider: {sonar['provider']}")
    print(f"  - Cost: ${sonar['cost_per_1m_tokens']}/1M tokens")
    print(f"  - Context: {sonar['context_window']:,} tokens")
    print(f"  - Capabilities: {', '.join(sonar['capabilities'])}")

    print("\n✓ Test 1 PASSED: Both Perplexity models properly registered")


def test_perplexity_provider_initialization():
    """Test 2: PerplexityProvider can be initialized"""
    print("\n" + "="*70)
    print("Test 2: PerplexityProvider initialization")
    print("="*70)

    # Initialize with default model
    provider = PerplexityProvider()
    assert provider.name == 'perplexity', "Provider name should be 'perplexity'"
    assert provider.default_model in ['sonar-pro', 'sonar'], "Default model should be sonar-pro or sonar"

    print(f"✓ PerplexityProvider initialized:")
    print(f"  - Name: {provider.name}")
    print(f"  - Default model: {provider.default_model}")
    print(f"  - Base URL: https://api.perplexity.ai")

    # Initialize with specific model
    provider_sonar = PerplexityProvider(model='sonar')
    assert provider_sonar.default_model == 'sonar', "Should use specified model"

    print(f"\n✓ PerplexityProvider with custom model:")
    print(f"  - Model: {provider_sonar.default_model}")

    print("\n✓ Test 2 PASSED: PerplexityProvider initializes correctly")


def test_realtime_research_routing():
    """Test 3: realtime_research routes to Perplexity"""
    print("\n" + "="*70)
    print("Test 3: realtime_research task routing")
    print("="*70)

    # Test model availability
    perplexity_available = is_model_available('sonar-pro')
    print(f"Perplexity API key configured: {perplexity_available}")

    # Get provider for realtime_research task
    provider = get_model_for_task('realtime_research')
    assert provider is not None, "Should return a provider"

    print(f"\n✓ realtime_research routes to:")
    print(f"  - Provider: {provider.name}")
    print(f"  - Model: {provider.default_model}")

    if perplexity_available:
        assert provider.name == 'perplexity', "Should use Perplexity when API key is set"
        assert provider.default_model in ['sonar-pro', 'sonar'], "Should use Perplexity model"
        print(f"  - Status: ✓ Using Perplexity (API key configured)")
    else:
        print(f"  - Status: ⚠ Using fallback (PERPLEXITY_API_KEY not set)")

    print("\n✓ Test 3 PASSED: Task routing works correctly")


def test_perplexity_api_call():
    """Test 4: Make actual API call to Perplexity (if key available)"""
    print("\n" + "="*70)
    print("Test 4: Perplexity API call")
    print("="*70)

    if not os.getenv('PERPLEXITY_API_KEY'):
        print("⚠ Skipping: PERPLEXITY_API_KEY not set")
        print("  To test API calls, set PERPLEXITY_API_KEY environment variable")
        return

    try:
        # Get provider for sonar-pro (cheaper for testing)
        provider = get_model('sonar')

        print(f"Making API call to Perplexity ({provider.default_model})...")
        print(f"Query: 'What is California AB 1147?'")

        # Make API call
        response = provider.complete(
            messages=[{
                "role": "user",
                "content": "What is California AB 1147? Provide a brief 2-sentence summary."
            }],
            max_tokens=500,
            temperature=0.7
        )

        assert response.content is not None, "Response should have content"
        assert len(response.content) > 0, "Response content should not be empty"

        print(f"\n✓ API call successful!")
        print(f"\nResponse:")
        print(f"  {response.content[:300]}{'...' if len(response.content) > 300 else ''}")

        # Check for citations in metadata
        if hasattr(response, 'metadata') and response.metadata:
            citations = response.metadata.get('citations', [])
            if citations:
                print(f"\n✓ Citations found: {len(citations)} sources")
                for i, citation in enumerate(citations[:3], 1):
                    print(f"  [{i}] {citation}")

        # Check token usage
        if hasattr(response, 'usage') and response.usage:
            print(f"\nToken usage:")
            print(f"  - Input: {response.usage.get('prompt_tokens', 0)} tokens")
            print(f"  - Output: {response.usage.get('completion_tokens', 0)} tokens")
            print(f"  - Total: {response.usage.get('total_tokens', 0)} tokens")

        print("\n✓ Test 4 PASSED: Perplexity API call successful")

    except Exception as e:
        print(f"\n✗ Test 4 FAILED: {str(e)}")
        raise


def test_model_fallback():
    """Test 5: Fallback behavior when Perplexity unavailable"""
    print("\n" + "="*70)
    print("Test 5: Model fallback behavior")
    print("="*70)

    # Temporarily unset PERPLEXITY_API_KEY to test fallback
    original_key = os.getenv('PERPLEXITY_API_KEY')
    if original_key:
        os.environ.pop('PERPLEXITY_API_KEY', None)

    try:
        provider = get_model_for_task('realtime_research')
        assert provider is not None, "Should return fallback provider"

        print(f"✓ Fallback provider when Perplexity unavailable:")
        print(f"  - Provider: {provider.name}")
        print(f"  - Model: {provider.default_model}")
        print(f"  - Expected: gemini-2.0-flash-exp or gpt-4o-mini")

        assert provider.default_model in ['gemini-2.0-flash-exp', 'gpt-4o-mini'], \
            "Should fallback to Gemini or OpenAI"

        print("\n✓ Test 5 PASSED: Fallback behavior works correctly")

    finally:
        # Restore original key
        if original_key:
            os.environ['PERPLEXITY_API_KEY'] = original_key


def run_all_tests():
    """Run all Perplexity integration tests"""
    print("\n" + "="*70)
    print("Perplexity Integration Test Suite (Session 75)")
    print("="*70)

    tests = [
        test_perplexity_models_in_registry,
        test_perplexity_provider_initialization,
        test_realtime_research_routing,
        test_perplexity_api_call,
        test_model_fallback
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"\n✗ Test failed with error: {str(e)}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*70)
    print(f"Test Summary: {passed} passed, {failed} failed")
    print("="*70)

    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    run_all_tests()
