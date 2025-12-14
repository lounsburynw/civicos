"""
Test operational→agenda matching with real San Rafael data

Session 90: Validate matching logic works with actual SeeClickFix complaints
and real San Rafael City Council agenda items.
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from seeclickfix_client import SeeClickFixClient
from operational_agenda_matcher import OperationalAgendaMatcher


def load_san_rafael_agendas():
    """Load latest San Rafael event data"""
    events_dir = Path('data/events')
    san_rafael_files = sorted(events_dir.glob('events_city-san-rafael_*.json'), reverse=True)

    if not san_rafael_files:
        print("❌ No San Rafael event files found")
        return []

    latest_file = san_rafael_files[0]
    print(f"📄 Loading San Rafael agendas from: {latest_file.name}")

    with open(latest_file, 'r') as f:
        data = json.load(f)

    # Extract all actionable items from all events
    agenda_items = []
    for event in data.get('events', []):
        items = event.get('actionable_items', [])
        # Add event context to each item
        for item in items:
            item['event_date'] = event.get('date')
            item['event_name'] = event.get('name')
        agenda_items.extend(items)

    return agenda_items


def main():
    print("🔗 Testing Real San Rafael Operational→Agenda Matching")
    print("=" * 70)

    # Step 1: Fetch real operational issues from SeeClickFix
    print("\n📍 Fetching San Rafael operational issues from SeeClickFix...")
    client = SeeClickFixClient()
    result = client.get_issues(place_url='san-rafael', per_page=20, status='open')
    operational_issues = result.get('issues', [])

    print(f"✅ Found {len(operational_issues)} open operational issues")

    # Step 2: Load San Rafael agenda items
    print("\n📋 Loading San Rafael agenda items...")
    agenda_items = load_san_rafael_agendas()

    if not agenda_items:
        print("⚠️  No agenda items found - San Rafael may not have published agendas yet")
        print("   This is expected - we'll still show operational issues for future matching\n")

    print(f"✅ Found {len(agenda_items)} agenda items")

    # Step 3: Match operational issues to agenda items
    print("\n🔗 Matching operational issues to agenda items...")
    matcher = OperationalAgendaMatcher(use_llm=False)  # Keyword-only for now

    matches = matcher.match_issues_batch(
        operational_issues,
        agenda_items,
        min_confidence=20
    )

    # Step 4: Display results
    print(f"\n📊 Match Results:")
    print(f"   Total operational issues: {len(operational_issues)}")
    print(f"   Total agenda items: {len(agenda_items)}")
    print(f"   Matched issues: {len(matches)}")
    print(f"   Match rate: {len(matches) / len(operational_issues) * 100:.1f}%" if operational_issues else "   Match rate: N/A")

    # Show sample operational issues (even if no matches)
    print(f"\n📍 Sample Operational Issues:")
    for i, issue in enumerate(operational_issues[:5], 1):
        print(f"\n{i}. {issue['title']}")
        print(f"   Category: {issue['category']}")
        print(f"   Location: {issue['location']['address']}")
        print(f"   Status: {issue['status']}")

        # Check if this issue has matches
        if issue['id'] in matches:
            print(f"   💡 MATCHED to {len(matches[issue['id']])} agenda item(s):")
            for match in matches[issue['id']][:2]:  # Show top 2 matches
                print(f"      → {match['agenda_item']['title']}")
                print(f"        Confidence: {match['confidence']}")
                print(f"        Connection: {match['connection_type']}")

    # Show unmatched high-priority issues
    if agenda_items:
        print(f"\n🚨 High-Impact Unmatched Issues (could benefit from policy attention):")
        unmatched_issues = [
            issue for issue in operational_issues
            if issue['id'] not in matches and issue.get('rating', 0) > 1
        ]

        for i, issue in enumerate(unmatched_issues[:5], 1):
            print(f"\n{i}. {issue['title']}")
            print(f"   Category: {issue['category']}")
            print(f"   Rating: {issue.get('rating', 0)}")
            print(f"   💡 Opportunity: This could indicate need for policy discussion")

    # Statistics by category
    if agenda_items and matches:
        print(f"\n📈 Match Statistics by Category:")
        stats = matcher.get_match_statistics(operational_issues, agenda_items)
        for category, data in sorted(stats['by_category'].items(), key=lambda x: -x[1]['matched']):
            match_rate = data['matched'] / data['total'] * 100 if data['total'] > 0 else 0
            print(f"   {category}: {data['matched']}/{data['total']} ({match_rate:.0f}%)")

    # Example UX patterns (future)
    if matches:
        print(f"\n💡 Example UX Pattern (future implementation):")
        first_match_id = list(matches.keys())[0]
        first_match = matches[first_match_id][0]
        issue = next(i for i in operational_issues if i['id'] == first_match_id)

        print(f"\n   🔧 TIER 2: Operational → Policy Bridge")
        print(f"   \"{issue['title']}\"")
        print(f"   {issue.get('rating', 0)} neighbors reported this issue")
        print(f"   💡 Related: {first_match['agenda_item']['title']}")
        if first_match['agenda_item'].get('event_date'):
            print(f"   📅 City Council Meeting - {first_match['agenda_item']['event_date']}")
        print(f"   [See on SeeClickFix] [Draft Joint Comment] [Join {issue.get('rating', 0)} Neighbors]")

    print("\n" + "=" * 70)
    print("✅ Real data matching test complete!")
    print("\nNext steps:")
    print("  1. Frontend display (map + list view)")
    print("  2. Enable LLM matching for better accuracy")
    print("  3. Santa Venetia pilot prep")


if __name__ == "__main__":
    main()
