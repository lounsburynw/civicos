#!/usr/bin/env python3
"""
Run retrospective analysis on scraped San Rafael meetings

Takes output from scrape_sanrafael_archives.py and runs high-stakes
decision extraction on each meeting's agenda packet.
"""

import sys
import os
import json
from typing import Dict, List
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from retrospective_analyzer import RetrospectiveAnalyzer, HighStakesDecision


def convert_scraped_meeting_to_event(meeting: Dict) -> Dict:
    """
    Convert scraped meeting dict to event format for RetrospectiveAnalyzer

    Input (from scraper):
    {
        "title": "City Council – October 6, 2025",
        "meeting_url": "https://...",
        "agenda_packet_url": "https://...#tab-agenda-packet",
        "date_parsed": "2025-10-06",
        "meeting_type": "city_council"
    }

    Output (event format):
    {
        "title": "City Council – October 6, 2025",
        "when_human": "Mon Oct 06, 2025",
        "when_iso": "2025-10-06T18:00:00-07:00",
        "agenda_url": "https://...",
        ...
    }
    """
    # Parse date
    date_obj = datetime.fromisoformat(meeting['date_parsed'])

    # Assume evening meetings (6pm) for City Council/Planning, daytime (10am) for others
    if meeting['meeting_type'] in ['city_council', 'planning_commission']:
        date_obj = date_obj.replace(hour=18)
    else:
        date_obj = date_obj.replace(hour=10)

    return {
        'title': meeting['title'],
        'when_human': date_obj.strftime('%a %b %d, %Y'),
        'when_iso': date_obj.isoformat(),
        'meeting_type': meeting['meeting_type'],
        'source_url': meeting['meeting_url'],
        'agenda_url': meeting.get('agenda_packet_pdf_url', meeting['agenda_packet_url']),
        'participation_mechanisms': [
            {
                'type': 'email',
                'value': 'Lindsay.lara@cityofsanrafael.org'
            }
        ],
        '_scraped_metadata': meeting
    }


