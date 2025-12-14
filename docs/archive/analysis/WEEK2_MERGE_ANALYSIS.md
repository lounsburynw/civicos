# Week 2: Archetype Merge Analysis & Recommendations

**Date**: 2025-10-30
**Status**: Investigation Complete - Decision Needed

---

## Executive Summary

**PCA vs. Correlation Tension**:
- **PCA says**: 9 components explain 90% variance → Target 18 archetypes (need 7 merges)
- **Correlation says**: Only 1 strong pair (r > 0.90) → Merge to 24 archetypes (need 1 merge)
- **Gap**: 6 additional merges needed to reach PCA target

**Key Finding**: The 9 "weak" pairs (0.80 < r ≤ 0.85) have only 63-75% agreement on scenarios, suggesting they ARE meaningfully distinct despite moderate correlation.

---

## Statistical Results

### Strong Merge Candidates (r > 0.90)

#### 1. Slow Growth Advocate + Anti-Gentrification Activist (r = 0.902) ✅ MERGE

**Why merge?**
- 75.9% agreement (41/54 scenarios)
- Core overlap: Anti-displacement, community stability, skeptical of market-rate development
- Main difference: Racial equity framing (Anti-Gentrification) vs. general anti-displacement (Slow Growth)

**Proposed merged name**: "Anti-Displacement Advocate"
- Combines anti-gentrification + slow growth perspectives
- Focuses on community stability and racial equity
- Opposes development that threatens displacement

---

## Weak Merge Candidates (0.80 < r ≤ 0.85) - CONCEPTUAL REVIEW NEEDED

### Cluster 1: Progressive Economic Coalition (Labor-Adjacent)

These 6 pairs all involve **Labor Organizer** correlating with various progressive housing/climate archetypes:

#### 2. Labor Organizer + Affordable Housing Absolutist (r = 0.814)
- Agreement: 63.0% (34/54) - **LOWEST IN TOP 10**
- Distinction: Worker rights vs. housing policy focus
- **Recommendation**: KEEP SEPARATE (distinct issue areas)

#### 3. Renter Advocate + Labor Organizer (r = 0.813)
- Agreement: 66.7% (36/54)
- Distinction: Tenant protections vs. worker protections
- **Recommendation**: KEEP SEPARATE (overlapping coalitions, distinct core issues)

#### 4. Green New Dealer + Labor Organizer (r = 0.810)
- Agreement: 74.1% (40/54)
- Distinction: Climate policy vs. labor policy
- **Recommendation**: KEEP SEPARATE (distinct primary focus)

#### 5. Slow Growth Advocate + Labor Organizer (r = 0.809)
- Agreement: 66.7% (36/54)
- Distinction: Anti-displacement vs. worker rights
- **Recommendation**: KEEP SEPARATE (note: Slow Growth already merged with Anti-Gentrif)

#### 6. Green New Dealer + Renter Advocate (r = 0.809)
- Agreement: 70.4% (38/54)
- Distinction: Climate policy vs. housing policy
- **Recommendation**: KEEP SEPARATE

#### 7. Renter Advocate + Affordable Housing Absolutist (r = 0.807)
- Agreement: 63.0% (34/54)
- Distinction: Tenant protections vs. social housing model
- **Recommendation**: CONSIDER MERGE? (both housing-focused, but different tactics)

### Cluster 2: Community-Focused Progressives

#### 8. Slow Growth Advocate + Community Builder (r = 0.807)
- Agreement: 63.0% (34/54)
- Distinction: Anti-displacement vs. social cohesion
- **Recommendation**: KEEP SEPARATE (Community Builder is more centrist)

### Cluster 3: Housing Absolutists

#### 9. Affordable Housing Absolutist + Anti-Gentrification Activist (r = 0.806)
- Agreement: 63.0% (34/54)
- Distinction: Social housing model vs. racial equity/community control
- **Recommendation**: CONSIDER MERGE? (note: Anti-Gentrif already merged with Slow Growth)

#### 10. Slow Growth Advocate + Affordable Housing Absolutist (r = 0.805)
- Agreement: 64.8% (35/54)
- **Recommendation**: Already covered by Slow Growth → Anti-Displacement merge

