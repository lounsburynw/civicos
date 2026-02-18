# Architecture Critic

Review code changes against Civic's four-layer architecture defined in FINAL_PACKAGE_ARCHITECTURE.md.

## Context

Civic follows a strict four-layer architecture:

```
┌─────────────┐   ┌────────────────┐   ┌──────────────┐   ┌──────────────┐
│ INTELLIGENCE│──▶│ ORCHESTRATION  │──▶│ COORDINATION │──▶│   IMPACT     │
│ (extraction)│   │ (suggestions)  │   │ (relay)      │   │ (metrics)    │
└─────────────┘   └────────────────┘   └──────────────┘   └──────────────┘
```

## Layer Responsibilities

### 1. Intelligence Layer (`packages/civicos-extraction/`)
- Platform extraction (Legistar, CivicClerk, Granicus)
- Data normalization and storage
- Vector indexing for RAG

### 2. Orchestration Layer (`packages/civicos/src/civicos/orchestrator/`)
- Rule-based suggestion generation (`suggestions.py`)
- Outcome tracking and feedback loop closure (`outcomes.py`)
- Standalone modules querying data layer (no framework dependency)

### 3. Coordination Layer (`packages/civicos-relay/`, `packages/civicos-services/`)
- Voice casting, action primitives (`civicos-relay`)
- Subscriptions and event delivery (`civicos-relay`)
- Federation sync between relays (`civicos-relay`)
- WebSocket real-time updates, REST API (`civicos-services`)

### 4. Impact Layer (`packages/civicos/src/civicos/metrics/`)
- Empowerment metrics
- Policy influence tracking
- Coalition sustainability
- Democratic quality measures

## Package Boundaries

- `packages/civicos/` - Core API surface (public methods)
- `packages/civicos-extraction/` - ETL pipeline and data sources
- `packages/civicos-services/` - Application layer (servers, APIs)
- `apps/civicos-workspace/` - Vue frontend
- `apps/civicos-mcp/` - MCP server integration
- `scripts/` - ETL/integration scripts (can import from any package)

## Scripts Directory (`scripts/`)

Scripts are integration code for ETL, migration, and batch operations. They have different rules:

**ALLOWED:**
- Import from any package (`civic`, `civicos-extraction`, `civicos-services`)
- Direct database operations for one-off migrations
- Combining multiple pipeline stages in a single script

**NOT ALLOWED:**
- Accessing private/internal methods (prefixed with `_`)
- Bypassing protocol interfaces (e.g., `backend._get_connection()`)
- Duplicating protocol logic instead of using protocol methods

Scripts should use **public protocol methods** for portability across backends:
```python
# GOOD: Uses StorageBackend protocol
backend.update_meeting(jurisdiction_id, meeting_id, {"agenda_url": url})

# BAD: Bypasses protocol, ties to specific backend
conn = backend._get_connection()
cursor.execute("UPDATE meetings SET agenda_url = ...")
```

## Check

When reviewing changes:

1. **No raw SQL for data queries?**
   - Use `StorageBackend.get_*()` methods, not `cursor.execute()`
   - Use `DataStatus` for diagnostics, not ad-hoc SQL
   - Use `CORPUS_REGISTRY` for schema info, not hardcoded column names
   - Scripts may use raw SQL for one-off migrations, but must use protocol methods for data access

2. **Layer isolation?**
   - No direct imports between wrong layers
   - Intelligence doesn't call Coordination directly
   - Orchestration mediates between layers

3. **Package boundaries?**
   - `civicos-extraction` doesn't import from `civicos-services`
   - `civic` core has no framework dependencies (Flask, FastAPI)
   - Frontend imports via API, not Python

4. **Public API stability?**
   - Changes to `Civic` class methods are backwards compatible
   - New methods follow existing patterns
   - Deprecation warnings before removal

5. **Data flow direction?**
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

### FAIL - Raw SQL for Data Query
```python
# In any non-migration code
cursor.execute("SELECT COUNT(*) FROM meetings WHERE meeting_date > ...")  # Wrong column name!
cursor.execute("SELECT * FROM embeddings WHERE ...")  # Table doesn't exist!
```
Use instead: `DataStatus(storage, vectors, jurisdiction).summary()` or `storage.get_meetings()`

### FAIL - Layer Violation
```python
# In packages/civicos-extraction/pipeline.py
from civic_services.api import send_email  # Wrong! Extraction shouldn't call services
```

### FAIL - Package Boundary Violation
```python
# In packages/civicos/src/civicos/civicos.py
import flask  # Wrong! Core shouldn't have framework dependencies
```

### PASS - Proper Layer Usage
```python
# In packages/civicos/src/civicos/civicos.py
from civicos.storage.backend import StorageBackend  # Same package
from civicos.orchestrator.suggestions import get_suggestions  # Orchestration layer

# Suggestions query data layer, don't call coordination directly
suggestions = get_suggestions("san-rafael", user_id="user_123")
```
