# User Flow Simulations: Demographic Perspectives

**Purpose**: Identify data requirements by tracing real user journeys
**Method**: Persona → Trigger → Queries → Data Needed → Pain Points

---

## Persona 1: Maria, Renter Facing Displacement

**Demographics**: 34, single mom, renting in San Rafael, works two jobs
**Civic experience**: None - never attended a meeting
**Trigger**: Received notice that landlord is selling building

### User Flow

```
TRIGGER: "My landlord is selling. What are my rights?"

Query 1: "What tenant protections exist in San Rafael?"
  → NEEDS: Municipal Code (rent stabilization, just cause eviction)
  → NEEDS: State law (AB 1482 Tenant Protection Act)

Query 2: "Is there a meeting where I can speak about this?"
  → NEEDS: Upcoming council/commission meetings (civic-state)
  → NEEDS: Agenda items related to housing/tenant rights

Query 3: "Has San Rafael done anything about tenant displacement before?"
  → NEEDS: Historical decisions (past resolutions, ordinances)

Query 4: "What are other cities doing?"
  → NEEDS: Regional comparison (Marin County cities' tenant laws)

Query 5: "Is there funding to help me relocate if I have to move?"
  → NEEDS: Federal programs (Section 8, emergency assistance)
  → NEEDS: State programs (CA Emergency Rental Assistance)
  → NEEDS: Local programs (if any)
```

### Pain Points by Architecture

| Architecture | Pain Point |
|--------------|------------|
| Current | Can't answer Query 1 (no municipal code) |
| Level-specific | Must query 4 packages for full answer |
| Query-centric | Natural fit - "what applies to me?" |

---

## Persona 2: David, Homeowner Concerned About Development

**Demographics**: 58, owns home near proposed development site, retired
**Civic experience**: Moderate - attends meetings occasionally
**Trigger**: Sees construction notice posted on vacant lot nearby

### User Flow

```
TRIGGER: "What's being built next to my house?"

Query 1: "What's the zoning for this parcel?"
  → NEEDS: Municipal zoning code
  → NEEDS: Zoning map (GIS)

Query 2: "What's the approval process for this?"
  → NEEDS: Municipal Code (planning process)
  → NEEDS: State law (CEQA requirements, SB 35 streamlining)

Query 3: "When can I comment on this project?"
  → NEEDS: Planning Commission calendar (civic-state)
  → NEEDS: Public hearing requirements (municipal code)

Query 4: "Can the city even deny this?"
  → NEEDS: State preemption rules (Housing Element law)
  → NEEDS: Builder's Remedy provisions
  → COMPLEX: Requires understanding state/local interaction

Query 5: "What did the city decide on similar projects?"
  → NEEDS: Historical planning decisions
  → NEEDS: Precedent from same neighborhood
```

### Pain Points by Architecture

| Architecture | Pain Point |
|--------------|------------|
| Current | Can't answer zoning (Query 1) or preemption (Query 4) |
| Single package | Works but preemption logic is complex |
| Query-centric | Query 4 is exactly "where does local authority end?" |

---

## Persona 3: Aisha, Environmental Activist

**Demographics**: 27, UC Berkeley grad, works at environmental nonprofit
**Civic experience**: High - regularly attends and testifies
**Trigger**: Wildfire season approaching, wants to advocate for prevention funding

### User Flow

```
TRIGGER: "I want to push for more wildfire prevention funding"

Query 1: "What's in the city budget for fire prevention?"
  → NEEDS: Current city budget (civic-state or civic-decisions)
  → NEEDS: Historical budget allocations

Query 2: "What state programs fund wildfire prevention?"
  → NEEDS: State legislation (CAL FIRE programs, SB 901)
  → NEEDS: Federal programs (FEMA, Forest Service grants)

Query 3: "What has San Rafael committed to vs. actually done?"
  → NEEDS: Past resolutions/commitments (historical decisions)
  → NEEDS: Actual spending (budget documents)
  → COMPLEX: Gap analysis between promise and action

Query 4: "How does San Rafael compare to other Marin cities?"
  → NEEDS: Regional data (county-level or multi-city)
  → NEEDS: Standardized metrics for comparison

Query 5: "Who else in the community cares about this?"
  → NEEDS: Testimony from past meetings (civic-state)
  → NEEDS: Public commenters on related issues
  → THIS IS COORDINATION - our moat
```

