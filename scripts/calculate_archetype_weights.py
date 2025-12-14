"""
Calculate archetype weight vectors from refined response matrix

Produces:
- Scenario-based weights (70%): 22 archetypes × 20 scenarios
- Topic interest weights (30%): 22 archetypes × 9 topics

Output: data/archetypes/archetype_weights_final.json
"""

import json
import pandas as pd
import numpy as np
from collections import defaultdict

def calculate_weights():
    """Calculate scenario + topic weights for each refined archetype"""

    print("="*80)
    print("ARCHETYPE WEIGHT CALCULATION")
    print("="*80)

    # Load refined archetypes (22)
    with open('data/archetypes/archetype_definitions_v3_refined.json') as f:
        v3_data = json.load(f)
        refined_archetypes = v3_data['archetypes']

    # Load refined scenarios (20)
    with open('data/scenarios/civic_scenarios_v2_refined.json') as f:
        refined_scenarios_data = json.load(f)
        refined_scenarios = refined_scenarios_data['scenarios']
        refined_scenario_ids = [s['id'] for s in refined_scenarios]

    # Load original response matrix (25 archetypes × 54 scenarios)
    response_matrix = pd.read_csv('data/archetype_response_matrix.csv', index_col=0)

    # Mapping of refined archetype IDs to original archetype names
    archetype_mapping = {}
    for arch in refined_archetypes:
        if 'merged_from' in arch:
            # This is a merged archetype - average constituent responses
            archetype_mapping[arch['id']] = arch['merged_from']
        else:
            # Unchanged archetype - use original name
            archetype_mapping[arch['id']] = [arch['name']]

    print(f"\nProcessing {len(refined_archetypes)} archetypes × {len(refined_scenarios)} scenarios")
    print(f"Merges detected: {sum(1 for arch in refined_archetypes if 'merged_from' in arch)}")

    # Build final weight vectors
    weights = {
        "version": "3.0_final",
        "created_at": "2025-10-30",
        "scenario_weight": 0.70,
        "topic_weight": 0.30,
        "archetype_count": len(refined_archetypes),
        "scenario_count": len(refined_scenarios),
        "archetypes": []
    }

    # Extract topic from scenario_id
    def get_topic(scenario_id):
        return scenario_id.rsplit('_', 1)[0]

    topics = sorted(set(get_topic(s['id']) for s in refined_scenarios))

    print(f"\nTopics: {', '.join(topics)}")

    for arch in refined_archetypes:
        arch_id = arch['id']
        arch_name = arch['name']

        # Get responses for this archetype
        original_names = archetype_mapping[arch_id]

        # Get responses (average if merged)
        responses = {}
        for scenario_id in refined_scenario_ids:
            if scenario_id in response_matrix.columns:
                values = [response_matrix.loc[name, scenario_id] for name in original_names if name in response_matrix.index]
                if values:
                    responses[scenario_id] = float(np.mean(values))
                else:
                    responses[scenario_id] = 0.0
            else:
                responses[scenario_id] = 0.0

        # Calculate topic weights from scenario positions
        topic_weights = defaultdict(list)
        for scenario_id, position in responses.items():
            topic = get_topic(scenario_id)
            topic_weights[topic].append(position)

        # Average positions per topic (normalized to 0-1 for interest level)
        topic_interest = {}
        for topic in topics:
            if topic in topic_weights and topic_weights[topic]:
                avg_position = np.mean(topic_weights[topic])
                # Convert position (-2 to 2) to interest (0 to 1)
                # Positive = high interest, Negative = low interest
                # But we want absolute value = interest level
                interest = (abs(avg_position) / 2.0)  # 0 to 1 scale
                topic_interest[topic] = round(float(interest), 3)
            else:
                topic_interest[topic] = 0.0

        weights['archetypes'].append({
            "id": arch_id,
            "name": arch_name,
            "scenario_weights": {sid: round(float(v), 2) for sid, v in responses.items()},
            "topic_weights": topic_interest,
            "merged_from": arch.get('merged_from', None)
        })

        print(f"  ✓ {arch_name}")

    # Save
    output_path = 'data/archetypes/archetype_weights_final.json'
    with open(output_path, 'w') as f:
        json.dump(weights, f, indent=2)

    print(f"\n{'='*80}")
    print(f"✓ Saved weights to {output_path}")
    print(f"{'='*80}")
    print(f"\nFinal weights:")
    print(f"  Archetypes: {len(weights['archetypes'])}")
    print(f"  Scenarios per archetype: {len(refined_scenario_ids)}")
    print(f"  Topics per archetype: {len(topics)}")
    print(f"  Weighting: 70% scenario + 30% topic")
    print(f"\n✓ Ready for client-side matching!")

if __name__ == "__main__":
    calculate_weights()
