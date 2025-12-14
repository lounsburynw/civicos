# Phase 1: Topic Discovery from 3,563 Utterances

**Date**: 2024-11-24
**Dataset**: 9 San Rafael City Council meetings (March-October 2024)
**Method**: Keyword frequency analysis + meeting-level topic extraction

---

## Executive Summary

### Key Finding: Homelessness/Camping is NOT the Dominant Topic

Contrary to Phase 2 agenda analysis which suggested homelessness dominated, **keyword frequency reveals a more diverse topic distribution**:

| Topic Area | Keyword Mentions | % of Policy Keywords |
|------------|------------------|---------------------|
| **Budget/Finance** | 569 (budget+fund+funding+fiscal+million) | 29% |
| **Camping/Homelessness** | 378 (camping+homeless+homelessness+unhoused+encampment) | 20% |
| **Housing** | 296 (housing+affordable+rent+tenant+property) | 15% |
| **Ordinance/Policy** | 290 (ordinance) | 15% |
| **Climate/Environment** | 123 (climate+emissions) | 6% |
| **Safety** | 233 (safety+police) | 12% |

**Wildfire mentions**: 17 total (0.9% of policy keywords) - confirms wildfire is NOT in this dataset

---

## Methodology

### 1. Data Extraction
- 3,563 utterances exported from testimony database
- Speakers: Mix of council members, staff, and public commenters
- Temporal range: March 18 - October 7, 2024

### 2. Keyword Frequency Analysis
- Extracted all 4+ letter words from utterances
- Filtered common stopwords + meeting procedural terms
- 112,383 total words, 8,011 unique words analyzed

### 3. Meeting-Level Topic Signatures
- Top 20 keywords extracted per meeting
- Topics inferred from keyword clusters

---

## Meeting-by-Meeting Analysis

### March 18, 2024 (214 utterances)
**Topic**: Objective Design Standards

| Keyword | Count |
|---------|-------|
| standards | 50 |
| design | 34 |
| development | 25 |
| planning | 23 |

**Interpretation**: Joint Planning Commission + Council meeting on housing development design standards. Technical/regulatory discussion, not high public engagement.

---

### April 15, 2024 (714 utterances) - HIGHEST ENGAGEMENT
**Topic**: Camping Ordinance + Tenant Protections + Canal Neighborhood

| Keyword | Count |
|---------|-------|
| ordinance | 169 |
| housing | 90 |
| canal | 75 |
| tenant | 54 |
| property | 53 |
| zone | 50 |

**Interpretation**: Major policy debate with three intersecting issues:
1. Camping/homelessness ordinance (most controversial)
2. Tenant protection policies
3. Canal neighborhood concerns (where encampments are located)

This single meeting represents **20% of all utterances** - extremely high engagement.

---

### May 6, 2024 (230 utterances)
**Topic**: Mental Health Services

| Keyword | Count |
|---------|-------|
| health | 37 |
| mental | 29 |
| funding | 31 |
| county | 47 |

**Interpretation**: Discussion of mental health services, likely county-level coordination. Moderate engagement.

---

### June 3, 2024 (515 utterances) - HIGH ENGAGEMENT
**Topic**: City Budget Presentation

| Keyword | Count |
|---------|-------|
| budget | 107 |
| fund | 78 |
| projects | 65 |
| million | 59 |
| equipment | 63 |
| funding | 53 |

**Interpretation**: Annual budget presentation with detailed discussion of capital projects and equipment purchases. High engagement driven by staff presentations + council questions.

---

### June 17, 2024 (228 utterances)
**Topic**: Budget Adoption + Policies

| Keyword | Count |
|---------|-------|
| budget | 48 |
| policy | 33 |
| ordinance | 33 |
| resolution | 31 |

**Interpretation**: Final budget adoption with associated policy resolutions. Moderate engagement.

---

### July 15, 2024 (494 utterances) - HIGH ENGAGEMENT
**Topic**: Bike Safety + Employee Matters

| Keyword | Count |
|---------|-------|
| bike | 43 |
| bikes | 41 |
| employees | 40 |
| safety | 33 |
| county | 80 |

**Interpretation**: Two major topics:
1. E-bike/bike safety regulations
2. Employee-related matters (possibly union/labor)

This may be a discovery - bike safety wasn't prominently featured in agenda analysis.

---

### August 19, 2024 (679 utterances) - SECOND HIGHEST ENGAGEMENT
**Topic**: Camping Ordinance Implementation + Housing Programs

| Keyword | Count |
|---------|-------|
| camping | 89 |
| program | 82 |
| housing | 61 |
| ordinance | 53 |
| individuals | 49 |
| area | 68 |

**Interpretation**: Follow-up to April 15 camping ordinance discussion. Focus on:
1. Implementation of camping regulations
2. Housing/shelter programs for affected individuals
3. Specific geographic areas affected

Combined with April 15, camping/homelessness topic generated **1,393 utterances** (39% of total).

---

### September 16, 2024 (406 utterances)
**Topic**: Climate Action / GHG Emissions

