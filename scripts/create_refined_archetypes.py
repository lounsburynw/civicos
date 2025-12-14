"""
Create refined archetype definitions (v3) with strategic merges

Merges:
1. Slow Growth Advocate + Anti-Gentrification Activist → Anti-Displacement Advocate
2. Renter Advocate + Affordable Housing Absolutist → Housing Rights Advocate
3. Parent Prioritizer + Education Advocate → Family & Education Advocate

Result: 25 → 22 archetypes
"""

import json
from datetime import datetime

def create_refined_archetypes():
    """Create v3 refined archetypes with strategic merges"""

    # Load v2 archetypes
    with open('data/archetypes/archetype_definitions_v2.json') as f:
        v2_data = json.load(f)

    # IDs to remove (6 archetypes being merged into 3)
    remove_ids = {
        'slow_growth_advocate',
        'anti_gentrification_activist',
        'renter_advocate',
        'affordable_housing_absolutist',
        'parent_prioritizer',
        'education_advocate'
    }

    # Keep all archetypes except those being merged
    kept_archetypes = [a for a in v2_data['archetypes'] if a['id'] not in remove_ids]

    # Define merged archetypes
    merged_archetypes = [
        {
            "id": "anti_displacement_advocate",
            "name": "Anti-Displacement Advocate",
            "icon": "Shield",
            "iconColor": "#d33682",
            "description": "Community stability, anti-displacement, racial equity, skeptical of market-rate development",
            "core_values": [
                "Community stability and anti-displacement as top priorities",
                "Racial justice and reparations for displacement",
                "Affordable housing without gentrification pressure",
                "Community ownership and cultural preservation"
            ],
            "typical_concerns": [
                "Luxury apartments pricing out existing residents",
                "Racial inequities and historical displacement",
                "Loss of cultural community character and small businesses",
                "Corporate landlords vs. community ownership"
            ],
            "priorities": [
                "100% affordable housing projects and community land trusts",
                "Strong tenant protections and rent control",
                "Racial equity and anti-gentrification measures",
                "Community benefits agreements and local hire"
            ],
            "differentiators": {
                "vs_housing_champion": "Strongly opposed to market-rate development even with affordability requirements",
                "vs_housing_rights_advocate": "More focused on preventing displacement than expanding tenant rights",
                "vs_neighborhood_protector": "Equity-focused not aesthetic, frames preservation through racial justice lens"
            },
            "real_world_examples": [
                "Causa Justa :: Just Cause (Oakland/SF)",
                "SF Mission District tenant organizers",
                "Anti-Eviction Mapping Project"
            ],
            "sample_positions": {
                "market_rate_housing_with_15pct_affordable": "strongly_oppose",
                "100pct_affordable_housing_project": "strongly_support",
                "rent_control_expansion": "strongly_support",
                "community_land_trust_funding": "strongly_support",
                "upzoning_without_affordability_requirements": "strongly_oppose"
            },
            "merged_from": ["slow_growth_advocate", "anti_gentrification_activist"],
            "merge_rationale": "r=0.902 correlation, 76% agreement. Both focused on preventing displacement with slight framing differences (racial equity vs. general anti-displacement). Merge preserves both concerns."
        },
        {
            "id": "housing_rights_advocate",
            "name": "Housing Rights Advocate",
            "icon": "Home",
            "iconColor": "#6c71c4",
            "description": "Housing as human right, tenant protections, social housing, anti-commodification",
            "core_values": [
                "Housing as human right requiring public provision and strong protections",
                "Tenant rights, rent control, and anti-eviction protections",
                "Social housing model (Vienna, Singapore) as alternative to market",
                "Renter power in housing policy and community control"
            ],
            "typical_concerns": [
                "Housing treated as commodity not human right",
                "Weak tenant protections and arbitrary evictions",
                "Insufficient public/social housing investment",
                "Landlord power and real estate speculation"
            ],
            "priorities": [
                "Social housing programs modeled on Vienna, Singapore",
                "Strong rent control and just-cause eviction laws",
                "Tenant organizing and renter power in policy",
                "Public land trusts and community ownership"
            ],
            "differentiators": {
                "vs_housing_champion": "Opposes market-rate development, supports only public/social housing",
                "vs_anti_displacement_advocate": "More focused on tenant rights and public housing than preventing displacement",
                "vs_market_urbanist": "Rejects market solutions, believes housing requires public provision"
            },
            "real_world_examples": [
                "Tenants Together (CA)",
                "Public Housing Advocates",
                "Social Housing Alliance"
            ],
            "sample_positions": {
                "market_rate_housing_with_15pct_affordable": "oppose",
                "100pct_affordable_housing_project": "strongly_support",
                "social_housing_program": "strongly_support",
                "rent_control_expansion": "strongly_support",
                "tenant_right_to_counsel": "strongly_support"
            },
            "merged_from": ["renter_advocate", "affordable_housing_absolutist"],
            "merge_rationale": "r=0.807 correlation, 63% agreement. Both progressive housing advocates with different emphases (tenant protections vs. social housing). Merge creates comprehensive housing rights perspective."
        },
        {
            "id": "family_education_advocate",
            "name": "Family & Education Advocate",
            "icon": "Users",
            "iconColor": "#859900",
            "description": "Schools, family services, childcare, educational equity, child safety",
            "core_values": [
                "Quality public education and well-funded schools",
                "Accessible childcare and after-school programs",
                "Safe, family-friendly neighborhoods and infrastructure",
                "Educational equity and support for all children"
            ],
            "typical_concerns": [
                "Underfunded schools and teacher shortages",
                "Lack of affordable childcare and family services",
                "Unsafe streets and inadequate child-friendly infrastructure",
                "Educational inequity and achievement gaps"
            ],
            "priorities": [
                "Increased school funding and teacher compensation",
                "Universal pre-K and affordable childcare programs",
                "Safe Routes to School and family-friendly design",
                "Library expansion and youth programs"
            ],
            "differentiators": {
                "vs_senior_services_advocate": "Focuses on children and families rather than older adults",
                "vs_community_builder": "Specifically focused on education and family services, not general community programs",
                "vs_safety_first": "Child safety through infrastructure and services, not just law enforcement"
            },
            "real_world_examples": [
                "Parent-Teacher Associations",
                "Education advocacy organizations",
                "Family service nonprofits"
            ],
            "sample_positions": {
                "school_funding_increase": "strongly_support",
                "universal_preschool": "strongly_support",
                "library_expansion": "strongly_support",
                "childcare_subsidy_program": "strongly_support",
                "safe_routes_to_school": "strongly_support"
            },
            "merged_from": ["parent_prioritizer", "education_advocate"],
            "merge_rationale": "Conceptual overlap - parents primarily concerned with education and child services. Education advocates focus on schools and youth programs. Merge captures family-oriented civic priorities comprehensively."
        }
    ]

    # Combine kept + merged archetypes
    v3_archetypes = kept_archetypes + merged_archetypes

    # Sort alphabetically by name
    v3_archetypes.sort(key=lambda x: x['name'])

    # Create v3 data structure
    v3_data = {
        "version": "3.0_refined",
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "archetype_count": len(v3_archetypes),
        "refinement_notes": "Reduced from 25 to 22 archetypes through 3 strategic merges based on correlation analysis and conceptual overlap",
        "merges_applied": [
            {
                "from": ["Slow Growth Advocate", "Anti-Gentrification Activist"],
                "to": "Anti-Displacement Advocate",
                "correlation": 0.902,
                "type": "statistical"
            },
            {
                "from": ["Renter Advocate", "Affordable Housing Absolutist"],
                "to": "Housing Rights Advocate",
                "correlation": 0.807,
                "type": "statistical"
            },
            {
                "from": ["Parent Prioritizer", "Education Advocate"],
                "to": "Family & Education Advocate",
                "correlation": None,
                "type": "conceptual"
            }
        ],
        "preserved_file": "archetype_definitions_v2.json",
        "archetypes": v3_archetypes
    }

    # Save v3
    output_path = 'data/archetypes/archetype_definitions_v3_refined.json'
    with open(output_path, 'w') as f:
        json.dump(v3_data, f, indent=2)

    print(f"✓ Created refined archetypes: {output_path}")
    print(f"\nRefined archetype count: {len(v3_archetypes)}")
    print(f"Original archetype count: {len(v2_data['archetypes'])}")
    print(f"Merges applied: 3 pairs (6 archetypes → 3 archetypes)")
    print(f"\nMerged archetypes:")
    for merged in merged_archetypes:
        print(f"  • {merged['name']} (from: {', '.join(merged['merged_from'])})")

    print(f"\nPreserved original: data/archetypes/archetype_definitions_v2.json")
    print(f"\n✓ All 22 refined archetypes saved successfully")

if __name__ == "__main__":
    create_refined_archetypes()
