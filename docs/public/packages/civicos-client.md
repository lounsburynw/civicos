# civicos-client

TypeScript client library for the CivicOS REST API and coordination relay.

**Location:** `packages/civicos-client/`

Used by the browser extension and any TypeScript/JavaScript application.

## Core Classes

### RegistryClient
Service discovery — resolves jurisdiction URLs and manages active jurisdiction.

```typescript
import { RegistryClient } from '@civicos/client';

const registry = new RegistryClient();
const servers = await registry.getRegistryServers();
const parents = await registry.getParentServers('city-san-rafael');
await registry.setActiveJurisdiction('city-san-rafael');
```

### ApiClient
REST API wrapper — typed methods for all CivicOS endpoints.

```typescript
import { ApiClient } from '@civicos/client';

const api = new ApiClient(baseUrl);
await api.castVoice(entityId, 'support', jurisdiction, proof);
const counts = await api.getVoiceCountsBatch(ids, jurisdiction);
const synthesis = await api.getCommentSynthesis(entityId);
```

### CivicSession
High-level session orchestration — loads city pulse, manages state.

```typescript
import { CivicSession } from '@civicos/client';

const session = new CivicSession(registryClient);
const pulse = await session.loadPulse(); // CityPulseData
```

### AIManager
AI provider orchestration — manages multiple LLM backends.

Supported providers: Claude (Anthropic), OpenAI, Gemini, Ollama (local), Chrome Nano (on-device), CivicOS proxy.

## Key Types

- `CityPulseData` — City dashboard (meetings, outcomes, community pulse, participation windows)
- `VoiceCounts` — Voice aggregation by stance
- `Initiative`, `CivicAction`, `CivicActionProgress` — Community coordination
- `ContextBundle` — Full context for a civic item (history, regulatory, testimony)
- `Comment`, `CommentCounts`, `CommentSynthesis` — Comment aggregation

## Interfaces

- `StorageAdapter` — Pluggable storage (chrome.storage, localStorage, etc.)
- `Signer` — Cryptographic signing interface

See `packages/civicos-client/src/types.ts` for all type definitions.
