# Panel Critique: Legislation Semantic Search Strategy

**Date:** 2026-01-23
**Context:** Critique of `what_applies()` implementation in `packages/civicos/src/civicos/context.py:109-195`

---

## Executive Summary

The current implementation is **well-designed for its primary use case** but has specific blindspots that affect different user personas. The key finding: **score distributions are extremely compressed** (0.68-0.78 range), making the 0.4 floor irrelevant and gap-based cutoffs ineffective.

**Recommendation:** Keep the current approach with **two surgical changes**:
1. Add bill-first ranking as an option for narrow queries
2. Add tiered response structure for pagination

---

## Empirical Data Gathered

### Score Distribution Analysis

| Query Type | Score Range | Above 0.7 | Above 0.6 | Key Finding |
|------------|-------------|-----------|-----------|-------------|
| Narrow ("SB9 ADU") | 0.68-0.78 | 32/100 | 100/100 | Tight cluster, small gaps |
| Broad ("housing development permits") | 0.72-0.75 | 100/100 | 100/100 | Extremely flat distribution |
| Generic ("housing") | 0.65-0.70 | 1/100 | 99/100 | All results viable |

**Critical Insight:** The 0.4 score floor never triggers. All semantic matches cluster above 0.6, making the floor operationally meaningless.

### Bill Concentration (Chunk-First Bias)

For "housing" query across 100 chunks:
- 14 unique bills represented
- Top 2 bills: 66% of chunks (AB130: 36, SB130: 30)
- Bottom 5 bills: 5% of chunks (1 each)

**Mitigation:** The `CHUNKS_PER_BILL=3` cap effectively normalizes representation. A bill with 36 chunks gets the same final weight as one with 3 chunks.

### Cross-Domain Balance ("housing near transit stations")

| Domain | Bills | % of 26 Results |
|--------|-------|-----------------|
| HOUSING | 16 | 62% |
| TRANSIT | 5 | 19% |
| LAND | 1 | 4% |
| OTHER | 4 | 15% |

**Finding:** Housing dominates despite equal query emphasis on transit. This is acceptable given semantic similarity - housing bills mention transit more than transit bills mention housing.

---

## Persona-by-Persona Critique

### Persona 1: Community Organizer
**Query:** "tenant protections against eviction"

**Results:**
```
1. [0.741] SB522: Housing: tenant protections
2. [0.734] AB924: Leases: termination of tenancy: abuse or violence
3. [0.715] AB311: Dwelling units: persons at risk of homelessness
4. [0.712] AB246: Social Security Tenant Protection Act of 2025
5. [0.695] SB436: Unlawful detainer: notice to terminate tenancy
```

**Verdict: EXCELLENT**
- Highly relevant results ranked correctly
- 14 bills returned is comprehensive but not overwhelming
- Eviction-specific sections surfaced via `relevant_sections`

**No changes needed** for this use case.

---

### Persona 2: City Planner
**Query:** "housing near transit stations"

**Results:**
```
1. [0.654] SB273: Surplus land
2. [0.632] SB79: Housing development: transit-oriented development
3. [0.620] SB130: Housing
...
26 total bills
```

**Issues Identified:**
1. SB79 (explicitly about transit-oriented development) ranks #2, not #1
2. "Surplus land" ranked higher than transit-specific bill
3. HOUSING domain over-represented vs TRANSIT

**Verdict: ACCEPTABLE WITH CAVEAT**
- Results are relevant for a staff report
- Cross-domain query inherently favors the more common domain
- The 26-bill count provides comprehensive coverage

**Minor improvement:** Consider query expansion for cross-domain searches (detect "housing" + "transit" and boost intersection).

---

### Persona 3: Journalist on Deadline
**Query:** "SB9 duplex law"

**Results:**
```
1. [0.674] SB79: Housing development: transit-oriented development
2. [0.673] SB9: Accessory Dwelling Units: ordinances  <-- THE TARGET
3. [0.666] AB130: Housing
4. [0.648] SB130: Housing
...
24 total bills
```

**Critical Issue:** SB9 ranks #2, not #1. The journalist wants THE bill, not 24 tangentially related ones.

**Root Cause:** Section-first ranking. SB79 happens to have a chunk with slightly higher embedding similarity to "SB9 duplex law" than SB9's own chunks.