### Pain Points by Architecture

| Architecture | Pain Point |
|--------------|------------|
| Current | Query 3 (gap analysis) impossible without decisions |
| Level-specific | Query 4 requires querying multiple city packages |
| Query-centric | "Precedent" module handles Query 3-4 naturally |

---

## Persona 4: James, Small Business Owner

**Demographics**: 45, owns restaurant downtown, immigrant
**Civic experience**: Low - "government is confusing"
**Trigger**: Wants to add outdoor seating, doesn't know where to start

### User Flow

```
TRIGGER: "How do I get a permit for outdoor seating?"

Query 1: "What permits do I need?"
  → NEEDS: Municipal Code (business licenses, encroachment permits)
  → NEEDS: Health department requirements (county level!)
  → NEEDS: ABC if serving alcohol (state level)

Query 2: "How long does this take?"
  → NEEDS: Typical processing times (historical decisions)
  → NEEDS: Current backlog (civic-state if tracked)

Query 3: "How much does it cost?"
  → NEEDS: Fee schedules (municipal code or city website)

Query 4: "Has anyone else done this recently?"
  → NEEDS: Similar permits approved (historical decisions)
  → NEEDS: Contact info? (privacy concerns)

Query 5: "Are there any programs to help small businesses?"
  → NEEDS: Federal (SBA programs)
  → NEEDS: State (GO-Biz, tax credits)
  → NEEDS: Local (facade improvement, permit fee waivers)
```

### Pain Points by Architecture

| Architecture | Pain Point |
|--------------|------------|
| Current | Can't answer ANY of these queries |
| Level-specific | Query 1 requires city + county + state |
| Single package | Natural fit - "permit stack" query |

**KEY INSIGHT**: This user needs COUNTY (health dept) - validates your scope choice.

---

## Persona 5: Linda, Senior on Fixed Income

**Demographics**: 72, retired teacher, owns home, lives alone
**Civic experience**: Used to be active, now finds it hard to attend
**Trigger**: Property tax bill seems high, struggling to pay

### User Flow

```
TRIGGER: "My property taxes are too high. What can I do?"

Query 1: "Are there any exemptions I qualify for?"
  → NEEDS: State law (Prop 13, senior exemptions)
  → NEEDS: County assessor programs (Marin County)
  → NEEDS: City programs (if any rebates)

Query 2: "How do I apply?"
  → NEEDS: County assessor procedures
  → NEEDS: Deadlines and forms

Query 3: "Is there anyone advocating for seniors on this?"
  → NEEDS: Past testimony on property tax issues
  → NEEDS: Senior advocacy groups (coordination)

Query 4: "What's the city doing with my tax money anyway?"
  → NEEDS: City budget breakdown
  → NEEDS: Historical spending trends
```

### Pain Points by Architecture

| Architecture | Pain Point |
|--------------|------------|
| Current | Can't answer property tax questions (county) |
| Level-specific | Query 1 requires state + county + city |
| Query-centric | "What applies to me?" handles this |

---

## Persona 6: Marcus, First-Time Participant

**Demographics**: 31, software engineer, new to San Rafael
**Civic experience**: Zero - voted but never engaged locally
**Trigger**: Frustrated by traffic/bike safety after near-miss

### User Flow

```
TRIGGER: "I almost got hit biking. Who do I complain to?"

Query 1: "Who's responsible for this street?"
  → NEEDS: Street jurisdiction (city vs. county vs. state/Caltrans)
  → COMPLEX: Different streets have different owners

Query 2: "Has anyone else complained about this intersection?"
  → NEEDS: 311/SeeClickFix complaints (civic-state)
  → NEEDS: Collision data (county/state)

Query 3: "Is there a bike plan or something?"
  → NEEDS: General Plan (Circulation Element)
  → NEEDS: Bike/Ped Master Plan (city document)

Query 4: "When is the city talking about bike stuff?"
  → NEEDS: Upcoming meetings (civic-state)
  → NEEDS: Agenda filtering by topic

Query 5: "What would it take to get a protected bike lane?"
  → NEEDS: Municipal Code (street standards)
  → NEEDS: State law (Complete Streets Act)
  → NEEDS: Funding programs (federal, state, local)
  → NEEDS: Past decisions on similar requests
```

