# Archetype System Refinement Strategy

**Status**: Proposed (Session 40+ - 2025-10-30)
**Priority**: High - Foundation for personalization accuracy
**Approach**: LLM-simulated eigenspace derivation + scenario-based discrimination

---

## Executive Summary

**Current System**: 12 hand-crafted archetypes with topic-based weights
**Proposed System**: 20-25 LLM-derived archetypes with scenario-validated positions
**Methodology**: Claude-simulated responses → eigenvector decomposition → validation

**Key Insight**: We can leverage LLM simulation to rapidly prototype and test archetype systems without expensive empirical research. Start comprehensive, validate with real users, iterate.

---

## 🎯 Strategic Goals

### 1. **Greater Expressivity** (Primary Goal)
- Capture nuanced ideological positions (not just topic interests)
- Support intersectional identities (e.g., pro-housing + fiscally conservative)
- Enable fine-grained matching (80%+ user satisfaction with archetype assignments)

### 2. **Predictive Power**
- Infer positions on unseen issues from archetype membership
- Recommend meetings based on *why* someone cares, not just *what topics*
- Support personalized comment drafting with authentic voice

### 3. **Community Formation**
- Connect users with genuinely shared values (not just shared topics)
- Enable nuanced coalition-building (find allies on specific issues)
- Support cross-archetype dialogue (understand opposing viewpoints)

### 4. **Privacy Preservation** (Non-negotiable)
- Maintain Tier 1 architecture (browser-only storage)
- All archetype matching happens client-side
- Zero political data sent to server

---

## 📊 Current System Analysis

### **Architecture** (as of Session 40)

```typescript
// 12 Archetypes with topic weights
const ARCHETYPES = [
  {
    id: 'housing_champion',
    topics: ['housing', 'development', 'zoning'],
    weights: { housing: 1.0, development: 0.6, budget: 0.3 }
  },
  // ... 11 more
]

// Matching: Weighted topic overlap
function matchToArchetypes(swipes) {
  const likedTopics = swipes.filter(s => s.direction === 'right')
  // Score each archetype based on topic overlap
  return topArchetypes(scoreByTopicWeights(likedTopics))
}
```

### **Strengths**
✅ Privacy-preserving (client-side only)
✅ Low cognitive load (swipe = intuitive)
✅ Fast onboarding (30 seconds)
✅ Functional prototype (working code)

### **Limitations**
⚠️ **Topic ≠ Ideology**: "Housing Champion" includes YIMBYs AND inclusionary zoning advocates
⚠️ **Coarse granularity**: 12 archetypes can't capture Bay Area political diversity
⚠️ **No position data**: Can't predict stance on specific issues
⚠️ **Hand-crafted weights**: Assumptions, not data-driven
⚠️ **Limited discrimination**: Multiple archetypes score similarly for many users

---

## 🧬 Proposed System: Eigenspace Archetypes

### **Core Concept: Archetypes as Basis Vectors**

Treat civic values as a high-dimensional space where:
- **Dimensions**: Positions on 40-50 discriminating scenarios
- **Archetypes**: Orthogonal basis vectors (eigenvectors of covariance matrix)
- **Users**: Linear combinations of archetypes

**Mathematical Framework**:
```
User vector U = Σ(w_i × A_i) where:
- U: User's position vector (40-dimensional)
- A_i: Archetype i (basis vector)
- w_i: Weight of archetype i for this user
```

**Example**:
```
User = 0.7×Housing_Champion + 0.5×Fiscal_Conservative + 0.3×Transit_Advocate

Housing scenario: Predict user position via weighted archetype positions
Position_user = 0.7×(+2) + 0.5×(-1) + 0.3×(+1) = +1.1 (support)
```

### **Why Eigenspace?**

1. **Orthogonality**: Archetypes capture independent dimensions of variation
   - Housing density vs. fiscal policy (uncorrelated axes)
   - Environmental protection vs. government transparency (orthogonal concerns)

2. **Interpretability**: Each archetype represents a "pure type"
   - Real users are blends, but archetypes are coherent
   - Like RGB color space: pure red/green/blue combine to make all colors

