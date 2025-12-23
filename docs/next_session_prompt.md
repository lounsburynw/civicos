# Recommended: Dashboard Visual Hierarchy & Inline Help

**Priority:** P0 (IMMEDIATE)
**Area:** frontend_refinement > interface_clarity
**Date:** 2025-12-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 357 completed `e2e_data_ingestion_verification` - verified the full data pipeline works end-to-end for San Rafael. However, reviewing the Data Pipeline dashboard revealed UX issues that need immediate attention before pilot.

**This task:** Simplify the Data Pipeline dashboard interface. Current state is overwhelming and lacks clarity for users.

## Current Problems

The dashboard shows a 4×4 grid of data (Meetings, Agenda Items, Issues, Initiatives × Coverage, Ingested, Stored, Indexed):

1. **Too much information competing for attention** - 16 cells with arrows between them
2. **Unclear visual hierarchy** - Nothing tells users what's important vs informational
3. **No inline help** - Users don't understand what "COVERAGE" or "INDEXED" means
4. **Status indicators unclear** - "Degraded" shown but no explanation of why or what to do

## Screenshot Reference

See screenshot from Session 357 showing the overwhelming interface with:
- Multiple rows (Meetings, Agenda Items, Issues, Initiatives)
- Multiple columns (COVERAGE → INGESTED → STORED → INDEXED)
- Numeric values and timestamps scattered throughout
- "Degraded" status with no actionable guidance

## Suggested Improvements

1. **Collapse by default** - Show only summary status, expand for details
2. **Highlight actionable items** - Clear visual distinction for items needing attention
3. **Add help tooltips** - Explain what each metric means on hover
4. **Simplify status indicators** - "Healthy" / "Needs attention" / "Error" with clear next steps
5. **Reduce visual noise** - Remove or de-emphasize less critical information

## Key Files

- `apps/civic-workspace/src/components/DataPipeline.vue` - Main dashboard component
- `apps/civic-workspace/src/components/` - Related UI components

## Success Criteria

- [ ] Dashboard has clear visual hierarchy
- [ ] Most important information is immediately visible
- [ ] Help text/tooltips explain each section
- [ ] Status indicators have clear meaning
- [ ] Interface feels approachable, not overwhelming

## Pilot Progress

- 164/177 items ready (92.7%)
- 13 items remaining
- P0: dashboard_visual_hierarchy (this item)
