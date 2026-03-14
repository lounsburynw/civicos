# CivicOS API Reference

CivicOS provides two interfaces: a **REST API** for HTTP clients (curl, JavaScript, etc.) and a **Python SDK** for direct integration.

## Quick Start (REST API)

```bash
# Base URL (San Rafael pilot)
BASE=https://san-rafael.civicosproject.org

# Upcoming meetings
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "$BASE/api/events/search?topics=housing&date_range=next+month"

# Past decisions
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "$BASE/api/events/search?q=housing"

# Legislation
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "$BASE/api/legislation/state/housing"

# Interactive docs (no auth required)
open "$BASE/docs"
```

### Getting an API Key

**Open tier** (30 req/min, limited tools): No key required for `city_pulse`, `get_voice_counts`, and a few other discovery tools.

**Free tier** (60 req/min): Contact us via GitHub Issues.

**Paid tiers**: Visit the billing endpoint to provision a key:

```bash
curl -X POST "$BASE/api/billing/checkout" \
  -H "Content-Type: application/json" \
  -d '{"tier": "builder", "email": "you@example.com"}'
```

Returns a Stripe checkout URL. After payment, your API key is provisioned automatically. Key delivery is currently manual — an admin will send it to the email you provide. Automated delivery is planned.

| Tier | Rate Limit | Use Case | Tools |
|------|-----------|----------|-------|
| **open** | 30 req/min | Discovery, dashboards | 6 tools (city_pulse, get_started, voice counts, relays, initiatives) |
| **free** | 60 req/min | Personal use, exploration | + All read-only civic data (~30 tools) |
| **builder** | 300 req/min | Application integrations, civic tech | + Participation tools (testimony, comment drafting, meeting prep) |
| **organization** | 300 req/min | Nonprofits, civic orgs | Same as builder |
| **city** | 600 req/min | Municipal staff, officials | Same as builder |
| **admin** | 1,000 req/min | Platform operations | + Admin tools (data status, cost dashboard, key management) |

