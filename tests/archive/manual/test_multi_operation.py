#!/usr/bin/env python3
"""
Quick test for multi-operation navigation logic (Session 57.5)

Tests:
1. Single operation (backward compatible)
2. Multi-operation OR query
"""

import json
from unittest.mock import Mock, patch
from civic_services.civic_chat_router import ChatRouter

def test_single_operation():
    """Test single operation (backward compatible)"""
    print("TEST 1: Single operation query")
    print("=" * 60)

    # Mock OpenAI response with single operation
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps({
        "operations": [
            {
                "type": "search_events",
                "filters": {
                    "jurisdiction": "berkeley",
                    "topic": "housing",
                    "dateRange": None,
                    "searchQuery": None,
                    "level": None
                },
                "target": None,
                "question": None,
                "options": None
            }
        ]
    })
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 150

    # Create router and mock OpenAI client
    router = ChatRouter()
    with patch.object(router.client.chat.completions, 'create', return_value=mock_response):
        result = router.handle_navigation_mode(
            message="Find housing meetings in Berkeley",
            context={'user_city': 'oakland'}
        )

    # Verify result
    print(f"Action: {result['action']}")
    print(f"Parameters: {result['parameters']}")
    print(f"Multi-operation: {result.get('multi_operation', False)}")

    assert result['action'] == 'search_events'
    assert result['parameters']['jurisdiction'] == 'city-berkeley'
    assert result['parameters']['topic'] == 'housing'
    assert 'multi_operation' not in result or result['multi_operation'] == False

    print("✓ PASSED: Single operation works correctly\n")


def test_multi_operation():
    """Test multi-operation OR query"""
    print("TEST 2: Multi-operation OR query")
    print("=" * 60)

    # Mock OpenAI response with 2 operations
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps({
        "operations": [
            {
                "type": "search_events",
                "filters": {
                    "jurisdiction": "berkeley",
                    "topic": "housing",
                    "dateRange": None,
                    "searchQuery": None,
                    "level": None
                },
                "target": None,
                "question": None,
                "options": None
            },
            {
                "type": "search_events",
                "filters": {
                    "jurisdiction": "concord",
                    "topic": "transportation",
                    "dateRange": None,
                    "searchQuery": None,
                    "level": None
                },
                "target": None,
                "question": None,
                "options": None
            }
        ]
    })
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 150
    mock_response.usage.completion_tokens = 100
    mock_response.usage.total_tokens = 250

    # Create router and mock OpenAI client
    router = ChatRouter()
    with patch.object(router.client.chat.completions, 'create', return_value=mock_response):
        result = router.handle_navigation_mode(
            message="Find housing in Berkeley OR transportation in Concord",
            context={'user_city': 'oakland'}
        )

    # Verify result
    print(f"Action: {result['action']}")
    print(f"Parameters: {result['parameters']}")
    print(f"Multi-operation: {result.get('multi_operation', False)}")
    print(f"Operation count: {result.get('operation_count', 0)}")
    print(f"Total operations: {len(result.get('all_operations', []))}")

    # Primary operation should be first (Berkeley housing)
    assert result['action'] == 'search_events'
    assert result['parameters']['jurisdiction'] == 'city-berkeley'
    assert result['parameters']['topic'] == 'housing'

    # Multi-operation metadata should be present
    assert result.get('multi_operation') == True
    assert result.get('operation_count') == 2
    assert len(result.get('all_operations', [])) == 2

    # Second operation should be Concord transportation
    second_op = result['all_operations'][1]
    assert second_op['action'] == 'search_events'
    assert second_op['parameters']['jurisdiction'] == 'city-concord'
    assert second_op['parameters']['topic'] == 'transportation'

    print("✓ PASSED: Multi-operation works correctly\n")


def test_topic_normalization():
    """Test topic synonym normalization (e.g., 'zoning' → 'housing')"""
    print("TEST 3: Topic normalization")
    print("=" * 60)

    # Mock OpenAI response with synonym topic
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = json.dumps({
        "operations": [
            {
                "type": "search_events",
                "filters": {
                    "jurisdiction": "berkeley",
                    "topic": "zoning",  # Synonym for housing
                    "dateRange": None,
                    "searchQuery": None,
                    "level": None
                },
                "target": None,
                "question": None,
                "options": None
            }
        ]
    })
    mock_response.usage = Mock()
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 150

    # Create router and mock OpenAI client
    router = ChatRouter()
    with patch.object(router.client.chat.completions, 'create', return_value=mock_response):
        result = router.handle_navigation_mode(
            message="Find zoning meetings in Berkeley",
            context={'user_city': 'oakland'}
        )

    # Verify result
    print(f"Action: {result['action']}")
    print(f"Topic (normalized): {result['parameters']['topic']}")

    assert result['action'] == 'search_events'
    assert result['parameters']['topic'] == 'housing'  # Should be normalized

    print("✓ PASSED: Topic normalization works correctly\n")


if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("MULTI-OPERATION NAVIGATION TESTS (Session 57.5)")
    print("=" * 60 + "\n")

    try:
        test_single_operation()
        test_multi_operation()
        test_topic_normalization()

        print("=" * 60)
        print("ALL TESTS PASSED ✓")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        raise
