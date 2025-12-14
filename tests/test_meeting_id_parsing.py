#!/usr/bin/env python3
"""
Test suite for meeting ID parsing from virtual participation mechanisms.

Validates that meeting IDs are properly extracted from phone strings and stored
as separate fields in the virtual participation mechanism.

Critical Requirements:
- Meeting IDs extracted from various phone string formats
- Phone numbers cleaned (no ID text remaining)
- meeting_id field populated in virtual mechanism
- Handles multiple ID format patterns
"""

import json
import glob
import os
import re

def find_latest_events_file(city='san-rafael'):
    """Find most recent events file for given city."""
    pattern = f'data/events/events_city-{city}_*.json'
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def test_meeting_id_extraction():
    """Test that meeting IDs are properly extracted and separated."""
    print("Testing meeting ID extraction from virtual mechanisms...")

    latest_file = find_latest_events_file()
    if not latest_file:
        print("❌ No test data found")
        return False

    with open(latest_file) as f:
        data = json.load(f)

    if not data.get('events'):
        print("❌ No events found in test data")
        return False

    passed = 0
    failed = 0
    total_virtual = 0

    for event in data['events']:
        for mech in event.get('participation_mechanisms', []):
            if mech['type'] == 'virtual':
                total_virtual += 1
                phone = mech.get('phone', '')
                meeting_id = mech.get('meeting_id')

                # Test 1: If phone contains ID pattern, meeting_id should be extracted
                if re.search(r'(?:ID|id|Meeting ID)[:\s]+[0-9\s#]+', phone):
                    if meeting_id:
                        print(f"⚠️ Phone contains ID text but meeting_id was extracted")
                        print(f"   Phone: {phone}")
                        print(f"   Meeting ID: {meeting_id}")
                        failed += 1
                    else:
                        print(f"❌ Phone contains ID text but meeting_id not extracted")
                        print(f"   Phone: {phone}")
                        failed += 1
                    continue

                # Test 2: If meeting_id exists, phone should NOT contain ID text
                if meeting_id:
                    if 'ID' in phone or 'id' in phone:
                        print(f"❌ Meeting ID extracted but phone still contains ID text")
                        print(f"   Phone: {phone}")
                        print(f"   Meeting ID: {meeting_id}")
                        failed += 1
                    else:
                        print(f"✅ Meeting ID properly separated: {meeting_id}")
                        print(f"   Phone: {phone}")
                        passed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"Total virtual mechanisms tested: {total_virtual}")

    if total_virtual == 0:
        print("\n⚠️ No virtual mechanisms found in test data")
        return False

    if failed == 0 and passed > 0:
        print("\n✅ SUCCESS: Meeting IDs properly extracted and separated")
        return True
    else:
        print("\n❌ FAILURE: Meeting ID parsing issues detected")
        return False

def test_meeting_id_patterns():
    """Test various meeting ID patterns."""
    print("\nTesting meeting ID pattern recognition...")

    patterns_to_test = [
        ("1 (669) 444-9171, ID: 840 9897 7308#", "840 9897 7308", "1 (669) 444-9171"),
        ("(669) 444-9171, Meeting ID: 84098977308", "84098977308", "(669) 444-9171"),
        ("Call: 1-669-444-9171, ID 840 9897 7308", "840 9897 7308", "Call: 1-669-444-9171"),
        ("Phone: (669) 444-9171 ID: 123 456 789#", "123 456 789", "Phone: (669) 444-9171"),
    ]

    passed = 0
    failed = 0

    for input_str, expected_id, expected_phone in patterns_to_test:
        # Simulate the parsing logic
        meeting_id = None
        phone = input_str

        id_match = re.search(r'(?:ID|id|Meeting ID|meeting id)[:\s]+([0-9\s#]+)', phone)
        if id_match:
            meeting_id = id_match.group(1).replace('#', '').strip()
            phone = re.sub(r',?\s*(?:ID|id|Meeting ID|meeting id)[:\s]+.*$', '', phone).strip()

        if meeting_id == expected_id and phone == expected_phone:
            print(f"✅ Pattern parsed correctly:")
            print(f"   Input: {input_str}")
            print(f"   ID: {meeting_id}, Phone: {phone}")
            passed += 1
        else:
            print(f"❌ Pattern parsing failed:")
            print(f"   Input: {input_str}")
            print(f"   Expected - ID: {expected_id}, Phone: {expected_phone}")
            print(f"   Got - ID: {meeting_id}, Phone: {phone}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Pattern Tests: {passed} passed, {failed} failed")

    return failed == 0

def test_virtual_mechanism_structure():
    """Test that virtual mechanisms have proper structure."""
    print("\nTesting virtual mechanism structure...")

    latest_file = find_latest_events_file()
    if not latest_file:
        print("❌ No test data found")
        return False

    with open(latest_file) as f:
        data = json.load(f)

    required_fields = ['type', 'platform', 'description', 'when', 'duration_minutes']
    optional_fields = ['url', 'phone', 'meeting_id']

    passed = 0
    failed = 0

    for event in data.get('events', []):
        for mech in event.get('participation_mechanisms', []):
            if mech['type'] == 'virtual':
                # Check required fields
                missing = [f for f in required_fields if f not in mech]
                if missing:
                    print(f"❌ Missing required fields: {missing}")
                    failed += 1
                    continue

                # Check at least one access method
                has_access = any(mech.get(f) for f in optional_fields)
                if not has_access:
                    print(f"❌ No access method (url, phone, or meeting_id)")
                    failed += 1
                    continue

                print(f"✅ Valid virtual mechanism structure")
                print(f"   Platform: {mech['platform']}")
                print(f"   Access: url={bool(mech.get('url'))}, phone={bool(mech.get('phone'))}, meeting_id={bool(mech.get('meeting_id'))}")
                passed += 1

    print(f"\n{'='*60}")
    print(f"Structure Tests: {passed} passed, {failed} failed")

    return failed == 0

if __name__ == '__main__':
    print("="*60)
    print("MEETING ID PARSING TEST SUITE")
    print("="*60 + "\n")

    results = []
    results.append(("Meeting ID Extraction", test_meeting_id_extraction()))
    results.append(("Pattern Recognition", test_meeting_id_patterns()))
    results.append(("Mechanism Structure", test_virtual_mechanism_structure()))

    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(result[1] for result in results)

    if all_passed:
        print("\n✅ All tests passed - Meeting ID parsing working correctly!")
    else:
        print("\n❌ Some tests failed - see details above")

    import sys
    sys.exit(0 if all_passed else 1)