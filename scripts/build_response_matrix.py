"""
Build response matrix from archetype responses

Output: CSV with rows=archetypes, columns=scenarios, values=positions

Usage:
  python scripts/build_response_matrix.py
  python scripts/build_response_matrix.py --visualize  # Also generate heatmaps
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
import argparse

# Position mapping: text → numeric
POSITION_MAP = {
    'strongly_oppose': -2,
    'oppose': -1,
    'neutral': 0,
    'support': 1,
    'strongly_support': 2
}


def build_matrix():
    """Build archetype × scenario response matrix"""

    # Load scenarios
    with open('data/scenarios/civic_scenarios_v1.json') as f:
        scenarios_data = json.load(f)
        scenarios = scenarios_data['scenarios']
        scenario_ids = [s['id'] for s in scenarios]

    # Load archetype definitions
    with open('data/archetypes/archetype_definitions_v2.json') as f:
        archetypes_data = json.load(f)
        archetypes = archetypes_data['archetypes']
        archetype_ids = [a['id'] for a in archetypes]
        archetype_names = [a['name'] for a in archetypes]

    print(f"Building matrix for {len(archetypes)} archetypes × {len(scenarios)} scenarios...")

    # Build matrix
    matrix = np.zeros((len(archetypes), len(scenarios)))
    missing_responses = []

    for i, archetype_id in enumerate(archetype_ids):
        # Load responses for this archetype
        response_file = f'data/archetype_responses/{archetype_id}_responses.json'

        try:
            with open(response_file) as f:
                responses_data = json.load(f)
                responses = responses_data['responses']

            # Fill row
            for j, scenario_id in enumerate(scenario_ids):
                response = next((r for r in responses if r['scenario_id'] == scenario_id), None)

                if response:
                    position = response['position']
                    matrix[i, j] = POSITION_MAP.get(position, 0)
                else:
                    missing_responses.append((archetype_id, scenario_id))
                    matrix[i, j] = 0  # Default to neutral for missing

        except FileNotFoundError:
            print(f"  Warning: Response file not found for {archetype_id}")
            missing_responses.append((archetype_id, "ALL"))
            # Leave row as zeros

    # Create DataFrame
    df = pd.DataFrame(
        matrix,
        index=archetype_names,
        columns=scenario_ids
    )

    # Save
    output_path = 'data/archetype_response_matrix.csv'
    df.to_csv(output_path)
    print(f"\n✓ Saved response matrix to {output_path}")
    print(f"  Shape: {df.shape[0]} archetypes × {df.shape[1]} scenarios")

    if missing_responses:
        print(f"\n  Warning: {len(missing_responses)} missing responses")
        if len(missing_responses) <= 10:
            for arch, scen in missing_responses:
                print(f"    - {arch}: {scen}")

    return df


def analyze_matrix(df: pd.DataFrame):
    """Generate basic statistics and correlation analysis"""

    print("\n" + "="*60)
    print("MATRIX STATISTICS")
    print("="*60)

    print(f"\nDimensions: {df.shape[0]} archetypes × {df.shape[1]} scenarios")
    print(f"\nValue range: [{df.min().min():.0f}, {df.max().max():.0f}]")
    print(f"Mean position: {df.mean().mean():.2f}")
    print(f"Std deviation: {df.std().std():.2f}")

    # Per-archetype statistics
    print("\nPer-Archetype Statistics:")
    print(f"  Mean position range: [{df.mean(axis=1).min():.2f}, {df.mean(axis=1).max():.2f}]")

    print("\nMost supportive archetypes (avg position > 1.0):")
    supportive = df.mean(axis=1).sort_values(ascending=False)
    for name, score in supportive.head(5).items():
        print(f"  {name}: {score:.2f}")

    print("\nMost oppositional archetypes (avg position < -1.0):")
    oppositional = df.mean(axis=1).sort_values()
    for name, score in oppositional.head(5).items():
        print(f"  {name}: {score:.2f}")

    # Archetype correlation analysis
    print("\n" + "="*60)
    print("ARCHETYPE CORRELATION ANALYSIS")
    print("="*60)

    corr = df.T.corr()  # Archetype correlation (transpose so scenarios are rows)

    print("\nHighly correlated archetype pairs (r > 0.8):")
    high_corr = []
    for i in range(len(corr)):
        for j in range(i+1, len(corr)):
            if corr.iloc[i, j] > 0.8:
                high_corr.append((corr.index[i], corr.index[j], corr.iloc[i, j]))

    if high_corr:
        for name1, name2, r in sorted(high_corr, key=lambda x: -x[2]):
            print(f"  {name1} <-> {name2}: {r:.3f}")
    else:
        print("  (None found)")

    print("\nAnti-correlated archetype pairs (r < -0.6):")
    low_corr = []
    for i in range(len(corr)):
        for j in range(i+1, len(corr)):
            if corr.iloc[i, j] < -0.6:
                low_corr.append((corr.index[i], corr.index[j], corr.iloc[i, j]))

    if low_corr:
        for name1, name2, r in sorted(low_corr, key=lambda x: x[2]):
            print(f"  {name1} <-> {name2}: {r:.3f}")
    else:
        print("  (None found)")

    # Scenario discrimination analysis
    print("\n" + "="*60)
    print("SCENARIO DISCRIMINATION ANALYSIS")
    print("="*60)

    # Standard deviation per scenario (higher = more discriminating)
    scenario_variance = df.std(axis=0).sort_values(ascending=False)

    print("\nMost discriminating scenarios (std > 1.2):")
    for scen_id, std in scenario_variance.head(10).items():
        print(f"  {scen_id}: {std:.2f}")

    print("\nLeast discriminating scenarios (std < 0.8):")
    for scen_id, std in scenario_variance.tail(5).items():
        print(f"  {scen_id}: {std:.2f}")

    return corr, scenario_variance


def visualize_matrix(df: pd.DataFrame, corr: pd.DataFrame):
    """Generate heatmap visualizations"""

    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
    except ImportError:
        print("\nWarning: matplotlib and seaborn required for visualization")
        print("Install with: pip install matplotlib seaborn")
        return

    print("\n" + "="*60)
    print("GENERATING VISUALIZATIONS")
    print("="*60)

    # Set style
    sns.set_style("whitegrid")
    plt.rcParams['figure.facecolor'] = 'white'

    # 1. Archetype correlation heatmap
    print("\n1. Archetype correlation heatmap...")
    fig, ax = plt.subplots(figsize=(20, 16))
    sns.heatmap(corr, annot=False, cmap='coolwarm', center=0,
                square=True, linewidths=0.5, cbar_kws={"shrink": 0.8},
                vmin=-1, vmax=1)
    plt.title('Archetype Correlation Matrix', fontsize=16, pad=20)
    plt.xlabel('Archetype', fontsize=12)
    plt.ylabel('Archetype', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.savefig('data/archetype_correlation_heatmap.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("   ✓ Saved to data/archetype_correlation_heatmap.png")

    # 2. Response matrix heatmap (archetypes × scenarios)
    print("\n2. Full response matrix heatmap...")
    fig, ax = plt.subplots(figsize=(30, 12))
    sns.heatmap(df, cmap='RdBu_r', center=0, cbar_kws={"shrink": 0.6},
                vmin=-2, vmax=2, linewidths=0)
    plt.title('Archetype Response Matrix (25 archetypes × 50 scenarios)', fontsize=16, pad=20)
    plt.xlabel('Scenario ID', fontsize=12)
    plt.ylabel('Archetype', fontsize=12)
    plt.xticks(rotation=90, fontsize=6)
    plt.yticks(fontsize=8)
    plt.tight_layout()
    plt.savefig('data/archetype_response_matrix_heatmap.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("   ✓ Saved to data/archetype_response_matrix_heatmap.png")

    # 3. Scenario discrimination heatmap (variance)
    print("\n3. Scenario discrimination visualization...")
    scenario_variance = df.std(axis=0).sort_values(ascending=False)
    fig, ax = plt.subplots(figsize=(16, 8))
    scenario_variance.plot(kind='bar', color='steelblue')
    plt.axhline(y=1.0, color='red', linestyle='--', label='Good discrimination (std=1.0)')
    plt.title('Scenario Discrimination Power (Standard Deviation)', fontsize=14, pad=20)
    plt.xlabel('Scenario ID', fontsize=12)
    plt.ylabel('Standard Deviation', fontsize=12)
    plt.xticks(rotation=90, fontsize=6)
    plt.legend()
    plt.tight_layout()
    plt.savefig('data/scenario_discrimination.png', dpi=150, bbox_inches='tight')
    plt.close()
    print("   ✓ Saved to data/scenario_discrimination.png")

    print("\n✓ All visualizations complete")


def main():
    parser = argparse.ArgumentParser(description='Build response matrix from archetype responses')
    parser.add_argument('--visualize', action='store_true',
                       help='Generate heatmap visualizations (requires matplotlib/seaborn)')

    args = parser.parse_args()

    # Build matrix
    df = build_matrix()

    # Analyze
    corr, scenario_variance = analyze_matrix(df)

    # Visualize if requested
    if args.visualize:
        visualize_matrix(df, corr)

    print("\n" + "="*60)
    print("NEXT STEPS (Week 2)")
    print("="*60)
    print("\n1. Review highly correlated archetypes (candidates for merging)")
    print("2. Identify low-discrimination scenarios (candidates for removal)")
    print("3. Run PCA to determine optimal archetype count")
    print("4. Proceed to Week 2: Statistical Analysis & Refinement")
    print("\nSee: docs/ARCHETYPE_SYSTEM_STRATEGY.md for complete roadmap")


if __name__ == "__main__":
    main()
