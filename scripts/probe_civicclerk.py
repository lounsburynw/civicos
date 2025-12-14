#!/usr/bin/env python3
"""Probe for CivicClerk API endpoints across Bay Area cities"""
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Bay Area cities that might use CivicClerk
CANDIDATE_CITIES = [
    # Contra Costa County
    ('concord', 'Concord'),
    ('antioch', 'Antioch'),
    ('pittsburg', 'Pittsburg'),
    ('richmond', 'Richmond'),
    ('walnutcreek', 'Walnut Creek'),
    ('martinez', 'Martinez'),
    ('sanpablo', 'San Pablo'),
    ('elcerrito', 'El Cerrito'),
    ('hercules', 'Hercules'),
    ('pinole', 'Pinole'),

    # Alameda County
    ('sanleandro', 'San Leandro'),
    ('hayward', 'Hayward'),
    ('fremont', 'Fremont'),
    ('pleasanton', 'Pleasanton'),
    ('livermore', 'Livermore'),
    ('dublin', 'Dublin'),
    ('albany', 'Albany'),
    ('alameda', 'Alameda'),
    ('unioncity', 'Union City'),
    ('newark', 'Newark'),

    # San Mateo County
    ('dalycity', 'Daly City'),
    ('sanmateo', 'San Mateo'),
    ('redwoodcity', 'Redwood City'),
    ('burlingame', 'Burlingame'),
    ('sancarlos', 'San Carlos'),
    ('fostercity', 'Foster City'),
    ('pacifica', 'Pacifica'),
    ('halfmoonbay', 'Half Moon Bay'),
    ('menlopark', 'Menlo Park'),

    # Santa Clara County
    ('sanjose', 'San Jose'),
    ('sunnyvale', 'Sunnyvale'),
    ('santaclara', 'Santa Clara'),
    ('cupertino', 'Cupertino'),
    ('milpitas', 'Milpitas'),
    ('campbell', 'Campbell'),
    ('losgatos', 'Los Gatos'),
    ('saratoga', 'Saratoga'),
    ('losaltos', 'Los Altos'),
    ('losaltoshills', 'Los Altos Hills'),
    ('montesereno', 'Monte Sereno'),
    ('mountainview', 'Mountain View'),
    ('paloalto', 'Palo Alto'),

    # Santa Cruz County
    ('santacruz', 'Santa Cruz'),
    ('capitola', 'Capitola'),
    ('watsonville', 'Watsonville'),
    ('scottsvalley', 'Scotts Valley'),

    # San Francisco Bay
    ('sanfrancisco', 'San Francisco'),
]

def probe_civicclerk(slug, name):
    """Check if city has CivicClerk API endpoint"""
    from urllib.parse import quote
    from datetime import datetime, timedelta

    # Build a simple query
    start_date = datetime.now()
    end_date = start_date + timedelta(days=30)
    start_str = start_date.strftime('%Y-%m-%dT00:00:00.000Z')
    end_str = end_date.strftime('%Y-%m-%dT23:59:59.999Z')
    filter_str = quote(f"startDateTime ge {start_str} and startDateTime le {end_str}")

    # Try common patterns with 'ca' suffix (California)
    # NOTE: API endpoint is .api.civicclerk.com, not .portal.civicclerk.com
    patterns = [
        f'https://{slug}ca.api.civicclerk.com/v1/Events?$filter={filter_str}',
        f'https://{slug}.api.civicclerk.com/v1/Events?$filter={filter_str}',
        f'https://city{slug}.api.civicclerk.com/v1/Events?$filter={filter_str}',
        f'https://cityof{slug}.api.civicclerk.com/v1/Events?$filter={filter_str}',
    ]

    for api_url in patterns:
        try:
            response = requests.get(api_url, timeout=5, headers={'Accept': 'application/json'})
            if response.status_code == 200:
                data = response.json()
                events = data.get('value', [])
                subdomain = api_url.split('//')[1].split('.')[0]
                return {
                    'name': name,
                    'slug': slug,
                    'subdomain': subdomain,
                    'api_url': api_url.split('?')[0],  # Remove query params
                    'status': 'FOUND',
                    'event_count': len(events)
                }
        except requests.exceptions.RequestException:
            continue

    return {'name': name, 'slug': slug, 'status': 'NOT_FOUND'}

print("=== CivicClerk API Discovery Scan ===\n")
print("Probing Bay Area cities for CivicClerk endpoints...\n")

found_cities = []
not_found = []

with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {executor.submit(probe_civicclerk, slug, name): (slug, name)
               for slug, name in CANDIDATE_CITIES}

    for future in as_completed(futures):
        result = future.result()
        if result['status'] == 'FOUND':
            found_cities.append(result)
            print(f"✅ FOUND: {result['name']}")
            print(f"   Subdomain: {result['subdomain']}")
            print(f"   Events: {result['event_count']}")
            print()
        else:
            not_found.append(result['name'])

print(f"\n{'='*60}")
print(f"RESULTS: {len(found_cities)} CivicClerk cities found")
print(f"{'='*60}\n")

if found_cities:
    print("Cities with CivicClerk API:")
    for city in sorted(found_cities, key=lambda x: x['name']):
        print(f"  • {city['name']}: {city['subdomain']} ({city['event_count']} upcoming events)")
        print(f"    API: {city['api_url']}")
else:
    print("⚠️  No additional CivicClerk cities found beyond El Cerrito")
    print("This may indicate CivicClerk has limited Bay Area deployment")

print(f"\nNot found ({len(not_found)} cities): {', '.join(sorted(not_found[:15]))}...")
