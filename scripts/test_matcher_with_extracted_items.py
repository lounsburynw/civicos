"""
Test operational→policy matching with extracted October 6 agenda items

This validates that operational complaints can match to detailed budget items.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from operational_agenda_matcher import OperationalAgendaMatcher
import json

def test_matcher():
    """Test matching operational issues to extracted agenda items"""

    print("=" * 80)
    print("Testing Operational → Policy Matcher with Real Agenda Items")
    print("=" * 80)

    # Load extracted agenda items
    with open('data/test_extraction_results.json', 'r') as f:
        extraction_data = json.load(f)

    print(f"\nLoaded {extraction_data['total_items']} agenda items from October 6 extraction")

    # Create test operational issues (based on San Rafael SeeClickFix data)
    # Using 'category' field as expected by matcher
    operational_issues = [
        {
            'id': 1,
            'category': 'Stormwater',
            'description': 'Storm drain clogged with debris on Knight Drive',
            'address': 'Knight Dr, San Rafael, CA'
        },
        {
            'id': 2,
            'category': 'Pothole',
            'description': 'Large pothole on Anderson Drive needs repair',
            'address': 'Anderson Dr, San Rafael, CA'
        },
        {
            'id': 3,
            'category': 'Illegal Dumping',
            'description': 'Trash and furniture dumped near creek',
            'address': 'San Rafael, CA'
        },
        {
            'id': 4,
            'category': 'Tree Maintenance',
            'description': 'Overgrown vegetation creating fire hazard',
            'address': 'San Rafael, CA'
        },
        {
            'id': 5,
            'category': 'Street Sign/Markings',
            'description': 'Faded crosswalk markings need repainting',
            'address': 'Downtown San Rafael, CA'
        }
    ]

    # Create agenda items list from extracted data
    # Using 'project_type' (primary type) as expected by matcher
    agenda_items = [
        {
            'item_ref': item['ref'],
            'title': item['title'],
            'description': item['description'],
            'project_type': item['types'][0] if item['types'] else 'governance'  # Use primary type
        }
        for item in extraction_data['items']
    ]

    # Initialize matcher
    print("\nInitializing matcher...")
    matcher = OperationalAgendaMatcher()

    # Test each operational issue
    print("\nTesting matches:\n")
    total_matches = 0

    for issue in operational_issues:
        print(f"Issue #{issue['id']}: {issue['category']} - {issue['description'][:60]}...")

        matches = matcher.match_issue_to_agendas(issue, agenda_items)

        if matches:
            total_matches += len(matches)
            print(f"  ✓ Found {len(matches)} match(es):")
            for match in matches:
                item = match['agenda_item']
                print(f"    • Item {item['item_ref']}: {item['title'][:60]}...")
                print(f"      Confidence: {match['confidence']}")
                print(f"      Reason: {match['reasoning'][:80]}...")
        else:
            print(f"  ✗ No matches found")
        print()

    # Summary
    print("=" * 80)
    match_rate = (total_matches / len(operational_issues)) * 100
    print(f"RESULTS: {total_matches} total matches across {len(operational_issues)} issues ({match_rate:.0f}% average)")
    print("=" * 80)

    # Expected matches based on agenda content:
    # - Stormwater → Environmental consulting (5.b) or Wildfire prevention (5.g)
    # - Pothole → Infrastructure items
    # - Illegal Dumping → Environmental items
    # - Tree Maintenance → Wildfire prevention (5.g, 7.b)
    # - Street Signs → Infrastructure items

    if total_matches >= 3:
        print("✓ PASS: Matcher successfully connects operational issues to policy items")
        return True
    else:
        print("⚠️  WARNING: Low match rate - may need tuning")
        return False

if __name__ == '__main__':
    success = test_matcher()
    sys.exit(0 if success else 1)
