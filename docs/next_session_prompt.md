# Next Session: Dashboard MVP — Refine Visualizations

## What Was Done (2026-02-07)

1. **Removed "I'll Speak"** from CityPulse.svelte — button, state, API, CSS all cleaned out
2. **Added 3 viz primitives** to CityPulse: MeetingCalendar, DecisionFlow, IssueMap
3. **Added `GET /api/tools/issue-geography`** endpoint to rest_api.py (returns lat/lng for all 1,749 issues)
4. **Updated civic.ts** with `getIssueGeography()` + `IssuePoint` type

## Uncommitted / Unpushed

- **civicos**: rest_api.py, pilot.json, claude-progress.txt modified. Needs commit + push.
- **civicos-openwebui**: CityPulse.svelte modified, 3 new components (MeetingCalendar.svelte, DecisionFlow.svelte, IssueMap.svelte), civic.ts modified. Also has unrelated static file deletions. Needs commit + push.

## Critical Feedback from User

The user reviewed the live dashboard and raised these concerns:

### 1. DecisionFlow ("Pipeline") — LOW UTILITY, RETHINK
The bar showing "10 upcoming, 10 decided" is **unclear and not useful**. The user doesn't understand what it's counting or why it matters. Options:
- **Remove it** — simplest, frees space
- **Replace with something more meaningful** — e.g., a timeline of decisions with outcomes, or a "what's stuck" view showing items continued multiple times
- The current data (all 44 decisions are "approved") makes this especially uninformative

### 2. MeetingCalendar ("Meeting Activity") — LOW UTILITY, RETHINK
The calendar heatmap is **unclear about what it represents**. A green square on a day doesn't tell the user much. Options:
- **Remove it** — if it doesn't earn its space
- **Make it clickable** — click a day to see that day's meetings
- **Add context** — show meeting titles inline instead of requiring hover
- The fundamental question: does a heatmap of meeting frequency matter to a civic participant?

### 3. IssueMap — HIGH POTENTIAL, ENHANCE
The map is the **most promising** visualization. The user specifically asked: "Is it possible to overlay issues onto the map based off of geolocation?" — which is exactly what IssueMap already does (1,749 geocoded dots). But:
- Needs deployment to Modal first (issue-geography endpoint)
- May not have been visible in the screenshot if the endpoint wasn't live
- Consider: cluster markers for dense areas, filter by issue type, larger map height

## Deployment Needed

Both repos need deployment before visualizations work in production:

```bash
# 1. CivicOS MCP (issue-geography endpoint)
modal deploy apps/civicos-mcp/modal_mcp.py

# 2. OpenWebUI fork (new viz components)
cd ~/projects/civicos-openwebui
# Push to civicos-main branch, then deploy
```

## Recommended Approach for Next Session

1. **Commit + push** both repos (civicos + civicos-openwebui)
2. **Deploy** MCP server to Modal
3. **Evaluate DecisionFlow and MeetingCalendar** — likely remove or significantly redesign
4. **Focus on IssueMap** — this has the most user value. Make sure it renders properly with the live endpoint. Consider expanding map height, adding type filters, clustering.
5. **Layout CSS** — dashboard still needs polish (overlaps noted in pilot.json)

## P0 Status
`civic_dashboard_mvp` remains P0 in pilot.json. 3 viz primitives are implemented but 2 may need replacement.

## Key Files
| File | Repo | What |
|------|------|------|
| `src/lib/components/civic/CityPulse.svelte` | civicos-openwebui | Main dashboard, imports all 3 viz |
| `src/lib/components/civic/MeetingCalendar.svelte` | civicos-openwebui | Calendar heatmap (may remove) |
| `src/lib/components/civic/DecisionFlow.svelte` | civicos-openwebui | Pipeline bar (may remove) |
| `src/lib/components/civic/IssueMap.svelte` | civicos-openwebui | Leaflet dot map (keep, enhance) |
| `src/lib/apis/civic.ts` | civicos-openwebui | API client (getIssueGeography) |
| `apps/civicos-mcp/rest_api.py` | civicos | issue-geography endpoint |
| `pilot.json` | civicos | Progress tracking |
