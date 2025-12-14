#!/usr/bin/env python3
"""
Discover federal programs and their local government requirements using Perplexity API.
"""

import json
import os
import sys
import requests
from datetime import datetime

def discover_federal_program(program_name, topic="housing"):
    """Use Perplexity to discover federal program details."""
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        raise ValueError("PERPLEXITY_API_KEY not set")

    # Topic-specific context
    topic_context = {
        "housing": "affordable housing, community development, homelessness prevention, and housing accessibility",
        "transportation": "public transit, active transportation, complete streets, and transportation equity",
        "environment": "climate action, renewable energy, sustainability, and environmental justice",
        "budget": "municipal finance, infrastructure investment, capital improvement projects, and fiscal planning",
        "education": "K-12 education, community colleges, workforce development, and educational equity"
    }

    prompt = f"""Provide comprehensive details about the federal {program_name} program, focusing on local government implementation and citizen participation opportunities.

Please provide:

1. **Program Overview**
   - Full official program name
   - Administering federal agency (HUD, DOT, EPA, etc.)
   - 2-3 sentence description focusing on local government role

2. **Eligible Activities**
   - List 5-7 specific activities local governments can fund
   - Focus on {topic_context.get(topic, 'community benefit')} activities

3. **Citizen Participation Requirements**
   - Required public hearings or comment periods
   - Community needs assessment processes
   - Resident advisory committees or councils
   - Annual planning or reporting that requires public input

4. **Leverage Points for Residents**
   - How residents can influence local funding decisions
   - When and how to participate in planning processes
   - Who to contact in local government (typical roles, not specific names)

5. **Reporting & Compliance**
   - Annual reporting requirements
   - Performance metrics tracked
   - Public availability of reports

6. **Key Resources**
   - Official federal program URL (.gov)
   - Citizen participation plan requirements URL
   - Annual allocation/formula information URL

Format as structured information with clear headers. Include specific requirements from federal regulations (e.g., "24 CFR Part 91" for HUD programs)."""

    print(f"\n{'='*80}")
    print(f"QUERYING PERPLEXITY FOR: {program_name}")
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

    # Extract the response
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
        'program_name': program_name,
        'topic': topic,
        'response': result,
        'citations': citations,
        'cost': cost,
        'timestamp': datetime.now().isoformat()
    }

def save_audit_trail(results, output_file):
    """Save Perplexity results to audit file."""
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Audit trail saved to: {output_file}")

if __name__ == '__main__':
    # Programs to query
    programs = [
        ('HOME Investment Partnerships Program', 'housing'),
        ('Section 8 Housing Choice Voucher Program', 'housing'),
        ('Low-Income Housing Tax Credit (LIHTC) Program', 'housing'),
        ('Federal Transit Administration (FTA) Formula Grants', 'transportation'),
        ('Transportation Alternatives Program (TAP)', 'transportation'),
        ('Environmental Protection Agency (EPA) Environmental Justice Grants', 'environment'),
        ('Department of Energy (DOE) Energy Efficiency and Conservation Block Grant', 'environment')
    ]

    if len(sys.argv) > 1:
        # Query specific program
        program_name = sys.argv[1]
        topic = sys.argv[2] if len(sys.argv) > 2 else 'housing'
        result = discover_federal_program(program_name, topic)

        # Save audit trail
        output_file = f"data/federal_programs/{topic}_perplexity_audit.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        # Load existing or create new
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                audit_data = json.load(f)
        else:
            audit_data = {'queries': []}

        audit_data['queries'].append(result)
        save_audit_trail(audit_data, output_file)
    else:
        # Query all programs
        all_results = {'queries': []}
        total_cost = 0

        for program_name, topic in programs:
            result = discover_federal_program(program_name, topic)
            all_results['queries'].append(result)
            total_cost += result['cost']

            print(f"\n⏸️  Sleeping 2s between queries...\n")
            import time
            time.sleep(2)

        print(f"\n{'='*80}")
        print(f"TOTAL COST: ${total_cost:.4f}")
        print(f"{'='*80}\n")

        # Save by topic
        by_topic = {}
        for result in all_results['queries']:
            topic = result['topic']
            if topic not in by_topic:
                by_topic[topic] = {'queries': []}
            by_topic[topic]['queries'].append(result)

        for topic, data in by_topic.items():
            output_file = f"data/federal_programs/{topic}_perplexity_audit.json"
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            save_audit_trail(data, output_file)
