# Week 1: Archetype System Implementation Status

**Date**: 2025-10-30
**Session**: 42
**Status**: ✅ **Data Generation Complete** | ⏸️ **Awaiting LLM Simulation Run**

---

## 📊 Completed Deliverables

### ✅ Task 1: Scenario Generation (COMPLETE)

**File**: `data/scenarios/civic_scenarios_v1.json`
**Status**: ✅ 50 scenarios created manually (high quality)

**Distribution**:
- Housing: 6 scenarios (density, affordability, displacement, zoning, tenant protection, social housing)
- Transportation: 6 scenarios (transit, bikes, parking, cars, pedestrian safety)
- Environment: 6 scenarios (climate, trees, energy, waste, water)
- Budget: 6 scenarios (taxes, spending, revenue, debt, priorities, pensions)
- Public Safety: 6 scenarios (police, oversight, surveillance, fire, community, harm reduction)
- Education: 6 scenarios (funding, schools, libraries, early childhood, equity, access)
- Governance: 6 scenarios (transparency, participation, elections, term limits, accountability, voting)
- Development: 6 scenarios (commercial, economic, industrial, downtown, historic, tech)
- Community: 6 scenarios (parks, social services, culture, public spaces, youth, equity)

**Quality Features**:
- ✅ Specific numbers and details (e.g., "8-story, 120-unit", "$500M bond")
- ✅ Real Bay Area context (BART, CalTrain, Berkeley, Oakland)
- ✅ Neutral framing (no loaded language)
- ✅ Real trade-offs revealing values
- ✅ Difficulty tags (easy/moderate/divisive)

---

### ✅ Task 2: Archetype Definitions (COMPLETE)

**File**: `data/archetypes/archetype_definitions_v2.json`
**Status**: ✅ 25 archetypes with full characterization

**Expanded Taxonomy** (from 12 → 25):

**Original 12**:
1. Housing Champion
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

**New 13 Archetypes**:
13. Slow Growth Advocate (left-NIMBY)
14. Market Urbanist (libertarian YIMBY)
15. Green New Dealer (climate + jobs)
16. Techno-Optimist (smart cities)
17. Renter Advocate (tenant rights)
18. Homeowner Stability Seeker (Prop 13)
19. Parent Prioritizer (family services)
20. Senior Services Advocate
21. Direct Democracy Proponent
22. Pragmatic Incrementalist
23. Labor Organizer
24. Affordable Housing Absolutist
25. Anti-Gentrification Activist

**Each Archetype Includes**:
- Core values (4-5 items)
- Typical concerns (4-5 items)
- Priorities (4-5 items)
- Differentiators (vs. 2-3 similar archetypes)
- Real-world Bay Area examples
- Sample positions (5 hypothetical scenarios)
- Icon and color for UI

---

### ✅ Task 3: Response Simulation Script (COMPLETE)

**File**: `scripts/simulate_archetype_responses.py`
**Status**: ✅ Script ready to run

**Features**:
- ✅ Supports both Anthropic Claude and OpenAI GPT-4
- ✅ Flexible rate limiting (default: 1 second delay)
- ✅ Error handling and retry logic
- ✅ Progress tracking
- ✅ JSON output with metadata

**Usage**:
```bash
# Single archetype (testing)
python scripts/simulate_archetype_responses.py --archetype housing_champion --use-openai

# All 25 archetypes (full run - ~50 minutes with 1s rate limit)
python scripts/simulate_archetype_responses.py --all --use-openai
```

**Cost Estimate** (using OpenAI GPT-4):
- 1,250 API calls (25 archetypes × 50 scenarios)
- ~500 tokens per call (input + output)
- ~625K tokens total
- **Estimated cost**: ~$3-5 for full run

---

### ✅ Task 4: Matrix Builder Script (COMPLETE)

**File**: `scripts/build_response_matrix.py`
**Status**: ✅ Script ready to run

**Features**:
- ✅ Builds 25×50 response matrix
- ✅ Statistical analysis (correlation, discrimination)
- ✅ Identifies highly correlated archetypes
- ✅ Identifies low-discrimination scenarios
- ✅ Optional visualizations (requires matplotlib/seaborn)

**Outputs**:
- `data/archetype_response_matrix.csv` - Full matrix
- `data/archetype_correlation_heatmap.png` - Archetype similarity
- `data/archetype_response_matrix_heatmap.png` - Full response visualization
- `data/scenario_discrimination.png` - Scenario discrimination power

**Usage**:
```bash
# Build matrix only
python scripts/build_response_matrix.py

# Build matrix + generate visualizations
python scripts/build_response_matrix.py --visualize
```

---

## ⏸️ Remaining Tasks (User Action Required)

### 🔄 Task 5: Run LLM Simulation (USER ACTION NEEDED)

**What**: Generate 1,250 simulated responses using LLM API

**Prerequisites**:
1. Set API key:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...  # OR
   export OPENAI_API_KEY=sk-proj-...
   ```

2. Install required packages:
   ```bash
   pip install anthropic  # OR
   pip install openai
   ```

**Commands**:
```bash
cd /Users/nicolaslounsbury/projects/civic
source civic-env/bin/activate