**Verdict: PROBLEM**
- This is the clearest failure mode
- Narrow, specific queries need different handling

**Recommendation:** See "Bill-First Mode" below.

---

### Persona 4: Legislative Researcher
**Query:** "all active housing bills 2024-2025"

**Finding:** Only 14 "Active" status bills exist in the database (of 2,848 total). The semantic search isn't filtering by status.

**Issue:** Query implies status filter but semantic search ignores metadata.

**Verdict: OUT OF SCOPE**
- This is a structured query, not semantic
- Should route to `get_legislation(status="Active")` instead
- Consider hybrid: semantic + metadata filters

**No algorithm change needed** - this is a query routing problem.

---

### Persona 5: Casual Resident
**Query:** "can I build an ADU"

**Results:**
```
1. [0.620] SB130: Housing
2. [0.574] AB130: Housing
3. [0.561] SB543: Accessory dwelling units and junior accessory dwel...
...
30 bills total (max)
```

**Issues:**
1. Generic "Housing" bills outrank ADU-specific SB543
2. `relevant_sections` excerpt helpful but jargon-heavy
3. 30 results is overwhelming for a yes/no question

**Sample section excerpt:**
```
"[Bill SB130: Housing. continued] extinguish the ability to
otherwise construct, an ADU or JADU consistent with those
aforementioned minimum standards provisions..."
```

**Verdict: NEEDS IMPROVEMENT**
- Correct bills are present but buried
- Plain-language summary would help more than section excerpts
- This user needs a conversational answer, not a bill list

**Recommendation:**
- This is an LLM context problem, not a retrieval problem
- The MCP server should synthesize "Yes, you can build an ADU. Key laws: SB543 (ADU ordinances), SB130 (housing standards)..."

---

## Analysis of Alternative Strategies

### A. Bill-First Ranking

**Current:** Chunks → Filter → Group → Limit
**Proposed:** Chunks → Score bills by max chunk → Rank bills → Fetch sections

**Evaluation:**
- **Pro:** Fixes Persona 3 (journalist) - bill name match would rank SB9 higher
- **Pro:** Fair to bills with fewer chunks
- **Con:** May miss highly relevant sections in lower-ranked bills
- **Con:** Requires algorithm change

**Verdict: IMPLEMENT AS OPTION**
```python
def what_applies(topic, *, ranking_mode='section_first'):
    # 'section_first' = current behavior
    # 'bill_first' = score bills by max chunk similarity
```

Use bill-first for queries containing specific bill numbers (detect via regex: `[SAH]B\d+`).

---

### B. Dynamic Limits (Score Gap Detection)

**Proposed:**
```python
if prev_score - score > 0.1:  # Stop at large gaps
    break
```

**Evaluation based on data:**
- Narrow query gaps: 0.015, 0.012, 0.009 (too small)
- Broad query gaps: 0.003, 0.002, 0.001 (way too small)

**Verdict: NOT VIABLE**
Score distributions are too compressed for gap detection. There are no natural breakpoints.

---

### C. Tiered Response

**Proposed:**
```python
{
    "top_results": [...],      # Top 10, high confidence
    "additional": [...],       # Next 20, moderate confidence
    "total_available": 47      # For pagination
}
```

**Evaluation:**
- **Pro:** Serves both quick-answer and research use cases
- **Pro:** Simple to implement
- **Con:** API change, MCP prompt updates needed

**Verdict: IMPLEMENT**
This is the right approach for serving multiple personas. Top 10 for casual users, full list for researchers.

---

### D. Query-Adaptive Limits

**Proposed:** Detect query breadth, adjust limits:
- Narrow (specific bill): limit=5
- Broad (topic area): limit=50

**Evaluation:**
- Query breadth detection is unreliable
- "SB9 duplex law" looks narrow but returns 24 results with flat scores
- Adds complexity without clear benefit over tiered response

**Verdict: NOT RECOMMENDED**

---

## Implemented Changes

### Change 1: Bill-First Mode with Query Boosting (IMPLEMENTED)

**Status:** Implemented in `context.py`

**New API:**
```python
# New parameters for what_applies()
c.what_applies(
    topic,
    ranking_mode="auto",  # "section_first", "bill_first", or "auto"
    max_results=30,       # Configurable limit
    min_score=0.4,        # Configurable floor
)
```

