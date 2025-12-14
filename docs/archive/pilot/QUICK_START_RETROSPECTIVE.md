# Quick Start: Retrospective Analysis

**Goal**: Extract 12 months of high-stakes decisions and measure coordination gaps in under 5 minutes (reading time).

---

## TL;DR

```bash
# 1. Scrape archives (10 sec)
python scripts/scrape_sanrafael_archives.py \
  --start-date 2024-11-01 --end-date 2025-11-30 \
  --output data/pilot/san_rafael_meetings.json

# 2. Extract high-stakes (30-60 min for City Council)
python scripts/analyze_sanrafael_retrospective.py \
  data/pilot/san_rafael_meetings.json \
  --output data/pilot/decisions.json \
  --meeting-types city_council \
  --min-stakes 6

# 3. Match complaints (30-60 min)
python scripts/match_seeclickfix_to_decisions.py \
  data/pilot/decisions.json \
  --output data/pilot/matches.json

# 4. Manually add testimony counts to matches.json
# (Edit file, add "testimony_count": N to each match)

# 5. Calculate gaps (instant)
python scripts/calculate_coordination_gaps.py \
  data/pilot/matches.json
```

---

## What You Get

**Foundation pitch evidence**:
- "**18 decisions**, **342 complaints**, **86% coordination gap**"
- "Top 5 opportunities: [list with budget amounts, resident counts]"
- "Pattern: Budget decisions in Sep-Oct average 87% gaps"

**Use cases**:
- Foundation grant applications
- Pilot city selection
- Automation design input
- Pattern validation

---

## Output Files

1. **`meetings.json`**: 114 meetings with agenda URLs
2. **`decisions.json`**: 15-30 high-stakes decisions with budgets, keywords
3. **`matches.json`**: Per-decision complaint counts (30-day lookback)
4. **`gaps.json`**: Coordination gap statistics + pattern analysis

---

## Time & Cost

| Step | Time | Cost | Notes |
|------|------|------|-------|
| 1. Scrape | 10 sec | Free | HTML parsing |
| 2. Extract (CC only) | 30-60 min | $8-10 | 33 meetings × LLM |
| 2. Extract (all) | 2-3 hours | $28-30 | 114 meetings × LLM |
| 3. Match | 30-60 min | Free | SeeClickFix API |
| 4. Manual testimony | 30-60 min | Free | Watch videos/read minutes |
| 5. Calculate | <1 sec | Free | Math |

**Total (City Council only)**: ~2 hours, $8-10
**Total (all meetings)**: ~4 hours, $28-30

---

## Example Output

### From Step 2 (High-Stakes Extraction)

```
📊 ANALYSIS COMPLETE

   Meetings analyzed: 33
   Meetings with high-stakes decisions: 18
   Total high-stakes decisions: 22
   Total budget amount: $5,200,000

   By decision type:
     - budget: 10
     - development: 6
     - environmental: 4
     - policy: 2

   By meeting type:
     - city_council: 22
```

### From Step 3 (Complaint Matching)

```
📊 MATCHING COMPLETE

   Decisions analyzed: 22
   Decisions with complaints: 19
   Total complaints found: 342
   Average complaints per decision: 18.0
```

### From Step 5 (Gap Calculation)

```
📊 COORDINATION GAP ANALYSIS

   Total complaints: 342
   Total testimony: 48
   Total gap: 294 residents
   Average gap percentage: 85.9%

🔝 TOP 5 COORDINATION GAPS

   1. Supplemental Appropriation for Wildfire Prevention
      Complaints: 22 | Testimony: 4 | Gap: 18 (81.8%)
      Budget: $1,108,319

   2. Affordable Housing Overlay Zone Amendment
      Complaints: 34 | Testimony: 6 | Gap: 28 (82.4%)
      Budget: $0

   3. Stormwater Infrastructure Improvement Project
      Complaints: 28 | Testimony: 3 | Gap: 25 (89.3%)
      Budget: $650,000

   ...
```

---

## Filters & Options

### Adjust Sensitivity

```bash
# More permissive (catch borderline decisions)
--min-stakes 4

# More restrictive (only major decisions)
--min-stakes 8

# Budget threshold
--min-budget 250000  # Only $250K+ decisions
```

### Focus on Specific Meeting Types

```bash
# City Council only (fastest)
--meeting-types city_council

# Planning Commission only (development focus)
--meeting-types planning_commission

# Multiple types
--meeting-types city_council planning_commission
```

### Adjust Complaint Lookback

```bash
# Shorter window (more precise, fewer complaints)
--lookback-days 14

# Longer window (more complaints, less precise)
--lookback-days 60
```

---

## Validation Checklist

After running pipeline, verify:

- [ ] **Step 2**: At least 10-15 decisions found (if 0, lower `--min-stakes`)
- [ ] **Step 3**: At least 50% of decisions have complaints (if 0, check keywords)
- [ ] **Step 4**: Testimony counts added for at least 10 decisions
- [ ] **Step 5**: Average gap percentage >50% (validates hypothesis)

---

## Common Issues

### "No high-stakes decisions found"

**Cause**: Threshold too high or meetings are procedural
**Fix**: Try `--min-stakes 4` or check meeting list manually

### "0 complaints matched"

**Cause**: Keywords too specific or SeeClickFix has no data
**Fix**: Review keywords in decisions.json, broaden manually

### "LLM timeout"

**Cause**: Agenda PDF is huge (>50MB) or network slow
**Fix**: Skip that meeting or increase timeout in code

---

## Next Steps After Pipeline

1. **Review top 5 gaps**: Deep dive case studies (like Oct 6 wildfire)
2. **Identify patterns**: Do Sep-Oct budget decisions cluster?
3. **Select pilot decisions**: Which have highest impact + feasibility?
4. **Foundation pitch**: Compile evidence into deck
5. **Multi-city validation**: Run on Berkeley, Santa Rosa

---

## Full Documentation

See `docs/pilot/RETROSPECTIVE_ANALYSIS_PIPELINE.md` for:
- Complete technical architecture
- Output format specifications
- Troubleshooting guide
- Future enhancement roadmap

---

**Questions?** See Session 98 completion notes or run `--help` on any script.
