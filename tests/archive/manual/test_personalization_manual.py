#!/usr/bin/env python3
"""
Manual test script for PersonalizationService
Run this before writing comprehensive unit tests to verify basic functionality
"""

from civic_services.personalization_service import PersonalizationService
import sqlite3

service = PersonalizationService('data/civic_participation.db')

print("=== Manual PersonalizationService Tests ===\n")

# Test 1: Create profile
print("Test 1: Create user profile...")
profile = service.create_user_profile('test_user_001', {
    'jurisdictionId': 'city-berkeley',
    'displayName': 'Test User',
    'stakes': ['homeowner', 'parent'],
    'yearsInArea': 15,
    'civicInterests': ['housing', 'transportation'],
    'district': 'District 4',
    'expertise': 'Urban planning background'
})
assert profile['user_id'] == 'test_user_001'
assert profile['profile_completeness'] > 0
print(f"✅ Profile created: {profile['user_id']}, completeness: {profile['profile_completeness']}%")
print(f"   Stakes: {profile['stakes']}")
print(f"   Interests: {profile['civic_interests']}\n")

# Test 2: Retrieve profile
print("Test 2: Retrieve user profile...")
retrieved = service.get_user_profile('test_user_001')
assert retrieved['user_id'] == 'test_user_001'
assert retrieved['display_name'] == 'Test User'
print(f"✅ Profile retrieved: {retrieved['display_name']}\n")

# Test 3: Track action
print("Test 3: Track civic action...")
action_id = service.track_action(
    'test_user_001',
    'event_clicked',
    'event',
    'event-berkeley-planning-123',
    {'topic': 'housing', 'jurisdictionId': 'city-berkeley'}
)
print(f"✅ Action tracked: {action_id}\n")

# Test 4: Get civic history
print("Test 4: Get civic history...")
history = service.get_civic_history('test_user_001')
assert len(history) == 1
assert history[0]['action_type'] == 'event_clicked'
print(f"✅ Civic history retrieved: {len(history)} action(s)")
print(f"   Latest: {history[0]['action_type']} on {history[0]['entity_id']}\n")

# Test 5: Infer interests (track multiple housing actions first)
print("Test 5: Track multiple actions and infer interests...")
for i in range(10):
    service.track_action(
        'test_user_001',
        'event_clicked',
        'event',
        f'event-housing-{i}',
        {'topic': 'housing', 'jurisdictionId': 'city-berkeley'}
    )
# Add some transportation actions
for i in range(5):
    service.track_action(
        'test_user_001',
        'event_clicked',
        'event',
        f'event-transport-{i}',
        {'topic': 'transportation', 'jurisdictionId': 'city-berkeley'}
    )

interests = service.infer_civic_interests('test_user_001')
print(f"✅ Interests inferred: {interests}")
assert 'housing' in interests
assert interests['housing'] > 0.5  # Housing should have higher score
print(f"   Housing score: {interests.get('housing', 0):.2f}")
print(f"   Transportation score: {interests.get('transportation', 0):.2f}\n")

# Test 6: Get context for AI
print("Test 6: Get AI context (demographics only)...")
context = service.get_context_for_ai('test_user_001', context_type='demographics')
assert 'stakes' in context
assert 'yearsInArea' in context
print(f"✅ Context retrieved: {list(context.keys())}")
print(f"   Stakes: {context['stakes']}")
print(f"   Years: {context['yearsInArea']}\n")

print("Test 7: Get AI context (full)...")
full_context = service.get_context_for_ai('test_user_001', context_type='full')
assert 'stakes' in full_context
assert 'inferredInterests' in full_context
assert 'recentActions' in full_context
print(f"✅ Full context retrieved: {list(full_context.keys())}")
print(f"   Recent actions count: {len(full_context['recentActions'])}\n")

# Test 8: Cache behavior
print("Test 8: Test cache behavior...")
# Clear cache
service.cache.clear()
# First call should hit database
profile1 = service.get_user_profile('test_user_001')
# Second call should hit cache
profile2 = service.get_user_profile('test_user_001')
assert profile1 == profile2
assert 'test_user_001' in service.cache
print(f"✅ Cache working correctly (user in cache: {'test_user_001' in service.cache})\n")

# Clean up
print("Cleaning up test data...")
conn = sqlite3.connect('data/civic_participation.db')
conn.execute("DELETE FROM user_profiles WHERE user_id = 'test_user_001'")
conn.commit()
conn.close()
print("✅ Test cleanup complete\n")

print("=== All Manual Tests Passed! ===")
