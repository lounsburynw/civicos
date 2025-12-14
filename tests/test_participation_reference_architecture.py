#!/usr/bin/env python3
"""
Test suite for participation mechanism reference architecture.

Validates that agenda items reference parent opportunity participation mechanisms
instead of duplicating them, eliminating data redundancy.

Critical Architecture:
- Event-level events contain participation_mechanisms (single source of truth)
- Agenda items contain opportunity_id reference (NOT participation_mechanisms)
- Frontend resolves mechanisms via opportunity_id lookup
"""

import json
import glob
import os
import sys

def find_latest_events_file(city='san-rafael'):
    """Find most recent events file for given city."""
    pattern = f'data/events/events_city-{city}_*.json'
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def test_reference_architecture():
    """Test that agenda items use reference architecture, not duplication."""
    print("Testing participation mechanism reference architecture...")

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

    for event in data['events']:
        # Check event has participation mechanisms
        if 'participation_mechanisms' not in event:
            print(f"❌ Event {event.get('id')} missing participation_mechanisms")
            failed += 1
            continue

        # Check agenda items if present
        if 'agenda_expansion' in event and event['agenda_expansion']:
            items = event['agenda_expansion'].get('actionable_items', [])

            for item in items:
                # MUST have opportunity_id
                if 'opportunity_id' not in item:
                    print(f"❌ Agenda item missing opportunity_id: {item.get('title')}")
                    failed += 1
                    continue

                # MUST NOT have participation_mechanisms
                if 'participation_mechanisms' in item:
                    print(f"❌ Agenda item has duplicated mechanisms: {item.get('title')}")
                    print(f"   This violates reference architecture!")
                    failed += 1
                    continue

                # Verify opportunity_id matches parent
                if item['opportunity_id'] != event['id']:
                    print(f"❌ opportunity_id mismatch: {item.get('title')}")
                    print(f"   Item: {item['opportunity_id']}")
                    print(f"   Event: {event['id']}")
                    failed += 1
                    continue

                passed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("\n✅ SUCCESS: Reference architecture correctly implemented")
        print("   - Agenda items reference parent via opportunity_id")
        print("   - No participation mechanism duplication")
        print("   - Single source of truth maintained")
        return True
    else:
        print("\n❌ FAILURE: Architecture violations detected")
        return False

def test_data_size_savings():
    """Calculate data size savings from reference architecture."""
    print("\nCalculating data size savings...")

    latest_file = find_latest_events_file()
    if not latest_file:
        print("❌ No test data found")
        return False

    with open(latest_file) as f:
        data = json.load(f)

    total_items = 0
    for event in data.get('events', []):
        if 'agenda_expansion' in event and event['agenda_expansion']:
            items = event['agenda_expansion'].get('actionable_items', [])
            total_items += len(items)

    # Estimate: 3 mechanisms × ~150 bytes each = 450 bytes per item
    estimated_savings = total_items * 450

    print(f"Total agenda items: {total_items}")
    print(f"Estimated data savings: ~{estimated_savings} bytes ({estimated_savings/1024:.1f} KB)")
    print(f"Per event (avg 9 items): ~4 KB")

    return True

def test_frontend_resolution_example():
    """Show how frontend should resolve participation mechanisms."""
    print("\nFrontend Resolution Pattern:")
    print("-" * 60)
    print("""
// Frontend code to resolve mechanisms from agenda items
function getParticipationMechanisms(agendaItem, allOpportunities) {
  const parentEvent = allOpportunities.find(
    o => o.id === agendaItem.opportunity_id
  );
  return parentEvent?.participation_mechanisms || [];
}

// Usage example
const agendaItem = {
  "item_ref": "1",
  "opportunity_id": "d070d2d4-4043-4d2d-aaf0-3905715a0476",
  "title": "990 Andersen Drive Expansion"
};

const mechanisms = getParticipationMechanisms(agendaItem, events);
// Returns: [email, attend, virtual] from parent event
""")
    return True

if __name__ == '__main__':
    print("="*60)
    print("PARTICIPATION MECHANISM REFERENCE ARCHITECTURE TEST")
    print("="*60 + "\n")

    results = []
    results.append(("Reference Architecture", test_reference_architecture()))
    results.append(("Data Size Savings", test_data_size_savings()))
    results.append(("Frontend Resolution", test_frontend_resolution_example()))

    print("\n" + "="*60)
    print("FINAL RESULTS")
    print("="*60)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(result[1] for result in results)
    sys.exit(0 if all_passed else 1)