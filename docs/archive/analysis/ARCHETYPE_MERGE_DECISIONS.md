# Archetype Merge Decisions - Week 2

**Date**: 2025-10-30
**Action**: Reduced from 25 to 22 archetypes through strategic merges
**Files**:
- Original: `data/archetypes/archetype_definitions_v2.json` (preserved)
- Refined: `data/archetypes/archetype_definitions_v3_refined.json` (22 archetypes)

---

## Executive Summary

**Decision**: Applied **3 strategic merges** to reduce from 25 → 22 archetypes

**Rationale**:
- PCA analysis suggested 18-19 archetypes optimal (9 components = 90% variance)
- Correlation analysis found only 1 strong merge candidate (r > 0.90)
- **Compromise**: Moderate path balancing statistical guidance with preserving distinctions
- Result: 22 archetypes (close to PCA target, respects correlation thresholds)

---

## Statistical Foundation

### PCA Results
- **PC1**: 50.8% variance (progressive ↔ conservative axis dominates)
- **Components for 90% variance**: 9
- **Recommended archetype range**: 15-19

### Correlation Analysis
- **High correlation pairs** (r > 0.80): 10 pairs
- **Strong merge candidates** (r > 0.90): 1 pair
- **Moderate candidates** (0.85 < r ≤ 0.90): 0 pairs
- **Weak candidates** (0.80 < r ≤ 0.85): 9 pairs

### Key Finding
The 9 "weak" pairs (r = 0.80-0.85) showed only 63-75% agreement on scenarios with significant disagreements (Δ = 1.0-3.0), suggesting they ARE meaningfully distinct despite moderate correlation.

---

## Merges Applied

### 1. ✅ Slow Growth Advocate + Anti-Gentrification Activist → **Anti-Displacement Advocate**

**Type**: Statistical merge (strong evidence)

**Correlation**: r = 0.902 (highest in dataset)

**Agreement**: 75.9% (41/54 scenarios)

**Rationale**:
- Both focused on preventing displacement and community stability
- Main difference: Racial equity framing (Anti-Gentrification) vs. general anti-displacement (Slow Growth)
- Merged archetype preserves both concerns under unified "anti-displacement" frame

**Biggest disagreements**:
- budget_002: Δ = 2.00 (-1.0 vs 1.0)
- transportation_001: Δ = 1.00 (0.0 vs -1.0)

**New archetype characteristics**:
- **Core values**: Community stability, racial justice, affordable housing, community ownership
- **Typical concerns**: Luxury displacement, racial inequities, cultural loss, corporate landlords
- **Priorities**: 100% affordable housing, tenant protections, racial equity, community benefits

**Preserves**:
- Anti-displacement focus (from Slow Growth)
- Racial justice frame (from Anti-Gentrification)
- Skepticism of market-rate development (both)
- Community land trust advocacy (both)

---

### 2. ✅ Renter Advocate + Affordable Housing Absolutist → **Housing Rights Advocate**

**Type**: Statistical merge (moderate evidence)

**Correlation**: r = 0.807

**Agreement**: 63.0% (34/54 scenarios)

**Rationale**:
- Both are progressive housing advocates
- Renter Advocate: Defensive (tenant protections, rent control)
- Affordable Housing Absolutist: Offensive (social housing, public development)
- Merged archetype: Comprehensive housing rights perspective (defensive + offensive)

**Biggest disagreements**:
- housing_001: Δ = 2.00 (0.0 vs -2.0)
- transportation_001: Δ = 2.00 (1.0 vs -1.0)

**New archetype characteristics**:
- **Core values**: Housing as human right, tenant protections, social housing model, renter power
- **Typical concerns**: Housing commodification, weak tenant protections, insufficient public housing
- **Priorities**: Social housing (Vienna/Singapore model), rent control, tenant organizing, public land trusts

**Preserves**:
- Tenant protections (from Renter Advocate)
- Social housing advocacy (from Absolutist)
- Anti-commodification stance (both)
- Public provision model (both)

**Why this merge works**:
- Both reject market solutions
- Both frame housing as human right
- Complementary tactics (defensive protections + offensive public provision)

---

### 3. ✅ Parent Prioritizer + Education Advocate → **Family & Education Advocate**

**Type**: Conceptual merge

**Correlation**: Not measured (no correlation data between these two)

**Rationale**:
- Parents primarily concerned with education and child services
- Education advocates focus on schools and youth programs
- Significant conceptual overlap - parents ARE education advocates

