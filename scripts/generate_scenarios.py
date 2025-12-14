"""
Generate civic decision scenarios using Claude API

Usage:
  python scripts/generate_scenarios.py --topic housing --count 5
  python scripts/generate_scenarios.py --topic all --count 5
"""

import anthropic
import json
import os
import re
from typing import List, Dict
from datetime import datetime

SCENARIO_GENERATION_PROMPT = """You are an expert in local government and civic engagement. Generate realistic civic decision scenarios for Bay Area municipalities that reveal political values and priorities.

REQUIREMENTS:
1. Real trade-offs (not softball questions)
2. Specific and concrete (numbers, locations, timelines)
3. Neutral framing (no loaded language)
4. Discriminating (different ideologies give different answers)

SCENARIO STRUCTURE:
- Context (1 sentence)
- Decision (specific proposal with numbers)
- Response scale: Strongly Support / Support / Neutral / Oppose / Strongly Oppose

EXAMPLE (Good):
"A developer proposes an 8-story, 120-unit apartment building on a surface parking lot downtown. 15% of units would be affordable (80% AMI). The project requires a zoning variance for height. Do you support this project?"

EXAMPLE (Bad - too vague):
"Should the city build more housing?"

BAY AREA CONTEXT:
- Reference BART, CalTrain, VTA when relevant
- Use California policies (Prop 13, density bonus law, SB 9, etc.)
- Reference real cities (Berkeley, Oakland, San Jose, etc.)
- Consider regional housing crisis, transit challenges, climate goals

Generate {count} scenarios for topic: {topic}

For each scenario, provide:
1. A clear, specific question with concrete numbers
2. Realistic Bay Area context
3. Real trade-offs that reveal values

Format each scenario clearly numbered (1., 2., 3., etc.) with the full scenario text."""


def generate_scenarios(topic: str, count: int = 5) -> List[Dict]:
    """Generate scenarios using Claude API"""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    # Topic descriptions for better generation
    topic_descriptions = {
        'housing': 'Density, affordability, displacement, zoning, gentrification',
        'transportation': 'Cars vs. transit vs. bikes, parking, traffic, infrastructure',
        'environment': 'Climate action, trees, waste, energy, sustainability',
        'budget': 'Taxes, spending priorities, debt, revenue',
        'public_safety': 'Police, fire, emergency services, community safety',
        'education': 'Schools, libraries, youth programs, funding',
        'governance': 'Transparency, accountability, participation, democracy',
        'development': 'Commercial, mixed-use, economic development, job creation',
        'community': 'Parks, culture, social services, public spaces'
    }

    topic_detail = topic_descriptions.get(topic, topic)

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=8000,
        messages=[{
            "role": "user",
            "content": SCENARIO_GENERATION_PROMPT.format(
                topic=f"{topic} ({topic_detail})",
                count=count
            )
        }]
    )

    # Parse response
    response_text = message.content[0].text
    scenarios = parse_scenarios(response_text, topic)

    return scenarios


def parse_scenarios(text: str, topic: str) -> List[Dict]:
    """Parse scenario text into structured JSON"""
    scenarios = []

    # Split by numbered list (1., 2., 3., etc.)
    # More flexible regex to catch various numbering formats
    pattern = r'(?:^|\n)(\d+)[\.\)]\s*(.+?)(?=(?:\n\d+[\.\)]|\Z))'
    matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)

    for num, scenario_text in matches:
        # Clean up the text
        scenario_text = scenario_text.strip()

        # Skip very short matches (likely parsing errors)
        if len(scenario_text) < 50:
            continue

        # Generate a simple ID
        scenario_id = f"{topic}_{int(num):03d}"

        # Try to categorize based on keywords
        category = categorize_scenario(scenario_text, topic)

        scenarios.append({
            "id": scenario_id,
            "topic": topic,
            "category": category,
            "text": scenario_text,
            "response_scale": [
                "strongly_support",
                "support",
                "neutral",
                "oppose",
                "strongly_oppose"
            ],
            "difficulty": "moderate",  # Can be refined manually
            "tags": extract_tags(scenario_text)
        })

    return scenarios


