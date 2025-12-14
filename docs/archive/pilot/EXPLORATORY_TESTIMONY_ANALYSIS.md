# Exploratory Testimony Analysis: Ground-Up Approach

**Created**: 2024-11-24
**Status**: In Progress
**Goal**: Discover citizen engagement patterns without inductive bias

---

## Motivation

**Problem**: The Oct 6 wildfire case study (86% participation gap) is compelling, but we risk confirmation bias by building our entire strategy around one finding.

**Question**: Is the wildfire gap:
- **Representative** - all topics show similar gaps?
- **An outlier** - wildfire had an especially bad gap?
- **One story among many** - other insights are equally/more valuable?

**Approach**: Analyze the full dataset (9 meetings, 78 speakers, 3,563 utterances) inductively to discover patterns before drawing conclusions.

---

## Dataset Overview

**Source**: San Rafael City Council testimony extraction (Session 112)
- **Meetings**: 9 (March 18 - October 7, 2024)
- **Speakers**: 78 total, 10 unique identified names
- **Utterances**: 3,563 with full-text search capability
- **Processing cost**: $27 ($3/meeting)
- **Database**: `data/civic_participation.db`

**Quality metrics**:
- Speaker count accuracy: 100%
- Extraction success rate: 100% (9 of 9 meetings)
- Identification rate: 13% (10 of 78 speakers named)

---

## Analysis Phases

### Phase 1: Topic Discovery (Bottom-Up)
**Status**: Pending
**Time estimate**: 1 hour
**Goal**: Discover what people actually testify about, without preconceptions

**Method**:
1. Extract all 3,563 utterances to CSV
2. LLM-based topic clustering (no predefined categories)
3. Keyword frequency analysis
4. Identify which topics drove high vs low engagement meetings

**Key questions**:
- What are the top 5-10 themes across 7 months?
- Is wildfire even prominent in the data?
- What topics correlate with high-engagement meetings?

**Output**: Topic taxonomy with meeting-level distribution

---

### Phase 2: Meeting Anatomy
**Status**: Pending
**Time estimate**: 30 minutes
**Goal**: Understand what drives participation variance

**High engagement** (identify what made these active):
- Aug 19, 2024: 679 utterances, 8 speakers (84.9 avg/speaker)
- April 15, 2024: 714 utterances, 10 speakers (71.4 avg/speaker)

**Low engagement** (identify why participation was minimal):
- Oct 7, 2024: 83 utterances, 5 speakers (16.6 avg/speaker)
- March 18, 2024: 214 utterances, 10 speakers (21.4 avg/speaker)

**Method**:
1. Retrieve actual meeting agendas for all 9 meetings
2. Identify high-stakes decisions (budgets, zoning, policy changes)
3. Compare agenda items to participation levels
4. Test hypothesis: High-stakes decisions → more testimony

**Key questions**:
- Were high-engagement meetings about consequential decisions?
- Were low-engagement meetings routine/ceremonial?
- Can we predict participation based on agenda content?

**Output**: Meeting-by-meeting agenda summary with participation correlation

---

### Phase 3: Systematic Complaint-Policy Gap Analysis
**Status**: Pending
**Time estimate**: 2 hours
**Goal**: Test if 86% gap is universal or topic-specific

**Current limitation**: Only analyzed wildfire complaints for Oct 6

**Broader method**:
1. Pull ALL SeeClickFix complaints for March-October 2024 (all categories)
2. Categorize by topic (infrastructure, housing, trees, parks, public safety, etc.)
3. Extract agenda items for all 9 meetings (from Phase 2)
4. Match complaints → agenda topics across all months
5. Calculate participation gap for EACH topic separately

**Key questions**:
- Is 86% the norm across all topics?
- Do some topics have worse gaps (e.g., 95% for housing)?
- Do some topics have better engagement (e.g., 50% for development projects)?
- Are environmental issues systematically worse than others?

**Output**: Topic-by-topic gap analysis table

| Topic | Complaint Count | Testimony Count | Gap % | Notes |
|-------|----------------|-----------------|-------|-------|
| Wildfire | 22 | 3 | 86% | Oct 6 case study |
| Housing | TBD | TBD | TBD | |
| Infrastructure | TBD | TBD | TBD | |
| Parks | TBD | TBD | TBD | |

