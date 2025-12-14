# SeeClickFix Integration Architecture

**Status**: Draft (Feature Branch)
**Created**: 2025-11-11
**Strategic Shift**: From standalone platform to "SeeClickFix → Civic Power" bridge

---

## Strategic Context

### The Problem
San Rafael (and 340+ US cities) use SeeClickFix for operational issue tracking (potholes, graffiti, trash). SeeClickFix explicitly avoids policy engagement - they're "geared toward bringing a ticket to resolution," redirecting policy discussions to "City Council Meetings" instead.

**Gap**: No bridge between operational complaints and policy participation.

### Our Solution
**"We turn complaints into civic power."**

Read SeeClickFix complaints → Match to council agendas → Add legislative context → Enable collective action → Measure conversion to civic engagement.

---

## 🎯 ORCHESTRATION ARCHITECTURE (Session 94 Strategic Expansion)

### From Pattern Matching to Multi-Actor Coordination

**Original Focus (Sessions 89-93)**: Match operational complaints to agenda items
**Expanded Focus (Session 94+)**: Orchestrate multi-actor campaigns for collective action

**The Insight**: Intelligence (matching) is TABLE STAKES. Coordination (orchestration) is THE MOAT.

### Actor Taxonomy

**The system identifies and routes to six actor types:**

1. **Affected Residents**: People with operational complaints or geographic proximity
   - Discovery: SeeClickFix complaints, address proximity, issue follows
   - Example: 16 residents who reported stormwater issues

2. **Advocacy Organizations**: Groups with technical expertise and organizing capacity
   - Discovery: Issue tags, past participation in similar campaigns
   - Example: Friends of Marin, Housing Action Coalition

3. **Subject Matter Experts**: Professionals with domain knowledge
   - Discovery: LinkedIn, past testimony, professional networks
   - Example: Civil engineer for stormwater, urban planner for housing

4. **Elected Officials**: Political champions who can amplify resident voice
   - Discovery: District mapping, past vote patterns, campaign platforms
   - Example: Councilmember who previously supported climate initiatives

5. **City Staff**: Implementation partners who execute policy
   - Discovery: Department org charts, agenda item presenters
   - Example: Public Works Director for infrastructure decisions

6. **Media**: Platforms for public pressure and narrative shaping
   - Discovery: Beat reporters, local outlets, community journalists
   - Example: Marin Independent Journal reporter covering city government

### Routing Logic: Who Should Coordinate with Whom?

**For a high-stakes decision (e.g., $1.1M wildfire prevention fund):**

```
STEP 1: Detect Decision
- San Rafael City Council agenda item
- $1.1M budget allocation (high-stakes threshold)
- Fire prevention (topic: public safety, environment)

STEP 2: Identify Affected Residents
- 10 residents who reported tree maintenance issues (SeeClickFix)
- 16 residents in high fire risk zones (geographic data)
- 8 residents following environmental issues (platform behavior)
→ 34 potentially affected residents

STEP 3: Identify Expert Resources
- Marin Wildfire Prevention Authority (advocacy org)
- CalFire district chief (subject expert)
- Councilmember Kate Colin (political champion - environmental record)
- Fire Department Chief (city staff)
- Marin IJ city hall reporter (media)

STEP 4: Orchestrate Coordination
Pre-meeting (7 days before):
├─ Notify 34 residents of decision
├─ Invite to strategy session (virtual or in-person)
├─ Connect with Wildfire Prevention Authority for talking points
└─ Brief Councilmember Colin on resident interest

Meeting preparation (3 days before):
├─ Draft aligned testimony (residents + advocacy org collaboration)
├─ Assign testimony order (storytelling arc)
├─ Request fire chief presentation of allocation plan
└─ Invite reporter to cover resident mobilization

At meeting:
├─ 26 residents testify (coordinated, not repetitive)
├─ Advocacy org provides technical data
├─ Councilmember highlights resident engagement
└─ Reporter covers "unprecedented turnout"

Post-meeting:
├─ Track allocation deployment
├─ Notify residents of implementation progress
├─ Measure outcome: Did coordination influence decision?
└─ Document for future campaigns
```

