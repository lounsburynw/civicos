#!/usr/bin/env python3
"""
CLI tool for generating testimony quality reports.

Generates quality reports for individual meetings or aggregate reports across
multiple meetings.

Session: 111 (production hardening)

Usage:
    # Single meeting report
    python scripts/testimony_quality_report.py --meeting san-rafael_2024-10-06_MpxrGRb16HQ

    # Aggregate report for jurisdiction
    python scripts/testimony_quality_report.py --jurisdiction san-rafael

    # Aggregate report for date range
    python scripts/testimony_quality_report.py --jurisdiction san-rafael --start 2024-01-01 --end 2024-12-31

    # Show speaker breakdown
    python scripts/testimony_quality_report.py --meeting san-rafael_2024-10-06_MpxrGRb16HQ --breakdown
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from testimony_quality_metrics import TestimonyQualityMetrics


def print_meeting_report(metrics: TestimonyQualityMetrics, meeting_id: str, show_breakdown: bool = False):
    """Print quality report for a single meeting."""
    report = metrics.calculate_meeting_metrics(meeting_id)

    if not report:
        print(f"Error: Meeting {meeting_id} not found in database")
        return

    print(report.format_report())

    if show_breakdown:
        print("\n")
        print("=" * 70)
        print("SPEAKER IDENTIFICATION BREAKDOWN")
        print("=" * 70)

        breakdown = metrics.get_identification_breakdown(meeting_id)

        # Group by method
        methods = {}
        for speaker in breakdown:
            method = speaker['identification_method']
            if method not in methods:
                methods[method] = []
            methods[method].append(speaker)

        for method, speakers in sorted(methods.items(), key=lambda x: -len(x[1])):
            print(f"\n{method.replace('_', ' ').title()} ({len(speakers)} speakers):")
            for i, speaker in enumerate(speakers[:5], 1):  # Show top 5 per method
                print(f"  {i}. {speaker['name']} ({speaker['speaker_label']})")
                print(f"     Role: {speaker['role']} | Confidence: {speaker['confidence']} | Utterances: {speaker['utterance_count']}")

            if len(speakers) > 5:
                print(f"  ... and {len(speakers) - 5} more")


def print_aggregate_report(
    metrics: TestimonyQualityMetrics,
    jurisdiction_id: str = None,
    start_date: str = None,
    end_date: str = None
):
    """Print aggregate quality report across multiple meetings."""
    agg = metrics.calculate_aggregate_metrics(
        jurisdiction_id=jurisdiction_id,
        start_date=start_date,
        end_date=end_date
    )

    filters = []
    if jurisdiction_id:
        filters.append(f"Jurisdiction: {jurisdiction_id}")
    if start_date:
        filters.append(f"Start: {start_date}")
    if end_date:
        filters.append(f"End: {end_date}")

    filter_str = " | ".join(filters) if filters else "All meetings"

    print("=" * 70)
    print("AGGREGATE TESTIMONY QUALITY REPORT")
    print("=" * 70)
    print(f"Filters: {filter_str}")
    print()
    print(f"Total Meetings: {agg['total_meetings']}")
    print(f"Total Speakers: {agg['total_speakers']}")
    print(f"Total Utterances: {agg['total_utterances']}")
    print()
    print(f"Identification Rate: {agg['identification_rate']:.1%}")
    print(f"  - Identified: {agg['identified_speakers']} speakers")
    print(f"  - Unknown: {agg['total_speakers'] - agg['identified_speakers']} speakers")
    print()
    print(f"Average Speaker Count Accuracy: {agg['avg_count_accuracy']:.1%}")
    print()
    print(f"Total Cost: ${agg['total_cost']:.2f}")
    print(f"Cost per Meeting: ${agg['cost_per_meeting']:.2f}")
    print(f"Cost per Speaker: ${agg['total_cost'] / agg['total_speakers']:.4f}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Generate testimony extraction quality reports"
    )

    parser.add_argument(
        "--meeting",
        help="Meeting ID for single meeting report (e.g., san-rafael_2024-10-06_MpxrGRb16HQ)"
    )

    parser.add_argument(
        "--jurisdiction",
        help="Jurisdiction ID for aggregate report (e.g., san-rafael)"
    )

    parser.add_argument(
        "--start",
        help="Start date for aggregate report (ISO format: YYYY-MM-DD)"
    )

    parser.add_argument(
        "--end",
        help="End date for aggregate report (ISO format: YYYY-MM-DD)"
    )

    parser.add_argument(
        "--breakdown",
        action="store_true",
        help="Show detailed speaker identification breakdown (for single meeting reports)"
    )

    parser.add_argument(
        "--db",
        default="data/civic_participation.db",
        help="Path to SQLite database (default: data/civic_participation.db)"
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.meeting and not args.jurisdiction:
        parser.error("Must specify either --meeting or --jurisdiction")

    if args.meeting and (args.jurisdiction or args.start or args.end):
        parser.error("Cannot combine --meeting with --jurisdiction, --start, or --end")

    if args.breakdown and not args.meeting:
        parser.error("--breakdown only works with --meeting")

    # Initialize metrics
    try:
        metrics = TestimonyQualityMetrics(db_path=args.db)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # Generate report
    if args.meeting:
        print_meeting_report(metrics, args.meeting, args.breakdown)
    else:
        print_aggregate_report(
            metrics,
            jurisdiction_id=args.jurisdiction,
            start_date=args.start,
            end_date=args.end
        )


if __name__ == '__main__':
    main()
