"""
Select final 20 refined scenarios based on discrimination power and topic balance

Usage:
  python scripts/select_refined_scenarios.py
"""

import json
import pandas as pd

def select_refined_scenarios():
    """Select 20 scenarios balancing discrimination and topic coverage"""

    # Load response matrix for discrimination analysis
    df = pd.read_csv('data/archetype_response_matrix.csv', index_col=0)
    scenario_std = df.std(axis=0).sort_values(ascending=False)

    # Load original scenarios
    with open('data/scenarios/civic_scenarios_v1.json') as f:
        scenarios_data = json.load(f)
        scenarios = {s['id']: s for s in scenarios_data['scenarios']}

    # Extract topic from scenario_id (e.g., "housing_001" -> "housing")
    scenario_topics = {}
    for scenario_id in scenario_std.index:
        topic = scenario_id.rsplit('_', 1)[0]
        scenario_topics[scenario_id] = topic

    print("="*80)
    print("SCENARIO SELECTION (Top 20)")
    print("="*80)

    # Target: 2-3 per topic, prioritize high discrimination
    topics = {}
    for scenario_id in scenario_std.index:
        topic = scenario_topics[scenario_id]
        if topic not in topics:
            topics[topic] = []
        topics[topic].append({
            'id': scenario_id,
            'std': scenario_std[scenario_id]
        })

    print(f"\nTopics found: {len(topics)}")
    for topic, scenarios_list in topics.items():
        print(f"  {topic}: {len(scenarios_list)} scenarios")

    # Select top 2-3 from each topic (prioritizing high std)
    selected = []
    for topic, scenarios_list in sorted(topics.items()):
        # Sort by std descending
        scenarios_list.sort(key=lambda x: -x['std'])

        # Take top 2-3 scenarios per topic
        target_per_topic = 3 if len(topics) <= 7 else 2
        topic_selected = scenarios_list[:target_per_topic]

        print(f"\n{topic.upper()}: Selecting top {len(topic_selected)}")
        for s in topic_selected:
            selected.append(s['id'])
            print(f"  • {s['id']}: std={s['std']:.2f}")

    # If we have < 20, add more high-discrimination scenarios
    if len(selected) < 20:
        remaining_needed = 20 - len(selected)
        print(f"\nAdding {remaining_needed} more high-discrimination scenarios...")

        for scenario_id in scenario_std.index:
            if scenario_id not in selected:
                selected.append(scenario_id)
                print(f"  • {scenario_id}: std={scenario_std[scenario_id]:.2f}")
                if len(selected) >= 20:
                    break

    # Trim to exactly 20
    selected = selected[:20]

    print(f"\n{'='*80}")
    print(f"FINAL SELECTION: {len(selected)} scenarios")
    print(f"{'='*80}\n")

    # Create refined scenarios file
    refined_scenarios = [scenarios[sid] for sid in selected]

    refined_data = {
        "version": "2.0_refined",
        "created_at": "2025-10-30",
        "scenario_count": len(refined_scenarios),
        "selection_criteria": "High discrimination (std > 1.0) with topic balance (2-3 per topic)",
        "refined_from": "civic_scenarios_v1.json (54 scenarios)",
        "scenarios": refined_scenarios
    }

    output_path = 'data/scenarios/civic_scenarios_v2_refined.json'
    with open(output_path, 'w') as f:
        json.dump(refined_data, f, indent=2)

    print(f"✓ Saved refined scenarios to {output_path}")

    # Show topic distribution
    topic_counts = {}
    for s in refined_scenarios:
        topic = s['id'].rsplit('_', 1)[0]
        topic_counts[topic] = topic_counts.get(topic, 0) + 1

    print(f"\nTopic distribution:")
    for topic, count in sorted(topic_counts.items()):
        print(f"  {topic}: {count} scenarios")

    print(f"\n✓ Scenario selection complete!")
    return selected

if __name__ == "__main__":
    selected = select_refined_scenarios()
