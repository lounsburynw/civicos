# Jurisdiction Critic

Review code changes for proper jurisdiction isolation — ensuring municipal data never leaks across cities.

## Context

CivicOS serves multiple jurisdictions (cities, counties). Municipal data (meetings, decisions, issues, budgets, transcripts) is scoped by `jurisdiction_id`. A missing or hardcoded jurisdiction filter causes data leakage: City A sees City B's meetings, or worse, City B's data overwrites City A's.

This class of bug is invisible in single-city testing and only surfaces when a second city is onboarded — at which point it's a data privacy incident.

## Scope

All code that reads, writes, or queries civic data:
- `packages/civicos/src/civicos/` — Core API and storage
- `packages/civicos-services/src/civicos_services/servers/routers/` — API endpoints
- `packages/civicos-relay/src/civicos_relay/` — Coordination storage
- `packages/civicos-extraction/src/civicos_extraction/` — ETL pipeline
- `scripts/` — Ingestion and migration scripts

## Data Scoping Rules

### Jurisdiction-scoped (MUST filter by jurisdiction_id)

All municipal data requires `jurisdiction_id`:
- Meetings, decisions, agenda items, transcripts, videos, chunks
- Issues (SeeClickFix/311)
- Budget items, federal awards, state passthrough funds, budget funding links
- Elections, election deadlines, election contests, elected officials
- Municipal code
- Federal program allocations (allocations to a specific city)
- Vector search and indexing (all VectorBackend methods)

### National/shared data (NOT jurisdiction-scoped)

These data types are shared across all jurisdictions by design:
- **Legislation** — scoped by `state` (e.g., "CA", "US"), not jurisdiction_id
- **Executive orders** — presidential, no scoping parameter
- **Federal rules** — Federal Register, no scoping parameter
- **Federal programs** — national catalog (but allocations ARE jurisdiction-scoped)
- **Codified law** — uses jurisdiction_id as namespace ("federal-US", "state-CA"), not city-level
- **Legislative events** — scoped by `state` and `bill_id`

### Coordination data (mixed)

Relay coordination follows different isolation rules:
- **Voices** — global (keyed by public_key + entity, entity is already namespaced)
- **Comments** — have jurisdiction field but stored globally
- **Subscriptions** — ARE jurisdiction-scoped (`get_subscriptions_for_jurisdiction()`)
- **Provenance** — global (per-key tracking)

## Check

### 1. StorageBackend calls include jurisdiction_id?

Every call to a jurisdiction-scoped storage method must pass `jurisdiction_id` from the request context, not hardcoded.

```python
# FAIL — hardcoded jurisdiction
meetings = storage.get_meetings("city-san-rafael", limit=10)

# FAIL — missing jurisdiction_id
meetings = storage.get_meetings(limit=10)

# PASS — from request/config
meetings = storage.get_meetings(jurisdiction_id=jurisdiction_id, limit=10)
```

Exception: Scripts performing one-off operations on a specific jurisdiction may hardcode it if the script itself is jurisdiction-specific (e.g., `backfill_san_rafael.py`).

### 2. VectorBackend calls include jurisdiction_id?

All VectorBackend methods require `jurisdiction_id`. No exceptions.

```python
# FAIL — missing jurisdiction
results = vectors.search(query="housing policy", corpus_type="meetings")

# PASS
results = vectors.search(query="housing policy", jurisdiction_id=jurisdiction_id, corpus_type="meetings")
```

### 3. API endpoints pass jurisdiction from request, not hardcoded?

Endpoints must receive jurisdiction_id from URL path params, query params, or request body — never hardcoded in the handler.

```python
# FAIL — hardcoded jurisdiction in endpoint handler
@router.get("/legislation/state/{topic}")
async def get_state_legislation(topic: str):
    c = CivicOS("city-san-rafael")  # HARDCODED!

# PASS — from URL path
@router.get("/elections/{jurisdiction_id}")
async def get_elections(jurisdiction_id: str):
    c = CivicOS(jurisdiction_id)

# PASS — from query param
@router.get("/issues/search")
async def search_issues(jurisdiction: str = Query(...)):
    issues = storage.get_issues(jurisdiction_id=jurisdiction)
```

### 4. National data correctly excluded from jurisdiction scoping?

Don't add unnecessary jurisdiction_id filters to shared data:

```python
# FAIL — jurisdiction filter on national data
orders = storage.get_executive_orders(jurisdiction_id="city-san-rafael")  # No such param

# PASS — national data uses its own scoping
bills = storage.get_legislation(state="CA", topic="housing")
orders = storage.get_executive_orders(president="Biden")
```

### 5. New tables/queries include jurisdiction_id?

When adding a new table or query for municipal data, it MUST:
- Have a `jurisdiction_id` column
- Include `WHERE jurisdiction_id = $1` in all queries
- Be added to the jurisdiction-scoped list above

### 6. Relay coordination data has jurisdiction context?

When creating voices, comments, or actions via the relay:
- The `jurisdiction` field should be populated from request context
- Subscription queries should filter by jurisdiction when returning user-facing data

## Output

Respond with JSON:
```json
{
  "critic": "jurisdiction",
  "pass": boolean,
  "issues": ["list of jurisdiction isolation violations"],
  "severity": "critical" | "warning" | "info",
  "suggestions": ["specific fixes"],
  "data_types_affected": ["meetings", "decisions", "issues", etc]
}
```

Severity guide:
- **critical**: Missing jurisdiction filter on municipal data query, hardcoded jurisdiction in production endpoint
- **warning**: Missing jurisdiction on relay coordination data, jurisdiction validation absent
- **info**: Hardcoded jurisdiction in one-off script (acceptable but note it)

## Examples

### FAIL (critical) — Hardcoded jurisdiction in API endpoint
```python
@router.get("/legislation/state/{topic}")
async def get_state_legislation(topic: str):
    c = CivicOS("city-san-rafael")  # Hardcoded — only works for one city
    bills = c.storage.get_legislation(state="CA", topic=topic)
```

### FAIL (critical) — Missing jurisdiction_id in storage call
```python
def get_upcoming_meetings(storage):
    return storage.get_meetings(since=datetime.now(), limit=5)  # Missing jurisdiction_id!
```

### FAIL (critical) — Missing jurisdiction in vector search
```python
results = vectors.search("bike lane safety", corpus_type="transcripts", top_k=5)
# Missing jurisdiction_id — returns results from ALL cities
```

### FAIL (warning) — Voice without jurisdiction context
```python
voice = Voice(
    entity=request.entity,
    stance=request.stance,
    public_key=request.public_key,
    signature=request.signature,
    # Missing: jurisdiction=request.jurisdiction
)
```

### PASS — Proper jurisdiction isolation
```python
@router.get("/meetings/{jurisdiction_id}")
async def get_meetings(jurisdiction_id: str, limit: int = 20):
    meetings = storage.get_meetings(jurisdiction_id=jurisdiction_id, limit=limit)
    return {"meetings": meetings}
```

### PASS — National data correctly unscoped
```python
# Executive orders are national — no jurisdiction filter needed
orders = storage.get_executive_orders(president="Biden", limit=10)
```
