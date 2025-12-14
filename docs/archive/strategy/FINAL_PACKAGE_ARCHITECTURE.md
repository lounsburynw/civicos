# Final Package Architecture

**Status**: Approved
**Date**: 2025-11-27
**Version**: 2.1 (adds action API + feedback loops + AI orchestration)

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

## Public API

### Query Methods (Learn)

```python
from civic import Civic

c = Civic("san-rafael-ca")

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

```
civic/
├── pyproject.toml
├── src/civic/
│   │
│   ├── __init__.py                 # Public API exports
│   ├── civic.py                    # Civic class - main entry point
│   │
│   ├── # ─────────── QUERY MODULES ───────────
│   ├── context.py                  # what_applies()
│   ├── history.py                  # what_happened()
│   ├── calendar.py                 # whats_next()
│   ├── community.py                # whos_with_me()
│   │
│   ├── # ─────────── ACTION MODULES ───────────
│   ├── actions/
│   │   ├── __init__.py
│   │   ├── initiatives.py          # start_something()
│   │   ├── voices.py               # add_voice()
│   │   ├── subscriptions.py        # follow()
│   │   └── preparation.py          # prepare()
│   │
│   ├── # ─────────── AI ORCHESTRATION (LangGraph) ───────────
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── graphs/                 # LangGraph workflow definitions
│   │   │   ├── __init__.py
│   │   │   ├── coordination.py     # Main coordination workflow
│   │   │   ├── suggestion.py       # Suggestion generation workflow
│   │   │   └── preparation.py      # Meeting prep workflow
│   │   ├── nodes/                  # Individual LangGraph nodes
│   │   │   ├── __init__.py
│   │   │   ├── detect.py           # Score decision importance
│   │   │   ├── discover.py         # Find affected residents
│   │   │   ├── suggest.py          # Generate suggestions
│   │   │   ├── plan.py             # Create coordination plans
│   │   │   └── learn.py            # Extract patterns from outcomes
│   │   ├── state.py                # Shared state schemas (TypedDict)
│   │   └── checkpointer.py         # PostgreSQL checkpointer for production
│   │
│   ├── # ─────────── FEEDBACK SYSTEM ───────────
│   ├── feedback/
│   │   ├── __init__.py
│   │   ├── events.py               # Event capture
│   │   ├── store.py                # Event storage
│   │   └── analyzer.py             # Pattern analysis
│   │
│   ├── # ─────────── JURISDICTION MODEL ───────────
│   ├── jurisdiction/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── simple.py
│   │   ├── complex.py
│   │   ├── resolver.py
│   │   └── loader.py
│   │
│   ├── # ─────────── DATA LAYER (internal) ───────────
│   ├── _corpus/
│   │   ├── __init__.py
│   │   ├── search.py
│   │   ├── providers/
│   │   │   ├── base.py
│   │   │   ├── municode.py
│   │   │   ├── american_legal.py
│   │   │   └── leginfo.py
│   │   ├── state/
│   │   │   └── california.py
│   │   └── municipal/
│   │       └── generic.py
│   │
│   ├── _decisions/
│   │   ├── __init__.py
│   │   ├── store.py
│   │   ├── extractor.py
│   │   └── classifier.py
│   │
│   ├── _activity/
│   │   ├── __init__.py
│   │   ├── meetings.py
│   │   ├── initiatives.py          # User-created initiatives
│   │   ├── voices.py               # Comments, support, opposition
│   │   └── subscriptions.py        # What users follow
│   │
│   └── # ─────────── MCP SERVER ───────────
│       mcp.py                      # Unified MCP server
│
├── config/
│   ├── states/
│   └── jurisdictions/
│
└── tests/
```

---

## MCP Server (AI Interface)

```python
# civic/mcp.py
from mcp.server import Server
from civic import Civic

server = Server("civic")

# ─────────── QUERY TOOLS ───────────

@server.tool()
def what_applies(jurisdiction: str, topic: str, location: str = None) -> dict:
    """Get regulatory stack for a topic.

    Use when user asks: "What are the rules for...", "Can I...", "Is it legal to..."
    """
    return Civic(jurisdiction).what_applies(topic, location)

