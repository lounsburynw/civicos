#!/usr/bin/env python3
"""
Automate legislative context generation for all topics.

Uses Perplexity API to discover and generate metadata for:
- Housing (already complete)
- Transportation
- Environment
- Budget

Time: ~30 minutes per topic = 1.5 hours total
Cost: ~$0.12 total ($0.04 per topic)
"""

import json
import os
import requests
from datetime import datetime
from typing import Dict, Any

PERPLEXITY_API_KEY = os.environ.get('PERPLEXITY_API_KEY')

TOPICS = {
    'transportation': {
        'keywords': ['transportation', 'transit', 'bicycle', 'pedestrian', 'VMT', 'complete streets', 'public transit'],
        'prompt_focus': 'transportation, transit, bicycle/pedestrian infrastructure, VMT reduction, complete streets',
        'example_bills': 'SB 743 (VMT), AB 1147 (transit-oriented development), etc.'
    },
    'environment': {
        'keywords': ['climate', 'environment', 'sustainability', 'clean energy', 'emissions', 'conservation', 'CEQA'],
        'prompt_focus': 'climate action, environmental protection, clean energy, emissions reduction, CEQA',
        'example_bills': 'SB 100 (clean energy), AB 1279 (carbon neutrality), etc.'
    },
    'budget': {
        'keywords': ['budget', 'tax', 'revenue', 'bond', 'fiscal', 'appropriation', 'Prop 13'],
        'prompt_focus': 'municipal finance, property tax, revenue measures, bonds, fiscal policy',
        'example_bills': 'Prop 13 split roll, AB 5 (gig economy), etc.'
    }
}

def query_perplexity(prompt: str, model: str = "sonar-pro") -> Dict[str, Any]:
    """Query Perplexity API."""
    response = requests.post(
        'https://api.perplexity.ai/chat/completions',
        headers={
            'Authorization': f'Bearer {PERPLEXITY_API_KEY}',
            'Content-Type': 'application/json'
        },
        json={
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 4000,
            'temperature': 0.2
        },
        timeout=120
    )
    response.raise_for_status()
    return response.json()

def discover_topic_bills(topic: str, config: Dict) -> Dict[str, Any]:
    """Discover bills for a specific topic."""
    prompt = f"""For California {topic} legislation from 2017-2025, provide COMPLETE metadata in JSON format for the most impactful bills related to {config['prompt_focus']}.

Find 4-6 landmark bills that:
1. Require local government implementation OR
2. Create opportunities for resident participation in local decisions

For each bill, provide:
{{
  "bill_id": "ca-sb743",
  "bill_number": "SB 743",
  "bill_name": "Full bill name",
  "year_enacted": 2013,
  "enactment_date": "2013-09-27",
  "status": "Active",
  "local_implementation_required": true,
  "local_deadline": "2020-07-01",
  "summary": "Brief 1-2 sentence summary",
  "leverage_point": "How residents can use this at local meetings",
  "official_url": "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=...",
  "keywords": {json.dumps(config['keywords'])}
}}

Examples of the types of bills to find: {config['example_bills']}

Return ONLY valid JSON array of bill objects. Use actual verified dates from leginfo.legislature.ca.gov."""

    print(f"\nQuerying Perplexity for {topic} bills...")
    result = query_perplexity(prompt)

    return {
        'content': result['choices'][0]['message']['content'],
        'citations': result.get('citations', []),
        'cost': result['usage']['cost']['total_cost']
    }

def parse_json_from_response(content: str) -> Any:
    """Extract JSON from response (handles markdown code blocks)."""
    if '```json' in content:
        start = content.find('```json') + 7
        end = content.find('```', start)
        content = content[start:end].strip()
    elif '```' in content:
        start = content.find('```') + 3
        end = content.find('```', start)
        content = content[start:end].strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        for start_char, end_char in [('[', ']'), ('{', '}')]:
            start = content.find(start_char)
            end = content.rfind(end_char)
            if start != -1 and end != -1:
                try:
                    return json.loads(content[start:end+1])
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"Could not extract JSON from response: {content[:200]}...")