3. **Dimensionality reduction**: 40 scenarios → 20 archetypes → captures 90% of variance
   - PCA-style compression
   - Discard low-variance dimensions (noise)

4. **Predictive power**: Position on new issue ≈ weighted sum of archetype positions
   - Generalization beyond training scenarios

---

## 🔬 Methodology: LLM-Simulated Derivation

### **Phase 1: Scenario Generation** (2-3 hours)

**Objective**: Create 50 discriminating civic scenarios spanning all topics

**LLM Prompt Strategy**:
```
System: You are an expert in local government and civic engagement. Generate realistic
civic decision scenarios that reveal political values and priorities.

User: Generate 50 civic decision scenarios for Bay Area municipalities that:

REQUIREMENTS:
1. Real trade-offs (not softball questions)
2. Specific and concrete (numbers, locations, timelines)
3. Neutral framing (no loaded language)
4. Span all topics: housing, transit, environment, budget, safety, education,
   governance, development, community, elections
5. Multiple difficulty levels (easy to divisive)
6. Discriminating (different ideologies give different answers)

TOPICS TO COVER (5 scenarios each):
- Housing: Density, affordability, displacement, zoning
- Transportation: Cars vs. transit vs. bikes, parking, traffic
- Environment: Climate, trees, waste, energy
- Budget: Taxes, spending priorities, debt
- Public Safety: Police, fire, emergency services
- Education: Schools, libraries, youth programs
- Governance: Transparency, accountability, participation
- Development: Commercial, mixed-use, economic development
- Community: Parks, culture, social services
- Elections: Voting, districts, campaign finance

SCENARIO STRUCTURE:
- Context (1 sentence)
- Decision (specific proposal with numbers)
- Response scale: Strongly Support / Support / Neutral / Oppose / Strongly Oppose

EXAMPLE (Good):
"A developer proposes an 8-story, 120-unit apartment building on a surface parking lot
downtown. 15% of units would be affordable (80% AMI). The project requires a zoning
variance for height. Do you support this project?"

EXAMPLE (Bad - too vague):
"Should the city build more housing?"

Generate all 50 scenarios now.
```

**Quality Criteria**:
- Each scenario should discriminate between at least 3-4 archetypes
- No scenarios where >80% of archetypes agree (too easy)
- Cover range of local government authority (not federal issues)
- Use Bay Area context (BART, CalTrain, Prop 13, etc.)

**Output**: JSON file with 50 scenarios
```json
{
  "scenarios": [
    {
      "id": "housing_001",
      "topic": "housing",
      "category": "density",
      "text": "A developer proposes...",
      "response_scale": ["strongly_support", "support", "neutral", "oppose", "strongly_oppose"],
      "difficulty": "moderate"
    }
  ]
}
```

---

### **Phase 2: Archetype Definition** (3-4 hours)

**Objective**: Define 20-25 civic archetypes with rich characterization

**Expanded Archetype Taxonomy** (proposed):

#### **Core Archetypes** (12 - existing)
1. Housing Champion (YIMBY)
2. Transit Advocate
3. Environmental Steward
4. Fiscal Conservative
5. Community Builder
6. Safety First
7. Education Advocate
8. Small Business Booster
9. Government Watchdog
10. Neighborhood Protector
11. Justice Reformer
12. Regional Thinker

#### **New Archetypes** (8-13 additional)

**Ideological Nuance:**
13. **Slow Growth Advocate** (left-NIMBY)
    - Anti-displacement, pro-tenant, skeptical of market-rate development
    - Distinct from Neighborhood Protector (equity focus vs. aesthetic focus)

14. **Market Urbanist** (libertarian YIMBY)
    - Pro-housing density, anti-regulation, free market solutions
    - Distinct from Housing Champion (less affordable housing mandates)

15. **Green New Dealer** (climate + jobs)
    - Environmental action via government programs
    - Distinct from Environmental Steward (policy mechanism)

16. **Techno-Optimist**
    - Smart cities, data-driven governance, innovation
    - Distinct from Regional Thinker (technology focus)

