"""
Recommend archetype mergers and scenario selections based on statistical analysis

Usage:
  python scripts/recommend_archetype_refinements.py
"""

import pandas as pd
import numpy as np

def analyze_refinements():
    """Analyze correlation and discrimination to recommend refinements"""

    # Load matrix
    df = pd.read_csv('data/archetype_response_matrix.csv', index_col=0)

    print("="*60)
    print("ARCHETYPE REFINEMENT RECOMMENDATIONS")
    print("="*60)

    # 1. High correlation pairs (merge candidates)
    print("\n1. MERGE CANDIDATES (r > 0.85):")
    print("-" * 60)

    corr = df.T.corr()
    merge_candidates = []

    for i in range(len(corr)):
        for j in range(i+1, len(corr)):
            if corr.iloc[i, j] > 0.85:
                merge_candidates.append({
                    'archetype1': corr.index[i],
                    'archetype2': corr.index[j],
                    'correlation': corr.iloc[i, j]
                })

    if merge_candidates:
        for mc in sorted(merge_candidates, key=lambda x: -x['correlation']):
            print(f"  • {mc['archetype1']}")
            print(f"    + {mc['archetype2']}")
            print(f"    Correlation: {mc['correlation']:.3f}")
            print()
    else:
        print("  ✓ No high-correlation pairs (r > 0.85)")
        print("  → All archetypes are sufficiently distinct")

    # 2. Anti-correlated pairs (good opposites)
    print("\n2. ANTI-CORRELATED PAIRS (r < -0.6):")
    print("-" * 60)

    anti_corr = []
    for i in range(len(corr)):
        for j in range(i+1, len(corr)):
            if corr.iloc[i, j] < -0.6:
                anti_corr.append({
                    'archetype1': corr.index[i],
                    'archetype2': corr.index[j],
                    'correlation': corr.iloc[i, j]
                })

    if anti_corr:
        for ac in sorted(anti_corr, key=lambda x: x['correlation']):
            print(f"  • {ac['archetype1']} vs {ac['archetype2']}: {ac['correlation']:.3f}")
    else:
        print("  (No strong anti-correlations)")

    # 3. Scenario discrimination
    print("\n3. SCENARIO SELECTION:")
    print("-" * 60)

    scenario_std = df.std(axis=0).sort_values(ascending=False)

    print("\nTop 20 discriminating scenarios (std > 1.0):")
    top_scenarios = scenario_std[scenario_std > 1.0].head(20)
    for scenario_id, std in top_scenarios.items():
        print(f"  • {scenario_id}: {std:.2f}")

    print(f"\nTotal scenarios with std > 1.0: {(scenario_std > 1.0).sum()}")

    print("\nBottom 10 scenarios (low discrimination):")
    bottom_scenarios = scenario_std.tail(10)
    for scenario_id, std in bottom_scenarios.items():
        print(f"  • {scenario_id}: {std:.2f}")

    # 4. Recommendations
    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)

    n_merges = len(merge_candidates)
    final_count = 25 - n_merges

    print(f"\n1. Archetype Count:")
    print(f"   Starting: 25 archetypes")
    print(f"   Merge: {n_merges} pairs → {final_count} archetypes")
    print(f"   PCA suggests: 15-19 archetypes optimal")
    print(f"   Target: 18 archetypes (9 PCA components + 9 buffer)")

    print(f"\n2. Scenario Count:")
    print(f"   Starting: 54 scenarios")
    print(f"   Keep top: 20 scenarios (std > 1.0)")
    print(f"   Target: Balance topics (2-3 per topic)")

    print(f"\n3. Next Steps:")
    print(f"   a. Review merge candidates (check differentiators)")
    print(f"   b. Create refined archetype definitions")
    print(f"   c. Select final 20 scenarios")
    print(f"   d. Calculate archetype weights (70% scenario + 30% topic)")

if __name__ == "__main__":
    analyze_refinements()
