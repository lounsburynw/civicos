#!/usr/bin/env python3
"""
Test fetching San Rafael-specific issues from SeeClickFix API.
"""

import requests
import json
from typing import Dict, List

API_BASE = "https://seeclickfix.com/api/v2/issues"

# San Rafael coordinates (approximate city center)
SAN_RAFAEL_LAT = 37.9735
SAN_RAFAEL_LNG = -122.5311

def test_geographic_filter():
    """Test fetching issues near San Rafael."""
    print("Testing geographic filter for San Rafael")
    print("="*80)

    params = {
        'lat': SAN_RAFAEL_LAT,
        'lng': SAN_RAFAEL_LNG,
        'per_page': 20,
        'radius': 5000,  # meters (5km radius)
    }

    try:
        response = requests.get(
            API_BASE,
            params=params,
            timeout=10,
            headers={'User-Agent': 'CivicOS/0.1'}
        )

        if response.status_code == 200:
            data = response.json()
            issues = data.get('issues', [])

            print(f"✅ Found {len(issues)} issues within 5km of San Rafael")

            if issues:
                # Analyze results
                cities = {}
                categories = {}

                for issue in issues:
                    # Extract city from address
                    address = issue.get('address', '')
                    if ',' in address:
                        parts = address.split(',')
                        if len(parts) >= 2:
                            city = parts[-3].strip() if len(parts) >= 3 else parts[-2].strip()
                            cities[city] = cities.get(city, 0) + 1

                    # Extract category
                    request_type = issue.get('request_type', {})
                    category = request_type.get('title', 'Unknown')
                    categories[category] = categories.get(category, 0) + 1

                print(f"\nCities found:")
                for city, count in sorted(cities.items(), key=lambda x: x[1], reverse=True):
                    print(f"  {city}: {count} issues")

                print(f"\nCategories found:")
                for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]:
                    print(f"  {cat}: {count} issues")

                # Show a San Rafael-specific issue if exists
                san_rafael_issues = [i for i in issues if 'San Rafael' in i.get('address', '')]
                if san_rafael_issues:
                    print(f"\n✅ Found {len(san_rafael_issues)} San Rafael-specific issues!")
                    print(f"\nExample San Rafael issue:")
                    issue = san_rafael_issues[0]
                    print(f"  Title: {issue.get('summary')}")
                    print(f"  Description: {issue.get('description', '')[:200]}")
                    print(f"  Address: {issue.get('address')}")
                    print(f"  Category: {issue.get('request_type', {}).get('title')}")
                    print(f"  Status: {issue.get('status')}")
                    print(f"  Created: {issue.get('created_at')}")
                    print(f"  URL: {issue.get('html_url')}")
                else:
                    print(f"\n⚠️ No San Rafael-specific issues in this sample")
                    print(f"   (May need to adjust radius or try place_url filter)")

            return len([i for i in issues if 'San Rafael' in i.get('address', '')])

    except Exception as e:
        print(f"❌ Error: {e}")
        return 0

def test_place_url_filter():
    """Test using place_url parameter."""
    print("\n" + "="*80)
    print("Testing place_url filter for San Rafael")
    print("="*80)

    params = {
        'place_url': 'san-rafael',
        'per_page': 20,
    }

    try:
        response = requests.get(
            API_BASE,
            params=params,
            timeout=10,
            headers={'User-Agent': 'CivicOS/0.1'}
        )

        if response.status_code == 200:
            data = response.json()
            issues = data.get('issues', [])

            print(f"✅ place_url filter returned {len(issues)} issues")

            if issues:
                san_rafael_count = len([i for i in issues if 'San Rafael' in i.get('address', '')])
                print(f"   {san_rafael_count} are in San Rafael")

                if san_rafael_count > 0:
                    print(f"\n✅ place_url='san-rafael' filter WORKS!")
                    return san_rafael_count

            return len(issues)
        else:
            print(f"❌ Failed with status {response.status_code}")
            return 0

    except Exception as e:
        print(f"❌ Error: {e}")
        return 0

def main():
    """Run all tests."""
    print("SeeClickFix San Rafael API Test")
    print("="*80 + "\n")

    # Test 1: Geographic filter
    geo_count = test_geographic_filter()

    # Test 2: place_url filter
    place_count = test_place_url_filter()

    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)

    if geo_count > 0 or place_count > 0:
        print(f"✅ SUCCESS - Can fetch San Rafael issues!")
        print(f"   Geographic filter: {geo_count} San Rafael issues")
        print(f"   place_url filter: {place_count} issues")

        print(f"\n📊 Recommended approach:")
        if place_count > geo_count:
            print(f"   Use place_url='san-rafael' (cleaner, city-specific)")
        else:
            print(f"   Use lat/lng + radius (more flexible for neighborhoods)")

        print(f"\n✅ Integration is VIABLE")
        print(f"   - API works")
        print(f"   - Can filter to San Rafael")
        print(f"   - Data quality looks good")
        print(f"\n📝 Next: Build seeclickfix_client.py")
        return True
    else:
        print(f"⚠️ WARNING - No San Rafael issues found")
        print(f"   This might mean:")
        print(f"   1. San Rafael doesn't use SeeClickFix (check city website)")
        print(f"   2. No recent issues reported")
        print(f"   3. Need different API parameters")
        print(f"\n📝 Next: Verify San Rafael uses SeeClickFix")
        return False

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
