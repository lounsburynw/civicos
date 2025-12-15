# MCP Integration Strategy

**Created**: 2025-11-24 (Session 118)
**Status**: Strategy Defined, Implementation Starting Session 119
**Priority**: Strategic - Industry standards adoption for portability

---

## Executive Summary

**Decision**: Adopt MCP (Model Context Protocol) incrementally for new integrations, not as a full migration.

**Why Now**: MCP is becoming the industry standard for AI-tool integration (Anthropic, Vercel, OpenAI ecosystem). Building on standards ensures portability and ecosystem access.

**Approach**: New integrations as MCP-native servers. Existing REST API remains for frontend. LangGraph workflows can consume MCP tools.

**First Target**: StateManager as MCP server (Session 119, ~50 lines)

---

## Table of Contents

1. [What is MCP](#1-what-is-mcp)
2. [Strategic Rationale](#2-strategic-rationale)
3. [Integration Architecture](#3-integration-architecture)
4. [Implementation Plan](#4-implementation-plan)
5. [MCP Server Specifications](#5-mcp-server-specifications)
6. [LangGraph Integration](#6-langgraph-integration)
7. [Frontend Considerations](#7-frontend-considerations)
8. [Decision Points](#8-decision-points)

---

## 1. What is MCP

### 1.1 Model Context Protocol Overview

MCP (Model Context Protocol) is an open standard introduced by Anthropic in November 2024 for connecting AI systems to external tools and data sources.

**Key Concepts**:
- **MCP Servers**: Expose tools/resources that AI can call
- **MCP Clients**: AI applications that consume MCP servers
- **Transport**: stdio (local) or SSE (remote)
- **Tools**: Functions AI can invoke with structured inputs/outputs

**Example**:
```python
# MCP Server exposes a tool
@server.tool("query_issues")
def query_issues(jurisdiction: str, street: str = None):
    """Query civic issues by jurisdiction and street"""
    return StateManager().query_issues(jurisdiction, street=street)

# MCP Client (any AI) can call it
# Claude Desktop, GPT, local models, custom apps
```

### 1.2 Why MCP Matters

**Industry Adoption**:
- Anthropic (Claude Desktop, Claude API)
- Vercel (AI SDK 4.2+, native MCP support)
- Growing ecosystem of pre-built servers (GitHub, Slack, Filesystem)

**The M×N Problem**:
Without MCP: M AI models × N tools = M×N custom integrations
With MCP: M AI models + N tools = M+N MCP implementations

### 1.3 MCP vs REST API

| Aspect | REST API | MCP Server |
|--------|----------|------------|
| Consumer | Frontend, custom apps | Any MCP-compatible AI |
| Discovery | Manual documentation | Auto-discovery via protocol |
| Schema | OpenAPI/JSON Schema | MCP tool definitions |
| Transport | HTTP | stdio/SSE |
| Use Case | Frontend integration | AI tool integration |

**Our Approach**: Keep REST API for frontend, add MCP for AI interoperability.

---

## 2. Strategic Rationale

### 2.1 Benefits for Civic Platform

1. **Portability**
   - Civic data queryable by Claude, GPT, Gemini, local models
   - No lock-in to specific AI provider
   - Future-proof as AI ecosystem evolves

2. **Standards Compliance**
   - Industry-standard protocol
   - Community-maintained tooling
   - Documentation and best practices

3. **Ecosystem Access**
   - Pre-built MCP servers for GitHub, Slack, Calendar
   - Can compose workflows using external tools
   - LangGraph can orchestrate MCP tools

4. **Developer Experience**
   - Claude Desktop can query San Rafael issues directly
   - Any MCP client can access civic data
   - Faster prototyping for new AI features

### 2.2 Risk Assessment

**Low Risk**:
- Incremental adoption (not migration)
- Existing REST API unchanged
- MCP is open standard (Apache 2.0)

**Considerations**:
- MCP SDK maturity (still evolving)
- Security model for public deployment
- Overhead of maintaining both REST + MCP

### 2.3 Decision: Incremental Adoption

```
EXISTING (keep as-is):
├── civic_api_integrated.py    # REST API for Vue frontend
├── civic_chat_router.py       # Custom chat routing
├── civic_socketio_server.py   # WebSocket for real-time
└── coordination_graph.py      # LangGraph workflows

NEW WORK (MCP-native):
├── apps/civic-mcp/
│   ├── civic_issues.py        # StateManager queries
│   ├── civic_events.py        # Events/agendas
│   ├── legislative.py         # Bills/programs
│   └── seeclickfix.py         # SeeClickFix client
```

---

## 3. Integration Architecture

### 3.1 System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CIVIC PLATFORM ARCHITECTURE                           │
│                    (with MCP Integration Layer)                          │
└─────────────────────────────────────────────────────────────────────────┘

                          ┌─────────────────────┐
                          │   Vue Frontend      │
                          │   (civic-workspace) │
                          └──────────┬──────────┘
                                     │ REST API
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         EXISTING LAYER                                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   │
│  │ civic_api_       │   │ civic_chat_      │   │ civic_socketio_  │   │
│  │ integrated.py    │   │ router.py        │   │ server.py        │   │
│  │ (REST API)       │   │ (Chat)           │   │ (WebSocket)      │   │
│  └────────┬─────────┘   └──────────────────┘   └──────────────────┘   │
│           │                                                             │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                    StateManager / Data Layer                      │  │
│  │  • state_manager.py (issues, meetings, agendas)                  │  │
│  │  • seeclickfix_client.py (operational complaints)                │  │
│  │  • legislative_context_cache.py (bills, programs)                │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└────────────────────────────────────────────────────────────────────────┘
                                     │
                                     │ Wrapped by
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         MCP LAYER (NEW)                                 │
├────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   │
│  │ apps/civic-mcp/     │   │ apps/civic-mcp/     │   │ apps/civic-mcp/     │   │
│  │ civic_issues.py  │   │ civic_events.py  │   │ legislative.py   │   │
│  │                  │   │                  │   │                  │   │
│  │ Tools:           │   │ Tools:           │   │ Tools:           │   │
│  │ • query_issues   │   │ • get_events     │   │ • get_bills      │   │
│  │ • get_stats      │   │ • get_agenda     │   │ • get_programs   │   │
│  │ • query_corridor │   │ • search_events  │   │ • match_topic    │   │
│  └────────┬─────────┘   └────────┬─────────┘   └────────┬─────────┘   │
│           │                      │                      │              │
│           └──────────────────────┼──────────────────────┘              │
│                                  │                                      │
│                                  ▼                                      │
│                        ┌──────────────────┐                            │
│                        │   MCP Protocol   │                            │
│                        │   (stdio/SSE)    │                            │
│                        └────────┬─────────┘                            │
│                                 │                                       │
└─────────────────────────────────┼───────────────────────────────────────┘
                                  │
                  ┌───────────────┼───────────────┐
                  │               │               │
                  ▼               ▼               ▼
           ┌────────────┐ ┌────────────┐ ┌────────────┐
           │ Claude     │ │ LangGraph  │ │ Custom     │
           │ Desktop    │ │ Workflows  │ │ AI Apps    │
           └────────────┘ └────────────┘ └────────────┘
```

### 3.2 Data Flow

**Current Flow (REST)**:
```
Vue Frontend → REST API → StateManager → SQLite
```

**New Flow (MCP)**:
```
Any MCP Client → MCP Server → StateManager → SQLite
```

**Combined Flow**:
```
Vue Frontend ──────────────────────────┐
                                       ▼
                              ┌──────────────────┐
Claude Desktop ───┐           │                  │
                  ├──► MCP ──►│  StateManager    │──► SQLite
LangGraph ────────┘           │                  │
                              └──────────────────┘
```

---

## 4. Implementation Plan

### 4.1 Phase 1: StateManager MCP Server (Session 119)

**Goal**: Expose StateManager queries via MCP

**File**: `apps/civic-mcp/civic_issues.py`

**Tools**:
| Tool | Description | Parameters |
|------|-------------|------------|
| `query_issues` | Query civic issues | jurisdiction, street?, issue_type?, limit? |
| `get_issue_stats` | Get issue statistics | jurisdiction |
| `query_corridor` | Query by corridor name | jurisdiction, corridor |

**Effort**: 1-2 hours

### 4.2 Phase 2: Events/Agendas MCP Server (Future)

**Goal**: Expose event and agenda data via MCP

**File**: `apps/civic-mcp/civic_events.py`

**Tools**:
| Tool | Description | Parameters |
|------|-------------|------------|
| `get_events` | Get upcoming events | jurisdiction, days_future? |
| `get_agenda` | Get agenda items for event | event_id |
| `search_events` | Search events by topic | jurisdiction, topic, date_from?, date_to? |

### 4.3 Phase 3: Legislative Context MCP Server (Future)

**Goal**: Expose legislative data via MCP

**File**: `apps/civic-mcp/legislative.py`

**Tools**:
| Tool | Description | Parameters |
|------|-------------|------------|
| `get_bills` | Get bills by topic | topic |
| `get_programs` | Get federal programs | topic |
| `match_topic` | Match text to legislative context | text |

### 4.4 Phase 4: LangGraph Integration (Future)

**Goal**: LangGraph workflows use MCP tools instead of direct imports

**Before**:
```python
from state_manager import StateManager
sm = StateManager()
issues = sm.query_issues(jurisdiction, street=street)
```

**After**:
```python
from langchain_mcp_adapters import MCPToolkit
toolkit = MCPToolkit(server_url="http://localhost:8080")
tools = toolkit.get_tools()
# LangGraph nodes use tools via MCP
```

---

## 5. MCP Server Specifications

### 5.1 Civic Issues Server

```python
# apps/civic-mcp/civic_issues.py
"""
MCP Server for Civic Issues (StateManager wrapper)

Exposes civic issue queries to any MCP-compatible AI client.
"""

from mcp.server import Server
from mcp.types import Tool, TextContent
import sys
sys.path.insert(0, 'src')
from state_manager import StateManager

server = Server("civic-issues")

@server.tool("query_issues")
def query_issues(
    jurisdiction: str,
    street: str = None,
    issue_type: str = None,
    status: str = None,
    limit: int = 50
) -> list:
    """
    Query civic issues by jurisdiction and optional filters.

    Args:
        jurisdiction: City identifier (e.g., "city-san-rafael")
        street: Filter by street name (partial match)
        issue_type: Filter by issue type (e.g., "parking", "traffic")
        status: Filter by status (open, closed, acknowledged)
        limit: Maximum results (default 50)

    Returns:
        List of issue dictionaries with address, type, status, created_at
    """
    sm = StateManager('data/civic_state.db')
    return sm.query_issues(
        jurisdiction,
        street=street,
        issue_type=issue_type,
        status=status,
        limit=limit
    )

@server.tool("get_issue_stats")
def get_issue_stats(jurisdiction: str) -> dict:
    """
    Get statistics about issues for a jurisdiction.

    Args:
        jurisdiction: City identifier (e.g., "city-san-rafael")

    Returns:
        Dictionary with total_issues, by_status, top_types
    """
    sm = StateManager('data/civic_state.db')
    return sm.get_issue_stats(jurisdiction)

@server.tool("query_corridor")
def query_corridor(jurisdiction: str, corridor: str) -> dict:
    """
    Query issues by named corridor (convenience method).

    Args:
        jurisdiction: City identifier
        corridor: Corridor name (e.g., "4th St", "Lincoln Ave")

    Returns:
        Dictionary with issues and summary statistics
    """
    sm = StateManager('data/civic_state.db')
    issues = sm.query_issues(jurisdiction, street=corridor)

    # Summarize by type
    type_counts = {}
    for issue in issues:
        t = issue.get('issue_type', 'Unknown')
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "corridor": corridor,
        "total_issues": len(issues),
        "by_type": type_counts,
        "issues": issues[:20]  # Return top 20 for context
    }

if __name__ == "__main__":
    import asyncio
    asyncio.run(server.run())
```

### 5.2 Running the Server

**Local (stdio)**:
```bash
# For Claude Desktop
python apps/civic-mcp/civic_issues.py
```

**Remote (SSE)**:
```bash
# For remote clients
uvicorn mcp_servers.civic_issues:app --host 0.0.0.0 --port 8080
```

### 5.3 Claude Desktop Configuration

```json
// ~/.config/claude/config.json (macOS)
{
  "mcpServers": {
    "civic-issues": {
      "command": "python",
      "args": ["/path/to/civic/apps/civic-mcp/civic_issues.py"]
    }
  }
}
```

---

## 6. LangGraph Integration

### 6.1 Using MCP Tools in LangGraph

```python
# src/coordination_graph.py (future update)
from langchain_mcp_adapters import MCPToolkit
from langgraph.graph import StateGraph

# Connect to MCP server
toolkit = MCPToolkit(server_url="http://localhost:8080")
mcp_tools = toolkit.get_tools()

def discover_residents_via_mcp(state: CoordinationState) -> CoordinationState:
    """
    Discovery node using MCP tools instead of direct imports.
    """
    query_issues = mcp_tools["query_issues"]

    # Query via MCP
    issues = query_issues.invoke({
        "jurisdiction": state["jurisdiction_id"],
        "street": state.get("corridor"),
        "limit": 50
    })

    return {
        **state,
        "actors": {"residents": issues}
    }
```

### 6.2 Benefits of MCP in LangGraph

1. **Decoupling**: Workflow doesn't depend on StateManager import
2. **Portability**: Same workflow can use any MCP-compatible data source
3. **Observability**: MCP calls visible in LangSmith traces
4. **Scalability**: MCP servers can be deployed independently

---

## 7. Frontend Considerations

### 7.1 Current State

Vue frontend uses REST API (`civic_api_integrated.py`). No changes needed for MCP adoption.

### 7.2 Future: MCP-UI Components

MCP-UI (https://mcpui.dev/) provides:
- React and Web Components for rendering MCP resources
- Sandboxed iframe security
- Interactive UI that AI can compose

**Potential Use Cases**:
- AI-generated issue cards
- Dynamic legislative context panels
- Agent-rendered coordination dashboards

### 7.3 Migration Path

```
Phase 1: Backend MCP (current focus)
  └── MCP servers expose data

Phase 2: Keep REST for Frontend
  └── Vue continues using REST API

Phase 3: Evaluate MCP-UI (future)
  └── Consider Web Components for AI-rendered UI
```

---

## 8. Decision Points

### 8.1 After Phase 1 (Session 119)

```
IF MCP server works smoothly:
  → Continue with civic_events.py, legislative.py
  → Update LangGraph to use MCP tools
  → Consider MCP-UI for frontend components

IF MCP adds too much complexity:
  → Keep REST API for all integrations
  → Use MCP only for Claude Desktop experimentation
```

### 8.2 MCP vs Direct Integration

**Use MCP when**:
- External AI clients need access
- Portability across AI providers matters
- Composing with external MCP servers

**Use direct integration when**:
- Frontend-specific endpoints
- High-performance requirements
- Tight coupling acceptable

---

## 9. City Integration Modes

### 9.1 Strategic Context: Parsing vs Official Adoption

**Key Insight**: The foundation-funded model ($50-100K/year/region) implies city partnerships, not scraping. This fundamentally changes the value of parser infrastructure.

**Growth Model Comparison**:

| Path | Description | Parser Value | Our Focus |
|------|-------------|--------------|-----------|
| **Grassroots** | Community parsers → Coverage → Cities notice | High | Data acquisition |
| **Top-Down** | Foundation funding → City partnership → Direct integration | Low | Intelligence layer |
| **Hybrid** | Parse to demonstrate → City adopts → Deprecate parser | Medium (temporary) | Both |

**Conclusion**: Don't over-invest in parser abstraction. Focus on intelligence (enrichment, coordination) and integration modes that support official adoption.

### 9.2 Four Integration Modes

```
CITY INTEGRATION MODES
━━━━━━━━━━━━━━━━━━━━━━

Mode 1: PARSE (Bootstrap/Legacy)
├── We scrape city's public data
├── Existing *_client.py files
├── No city involvement required
└── Use for: Demonstrating value before partnership

Mode 2: API ACCESS (Privileged)
├── City provides API keys or allowlisted access
├── Same data, better reliability
├── City aware but passive
└── Use for: Early partnership, pilot cities

Mode 3: PUSH (Official Adoption)
├── City pushes data to our ingestion API
├── They use civic-app-schema.json format
├── City is active partner
└── Use for: Full adoption, production cities

Mode 4: MCP FEDERATION (Future)
├── City runs their own MCP server
├── We aggregate multiple city MCP servers
├── Maximum decentralization
└── Use for: Statewide/national scale
```

### 9.3 Ingestion API for Adopted Cities

When a city officially adopts, they can push data directly:

```python
# POST /api/ingest/{jurisdiction_id}
# Headers: Authorization: Bearer <city_api_key>

{
    "events": [
        {
            "id": "mtg-2025-11-25-council",
            "title": "City Council Regular Meeting",
            "meeting_datetime": "2025-11-25T18:00:00-08:00",
            "meeting_type": "city_council",
            "location": "City Hall, 1400 Fifth Ave",
            "agenda_url": "https://city.gov/agenda.pdf",
            "agenda_items": [
                {
                    "item_number": "5.1",
                    "title": "Wildfire Prevention Fund Allocation",
                    "project_type": "environment",
                    "description": "..."
                }
            ]
        }
    ],
    "source": "city_clerk_system",
    "pushed_at": "2025-11-25T10:00:00Z"
}

# Response: 201 Created
{
    "status": "accepted",
    "events_processed": 1,
    "agenda_items_processed": 1,
    "enrichment_applied": true,
    "legislative_matches": ["SB-423", "AB-1001"]
}
```

**Key Design Points**:
- City pushes in `civic-app-schema.json` format
- We still apply intelligence layer (legislative enrichment, coordination scoring)
- Parsers become unnecessary for adopted cities

### 9.4 Architecture Layers Revisited

```
┌─────────────────────────────────────────────────────────────────┐
│                    CIVIC DATA PIPELINE                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ACQUISITION LAYER (City Integration Modes)                     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│  │ Mode 1:     │ │ Mode 2:     │ │ Mode 3:     │               │
│  │ Parse       │ │ API Access  │ │ Push        │               │
│  │ (bootstrap) │ │ (privilege) │ │ (adoption)  │               │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘               │
│         │               │               │                       │
│         └───────────────┼───────────────┘                       │
│                         ▼                                       │
│  ┌───────────────────────────────────────────────┐             │
│  │           StateManager / Database              │             │
│  │  (Normalized civic data: events, issues)       │             │
│  └─────────────────────┬─────────────────────────┘             │
│                        │                                        │
│  INTELLIGENCE LAYER (Our Moat - applies to ALL modes)          │
│  ┌───────────────────────────────────────────────┐             │
│  │  • Legislative enrichment (bills, programs)    │             │
│  │  • Coordination scoring (LangGraph)            │             │
│  │  • Complaint-to-agenda matching                │             │
│  │  • 99.99% reference validation                 │             │
│  └─────────────────────┬─────────────────────────┘             │
│                        │                                        │
│  DISTRIBUTION LAYER (MCP)                                       │
│  ┌───────────────────────────────────────────────┐             │
│  │  • MCP servers for AI access                   │             │
│  │  • REST API for frontend                       │             │
│  │  • Mode 4: Federate city MCP servers           │             │
│  └───────────────────────────────────────────────┘             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 9.5 Investment Prioritization

Given the foundation-funded city partnership model:

| Investment | Priority | Rationale |
|------------|----------|-----------|
| **Intelligence Layer** | Highest | Our moat - cities can't build this |
| **MCP Distribution** | High | Enables AI access, federation |
| **Ingestion API** | High | Supports official adoption |
| **StateManager** | High | Single source of truth |
| **Parser Abstraction** | Low | Bypassed by official adoption |
| **Community Parsers** | Low | Nice-to-have, not critical path |

### 9.6 Migration Path Per City

```
Typical City Journey:
━━━━━━━━━━━━━━━━━━━━

1. DISCOVERY
   └── We find city uses Legistar/CivicClerk/etc.

2. PARSE (Mode 1)
   └── Add to CITY_CONFIGS, extract data
   └── Demonstrate value in pilot

3. PARTNERSHIP CONVERSATION
   └── "We're already tracking your meetings..."
   └── "Would you like official integration?"

4. API ACCESS (Mode 2)
   └── City provides API key or allowlists us
   └── Better data quality, same code

5. OFFICIAL ADOPTION (Mode 3)
   └── City pushes data to our ingestion API
   └── Parser deprecated for this city

6. MCP FEDERATION (Mode 4, future)
   └── City runs civic-issues MCP server
   └── We aggregate across cities
```

---

## 10. MCP Apps: Interactive UI Extension (Research - Nov 2025)

### 10.1 Overview

**MCP Apps** (SEP-1865) is an official MCP extension announced November 2025 that enables MCP servers to deliver **interactive user interfaces** to host applications, not just data.

**Status**: Research phase - monitoring for adoption before implementation.

**Sources**:
- Official announcement: https://blog.modelcontextprotocol.io/posts/2025-11-21-mcp-apps/
- MCP-UI (predecessor): https://mcpui.dev/

### 10.2 How MCP Apps Works

```
MCP Server                     MCP Host (Claude Desktop, etc.)
    │                                     │
    │ ── ui:// template registration ───▶ │  (pre-declared)
    │                                     │
    │ ◀── tool call ───────────────────── │
    │                                     │
    │ ── tool result + UI reference ────▶ │
    │                                     │
    │                           ┌─────────┴─────────┐
    │                           │ Sandboxed iframe  │
    │                           │ renders HTML UI   │
    │                           └─────────┬─────────┘
    │                                     │
    │ ◀── JSON-RPC over postMessage ───── │ (user interactions)
```

**Key architectural decisions**:

| Decision | Rationale |
|----------|-----------|
| `ui://` URI scheme | Separate UI templates from tools; enables prefetching |
| HTML in sandboxed iframes | Universal browser support, established security model |
| JSON-RPC over postMessage | Structured, auditable communication |
| Pre-declared resources | Hosts can review/approve before rendering |
| Backward compatible | Text fallbacks for non-UI hosts |

### 10.3 Relevance to Civic Platform

**High relevance** - MCP Apps could enable AI-native civic interfaces:

| Our MCP Server | Potential UI |
|----------------|--------------|
| `civic-issues` | Interactive issue cards with Follow button, map view |
| `civic-events` | Meeting cards with RSVP, agenda preview, comment form |
| `civic-coordination` | Campaign dashboard, testimony queue, RSVP tracker |
| `civic-enrichment` | Bill summary cards with legislative context |

**Example transformation**:

```
# Current (data only)
User: "What issues are on 5th Ave?"
Server returns: JSON with 42 issues
Claude: "There are 42 issues. Top types are traffic (14), parking (9)..."

# With MCP Apps (data + UI)
User: "What issues are on 5th Ave?"
Server returns: JSON + ui://civic-issues/issue-grid
Claude Desktop renders: Interactive card grid with:
  - Issue cards (photo, status, address)
  - "Follow Issue" buttons
  - Filter controls
  - Map toggle
```

### 10.4 Strategic Assessment

**Benefits**:
- Reduces Vue frontend burden (MCP servers own their UI)
- AI-native interface (Claude Desktop becomes civic data browser)
- Multi-host distribution (same UI works everywhere)
- Foundation narrative ("civic infrastructure with AI-native interfaces")

**Concerns**:
- Very new (Nov 2025) - adoption unclear
- Adds complexity vs. traditional approach
- Host support TBD (Claude Desktop likely first)
- HTML iframes may feel less native than Vue

### 10.5 Recommendation

| Timeframe | Action |
|-----------|--------|
| **Now** | Build data-only MCP servers (`civic-issues`, etc.) |
| **Q1 2025** | Monitor MCP Apps adoption in Claude Desktop |
| **If adopted** | Add `ui://` templates to existing servers |
| **Post-pilot** | Evaluate if MCP Apps can replace Vue components |

**Key decision point**: When Claude Desktop ships MCP Apps support, evaluate adding UI templates to `civic-issues` server as pilot.

### 10.6 Implementation Notes (Future)

When ready to implement, MCP Apps requires:

```python
# Server-side: Register UI template
from mcp_ui_server import create_ui_resource

@server.resource("ui://civic-issues/issue-card")
def issue_card_template():
    return create_ui_resource(
        uri="ui://civic-issues/issue-card",
        content_type="text/html",
        content="""
        <div class="issue-card">
            <h3>{{title}}</h3>
            <p>{{address}}</p>
            <button onclick="mcp.call('follow_issue', {id: '{{id}}'})">
                Follow
            </button>
        </div>
        """
    )

# Tool references UI template in metadata
@server.tool("query_issues")
def query_issues(jurisdiction: str):
    issues = StateManager().query_issues(jurisdiction)
    return {
        "issues": issues,
        "_ui": "ui://civic-issues/issue-card"  # Reference to template
    }
```

**Python SDK**: `pip install mcp-ui-server` (PyPI)

---

## Related Documentation

- `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md` - Master architecture, LangGraph workflows
- `docs/critical/PILOT_ROADMAP.md` - Pilot timeline and readiness
- **External**: [MCP Documentation](https://modelcontextprotocol.io/)
- **External**: [Vercel AI SDK MCP](https://vercel.com/docs/mcp)
- **External**: [MCP-UI](https://mcpui.dev/)

---

## Appendix: MCP Resources

### A.1 Installation

```bash
# MCP Python SDK
pip install mcp

# LangChain MCP Adapters (for LangGraph)
pip install langchain-mcp-adapters

# MCP Inspector (for testing)
npx @anthropic-ai/mcp-inspector
```

### A.2 MCP Server Template

```python
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("my-server")

@server.tool("my_tool")
def my_tool(param1: str, param2: int = 10) -> dict:
    """Tool description for AI discovery."""
    return {"result": f"{param1} x {param2}"}

if __name__ == "__main__":
    import asyncio
    asyncio.run(server.run())
```

### A.3 Testing with MCP Inspector

```bash
# Start inspector
npx @anthropic-ai/mcp-inspector

# Connect to local server
# Enter: python apps/civic-mcp/civic_issues.py

# Test tools interactively
```
