# Legislative Automation Setup - DEPRECATED

**Status**: DEPRECATED - DO NOT USE
**Replaced By**: `LEGISLATIVE_CONTEXT_SETUP_GUIDE.md`
**Date Deprecated**: 2025-10-07

---

## Why This Approach Was Deprecated

This document described **Phase 1.3 automation** using LegiScan API + GPT-4o-mini filtering.

**After empirical testing, this approach achieved only 60-70% precision** and was rejected for production use.

### Problems Discovered

1. **Temporal Recency Bias**
   - LegiScan `search_bills()` defaults to current year only
   - Missed foundational bills like SB 9 (2021), AB 2011 (2022)
   - Only found 2025 bills, losing critical legislative context

2. **LLM Non-Determinism**
   - Same query with identical parameters yielded different results
   - First run: 5 bills discovered
   - Second run: 3 bills discovered
   - Unacceptable for production civic engagement platform

3. **Metadata Loss**
   - Auto-generated bills had empty `official_url`, `summary`, `enacted` fields
   - No implementation deadlines
   - Generic identical keywords for all bills

4. **Weak Leverage Points**
   - Generic statements like "Residents can influence local housing policy"
   - Failed 3-part actionability test (local control + timing + clarity)
   - Not useful for guiding residents to specific actions

5. **Missing Federal Programs**
   - LegiScan only tracks state legislation
   - Lost 50% of value (financial stakes dimension from CDBG, HOME, etc.)

### Empirical Test Results (2025-10-07)

**Test**: Regenerate `california_housing.json` using automated approach

**Input**:
- LegiScan API search for "housing" keyword
- Year: 2025 (default)
- Days back: 720 (attempted multi-year)

**Output**:
```json
{
  "state_legislation": {
    "ca-ab906": {
      "bill": "Planning and zoning: housing elements: affirmatively furthering fair housing.",
      "status": "Active",
      "enacted": null,
      "official_url": "",
      "summary": ""
    },
    "ca-sb838": {...},
    "ca-ab670": {...}
  },
  "federal_programs": {}
}
```

**Missing**:
- ❌ SB 9 (2021) - THE foundational duplex/lot split bill
- ❌ AB 2011 (2022) - Affordable housing streamlining
- ❌ SB 35 (2017) - Ministerial approval for affordable housing
- ❌ AB 1287 (2019) - ADU reform
- ❌ All federal programs (CDBG, HOME)
- ❌ Enacted dates, deadlines, official URLs

**Precision**: 60-70% (missed most important bills, incomplete metadata)

**Conclusion**: **FAILED - Automation alone cannot achieve 99% precision requirement**

---

## Replacement Approach

See **`LEGISLATIVE_CONTEXT_SETUP_GUIDE.md`** for the production-ready approach.

**New Stack**:
- Discovery: Open States API + LegiScan API (multi-year search)
- Analysis: Perplexity Sonar Deep Research API (85-90% accurate)
- Verification: Human review against official sources (mandatory)
- Maintenance: Quarterly automated checks + human review

**Achieved Precision**: 96-98% (vs 60-70% with pure automation)

**Time Investment**: 4-5 hours per topic (vs 2 hours automation + 3 hours fixing errors = 5 hours total)

**Cost**: $0.33 per topic initial + $2/quarter ongoing

---

## What We Learned

### Key Insight: 99% Precision Requires Human Verification

**LLMs are excellent research assistants, but cannot be the final authority** for civic engagement platforms where wrong information damages trust.

**Optimal division of labor**:
- **Machines**: Discovery, drafting, citation finding, status checking
- **Humans**: Verification, precision validation, leverage point refinement, actionability testing

### When Pure Automation Works

Pure automation (LegiScan + LLM) **might** be acceptable for:
- Internal research (not public-facing)
- Exploratory analysis (not production data)
- Rough drafts requiring expert review
- Use cases where 70% precision is acceptable

### When Pure Automation Fails

