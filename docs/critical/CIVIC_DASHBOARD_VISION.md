# Civic Dashboard Vision: City Status at a Glance

**Created**: 2026-01-22
**Updated**: 2026-02-04
**Status**: In Progress - Open WebUI artifact integration validated
**Priority**: Active - implementing for pilot launch

---

## Problem Statement

Citizens want to understand how their municipality is functioning, but face a UX dilemma:

- **Too much info** → Overwhelm, analysis paralysis
- **Too little info** → Useless, feels like marketing
- **News feeds** → Distant, editorialized, passive

The goal: A dashboard that **minimizes friction** for a layperson to understand their city's current state—strengths, weaknesses, what's being decided, what's stuck.

---

## Design Principles

### 1. Data-Forward, Minimal Editorial

Let patterns emerge from data structure, not commentary. Instead of saying "the city is ignoring this issue," show:

```
47 complaints filed  →  0 agenda items mentioning topic
```

The user draws the conclusion. This builds trust and avoids the "biased platform" perception.

### 2. Decisions, Not News

News is passive ("here's what happened"). Civic engagement is about **agency**. Bias toward:

- What's **being decided** (future-facing, actionable)
- What **just got decided** (accountability, outcomes)
- What's **persistently unresolved** (chronic community pain)

### 3. Progressive Engagement (Not Personas)

Don't design for static personas (activist vs. casual). Design for **progression states**—the same person moving through an engagement journey. The UX should make the *next step* visible without forcing it.

### 4. Conditional on Values, Not Editorial

Personalization via explicit user input ("what topics matter to you?") rather than algorithmic inference or platform-imposed framing. Relevance filtering, not editorializing.

---

## The Engagement Ladder

Users progress through stages. Each stage uses the same underlying data, structured differently:

```
AWARENESS        →   RELEVANCE        →   PARTICIPATION    →   COORDINATION
"What's happening"   "What affects me"    "Where I can act"    "Who's with me"
                                                                      ↓
                                                               FOCAL POINTS
                                                            "What we're building"
```

| Stage | Question | Data Surface |
|-------|----------|--------------|
| **Awareness** | What's happening in my city? | Decision flow, meeting calendar, issue density |
| **Relevance** | What affects me/my neighborhood? | Filtered by location, stated interests |
| **Participation** | Where can I have input? | Upcoming hearings, comment periods, testimony slots |
| **Coordination** | Who else cares about this? | `whos_with_me()`, related complaints, past testifiers |
| **Focal Points** | What are we building together? | Initiatives, campaigns, collective asks |

The dashboard should serve all stages, with clear pathways between them.

---

## Visualization Primitives

Data-forward visualizations that reveal patterns without editorializing:

### 1. Decision Flow (Sankey-style)

Shows how items move through the civic process:

```
INTRODUCED        HEARD           DECIDED         IMPLEMENTED
    │               │                │                │
    ├─ Housing ─────┼── Approved ────┼── Funded ──────┤
    │               │                │                │
    ├─ Cannabis ────┼── Approved ────┼── Pending ─────┤
    │               │                │                │
    └─ Parking ─────┴── Continued ───┴────────────────┘
                         (stuck here 3x)
```

**Reveals**: Where things stall. User sees that parking has been "continued" 3 times without commentary.

### 2. Participation Density (Calendar Heatmap)

```
     Jan 2026
Su Mo Tu We Th Fr Sa
          1  2  3  4
 5  6  7 [8] 9 10 11    ← [8] = Council meeting, 12 commenters
12 13 14 15 16 17 18
19 20 21[22]23 24 25    ← [22] = Planning, 3 commenters
26 27 28 29 30 31

Darker = more public participation
```

**Reveals**: Which meetings draw engagement. Over time, patterns emerge.

### 3. Issue Geography (Dot Density / Hex Bin)

```
┌─────────────────────────────────┐
│  ·                    · ·       │  Terra Linda (sparse)
├─────────────────────────────────┤
│         · · ·                   │  Downtown (moderate)
├─────────────────────────────────┤
│  · · · · · · · · · · · · · ·    │  Canal (dense)
└─────────────────────────────────┘
Each dot = 1 issue report (311/SeeClickFix)
```

**Reveals**: Where problems concentrate. No commentary needed.

### 4. Budget Treemap

```
┌─────────────────────────────────────────────┐
│           PUBLIC SAFETY $72M (40%)          │
├─────────────────────┬───────────────────────┤
│   INFRASTRUCTURE    │    COMMUNITY SVCS     │
│      $45M (25%)     │       $27M (15%)      │
├─────────────────────┴───────────────────────┤
│  ADMIN $18M  │  PARKS $12M  │  OTHER $6M    │
└─────────────────────────────────────────────┘
```

