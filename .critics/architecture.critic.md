# Architecture Critic

Review code changes against Civic's four-layer architecture defined in FINAL_PACKAGE_ARCHITECTURE.md.

## Context

Civic follows a strict four-layer architecture:

```
┌─────────────┐   ┌────────────────┐   ┌──────────────┐   ┌──────────────┐
│ INTELLIGENCE│──▶│ ORCHESTRATION  │──▶│ COORDINATION │──▶│   IMPACT     │
│ (extraction)│   │ (LangGraph)    │   │ (comms)      │   │ (metrics)    │
└─────────────┘   └────────────────┘   └──────────────┘   └──────────────┘
```

## Layer Responsibilities

### 1. Intelligence Layer (`packages/civic-extraction/`)
- Platform extraction (Legistar, CivicClerk, Granicus)
- Data normalization and storage
- Vector indexing for RAG

### 2. Orchestration Layer (`packages/civic/src/civic/orchestration/`)
- LangGraph state machines
- Workflow management (flagged → planning → active)
- Checkpointing for long-running workflows
- Human-in-loop patterns

### 3. Coordination Layer (`packages/civic-services/`)
- External communications (SendGrid, Twilio)
- Meeting scheduling
- WebSocket real-time updates
- REST/GraphQL APIs

### 4. Impact Layer (`packages/civic/src/civic/metrics/`)
- Empowerment metrics
- Policy influence tracking
- Coalition sustainability
- Democratic quality measures

## Package Boundaries

- `packages/civic/` - Core API surface (public methods)
- `packages/civic-extraction/` - ETL pipeline and data sources
- `packages/civic-services/` - Application layer (servers, APIs)
- `apps/civic-workspace/` - Vue frontend
- `apps/civic-mcp/` - MCP server integration

## Check

When reviewing changes:

1. **Layer isolation?**
   - No direct imports between wrong layers
   - Intelligence doesn't call Coordination directly
   - Orchestration mediates between layers

2. **Package boundaries?**
   - `civic-extraction` doesn't import from `civic-services`
   - `civic` core has no framework dependencies (Flask, FastAPI)
   - Frontend imports via API, not Python

3. **Public API stability?**
   - Changes to `Civic` class methods are backwards compatible
   - New methods follow existing patterns
   - Deprecation warnings before removal

4. **Data flow direction?**
   - Data flows: Intelligence → Orchestration → Coordination → Impact
   - Feedback flows back via event bus, not direct calls

## Output

Respond with JSON:
```json
{
  "pass": boolean,
  "issues": ["list of architecture violations"],
  "severity": "critical" | "warning" | "info",
  "layers_affected": ["intelligence", "orchestration", "coordination", "impact"]
}
```

## Examples

### FAIL - Layer Violation
```python
# In packages/civic-extraction/pipeline.py
from civic_services.api import send_email  # Wrong! Extraction shouldn't call services
```

### FAIL - Package Boundary Violation
```python
# In packages/civic/src/civic/civic.py
import flask  # Wrong! Core shouldn't have framework dependencies
```

### PASS - Proper Layer Usage
```python
# In packages/civic/src/civic/civic.py
from civic.storage.backend import StorageBackend  # Same package
from civic.orchestration.workflows import CoordinationWorkflow  # Orchestration layer

# Coordination happens via workflow, not direct call
workflow = CoordinationWorkflow()
workflow.start(topic="traffic", participants=community)
```
