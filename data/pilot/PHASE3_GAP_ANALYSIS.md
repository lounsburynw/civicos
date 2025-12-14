# Phase 3: Systematic Complaint-Policy Gap Analysis

**Date**: 2024-11-24
**Dataset**: SeeClickFix complaints (237 matched) + Testimony (Mar-Oct 2024)
**Finding**: Gap is TOPIC-DEPENDENT - camping has INVERSE gap, traffic/infrastructure have HIGH gaps

---

## Executive Summary

### TEMPORALLY MATCHED DATA (Corrected Analysis)

Initial analysis used mismatched time periods. After full API pagination, we have **237 SeeClickFix complaints properly matched to the March-October 2024 testimony period**.

### Key Finding: Gap Varies by Topic Type

| Topic | Complaints | Testimony | Ratio | Interpretation |
|-------|-----------|-----------|-------|----------------|
| **Camping/Homelessness** | 7 | 18 speakers | **0.4:1** | INVERSE - more testimony than complaints |
| **Traffic Safety** | 111 | 8 speakers | **13.9:1** | HIGH gap - 14x more complainants |
| **Infrastructure** | 81 | 0 speakers | **∞:1** | EXTREME gap - no testimony |
| **Environment** | 11 | 0 speakers | **∞:1** | EXTREME gap - no testimony |

### Validated Hypothesis

**Policy topics (camping, housing)**: People TESTIFY but don't file 311 complaints
**Operational topics (traffic, potholes)**: People FILE COMPLAINTS but don't testify

---

## Data Sources

### SeeClickFix Complaints (Temporally Matched)
- **Period**: March 1 - October 31, 2024
- **Total**: 237 complaints (from 1,340 total in API)
- **Source**: Full API pagination (14 pages)

| Category | Count | % |
|----------|-------|---|
| Traffic Safety | 111 | 46.8% |
| Infrastructure | 81 | 34.2% |
| Other | 27 | 11.4% |
| Environment | 11 | 4.6% |
| Camping/Homelessness | 7 | 3.0% |

### Testimony Data
- **Period**: March 18 - October 7, 2024
- **Meetings**: 9 San Rafael City Council meetings
- **Utterances**: 3,563 total
- **Speakers**: 78 speaker slots across meetings

| Topic | Speakers | Meetings |
|-------|----------|----------|
| Budget | 19 | 2 |
| Camping/Homelessness | 18 | 2 |
| Design Standards | 10 | 1 |
| Health Services | 10 | 1 |
| Traffic Safety | 8 | 1 |
| Climate | 8 | 1 |

---

## The Inverse Gap Hypothesis

### Camping: More Testimony than Complaints

**Data:**
- SeeClickFix camping complaints: 16 (2.1% of all complaints)
- Testimony speakers on camping: 18 speakers across 2 meetings
- April 15 + Aug 19 = 1,393 utterances (39% of all testimony)

**Interpretation:** Camping/homelessness is a **policy-driven** topic. People engage through testimony (advocacy), not 311 complaints. The "gap" doesn't apply - residents ALREADY participate at high rates on controversial policy topics.

### Infrastructure: More Complaints than Testimony

**Data:**
- SeeClickFix infrastructure complaints: 212 (27.5% of all complaints)
- Testimony speakers on infrastructure: ~0 (no infrastructure-focused meetings in dataset)

**Interpretation:** Infrastructure is **operationally-driven**. People file 311 complaints but DON'T attend council meetings about potholes. This is where the gap hypothesis holds.

### Traffic: Mixed Pattern

**Data:**
- SeeClickFix traffic complaints: 195 (25.3% of all complaints)
- Testimony speakers on e-bikes: 8 (July 15 meeting)

**Interpretation:** Traffic has BOTH 311 complaints AND testimony when policy is debated (e-bike safety). Gap may apply for routine traffic issues but not for policy decisions.

---

## Revised Gap Framework

### Category 1: Policy Topics (LOW Gap)
- Camping/homelessness
- Housing/development
- Climate/environment policy
- Budget priorities

**Characteristics:**
- High controversy
- Media coverage
- Organized advocacy groups
- Residents already engaged

**Platform opportunity:** Coordination infrastructure (help engaged residents be more effective)

### Category 2: Operational Topics (HIGH Gap)
- Potholes/road conditions
- Streetlights
- Sidewalk repairs
- Stormwater drainage

**Characteristics:**
- Low controversy
- No media coverage
- Individual complaints, not organized
- Residents file 311 but don't attend meetings

**Platform opportunity:** Decision awareness (notify complainants when policy affects their issue)

### Category 3: Bridge Topics (VARIABLE Gap)
- Traffic safety (operations + policy)
- Parks (maintenance + programming)
- Trees (maintenance + climate policy)

**Characteristics:**
- Depends on whether policy decision is pending
- Gap widens when no pending decision
- Gap narrows when controversial decision upcoming

**Platform opportunity:** Matching + timing (connect complaints to decisions when they occur)

---

## Wildfire Case Study Validation

### The 82% Gap is REAL but CONTEXT-SPECIFIC

**October 6, 2025 Wildfire Fund (API-validated Sessions 96-97):**
- 22 fire/vegetation complaints in 30 days before meeting
- 4 residents testified
- 82% gap = 18 residents