### Pain Points by Architecture

| Architecture | Pain Point |
|--------------|------------|
| Current | Query 1 (jurisdiction) unanswerable |
| Level-specific | Query 5 requires all levels |
| Query-centric | "What applies?" + "Precedent" both needed |

---

## Synthesis: Query Patterns Across Personas

### Most Common Query Types

| Query Type | Frequency | Data Required |
|------------|-----------|---------------|
| "What law/rule applies?" | 6/6 personas | Municipal + State + sometimes County |
| "What's been decided before?" | 5/6 personas | Historical decisions |
| "When can I participate?" | 5/6 personas | civic-state (meetings) |
| "Who else cares?" | 4/6 personas | Coordination (our moat) |
| "What funding exists?" | 4/6 personas | Federal + State programs |
| "How does my city compare?" | 3/6 personas | Multi-jurisdiction |

### Data Layer Requirements (by frequency)

```
ESSENTIAL (all personas need):
├── Municipal Code           ← MISSING
├── State Law/Codes         ← Partial (bills only, not codes)
├── Upcoming Meetings       ← Have (civic-state)
└── Historical Decisions    ← MISSING

IMPORTANT (most personas need):
├── Federal Programs        ← Have (civic-legal)
├── County Regulations      ← MISSING
├── General Plans           ← MISSING
└── Coordination Features   ← Have (civic-state)

NICE TO HAVE:
├── Multi-jurisdiction Compare ← Future
├── GIS/Mapping               ← Future
└── Real-time Tracking        ← Future
```

---

## Pain Point Summary by Architecture

### Option A: Single Package (civic-legal expands)

| Pro | Con |
|-----|-----|
| Single query interface | Massive scope |
| Cross-level queries natural | Different update cadences |
| Simpler for users | Complex to maintain |

**Pain points**: Package becomes unwieldy, hard to test

### Option B: Level-Specific Packages

| Pro | Con |
|-----|-----|
| Clean separation | Most queries need 2-3 packages |
| Independent updates | Confusing for users |
| Focused maintenance | Cross-level logic duplicated |

**Pain points**: Every real query requires orchestration layer

### Option C: Canonical vs. Ephemeral

| Pro | Con |
|-----|-----|
| Clear mental model | Users don't think this way |
| Update cadences align | Still need cross-level queries |

**Pain points**: Doesn't match user mental model

### Option D: Query-Centric

| Pro | Con |
|-----|-----|
| Matches user needs exactly | Abstracts government structure |
| "What applies?" is natural | Implementation still needs levels |
| "Precedent" is common query | Harder to maintain data freshness |

**Pain points**: Internal complexity hidden, may confuse power users

---

## Emerging Recommendation

### Hybrid: Query Layer + Data Layer

```
┌─────────────────────────────────────────────────────────────┐
│                    USER-FACING LAYER                        │
│  civic-context     "What law/rule applies to my situation?" │
│  civic-precedent   "What's been decided before?"            │
│  civic-participate "When/where can I engage?" (civic-state) │
│  civic-coordinate  "Who else cares?" (our moat)             │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    DATA LAYER (internal)                    │
│  corpus-federal    US Code, CFR, programs                   │
│  corpus-state      CA Codes, bills, regulations             │
│  corpus-county     County codes, health regs                │
│  corpus-municipal  City codes, general plans                │
│  corpus-decisions  Historical decisions (extracted)         │
└─────────────────────────────────────────────────────────────┘
```

**Key insight**: Users don't care about government levels. They care about:
1. What rules apply to me?
2. What's been done before?
3. When can I participate?
4. Who's with me?

The data layer is an implementation detail.

---

## Questions for Team

1. Does this hybrid approach resonate?
2. Should the data layer packages be internal-only or also exposed?
3. For pilot, which query-layer packages are MVP?
4. How do we handle the "jurisdiction determination" problem (whose street is this)?

---

*Simulations complete. Ready for architecture decision.*
