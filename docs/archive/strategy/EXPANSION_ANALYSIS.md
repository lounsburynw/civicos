# Expansion Analysis: Beyond the Pilot

**Question**: Is the proposed architecture sustainable for expansion?
**Method**: Stress-test against realistic expansion scenarios

---

## Expansion Dimensions

| Dimension | Pilot (Jan 2025) | Year 1 | Year 3 |
|-----------|------------------|--------|--------|
| Cities | 1 (San Rafael) | 26 (Bay Area) | 500+ (National) |
| States | 1 (CA) | 1 (CA) | 50 |
| Users | 50 | 5,000 | 500,000 |
| Contributors | 1 (you) | 5 | 50+ |
| Data Sources | 3 | 10 | 50+ |

---

## Scenario 1: Adding 25 More California Cities

**Task**: Scale from San Rafael to all 26 pilot cities

### What Works

```python
# Provider abstraction handles multiple cities cleanly
from civic import Civic

# Same API, different config
sr = Civic("san-rafael-ca")
berkeley = Civic("berkeley-ca")
oakland = Civic("oakland-ca")

# Each loads its own jurisdiction config
# config/jurisdictions/berkeley-ca.yaml
# config/jurisdictions/oakland-ca.yaml
```

### What Breaks

| Issue | Solution |
|-------|----------|
| 26 config files to maintain | Config inheritance: `extends: _california_defaults.yaml` |
| Provider varies by city | Already handled by provider abstraction |
| Testing 26 cities | Golden test (SR) + config-only tests for others |
| ChromaDB scaling | Single index with jurisdiction metadata filter |

### Verdict: ✅ Architecture handles this well

---

## Scenario 2: Adding Texas (New State)

**Task**: Expand beyond California to Texas

### What Works

```python
from civic import Civic

austin = Civic("austin-tx")
austin.what_applies("accessory dwelling unit")
# Returns TX state law + Austin municipal code
```

### What Breaks

| Issue | Severity | Solution |
|-------|----------|----------|
| TX state codes different structure | Medium | Add `_corpus/state/texas.py` with TX-specific parsing |
| TX has no Housing Element mandate | Low | Feature flags per state in config |
| Different terminology | Medium | Synonym mapping in search layer |
| Contributor needs TX legal knowledge | High | Documentation + legal review process |

### Required Changes

```python
# New state requires:
# 1. State corpus provider
civic/_corpus/state/texas.py

# 2. State-specific config defaults
config/states/tx.yaml:
  terminology:
    "accessory dwelling unit": ["ADU", "granny flat", "secondary unit"]
  preemption_rules: []  # TX has few state mandates

# 3. Documentation for contributors
docs/contributing/adding-a-state.md
```

### Verdict: ⚠️ Requires new code, but architecture accommodates it

**Sustainability factor**: Each new state = ~40 hours of work (legal research + code)

---

## Scenario 3: Adding NYC (Complex Jurisdiction)

**Task**: Support New York City's complex structure

### NYC Structure
```
NYC
├── Mayor
├── City Council (51 members)
├── 5 Borough Presidents
├── 59 Community Boards
├── Multiple agencies (DOB, HPD, etc.)
└── State oversight (Albany)
```

### What Breaks

| Issue | Severity | Solution |
|-------|----------|----------|
| Multi-level city government | High | `jurisdiction` model needs hierarchy |
| Community boards have real power | High | Sub-jurisdiction support |
| Agency-specific decisions | Medium | Expand decision sources |
| Sheer volume of meetings | Medium | Filtering + prioritization |

### Required Architecture Changes

```python
# Current: flat jurisdiction
Civic("san-rafael-ca")

# Needed: hierarchical jurisdiction
Civic("nyc-ny")  # City-wide
Civic("nyc-ny/manhattan")  # Borough
Civic("nyc-ny/manhattan/cb7")  # Community board

# Or: jurisdiction with context
Civic("nyc-ny", scope="community_board", district="manhattan-7")
```