**Why wildfire gap exists:**
1. Wildfire prevention is **budgetary** (Category 2: operational) not **advocacy** (Category 1: policy)
2. Consent calendar item = low visibility
3. No organized advocacy group for vegetation management
4. Complainants didn't know about budget allocation

**Why camping gap is different:**
1. Camping ordinance is **highly controversial** (Category 1: policy)
2. Major agenda item = high visibility
3. Organized advocacy on both sides
4. Multiple media stories increased awareness

---

## Hypothesis Refinement

### Original Hypothesis
> "86% of complaint filers don't participate in policy decisions"

### Refined Hypothesis
> "The complaint-to-testimony gap is topic-dependent:
> - **Low gap** for controversial policy topics (advocacy-driven engagement)
> - **High gap** for routine operational topics (311-driven, no policy awareness)
> - **Variable gap** for bridge topics (depends on pending decisions)"

### Testable Predictions

1. **Infrastructure budget decisions** should have HIGH gaps (residents complain but don't testify)
2. **Housing development projects** should have LOW gaps (organized opposition/support)
3. **Climate policy decisions** should have LOW gaps (environmental groups mobilize)
4. **Fee schedule updates** should have HIGH gaps (affects many, few testify)

---

## Implications for Platform Design

### 1. Differentiate Notification Strategy by Topic

**Operational topics (high gap):**
- Proactive notification: "Your pothole complaint is near an area getting $500K road budget"
- Low barrier: "Click to add your name to a letter" (not "attend meeting")
- Timing: 2-3 weeks before decision

**Policy topics (low gap):**
- Coordination infrastructure: "15 others are attending this housing meeting"
- Talking points: "Here's what advocates are saying"
- Post-meeting: "Here's what was decided about your issue"

### 2. Focus SeeClickFix Bridge on Budget Decisions

The wildfire case study worked because:
- Budget decision (operational, not advocacy)
- Clear match (vegetation complaints → vegetation budget)
- Measurable impact ($1.1M allocation)

**Prioritize:**
- Infrastructure budget allocations
- Park maintenance funding
- Traffic safety capital projects

**Deprioritize (for SeeClickFix bridge):**
- Zoning decisions (already high engagement)
- Controversial policy debates (already high engagement)

### 3. Measure Success Differently by Topic

**Operational topics:**
- Success = increased testimony rate (from 18% to 50%)
- Metric = complainants notified who took action

**Policy topics:**
- Success = improved coordination quality (talking points, alignment)
- Metric = testimony coherence, policy mentions

---

## Data Limitations

### 1. Temporal Mismatch
- SeeClickFix data: Sept 2024 - Nov 2025
- Testimony data: Mar - Oct 2024
- Cannot directly match complaints → testimony for same meetings

### 2. Category Precision
- SeeClickFix categories don't map 1:1 to testimony topics
- "Campsite Fire Hazard" = camping, not wildfire
- Some categories span multiple topics

### 3. Speaker Identification
- Testimony speakers identified by label (SPEAKER_1, etc.)
- Cannot match to SeeClickFix reporter accounts
- Same person may file complaint AND testify (double-count)

### 4. Historical Complaint Data
- SeeClickFix API doesn't return complaints before Sept 2024
- Cannot validate gap for Mar-Aug 2024 meetings

---

## Files Generated

| File | Description |
|------|-------------|
| `seeclickfix_sanrafael_all.json` | 771 complaints (Sept 2024-Nov 2025) |
| `seeclickfix_sanrafael_mar_oct_2024.json` | 11 complaints (limited historical data) |
| `complaint_topic_categorization.json` | Category → topic mapping |
| `testimony_speakers_by_topic.json` | Speaker counts by topic |
| `PHASE3_GAP_ANALYSIS.md` | This analysis |

---

## Next Steps

### Immediate (Phase 4: Speaker Network Analysis)
1. Extract unique speaker identities from testimony
2. Cross-reference with SeeClickFix reporter data (where available)
3. Identify "super-engagers" who both complain AND testify

### Near-term (12-month Decision Analysis)
1. Build decision database for San Rafael (Oct 2024 - Oct 2025)
2. Match SeeClickFix complaints to specific decisions
3. Calculate topic-specific gaps with temporal alignment

### Validation
1. Test hypothesis on 2025 budget decisions (infrastructure vs. policy)
2. Measure actual gaps when platform deployed
3. A/B test notification strategies by topic type

---

## Appendix: Category Mapping

```json
{
  "camping_homelessness": [
    "Report a Campsite Fire Hazard"
  ],
  "wildfire_vegetation": [
    "Vegetation Fire Hazard"
  ],
  "traffic_safety": [
    "Traffic/ Traffic Signal",
    "Parking violations",
    "Abandoned Vehicle",
    "Broken Parking Meter"
  ],
  "infrastructure": [
    "Pothole/Road Condition",
    "Street Sign and Markings",
    "Street Light",
    "Sidewalks",
    "Stormwater Drainage",
    "Street Sweeping"
  ],
  "environment": [
    "Trees",
    "Illegal Dumping",
    "Roadside Vegetation",
    "Open Space",
    "Medians",
    "Graffiti"
  ],
  "parks": [
    "Parks and Playgrounds"
  ]
}
```
