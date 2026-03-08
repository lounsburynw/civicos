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

**Free tier** (60 req/min): Contact us via GitHub Issues.

**Paid tiers**: Visit the billing endpoint to provision a key:

```bash
curl -X POST "$BASE/api/billing/checkout" \
  -H "Content-Type: application/json" \
  -d '{"tier": "journalist", "email": "you@example.com"}'
```

Returns a Stripe checkout URL. After payment, your API key is emailed.

| Tier | Rate Limit | Use Case |
|------|-----------|----------|
| **free** | 60 req/min | Personal use, exploration |
| **journalist** | 120 req/min | Reporting, investigations |
| **organization** | 300 req/min | Nonprofits, civic tech |
| **city** | 600 req/min | Municipal staff, officials |
| **api** | 1,000 req/min | Application integrations |

All tiers have a 10,000 req/hour ceiling. LLM-powered endpoints (conversation, chat routing) are limited to 30 req/min regardless of tier.

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

Voice, subscription, and initiative endpoints use Nostr-signed requests instead of API key auth. See [Coordination docs](../packages/civicos-relay.md).

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

## Python SDK

For direct integration without HTTP overhead.

```python
from dotenv import load_dotenv
load_dotenv()  # Loads DATABASE_URL from .env

from civicos import CivicOS
c = CivicOS("city-san-rafael")
```

### Query Methods

#### what_happened(query, since=None) -> List[Decision]

Search past council decisions by topic.

```python
decisions = c.what_happened("housing")
for d in decisions:
    print(d.title, d.outcome, d.date)
```

**Decision fields:** `id`, `title`, `date` (datetime), `outcome`, `body`, `votes` (dict)

Outcomes: `approved`, `denied`, `continued`, `withdrawn`, `received`, `adopted`, `other`

#### what_happened_full_context(query, since=None, top_k=5) -> List[DecisionWithContext]

Decisions with linked transcript excerpts and public comment context.

**DecisionWithContext fields:** `decision` (Decision), `transcript_links` (List[TranscriptLink]), `link_confidence` (float), `link_type` (str)

Properties: `has_transcript`, `public_comments`, `staff_discussion`, `council_discussion`

#### whats_next(topics=None, days=30, include_elections=False) -> List[Meeting]

Upcoming meetings, optionally filtered by topic.

```python
meetings = c.whats_next(["transportation"], days=14)
for m in meetings:
    print(m.title, m.date, len(m.agenda_items), "agenda items")
```

**Meeting fields:** `id`, `title`, `date` (datetime), `body`, `agenda_items` (list), `location`

#### what_applies(topic, location=None, ranking_mode="auto") -> RegulatoryStack

Federal, state, and local regulations relevant to a topic.

```python
regs = c.what_applies("housing", ranking_mode="section_first")
print(len(regs.federal), "federal")
print(len(regs.state), "state")
print(len(regs.local), "local")
```

**RegulatoryStack fields:** `topic`, `jurisdiction`, `federal` (list), `state` (list), `local` (list), `retrieved_at` (datetime)

#### what_was_said(query, top_k=10) -> List[TranscriptExcerpt]

Search meeting transcripts by topic.

**TranscriptExcerpt fields:** `id`, `text`, `speaker`, `speaker_role`, `video_id`, `start_timestamp`, `end_timestamp`, `is_public_comment`, `score`

Property: `video_url` — YouTube link with timestamp

#### get_public_testimony(topic, top_k=10) -> List[TranscriptExcerpt]

Public comment excerpts only (filters to public comment segments).

#### what_happened_with_discussion(query, top_k=10, agenda_item=None) -> List[HybridSearchResult]

Combined PDF + transcript search. Each result has `source_type` ("pdf" or "transcript").

### Budget & Finance

#### budget(department=None, fund=None, fiscal_year=None) -> List[BudgetItem]

```python
items = c.budget(department="Fire")
for item in items:
    print(item.department, item.line_item, f"${item.budgeted_dollars:,.0f}")
```

**BudgetItem fields:** `id`, `fund`, `department`, `program`, `line_item`, `budgeted_dollars` (float), `fiscal_year`, `revised_dollars`, `actual_dollars`, `source_url`, `source_page`, `notes`