**Demographic/Identity Archetypes:**
17. **Renter Advocate**
    - Tenant protections, rent control, eviction defense
    - High overlap with Housing Champion, but distinct priorities

18. **Homeowner Stability Seeker**
    - Property value protection, tax stability (Prop 13)
    - Distinct from Fiscal Conservative (personal stake vs. ideology)

19. **Parent Prioritizer**
    - Schools, childcare, youth programs, safety
    - Crosscutting (can be progressive or conservative)

20. **Senior Services Advocate**
    - Accessible infrastructure, healthcare, fixed income concerns
    - Often fiscally moderate, socially varied

**Governance Philosophy:**
21. **Direct Democracy Proponent**
    - Ballot measures, referendums, participatory budgeting
    - Distinct from Government Watchdog (mechanism preference)

22. **Pragmatic Incrementalist**
    - Evidence-based policy, pilot programs, iterative improvement
    - Moderate on most issues, focused on implementation

**Economic Justice:**
23. **Labor Organizer**
    - Worker rights, living wage, union support, prevailing wage
    - Distinct from Justice Reformer (economic vs. criminal justice)

24. **Affordable Housing Absolutist**
    - 100% affordable projects, social housing, anti-market solutions
    - Distinct from Housing Champion (public vs. mixed approach)

25. **Anti-Gentrification Activist**
    - Community land trusts, tenant ownership, anti-displacement
    - Overlaps with Slow Growth, but focused on racial equity

**Total: 25 Archetypes**

**Archetype Characterization Template**:
```json
{
  "id": "slow_growth_advocate",
  "name": "Slow Growth Advocate",
  "icon": "Shield",
  "iconColor": "#d33682",
  "description": "Anti-displacement focus, skeptical of market-rate development",

  "core_values": [
    "Community stability and anti-displacement",
    "Affordable housing without gentrification",
    "Tenant protections and rent control",
    "Equity over growth"
  ],

  "typical_concerns": [
    "Luxury apartments pricing out existing residents",
    "Developers exploiting affordable housing loopholes",
    "Loss of cultural community character",
    "Corporate landlords vs. local ownership"
  ],

  "priorities": [
    "100% affordable housing projects",
    "Community land trusts",
    "Strong tenant protections",
    "Local hire requirements"
  ],

  "differentiators": {
    "vs_housing_champion": "Skeptical of market-rate development (even with affordability %)",
    "vs_neighborhood_protector": "Equity-focused (not aesthetic), supports density if affordable",
    "vs_affordable_housing_absolutist": "Accepts some market-rate if strong protections"
  },

  "real_world_examples": [
    "SF Mission District tenant organizers",
    "Oakland anti-displacement activists",
    "Berkeley inclusionary zoning advocates"
  ],

  "sample_positions": {
    "800_unit_market_rate": "oppose",
    "100_unit_100pct_affordable": "strongly_support",
    "rent_control_expansion": "strongly_support",
    "upzoning_without_affordability": "oppose",
    "community_land_trust": "strongly_support"
  }
}
```

---

### **Phase 3: LLM Response Simulation** (2-3 hours)

**Objective**: Generate archetype response profiles for all 50 scenarios

**LLM Prompt (per archetype)**:
```
System: You are simulating a specific civic archetype for research purposes.
Respond authentically to civic scenarios based on this archetype's values and priorities.

User: You are simulating the "{archetype_name}" archetype.

ARCHETYPE CHARACTERISTICS:
Name: {name}
Description: {description}
Core values: {values}
Typical concerns: {concerns}
Priorities: {priorities}
Real-world examples: {examples}

TASK: Respond to the following 50 civic decision scenarios.

For each scenario, provide:
1. Position: strongly_support / support / neutral / oppose / strongly_oppose
2. Confidence: 0-100 (how certain is this archetype's position?)
3. Reasoning: 2-3 sentences explaining why this archetype holds this view

IMPORTANT:
- Be consistent with the archetype's values
- Show nuance (this isn't a caricature)
- Consider trade-offs (archetypes can have conflicting values)
- Use realistic reasoning (not Twitter slogans)
- Acknowledge when the archetype would be internally conflicted (lower confidence)

SCENARIO 1:
{scenario_text}

Your response:
```