@server.tool()
def what_happened(jurisdiction: str, query: str, since: str = None) -> list:
    """Search past decisions.

    Use when user asks: "Has the city ever...", "What happened with...", "Any precedent for..."
    """
    return Civic(jurisdiction).what_happened(query, since)

@server.tool()
def whats_next(jurisdiction: str, topics: list = None, days: int = 30) -> list:
    """Get upcoming meetings and agendas.

    Use when user asks: "When can I...", "Is there a meeting about...", "How do I participate..."
    """
    return Civic(jurisdiction).whats_next(topics, days)

@server.tool()
def whos_with_me(jurisdiction: str, topic: str) -> dict:
    """Find others who care about this topic.

    Use when user asks: "Am I alone in...", "Who else cares about...", "Is anyone working on..."
    """
    return Civic(jurisdiction).whos_with_me(topic)

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
    return Civic(jurisdiction).start_something(topic, title, description, location)

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
    return Civic(jurisdiction).add_voice(item_type, item_id, stance, comment)

@server.tool()
def follow(jurisdiction: str, item_type: str, item_id: str) -> dict:
    """Follow an item for updates.

    Use when user says: "Keep me posted on...", "Let me know when...", "Track this for me..."
    """
    return Civic(jurisdiction).follow(item_type, item_id)

@server.tool()
def prepare(jurisdiction: str, agenda_item_id: str) -> dict:
    """Get preparation materials for participating.

    Use when user says: "I'm going to the meeting...", "How do I testify about...", "Help me prepare..."
    Returns: context, talking points, who else is going, logistics.
    """
    return Civic(jurisdiction).prepare(agenda_item_id)

# ─────────── ORCHESTRATION TOOLS ───────────

@server.tool()
def get_suggestions(jurisdiction: str, user_id: str = None) -> list:
    """Get proactive suggestions for user.

    AI should call this periodically or at session start to surface opportunities.
    """
    return Civic(jurisdiction).suggestions(user_id)

@server.tool()
def coordinate(jurisdiction: str, initiative_id: str, action: str) -> dict:
    """Request coordination support.

    Use when initiative is ready for collective action.
    Actions: "schedule_meeting", "draft_letter", "plan_testimony", "notify_supporters"
    """
    return Civic(jurisdiction).coordinate(initiative_id, action)

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
    return Civic(jurisdiction).report_outcome(item_id, outcome, notes)
```

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

## Migration from Current Packages

| Current | New Location | Notes |
|---------|--------------|-------|
| `civic-state` StateManager | `_activity/` | Becomes internal |
| `civic-state` issues | `_activity/initiatives.py` + `actions/initiatives.py` | Split read/write |
| `civic-state` follows | `_activity/subscriptions.py` + `actions/subscriptions.py` | Split read/write |
| `civic-legal` | `_corpus/state/california.py` | CA-specific |
| `civic-enrichment` | `_corpus/search.py` | Merge into search |
| `civic-coordination` | `orchestrator/` | Expand significantly |
| `src/coordination_graph.py` | `orchestrator/graphs/coordination.py` | LangGraph prototype → production |

### LangGraph Migration

The existing `src/coordination_graph.py` (280 lines) becomes the foundation:

```
src/coordination_graph.py
├── CoordinationState        → orchestrator/state.py
├── detect_decision()        → orchestrator/nodes/detect.py
├── discover_residents()     → orchestrator/nodes/discover.py
├── create_coordination_workflow() → orchestrator/graphs/coordination.py
└── MemorySaver              → orchestrator/checkpointer.py (PostgresSaver)
```

Key upgrades:
1. **MemorySaver → PostgresSaver** for persistence across restarts
2. **Add human-in-the-loop** for coordination approval
3. **Add more workflows** (suggestion, preparation)
4. **Integrate with public API** (`c.coordinate()` triggers workflow)

---

## Implementation Priority

### Phase 1: Pilot (Jan 2025)
- [ ] Query methods (4)
- [ ] Basic action methods (start_something, add_voice, follow)
- [ ] Simple suggestions (upcoming meetings matching interests)
- [ ] MCP server with all tools

### Phase 2: Coordination (Mar 2025)
- [ ] prepare() method
- [ ] coordinate() method
- [ ] Coordination planner
- [ ] Outcome tracking

### Phase 3: Learning (Jun 2025)
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
