#!/usr/bin/env python3
"""
Test retrospective analysis on sample San Rafael meetings
"""

import sys
import os
import json

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from retrospective_analyzer import RetrospectiveAnalyzer, HighStakesDecision


def test_single_meeting():
    """Test extraction on a single meeting"""

    # Load most recent San Rafael event file
    event_file = "data/events/events_city-san-rafael_20251112_220935.json"

    with open(event_file, 'r') as f:
        data = json.load(f)

    events = data.get('events', [])

    if not events:
        print("⚠️  No events found in file")
        return

    print(f"📊 Testing retrospective analysis on {len(events)} events from {event_file}")

    # Initialize analyzer
    analyzer = RetrospectiveAnalyzer()

    # Test on first event
    event = events[0]
    print(f"\n🔍 Analyzing: {event.get('title', 'Unknown')}")
    print(f"   Date: {event.get('when_human', 'Unknown')}")
    print(f"   Meeting type: {event.get('meeting_type', 'Unknown')}")

    # Check if agenda URL exists
    agenda_url = analyzer._get_agenda_url(event)
    if agenda_url:
        print(f"   Agenda URL: {agenda_url}")
    else:
        print(f"   ⚠️  No agenda URL found")
        return

    # Extract high-stakes decisions
    print(f"\n⚙️  Running high-stakes extraction...")
    decisions = analyzer.extract_high_stakes_decisions(
        event,
        min_budget=100000,
        min_stakes_score=6
    )

    print(f"\n✅ Found {len(decisions)} high-stakes decisions")

    for i, decision in enumerate(decisions, 1):
        print(f"\n   {i}. {decision.title}")
        print(f"      Item: {decision.item_ref}")
        print(f"      Type: {decision.decision_type}")
        print(f"      Stakes: {decision.stakes_score}/10")
        if decision.budget_amount:
            print(f"      Budget: ${decision.budget_amount:,.0f}")
        if decision.project_size_units:
            print(f"      Project size: {decision.project_size_units} units")
        print(f"      Keywords: {', '.join(decision.keywords_for_matching[:5])}")
        print(f"      Description: {decision.description[:150]}...")

    return decisions


def test_batch_analysis():
    """Test batch analysis on multiple meetings"""

    event_file = "data/events/events_city-san-rafael_20251112_220935.json"

    with open(event_file, 'r') as f:
        data = json.load(f)

    events = data.get('events', [])

    print(f"\n📊 Testing batch analysis on {len(events)} meetings")

    analyzer = RetrospectiveAnalyzer()
    results = analyzer.analyze_meeting_batch(
        events,
        min_budget=100000,
        min_stakes_score=6
    )

    print(f"\n✅ BATCH ANALYSIS COMPLETE")
    print(f"   Meetings analyzed: {results['meetings_analyzed']}")
    print(f"   High-stakes decisions: {results['decision_count']}")

    if results['decision_count'] > 0:
        print(f"   Total budget: ${results['total_budget_amount']:,.0f}")
        print(f"\n   By decision type:")
        for dtype, count in results['decision_types_breakdown'].items():
            print(f"     - {dtype}: {count}")
        print(f"\n   By meeting type:")
        for mtype, count in results['by_meeting_type'].items():
            print(f"     - {mtype}: {count}")

    return results


if __name__ == "__main__":
    print("🧪 RETROSPECTIVE ANALYSIS TEST\n")
    print("=" * 60)

    # Test 1: Single meeting extraction
    print("\n📋 TEST 1: Single Meeting Extraction")
    print("=" * 60)
    try:
        decisions = test_single_meeting()
    except Exception as e:
        print(f"❌ Test 1 failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: Batch analysis
    print("\n\n📋 TEST 2: Batch Analysis")
    print("=" * 60)
    try:
        results = test_batch_analysis()
    except Exception as e:
        print(f"❌ Test 2 failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    print("\n\n✅ Testing complete!")
