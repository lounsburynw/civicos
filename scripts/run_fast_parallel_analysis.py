#!/usr/bin/env python3
"""
Fast Parallel Retrospective Analysis using PyMuPDF4LLM

Processes 33 San Rafael meetings in 15-20 minutes (vs 3.5 hours with Docling)
Uses parallel processing (8 workers) + fast PDF extraction (pymupdf4llm)

Usage:
    python scripts/run_fast_parallel_analysis.py \
        data/pilot/san_rafael_meetings_enhanced.json \
        --output data/pilot/san_rafael_high_stakes_fast.json \
        --meeting-types city_council \
        --workers 8

Session 102: Option A implementation (Fast & Free)
"""

import sys
import os
import json
import argparse
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fast_retrospective_analyzer import FastRetrospectiveAnalyzer


def process_single_meeting(meeting: Dict, min_budget: int, min_stakes_score: int) -> Dict:
    """
    Process a single meeting (for parallel execution)

    Args:
        meeting: Meeting dict with title, date, pdf_url, etc.
        min_budget: Minimum budget threshold
        min_stakes_score: Minimum stakes score

    Returns:
        Dict with meeting metadata + decisions
    """
    try:
        print(f"[{meeting['date']}] Processing: {meeting['title'][:60]}...")

        analyzer = FastRetrospectiveAnalyzer()

        decisions = analyzer.extract_high_stakes_decisions(
            pdf_url=meeting['pdf_url'],
            meeting_date=meeting['date'],
            meeting_type=meeting['meeting_type']
        )

        # Convert decisions to dicts and add meeting metadata
        decision_dicts = []
        for decision in decisions:
            decision_dict = decision.to_dict()
            decision_dict['meeting_title'] = meeting['title']
            decision_dict['meeting_url'] = meeting.get('meeting_url', '')
            decision_dicts.append(decision_dict)

        return {
            'meeting': meeting,
            'decisions': decision_dicts,
            'success': True,
            'error': None
        }

    except Exception as e:
        print(f"[{meeting['date']}] ❌ Error: {type(e).__name__}: {e}")
        return {
            'meeting': meeting,
            'decisions': [],
            'success': False,
            'error': str(e)
        }


