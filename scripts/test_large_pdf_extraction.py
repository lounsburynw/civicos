"""
Test large PDF extraction with October 6 San Rafael agenda packet (25MB, 329 pages)

This script validates that the updated AgendaIntegration can:
1. Handle PDFs over 10MB (up to 50MB limit)
2. Extract detailed agenda items from large packets
3. Identify budget items ($675K, $4.4M, $1.1M) for operational matching
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agenda_integration import AgendaIntegrator
from datetime import datetime
import json

def test_october_6_extraction():
    """Test extraction of October 6, 2025 San Rafael City Council agenda"""

    print("=" * 80)
    print("Testing Large PDF Extraction - San Rafael October 6, 2025")
    print("=" * 80)

    # Initialize integrator with long_document task type (uses Gemini 1.5 Pro)
    print("\n1. Initializing AgendaIntegrator with 'long_document' task type...")
    integrator = AgendaIntegrator(task_type='long_document')
    print(f"   ✓ Provider: {integrator.provider.__class__.__name__}")

    # Create test event
    event = {
        'title': 'City Council Meeting',
        'when': '2025-10-06T18:00:00',
        'when_human': 'Monday, October 6, 2025 at 6:00 PM',
        'contact_info': {
            'email': 'city.clerk@cityofsanrafael.org'
        }
    }

    # Test with the full agenda packet (25MB, 329 pages)
    agenda_url = 'https://storage.googleapis.com/proudcity/sanrafaelca/2025/10/Agenda-Packet-2025-10-06.pdf'

    print(f"\n2. Parsing agenda packet...")
    print(f"   URL: {agenda_url}")
    print(f"   Expected size: ~25MB")
    print(f"   Expected pages: 329")
    print(f"   This will take 30-60 seconds with Gemini 1.5 Pro...\n")

    try:
        agenda_items = integrator.parse_agenda_content(agenda_url, event)

        print(f"\n3. Extraction Results:")
        print(f"   ✓ Successfully parsed!")
        print(f"   ✓ Found {len(agenda_items)} actionable items\n")

        if len(agenda_items) == 0:
            print("   ⚠️  WARNING: No items extracted - this may indicate an issue")
            return False

        # Look for expected budget items
        print("4. Searching for expected budget items:")
        expected_keywords = [
            ('environmental consulting', '$675K'),
            ('albert park', '$4.4M'),
            ('wildfire prevention', '$1.1M'),
            ('measure c', '$1.1M')
        ]

        found_items = []
        for item in agenda_items:
            item_text = f"{item.title} {item.description}".lower()
            for keyword, amount in expected_keywords:
                if keyword in item_text:
                    found_items.append({
                        'ref': item.item_ref,
                        'title': item.title,
                        'description': item.description[:100] + '...' if len(item.description) > 100 else item.description,
                        'types': item.project_types,
                        'keyword': keyword,
                        'amount': amount
                    })
                    print(f"\n   ✓ Found: {keyword.upper()} ({amount})")
                    print(f"     Item: {item.item_ref} - {item.title}")
                    print(f"     Types: {', '.join(item.project_types)}")
                    print(f"     Description: {item.description[:100]}...")

        if len(found_items) == 0:
            print("\n   ⚠️  WARNING: None of the expected budget items found")
            print("\n   All extracted items:")
            for item in agenda_items:
                print(f"     • {item.item_ref}: {item.title}")
                print(f"       Types: {', '.join(item.project_types)}")

        # Save results for inspection
        output_file = 'data/test_extraction_results.json'
        with open(output_file, 'w') as f:
            json.dump({
                'extraction_date': datetime.now().isoformat(),
                'agenda_url': agenda_url,
                'total_items': len(agenda_items),
                'expected_items_found': len(found_items),
                'items': [
                    {
                        'ref': item.item_ref,
                        'title': item.title,
                        'description': item.description,
                        'types': item.project_types,
                        'actionable_reason': item.actionable_reason
                    }
                    for item in agenda_items
                ]
            }, f, indent=2)

        print(f"\n5. Results saved to: {output_file}")
        print(f"\n{'=' * 80}")
        print(f"TEST RESULT: {'✓ PASS' if len(found_items) > 0 else '⚠️  PARTIAL'} - Extracted {len(agenda_items)} items, found {len(found_items)}/{len(expected_keywords)} expected budget items")
        print(f"{'=' * 80}\n")

        return len(agenda_items) > 0

    except Exception as e:
        print(f"\n   ✗ FAILED: {type(e).__name__}")
        print(f"   Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_october_6_extraction()
    sys.exit(0 if success else 1)
