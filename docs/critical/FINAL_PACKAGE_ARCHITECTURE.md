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

## Four-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CIVIC COORDINATION PLATFORM                           │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────┐   ┌────────────────┐   ┌──────────────┐   ┌──────────────┐
│ INTELLIGENCE│   │ ORCHESTRATION  │   │ COORDINATION │   │   IMPACT     │
│ LAYER       │──▶│ LAYER          │──▶│ LAYER        │──▶│   LAYER      │
│ (table      │   │ (LangGraph)    │   │ (Custom)     │   │              │
│  stakes)    │   │                │   │              │   │              │
└─────────────┘   └────────────────┘   └──────────────┘   └──────────────┘

1. INTELLIGENCE (90% complete):
   - Multi-platform extraction (Legistar, CivicClerk, Granicus)
   - Legislative enrichment (28 state bills, federal programs)
   - SeeClickFix operational complaints (1,340 San Rafael issues)
   - Unified city state database

2. ORCHESTRATION (LangGraph):
   - State machine workflows (flagged → planning → active)
   - Checkpointing (resume after days/weeks)
   - Parallel execution (discover actors concurrently)
   - Human-in-loop (RSVP waiting, approvals)
   - LangSmith observability

3. COORDINATION (Custom):
   - Email/SMS (SendGrid, Twilio)
   - Meeting scheduling (Google Meet, Zoom)
   - PostGIS spatial queries
   - WebSocket real-time coordination

4. IMPACT:
   - Empowerment metrics (surveys)
   - Policy influence (decisions changed)
   - Coalition sustainability (repeat coordination)
   - Democratic quality (participation equity)
```

**The Thesis**: Intelligence is table stakes. Coordination is the moat.

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

# Request coordination
c.coordinate(
    initiative_id="init_123",
    action="schedule_meeting"  # or "draft_letter", "plan_testimony"
) -> CoordinationPlan

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
│   │   │   ├── relay/              # Events, subscriptions, delivery
│   │   │   ├── provenance/         # Key age, history, trust signals
│   │   │   ├── identity/           # Relay keypair, peering config
│   │   │   ├── sync/               # Voice sync protocol (federation)
│   │   │   ├── storage/            # Postgres + in-memory backends
│   │   │   └── server/             # Standalone FastAPI server
│   │   ├── schema.sql              # PostgreSQL tables
│   │   └── tests/                  # 30 tests including multi-relay sync
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
│   │   ├── src/civicos_mcp/
│   │   │   ├── server.py           # FastMCP server
│   │   │   └── tools/              # MCP tool definitions
│   │   └── fly.toml                # Fly.io deployment
│   │
│   └── civicos-workspace/          # Vue frontend
│       ├── src/
│       │   ├── components/         # Vue components
│       │   ├── composables/        # State management
│       │   └── services/           # API clients
│       └── vite.config.ts
│
├── data/                           # Local data (gitignored in production)
├── docs/critical/                  # Architecture documentation
├── scripts/                        # Dev and deployment scripts
└── deploy/                         # Deployment artifacts (Docker, Fly, etc.)
```

### Package Responsibilities

| Package | Responsibility |
|---------|----------------|
| `civicos` | Core API (`CivicOS` class), query methods, storage protocol |
| `civicos-relay` | Voice casting, subscriptions, federation sync, standalone server |
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
def coordinate(jurisdiction: str, initiative_id: str, action: str) -> dict:
    """Request coordination support.

    Use when initiative is ready for collective action.
    Actions: "schedule_meeting", "draft_letter", "plan_testimony", "notify_supporters"
    """
    return CivicOS(jurisdiction).coordinate(initiative_id, action)

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
│   │  • ECDSA keypair for signing events and sync responses            │   │
│   │  • Peer configuration (URLs, namespaces, sync intervals)          │   │
│   └───────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Voice Model

Voices are cryptographically signed expressions of civic interest:

```python
Voice(
    entity="agenda:2026-02-03:item-6a",  # What they're voicing on
    stance=Stance.SUPPORT,                # support | oppose | watching
    public_key="02ab3f...",               # ECDSA public key
    signature="3045...",                  # Signature of entity+stance
    timestamp=datetime.utcnow(),
)
```

Key properties:
- **Self-verifying**: Any relay can verify a voice independently
- **Portable**: Voices can sync between relays
- **One voice per key per entity**: Deduplication by `(public_key, entity)`

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

