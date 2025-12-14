# PDF Extraction Assessment & Improvement Plan

**Date**: 2025-11-13 (Session 98)
**Focus**: Oct 6 Meeting Analysis + Data Structure Review

---

## Executive Summary

**Current Status**: Pipeline works but extracts wrong PDFs
- ✅ Found 5 high-stakes decisions from 33 meetings
- ❌ Missing Oct 6 wildfire case ($1.1M) - our validation case!
- ❌ Expected 15-30 decisions, only found 5

**Root Cause**: Scraper grabs **first PDF** instead of **full agenda packet**

**Solution**: Multi-document extraction strategy (agenda packet + minutes + staff reports)

---

## Oct 6 Meeting Structure Analysis

### Available Documents:

**Agenda Packet Tab** (`#tab-agenda-packet`):
```
📦 Full Agenda Packet
URL: https://storage.googleapis.com/proudcity/sanrafaelca/2025/10/Agenda-Packet-2025-10-06.pdf
Contains: Complete agenda with ALL items
```

**Minutes Tab** (`#tab-minutes`):
```
📋 Approved Minutes
URL: https://storage.googleapis.com/proudcity/sanrafaelca/2025/10/db640875-cc-minutes-2025-10-06.pdf
Contains:
  - Vote results
  - Speaker names
  - Testimony count (e.g., "4 speakers on item 5.g")
  - Motion details
  - Public comment summary
```

**Individual Agenda Items** (`#tab-agenda`):
```
20 individual PDFs including:
  • 5.g - Measure C Wildfire Prevention Fund ($1.1M) ← Our case study!
  • 5.b - Dominican Development project
  • 7.a - Albert Park Library
  • 7.b - Wildfire Prevention Report (2019-2025)
  ... 16 more items
```

### What We Currently Extract:
```
❌ "SM-1.a-Boards-Commissions-and-Committees-Interviews.pdf"
   (First PDF found, special meeting item, NOT the main agenda)
```

### What We Should Extract:
```
✅ Agenda Packet (2025-10-06.pdf) - Primary source for decisions
✅ Minutes (cc-minutes-2025-10-06.pdf) - Testimony counts, votes
✅ Key Staff Reports (optional, for depth)
```

---

## Current Data Structure Review

### HighStakesDecision Fields:

**✅ Sufficient for SeeClickFix Matching:**
```json
{
  "meeting_date": "2025-10-06T18:00:00",        // For 30-day lookback
  "keywords_for_matching": [                    // For keyword filtering
    "fire", "wildfire", "tree", "vegetation"
  ],
  "decision_type": "budget",                    // Topical filtering
  "geographic_scope": "citywide",               // Location filtering
  "budget_amount": 1108319,                     // Scale indicator
  "project_types": ["environment", "budget"]    // Multi-tag
}
```

**⚠️ Missing for Coordination Gap Analysis:**
```json
{
  "testimony_count": null,          // ❌ Need from minutes!
  "speaker_names": null,            // ❌ For deduplication
  "vote_results": null,             // ❌ For decision outcome
  "staff_report_urls": [],          // ❌ For deep dives
  "minutes_url": null,              // ❌ For verification
  "full_agenda_packet_url": null    // ❌ For source tracing
}
```

**🔮 Valuable for Future App Features:**
```json
{
  "speaker_names": [...],           // Coalition building
  "testimony_excerpts": [...],      // Quote mining
  "vote_breakdown": {               // Council member tracking
    "yes": 4, "no": 0, "abstain": 0
  },
  "related_items": [...],           // Policy chains
  "prior_discussion_dates": [...],  // Multi-meeting tracking
  "implementation_timeline": null   // Follow-up tracking
}
```

---

## Cross-Reference Robustness Assessment

### For SeeClickFix Complaint Matching:

**Current Capability** (5/5 stars ⭐⭐⭐⭐⭐):
```python
# Works perfectly for:
decision_date = "2025-10-06"
lookback_window = decision_date - timedelta(days=30)  # Sep 6 - Oct 6
keywords = ["fire", "wildfire", "tree", "vegetation", "hazard"]

# Can filter complaints by:
✅ Date range (30-day window)
✅ Keywords (multi-term OR logic)
✅ Decision type (budget/environmental/etc)
✅ Geographic scope (citywide vs neighborhood)
```