#### budget_summary(fiscal_year=None, group_by="department") -> List[BudgetSummary]

Aggregated budget by department or fund.

**BudgetSummary fields:** `name`, `budgeted_dollars` (float), `item_count` (int), `revised_dollars`, `actual_dollars`

#### federal_expenditures(cfda_number=None, audit_year=None) -> List[FederalExpenditure]

Audited federal spending from the Single Audit (Federal Audit Clearinghouse data).

```python
exps = c.federal_expenditures()
for e in exps[:5]:
    print(f"{e.federal_program_name}: ${e.amount_expended_dollars:,.0f}")
```

**FederalExpenditure fields:** `report_id`, `cfda_number`, `audit_year` (int), `amount_expended_dollars` (float), `federal_program_total_dollars`, `cluster_total_dollars`, `federal_program_name`, `cluster_name`, `federal_agency_prefix`, `is_major` (bool), `is_passthrough` (bool), `source_url`

#### federal_expenditures_summary(audit_year=None) -> dict

Aggregated federal spending summary.

```python
summary = c.federal_expenditures_summary()
print(f"Total: ${summary['total_dollars']:,.0f} across {len(summary['programs'])} programs")
```

**Returns:** `{"total_dollars": float, "audit_year": int, "programs": [...]}`

#### intergovernmental_revenue(fiscal_year=None, source=None) -> IntergovernmentalRevenueSummary

Revenue from federal, state, and county sources (CA State Controller data).

```python
rev = c.intergovernmental_revenue()
print(f"Federal: ${rev.federal_total_dollars:,.0f}")
print(f"State:   ${rev.state_total_dollars:,.0f}")
print(f"County:  ${rev.county_total_dollars:,.0f}")
print(f"Total:   ${rev.total_dollars:,.0f}")
```

**IntergovernmentalRevenueSummary fields:** `fiscal_year` (int), `entity_name`, `federal_total_dollars` (float), `state_total_dollars` (float), `county_total_dollars` (float), `undetermined_total_dollars` (float), `total_dollars` (float), `details` (List[IntergovernmentalRevenue])

**IntergovernmentalRevenue fields:** `fiscal_year`, `form_table` (SCO form code), `source` ("federal"/"state"/"county"), `amount_dollars` (float), `category`, `subcategory`, `line_description`, `entity_name`

#### funding_flow(program=None, cfda_number=None) -> List[FundingFlow]

Trace federal-to-state-to-city funding paths. Links federal awards to state pass-throughs to city budget items.

> **Note:** This feature requires funding flow linkage data, which is not yet available for all jurisdictions. Returns empty results where linkage data hasn't been ingested.

**FundingFlow fields:** `budget_item_id`, `budget_description`, `budget_dollars` (float), `department`, `fund`, `fiscal_year`, `federal_award_id`, `federal_cfda_number`, `federal_program_name`, `federal_agency`, `federal_dollars`, `match_type`, `match_confidence` (float), `reconciliation_status`

#### funding_flow_impact(program=None, cfda_number=None, cut_percentage=0.20) -> FundingFlowImpact

Model the impact of hypothetical funding cuts on local budget items.

> **Note:** Depends on funding flow linkage data (see above).

**FundingFlowImpact fields:** `program_name`, `cfda_number`, `cut_percentage` (float), `total_current_dollars` (float), `total_impact_dollars` (float), `affected_items` (List[FundingFlow])

### Voting Records

#### get_voting_record(official_name, topic=None, since=None, until=None) -> VotingRecord

Voting statistics for an elected official, optionally filtered by topic.

**VotingRecord fields:** `official_id`, `official_name`, `topic`, `total_votes` (int), `yes_votes` (int), `no_votes` (int), `abstain_votes` (int), `decisions` (list of dicts)

Properties: `yes_percentage`, `no_percentage`, `abstain_percentage`

### AI Actions

#### draft_action(action_type, topic, description, target=None, template=None) -> ActionDraft

AI-generated civic action draft (public comment, letter, etc.).

**ActionDraft fields:** `draft` (str), `description`, `citations` (list)

## Data Coverage

All amounts are in **dollars** (not cents). Dates are ISO 8601 datetimes.

See [Data Dictionary](data-dictionary.md) for complete field-level schemas of all return types.

### San Rafael Pilot (current data)

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