**Response Format**:
```json
{
  "archetype_id": "slow_growth_advocate",
  "scenario_responses": [
    {
      "scenario_id": "housing_001",
      "position": "oppose",
      "confidence": 75,
      "reasoning": "While the 15% affordability is a start, 85% market-rate units will drive up surrounding rents and displace existing low-income residents. The height variance also sets a precedent for luxury development. This archetype would prefer 100% affordable or stronger affordability requirements."
    }
  ]
}
```

**Execution**:
- Generate responses for all 25 archetypes (25 LLM calls)
- Store in `data/archetype_responses/` directory
- Takes ~2-3 hours with rate limiting

---

### **Phase 4: Eigenspace Decomposition** (1-2 hours)

**Objective**: Extract orthogonal dimensions and validate archetype independence

**Step 1: Build Response Matrix**
```python
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA

# Load all archetype responses
responses = load_archetype_responses()

# Build matrix: rows = archetypes, columns = scenarios
# Values: -2 (strongly oppose) to +2 (strongly support)
position_map = {
    'strongly_oppose': -2,
    'oppose': -1,
    'neutral': 0,
    'support': 1,
    'strongly_support': 2
}

matrix = np.zeros((25, 50))  # 25 archetypes × 50 scenarios
for i, archetype in enumerate(archetypes):
    for j, scenario in enumerate(scenarios):
        position = responses[archetype.id][scenario.id]['position']
        matrix[i, j] = position_map[position]

# Save for analysis
df = pd.DataFrame(matrix,
                  index=[a.name for a in archetypes],
                  columns=[s.id for s in scenarios])
df.to_csv('data/archetype_response_matrix.csv')
```

**Step 2: PCA Analysis**
```python
# Principal Component Analysis
pca = PCA(n_components=25)
pca.fit(matrix)

# Analyze explained variance
explained_variance = pca.explained_variance_ratio_
cumulative_variance = np.cumsum(explained_variance)

# How many components explain 90% of variance?
n_components_90 = np.argmax(cumulative_variance > 0.9) + 1
print(f"Components needed for 90% variance: {n_components_90}")

# Expected: 15-20 components (some archetypes are highly correlated)
```

**Step 3: Correlation Analysis**
```python
# Calculate archetype correlation matrix
correlation = np.corrcoef(matrix)

# Identify highly correlated archetypes (r > 0.8)
high_correlation_pairs = []
for i in range(25):
    for j in range(i+1, 25):
        if correlation[i, j] > 0.8:
            high_correlation_pairs.append((
                archetypes[i].name,
                archetypes[j].name,
                correlation[i, j]
            ))

# Consider merging highly correlated archetypes
print("Highly correlated pairs (consider merging):")
for pair in high_correlation_pairs:
    print(f"  {pair[0]} <-> {pair[1]}: r={pair[2]:.2f}")
```

**Step 4: Scenario Discrimination Analysis**
```python
# For each scenario, calculate variance in archetype positions
scenario_discrimination = []
for j, scenario in enumerate(scenarios):
    positions = matrix[:, j]
    variance = np.var(positions)

    # Higher variance = better discrimination between archetypes
    scenario_discrimination.append({
        'scenario_id': scenario.id,
        'topic': scenario.topic,
        'variance': variance,
        'mean_position': np.mean(positions),
        'range': np.max(positions) - np.min(positions)
    })

# Sort by discrimination power
scenario_discrimination.sort(key=lambda x: x['variance'], reverse=True)

# Keep top 20 scenarios (highest discrimination)
best_scenarios = scenario_discrimination[:20]
```

**Expected Outcomes**:
- **Dimensionality**: 15-20 independent dimensions (rest are redundant)
- **Correlations**: Some archetypes will be highly correlated (merge candidates)
- **Scenario quality**: 20-25 scenarios with high discrimination power

---

### **Phase 5: Archetype Refinement** (2-3 hours)

**Objective**: Prune/merge archetypes based on PCA results

