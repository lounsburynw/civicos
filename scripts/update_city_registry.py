#!/usr/bin/env python3
"""
Generate/update city status registry from extracted event data.
Run after each batch extraction to maintain operational visibility.

Usage:
    python scripts/update_city_registry.py
    python scripts/update_city_registry.py --city city-oakland  # single city
    python scripts/update_city_registry.py --report             # human-readable summary
"""

import json
import glob
import os
import sys
import argparse
import re
from datetime import datetime
from typing import Dict, List, Tuple
from collections import defaultdict


def parse_event_filename(filename: str) -> Tuple[str, str]:
    """
    Extract jurisdiction_id and timestamp from event filename.

    Examples:
        events_city-oakland_20251004_133427.json -> (city-oakland, 20251004_133427)
        events_bart_20251002_215041.json -> (bart, 20251002_215041)
    """
    basename = os.path.basename(filename)
    # Pattern: events_{jurisdiction_id}_{timestamp}.json
    match = re.match(r'events_(.+?)_(\d{8}_\d{6})\.json', basename)
    if match:
        return match.group(1), match.group(2)
    return None, None


def load_event_file(filepath: str) -> Dict:
    """Load and parse event JSON file"""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}", file=sys.stderr)
        return None


def detect_platform(event_data: Dict, jurisdiction_id: str = None) -> str:
    """Detect platform from CITY_CONFIGS first, then fall back to event data metadata"""

    # PRIORITY 1: Check CITY_CONFIGS for agent_type (authoritative source)
    if jurisdiction_id:
        try:
            from automated_civic_refresh import CITY_CONFIGS

            # Find matching config by jurisdiction_id
            for city_key, config in CITY_CONFIGS.items():
                if config.get('jurisdiction_id') == jurisdiction_id:
                    agent_type = config.get('agent_type', '')

                    # Map agent_type to platform name
                    platform_map = {
                        'legistar': 'Legistar',
                        'civicclerk': 'CivicClerk',
                        'granicus': 'Granicus',
                        'civicplus_cms': 'CivicPlus',
                        'berkeley_cms': 'Berkeley',
                        'standard': 'HTML'
                    }

                    if agent_type in platform_map:
                        return platform_map[agent_type]
                    break
        except (ImportError, Exception) as e:
            # Continue to fallback detection if config lookup fails
            pass

    # PRIORITY 2: Check event data metadata
    if not event_data or 'events' not in event_data:
        return "Unknown"

    events = event_data.get('events', [])
    if not events:
        return "Unknown"

    # Check first opportunity for platform metadata
    opp = events[0]

    if '_legistar_metadata' in opp:
        return "Legistar"
    elif '_civicclerk_metadata' in opp:
        return "CivicClerk"
    elif '_granicus_metadata' in opp:
        return "Granicus"
    elif '_civicplus_metadata' in opp:
        return "CivicPlus"
    elif 'scraped_from' in opp and 'sanrafael' in opp.get('scraped_from', '').lower():
        return "HTML"
    else:
        # Try to infer from source URL
        source_url = opp.get('source_url', '') or opp.get('scraped_from', '')
        if 'legistar.com' in source_url:
            return "Legistar"
        elif 'civicclerk.com' in source_url:
            return "CivicClerk"
        elif 'granicus.com' in source_url:
            return "Granicus"
        elif 'AgendaCenter' in source_url:
            return "CivicPlus"
        elif 'berkeleyca.gov' in source_url:
            return "Berkeley"
        else:
            return "Unknown"


def analyze_extraction(event_data: Dict, timestamp: str) -> Dict:
    """Analyze single extraction metrics"""
    if not event_data:
        return None

    events = event_data.get('events', [])
    events_found = len(events)
    agendas_parsed = 0
    items_extracted = 0
    errors = []

    for opp in events:
        agenda_expansion = opp.get('agenda_expansion', {})
        if agenda_expansion.get('parsed'):
            agendas_parsed += 1
            actionable_items = agenda_expansion.get('actionable_items', [])
            items_extracted += len(actionable_items)

        # Check for parse failures
        if agenda_expansion.get('available') and not agenda_expansion.get('parsed'):
            if 'parse_failure_reason' in agenda_expansion:
                errors.append(agenda_expansion['parse_failure_reason'])

    parse_rate = agendas_parsed / events_found if events_found > 0 else 0.0

    # Extract cost if available
    cost = event_data.get('generation_metadata', {}).get('generation_cost', 0.0)

    return {
        'timestamp': timestamp,
        'events_found': events_found,
        'agendas_parsed': agendas_parsed,
        'items_extracted': items_extracted,
        'parse_rate': round(parse_rate, 2),
        'cost': cost,
        'errors': list(set(errors))  # Deduplicate errors
    }


