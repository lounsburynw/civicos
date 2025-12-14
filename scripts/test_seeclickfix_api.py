#!/usr/bin/env python3
"""
Technical spike: Test SeeClickFix Open311 API access for San Rafael

Goal: Validate we can fetch real complaint data before committing to integration strategy.
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Potential SeeClickFix API endpoints for San Rafael
POTENTIAL_ENDPOINTS = [
    # Open311 standard format
    "https://seeclickfix.com/open311/v2/san-rafael",
    "https://sanrafael.seeclickfix.com/open311/v2",

    # SeeClickFix API v2 format
    "https://seeclickfix.com/api/v2/issues",

    # Direct city subdomain
    "https://sanrafael.seeclickfix.com/api/v2/issues",
]

def test_endpoint(base_url: str, params: Optional[Dict] = None) -> Dict:
    """Test an API endpoint and return results."""
    print(f"\n{'='*80}")
    print(f"Testing: {base_url}")
    print(f"Params: {params}")
    print(f"{'='*80}")

    try:
        response = requests.get(
            base_url,
            params=params,
            timeout=10,
            headers={'User-Agent': 'CivicOS/0.1 (Civic Engagement Platform)'}
        )

        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")

        if response.status_code == 200:
            try:
                data = response.json()
                print(f"✅ SUCCESS - Got JSON response")
                print(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'List response'}")

                # Try to extract issues count
                if isinstance(data, list):
                    print(f"Issues count: {len(data)}")
                    if len(data) > 0:
                        print(f"\nFirst issue sample:")
                        print(json.dumps(data[0], indent=2))
                elif isinstance(data, dict):
                    if 'issues' in data:
                        print(f"Issues count: {len(data['issues'])}")
                        if len(data['issues']) > 0:
                            print(f"\nFirst issue sample:")
                            print(json.dumps(data['issues'][0], indent=2))
                    elif 'requests' in data:
                        print(f"Requests count: {len(data['requests'])}")
                        if len(data['requests']) > 0:
                            print(f"\nFirst request sample:")
                            print(json.dumps(data['requests'][0], indent=2))
                    else:
                        print(f"\nFull response sample:")
                        print(json.dumps(data, indent=2)[:1000])

                return {
                    'success': True,
                    'endpoint': base_url,
                    'data': data
                }
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error: {e}")
                print(f"Raw response: {response.text[:500]}")
                return {'success': False, 'error': 'JSON decode failed'}
        else:
            print(f"❌ FAILED - Status {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return {'success': False, 'error': f'HTTP {response.status_code}'}

    except requests.exceptions.RequestException as e:
        print(f"❌ REQUEST ERROR: {e}")
        return {'success': False, 'error': str(e)}

def test_open311_discovery():
    """Test Open311 service discovery endpoint."""
    print("\n" + "="*80)
    print("TESTING OPEN311 SERVICE DISCOVERY")
    print("="*80)

    discovery_urls = [
        "https://seeclickfix.com/open311/v2/discovery.json",
        "https://sanrafael.seeclickfix.com/open311/v2/discovery.json",
    ]

    for url in discovery_urls:
        test_endpoint(url)

def test_seeclickfix_web_search():
    """Test if we can find San Rafael's SeeClickFix page via web search pattern."""
    print("\n" + "="*80)
    print("TESTING WEB-BASED SEECLICKFIX PAGE")
    print("="*80)

    # Many cities have a pattern like: https://seeclickfix.com/web_pages/{city-name}
    web_urls = [
        "https://seeclickfix.com/san-rafael",
        "https://seeclickfix.com/san_rafael",
        "https://seeclickfix.com/web_pages/san-rafael",
        "https://seeclickfix.com/cities/san-rafael",
    ]

    for url in web_urls:
        try:
            response = requests.get(url, timeout=5)
            print(f"{url} → {response.status_code}")
            if response.status_code == 200:
                print(f"✅ Found web page at: {url}")
                # Look for API hints in HTML
                if 'api' in response.text.lower():
                    print("   Page mentions 'api'")
        except Exception as e:
            print(f"{url} → Error: {e}")

def main():
    """Run all API tests."""
    print("SeeClickFix Open311 API Spike - San Rafael")
    print("="*80)

    results = []

    # Test 1: Open311 service discovery
    test_open311_discovery()

    # Test 2: Try various API endpoints
    for endpoint in POTENTIAL_ENDPOINTS:
        # Try without params
        result = test_endpoint(endpoint)
        if result.get('success'):
            results.append(result)
            break  # Found working endpoint

        # Try with place_url param (common SeeClickFix pattern)
        result = test_endpoint(
            endpoint,
            params={'place_url': 'san-rafael'}
        )
        if result.get('success'):
            results.append(result)
            break

        # Try with address param
        result = test_endpoint(
            endpoint,
            params={'address': 'San Rafael, CA'}
        )
        if result.get('success'):
            results.append(result)
            break

    # Test 3: Web page search
    test_seeclickfix_web_search()

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    if results:
        print(f"✅ Found {len(results)} working endpoint(s):")
        for r in results:
            print(f"   - {r['endpoint']}")

        print("\n📊 Next Steps:")
        print("   1. Use working endpoint in seeclickfix_client.py")
        print("   2. Build caching layer for performance")
        print("   3. Test AI matching against agenda items")
        print("   4. Build frontend display")
    else:
        print("❌ No working endpoints found")
        print("\n🤔 Alternatives:")
        print("   1. Contact San Rafael to ask about their SeeClickFix API")
        print("   2. Check if they use a different 311 system")
        print("   3. Fall back to policy-only issue tracker (no SeeClickFix integration)")
        print("   4. Web scraping (legal gray area, not recommended)")

    return len(results) > 0

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
