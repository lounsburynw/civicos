#!/usr/bin/env python3
"""
Discover municipal funding programs using Perplexity API.

Usage:
    # Query single municipality
    python scripts/perplexity_municipal_programs.py "San Rafael" "California"

    # Query with specific topic
    python scripts/perplexity_municipal_programs.py "San Rafael" "California" "housing"
"""

import json
import os
import sys
import requests
from datetime import datetime


def discover_municipal_programs(municipality: str, state: str, topic: str = "housing"):
    """Use Perplexity to discover municipal funding programs."""
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        raise ValueError("PERPLEXITY_API_KEY not set")

    topic_context = {
        "housing": "affordable housing, housing trust funds, inclusionary housing, in-lieu fees, and housing assistance",
        "transportation": "local transit, bicycle infrastructure, pedestrian improvements, and traffic calming",
        "environment": "climate action, sustainability programs, green building, and environmental initiatives",
    }

    prompt = f"""Research the City of {municipality}, {state}'s municipal funding programs related to {topic_context.get(topic, topic)}.

Provide comprehensive details for each program found:

## 1. Housing Trust Fund / Affordable Housing Fund
- Official program name
- Administering city department
- Fund sources (in-lieu fees, general fund, grants, etc.)
- Annual funding available (if known)
- Eligible activities (what the fund can support)
- Application process and cycles
- Affordability period requirements
- Contact information (department, phone, email)
- Official city website URL

## 2. Inclusionary Housing Requirements
- Percentage of affordable units required
- Project size thresholds that trigger requirements
- Current in-lieu fee amounts per unit (with effective dates)
- Fee adjustment methodology (CPI, construction cost index, etc.)
- Menu of compliance options (on-site, off-site, fees, land dedication)
- Governing ordinance/municipal code section
- Recent fee updates or changes

## 3. Commercial Linkage Fees
- Fee rates by building type (office, retail, hotel, etc.)
- Square footage thresholds/exemptions
- Nexus study information
- How fees are used

## 4. Local Ballot Measures (housing-related)
- Recent measures (2020-2024) related to housing, community facilities, or parcel taxes
- What each measure funds
- Tax rates and duration
- Revenue amounts
- Exemptions available

## 5. Federal/State Pass-Through Programs
- City's share of CDBG funding
- HOME program participation
- Any cooperative agreements with county
- How residents can influence local allocation priorities

## 6. Other Municipal Housing Programs
- Below Market Rate (BMR) rental programs
- Homeownership assistance programs
- Tenant protection programs
- Anti-displacement strategies

For each program, include:
- Resident input opportunities (public hearings, comment periods, advisory committees)
- How residents can leverage these programs at city council meetings
- Key leverage points for civic engagement

Cite official city sources (.gov URLs) whenever possible."""

    print(f"\n{'='*80}")
    print(f"QUERYING PERPLEXITY FOR: {municipality}, {state}")
    print(f"Topic: {topic}")
    print(f"{'='*80}\n")

    response = requests.post(
        'https://api.perplexity.ai/chat/completions',
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        },
        json={
            'model': 'sonar-pro',
            'messages': [{'role': 'user', 'content': prompt}],
            'max_tokens': 4000,
            'temperature': 0.2
        },
        timeout=90
    )

    response.raise_for_status()
    data = response.json()

    result = data['choices'][0]['message']['content']
    citations = data.get('citations', [])
    cost = data['usage']['cost']['total_cost']

    print(result)
    print()
    print(f"{'='*80}")
    print(f"CITATIONS ({len(citations)} sources)")
    print(f"{'='*80}")
    for i, citation in enumerate(citations, 1):
        print(f"{i}. {citation}")
    print()
    print(f"{'='*80}")
    print(f"Cost: ${cost:.4f}")
    print(f"{'='*80}\n")

    return {
        'municipality': municipality,
        'state': state,
        'topic': topic,
        'response': result,
        'citations': citations,
        'cost': cost,
        'timestamp': datetime.now().isoformat()
    }


def save_audit_trail(results, output_file):
    """Save Perplexity results to audit file."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Audit trail saved to: {output_file}")


def main():
    if len(sys.argv) < 3:
        print("Usage: python perplexity_municipal_programs.py <municipality> <state> [topic]")
        print("Example: python perplexity_municipal_programs.py 'San Rafael' 'California' 'housing'")
        sys.exit(1)

    municipality = sys.argv[1]
    state = sys.argv[2]
    topic = sys.argv[3] if len(sys.argv) > 3 else 'housing'

    # Normalize municipality name for file paths
    municipality_slug = municipality.lower().replace(' ', '-')

    result = discover_municipal_programs(municipality, state, topic)

    # Save audit trail
    output_dir = f"data/funding/municipal/{municipality_slug}"
    output_file = f"{output_dir}/{topic}_perplexity_audit.json"

    # Load existing or create new
    if os.path.exists(output_file):
        with open(output_file, 'r') as f:
            audit_data = json.load(f)
    else:
        audit_data = {'queries': []}

    audit_data['queries'].append(result)
    save_audit_trail(audit_data, output_file)

    print(f"\nNext step: Run convert script to generate structured JSON")
    print(f"  python scripts/convert_perplexity_to_municipal_programs.py {municipality_slug}")


if __name__ == '__main__':
    main()