### Coordination Workflows

**Campaign Lifecycle:**

```
1. DETECTION PHASE (System Automated)
   - Agenda item parsing
   - Threshold analysis (budget $, policy impact)
   - Actor identification

2. NOTIFICATION PHASE (System Automated)
   - Resident alerts (affected individuals)
   - Org invitations (relevant advocacy groups)
   - Official briefings (political champions)

3. STRATEGY PHASE (Human-Led, System-Facilitated)
   - Pre-meeting coordination chat
   - Talking point development
   - Testimony assignments
   - Expert resource coordination

4. ACTION PHASE (Hybrid)
   - Testimony delivery (human)
   - Real-time coordination updates (system)
   - Media engagement (human)

5. IMPACT PHASE (System Automated + Human Validation)
   - Outcome tracking (did policy change?)
   - Implementation monitoring (is it happening?)
   - Coalition maintenance (stay engaged for follow-up)
```

### Data Structures for Orchestration

**Extend existing schema with coordination primitives:**

```sql
-- Campaign entity (NEW)
CREATE TABLE coordination_campaigns (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,              -- Links to agenda item
    decision_title TEXT NOT NULL,
    stakes_level TEXT NOT NULL,             -- 'low', 'medium', 'high', 'transformative'
    status TEXT NOT NULL,                   -- 'detecting', 'notifying', 'strategizing', 'acting', 'tracking'
    created_at TEXT NOT NULL,
    meeting_date TEXT,

    -- Metrics
    residents_identified INTEGER DEFAULT 0,
    residents_engaged INTEGER DEFAULT 0,
    testimony_count INTEGER DEFAULT 0,
    outcome_influenced BOOLEAN DEFAULT FALSE,

    FOREIGN KEY (decision_id) REFERENCES agenda_items(id)
);

-- Actor assignment (NEW)
CREATE TABLE campaign_actors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    actor_type TEXT NOT NULL,               -- 'resident', 'advocacy_org', 'expert', 'official', 'staff', 'media'
    actor_id TEXT,                          -- User ID or external entity ID
    actor_name TEXT NOT NULL,
    role_assignment TEXT,                   -- 'testimony', 'technical_support', 'political_champion', etc.
    engagement_status TEXT,                 -- 'invited', 'interested', 'committed', 'participated'

    FOREIGN KEY (campaign_id) REFERENCES coordination_campaigns(id)
);

-- Coordination events (NEW)
CREATE TABLE coordination_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT NOT NULL,
    event_type TEXT NOT NULL,               -- 'strategy_session', 'testimony_prep', 'outcome_review'
    event_date TEXT NOT NULL,
    attendee_count INTEGER DEFAULT 0,
    notes TEXT,

    FOREIGN KEY (campaign_id) REFERENCES coordination_campaigns(id)
);
```

### Success Metrics for Orchestration

**Traditional Metrics (Intelligence Layer):**
- Match rate (complaints → agenda items)
- Legislative context enrichment rate
- Factual accuracy (99.99% target)

**NEW: Orchestration Metrics (Coordination Layer):**
- **Actor identification accuracy**: Did we find the right people?
- **Coordination participation rate**: % of invited actors who engage
- **Testimony alignment**: Coordinated vs. redundant testimony
- **Political champion activation**: Did officials amplify resident voice?
- **Outcome influence**: Did coordination change the decision?
- **Coalition sustainability**: Do coordinated groups stay engaged?

**The North Star**: "Did residents feel empowered to influence high-stakes decisions?"

### Implementation Priorities

**Phase 1 (Current - Sessions 89-93)**: ✅ Intelligence Foundation
- SeeClickFix integration
- AI matching (operational → policy)
- Legislative enrichment