**Example Match**:
```
Decision: Measure C Wildfire Fund ($1.1M)
  Date: Oct 6, 2025
  Keywords: ["fire", "wildfire", "tree", "vegetation"]

SeeClickFix Complaint: "Tree limb hanging over house"
  Date: Sep 15, 2025 (21 days before decision)
  Text: "Large tree branch overhanging my roof, fire hazard"
  ✅ MATCHED: Contains "tree" + "fire" + within 30 days
```

### For Coordination Gap Calculation:

**Current Capability** (2/5 stars ⭐⭐☆☆☆):
```python
# Have:
complaints_count = 22  # From SeeClickFix
decision_date = "2025-10-06"
keywords = [...]

# Missing:
testimony_count = ???  # ❌ Need from minutes!
gap = complaints_count - testimony_count  # Can't calculate!
```

**What Minutes Provide**:
```
From Oct 6 minutes PDF:
"Item 5.g: Measure C Wildfire Prevention Fund
 - Staff presentation by Fire Chief
 - Public comment: 4 speakers
   * Speaker 1: John Smith, Lincoln Hill resident
   * Speaker 2: Jane Doe, concern about defensible space
   * Speaker 3: ...
   * Speaker 4: ...
 - Motion by Councilmember X, seconded by Y
 - Vote: 4-0 (unanimous approval)"

Extract:
✅ testimony_count = 4
✅ speaker_names = ["John Smith", "Jane Doe", ...]
✅ vote_results = {"yes": 4, "no": 0}
```

**Enables Gap Calculation**:
```python
complaints_count = 22
testimony_count = 4
gap = 22 - 4 = 18 residents (82% coordination gap)
```

---

## Alternative/Tangential Use Cases

### 1. Coalition Building (Future App Feature)
**Data Needed**: Speaker names from minutes
```
"Who else cares about wildfire issues?"
→ Show: John Smith, Jane Doe testified on Oct 6
→ Connect: Similar concerns, potential coalition members
```

### 2. Council Member Tracking
**Data Needed**: Vote breakdowns
```
"Which council members support environmental issues?"
→ Analysis: Councilmember X voted yes on 8/10 environmental items
→ Target: Effective advocacy paths
```

### 3. Policy Chain Tracking
**Data Needed**: Related agenda items, follow-up mentions
```
"What happened after the Oct 6 wildfire decision?"
→ Track: Budget allocation → Implementation → Progress reports
→ Link: Multi-meeting narrative
```

### 4. Staff Report Deep Dives
**Data Needed**: Individual staff report URLs
```
"Why did they allocate $734K to defensible space?"
→ Source: Staff Report 5.g, page 2, justification section
→ Quote: "$200K grants already issued to 102 residents"
```

### 5. Quote Mining for Social Media
**Data Needed**: Testimony excerpts from minutes
```
"Powerful resident testimony on wildfire risks"
→ Quote: "My family evacuated twice last year..." - Jane Doe
→ Share: Humanize the data, drive engagement
```

### 6. Precedent Research
**Data Needed**: Historical similar decisions
```
"Have they funded wildfire before?"
→ Find: 3 prior Measure C allocations (2019, 2021, 2023)
→ Pattern: Increasing budgets, consistent September timing
```

---

## Proposed Data Model Enhancements

### Enhanced HighStakesDecision Schema:

```python
@dataclass
class HighStakesDecision:
    # ========================================
    # CURRENT FIELDS (keep as-is)
    # ========================================
    item_ref: str
    title: str
    description: str
    meeting_date: str
    meeting_type: str
    is_high_stakes: bool
    stakes_score: int
    decision_type: str
    budget_amount: Optional[float]
    budget_description: str
    affected_population_estimate: Optional[int]
    geographic_scope: str
    project_size_units: Optional[int]
    project_location: Optional[str]
    project_types: List[str]
    keywords_for_matching: List[str]
    participation_mechanisms: List[Dict]
    agenda_url: Optional[str]
    staff_report_url: Optional[str]

    # ========================================
    # NEW FIELDS (add for enhanced analysis)
    # ========================================

    # Source document tracking
    full_agenda_packet_url: Optional[str]     # Full packet PDF
    minutes_url: Optional[str]                # Minutes PDF
    staff_report_urls: List[str]              # All related reports

    # Testimony & participation
    testimony_count: Optional[int]            # From minutes
    speaker_names: List[str]                  # From minutes
    testimony_excerpts: List[Dict]            # {speaker, quote, timestamp}

    # Vote & outcome
    vote_results: Optional[Dict]              # {yes: N, no: N, abstain: N}
    vote_breakdown: List[Dict]                # [{member: "X", vote: "yes"}, ...]
    passed: bool                              # True if approved

    # Relationships
    related_items: List[str]                  # Other agenda items
    prior_discussion_dates: List[str]         # Previous meetings
    follow_up_items: List[str]                # Future agenda items

    # Implementation tracking
    implementation_timeline: Optional[str]    # When effective
    responsible_department: Optional[str]     # Who implements
    progress_report_dates: List[str]          # Future checkpoints
```