**Decision Rules**:

1. **Merge highly correlated archetypes** (r > 0.85)
   - Example: If "Transit Advocate" and "Regional Thinker" are 0.9 correlated, merge into "Transit & Regional Advocate"

2. **Remove low-variance archetypes** (explain <1% of variance)
   - These don't add discriminatory power

3. **Validate archetype distinctiveness**
   - Each archetype should have at least 3-5 scenarios where it differs significantly from others

4. **Check topic coverage**
   - Ensure all major topics have at least 2 archetypes with differing views

**Refinement Process**:
```python
def refine_archetypes(archetypes, correlation_matrix, pca_results):
    """Prune/merge archetypes based on statistical analysis"""

    refined = []
    merged = set()

    for i, archetype in enumerate(archetypes):
        if i in merged:
            continue

        # Check if this archetype is highly correlated with any other
        high_corr_indices = np.where(correlation_matrix[i] > 0.85)[0]
        high_corr_indices = [idx for idx in high_corr_indices if idx > i]  # Avoid duplicates

        if len(high_corr_indices) > 0:
            # Merge archetypes
            merge_candidates = [archetypes[idx] for idx in high_corr_indices]
            merged_archetype = merge_archetypes(archetype, merge_candidates)
            refined.append(merged_archetype)
            merged.update(high_corr_indices)
        else:
            # Keep archetype as-is
            refined.append(archetype)

    return refined
```

**Expected Result**: 18-22 refined archetypes with low inter-correlation

---

## 🎮 Implementation: Hybrid Onboarding Flow

### **User Experience** (5-7 minutes total)

**Phase 1: Topic Discovery** (1-2 min, existing)
- Swipe on 10-12 topic cards
- Quick interest filtering
- Low cognitive load

**Phase 2: Scenario Positioning** (4-5 min, new)
- Show 12-15 high-discrimination scenarios
- Scenarios selected based on Phase 1 interests (personalized)
- 5-point Likert scale: Strongly Support → Strongly Oppose
- Optional "Why?" free-text field (for qualitative analysis)

**Phase 3: Archetype Assignment** (instant, client-side)
- Calculate archetype weights based on scenario responses
- Show user top 3 archetypes with explanations
- Allow user to adjust weights ("I'm more X than Y")

### **Matching Algorithm** (Client-Side TypeScript)

```typescript
interface ScenarioResponse {
  scenario_id: string
  position: -2 | -1 | 0 | 1 | 2  // Strongly oppose → Strongly support
  confidence?: number
}

interface ArchetypeWeight {
  archetype_id: string
  weight: number  // 0-1 normalized
  fit_score: number  // Correlation with archetype's response profile
}

function matchToArchetypes(
  topicSwipes: SwipeResult[],
  scenarioResponses: ScenarioResponse[],
  topN: number = 3
): ArchetypeWeight[] {

  // Build user response vector (50-dimensional)
  const userVector = buildResponseVector(scenarioResponses)

  // Calculate correlation with each archetype's response profile
  const archetypeScores = ARCHETYPES.map(archetype => {
    // Pearson correlation between user vector and archetype vector
    const correlation = pearsonCorrelation(userVector, archetype.responseVector)

    // Weighted by topic interest (from swipes)
    const topicBoost = calculateTopicBoost(topicSwipes, archetype.topics)

    // Combined score: 70% scenario correlation, 30% topic interest
    const finalScore = 0.7 * correlation + 0.3 * topicBoost

    return {
      archetype_id: archetype.id,
      weight: 0,  // Will be normalized later
      fit_score: finalScore
    }
  })

  // Normalize scores to sum to 1.0
  const totalScore = archetypeScores.reduce((sum, a) => sum + a.fit_score, 0)
  archetypeScores.forEach(a => {
    a.weight = a.fit_score / totalScore
  })

  // Return top N archetypes
  return archetypeScores
    .sort((a, b) => b.weight - a.weight)
    .slice(0, topN)
}

function pearsonCorrelation(vectorA: number[], vectorB: number[]): number {
  const n = vectorA.length
  const meanA = vectorA.reduce((sum, x) => sum + x, 0) / n
  const meanB = vectorB.reduce((sum, x) => sum + x, 0) / n

  let numerator = 0
  let denomA = 0
  let denomB = 0

  for (let i = 0; i < n; i++) {
    const diffA = vectorA[i] - meanA
    const diffB = vectorB[i] - meanB
    numerator += diffA * diffB
    denomA += diffA * diffA
    denomB += diffB * diffB
  }

  return numerator / Math.sqrt(denomA * denomB)
}
```