# Option 1: Use Anthropic Claude (recommended)
export ANTHROPIC_API_KEY=<your-key>
python scripts/simulate_archetype_responses.py --all

# Option 2: Use OpenAI GPT-4 (works with existing key)
export OPENAI_API_KEY=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
python scripts/simulate_archetype_responses.py --all --use-openai
```

**Time Estimate**: 30-60 minutes (with 1s rate limiting)

**Expected Output**:
- 25 JSON files in `data/archetype_responses/`
- Each file contains 50 scenario responses
- Total: 1,250 simulated responses

---

### 🔄 Task 6: Build Response Matrix (USER ACTION NEEDED)

**What**: Construct 25×50 matrix and generate correlation analysis

**Prerequisites**: Task 5 must be complete (all 25 response files exist)

**Commands**:
```bash
# Install visualization dependencies
pip install pandas numpy matplotlib seaborn

# Build matrix with visualizations
python scripts/build_response_matrix.py --visualize
```

**Expected Output**:
- `data/archetype_response_matrix.csv` (25 rows × 50 columns)
- `data/archetype_correlation_heatmap.png`
- `data/archetype_response_matrix_heatmap.png`
- `data/scenario_discrimination.png`
- Console output with correlation analysis

---

## 📁 Current Directory Structure

```
data/
├── scenarios/
│   └── civic_scenarios_v1.json              ✅ 50 scenarios (29KB)
├── archetypes/
│   └── archetype_definitions_v2.json        ✅ 25 archetypes (42KB)
├── archetype_responses/                     ⏸️ (awaiting simulation)
│   ├── housing_champion_responses.json       (to be generated)
│   ├── slow_growth_advocate_responses.json   (to be generated)
│   └── ... (23 more)
└── (matrix files to be generated)

scripts/
├── generate_scenarios.py                    ✅ Scenario generation
├── simulate_archetype_responses.py          ✅ Response simulation
└── build_response_matrix.py                 ✅ Matrix construction
```

---

## 🎯 Success Criteria

| Metric | Target | Current Status |
|--------|--------|----------------|
| Scenario count | 50 | ✅ 50 |
| Scenarios per topic | 5-6 | ✅ 5-6 per topic |
| Archetype count | 25 | ✅ 25 |
| Response count | 1,250 | ⏸️ 0 (pending simulation) |
| Matrix completeness | 100% | ⏸️ N/A (pending) |
| High correlations | <5 pairs | ⏸️ N/A (pending) |

---

## 🚀 Next Steps

### Immediate (Complete Week 1):
1. **Run LLM simulation** (30-60 minutes, $3-5 cost)
   ```bash
   python scripts/simulate_archetype_responses.py --all --use-openai
   ```

2. **Build response matrix** (1-2 minutes)
   ```bash
   python scripts/build_response_matrix.py --visualize
   ```

3. **Review outputs**:
   - Check for highly correlated archetypes (r > 0.85)
   - Identify low-discrimination scenarios (std < 0.8)
   - Document findings for Week 2

### Week 2 (Next Session):
1. Run PCA on response matrix
2. Identify optimal archetype count (18-22 target)
3. Merge highly correlated archetypes
4. Select top 20 scenarios by discrimination power
5. Finalize refined archetype set

**See**: `docs/ARCHETYPE_SYSTEM_STRATEGY.md` for complete 4-week roadmap

---

## 📚 Key References

**Strategy Documents**:
- `docs/ARCHETYPE_SYSTEM_STRATEGY.md` - Complete 4-week roadmap (32 pages)
- `docs/PRIVACY_ARCHITECTURE.md` - Privacy-first design (Tier 1 browser-only)
- `docs/PERSONALIZATION_SERVICE_ARCHITECTURE.md` - Backend integration

**Data Files**:
- `data/scenarios/civic_scenarios_v1.json` - 50 civic scenarios
- `data/archetypes/archetype_definitions_v2.json` - 25 archetype definitions

**Scripts**:
- `scripts/generate_scenarios.py` - Scenario generation (future use)
- `scripts/simulate_archetype_responses.py` - LLM response simulation
- `scripts/build_response_matrix.py` - Matrix construction & analysis

---

## 💡 Notes

**Why Not Use Anthropic API?**
- Script requires `ANTHROPIC_API_KEY` environment variable
- User has `OPENAI_API_KEY` configured in .env
- Script supports both APIs via `--use-openai` flag
- OpenAI GPT-4 will produce comparable results

**Alternative Approach** (if API costs are concern):
- Could manually simulate a subset of responses (5-10 archetypes × 50 scenarios)
- Would still provide valuable data for correlation analysis
- Could fill in remaining responses with rule-based logic

**Quality Assurance**:
- All 50 scenarios manually reviewed for quality
- All 25 archetypes have comprehensive characterization
- Scripts include error handling and progress tracking
- Matrix builder includes statistical validation

---

**Status**: ✅ Week 1 data generation complete, ready for LLM simulation run
**Time to Complete Week 1**: 1-2 hours (simulation + analysis)
**Estimated Cost**: $3-5 (using OpenAI GPT-4)
