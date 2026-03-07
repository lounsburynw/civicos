# Final Package Architecture

**Status**: Approved
**Date**: 2026-01-29
**Version**: 2.3 (added civicos-relay package, federation architecture)

---

## Design Principles

1. **Query-centric surface** - Users ask questions, not government levels
2. **Action-oriented** - Every query can lead to action
3. **Feedback loops** - Actions create data that improves future queries
4. **AI as orchestrator** - System proactively connects and coordinates
5. **Hierarchy-aware jurisdictions** - Simple and complex cities use same API
6. **Provider abstraction** - Data sources are pluggable from day one
7. **Coordination is the moat** - The network effect, not the data

---

## The Living Ecosystem Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER                                           │
│                                │                                            │
│                    ┌───────────┴───────────┐                               │
│                    ▼                       ▼                               │
│              ┌──────────┐           ┌──────────┐                           │
│              │  QUERY   │           │  ACTION  │                           │
│              │ (learn)  │           │  (act)   │                           │
│              └────┬─────┘           └────┬─────┘                           │
│                   │                      │                                  │
│                   ▼                      ▼                                  │
│              ┌─────────────────────────────────────┐                       │
│              │         AI ORCHESTRATOR             │                       │
│              │  • Connects similar concerns        │                       │
│              │  • Suggests timing                  │                       │
│              │  • Tracks outcomes                  │                       │
│              │  • Learns what works                │                       │
│              └────────────────┬────────────────────┘                       │
│                               │                                            │
│                               ▼                                            │
│              ┌─────────────────────────────────────┐                       │
│              │         FEEDBACK LOOP               │                       │
│              │  Action outcomes feed back into     │                       │
│              │  recommendations for next user      │                       │
│              └─────────────────────────────────────┘                       │
│                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Five-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USER                                        │
│                    (Claude.ai, ChatGPT, Web)                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    EDGE INTELLIGENCE LAYER                               │
│                    (Personal MCP - user's agent)                         │
│                                                                          │
│   • User context, interests, filtering                                  │
│   • Tiered identity (Easy/Private/Sovereign)                            │
│   • Signing (Nostr-compatible, client-side)                             │
│   • Personalized reasoning ("showing this because...")                  │
│   • See: EDGE_INTELLIGENCE_ARCHITECTURE.md                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    CIVIC COORDINATION PLATFORM                           │
│                    (Jurisdiction MCP + Backend)                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────┐   ┌────────────────┐   ┌──────────────┐   ┌──────────────┐
│ INTELLIGENCE│   │ ORCHESTRATION  │   │ COORDINATION │   │   IMPACT     │
│ LAYER       │──▶│ LAYER          │──▶│ LAYER        │──▶│   LAYER      │
│ (table      │   │ (suggestions,  │   │ (civicos-    │   │              │
│  stakes)    │   │  outcomes)     │   │  relay)      │   │              │
└─────────────┘   └────────────────┘   └──────────────┘   └──────────────┘

0. EDGE INTELLIGENCE (Personal MCP):
   - User-controlled agent, runs in Claude.ai/ChatGPT or locally
   - Queries Jurisdiction MCP for civic data
   - Applies user context for personalization
   - Handles identity and signing (keys never leave user control)
   - See: apps/civicos-personal-mcp/, EDGE_INTELLIGENCE_ARCHITECTURE.md

1. INTELLIGENCE (Jurisdiction MCP):
   - Multi-platform extraction (Legistar, CivicClerk, Granicus)
   - Legislative enrichment (28 state bills, federal programs)
   - SeeClickFix operational complaints (1,340 San Rafael issues)
   - Read-only public civic data via MCP tools

2. ORCHESTRATION (suggestions + outcomes):
   - Proactive suggestions based on user interests and system state
   - Outcome tracking for feedback loop (what coordination worked?)
   - Pattern learning from successful campaigns

3. COORDINATION (civicos-relay):
   - Voice casting, action primitives
   - Subscriptions and event delivery
   - Federation sync between relays
   - WebSocket real-time coordination

4. IMPACT:
   - Empowerment metrics (surveys)
   - Policy influence (decisions changed)
   - Coalition sustainability (repeat coordination)
   - Democratic quality (participation equity)
```

**The Thesis**: Intelligence is table stakes. Coordination is the moat. Edge Intelligence is the user-facing layer that makes both accessible.

---

## Public API

### Query Methods (Learn)

```python
from civicos import CivicOS

c = CivicOS("san-rafael-ca")

# What rules apply to my situation?
c.what_applies(topic, location?) -> RegulatoryStack

# What's been decided before?
c.what_happened(query, since?) -> List[Decision]

# When can I participate?
c.whats_next(topics?, days?) -> List[Meeting]

# Who else cares?
c.whos_with_me(topic) -> Community
```

### Action Methods (Act)

```python
# Start an initiative
c.start_something(
    topic="traffic safety",
    title="Protected bike lane on 4th St",
    description="Near-misses every week...",
    location="4th St & B St"
) -> Initiative

# Add your voice to something
c.add_voice(
    item_type="initiative",  # or "agenda_item", "decision"
    item_id="init_123",
    stance="support",        # support, oppose, question
    comment="As a daily cyclist..."
) -> Voice

# Follow something for updates
c.follow(
    item_type="meeting",     # meeting, initiative, topic, decision
    item_id="mtg_456"
) -> Subscription

# Prepare to participate
c.prepare(
    agenda_item_id="item_789"
) -> Preparation  # Context, talking points, allies, logistics
```

### AI Orchestration Methods

```python
# Get proactive suggestions (AI-driven)
c.suggestions() -> List[Suggestion]
# Returns:
# - "3 others commented on traffic safety this month - coordinate?"
# - "Housing item next Tuesday matches your interests"
# - "Your initiative reached 10 supporters - suggest next steps?"

# Report outcome (closes feedback loop)
c.report_outcome(
    item_id="item_789",
    outcome="passed",          # passed, failed, continued, modified
    notes="Passed 4-1, implementation starts Q2"
) -> Outcome
```

---

## Feedback Loop Architecture

### The Cycle

```
1. USER QUERIES
   c.what_applies("bike lanes")
   c.whats_next(["transportation"])
        │
        ▼
2. SYSTEM RESPONDS (with AI enrichment)
   "Here's the regulatory context..."
   "Meeting Tuesday - 2 others following this"
        │
        ▼
3. USER ACTS
   c.start_something("Protected bike lane on 4th")
   c.add_voice(item_id, "support", comment)
        │
        ▼
4. SYSTEM TRACKS
   - Who acted
   - On what
   - When
   - Context at time of action
        │
        ▼
5. OUTCOME RECORDED
   c.report_outcome(item_id, "passed")
   (or system detects from meeting minutes)
        │
        ▼
6. SYSTEM LEARNS
   - What context led to action?
   - What coordination patterns worked?
   - Which outcomes were achieved?
        │
        ▼
7. FUTURE QUERIES IMPROVED
   "Similar initiatives succeeded when..."
   "Users who cared about X also engaged with Y"
```

### Data Captured at Each Step

```python
# Query event
QueryEvent:
    user_id: str
    jurisdiction: str
    method: str           # "what_applies", "whats_next", etc.
    params: dict
    timestamp: datetime
    results_count: int

# Action event
ActionEvent:
    user_id: str
    jurisdiction: str
    action: str           # "start_something", "add_voice", etc.
    target_type: str      # "initiative", "agenda_item"
    target_id: str
    context: dict         # What queries preceded this?
    timestamp: datetime

# Outcome event
OutcomeEvent:
    item_type: str
    item_id: str
    outcome: str          # "passed", "failed", "continued"
    vote_breakdown: dict  # If available
    participants: List[str]  # Who engaged
    timestamp: datetime
```

---

## Package Structure

The project is organized as a monorepo with multiple packages:

```
civicos/
├── packages/
│   ├── civicos/                    # Core API package
│   │   ├── src/civicos/
│   │   │   ├── __init__.py         # Public API: CivicOS class
│   │   │   ├── context.py          # what_applies()
│   │   │   ├── _internal/          # Internal modules (state, legal, meetings)
│   │   │   └── storage/            # StorageBackend protocol + implementations
│   │   └── tests/
│   │
│   ├── civicos-relay/              # Federation-ready coordination relay
│   │   ├── src/civicos_relay/
│   │   │   ├── voice/              # Keypairs, signing, voice casting
│   │   │   ├── actions/            # Action primitives (commit, complete)
│   │   │   ├── relay/              # Events, subscriptions, delivery
│   │   │   ├── provenance/         # Key age, history, trust signals
│   │   │   ├── identity/           # Relay keypair, peering config
│   │   │   ├── sync/               # Voice sync protocol (federation)
│   │   │   ├── storage/            # Postgres + in-memory backends
│   │   │   └── server/             # Standalone FastAPI server
│   │   ├── schema.sql              # PostgreSQL tables
│   │   └── tests/                  # 30+ tests including multi-relay sync
│   │
│   ├── civicos-extraction/         # Platform parsers
│   │   └── src/civicos_extraction/
│   │       ├── platforms/          # Legistar, CivicClerk, Granicus
│   │       ├── cli/                # Transcription, ingestion CLI
│   │       └── pipeline/           # ETL orchestration
│   │
│   ├── civicos-services/           # Application layer
│   │   └── src/civicos_services/
│   │       ├── api/                # FastAPI REST server
│   │       ├── chat/               # Chat interface
│   │       └── websocket/          # Real-time coordination
│   │
│   └── civicos-config/             # Shared configuration
│       └── src/civicos_config/
│           └── jurisdictions/      # Per-jurisdiction config
│
├── apps/
│   ├── civicos-mcp/                # MCP server (Claude.ai, ChatGPT)
│   │   ├── tools/                  # Tool definitions (registry.py, handlers.py)
│   │   ├── handlers/               # Tool implementation
│   │   ├── server.py               # Container entry point
│   │   ├── modal_mcp.py            # Modal deployment
│   │   └── Dockerfile.mcp          # Docker build
│   │
│   ├── civicos-extension/          # Browser extension (Civic Lens)
│   └── civicos-workspace/          # Vue frontend (DEPRECATED — use Open WebUI)
│
├── data/                           # Local data (gitignored in production)
├── docs/                           # Documentation (MkDocs Material site)
└── scripts/                        # Dev and deployment scripts
```

### Package Responsibilities

| Package | Responsibility |
|---------|----------------|
| `civicos` | Core API (`CivicOS` class), query methods, storage protocol |
| `civicos-relay` | Voice casting, action primitives, subscriptions, federation sync, standalone server |
| `civicos-extraction` | Platform-specific parsers, transcription, ETL pipeline |
| `civicos-services` | REST API, WebSocket, chat interface |
| `civicos-config` | Shared jurisdiction configuration |
| `civicos-mcp` | MCP server for AI assistants |
| `civicos-workspace` | Vue frontend |

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACES                                 │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    │
│   │ Vue Frontend│   │ MCP (Claude)│   │ MCP (ChatGPT)│  │   REST API  │    │
│   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘    │
└──────────┼─────────────────┼─────────────────┼─────────────────┼────────────┘
           │                 │                 │                 │
           ▼                 ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           APPLICATION LAYER                                  │
│         civicos-services (API) + civicos-mcp (AI interface)                 │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │
           ┌──────────────────────────┼──────────────────────────┐
           ▼                          ▼                          ▼
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│    civicos (core)   │   │   civicos-relay     │   │ civicos-extraction  │
│  • Query methods    │   │  • Voice/subscribe  │   │  • Platform parsers │
│  • CivicOS class    │   │  • Federation sync  │   │  • Transcription    │
│  • Storage protocol │   │  • Event routing    │   │  • ETL pipeline     │
└──────────┬──────────┘   └──────────┬──────────┘   └──────────┬──────────┘
           │                         │                         │
           └─────────────────────────┼─────────────────────────┘
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              STORAGE LAYER                                   │
│   ┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────┐  │
│   │    PostgreSQL       │   │     pgvector        │   │  Cloudflare R2  │  │
│   │  (civic data)       │   │  (embeddings)       │   │  (blobs/audio)  │  │
│   └─────────────────────┘   └─────────────────────┘   └─────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## MCP Server (AI Interface)

```python
# civic/mcp.py
from mcp.server import Server
from civicos import CivicOS

server = Server("civic")

# ─────────── QUERY TOOLS ───────────

@server.tool()
def what_applies(jurisdiction: str, topic: str, location: str = None) -> dict:
    """Get regulatory stack for a topic.

    Use when user asks: "What are the rules for...", "Can I...", "Is it legal to..."
    """
    return CivicOS(jurisdiction).what_applies(topic, location)

@server.tool()
def what_happened(jurisdiction: str, query: str, since: str = None) -> list:
    """Search past decisions.

    Use when user asks: "Has the city ever...", "What happened with...", "Any precedent for..."
    """
    return CivicOS(jurisdiction).what_happened(query, since)

@server.tool()
def whats_next(jurisdiction: str, topics: list = None, days: int = 30) -> list:
    """Get upcoming meetings and agendas.

    Use when user asks: "When can I...", "Is there a meeting about...", "How do I participate..."
    """
    return CivicOS(jurisdiction).whats_next(topics, days)

@server.tool()
def whos_with_me(jurisdiction: str, topic: str) -> dict:
    """Find others who care about this topic.

    Use when user asks: "Am I alone in...", "Who else cares about...", "Is anyone working on..."
    """
    return CivicOS(jurisdiction).whos_with_me(topic)

# ─────────── ACTION TOOLS ───────────

@server.tool()
def start_something(
    jurisdiction: str,
    topic: str,
    title: str,
    description: str,
    location: str = None
) -> dict:
    """Start a new initiative.

    Use when user says: "I want to change...", "Someone should...", "Let's get people together..."
    AI should confirm intent before creating.
    """
    return CivicOS(jurisdiction).start_something(topic, title, description, location)

@server.tool()
def add_voice(
    jurisdiction: str,
    item_type: str,
    item_id: str,
    stance: str,
    comment: str
) -> dict:
    """Add user's voice to an item.

    Use when user says: "I support...", "I oppose...", "I want to comment on..."
    AI should help draft comment if requested.
    """
    return CivicOS(jurisdiction).add_voice(item_type, item_id, stance, comment)

@server.tool()
def follow(jurisdiction: str, item_type: str, item_id: str) -> dict:
    """Follow an item for updates.

    Use when user says: "Keep me posted on...", "Let me know when...", "Track this for me..."
    """
    return CivicOS(jurisdiction).follow(item_type, item_id)

@server.tool()
def prepare(jurisdiction: str, agenda_item_id: str) -> dict:
    """Get preparation materials for participating.

    Use when user says: "I'm going to the meeting...", "How do I testify about...", "Help me prepare..."
    Returns: context, talking points, who else is going, logistics.
    """
    return CivicOS(jurisdiction).prepare(agenda_item_id)

# ─────────── ORCHESTRATION TOOLS ───────────

@server.tool()
def get_suggestions(jurisdiction: str, user_id: str = None) -> list:
    """Get proactive suggestions for user.

    AI should call this periodically or at session start to surface opportunities.
    """
    return CivicOS(jurisdiction).suggestions(user_id)

@server.tool()
def report_outcome(
    jurisdiction: str,
    item_id: str,
    outcome: str,
    notes: str = None
) -> dict:
    """Report outcome of a decision/initiative.

    Use when: meeting concluded, vote taken, initiative succeeded/failed.
    This closes the feedback loop and improves future recommendations.
    """
    return CivicOS(jurisdiction).report_outcome(item_id, outcome, notes)
```

---

## Relay Architecture (Federation)

The `civicos-relay` package provides federation-ready coordination infrastructure. It can run integrated with the main backend or as a standalone service.

### Core Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              RELAY                                           │
│                                                                             │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   │
│   │   Voice     │   │   Relay     │   │ Provenance  │   │    Sync     │   │
│   │  Service    │   │  Service    │   │  Service    │   │  Service    │   │
│   │             │   │             │   │             │   │             │   │
│   │ • Cast      │   │ • Subscribe │   │ • Key age   │   │ • Export    │   │
│   │ • Verify    │   │ • Emit      │   │ • History   │   │ • Import    │   │
│   │ • Count     │   │ • Route     │   │ • Quality   │   │ • Dedupe    │   │
│   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   │
│          │                 │                 │                 │           │
│          └─────────────────┴─────────────────┴─────────────────┘           │
│                                     │                                       │
│                          ┌──────────┴──────────┐                           │
│                          │   Storage Backend   │                           │
│                          │  (Postgres / Memory)│                           │
│                          └─────────────────────┘                           │
│                                     │                                       │
│   ┌─────────────────────────────────┴─────────────────────────────────┐   │
│   │                      Relay Identity                                │   │
│   │  • P-256 ECDSA keypair for relay-to-relay authentication          │   │
│   │  • Peer configuration (URLs, namespaces, sync intervals)          │   │
│   └───────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Voice Model

Voices are cryptographically signed expressions of civic interest using secp256k1 Schnorr signatures (BIP-340, Nostr-compatible):

```python
Voice(
    entity="agenda:2026-02-03:item-6a",  # What they're voicing on
    stance=Stance.SUPPORT,                # support | oppose | watching
    public_key="ab3f...",                 # secp256k1 x-only public key (32 bytes)
    signature="...",                      # BIP-340 Schnorr signature (64 bytes)
    timestamp=datetime.utcnow(),
)
```

**Note:** Voices use secp256k1 Schnorr (Nostr-compatible) for user-facing cryptography. Relay-to-relay authentication uses P-256 ECDSA (separate key type).

Key properties:
- **Self-verifying**: Any relay can verify a voice independently
- **Portable**: Voices can sync between relays
- **One voice per key per entity**: Deduplication by `(public_key, entity)`

### Action Model

Actions bridge the gap from signal to outcome. While voices express intent, actions catalyze real-world civic participation:

```python
Action(
    entity="initiative:marin-housing",     # Parent initiative
    action_type=ActionType.WRITTEN_COMMENT,
    target="clerk@marincounty.org",
    deadline=datetime(2026, 2, 14, 17, 0),
    template="...",                         # Comment template
    target_count=30,                        # Goal
)

Commitment(
    action_id="action:marin-housing:written-comment",
    public_key="02ab3f...",
    status=CommitmentStatus.COMMITTED,      # committed | completed | withdrawn
)

Completion(
    action_id="action:marin-housing:written-comment",
    public_key="02ab3f...",
    evidence=EvidenceType.SELF_REPORT,
    completed_at=datetime.utcnow(),
)
```

Key properties:
- **Action types**: written_comment, attend_meeting, public_comment, contact_official, signature, share
- **Progress tracking**: commitments and completions enable "12 committed, 8 completed" visibility
- **Evidence types**: self_report, email_confirmation, attendance_check, verified

See `docs/critical/COORDINATION_PROTOCOL.md` for full action primitive specifications.

### Federation Model

```
┌─────────────────┐     sync     ┌─────────────────┐     sync     ┌─────────────────┐
│  San Rafael     │◄────────────►│  Marin County   │◄────────────►│   California    │
│  Relay          │              │  Relay          │              │   Relay         │
│                 │              │                 │              │                 │
│ city-san-rafael │              │ marin-county    │              │ state-california│
│ namespaces      │              │ namespaces      │              │ namespaces      │
└────────┬────────┘              └────────┬────────┘              └────────┬────────┘
         │                                │                                │
         ▼                                ▼                                ▼
    PostgreSQL                       PostgreSQL                       PostgreSQL
```

**What federates:**
- Voices (signed, portable, deduplicated)
- Events (agenda published, decision made)

**What stays local:**
- Subscriptions (private to each relay)
- Delivery preferences

### Sync Protocol

```
# Export voices for peer sync
GET /sync/voices?since={timestamp}&namespace={prefix}
Response: {
    voices: [Voice...],
    cursor: "next_page",
    relay_id: "relay.civicos.org/san-rafael",
    relay_signature: "..."  # Signed for verification
}

# Import voices from peer
POST /sync/voices
Body: {voices: [...], source_relay: "...", signature: "..."}
Response: {accepted: 42, rejected: 3, duplicates: 12}
```

### Deployment Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **Integrated** | Relay runs within civicos-services | Pilot (single jurisdiction) |
| **Standalone** | Relay runs as separate service | Multi-jurisdiction federation |
| **Federated** | Multiple relays sync with each other | Cross-city coordination |

For pilot: integrated mode. Post-pilot: standalone with federation enabled.

---

---

## Data Model (Living Ecosystem)

```python
# Core entities

@dataclass
class Initiative:
    """User-spawned initiative."""
    id: str
    jurisdiction: str
    creator_id: str
    topic: str
    title: str
    description: str
    location: Optional[str]
    status: str  # "active", "coordinating", "succeeded", "failed", "dormant"
    created_at: datetime
    updated_at: datetime

    # Relationships
    related_agenda_items: List[str]
    related_decisions: List[str]

@dataclass
class Voice:
    """User voice on an item."""
    id: str
    user_id: str
    item_type: str  # "initiative", "agenda_item", "decision"
    item_id: str
    stance: str  # "support", "oppose", "question"
    comment: Optional[str]
    created_at: datetime

@dataclass
class Subscription:
    """User following an item."""
    id: str
    user_id: str
    item_type: str
    item_id: str
    created_at: datetime
    notification_prefs: dict

@dataclass
class Outcome:
    """Recorded outcome of an item."""
    id: str
    item_type: str
    item_id: str
    outcome: str  # "passed", "failed", "continued", "modified"
    details: dict
    recorded_by: str  # user_id or "system"
    recorded_at: datetime

@dataclass
class CoordinationEvent:
    """Record of coordination activity."""
    id: str
    initiative_id: str
    action: str
    participants: List[str]
    plan: dict
    executed_at: Optional[datetime]
    outcome: Optional[str]
```

### Database Schema (SQL)

```sql
-- DECISIONS: High-stakes decisions requiring coordination
CREATE TABLE decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id),
    high_stakes_score INTEGER NOT NULL,
    coordination_status TEXT CHECK (coordination_status IN
        ('flagged', 'planning', 'active', 'completed')),
    decision_date TIMESTAMP NOT NULL,
    outcome_status TEXT CHECK (outcome_status IN
        ('approved', 'denied', 'amended', 'pending')),
    impact_area GEOGRAPHY(POLYGON, 4326),
    created_at TIMESTAMP DEFAULT NOW()
);

