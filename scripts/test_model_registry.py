"""
Test suite for Model Registry and model-first routing (Session 74).

This tests the new model-first architecture where provider is implementation
detail and model is primary abstraction.

Usage:
    python scripts/test_model_registry.py
"""

import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from model_registry import (
    MODEL_REGISTRY,
    get_model_info,
    find_models_by_capabilities,
    is_model_available,
    get_available_models,
    get_cheapest_model,
    get_models_by_provider
)
from llm_provider import (
    TASK_MODEL_CONFIG,
    get_model_for_task,
    get_model
)


def test_model_registry_structure():
    """Test 1: All models have required fields."""
    print("\n=== Test 1: Model Registry Structure ===")

    required_fields = ['provider', 'capabilities', 'cost_per_1m_tokens', 'context_window', 'speed', 'description']

    for model_name, info in MODEL_REGISTRY.items():
        for field in required_fields:
            assert field in info, f"Model {model_name} missing required field: {field}"

        # Validate field types
        assert isinstance(info['provider'], str), f"{model_name}: provider must be string"
        assert isinstance(info['capabilities'], list), f"{model_name}: capabilities must be list"
        assert isinstance(info['cost_per_1m_tokens'], (int, float)), f"{model_name}: cost must be numeric"
        assert isinstance(info['context_window'], int), f"{model_name}: context_window must be int"
        assert info['speed'] in ['ultra_fast', 'very_fast', 'fast', 'medium'], f"{model_name}: invalid speed"

    print(f"✓ All {len(MODEL_REGISTRY)} models have valid structure")


def test_provider_references():
    """Test 2: Provider references are valid."""
    print("\n=== Test 2: Provider References ===")

    valid_providers = {'openai', 'google', 'anthropic', 'groq'}

    for model_name, info in MODEL_REGISTRY.items():
        provider = info['provider']
        assert provider in valid_providers, f"Model {model_name} has invalid provider: {provider}"

    print(f"✓ All provider references are valid: {valid_providers}")


def test_capability_search():
    """Test 3: Capability-based search works."""
    print("\n=== Test 3: Capability-Based Search ===")

    # Test 1: Find models with structured outputs
    structured_models = find_models_by_capabilities(['structured_outputs'])
    assert len(structured_models) > 0, "Should find models with structured outputs"
    print(f"  Found {len(structured_models)} models with structured_outputs")

    # Test 2: Find models with long context
    long_context_models = find_models_by_capabilities(['long_context'])
    assert len(long_context_models) > 0, "Should find models with long_context"
    print(f"  Found {len(long_context_models)} models with long_context")

    # Test 3: Find cheap models (<$0.10/1M)
    cheap_models = find_models_by_capabilities(['structured_outputs'], max_cost=0.10)
    assert len(cheap_models) > 0, "Should find cheap models"
    print(f"  Found {len(cheap_models)} models under $0.10/1M")

    # Verify they are sorted by cost
    for i in range(len(cheap_models) - 1):
        cost_a = MODEL_REGISTRY[cheap_models[i]]['cost_per_1m_tokens']
        cost_b = MODEL_REGISTRY[cheap_models[i + 1]]['cost_per_1m_tokens']
        assert cost_a <= cost_b, "Models should be sorted by cost"

    # Test 4: Find models with minimum context window
    high_context = find_models_by_capabilities(['long_context'], min_context=500000)
    assert len(high_context) > 0, "Should find models with 500K+ context"
    print(f"  Found {len(high_context)} models with 500K+ context window")

    print("✓ Capability-based search works correctly")


def test_cost_optimization():
    """Test 4: Cost optimization works."""
    print("\n=== Test 4: Cost Optimization ===")

    # Find cheapest model with structured outputs
    cheapest = get_cheapest_model(['structured_outputs'])

    if cheapest:
        info = get_model_info(cheapest)
        print(f"  Cheapest model with structured_outputs: {cheapest}")
        print(f"    Cost: ${info['cost_per_1m_tokens']}/1M")
        print(f"    Provider: {info['provider']}")

        # Verify it's actually the cheapest
        all_structured = find_models_by_capabilities(['structured_outputs'])
        for model_name in all_structured:
            model_info = get_model_info(model_name)
            if is_model_available(model_name):
                assert info['cost_per_1m_tokens'] <= model_info['cost_per_1m_tokens'], \
                    "Should select the cheapest available model"

    print("✓ Cost optimization works correctly")


def test_model_availability():
    """Test 5: Model availability checks work."""
    print("\n=== Test 5: Model Availability ===")

    # All models should show as unavailable in test environment (no API keys)
    available = get_available_models()
    print(f"  Available models: {len(available)}")

    # Test that is_model_available works
    for model_name in MODEL_REGISTRY.keys():
        available = is_model_available(model_name)
        assert isinstance(available, bool), "is_model_available should return bool"

    print("✓ Model availability checks work")


