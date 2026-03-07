# Pilot Roadmap: Decision Awareness Validation

## Timeline Overview

```
Nov-Dec 2025: Technical Optimization (✅ complete)
├── Package consolidation (✅ complete)
├── MCP server architecture (✅ complete)
├── Infrastructure hardening (✅ complete)
└── Frictionless pilot enablement (✅ complete)

Jan-Feb 2026: Infrastructure Migration & Data Readiness (✅ complete)
├── Modal deployment (all services) (✅ complete)
├── Supabase PostgreSQL + pgvector (✅ complete)
├── Full data ingestion for San Rafael (✅ complete)
└── Browser extension + MCP integration (✅ complete)

Mar 2026: Final Preparation & Launch (current)
├── Week 1-2: Pilot user identification + outreach
├── Week 3: Pre-meeting coordination dry run
└── Week 4: Launch pilot with live San Rafael decision

Apr 2026+: Scale or Pivot
├── IF >50% empowerment: Scale to 5-10 decisions/month
│   └── See CIVIC_DASHBOARD_VISION.md for scaling UX direction
└── IF <50% empowerment: Pivot to alternative approach
```

## Completed: Technical Optimization (Nov-Dec 2025)

**Goals** (all complete):
1. ✅ Package consolidation into unified `civicos/` package (see FINAL_PACKAGE_ARCHITECTURE.md)
2. ✅ MCP server integration for Claude Desktop
3. ✅ Coordination infrastructure (relay protocol, voice casting)
4. ✅ Infrastructure migration to Modal (serverless) + Supabase (PostgreSQL)

## Completed: Infrastructure & Data Readiness (Jan-Feb 2026)

**Goals** (all complete):
1. ✅ All services deployed on Modal (MCP, API, relay, vector indexing)
2. ✅ Full San Rafael data corpus in Supabase PostgreSQL
3. ✅ Vector embeddings indexed (~16,786 embeddings)
4. ✅ Browser extension architecture

## Current Phase: Final Preparation & Launch (Mar 2026)

**Goals**:
1. Pilot user identification and outreach
2. Pre-meeting coordination dry run
3. Launch with live San Rafael decision
4. Pilot tooling (outreach templates, facilitation guides)

**Success Criteria**: Zero technical blockers. Residents can access civic intelligence through MCP-enabled AI tools.

---

## Pilot Phase: Decision Awareness Validation (Mar-Apr 2026)

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
- [x] San Rafael SeeClickFix data (1,730 issues)
- [x] Legislative context (state + federal bills)
- [x] Testimony extraction pipeline
- [x] Full PostgreSQL corpus (meetings, decisions, transcripts, chunks, municipal code, budget)
- [x] Vector embeddings (~16,786 for San Rafael)

### Package Architecture
- [x] civicos/: Unified package with CivicOS class
  - StorageBackend, PostgresBackend, PgVectorBackend
  - Legislative matching, MCP integration
  - Relay coordination protocol (voice casting, subscriptions)

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
| No high-stakes decision in March/April | Monitor San Rafael calendar; have backup decisions |
| Low response rate from residents | Over-recruit (contact 20+ to get 5-10) |
| Technical issues during pilot | Run dry-run in early March |
| Cold start delays on Modal | Pre-warm endpoints before pilot sessions |

---

*Created: Session 121 (2024-11-27)*
*Updated: Session 125 (2025-11-29) - Timeline shifted to Jan 2026*
*Updated: 2026-03-07 - Timeline updated to reflect Modal migration complete, pilot launching Mar 2026*
