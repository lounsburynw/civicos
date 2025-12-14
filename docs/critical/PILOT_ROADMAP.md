# Pilot Roadmap: Decision Awareness Validation

## Timeline Overview

```
Nov-Dec 2025: Technical Optimization (current)
├── Package consolidation (✅ complete)
├── MCP server architecture
├── Infrastructure hardening
└── Frictionless pilot enablement

Jan 2026: Pilot Execution (planned)
├── Week 1: Identify high-stakes decision
├── Week 2: Identify 5-10 affected residents
├── Week 3: Pre-meeting coordination
└── Week 4: Measure empowerment + document

Feb 2026+: Scale or Pivot
├── IF >50% empowerment: Scale to 5-10 decisions/month
└── IF <50% empowerment: Pivot to alternative approach
```

## Current Phase: Technical Optimization (Nov-Dec 2025)

**Rationale**: Holiday period (Thanksgiving, Christmas, New Year) makes resident coordination impractical. Using this time to ensure pilot infrastructure is frictionless.

**Goals**:
1. ✅ Package consolidation into unified `civic/` package (see FINAL_PACKAGE_ARCHITECTURE.md)
2. MCP server integration for Claude Desktop / LangGraph
3. Coordination workflow hardening (detect → discover → route)
4. Pilot tooling (resident identification, outreach templates)

**Success Criteria**: When pilot starts in January, zero technical blockers.

---

## Pilot Phase: Decision Awareness Validation (Jan 2026)

### Week 1: Decision Identification
- Identify high-stakes San Rafael decision:
  - Budget allocation >$500K, OR
  - Development >50 units, OR
  - Broad policy change
- Document decision context, timing, stakeholders

### Week 2: Resident Discovery
- Use SeeClickFix data to identify affected residents
- Cross-reference with geographic proximity
- Target: 5-10 residents minimum
- Outreach via email/phone (requires manual effort)

### Week 3: Coordination Execution
- Pre-meeting strategy session (60 min, virtual)
- Provide legislative context + aligned talking points
- Coordinate testimony (avoid redundancy)

### Week 4: Measurement
- **Primary metric**: Empowerment score >3.5/5
  - "I felt more capable of influencing the outcome"
- **Secondary metrics**:
  - Attendance rate (of those contacted)
  - Testimony alignment (coherent vs. scattered)
  - Post-meeting sentiment

---

## Success/Failure Criteria

| Outcome | Threshold | Action |
|---------|-----------|--------|
| **Success** | >50% report empowerment (>3.5/5) | Scale to 5-10 decisions/month |
| **Partial** | 30-50% empowerment | Iterate on approach, retry |
| **Failure** | <30% empowerment | Pivot to accountability tracking |

---

## Technical Readiness Checklist

### Data Layer
- [x] 26 cities extracting events
- [x] San Rafael SeeClickFix data (1,340 complaints)
- [x] Legislative context (state bills + federal programs)
- [x] Testimony extraction pipeline

### Package Architecture
- [x] civic/: Unified package with Civic class
  - StateManager, Legistar/CivicClerk clients
  - Legislative matching, MCP integration
  - LangGraph coordination workflow

### Coordination Infrastructure
- [x] detect_decision node (scoring logic)
- [x] discover_residents node (issue queries)
- [ ] route_to_residents node (outreach)
- [ ] track_outcomes node (post-meeting)

### Pilot Tooling
- [ ] Resident outreach templates
- [ ] Pre-meeting facilitation guide
- [ ] Empowerment survey instrument
- [ ] Case study documentation template

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| No high-stakes decision in January | Monitor San Rafael calendar now; have backup cities |
| Low response rate from residents | Over-recruit (contact 20+ to get 5-10) |
| Technical issues during pilot | Run dry-run in late December |
| Holidays extend into January | Start outreach Jan 6th (after New Year) |

---

*Created: Session 121 (2024-11-27)*
*Updated: Session 125 (2025-11-29) - Timeline shifted to Jan 2026*
*Next update: After pilot completion (late January 2026)*