-- COORDINATION CAMPAIGNS
CREATE TABLE coordination_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID REFERENCES decisions(id),
    name TEXT NOT NULL,
    status TEXT CHECK (status IN ('planning', 'outreach', 'orchestrating', 'completed')),
    strategy_session_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- CAMPAIGN PARTICIPANTS
CREATE TABLE campaign_participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID REFERENCES coordination_campaigns(id),
    actor_id UUID NOT NULL,
    actor_type TEXT CHECK (actor_type IN
        ('resident', 'org', 'expert', 'official', 'staff', 'media')),
    role TEXT CHECK (role IN ('testifier', 'advisor', 'champion', 'observer')),
    rsvp_status TEXT CHECK (rsvp_status IN
        ('invited', 'maybe', 'yes', 'declined', 'no_response')),
    testimony_allocated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- COORDINATION WINS (for foundation reporting)
CREATE TABLE coordination_wins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID REFERENCES coordination_campaigns(id),
    win_type TEXT CHECK (win_type IN
        ('policy', 'amendment', 'acknowledgment', 'participation', 'coalition')),
    description TEXT NOT NULL,
    evidence_url TEXT,
    visibility TEXT CHECK (visibility IN ('internal', 'coalition', 'public')),
    celebrated_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_decisions_coordination_status ON decisions(coordination_status);