def categorize_scenario(text: str, topic: str) -> str:
    """Simple keyword-based categorization"""
    text_lower = text.lower()

    category_keywords = {
        'housing': {
            'density': ['story', 'unit', 'apartment', 'building', 'height', 'zoning'],
            'affordability': ['affordable', 'ami', 'income', 'subsidy'],
            'displacement': ['displacement', 'gentrification', 'tenant', 'eviction'],
            'zoning': ['zoning', 'variance', 'upzone', 'residential']
        },
        'transportation': {
            'transit': ['bart', 'caltrain', 'vta', 'bus', 'light rail'],
            'bikes': ['bike', 'bicycle', 'cycle'],
            'parking': ['parking', 'garage'],
            'cars': ['car', 'vehicle', 'traffic', 'highway']
        },
        'environment': {
            'climate': ['climate', 'carbon', 'emissions', 'fossil'],
            'trees': ['tree', 'forest', 'canopy'],
            'energy': ['energy', 'solar', 'renewable', 'electric'],
            'waste': ['waste', 'recycling', 'compost']
        }
    }

    topic_cats = category_keywords.get(topic, {})
    for category, keywords in topic_cats.items():
        if any(keyword in text_lower for keyword in keywords):
            return category

    return 'general'


def extract_tags(text: str) -> List[str]:
    """Extract relevant tags from scenario text"""
    tags = []
    text_lower = text.lower()

    # Common civic tags
    tag_keywords = {
        'zoning': ['zoning', 'variance', 'upzone'],
        'affordability': ['affordable', 'ami', 'low-income'],
        'height': ['story', 'height', 'tall'],
        'transit': ['bart', 'caltrain', 'bus', 'transit'],
        'parking': ['parking'],
        'climate': ['climate', 'carbon', 'emissions'],
        'equity': ['equity', 'displacement', 'gentrification'],
        'tax': ['tax', 'levy', 'revenue'],
        'public_input': ['community', 'public comment', 'hearing']
    }

    for tag, keywords in tag_keywords.items():
        if any(keyword in text_lower for keyword in keywords):
            tags.append(tag)

    return tags[:5]  # Limit to 5 tags


def save_scenarios(scenarios: List[Dict], output_path: str):
    """Save scenarios to JSON file"""
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            "version": "1.0",
            "created_at": datetime.now().strftime("%Y-%m-%d"),
            "scenario_count": len(scenarios),
            "scenarios": scenarios
        }, f, indent=2)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Generate civic decision scenarios')
    parser.add_argument('--topic', required=True, help='Topic or "all"')
    parser.add_argument('--count', type=int, default=5, help='Scenarios per topic')
    parser.add_argument('--output', default='data/scenarios/civic_scenarios_v1.json',
                       help='Output file path')

    args = parser.parse_args()

    if args.topic == 'all':
        topics = [
            'housing', 'transportation', 'environment', 'budget',
            'public_safety', 'education', 'governance', 'development', 'community'
        ]
        all_scenarios = []

        print(f"Generating {args.count} scenarios for each of {len(topics)} topics...")
        for i, topic in enumerate(topics, 1):
            print(f"\n[{i}/{len(topics)}] Generating scenarios for {topic}...")
            try:
                scenarios = generate_scenarios(topic, args.count)
                all_scenarios.extend(scenarios)
                print(f"  ✓ Generated {len(scenarios)} scenarios for {topic}")
            except Exception as e:
                print(f"  ✗ Error generating scenarios for {topic}: {e}")

        save_scenarios(all_scenarios, args.output)
        print(f"\n✓ Saved {len(all_scenarios)} scenarios to {args.output}")
    else:
        print(f"Generating {args.count} scenarios for {args.topic}...")
        scenarios = generate_scenarios(args.topic, args.count)
        save_scenarios(scenarios, args.output)
        print(f"✓ Saved {len(scenarios)} scenarios to {args.output}")
