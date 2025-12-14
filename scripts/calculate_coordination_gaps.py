#!/usr/bin/env python3
"""
Calculate coordination gaps and identify patterns

Takes complaint match output and calculates gaps where testimony
counts are available. Identifies patterns across decisions.
"""

import json
import sys
from typing import Dict, List
from datetime import datetime
from collections import defaultdict


def calculate_gaps(matches: List[Dict]) -> Dict:
    """Calculate coordination gaps with enhanced pattern analysis"""

    stats = {
        "total_decisions": len(matches),
        "decisions_with_complaints": 0,
        "decisions_with_testimony_data": 0,
        "total_complaints": 0,
        "total_testimony": 0,
        "total_gap": 0,
        "average_complaints_per_decision": 0,
        "average_testimony_per_decision": 0,
        "average_gap_per_decision": 0,
        "average_gap_percentage": 0,
        "gaps_by_decision": [],
        "patterns": {
            "by_decision_type": {},
            "by_budget_range": {},
            "by_month": {},
            "by_meeting_type": {}
        }
    }

    # Track patterns
    by_type = defaultdict(lambda: {"complaints": 0, "testimony": 0, "gaps": [], "count": 0})
    by_budget = defaultdict(lambda: {"complaints": 0, "testimony": 0, "gaps": [], "count": 0})
    by_month = defaultdict(lambda: {"complaints": 0, "testimony": 0, "gaps": [], "count": 0})
    by_meeting = defaultdict(lambda: {"complaints": 0, "testimony": 0, "gaps": [], "count": 0})

    total_complaints = 0
    total_testimony = 0
    gaps = []

    for match in matches:
        complaint_count = match.get('complaints_found', 0)
        testimony_count = match.get('testimony_count')

        total_complaints += complaint_count

        if complaint_count > 0:
            stats['decisions_with_complaints'] += 1

        # Only calculate gap if we have testimony data
        if testimony_count is not None:
            stats['decisions_with_testimony_data'] += 1
            total_testimony += testimony_count

            gap = complaint_count - testimony_count
            gap_pct = (gap / complaint_count * 100) if complaint_count > 0 else 0

            match['coordination_gap'] = gap
            match['coordination_gap_percentage'] = gap_pct

            gaps.append(gap_pct)

            stats['gaps_by_decision'].append({
                "decision_title": match.get('decision_title'),
                "decision_date": match.get('decision_date'),
                "decision_type": match.get('decision_type'),
                "complaints": complaint_count,
                "testimony": testimony_count,
                "gap": gap,
                "gap_percentage": gap_pct,
                "budget_amount": match.get('budget_amount')
            })

            # Pattern analysis
            # By decision type
            dtype = match.get('decision_type', 'unknown')
            by_type[dtype]['complaints'] += complaint_count
            by_type[dtype]['testimony'] += testimony_count
            by_type[dtype]['gaps'].append(gap_pct)
            by_type[dtype]['count'] += 1

            # By budget range
            budget = match.get('budget_amount', 0)
            if budget:
                if budget >= 1000000:
                    brange = "$1M+"
                elif budget >= 500000:
                    brange = "$500K-$1M"
                elif budget >= 100000:
                    brange = "$100K-$500K"
                else:
                    brange = "<$100K"
            else:
                brange = "unknown"

            by_budget[brange]['complaints'] += complaint_count
            by_budget[brange]['testimony'] += testimony_count
            by_budget[brange]['gaps'].append(gap_pct)
            by_budget[brange]['count'] += 1

            # By month
            date_str = match.get('decision_date', '')
            if date_str:
                try:
                    if 'T' in date_str:
                        date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    else:
                        date_obj = datetime.fromisoformat(date_str)

                    month_key = date_obj.strftime('%Y-%m')
                    by_month[month_key]['complaints'] += complaint_count
                    by_month[month_key]['testimony'] += testimony_count
                    by_month[month_key]['gaps'].append(gap_pct)
                    by_month[month_key]['count'] += 1
                except:
                    pass

            # By meeting type (from decision metadata)
            # This would need to be added to decision during extraction
            meeting_type = match.get('meeting_type', 'unknown')
            by_meeting[meeting_type]['complaints'] += complaint_count
            by_meeting[meeting_type]['testimony'] += testimony_count
            by_meeting[meeting_type]['gaps'].append(gap_pct)
            by_meeting[meeting_type]['count'] += 1

    # Calculate averages
    stats['total_complaints'] = total_complaints
    stats['total_testimony'] = total_testimony
    stats['total_gap'] = total_complaints - total_testimony

    if stats['decisions_with_complaints'] > 0:
        stats['average_complaints_per_decision'] = total_complaints / stats['decisions_with_complaints']

    if stats['decisions_with_testimony_data'] > 0:
        stats['average_testimony_per_decision'] = total_testimony / stats['decisions_with_testimony_data']
        stats['average_gap_per_decision'] = stats['total_gap'] / stats['decisions_with_testimony_data']

    if gaps:
        stats['average_gap_percentage'] = sum(gaps) / len(gaps)

    # Compile pattern statistics
    def compile_pattern_stats(pattern_dict):
        return {
            key: {
                "count": data['count'],
                "total_complaints": data['complaints'],
                "total_testimony": data['testimony'],
                "average_gap_percentage": sum(data['gaps']) / len(data['gaps']) if data['gaps'] else 0
            }
            for key, data in pattern_dict.items()
        }

    stats['patterns']['by_decision_type'] = compile_pattern_stats(by_type)
    stats['patterns']['by_budget_range'] = compile_pattern_stats(by_budget)
    stats['patterns']['by_month'] = compile_pattern_stats(by_month)
    stats['patterns']['by_meeting_type'] = compile_pattern_stats(by_meeting)

    return stats


