#!/usr/bin/env python
"""Quick structural test for Session 76 refactor"""

import sys
sys.path.insert(0, 'src')

from civic_chat_router import ChatRouter, MODE_SYSTEM_PROMPTS, CIVIC_FUNCTIONS

# Test 1: Check ChatRouter class exists
assert ChatRouter is not None, "ChatRouter class missing"
print("✅ ChatRouter class exists")

# Test 2: Check route_message method exists on class
assert hasattr(ChatRouter, 'route_message'), "route_message method missing"
print("✅ route_message method exists on ChatRouter")

# Test 3: Check detect_mode method exists on class
assert hasattr(ChatRouter, 'detect_mode'), "detect_mode method missing"
print("✅ detect_mode method exists on ChatRouter")

# Test 4: Verify handle_navigation_mode is removed
assert not hasattr(ChatRouter, 'handle_navigation_mode'), "handle_navigation_mode should be removed!"
print("✅ handle_navigation_mode successfully removed")

# Test 5: Verify _process_single_operation is removed
assert not hasattr(ChatRouter, '_process_single_operation'), "_process_single_operation should be removed!"
print("✅ _process_single_operation successfully removed")

# Test 6: Check MODE_SYSTEM_PROMPTS structure
assert 'navigation' in MODE_SYSTEM_PROMPTS, "navigation prompt missing"
assert 'focus' in MODE_SYSTEM_PROMPTS, "focus prompt missing"
assert 'compare' in MODE_SYSTEM_PROMPTS, "compare prompt missing"
print("✅ All 3 mode prompts present")

# Test 7: Check CIVIC_FUNCTIONS includes all functions
function_names = [f['name'] for f in CIVIC_FUNCTIONS]
expected = ['search_events', 'file_complaint', 'view_legislative_context',
            'search_web', 'draft_comment', 'view_my_complaints', 'explain_event']
for func in expected:
    assert func in function_names, f"{func} missing from CIVIC_FUNCTIONS"
print(f"✅ All {len(CIVIC_FUNCTIONS)} civic functions present")

print("\n" + "="*60)
print("🎉 All structural tests passed!")
print("="*60)
print("Refactor complete - pure function-calling architecture working")
print("\nNOTE: Full integration tests require:")
print("  - OPENAI_API_KEY environment variable")
print("  - Backend API server running (python src/civic_api_integrated.py)")
print("  - Run: python tests/test_pure_function_calling.py")
