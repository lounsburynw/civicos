# Architecture Critic

Review code changes against Civic's layered architecture defined in FINAL_PACKAGE_ARCHITECTURE.md.

## Context

Civic follows a layered architecture:

```
┌─────────────┐   ┌──────────────┐   ┌──────────────┐
│ INTELLIGENCE│──▶│ COORDINATION │──▶│   IMPACT     │
│ (extraction)│   │ (relay)      │   │ (metrics)    │
└─────────────┘   └──────────────┘   └──────────────┘
```

Edge intelligence (suggestions, proactive recommendations) lives in the browser extension
and client SDK (`@civicos/client`), not in the Python backend.

## Layer Responsibilities

### 1. Intelligence Layer (`packages/civicos-extraction/`)
- Platform extraction (Legistar, CivicClerk, Granicus)
- Data normalization and storage
- Vector indexing for RAG

### 2. Coordination Layer (`packages/civicos-relay/`, `packages/civicos-services/`)
- Voice casting, action primitives (`civicos-relay`)
- Subscriptions and event delivery (`civicos-relay`)
- Federation sync between relays (`civicos-relay`)
- WebSocket real-time updates, REST API (`civicos-services`)

### 3. Impact Layer (`packages/civicos/src/civicos/metrics/`)
- Empowerment metrics
- Policy influence tracking
- Coalition sustainability
- Democratic quality measures

### 4. Edge Intelligence (`packages/civicos-client/`, `apps/civicos-extension/`)
- Proactive suggestions via City Pulse API and journal suggestions
- AI-drafted comments and enrichment
- User-centric orchestration in the browser extension

## Package Boundaries

- `packages/civicos/` - Core API surface (public methods)
- `packages/civicos-extraction/` - ETL pipeline and data sources
- `packages/civicos-services/` - Application layer (servers, APIs)
- `packages/civicos-client/` - TypeScript client SDK
- `apps/civicos-extension/` - Browser extension (edge intelligence)
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

3. **Package boundaries?**
   - `civicos-extraction` doesn't import from `civicos-services`
   - `civic` core has no framework dependencies (Flask, FastAPI)
   - Frontend imports via API, not Python

4. **Public API stability?**
   - Changes to `Civic` class methods are backwards compatible
   - New methods follow existing patterns
   - Deprecation warnings before removal

5. **Data flow direction?**
   - Data flows: Intelligence → Coordination → Impact
   - Feedback flows back via event bus, not direct calls

## Output

Respond with JSON:
```json
{
  "pass": boolean,
  "issues": ["list of architecture violations"],
  "severity": "critical" | "warning" | "info",
  "layers_affected": ["intelligence", "coordination", "impact", "edge"]
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
from civicos.actions.initiatives import create_initiative  # Action layer
```
