#!/usr/bin/env python3
"""
Fetch and display sample San Rafael SeeClickFix data.
"""

import requests
import json

API_BASE = "https://seeclickfix.com/api/v2/issues"

response = requests.get(
    API_BASE,
    params={'place_url': 'san-rafael', 'per_page': 5},
    headers={'User-Agent': 'CivicOS/0.1'}
)

if response.status_code == 200:
    data = response.json()
    issues = data.get('issues', [])

    print(f"Sample of {len(issues)} San Rafael SeeClickFix Issues")
    print("="*80 + "\n")

    for i, issue in enumerate(issues, 1):
        print(f"Issue #{i}:")
        print(f"  Title: {issue.get('summary')}")
        print(f"  Category: {issue.get('request_type', {}).get('title')}")
        print(f"  Description: {issue.get('description', 'N/A')[:150]}...")
        print(f"  Address: {issue.get('address')}")
        print(f"  Status: {issue.get('status')}")
        print(f"  Created: {issue.get('created_at')}")
        print(f"  Lat/Lng: {issue.get('lat')}, {issue.get('lng')}")
        print(f"  URL: {issue.get('html_url')}")
        print()

    # Save full sample to file for reference
    with open('/Users/nicolaslounsbury/projects/civic/data/seeclickfix_sample.json', 'w') as f:
        json.dump(issues, f, indent=2)
    print(f"✅ Full data saved to data/seeclickfix_sample.json")
