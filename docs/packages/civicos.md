# civicos

Core query API for CivicOS.

## Installation

```bash
pip install civicos
```

With MCP server support:
```bash
pip install civicos[mcp]
```

## Quick Start

```python
from civicos import CivicOS

c = CivicOS("city-san-rafael")

# Query (Learn)
c.what_applies("housing")           # Regulatory stack (local + state + federal)
c.what_happened("bike lanes")       # Search past decisions
c.whats_next(["transportation"])    # Get upcoming meetings
c.whos_with_me("traffic safety")    # Find community via 311 issues
c.what_was_said("homelessness")     # Search meeting transcripts

# Coordination (Act) — see civicos-relay package
```

## MCP Server

Run the unified MCP server:

```bash
civicos-server
```

## Architecture

Four-layer design:
1. **Intelligence** — Multi-platform data extraction (civicos-extraction)
2. **Query** — Civic data access (civicos)
3. **Coordination** — Voice, subscriptions, federation (civicos-relay)
4. **Impact** — Outcome tracking and learning

See [Package Architecture](../critical/FINAL_PACKAGE_ARCHITECTURE.md) for details.

## License

PolyForm Noncommercial 1.0.0
