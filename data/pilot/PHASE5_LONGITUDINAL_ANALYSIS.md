# Phase 5: Longitudinal Complaint Trends Analysis

**Date**: 2025-11-24
**Dataset**: 1,340 SeeClickFix complaints (2009-2025) for San Rafael
**Branch**: `feature/seeclickfix-integration`

---

## Executive Summary

San Rafael's SeeClickFix data reveals a **recent adoption pattern** (2023+), **severe resolution backlog** (94% unresolved), and **predictable geographic clustering**. The data suggests operational gaps that the civic platform can address through visibility and coordination.

### Key Findings

| Metric | Finding | Implication |
|--------|---------|-------------|
| **Adoption** | 90% of complaints from 2024-2025 | Platform recently adopted |
| **Resolution** | Only 6% closed, 53% stale >6 months | Tracking failure |
| **Seasonality** | May-Nov peak (2x winter volume) | Predictable capacity needs |
| **Geography** | Downtown corridors dominate | Target notification areas |

---

## Task 1: Complaint Volume Over Time

### Yearly Trend: Explosive Recent Growth

| Year | Complaints | Pattern |
|------|-----------|---------|
| 2009-2022 | 66 | Sparse (~5/year) |
| 2023 | 70 | Adoption begins |
| 2024 | 350 | 5x growth |
| 2025 | 854 | 2.4x growth (YTD) |

**Interpretation**: SeeClickFix was not widely used until 2023. The platform is now establishing itself as the primary 311 channel.

### Monthly Pattern (2024-2025)

```
Jan:  82 ████████████
Feb:  57 ████████
Mar:  55 ████████
Apr:  77 ███████████
May: 120 █████████████████
Jun: 130 ██████████████████
Jul: 103 ██████████████
Aug: 120 █████████████████
Sep: 125 █████████████████
Oct: 118 ████████████████
Nov: 184 █████████████████████████
Dec:  33 █████
```

**Seasonality**: May-November is peak season (2x winter volume). December sees dramatic drop.

### Day of Week

| Day | Complaints | Relative |
|-----|-----------|----------|
| Mon-Fri | 197-219 | **Weekday dominant** |
| Sat-Sun | 71-77 | 35% of weekday |

**Interpretation**: Complaints filed during work hours/commutes. Weekend reporting is underutilized.

---

## Task 2: Category Trends

### Overall Distribution

| Category | Count | % |
|----------|-------|---|
| Traffic/Signal | 224 | 16.7% |
| Street Signs | 146 | 10.9% |
| Parks | 88 | 6.6% |
| Parking Violations | 79 | 5.9% |
| Stormwater | 71 | 5.3% |
| Illegal Dumping | 69 | 5.1% |
| Abandoned Vehicles | 65 | 4.9% |
| Trees | 63 | 4.7% |
| Potholes | 60 | 4.5% |
| Street Lights | 55 | 4.1% |

**Key Pattern**: Traffic/infrastructure dominate. Quality-of-life issues (dumping, abandoned vehicles) are significant secondary category.

### Camping/Homeless Issues

**Total**: 112 issues (8.4% of all complaints)

```
Monthly Trend:
2024-04:  3 ← April 15 ordinance
2024-05:  3
2024-08:  1 ← Aug 19 ordinance
2024-09:  5
2024-11:  9 ← Spike begins
2025-05:  9
2025-07: 10
2025-11: 12 ← Current peak
```

**Finding**: No spike around policy dates (April/Aug 2024). Delayed response - complaints increased months later and continue growing into 2025.

### Stormwater Surge (Q4 2025)

| Quarter | Stormwater % |
|---------|-------------|
| 2024-Q1 | 3.6% |
| 2024-Q4 | 4.0% |
| 2025-Q3 | 5.5% |
| 2025-Q4 | **12.3%** |

**Interpretation**: Fall rain season drives 3x increase in drainage complaints.

---

## Task 3: Resolution Time Analysis

### Critical Finding: Resolution Funnel Failure