**Behavior:**
- `auto` mode detects bill numbers in query (regex: `[SAH]B\d+`, `HR\d+`)
- When bill numbers detected, uses `bill_first` mode with boosting
- Mentioned bills get +0.1 score boost, surfacing them to top of results
- Fixes journalist use case: "SB9 duplex law" now returns SB9 at rank #1

**Test Results:**
```
Query: "SB9 duplex law"

Auto mode (bill_first with boost):
  1. [0.673] SB9: Accessory Dwelling Units: ordinances <-- TARGET
  2. [0.674] SB79: Housing development: transit-oriented dev

Section-first mode (no boost):
  1. [0.674] SB79: Housing development: transit-oriented dev
  2. [0.673] SB9: Accessory Dwelling Units: ordinances <-- TARGET
```

### Change 2: Tiered Response Structure (IMPLEMENTED)

**Status:** Implemented in `context.py`

Each bill in the response now includes a `tier` field:
- `"primary"` - Top 10 results (high confidence)
- `"secondary"` - Results 11-30 (additional context)

```python
result = c.what_applies("housing")
for bill in result.state:
    print(f"{bill['tier']}: {bill['bill_number']}")
# Output:
# primary: SB130
# primary: AB130
# ...
# secondary: SB92
```

### Change 3: Configurable Parameters (IMPLEMENTED)

All three parameters are now exposed:
- `ranking_mode`: Explicit control over ranking algorithm
- `max_results`: Adjustable result limit (default 30)
- `min_score`: Adjustable similarity floor (default 0.4)

### Non-Changes (Validated by Data)

| Parameter | Current | Keep? | Rationale |
|-----------|---------|-------|-----------|
| `CHUNK_TOP_K = 100` | 100 | Yes | Provides good bill diversity |
| `CHUNKS_PER_BILL = 3` | 3 | Yes | Prevents chunk concentration bias |
| `MAX_BILLS = 30` | 30 | Yes | Comprehensive without overwhelming |
| `SEMANTIC_SCORE_FLOOR = 0.4` | 0.4 | Yes* | *Operationally never triggers, but harmless |

---

## URL Prominence Question

**Current:** `official_url` included in response but not prominently surfaced

**Finding:** URLs are present in the data:
```
URL: https://legiscan.com/CA/bill/SB130/2025
```

**Recommendation:** MCP prompt should be updated to emphasize:
> "Always cite the official URL when referencing legislation. Format: [Bill Number](URL)"

This is a prompt engineering fix, not an algorithm change.

---

## Summary

| Persona | Current State | Fix |
|---------|---------------|-----|
| Tenant Organizer | Excellent | None |
| City Planner | Good | Query expansion (future) |
| Journalist | Problem | Bill-first mode |
| Researcher | Out of scope | Hybrid query routing |
| Casual Resident | Good retrieval, needs synthesis | MCP prompt |

**Bottom line:** The algorithm is sound. The two recommended changes (bill-first mode + tiered response) are surgical fixes for specific use cases without disrupting the core design.

---

## Appendix: Raw Data

### Score Distribution: "housing" query
```
Total results: 100
Max score: 0.701
Min score: 0.651
Mean score: 0.661
Score buckets:
  "0.7+": 1
  "0.6-0.7": 99
  "0.5-0.6": 0
  "0.4-0.5": 0
  "<0.4": 0
```

### Bill Concentration
```
Unique bills in 100 chunks: 14
  ca-ab130: 36 chunks (36%)
  ca-sb130: 30 chunks (30%)
  ca-sb681: 13 chunks (13%)
  ca-ab1529: 7 chunks (7%)
  ca-ab1170: 3 chunks (3%)
  ...remaining 9 bills: 1-2 chunks each
```

### Narrow vs Broad Query Comparison
```
NARROW QUERY: 'SB9 accessory dwelling unit California'
  Score >=0.7: 32
  Score >=0.6: 100
  Max: 0.776, Min: 0.682
  Largest gaps: (0, 0.015), (4, 0.012), (2, 0.009)

BROAD QUERY: 'housing development requirements permits zones'
  Score >=0.7: 100
  Score >=0.6: 100
  Max: 0.750, Min: 0.721
  Largest gaps: (4, 0.003), (1, 0.002), (2, 0.001)
```