## LangGraph Workflows

The orchestrator uses **LangGraph** for stateful, multi-step workflows with checkpointing.

### Why LangGraph

| Capability | Benefit |
|------------|---------|
| **State machines** | Complex workflows with conditional branching |
| **Checkpointing** | Resume interrupted workflows, audit trail |
| **Human-in-the-loop** | Pause for user confirmation before actions |
| **Tool calling** | Nodes can call MCP tools |
| **Streaming** | Real-time progress updates |

### Workflow 1: Coordination Workflow

```python
# orchestrator/graphs/coordination.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

class CoordinationState(TypedDict):
    """State passed between coordination nodes."""
    initiative_id: str
    jurisdiction: str
    supporters: List[str]
    coordination_action: str  # "plan_testimony", "draft_letter", etc.
    plan: Optional[CoordinationPlan]
    status: str  # "analyzing", "planning", "awaiting_approval", "executing", "complete"
    human_approved: bool

def create_coordination_graph():
    """
    Coordination workflow:

    START → analyze_initiative → plan_action → [human_approval] → execute → END
                                      ↓
                                 (if rejected)
                                      ↓
                                  revise_plan → [human_approval]
    """
    workflow = StateGraph(CoordinationState)

    # Nodes
    workflow.add_node("analyze_initiative", analyze_initiative)
    workflow.add_node("plan_action", plan_action)
    workflow.add_node("await_approval", await_human_approval)  # Human-in-the-loop
    workflow.add_node("execute", execute_coordination)
    workflow.add_node("revise_plan", revise_plan)

    # Edges
    workflow.set_entry_point("analyze_initiative")
    workflow.add_edge("analyze_initiative", "plan_action")
    workflow.add_edge("plan_action", "await_approval")

    # Conditional: approved or needs revision
    workflow.add_conditional_edges(
        "await_approval",
        lambda s: "execute" if s["human_approved"] else "revise_plan",
        {"execute": "execute", "revise_plan": "revise_plan"}
    )

    workflow.add_edge("revise_plan", "await_approval")
    workflow.add_edge("execute", END)

    return workflow.compile(checkpointer=PostgresSaver(...))
```

### Workflow 2: Suggestion Workflow

```python
# orchestrator/graphs/suggestion.py

class SuggestionState(TypedDict):
    """State for suggestion generation."""
    user_id: str
    jurisdiction: str
    user_interests: List[str]
    user_history: List[dict]
    candidates: List[dict]
    ranked_suggestions: List[Suggestion]

def create_suggestion_graph():
    """
    Suggestion workflow:

    START → gather_context → generate_candidates → rank_by_relevance
              → filter_already_seen → format_output → END
    """
    workflow = StateGraph(SuggestionState)

    workflow.add_node("gather_context", gather_user_context)
    workflow.add_node("generate_candidates", generate_suggestion_candidates)
    workflow.add_node("rank", rank_by_relevance)
    workflow.add_node("filter", filter_seen)
    workflow.add_node("format", format_suggestions)

    workflow.set_entry_point("gather_context")
    workflow.add_edge("gather_context", "generate_candidates")
    workflow.add_edge("generate_candidates", "rank")
    workflow.add_edge("rank", "filter")
    workflow.add_edge("filter", "format")
    workflow.add_edge("format", END)

    return workflow.compile()
```

### Workflow 3: Preparation Workflow

```python
# orchestrator/graphs/preparation.py

class PreparationState(TypedDict):
    """State for meeting preparation."""
    agenda_item_id: str
    jurisdiction: str
    user_id: str
    regulatory_context: dict
    historical_decisions: List[dict]
    allies: List[dict]
    talking_points: List[str]
    logistics: dict

def create_preparation_graph():
    """
    Preparation workflow:

    START → fetch_item → [parallel] → compile_prep → END
                            ├── get_regulatory_context
                            ├── get_historical_decisions
                            ├── find_allies
                            └── generate_talking_points
    """
    workflow = StateGraph(PreparationState)

    workflow.add_node("fetch_item", fetch_agenda_item)
    workflow.add_node("get_context", get_regulatory_context)
    workflow.add_node("get_history", get_historical_decisions)
    workflow.add_node("find_allies", find_allies_attending)
    workflow.add_node("talking_points", generate_talking_points)
    workflow.add_node("compile", compile_preparation)

    workflow.set_entry_point("fetch_item")

    # Parallel execution after fetch
    workflow.add_edge("fetch_item", "get_context")
    workflow.add_edge("fetch_item", "get_history")
    workflow.add_edge("fetch_item", "find_allies")
    workflow.add_edge("fetch_item", "talking_points")

    # All parallel nodes feed into compile
    workflow.add_edge("get_context", "compile")
    workflow.add_edge("get_history", "compile")
    workflow.add_edge("find_allies", "compile")
    workflow.add_edge("talking_points", "compile")

    workflow.add_edge("compile", END)

    return workflow.compile()
```

