# Coordination Orchestration Architecture

**Created**: 2025-11-23
**Updated**: 2025-11-23 (Agent Framework Integration)
**Status**: Design Document
**Priority**: CRITICAL - This is the moat, not intelligence layer

---

## Executive Summary

**The Thesis**: Intelligence is table stakes. Coordination is the moat.

This document defines the complete architecture for the coordination layer - the 70% of the platform that's missing and differentiates us from ChatGPT, citymeetings.nyc, and municipal websites.

**Key Architectural Decision**: Use **LangGraph** for workflow orchestration + **custom integrations** for human coordination. This is multi-agent orchestration where humans are some of the agents.

**Core Capabilities**:
1. **Decision Detection**: Automatically identify high-stakes decisions requiring coordination
2. **Actor Discovery**: Find all affected residents, advocacy orgs, experts, officials
3. **Outreach & Mobilization**: Email/SMS campaigns, RSVP tracking, reminder automation
4. **Pre-Meeting Orchestration**: Strategy sessions, talking point allocation, coalition alignment
5. **Day-Of Coordination**: Live testimony queue, real-time messaging, meeting sync
6. **Outcome Tracking**: Decision capture, implementation monitoring, accountability dashboard

**Gap Analysis**:
- Intelligence Layer: 90% complete (over-invested)
- Coordination Layer: 30% complete (the moat)
- This document defines the remaining 70%

