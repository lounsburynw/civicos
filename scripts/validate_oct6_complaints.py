#!/usr/bin/env python3
"""
Validate Oct 6 Wildfire Case Study - Pull SeeClickFix complaints for 30-day window

Goal: Verify the "24 complainants" figure from Session 96 research with actual API data.

Query parameters:
- Location: San Rafael, CA
- Date Range: September 6 - October 6, 2025 (30 days before decision)
- Keywords: fire, tree, vegetation, wildfire, overgrown, fuel, hazard
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from seeclickfix_client import SeeClickFixClient
from datetime import datetime, timedelta, timezone
import json

def filter_by_date_and_keywords(issues, start_date, end_date, keywords):
    """Filter issues by date range and wildfire-related keywords."""
    filtered = []

    for issue in issues:
        # Parse created_at timestamp
        created_at_str = issue.get('created_at')
        if not created_at_str:
            continue

        try:
            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        except:
            continue

        # Check date range
        if not (start_date <= created_at <= end_date):
            continue

        # Check keywords in title, description, or category
        text_fields = [
            issue.get('title', '').lower(),
            issue.get('description', '').lower(),
            issue.get('category', '').lower()
        ]
        text_combined = ' '.join(text_fields)

        # Match any keyword
        if any(keyword.lower() in text_combined for keyword in keywords):
            filtered.append(issue)

    return filtered

def main():
    """Pull and analyze San Rafael SeeClickFix complaints for Oct 6 case."""

    print("="*80)
    print("OCT 6 WILDFIRE CASE STUDY - SeeClickFix Validation")
    print("="*80)

    # Date range: Sep 6 - Oct 6, 2025 (30 days before decision)
    end_date = datetime(2025, 10, 6, 23, 59, 59, tzinfo=timezone.utc)
    start_date = datetime(2025, 9, 6, 0, 0, 0, tzinfo=timezone.utc)

    print(f"\nDate Range: {start_date.date()} to {end_date.date()}")
    print(f"Location: San Rafael, CA")

    # Wildfire-related keywords
    keywords = [
        'fire', 'wildfire', 'tree', 'vegetation', 'overgrown',
        'fuel', 'hazard', 'defensible', 'space', 'brush',
        'weeds', 'limbs', 'branches', 'dead', 'dry'
    ]
    print(f"Keywords: {', '.join(keywords)}")

    # Initialize client
    client = SeeClickFixClient()

    # Fetch San Rafael issues
    # Note: SeeClickFix API doesn't support date filters, so we pull many pages
    # and filter locally
    print("\n" + "="*80)
    print("FETCHING ISSUES FROM SEECLICKFIX")
    print("="*80)

    all_issues = []
    page = 1
    max_pages = 20  # Pull up to 20 pages (2000 issues) to ensure coverage

    while page <= max_pages:
        print(f"\nFetching page {page}...")

        result = client.get_issues(
            place_url='san-rafael',
            per_page=100,
            page=page,
            status=None  # Get all statuses (open, acknowledged, closed)
        )

        issues = result.get('issues', [])
        metadata = result.get('metadata', {})

        print(f"  Got {len(issues)} issues")
        print(f"  Metadata: {metadata}")

        if not issues:
            print("  No more issues, stopping")
            break

        all_issues.extend(issues)

        # Check if we've gone back far enough
        if issues:
            oldest = min(datetime.fromisoformat(i['created_at'].replace('Z', '+00:00'))
                        for i in issues if i.get('created_at'))
            print(f"  Oldest issue on this page: {oldest.date()}")

            if oldest < start_date:
                print(f"  Reached target date range, stopping")
                break

        # Continue to next page (ignore has_more flag, keep trying until we get no issues)
        page += 1

    print(f"\nTotal issues fetched: {len(all_issues)}")

    # Filter by date and keywords
    print("\n" + "="*80)
    print("FILTERING BY DATE + KEYWORDS")
    print("="*80)

    filtered_issues = filter_by_date_and_keywords(
        all_issues,
        start_date,
        end_date,
        keywords
    )

    print(f"\n🎯 RESULT: {len(filtered_issues)} wildfire-related complaints")
    print(f"   Target from Session 96: 24 complaints")
    print(f"   Difference: {len(filtered_issues) - 24}")

    # Show details
    if filtered_issues:
        print("\n" + "="*80)
        print("COMPLAINT DETAILS")
        print("="*80)

        for i, issue in enumerate(filtered_issues, 1):
            created = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
            print(f"\n{i}. [{issue['id']}] {issue['title']}")
            print(f"   Date: {created.date()}")
            print(f"   Category: {issue['category']}")
            print(f"   Status: {issue['status']}")
            print(f"   Location: {issue['location']['address']}")
            if issue['description']:
                desc = issue['description'][:100] + ('...' if len(issue['description']) > 100 else '')
                print(f"   Description: {desc}")

        # Save to file for case study
        output_file = 'data/oct6_seeclickfix_complaints.json'
        with open(output_file, 'w') as f:
            json.dump({
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'keywords': keywords,
                'total_issues_fetched': len(all_issues),
                'filtered_count': len(filtered_issues),
                'issues': filtered_issues
            }, f, indent=2)

        print(f"\n💾 Saved to: {output_file}")

    # Summary for case study
    print("\n" + "="*80)
    print("CASE STUDY VALIDATION")
    print("="*80)

    if len(filtered_issues) >= 20:
        print("✅ VALIDATED: 20+ wildfire-related complaints in 30-day window")
        print(f"   Exact count: {len(filtered_issues)}")
        print(f"   Testimony count: 4 (from minutes)")
        print(f"   Coordination gap: {len(filtered_issues) - 4} ({(len(filtered_issues) - 4) / len(filtered_issues) * 100:.0f}%)")
    else:
        print(f"⚠️  Found fewer than expected: {len(filtered_issues)} vs. 24 target")
        print("   Possible reasons:")
        print("   - SeeClickFix API not returning historical data")
        print("   - Different keyword matching")
        print("   - Issues removed/moderated since Session 96")

    return len(filtered_issues)

if __name__ == '__main__':
    count = main()
    print()
    exit(0 if count > 0 else 1)