| Stage | Count | % |
|-------|-------|---|
| Total Issues | 1,340 | 100% |
| Acknowledged | 640 | **48%** |
| Closed | 76 | **6%** |

**94% of issues remain unresolved in the system.**

### Age of Open Issues

| Age | Count | % |
|-----|-------|---|
| >30 days | 610 | 90% |
| >90 days | 535 | 79% |
| >180 days | 363 | **53%** |

**Over half of open issues are more than 6 months old.** This indicates:
1. Resolution tracking failure (issues resolved but not marked)
2. Massive operational backlog
3. System abandonment for certain categories

### Acknowledgment Time

| Metric | Value |
|--------|-------|
| Median acknowledgment | 88.7 hours |
| Within 24 hours | 32% |
| Within 1 week | 65% |

### Resolution Time by Category (Closed Issues Only)

| Category | Closed | Avg Days | Median Days |
|----------|--------|----------|-------------|
| Potholes | 4 | 0.8 | 0 |
| Roadside Vegetation | 4 | 4.2 | 0 |
| Illegal Dumping | 21 | 5.6 | 5 |
| Street Signs | 3 | 3.7 | 3 |
| Stormwater | 10 | 20.6 | 13 |
| Graffiti | 4 | 18.5 | 22 |
| Parks | 8 | 45.6 | 2 |
| Trees | 4 | 47.5 | 4 |

**Fastest**: Potholes and vegetation (same-day)
**Slowest**: Trees and parks (6+ weeks average)

---

## Task 4: Geographic Clustering

### Top Complaint Streets

| Street | Complaints | Primary Issues |
|--------|-----------|----------------|
| 4th St | 40 | Parking, downtown |
| 3rd St | 30 | Traffic, signals |
| Lincoln Ave | 27 | Dumping (10), traffic |
| Mission Ave | 22 | Traffic (9) |
| 5th Ave | 19 | Parking (10) |

### Category Hotspots

| Category | Top Location | Count |
|----------|-------------|-------|
| Traffic | 3rd St | 10 |
| Parking | 4th St (downtown) | 12 |
| Illegal Dumping | Lincoln Ave | 10 |
| Potholes | Scattered | 2 max |

### Canal Neighborhood

Despite being known for homeless issues, Canal area shows only 42 total complaints:
- Parks: 5
- Illegal Dumping: 5
- Signs: 5
- Graffiti: 5
- Traffic: 5

**No dominant category** - homeless complaints in Canal are not significantly higher than other areas in the data.

---

## Implications for Civic Platform

### 1. Resolution Visibility Gap

**Problem**: 94% of issues show no resolution in SeeClickFix
**Opportunity**: Track resolution independently, surface stale issues to council

### 2. Seasonal Capacity Planning

**Pattern**: May-November = 2x winter volume
**Action**: Pre-position notifications for predictable seasonal spikes

### 3. Geographic Targeting

**Corridors**: 4th St, 3rd St, Lincoln Ave, Mission Ave
**Action**: Location-based notifications for these high-complaint areas

### 4. Category Prioritization

**Fastest response**: Potholes, vegetation (same-day)
**Slowest response**: Trees, parks (6+ weeks)
**Action**: Set user expectations by category

### 5. Camping Policy Feedback Loop

**Finding**: No immediate spike after ordinances (April/Aug 2024)
**Observation**: Complaints increased 6+ months later
**Question**: Does policy → behavior change take months to manifest in complaints?

---

## Appendix: Data Quality Notes

1. **Sample bias**: 90% of data from 2024-2025; historical trends unreliable
2. **Resolution tracking**: 94% unresolved suggests system/process issue, not actual backlog
3. **Address parsing**: Street extraction from free-text addresses (some noise)
4. **Category consistency**: Bilingual categories (English/Spanish) normalized

---

## Files Generated

- `data/pilot/PHASE5_LONGITUDINAL_ANALYSIS.md` - This document
- Data source: `data/pilot/seeclickfix_sanrafael_complete.json`