def detect_duplicates(jurisdiction_files: Dict[str, List[str]]) -> List[Tuple[str, str]]:
    """
    Find duplicate jurisdiction extractions.

    Returns list of (jurisdiction_id1, jurisdiction_id2) tuples that look like duplicates.
    """
    duplicates = []
    jurisdiction_ids = sorted(jurisdiction_files.keys())

    for i, jid1 in enumerate(jurisdiction_ids):
        for jid2 in jurisdiction_ids[i+1:]:
            # Check if one is a suffix variant of the other
            # e.g., 'city-losaltoshills' vs 'city-losaltoshillsca'
            base1 = jid1.rstrip('ca')
            base2 = jid2.rstrip('ca')

            if base1 == base2 or jid1.replace('-', '') == jid2.replace('-', ''):
                duplicates.append((jid1, jid2))

    return duplicates


def get_status(parse_rate: float, events_found: int, platform: str) -> str:
    """Determine city status based on metrics"""
    if events_found == 0:
        return "broken"

    if platform == "Unknown":
        return "broken"

    # Legistar should have high parse rate
    if platform == "Legistar" and parse_rate >= 0.7:
        return "operational"

    # CivicClerk has lower parse rates due to agenda publishing schedules
    if platform == "CivicClerk":
        if events_found > 0:
            # Even low parse rates are "operational" for CivicClerk
            # since agendas aren't published yet
            return "operational" if parse_rate >= 0.0 else "degraded"

    # CivicPlus similar to CivicClerk - calendar extraction works, agenda parsing varies
    if platform == "CivicPlus":
        if events_found > 0:
            # Event extraction working = operational, regardless of parse rate
            return "operational"

    # Berkeley platform (multi-pass extraction) - DEGRADED due to datetime issues
    if platform == "Berkeley":
        # Even with high parse rate, datetime extraction is broken
        return "degraded"  # Shows extraction timestamp, not meeting date

    # Other platforms
    if parse_rate >= 0.5:
        return "operational"
    elif parse_rate > 0:
        return "degraded"
    else:
        return "broken"


def get_known_limitations(platform: str, status: str, errors: List[str]) -> List[str]:
    """Get known limitations based on platform and status"""
    limitations = []

    if platform == "CivicClerk":
        limitations.append("CivicClerk API returns agendaId=0 for unpublished agendas")
        limitations.append("Many future meetings don't have agendas published yet")
        limitations.append("Parse rate improves closer to meeting dates")

    if platform == "CivicPlus":
        limitations.append("CivicPlus AgendaCenter calendar extraction (events only)")
        limitations.append("Agenda parsing depends on city publishing schedules")
        limitations.append("⚠️ DATETIME ISSUE: 50% failure rate - some cities show extraction timestamp instead of meeting date")
        limitations.append("Requires schema.org microdata with ISO datetime format")

    if platform == "Berkeley":
        limitations.append("Berkeley custom CMS with multi-pass extraction")
        limitations.append("❌ CRITICAL: Datetime extraction broken - shows extraction timestamp, not actual meeting date")
        limitations.append("User trust violation - verify dates manually before use")

    if platform == "Unknown":
        limitations.append("Platform not identified - extraction using fallback HTML parser")
        limitations.append("Need to inspect source URL and HTML structure manually")

    if status == "broken" and "Granicus" in platform:
        limitations.append("Granicus ViewPublisher view_id may be incorrect")
        limitations.append("Need to test alternate view_id values")

    if errors:
        for error in errors[:2]:  # Limit to first 2 errors
            limitations.append(f"Parse error: {error}")

    return limitations