### **Data Architecture** (Privacy-Preserving)

**What's stored in localStorage** (client-only):
```typescript
{
  "civic-archetypes": [
    {
      "archetype_id": "slow_growth_advocate",
      "weight": 0.45,
      "fit_score": 0.82,
      "rank": 1
    },
    {
      "archetype_id": "environmental_steward",
      "weight": 0.35,
      "fit_score": 0.71,
      "rank": 2
    },
    {
      "archetype_id": "housing_champion",
      "weight": 0.20,
      "fit_score": 0.58,
      "rank": 3
    }
  ],
  "civic-scenario-responses": [
    {
      "scenario_id": "housing_001",
      "position": -1,  // Oppose
      "timestamp": "2025-10-30T12:34:56Z"
    }
    // ... 14 more scenarios
  ],
  "civic-profile-updated": "2025-10-30T12:35:00Z"
}
```

**What's NEVER sent to server**:
- Scenario responses (positions on issues)
- Archetype weights
- Political preferences

**What IS sent to server** (optional, non-political):
- Demographics (stakes, years in area, expertise)
- Jurisdiction
- Behavioral tracking (which meetings clicked, but not why)

---

## 🧪 Validation Strategy

### **Phase 1: Internal Testing** (1-2 days)

**Team members + trusted advisors**:
1. Complete onboarding flow (swipes + scenarios)
2. Review archetype assignments
3. Qualitative feedback: "Does this feel accurate?"

**Success Criteria**:
- 80%+ say "This captures my values reasonably well"
- No major archetypes missing
- Scenarios feel realistic and fair

### **Phase 2: Small-Scale User Testing** (1 week, optional)

**Recruit 20-30 real users**:
- Mix of demographics (age, tenure, ideology)
- Diverse jurisdictions (Berkeley, Oakland, San Jose, etc.)
- Incentivize with early access / $25 gift cards

**Methodology**:
1. Users complete onboarding
2. Show them 5 predicted positions (based on archetypes)
3. Ask: "Do you agree with these predictions?"
4. Collect prediction accuracy

**Success Criteria**:
- 70%+ prediction accuracy (excellent for MVP)
- 50-70% accuracy (iterate on scenarios/archetypes)
- <50% accuracy (need empirical research)

### **Phase 3: Behavioral Validation** (Ongoing)

**Track user engagement** (client-side only):
- Do users click on recommended meetings?
- Do archetype-based recommendations outperform topic-based?
- Do users update/refine their archetypes over time?

**Metrics**:
- Click-through rate on recommendations
- Time spent on archetype-aligned content
- User retention and return visits

---

## 📋 Implementation Roadmap

### **Week 1: Foundation** (8-12 hours)

**Day 1-2: Scenario Generation**
- [ ] Design LLM prompts for scenario generation
- [ ] Generate 50 scenarios (10 per major topic)
- [ ] Review for quality, balance, and discrimination power
- [ ] Store in `data/scenarios/civic_scenarios_v1.json`

**Day 3-4: Archetype Expansion**
- [ ] Define 25 archetypes with full characterization
- [ ] Write archetype profiles (values, concerns, priorities)
- [ ] Document differentiators between similar archetypes
- [ ] Store in `frontend/civic-workspace/src/utils/archetypes.ts`

**Day 5: LLM Response Simulation**
- [ ] Design prompts for archetype simulation
- [ ] Generate 25 × 50 = 1,250 responses
- [ ] Store in `data/archetype_responses/`
- [ ] Build response matrix CSV

### **Week 2: Analysis & Refinement** (6-8 hours)

