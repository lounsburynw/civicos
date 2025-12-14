"""
Simulate archetype responses to civic scenarios using LLM API

Usage:
  python scripts/simulate_archetype_responses.py --archetype slow_growth_advocate
  python scripts/simulate_archetype_responses.py --all
  python scripts/simulate_archetype_responses.py --all --use-openai  # Use OpenAI instead of Anthropic
"""

import json
import os
import time
from typing import List, Dict
import argparse

# Try to import both APIs
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("Warning: anthropic package not installed. Use --use-openai flag.")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("Warning: openai package not installed.")


RESPONSE_SIMULATION_PROMPT = """You are simulating a specific civic archetype for research purposes. Respond authentically to civic scenarios based on this archetype's values and priorities.

ARCHETYPE CHARACTERISTICS:
Name: {name}
Description: {description}
Core values: {values}
Typical concerns: {concerns}
Priorities: {priorities}
Real-world examples: {examples}

TASK: Respond to the following civic decision scenario.

For this scenario, provide:
1. Position: strongly_support / support / neutral / oppose / strongly_oppose
2. Confidence: 0-100 (how certain is this archetype's position?)
3. Reasoning: 2-3 sentences explaining why this archetype holds this view

IMPORTANT:
- Be consistent with the archetype's values
- Show nuance (this isn't a caricature)
- Consider trade-offs (archetypes can have conflicting values)
- Use realistic reasoning (not Twitter slogans)
- Acknowledge when the archetype would be internally conflicted (lower confidence)

SCENARIO:
{scenario_text}

Respond in JSON format:
{{
  "position": "support|oppose|neutral|strongly_support|strongly_oppose",
  "confidence": 75,
  "reasoning": "2-3 sentence explanation"
}}"""


def simulate_response_anthropic(archetype: Dict, scenario: Dict) -> Dict:
    """Simulate archetype response to scenario using Anthropic Claude API"""
    if not ANTHROPIC_AVAILABLE:
        raise ImportError("anthropic package not installed. Run: pip install anthropic")

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    # Format prompt
    prompt = RESPONSE_SIMULATION_PROMPT.format(
        name=archetype['name'],
        description=archetype['description'],
        values='\n'.join(f"- {v}" for v in archetype['core_values']),
        concerns='\n'.join(f"- {c}" for c in archetype['typical_concerns']),
        priorities='\n'.join(f"- {p}" for p in archetype['priorities']),
        examples=', '.join(archetype['real_world_examples']),
        scenario_text=scenario['text']
    )

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    # Parse JSON response
    response_text = message.content[0].text

    # Extract JSON from response (may have markdown code blocks)
    if '```json' in response_text:
        response_text = response_text.split('```json')[1].split('```')[0].strip()
    elif '```' in response_text:
        response_text = response_text.split('```')[1].split('```')[0].strip()

    response_data = json.loads(response_text)

    return {
        "scenario_id": scenario['id'],
        "position": response_data['position'],
        "confidence": response_data['confidence'],
        "reasoning": response_data['reasoning']
    }


