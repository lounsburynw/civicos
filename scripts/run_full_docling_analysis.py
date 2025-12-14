#!/usr/bin/env python3
"""
Run full Docling-based retrospective analysis on San Rafael meetings

Processes all 33 City Council meetings from enhanced JSON using DoclingRetrospectiveAnalyzer.
Expected runtime: 2-3 hours (3 min/PDF + LLM processing per meeting).

Usage:
    python scripts/run_full_docling_analysis.py \
        data/pilot/san_rafael_meetings_enhanced.json \
        --output data/pilot/san_rafael_high_stakes_docling.json \
        --meeting-types city_council

Session 102: Full retrospective pipeline execution
"""

import sys
import os
import json
import argparse
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from docling_retrospective_analyzer import DoclingRetrospectiveAnalyzer


def load_meetings(meetings_file: str, meeting_types: Optional[List[str]] = None) -> List[Dict]:
    """
    Load meetings from enhanced JSON file

    Args:
        meetings_file: Path to san_rafael_meetings_enhanced.json
        meeting_types: Optional list of meeting types to filter (e.g., ['city_council'])

    Returns:
        List of meeting dicts with title, date, pdf_url
    """
    print(f"📂 Loading meetings from {meetings_file}")

    with open(meetings_file, 'r') as f:
        data = json.load(f)

    print(f"   Total meetings in file: {data['total_meetings']}")
    print(f"   Date range: {data['date_range']['start']} to {data['date_range']['end']}")

    # Extract meetings by type
    all_meetings = []
    for meeting_type, meetings in data['meetings'].items():
        if meeting_types and meeting_type not in meeting_types:
            continue

        for meeting in meetings:
            # Skip if no PDF URL available
            if not meeting.get('agenda_packet_pdf_url'):
                continue

            all_meetings.append({
                'title': meeting['title'],
                'date': meeting['date_parsed'],
                'pdf_url': meeting['agenda_packet_pdf_url'],
                'meeting_type': meeting['meeting_type'],
                'meeting_url': meeting.get('meeting_url', '')
            })

    # Sort by date (oldest first for retrospective analysis)
    all_meetings.sort(key=lambda m: m['date'])

    print(f"   Meetings to analyze: {len(all_meetings)}")
    if meeting_types:
        print(f"   Filtered to types: {', '.join(meeting_types)}")

    return all_meetings


