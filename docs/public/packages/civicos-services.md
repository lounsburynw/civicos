# civicos-services

FastAPI REST API server. Exposes civic data, coordination, AI, and admin endpoints.

**Location:** `packages/civicos-services/`

## Endpoints

### Core
- `GET /health` — Health check
- `GET /api/status` — Detailed health with dependency checks
- `GET /api/jurisdictions` — Available jurisdictions with data counts
- `GET /api/config/google-maps-key` — Frontend geocoding config

### Data
- `GET /api/events` — Meeting listings
- `GET /api/events/search` — Meeting search
- `GET /api/events/{id}` — Meeting detail
- `GET /api/issues` — Community issues
- `GET /api/issues/search` — Issue search
- `GET /api/legislation/state/{topic}` — State legislation by topic
- `GET /api/legislation/federal/{topic}` — Federal legislation by topic
- `GET /api/voting-record/*` — Official voting records
- `GET /api/budget` — Budget data
- `GET /api/transcripts` — Transcript search
- `GET /api/public-testimony` — Public testimony search

### Coordination
- `POST /api/coordination/voice` — Cast a voice (stance)
- `GET /api/coordination/voice/counts/{entity}` — Voice counts per entity
- `GET /api/coordination/voice/{entity}` — List voices on entity
- `POST /api/coordination/subscribe` — Subscribe to topic/entity
- `DELETE /api/coordination/subscribe/{id}` — Unsubscribe
- `GET /api/coordination/provenance/{public_key}` — Key provenance
- `GET /api/coordination/sync/voices` — Export voices for peer sync
- `POST /api/coordination/sync/voices` — Import voices from peer

### AI
- `POST /api/conversation` — AI conversation (30 req/min)
- `POST /api/chat/route` — Chat intent classification (30 req/min)
- `POST /api/ai/*` — LLM provider proxying

### User
- `/api/user/*` — Profile and preferences
- `/api/follows/*` — Topic/entity following
- `/api/threads/*` — Discussion threads
- `/api/drafts` — Draft comments

### Admin
- `POST /api/admin/trigger` — ETL operations (10 req/min)
- `/.well-known/nostr.json` — NIP-05 identity verification

## Auth

Optional API key authentication. Keys are tracked with usage logging.

## Rate Limiting

Global per-client rate limiting, plus stricter per-endpoint limits on AI and admin endpoints.

## Deployment

```bash
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py
```