**Phase 2 (Session 95+)**: Orchestration Layer
- Actor identification algorithms
- Notification routing system
- Strategy session coordination tools

**Phase 3 (Pilot)**: Decision Awareness Validation
- Identify one high-stakes San Rafael decision
- Find 5-10 affected residents
- Orchestrate pre-meeting coordination
- Measure: Did it feel empowering?

**Phase 4 (Scale)**: Multi-Actor Expansion
- Advocacy org partnerships
- Expert network development
- Official briefing protocols
- Media engagement playbooks

---

## Three-Tier Engagement Model

### The Complete System

**SeeClickFix integration is Tier 1-2 of a three-tier civic organizing platform.**

#### Tier 1: Operational Discovery (SeeClickFix Integration)
- **Examples**: Potholes, graffiti, broken streetlights
- **Engagement**: Individual complaints → quick fixes (or pattern recognition)
- **Value**: Discovery layer, trust builder, find neighbors who care
- **Timeline**: Days to weeks
- **User journey**: "I see 12 neighbors complained about potholes"
- **Data source**: SeeClickFix API (read-only)

#### Tier 2: Operational → Policy Bridge (SeeClickFix Clusters)
- **Examples**: Speeding complaints → traffic calming, recurring potholes → preventive maintenance budget
- **Engagement**: Small groups (10-30 people)
- **Value**: Connect operational frustration to policy solutions
- **Timeline**: Weeks to months
- **User journey**: "23 speeding complaints reveal need for traffic calming policy discussion"
- **Data source**: SeeClickFix clusters + our agenda matching

#### Tier 3: Pure Policy Issues (Native Tracker - NOT SeeClickFix)
- **Examples**: HOV lane hours, housing shortage, development projects, budget priorities, zoning changes
- **Engagement**: Large coalitions (50-500+ people)
- **Value**: Systemic change, multi-jurisdiction coordination, sustained campaigns
- **Timeline**: Months to years
- **User journey**: "234 commuters organize 6-month campaign for HOV policy change"
- **Data source**: Our native issue tracker (users create these)

### Why This Matters

**Without Tier 3, the app is just:**
- SeeClickFix visualizer (cool but limited)
- Only works if city is unresponsive to operational tickets (fragile assumption)
- Misses issues that SeeClickFix can't handle (policy, multi-jurisdiction, long-term)

**With Tier 3, the app becomes:**
- Civic organizing platform (powerful)
- Works regardless of operational ticket responsiveness (resilient)
- Handles issues that drive sustained engagement (HOV lanes, housing, development)

**Key Insight**: SeeClickFix (Tier 1-2) is the **gateway** to civic engagement. Pure policy issues (Tier 3) are where **real power accumulates**.

### Examples of Tier 3 Issues That Drive Sustained Engagement

**Marin County HOV Lane Hours** (Multi-jurisdiction, county-level):
- Affects thousands of commuters across San Rafael, Novato, Mill Valley
- NOT in SeeClickFix (policy decision, not operational complaint)
- Requires 6-month sustained campaign across multiple meetings
- Coalition building: 234+ residents, data collection, coordinated testimony

**San Rafael Housing Element** (State mandate, city-level):
- 3,165 new homes required by California law
- Draft concentrates units in Canal neighborhood (equity concerns)
- 15+ public hearings over 6 months
- Coalition: YIMBY residents, Canal advocates, environmental groups

**Development Projects** (Neighborhood-specific, planning-level):
- "Stop 200-unit development at 4th & A"
- Requires understanding planning process, state density bonus law, CEQA
- Multi-month campaign through Planning Commission → City Council

**Budget Priorities** (Citywide, fiscal):
- "Shift from reactive pothole patching ($400K/year) to preventive repaving ($800K/year)"
- Requires understanding capital improvement process, long-term fiscal impact
- Pattern recognition from Tier 1 data surfaces this policy question

### User Progression (Ladder of Engagement)