def test_get_model_info():
    """Test 6: get_model_info function works."""
    print("\n=== Test 6: get_model_info() ===")

    # Test valid model
    info = get_model_info('gpt-4o-mini')
    assert info is not None, "Should find gpt-4o-mini"
    assert info['provider'] == 'openai', "Should be OpenAI provider"

    # Test invalid model
    info = get_model_info('invalid-model-name')
    assert info is None, "Should return None for invalid model"

    print("✓ get_model_info() works correctly")


def test_get_models_by_provider():
    """Test 7: get_models_by_provider function works."""
    print("\n=== Test 7: get_models_by_provider() ===")

    openai_models = get_models_by_provider('openai')
    assert len(openai_models) > 0, "Should find OpenAI models"
    assert 'gpt-4o-mini' in openai_models, "Should include gpt-4o-mini"

    google_models = get_models_by_provider('google')
    assert len(google_models) > 0, "Should find Google models"
    assert 'gemini-2.0-flash-exp' in google_models, "Should include gemini-2.0-flash-exp"

    print(f"  OpenAI models: {len(openai_models)}")
    print(f"  Google models: {len(google_models)}")
    print("✓ get_models_by_provider() works correctly")


def test_task_model_config():
    """Test 8: TASK_MODEL_CONFIG is properly defined."""
    print("\n=== Test 8: TASK_MODEL_CONFIG Structure ===")

    required_tasks = ['navigation', 'explain', 'research', 'long_document', 'draft', 'conversational', 'realtime_research']

    for task in required_tasks:
        assert task in TASK_MODEL_CONFIG, f"Missing task config: {task}"

        config = TASK_MODEL_CONFIG[task]
        assert 'strategy' in config, f"Task {task} missing strategy"
        assert 'required_capabilities' in config, f"Task {task} missing required_capabilities"
        assert 'reason' in config, f"Task {task} missing reason"
        assert 'fallback_model' in config, f"Task {task} missing fallback_model"

        strategy = config['strategy']
        assert strategy in ['explicit', 'cost_optimized'], f"Task {task} has invalid strategy: {strategy}"

        if strategy == 'explicit':
            assert 'model_priority' in config, f"Task {task} with explicit strategy needs model_priority"
            assert len(config['model_priority']) > 0, f"Task {task} has empty model_priority"

    print(f"✓ All {len(required_tasks)} task types are properly configured")


def test_model_routing():
    """Test 9: Model routing logic works (no API calls)."""
    print("\n=== Test 9: Model Routing Logic ===")

    # We can't fully test routing without API keys, but we can test the logic
    # by checking that it doesn't crash and returns fallback when no providers available

    try:
        # These should all return the fallback model since no API keys in test
        for task_type in ['navigation', 'research', 'draft', 'long_document']:
            provider = get_model_for_task(task_type)
            assert provider is not None, f"Should return provider for {task_type}"
            print(f"  {task_type}: fallback to {provider.default_model}")

        print("✓ Model routing logic works correctly")
    except Exception as e:
        print(f"✗ Model routing failed: {e}")
        raise


def test_backward_compatibility():
    """Test 10: Backward compatibility with old API."""
    print("\n=== Test 10: Backward Compatibility ===")

    # get_provider_for_task should still work
    from llm_provider import get_provider_for_task

    try:
        provider = get_provider_for_task('navigation')
        assert provider is not None, "Legacy API should still work"
        print("✓ get_provider_for_task() still works (backward compatible)")
    except Exception as e:
        print(f"✗ Backward compatibility broken: {e}")
        raise


def test_model_first_vs_provider_first():
    """Test 11: Compare model-first vs provider-first results."""
    print("\n=== Test 11: Model-First vs Provider-First Comparison ===")

    # Both should work and return providers (though possibly different ones)
    try:
        from llm_provider import get_provider_for_task

        old_provider = get_provider_for_task('navigation')
        new_provider = get_model_for_task('navigation')

        print(f"  Old API (provider-first): {old_provider.name} / {old_provider.default_model}")
        print(f"  New API (model-first): {new_provider.name} / {new_provider.default_model}")
        print("✓ Both APIs return valid providers")
    except Exception as e:
        print(f"✗ Comparison failed: {e}")
        raise


def run_all_tests():
    """Run all tests."""
    print("=" * 70)
    print("Model Registry Test Suite (Session 74)")
    print("=" * 70)

    tests = [
        test_model_registry_structure,
        test_provider_references,
        test_capability_search,
        test_cost_optimization,
        test_model_availability,
        test_get_model_info,
        test_get_models_by_provider,
        test_task_model_config,
        test_model_routing,
        test_backward_compatibility,
        test_model_first_vs_provider_first
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"\n✗ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n✗ ERROR: {e}")
            failed += 1

    print("\n" + "=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
