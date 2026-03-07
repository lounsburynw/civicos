# Packages

CivicOS is organized as a monorepo with focused packages:

```
civicos/
├── packages/civicos/             # Core query API
├── packages/civicos-relay/       # Federation relay (voice, actions, sync)
├── packages/civicos-extraction/  # Data parsers (Legistar, SeeClickFix, etc.)
├── packages/civicos-services/    # REST API, WebSocket server
├── apps/civicos-mcp/             # MCP server (primary distribution)
└── apps/civicos-openwebui-fork/  # Open WebUI frontend
```

| Package | Purpose | Install |
|---------|---------|---------|
| [civicos](civicos.md) | Core API — `what_happened()`, `whats_next()`, `whos_with_me()` | `pip install civicos` |
| [civicos-relay](civicos-relay.md) | Federation relay — voice, actions, subscriptions, sync | `pip install civicos-relay` |
| [civicos-extraction](civicos-extraction.md) | Platform parsers — Legistar, SeeClickFix, Municode, etc. | `pip install civicos-extraction` |
| [civicos-mcp](civicos-mcp.md) | MCP server — 32 primitives for AI agents | Deployed on Modal |

## Architecture Layers

```
AI Agent (Claude, ChatGPT, etc.)
    |
    v
MCP Server (civicos-mcp)         <-- 32 tools, resources, prompts
    |
    v
Core API (civicos)                <-- CivicOS("city-san-rafael")
    |
    +---> Storage Backend         <-- PostgreSQL (prod) / SQLite (dev)
    +---> Vector Backend          <-- pgvector (prod) / ChromaDB (dev)
    |
    v
Relay (civicos-relay)             <-- Federation, voice, coordination
    |
    v
Extraction (civicos-extraction)   <-- Platform parsers, ETL
```