**Month 1**: User discovers app via Tier 1 (operational issue)
- Sarah sees 12 pothole complaints on her street
- Builds trust in platform, finds neighbors

**Month 2**: User engages with Tier 2 (operational → policy bridge)
- Sarah coordinates with 15 neighbors on speeding → traffic calming
- First taste of policy engagement, small group coordination

**Month 3+**: User joins Tier 3 (pure policy campaign)
- Sarah joins 234-person HOV lane coalition
- Sustained multi-month engagement, transformative change

**This progression is the real product** - not just SeeClickFix visualization.

---

## Integration Model: Read-Only Bridge

**Note**: This section describes Tier 1-2 implementation. Tier 3 (pure policy) uses our existing native issue tracker.

### Core Principle
**We augment SeeClickFix, not replace it.**

- ✅ Display SeeClickFix complaints (via Open311 API)
- ✅ Match complaints to policy discussions (our AI)
- ✅ Add legislative context (state bills, federal programs)
- ✅ Enable coordination (our social layer)
- ❌ Don't store/resolve operational tickets (SeeClickFix's domain)

### Why Read-Only?
1. **No competition** with city's paid system ($50K+/year)
2. **No cold start** - leverage existing complaint data
3. **Clear positioning** - we handle civic engagement, they handle resolution
4. **Public utility ethos** - building on open standards (Open311)

---

## Issue Taxonomy

### Two Types of Issues

**Operational Issues** (SeeClickFix Domain)
- Examples: Pothole, graffiti, streetlight, trash pickup
- Resolution: City fixes it (concrete action)
- Engagement: Individual → Government (1:1)
- Timeline: Days to weeks
- **Our handling**: Read-only display, match to policy agendas

**Policy Issues** (Our Domain)
- Examples: Housing affordability, development opposition, transit funding
- Resolution: Policy change through deliberation
- Engagement: Collective → Council (many:many)
- Timeline: Months to years
- **Our handling**: Full CRUD in our database, coordination tools

**Hybrid Issues** (Bridge Cases)
- Examples: "12 pothole complaints" → street repair budget discussion
- **Our handling**: Cluster operational complaints, surface policy question

---

## User Flows

### Flow 1: Operational Complaint → Policy Engagement

**User journey:**
1. Resident reports pothole on SeeClickFix (existing behavior)
2. **Our system** fetches via Open311 API
3. **AI matching**: Links complaint to "Street Repair Budget" agenda item (Feb 6)
4. **Legislative context**: Shows SB-1 gas tax funding (state bill)
5. **Collective action**: "12 neighbors reported potholes - draft joint comment?"
6. **Conversion**: Residents attend meeting, submit comment

**Success metric**: SeeClickFix complaint → council meeting attendance

---

### Flow 2: Policy Campaign Creation

**User journey:**
1. Resident sees development proposal on agenda
2. Creates policy issue in **our system**: "Stop 200-unit development at 4th & A"
3. Invites neighbors via coordination chat
4. System provides legislative context (SB-9 limits on city power)
5. Group drafts collective comment
6. Tracks government response

**Success metric**: Policy issue → coordinated civic action

---

### Flow 3: Discovery (Browsing Neighborhood Issues)

**User journey:**
1. Resident opens map view
2. Sees **operational** issues (from SeeClickFix) + **policy** campaigns (from our DB)
3. Visual distinction: 🔧 operational vs 🏛️ policy
4. Can filter by type, location, status
5. Discovers both "what's broken" and "what's being deliberated"

**Success metric**: Map engagement → issue following/coordination

---

## Technical Architecture

### Data Sources

```
┌─────────────────┐
│  SeeClickFix    │ (Read-Only via Open311 API)
│  Open311 API   │ → Operational complaints
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Civic Digest   │ (Existing)
│  Agenda Parser  │ → Council agendas + items
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  AI Matching    │ (New)
│  Engine         │ → Link complaints to agendas
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Legislative    │ (Existing)
│  Enrichment     │ → State bills, federal programs
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Our Database   │
│  + API Layer    │ → Policy issues, coordination
└─────────────────┘
```