| Keyword | Count |
|---------|-------|
| emissions | 61 |
| fees | 53 |
| climate | 49 |
| level | 40 |

**Interpretation**: Climate action plan discussion with focus on:
1. Greenhouse gas emissions targets
2. Fee structures (possibly carbon fees or related)

Moderate-high engagement on environmental policy.

---

### October 7, 2024 (83 utterances) - LOWEST ENGAGEMENT
**Topic**: Planning Commission Interviews

| Keyword | Count |
|---------|-------|
| interviews | 8 |
| commission | 7 |
| planning | 6 |
| applicants | 5 |

**Interpretation**: Special meeting for interviewing Planning Commission applicants. Administrative, not policy-focused. Confirms Phase 2 finding.

---

## Key Questions Answered

### 1. Is homelessness the dominant topic?
**Partially confirmed, but not as dominant as Phase 2 suggested**

- Camping/homelessness: 378 keyword mentions (20% of policy keywords)
- April 15 + Aug 19 meetings generated 1,393 utterances (39% of total)
- BUT budget/finance keywords (569) actually exceed camping keywords

**Nuance**: Camping dominates in *public controversy* and *speaker count*, but budget discussions generate significant council/staff dialogue.

### 2. Is wildfire mentioned?
**Confirmed ABSENT**

- "fire": 103 mentions (likely "fire department" or general)
- "wildfire": 17 mentions (<1%)
- "trees/brush/vegetation/hazard": minimal (9, 1, 2, 11)

This dataset does NOT contain the Oct 6 Wildfire Fund discussion - that's a separate meeting or the topic wasn't discussed in testimony.

### 3. What topics did we miss in agenda analysis?
**Discovery: Bike safety emerged as a significant topic**

July 15 meeting had 84 bike-related keyword mentions (bike+bikes), suggesting substantial discussion of e-bike regulations or bike safety that wasn't prominently featured in Phase 2.

### 4. Do testimonies match agendas?
**Generally yes**, keyword signatures align with expected agenda topics:
- Budget meetings → budget keywords dominate
- Camping ordinance meetings → camping/housing keywords dominate
- Climate meeting → emissions/climate keywords dominate

No evidence of major divergence between agenda items and testimony content.

### 5. Which meetings need Phase 3 deep dive?
**Priority for complaint-policy gap analysis:**

1. **April 15 + August 19**: Camping ordinance (combined 1,393 utterances)
   - Test: Do SeeClickFix complaints about encampments correlate with testimony?

2. **September 16**: Climate/emissions (406 utterances)
   - Test: Are there climate-related complaints in SeeClickFix?

3. **July 15**: Bike safety (494 utterances)
   - Test: Do bike safety complaints exist in SeeClickFix data?

---

## Data Outputs

| File | Description |
|------|-------------|
| `all_utterances_march_oct_2024.csv` | Full utterance export (3,563 rows) |
| `keyword_frequency_top100.json` | Global keyword frequency |
| `meeting_topic_distribution.json` | Per-meeting keyword breakdown |

---

## Next Steps: Phase 3 Preparation

1. **Pull SeeClickFix complaints** for San Rafael (March-Oct 2024)
2. **Categorize by discovered topics**:
   - Camping/encampment complaints
   - Bike/traffic safety complaints
   - Climate/environmental complaints
   - Infrastructure complaints
3. **Calculate topic-specific gaps**:
   - How many camping complaints vs camping testimony participants?
   - How many bike safety complaints vs July 15 participants?
4. **Test hypothesis**: Is the 86% gap universal or topic-specific?

---

## Appendix: Specific Topic Keyword Counts

### Homelessness Cluster
| Keyword | Count |
|---------|-------|
| homeless | 70 |
| homelessness | 82 |
| unhoused | 36 |
| encampment | 49 |
| camping | 141 |
| **TOTAL** | **378** |

### Fire/Wildfire Cluster
| Keyword | Count |
|---------|-------|
| fire | 103 |
| wildfire | 17 |
| trees | 9 |
| vegetation | 2 |
| brush | 1 |
| hazard | 11 |
| smoke | 1 |
| **TOTAL** | **144** |

Note: "fire" likely refers to fire department, not wildfire risk.

### Climate Cluster
| Keyword | Count |
|---------|-------|
| climate | 60 |
| emissions | 63 |
| **TOTAL** | **123** |

### Housing Cluster
| Keyword | Count |
|---------|-------|
| housing | 203 |
| affordable | 32 |
| rent | 51 |
| tenant | 54* |
| property | 159* |
| development | 110 |
| **TOTAL (core)** | **286** |

*tenant/property may overlap with camping ordinance context

### Budget Cluster
| Keyword | Count |
|---------|-------|
| budget | 187 |
| fund | 152 |
| funding | 132 |
| fiscal | 98 |
| million | 113 |
| **TOTAL** | **682** |

### Safety Cluster
| Keyword | Count |
|---------|-------|
| police | 107 |
| safety | 126 |
| crime | 7 |
| **TOTAL** | **240** |