```yaml
# config/jurisdictions/nyc-ny.yaml
jurisdiction:
  id: nyc-ny
  type: complex_city  # New type
  hierarchy:
    - level: city
      body: city_council
    - level: borough
      bodies: [manhattan, brooklyn, queens, bronx, staten_island]
    - level: community_board
      count: 59
```

### Verdict: ❌ Current architecture breaks. Needs hierarchy support.

**Recommendation**: Design for hierarchy now, even if pilot doesn't use it.

```python
# Simple API that hides complexity
c = Civic("san-rafael-ca")  # Simple city, works as-is

c = Civic("nyc-ny")  # Complex city
c.what_applies("zoning", location="123 W 72nd St")
# System determines: this is Manhattan CB7, returns relevant decisions
```

---

## Scenario 4: 50 Open-Source Contributors

**Task**: Scale contributor base from 1 to 50

### What Works

```
# Clear contribution paths
1. Add a city (config only) → Easy
2. Add a provider (Municode alternative) → Medium
3. Add a state → Hard (needs review)
4. Core architecture changes → Requires maintainer
```

### What Breaks

| Issue | Severity | Solution |
|-------|----------|----------|
| No contribution docs | High | Write `CONTRIBUTING.md` |
| No provider interface spec | High | Document provider contract |
| Legal review bottleneck | High | Community legal advisors |
| Quality varies by contributor | Medium | CI checks + golden tests |

### Required for Contributor Scale

```markdown
# docs/contributing/

## Adding a City (Easy)
1. Copy `config/jurisdictions/_template.yaml`
2. Fill in jurisdiction details
3. Run `civic validate austin-tx`
4. Submit PR

## Adding a Provider (Medium)
1. Implement `civic._corpus.providers.base.Provider`
2. Add tests against real API
3. Document rate limits and auth

## Adding a State (Hard)
1. Research state legal structure
2. Implement state corpus
3. Legal review required
4. Add state-specific tests
```

### Verdict: ⚠️ Architecture is fine, but needs documentation + process

---

## Scenario 5: 500,000 Users

**Task**: Scale from 50 pilot users to 500K

### Current Assumptions
- ChromaDB: Local, single instance
- PostgreSQL: Local, single instance
- No caching layer
- No CDN

### What Breaks at Scale

| Component | Limit | Solution |
|-----------|-------|----------|
| ChromaDB | ~1M vectors before slowdown | Shard by state |
| PostgreSQL | Depends on query patterns | Read replicas |
| API | No rate limiting | Add rate limiting |
| Cold start | First query per city is slow | Warm cache on deploy |

### Scaling Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         CDN                                 │
│            (Cache static corpus data)                       │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────┴───────────────────────────────────┐
│                      API Gateway                            │
│              (Rate limiting, auth)                          │
└─────────────────────────┬───────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         │                │                │
         ▼                ▼                ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐
    │ Worker  │     │ Worker  │     │ Worker  │
    │   1     │     │   2     │     │   N     │
    └────┬────┘     └────┬────┘     └────┬────┘
         │                │                │
         └────────────────┼────────────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
        ┌──────────┐           ┌──────────┐
        │ Postgres │           │ ChromaDB │
        │ Primary  │           │ Cluster  │
        └────┬─────┘           └──────────┘
             │
        ┌────┴────┐
        ▼         ▼
    ┌───────┐ ┌───────┐
    │Replica│ │Replica│
    └───────┘ └───────┘
```

### Verdict: ⚠️ Architecture is fine, but deployment topology changes

**Key insight**: The code doesn't change, the infrastructure does. Good sign.

---

## Scenario 6: Adding New Feature (Coalition Formation)

**Task**: Add v2 feature `form_coalition()` without breaking v1

### What Works

```python
# v1 API unchanged
c.what_applies(...)
c.what_happened(...)
c.whats_next(...)
c.whos_with_me(...)