### Database Schema

**No changes to existing `issues` table** - it stores policy issues only.

**New table for SeeClickFix cache** (optional, for performance):

```sql
CREATE TABLE IF NOT EXISTS seeclickfix_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE NOT NULL,          -- SeeClickFix issue ID
    jurisdiction_id TEXT NOT NULL,             -- e.g., 'san-rafael'
    title TEXT NOT NULL,
    description TEXT,
    category TEXT,                             -- e.g., 'pothole', 'graffiti'
    latitude REAL,
    longitude REAL,
    status TEXT,                               -- 'open', 'closed', etc.
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    cached_at TEXT NOT NULL,                   -- When we fetched it
    matched_event_id TEXT,                     -- Link to agenda item
    match_score REAL,
    FOREIGN KEY (matched_event_id) REFERENCES events(id)
);

CREATE INDEX idx_seeclickfix_jurisdiction ON seeclickfix_cache(jurisdiction_id);
CREATE INDEX idx_seeclickfix_location ON seeclickfix_cache(latitude, longitude);
CREATE INDEX idx_seeclickfix_category ON seeclickfix_cache(category);
```

**Note**: Cache is optional. Could also query Open311 API in real-time for fresher data (tradeoff: latency vs. freshness).

### API Integration

**✅ VALIDATED API Endpoint (2025-11-11):**
```python
# SeeClickFix API v2 - CONFIRMED WORKING
BASE_URL = "https://seeclickfix.com/api/v2/issues"

# Filter to San Rafael using place_url parameter
params = {
    'place_url': 'san-rafael',  # City-specific filter
    'per_page': 20,             # Pagination (max 100)
    'page': 1,                  # Page number
}

# Response format:
# {
#   "issues": [...],          # Array of issue objects
#   "metadata": {...},        # Pagination info
#   "errors": []
# }
```

**Spike Results:**
- ✅ API works without authentication
- ✅ Can filter to San Rafael with `place_url='san-rafael'`
- ✅ Returns real-time data (issues from today: 2025-11-11)
- ✅ Categories: Pothole, Illegal Dumping, Stormwater, Street Signs, etc.
- ✅ Geographic data included (lat/lng for mapping)
- ✅ HTML URLs for attribution/linking back to SeeClickFix

**Key API Calls:**
- `GET /requests.json` - Fetch recent issues
- `GET /requests/{id}.json` - Fetch single issue details
- Pagination support needed
- Rate limiting consideration (public API, no auth required)

### AI Matching Logic

**Extend existing agenda matching** (`src/civic_digest.py` agenda integration):

```python
def match_operational_issue_to_agenda(issue: Dict, events: List[Dict]) -> Optional[Match]:
    """
    Match SeeClickFix operational issue to policy agenda item.

    Examples:
    - 'pothole' → 'Street Repair Budget' agenda item
    - 'homeless encampment' → 'Housing Element Update' agenda item
    - 'speeding cars' → 'Vision Zero Policy' agenda item
    """
    # Use same LLM matching logic as complaint→event matching
    # But with operational→policy semantic bridge
    pass
```

**Clustering Logic:**

```python
def cluster_operational_issues(issues: List[Dict]) -> List[Cluster]:
    """
    Group related SeeClickFix issues to surface policy questions.

    Example:
    - 12 pothole complaints on Main St → "Street maintenance backlog"
    - 8 homeless encampment reports → "Housing crisis"
    - 5 speeding complaints in neighborhood → "Traffic safety"
    """
    # Cluster by:
    # 1. Geographic proximity (500m radius)
    # 2. Category similarity (same SeeClickFix category)
    # 3. Temporal proximity (within 30 days)
    pass
```

---

## UX Patterns

### Visual Distinction

