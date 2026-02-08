# Recommended: Expandable Decision Detail Cards

**Priority:** P0
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-08

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session completed `agenda_actionability` — LLM-based classification of agenda items as actionable/informational/mixed. The dashboard now hides voice/comment UI on informational items (like "Open Time for Public Expression") and shows badges. Backfilled all 209 existing items: 74 actionable, 116 informational, 19 mixed. Deployed to Modal.

The dashboard MVP (`civic_dashboard_mvp`) has most sub-items complete:
- IssueMap with filtering, full-screen expand
- Voice toggle + comment threads
- Calendar links (Google Calendar, .ics download)
- Comment synthesis sentiment bar
- Budget allocation chart
- Agenda item actionability badges

**Remaining for MVP:** `expandable_decisions` (P0) and `provenance_footer` (P2). Completing expandable_decisions would make the Recent Decisions section interactive and data-rich, which is the biggest UX gap in the current dashboard.

## Recommended Task

Add expandable detail cards to the Recent Decisions section of CityPulse. Click a decision row to expand inline, showing:
- Vote breakdown (if available)
- Related public testimony (via transcript vector search)
- Linked agenda packet chunks
- Timeline context

## Implementation Plan

1. **Backend endpoint:** `/decision-detail?id=X`
   - Fetch decision details from storage
   - Vector search for related transcript chunks (existing embeddings)
   - Vector search for related agenda packet chunks
   - Return structured response

2. **Frontend:** Expandable card in CityPulse
   - Click decision row to expand inline (slide transition)
   - Fetch detail on demand (lazy load)
   - Show vote breakdown, testimony excerpts, linked documents
   - Collapse on click or on new expansion

## Key Files

- `apps/civicos-mcp/tools/handlers.py:425-451` — `city_pulse()` Recent Decisions section
- `~/projects/civicos-openwebui/src/lib/components/civic/CityPulse.svelte` — decision rendering
- `packages/civicos/src/civicos/storage/pgvector_backend.py` — vector search methods
- `packages/civicos/src/civicos/storage/postgres_backend.py` — decision storage methods

## Completed This Session

- [x] `agenda_actionability` — LLM classification module, backfill, API + frontend, deployed to Modal
- [x] Commits: civicos `6fec91c`; openwebui `a483275`

## What's Next After expandable_decisions

- `provenance_footer` (P2) — Data source info footer
- `civic_dashboard_mvp` meta-item can be marked ready once expandable_decisions + provenance_footer are done
- Then: `mcp_registry_listing` (blocked by MVP)