---

### Phase 4: Speaker Network Analysis
**Status**: Pending
**Time estimate**: 30 minutes
**Goal**: Understand who participates and why

**Method**:
```sql
-- Find repeat participants
SELECT
  name,
  COUNT(DISTINCT meeting_id) as meetings_attended,
  SUM(utterance_count) as total_utterances
FROM testimony_speakers
WHERE name NOT LIKE 'Unknown%'
GROUP BY name
ORDER BY meetings_attended DESC;
```

**Key questions**:
- Who are the "regulars" (testified at 3+ meetings)?
- Who are one-time participants (single-issue testifiers)?
- Are regulars organized advocates or affected residents?
- Do different topics bring out different speakers?

**Output**:
- Speaker participation matrix (who attended which meetings)
- Participant typology (regulars vs one-timers, advocates vs residents)

---

### Phase 5: Longitudinal Complaint Trends
**Status**: Pending
**Time estimate**: 1 hour
**Goal**: Understand operational engagement trends over 7 months

**Method**:
1. Pull ALL SeeClickFix complaints for March-October 2024
2. Aggregate by month and category
3. Compare complaint volume to testimony participation
4. Test correlation hypotheses

**Key questions**:
- Do months with more complaints → more testimony? (awareness effect)
- Or inverse: More complaints → LESS testimony? (frustration/burnout)
- Are there seasonal patterns in both complaints and testimony?
- Which complaint categories have highest volume?

**Output**:
- Monthly complaint volume by category
- Correlation analysis: complaints vs testimony participation

---

## Expected Outcomes

### Scenario A: Wildfire Was Representative
**Finding**: All topics show 80-90% participation gaps
**Implication**: Universal awareness problem, not topic-specific
**Strategy**: Focus on notification infrastructure for ALL agenda items
**Moat**: Platform becomes essential civic infrastructure (like email for government)

### Scenario B: Wildfire Was an Outlier
**Finding**: Other topics have 40-60% gaps (wildfire especially bad at 86%)
**Implication**: Environmental/safety issues have systematically worse engagement
**Strategy**: Target specific topic categories with proven gaps
**Moat**: Domain expertise in low-engagement policy areas

### Scenario C: Other Topics Dominate
**Finding**: Housing/development dominated 5 of 9 meetings with 95% gaps
**Implication**: Wildfire was a distraction; real opportunity is elsewhere
**Strategy**: Pivot focus to highest-volume/highest-gap topic
**Moat**: Deep integration with highest-impact policy domain

### Scenario D: Gap Hypothesis Is Flawed
**Finding**: Most testimony from organized advocates, not affected residents
**Implication**: Complaint filers don't intend to engage in policy (different user segments)
**Strategy**: Focus on coordination/coalition tools for existing advocates
**Moat**: Network effects from connecting advocates across jurisdictions

---

## Execution Plan

**Recommended order** (least bias, highest insight potential):

1. **Phase 2 first** (30 min) - Ground analysis in concrete meeting agendas
2. **Phase 1 second** (1 hour) - Discover actual topics from utterances
3. **Phase 3 third** (2 hours) - Rigorous gap hypothesis testing
4. **Phase 4 fourth** (30 min) - Speaker patterns and networks
5. **Phase 5 fifth** (1 hour) - Longitudinal context

**Total estimated time**: ~5 hours across multiple sessions

---

## Progress Tracking

**Session 113** (2024-11-24):
- Created exploratory analysis methodology document
- Documented 5-phase approach
- Ready to begin Phase 2 (meeting agendas)

**Next session**: Start Phase 2 - retrieve and analyze actual meeting agendas

---

## Files Generated

**Analysis outputs**:
- `data/pilot/all_utterances_7months.csv` - Full utterance export (Phase 1)
- `data/pilot/meeting_agendas_march_oct_2024.json` - Agenda extraction (Phase 2)
- `data/pilot/topic_gap_analysis.csv` - Systematic gap testing (Phase 3)
- `data/pilot/speaker_network_analysis.json` - Participation patterns (Phase 4)
- `data/pilot/complaint_trends_7months.csv` - Longitudinal complaints (Phase 5)

**Final deliverable**:
- `data/pilot/EXPLORATORY_FINDINGS_REPORT.md` - Comprehensive findings across all phases
