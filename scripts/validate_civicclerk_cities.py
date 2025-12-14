#!/usr/bin/env python3
"""
Validate CivicClerk cities discovered by probe_civicclerk.py
Tests data extraction quality for each city
"""

import sys
import json
import re
sys.path.insert(0, 'src')

from civicclerk_client import CivicClerkClient
from datetime import datetime

# Cities discovered by probe scan
CIVICCLERK_CITIES = [
    {'name': 'Daly City', 'subdomain': 'dalycityca', 'expected_events': 15},
    {'name': 'Los Altos', 'subdomain': 'losaltosca', 'expected_events': 15},
    {'name': 'Los Altos Hills', 'subdomain': 'losaltoshillsca', 'expected_events': 15},
    {'name': 'Milpitas', 'subdomain': 'milpitasca', 'expected_events': 10},
    {'name': 'Pinole', 'subdomain': 'pinoleca', 'expected_events': 6},
    {'name': 'Scotts Valley', 'subdomain': 'scottsvalleyca', 'expected_events': 5},
    {'name': 'Pleasanton', 'subdomain': 'pleasantonca', 'expected_events': 3},
    {'name': 'El Cerrito', 'subdomain': 'elcerritoca', 'expected_events': 2},  # Reference
    {'name': 'Pittsburg', 'subdomain': 'pittsburgca', 'expected_events': 2},
]

def validate_city(city_info):
    """Validate data extraction for a single city"""
    print(f"\n{'='*60}")
    print(f"Validating: {city_info['name']}")
    print(f"{'='*60}")

    subdomain = city_info['subdomain']
    client = CivicClerkClient(subdomain)

    # Get events
    events = client.get_events(days_ahead=90)

    print(f"✅ Events found: {len(events)} (expected: {city_info['expected_events']})")

    if not events:
        print("⚠️  No events - may be off season or no upcoming meetings")
        return {'city': city_info['name'], 'quality_score': 0, 'status': 'no_events'}

    # Analyze event quality
    events_with_agendas = sum(1 for e in events if e.get('hasAgenda'))
    events_with_location = sum(1 for e in events if e.get('address1'))

    print(f"   Agendas available: {events_with_agendas}/{len(events)} ({100*events_with_agendas//len(events)}%)")
    print(f"   Location data: {events_with_location}/{len(events)} ({100*events_with_location//len(events)}%)")

    # Test agenda file availability for first event with agenda
    agenda_available = False
    file_types_found = []
    potential_stale = False

    for event in events:
        if event.get('hasAgenda'):
            event_id = event.get('id')
            print(f"\n   Testing agenda files for event {event_id}...")

            try:
                # Fetch detailed event info which includes publishedFiles
                detailed_event = client.get_event_details(event_id)
                if not detailed_event:
                    print(f"   ⚠️  Could not fetch event details")
                    continue

                agenda_data = client.get_agenda_info(detailed_event)
                if agenda_data:
                    file_type = agenda_data.get('file_type', 'unknown')
                    file_url = agenda_data.get('file_url')
                    confidence = agenda_data.get('confidence', 'unknown')

                    file_types_found.append(file_type)

                    print(f"   ✅ Agenda file available: {file_type} (confidence: {confidence})")

                    if file_url:
                        agenda_available = True
                        print(f"      URL: {file_url[:80]}...")

                        # Check for potential stale content indicators in the file type/name
                        if re.search(r'\b(2018|2019|2020|2021)\b', file_type):
                            potential_stale = True
                            print(f"      ⚠️  Potential stale content detected in file type")

                    break
            except Exception as e:
                print(f"   ⚠️  Error checking agenda: {e}")
                break

    # Calculate quality score (0-10)
    score = 0
    if len(events) >= 3: score += 3  # Has sufficient data
    if events_with_agendas > 0: score += 2  # Has agendas
    if agenda_available: score += 3  # Agenda files accessible
    if events_with_location >= len(events) * 0.8: score += 1  # Good location data
    if not potential_stale: score += 1  # No stale content warnings

    print(f"\n📊 Data Quality Score: {score}/10")

    status = 'production_ready' if score >= 7 else ('needs_work' if score >= 5 else 'failed')

    return {
        'city': city_info['name'],
        'subdomain': subdomain,
        'events': len(events),
        'with_agendas': events_with_agendas,
        'with_location': events_with_location,
        'agenda_available': agenda_available,
        'file_types': list(set(file_types_found)),
        'potential_stale': potential_stale,
        'quality_score': score,
        'status': status
    }

if __name__ == '__main__':
    print("=== CivicClerk Cities Validation Suite ===")
    print("Testing data extraction quality across discovered cities\n")

    results = []

    # Test top 4 cities by event count
    test_cities = CIVICCLERK_CITIES[:4]

    for city_info in test_cities:
        try:
            result = validate_city(city_info)
            results.append(result)
        except Exception as e:
            print(f"❌ Fatal error validating {city_info['name']}: {e}")
            results.append({
                'city': city_info['name'],
                'quality_score': 0,
                'status': 'error',
                'error': str(e)
            })

    # Summary
    print(f"\n{'='*60}")
    print("VALIDATION SUMMARY")
    print(f"{'='*60}\n")

    for result in results:
        status_emoji = {'production_ready': '✅', 'needs_work': '⚠️', 'failed': '❌', 'error': '💥', 'no_events': '⏸️'}
        emoji = status_emoji.get(result['status'], '❓')
        print(f"{emoji} {result['city']}: {result['quality_score']}/10 ({result['status']})")
        if 'events' in result:
            print(f"   Events: {result['events']}, Agendas: {result.get('with_agendas', 0)}, File types: {', '.join(result.get('file_types', []))}")

    production_ready = sum(1 for r in results if r['status'] == 'production_ready')
    print(f"\n✅ Production ready: {production_ready}/{len(results)} cities")

    # Save results
    output_file = 'civicclerk_validation_results.json'
    with open(output_file, 'w') as f:
        json.dump({
            'validated_at': datetime.now().isoformat(),
            'cities_tested': len(results),
            'production_ready': production_ready,
            'results': results
        }, f, indent=2)

    print(f"\n💾 Results saved to: {output_file}")