### LangGraph Nodes (Reusable)

```python
# orchestrator/nodes/detect.py
def detect_decision_importance(state: CoordinationState) -> CoordinationState:
    """
    Score a decision for coordination potential.

    Migrated from src/coordination_graph.py
    """
    score = 0

    # Score by topic
    high_stakes = {"housing": 90, "wildfire": 80, "budget": 70, "parking": 60}
    for topic, points in high_stakes.items():
        if topic in state["decision_type"].lower():
            score += points
            break

    # Score by complaint volume
    complaints = query_complaints(state["jurisdiction"], state["decision_type"])
    if len(complaints) > 100:
        score += 50
    elif len(complaints) > 50:
        score += 30

    return {**state, "decision_score": score}


# orchestrator/nodes/discover.py
def discover_affected_residents(state: CoordinationState) -> CoordinationState:
    """
    Find residents affected by a decision.

    Uses:
    - SeeClickFix complaints (by street/type)
    - Previous commenters on similar items
    - Users following related topics
    """
    residents = []

    # From complaints
    complaints = query_complaints(state["jurisdiction"], state["decision_type"])
    for c in complaints:
        residents.append({"source": "complaint", "address": c["address"]})

    # From previous comments
    commenters = query_previous_commenters(state["jurisdiction"], state["decision_type"])
    for c in commenters:
        residents.append({"source": "commenter", "user_id": c["user_id"]})

    return {**state, "actors": {"residents": residents}}
```

### Actor Taxonomy (6 Types)

The `discover_affected_residents` node queries these actor types:

| Type | Discovery Methods | Routing Criteria | Examples |
|------|------------------|------------------|----------|
| **Residents** | PostGIS radius, SeeClickFix complaints, issue follows | Distance, complaint recency, past engagement | Property owners, renters in impact zone |
| **Advocacy Orgs** | Topic expertise, partnership DB, past campaigns | Subject expertise, jurisdiction, success history | YIMBY, transit groups, housing advocates |
| **Subject Experts** | Credentials, academic affiliations, past testimony | Technical credibility, communication clarity | Fire Chief, urban planners, engineers |
| **Political Champions** | Vote alignment, constituent overlap, public statements | Issue alignment, receptiveness | Councilmembers, Planning Commissioners |
| **Municipal Staff** | Department mapping, staff reports, implementation role | Technical Q&A capacity, accountability | Public Works Director, City Manager |
| **Media** | Beat reporters, past coverage, outlet reach | Topic relevance, visibility goals | Local papers, TV news, community radio |

```python
# orchestrator/nodes/discover.py

class ResidentDiscoveryAgent:
    """Discover affected residents using PostGIS + LLM relevance scoring."""

    def __call__(self, state: CoordinationState):
        residents = []

        # PostGIS spatial query
        residents.extend(self._query_by_radius(state["impact_area"], 2000))

        # SeeClickFix complaints
        residents.extend(self._query_by_complaints(state["decision_type"]))

        # Issue followers
        residents.extend(self._query_by_follows(state["decision_type"]))

        # LLM relevance scoring + dedup
        scored = self._score_relevance(residents, state)
        return {**state, "actors": {"residents": scored[:50]}}
```

### Checkpointing (Production)

```python
# orchestrator/checkpointer.py
from langgraph.checkpoint.postgres import PostgresSaver

def get_checkpointer():
    """Get production checkpointer with PostgreSQL."""
    return PostgresSaver.from_conn_string(
        os.environ.get("DATABASE_URL", "postgresql://localhost/civic")
    )

# Usage in workflow
workflow = create_coordination_graph()
app = workflow.compile(checkpointer=get_checkpointer())

# Resume interrupted workflow
state = app.get_state(config={"configurable": {"thread_id": "campaign-123"}})
if state.values["status"] == "awaiting_approval":
    # User approved, continue
    app.update_state(
        config={"configurable": {"thread_id": "campaign-123"}},
        values={"human_approved": True}
    )
    result = app.invoke(None, config={"configurable": {"thread_id": "campaign-123"}})
```

