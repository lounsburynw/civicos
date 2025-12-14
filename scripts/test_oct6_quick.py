#!/usr/bin/env python3
"""Quick test of Oct 6 extraction"""

import sys
import os
import json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from retrospective_analyzer import RetrospectiveAnalyzer

# Load just the Oct 6 meeting
with open('data/pilot/san_rafael_meetings_enhanced.json', 'r') as f:
    data = json.load(f)

oct6_meeting = [m for m in data['meetings']['city_council'] if m['date_parsed'] == '2025-10-06'][0]

print(f"Testing extraction for: {oct6_meeting['title']}")
print(f"Agenda PDF: {oct6_meeting['agenda_packet_pdf_url']}\n")

# Convert to event format
from datetime import datetime
date_obj = datetime.fromisoformat(oct6_meeting['date_parsed']).replace(hour=18)

event = {
    'title': oct6_meeting['title'],
    'when_human': date_obj.strftime('%a %b %d, %Y'),
    'when_iso': date_obj.isoformat(),
    'meeting_type': 'city_council',
    'source_url': oct6_meeting['meeting_url'],
    'agenda_url': oct6_meeting['agenda_packet_pdf_url'],
    'participation_mechanisms': [{'type': 'email', 'value': 'Lindsay.lara@cityofsanrafael.org'}]
}

# Run extraction
analyzer = RetrospectiveAnalyzer()
decisions = analyzer.extract_high_stakes_decisions(event, min_budget=100000, min_stakes_score=6)

print(f"\n✅ Found {len(decisions)} high-stakes decisions\n")

for d in decisions:
    print(f"- {d.item_ref}: {d.title}")
    print(f"  Stakes: {d.stakes_score}/10")
    if d.budget_amount:
        print(f"  Budget: ${d.budget_amount:,.0f}")
    print()

# Check for wildfire
wildfire = [d for d in decisions if 'wildfire' in d.title.lower() or 'wildfire' in d.description.lower()]
if wildfire:
    print(f"\n🔥 WILDFIRE CASE FOUND: {wildfire[0].item_ref}")
    print(f"   Budget: ${wildfire[0].budget_amount:,.0f}")
else:
    print("\n⚠️ WILDFIRE CASE NOT FOUND")
