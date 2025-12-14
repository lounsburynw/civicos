# Phase 4: Speaker Network Analysis

**Date**: 2024-11-24
**Dataset**: 78 speaker labels across 9 San Rafael meetings (Mar-Oct 2024)
**Finding**: Diarization fragments speakers - cannot reliably count unique public participants

---

## Executive Summary

### Critical Data Quality Finding

**Speaker diarization is imperfect**: Single individuals are split across multiple speaker labels.

**Example**: At April 15, 2024 (28-32 min mark):
- "Rich Storek" appears as BOTH Speaker D and Speaker I
- His continuous testimony alternates between labels
- Diarization failed to recognize same voice

**Implication**: The 78 speaker labels do NOT represent 78 unique individuals.

### What We CAN Measure

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Total speaker labels | 78 | Upper bound on speakers |
| Council/staff (>10 min) | 50 (64%) | Reliable - consistent voices |
| Public commenters (<5 min) | 15 (19%) | UNDER-counted - fragmented |
| Presentations (5-10 min) | 13 (17%) | Staff presentations |

### What We CANNOT Measure

- Exact number of unique public commenters
- Same person appearing at multiple meetings
- Speaker network / relationships

---

## Speaker Distribution by Duration

### Classification Method
- **Public (<5 min)**: Brief testimony, likely subject to 3-min limit
- **Council/Staff (>10 min)**: Extended speaking throughout meeting
- **Presentations (5-10 min)**: Staff reports, invited speakers

### Results

| Role | Speakers | % | Total Utterances | Avg Duration |
|------|----------|---|------------------|--------------|
| Council/Staff | 50 | 64% | 3,163 | 23.2 min |
| Presentations | 13 | 17% | 249 | 6.6 min |
| Public | 15 | 19% | 151 | 2.1 min |

**Key insight**: 88% of utterances come from council/staff, only 4% from public commenters.

---

## High-Engagement Meeting Analysis

### April 15, 2024 (Camping Ordinance)
- 714 utterances, 233 minutes
- 10 speaker labels
- ALL speakers >10 min duration
- Public comments embedded within council discussion

### August 19, 2024 (Camping + Housing)
- 679 utterances, 228 minutes
- 8 speaker labels
- ALL speakers >10 min duration
- Same pattern as April 15

**Observation**: During controversial topics, the meeting structure changes:
- Council deliberation expands significantly
- Public comment periods still ~3 min per person
- But overall meeting dominated by council discussion

---

## Speaker Role Identification

### Confirmed Roles (from utterance content)

| Speaker | Meeting | Role Evidence |
|---------|---------|---------------|
| A (various) | Most meetings | "Welcome everybody to the regular meeting..." = Mayor |
| B (Apr 15) | 2024-04-15 | "Tonight's meeting is being recorded..." = Council/Staff |
| D+I (Apr 15) | 2024-04-15 | "I am Rich Storek" = Public (fragmented) |
| G (Apr 15) | 2024-04-15 | "One second, please" (interpreting) = Interpreter |

### Role Distribution Pattern

Per meeting:
- **2-3 labels**: Council members (Mayor, Vice Mayor, 1-2 others)
- **2-3 labels**: City staff (City Manager, Department heads)
- **1-2 labels**: Interpreters (Spanish)
- **2-5 labels**: Public commenters (fragmented)

---

## Diarization Fragmentation Evidence

### Case Study: Rich Storek Testimony (April 15, 28-32 min)

```
[29.0] Speaker D: The council and city staff. I am Rich Storek.
[29.0] Speaker I: I'm here representing the Canal Arts nonprofit.
[29.0] Speaker D: But I'm also here on behalf of.
[29.0] Speaker I: The arts in San Rafael...
[30.0] Speaker D: About three years ago...
[30.0] Speaker I: In San Rafael, what could be done...
```

**Pattern**: D and I alternate within the SAME sentence.

**Cause**: Diarization algorithm misidentified speaker boundaries.

**Impact**: One public speaker counted as two speaker labels.

---

## Public Comment Time Analysis

### Meeting Structure (typical)

1. **Call to Order** (0-5 min)
2. **Proclamations/Presentations** (5-30 min)
3. **Public Comment - General** (varies)
4. **Consent Calendar** (brief)
5. **Agenda Items** (with per-item public comment)
6. **Council Deliberation** (extended during controversial items)

### Public Comment Duration by Meeting

| Meeting | Total Duration | Est. Public Comment Time | % Public |
|---------|---------------|-------------------------|----------|
| Mar 18 | 59 min | ~10 min | 17% |
| Apr 15 | 233 min | ~30 min | 13% |
| May 6 | 110 min | ~15 min | 14% |
| Jun 3 | 211 min | ~20 min | 9% |
| Jun 17 | 102 min | ~10 min | 10% |
| Jul 15 | 155 min | ~15 min | 10% |
| Aug 19 | 228 min | ~25 min | 11% |
| Sep 16 | 172 min | ~15 min | 9% |
| Oct 7 | 6 min | ~2 min | 33% |

**Observation**: Even on high-engagement topics, public comment is ~10-15% of meeting time. Council deliberation dominates.

---

## Implications for Platform Design

### 1. Can't Track Individual Engagement
- Cannot identify repeat public commenters
- Cannot build "civic engagement profiles" from testimony data
- Would need name extraction + fuzzy matching

### 2. Focus on Complaint → Decision, Not Speaker Networks
- SeeClickFix has reliable individual IDs (reporter accounts)
- Council meetings don't (diarization is fragmented)
- Bridge should go: Complaint → Notification → Testimony (not speaker tracking)

### 3. Public Comment is Small % of Meeting
- 10-15% of meeting time is public comment
- 88% of utterances are council/staff
- Platform value: Help public's small window be more impactful

---

## Data Quality Recommendations

### For Future Testimony Extraction

1. **Name extraction**: Parse "My name is X" patterns from transcript
2. **Speaker merging**: Use LLM to identify fragmented speakers
3. **Role tagging**: Mark council, staff, interpreter, public labels
4. **Time alignment**: Map speakers to agenda items

### For Gap Analysis

1. **Use SeeClickFix IDs** as primary individual identifier
2. **Don't rely on diarization** for unique speaker counts
3. **Cross-reference minutes** for official speaker lists (if available)

---

## Files Generated

| File | Description |
|------|-------------|
| `PHASE4_SPEAKER_ANALYSIS.md` | This analysis |

---

## Next Steps: Phase 5

**Longitudinal Complaint Trends**
- How do SeeClickFix complaints change over time?
- Seasonality patterns?
- Complaint → resolution time?

OR

**Apply Findings**
- Design notification intervention for traffic complainants
- Mockup user experience for "decision awareness"
