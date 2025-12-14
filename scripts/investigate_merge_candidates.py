"""
Investigate archetype merge candidates with detailed correlation analysis

Usage:
  python scripts/investigate_merge_candidates.py
"""

import pandas as pd
import numpy as np
import json

def investigate_merges():
    """Show detailed correlation analysis for merge candidates"""

    # Load matrix
    df = pd.read_csv('data/archetype_response_matrix.csv', index_col=0)

    # Load archetype definitions (index by name since matrix uses names)
    with open('data/archetypes/archetype_definitions_v2.json') as f:
        archetypes_data = json.load(f)
        archetypes = {a['name']: a for a in archetypes_data['archetypes']}

    print("="*80)
    print("DETAILED MERGE CANDIDATE ANALYSIS (r > 0.80)")
    print("="*80)

    # Calculate correlation matrix
    corr = df.T.corr()

    # Find all pairs > 0.80
    merge_candidates = []
    for i in range(len(corr)):
        for j in range(i+1, len(corr)):
            if corr.iloc[i, j] > 0.80:
                merge_candidates.append({
                    'archetype1_id': corr.index[i],
                    'archetype2_id': corr.index[j],
                    'correlation': corr.iloc[i, j]
                })

    # Sort by correlation
    merge_candidates = sorted(merge_candidates, key=lambda x: -x['correlation'])

    print(f"\nFound {len(merge_candidates)} pairs with r > 0.80\n")

    for idx, mc in enumerate(merge_candidates, 1):
        arch1_name = mc['archetype1_id']
        arch2_name = mc['archetype2_id']
        arch1 = archetypes[arch1_name]
        arch2 = archetypes[arch2_name]

        print(f"{'='*80}")
        print(f"PAIR {idx}: r = {mc['correlation']:.3f}")
        print(f"{'='*80}")

        print(f"\n[A] {arch1['name']}")
        print(f"    ID: {arch1['id']}")
        print(f"    Description: {arch1['description']}")
        print(f"    Core values:")
        for val in arch1['core_values'][:3]:  # First 3
            print(f"      • {val}")

        print(f"\n[B] {arch2['name']}")
        print(f"    ID: {arch2['id']}")
        print(f"    Description: {arch2['description']}")
        print(f"    Core values:")
        for val in arch2['core_values'][:3]:  # First 3
            print(f"      • {val}")

        # Calculate agreement on scenarios
        arch1_responses = df.loc[arch1_name]
        arch2_responses = df.loc[arch2_name]

        # Count agreements (same sign and within 0.5 difference)
        same_sign = (arch1_responses * arch2_responses) > 0
        similar_magnitude = np.abs(arch1_responses - arch2_responses) < 0.5
        agreements = (same_sign & similar_magnitude).sum()

        print(f"\n    Agreement: {agreements}/{len(df.columns)} scenarios ({agreements/len(df.columns)*100:.1f}%)")

        # Find biggest disagreements
        disagreements = np.abs(arch1_responses - arch2_responses)
        top_disagreements = disagreements.nlargest(3)

        print(f"    Biggest disagreements:")
        for scenario_id, diff in top_disagreements.items():
            print(f"      • {scenario_id}: Δ = {diff:.2f} ({arch1_responses[scenario_id]:.1f} vs {arch2_responses[scenario_id]:.1f})")

        print(f"\n    MERGE RECOMMENDATION: ", end="")
        if mc['correlation'] > 0.90:
            print("✅ STRONG - Very similar perspectives")
        elif mc['correlation'] > 0.85:
            print("⚠️  MODERATE - Review differentiators")
        else:
            print("❓ WEAK - Likely distinct enough to keep")

        print()

    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)

    strong_merges = [mc for mc in merge_candidates if mc['correlation'] > 0.90]
    moderate_merges = [mc for mc in merge_candidates if 0.85 < mc['correlation'] <= 0.90]
    weak_merges = [mc for mc in merge_candidates if 0.80 < mc['correlation'] <= 0.85]

    print(f"\nMerge Strength Breakdown:")
    print(f"  ✅ Strong (r > 0.90):        {len(strong_merges)} pairs - MERGE THESE")
    print(f"  ⚠️  Moderate (0.85 < r ≤ 0.90): {len(moderate_merges)} pairs - REVIEW CAREFULLY")
    print(f"  ❓ Weak (0.80 < r ≤ 0.85):     {len(weak_merges)} pairs - LIKELY KEEP SEPARATE")

    print(f"\nIf we merge all strong + moderate pairs:")
    print(f"  25 archetypes → {25 - len(strong_merges) - len(moderate_merges)} archetypes")
    print(f"  PCA target: 18 archetypes")
    print(f"  Gap: {25 - len(strong_merges) - len(moderate_merges) - 18} more merges needed")

    print("\n" + "="*80)
    print("NEXT STEP: Review each pair above and decide:")
    print("  1. Which pairs are conceptually redundant?")
    print("  2. Which pairs have meaningful distinctions?")
    print("  3. Target: Merge enough pairs to reach ~18 archetypes")
    print("="*80)

if __name__ == "__main__":
    investigate_merges()
