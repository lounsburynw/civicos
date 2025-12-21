# Next Session: Admin Dashboard Redesign

## Context

Session 310 completed:
- Created `scripts/dev.sh` for launching dev servers with proper env config
- Fixed 90+ bare imports across civic_services to use full module paths
- Added `/launch` command documenting the startup process
- Updated CLAUDE.md with launch instructions

## Problem: Admin Dashboard is Confusing

The current admin "Data Pipeline" dashboard (`AdminStatusPage.vue`) displays metrics that don't make intuitive sense:

**Current display (Meetings row):**
| COVERAGE | INGESTED | SEARCHABLE |
|----------|----------|------------|
| 6/15 (40%) | 0 | 0 |

**The confusion:**
- "Coverage" = meeting *types* configured vs discovered (categories like "City Council", "Planning Commission")
- "Ingested" = actual meeting records in database
- "Searchable" = meetings indexed in vector store

A user sees "6/15 coverage" but "0 ingested" and has no idea what that means. You can have type coverage but no actual data.

**Agenda Items row is redundant** - agenda items are intrinsically tied to meetings. When you ingest a meeting, you get its agenda items. Having a separate row implies they're independent sources.

## Goal: Layman-Friendly Dashboard

Design a dashboard that a **new person setting up Civic in their own city** can understand:

1. **Clear data flow**: Source → Database → Search Index
2. **Actionable metrics**: What's working, what needs attention
3. **Honest labels**: No jargon, no misleading percentages
4. **Guidance**: When data is missing, tell them what to do

## Files to Explore

**Backend (data sources):**
- `packages/civic-services/src/civic_services/servers/civic_api_integrated.py` - `serve_admin_status()` at line ~7325
- `packages/civic-extraction/` - Platform scrapers (ProudCity, SeeClickFix)

**Frontend:**
- `apps/civic-workspace/src/components/workspace/AdminStatusPage.vue` - Current dashboard UI

**Data flow:**
1. **Meetings**: ProudCity scraper → `meetings` table → ChromaDB `decisions` collection
2. **Issues**: SeeClickFix API → `issues` table → ChromaDB `issues` collection
3. **Initiatives**: User-created → `initiatives` table → (not indexed)

## Suggested Approach

### 1. Understand the actual data pipeline
```
Source (external)     →  Database (storage)  →  Vector Store (search)
├─ ProudCity meetings    ├─ meetings table      ├─ decisions collection
├─ SeeClickFix issues    ├─ issues table        ├─ issues collection
└─ YouTube videos        └─ agenda_items        └─ transcripts collection
```

### 2. Simplify the dashboard rows

**Before (confusing):**
- Meetings: COVERAGE → INGESTED → SEARCHABLE
- Agenda Items: AVAILABLE → INGESTED → SEARCHABLE

**After (clear):**
- Meetings: `115 meetings` | `Last scraped: 2 days ago` | `92 indexed for search`
- Issues: `1,340 issues` | `Open: 47` | `Last updated: 1 hour ago`

### 3. Remove redundant rows
- Remove "Agenda Items" as separate row (they come from meetings)
- Or rename to "Meeting Documents" if we're tracking PDFs/attachments separately

### 4. Add guidance
When ingested=0, show: "Click 'Fetch Meetings' to scrape your first meetings from ProudCity"

## Key Questions to Answer

1. What does a healthy pipeline look like? (counts, freshness thresholds)
2. What actions can a user take when something is wrong?
3. What's the minimum viable dashboard for a new city setup?

## Launch the App

```bash
./scripts/dev.sh
```

Then navigate to the Admin page to see the current dashboard.
