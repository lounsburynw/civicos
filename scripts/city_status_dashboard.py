#!/usr/bin/env python3
"""
Interactive city status dashboard for quick debugging.

Usage:
    python scripts/city_status_dashboard.py                    # show all cities
    python scripts/city_status_dashboard.py oakland            # single city detail
    python scripts/city_status_dashboard.py --platform Legistar # filter by platform
    python scripts/city_status_dashboard.py --broken            # show only broken
    python scripts/city_status_dashboard.py --degraded         # show only degraded
"""

import json
import sys
import argparse
from typing import Dict, List


def load_registry(registry_path: str = 'data/city_status_registry.json') -> Dict:
    """Load city status registry"""
    try:
        with open(registry_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Registry not found at {registry_path}", file=sys.stderr)
        print(f"   Run: python scripts/update_city_registry.py", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in {registry_path}: {e}", file=sys.stderr)
        sys.exit(1)


def find_city(registry: Dict, search_term: str) -> Dict:
    """Find city by name or jurisdiction_id (case-insensitive, partial match)"""
    search_lower = search_term.lower()

    # Exact match on jurisdiction_id
    for jid, city in registry['cities'].items():
        if jid.lower() == search_lower:
            return city

    # Partial match on name or jurisdiction_id
    matches = []
    for jid, city in registry['cities'].items():
        if (search_lower in city['name'].lower() or
            search_lower in jid.lower()):
            matches.append((jid, city))

    if len(matches) == 1:
        return matches[0][1]
    elif len(matches) > 1:
        print(f"❓ Multiple matches found for '{search_term}':", file=sys.stderr)
        for jid, city in matches:
            print(f"   - {city['name']} ({jid})", file=sys.stderr)
        sys.exit(1)
    else:
        return None


def show_city_detail(city: Dict, jurisdiction_id: str = None):
    """Show detailed status for single city including extraction history"""

    print("=" * 80)
    print(f"CITY DETAIL: {city['name']}")
    if jurisdiction_id:
        print(f"Jurisdiction ID: {jurisdiction_id}")
    print("=" * 80)

    # Status overview
    status_emoji = {
        'operational': '✅',
        'degraded': '⚠️ ',
        'broken': '❌'
    }.get(city['status'], '❓')

    print(f"\nStatus: {status_emoji} {city['status'].upper()}")
    print(f"Platform: {city['platform']}")
    print(f"Last Extraction: {city['last_extraction']}")

    # Current metrics
    print("\n--- CURRENT METRICS ---")
    metrics = city['current_metrics']
    print(f"Events Found: {metrics['events']}")
    print(f"Agendas Parsed: {metrics['agendas_parsed']}")
    print(f"Actionable Items: {metrics['actionable_items']}")
    print(f"Parse Rate: {metrics['parse_rate']:.0%}")
    print(f"Avg Items per Agenda: {metrics['avg_items_per_agenda']:.1f}")

    # Extraction history
    if 'extraction_history' in city and city['extraction_history']:
        print("\n--- EXTRACTION HISTORY ---")
        for i, extraction in enumerate(city['extraction_history']):
            print(f"\nExtraction {i+1}: {extraction['timestamp']}")
            print(f"  Events: {extraction['events_found']} | "
                  f"Parsed: {extraction['agendas_parsed']} | "
                  f"Items: {extraction['items_extracted']} | "
                  f"Rate: {extraction['parse_rate']:.0%}")
            if extraction.get('cost', 0) > 0:
                print(f"  Cost: ${extraction['cost']:.4f}")
            if extraction.get('errors'):
                print(f"  Errors: {', '.join(extraction['errors'][:2])}")

    # Known limitations
    if city.get('known_limitations'):
        print("\n--- KNOWN LIMITATIONS ---")
        for limitation in city['known_limitations']:
            print(f"  • {limitation}")

    # Platform config
    if city.get('platform_config'):
        print("\n--- PLATFORM CONFIG ---")
        config = city['platform_config']
        print(f"Agent Type: {config.get('agent_type', 'unknown')}")
        print(f"Meeting URLs:")
        for url in config.get('meeting_urls', []):
            print(f"  - {url}")
        print(f"Agenda Parsing: {'Enabled' if config.get('agenda_parsing_enabled') else 'Disabled'}")

    # Notes
    if city.get('notes'):
        print("\n--- NOTES ---")
        print(city['notes'])

    # Duplicate warning
    if 'duplicate_warning' in city:
        print("\n--- ⚠️  DUPLICATE WARNING ---")
        print(city['duplicate_warning'])

    # Debugging suggestions
    if city['status'] == 'broken':
        print("\n--- 🔧 DEBUGGING SUGGESTIONS ---")
        print("1. Check source URL accessibility:")
        if city.get('platform_config'):
            for url in city['platform_config'].get('meeting_urls', []):
                print(f"   curl -I '{url}'")
        print("2. Test extraction manually:")
        print(f"   python src/civic_digest.py schema '<meeting_url>' --skip-agenda-parsing")
        print("3. Inspect platform HTML structure")
        print("4. Check automated_civic_refresh.py CITY_CONFIGS")

    elif city['status'] == 'degraded' and city['platform'] != 'CivicClerk':
        print("\n--- 🔧 DEBUGGING SUGGESTIONS ---")
        print("1. Check if agendas are actually published yet (future meetings)")
        print("2. Try re-running extraction closer to meeting dates")
        print("3. Manually verify agenda URLs are accessible")

    print("\n" + "=" * 80)


def filter_cities(registry: Dict, platform: str = None, status: str = None) -> List:
    """Filter cities by platform and/or status"""
    filtered = []

    for jid, city in sorted(registry['cities'].items()):
        if platform and city['platform'].lower() != platform.lower():
            continue
        if status and city['status'] != status:
            continue
        filtered.append((jid, city))

    return filtered


def show_summary(registry: Dict, platform: str = None, status: str = None):
    """Show summary of all cities (optionally filtered)"""

    filtered = filter_cities(registry, platform, status)

    if not filtered:
        print(f"No cities found matching filters (platform={platform}, status={status})")
        return

    print("=" * 80)
    title = "ALL CITIES"
    if platform:
        title += f" - Platform: {platform}"
    if status:
        title += f" - Status: {status}"
    print(title)
    print("=" * 80)

    for jid, city in filtered:
        status_emoji = {
            'operational': '✅',
            'degraded': '⚠️ ',
            'broken': '❌'
        }.get(city['status'], '❓')

        metrics = city['current_metrics']
        print(f"{status_emoji} {city['name']:25} | {city['platform']:12} | "
              f"{metrics['parse_rate']:4.0%} parse | "
              f"{metrics['events']:2} events | "
              f"{metrics['actionable_items']:3} items")

    print(f"\nTotal: {len(filtered)} cities")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Interactive city status dashboard',
        epilog='Examples:\n'
               '  %(prog)s                      # Show all cities summary\n'
               '  %(prog)s oakland              # Show Oakland detail\n'
               '  %(prog)s --platform Legistar  # Show only Legistar cities\n'
               '  %(prog)s --broken             # Show only broken cities\n',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('city', nargs='?', help='City name or jurisdiction_id to show details')
    parser.add_argument('--platform', help='Filter by platform (Legistar, CivicClerk, etc)')
    parser.add_argument('--broken', action='store_true', help='Show only broken cities')
    parser.add_argument('--degraded', action='store_true', help='Show only degraded cities')
    parser.add_argument('--operational', action='store_true', help='Show only operational cities')
    parser.add_argument('--registry', default='data/city_status_registry.json',
                       help='Path to registry JSON (default: data/city_status_registry.json)')

    args = parser.parse_args()

    # Load registry
    registry = load_registry(args.registry)

    # Determine status filter
    status = None
    if args.broken:
        status = 'broken'
    elif args.degraded:
        status = 'degraded'
    elif args.operational:
        status = 'operational'

    # Show city detail or summary
    if args.city:
        city = find_city(registry, args.city)
        if city:
            # Find jurisdiction_id for display
            jid = None
            for jurisdiction_id, c in registry['cities'].items():
                if c == city:
                    jid = jurisdiction_id
                    break
            show_city_detail(city, jid)
        else:
            print(f"❌ City not found: {args.city}", file=sys.stderr)
            print(f"\nAvailable cities:", file=sys.stderr)
            for jid, c in sorted(registry['cities'].items())[:10]:
                print(f"  - {c['name']} ({jid})", file=sys.stderr)
            if len(registry['cities']) > 10:
                print(f"  ... and {len(registry['cities']) - 10} more", file=sys.stderr)
            sys.exit(1)
    else:
        show_summary(registry, args.platform, status)


if __name__ == '__main__':
    main()