---

## AI Orchestrator Behavior

### Proactive Suggestions

```python
# orchestrator/suggestions.py

class SuggestionEngine:
    """Generate proactive suggestions based on user context and system state."""

    def generate(self, user_id: str, jurisdiction: str) -> List[Suggestion]:
        suggestions = []

        # 1. Upcoming meetings matching user interests
        interests = self.get_user_interests(user_id)
        meetings = self.get_upcoming_meetings(jurisdiction)
        for meeting in meetings:
            if self.matches_interests(meeting, interests):
                suggestions.append(Suggestion(
                    type="upcoming_meeting",
                    title=f"Meeting on {meeting.date}: {meeting.topic}",
                    reason="Matches your interest in {interest}",
                    action="follow",
                    item_id=meeting.id
                ))

        # 2. Initiatives gaining momentum
        initiatives = self.get_trending_initiatives(jurisdiction)
        for init in initiatives:
            if self.user_might_care(user_id, init):
                suggestions.append(Suggestion(
                    type="trending_initiative",
                    title=f"{init.supporter_count} people supporting: {init.title}",
                    reason="Similar to issues you've engaged with",
                    action="add_voice",
                    item_id=init.id
                ))

        # 3. Coordination opportunities
        user_initiatives = self.get_user_initiatives(user_id)
        for init in user_initiatives:
            if init.supporter_count >= 5 and not init.coordinated:
                suggestions.append(Suggestion(
                    type="coordination_ready",
                    title=f"Your initiative has {init.supporter_count} supporters",
                    reason="Ready to take collective action?",
                    action="coordinate",
                    item_id=init.id
                ))

        # 4. Outcomes to report
        pending_outcomes = self.get_pending_outcomes(user_id)
        for item in pending_outcomes:
            suggestions.append(Suggestion(
                type="outcome_pending",
                title=f"What happened with {item.title}?",
                reason="Meeting was on {item.meeting_date}",
                action="report_outcome",
                item_id=item.id
            ))

        return suggestions
```

### Coordination Planning

```python
# orchestrator/coordinator.py

class CoordinationPlanner:
    """Help groups take collective action."""

    def plan(self, initiative_id: str, action: str) -> CoordinationPlan:
        initiative = self.get_initiative(initiative_id)
        supporters = self.get_supporters(initiative_id)

        if action == "plan_testimony":
            # Find upcoming relevant meeting
            meeting = self.find_relevant_meeting(initiative)

            return CoordinationPlan(
                action="plan_testimony",
                meeting=meeting,
                steps=[
                    Step("Notify supporters", self.draft_notification(supporters, meeting)),
                    Step("Assign speaking slots", self.suggest_speakers(supporters)),
                    Step("Share talking points", self.generate_talking_points(initiative)),
                    Step("Day-of coordination", self.logistics(meeting))
                ],
                supporters=supporters,
                deadline=meeting.public_comment_deadline
            )

        elif action == "draft_letter":
            return CoordinationPlan(
                action="draft_letter",
                steps=[
                    Step("Draft letter", self.generate_letter_draft(initiative)),
                    Step("Collect signatures", self.signature_collection_plan(supporters)),
                    Step("Identify recipients", self.suggest_recipients(initiative)),
                    Step("Send", self.delivery_plan())
                ],
                supporters=supporters
            )
```

### Pattern Learning