**Operational Issues (from SeeClickFix):**
```
🔧 12 pothole complaints on Main St
   Status: City tracking via SeeClickFix

   💡 Related Discussion:
   Street Repair Budget - Feb 6, 6pm

   [See on SeeClickFix] [Draft Joint Comment]
```

**Policy Issues (native to our system):**
```
🏛️ Stop 200-unit development at 4th & A
   23 neighbors joined this campaign

   Next: Planning Commission - Feb 20
   State context: SB-9 limits city power

   [Join Campaign] [Coordination Chat]
```

### Map View

**Dual layer approach:**
- Layer 1: 🔧 Operational issues (SeeClickFix data) - clustered heatmap
- Layer 2: 🏛️ Policy campaigns (our data) - individual markers
- Toggle: Show operational / Show policy / Show both
- Click operational cluster → See policy connection

---

## Success Metrics

### North Star: User Progression Through Three Tiers
**Goal**: Move users from Tier 1 (discovery) → Tier 2 (small action) → Tier 3 (sustained engagement)

### Tier-Specific Metrics

#### Tier 1: Operational Discovery (SeeClickFix)
**Goal**: Get users in the door, build trust, find neighbors

**Metrics**:
- SeeClickFix issue views (discovery)
- Neighbor discovery rate (% who see "X neighbors also reported")
- Cluster recognition ("aha" moment when seeing patterns)
- Trust building (resolved issues marked as success stories)

**Success threshold**: >50 users discover operational clusters in pilot

#### Tier 2: Operational → Policy Bridge
**Goal**: First taste of policy engagement through small wins

**Metrics**:
- Operational clusters that match to policy agendas (match rate)
- Small group coordination (10-30 people per issue)
- Meeting attendance from operational issues
- Policy outcomes from operational patterns (e.g., traffic calming from speeding complaints)

**Success threshold**: >5 examples of operational cluster → policy meeting attendance

#### Tier 3: Pure Policy Issues (Power Layer)
**Goal**: Sustained engagement on transformative issues

**Metrics**:
- Pure policy issues created (HOV lanes, housing, development, budgets)
- Coalition size (50-500+ people per major issue)
- Multi-meeting participation (sustained over months)
- Policy outcomes (HOV hours changed, housing element amended, etc.)

**Success threshold**: >1 campaign with 30+ engaged residents over 3+ months

### Engagement Progression (Key Product Metric)

**The real success metric is user progression:**

```
Tier 1 Entry → Tier 2 Action → Tier 3 Sustained
   (50%)          (20%)           (5%)

100 users → 50 try Tier 1 → 10 engage Tier 2 → 5 join Tier 3 campaign
```

**Why this matters**:
- Tier 1 alone = interesting but low engagement
- Tier 2 alone = small wins but limited scale
- Tier 3 alone = high friction, hard to recruit
- **All three together = ladder of engagement** that meets users where they are

### Supporting Metrics

1. **SeeClickFix integration health** (Tier 1-2):
   - API uptime
   - Issues fetched per day
   - Match rate (% of operational issues matched to agendas)

2. **Engagement funnel** (Across all tiers):
   - Issue views (Tier 1)
   - Coordination chat joins (Tier 2-3)
   - Comment draft starts (Tier 2-3)
   - Meeting RSVPs (Tier 2-3)

3. **Clustering effectiveness** (Tier 1-2):
   - Clusters created per week
   - Avg issues per cluster
   - Policy campaigns spawned from clusters

4. **Policy campaign health** (Tier 3):
   - Active campaigns
   - Average coalition size
   - Campaign duration (want: months, not weeks)
   - Policy outcomes achieved

---

## Implementation Phases

### Phase 0: Validation Spike (This Session)
- ✅ Test Open311 API access for San Rafael
- ✅ Pull 30 days of issues
- ✅ Validate data quality (categories, locations, descriptions)
- ✅ Test basic matching against existing agenda items
- **Decision point**: Proceed or pivot based on data quality

