"""
Test OpenRouter integration.

Tests that OpenRouter provider, models, and routing are properly configured.
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def test_openrouter_provider():
    """Test that OpenRouterProvider can be imported and instantiated."""
    from providers.openai_compatible_provider import OpenRouterProvider

    # Test instantiation (will use env var or fail gracefully)
    provider = OpenRouterProvider(api_key='test-key')

    assert provider.name == 'openrouter'
    assert provider.default_model == 'meta-llama/llama-3.3-70b-instruct'
    print("✓ OpenRouterProvider instantiation works")


def test_openrouter_factory():
    """Test that factory can create OpenRouter provider."""
    from llm_provider import get_provider

    # Mock the API key for testing
    os.environ['OPENROUTER_API_KEY'] = 'test-key'

    try:
        provider = get_provider('openrouter')
        assert provider.name == 'openrouter'
        print("✓ Factory creates OpenRouter provider correctly")
    finally:
        # Clean up
        if 'OPENROUTER_API_KEY' in os.environ:
            del os.environ['OPENROUTER_API_KEY']


def test_openrouter_models_in_registry():
    """Test that OpenRouter models are registered."""
    from model_registry import MODEL_REGISTRY, get_model_info, get_models_by_provider

    # Check that OpenRouter models exist
    openrouter_models = get_models_by_provider('openrouter')

    assert len(openrouter_models) > 0, "No OpenRouter models found in registry"
    print(f"✓ Found {len(openrouter_models)} OpenRouter models in registry")

    # Check specific models
    expected_models = [
        'anthropic/claude-3.5-sonnet',
        'anthropic/claude-3-5-haiku',
        'meta-llama/llama-3.3-70b-instruct',
        'google/gemini-2.0-flash-exp:free',
        'openai/gpt-4o-mini'
    ]

    for model in expected_models:
        info = get_model_info(model)
        assert info is not None, f"Model {model} not found in registry"
        assert info['provider'] == 'openrouter'
        print(f"  - {model}: ${info['cost_per_1m_tokens']}/1M ({info['description']})")

    print("✓ All expected OpenRouter models are registered")


def test_task_routing_includes_openrouter():
    """Test that task routing config includes OpenRouter models."""
    from llm_provider import TASK_MODEL_CONFIG

    # Check that OpenRouter models appear in task priorities
    openrouter_model_count = 0

    for task_type, config in TASK_MODEL_CONFIG.items():
        model_priority = config.get('model_priority', [])

        openrouter_in_task = any('/' in model for model in model_priority)
        if openrouter_in_task:
            openrouter_model_count += 1
            openrouter_models = [m for m in model_priority if '/' in m]
            print(f"  - {task_type}: {len(openrouter_models)} OpenRouter options")

    assert openrouter_model_count > 0, "No OpenRouter models in task routing"
    print(f"✓ OpenRouter models available in {openrouter_model_count}/{len(TASK_MODEL_CONFIG)} task types")


def test_provider_availability_check():
    """Test that is_provider_available works for OpenRouter."""
    from llm_provider import is_provider_available

    # Without API key, should be unavailable
    if 'OPENROUTER_API_KEY' in os.environ:
        del os.environ['OPENROUTER_API_KEY']

    assert not is_provider_available('openrouter')
    print("✓ OpenRouter correctly reported as unavailable without API key")

    # With API key, should be available
    os.environ['OPENROUTER_API_KEY'] = 'test-key'
    assert is_provider_available('openrouter')
    print("✓ OpenRouter correctly reported as available with API key")

    # Clean up
    del os.environ['OPENROUTER_API_KEY']


def test_model_with_override():
    """Test that get_provider_with_model works for OpenRouter."""
    from llm_provider import get_provider_with_model

    os.environ['OPENROUTER_API_KEY'] = 'test-key'

    try:
        provider = get_provider_with_model('openrouter', 'anthropic/claude-3.5-sonnet')
        assert provider.name == 'openrouter'
        assert provider.default_model == 'anthropic/claude-3.5-sonnet'
        print("✓ Model override works for OpenRouter")
    finally:
        del os.environ['OPENROUTER_API_KEY']


def main():
    """Run all tests."""
    print("=== OpenRouter Integration Tests ===\n")

    try:
        test_openrouter_provider()
        test_openrouter_factory()
        test_openrouter_models_in_registry()
        test_task_routing_includes_openrouter()
        test_provider_availability_check()
        test_model_with_override()

        print("\n✅ All tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