**Day 1: Statistical Analysis**
- [ ] Run PCA on archetype response matrix
- [ ] Calculate correlation matrix
- [ ] Identify high-correlation pairs (merge candidates)
- [ ] Rank scenarios by discrimination power

**Day 2: Archetype Pruning**
- [ ] Merge highly correlated archetypes
- [ ] Remove low-variance archetypes
- [ ] Finalize 18-22 refined archetypes
- [ ] Update archetype definitions

**Day 3: Scenario Selection**
- [ ] Select top 20 scenarios (highest discrimination)
- [ ] Ensure topic balance (2-3 per major topic)
- [ ] Ensure difficulty range (easy to divisive)
- [ ] Finalize scenario set

### **Week 3: Implementation** (12-16 hours)

**Day 1-2: Scenario UI**
- [ ] Build `ScenarioCard.vue` component
- [ ] 5-point Likert scale interaction
- [ ] Progress tracking
- [ ] Mobile-responsive design

**Day 2-3: Matching Algorithm**
- [ ] Implement Pearson correlation calculation
- [ ] Build hybrid scoring (scenarios + topics)
- [ ] Archetype weight normalization
- [ ] Client-side localStorage persistence

**Day 3-4: Results Display**
- [ ] Archetype results screen
- [ ] Top 3 archetypes with weights
- [ ] Archetype descriptions and icons
- [ ] "Refine Profile" flow

**Day 4-5: Integration**
- [ ] Update `ProfilePanel.vue` to display archetypes
- [ ] Update event filtering to use scenario-based archetypes
- [ ] Export/import with scenario responses
- [ ] Migration from old archetype format

### **Week 4: Testing & Launch** (6-8 hours)

**Day 1-2: Internal Testing**
- [ ] Team completes onboarding
- [ ] Qualitative feedback session
- [ ] Bug fixes and UX refinements

**Day 3: Documentation**
- [ ] User-facing archetype explanations
- [ ] Privacy disclosure updates
- [ ] API documentation (scenario retrieval endpoint)

**Day 4: Soft Launch**
- [ ] Deploy to staging
- [ ] Invite 10-20 beta testers
- [ ] Monitor for issues

**Day 5: Production Deployment**
- [ ] Deploy to production
- [ ] Monitor engagement metrics
- [ ] Collect feedback for iteration

---

## 📊 Success Metrics

### **Technical Metrics**

| Metric | Target | Measurement |
|--------|--------|-------------|
| Archetype count | 18-22 | Final refined set |
| Explained variance | >90% | PCA cumulative variance |
| Inter-archetype correlation | <0.8 | Pearson correlation matrix |
| Scenario discrimination | Variance >0.5 | Position variance across archetypes |
| Onboarding completion rate | >70% | Users who finish scenario phase |

### **User Metrics**

| Metric | Target | Measurement |
|--------|--------|-------------|
| Archetype fit satisfaction | >75% | "Does this feel accurate?" |
| Prediction accuracy | >70% | Held-out scenarios |
| Recommendation CTR | >30% | Clicks on archetype-based recommendations |
| Profile refinement rate | 10-20% | Users who retake onboarding |
| Time to complete onboarding | 5-7 min | Median completion time |

### **Privacy Metrics**

| Metric | Target | Measurement |
|--------|--------|-------------|
| Server political data storage | 0 bytes | Verify no scenario responses stored |
| localStorage usage | <50KB | Average user data size |
| Export success rate | >95% | Users can export/import profiles |

---

## 🚀 Future Enhancements

### **Short-term** (Next 3 months)

1. **Adaptive Scenario Selection**
   - Show scenarios most likely to discriminate based on previous answers
   - Reduce onboarding time from 15 scenarios to 8-10

2. **Confidence Weighting**
   - Users indicate confidence in their positions
   - Weight high-confidence responses more heavily

3. **Archetype Evolution Tracking**
   - Detect when user behavior diverges from archetypes
   - Prompt: "Your interests seem to have shifted. Update profile?"

### **Medium-term** (6-12 months)

4. **Empirical Validation**
   - Survey 100-200 real residents
   - Compare LLM-simulated archetypes to empirical clusters
   - Refine based on real data

