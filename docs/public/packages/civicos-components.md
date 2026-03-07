# civicos-components

Reusable Svelte 5 UI components for rendering civic data.

**Location:** `packages/civicos-components/`

Depends on `@civicos/client` for types. Optional peer dependencies: `chart.js` (budgets), `leaflet` (maps).

## Components

### Leaf Components (Composable)
- `CivicMeetingCard` — Meeting with date, location, agenda link
- `CivicAgendaItemCard` — Agenda item with summary and participation guide
- `CivicDecisionCard` — Decision with outcome badge and vote breakdown
- `CivicVoiceButtons` — Support/oppose/watching stance buttons
- `CivicInitiativeCard` — Initiative with attestation badges
- `CivicCommentThread` — Comment display
- `CivicProvenancePanel` — Data source attribution
- `CivicIdentityChip` — User identity display (truncated npub)
- `CivicSynthesisBar` — Synthesis visualization
- `CivicReadOnlyPulse` — Read-only city pulse summary
- `CivicProcessBar` — Process/progress visualization

### Smart Views (Own State)
- `CivicAgendaView` — Full agenda listing with filtering
- `CivicDecisionView` — Decision with full context
- `CivicInitiativeView` — Initiative with actions

### Visualization (Self-Contained)
- `CivicIssueMap` — Geographic issue map (Leaflet)
- `CivicBudgetBreakdown` — Budget breakdown chart (Chart.js)

## Theme System

```typescript
import { initTheme, setTheme, applyTheme } from '@civicos/components';

initTheme();       // Apply saved theme on page load
setTheme('dark');  // Switch to dark mode
```

Themes use CSS custom properties (`--civic-*` tokens).

## Utilities

`civic-helpers.js` exports:
- `isPastMeeting()`, `formatMeetingTime()`, `formatRelativeDate()`
- `truncateNpub()`, `outcomeIcon()`, `outcomeClass()`
- `googleCalendarUrl()`, `downloadIcs()`
- `computeCityFocalMeetings()`, `urgencyClass()`, `meetingDaysUntil()`
