# CivicOS

Unified civic engagement platform for local self-organization.

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

c = CivicOS("san-rafael-ca")

# Query (Learn)
c.what_applies("housing")           # Get regulatory context
c.what_happened("bike lanes")       # Search past decisions
c.whats_next(["transportation"])    # Get upcoming meetings
c.whos_with_me("traffic safety")    # Find community

# Action (Act)
c.start_something(topic="traffic", title="Protected bike lane")
c.add_voice("agenda_item", "item_123", "support", "As a cyclist...")
c.follow("meeting", "mtg_456")
c.prepare("item_789")

# AI Orchestration
c.suggestions()                     # Get proactive recommendations
c.coordinate("init_123", "plan_testimony")
c.report_outcome("item_789", "passed")
```

## MCP Server

Run the unified MCP server:

```bash
civicos-server
```

## Architecture

Four-layer design:
1. **Intelligence** - Multi-platform data extraction
2. **Orchestration** - Rule-based suggestions and outcome tracking
3. **Coordination** - Custom coordination tools
4. **Impact** - Outcome tracking and learning

See `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md` for details.

## License

MIT