def analyze_all_meetings(
    meetings_file: str,
    output_file: str,
    min_budget: int = 100000,
    min_stakes_score: int = 6,
    meeting_types: List[str] = None
) -> Dict:
    """
    Analyze all meetings from scraper output

    Args:
        meetings_file: Path to JSON file from scrape_sanrafael_archives.py
        output_file: Where to save high-stakes decisions
        min_budget: Minimum budget threshold
        min_stakes_score: Minimum stakes score (1-10)
        meeting_types: Optional list of meeting types to analyze (default: all)

    Returns:
        Analysis results dict
    """
    print("🔍 SAN RAFAEL RETROSPECTIVE ANALYSIS")
    print("=" * 70)

    # Load scraped meetings
    with open(meetings_file, 'r') as f:
        data = json.load(f)

    all_meetings_by_type = data['meetings']
    total_meetings = data['total_meetings']

    print(f"Loaded {total_meetings} meetings from {meetings_file}")
    print(f"Date range: {data['date_range']['start']} to {data['date_range']['end']}\n")

    # Filter meeting types if specified
    if meeting_types:
        all_meetings_by_type = {
            k: v for k, v in all_meetings_by_type.items()
            if k in meeting_types
        }
        total_meetings = sum(len(meetings) for meetings in all_meetings_by_type.values())
        print(f"Filtering to {len(meeting_types)} meeting types: {', '.join(meeting_types)}")
        print(f"Analyzing {total_meetings} meetings\n")

    # Initialize analyzer
    analyzer = RetrospectiveAnalyzer()

    # Process each meeting
    all_decisions = []
    meetings_analyzed = 0
    meetings_with_decisions = 0

    for meeting_type, meetings in all_meetings_by_type.items():
        print(f"\n📋 {meeting_type.upper().replace('_', ' ')}")
        print(f"   {len(meetings)} meetings to analyze")

        for i, meeting in enumerate(meetings, 1):
            meetings_analyzed += 1

            print(f"\n   [{meetings_analyzed}/{total_meetings}] {meeting['title']}")
            print(f"       Date: {meeting['date_parsed']}")

            # Convert to event format
            event = convert_scraped_meeting_to_event(meeting)

            # Extract high-stakes decisions
            try:
                decisions = analyzer.extract_high_stakes_decisions(
                    event,
                    min_budget=min_budget,
                    min_stakes_score=min_stakes_score
                )

                if decisions:
                    print(f"       ✅ Found {len(decisions)} high-stakes decisions")
                    for decision in decisions:
                        print(f"          - {decision.title} (stakes: {decision.stakes_score}/10)")
                        if decision.budget_amount:
                            print(f"            Budget: ${decision.budget_amount:,.0f}")

                    all_decisions.extend([d.to_dict() for d in decisions])
                    meetings_with_decisions += 1
                else:
                    print(f"       ⚠️  No high-stakes decisions found")

            except Exception as e:
                print(f"       ❌ Error: {type(e).__name__}: {e}")

    # Compile results
    results = {
        'jurisdiction_id': data['jurisdiction_id'],
        'jurisdiction_name': data['jurisdiction_name'],
        'date_range': data['date_range'],
        'analysis_timestamp': datetime.now().isoformat(),
        'meetings_analyzed': meetings_analyzed,
        'meetings_with_high_stakes_decisions': meetings_with_decisions,
        'total_high_stakes_decisions': len(all_decisions),
        'min_budget_threshold': min_budget,
        'min_stakes_score': min_stakes_score,
        'decisions': all_decisions
    }

    # Calculate summary statistics
    decision_types = {}
    total_budget = 0.0
    by_meeting_type = {}

    for decision in all_decisions:
        # Count by decision type
        dtype = decision.get('decision_type', 'unknown')
        decision_types[dtype] = decision_types.get(dtype, 0) + 1

        # Count by meeting type
        mtype = decision.get('meeting_type', 'unknown')
        by_meeting_type[mtype] = by_meeting_type.get(mtype, 0) + 1

        # Sum budgets
        if decision.get('budget_amount'):
            total_budget += decision['budget_amount']

    results['summary'] = {
        'total_budget_amount': total_budget,
        'decision_types_breakdown': decision_types,
        'by_meeting_type': by_meeting_type
    }

    # Save results
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print("\n" + "=" * 70)
    print("📊 ANALYSIS COMPLETE")
    print(f"\n   Meetings analyzed: {meetings_analyzed}")
    print(f"   Meetings with high-stakes decisions: {meetings_with_decisions}")
    print(f"   Total high-stakes decisions: {len(all_decisions)}")
    print(f"   Total budget amount: ${total_budget:,.0f}")

    if decision_types:
        print(f"\n   By decision type:")
        for dtype, count in sorted(decision_types.items(), key=lambda x: -x[1]):
            print(f"     - {dtype}: {count}")

    if by_meeting_type:
        print(f"\n   By meeting type:")
        for mtype, count in sorted(by_meeting_type.items(), key=lambda x: -x[1]):
            print(f"     - {mtype}: {count}")

    print(f"\n✅ Results saved to {output_file}")

    return results


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Run retrospective analysis on scraped San Rafael meetings'
    )
    parser.add_argument('meetings_file', help='JSON file from scrape_sanrafael_archives.py')
    parser.add_argument('--output', default='data/pilot/san_rafael_high_stakes_decisions.json',
                        help='Output file for high-stakes decisions')
    parser.add_argument('--min-budget', type=int, default=100000,
                        help='Minimum budget threshold (default: $100K)')
    parser.add_argument('--min-stakes', type=int, default=6,
                        help='Minimum stakes score 1-10 (default: 6)')
    parser.add_argument('--meeting-types', nargs='+',
                        help='Specific meeting types to analyze (default: all)')

    args = parser.parse_args()

    results = analyze_all_meetings(
        meetings_file=args.meetings_file,
        output_file=args.output,
        min_budget=args.min_budget,
        min_stakes_score=args.min_stakes,
        meeting_types=args.meeting_types
    )

    print(f"\n📈 NEXT STEPS:")
    print(f"   1. Review high-stakes decisions in {args.output}")
    print(f"   2. Match SeeClickFix complaints to decisions:")
    print(f"      python scripts/match_seeclickfix_to_decisions.py {args.output}")
    print(f"   3. Calculate coordination gaps and identify patterns")


if __name__ == "__main__":
    main()