CREATE INDEX idx_decisions_impact_area ON decisions USING GIST(impact_area);
CREATE INDEX idx_campaigns_status ON coordination_campaigns(status);
CREATE INDEX idx_participants_rsvp ON campaign_participants(rsvp_status);
```

---

## Feedback Metrics

### Success Indicators

```python
# What we track to know if the ecosystem is healthy

class EcosystemMetrics:

    # Engagement funnel
    queries_per_day: int              # Top of funnel
    actions_per_day: int              # Middle of funnel
    outcomes_reported_per_week: int   # Bottom of funnel

    # Network effects
    avg_supporters_per_initiative: float
    coordination_events_per_month: int
    cross_initiative_collaboration: int  # Users in multiple initiatives

    # Effectiveness
    initiatives_with_outcomes: float      # % that reached conclusion
    success_rate: float                   # % of outcomes = "passed"
    time_to_outcome: timedelta            # Avg time from creation to outcome

    # Learning
    suggestion_acceptance_rate: float     # % of suggestions acted on
    pattern_prediction_accuracy: float    # Did predicted strategies work?
```

---

## Error Handling & Resilience

Orchestrator modules (`suggestions.py`, `outcomes.py`) use standard Python error handling:

- **Graceful degradation**: If a data source is unavailable, return partial results rather than failing
- **Logging**: All errors logged with context for debugging
- **Idempotency**: Outcome recording is idempotent — re-reporting the same outcome is a no-op

---

## Tactical Escalation Paths

### The "Back to Tahrir" Problem

Movement research (Tufekci, 2017) identifies a critical failure mode: movements that succeed with one tactic keep returning to it even when it stops working.

**Our response**: When campaigns fail, the workflow routes to escalation options rather than END.

### Escalation Options

| Outcome | Next Lever | Time Horizon | Coordination Type |
|---------|-----------|--------------|-------------------|
| **Win** | Track implementation | 6-12 months | Accountability monitoring |
| **Partial** | Next related decision | 1-3 months | Same coalition, new venue |
| **Loss - Appealable** | Board of Supervisors | 30-60 days | Expanded coalition |
| **Loss - Policy** | State legislation | 6-12 months | Regional coalition |
| **Loss - Visibility** | Media campaign | 1-2 weeks | Public pressure |

```python
def route_after_impact(state: CoordinationState) -> Literal["end", "track", "escalate"]:
    """Route based on campaign outcome."""
    if state['outcome_status'] == 'approved':
        return "end"      # Win - celebrate and archive
    elif state['outcome_status'] == 'amended':
        return "track"    # Partial - monitor next decision
    else:
        return "escalate" # Loss - present escalation options