# v2 additions
c.form_coalition(issue_id="traffic-123")
c.coordinate_action(coalition_id="coal-456")
```

### What Could Break

| Issue | Severity | Solution |
|-------|----------|----------|
| Database schema changes | Medium | Migration system (Alembic) |
| New dependencies | Low | Optional dependencies `civic[coalitions]` |
| API versioning | Low | Additive changes only, no breaking |

### Verdict: ✅ Additive features are clean

---

## Architecture Gaps Identified

### Must Fix Before Expansion

| Gap | Impact | Fix |
|-----|--------|-----|
| Flat jurisdiction model | Blocks NYC, LA, Chicago | Add hierarchy support |
| No contribution docs | Blocks contributors | Write docs |
| No provider interface spec | Blocks new data sources | Define interface |
| Single ChromaDB | Blocks 500K users | Design sharding strategy |

### Should Fix (Not Blocking)

| Gap | Impact | Fix |
|-----|--------|-----|
| No state inheritance | Repetitive config | Add `extends:` |
| No config validation | Bad PRs | Add `civic validate` CLI |
| No legal review process | Liability | Document process |

---

## Revised Architecture for Expansion

```python
civic/
├── src/civic/
│   ├── __init__.py
│   │
│   ├── # Public API (stable)
│   ├── context.py          # what_applies()
│   ├── history.py          # what_happened()
│   ├── calendar.py         # whats_next()
│   ├── together.py         # whos_with_me(), form_coalition() [v2]
│   │
│   ├── # Jurisdiction model (needs hierarchy)
│   ├── jurisdiction/
│   │   ├── base.py         # Jurisdiction base class
│   │   ├── simple.py       # San Rafael, Berkeley (flat)
│   │   ├── complex.py      # NYC, LA (hierarchical)
│   │   └── loader.py       # Load from config
│   │
│   ├── # Corpus layer (provider-based)
│   ├── _corpus/
│   │   ├── providers/
│   │   │   ├── base.py     # Provider interface ← DOCUMENT THIS
│   │   │   ├── municode.py
│   │   │   ├── american_legal.py
│   │   │   └── leginfo.py  # CA state
│   │   ├── state/
│   │   │   ├── california.py
│   │   │   └── texas.py    # Future
│   │   └── municipal/
│   │       └── generic.py  # Works with any provider
│   │
│   ├── _decisions/
│   └── _activity/
│
├── config/
│   ├── states/             # State-level defaults
│   │   ├── ca.yaml
│   │   └── tx.yaml
│   └── jurisdictions/      # City configs (inherit from state)
│       ├── san-rafael-ca.yaml
│       └── nyc-ny.yaml     # Uses complex jurisdiction
│
└── docs/
    └── contributing/       # Contributor docs
        ├── adding-a-city.md
        ├── adding-a-provider.md
        └── adding-a-state.md
```

---

## Sustainability Score

| Dimension | Score | Notes |
|-----------|-------|-------|
| More CA cities | ✅ 5/5 | Config only |
| New states | ⚠️ 3/5 | Needs state corpus code |
| Complex cities (NYC) | ❌ 2/5 | Needs hierarchy support |
| More contributors | ⚠️ 3/5 | Needs docs |
| More users | ⚠️ 4/5 | Infra changes, code stable |
| New features | ✅ 5/5 | Additive API |

**Overall: 3.7/5** - Sustainable with one architectural fix (jurisdiction hierarchy)

---

## Recommendation

**For pilot (Jan 2025)**: Current architecture is fine.

**Before Year 1 expansion**:
1. Add jurisdiction hierarchy support (for future NYC/LA)
2. Write contributor documentation
3. Define provider interface spec

**Before Year 3 expansion**:
1. Sharding strategy for ChromaDB
2. Legal review process for new states
3. API versioning strategy

---

*Expansion analysis complete. Architecture is sustainable with noted fixes.*