---

## Pattern Analysis

### Why is "Labor Organizer" everywhere?

**Labor Organizer appears in 4 of 10 pairs**, correlating with:
- Affordable Housing Absolutist
- Renter Advocate
- Green New Dealer
- Slow Growth Advocate

**Interpretation**: Labor Organizer represents the **economic justice axis** that overlaps with many progressive policy areas (housing, climate, anti-displacement). However, it maintains a distinct **worker-centric frame** that's different from issue-specific frames.

**Recommendation**: KEEP Labor Organizer as distinct archetype - it's the "economic justice bridge" that connects multiple progressive movements.

---

## Merge Decision Framework

### Option 1: Conservative (1 merge) → 24 Archetypes
**Merge only**:
1. Slow Growth Advocate + Anti-Gentrification Activist → "Anti-Displacement Advocate"

**Result**: 24 archetypes, all others stay distinct
**Pros**: Respects correlation thresholds, preserves distinct perspectives
**Cons**: Still above PCA recommendation (18-19 target)

---

### Option 2: Moderate (3 merges) → 22 Archetypes
**Merge**:
1. Slow Growth Advocate + Anti-Gentrification Activist → "Anti-Displacement Advocate"
2. Renter Advocate + Affordable Housing Absolutist → "Housing Rights Advocate"
3. (One more TBD - need to review full archetype list for non-correlated candidates)

**Result**: 22 archetypes
**Pros**: Closer to PCA target, consolidates housing advocacy perspectives
**Cons**: May lose nuance between tenant protections (Renter) and social housing (Absolutist)

---

### Option 3: Aggressive (7 merges) → 18 Archetypes
**To reach PCA target of 18, we'd need to merge 7 pairs**

**Challenge**: Only 1 pair has strong statistical support (r > 0.90). The other 6 merges would be forcing consolidation of archetypes that are 63-75% similar but with meaningful 25-37% differences.

**Risk**: Losing important distinctions (e.g., merging Labor Organizer into other archetypes loses the worker-centric frame)

---

## Recommendation

### Path Forward: Option 1 (Conservative) + Manual Review

**Step 1**: Merge the 1 strong candidate (Slow Growth + Anti-Gentrification)

**Step 2**: Review **full archetype list** for conceptual redundancies not captured by correlation:
- Are there archetypes that are conceptually similar but use different framing?
- Are there archetypes with low discrimination across ALL scenarios (not just correlated with one other)?
- Are there archetypes that feel like "sub-types" of broader categories?

**Step 3**: Make 1-2 additional conceptual merges to reach **22-23 archetypes**

**Step 4**: Ship with 22-23 archetypes (close enough to PCA guidance, respects statistical distinctness)

---

## Why Not Trust PCA Fully?

The PCA is telling us that 50.8% of variance is explained by PC1 (likely progressive ↔ conservative axis). This suggests:

1. **Most political variation is on one axis** - the left-right spectrum
2. **But**: We want to capture **within-coalition distinctions** (e.g., different flavors of progressivism)
3. **PCA optimizes for variance**, but we optimize for **user matching and interpretability**

**Example**: Labor Organizer, Green New Dealer, and Renter Advocate might all be "progressive" (similar PC1), but users care about the distinction between worker-focus, climate-focus, and housing-focus.

---

## Next Steps

1. **Decide on merge strategy** (Option 1, 2, or 3)
2. **Review full archetype list** for non-correlated redundancies
3. **Create refined archetype definitions** (v3)
4. **Select final 20 scenarios** (high discrimination, topic balance)
5. **Calculate archetype weights** for client-side matching

---

## Files Generated

- `scripts/investigate_merge_candidates.py` - Detailed correlation analysis
- `data/archetype_correlation_heatmap.png` - Visual correlation matrix
- `data/pca_scree_plot.png` - PCA scree plot
- `data/scenario_discrimination.png` - Scenario discrimination analysis

---

**Status**: ✅ Analysis complete, awaiting decision on merge strategy