def run_analysis(
    meetings_file: str,
    output_file: str,
    meeting_types: Optional[List[str]] = None,
    min_budget: int = 100000,
    min_stakes_score: int = 6
) -> Dict:
    """
    Run full retrospective analysis on all meetings

    Args:
        meetings_file: Path to enhanced meetings JSON
        output_file: Where to save results
        meeting_types: Optional meeting type filter
        min_budget: Minimum budget threshold for high-stakes classification
        min_stakes_score: Minimum stakes score (1-10)

    Returns:
        Analysis results dict
    """
    print("\n" + "="*70)
    print("🔍 SAN RAFAEL DOCLING RETROSPECTIVE ANALYSIS")
    print("="*70 + "\n")

    # Load meetings
    meetings = load_meetings(meetings_file, meeting_types)

    if not meetings:
        print("❌ No meetings found to analyze")
        return None

    # Initialize analyzer
    print("\n📊 Initializing Docling analyzer...")
    analyzer = DoclingRetrospectiveAnalyzer()

    # Process each meeting
    all_decisions = []
    meetings_processed = 0
    meetings_with_decisions = 0
    meetings_failed = 0

    print("\n" + "="*70)
    print("🚀 PROCESSING MEETINGS")
    print("="*70 + "\n")

    for i, meeting in enumerate(meetings, 1):
        print(f"\n[{i}/{len(meetings)}] {meeting['title']}")
        print(f"   Date: {meeting['date']}")
        print(f"   PDF: {meeting['pdf_url']}")

        try:
            # Extract high-stakes decisions
            decisions = analyzer.extract_high_stakes_decisions(
                pdf_url=meeting['pdf_url'],
                meeting_date=meeting['date'],
                meeting_type=meeting['meeting_type']
            )

            meetings_processed += 1

            if decisions:
                print(f"   ✅ Found {len(decisions)} high-stakes decisions")

                # Show summary of decisions
                for decision in decisions:
                    print(f"      • {decision.title}")
                    if decision.budget_amount:
                        print(f"        ${decision.budget_amount:,.0f} | Stakes: {decision.stakes_score}/10")
                    else:
                        print(f"        Stakes: {decision.stakes_score}/10")

                # Add meeting metadata to decisions
                for decision in decisions:
                    decision_dict = decision.to_dict()
                    decision_dict['meeting_title'] = meeting['title']
                    decision_dict['meeting_url'] = meeting['meeting_url']
                    all_decisions.append(decision_dict)

                meetings_with_decisions += 1
            else:
                print(f"   ⚠️  No high-stakes decisions found")

        except Exception as e:
            print(f"   ❌ Error: {type(e).__name__}: {e}")
            meetings_failed += 1
            import traceback
            traceback.print_exc()

    # Compile results
    results = {
        'jurisdiction_id': 'sanrafael',
        'jurisdiction_name': 'San Rafael',
        'analysis_timestamp': datetime.now().isoformat(),
        'analyzer_type': 'docling',
        'date_range': {
            'start': min(m['date'] for m in meetings),
            'end': max(m['date'] for m in meetings)
        },
        'meetings_total': len(meetings),
        'meetings_processed': meetings_processed,
        'meetings_with_decisions': meetings_with_decisions,
        'meetings_failed': meetings_failed,
        'total_decisions': len(all_decisions),
        'min_budget_threshold': min_budget,
        'min_stakes_score': min_stakes_score,
        'decisions': all_decisions
    }

    # Calculate summary statistics
    decision_types = {}
    total_budget = 0.0
    stakes_distribution = {i: 0 for i in range(1, 11)}

    for decision in all_decisions:
        # Count by decision type
        dtype = decision.get('decision_type', 'unknown')
        decision_types[dtype] = decision_types.get(dtype, 0) + 1

        # Sum budgets
        if decision.get('budget_amount'):
            total_budget += decision['budget_amount']

        # Track stakes scores
        stakes = decision.get('stakes_score', 0)
        if 1 <= stakes <= 10:
            stakes_distribution[stakes] += 1

    results['summary'] = {
        'total_budget_amount': total_budget,
        'decision_types_breakdown': decision_types,
        'stakes_distribution': stakes_distribution
    }

    # Save results
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    # Print summary
    print("\n" + "="*70)
    print("📊 ANALYSIS COMPLETE")
    print("="*70)
    print(f"\n   Meetings processed: {meetings_processed}/{len(meetings)}")
    print(f"   Meetings with high-stakes decisions: {meetings_with_decisions}")
    print(f"   Meetings failed: {meetings_failed}")
    print(f"   Total high-stakes decisions: {len(all_decisions)}")
    print(f"   Total budget tracked: ${total_budget:,.0f}")

    if decision_types:
        print(f"\n   📋 By decision type:")
        for dtype, count in sorted(decision_types.items(), key=lambda x: -x[1]):
            print(f"      • {dtype}: {count}")

    if any(stakes_distribution.values()):
        print(f"\n   🎯 Stakes score distribution:")
        for score in range(10, 0, -1):
            count = stakes_distribution[score]
            if count > 0:
                bar = "█" * count
                print(f"      {score:2d}/10: {bar} ({count})")

    print(f"\n✅ Results saved to: {output_file}")

    # Next steps
    print(f"\n📈 NEXT STEPS:")
    print(f"   1. Review decisions: cat {output_file} | jq '.decisions[] | {{title, budget_amount, stakes_score}}'")
    print(f"   2. Find wildfire case: cat {output_file} | jq '.decisions[] | select(.title | contains(\"Wildfire\"))'")
    print(f"   3. Enrich with testimony: python scripts/enrich_with_testimony.py {output_file}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Run full Docling retrospective analysis on San Rafael meetings',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Process all city council meetings
    python scripts/run_full_docling_analysis.py \\
        data/pilot/san_rafael_meetings_enhanced.json \\
        --output data/pilot/san_rafael_high_stakes_docling.json \\
        --meeting-types city_council

    # Process all meeting types with custom thresholds
    python scripts/run_full_docling_analysis.py \\
        data/pilot/san_rafael_meetings_enhanced.json \\
        --output data/pilot/san_rafael_all_decisions.json \\
        --min-budget 50000 \\
        --min-stakes 5
        """
    )

    parser.add_argument(
        'meetings_file',
        help='Path to san_rafael_meetings_enhanced.json'
    )

    parser.add_argument(
        '--output',
        default='data/pilot/san_rafael_high_stakes_docling.json',
        help='Output file for analysis results (default: %(default)s)'
    )

    parser.add_argument(
        '--meeting-types',
        nargs='+',
        help='Specific meeting types to analyze (default: all types). Options: city_council, planning_commission, etc.'
    )

    parser.add_argument(
        '--min-budget',
        type=int,
        default=100000,
        help='Minimum budget threshold for high-stakes classification (default: %(default)s)'
    )

    parser.add_argument(
        '--min-stakes',
        type=int,
        default=6,
        help='Minimum stakes score 1-10 for high-stakes classification (default: %(default)s)'
    )

    args = parser.parse_args()

    # Validate input file
    if not os.path.exists(args.meetings_file):
        print(f"❌ Error: Meetings file not found: {args.meetings_file}")
        sys.exit(1)

    # Run analysis
    results = run_analysis(
        meetings_file=args.meetings_file,
        output_file=args.output,
        meeting_types=args.meeting_types,
        min_budget=args.min_budget,
        min_stakes_score=args.min_stakes
    )

    if results:
        print("\n✅ Analysis complete!")
    else:
        print("\n❌ Analysis failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