**New archetype characteristics**:
- **Core values**: Quality education, childcare access, child safety, educational equity
- **Typical concerns**: Underfunded schools, lack of childcare, unsafe infrastructure, achievement gaps
- **Priorities**: School funding, universal pre-K, safe routes to school, libraries

**Preserves**:
- Education focus (from Education Advocate)
- Family services focus (from Parent Prioritizer)
- Child safety concerns (from Parent Prioritizer)
- Educational equity (from Education Advocate)

**Why this merge works**:
- Natural overlap - parents care most about education
- Both focus on services for children/youth
- Complementary rather than redundant

---

## Archetypes Preserved

### Why We Kept "Labor Organizer" Despite Multiple Correlations

**Labor Organizer** appeared in 4 of 10 high-correlation pairs:
- r=0.814 with Affordable Housing Absolutist
- r=0.813 with Renter Advocate
- r=0.810 with Green New Dealer
- r=0.809 with Slow Growth Advocate

**Decision: KEEP SEPARATE**

**Rationale**:
- Only 63-74% agreement with each correlated archetype
- Maintains distinct "worker-centric" frame vs. issue-specific frames
- Acts as bridge across progressive coalition (housing, climate, labor)
- Economic justice lens is fundamentally different from housing/climate policy lenses

**Pattern**: Labor Organizer correlates with many progressive archetypes NOT because it's redundant, but because it's in the same coalition. They vote together but for different reasons.

---

## Final Archetype Set (22 Total)

### Progressive Housing (2)
1. **Anti-Displacement Advocate** (merged)
2. **Housing Rights Advocate** (merged)

### Pro-Development (2)
3. Housing Champion
4. Market Urbanist

### Climate/Environment (3)
5. Environmental Steward
6. Green New Dealer
7. Transit Advocate

### Demographics (2)
8. **Family & Education Advocate** (merged)
9. Senior Services Advocate

### Economic (3)
10. Labor Organizer
11. Fiscal Conservative
12. Small Business Booster

### Criminal Justice (2)
13. Safety First
14. Justice Reformer

### Governance (3)
15. Government Watchdog
16. Direct Democracy Proponent
17. Pragmatic Incrementalist

### Community (4)
18. Community Builder
19. Neighborhood Protector
20. Regional Thinker
21. Homeowner Stability Seeker

### Technology (1)
22. Techno-Optimist

---

## Comparison to PCA Target

| Metric | Value |
|--------|-------|
| PCA recommendation | 18-19 archetypes |
| Our decision | 22 archetypes |
| Gap | +3 to +4 archetypes |

**Why the gap is acceptable**:
1. PCA optimizes for variance, not interpretability
2. We optimize for user matching and meaningful distinctions
3. Within-coalition differences matter (e.g., Labor vs. Housing vs. Climate focus)
4. 22 is "close enough" while preserving important perspectives

---

## Implementation Notes

### File Preservation
- **Original v2** preserved at `data/archetypes/archetype_definitions_v2.json`
- **Refined v3** created at `data/archetypes/archetype_definitions_v3_refined.json`
- Can revert to v2 if needed

### Metadata Added
Each merged archetype includes:
- `merged_from`: Array of original archetype IDs
- `merge_rationale`: Explanation of why merge was performed

Example:
```json
{
  "id": "anti_displacement_advocate",
  "name": "Anti-Displacement Advocate",
  "merged_from": ["slow_growth_advocate", "anti_gentrification_activist"],
  "merge_rationale": "r=0.902 correlation, 76% agreement..."
}
```

### Next Steps
1. ✅ v3 refined archetypes created (22 archetypes)
2. ⏸️ Select final 20 scenarios (high discrimination, topic balance)
3. ⏸️ Re-run simulation OR use subset of existing responses
4. ⏸️ Calculate archetype weights for client-side matching

---

## Decision Authority

This merge decision balances:
- **Statistical rigor** (PCA, correlation analysis)
- **Conceptual coherence** (meaningful distinctions preserved)
- **Practical utility** (user matching, interpretability)
- **Political reality** (within-coalition differences matter)

The 22-archetype set represents a principled compromise between pure statistical optimization (18-19) and preserving all distinctions (25).

---

**Status**: ✅ Merge decisions finalized and implemented
**Files**: v2 preserved, v3 created (22 archetypes)
**Ready for**: Scenario selection + weight calculation
