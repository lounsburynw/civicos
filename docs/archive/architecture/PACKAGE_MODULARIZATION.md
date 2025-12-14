# Package Modularization Architecture

**Created**: 2025-11-27 (Session 120)
**Status**: Design Proposal
**Goal**: Transform monolithic `src/` into reusable packages

---

## Executive Summary

Transform the current 67-file monolithic `src/` directory into **5 reusable packages** that can be:
1. Used independently in other civic tech projects
2. Distributed as standalone Python packages (PyPI)
3. Composed together for the full civic platform

**Key Principle**: Each package should be usable WITHOUT the others where possible.

---

## Proposed Package Structure

```
civic/                                    # Project root
├── packages/                             # Reusable packages
│   ├── civic-state/                      # StateManager + temporal data + MCP
│   ├── civic-extraction/                 # Multi-platform parsers + MCP
│   ├── civic-enrichment/                 # Legislative context + matching + MCP
│   └── civic-coordination/               # LangGraph workflows
│
├── src/                                  # Application layer (uses packages)
│   ├── api/                              # REST API server
│   ├── chat/                             # Chat routing
│   └── websocket/                        # Real-time messaging
│
├── frontend/                             # Vue workspace (unchanged)
├── scripts/                              # CLI tools and utilities
└── data/                                 # Data files (unchanged)
```

---

## Package Specifications

### 1. `civic-state` - Temporal State Management

**Purpose**: Single source of truth for civic data with temporal versioning.

**Reusability**: Any project needing versioned data with "state at time T" queries.

```
packages/civic-state/
├── pyproject.toml
├── README.md
├── civic_state/
│   ├── __init__.py
│   ├── manager.py              # StateManager class (from state_manager.py)
│   ├── models.py               # Pydantic models (Issue, Meeting, AgendaItem)
│   ├── temporal.py             # Temporal query helpers
│   ├── migrations/             # SQL migrations
│   │   ├── 001_initial.sql
│   │   └── ...
│   └── backends/
│       ├── sqlite.py           # SQLite backend
│       └── postgres.py         # PostgreSQL backend (future)
└── tests/
    └── test_state_manager.py
```

**Public API**:
```python
from civic_state import StateManager

sm = StateManager("civic_state.db")
sm.upsert_issues(jurisdiction_id, issues)
sm.query_issues(jurisdiction_id, street="5th", status="open")
sm.get_city_state(jurisdiction_id, as_of=datetime)
```

**Dependencies**: `pydantic`, `sqlite3` (stdlib)

---

### 2. MCP Integration (Co-located in Each Package)

**Design Decision**: MCP servers are co-located within each package, not in a separate `civic-mcp` package.

**Rationale**:
- Each package is self-contained (data + interface together)
- Install one package, get its MCP server too
- No extra wrapper package needed

**Pattern** (each package follows this):
```
packages/civic-state/
├── src/civic_state/
│   ├── manager.py      # Core functionality
│   └── mcp.py          # Optional MCP server (requires: pip install civic-state[mcp])
│   ├── client.py               # MCP client utilities
│   └── adapters/
│       └── langgraph.py        # LangGraph adapter helpers
└── tests/
    ├── test_issues_server.py
    └── test_langgraph_integration.py
```

**Public API**:
```python
# Running servers
from civic_mcp.servers import issues, events, legislative

# As CLI
python -m civic_mcp.servers.issues --http --port 8080

# LangGraph integration
from civic_mcp.adapters.langgraph import get_civic_tools
tools = await get_civic_tools(["issues", "events"])
```

**Dependencies**: `mcp`, `civic-state`, `langchain-mcp-adapters` (optional)

---

### 3. `civic-extraction` - Multi-Platform Parsers

**Purpose**: Extract civic data from municipal platforms (Legistar, CivicClerk, etc.)

**Reusability**: Any project needing to scrape government meeting data.

```
packages/civic-extraction/
├── pyproject.toml
├── README.md
├── civic_extraction/
│   ├── __init__.py
│   ├── base.py                 # BaseExtractor ABC
│   ├── schema.py               # civic-app-schema.json as Pydantic
│   ├── platforms/
│   │   ├── __init__.py
│   │   ├── legistar.py         # Legistar API client
│   │   ├── civicclerk.py       # CivicClerk API client
│   │   ├── granicus.py         # Granicus HTML parser
│   │   ├── seeclickfix.py      # SeeClickFix API client
│   │   └── html.py             # Generic HTML parser
│   ├── agenda/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py       # PDF agenda extraction
│   │   └── actionability.py    # LLM actionability assessment
│   └── registry.py             # Platform detection + routing
└── tests/
    ├── test_legistar.py
    ├── test_civicclerk.py
    └── test_seeclickfix.py
```

