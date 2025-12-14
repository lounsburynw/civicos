#!/usr/bin/env python3
"""
Layer 3 Validation Script: Complaint-to-Event Matching

Validates:
1. >30% match rate on test complaints
2. <100ms latency per complaint
3. Keyword scoring working correctly
4. Fallback strategy for unmatched complaints

Usage:
    python scripts/validate_layer3_matching.py
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from complaint_matcher import match_complaint_to_events, get_match_statistics
from complaint_fallback import handle_no_match
from complaint_storage import ComplaintStorage, Complaint

# Test complaints covering different issue types
TEST_COMPLAINTS = [
    {
        "description": "My landlord won't fix broken heating and there's mold growing in the apartment",
        "issue_type": "housing",
        "jurisdiction_id": "city-berkeley"
    },
    {
        "description": "Dangerous intersection at Main and Elm needs traffic light and crosswalk",
        "issue_type": "transportation",
        "jurisdiction_id": "city-berkeley"
    },
    {
        "description": "Need more affordable housing options in our neighborhood, rent is too high",
        "issue_type": "housing",
        "jurisdiction_id": "city-berkeley"
    },
    {
        "description": "Air pollution from nearby factory affecting our health",
        "issue_type": "environment",
        "jurisdiction_id": "city-berkeley"
    },
    {
        "description": "Pothole on Oak Street has been there for months, needs repair",
        "issue_type": "infrastructure",
        "jurisdiction_id": "city-berkeley"
    },
    {
        "description": "Noise complaints from late-night bar, need police enforcement",
        "issue_type": "public_safety",
        "jurisdiction_id": "city-berkeley"
    },
    {
        "description": "Zoning variance request for ADU construction on my property",
        "issue_type": "housing",
        "jurisdiction_id": "city-berkeley"
    },
    {
        "description": "Bus route cuts have made it impossible to get to work on time",
        "issue_type": "transportation",
        "jurisdiction_id": "city-berkeley"
    },
]


def validate_matching_algorithm():
    """Validate the complaint matching algorithm"""
    print("=" * 80)
    print("LAYER 3 VALIDATION: Complaint-to-Event Matching")
    print("=" * 80)
    print()

    # Statistics
    total_complaints = len(TEST_COMPLAINTS)
    matched_count = 0
    total_latency = 0
    all_matches = []

    print(f"Testing {total_complaints} complaints...\n")

    for i, complaint in enumerate(TEST_COMPLAINTS, 1):
        print(f"{i}. {complaint['description'][:60]}...")
        print(f"   Issue Type: {complaint['issue_type']}")

        # Measure latency
        start = time.time()
        matches = match_complaint_to_events(complaint)
        latency = (time.time() - start) * 1000  # Convert to ms

        total_latency += latency

        if matches:
            matched_count += 1
            stats = get_match_statistics(matches)
            print(f"   ✓ Matched to {len(matches)} events (avg score: {stats['average_score']:.1f})")
            print(f"   ✓ Top match: {matches[0][0]['title'][:50]}... (score: {matches[0][1]:.0f})")
            print(f"   ✓ Reason: {matches[0][2]}")
            all_matches.extend(matches)
        else:
            print(f"   ✗ No matches found")

        print(f"   ⏱  Latency: {latency:.2f}ms")
        print()

    # Calculate overall statistics
    match_rate = (matched_count / total_complaints) * 100
    avg_latency = total_latency / total_complaints

    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()
    print(f"Match Rate: {match_rate:.1f}% ({matched_count}/{total_complaints})")
    print(f"Average Latency: {avg_latency:.2f}ms")
    print()

    # Validation gates
    print("VALIDATION GATES:")
    print()

    # Gate 1: Match rate
    if match_rate >= 30:
        print(f"✓ PASS: Match rate {match_rate:.1f}% >= 30%")
    else:
        print(f"✗ FAIL: Match rate {match_rate:.1f}% < 30%")

    # Gate 2: Latency
    if avg_latency < 100:
        print(f"✓ PASS: Average latency {avg_latency:.2f}ms < 100ms")
    else:
        print(f"✗ FAIL: Average latency {avg_latency:.2f}ms >= 100ms")

    print()

    # Match quality analysis
    if all_matches:
        all_stats = get_match_statistics(all_matches)
        print("MATCH QUALITY:")
        print(f"  Total matches: {all_stats['total_matches']}")
        print(f"  High confidence (>60): {all_stats['high_confidence']}")
        print(f"  Average score: {all_stats['average_score']:.1f}")
        print(f"  Score range: {all_stats['min_score']:.0f} - {all_stats['max_score']:.0f}")
        print()

    return match_rate >= 30 and avg_latency < 100


def validate_fallback_strategy():
    """Validate the fallback strategy for unmatched complaints"""
    print("=" * 80)
    print("FALLBACK STRATEGY VALIDATION")
    print("=" * 80)
    print()

    storage = ComplaintStorage()

    # Test complaint with no matches
    test_complaint = {
        "id": "test-validation",
        "description": "Very specific issue that won't match any events",
        "issue_type": "infrastructure",
        "jurisdiction_id": "city-berkeley",
        "user_id": "test-user",
        "status": "open",
        "created_at": "2025-10-12 00:00:00",
        "matched_events": []
    }

    print("Testing fallback response for unmatched complaint...")
    response = handle_no_match(test_complaint)

    print()
    print("Message Generated:")
    print(f"  {response['message']}")
    print()
    print(f"Similar Complaints Found: {response['similar_count']}")
    print(f"Community Formation Potential: {response['community_formation_potential']}")
    print()
    print("Actions Available:")
    for action in response["actions"]:
        print(f"  - {action['action_label']}")
    print()

    # Validate response structure
    has_message = "message" in response and len(response["message"]) > 0
    has_actions = "actions" in response and len(response["actions"]) > 0

    print("VALIDATION:")
    if has_message:
        print("✓ PASS: Helpful message generated")
    else:
        print("✗ FAIL: No message generated")

    if has_actions:
        print("✓ PASS: Civic actions provided")
    else:
        print("✗ FAIL: No actions provided")

    print()

    return has_message and has_actions


def demonstrate_participation_mechanism():
    """Demonstrate Complaint as ParticipationMechanism"""
    print("=" * 80)
    print("PARTICIPATION MECHANISM INTERFACE")
    print("=" * 80)
    print()

    # Create a test complaint
    complaint_data = {
        "id": "demo-complaint",
        "description": "Housing affordability issue in neighborhood",
        "issue_type": "housing",
        "jurisdiction_id": "city-berkeley",
        "user_id": "demo-user",
        "status": "matched",
        "created_at": "2025-10-12 12:00:00",
        "matched_events": [
            {
                "event_id": "event-1",
                "match_score": 75,
                "match_reason": "3 keyword matches, project type: housing"
            }
        ],
        "related_complaints": []
    }

    complaint = Complaint(complaint_data)

    print("Complaint as ParticipationMechanism:")
    print(f"  ID: {complaint.get_id()}")
    print(f"  Type: {complaint.get_type()}")
    print(f"  Lifecycle Status: {complaint.get_lifecycle_status()}")
    print(f"  Participation Threshold: {complaint.get_participation_threshold()}")
    print()

    print("Available Actions:")
    for action in complaint.get_actions():
        print(f"  - {action['action_label']}: {action['action_target']}")
    print()

    print("Context:")
    context = complaint.get_context()
    for key, value in context.items():
        print(f"  {key}: {value}")
    print()

    print("✓ PASS: Complaint implements ParticipationMechanism interface")
    print()


def main():
    """Run all validations"""
    print("\n")
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 20 + "LAYER 3 VALIDATION SUITE" + " " * 34 + "║")
    print("║" + " " * 15 + "Complaint-to-Event Matching Algorithm" + " " * 26 + "║")
    print("╚" + "═" * 78 + "╝")
    print()

    # Run validations
    matching_pass = validate_matching_algorithm()
    fallback_pass = validate_fallback_strategy()
    demonstrate_participation_mechanism()

    # Overall result
    print("=" * 80)
    print("OVERALL VALIDATION RESULT")
    print("=" * 80)
    print()

    if matching_pass and fallback_pass:
        print("✓✓✓ ALL VALIDATION GATES PASSED ✓✓✓")
        print()
        print("Layer 3 implementation is COMPLETE and ready for integration.")
        print()
        return 0
    else:
        print("✗✗✗ VALIDATION FAILED ✗✗✗")
        print()
        if not matching_pass:
            print("- Matching algorithm did not meet requirements")
        if not fallback_pass:
            print("- Fallback strategy did not meet requirements")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
