# Legal Abstraction Strategy Session

**Date**: 2025-11-27
**Status**: Draft for team discussion
**Goal**: Determine the right package architecture for legal/code/decisions across government levels

---

## The Problem

We have `civic-legal` for state bills and federal programs, but users ask questions that span multiple levels:

- "Can my city block this housing development?" → Requires municipal zoning code
- "What state laws apply to this council decision?" → Requires state statutes
- "Has any Bay Area city done this before?" → Requires historical decisions
- "What federal funding could support this?" → Requires federal programs

**Current gap**: No corpus of municipal codes, general plans, or historical resolutions.

---

## Government Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│ FEDERAL                                                      │
│   Canonical: US Code, CFR, Federal Programs                 │
│   Ephemeral: Congressional hearings, agency rulemakings     │
├─────────────────────────────────────────────────────────────┤
│ STATE (California)                                           │
│   Canonical: CA Codes, Statutes (22 codes), Regulations     │
│   Ephemeral: Legislature sessions, bill progress            │
├─────────────────────────────────────────────────────────────┤
│ COUNTY (e.g., Marin)                                        │
│   Canonical: County Code, General Plan, LCP                 │
│   Ephemeral: Board of Supervisors meetings                  │
├─────────────────────────────────────────────────────────────┤
│ CITY (e.g., San Rafael)                                     │
│   Canonical: Municipal Code, General Plan, Specific Plans   │
│   Ephemeral: Council meetings, commission hearings          │
└─────────────────────────────────────────────────────────────┘
```

---

## What Users Actually Ask

### Tier 1: "What applies to this decision?"
- Which state laws govern this zoning change?
- What does our municipal code say about ADUs?
- Are there federal programs for this?

### Tier 2: "What's the precedent?"
- Has our city done this before?
- How did neighboring cities handle this?
- What was the outcome last time?

### Tier 3: "What's the full context?"
- Show me the complete regulatory stack for housing
- What's blocking affordable housing in my city?
- Where does local authority end and state preemption begin?

---

## Data Sources by Level

### Federal
| Type | Source | Accessibility |
|------|--------|---------------|
| US Code | uscode.house.gov | Free, structured |
| CFR (regulations) | ecfr.gov | Free, structured |
| Federal programs | CFDA, grants.gov | Free, semi-structured |
| Case law | CourtListener | Free API |

### State (California)
| Type | Source | Accessibility |
|------|--------|---------------|
| Bills | leginfo.legislature.ca.gov | Free, HTML |
| Codes (29) | leginfo.legislature.ca.gov | Free, HTML |
| Regulations | oal.ca.gov | Free, PDF-heavy |
| Case law | courts.ca.gov | Limited |

### County
| Type | Source | Accessibility |
|------|--------|---------------|
| County Code | Municode, county websites | Varies |
| General Plan | County planning dept | PDF |
| Board actions | Granicus, Legistar | API possible |

### City
| Type | Source | Accessibility |
|------|--------|---------------|
| Municipal Code | Municode, American Legal, eCode360 | Varies |
| General Plan | City planning dept | PDF |
| Zoning maps | GIS portals | Varies |
| Council actions | CivicClerk, Legistar | API possible |

---

## Architectural Options

### Option A: Single Package (`civic-legal`)
Expand civic-legal to handle all levels:

```
civic-legal/
├── federal/
│   ├── uscode.py
│   ├── cfr.py
│   └── programs.py
├── state/
│   ├── bills.py
│   ├── codes.py      # CA Government Code, etc.
│   └── regulations.py
├── county/
│   ├── code.py
│   └── plans.py
├── municipal/
│   ├── code.py       # Municode integration
│   ├── general_plan.py
│   └── zoning.py
└── unified/
    ├── search.py     # Cross-level search
    └── context.py    # Build full regulatory context
```

**Pros**: Single interface, unified search
**Cons**: Large package, different update cadences, different data sources

### Option B: Level-Specific Packages
Separate packages per government level:

```
civic-federal/    # US Code, CFR, federal programs
civic-state/      # CA codes, bills, regulations (rename current civic-legal?)
civic-county/     # County codes, general plans
civic-municipal/  # Municipal codes, city general plans
civic-decisions/  # Historical decisions across all levels
```

**Pros**: Separation of concerns, independent deployment
**Cons**: Cross-level queries harder, more packages to maintain

### Option C: Canonical vs. Ephemeral Split
Organize by permanence rather than level:

```
civic-corpus/     # All canonical law (codes, statutes, regulations)
├── federal.py
├── state.py
├── county.py
└── municipal.py

civic-activity/   # All ephemeral activity (meetings, decisions)
├── federal.py    # Congressional hearings
├── state.py      # Legislature sessions
├── county.py     # Board meetings
└── municipal.py  # Council meetings

civic-decisions/  # Extracted decisions (derived from activity)
```

**Pros**: Clear separation of "law" vs. "process"
**Cons**: Queries often need both

### Option D: Query-Centric Architecture
Organize by user query patterns:

```
civic-context/    # "What law applies here?"
├── stack.py      # Build full regulatory stack for a topic
└── preemption.py # Where does local authority end?

civic-precedent/  # "What's been done before?"
├── local.py      # Same jurisdiction history
└── regional.py   # Neighboring jurisdictions

civic-corpus/     # Raw data layer (internal)
```

**Pros**: Aligned with user needs
**Cons**: Abstracts away government structure (may confuse)

---

## Key Questions for Discussion

1. **Primary use case**: Are users asking "what law applies?" or "what's been decided?"

2. **Scope**: Do we need federal/county, or is state + city sufficient for pilot?

3. **Municipal code priority**: Is Municode integration worth the effort?
   - Pro: Answers "what does our code say?" directly
   - Con: 26 cities × complex scraping

4. **Historical decisions**: Should we extract/index past council decisions?
   - We have the extraction pipeline (civic-extraction)
   - Could backfill 12 months of decisions into searchable corpus

5. **Preemption logic**: How do we handle state preemption of local control?
   - Housing: State law often preempts local zoning
   - This is high-value context for residents

6. **Update frequency**:
   - Municipal codes: Change ~monthly
   - State codes: Change annually (Jan 1)
   - Federal: Continuous
   - Do we need real-time or is periodic OK?

---

## Recommendation (Draft)

Given pilot timeline (Jan 2025) and San Rafael focus:

### Phase 1: State + Federal (Current)
- `civic-legal` as built - CA bills, federal programs
- Sufficient for "what state law applies to this decision?"

### Phase 2: Add Municipal Code (Post-Pilot)
- San Rafael Municipal Code (via Municode)
- San Rafael General Plan (PDF extraction)
- Proves value before scaling to 26 cities

### Phase 3: Historical Decisions
- Backfill 12 months of San Rafael council decisions
- Index with embeddings for "has this been done before?"

### Phase 4: Scale
- Add remaining pilot cities
- County-level if needed

---

## Open Questions

- [ ] What's the actual user query distribution? (Need pilot data)
- [ ] Is Municode scrapable or do we need partnership?
- [ ] How do we handle PDF-heavy general plans?
- [ ] Should county be in scope for pilot?

---

*This is a draft for team discussion. Please add comments and questions.*
