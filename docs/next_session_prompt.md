# Recommended: Interactive Database Viewer for Pipeline Dashboard

**Priority:** P0 (IMMEDIATE)
**Area:** frontend_refinement > interface_clarity
**Item:** dashboard_visual_hierarchy (continued iteration)
**Date:** 2025-12-24

> This is recommended context from Session 358. The dashboard UX work is ongoing - continue iterating.

## Session 358 Progress

Implemented first iteration of outcome-focused dashboard:
- **Data Cards** with status badges (Meetings, Search Index, 311 Issues)
- **Sample data preview** showing 3 recent meetings with dates/titles
- **API endpoint** `include_samples=true` returns actual meeting data
- **Collapsible pipeline details** - technical 4x4 grid hidden by default

**User feedback:** "Better! We need to workshop this ALOT more."

## Next Phase: Embeddable Database Viewer Widget

The user envisions an **interactive database viewer** that makes the backend data tangible and navigable. This isn't necessarily the final product, but helps build intuition for presenting ETL status.

### Concept: Table Widget

A mini-spreadsheet component embedded in each data card that lets users:
1. **Browse rows** - See actual database records, not just counts
2. **Sort/filter** - By date, status, type
3. **Pagination** - Navigate large datasets
4. **Click to expand** - View full record details

### Design Questions to Explore

1. **Scope**: Just meetings? Or all data types (agenda items, issues, initiatives)?
2. **Interaction depth**: Read-only viewer? Or allow inline edits?
3. **Relationship navigation**: Click a meeting → see its agenda items?
4. **Search within table**: Filter by keyword?
5. **Export**: Download as CSV/JSON?

### Expert Panel Insights (from Session 358)

**UX perspective**: Users don't care about pipeline stages. They care about:
- "Is my data fresh?"
- "Is search working?"
- "What's broken?"

**Data engineering perspective**: The current grid mixes two audiences:
- Operators need "is it healthy?"
- Developers need "which stage broke?"

**Information architecture perspective**: Inconsistent column headers across rows make pattern recognition impossible.

### Proposed Widget Architecture

```
┌─────────────────────────────────────────────────────┐
│  Meetings                          [Current] ✓     │
│  17 tracked                                        │
├─────────────────────────────────────────────────────┤
│  Date       │ Body            │ Title              │
│─────────────┼─────────────────┼────────────────────│
│  Dec 1      │ City Council    │ Regular Meeting    │
│  Dec 2      │ Finance Sub...  │ Special Meeting    │
│  Dec 3      │ Zoning Admin    │ Hearing            │
│             │ [Load more...]                       │
├─────────────────────────────────────────────────────┤
│  [Fetch New]           Last updated: 6 hours ago   │
└─────────────────────────────────────────────────────┘
```

### Implementation Approach

1. **Create `<DataTableWidget>` component**
   - Props: dataType, columns, fetchFn
   - State: rows, loading, pagination
   - Reusable across Meetings/Issues/Initiatives

2. **Extend API for pagination**
   - `GET /admin/data/meetings?page=1&per_page=10`
   - Return total count for pagination

3. **Add detail modal**
   - Click row → show full record JSON
   - Link to related data (meeting → agenda items)

4. **Consider existing patterns**
   - Check if Vue data table libraries are already used
   - Maintain consistency with rest of app

### Key Files

- `apps/civic-workspace/src/components/workspace/AdminStatusPage.vue` - Current dashboard
- `apps/civic-workspace/src/components/shared/` - Shared components
- `apps/civic-workspace/src/services/api.ts` - API client
- `packages/civic-services/src/civic_services/servers/civic_api_integrated.py` - Backend

### Questions for User

Before implementing, clarify:
1. Which data types need the table widget first? (Meetings only, or all?)
2. Is row-click expansion important, or just viewing the list?
3. Any preference on table library (native HTML, or use a Vue table component)?

### Success Criteria

- [ ] Users can browse actual database records, not just counts
- [ ] Data feels "real" and navigable
- [ ] Clear visual connection between count and underlying data
- [ ] Technical pipeline details remain accessible but not dominant

## Current State

- **Frontend**: http://localhost:5173 (running)
- **API**: http://localhost:8001 (running with `include_samples`)
- **Pilot Progress**: 165/177 items (93.2%)

## Files Modified in Session 358

1. `AdminStatusPage.vue` - New data cards with sample preview
2. `api.ts` - Added `includeSamples` option
3. `civic.ts` - Added samples type to AdminStatusResponse
4. `civic_api_integrated.py` - Added sample data fetching with `include_samples=true`