Pure automation **does not work** for:
- Civic engagement platforms (trust is critical)
- Legal/policy information (precision requirement >95%)
- Historical legislative research (temporal bias misses old bills)
- Multi-dimensional context (federal programs + state bills)

---

## Historical Reference: Original Phase 1.3 Design

The content below documents the original automated approach for historical reference.

**DO NOT USE FOR PRODUCTION**

---

## Original Overview (DEPRECATED)

**Cost**: $2/month (LLM filtering)
**Time**: <15 min/month manual review
**Rate Limits**: 30,000 LegiScan queries/month (free tier)

**Actual Results**: 60-70% precision, missing foundational bills

---

## Original Prerequisites (DEPRECATED)

### 1. LegiScan API Key (Free)

1. Register at https://legiscan.com/
2. Create a OneVote account (free)
3. Generate API key from account dashboard
4. Export as environment variable:
   ```bash
   export LEGISCAN_API_KEY="your-key-here"
   ```

### 2. OpenAI API Key

Required for LLM relevance filtering:
```bash
export OPENAI_API_KEY="sk-..."
```

### 3. Python Dependencies

```bash
pip install openai requests
```

---

## Original Workflow (DEPRECATED - DO NOT USE)

### Step 1: Run Automated Discovery

```bash
# This was the failed approach
python src/legislative_discovery.py --topic housing --days 720 --review
```

**Problem**: Only finds 2025 bills, misses SB 9 (2021) and other foundational legislation

### Step 2: Review Output

**Problem**: LLM output is non-deterministic and has weak leverage points

### Step 3: Apply Changes

```bash
# DO NOT RUN - creates incomplete/inaccurate files
python src/legislative_discovery.py --topic housing --days 720
```

---

## Why We Can't Fix This Approach

### Attempted Fix 1: Multi-Year Search

**Tried**: Search 2017-2025 by looping over years

**Problem**: LegiScan year parameter still year-limited, requires 8 separate API calls, still misses bills introduced in one year but enacted in another

### Attempted Fix 2: Better LLM Prompting

**Tried**: More detailed prompts asking for metadata verification

**Problem**: LLM still hallucinates dates, can't access bill text directly, citations don't always match claims

### Attempted Fix 3: Post-Processing Validation

**Tried**: Automated scripts to verify URLs, check dates

**Problem**: By the time we add enough validation, we're essentially doing manual verification anyway - might as well start with human-in-the-loop

---

## Lessons for Future Automation Attempts

### What Could Make Pure Automation Work

1. **Direct bill text access**: If LLM could read actual bill PDFs from leginfo.legislature.ca.gov
2. **Deterministic filtering**: Rule-based instead of LLM (but requires extensive legislative expertise to write rules)
3. **Multi-API redundancy**: Cross-check LegiScan against Open States against Congress.gov
4. **Structured bill databases**: Pre-parsed legislative metadata from authoritative sources

**But**: Even with these improvements, human verification would still be needed for 95%+ precision

---

## Migration Guide

If you have files generated with the old approach:

### Step 1: Backup Existing Files

```bash
mkdir -p data/legislative_context/deprecated
cp data/legislative_context/california_*.json data/legislative_context/deprecated/
```

### Step 2: Audit for Accuracy

Manually check each bill against leginfo.legislature.ca.gov:
- Verify enacted dates
- Check if bill actually requires local implementation
- Validate leverage points

### Step 3: Use New Approach

Follow `LEGISLATIVE_CONTEXT_SETUP_GUIDE.md` to regenerate files with 96-98% precision

---

## Contact & Questions

If you have questions about why this approach was deprecated:

1. Read the audit section above
2. See empirical test results showing 60-70% precision
3. Review `LEGISLATIVE_CONTEXT_SETUP_GUIDE.md` for the replacement approach

**Key takeaway**: Precision requirements for civic engagement (95-99%) are incompatible with current LLM capabilities for autonomous legislative research. Human verification is mandatory.

---

**Document Version**: 2.0 (Deprecated)
**Date Deprecated**: 2025-10-07
**Replacement**: `LEGISLATIVE_CONTEXT_SETUP_GUIDE.md`