All tiers have a 10,000 req/hour ceiling. LLM-powered endpoints (conversation, chat routing) are limited to 30 req/min regardless of tier. See [MCP Tool Access by Tier](mcp/setup.md#tool-access-by-api-tier) for the complete tool-to-tier mapping.

### Billing Webhooks

Stripe webhook events (`checkout.session.completed`, `customer.subscription.deleted`, `invoice.payment_failed`) are handled at `POST /api/billing/webhook`. On successful checkout, the key is auto-provisioned with the correct tier. Subscription changes (cancellations, failures) update key status automatically.

## Authentication

All API requests require a Bearer token in the `Authorization` header:

```
Authorization: Bearer YOUR_API_KEY
```

**Key format:** `cvk_live_` followed by 32 hex characters.

**Unauthenticated requests return 401:**

```json
{
  "detail": {
    "error": "Authentication required",
    "message": "Include Bearer token in Authorization header",
    "example": "Authorization: Bearer <your_api_key>"
  }
}
```

## Rate Limiting

The API uses a sliding-window rate limiter with per-minute and per-hour windows, plus a burst token bucket for spike protection. Rate limits are tracked per API key (or per IP for unauthenticated requests).

Rate limit status is returned in response headers:

```
X-RateLimit-Limit-Minute: 120
X-RateLimit-Remaining-Minute: 118
X-RateLimit-Limit-Hour: 10000
X-RateLimit-Remaining-Hour: 9998
X-RateLimit-Burst-Remaining: 20
```

**When rate limited (429):**

```json
{
  "detail": {
    "error": "Rate limit exceeded",
    "message": "Too many requests. Limit: 120 per minute",
    "retry_after": 45
  }
}
```

The `Retry-After` header tells you how many seconds to wait.

> **Note:** Rate limit counters are in-memory and reset on server restart. This is acceptable for pilot scale but means brief windows of unrestricted access after deploys.

## Error Responses

| Status | Meaning |
|--------|---------|
| 400 | Bad request — invalid parameters |
| 401 | Unauthorized — missing or invalid API key |
| 404 | Not found — resource doesn't exist |
| 422 | Validation error — malformed request body |
| 429 | Rate limited — see `Retry-After` header |
| 500 | Internal error |
| 503 | Service unavailable — downstream dependency down |

**Validation errors (422)** return field-level details:

```json
{
  "detail": [
    {
      "loc": ["body", "title"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## REST Endpoints

### Meetings & Events

#### GET /api/events/search

Search upcoming and past meetings.

| Parameter | Type | Description |
|-----------|------|-------------|
| `jurisdiction` | string | Jurisdiction ID (default: `city-san-rafael`) |
| `topics` | string | Comma-separated topic filter |
| `q` | string | Free-text search query |
| `date_range` | string | `"this week"`, `"next month"`, or month name |
| `itemCountMin` | int | Minimum agenda items |

```bash
curl -H "Authorization: Bearer $KEY" \
  "$BASE/api/events/search?topics=housing,transportation&date_range=next+month"
```

**Response:**

```json
{
  "events": [
    {
      "id": "mtg-2026-03-10-cc",
      "title": "City Council Regular Meeting",
      "date": "2026-03-10T19:00:00",
      "body": "City Council",
      "location": "City Hall, 1400 Fifth Ave",
      "agenda_items": [...]
    }
  ],
  "count": 5,
  "query": {"topics": ["housing", "transportation"]},
  "jurisdictions_searched": ["city-san-rafael"]
}
```

#### GET /api/events/{event_id}

Get a single meeting with full agenda.

#### GET /api/events

List all events, optionally filtered by `jurisdiction`, `project_type`, or `start_date`.

### Legislation

#### GET /api/legislation/state/{topic}

State bills relevant to a topic.

| Parameter | Type | Description |
|-----------|------|-------------|
| `jurisdiction` | string | Filter by jurisdiction |
| `status` | string | Bill status filter |
| `limit` | int | Max results (default: 50) |

```bash
curl -H "Authorization: Bearer $KEY" "$BASE/api/legislation/state/housing?limit=10"
```

**Response:**

```json
{
  "topic": "housing",
  "level": "state",
  "bills": [
    {
      "bill_id": "ca-sb123",
      "bill_number": "SB 123",
      "bill_name": "Housing Accountability Act",
      "status": "3",
      "summary": "...",
      "leverage_point": "Comment period open until March 15"
    }
  ],
  "count": 10
}
```

#### GET /api/legislation/federal/{topic}

Federal bills relevant to a topic. Same parameters as state.

### Voting Records

#### GET /api/voting-record/{official}/{jurisdiction}

Voting statistics for an elected official.

```bash
curl -H "Authorization: Bearer $KEY" \
  "$BASE/api/voting-record/Kate+Colin/city-san-rafael"
```

### Issues (SeeClickFix / 311)

#### GET /api/operational-issues/{jurisdiction_id}

SeeClickFix community issues.

| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | int | Max results (default: 50) |
| `status` | string | Filter by status |

#### GET /api/issues/search

Search user-created issues with filters for `category`, `jurisdiction`, `status`, and free-text `q`.

### Context Assembly

#### GET /api/context/{item_type}/{item_id}

Assemble a rich context bundle for any civic item. This is the primary endpoint for getting comprehensive background on a meeting, decision, or issue.

| Parameter | Type | Description |
|-----------|------|-------------|
| `item_type` | string | `"decision"`, `"meeting"`, `"issue"`, `"event"`, `"legislation"`, `"initiative"` |
| `item_id` | string | Entity identifier |
| `jurisdiction` | string | Required. e.g., `"city-san-rafael"` |
| `sections` | string | Comma-separated: `history`, `regulatory`, `financial`, `testimony`, `participation` |
| `depth` | string | `"minimal"`, `"standard"` (default), `"deep"` |

```bash
curl -H "Authorization: Bearer $KEY" \
  "$BASE/api/context/decision/dec-123?jurisdiction=city-san-rafael&sections=history,regulatory"
```

### Coordination (Nostr-based)

Read endpoints (voice counts, initiative listings) are available via the REST API. **Write endpoints** (casting voices, creating initiatives, committing to actions) are served exclusively by the [relay](relay/overview.md) and require Nostr-signed requests. Write tools are not available through the MCP server or API key tiers.

Write requests are subject to the relay's [acceptance policy](relay/overview.md#acceptance-policy) — rate limiting per public key, with unlimited access for attested or paying users.

#### GET /api/coordination/voice/counts/{entity}

Public endpoint (no auth). Returns voice counts for an entity.

```json
{
  "entity": "city-san-rafael:mtg-2026-03-10-cc:item-5",
  "support": 42,
  "oppose": 12,
  "watching": 8,
  "total": 62
}
```

### Admin & Diagnostics

#### GET /api/tools/data-provenance

Public endpoint. Returns data coverage and freshness for the jurisdiction.

#### GET /api/status

Public endpoint. Health check with database, vector, and service status.

#### GET /api/admin/cost-dashboard

Operating cost breakdown (admin auth required).

---

## v2 Query Interface (Recommended)

The v2 interface provides server-side composition across corpora and jurisdictions. All queries go through 5 verbs at `/api/v2/civic/`:

```bash
# Multi-corpus search
curl -X POST "$BASE/api/v2/civic/search" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "housing", "corpus": ["decisions", "legislation", "meetings"]}'

