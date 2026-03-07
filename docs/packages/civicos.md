# civicos

Core query and action API for CivicOS.

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

# Action (Act)
c.start_something(topic="traffic", title="Protected bike lane")
c.add_voice("agenda_item", "item_123", "support", "As a cyclist...")
c.follow("meeting", "mtg_456")
c.prepare("item_789")

# AI Orchestration
c.suggestions()                     # Proactive recommendations
c.report_outcome("item_789", "passed")
```

## MCP Server

Run the unified MCP server:

```bash
civicos-server
```

## Architecture

Four-layer design:
1. **Intelligence** — Multi-platform data extraction (civicos-extraction)
2. **Orchestration** — Rule-based suggestions and outcome tracking
3. **Coordination** — Voice, subscriptions, federation (civicos-relay)
4. **Impact** — Outcome tracking and learning

See [Package Architecture](../critical/FINAL_PACKAGE_ARCHITECTURE.md) for details.

## License

PolyForm Noncommercial 1.0.0
