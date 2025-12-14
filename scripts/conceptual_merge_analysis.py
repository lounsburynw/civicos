"""
Analyze archetypes for conceptual redundancies beyond statistical correlation

Usage:
  python scripts/conceptual_merge_analysis.py
"""

import json

def analyze_conceptual_merges():
    """Identify conceptual redundancies in archetype set"""

    # Load archetypes
    with open('data/archetypes/archetype_definitions_v2.json') as f:
        data = json.load(f)
        archetypes = {a['name']: a for a in data['archetypes']}

    print("="*80)
    print("CONCEPTUAL MERGE ANALYSIS")
    print("="*80)
    print("\nReviewing all 25 archetypes for conceptual overlaps...\n")

    # Group by thematic clusters
    clusters = {
        "Progressive Housing": [
            "Slow Growth Advocate",
            "Anti-Gentrification Activist",
            "Affordable Housing Absolutist",
            "Renter Advocate"
        ],
        "Pro-Development": [
            "Housing Champion",
            "Market Urbanist"
        ],
        "Climate/Environment": [
            "Environmental Steward",
            "Green New Dealer",
            "Transit Advocate"
        ],
        "Demographics": [
            "Parent Prioritizer",
            "Senior Services Advocate",
            "Education Advocate"
        ],
        "Economic": [
            "Labor Organizer",
            "Fiscal Conservative",
            "Small Business Booster"
        ],
        "Criminal Justice": [
            "Safety First",
            "Justice Reformer"
        ],
        "Governance": [
            "Government Watchdog",
            "Direct Democracy Proponent",
            "Pragmatic Incrementalist"
        ],
        "Community": [
            "Community Builder",
            "Neighborhood Protector",
            "Regional Thinker",
            "Homeowner Stability Seeker"
        ],
        "Technology": [
            "Techno-Optimist"
        ]
    }

    # Analyze each cluster
    for cluster_name, archetype_names in clusters.items():
        if len(archetype_names) <= 1:
            continue

        print(f"{'='*80}")
        print(f"CLUSTER: {cluster_name} ({len(archetype_names)} archetypes)")
        print(f"{'='*80}\n")

        for name in archetype_names:
            arch = archetypes[name]
            print(f"• {name}")
            print(f"  Description: {arch['description']}")
            print(f"  Core values: {arch['core_values'][0]}")
            print()

    print("="*80)
    print("MERGE RECOMMENDATIONS")
    print("="*80)

    recommendations = [
        {
            "strength": "STRONG",
            "pair": ["Slow Growth Advocate", "Anti-Gentrification Activist"],
            "merged_name": "Anti-Displacement Advocate",
            "rationale": "r=0.902 correlation, 76% agreement. Both focused on preventing displacement, main difference is racial equity framing (Anti-Gentrif) vs. general anti-displacement (Slow Growth). Merge preserves both concerns.",
            "merged_description": "Community stability, anti-displacement, racial equity, skeptical of market-rate development",
            "merged_values": [
                "Community stability and anti-displacement as top priorities",
                "Racial justice and reparations for displacement",
                "Affordable housing without gentrification pressure",
                "Community ownership and cultural preservation"
            ]
        },
        {
            "strength": "MODERATE",
            "pair": ["Renter Advocate", "Affordable Housing Absolutist"],
            "merged_name": "Housing Rights Advocate",
            "rationale": "r=0.807 correlation, 63% agreement. Both are progressive housing advocates. Renter focuses on tenant protections (defensive), Absolutist on social housing (offensive). Merge creates comprehensive housing rights perspective.",
            "merged_description": "Housing as human right, tenant protections, social housing, anti-commodification",
            "merged_values": [
                "Housing as human right requiring public provision and strong protections",
                "Tenant rights, rent control, and anti-eviction protections",
                "Social housing model (Vienna, Singapore) as alternative to market",
                "Renter power in housing policy and community control"
            ]
        },
        {
            "strength": "MODERATE",
            "pair": ["Parent Prioritizer", "Education Advocate"],
            "merged_name": "Family & Education Advocate",
            "rationale": "Conceptual overlap: Parents primarily concerned with education and child services. Education advocates focus on schools and youth programs. Merge captures family-oriented civic priorities comprehensively.",
            "merged_description": "Schools, family services, childcare, educational equity, child safety",
            "merged_values": [
                "Quality public education and well-funded schools",
                "Accessible childcare and after-school programs",
                "Safe, family-friendly neighborhoods and infrastructure",
                "Educational equity and support for all children"
            ]
        }
    ]

    for i, rec in enumerate(recommendations, 1):
        print(f"\n{i}. [{rec['strength']}] {rec['pair'][0]} + {rec['pair'][1]}")
        print(f"   → {rec['merged_name']}")
        print(f"\n   Rationale: {rec['rationale']}")
        print(f"\n   New description: {rec['merged_description']}")
        print(f"   New values:")
        for val in rec['merged_values']:
            print(f"     • {val}")

    print("\n" + "="*80)
    print("RESULT")
    print("="*80)
    print(f"\nStarting archetypes: 25")
    print(f"Recommended merges: 3 pairs")
    print(f"Final archetype count: 22")
    print(f"\nPCA target: 18-19")
    print(f"This recommendation: 22")
    print(f"Gap: 3-4 archetypes (acceptable - preserves important distinctions)")

    print("\n" + "="*80)
    print("NEXT STEPS")
    print("="*80)
    print("\n1. Review recommendations above")
    print("2. Decide which merges to accept (all 3, or just 1-2)")
    print("3. Create archetype_definitions_v3_refined.json")
    print("4. Document merge decisions")
    print("5. Preserve v2 file for potential future use")

if __name__ == "__main__":
    analyze_conceptual_merges()