### Phase 1: Read-Only Integration (Week 1)
- Create `seeclickfix_client.py` (Open311 API wrapper)
- Build basic issue fetching + caching
- API endpoint: `GET /api/operational-issues/{jurisdiction_id}`
- Simple frontend display (list view, no matching yet)

### Phase 2: AI Matching (Week 2)
- Extend existing matching logic for operational→policy bridge
- Add matched_event_id to SeeClickFix cache
- Frontend: Show "Related discussion" for matched issues
- Metric: Track match rate

### Phase 3: Clustering (Week 2-3)
- Geographic + categorical clustering logic
- Cluster visualization on map
- "Create policy campaign from cluster" UI
- Metric: Track cluster→campaign conversion

### Phase 4: Santa Venetia Pilot (Week 3-4)
- Filter to Santa Venetia neighborhood
- Demo to neighborhood association
- Measure: Complaint views → meeting attendance
- Iterate based on feedback

### Phase 5: Expand (Month 2+)
- Federation of San Rafael Neighborhoods pitch
- Citywide rollout
- Government partnership conversation

---

## Risks & Mitigations

### Risk 1: SeeClickFix API Unavailable/Rate Limited
**Mitigation**: Cache aggressively, fallback to manual issue entry for policy campaigns

### Risk 2: Poor Data Quality (vague descriptions, bad locations)
**Mitigation**: Phase 0 spike validates this before committing

### Risk 3: Low Match Rate (operational issues don't map to agendas)
**Mitigation**: Focus on clustering + policy campaign creation, not 1:1 matching

### Risk 4: SeeClickFix or City Objects to Integration
**Mitigation**:
- Public API = public data (legally clear)
- Position as augmentation, not replacement
- Offer to donate code to city if valuable

### Risk 5: Users Confused by Dual Issue Types
**Mitigation**:
- Clear visual distinction (🔧 vs 🏛️)
- Onboarding explains "report vs. campaign"
- Metric: Track confusion signals (support requests, abandoned flows)

---

## Open Questions (Updated Post-Spike)

### ✅ Answered
1. **API Access**: ✅ CONFIRMED - public API works, no auth required
2. **San Rafael Data**: ✅ CONFIRMED - real-time issues available
3. **Geographic Data**: ✅ CONFIRMED - lat/lng included for mapping

### Still Open
1. **Caching strategy**: Real-time API calls vs. daily batch fetch?
   - *Recommendation*: Start with daily batch, move to real-time if needed
2. **SeeClickFix attribution**: Do we show "via SeeClickFix" prominently? Link back to their app?
   - *Recommendation*: Yes - show "Reported via SeeClickFix" + link to html_url (good citizen behavior)
3. **Submission flow**: Do we allow submitting NEW issues to SeeClickFix via our UI?
   - *Recommendation*: Phase 2 feature - focus on read-only first
4. **Privacy**: Are all returned issues public?
   - *Observation*: API returned `"private_visibility": false` for all issues, suggests public-only
5. **Categories**: Normalize to our taxonomy or keep SeeClickFix's?
   - *Observation*: San Rafael uses bilingual categories (English/Spanish)
   - *Recommendation*: Keep theirs for display, map to ours for matching logic

### Real San Rafael Examples (2025-11-11)

**Example 1: Pothole → Street Repair Budget**
```
Title: "Pothole/Road Condition"
Description: "Manhole cover popped up by heavy machinery..."
Category: "Pothole/Road Condition / Bache (hoyo)/Condición de Carreteras"
→ Could match to: Street/Infrastructure maintenance agenda items
```

**Example 2: Stormwater → Climate/Infrastructure**
```
Title: "Stormwater Drainage"
Description: "Request to clear drainage area down Jewell Street..."
Category: "Stormwater Drainage / Drenaje de Aguas Pluviales"
→ Could match to: Climate adaptation, infrastructure agenda items
```

**Example 3: Illegal Dumping → Waste Policy**
```
Title: "Illegal Dumping"
Category: "Illegal Dumping / Desecho ilegal"
→ Could match to: Waste management, enforcement policy
```