def load_meetings(meetings_file: str, meeting_types: Optional[List[str]] = None) -> List[Dict]:
    """
    Load meetings from enhanced JSON file

    Args:
        meetings_file: Path to san_rafael_meetings_enhanced.json
        meeting_types: Optional list of meeting types to filter

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


def run_parallel_analysis(
    meetings_file: str,
    output_file: str,
    meeting_types: Optional[List[str]] = None,
    min_budget: int = 100000,
    min_stakes_score: int = 6,
    workers: int = 8
) -> Dict:
    """
    Run parallel retrospective analysis on all meetings

    Args:
        meetings_file: Path to enhanced meetings JSON
        output_file: Where to save results
        meeting_types: Optional meeting type filter
        min_budget: Minimum budget threshold
        min_stakes_score: Minimum stakes score (1-10)
        workers: Number of parallel workers (default: 8)

    Returns:
        Analysis results dict
    """
    print("\n" + "="*70)
    print("🚀 FAST PARALLEL RETROSPECTIVE ANALYSIS (PyMuPDF4LLM)")
    print("="*70 + "\n")

    # Load meetings
    meetings = load_meetings(meetings_file, meeting_types)

    if not meetings:
        print("❌ No meetings found to analyze")
        return None

    print(f"\n⚡ Using {workers} parallel workers")
    print("="*70 + "\n")

    # Track progress
    start_time = time.time()
    all_decisions = []
    meetings_processed = 0
    meetings_with_decisions = 0
    meetings_failed = 0

    # Process in parallel
    with ProcessPoolExecutor(max_workers=workers) as executor:
        # Submit all tasks
        future_to_meeting = {
            executor.submit(
                process_single_meeting,
                meeting,
                min_budget,
                min_stakes_score
            ): meeting
            for meeting in meetings
        }

        # Process results as they complete
        for future in as_completed(future_to_meeting):
            result = future.result()
            meetings_processed += 1

            # Progress indicator
            elapsed = time.time() - start_time
            rate = meetings_processed / elapsed if elapsed > 0 else 0
            remaining = (len(meetings) - meetings_processed) / rate if rate > 0 else 0

            print(f"\n[{meetings_processed}/{len(meetings)}] {result['meeting']['title'][:60]}")
            print(f"   Elapsed: {elapsed/60:.1f}m | Remaining: ~{remaining/60:.1f}m | Rate: {rate:.1f}/min")

            if result['success']:
                decisions = result['decisions']
                if decisions:
                    print(f"   ✅ Found {len(decisions)} high-stakes decisions")
                    for decision in decisions:
                        print(f"      • {decision['title']}")
                        if decision.get('budget_amount'):
                            print(f"        ${decision['budget_amount']:,.0f} | Stakes: {decision['stakes_score']}/10")
                    all_decisions.extend(decisions)
                    meetings_with_decisions += 1
                else:
                    print(f"   ⚠️  No high-stakes decisions found")
            else:
                print(f"   ❌ Failed: {result['error']}")
                meetings_failed += 1

    # Compile results
    elapsed_total = time.time() - start_time

    results = {
        'jurisdiction_id': 'sanrafael',
        'jurisdiction_name': 'San Rafael',
        'analysis_timestamp': datetime.now().isoformat(),
        'analyzer_type': 'fast_parallel_pymupdf',
        'processing_time_seconds': elapsed_total,
        'parallel_workers': workers,
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
    print(f"\n   Total time: {elapsed_total/60:.1f} minutes")
    print(f"   Meetings processed: {meetings_processed}/{len(meetings)}")
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

    # Performance summary
    avg_time = elapsed_total / len(meetings) if meetings else 0
    print(f"\n⚡ Performance:")
    print(f"   Average time per meeting: {avg_time:.1f}s")
    print(f"   Speedup vs serial: ~{workers:.0f}x")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Fast parallel retrospective analysis using PyMuPDF4LLM',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Process all city council meetings with 8 workers (15-20 min)
    python scripts/run_fast_parallel_analysis.py \\
        data/pilot/san_rafael_meetings_enhanced.json \\
        --output data/pilot/san_rafael_high_stakes_fast.json \\
        --meeting-types city_council \\
        --workers 8

    # Maximum speed with 16 workers
    python scripts/run_fast_parallel_analysis.py \\
        data/pilot/san_rafael_meetings_enhanced.json \\
        --output data/pilot/san_rafael_high_stakes_fast.json \\
        --meeting-types city_council \\
        --workers 16
        """
    )

    parser.add_argument(
        'meetings_file',
        help='Path to san_rafael_meetings_enhanced.json'
    )

    parser.add_argument(
        '--output',
        default='data/pilot/san_rafael_high_stakes_fast.json',
        help='Output file for analysis results (default: %(default)s)'
    )

    parser.add_argument(
        '--meeting-types',
        nargs='+',
        help='Specific meeting types to analyze (default: all types)'
    )

    parser.add_argument(
        '--min-budget',
        type=int,
        default=100000,
        help='Minimum budget threshold (default: %(default)s)'
    )

    parser.add_argument(
        '--min-stakes',
        type=int,
        default=6,
        help='Minimum stakes score 1-10 (default: %(default)s)'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=8,
        help='Number of parallel workers (default: %(default)s, max: 16)'
    )

    args = parser.parse_args()

    # Validate input file
    if not os.path.exists(args.meetings_file):
        print(f"❌ Error: Meetings file not found: {args.meetings_file}")
        sys.exit(1)

    # Cap workers at reasonable max
    if args.workers > 16:
        print(f"⚠️  Warning: Capping workers at 16 (you requested {args.workers})")
        args.workers = 16

    # Run analysis
    results = run_parallel_analysis(
        meetings_file=args.meetings_file,
        output_file=args.output,
        meeting_types=args.meeting_types,
        min_budget=args.min_budget,
        min_stakes_score=args.min_stakes,
        workers=args.workers
    )

    if results:
        print("\n✅ Fast parallel analysis complete!")
    else:
        print("\n❌ Analysis failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