**Drillable**: Click Public Safety → Police vs Fire vs dispatch breakdown.

**Reveals**: Where money goes, proportionally.

### 5. Upstream/Downstream (Multi-Level Governance)

Shows how federal → state → local decisions connect:

```
FEDERAL                     STATE                       LOCAL
───────────────────────────────────────────────────────────────
HUD Fair Housing Act   →   CA Fair Housing Act    →   Housing Element
                           (AB 686)                    (compliance required)
                                ↓
                           RHNA Allocation        →   Zoning updates
                           (1,007 units)              (in progress)
```

**Reveals**: Why local decisions are constrained. "The city *must* plan for 1,007 units because of state RHNA."

### 6. Attention Alignment (Optional - More Editorial)

```
ALIGNED (both government and community focused)
├── Housing affordability: 23 complaints, 3 upcoming hearings

COMMUNITY CONCERNS (high complaints, low official attention)
├── Illegal dumping (Terra Linda): 34 reports, 0 agenda items

OFFICIAL PRIORITIES (on agenda, low community engagement)
└── Zoning text amendments: 0 public comments
```

**Note**: This is more editorial than pure data visualization. Include only if users opt into this framing.

---

## Multi-Surface Architecture

The same structured data serves multiple rendering contexts:

```
┌─────────────────────────────────────────────────────────┐
│                    CivicOS Core                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  Structured Data (decisions, issues, budget...)  │   │
│  └─────────────────────────────────────────────────┘   │
│                          │                              │
│         ┌────────────────┼────────────────┐            │
│         ▼                ▼                ▼            │
│  ┌────────────┐  ┌────────────────┐  ┌──────────┐     │
│  │ MCP Tools  │  │ Viz Primitives │  │ Web API  │     │
│  └────────────┘  └────────────────┘  └──────────┘     │
└─────────────────────────────────────────────────────────┘
         │                │                │
         ▼                ▼                ▼
┌─────────────┐  ┌─────────────────┐  ┌─────────────┐
│ Claude Chat │  │ Claude Artifact │  │ CivicOS Web │
│ (text)      │  │ (rendered viz)  │  │ (full app)  │
└─────────────┘  └─────────────────┘  └─────────────┘
```

### MCP Response Shape

MCP tools return structured data + optional visualization hints:

```python
def city_pulse(jurisdiction: str) -> dict:
    return {
        "data": {
            "decisions_this_week": [...],
            "recent_outcomes": [...],
            "issue_density_by_area": {...},
            "budget_allocation": {...}
        },
        "visualizations": [
            {
                "type": "calendar_heatmap",
                "title": "Upcoming Participation Opportunities",
                "data_key": "decisions_this_week",
                "x": "date",
                "intensity": "expected_participation"
            },
            {
                "type": "treemap",
                "title": "Budget Allocation",
                "data_key": "budget_allocation",
                "value": "amount",
                "label": "category"
            }
        ],
        "narrative_hints": {
            # For LLM to construct prose if needed
            "notable": ["Housing Element hearing draws 3x avg participation"],
            "patterns": ["Canal issues up 15% month-over-month"]
        }
    }
```

### Claude Artifact Rendering

Claude's web interface can render React/SVG artifacts. The LLM interprets structured data and emits appropriate visualizations:

```jsx
// Claude generates based on visualization hints
<CivicCalendar
  meetings={data.decisions_this_week}
  heatmapIntensity="participation_count"
/>
```

### CivicOS Web App

Full interactive experience:
- Click to drill down
- Persistence (save views, follow topics)
- Personalization (neighborhood, interests)

---

## User Personalization

Rather than algorithmic inference, use explicit value selection:

```
What matters to you? (shapes your civic view)

□ Housing affordability
□ Public safety
□ Environmental sustainability
□ Small business / economic development
□ Transportation / mobility
□ Parks and recreation
```

This filters/weights the same data:
- Decision flow shows matching items first
- Issue density highlights relevant categories
- Budget view emphasizes relevant allocations

This is **relevance filtering**, not editorializing.

---

## Open Questions

### Geographic Granularity
Current ETL is city-wide. Neighborhood-level views require:
- Better geocoding of issues
- Neighborhood boundary definitions
- Per-neighborhood aggregation

### Multi-Level Governance
How to show state/federal context coherently:
- Upstream dependencies (why local decisions are constrained)
- Funding flows (federal → state → local)
- Legislative connections (local policy ↔ state bills)

