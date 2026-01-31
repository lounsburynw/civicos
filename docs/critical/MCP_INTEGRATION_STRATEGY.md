# MCP Integration Strategy

**Created**: 2025-11-24 (Session 118)
**Updated**: 2026-01-29 (Session 559 - Relay + MCP federation architecture)
**Status**: MCP Server Complete (32 primitives), HTTP Transport Ready, Deployment in Progress
**Priority**: Strategic - Multi-platform AI distribution for pilot demo

---

## Executive Summary

**Decision**: Deploy single MCP server with HTTP transport to serve both Claude.ai AND ChatGPT.

**Key Discovery (Jan 2026)**: ChatGPT now has native MCP client support (developer mode beta). This supersedes the Custom GPT + Actions approach - a single MCP server now serves all platforms.

**Why This Matters**:
- Single codebase serves Claude Desktop, Claude.ai, AND ChatGPT
- No need for separate OpenAPI spec maintenance for ChatGPT Actions
- Better security (no exposed system prompts like Custom GPTs)
- Future-proof as MCP becomes industry standard

**Strategy**: Deploy MCP server publicly with HTTPS, connect to ChatGPT and Claude.ai as connectors.

**Current State**:
- MCP server complete: 25 tools + 5 resources + 2 prompts (`apps/civicos-mcp/civicos_server.py`)
- 311 analysis suite (10 tools): analytics, trends, geo-search, accountability, neighborhood reports
- HTTP transport added (Session 535) - ready for public deployment
- REST API complete: FastAPI endpoints (`packages/civicos-services/`)
- Vue frontend available: `apps/civicos-workspace/`

**Next Steps** (P0):
1. Deploy MCP server with HTTPS (Railway, Fly.io, or ngrok for testing)
2. Connect to ChatGPT via developer mode connector
3. Connect to Claude.ai via Connectors settings (OAuth optional for start)
4. Register on MCP Registry after validation

---

## HTTP Transport Deployment Guide (NEW - Session 536)

This section covers deploying the MCP server with HTTP transport for public access.

### Quick Start - Local Testing

```bash
# Start MCP server with HTTP transport
civicos-env/bin/python apps/civicos-mcp/civicos_server.py -t http -p 8080

# In another terminal, expose via ngrok for HTTPS
ngrok http 8080
# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
```

### Server Usage

```bash
# Local development (stdio - Claude Desktop default)
civicos-env/bin/python apps/civicos-mcp/civicos_server.py

# HTTP transport for ChatGPT/Claude.ai
civicos-env/bin/python apps/civicos-mcp/civicos_server.py -t http -p 8080

# With custom host (for production deployment)
civicos-env/bin/python apps/civicos-mcp/civicos_server.py -t http --host 0.0.0.0 -p 8080
```

### Testing HTTP Endpoint

```bash
# Test MCP initialization
curl -s http://localhost:8080/mcp \
  -X POST \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}, "id": 1}'

# Expected response includes serverInfo: "CivicOS Engagement Server"
```

### Deployment Options

| Option | Use Case | Cost | Setup Complexity | Notes |
|--------|----------|------|------------------|-------|
| **Modal** | Production (current) | ~$2-5/month | Low | All compute on one platform |
| **Fly.io** | Legacy/alternative | ~$2/month | Medium | Previously at `civicos-mcp.fly.dev` |
| **ngrok** | Development/Demo | Free tier available | Lowest | Temporary URLs |
| **Railway** | Alternative | ~$5/month | Low | Good alternative |
| **Render** | Alternative | Free tier + $7/month | Low | |

**Current State (Jan 2026):** MCP server is deployed on **Modal** at `https://civicos--civicos-mcp-mcp-endpoint.modal.run`. This consolidates all serverless compute (MCP server, relay worker, vector indexer) on one platform.

Benefits of Modal consolidation:
- Single platform for all compute
- Serverless scaling (0 to N instances)
- `keep_warm=1` prevents cold starts
- GPU access for embeddings
- Cron triggers for relay worker

### Environment Variables (Required for Deployment)

```bash
DATABASE_URL=postgresql://...        # Supabase connection string
CIVICOS_JURISDICTION=city-san-rafael  # Default jurisdiction
```

### Connecting to ChatGPT

ChatGPT has native MCP support in developer mode (beta, Jan 2025):

