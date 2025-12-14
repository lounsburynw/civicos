#!/usr/bin/env python3
"""
Cross-reference wildfire testimony with SeeClickFix complaints.

This creates the Oct 6 case study showing:
24 complaints filed → 3 residents testified → Council decision
"""

import json
from collections import defaultdict
from datetime import datetime

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    # Load complaints data
    complaints_data = load_json('data/oct6_seeclickfix_complaints.json')
    complaints = complaints_data['issues']

    # Load testimony data
    testimony_data = load_json('data/pilot/oct6_wildfire_testimony.json')

    print("="*70)
    print("OCT 6 WILDFIRE CASE STUDY: Complaints → Testimony → Decision")
    print("="*70)

    # Analyze complaints by category
    fire_categories = [
        "Vegetation Fire Hazard / Un Peligro de Incendio de Vegetación",
        "Report a Campsite Fire Hazard / Reporte un peligro de incendio en un campamento",
        "Roadside Vegetation / Vegetación en borde de carretera",
        "Trees / árboles"
    ]

    complaints_by_category = defaultdict(list)
    for c in complaints:
        category = c.get('category', '')
        complaints_by_category[category].append(c)

    # Count fire-related complaints
    fire_complaint_count = 0
    for cat in fire_categories:
        count = len(complaints_by_category.get(cat, []))
        if count > 0:
            print(f"\n{cat}: {count} complaints")
            fire_complaint_count += count

    # Show other vegetation-related categories
    other_vegetation = [
        "Open Space / Espacio Abierto",
        "Parks and Playgrounds / Parques y áreas de Juego"
    ]

    print(f"\nRelated categories:")
    for cat in other_vegetation:
        count = len(complaints_by_category.get(cat, []))
        if count > 0:
            print(f"  {cat}: {count} complaints")

    print(f"\n{'='*70}")
    print(f"TOTAL FIRE-SPECIFIC COMPLAINTS: {fire_complaint_count}")
    print(f"TOTAL COMPLAINTS (all categories): {len(complaints)}")
    print(f"{'='*70}")

    # Testimony summary
    print(f"\nTESTIMONY SPEAKERS: {len(testimony_data)}")
    for speaker in testimony_data:
        print(f"\n{speaker['name']}")
        print(f"  Role: {speaker['role']}")
        print(f"  Utterances: {speaker['utterance_count']}")
        print(f"  Confidence: {speaker['confidence']}")

    # Calculate participation gap
    print(f"\n{'='*70}")
    print(f"PARTICIPATION GAP ANALYSIS")
    print(f"{'='*70}")

    # Count unique complaint filers
    unique_filers = set()
    for c in complaints:
        reporter_name = c.get('reporter', {}).get('name', 'Unknown')
        if reporter_name != 'Unknown':
            unique_filers.add(reporter_name)

    print(f"\nFire-related complaints filed: {fire_complaint_count}")
    print(f"Unique complaint filers: {len(unique_filers)}")
    print(f"Residents who testified: {len(testimony_data)}")
    print(f"Participation gap: {len(unique_filers) - len(testimony_data)} filers did NOT testify")

    if len(unique_filers) > 0:
        gap_percentage = ((len(unique_filers) - len(testimony_data)) / len(unique_filers)) * 100
        print(f"Gap percentage: {gap_percentage:.1f}%")

    # Case study narrative
    print(f"\n{'='*70}")
    print(f"CASE STUDY NARRATIVE")
    print(f"{'='*70}")

    print(f"""
Oct 6, 2024 San Rafael City Council Meeting
Agenda Item 7.b: Wildfire Prevention Authority Update

COMPLAINT PHASE (Sept 6 - Oct 6):
- {fire_complaint_count} fire-specific complaints filed via SeeClickFix
- {len(unique_filers)} unique residents raised concerns
- Categories: Vegetation hazards, fire risks, tree maintenance

TESTIMONY PHASE (Oct 6 meeting):
- {len(testimony_data)} residents testified in person
- Belle Cole: Firewise Committee Chair - coordination & outreach
- Sherna Deamer: Neighborhood fire hazards - unmaintained properties
- Salama: Age-Friendly Committee - senior fire safety

DECISION PHASE:
- Council acknowledged wildfire prevention update
- Measure C funding supporting mitigation work
- 85% completion of wildfire mitigation plan

COORDINATION GAP:
- {len(unique_filers) - len(testimony_data)} complaint filers ({gap_percentage:.0f}%) did NOT testify
- No mechanism to connect operational complaints → policy decisions
- No notification system for related agenda items

VALUE PROPOSITION:
Our platform bridges this gap by:
1. Matching SeeClickFix complaints to council agendas (AI-powered)
2. Notifying complaint filers when related items appear
3. Providing coordination infrastructure (chat, following, issue linking)
4. Lowering participation barriers (draft comments, legislative context)
    """)

    # Save summary
    summary = {
        "meeting_date": "2024-10-06",
        "agenda_item": "7.b",
        "topic": "Wildfire Prevention Authority Update",
        "complaint_stats": {
            "fire_specific": fire_complaint_count,
            "total_complaints": len(complaints),
            "unique_filers": len(unique_filers),
            "date_range": complaints_data['date_range']
        },
        "testimony_stats": {
            "speakers": len(testimony_data),
            "speakers_list": [
                {
                    "name": s['name'],
                    "role": s['role'],
                    "utterances": s['utterance_count']
                }
                for s in testimony_data
            ]
        },
        "participation_gap": {
            "filers_who_did_not_testify": len(unique_filers) - len(testimony_data),
            "gap_percentage": gap_percentage if len(unique_filers) > 0 else 0
        }
    }

    with open('data/pilot/oct6_case_study_summary.json', 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    print(f"\n{'='*70}")
    print(f"✓ Case study summary saved to: data/pilot/oct6_case_study_summary.json")
    print(f"{'='*70}")

if __name__ == '__main__':
    main()