def analyze_city_status(jurisdiction_id: str, filepaths: List[str], duplicates: List[Tuple]) -> Dict:
    """Analyze all extractions for a city, detect issues, generate status"""

    # Sort by timestamp (most recent first)
    file_data = []
    for filepath in filepaths:
        _, timestamp = parse_event_filename(filepath)
        if timestamp:
            file_data.append((timestamp, filepath))

    file_data.sort(reverse=True)

    if not file_data:
        return None

    # Load most recent extraction
    latest_timestamp, latest_filepath = file_data[0]
    latest_data = load_event_file(latest_filepath)

    if not latest_data:
        return None

    # Get basic info
    jurisdiction_info = latest_data.get('jurisdiction', {})
    city_name = jurisdiction_info.get('name', jurisdiction_id)

    # Detect platform (pass jurisdiction_id for config lookup)
    platform = detect_platform(latest_data, jurisdiction_id)

    # Analyze extraction history (up to last 5)
    extraction_history = []
    for timestamp, filepath in file_data[:5]:
        event_data = load_event_file(filepath)
        analysis = analyze_extraction(event_data, timestamp)
        if analysis:
            extraction_history.append(analysis)

    # Current metrics from latest extraction
    current_metrics = extraction_history[0] if extraction_history else {}

    # Determine status
    parse_rate = current_metrics.get('parse_rate', 0.0)
    events_found = current_metrics.get('events_found', 0)
    status = get_status(parse_rate, events_found, platform)

    # Get limitations
    errors = current_metrics.get('errors', [])
    limitations = get_known_limitations(platform, status, errors)

    # Check if this is a duplicate
    duplicate_warning = None
    for jid1, jid2 in duplicates:
        if jurisdiction_id in (jid1, jid2):
            other = jid2 if jurisdiction_id == jid1 else jid1
            duplicate_warning = f"DUPLICATE: Also extracted as '{other}' - need jurisdiction_id normalization"
            break

    # Build city status dict
    city_status = {
        'name': city_name,
        'jurisdiction_id': jurisdiction_id,
        'platform': platform,
        'status': status,
        'last_extraction': f"{latest_timestamp[:8]}-{latest_timestamp[8:10]}-{latest_timestamp[10:12]}T{latest_timestamp[13:15]}:{latest_timestamp[15:17]}:{latest_timestamp[17:19]}Z",
        'extraction_history': extraction_history[:3],  # Keep last 3
        'current_metrics': {
            'events': current_metrics.get('events_found', 0),
            'agendas_parsed': current_metrics.get('agendas_parsed', 0),
            'actionable_items': current_metrics.get('items_extracted', 0),
            'parse_rate': current_metrics.get('parse_rate', 0.0),
            'avg_items_per_agenda': round(
                current_metrics.get('items_extracted', 0) / current_metrics.get('agendas_parsed', 1),
                1
            ) if current_metrics.get('agendas_parsed', 0) > 0 else 0.0
        },
        'known_limitations': limitations,
        'notes': get_notes(status, platform, parse_rate)
    }

    if duplicate_warning:
        city_status['duplicate_warning'] = duplicate_warning

    # Add platform config if available
    meeting_url = jurisdiction_info.get('meeting_calendar_url')
    if meeting_url:
        city_status['platform_config'] = {
            'agent_type': platform.lower(),
            'meeting_urls': [meeting_url],
            'agenda_parsing_enabled': True
        }

    return city_status


def get_notes(status: str, platform: str, parse_rate: float) -> str:
    """Generate notes based on status"""
    if status == "operational" and platform == "Legistar":
        return "Best performing city - consistent agenda publication"
    elif status == "operational" and platform == "CivicClerk":
        return "Events extracting correctly, agenda availability depends on city publishing schedule"
    elif status == "operational" and platform == "CivicPlus":
        return "⚠️ Event extraction working but verify meeting dates (50% failure rate on datetime)"
    elif status == "degraded" and platform == "Berkeley":
        return "❌ DATETIME BROKEN - Shows extraction timestamp, not actual meeting date"
    elif status == "degraded":
        return f"Low parse rate ({parse_rate:.0%}) - check if agendas are published yet"
    elif status == "broken":
        return "NEEDS INVESTIGATION: Platform detection failed or extraction incomplete"
    else:
        return ""


