#!/usr/bin/env python3
"""
Match SeeClickFix complaints to high-stakes decisions

Takes output from analyze_sanrafael_retrospective.py and matches
each decision to SeeClickFix complaints using:
- 30-day lookback window before decision
- Keywords extracted during retrospective analysis
- Geographic filtering (San Rafael)

Calculates coordination gap: (complaints - testimony) / complaints
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from seeclickfix_client import SeeClickFixClient
from datetime import datetime, timedelta, timezone
import json
from typing import List, Dict, Optional


def parse_decision_date(date_str: str) -> datetime:
    """Parse decision date to datetime object"""
    # Handle various formats
    # "2025-10-06", "2025-10-06T18:00:00-07:00", "Mon Oct 06, 2025"

    try:
        # Try ISO format first
        if 'T' in date_str:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            # Try YYYY-MM-DD
            return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except:
        # Try parsing from scraped metadata
        return None


def filter_by_keywords(issues: List[Dict], keywords: List[str]) -> List[Dict]:
    """
    Filter issues by keywords in title, description, or category

    Uses case-insensitive matching across all text fields
    """
    if not keywords:
        return []

    filtered = []

    for issue in issues:
        # Combine all text fields
        text_fields = [
            issue.get('title', '').lower(),
            issue.get('description', '').lower(),
            issue.get('category', '').lower(),
            issue.get('request_type', {}).get('title', '').lower()
        ]
        text_combined = ' '.join(text_fields)

        # Match any keyword
        if any(keyword.lower() in text_combined for keyword in keywords):
            # Track which keywords matched
            matched_keywords = [k for k in keywords if k.lower() in text_combined]
            issue['_matched_keywords'] = matched_keywords
            filtered.append(issue)

    return filtered


def match_decision_to_complaints(
    decision: Dict,
    client: SeeClickFixClient,
    lookback_days: int = 30,
    max_pages: int = 10
) -> Dict:
    """
    Match a single decision to SeeClickFix complaints

    Returns:
        {
            "decision_id": decision title,
            "decision_date": ISO date,
            "keywords": [...],
            "lookback_window": {"start": "...", "end": "..."},
            "complaints_found": count,
            "complaints": [...],
            "coordination_gap": null (needs testimony count)
        }
    """
    # Parse decision date
    decision_date_str = decision.get('meeting_date', '')
    decision_date = parse_decision_date(decision_date_str)

    if not decision_date:
        return {
            "error": "Could not parse decision date",
            "decision_date_str": decision_date_str
        }

    # Calculate lookback window
    end_date = decision_date
    start_date = decision_date - timedelta(days=lookback_days)

    print(f"\n   Decision: {decision.get('title', 'Unknown')}")
    print(f"   Date: {decision_date.date()}")
    print(f"   Lookback: {start_date.date()} to {end_date.date()}")

    # Get keywords from decision
    keywords = decision.get('keywords_for_matching', [])
    if not keywords:
        print(f"   ⚠️  No keywords found - skipping")
        return {
            "decision_title": decision.get('title'),
            "decision_date": decision_date_str,
            "keywords": [],
            "complaints_found": 0,
            "complaints": [],
            "error": "No keywords for matching"
        }

    print(f"   Keywords: {', '.join(keywords[:10])}")

    # Fetch SeeClickFix issues for San Rafael
    print(f"   📥 Fetching SeeClickFix issues...")

    try:
        # Fetch issues (API doesn't support date filters, so we pull multiple pages)
        all_issues = []
        for page in range(1, max_pages + 1):
            issues = client.get_issues(
                place='san-rafael-ca',
                page=page,
                per_page=100
            )

            if not issues:
                break

            all_issues.extend(issues)

            # Check if oldest issue is before our window
            if issues:
                oldest_created = issues[-1].get('created_at', '')
                try:
                    oldest_date = datetime.fromisoformat(oldest_created.replace('Z', '+00:00'))
                    if oldest_date < start_date:
                        # We've gone far enough back
                        break
                except:
                    pass

        print(f"      Fetched {len(all_issues)} total issues from SeeClickFix")

        # Filter by date range
        date_filtered = []
        for issue in all_issues:
            created_at_str = issue.get('created_at', '')
            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    if start_date <= created_at <= end_date:
                        date_filtered.append(issue)
                except:
                    pass

        print(f"      {len(date_filtered)} issues in date range")

        # Filter by keywords
        keyword_matched = filter_by_keywords(date_filtered, keywords)

        print(f"      ✅ {len(keyword_matched)} complaints matched keywords")

        return {
            "decision_title": decision.get('title'),
            "decision_id": decision.get('item_ref'),
            "decision_date": decision_date_str,
            "decision_type": decision.get('decision_type'),
            "budget_amount": decision.get('budget_amount'),
            "keywords": keywords,
            "lookback_window": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": lookback_days
            },
            "complaints_found": len(keyword_matched),
            "complaints": [
                {
                    "id": issue.get('id'),
                    "title": issue.get('title'),
                    "description": issue.get('description', '')[:200],
                    "created_at": issue.get('created_at'),
                    "status": issue.get('status'),
                    "category": issue.get('category'),
                    "matched_keywords": issue.get('_matched_keywords', [])
                }
                for issue in keyword_matched
            ],
            "testimony_count": None,  # To be filled in from meeting minutes
            "coordination_gap": None,  # Calculated after testimony count added
            "coordination_gap_percentage": None
        }

    except Exception as e:
        print(f"      ❌ Error: {type(e).__name__}: {e}")
        return {
            "decision_title": decision.get('title'),
            "decision_date": decision_date_str,
            "error": str(e)
        }


def calculate_coordination_gaps(matches: List[Dict]) -> Dict:
    """
    Calculate coordination gap statistics across all matches

    Gap = (complaints - testimony) / complaints
    Only calculated when testimony_count is available
    """
    stats = {
        "total_decisions": len(matches),
        "decisions_with_complaints": 0,
        "total_complaints": 0,
        "average_complaints_per_decision": 0,
        "decisions_with_testimony_data": 0,
        "average_gap_percentage": None,
        "gaps_by_decision": []
    }

    total_complaints = 0
    decisions_with_complaints = 0
    gaps = []

    for match in matches:
        complaint_count = match.get('complaints_found', 0)
        testimony_count = match.get('testimony_count')

        total_complaints += complaint_count
        if complaint_count > 0:
            decisions_with_complaints += 1

        if testimony_count is not None and complaint_count > 0:
            gap = complaint_count - testimony_count
            gap_pct = (gap / complaint_count) * 100

            match['coordination_gap'] = gap
            match['coordination_gap_percentage'] = gap_pct

            gaps.append(gap_pct)

            stats['gaps_by_decision'].append({
                "decision_title": match.get('decision_title'),
                "complaints": complaint_count,
                "testimony": testimony_count,
                "gap": gap,
                "gap_percentage": gap_pct
            })

    stats['total_complaints'] = total_complaints
    stats['decisions_with_complaints'] = decisions_with_complaints

    if decisions_with_complaints > 0:
        stats['average_complaints_per_decision'] = total_complaints / decisions_with_complaints

    if gaps:
        stats['decisions_with_testimony_data'] = len(gaps)
        stats['average_gap_percentage'] = sum(gaps) / len(gaps)

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Match SeeClickFix complaints to high-stakes decisions'
    )
    parser.add_argument('decisions_file',
                        help='JSON file from analyze_sanrafael_retrospective.py')
    parser.add_argument('--output',
                        default='data/pilot/san_rafael_complaint_matches.json',
                        help='Output file for matches')
    parser.add_argument('--lookback-days', type=int, default=30,
                        help='Days before decision to look for complaints (default: 30)')
    parser.add_argument('--max-pages', type=int, default=10,
                        help='Maximum SeeClickFix pages to fetch (default: 10)')

    args = parser.parse_args()

    print("🔍 SEECLICKFIX COMPLAINT MATCHING")
    print("=" * 70)

    # Load high-stakes decisions
    with open(args.decisions_file, 'r') as f:
        data = json.load(f)

    decisions = data.get('decisions', [])

    print(f"Loaded {len(decisions)} high-stakes decisions from {args.decisions_file}")
    print(f"Lookback window: {args.lookback_days} days")
    print(f"Max pages per query: {args.max_pages}\n")

    # Initialize SeeClickFix client
    client = SeeClickFixClient()

    # Match each decision to complaints
    all_matches = []

    for i, decision in enumerate(decisions, 1):
        print(f"\n[{i}/{len(decisions)}] Matching decision...")

        match = match_decision_to_complaints(
            decision,
            client,
            lookback_days=args.lookback_days,
            max_pages=args.max_pages
        )

        all_matches.append(match)

    # Calculate statistics
    stats = calculate_coordination_gaps(all_matches)

    # Save results
    output = {
        "jurisdiction_id": data.get('jurisdiction_id'),
        "jurisdiction_name": data.get('jurisdiction_name'),
        "date_range": data.get('date_range'),
        "matching_timestamp": datetime.now().isoformat(),
        "lookback_days": args.lookback_days,
        "statistics": stats,
        "matches": all_matches
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    with open(args.output, 'w') as f:
        json.dump(output, f, indent=2)

    # Print summary
    print("\n" + "=" * 70)
    print("📊 MATCHING COMPLETE")
    print(f"\n   Decisions analyzed: {stats['total_decisions']}")
    print(f"   Decisions with complaints: {stats['decisions_with_complaints']}")
    print(f"   Total complaints found: {stats['total_complaints']}")

    if stats['average_complaints_per_decision'] > 0:
        print(f"   Average complaints per decision: {stats['average_complaints_per_decision']:.1f}")

    if stats['average_gap_percentage'] is not None:
        print(f"\n   Coordination gap statistics:")
        print(f"     Decisions with testimony data: {stats['decisions_with_testimony_data']}")
        print(f"     Average gap: {stats['average_gap_percentage']:.1f}%")

    print(f"\n✅ Results saved to {args.output}")

    print(f"\n📈 NEXT STEPS:")
    print(f"   1. Review complaint matches in {args.output}")
    print(f"   2. Add testimony counts from meeting minutes/videos")
    print(f"   3. Re-run to calculate coordination gaps:")
    print(f"      python scripts/calculate_coordination_gaps.py {args.output}")


if __name__ == "__main__":
    main()
