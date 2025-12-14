#!/usr/bin/env python3
"""
Discover California housing legislation using Perplexity API.
"""

import json
import os
import requests

def discover_housing_bills():
    """Use Perplexity to discover California housing bills 2017-2025."""
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        raise ValueError("PERPLEXITY_API_KEY not set")

    prompt = """List the most impactful California state housing legislation from 2017-2025 that requires local government implementation or creates opportunities for resident participation in local decisions.

For each bill provide:
1. Bill number (e.g., SB 9, AB 2011)
2. Full bill name/title
3. Year enacted (when it became law)
4. Brief summary (1-2 sentences)
5. Whether it requires local implementation (yes/no)
6. Key deadlines for local governments (if any)
7. Official leginfo.legislature.ca.gov URL
8. How residents can leverage this at local meetings

Focus on landmark legislation like:
- SB 9 (duplex conversion/lot splits)
- AB 2011 (affordable housing streamlining)
- SB 35 (streamlined housing approvals)
- AB 1287 (ADU regulations)
- SB 330 (Housing Crisis Act)
- And other similarly impactful bills

Format as a structured list with all metadata."""

    response = requests.post(
        'https://api.perplexity.ai/chat/completions',
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        },
        json={
            'model': 'sonar-pro',
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 3000,
            'temperature': 0.2
        },
        timeout=60
    )

    response.raise_for_status()
    data = response.json()

    # Extract the response
    result = data['choices'][0]['message']['content']
    citations = data.get('citations', [])

    print("=" * 80)
    print("CALIFORNIA HOUSING LEGISLATION DISCOVERY (2017-2025)")
    print("=" * 80)
    print()
    print(result)
    print()
    print("=" * 80)
    print(f"CITATIONS ({len(citations)} sources)")
    print("=" * 80)
    for i, citation in enumerate(citations, 1):
        print(f"{i}. {citation}")
    print()
    print("=" * 80)
    print(f"Cost: ${data['usage']['cost']['total_cost']:.4f}")
    print("=" * 80)

if __name__ == '__main__':
    discover_housing_bills()