1. Enable developer mode: **Settings > Connectors > Advanced > Developer mode**
2. Create connector: **Settings > Connectors > Create**
3. Enter your HTTPS URL (e.g., `https://your-app.railway.app/mcp`)
4. Test: "What's on the San Rafael city council agenda?"

**References**:
- [ChatGPT MCP Connectors](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta)
- [OpenAI Apps SDK - MCP](https://developers.openai.com/apps-sdk/concepts/mcp-server/)

### Connecting to Claude.ai

Claude.ai supports remote MCP servers for Pro/Max/Team/Enterprise:

1. Deploy MCP server publicly with HTTPS
2. (Optional) Implement OAuth 2.0 for authentication
   - Callback URL: `https://claude.ai/api/mcp/auth_callback`
3. Add connector: **Settings > Connectors > Add connector**
4. Enter server URL

**References**:
- [Building Custom Connectors](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)

### Modal Deployment (Production)

The MCP server is deployed on Modal, consolidating all serverless compute on one platform.

**Deployed at:** `https://civicos--civicos-mcp-mcp-endpoint.modal.run`

**Key Features:**
- **Serverless scaling**: 0 to N instances based on traffic
- **`min_containers=1`**: Prevents cold starts by maintaining one warm instance
- **Singleton initialization**: CivicOS and embedding model initialized once per container
- **Consolidated compute**: MCP server, relay worker, and vector indexer all on Modal

```bash
# Install Modal CLI
pip install modal

# Authenticate
modal token new

# Create secrets
modal secret create civicos-env \
    DATABASE_URL="postgresql://..." \
    RELAY_DATABASE_URL="postgresql://..." \
    CIVICOS_JURISDICTION="city-san-rafael"

# Deploy MCP server
modal deploy apps/civicos-mcp/modal_app.py

# Test locally first
modal serve apps/civicos-mcp/modal_app.py

# Endpoints after deployment:
# MCP:    https://civicos--civicos-mcp-mcp-endpoint.modal.run
# Health: https://civicos--civicos-mcp-health.modal.run
```

**Architecture:**
```
Claude.ai/ChatGPT
        │
        ▼
┌─────────────────────────────┐
│  Modal (civicos-mcp app)    │
│  ┌───────────────────────┐  │
│  │   MCPServer class     │  │
│  │   @modal.enter()      │  │  ← CivicOS + embeddings initialized once
│  │   - CivicOS singleton │  │
│  │   - 25+ tools         │  │
│  │   - Input validation  │  │
│  │   - Federation support│  │
│  └───────────────────────┘  │
│  min_containers=1 (warm)    │
└─────────────────────────────┘
        │
        ▼
    Supabase (PostgreSQL + pgvector)
```

### Fly.io Deployment (Legacy)

Previously deployed on Fly.io at `civicos-mcp.fly.dev`. Configuration files remain for reference:

- `fly-mcp.toml` - Fly.io app configuration
- `Dockerfile.mcp` - Container definition
- `scripts/deploy-mcp.sh` - Deployment script

### Railway Deployment (Alternative)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and initialize
railway login
railway init

# Set environment variables
railway variables set DATABASE_URL="postgresql://..."
railway variables set CIVICOS_JURISDICTION="city-san-rafael"

# Deploy (needs Dockerfile or Procfile)
railway up
```

**Procfile** for Railway:
```
web: python apps/civicos-mcp/civicos_server.py -t http --host 0.0.0.0 -p $PORT
```

---

## Multi-Platform Distribution Strategy (2026)

### Platform Landscape (Updated Jan 2026)

| Platform | Method | Reach | Status |
|----------|--------|-------|--------|
| **Claude.ai web** | Remote MCP via Connectors | Pro/Max/Team/Enterprise users | Ready to deploy |
| **Claude Desktop** | Local MCP server (stdio) | All users | Working |
| **Claude Mobile** | Remote MCP (same as web) | Pro+ users (iOS/Android) | Ready to deploy |
| **ChatGPT** | MCP via developer mode | ChatGPT Plus/Team | Ready to deploy |
| **ChatGPT (fallback)** | Custom GPT + Actions | All ChatGPT users | SUPERSEDED by MCP |
| **Web app** | Direct access | Everyone | Working |

### Claude.ai Remote MCP (NEW - May 2025)

Claude.ai web now supports **remote MCP servers** via "Integrations" feature:
- Available on Pro, Max, Team, Enterprise plans
- Also works on Claude Mobile (iOS/Android)
- Supports OAuth authentication
- User connects via Settings > Connectors

**Deployment requirements**:
```
Remote MCP Server Checklist:
├── Host MCP server publicly (Railway, Fly.io, Render, etc.)
├── Implement OAuth 2.0 authentication
│   └── Callback URL: https://claude.ai/api/mcp/auth_callback
├── Support SSE or Streamable HTTP transport
├── Expose tools, resources, prompts via MCP protocol
└── Add to Claude.ai via connector URL
```

**References**:
- [Claude Integrations announcement](https://www.anthropic.com/news/integrations)
- [Building Custom Connectors](https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers)
- [Remote MCP Server docs](https://modelcontextprotocol.io/docs/develop/connect-remote-servers)

### MCP Discovery Channels

| Channel | URL | Notes |
|---------|-----|-------|
| **Official MCP Registry** | [registry.modelcontextprotocol.io](https://registry.modelcontextprotocol.io/) | Canonical, launching toward GA |
| **MCP.so** | [mcp.so](https://mcp.so/) | 17k+ servers, community-driven |
| **MCPServers.org** | [mcpservers.org](https://mcpservers.org/) | Curated collection |
| **MCP Market** | [mcpmarket.com](https://mcpmarket.com/) | Discovery + docs |
| **Desktop Extensions** | `.mcpb` bundles | One-click install for Claude Desktop |

**Strategy**: Register on all directories for maximum discoverability.

### ChatGPT Distribution (Updated Jan 2026)

**IMPORTANT**: ChatGPT now supports MCP natively via developer mode (beta, Jan 2025). This supersedes the Custom GPT + Actions approach.

**Preferred Approach**: MCP Server with HTTP Transport
```
ChatGPT MCP Integration:
├── Deploy MCP server with HTTPS
├── Enable developer mode in ChatGPT settings
├── Create connector pointing to MCP server URL
└── All 25 MCP tools available automatically
```

**Benefits over Custom GPT**:
- Single codebase for Claude AND ChatGPT
- No OpenAPI spec maintenance
- No exposed system prompts (security)
- Real-time tool updates without GPT reconfiguration

**Fallback Approach** (if MCP unavailable): Custom GPT + Actions
```
ChatGPT Custom GPT "Civic San Rafael":
├── System prompt: Civic engagement assistant for San Rafael
├── Actions: OpenAPI spec wrapping civicos-services REST API
│   ├── GET /api/meetings - whats_next()
│   ├── GET /api/decisions - what_happened()
│   ├── GET /api/issues - whos_with_me()
│   ├── POST /api/search - multi-corpus search
│   └── GET /api/budget - budget queries
├── Knowledge: San Rafael context document
└── Conversation starters: "What's on the city council agenda?"
```

**References**:
- [ChatGPT MCP Developer Mode](https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta)
- [OpenAI Apps SDK - MCP](https://developers.openai.com/apps-sdk/concepts/mcp-server/)
- [GPT Actions docs](https://platform.openai.com/docs/actions/introduction) (fallback)

### ChatGPT Custom GPT Configuration Guide

Step-by-step guide for creating the "Civic San Rafael" Custom GPT.

#### 1. Create the GPT

1. Go to [chat.openai.com/gpts/editor](https://chat.openai.com/gpts/editor) (requires ChatGPT Plus)
2. Click "Create a GPT"
3. Use the "Configure" tab for detailed settings

#### 2. Configure Basic Info

**Name**: `Civic San Rafael`

**Description**:
```
Your local government assistant for San Rafael, CA. Track city council decisions,
find upcoming meetings, discover community issues, and prepare to participate in
local democracy.
```

**Profile Picture**: Use Civic logo or San Rafael city seal

#### 3. System Prompt (Instructions)

```
You are Civic, a friendly assistant helping San Rafael residents engage with their
local government. You have access to city council meetings, decisions, community
issues, and budget information.

CAPABILITIES:
- Search past city council decisions and what was said at meetings
- Find upcoming meetings and agenda items
- Discover community concerns similar to the user's
- Explain budget allocations and expenditures
- Help users prepare public comments

GUIDELINES:
- Be conversational and accessible - avoid jargon
- When citing decisions or meetings, include dates
- Encourage civic participation but remain neutral on political positions
- If you don't have information, say so and suggest where to look
- Offer to help users take action (submit comments, attend meetings)

JURISDICTION: San Rafael, California
DATA FRESHNESS: Updated daily from official city sources
```

#### 4. Conversation Starters

Add these 4 conversation starters (matches get_started() categories):

| Starter | Purpose |
|---------|---------|
| "What's on the agenda for the next council meeting?" | Discovery - upcoming meetings |
| "What has the council decided about housing?" | Research - past decisions |
| "What are residents saying about traffic downtown?" | Community - similar issues |
| "Help me prepare to speak at Monday's meeting" | Action - public participation |

#### 5. Configure Actions (API Integration)

**Schema Type**: OpenAPI 3.0

**Server URL**: `https://civic-api.example.com` (replace with deployed civicos-services URL)

**OpenAPI Spec** (minimal example):
```yaml
openapi: 3.0.0
info:
  title: Civic San Rafael API
  version: 1.0.0
servers:
  - url: https://civic-api.example.com
paths:
  /api/meetings:
    get:
      operationId: getUpcomingMeetings
      summary: Get upcoming city council meetings
      parameters:
        - name: days
          in: query
          schema:
            type: integer
            default: 30
      responses:
        '200':
          description: List of upcoming meetings
  /api/decisions:
    get:
      operationId: searchDecisions
      summary: Search past council decisions
      parameters:
        - name: query
          in: query
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Matching decisions
  /api/issues:
    get:
      operationId: findSimilarIssues
      summary: Find community issues similar to a topic
      parameters:
        - name: topic
          in: query
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Similar community issues
```

**Authentication**: Configure API key or OAuth as appropriate

#### 6. Knowledge Files (Optional)

Upload supporting documents:
- San Rafael municipal code summary
- City council member roster
- Common civic processes guide

#### 7. Publishing

1. Test thoroughly with sample questions
2. Set visibility: "Anyone with a link" or "Public" (GPT Store)
3. Copy shareable link for distribution

#### 8. Verification Checklist

| Check | Expected Result |
|-------|-----------------|
| "What's on the agenda?" | Returns upcoming meeting info |
| "Council decisions about housing" | Returns relevant decisions |
| "Traffic complaints downtown" | Returns similar SeeClickFix issues |
| "How do I submit a comment?" | Explains public comment process |

### Distribution Architecture (Updated Jan 2026)

**Unified MCP Approach**: Single server serves all AI platforms

```
                    ┌─────────────────────────────────┐
                    │     civicos-mcp (MCP Server)    │
                    │   HTTP transport on HTTPS       │
                    │   (civicos_server.py -t http)   │
                    └───────────────┬─────────────────┘
                                    │
        ┌───────────────┬───────────┼───────────┬───────────────┐
        │               │           │           │               │
        ▼               ▼           ▼           ▼               ▼
┌───────────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐
│  Claude.ai    │ │ Claude    │ │ Claude    │ │ ChatGPT   │ │ Future:   │
│  (Web)        │ │ Desktop   │ │ Mobile    │ │ (MCP dev  │ │ Gemini,   │
│  Pro+ plans   │ │ (stdio)   │ │ (iOS/And) │ │  mode)    │ │ Copilot   │
└───────────────┘ └───────────┘ └───────────┘ └───────────┘ └───────────┘

                    ┌─────────────────────────────────┐
                    │   civicos-services REST API     │
                    │   (FastAPI for web frontend)    │
                    └───────────────┬─────────────────┘
                                    │
                                    ▼
                          ┌───────────────┐
                          │civicos-workspace│
                          │ (Vue web app)  │
                          │ Main product   │
                          └───────────────┘
```

**Note**: ChatGPT now uses MCP directly - no separate Custom GPT needed.
The REST API is primarily for the Vue frontend.

```
BEFORE (Jan 2026):           AFTER (Jan 2026):
├── MCP → Claude             ├── MCP → Claude + ChatGPT + Future
├── REST/OpenAPI → ChatGPT   │     (single server)
└── REST → Vue frontend      └── REST → Vue frontend only
```

### Linkback Strategy

AI assistants should drive users to the main web app for depth:

```python
# MCP tool responses include deep links
def search_meeting_history(query: str) -> str:
    results = civic.what_happened(query)
    return f"""
Found {len(results)} decisions about "{query}".

Top result: {results[0]['title']}
- Date: {results[0]['date']}
- Outcome: {results[0]['outcome']}

View full details and related documents:
→ https://civic.example.com/decisions/{results[0]['id']}

Browse all results:
→ https://civic.example.com/search?q={query}
"""
```

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
├── apps/civicos-mcp/
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
                          │   (civicos-workspace) │
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
│  │ apps/civicos-mcp/     │   │ apps/civicos-mcp/     │   │ apps/civicos-mcp/     │   │
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

**File**: `apps/civicos-mcp/civic_issues.py`

**Tools**:
| Tool | Description | Parameters |
|------|-------------|------------|
| `query_issues` | Query civic issues | jurisdiction, street?, issue_type?, limit? |
| `get_issue_stats` | Get issue statistics | jurisdiction |
| `query_corridor` | Query by corridor name | jurisdiction, corridor |

**Effort**: 1-2 hours

### 4.2 Phase 2: Events/Agendas MCP Server (Future)

**Goal**: Expose event and agenda data via MCP

**File**: `apps/civicos-mcp/civic_events.py`

**Tools**:
| Tool | Description | Parameters |
|------|-------------|------------|
| `get_events` | Get upcoming events | jurisdiction, days_future? |
| `get_agenda` | Get agenda items for event | event_id |
| `search_events` | Search events by topic | jurisdiction, topic, date_from?, date_to? |

### 4.3 Phase 3: Legislative Context MCP Server (Future)

**Goal**: Expose legislative data via MCP

**File**: `apps/civicos-mcp/legislative.py`

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
# apps/civicos-mcp/civic_issues.py
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
python apps/civicos-mcp/civic_issues.py
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
      "args": ["/path/to/civic/apps/civicos-mcp/civic_issues.py"]
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

### 9.2.1 Relay + MCP Integration

The `civicos-relay` package provides coordination infrastructure (voices, subscriptions) that integrates with MCP:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FEDERATION TOPOLOGY                             │
│                                                                             │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐       │
│  │  San Rafael     │     │  Novato         │     │  Marin County   │       │
│  │  ┌───────────┐  │     │  ┌───────────┐  │     │  ┌───────────┐  │       │
│  │  │   Relay   │◄─┼─────┼─►│   Relay   │◄─┼─────┼─►│   Relay   │  │       │
│  │  └─────┬─────┘  │     │  └─────┬─────┘  │     │  └─────┬─────┘  │       │
│  │        │        │     │        │        │     │        │        │       │
│  │  ┌─────┴─────┐  │     │  ┌─────┴─────┐  │     │  ┌─────┴─────┐  │       │
│  │  │MCP Server │  │     │  │MCP Server │  │     │  │MCP Server │  │       │
│  │  └───────────┘  │     │  └───────────┘  │     │  └───────────┘  │       │
│  └─────────────────┘     └─────────────────┘     └─────────────────┘       │
│           │                       │                       │                 │
│           └───────────────────────┼───────────────────────┘                 │
│                                   ▼                                         │
│                        ┌─────────────────────┐                              │
│                        │   User's AI Agent   │                              │
│                        │  (Claude, ChatGPT)  │                              │
│                        └─────────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Two federation layers:**

| Layer | What Federates | Protocol |
|-------|----------------|----------|
| **Relay** | Voices, events | `civicos-relay` sync protocol |
| **MCP** | Queries | Fan-out to peer MCP servers |

**Relay provides MCP with:**
- Voice counts per entity (`get_voice_counts`)
- Subscription management (`subscribe_to_topic`)
- Provenance data (`get_key_provenance`)

**MCP federation options:**

1. **Single MCP, federated relay**: One MCP server connects to a relay that syncs with peers
2. **Federated MCP**: Multiple MCP servers, each with local relay, query fan-out at MCP layer
3. **Agent-side federation**: Agent connects to multiple MCP servers directly

For pilot: Option 1 (single MCP). Post-pilot: Option 2 for turnkey city deployments.

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
- `docs/critical/CIVIC_DASHBOARD_VISION.md` - Post-pilot UX vision (visualization primitives, multi-surface rendering)
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
# Enter: python apps/civicos-mcp/civic_issues.py

# Test tools interactively
```