# Cross-jurisdiction search (parents = county, state, federal)
curl -X POST "$BASE/api/v2/civic/search" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "housing", "corpus": ["decisions"], "include_parents": true}'

# Cross-jurisdiction with siblings (other cities in same county)
curl -X POST "$BASE/api/v2/civic/search" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "housing", "corpus": ["decisions"], "include_parents": true, "include_siblings": true}'
```

### civic.search

`POST /api/v2/civic/search`

| Field | Type | Description |
|-------|------|-------------|
| `query` | string | Natural language query (required) |
| `corpus` | string[] | Corpus types to search (required): `decisions`, `testimony`, `legislation`, `meetings`, `issues`, `budget`, `municipal_code`, `packets`, `rules`, `orders` |
| `jurisdiction` | string | Override jurisdiction (default: server's jurisdiction) |
| `since` | string | Date range start (ISO) |
| `until` | string | Date range end (ISO) |
| `location` | string | Geographic filter |
| `limit` | int | Max results (1-100, default 10) |
| `depth` | string | `minimal`, `standard` (default), `deep` |
| `mode` | string | `search` (default), `aggregate`, `trend`, `diff`, `intersect` |
| `include_parents` | bool | Include parent jurisdictions (county, state, federal) |
| `include_siblings` | bool | Include sibling jurisdictions (same parent county) |

**Response:**

```json
{
  "results": [
    {
      "type": "decision",
      "ref": "decision:city-san-rafael:dec-123",
      "title": "Approve Housing Element Update",
      "date": "2026-02-15",
      "summary": "Approved 4-1 — City Council",
      "relevance": 0.95,
      "jurisdiction": "city-san-rafael",
      "details": {"outcome": "Approved 4-1", "vote_summary": "4-1"}
    }
  ],
  "jurisdiction_results": {
    "city-san-rafael": [...],
    "county-marin": [...]
  },
  "meta": {
    "schema_version": "2025.1",
    "query_time_ms": 245,
    "total_results": 12,
    "corpus_counts": {"decisions": 5, "legislation": 7}
  }
}
```

`jurisdiction_results` is only present in cross-jurisdiction queries. Each `CivicResult` includes a `jurisdiction` field.

### civic.upcoming

`POST /api/v2/civic/upcoming`

| Field | Type | Description |
|-------|------|-------------|
| `types` | string[] | Event types: `meetings`, `hearings`, `comment_periods`, `legislation`, `elections` |
| `days` | int | Look-ahead window (1-365, default 14) |
| `actionable_only` | bool | Only events with participation opportunities |

### civic.context

`POST /api/v2/civic/context`

| Field | Type | Description |
|-------|------|-------------|
| `ref` | string | Opaque ref from a search/upcoming result |
| `concept` | string | Civic term to look up (e.g., "conditional use permit") |
| `depth` | string | `minimal`, `standard`, `deep` |

Provide either `ref` (item context) or `concept` (jargon lookup), not both.

### civic.act

`POST /api/v2/civic/act`

| Field | Type | Description |
|-------|------|-------------|
| `action` | string | Action name: `prepare_comment`, `comment_template`, etc. |
| `ref` | string | Item reference for context-dependent actions |
| `params` | object | Action-specific parameters |

### civic.explore

`POST /api/v2/civic/explore`

| Field | Type | Description |
|-------|------|-------------|
| `what` | string | `jurisdictions`, `corpora`, `corpus_schema:{name}`, `actions`, `capabilities`, `schema_version` |

---

## Data Coverage

All amounts are in **dollars** (not cents). Dates are ISO 8601 datetimes.

See [Data Dictionary](data-dictionary.md) for complete field-level schemas of all return types.

### San Rafael Pilot (as of March 2026)

| Corpus | Records | Source |
|--------|---------|--------|
| Meetings | ~98 | ProudCity |
| Decisions | ~44 | Minutes extraction |
| Transcripts | ~19 | YouTube + AssemblyAI |
| Agenda packets | ~5,084 chunks | City agenda PDFs |
| Municipal code | ~16,175 sections | Municode |
| Community issues | ~1,730 | SeeClickFix (311) |
| Budget items | ~58 | FY25-26 budget |
| Legislation | ~17,719 | LegiScan (CA + federal) |
| Federal expenditures | 52 | FAC Single Audit |
| Intergovernmental revenue | 10 line items | CA State Controller |

### Known Limitations

- **Funding flow linkage** (`funding_flow()`, `funding_flow_impact()`) — linkage data not yet ingested. These methods return empty results.
- **Transcript search** — requires vector embeddings. Available via the hosted API but not in local SQLite mode.
- **Data freshness** — meetings and agendas update daily. Legislation updates weekly. Budget data is per fiscal year.