**Public API**:
```python
from civic_extraction import extract_events
from civic_extraction.platforms import LegistarClient, SeeClickFixClient

# Auto-detect platform
events = extract_events("https://berkeley.legistar.com/Calendar.aspx")

# Direct client usage
client = SeeClickFixClient()
issues = client.get_issues("san-rafael", status="open")
```

**Dependencies**: `requests`, `beautifulsoup4`, `pdfplumber`, `openai` (optional for LLM)

---

### 4. `civic-enrichment` - Legislative Context

**Purpose**: Match civic data to state bills and federal programs.

**Reusability**: Any project needing legislative context for local government data.

```
packages/civic-enrichment/
├── pyproject.toml
├── README.md
├── civic_enrichment/
│   ├── __init__.py
│   ├── matcher.py              # Keyword + semantic matching
│   ├── validator.py            # Reference validation (99.99% accuracy)
│   ├── cache.py                # Legislative context cache with TTL
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── state_bills.py      # State legislation data
│   │   ├── federal_programs.py # Federal programs (CDBG, HUD, etc.)
│   │   └── legiscan.py         # LegiScan API client
│   └── data/                   # Bundled legislative data
│       ├── california_bills.json
│       └── federal_programs.json
└── tests/
    ├── test_matcher.py
    └── test_validator.py
```

**Public API**:
```python
from civic_enrichment import enrich_agenda_item, validate_reference

# Enrich an agenda item
enriched = enrich_agenda_item({
    "title": "Affordable Housing Development",
    "project_type": "housing"
})
# Returns: {"relevant_bills": ["AB-1482", "SB-423"], "federal_programs": ["CDBG"]}

# Validate a citation
is_valid, correction = validate_reference("AB-148")  # Returns (False, "AB-1482")
```

**Dependencies**: `civic-state` (for caching), `openai` (optional for semantic)

---

### 5. `civic-coordination` - LangGraph Workflows

**Purpose**: Multi-step coordination workflows for civic engagement campaigns.

**Reusability**: Any project needing human-in-the-loop AI workflows.

```
packages/civic-coordination/
├── pyproject.toml
├── README.md
├── civic_coordination/
│   ├── __init__.py
│   ├── state.py                # CoordinationState schema
│   ├── workflows/
│   │   ├── __init__.py
│   │   ├── decision_awareness.py  # Main coordination workflow
│   │   └── outreach.py            # Outreach sub-workflow
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── detector.py         # Decision detector agent
│   │   ├── discovery.py        # Actor discovery agent
│   │   └── allocator.py        # Testimony allocator agent
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── email.py            # SendGrid integration
│   │   ├── calendar.py         # Google Calendar integration
│   │   └── survey.py           # Survey delivery
│   └── checkpointing/
│       ├── memory.py           # Memory checkpointer (dev)
│       └── postgres.py         # PostgreSQL checkpointer (prod)
└── tests/
    ├── test_workflow.py
    └── test_agents.py
```

**Public API**:
```python
from civic_coordination import run_coordination_campaign
from civic_coordination.workflows import DecisionAwarenessWorkflow

# Run a campaign
result = await run_coordination_campaign(
    decision_id="sr-2025-02-12-wildfire",
    jurisdiction_id="city-san-rafael"
)

# Custom workflow
workflow = DecisionAwarenessWorkflow(
    checkpointer="postgres://...",
    interrupt_before=["send_outreach"]
)
app = workflow.compile()
```

**Dependencies**: `langgraph`, `civic-state`, `civic-mcp` (optional)

---

## Application Layer (`src/`)

The application layer composes packages into the full civic platform:

```
src/
├── api/
│   ├── __init__.py
│   ├── server.py               # FastAPI app (civic_api_integrated.py)
│   ├── routes/
│   │   ├── events.py           # Event endpoints
│   │   ├── issues.py           # Issue endpoints
│   │   ├── chat.py             # Chat routing endpoints
│   │   └── coordination.py     # Coordination campaign endpoints
│   └── middleware/
│       ├── auth.py             # Bearer token auth
│       └── rate_limit.py       # Rate limiting
│
├── chat/
│   ├── __init__.py
│   ├── router.py               # Chat routing (civic_chat_router.py)
│   └── providers/              # LLM providers (existing)
│
├── websocket/
│   ├── __init__.py
│   └── server.py               # Socket.io server
│
└── cli/
    ├── __init__.py
    └── refresh.py              # automated_civic_refresh.py
```

---

## Migration Strategy

### Phase 1: Create Package Scaffolding (Week 1)

