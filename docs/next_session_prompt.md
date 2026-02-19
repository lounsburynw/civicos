# Recommended: Enrich Focal Points + Voice Disclaimer

**Priority:** P0 (engagement_ladder_ux)
**Area:** frontend_refinement > city_status_dashboard
**Date:** 2026-02-19

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

This session promoted focal points (Comment Periods, Upcoming Hearings, Governor's Desk) to the top of CivicReadOnlyPulse under a "Take Action" group with amber accent styling. Added drag-to-AI with context composers for all 3 types, and wired voice buttons (support/oppose/watching) to all focal point cards. A simulated user panel identified actionable gaps that should be addressed next.

### Commits This Session
- `0c5fa7a` feat: Promote focal points to top of pulse and add drag-to-AI
- `efa6436` feat: Add voice buttons to focal point cards

## Recommended Tasks (from user feedback panel)

### 1. Enrich Hearing Data via JOIN (Quick Win)
Hearings currently show raw `bill_id` as title because `bill_number` and `bill_name` are never joined from the `legislation` table. The Svelte component expects them but they never arrive.

**Fix:** In the pulse handler's `get_upcoming_hearings()` query, JOIN `legislative_events` to `legislation` on `bill_id` to pull `bill_number`, `bill_name`, `official_url`, and `summary`.

Key files:
- `packages/civicos/src/civicos/storage/postgres_backend.py` — `get_upcoming_hearings()` (no JOIN currently)
- `apps/civicos-mcp/tools/handlers.py:591-616` — pulse handler hearings section (drops bill_number, bill_name)
- `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte:302-334` — hearing cards (already render bill_number/bill_name when present)

### 2. Add Voice Disclaimer
All voice buttons need a disclaimer: *"Voices are informal signals of community interest — they are not official votes, public testimony, or legal actions."*

Options:
- Tooltip on first voice cast
- Subtle text below voice buttons section
- Part of identity unlock flow

### 3. Enrich Comment Periods (data already in DB)
Pass through fields that are stored in `federal_rules` but dropped before reaching the component:
- `document_type` — "Proposed Rule" vs "Notice" label
- `topics` — JSONB tags for filtering/display
- `pdf_url` — direct link to official PDF
- `publication_date` — "Published X days ago" context

Key files:
- `apps/civicos-mcp/tools/handlers.py:556-587` — pulse handler comment periods section
- `packages/civicos-client/src/types.ts:71-80` — CommentPeriod type (add fields)
- `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte:254-284` — comment period cards

### 4. Wire LegiScan Calendar API (Medium Effort)
`LegiScanClient.get_session_calendar()` is **implemented but never called** in the ingestion pipeline. It returns authoritative hearing dates, locations, descriptions, and linked bills — far richer than the current regex parsing of `last_action` text.

Key files:
- `packages/civicos-extraction/src/civicos_extraction/clients/legiscan.py` — `get_session_calendar()` exists
- `scripts/modal_ingest.py:1146-1208` — `extract_legislative_events()` uses regex only

### 5. Hide Voices on Closed Comment Periods
When `days_remaining <= 0`, voice buttons are less meaningful. Consider hiding them or showing results-only (read-only vote tally).

### 6. Governor's Desk Label Clarity
User feedback: "Governor's Desk means nothing to me." Consider rephrasing to "Awaiting Governor's Signature" or adding a subtitle.

## Key Files

- `packages/civicos-components/src/components/CivicReadOnlyPulse.svelte` — Main pulse component (focal points at top, voice buttons wired)
- `apps/civicos-mcp/tools/handlers.py:556-634` — Pulse handler producing comment_periods, upcoming_hearings, governors_desk
- `packages/civicos/src/civicos/storage/postgres_backend.py` — `get_upcoming_hearings()`, `get_federal_rules()`
- `packages/civicos-extraction/src/civicos_extraction/clients/legiscan.py` — `get_session_calendar()` (unused)
- `scripts/modal_ingest.py:1146-1208` — `extract_legislative_events()` (regex-only)
- `packages/civicos-client/src/types.ts` — TypeScript types for focal point data

## Suggested Approach

1. Start with Task 1 (hearing JOIN) — biggest visible impact, small change
2. Task 2 (voice disclaimer) — important for credibility
3. Task 3 (comment period enrichment) — data already stored, just pass-through
4. Task 6 (governor's desk label) — one-line fix
5. Task 5 (hide closed voices) — small conditional
6. Task 4 (LegiScan calendar) — larger pipeline change, do if time permits

## Success Criteria

- [ ] Hearing cards show bill_number and bill_name (not raw bill_id)
- [ ] Voice disclaimer visible to users before or during first voice cast
- [ ] Comment period cards show document type and topics
- [ ] Governor's Desk header is clear to non-political users
- [ ] Voice buttons hidden or read-only on closed comment periods