def generate_topic_json(topic: str, bills_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate topic JSON from Perplexity data."""
    try:
        bills = parse_json_from_response(bills_data['content'])
    except (json.JSONDecodeError, ValueError) as e:
        print(f"WARNING: Could not parse Perplexity response: {e}")
        bills = []

    state_legislation = {}
    for bill in bills:
        bill_id = bill.get('bill_id', f"ca-{bill.get('bill_number', 'unknown').lower().replace(' ', '')}")
        state_legislation[bill_id] = {
            "bill": bill.get('bill_name', bill.get('bill_number', 'Unknown')),
            "status": bill.get('status', 'Active'),
            "enacted": bill.get('enactment_date'),
            "local_implementation_required": bill.get('local_implementation_required', True),
            "local_deadline": bill.get('local_deadline'),
            "leverage_point": bill.get('leverage_point', ''),
            "official_url": bill.get('official_url', ''),
            "summary": bill.get('summary', ''),
            "keywords": bill.get('keywords', TOPICS[topic]['keywords'])
        }

    return {
        "jurisdiction": "california",
        "topic": topic,
        "last_updated": datetime.now().isoformat(),
        "data_sources": [
            "Perplexity Sonar Pro API",
            "leginfo.legislature.ca.gov (cited by Perplexity)",
            "Trusted Perplexity sources (~90-95% precision)"
        ],
        "perplexity_citations": bills_data['citations'],
        "state_legislation": state_legislation,
        "federal_programs": {}
    }

def main():
    """Generate legislative context for all topics."""
    if not PERPLEXITY_API_KEY:
        print("ERROR: PERPLEXITY_API_KEY not set")
        return 1

    print("="*80)
    print("LEGISLATIVE CONTEXT AUTOMATION - ALL TOPICS")
    print("="*80)
    print("\nGenerating context for: transportation, environment, budget")
    print("Estimated time: 1.5 hours")
    print("Estimated cost: $0.12\n")

    total_cost = 0.0
    results = {}

    for topic, config in TOPICS.items():
        print("\n" + "="*80)
        print(f"TOPIC: {topic.upper()}")
        print("="*80)

        # Check cache
        cache_file = f'data/legislative_context/.cache_{topic}_bills.json'
        if os.path.exists(cache_file):
            print(f"Loading from cache: {cache_file}")
            with open(cache_file, 'r') as f:
                bills_data = json.load(f)
            print("✓ Loaded cached data")
        else:
            bills_data = discover_topic_bills(topic, config)
            total_cost += bills_data['cost']
            print(f"✓ Found legislation data (cost: ${bills_data['cost']:.4f})")

            # Cache the result
            os.makedirs(os.path.dirname(cache_file), exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(bills_data, f, indent=2)
            print(f"✓ Cached to: {cache_file}")

        # Generate JSON
        topic_json = generate_topic_json(topic, bills_data)

        # Save
        output_path = f'data/legislative_context/california_{topic}.json'
        with open(output_path, 'w') as f:
            json.dump(topic_json, f, indent=2)

        print(f"✓ Saved: {output_path}")
        print(f"✓ Bills: {len(topic_json['state_legislation'])}")

        results[topic] = {
            'bills': len(topic_json['state_legislation']),
            'cost': bills_data.get('cost', 0),
            'file': output_path
        }

    # Summary
    print("\n" + "="*80)
    print("AUTOMATION COMPLETE")
    print("="*80)
    print(f"\nTotal cost: ${total_cost:.4f}")
    print(f"Topics generated: {len(results)}")
    print()

    for topic, data in results.items():
        print(f"  {topic}: {data['bills']} bills → {data['file']}")

    print("\nNext steps:")
    print("1. Review generated files")
    print("2. Commit to git:")
    print("   git add data/legislative_context/california_*.json")
    print('   git commit -m "Add transportation, environment, budget legislative context"')

    return 0

if __name__ == '__main__':
    exit(main())
