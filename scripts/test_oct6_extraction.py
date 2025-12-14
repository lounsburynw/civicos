#!/usr/bin/env python3
"""Test retrospective extraction on Oct 6 meeting (wildfire fund case study)"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from retrospective_analyzer import RetrospectiveAnalyzer

# Load Oct 6 meeting
with open('data/events/events_city-san-rafael_20251111_233335.json') as f:
    data = json.load(f)
    event = data['events'][0]

print(f"🔍 Testing retrospective extraction on Oct 6 meeting")
print(f"   Title: {event['title']}")
print(f"   Date: {event['when_human']}")
print(f"   Agenda: {event.get('agenda_expansion', {}).get('source_url', 'None')}\n")

analyzer = RetrospectiveAnalyzer()

print("⚙️  Extracting high-stakes decisions (min budget: $100K, min stakes: 6/10)...\n")

decisions = analyzer.extract_high_stakes_decisions(
    event,
    min_budget=100000,
    min_stakes_score=6
)

print(f"✅ Found {len(decisions)} high-stakes decisions\n")

for i, d in enumerate(decisions, 1):
    print(f"{i}. {d.title}")
    print(f"   Item: {d.item_ref}")
    print(f"   Type: {d.decision_type}")
    print(f"   Stakes: {d.stakes_score}/10")
    if d.budget_amount:
        print(f"   Budget: ${d.budget_amount:,.0f}")
    if d.affected_population_estimate:
        print(f"   Affected: ~{d.affected_population_estimate:,} residents")
    print(f"   Scope: {d.geographic_scope}")
    print(f"   Keywords: {', '.join(d.keywords_for_matching[:8])}")
    print(f"   Description: {d.description}")
    print()

# Save results
output = {
    "meeting_date": event['when_human'],
    "meeting_title": event['title'],
    "decisions": [d.to_dict() for d in decisions]
}

with open('data/pilot/oct6_high_stakes_test.json', 'w') as f:
    json.dump(output, f, indent=2)
    print(f"💾 Saved results to data/pilot/oct6_high_stakes_test.json")
