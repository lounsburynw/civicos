#!/usr/bin/env python3
"""
Bay Area Legistar Auto-Discovery Script
Systematically test for additional API clients
"""

import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import requests
import time
from typing import Dict, List

class LegistarDiscovery:
    """Auto-discovery system for Legistar API clients"""

    def __init__(self):
        self.session = requests.Session()
        self.discovered_clients = []
        self.failed_clients = []

    def test_client(self, client_name: str, timeout: int = 5) -> Dict:
        """Test if a Legistar client exists and is accessible"""
        base_url = f"https://webapi.legistar.com/v1/{client_name}"

        result = {
            'client_name': client_name,
            'api_accessible': False,
            'bodies_count': 0,
            'events_count': 0,
            'test_results': []
        }

        try:
            print(f"🔍 Testing {client_name}...", end=" ")

            # Test Bodies endpoint
            bodies_response = self.session.get(f"{base_url}/bodies", params={"$top": 1}, timeout=timeout)
            if bodies_response.status_code == 200:
                bodies_data = bodies_response.json()
                if isinstance(bodies_data, list):
                    result['bodies_count'] = len(bodies_data)
                    result['test_results'].append('bodies_ok')

                    # Test Events endpoint
                    events_response = self.session.get(f"{base_url}/events", params={"$top": 1}, timeout=timeout)
                    if events_response.status_code == 200:
                        events_data = events_response.json()
                        if isinstance(events_data, list):
                            result['events_count'] = len(events_data)
                            result['test_results'].append('events_ok')
                            result['api_accessible'] = True
                            print("✅ WORKING")
                            self.discovered_clients.append(client_name)
                            return result

            print("❌ Failed")
            self.failed_clients.append(client_name)

        except Exception as e:
            print(f"❌ Error: {str(e)[:30]}...")
            self.failed_clients.append(client_name)
            result['test_results'].append(f'error: {str(e)[:50]}')

        return result

    def discover_bay_area_clients(self) -> List[Dict]:
        """Systematic discovery of Bay Area Legistar clients"""

        # Known working clients (for verification)
        known_working = ['oakland', 'santa-rosa', 'sonoma-county']

        # Bay Area cities and counties to test
        discovery_patterns = {
            'major_cities': [
                'san-jose', 'san-francisco', 'fremont', 'hayward',
                'richmond', 'berkeley', 'palo-alto', 'mountain-view',
                'sunnyvale', 'santa-clara', 'redwood-city', 'san-mateo',
                'daly-city', 'vallejo', 'antioch', 'concord', 'livermore',
                'tracy', 'napa', 'petaluma', 'novato', 'san-rafael'
            ],
            'counties': [
                'alameda-county', 'contra-costa-county', 'marin-county',
                'san-mateo-county', 'santa-clara-county', 'solano-county',
                'napa-county'
            ],
            'regional_agencies': [
                'bart', 'golden-gate-bridge', 'bay-area-rapid-transit',
                'samtrans', 'vta', 'ac-transit'
            ],
            'special_districts': [
                'acwd', 'ebmud', 'sfwater', 'water-district',
                'bay-area-water', 'peninsula-water'
            ]
        }

        results = []
        total_tests = sum(len(patterns) for patterns in discovery_patterns.values())
        current_test = 0

        print(f"🚀 SYSTEMATIC LEGISTAR DISCOVERY - Testing {total_tests} patterns")
        print("=" * 60)

        # First verify known working clients
        print("\n📋 Verifying known working clients:")
        for client in known_working:
            result = self.test_client(client)
            results.append(result)
            current_test += 1

        # Test each category
        for category, patterns in discovery_patterns.items():
            print(f"\n🏛️  Testing {category.replace('_', ' ').title()} ({len(patterns)} patterns):")

            for pattern in patterns:
                result = self.test_client(pattern)
                results.append(result)
                current_test += 1

                # Rate limiting - don't overwhelm the API
                time.sleep(0.2)

                # Progress indicator
                if current_test % 10 == 0:
                    print(f"   Progress: {current_test}/{total_tests} completed")

        return results

    def generate_summary(self, results: List[Dict]) -> None:
        """Generate discovery summary"""
        working_clients = [r for r in results if r['api_accessible']]
        failed_clients = [r for r in results if not r['api_accessible']]

        print("\n" + "=" * 60)
        print("🎯 DISCOVERY SUMMARY")
        print("=" * 60)

        print(f"\n✅ WORKING CLIENTS ({len(working_clients)}):")
        for client in working_clients:
            bodies = client['bodies_count']
            events = client['events_count']
            print(f"   • {client['client_name']} - {bodies} bodies, {events} events")

        print(f"\n❌ Failed clients: {len(failed_clients)}")

        if working_clients:
            print("\n🔧 LEGISTAR_CLIENT.PY UPDATE:")
            print("Add these to KNOWN_LEGISTAR_CLIENTS:")
            for client in working_clients:
                if client['client_name'] not in ['oakland', 'santa-rosa', 'sonoma-county']:
                    city_name = client['client_name'].replace('-', '_')
                    display_name = client['client_name'].replace('-', ' ').title()
                    print(f'''    "{client['client_name']}": {{
        "client_name": "{client['client_name']}",
        "status": "discovered_api",
        "expected_bodies": ["City Council", "Planning Commission"],
        "timezone": "America/Los_Angeles"
    }},''')

        print(f"\n💰 COST ESTIMATE:")
        print(f"   • {len(working_clients)} working clients")
        print(f"   • ~$0.05 per session per client")
        print(f"   • Estimated monthly cost: ${len(working_clients) * 0.05 * 30:.2f}")

def main():
    discovery = LegistarDiscovery()
    results = discovery.discover_bay_area_clients()
    discovery.generate_summary(results)

if __name__ == "__main__":
    main()