1. Create `packages/` directory structure
2. Add `pyproject.toml` for each package
3. Create `__init__.py` with public API stubs

### Phase 2: Extract `civic-state` (Week 2)

1. Move `state_manager.py` → `packages/civic-state/civic_state/manager.py`
2. Extract models into `models.py`
3. Update imports in dependent files
4. Add tests

### Phase 3: Extract `civic-mcp` (Week 3)

1. Move `mcp_servers/` → `packages/civic-mcp/civic_mcp/servers/`
2. Create `civic-events` and `civic-legislative` servers
3. Add LangGraph adapter
4. Update tests

### Phase 4: Extract `civic-extraction` (Week 4)

1. Move platform clients (`legistar_client.py`, etc.) → package
2. Extract `civic_digest.py` extraction logic
3. Create platform registry
4. Add schema validation

### Phase 5: Extract `civic-enrichment` (Week 5)

1. Move `legislative_enrichment.py` → package
2. Move `legislative_reference_validator.py` → package
3. Bundle legislative data files
4. Add caching layer

### Phase 6: Extract `civic-coordination` (Week 6)

1. Move `coordination_graph.py` → package
2. Create agent modules
3. Add checkpointing backends
4. Create workflow builder API

### Phase 7: Refactor Application Layer (Week 7-8)

1. Update `src/` to use packages
2. Remove duplicated code
3. Update imports throughout
4. Integration testing

---

## Package Dependencies

```
                    ┌─────────────────────┐
                    │  civic-coordination │
                    │  (LangGraph)        │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
    ┌─────────────────┐ ┌─────────────┐ ┌─────────────────┐
    │   civic-mcp     │ │ civic-state │ │ civic-enrichment│
    │   (MCP servers) │ │ (StateManager)│ │ (Legislative)  │
    └────────┬────────┘ └──────┬──────┘ └────────┬────────┘
             │                 │                  │
             │                 │                  │
             └─────────────────┼──────────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  civic-extraction   │
                    │  (Platform parsers) │
                    └─────────────────────┘
```

**Dependency Rules**:
- `civic-extraction`: No package dependencies (standalone)
- `civic-state`: No package dependencies (standalone)
- `civic-enrichment`: Depends on `civic-state` (for caching)
- `civic-mcp`: Depends on `civic-state` (for data access)
- `civic-coordination`: Depends on all (orchestration layer)

---

## Standalone Usage Examples

### Example 1: Just Extract Meeting Data

```python
# Install only what you need
# pip install civic-extraction

from civic_extraction.platforms import LegistarClient

client = LegistarClient("berkeley")
events = client.get_events(days_future=30)

for event in events:
    print(f"{event.title} - {event.meeting_datetime}")
```

### Example 2: Query Civic Data via MCP

```python
# pip install civic-mcp civic-state

# Start MCP server
# python -m civic_mcp.servers.issues --http --port 8080

# Use with Claude Desktop or LangGraph
```

### Example 3: Add Legislative Context

```python
# pip install civic-enrichment

from civic_enrichment import enrich_agenda_item

item = {
    "title": "Wildfire Prevention Fund Allocation",
    "project_type": "environment"
}

enriched = enrich_agenda_item(item)
print(enriched["relevant_bills"])  # ["SB-423", "AB-1001"]
```

---

## Benefits

### For This Project
- **Cleaner codebase**: 67 files → 5 focused packages
- **Easier testing**: Test packages independently
- **Better documentation**: Each package has its own README

### For Reusability
- **Other civic tech projects** can use individual packages
- **Foundation pitch**: "We built reusable civic infrastructure"
- **Open source value**: Others can contribute to specific packages

### For Resilience
- **If civic hypothesis fails**: Packages remain valuable
- **StateManager pattern**: Useful for any temporal data project
- **MCP servers**: Useful for any AI-data integration
- **LangGraph workflows**: Useful for any coordination project

---

## Open Questions

1. **Monorepo vs Multi-repo?**
   - Monorepo (recommended): Easier development, atomic commits
   - Multi-repo: Harder coordination, independent versioning

2. **Package naming?**
   - `civic-state` vs `civic_state` vs `civicstate`
   - PyPI namespace: `civic-*` or `civictech-*`?

3. **Minimum Python version?**
   - Python 3.10+ (for modern type hints)
   - Python 3.9 (broader compatibility)

4. **When to publish to PyPI?**
   - After pilot validation
   - When first external user appears

---

## Next Steps

1. **Review this proposal** - Feedback on structure?
2. **Prioritize packages** - Which to extract first?
3. **Create scaffolding** - `packages/` directory + pyproject.toml
4. **Start with `civic-state`** - Foundation for others

---

*Created: Session 120 (2025-11-27)*