---

## Improved PDF Extraction Strategy

### Strategy: Multi-Document Extraction

**Phase 1: Agenda Packet (Primary)**
```python
# Target: #tab-agenda-packet
# Priority: PDFs with "Agenda-Packet" or "Full" in filename
# Fallback: Largest PDF in tab

url = meeting_url + "#tab-agenda-packet"
pdf_url = find_pdf_by_priority([
    "agenda-packet",
    "full-packet",
    "complete-agenda"
])

# Extract ALL agenda items from packet
decisions = extract_high_stakes_from_pdf(pdf_url)
```

**Phase 2: Minutes (Supplement)**
```python
# Target: #tab-minutes
# Extract: testimony_count, speaker_names, vote_results

url = meeting_url + "#tab-minutes"
minutes_pdf = find_pdf_with("minutes")

# Parse structured data
for decision in decisions:
    item_ref = decision.item_ref  # e.g., "5.g"

    # Find in minutes
    testimony_data = extract_testimony_for_item(
        minutes_pdf,
        item_ref
    )

    decision.testimony_count = testimony_data['count']
    decision.speaker_names = testimony_data['speakers']
    decision.vote_results = testimony_data['vote']
```

**Phase 3: Individual Staff Reports (Optional)**
```python
# Target: #tab-agenda individual items
# For deep dives on top decisions

for decision in top_10_decisions:
    # Find matching staff report
    staff_report_url = find_pdf_for_item(
        meeting_url + "#tab-agenda",
        decision.item_ref
    )

    if staff_report_url:
        decision.staff_report_urls.append(staff_report_url)
```

---

## Implementation Priorities

### Immediate (Session 98 Completion):

1. **Fix Agenda Packet Selection** ⭐⭐⭐⭐⭐
   - Modify scraper to target `#tab-agenda-packet`
   - Prioritize "Agenda-Packet-YYYY-MM-DD.pdf"
   - Re-run Oct 6 to validate wildfire case found

2. **Add Minutes Extraction** ⭐⭐⭐⭐☆
   - Extract testimony counts for gap calculation
   - Basic speaker name parsing
   - Vote results (yes/no/abstain)

3. **Enhance Data Model** ⭐⭐⭐☆☆
   - Add `full_agenda_packet_url`
   - Add `minutes_url`
   - Add `testimony_count`
   - Add `vote_results`

### Short-Term (Session 99-100):

4. **Speaker Name Extraction** ⭐⭐⭐☆☆
   - Parse "Speaker 1: John Smith" patterns
   - Deduplicate across meetings
   - Build speaker database

5. **Staff Report Links** ⭐⭐☆☆☆
   - Capture individual item PDFs
   - Store for deep dive analysis

### Long-Term (Multi-City Validation):

6. **Vote Breakdown** ⭐⭐☆☆☆
   - Parse council member names
   - Track voting patterns

7. **Policy Chain Tracking** ⭐☆☆☆☆
   - Link related items across meetings
   - Build decision timelines

---

## Success Metrics

### Phase 1 (Immediate):
- ✅ Find Oct 6 wildfire decision ($1.1M)
- ✅ Extract 15-30 decisions from 33 meetings (vs current 5)
- ✅ Testimony counts for ≥10 decisions

### Phase 2 (Short-term):
- ✅ 80%+ of decisions have testimony counts
- ✅ Speaker names for top 10 decisions
- ✅ Vote results for all decisions

### Phase 3 (Long-term):
- ✅ Complete speaker database
- ✅ Policy chains identified
- ✅ Multi-meeting narratives

---

## Next Steps

1. **Update scraper** to extract from multiple tabs:
   - `#tab-agenda-packet` → full agenda
   - `#tab-minutes` → testimony data
   - `#tab-agenda` → staff reports (optional)

2. **Update HighStakesDecision** dataclass with new fields

3. **Create minutes parser** for testimony/vote extraction

4. **Re-run analysis** on Oct 6 to validate

5. **Run full 33-meeting analysis** with improved extraction

---

**Status**: Ready to implement
**Estimated Time**: 2-3 hours
**Expected Outcome**: 15-30 decisions with testimony counts