def print_analysis(stats: Dict):
    """Print detailed analysis report"""

    print("\n" + "=" * 70)
    print("📊 COORDINATION GAP ANALYSIS")
    print("=" * 70)

    print(f"\n📋 OVERALL STATISTICS")
    print(f"   Decisions analyzed: {stats['total_decisions']}")
    print(f"   Decisions with complaints: {stats['decisions_with_complaints']}")
    print(f"   Decisions with testimony data: {stats['decisions_with_testimony_data']}")

    print(f"\n📈 AGGREGATE NUMBERS")
    print(f"   Total complaints: {stats['total_complaints']}")
    print(f"   Total testimony: {stats['total_testimony']}")
    print(f"   Total gap: {stats['total_gap']} residents")

    print(f"\n📊 AVERAGES")
    print(f"   Complaints per decision: {stats['average_complaints_per_decision']:.1f}")
    print(f"   Testimony per decision: {stats['average_testimony_per_decision']:.1f}")
    print(f"   Gap per decision: {stats['average_gap_per_decision']:.1f} residents")
    print(f"   Average gap percentage: {stats['average_gap_percentage']:.1f}%")

    # Top gaps
    if stats['gaps_by_decision']:
        print(f"\n🔝 TOP 5 COORDINATION GAPS")
        sorted_gaps = sorted(
            stats['gaps_by_decision'],
            key=lambda x: x['gap'],
            reverse=True
        )[:5]

        for i, gap_info in enumerate(sorted_gaps, 1):
            print(f"\n   {i}. {gap_info['decision_title']}")
            print(f"      Date: {gap_info['decision_date']}")
            print(f"      Type: {gap_info['decision_type']}")
            print(f"      Complaints: {gap_info['complaints']}")
            print(f"      Testimony: {gap_info['testimony']}")
            print(f"      Gap: {gap_info['gap']} residents ({gap_info['gap_percentage']:.1f}%)")
            if gap_info.get('budget_amount'):
                print(f"      Budget: ${gap_info['budget_amount']:,.0f}")

    # Patterns
    patterns = stats['patterns']

    if patterns['by_decision_type']:
        print(f"\n📊 PATTERNS BY DECISION TYPE")
        for dtype, data in sorted(patterns['by_decision_type'].items(),
                                  key=lambda x: -x[1]['count']):
            print(f"   {dtype}: {data['count']} decisions, "
                  f"{data['total_complaints']} complaints, "
                  f"{data['average_gap_percentage']:.1f}% avg gap")

    if patterns['by_budget_range']:
        print(f"\n💰 PATTERNS BY BUDGET RANGE")
        budget_order = ["$1M+", "$500K-$1M", "$100K-$500K", "<$100K", "unknown"]
        for brange in budget_order:
            if brange in patterns['by_budget_range']:
                data = patterns['by_budget_range'][brange]
                print(f"   {brange}: {data['count']} decisions, "
                      f"{data['total_complaints']} complaints, "
                      f"{data['average_gap_percentage']:.1f}% avg gap")

    if patterns['by_month']:
        print(f"\n📅 PATTERNS BY MONTH")
        for month, data in sorted(patterns['by_month'].items()):
            print(f"   {month}: {data['count']} decisions, "
                  f"{data['total_complaints']} complaints, "
                  f"{data['average_gap_percentage']:.1f}% avg gap")

    print("\n" + "=" * 70)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Calculate coordination gaps and identify patterns'
    )
    parser.add_argument('matches_file',
                        help='JSON file from match_seeclickfix_to_decisions.py')
    parser.add_argument('--output',
                        help='Output file for updated results (default: overwrite input)')

    args = parser.parse_args()

    # Load matches
    with open(args.matches_file, 'r') as f:
        data = json.load(f)

    matches = data.get('matches', [])

    print(f"Loaded {len(matches)} decision matches from {args.matches_file}\n")

    # Calculate gaps
    stats = calculate_gaps(matches)

    # Update data
    data['statistics'] = stats
    data['matches'] = matches  # Updated with gap calculations
    data['gap_analysis_timestamp'] = datetime.now().isoformat()

    # Save
    output_file = args.output or args.matches_file

    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✅ Updated results saved to {output_file}")

    # Print analysis
    print_analysis(stats)


if __name__ == "__main__":
    main()