---

## Phase 5 Analysis Results (November 2025)

**Analysis Complete**: `data/pilot/PHASE5_LONGITUDINAL_ANALYSIS.md`
**Dataset**: 1,340 San Rafael SeeClickFix complaints (2009-2025)

### Key Findings

| Metric | Value | Implication |
|--------|-------|-------------|
| **Total Complaints** | 1,340 | Rich discovery dataset |
| **Platform Adoption** | 90% from 2024-2025 | Recent, growing usage |
| **Resolution Rate** | 6% closed | Massive accountability gap |
| **Stale Issues** | 53% >6 months | Tracking/system failure |
| **Peak Season** | May-November | 2x winter volume |

### Geographic Hotspots for Pilot

| Corridor | Complaints | Dominant Issue |
|----------|-----------|----------------|
| 4th St | 40 | Parking (25%), Trees (18%) |
| 3rd St | 30 | Traffic (33%), Dumping (20%) |
| Lincoln Ave | 27 | Illegal dumping (37%) |
| Mission Ave | 22 | Abandoned vehicles (45%) |

### Policy Feedback Finding

```
Camping complaints:
  Before ordinance (Jan-Mar 2024): 2.7/month
  After ordinances (Sep 2024+):    6.9/month

  3.4x increase AFTER policy with 3-6 month lag
```

**Implication**: Residents continue complaining after policy passes. Decision Awareness can help them track implementation.

### Category Distribution

| Category | Count | % |
|----------|-------|---|
| Traffic/Signal | 224 | 16.7% |
| Street Signs | 146 | 10.9% |
| Camping/Homeless | 112 | 8.4% |
| Parks | 88 | 6.6% |
| Parking Violations | 79 | 5.9% |
| Stormwater | 71 | 5.3% |
| Illegal Dumping | 69 | 5.1% |

### Integration Plan (Next Steps)

1. **Immediate**: Use Phase 5 corridors for resident discovery
2. **Week 1-2**: Match corridor complaints to upcoming agendas
3. **Week 3-4**: Manual pilot with 5-10 residents from 4th St corridor

---

## Related Documentation

- `docs/core/COMMUNITY_CIVIC_PMF_STRATEGY.md` - Overall engagement strategy (to be updated)
- `docs/architecture/FEDERAL_STATE_LEGISLATIVE_CONTEXT_INTEGRATION.md` - Legislative enrichment
- `docs/strategy/FOCAL_POINT_DECISION_AWARENESS.md` - Pilot strategy with Phase 5 data
- `docs/architecture/COORDINATION_ORCHESTRATION_ARCHITECTURE.md` - LangGraph orchestration
- `data/pilot/PHASE5_LONGITUDINAL_ANALYSIS.md` - Complete Phase 5 analysis
- `src/agenda_integration.py` - Existing AI matching logic to extend

---

## Success Criteria for This Feature Branch

**Phase 0 (COMPLETE ✅):**
- ✅ API validated - working with real San Rafael data
- ✅ Architecture documented
- ✅ Example operational→policy matches identified

**Remaining merge criteria:**
1. ⏳ Build `seeclickfix_client.py` (API wrapper)
2. ⏳ Create backend endpoint `/api/operational-issues/{jurisdiction}`
3. ⏳ Frontend display (map + list view)
4. ⏳ AI matching operational→agenda items (>20% match rate)
5. ⏳ Clear UX distinction operational vs. policy issues
6. ⏳ Santa Venetia pilot shows >0 complaint→meeting conversions
7. ⏳ Documentation updated (CLAUDE.md, PMF strategy) - **IN PROGRESS**

**Failure criteria** (pivot or abandon):
- ❌ Open311 API blocked/unavailable - **PASSED ✅**
- ❌ Data quality too poor to match (<5% match rate) - **DATA LOOKS GOOD ✅**
- ❌ Legal/political objection from city
- ❌ Zero user interest in operational→policy bridge