```python
# orchestrator/learner.py

class PatternLearner:
    """Learn from outcomes to improve recommendations."""

    def learn_from_outcome(self, outcome: OutcomeEvent):
        # What actions preceded this outcome?
        actions = self.get_preceding_actions(outcome.item_id)

        # What was the context?
        context = self.get_context_at_time(outcome.item_id, actions[0].timestamp)

        # Store pattern
        pattern = Pattern(
            topic=context.topic,
            jurisdiction=context.jurisdiction,
            actions=actions,
            outcome=outcome.outcome,
            participant_count=len(outcome.participants),
            coordination_used=any(a.action == "coordinate" for a in actions)
        )

        self.store_pattern(pattern)

    def get_success_patterns(self, topic: str, jurisdiction: str) -> List[Pattern]:
        """Get patterns that led to successful outcomes."""
        return self.query_patterns(
            topic=topic,
            jurisdiction=jurisdiction,
            outcome="passed"
        )

    def suggest_strategy(self, initiative_id: str) -> Strategy:
        """Suggest strategy based on successful patterns."""
        initiative = self.get_initiative(initiative_id)

        patterns = self.get_success_patterns(
            topic=initiative.topic,
            jurisdiction=initiative.jurisdiction
        )

        if not patterns:
            return Strategy(confidence="low", suggestion="No similar precedent found")

        # Analyze successful patterns
        avg_supporters = mean(p.participant_count for p in patterns)
        used_coordination = sum(1 for p in patterns if p.coordination_used) / len(patterns)

        return Strategy(
            confidence="medium" if len(patterns) > 3 else "low",
            suggestion=f"Similar initiatives succeeded with ~{avg_supporters} supporters",
            recommend_coordination=used_coordination > 0.5,
            similar_successes=patterns[:3]
        )
```

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
    langgraph_thread_id TEXT NOT NULL,
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

### Workflow Error Handling

```python
def handle_error(state: CoordinationState, error: Exception) -> CoordinationState:
    """Global error handler for workflow failures."""
    logger.error(f"Campaign {state['campaign_id']} failed: {error}")

    db.execute("""
        UPDATE coordination_campaigns
        SET status = 'failed', error_message = %(error)s
        WHERE id = %(id)s
    """, {'id': state['campaign_id'], 'error': str(error)})

    return {**state, "status": "failed", "error": str(error)}

app = workflow.compile(
    checkpointer=checkpointer,
    on_error=handle_error
)
```

### Retry Logic

```python
class SendInvitationsNode:
    """Custom node with built-in retry logic."""

    async def __call__(self, state: CoordinationState):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await outreach.send_campaign(...)
                return {**state, "invitations_sent": result['sent_count']}
            except SendGridAPIError:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise
```

### Stalled Campaign Detection

```python
async def check_stalled_campaigns():
    """Alert on campaigns stuck beyond timeout."""
    stalled = db.execute("""
        SELECT c.* FROM coordination_campaigns c
        JOIN checkpoints s ON c.langgraph_thread_id = s.thread_id
        WHERE c.status = 'outreach'
          AND s.next = '["wait_rsvps"]'
          AND s.updated_at < NOW() - INTERVAL '7 days'
    """)

    for campaign in stalled:
        if get_rsvp_count(campaign['id']) < 3:
            await cancel_campaign(campaign['id'], reason='Insufficient RSVPs')
```

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
| `packages/civicos-relay/` | Voice casting, subscriptions, federation sync | Active (new) |
| `packages/civicos-extraction/` | Platform parsers, transcription, ETL | Active |
| `packages/civicos-services/` | REST API, WebSocket, chat | Active |
| `packages/civicos-config/` | Shared jurisdiction configuration | Active |
| `apps/civicos-mcp/` | MCP server for AI assistants | Active |
| `apps/civicos-workspace/` | Vue frontend | Active |

### Coordination Layer Split

The coordination functionality is now split between two packages:

| Concern | Package | Rationale |
|---------|---------|-----------|
| **Civic queries** (`what_happened`, `whats_next`) | `civicos` | Core API stays lean |
| **Voice casting, signatures** | `civicos-relay` | Federation-ready, standalone deployable |
| **Subscriptions, events** | `civicos-relay` | Can run as separate service |
| **LangGraph orchestration** | `civicos` | Tightly coupled to query/action cycle |

### Relay Package Architecture

The `civicos-relay` package is designed for federation from day one:

```
packages/civicos-relay/src/civicos_relay/
├── voice/          # Keypairs, signing, voice casting
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

### Phase 1: Pilot (Jan 2026)
- [ ] Query methods (4)
- [ ] Basic action methods (start_something, add_voice, follow)
- [ ] Simple suggestions (upcoming meetings matching interests)
- [ ] MCP server with all tools

### Phase 2: Coordination (Mar 2026)
- [ ] prepare() method
- [ ] coordinate() method
- [ ] Coordination planner
- [ ] Outcome tracking

### Phase 3: Learning (Jun 2026)
- [ ] Pattern learner
- [ ] Strategy suggestions
- [ ] Feedback loop analytics
- [ ] Ecosystem health metrics

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
