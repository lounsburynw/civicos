# Civic Platform Verification Tutorial

**Purpose**: Hands-on verification of the Civic platform before pilot launch.
**Audience**: Developers, auditors, and stakeholders testing the system.
**Last Updated**: 2025-11-30

---

## Overview

This tutorial walks you through hands-on verification of the Civic platform. You'll test each layer:

1. **Python API** - Direct library usage
2. **REST API** - HTTP endpoints
3. **MCP Server** - AI tool integration
4. **Frontend** - User interface

---

## Prerequisites

```bash
source civic-env/bin/activate
./init.sh  # Verify environment (158 tests should pass)
```

---

## Part 1: Python API (Core Library)

Open a Python REPL or create a test script:

```bash
python3
```

### 1.1 Query Methods

```python
from civic import Civic

c = Civic("san-rafael")

# What's coming up?
meetings = c.whats_next(days=30)
print(f"Upcoming meetings: {len(meetings)}")

# What rules apply to housing?
context = c.what_applies("housing")
print(f"Regulatory context: {context}")

# What happened with traffic?
history = c.what_happened("traffic")
print(f"Historical decisions: {len(history)}")

# Who cares about bike lanes?
community = c.whos_with_me("bike lanes")
print(f"Community: {community}")
```

### 1.2 Action Methods

```python
# Start an initiative
initiative = c.start_something(
    topic="traffic safety",
    title="Protected bike lane on 4th Street",
    description="Near-misses every week at 4th & B intersection"
)
print(f"Created: {initiative.id}")

# Add your voice
voice = c.add_voice(
    item_type="initiative",
    item_id=initiative.id,
    stance="support",
    comment="I bike this route daily and it's dangerous"
)
print(f"Voice added: {voice.id}")

# Follow the initiative
sub = c.follow(
    item_type="initiative",
    item_id=initiative.id
)
print(f"Following: {sub.id}")
```

### 1.3 Orchestration Methods

```python
# Get AI-powered suggestions
suggestions = c.suggestions()
print(f"Suggestions: {suggestions}")

# Report an outcome (closes feedback loop)
outcome = c.report_outcome(
    item_id=initiative.id,
    outcome="passed",
    notes="Council approved 4-1"
)
print(f"Outcome recorded: {outcome.id}")
```

---

## Part 2: REST API

### 2.1 Start the Server

```bash
# Terminal 1
python src/civic_api_integrated.py
# Should start on http://localhost:8001
```

### 2.2 Test Endpoints

```bash
# Terminal 2 - Query endpoints
curl http://localhost:8001/api/whats-next/san-rafael
curl http://localhost:8001/api/what-applies/san-rafael/housing
curl http://localhost:8001/api/what-happened/san-rafael/traffic

# Action endpoints
curl -X POST http://localhost:8001/api/start-something \
  -H "Content-Type: application/json" \
  -d '{"jurisdiction": "san-rafael", "topic": "parking", "title": "Resident parking permits", "description": "Downtown parking is impossible"}'

curl -X POST http://localhost:8001/api/add-voice \
  -H "Content-Type: application/json" \
  -d '{"item_type": "initiative", "item_id": "init_test123", "stance": "support", "comment": "I agree!"}'
```

---

## Part 3: MCP Server (AI Integration)

### 3.1 Test MCP Tools Programmatically

```python
from civic.mcp import CivicServer

server = CivicServer()

# List available tools
tools = server.list_tools()
print(f"MCP Tools: {[t.name for t in tools]}")

# Call a tool
result = server.call_tool("whats_next", {"jurisdiction": "san-rafael", "days": 30})
print(f"Result: {result}")
```

### 3.2 Expected Tools

- **Query**: `what_applies`, `what_happened`, `whats_next`, `whos_with_me`
- **Action**: `start_something`, `add_voice`, `follow`, `prepare`
- **Orchestration**: `get_suggestions`, `coordinate`, `report_outcome`

---

## Part 4: Frontend

### 4.1 Start Services

```bash
# Terminal 1 - API Server
python src/civic_api_integrated.py

# Terminal 2 - WebSocket Server
python src/civic_socketio_server.py

# Terminal 3 - Frontend
cd apps/civic-workspace && npm run dev
```

### 4.2 Manual Testing Checklist

Open http://localhost:5173 (or the Vite dev server URL)

- [ ] Browse upcoming events
- [ ] View legislative context panel
- [ ] Create/view issues
- [ ] Draft a comment
- [ ] Test coordination chat

---

## Part 5: Database Verification

Check that data persists:

```bash
sqlite3 data/civic_state.db

# Check tables exist
.tables

# Check initiatives
SELECT * FROM initiatives LIMIT 5;

# Check voices
SELECT * FROM voices LIMIT 5;

# Check subscriptions
SELECT * FROM subscriptions LIMIT 5;

# Check outcomes
SELECT * FROM outcomes LIMIT 5;

.quit
```

---

## Verification Checklist

| Component | Test | Pass? |
|-----------|------|-------|
| **Python API** | `Civic("san-rafael")` instantiates | |
| **Query** | `whats_next()` returns list | |
| **Query** | `what_applies("housing")` returns context | |
| **Action** | `start_something()` creates initiative | |
| **Action** | `add_voice()` records stance | |
| **Action** | `follow()` creates subscription | |
| **Orchestration** | `suggestions()` returns recommendations | |
| **Orchestration** | `report_outcome()` records outcome | |
| **REST API** | Server starts on 8001 | |
| **REST API** | GET endpoints return data | |
| **REST API** | POST endpoints create records | |
| **MCP Server** | Tools list correctly | |
| **MCP Server** | Tool calls execute | |
| **Database** | Tables exist | |
| **Database** | Records persist | |
| **Frontend** | Dev server starts | |
| **Frontend** | UI renders | |

---

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| "No meetings found" | No events extracted recently | Expected - run extraction or use test data |
| Database locked | Multiple connections | Close other sqlite3 sessions |
| Import errors | Virtual env not active | Run `source civic-env/bin/activate` |
| Port in use | Existing process | Kill processes on 8001/8002/5173 |
| MCP import fails | Optional dependency | Install with `pip install mcp` |

---

## Next Steps

After completing verification:

1. Document any failures in the checklist
2. File issues for bugs discovered
3. Schedule expert code audit
4. Plan pilot deployment for San Rafael (Jan 2026)

---

## Related Documentation

- [FINAL_PACKAGE_ARCHITECTURE.md](critical/FINAL_PACKAGE_ARCHITECTURE.md) - System architecture
- [MCP_INTEGRATION_STRATEGY.md](critical/MCP_INTEGRATION_STRATEGY.md) - MCP server design
- [PILOT_ROADMAP.md](critical/PILOT_ROADMAP.md) - Pilot deployment plan