def load_existing_registry(registry_path: str = 'data/city_status_registry.json') -> Dict:
    """Load existing registry if it exists"""
    try:
        with open(registry_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as e:
        print(f"⚠️  Warning: Existing registry corrupted, regenerating from scratch", file=sys.stderr)
        return None


def get_cities_needing_update(jurisdiction_files: Dict[str, List[str]], existing_registry: Dict) -> set:
    """
    Determine which cities need re-analysis based on new event files.

    Returns set of jurisdiction_ids that have event files newer than registry data.
    """
    if not existing_registry:
        # No existing registry - update all
        return set(jurisdiction_files.keys())

    cities_to_update = set()
    existing_cities = existing_registry.get('cities', {})

    for jurisdiction_id, filepaths in jurisdiction_files.items():
        # Get most recent event file timestamp for this city
        latest_event_timestamp = None
        for filepath in filepaths:
            _, timestamp = parse_event_filename(filepath)
            if timestamp and (not latest_event_timestamp or timestamp > latest_event_timestamp):
                latest_event_timestamp = timestamp

        if not latest_event_timestamp:
            continue

        # Check if city exists in registry
        if jurisdiction_id not in existing_cities:
            cities_to_update.add(jurisdiction_id)
            continue

        # Compare with registry's last_extraction timestamp
        city_data = existing_cities[jurisdiction_id]
        registry_timestamp = city_data.get('extraction_history', [{}])[0].get('timestamp', '')

        if latest_event_timestamp > registry_timestamp:
            cities_to_update.add(jurisdiction_id)

    return cities_to_update


def generate_registry(filter_city: str = None, incremental: bool = False, registry_path: str = 'data/city_status_registry.json') -> Dict:
    """Generate complete city status registry from data/events/*.json

    Args:
        filter_city: Optional jurisdiction_id to analyze (ignores others)
        incremental: If True, only re-analyze cities with new event files
        registry_path: Path to existing registry (for incremental mode)

    Returns:
        Complete registry dict
    """

    # Find all event files
    event_files = glob.glob('data/events/events_*.json')

    # Group by jurisdiction_id
    jurisdiction_files = defaultdict(list)
    for filepath in event_files:
        jurisdiction_id, _ = parse_event_filename(filepath)
        if jurisdiction_id:
            jurisdiction_files[jurisdiction_id].append(filepath)

    # Detect duplicates
    duplicates = detect_duplicates(jurisdiction_files)

    # Incremental mode: load existing registry and determine what needs updating
    existing_registry = None
    cities_to_update = set()

    if incremental:
        existing_registry = load_existing_registry(registry_path)
        if existing_registry:
            cities_to_update = get_cities_needing_update(jurisdiction_files, existing_registry)
            print(f"🔄 Incremental mode: {len(cities_to_update)} cities need updating", file=sys.stderr)
        else:
            print(f"⚠️  No existing registry found, performing full analysis", file=sys.stderr)
            incremental = False  # Fall back to full regeneration

    # Start with existing cities if incremental
    if incremental and existing_registry:
        cities = existing_registry.get('cities', {}).copy()
    else:
        cities = {}

    # Analyze cities (all cities, or just those needing update)
    analysis_count = 0
    for jurisdiction_id, filepaths in sorted(jurisdiction_files.items()):
        if filter_city and jurisdiction_id != filter_city:
            continue

        # Skip if incremental and city doesn't need update
        if incremental and jurisdiction_id not in cities_to_update:
            continue

        city_status = analyze_city_status(jurisdiction_id, filepaths, duplicates)
        if city_status:
            cities[jurisdiction_id] = city_status
            analysis_count += 1

    if incremental:
        print(f"✅ Analyzed {analysis_count} cities (skipped {len(cities) - analysis_count} unchanged)", file=sys.stderr)

    # Platform summary
    platform_summary = defaultdict(lambda: {
        'cities': 0,
        'total_parse_rate': 0.0,
        'total_items': 0,
        'status': 'unknown'
    })

    for city_id, city in cities.items():
        platform = city['platform']
        platform_summary[platform]['cities'] += 1
        platform_summary[platform]['total_parse_rate'] += city['current_metrics']['parse_rate']
        platform_summary[platform]['total_items'] += city['current_metrics']['actionable_items']

    # Calculate averages and status
    for platform, stats in platform_summary.items():
        count = stats['cities']
        stats['avg_parse_rate'] = round(stats['total_parse_rate'] / count, 2) if count > 0 else 0.0
        del stats['total_parse_rate']

        # Determine platform status
        avg_rate = stats['avg_parse_rate']
        if platform == "Legistar" and avg_rate >= 0.7:
            stats['status'] = 'excellent'
        elif platform == "CivicClerk":
            stats['status'] = 'operational'
            stats['notes'] = "Low parse rate due to agenda publishing schedules, not code issues"
        elif platform == "Unknown":
            stats['status'] = 'needs_investigation'
            stats['notes'] = "Platform detection failed - need manual URL inspection"
        elif avg_rate >= 0.5:
            stats['status'] = 'operational'
        else:
            stats['status'] = 'degraded'

    registry = {
        'last_updated': datetime.utcnow().isoformat() + 'Z',
        'total_cities': len(cities),
        'duplicate_count': len(duplicates),
        'cities': cities,
        'platform_summary': dict(platform_summary)
    }

    return registry


def print_human_report(registry: Dict):
    """Print human-readable status report for solo dev"""
    print("=" * 80)
    print("CIVIC CITY STATUS REGISTRY")
    print("=" * 80)
    print(f"\nLast Updated: {registry['last_updated']}")
    print(f"Total Cities: {registry['total_cities']}")
    if registry.get('duplicate_count', 0) > 0:
        print(f"⚠️  Duplicate Extractions: {registry['duplicate_count']} pairs")

    print("\n" + "=" * 80)
    print("OPERATIONAL CITIES")
    print("=" * 80)
    operational = [(jid, city) for jid, city in sorted(registry['cities'].items())
                   if city['status'] == 'operational']

    if operational:
        for city_id, city in operational:
            print(f"✅ {city['name']:25} | {city['platform']:12} | "
                  f"{city['current_metrics']['parse_rate']:4.0%} parse | "
                  f"{city['current_metrics']['actionable_items']:3} items")
    else:
        print("(none)")

    print("\n" + "=" * 80)
    print("DEGRADED CITIES (Low Parse Rate)")
    print("=" * 80)
    degraded = [(jid, city) for jid, city in sorted(registry['cities'].items())
                if city['status'] == 'degraded']

    if degraded:
        for city_id, city in degraded:
            limitation = city['known_limitations'][0] if city['known_limitations'] else 'Unknown'
            print(f"⚠️  {city['name']:25} | {city['platform']:12} | "
                  f"{city['current_metrics']['parse_rate']:4.0%} parse | "
                  f"Reason: {limitation[:50]}")
    else:
        print("(none)")

    print("\n" + "=" * 80)
    print("BROKEN CITIES (Need Investigation)")
    print("=" * 80)
    broken = [(jid, city) for jid, city in sorted(registry['cities'].items())
              if city['status'] == 'broken']

    if broken:
        for city_id, city in broken:
            print(f"❌ {city['name']:25} | {city['platform']:12} | "
                  f"Issue: {city['notes']}")
    else:
        print("(none)")

    print("\n" + "=" * 80)
    print("DUPLICATE WARNINGS")
    print("=" * 80)
    duplicates = [(jid, city) for jid, city in sorted(registry['cities'].items())
                  if 'duplicate_warning' in city]

    if duplicates:
        for city_id, city in duplicates:
            print(f"🔄 {city['name']:25} | {city['duplicate_warning']}")
    else:
        print("(none)")

    print("\n" + "=" * 80)
    print("PLATFORM SUMMARY")
    print("=" * 80)
    for platform, stats in sorted(registry['platform_summary'].items()):
        status_emoji = {
            'excellent': '⭐',
            'operational': '✅',
            'degraded': '⚠️ ',
            'needs_investigation': '❌'
        }.get(stats['status'], '❓')

        print(f"{status_emoji} {platform:15} | {stats['cities']:2} cities | "
              f"{stats['avg_parse_rate']:4.0%} avg parse | "
              f"{stats['total_items']:3} items | "
              f"{stats['status']}")

        if 'notes' in stats:
            print(f"   Note: {stats['notes']}")

    print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description='Generate city status registry',
        epilog='Examples:\n'
               '  %(prog)s                          # Full regeneration\n'
               '  %(prog)s --incremental            # Only analyze new/changed cities\n'
               '  %(prog)s --report                 # Full regen + human report\n'
               '  %(prog)s --incremental --report   # Incremental + report\n'
               '  %(prog)s --city city-oakland      # Analyze single city\n',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--city', help='Filter to specific jurisdiction_id')
    parser.add_argument('--report', action='store_true', help='Print human-readable report')
    parser.add_argument('--incremental', action='store_true',
                       help='Only re-analyze cities with new event files (faster)')
    parser.add_argument('--output', default='data/city_status_registry.json',
                       help='Output path (default: data/city_status_registry.json)')

    args = parser.parse_args()

    # Generate registry
    if args.incremental:
        print(f"🔄 Incremental update mode (analyzing only new/changed cities)...", file=sys.stderr)
    else:
        print(f"Analyzing event files in data/events/...", file=sys.stderr)

    registry = generate_registry(
        filter_city=args.city,
        incremental=args.incremental,
        registry_path=args.output
    )

    # Save JSON
    with open(args.output, 'w') as f:
        json.dump(registry, f, indent=2)

    print(f"✅ Registry saved to {args.output}", file=sys.stderr)

    # Print human report if requested or if stdout is a terminal
    if args.report or sys.stdout.isatty():
        print_human_report(registry)


if __name__ == '__main__':
    main()
