# Architecture Critic

Review code changes against CivicOS's layered architecture and package boundaries.

## Context

CivicOS follows a layered architecture with clear package boundaries:

```
┌─────────────┐   ┌──────────────┐   ┌───────────────┐
│ INTELLIGENCE│──▶│ COORDINATION │──▶│ EDGE          │
│ (extraction)│   │ (relay)      │   │ (extension,   │
│             │   │ (services)   │   │  MCP, client) │
└─────────────┘   └──────────────┘   └───────────────┘
```

## Layer Responsibilities

### 1. Intelligence Layer (`packages/civicos-extraction/`)
- Platform extraction (Legistar, CivicClerk, Granicus, SeeClickFix)
- Data normalization and storage via StorageBackend protocol
- Vector indexing for RAG via VectorBackend protocol
- Python package name: `civicos_extraction`

### 2. Core Data Layer (`packages/civicos/`)
- CivicOS API surface (`what_happened()`, `what_applies()`, etc.)
- StorageBackend, VectorBackend, DataSource protocols
- Sub-protocols: ContentStorage, LegislationStorage, FinancialStorage, CommunityStorage, ElectionStorage, OperationsStorage
- Diagnostics: DataStatus, VectorCoverage
- Python package name: `civicos`

### 3. Coordination Layer
- `packages/civicos-relay/` — Voice casting, actions, attestation, subscriptions, sync, federation (`civicos_relay`)
- `packages/civicos-signer/` — Portable attestation signing service for issuer orgs (`civicos_signer`)
- `packages/civicos-services/` — REST API, WebSocket, chat servers (`civicos_services`)

### 4. Edge Intelligence
- `packages/civicos-client/` — TypeScript SDK (`@civicos/client`)
- `packages/civicos-components/` — Svelte UI component library
- `apps/civicos-extension/` — Chrome browser extension (primary user surface)
- `apps/civicos-mcp/` — MCP server for AI agents (Claude, ChatGPT)

### 5. Shared
- `packages/civicos-config/` — Shared jurisdiction configuration (`civicos_config`)

## Package Boundaries

### Python Packages

| Filesystem Path | Python Import | Purpose |
|-----------------|---------------|---------|
| `packages/civicos/` | `from civicos import ...` | Core API + protocols |
| `packages/civicos-extraction/` | `from civicos_extraction import ...` | ETL pipeline |
| `packages/civicos-relay/` | `from civicos_relay import ...` | Coordination/federation |
| `packages/civicos-signer/` | `from civicos_signer import ...` | Attestation signing |
| `packages/civicos-services/` | `from civicos_services import ...` | Application servers |
| `packages/civicos-config/` | `from civicos_config import ...` | Shared config |

### TypeScript/Node Packages

| Filesystem Path | Import | Purpose |
|-----------------|--------|---------|
| `packages/civicos-client/` | `@civicos/client` | Client SDK |
| `packages/civicos-components/` | Svelte components | UI library |
| `apps/civicos-extension/` | Chrome extension | Primary UX |
| `apps/civicos-mcp/` | Modal deployment | MCP server |

### Apps (Deployments)

| Path | Purpose | Status |
|------|---------|--------|
| `apps/civicos-extension/` | Browser extension | Active (primary) |
| `apps/civicos-mcp/` | MCP server | Active |
| `apps/civicos-openwebui-fork/` | Open WebUI (separate repo, symlinked) | Secondary |
| `apps/civicos-workspace/` | Vue frontend | **DEPRECATED** |

## CivicOS Private Attribute Access

**NEVER** access `_storage` or `_vectors` on a CivicOS instance from outside the CivicOS class itself.

Use the **public properties** instead:
- `civic.storage` (not `civic._storage`)
- `civic.vectors` (not `civic._vectors`)

This applies everywhere: apps, services, scripts, tests. The public properties exist specifically for this purpose.