### Engagement Metrics
What signals "healthy" civic engagement?
- Participation rates (vs. what baseline?)
- Issue resolution times
- Decision follow-through

### Platform Parity
Should MCP users get the same experience as web users? Or is MCP for exploration and web for action?

---

## Implementation Progress (Feb 2026)

### Validated Approach: Open WebUI + Artifacts

We validated that Open WebUI's artifact system can render civic widgets effectively:

```
┌─────────────────────────────────────────────────────────────────┐
│                     Open WebUI Interface                         │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────┐  ┌──────────────────────────┐  │
│  │                             │  │    ARTIFACT PANEL        │  │
│  │       CHAT INTERFACE        │  │  ┌────────────────────┐  │  │
│  │                             │  │  │   City Pulse       │  │  │
│  │   "What's happening in      │  │  │   Widget           │  │  │
│  │    San Rafael?"             │  │  │                    │  │  │
│  │                             │  │  │   [Live Data]      │  │  │
│  │   → Shows City Pulse in     │  │  │   [Trending]       │  │  │
│  │     artifact panel ───────────────│   [Voice Stats]    │  │  │
│  │                             │  │  └────────────────────┘  │  │
│  └─────────────────────────────┘  └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Findings:**
- Self-contained HTML widgets render cleanly in sandboxed iframe
- CSS animations (pulse effects) work correctly
- Widget design system (CSS variables) transfers cleanly
- Side panel works well for detailed widgets

### Widget Placement Strategy

Different widget types suit different placements:

| Widget Type | Placement | Rationale |
|-------------|-----------|-----------|
| **City Pulse summary** | Top banner (dropdown) | Persistent context, quick glance, high visibility |
| **Notifications/Alerts** | Top banner | Time-sensitive, shouldn't miss |
| **Meeting Prep** | Side panel | Deep content, reference while chatting |
| **Issue Details** | Side panel | Exploration, multiple data points |
| **Voice Widget** | Side panel or modal | Action-focused, needs space for options |
| **Quick Actions** | Inline in chat | Low friction, contextual |

**Hybrid approach recommended:**
- **Top banner**: City context + alerts (collapsible)
- **Side panel**: Detailed widgets triggered by conversation
- **Inline**: Quick actions and confirmations

### Immediate Priorities

| Priority | Task | Status |
|----------|------|--------|
| 1 | Connect City Pulse widget to live MCP data | Done |
| 2 | LLM-triggered artifact opening (query → widget) | Done |
| 3 | Top banner component for City Pulse summary | Pending |
| 4 | Port Voice widget to Open WebUI artifacts | Pending |
| 5 | Port Meeting Prep widget | Pending |

### Technical Stack

```
civicos-openwebui/                    # Open WebUI fork
├── src/routes/(app)/+page.svelte    # Main page (Chat + test button)
├── src/lib/components/civic/        # Civic Svelte components (unused for now)
├── src/lib/stores/                   # Artifact stores (showArtifacts, artifactContents)
└── src/lib/components/chat/
    └── Artifacts.svelte              # Side panel renderer

civicos-mcp-apps/                     # Existing MCP widgets (HTML)
└── src/widgets/
    ├── voice.html                    # Voice casting widget
    ├── meeting_prep.html             # Meeting preparation
    ├── issue_card.html               # Issue details
    └── pulse.html                    # City Pulse dashboard
```

**Integration path:** Port MCP Apps HTML widgets → Open WebUI artifacts, connecting to Modal MCP server for live data.

---

## Relationship to Pilot

This vision is **post-pilot**. The Jan 2026 pilot validates the core hypothesis:

> "If residents knew about high-stakes decisions and could coordinate, they'd participate more effectively."

If validated, this dashboard vision becomes the **scaling UX**—how we serve 5-10 decisions/month, then city-wide engagement.

If the pilot fails, this vision may need fundamental rethinking (maybe residents don't want dashboards; maybe they want push notifications only).

**Sequence**:
1. Pilot validates coordination value (Jan 2026)
2. Dashboard vision guides scaling UX (Feb 2026+)
3. Multi-surface architecture enables distribution (MCP + web + mobile)

---

## Related Documentation

- `FOCAL_POINT_DECISION_AWARENESS.md` - Core hypothesis this vision extends
- `MCP_INTEGRATION_STRATEGY.md` - Multi-platform distribution architecture
- `PILOT_ROADMAP.md` - Jan 2026 validation plan (prerequisite to this vision)
- `FINAL_PACKAGE_ARCHITECTURE.md` - Data layer this visualization consumes

---

*This document captures UX vision for post-pilot development. Implementation details will emerge after pilot validation.*