def simulate_response_openai(archetype: Dict, scenario: Dict) -> Dict:
    """Simulate archetype response to scenario using OpenAI API"""
    if not OPENAI_AVAILABLE:
        raise ImportError("openai package not installed. Run: pip install openai")

    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Format prompt
    prompt = RESPONSE_SIMULATION_PROMPT.format(
        name=archetype['name'],
        description=archetype['description'],
        values='\n'.join(f"- {v}" for v in archetype['core_values']),
        concerns='\n'.join(f"- {c}" for c in archetype['typical_concerns']),
        priorities='\n'.join(f"- {p}" for p in archetype['priorities']),
        examples=', '.join(archetype['real_world_examples']),
        scenario_text=scenario['text']
    )

    response = client.chat.completions.create(
        model="gpt-4o",  # or gpt-4-turbo
        messages=[
            {"role": "system", "content": "You are a civic policy analyst simulating different political archetypes."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=500,
        temperature=0.7,
        response_format={"type": "json_object"}
    )

    # Parse JSON response
    response_text = response.choices[0].message.content
    response_data = json.loads(response_text)

    return {
        "scenario_id": scenario['id'],
        "position": response_data['position'],
        "confidence": response_data['confidence'],
        "reasoning": response_data['reasoning']
    }


def simulate_all_responses(archetype_id: str, use_openai: bool = False, rate_limit_delay: float = 1.0):
    """Simulate responses for one archetype across all scenarios"""

    # Load archetype definition
    with open('data/archetypes/archetype_definitions_v2.json') as f:
        archetypes_data = json.load(f)
        archetype = next((a for a in archetypes_data['archetypes'] if a['id'] == archetype_id), None)

        if archetype is None:
            print(f"Error: Archetype '{archetype_id}' not found")
            return

    # Load scenarios
    with open('data/scenarios/civic_scenarios_v1.json') as f:
        scenarios_data = json.load(f)
        scenarios = scenarios_data['scenarios']

    print(f"\nSimulating {archetype['name']} responses to {len(scenarios)} scenarios...")
    print(f"Using {'OpenAI' if use_openai else 'Anthropic'} API")

    # Simulate responses
    responses = []
    errors = 0

    for i, scenario in enumerate(scenarios):
        try:
            print(f"  [{i+1}/{len(scenarios)}] Simulating response to {scenario['id']}...", end=' ')

            if use_openai:
                response = simulate_response_openai(archetype, scenario)
            else:
                response = simulate_response_anthropic(archetype, scenario)

            responses.append(response)
            print("✓")

            # Rate limiting
            if i < len(scenarios) - 1:  # Don't delay after last request
                time.sleep(rate_limit_delay)

        except Exception as e:
            print(f"✗ Error: {e}")
            errors += 1
            # Add placeholder response
            responses.append({
                "scenario_id": scenario['id'],
                "position": "neutral",
                "confidence": 0,
                "reasoning": f"Error during simulation: {str(e)}"
            })

    # Save responses
    output = {
        "archetype_id": archetype_id,
        "archetype_name": archetype['name'],
        "scenario_count": len(scenarios),
        "successful_responses": len(scenarios) - errors,
        "errors": errors,
        "api_used": "openai" if use_openai else "anthropic",
        "responses": responses
    }

    output_path = f'data/archetype_responses/{archetype_id}_responses.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ Saved {len(responses)} responses to {output_path}")
    if errors > 0:
        print(f"  Warning: {errors} errors occurred during simulation")


def main():
    parser = argparse.ArgumentParser(description='Simulate archetype responses to civic scenarios')
    parser.add_argument('--archetype', help='Archetype ID to simulate')
    parser.add_argument('--all', action='store_true', help='Simulate all archetypes')
    parser.add_argument('--use-openai', action='store_true', help='Use OpenAI API instead of Anthropic')
    parser.add_argument('--rate-limit', type=float, default=1.0,
                       help='Delay between API calls in seconds (default: 1.0)')

    args = parser.parse_args()

    if not args.archetype and not args.all:
        parser.error("Must specify either --archetype or --all")

    # Check API availability
    if args.use_openai and not OPENAI_AVAILABLE:
        parser.error("OpenAI not available. Install with: pip install openai")
    elif not args.use_openai and not ANTHROPIC_AVAILABLE:
        parser.error("Anthropic not available. Install with: pip install anthropic")

    if args.all:
        # Load all archetype IDs
        with open('data/archetypes/archetype_definitions_v2.json') as f:
            archetypes_data = json.load(f)
            archetype_ids = [a['id'] for a in archetypes_data['archetypes']]

        print(f"Simulating all {len(archetype_ids)} archetypes")
        print(f"Estimated time: {len(archetype_ids) * 50 * args.rate_limit / 60:.1f} minutes")

        for i, archetype_id in enumerate(archetype_ids, 1):
            print(f"\n[{i}/{len(archetype_ids)}] Processing {archetype_id}...")
            simulate_all_responses(archetype_id, use_openai=args.use_openai,
                                 rate_limit_delay=args.rate_limit)

        print(f"\n✓ Completed all {len(archetype_ids)} archetypes")
    else:
        simulate_all_responses(args.archetype, use_openai=args.use_openai,
                             rate_limit_delay=args.rate_limit)


if __name__ == "__main__":
    main()