**Architectural Approach**:
- **LangGraph**: State machine orchestration, checkpointing, observability
- **Custom Code**: Email/SMS, meetings, database, PostGIS, surveys
- **Hybrid Benefits**: Proven agent patterns + human coordination reality

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Agent Orchestration Architecture](#2-agent-orchestration-architecture)
3. [Decision Awareness Pipeline](#3-decision-awareness-pipeline)
4. [Actor Discovery & Routing](#4-actor-discovery--routing)
5. [Data Model](#5-data-model)
6. [API Architecture](#6-api-architecture)
7. [Implementation Roadmap](#7-implementation-roadmap)
8. [Integration Points](#8-integration-points)
9. [Technical Specifications](#9-technical-specifications)
10. [Error Handling & Resilience](#10-error-handling--resilience)
11. [Tactical Escalation Paths](#11-tactical-escalation-paths)
12. [Win Recognition System](#12-win-recognition-system)
13. [Success Metrics](#13-success-metrics)
14. [Next Steps](#14-next-steps)

---

## 1. System Overview

### 1.1 Four-Layer Architecture (Updated)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CIVIC COORDINATION PLATFORM                           │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────┐   ┌────────────────┐   ┌──────────────┐   ┌──────────────┐
│ INTELLIGENCE│   │ ORCHESTRATION  │   │ COORDINATION │   │   IMPACT     │
│ LAYER       │──▶│ LAYER          │──▶│ LAYER        │──▶│   LAYER      │
│ (TABLE      │   │ (LangGraph)    │   │ (Custom)     │   │              │
│  STAKES)    │   │ NEW ✨         │   │              │   │              │
└─────────────┘   └────────────────┘   └──────────────┘   └──────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ 1. INTELLIGENCE LAYER (What You Have - 90%)                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐             │
│  │  Multi-      │    │  Legislative │    │  SeeClickFix │             │
│  │  Platform    │───▶│  Enrichment  │◀───│  Operational │             │
│  │  Extraction  │    │  (28 bills)  │    │  Complaints  │             │
│  └──────────────┘    └──────────────┘    └──────────────┘             │
│         │                    │                    │                     │
│         └────────────────────┼────────────────────┘                     │
│                              ▼                                           │
│                    ┌──────────────────┐                                 │
│                    │  Unified City    │                                 │
│                    │  State Database  │                                 │
│                    └──────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ 2. ORCHESTRATION LAYER (LangGraph) - NEW ✨                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────┐            │
│  │  LangGraph State Machine                               │            │
│  │  • Workflow states (flagged → planning → active)       │            │
│  │  • Conditional routing (if RSVP < 5, cancel)           │            │
│  │  • Parallel execution (discover actors concurrently)   │            │
│  │  • Checkpointing (resume after days/weeks)             │            │
│  │  • Human-in-loop (wait for RSVPs, approvals)           │            │
│  └────────────────────────────────────────────────────────┘            │
│                                                                          │
│  AI Agents (LangGraph Nodes):                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │  Decision    │  │  Actor       │  │  Complaint   │                 │
│  │  Detector    │  │  Discovery   │  │  Matcher     │                 │
│  │  Agent       │  │  Agent       │  │  Agent       │                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
│                                                                          │
│  Custom Integration Nodes:                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │  Email       │  │  Schedule    │  │  Survey      │                 │
│  │  Outreach    │  │  Meeting     │  │  Delivery    │                 │
│  │  (SendGrid)  │  │  (Google)    │  │  (Custom)    │                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
│                                                                          │
│  Observability (LangSmith):                                             │
│  • Trace campaign execution                                             │
│  • Debug coordination failures                                          │
│  • Monitor RSVP conversion rates                                        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ 3. COORDINATION LAYER (Custom Integrations)                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Email/SMS:           Meetings:           Database:                     │
│  • SendGrid          • Google Meet        • Postgres + PostGIS          │
│  • Twilio            • Zoom API           • Campaign state              │
│  • Templates         • Calendar           • Actor data                  │
│                                                                          │
│  Surveys:            Spatial:             Real-time:                    │
│  • Typeform          • PostGIS queries    • WebSocket                   │
│  • Response track    • Geographic match   • Live coordination           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ 4. IMPACT LAYER                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  • Empowerment metrics (surveys, testimonials)                          │
│  • Policy influence (decisions changed, allocations shifted)            │
│  • Coalition sustainability (repeat coordination, growth)               │
│  • Democratic quality (participation equity, informed engagement)       │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Why Agent Orchestration?

**This IS Multi-Agent Coordination**:

```
TRADITIONAL VIEW                      AGENT FRAMEWORK VIEW
═══════════════════════════════════   ═══════════════════════════════════
Coordination platform                 Multi-agent orchestration system

Actors:                               Agents:
• Residents                           • Human agents (with goals)
• Advocacy orgs                       • Institutional agents (expertise)
• Officials                           • Political agents (alignment)
• Platform coordinator                • Orchestrator agent (workflow)

Tasks:                                Agent Tasks:
• Decision detection                  • Task: Find high-stakes decisions
• Actor discovery                     • Task: Find affected residents
• Outreach                            • Task: Invite and track RSVPs
• Strategy session                    • Task: Facilitate coordination
• Testimony allocation                • Task: Assign talking points
• Outcome tracking                    • Task: Monitor implementation

Workflow states:                      State Machine:
• Flagged → Planning → Active         • States with transitions
• Conditional logic (cancel if <5)    • Conditional routing
• Multi-week campaigns                • Checkpointed workflows
```

**LangGraph Advantages**:
1. ✅ **State machine clarity** - Declarative workflow vs imperative code
2. ✅ **Checkpointing** - Resume campaigns after days/weeks
3. ✅ **Parallel execution** - Discover residents + orgs + experts concurrently
4. ✅ **Human-in-loop** - Built-in patterns for approvals, RSVPs, input
5. ✅ **Observability** - LangSmith traces show exactly where coordination failed
6. ✅ **Conditional routing** - Dynamic decisions based on state

**What We Still Build Custom**:
- Email/SMS integrations (SendGrid, Twilio)
- Meeting scheduling (Google Calendar, Zoom)
- Database schema (campaigns, participants, surveys)
- PostGIS spatial queries (geographic actor discovery)
- Survey delivery (response tracking)
- Frontend UI (testimony queue, outcome dashboard)

---

## 2. Agent Orchestration Architecture

### 2.1 LangGraph State Machine

**Core Workflow States**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ COORDINATION WORKFLOW (LangGraph State Graph)                           │
└─────────────────────────────────────────────────────────────────────────┘

                              START
                                │
                                ▼
                      ┌──────────────────┐
                      │  DETECT_DECISION │
                      │  (AI Agent)      │
                      └────────┬─────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  Score >= 100?      │ (Conditional)
                    └──┬──────────────┬───┘
                 NO    │              │ YES
                       ▼              ▼
                     END    ┌──────────────────┐
                            │ DISCOVER_ACTORS  │
                            │ (AI Agent)       │
                            └────────┬─────────┘
                                     │
                  ┌──────────────────┼──────────────────┐
                  │                  │                  │
                  ▼                  ▼                  ▼
         ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
         │ Find Residents │ │ Find Orgs      │ │ Find Experts   │
         │ (Parallel)     │ │ (Parallel)     │ │ (Parallel)     │
         └────────┬───────┘ └────────┬───────┘ └────────┬───────┘
                  │                  │                  │
                  └──────────────────┼──────────────────┘
                                     ▼
                           ┌──────────────────┐
                           │  MERGE_ACTORS    │
                           └────────┬─────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  Actors >= 20?      │ (Conditional)
                         └──┬──────────────┬───┘
                      NO    │              │ YES
                            ▼              ▼
                          END    ┌──────────────────┐
                                 │ SEND_INVITATIONS │
                                 │ (Custom Node)    │
                                 └────────┬─────────┘
                                          │
                                          ▼
                                ┌──────────────────┐
                                │  WAIT_FOR_RSVPS  │
                                │  (Human-in-loop) │
                                │  Interrupt: 7d   │
                                └────────┬─────────┘
                                         │
                                         ▼
                              ┌─────────────────────┐
                              │  RSVPs >= 5?        │ (Conditional)
                              └──┬──────────────┬───┘
                           NO    │              │ YES
                                 ▼              ▼
                               END    ┌──────────────────┐
                                      │ SCHEDULE_SESSION │
                                      │ (Custom Node)    │
                                      └────────┬─────────┘
                                               │
                                               ▼
                                     ┌──────────────────┐
                                     │ ALLOCATE_TESTIMONY│
                                     │ (AI Agent)       │
                                     └────────┬─────────┘
                                              │
                                              ▼
                                    ┌──────────────────┐
                                    │ COORDINATE_LIVE  │
                                    │ (WebSocket)      │
                                    └────────┬─────────┘
                                             │
                                             ▼
                                   ┌──────────────────┐
                                   │ MEASURE_IMPACT   │
                                   │ (AI Agent)       │
                                   └────────┬─────────┘
                                            │
                                            ▼
                                          END
```

### 2.2 State Schema

```python
from typing import TypedDict, Annotated, Literal, Optional
import operator

def merge_actors(existing: dict, new: dict) -> dict:
    """
    Custom reducer for merging nested actor dictionaries.
    Extends lists within each actor type category.
    """
    result = existing.copy() if existing else {}
    for key, value in new.items():
        if key in result:
            result[key].extend(value)
        else:
            result[key] = value
    return result

class CoordinationState(TypedDict):
    """
    State object passed between workflow nodes.
    Annotated fields use reducers for state merging.
    """
    # Decision context
    decision_id: str
    decision_score: int
    decision_date: str
    impact_area: dict  # GeoJSON polygon

    # Actor discovery
    actors: Annotated[dict, merge_actors]  # Merge actor lists with custom reducer
    # {
    #   "residents": [user_ids],
    #   "orgs": [org_ids],
    #   "experts": [expert_ids]
    # }

    # Campaign state
    campaign_id: Optional[str]
    invitations_sent: int
    rsvps: Annotated[list, operator.add]  # Append RSVPs
    session_time: Optional[str]

    # Testimony coordination
    testimony_queue: list
    testimony_allocated: bool

    # Impact measurement
    empowerment_scores: Annotated[list, operator.add]
    empowerment_avg: float

    # Metadata
    created_at: str
    updated_at: str
```

### 2.3 Agent Types

**AI Agents** (LangGraph nodes using LLMs):

```python
# Note: LangGraph nodes are just callables - no base class needed

class DecisionDetectorAgent:
    """AI agent: Score decisions for coordination potential"""

    def __call__(self, state: CoordinationState):
        detector = DecisionDetector()
        score = detector.score_decision(state['decision_id'])

        return {
            **state,
            "decision_score": score,
            "updated_at": datetime.now().isoformat()
        }

class ActorDiscoveryAgent:
    """AI agent: Find affected residents using PostGIS + LLM"""

    def __call__(self, state: CoordinationState):
        discovery = ActorDiscovery()
        actors = discovery.discover_actors(
            decision_id=state['decision_id'],
            impact_area=state['impact_area']
        )

        return {
            **state,
            "actors": actors,
            "updated_at": datetime.now().isoformat()
        }

class TestimonyAllocatorAgent:
    """AI agent: Allocate talking points to avoid redundancy"""

    def __call__(self, state: CoordinationState):
        allocator = TestimonyAllocator()
        queue = allocator.allocate_testimony(
            participants=state['rsvps'],
            decision_context=state['decision_id']
        )

        return {
            **state,
            "testimony_queue": queue,
            "testimony_allocated": True,
            "updated_at": datetime.now().isoformat()
        }
```

**Custom Integration Nodes** (Real-world coordination):

```python
class SendInvitationsNode:
    """Custom node: Email outreach via SendGrid"""

    async def __call__(self, state: CoordinationState):
        outreach = OutreachManager()

        result = await outreach.send_campaign(
            campaign_id=state['campaign_id'],
            actor_ids=state['actors']['residents'],
            template='resident_invitation',
            channel='email'
        )

        return {
            **state,
            "invitations_sent": result['sent_count'],
            "updated_at": datetime.now().isoformat()
        }

class WaitForRSVPsNode:
    """Human-in-loop: Pause until RSVP threshold met"""

    def __call__(self, state: CoordinationState):
        # This node uses LangGraph's interrupt mechanism
        # Execution pauses here until external trigger
        # When resumed, it queries database for current RSVP state

        rsvps = get_current_rsvps(state['campaign_id'])

        return {
            **state,
            "rsvps": rsvps,
            "updated_at": datetime.now().isoformat()
        }

class ScheduleSessionNode:
    """Custom node: Google Meet scheduling"""

    async def __call__(self, state: CoordinationState):
        scheduler = MeetingScheduler()

        meeting = await scheduler.create_strategy_session(
            participants=[r['email'] for r in state['rsvps']],
            duration_minutes=60,
            title=f"Strategy Session: {state['decision_id']}"
        )

        return {
            **state,
            "session_time": meeting['start_time'],
            "updated_at": datetime.now().isoformat()
        }
```

### 2.4 Conditional Routing

```python
def should_send_invitations(state: CoordinationState) -> Literal["invite", "cancel"]:
    """Route based on actor count"""
    total_actors = sum(len(actors) for actors in state['actors'].values())

    if total_actors >= 20:
        return "invite"
    return "cancel"

def should_continue_campaign(state: CoordinationState) -> Literal["continue", "cancel"]:
    """Route based on RSVP threshold"""
    if len(state['rsvps']) >= 5:
        return "continue"
    return "cancel"

def should_allocate_testimony(state: CoordinationState) -> Literal["allocate", "skip"]:
    """Route based on participant count"""
    if len(state['rsvps']) >= 3:
        return "allocate"
    return "skip"
```

### 2.5 Complete Workflow Definition

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

# Initialize state graph
workflow = StateGraph(CoordinationState)

# Add AI agent nodes
workflow.add_node("detect_decision", DecisionDetectorAgent())
workflow.add_node("discover_residents", ResidentDiscoveryAgent())
workflow.add_node("discover_orgs", OrgDiscoveryAgent())
workflow.add_node("discover_experts", ExpertDiscoveryAgent())
workflow.add_node("merge_actors", MergeActorsAgent())
workflow.add_node("allocate_testimony", TestimonyAllocatorAgent())
workflow.add_node("measure_impact", ImpactMeasurementAgent())

# Add custom integration nodes
workflow.add_node("send_invitations", SendInvitationsNode())
workflow.add_node("wait_rsvps", WaitForRSVPsNode())
workflow.add_node("schedule_session", ScheduleSessionNode())
workflow.add_node("coordinate_live", LiveCoordinationNode())

# Define edges (workflow flow)
workflow.set_entry_point("detect_decision")

# Conditional: Only continue if high-stakes
# Routes to ALL three parallel discovery nodes or cancels
workflow.add_conditional_edges(
    "detect_decision",
    lambda state: "discover" if state['decision_score'] >= 100 else "cancel",
    {
        "discover": ["discover_residents", "discover_orgs", "discover_experts"],
        "cancel": END
    }
)

# Merge parallel results (fan-in from parallel execution)
workflow.add_edge("discover_residents", "merge_actors")
workflow.add_edge("discover_orgs", "merge_actors")
workflow.add_edge("discover_experts", "merge_actors")

# Conditional: Only invite if enough actors
workflow.add_conditional_edges(
    "merge_actors",
    should_send_invitations,
    {"invite": "send_invitations", "cancel": END}
)

workflow.add_edge("send_invitations", "wait_rsvps")

# Conditional: Only continue if enough RSVPs
workflow.add_conditional_edges(
    "wait_rsvps",
    should_continue_campaign,
    {"continue": "schedule_session", "cancel": END}
)

workflow.add_edge("schedule_session", "allocate_testimony")
workflow.add_edge("allocate_testimony", "coordinate_live")
workflow.add_edge("coordinate_live", "measure_impact")
workflow.add_edge("measure_impact", END)

# Compile with checkpointing
checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:pass@localhost/civic_participation"
)

app = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["wait_rsvps"]  # Pause for human input
)
```

### 2.6 Observability with LangSmith

```python
from langsmith import traceable

@traceable(run_type="chain", name="coordination_campaign")
def run_coordination_campaign(decision_id: str):
    """
    Run full coordination campaign with LangSmith tracing.
    """
    result = app.invoke(
        {"decision_id": decision_id},
        config={
            "configurable": {"thread_id": f"campaign-{decision_id}"},
            "callbacks": [LangSmithCallback()]
        }
    )

    return result

# LangSmith UI shows:
# ├─ detect_decision: score=140 ✓ (200ms)
# ├─ discover_residents: 32 found ✓ (1.2s)
# ├─ discover_orgs: 1 found ✓ (0.8s)
# ├─ discover_experts: 1 found ✓ (0.5s)
# ├─ merge_actors: 34 total ✓ (50ms)
# ├─ send_invitations: 34 sent ✓ (2.1s)
# ├─ wait_rsvps: PAUSED ⏸ (7 days)
# │  └─ RSVP count: 3/34 (8.8%) ⚠️
# └─ should_continue_campaign: CANCEL (threshold not met) ✗
#
# Root cause: Low RSVP conversion (8.8%)
# Recommendation: Improve email template, add SMS follow-up
```

---

## 3. Decision Awareness Pipeline

### 3.1 End-to-End Workflow (LangGraph Execution)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ DECISION AWARENESS PIPELINE (LangGraph Orchestration)                   │
│ From agenda item → coordinated campaign → policy impact                 │
└─────────────────────────────────────────────────────────────────────────┘

WEEK -4 to -2: DETECTION & DISCOVERY (Automated)
═══════════════════════════════════════════════════════════════════════════

┌─────────────────┐
│ City Council    │ "Feb 12: $1.1M Wildfire Prevention Fund"
│ Agenda Published│
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ LANGGRAPH NODE: detect_decision (AI Agent)                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Agent: DecisionDetectorAgent()                                         │
│  Task: Score decision for coordination potential                        │
│                                                                          │
│  INPUT: {"decision_id": "sr-2025-02-12-wildfire"}                      │
│                                                                          │
│  EXECUTION:                                                              │
│  • Query event from database                                            │
│  • Extract: budget=$1.1M, topic=environment, scope=city-wide           │
│  • LLM assessment: "High public interest, wildfire safety critical"    │
│  • Calculate score: 50 (budget) + 30 (topic) + 20 (scope) + 40 (LLM)  │
│                                                                          │
│  OUTPUT: {"decision_score": 140} → HIGH-STAKES ✓                       │
│                                                                          │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼ (Conditional edge: score >= 100)
                                    │
                  ┌─────────────────┼─────────────────┐
                  │                 │                 │
                  ▼                 ▼                 ▼
┌──────────────────────────┐ ┌──────────────┐ ┌──────────────────┐
│ LANGGRAPH NODE:          │ │ LANGGRAPH    │ │ LANGGRAPH NODE:  │
│ discover_residents       │ │ NODE:        │ │ discover_experts │
│ (AI Agent + PostGIS)     │ │ discover_orgs│ │ (AI Agent)       │
├──────────────────────────┤ ├──────────────┤ ├──────────────────┤
│                          │ │              │ │                  │
│ Parallel Execution ✨    │ │ Parallel ✨  │ │ Parallel ✨      │
│                          │ │              │ │                  │
│ Query 1: SeeClickFix     │ │ Query org DB │ │ Query experts DB │
│ 24 fire/tree complaints  │ │ Match topics │ │ Match expertise  │
│                          │ │ 1 org found  │ │ 1 expert found   │
│ Query 2: PostGIS         │ │              │ │                  │
│ 16 high-risk residents   │ │              │ │                  │
│                          │ │              │ │                  │
│ Query 3: Issue follows   │ │              │ │                  │
│ 12 environment followers │ │              │ │                  │
│                          │ │              │ │                  │
│ Deduplicate: 32 unique   │ │              │ │                  │
│                          │ │              │ │                  │
│ OUTPUT: 32 residents     │ │ OUTPUT: 1 org│ │ OUTPUT: 1 expert │
└──────────┬───────────────┘ └──────┬───────┘ └────────┬─────────┘
           │                        │                   │
           └────────────────────────┼───────────────────┘
                                    ▼
                          ┌──────────────────┐
                          │ LANGGRAPH NODE:  │
                          │ merge_actors     │
                          │ (Reducer)        │
                          ├──────────────────┤
                          │ 34 total actors  │
                          └────────┬─────────┘
                                   │
                                   ▼ (Conditional: actors >= 20)

WEEK -2 to -1: OUTREACH & MOBILIZATION (Custom Integration)
═══════════════════════════════════════════════════════════════════════════

                          ┌──────────────────┐
                          │ LANGGRAPH NODE:  │
                          │ send_invitations │
                          │ (Custom Node)    │
                          ├──────────────────┤
                          │ SendGrid API     │
                          │ 34 emails sent   │
                          │ Template: ...    │
                          └────────┬─────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │ LANGGRAPH NODE:  │
                          │ wait_rsvps       │
                          │ (Human-in-loop)  │
                          ├──────────────────┤
                          │ INTERRUPT ⏸      │
                          │ Timeout: 7 days  │
                          │                  │
                          │ Checkpoint saved │
                          │ Execution paused │
                          └────────┬─────────┘
                                   │
                      (7 days pass, RSVPs accumulate)
                                   │
                          ┌────────▼─────────┐
                          │ Resume execution │
                          │ RSVP count: 8/34 │
                          └────────┬─────────┘
                                   │
                                   ▼ (Conditional: rsvps >= 5)

WEEK -1: PRE-MEETING ORCHESTRATION (Custom Integration)
═══════════════════════════════════════════════════════════════════════════

                          ┌──────────────────┐
                          │ LANGGRAPH NODE:  │
                          │ schedule_session │
                          │ (Custom Node)    │
                          ├──────────────────┤
                          │ Google Meet API  │
                          │ Feb 9, 7pm       │
                          │ 8 attendees      │
                          └────────┬─────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │ LANGGRAPH NODE:  │
                          │ allocate_testimony│
                          │ (AI Agent)       │
                          ├──────────────────┤
                          │ LLM analyzes:    │
                          │ - Participant    │
                          │   backgrounds    │
                          │ - Decision topics│
                          │ - Talking points │
                          │                  │
                          │ Assigns:         │
                          │ Alice: Vegetation│
                          │ Bob: Evacuation  │
                          │ Carol: Education │
                          │ ...              │
                          └────────┬─────────┘
                                   │
                                   ▼

DAY 0: MEETING DAY COORDINATION (WebSocket)
═══════════════════════════════════════════════════════════════════════════

                          ┌──────────────────┐
                          │ LANGGRAPH NODE:  │
                          │ coordinate_live  │
                          │ (WebSocket)      │
                          ├──────────────────┤
                          │ Real-time chat   │
                          │ Testimony queue  │
                          │ Live updates     │
                          └────────┬─────────┘
                                   │
                                   ▼

WEEK +1: IMPACT MEASUREMENT (AI Agent + Custom)
═══════════════════════════════════════════════════════════════════════════

                          ┌──────────────────┐
                          │ LANGGRAPH NODE:  │
                          │ measure_impact   │
                          │ (AI Agent)       │
                          ├──────────────────┤
                          │ Send surveys     │
                          │ Analyze responses│
                          │ Calculate avg    │
                          │                  │
                          │ Empowerment: 4.3 │
                          │ Would repeat: 86%│
                          └────────┬─────────┘
                                   │
                                   ▼
                                  END

Campaign Complete ✓
State checkpointed to Postgres
LangSmith trace available for review
```

### 3.2 Checkpoint & Resume Example

```python
# Week -2: Campaign starts
result = app.invoke(
    {"decision_id": "sr-2025-02-12-wildfire"},
    config={"configurable": {"thread_id": "campaign-wildfire"}}
)

# Execution pauses at wait_rsvps node
# State checkpointed to Postgres

# Week -1: Check campaign status
state = app.get_state(config={"configurable": {"thread_id": "campaign-wildfire"}})
print(state)
# {
#   "next": ["wait_rsvps"],  # Paused at this node
#   "values": {
#     "decision_score": 140,
#     "actors": {"residents": [32 ids], "orgs": [1 id]},
#     "invitations_sent": 34,
#     "rsvps": [8 rsvp objects]
#   },
#   "checkpoint_id": "1a2b3c4d"
# }

# Resume execution (automatically continues from wait_rsvps)
# IMPORTANT: The wait_rsvps node queries database for current RSVP state
# External state (database) has been updated with new RSVPs via API
# The node will fetch fresh data when it re-executes
result = app.invoke(
    None,  # No new input, just resume
    config={"configurable": {"thread_id": "campaign-wildfire"}}
)

# Workflow continues: schedule_session → allocate_testimony → ...
```

---

## 4. Actor Discovery & Routing

### 4.1 Actor Taxonomy (6 Types)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ ACTOR TAXONOMY & ROUTING ARCHITECTURE                                   │
└─────────────────────────────────────────────────────────────────────────┘

TYPE 1: AFFECTED RESIDENTS
┌────────────────────────────────────────────┐
│ Discovery Methods:                         │
│ • Geographic radius (PostGIS)              │
│ • SeeClickFix complaint matching           │
│ • Issue follows/interests                  │
│ • Property ownership (public records)      │
│                                             │
│ Routing Criteria:                          │
│ • Distance to impact zone                  │
│ • Complaint recency/severity               │
│ • Past civic engagement                    │
│ • Demographic diversity (equity)           │
│                                             │
│ LangGraph Agent: ResidentDiscoveryAgent()  │
│ - Parallel PostGIS queries                 │
│ - LLM-based relevance scoring              │
└────────────────────────────────────────────┘

TYPE 2: ADVOCACY ORGANIZATIONS
┌────────────────────────────────────────────┐
│ Discovery Methods:                         │
│ • Topic expertise mapping                  │
│ • Partnership database                     │
│ • Past campaign participation              │
│                                             │
│ Routing Criteria:                          │
│ • Subject matter expertise                 │
│ • Geographic jurisdiction                  │
│ • Past coordination success                │
│ • Resource capacity                        │
│                                             │
│ LangGraph Agent: OrgDiscoveryAgent()       │
│ - Topic matching (embeddings)              │
│ - Success score ranking                    │
│                                             │
│ Examples:                                   │
│ • Wildfire Prevention Authority            │
│ • Housing advocacy (YIMBY/affordable)      │
│ • Transportation (bike/transit groups)     │
└────────────────────────────────────────────┘

TYPE 3: SUBJECT EXPERTS
┌────────────────────────────────────────────┐
│ Discovery Methods:                         │
│ • Professional credentials                 │
│ • Academic affiliations                    │
│ • Past testimony expertise                 │
│                                             │
│ Routing Criteria:                          │
│ • Technical credibility                    │
│ • Non-partisan positioning                 │
│ • Communication clarity                    │
│                                             │
│ LangGraph Agent: ExpertDiscoveryAgent()    │
│ - Credential verification                  │
│ - Expertise-topic matching                 │
│                                             │
│ Examples:                                   │
│ • Fire Chief (wildfire expertise)          │
│ • Urban planner (housing/development)      │
│ • Transportation engineer                  │
└────────────────────────────────────────────┘

TYPE 4: POLITICAL CHAMPIONS
┌────────────────────────────────────────────┐
│ Discovery Methods:                         │
│ • Past vote alignment                      │
│ • Constituent district overlap             │
│ • Public statements/priorities             │
│                                             │
│ Routing Criteria:                          │
│ • Issue alignment                          │
│ • Constituent overlap                      │
│ • Receptiveness to coordination            │
│                                             │
│ LangGraph Agent: ChampionDiscoveryAgent()  │
│ - Vote history analysis (LLM)              │
│ - District geospatial matching             │
│                                             │
│ Examples:                                   │
│ • Councilmember Colin (environment)        │
│ • Mayor (budget priorities)                │
│ • Planning Commissioner                    │
└────────────────────────────────────────────┘

TYPE 5: MUNICIPAL STAFF
┌────────────────────────────────────────────┐
│ Discovery Methods:                         │
│ • Department responsibility mapping        │
│ • Staff reports authorship                 │
│ • Implementation authority                 │
│                                             │
│ Routing Criteria:                          │
│ • Implementation role                      │
│ • Technical Q&A capacity                   │
│ • Outcome tracking responsibility          │
│                                             │
│ LangGraph Agent: StaffDiscoveryAgent()     │
│ - Department routing                       │
│ - Responsibility matching                  │
│                                             │
│ Examples:                                   │
│ • Public Works Director (infrastructure)   │
│ • Planning Director (development)          │
│ • City Manager (budget)                    │
└────────────────────────────────────────────┘

TYPE 6: MEDIA
┌────────────────────────────────────────────┐
│ Discovery Methods:                         │
│ • Beat reporter mapping                    │
│ • Past coverage topics                     │
│ • Outlet reach/audience                    │
│                                             │
│ Routing Criteria:                          │
│ • Topic relevance                          │
│ • Campaign visibility goals                │
│ • Public pressure tactics                  │
│                                             │
│ LangGraph Agent: MediaDiscoveryAgent()     │
│ - Beat-topic matching                      │
│ - Coverage threshold detection             │
│                                             │
│ Examples:                                   │
│ • Marin Independent Journal                │
│ • Local TV news (coverage threshold)       │
│ • Community radio                          │
└────────────────────────────────────────────┘
```

### 4.2 Actor Discovery as LangGraph Agent

```python
class ResidentDiscoveryAgent:
    """
    LangGraph agent for discovering affected residents.
    Uses PostGIS for geographic queries + LLM for relevance scoring.
    """

    def __call__(self, state: CoordinationState):
        discovery = ActorDiscovery()

        # PostGIS spatial queries
        residents = discovery.discover_residents(
            decision_id=state['decision_id'],
            impact_area=state['impact_area'],
            radius_meters=2000
        )

        # LLM-based relevance scoring
        scored_residents = self._score_relevance(residents, state)

        # Top 50 most relevant
        top_residents = sorted(
            scored_residents,
            key=lambda r: r['relevance_score'],
            reverse=True
        )[:50]

        return {
            **state,
            "actors": {
                **state.get("actors", {}),
                "residents": [r['id'] for r in top_residents]
            }
        }

    def _score_relevance(self, residents, state):
        """Use LLM to score resident relevance"""
        prompt = f"""
        Score resident relevance for coordination on: {state['decision_id']}

        Resident profile:
        - Distance: {resident['distance_meters']}m
        - Complaints: {resident['complaint_count']}
        - Topics: {resident['interests']}

        Score 0-100 based on:
        - Proximity to impact area
        - Past complaint relevance
        - Likelihood to participate

        Return only a number.
        """

        # ... LLM call ...
        return scored_residents
```

### 4.3 Parallel Actor Discovery

```python
from langgraph.graph import StateGraph

# Define parallel discovery workflow
workflow = StateGraph(CoordinationState)

# Add discovery agents
workflow.add_node("discover_residents", ResidentDiscoveryAgent())
workflow.add_node("discover_orgs", OrgDiscoveryAgent())
workflow.add_node("discover_experts", ExpertDiscoveryAgent())
workflow.add_node("merge", MergeActorsNode())

# Fan-out: Discover all actor types in parallel
workflow.add_edge("detect_decision", "discover_residents")
workflow.add_edge("detect_decision", "discover_orgs")
workflow.add_edge("detect_decision", "discover_experts")

# Fan-in: Merge results
workflow.add_edge("discover_residents", "merge")
workflow.add_edge("discover_orgs", "merge")
workflow.add_edge("discover_experts", "merge")

# Parallel execution reduces latency:
# Sequential: 1.2s + 0.8s + 0.5s = 2.5s
# Parallel:   max(1.2s, 0.8s, 0.5s) = 1.2s
# Speedup:    2.1x faster ✨
```

---

## 5. Data Model

### 5.1 Database Schema (Unchanged)

```sql
-- ============================================================================
-- COORDINATION ORCHESTRATION DATABASE SCHEMA
-- ============================================================================

-- ----------------------------------------------------------------------------
-- DECISIONS
-- High-stakes decisions requiring coordination
-- ----------------------------------------------------------------------------
CREATE TABLE decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    high_stakes_score INTEGER NOT NULL,
    coordination_status TEXT NOT NULL CHECK (coordination_status IN
        ('flagged', 'planning', 'active', 'completed')),
    decision_date TIMESTAMP NOT NULL,
    outcome_status TEXT CHECK (outcome_status IN
        ('approved', 'denied', 'amended', 'pending')),
    impact_area GEOGRAPHY(POLYGON, 4326),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_decisions_event_id ON decisions(event_id);
CREATE INDEX idx_decisions_coordination_status ON decisions(coordination_status);
CREATE INDEX idx_decisions_decision_date ON decisions(decision_date);
CREATE INDEX idx_decisions_impact_area ON decisions USING GIST(impact_area);

-- ----------------------------------------------------------------------------
-- LANGGRAPH CHECKPOINTS
-- LangGraph state checkpoints (auto-created and managed by LangGraph)
-- NOTE: This table is automatically created by PostgresSaver.from_conn_string()
-- You do NOT need to manually create this table via migration
-- Schema shown here for reference only
-- ----------------------------------------------------------------------------
-- CREATE TABLE checkpoints (
--     thread_id TEXT NOT NULL,
--     checkpoint_id TEXT NOT NULL,
--     parent_id TEXT,
--     checkpoint BYTEA NOT NULL,
--     metadata JSONB,
--     created_at TIMESTAMP DEFAULT NOW(),
--     PRIMARY KEY (thread_id, checkpoint_id)
-- );
--
-- CREATE INDEX idx_checkpoints_thread_id ON checkpoints(thread_id);
-- CREATE INDEX idx_checkpoints_created_at ON checkpoints(created_at);

-- ----------------------------------------------------------------------------
-- COORDINATION CAMPAIGNS
-- Coordination campaigns for decisions
-- ----------------------------------------------------------------------------
CREATE TABLE coordination_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    langgraph_thread_id TEXT NOT NULL,  -- Links to LangGraph state
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN
        ('planning', 'outreach', 'orchestrating', 'completed')),
    strategy_session_time TIMESTAMP,
    meeting_zoom_link TEXT,
    briefing_packet_url TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_coordination_campaigns_decision_id ON coordination_campaigns(decision_id);
CREATE INDEX idx_coordination_campaigns_langgraph_thread ON coordination_campaigns(langgraph_thread_id);
CREATE INDEX idx_coordination_campaigns_status ON coordination_campaigns(status);

-- ----------------------------------------------------------------------------
-- CAMPAIGN PARTICIPANTS
-- All actors participating in a campaign
-- ----------------------------------------------------------------------------
CREATE TABLE campaign_participants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES coordination_campaigns(id) ON DELETE CASCADE,
    actor_id UUID NOT NULL,
    actor_type TEXT NOT NULL CHECK (actor_type IN
        ('resident', 'org', 'expert', 'official', 'staff', 'media')),
    role TEXT CHECK (role IN
        ('testifier', 'advisor', 'champion', 'observer')),
    rsvp_status TEXT NOT NULL CHECK (rsvp_status IN
        ('invited', 'maybe', 'yes', 'declined', 'no_response')),
    testimony_allocated BOOLEAN DEFAULT FALSE,
    testified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_campaign_participants_campaign_id ON campaign_participants(campaign_id);
CREATE INDEX idx_campaign_participants_actor_type ON campaign_participants(actor_type);
CREATE INDEX idx_campaign_participants_rsvp_status ON campaign_participants(rsvp_status);

-- ... (Rest of schema from original document unchanged) ...
-- See original COORDINATION_ORCHESTRATION_ARCHITECTURE.md for:
-- - outreach_campaigns
-- - testimony_queue
-- - empowerment_surveys
-- - outcome_tracking
-- - advocacy_orgs
-- - subject_experts
-- - council_members
-- - municipal_staff
-- - media_contacts
-- - wildfire_risk_zones
```

### 5.2 LangGraph-Database Integration

```python
from langgraph.checkpoint.postgres import PostgresSaver

# Initialize checkpointer
checkpointer = PostgresSaver.from_conn_string(
    "postgresql://user:pass@localhost/civic_participation"
)

# Compile workflow with checkpointing
app = workflow.compile(checkpointer=checkpointer)

# State is automatically saved to 'checkpoints' table
# Each campaign has unique thread_id for resumability
```

---

## 6. API Architecture

### 6.1 REST API Endpoints (Updated for LangGraph)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ COORDINATION API ENDPOINTS (LangGraph Integration)                      │
└─────────────────────────────────────────────────────────────────────────┘

CAMPAIGN EXECUTION (LangGraph)
═══════════════════════════════════════════════════════════════════════════

POST   /api/campaigns/start
       Start new coordination campaign
       Body: { decision_id, config }
       Returns: { campaign_id, thread_id, status }

       Implementation:
       - Creates campaign in DB
       - Invokes LangGraph workflow
       - Returns initial state

GET    /api/campaigns/:id/state
       Get current campaign state
       Returns: { state, next_nodes, checkpoint_id }

       Implementation:
       - Queries LangGraph checkpointer
       - Returns current state + next actions

POST   /api/campaigns/:id/resume
       Resume paused campaign
       Body: { input } (optional)
       Returns: { state, status }

       Implementation:
       - Resumes from last checkpoint
       - Continues workflow execution

GET    /api/campaigns/:id/trace
       Get LangSmith trace for debugging
       Returns: { trace_url, execution_steps }

       Implementation:
       - Fetches LangSmith trace
       - Shows execution timeline

HUMAN-IN-LOOP INTERACTIONS
═══════════════════════════════════════════════════════════════════════════

POST   /api/campaigns/:id/rsvp
       Submit RSVP (triggers workflow resume)
       Body: { participant_id, status }
       Returns: { rsvp, campaign_resumed }

       Implementation:
       - Records RSVP in DB
       - Checks if threshold met
       - Resumes LangGraph workflow if ready

PATCH  /api/campaigns/:id/interrupt
       Manually interrupt campaign
       Body: { reason }
       Returns: { status: "interrupted" }

       Implementation:
       - Pauses LangGraph execution
       - Saves current state

... (Other endpoints from original document unchanged) ...
```

### 6.2 API Implementation with LangGraph

```python
from fastapi import APIRouter, HTTPException
from langgraph.checkpoint.postgres import PostgresSaver

router = APIRouter(prefix="/api/campaigns")

# Initialize LangGraph app (global)
checkpointer = PostgresSaver.from_conn_string(DB_URL)
coordination_app = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["wait_rsvps"]
)

@router.post("/start")
async def start_campaign(decision_id: str):
    """
    Start new coordination campaign using LangGraph.
    """
    # Create campaign in DB
    campaign = db.execute("""
        INSERT INTO coordination_campaigns (decision_id, name, status)
        VALUES (%(decision_id)s, %(name)s, 'planning')
        RETURNING *;
    """, {
        'decision_id': decision_id,
        'name': f"Campaign: {decision_id}"
    })

    thread_id = f"campaign-{campaign['id']}"

    # Update with thread_id
    db.execute("""
        UPDATE coordination_campaigns
        SET langgraph_thread_id = %(thread_id)s
        WHERE id = %(id)s;
    """, {'id': campaign['id'], 'thread_id': thread_id})

    # Start LangGraph workflow (async)
    asyncio.create_task(
        run_campaign_workflow(decision_id, thread_id)
    )

    return {
        "campaign_id": campaign['id'],
        "thread_id": thread_id,
        "status": "started"
    }

async def run_campaign_workflow(decision_id: str, thread_id: str):
    """Background task: Run LangGraph workflow"""
    try:
        result = coordination_app.invoke(
            {"decision_id": decision_id},
            config={"configurable": {"thread_id": thread_id}}
        )
    except Exception as e:
        logger.error(f"Campaign {thread_id} failed: {e}")
        # Update campaign status to failed

@router.get("/{campaign_id}/state")
async def get_campaign_state(campaign_id: str):
    """
    Get current campaign state from LangGraph checkpointer.
    """
    campaign = db.get('coordination_campaigns', campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found")

    # Query LangGraph state
    state = coordination_app.get_state(
        config={"thread_id": campaign['langgraph_thread_id']}
    )

    return {
        "campaign_id": campaign_id,
        "status": campaign['status'],
        "state": state.values,
        "next_nodes": state.next,
        "checkpoint_id": state.config['configurable']['checkpoint_id']
    }

@router.post("/{campaign_id}/rsvp")
async def submit_rsvp(campaign_id: str, participant_id: str, status: str):
    """
    Submit RSVP and resume campaign if threshold met.
    """
    # Record RSVP
    db.execute("""
        UPDATE campaign_participants
        SET rsvp_status = %(status)s
        WHERE id = %(id)s;
    """, {'id': participant_id, 'status': status})

    # Check if threshold met
    rsvp_count = db.execute("""
        SELECT COUNT(*) FROM campaign_participants
        WHERE campaign_id = %(campaign_id)s
          AND rsvp_status = 'yes';
    """, {'campaign_id': campaign_id})[0]['count']

    campaign_resumed = False

    if rsvp_count >= 5:
        # Resume LangGraph workflow
        campaign = db.get('coordination_campaigns', campaign_id)

        coordination_app.invoke(
            None,  # No new input, just resume
            config={"thread_id": campaign['langgraph_thread_id']}
        )

        campaign_resumed = True

    return {
        "rsvp": {"participant_id": participant_id, "status": status},
        "rsvp_count": rsvp_count,
        "campaign_resumed": campaign_resumed
    }
```

---

## 7. Implementation Roadmap

### 7.1 Revised Priority Tiers (with LangGraph)

**TIER 1: Core Infrastructure - 8-12 days**

| Component | Build Effort | Files | Priority |
|-----------|--------------|-------|----------|
| Database migration | 1 day | `migrations/011_coordination_orchestration.sql` | P0 |
| **LangGraph setup** | 2-3 days | `src/coordination/workflow.py` | **P0** |
| **Basic agents (detect, discover)** | 3-4 days | `src/coordination/agents/` | **P0** |
| Email outreach node | 2-3 days | `src/coordination/nodes/outreach.py` | P0 |
| Survey system | 2-3 days | `src/coordination/nodes/surveys.py` | P0 |

**TIER 2: Enhanced Features - 5-8 days**

| Component | Build Effort | Files | Priority |
|-----------|--------------|-------|----------|
| Advanced routing agents | 3-4 days | `src/coordination/agents/routing.py` | P1 |
| Outcome tracking | 2-3 days | `src/coordination/agents/outcomes.py` | P1 |
| LangSmith integration | 1 day | Config in `workflow.py` | P1 |

**TIER 3: Advanced Orchestration - 8-12 days**

| Component | Build Effort | Files | Priority |
|-----------|--------------|-------|----------|
| Multi-actor coordination | 3-5 days | `src/coordination/agents/multi_actor.py` | P2 |
| Frontend UI | 3-5 days | `frontend/civic-workspace/...` | P2 |
| Advanced workflows | 2-3 days | `src/coordination/workflows/` | P2 |

### 7.2 Implementation Phases

**Phase 1 (Week 1-2): LangGraph Foundation**

Sprint 1:
- Install LangGraph: `pip install langgraph langgraph-checkpoint-postgres`
- Database migration (add checkpoints table)
- Define CoordinationState schema
- Build basic workflow: detect → discover → END

Sprint 2:
- Add decision detector agent
- Add resident discovery agent (PostGIS)
- Test checkpointing & resumability
- Validate LangGraph approach

**Phase 2 (Week 3-4): Full Workflow**

Sprint 3:
- Add custom nodes (email, scheduling, surveys)
- Implement conditional routing
- Add parallel actor discovery
- Build API endpoints

Sprint 4:
- Human-in-loop (RSVP waiting)
- Outcome tracking agent
- LangSmith observability
- End-to-end testing

**Phase 3 (Month 2): Advanced Features**

- Multi-actor coordination (orgs, experts, officials)
- Testimony allocation agent
- Live coordination (WebSocket)
- Frontend UI

### 7.3 Comparison: LangGraph vs. Custom

**Without LangGraph** (Original Estimate):
- Build custom state machine: 5-7 days
- Build checkpointing: 3-5 days
- Build conditional routing: 2-3 days
- Build observability: 3-4 days
- **Total**: 13-19 days of orchestration infrastructure

**With LangGraph** (New Estimate):
- Learn LangGraph: 2-3 days
- Adapt existing code to agents: 3-4 days
- Build custom nodes: 3-5 days
- **Total**: 8-12 days + proven patterns

**Savings**: 5-7 days + better observability + resumability + community support

---

## 8. Integration Points

### 8.1 Existing Systems → LangGraph Agents

```python
# BEFORE: Custom orchestration
class CoordinationPipeline:
    def run(self, decision_id):
        # Manual state management
        state = {'decision_id': decision_id}

        # Sequential execution
        state = self.detect_decision(state)
        if state['score'] < 100:
            return None

        state = self.discover_actors(state)
        state = self.send_invitations(state)
        # ... etc

# AFTER: LangGraph orchestration
class DecisionDetectorAgent(Node):
    def __call__(self, state: CoordinationState):
        # Use existing code
        from civic_digest import get_event
        from decision_detector import DecisionDetector

        event = get_event(state['decision_id'])
        detector = DecisionDetector()
        score = detector.score_decision(event)

        return {**state, "decision_score": score}

# Existing code becomes agent nodes, not complete rewrite ✨
```

### 8.2 LangGraph → Custom Services

```python
class SendInvitationsNode(Node):
    """Bridge LangGraph workflow to existing email service"""

    def __call__(self, state: CoordinationState):
        # Use existing OutreachManager (no changes)
        from coordination.outreach_manager import OutreachManager

        outreach = OutreachManager()
        result = outreach.send_campaign(
            campaign_id=state['campaign_id'],
            actor_ids=state['actors']['residents'],
            template='resident_invitation'
        )

        return {
            **state,
            "invitations_sent": result['sent_count']
        }
```

### 8.3 PostGIS → LangGraph Agents

```python
class ResidentDiscoveryAgent:
    """LangGraph agent using PostGIS queries"""

    def __call__(self, state: CoordinationState):
        # Use existing PostGIS queries
        residents = db.execute("""
            SELECT u.*,
                ST_Distance(u.location, %(impact_area)s) AS distance
            FROM users u
            WHERE ST_DWithin(
                u.location,
                %(impact_area)s,
                2000
            )
            ORDER BY distance ASC
            LIMIT 50;
        """, {'impact_area': state['impact_area']})

        return {
            **state,
            "actors": {
                **state.get("actors", {}),
                "residents": [r['id'] for r in residents]
            }
        }
```

---

## 9. Technical Specifications

### 9.1 LangGraph Dependencies

```txt
# requirements.txt additions

langgraph>=0.2.0
langgraph-checkpoint>=0.2.0
langgraph-checkpoint-postgres>=0.2.0
langsmith>=0.1.0  # For observability
```

### 9.2 Configuration

```python
# src/coordination/config.py

from langgraph.checkpoint.postgres import PostgresSaver
import os

# LangGraph checkpointer
CHECKPOINTER = PostgresSaver.from_conn_string(
    os.environ.get('DATABASE_URL')
)

# LangSmith configuration (optional, for observability)
LANGSMITH_API_KEY = os.environ.get('LANGSMITH_API_KEY')
LANGSMITH_PROJECT = "civic-coordination"

# Workflow configuration
WORKFLOW_CONFIG = {
    'high_stakes_threshold': 100,
    'min_actors_to_invite': 20,
    'min_rsvps_to_continue': 5,
    'rsvp_timeout_days': 7
}
```

### 9.3 Cost Analysis (Updated)

**Per-campaign costs**:

| Component | Cost | Notes |
|-----------|------|-------|
| LangGraph execution | $0.00 | Open source, no API fees |
| LLM calls (decision detection) | $0.02 | gpt-4o-mini |
| LLM calls (actor relevance scoring) | $0.05 | ~50 residents × $0.001 |
| Email outreach (40 people) | $0.04 | SendGrid |
| Survey delivery (10 people) | $0.01 | SendGrid |
| LangSmith observability | $0.00 | Free tier for development (verify limits) |
| **Total per campaign** | **$0.12** | Even cheaper with LangGraph! |

**Annual costs at scale** (100 campaigns/year):
- LangGraph: $0/year (open source)
- LLM calls: $7/year (100 campaigns × $0.07)
- Email/SMS: $200/year (SendGrid/Twilio)
- LangSmith: $0/year (free tier for development, verify pricing at scale)
- Database: $50/year (Postgres with PostGIS)
- **Total**: **~$260/year** (vs $84/year intelligence layer)

**Coordination layer is ~3x more expensive than intelligence, but still negligible.**

### 9.4 Observability Example

```python
# LangSmith trace for failed campaign

Campaign Trace: sr-2025-02-12-wildfire
Duration: 7 days, 3 hours, 15 minutes
Status: CANCELLED (low RSVP conversion)

Execution Steps:
├─ detect_decision (200ms) ✓
│  └─ score: 140 (high-stakes)
│
├─ discover_residents (1.2s) ✓
│  └─ found: 32 residents
│
├─ discover_orgs (0.8s) ✓
│  └─ found: 1 org
│
├─ discover_experts (0.5s) ✓
│  └─ found: 1 expert
│
├─ merge_actors (50ms) ✓
│  └─ total: 34 actors
│
├─ send_invitations (2.1s) ✓
│  └─ sent: 34 emails
│
├─ wait_rsvps (7 days) ⏸
│  ├─ Day 1: 1 RSVP (2.9%)
│  ├─ Day 3: 2 RSVPs (5.9%)
│  ├─ Day 7: 3 RSVPs (8.8%) ⚠️
│  └─ Checkpoint: 1a2b3c4d
│
└─ should_continue_campaign ✗
   └─ CANCEL (threshold 5 not met)

Root Cause Analysis:
1. Low email open rate (8.8%)
2. Subject line not compelling
3. No SMS follow-up
4. Invitations sent during holiday week

Recommendations:
1. A/B test subject lines
2. Add SMS reminder after 3 days
3. Avoid holiday weeks for outreach
4. Improve email template personalization
```

---

## 10. Error Handling & Resilience

### 10.1 Error Handling Patterns

**Workflow-Level Error Handling**:

```python
from langgraph.graph import StateGraph, END
from typing import Literal

def handle_error(state: CoordinationState, error: Exception) -> CoordinationState:
    """Global error handler for workflow failures"""
    logger.error(f"Campaign {state['campaign_id']} failed: {error}")

    # Update campaign status
    db.execute("""
        UPDATE coordination_campaigns
        SET status = 'failed', error_message = %(error)s
        WHERE id = %(id)s
    """, {'id': state['campaign_id'], 'error': str(error)})

    return {**state, "status": "failed", "error": str(error)}

# Configure workflow with error handling
app = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["wait_rsvps"],
    on_error=handle_error
)
```

**Node-Level Retry Logic**:

```python
class SendInvitationsNode:
    """Custom node with built-in retry logic"""

    async def __call__(self, state: CoordinationState):
        outreach = OutreachManager()

        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = await outreach.send_campaign(
                    campaign_id=state['campaign_id'],
                    actor_ids=state['actors']['residents'],
                    template='resident_invitation',
                    channel='email'
                )

                return {
                    **state,
                    "invitations_sent": result['sent_count'],
                    "updated_at": datetime.now().isoformat()
                }

            except SendGridAPIError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"SendGrid attempt {attempt + 1} failed, retrying...")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error(f"SendGrid failed after {max_retries} attempts")
                    raise
```

**Dead Letter Queue for Failed Campaigns**:

```sql
-- Failed campaigns for manual review
CREATE TABLE failed_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID REFERENCES coordination_campaigns(id),
    failed_node TEXT NOT NULL,
    error_message TEXT NOT NULL,
    state_snapshot JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_failed_campaigns_campaign_id ON failed_campaigns(campaign_id);
CREATE INDEX idx_failed_campaigns_failed_node ON failed_campaigns(failed_node);
```

**Conditional Routing for Error States**:

```python
def should_retry_discovery(state: CoordinationState) -> Literal["retry", "skip", "fail"]:
    """Conditional routing based on actor discovery results"""

    total_actors = sum(len(actors) for actors in state.get('actors', {}).values())

    if total_actors >= 20:
        return "skip"  # Success, move to next node
    elif total_actors >= 10:
        return "retry"  # Partial success, retry with expanded radius
    else:
        return "fail"  # Critical failure, abort campaign

workflow.add_conditional_edges(
    "discover_actors",
    should_retry_discovery,
    {
        "skip": "send_invitations",
        "retry": "expand_search_radius",
        "fail": END
    }
)
```

### 10.2 Rollback Mechanisms

**Campaign Cancellation**:

```python
async def cancel_campaign(campaign_id: str, reason: str):
    """
    Rollback coordination campaign:
    - Cancel scheduled meetings
    - Send cancellation emails
    - Update database state
    - Archive LangGraph checkpoint
    """
    campaign = db.get('coordination_campaigns', campaign_id)

    # Cancel Google Meet
    if campaign['meeting_zoom_link']:
        await meeting_scheduler.cancel_meeting(campaign['meeting_zoom_link'])

    # Send cancellation emails
    participants = db.execute("""
        SELECT email FROM campaign_participants
        WHERE campaign_id = %(id)s AND rsvp_status = 'yes'
    """, {'id': campaign_id})

    await outreach.send_campaign(
        campaign_id=campaign_id,
        actor_ids=[p['id'] for p in participants],
        template='campaign_cancelled',
        context={'reason': reason}
    )

    # Update database
    db.execute("""
        UPDATE coordination_campaigns
        SET status = 'cancelled', cancellation_reason = %(reason)s
        WHERE id = %(id)s
    """, {'id': campaign_id, 'reason': reason})

    # Archive checkpoint (preserve for analysis)
    # LangGraph checkpoints remain in database for debugging
```

### 10.3 Monitoring & Alerting

**Campaign Health Checks**:

```python
# Scheduled job: Check for stalled campaigns
async def check_stalled_campaigns():
    """Alert on campaigns stuck in wait state beyond timeout"""

    stalled = db.execute("""
        SELECT c.*, s.next, s.updated_at
        FROM coordination_campaigns c
        JOIN checkpoints s ON c.langgraph_thread_id = s.thread_id
        WHERE c.status = 'outreach'
          AND s.next = '["wait_rsvps"]'
          AND s.updated_at < NOW() - INTERVAL '7 days'
    """)

    for campaign in stalled:
        logger.warning(f"Campaign {campaign['id']} stalled at wait_rsvps for 7+ days")

        # Auto-cancel low-response campaigns
        rsvp_count = get_rsvp_count(campaign['id'])
        if rsvp_count < 3:
            await cancel_campaign(campaign['id'], reason='Insufficient RSVPs')
```

**LangSmith Alerting** (if using paid tier):

```python
from langsmith import Client

client = Client()

# Set up alerts for failed campaigns
client.create_alert(
    name="coordination_campaign_failures",
    condition="feedback.score < 0.5 OR status == 'error'",
    project=LANGSMITH_PROJECT,
    notification_channels=["email:ops@civic.org"]
)
```

---

## 11. Tactical Escalation Paths

### 11.1 The "Back to Tahrir" Problem

Movement research (Tufekci, 2017) identifies a critical failure mode: movements that succeed with one tactic then keep returning to it even when it stops working. Occupy kept returning to encampments; Egyptian protesters kept returning to Tahrir Square.

**Our response**: The coordination workflow must include escalation paths when initial tactics fail.

### 11.2 Escalation Workflow Extension

When `measure_impact` detects policy failure (decision went against residents despite coordinated testimony), the workflow should route to escalation options rather than END:

```
                          ┌──────────────────┐
                          │ measure_impact   │
                          └────────┬─────────┘
                                   │
                     ┌─────────────┼─────────────┐
                     │             │             │
                     ▼             ▼             ▼
              [WIN]         [PARTIAL]      [LOSS]
                │               │              │
                ▼               ▼              ▼
              END        ┌───────────┐   ┌───────────────┐
                         │ NEXT      │   │ ESCALATION    │
                         │ DECISION  │   │ OPTIONS       │
                         │ TRACKING  │   └───────┬───────┘
                         └───────────┘           │
                                    ┌────────────┼────────────┐
                                    ▼            ▼            ▼
                             [APPEAL]     [COALITION]   [MEDIA]
                             Board of     Regional      Press
                             Supervisors  Orgs          Campaign
```

### 11.3 Escalation Options

| Outcome | Next Lever | Time Horizon | Coordination Type |
|---------|-----------|--------------|-------------------|
| **Win** | Track implementation | 6-12 months | Accountability monitoring |
| **Partial** | Next related decision | 1-3 months | Same coalition, new venue |
| **Loss - Appealable** | Board of Supervisors | 30-60 days | Expanded coalition |
| **Loss - Policy** | State legislation | 6-12 months | Regional coalition |
| **Loss - Visibility** | Media campaign | 1-2 weeks | Public pressure |

### 11.4 Implementation Sketch

```python
def route_after_impact(state: CoordinationState) -> Literal["end", "track", "escalate"]:
    """Route based on campaign outcome"""
    if state['outcome_status'] == 'approved':
        return "end"  # Win - celebrate and archive
    elif state['outcome_status'] == 'amended':
        return "track"  # Partial - monitor next decision
    else:
        return "escalate"  # Loss - present escalation options

# Escalation node presents options to campaign organizers
class EscalationOptionsNode:
    def __call__(self, state: CoordinationState):
        options = self._generate_options(state)
        # Human-in-loop: Organizers choose escalation path
        return {**state, "escalation_options": options, "awaiting_escalation_choice": True}
```

**Key insight**: The workflow doesn't automatically escalate—it presents options. Human judgment determines if escalation is strategic or counterproductive.

---

## 12. Win Recognition System

### 12.1 Why Wins Matter

Movements sustain through visible wins. Zeynep Tufekci's research shows that slow organizing builds "organizational muscle" through accumulated victories—each win demonstrates efficacy and attracts new participants.

**Current gap**: The Impact Layer measures empowerment (surveys) but doesn't systematically capture and celebrate wins.

### 12.2 Win Types

| Win Type | Example | Visibility |
|----------|---------|-----------|
| **Policy Win** | Wildfire Fund allocated to vegetation management | High - press release |
| **Amendment Win** | Budget item increased after testimony | Medium - coalition email |
| **Acknowledgment Win** | Council member cites resident testimony | Medium - social share |
| **Participation Win** | 12 residents testified (vs 0 historical) | Low - internal metric |
| **Coalition Win** | New org joined coordination | Low - network growth |

### 12.3 Win Tracking Schema

```sql
-- Track wins for coalition morale and foundation reporting
CREATE TABLE coordination_wins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID REFERENCES coordination_campaigns(id),
    win_type TEXT NOT NULL CHECK (win_type IN
        ('policy', 'amendment', 'acknowledgment', 'participation', 'coalition')),
    description TEXT NOT NULL,
    evidence_url TEXT,  -- Link to meeting minutes, press coverage
    visibility TEXT CHECK (visibility IN ('internal', 'coalition', 'public')),
    celebrated_at TIMESTAMP,  -- When win was communicated
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_coordination_wins_campaign ON coordination_wins(campaign_id);
CREATE INDEX idx_coordination_wins_type ON coordination_wins(win_type);
```

### 12.4 Win Communication Flow

```
Campaign completes → measure_impact detects win → create win record
                                                        │
                                    ┌───────────────────┼───────────────────┐
                                    ▼                   ▼                   ▼
                             [INTERNAL]          [COALITION]           [PUBLIC]
                             Dashboard           Email to              Press release
                             update              participants          Social media
```

### 12.5 Foundation Reporting Integration

Wins feed directly into foundation grant reporting:

```python
def generate_foundation_report(quarter: str) -> dict:
    """Generate quarterly impact report for foundation funders"""
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

**Strategic value**: Foundation funders care about outcomes. Systematic win tracking makes grant renewals easier and demonstrates moat value.

---

## 13. Success Metrics

### 13.1 Campaign-Level Metrics

**Participation funnel** (LangSmith tracked):
```
Node: send_invitations → 40 invitations ✓
  ↓ (7 days wait)
Node: wait_rsvps → 18 RSVPs (45% conversion) ✓
  ↓ (threshold met)
Node: schedule_session → 14 attended (78% attendance) ✓
  ↓
Node: coordinate_live → 12 testified (86% testimony rate) ✓
  ↓
Node: measure_impact → 4.3/5 empowerment avg ✓
```

**Workflow efficiency metrics**:
- Average campaign duration: 21 days (detection to outcome)
- Checkpoint resume time: <100ms (instant resumability)
- Parallel discovery speedup: 2.1x (vs sequential)
- Failed campaign debug time: 15 minutes (vs hours without observability)

---

## 14. Next Steps

### 14.1 Immediate (This Week)

1. ✅ Review this updated architecture doc
2. **Install LangGraph**: `pip install langgraph langgraph-checkpoint-postgres`
3. **Prototype simple workflow**: detect → discover → END
4. **Validate approach**: Does LangGraph feel right for our use case?

### 14.2 Next Session (Implementation Start)

**If LangGraph feels right**:
- Build CoordinationState schema
- Implement decision detector agent
- Implement resident discovery agent
- Test checkpointing to Postgres
- Validate parallel execution

**If LangGraph doesn't feel right**:
- Fall back to custom orchestration (original architecture)
- At least we learned what agent frameworks offer

### 14.3 Month 1 (Full Implementation)

- Complete all agents (detect, discover, allocate, measure)
- Build custom nodes (email, scheduling, surveys)
- Implement conditional routing
- Add LangSmith observability
- End-to-end testing

### 14.4 Month 2+ (If Pilot Succeeds)

- Advanced multi-actor routing
- Frontend UI for testimony queue
- Outcome tracking automation
- Scale to 3-5 decisions/month
- Foundation pitch deck

---

## Phase 5 Data Integration (November 2025)

### ResidentDiscoveryAgent Data Sources

**San Rafael SeeClickFix Analysis** (1,340 complaints, 2009-2025):
- Source file: `data/pilot/seeclickfix_sanrafael_complete.json`
- Analysis: `data/pilot/PHASE5_LONGITUDINAL_ANALYSIS.md`

**Discovery Inputs**:

| Corridor | Complaints | Dominant Issue | Discovery Priority |
|----------|-----------|----------------|-------------------|
| 4th St | 40 | Parking (25%), Trees (18%) | High |
| 3rd St | 30 | Traffic (33%), Dumping (20%) | High |
| Lincoln Ave | 27 | Illegal dumping (37%) | High |
| Mission Ave | 22 | Abandoned vehicles (45%) | Medium |

**Example Query** (ResidentDiscoveryAgent):
```python
# Find residents affected by parking policy decision
SELECT * FROM seeclickfix_cache
WHERE jurisdiction_id = 'san-rafael'
  AND category LIKE '%parking%'
  AND address LIKE '%4th St%'
  AND created_at > '2024-01-01';
# Returns: ~10 residents who complained about parking on 4th St
```

### ImpactMeasurementAgent Data Sources

**Phase 5 Accountability Gap Finding**:
- 94% unresolved rate → validates outcome tracking need
- 53% stale >6 months → validates implementation monitoring
- 48% acknowledged → validates acknowledgment tracking

**Policy Feedback Loop** (Camping Ordinances):
```
Before ordinance (Jan-Mar 2024): 2.7 complaints/month
After ordinances (Sep 2024+):    6.9 complaints/month
3.4x increase AFTER policy with 3-6 month lag
```

**Implication for ImpactMeasurementAgent**:
- Track complaint volume before/after decisions
- Measure 3-6 month lag for policy effects
- Alert if complaints increase post-decision (accountability signal)

### Seasonal Patterns for Campaign Timing

**Phase 5 Finding**:
- **Peak complaint season**: May-November (2x winter volume)
- **Best campaign timing**: Spring (April-May) or Fall (November-December)
- **Weekday dominant**: 85% of complaints filed Mon-Fri

**Implication for Outreach Timing**:
- Schedule outreach campaigns on weekdays
- Align with seasonal peaks for maximum relevance

---

## Related Documentation

- `docs/strategy/FOCAL_POINT_DECISION_AWARENESS.md` - Pilot strategy + Phase 5 discovery data
- `docs/strategy/COMPETITIVE_POSITIONING.md` - Why coordination is the moat
- `docs/strategy/FOUNDATION_FUNDING_THESIS.md` - Sustainability model
- `docs/architecture/SEECLICKFIX_INTEGRATION_ARCHITECTURE.md` - Operational bridge
- `data/pilot/PHASE5_LONGITUDINAL_ANALYSIS.md` - Complete Phase 5 analysis
- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/
- **LangSmith Docs**: https://docs.smith.langchain.com/

---

## Appendix: Why LangGraph Over Alternatives

**Considered alternatives**:
1. **CrewAI** - Too focused on AI agents, not human coordination
2. **AutoGen** - Conversational focus, less structure for workflows
3. **Custom orchestration** - Reinvents proven patterns
4. **No framework** - More code, less observability

**Why LangGraph wins**:
1. ✅ State machines (declarative workflows)
2. ✅ Checkpointing (multi-week campaigns)
3. ✅ Human-in-loop (built-in interrupt patterns)
4. ✅ Parallel execution (discover actors concurrently)
5. ✅ Observability (LangSmith debugging)
6. ✅ Proven at scale (LangChain ecosystem)
7. ✅ PostgreSQL integration (our existing DB)

**The hybrid approach** (LangGraph + custom integrations) gives us best of both worlds:
- Agent framework handles orchestration complexity
- Custom code handles human coordination reality

---

**Remember**: This is the moat. Intelligence is table stakes. LangGraph helps us build coordination infrastructure faster, with better observability and resumability.

**The world is validating that intelligence is being commoditized. Double down on coordination with proven agent orchestration patterns.**