```

---

## Win Recognition System

### Why Wins Matter

Movements sustain through visible wins. Each win demonstrates efficacy and attracts new participants.

### Win Types

| Win Type | Example | Visibility |
|----------|---------|-----------|
| **Policy Win** | Wildfire Fund allocated to vegetation | High - press release |
| **Amendment Win** | Budget item increased after testimony | Medium - coalition email |
| **Acknowledgment Win** | Council member cites testimony | Medium - social share |
| **Participation Win** | 12 testified (vs 0 historical) | Low - internal metric |
| **Coalition Win** | New org joined coordination | Low - network growth |

### Foundation Reporting Integration

```python
def generate_foundation_report(quarter: str) -> dict:
    """Generate quarterly impact report for funders."""
    wins = db.execute("""
        SELECT win_type, COUNT(*) as count,
               array_agg(description) as examples
        FROM coordination_wins
        WHERE created_at >= %(start)s AND created_at < %(end)s
        GROUP BY win_type
    """, quarter_bounds(quarter))

    return {
        "quarter": quarter,
        "wins_by_type": wins,
        "total_campaigns": get_campaign_count(quarter),
        "residents_engaged": get_unique_participants(quarter),
        "policy_changes": [w for w in wins if w['win_type'] == 'policy']
    }
```

---

## Current Package Structure

The codebase has been refactored from a monolithic structure to a multi-package monorepo:

| Package | Purpose | Status |
|---------|---------|--------|
| `packages/civicos/` | Core API (`CivicOS` class), query methods, storage protocol | Active |
| `packages/civicos-relay/` | Voice casting, action primitives, subscriptions, federation sync | Active |
| `packages/civicos-extraction/` | Platform parsers, transcription, ETL | Active |
| `packages/civicos-services/` | REST API, WebSocket, chat | Active |
| `packages/civicos-config/` | Shared jurisdiction configuration | Active |
| `apps/civicos-mcp/` | Jurisdiction MCP - read-only civic data for AI assistants | Active |
| `apps/civicos-personal-mcp/` | Personal MCP - user context, identity, personalization | In Progress |
| `apps/civicos-workspace/` | Vue frontend | Deprecated (use Open WebUI fork) |
| `apps/civicos-extension/` | Browser extension - contextual civic overlay | Active |
| `packages/civicos-client/` | TypeScript/JavaScript client library | Active |
| `packages/civicos-components/` | Svelte UI components | Active |

### Two-MCP Architecture

The MCP layer is split into two distinct servers (see `EDGE_INTELLIGENCE_ARCHITECTURE.md`):

| MCP Type | Package | Purpose |
|----------|---------|---------|
| **Jurisdiction MCP** | `apps/civicos-mcp/` | Read-only public civic data. Meetings, decisions, issues, voice counts. No user state. |
| **Personal MCP** | `apps/civicos-personal-mcp/` | User's edge agent. Context, identity, personalization, signing. Queries Jurisdiction MCP. |

**Why two MCPs?**
- Jurisdiction MCP is the "library" — public data, deployed per-jurisdiction
- Personal MCP is the "librarian" — knows the user, applies their preferences, handles signing
- Separation enables: privacy (user context never sent to Jurisdiction MCP), sovereignty (users can self-host Personal MCP), federation (any Personal MCP can query any Jurisdiction MCP)

### Coordination Layer Split

The coordination functionality is now split between two packages:

| Concern | Package | Rationale |
|---------|---------|-----------|
| **Civic queries** (`what_happened`, `whats_next`) | `civicos` | Core API stays lean |
| **Voice casting, signatures** | `civicos-relay` | Federation-ready, standalone deployable |
| **Action primitives** | `civicos-relay` | Coordination state (commits, completions) |
| **Subscriptions, events** | `civicos-relay` | Can run as separate service |
| **AI orchestration** (suggestions, outcomes) | `civicos` | Standalone modules querying the data layer |

### Relay Package Architecture

The `civicos-relay` package is designed for federation from day one:

```
packages/civicos-relay/src/civicos_relay/
├── voice/          # Keypairs, signing, voice casting
├── actions/        # Action primitives (commit, complete)
├── relay/          # Events, subscriptions, delivery
├── provenance/     # Key age, history, trust signals
├── identity/       # Relay keypair, peering config
├── sync/           # Voice sync protocol (federation)
├── storage/        # Postgres + in-memory backends
└── server/         # Standalone FastAPI server
```

Key design decisions:
1. **Voices are self-verifying** — Enables federation without trust hierarchy
2. **Relay can run standalone** — Other municipalities can deploy their own
3. **Sync protocol is versioned** — `civicos:voice:v1:...` for future compatibility
4. **Storage is pluggable** — Postgres for production, in-memory for tests

---

## Implementation Priority

### CivicOS API Phases

#### Phase 1: Pilot (Jan 2026)
- [ ] Query methods (4)
- [ ] Basic action methods (start_something, add_voice, follow)
- [ ] Simple suggestions (upcoming meetings matching interests)
- [ ] MCP server with all tools

#### Phase 2: Coordination (Mar 2026)
- [ ] prepare() method
- [ ] coordinate() method
- [ ] Coordination planner
- [ ] Outcome tracking

#### Phase 3: Learning (Jun 2026)
- [ ] Pattern learner
- [ ] Strategy suggestions
- [ ] Feedback loop analytics
- [ ] Ecosystem health metrics

### Relay/Coordination Protocol Phases

See `docs/critical/COORDINATION_PROTOCOL.md` for detailed specifications.

#### Phase 1: Nostr Foundation (Complete)
- [x] NIP-01 compliant WebSocket relay
- [x] Civic voice (kind 30800), entity (kind 30801), subscription (kind 30802)
- [x] Provenance tracking (kind 10800)
- [x] Schnorr signing (secp256k1, BIP-340)

#### Phase 2: Action Primitives (Current)
- [ ] Action (kind 30810) — defined tasks with deadlines, templates
- [ ] Commitment (kind 30811) — binding intent to act
- [ ] Completion (kind 30812) — evidence of action
- [ ] Action accounting — progress toward targets

#### Phase 3: Edge Intelligence (Next)
- [ ] Web chat at civicos.org/[jurisdiction]
- [ ] User context stored locally (browser localStorage)
- [ ] Context-aware agent using MCP for knowledge
- [ ] Client-side Nostr signing (NIP-07 support)

#### Phase 4: Full Provenance (Post-Pilot)
- [ ] Physical attestation at civic centers
- [ ] Device attestation via WebAuthn/platform APIs
- [ ] Vouching system (kind 1800)
- [ ] Key linking for migration (kind 1802)

---

## Cost Model (Updated)

### Per-Jurisdiction
| Component | One-time | Monthly |
|-----------|----------|---------|
| Corpus indexing | $2 | $0.10 |
| Decision backfill | $10 | $0 |
| **Total per city** | **$12** | **$0.10** |

### Platform (AI Orchestration)
| Component | Monthly (26 cities) |
|-----------|---------------------|
| Corpus updates | $2.60 |
| Activity monitoring | $5.00 |
| Suggestion generation | $5.00 |
| Coordination planning | $2.00 |
| **Total** | **~$15/month** |

---

*Architecture v2.1 - Living ecosystem with feedback loops and AI orchestration.*