**FAIL pattern:** `civic._storage.get_meetings(...)` or `_civic._vectors.search(...)`
**PASS pattern:** `civic.storage.get_meetings(...)` or `_civic.vectors.search(...)`

## Scripts Directory (`scripts/`)

Scripts are integration code for ETL, migration, and batch operations:

**ALLOWED:**
- Import from any package (`civicos`, `civicos_extraction`, `civicos_services`)
- Direct database operations for one-off migrations
- Combining multiple pipeline stages in a single script

**NOT ALLOWED:**
- Accessing private/internal methods (prefixed with `_`)
- Bypassing protocol interfaces (e.g., `backend._get_connection()`)
- Duplicating protocol logic instead of using protocol methods

## Check

When reviewing changes:

1. **No raw SQL for data queries?**
   - Use `StorageBackend.get_*()` methods, not `cursor.execute()`
   - Use `DataStatus` for diagnostics, not ad-hoc SQL
   - Use `CORPUS_REGISTRY` for schema info, not hardcoded column names
   - Scripts may use raw SQL for one-off migrations, but must use protocol methods for data access

2. **Layer isolation?**
   - No direct imports between wrong layers
   - Intelligence (`civicos_extraction`) doesn't import from Coordination (`civicos_relay`, `civicos_services`)
   - Coordination doesn't import from Intelligence
   - Edge reads via API, not Python imports

3. **Package boundaries?**
   - `civicos_extraction` doesn't import from `civicos_services` or `civicos_relay`
   - `civicos` core has no framework dependencies (Flask, FastAPI)
   - `civicos_relay` doesn't import from `civicos_extraction`
   - Frontend communicates via API, not Python

4. **Public API stability?**
   - Changes to `CivicOS` class methods are backwards compatible
   - New methods follow existing patterns
   - Protocol changes update all implementations

5. **Data flow direction?**
   - Data flows: Intelligence → Core Storage → Coordination → Edge
   - Relay coordination data flows separately from civic data
   - Federation sync is relay-to-relay, not through core

6. **Correct Python package names?**
   - `civicos_extraction` (NOT `civic_extraction`)
   - `civicos_relay` (NOT `civic_relay`)
   - `civicos_services` (NOT `civic_services`)

## Output

Respond with JSON:
```json
{
  "critic": "architecture",
  "pass": boolean,
  "issues": ["list of architecture violations"],
  "severity": "critical" | "warning" | "info",
  "layers_affected": ["intelligence", "core", "coordination", "edge"]
}
```

## Examples

### FAIL - Raw SQL for Data Query
```python
# In any non-migration code
cursor.execute("SELECT COUNT(*) FROM meetings WHERE meeting_datetime > ...")
```
Use instead: `storage.get_meetings(jurisdiction_id, since=...)` or `DataStatus(storage, vectors, jurisdiction).summary()`

### FAIL - Layer Violation
```python
# In packages/civicos-extraction/
from civicos_services.api import send_email  # Wrong! Extraction shouldn't call services

# In packages/civicos-relay/
from civicos_extraction.pipeline import Pipeline  # Wrong! Relay shouldn't import extraction
```

### FAIL - Package Boundary Violation
```python
# In packages/civicos/src/civicos/civicos.py
import flask  # Wrong! Core shouldn't have framework dependencies
```

### FAIL - Wrong Package Name
```python
from civic_extraction import Pipeline  # Wrong! It's civicos_extraction
from civic_relay import verify_voice   # Wrong! It's civicos_relay
```

### PASS - Proper Layer Usage
```python
# In packages/civicos/src/civicos/civicos.py
from civicos.storage.backend import StorageBackend  # Same package

# In packages/civicos-services/
from civicos_relay.voice.crypto import verify_voice  # Services can use relay

# In scripts/
from civicos_extraction.pipeline import Pipeline  # Scripts can import any package
from civicos.storage.backend import StorageBackend
```