5. **Regional Calibration**
   - Different archetype weights for different regions
   - Bay Area vs. Central Valley vs. SoCal political landscapes

6. **Dynamic Archetype Discovery**
   - Detect emerging civic archetypes from user behavior
   - Add new archetypes when variance is unexplained

### **Long-term** (12+ months)

7. **Cross-Jurisdictional Insights**
   - Compare archetype distributions across cities
   - "Berkeley is 40% Environmental Steward, Oakland is 25%"

8. **Coalition Mapping**
   - Which archetypes align on specific issues?
   - Visualize potential coalitions

9. **Personalized Comment Generation**
   - Use archetype weights to generate authentic-sounding comments
   - "Write like a Slow Growth Advocate + Environmental Steward"

---

## 🎯 Decision Points

### **Archetype Count: 18-22 vs. 25+**

**Recommendation: Start with 25, prune to 18-22 based on PCA**

Rationale:
- Better to start expressive and prune than miss important dimensions
- PCA will reveal redundancies
- Users only see top 3 (complexity is hidden)

### **Scenario Count: 15 vs. 20 vs. 30**

**Recommendation: 15 scenarios in onboarding, 50 in dataset**

Rationale:
- 15 is max users will tolerate (5-7 min)
- Select 15 adaptively based on topic swipes
- 50-scenario dataset allows future experimentation

### **Weighting: Scenarios vs. Topics**

**Recommendation: 70% scenarios, 30% topics**

Rationale:
- Scenarios reveal ideology (what we want)
- Topics provide topic-level filtering (still useful)
- Can A/B test different weightings

### **When to do Empirical Research?**

**Recommendation: LLM-first, empirical validation in 6 months**

Rationale:
- LLM simulation is fast and cheap (ship now)
- Validate with 20-30 users (small-scale testing)
- If 70%+ accuracy: keep iterating with LLM
- If <70% accuracy: invest in empirical study

---

## 📝 Open Questions

1. **Should we show archetype weights to users?**
   - Pros: Transparency, users understand their profile
   - Cons: Complexity, may feel reductive
   - Proposal: Optional "Advanced View" for power users

2. **How to handle archetype evolution?**
   - Do we track changes over time?
   - Prompt users to retake when behavior diverges?
   - Allow manual weight adjustment?

3. **Should scenario responses be exportable?**
   - Pros: Users own their data (privacy-first)
   - Cons: Could be used for political targeting if leaked
   - Proposal: Export but with prominent privacy warning

4. **How to present prediction uncertainty?**
   - Some archetypes won't have strong predictions on all issues
   - Show confidence intervals?
   - Say "unclear" instead of guessing?

5. **Should we allow users to see archetype response patterns?**
   - Educational: "Here's how a Fiscal Conservative typically thinks"
   - Risk: Stereotyping, caricature
   - Proposal: Show as "example position, not definitive"

---

## 🔗 Related Documents

- `docs/PRIVACY_ARCHITECTURE.md` - Privacy tiers and browser-only storage
- `docs/PERSONALIZATION_SERVICE_ARCHITECTURE.md` - Backend integration
- `docs/COMMENT_DRAFTING_ARCHITECTURE.md` - Archetype-based comment generation
- `docs/FRONTEND_TECHNICAL_ARCHITECTURE.md` - UI/UX integration
- `docs/next_session_prompt.md` - Current implementation status

---

## Conclusion

**Comprehensive LLM-based archetype system is achievable in 3-4 weeks** with:
- Greater expressivity (18-22 archetypes vs. 12)
- Higher accuracy (scenario-based vs. topic-based)
- Maintained privacy (browser-only storage)
- Empirically validatable (can test with real users later)

**Next Step**: Generate scenarios and archetype responses (Week 1)

**Long-term Vision**: Foundation-funded civic infrastructure with best-in-class personalization that respects user privacy and political autonomy.

---

**Status**: Ready for implementation
**Owner**: To be assigned
**Timeline**: 3-4 weeks to production-ready
**Dependencies**: None (can start immediately)
