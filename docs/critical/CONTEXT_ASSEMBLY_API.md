# Context Assembly API

Surface-agnostic context assembly layer for CivicOS. Given any civic item, returns a rich context bundle that any consumer surface can pass to an LLM.

**Status:** Design (P0)
**Date:** 2026-02-08

---

## Core Insight

The intelligence is in **assembling context**, not in any specific UI. Whether the consumer is Open WebUI, a browser extension, Claude.ai via MCP, or an embeddable widget, they all call the same endpoint, get the same context bundle, and pass it to an LLM however that surface does chat.

This decouples context quality from surface proliferation. Improve context assembly once, every surface benefits.

---

## 1. Item Types

The API supports these civic item types:

| Type | Source | Example ID |
|------|--------|------------|
| `agenda_item` | `storage.get_agenda_items()` | `agenda_item:{uuid}` |
| `decision` | `storage.get_decisions()` | `decision:{uuid}` |
| `issue` | `storage.get_issues()` | `issue:{uuid}` |
| `legislation` | `storage.get_legislation()` | `legislation:{bill_id}` |
| `meeting` | `storage.get_meetings()` | `meeting:{uuid}` |
| `initiative` | Relay: `coordination_initiatives` | `initiative:{uuid}` |

Item IDs are the existing database UUIDs. Federation entity namespacing (e.g., `agenda:2026-02-03:item-6a`) maps to these IDs via relay lookup but is not required for the API.

---

## 2. Endpoint Contract

### `GET /api/context/{item_type}/{item_id}`

**Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `item_type` | path | required | One of: `agenda_item`, `decision`, `issue`, `legislation`, `meeting`, `initiative` |
| `item_id` | path | required | Database ID of the item |
| `jurisdiction` | query | required | Jurisdiction ID (e.g., `city-san-rafael`) |
| `sections` | query | all | Comma-separated sections to include (e.g., `history,regulatory,community`). Omit for all. |
| `depth` | query | `standard` | `minimal` (item + summary only), `standard` (all sections), `deep` (extra cross-references, more testimony) |

**Authentication:** Same as existing API (web key or auth token).

### Response Shape

```json
{
  "item": { ... },
  "sections": {
    "history": { ... },
    "regulatory": { ... },
    "community": { ... },
    "financial": { ... },
    "testimony": { ... },
    "participation": { ... }
  },
  "suggested_questions": [ ... ],
  "metadata": { ... }
}
```

### Validation

`item_type` is validated via a `str, Enum`:

```python
class ItemType(str, Enum):
    agenda_item = "agenda_item"
    decision = "decision"
    issue = "issue"
    legislation = "legislation"
    meeting = "meeting"
    initiative = "initiative"
```

FastAPI returns 422 with valid options if an invalid `item_type` is provided.

### Error Responses

| Code | Meaning |
|------|---------|
| 404 | Item not found (explicit message with item type and ID) |
| 400 | Missing required `jurisdiction` parameter |
| 422 | Invalid `item_type` or `sections` parameter |
| 503 | Relay service unavailable (for `initiative` items only) |

Partial failures (some sections succeed, some fail) return 200 with `section_status` in metadata (see Section 3.9).

---

## 3. Context Bundle Schema

### 3.1 `item` — The Focal Item

Always present. Contains the item's core fields plus a generated summary.

```json
{
  "item": {
    "type": "agenda_item",
    "id": "abc-123",
    "title": "4th Street Corridor Rezoning Proposal",
    "description": "Proposal to rezone the 4th Street corridor from C-1 to MU-1...",
    "why_it_matters": "This would allow mixed-use development on a key transit corridor...",
    "jurisdiction": "city-san-rafael",

    "item_details": {
      "item_number": "6A",
      "meeting_id": "mtg-456",
      "meeting_title": "City Council Regular Meeting",
      "meeting_date": "2026-02-03T19:00:00Z",
      "meeting_location": "City Hall, 1400 Fifth Avenue",
      "project_type": "zoning",
      "stance_eligible": true,
      "comment_eligible": true
    }
  }
}
```

The `item_details` shape varies by item type and is enforced via Pydantic discriminated unions:

```python
class AgendaItemDetails(BaseModel):
    item_number: Optional[str] = None
    meeting_id: str
    meeting_title: str
    meeting_date: datetime
    meeting_location: Optional[str] = None
    project_type: Optional[str] = None
    stance_eligible: bool = False
    comment_eligible: bool = False

class DecisionDetails(BaseModel):
    outcome: Optional[str] = None
    decision_date: Optional[datetime] = None  # Maps from Decision.date
    votes: Optional[dict] = None
    body: Optional[str] = None

class IssueDetails(BaseModel):
    issue_type: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None
    created_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None

class LegislationDetails(BaseModel):
    bill_number: Optional[str] = None
    state: Optional[str] = None
    status_label: Optional[str] = None
    keywords: List[str] = []
    leverage_point: Optional[str] = None
    official_url: Optional[str] = None

class MeetingDetails(BaseModel):
    body: Optional[str] = None
    date: Optional[datetime] = None
    location: Optional[str] = None
    agenda_item_count: int = 0

class InitiativeDetails(BaseModel):
    creator_id: Optional[str] = None
    created_at: Optional[datetime] = None
    location: Optional[str] = None

class ContextItem(BaseModel):
    type: ItemType
    id: str
    title: str
    description: Optional[str] = None
    why_it_matters: Optional[str] = None
    jurisdiction: str
    item_details: Union[
        AgendaItemDetails, DecisionDetails, IssueDetails,
        LegislationDetails, MeetingDetails, InitiativeDetails
    ] = Field(discriminator=None)  # Discriminated by item.type at construction time
```

This makes invalid states unrepresentable — a response with `type: "agenda_item"` must have `AgendaItemDetails`. The assembler constructs the correct details type based on `item_type`.

**Field name mapping from internal types:**

| API field | Internal type field | Notes |
|-----------|-------------------|-------|
| `DecisionDetails.decision_date` | `Decision.date` | Renamed for clarity in API |
| `AgendaItemDetails.stance_eligible` | agenda_item dict `stance_eligible` | Direct mapping |
| `LegislationDetails.bill_number` | `Legislation.bill_number` | Direct mapping |

### 3.2 `sections.history` — What Happened Before

Related past decisions and outcomes on this topic.

```json
{
  "history": {
    "related_decisions": [
      {
        "id": "dec-789",
        "title": "4th Street Corridor Study Approval",
        "outcome": "approved",
        "date": "2025-10-15",
        "relevance": "Prior study that initiated this rezoning proposal"
      }
    ],
    "timeline_summary": "The 4th Street corridor has been under review since Oct 2025 when Council approved a corridor study. This is the rezoning proposal resulting from that study."
  }
}
```

**Source:** `civic.what_happened(item.title)` + `civic.what_happened_full_context()` for transcript links.

### 3.3 `sections.regulatory` — What Laws Apply

Federal, state, and local regulatory context.

```json
{
  "regulatory": {
    "municipal_code": [
      {
        "section_number": "14.06.030",
        "section_title": "Mixed-Use Districts",
        "excerpt": "MU-1 districts permit residential densities up to 43 units per acre...",
        "relevance_score": 0.92
      }
    ],
    "state_legislation": [
      {
        "bill_id": "ca-sb423",
        "bill_number": "SB 423",
        "status_label": "Chaptered",
        "summary": "Streamlined housing approvals for compliant jurisdictions",
        "leverage_point": "San Rafael's Housing Element compliance enables SB 423 streamlining"
      }
    ],
    "federal": [],
    "executive_orders": []
  }
}
```

**Source:** `civic.what_applies(item.title)` returns a `RegulatoryStack` with `federal`, `state`, `local` arrays.

**Mapping from `RegulatoryStack`:** The internal type has 3 arrays (`federal`, `state`, `local`). The API restructures this into 4 arrays for clarity:
- `RegulatoryStack.local` → `regulatory.municipal_code` (renamed for clarity)
- `RegulatoryStack.state` → `regulatory.state_legislation`
- `RegulatoryStack.federal` → `regulatory.federal` (legislation) + `regulatory.executive_orders` (split by type)

This is a presentation-layer transformation. If `RegulatoryStack` evolves (e.g., adds an `executive_orders` field), the mapping should be updated to match.

### 3.4 `sections.community` — Who's Engaged

Community activity around this topic.

```json
{
  "community": {
    "similar_issues": [
      {
        "id": "issue-456",
        "title": "Pothole on 4th St near Grand Ave",
        "issue_type": "Streets & Sidewalks",
        "status": "open",
        "distance_description": "On the same corridor"
      }
    ],
    "related_initiatives": [
      {
        "id": "init-789",
        "title": "Protected Bike Lane on 4th Street",
        "voice_count": 23
      }
    ],
    "voice_summary": {
      "total": 82,
      "support": 47,
      "oppose": 12,
      "watching": 23
    }
  }
}
```

**Source:** Multiple sources, assembled by the context layer:
- `similar_issues`: Direct issue search via `storage.get_issues()` with semantic matching (vector search on issue embeddings, 1,459 indexed)
- `related_initiatives`: From relay `coordination_initiatives` table (if relay is available)
- `voice_summary`: From relay `GET /api/coordination/voice/counts/{entity}` endpoint (returns `{support, oppose, watching, total}`)

**V1 data reality:** `civic.whos_with_me()` currently returns `Community` with `recent_voices=[]` and `active_initiatives=[]` always empty. The community section assembler must **not** rely on `whos_with_me()` alone — it should query issues directly via storage and voice counts via the relay API. V1 will have good `similar_issues` data (1,730 issues indexed) but `related_initiatives` and `voice_summary` depend on relay integration and may be sparse until more voices are cast.

### 3.5 `sections.financial` — Follow the Money

Budget context when relevant (primarily for items involving spending).

```json
{
  "financial": {
    "budget_items": [
      {
        "department": "Community Development",
        "line_item": "Corridor Planning",
        "budgeted_dollars": 150000,
        "fiscal_year": "FY25-26"
      }
    ],
    "funding_flows": [],
    "total_relevant_budget": 150000
  }
}
```

**Source:** `civic.budget(department=..., fund=...)` with parameters extracted from item metadata. NOT `civic.budget(item.title)` — the `budget()` method takes keyword arguments (`department`, `fund`, `fiscal_year`, `min_amount`, `max_amount`, `limit`), not a topic string.

**Assembly strategy:** The assembler extracts a department name from the item's metadata (e.g., agenda item's `project_type` → department mapping) and calls `civic.budget(department=extracted_dept)`. For items with no clear department mapping, this section returns empty. With only 58 budget line items for San Rafael, matches will be sparse.

**V1 scope:** Financial section is best-effort. Omitted for `depth=minimal`. Returns empty arrays rather than erroring when no budget data matches. A future `budget_search(topic: str)` method with semantic matching would improve coverage. `civic.funding_flow()` similarly takes `program`, `cfda_number`, `budget_item_id` — not a topic string.

### 3.6 `sections.testimony` — What Was Said

Transcript excerpts from public comment and council discussion.

```json
{
  "testimony": {
    "public_comments": [
      {
        "speaker": "Public Speaker",
        "speaker_role": "public",
        "text": "I've lived on 4th Street for 20 years and I'm concerned about parking...",
        "video_url": "https://youtube.com/watch?v=abc123&t=1847s",
        "start_timestamp": "00:30:47",
        "end_timestamp": "00:31:52"
      }
    ],
    "staff_discussion": [
      {
        "speaker": "Planning Director",
        "speaker_role": "staff",
        "text": "The environmental review found no significant impacts...",
        "video_url": "https://youtube.com/watch?v=abc123&t=923s",
        "start_timestamp": "00:15:23",
        "end_timestamp": "00:17:41"
      }
    ],
    "council_discussion": [
      {
        "speaker": "Council Member Mullen",
        "speaker_role": "council",
        "text": "I'd like to see the traffic study updated before we proceed...",
        "video_url": "https://youtube.com/watch?v=abc123&t=2341s",
        "start_timestamp": "00:39:01",
        "end_timestamp": "00:40:15"
      }
    ]
  }
}
```

Field names align with existing `TranscriptExcerpt` type (`types.py`): `speaker`, `speaker_role`, `start_timestamp`, `end_timestamp`, `video_url`. The `text` field maps from `TranscriptExcerpt.text`.

**Source:** `civic.what_was_said(item.title)` and `civic.get_public_testimony(item.title)`. For decisions, `DecisionWithContext.transcript_links` provides pre-linked excerpts.

### 3.7 `sections.participation` — How to Engage

Current participation state and available actions.

```json
{
  "participation": {
    "comment_status": {
      "open": true,
      "closes_at": "2026-02-03T19:00:00Z",
      "clerk_email": "cityclerk@cityofsanrafael.org"
    },
    "voice_enabled": true,
    "actions_available": ["voice", "comment", "follow"],
    "meeting_logistics": {
      "date": "Mon, Feb 3",
      "time": "7:00 PM",
      "location": "City Hall, 1400 Fifth Avenue",
      "how_to_attend": "In person or via Zoom (link on city website)"
    }
  }
}
```

**Source:** Derived from `stance_eligible`/`comment_eligible` flags on agenda items, plus meeting metadata.

### 3.8 `suggested_questions`

Auto-generated conversation starters tailored to the item type.

```json
{
  "suggested_questions": [
    "What laws apply to this rezoning?",
    "Has this area been rezoned before?",
    "What are residents saying about this?",
    "How does this affect housing density?",
    "What's the timeline for this proposal?"
  ]
}
```

Generated per item type using templates:

| Item Type | Question Templates |
|-----------|-------------------|
| `agenda_item` | Laws that apply, precedent, community opinion, timeline, how to participate |
| `decision` | Why it was decided, who voted how, what it means going forward, related legislation |
| `issue` | Similar issues nearby, city response patterns, who to contact, related policy |
| `legislation` | Local impact, implementation requirements, timeline, who it affects |
| `meeting` | Key agenda items, recent decisions by this body, how to attend |

### 3.9 `metadata`

Bundle provenance and assembly diagnostics.

```json
{
  "metadata": {
    "assembled_at": "2026-02-03T18:30:00Z",
    "jurisdiction": "city-san-rafael",
    "depth": "standard",
    "sections_included": ["history", "regulatory", "community", "testimony", "participation"],
    "section_status": {
      "history": "ok",
      "regulatory": "ok",
      "community": "ok",
      "testimony": "empty",
      "financial": "skipped",
      "participation": "ok"
    },
    "section_errors": {},
    "degraded": false,
    "sources_queried": {
      "what_happened": true,
      "what_applies": true,
      "what_was_said": true,
      "whos_with_me": true,
      "budget": false
    },
    "assembly_time_ms": 340,
    "section_times_ms": {
      "history": 210,
      "regulatory": 340,
      "community": 180,
      "testimony": 95,
      "participation": 5
    },
    "cache_status": "miss"
  }
}
```

**Section status values:**

| Status | Meaning |
|--------|---------|
| `ok` | Query succeeded, data returned |
| `empty` | Query succeeded, no matching data found |
| `error` | Query failed (see `section_errors` for details) |
| `skipped` | Section not requested or not applicable for this depth |
| `timeout` | Section assembly exceeded per-section timeout |
| `unavailable` | Data corpus not indexed for this jurisdiction |

When `section_errors` is non-empty, `degraded` is set to `true`. Consumers can check `degraded` to decide whether to show a "some data temporarily unavailable" notice.

Per-section timing (`section_times_ms`) enables performance monitoring and identifies slow sections.

---

## 4. Orchestration Logic

The context assembler orchestrates existing CivicOS API methods. No new data access — it's a composition layer.

### Assembly Flow

```
GET /api/context/agenda_item/abc-123?jurisdiction=city-san-rafael
                    │
                    ▼
            ┌─────────────┐
            │  Load Item   │  storage.get_agenda_items(id=item_id)
            └──────┬──────┘
                   │
                   ▼
         ┌─────────────────┐
         │ Parallel Queries │  (concurrent, not sequential)
         └─────────────────┘
          │    │    │    │    │
          ▼    ▼    ▼    ▼    ▼
       history reg  comm test  fin
          │    │    │    │    │
          ▼    ▼    ▼    ▼    ▼
         ┌─────────────────┐
         │ Assemble Bundle  │  Merge results + generate suggested_questions
         └─────────────────┘
                   │
                   ▼
              JSON Response
```

### Per-Section Source Mapping

| Section | CivicOS Method | Notes |
|---------|----------------|-------|
| `history` | `what_happened(title)`, `what_happened_full_context(title)` | Top 5 related decisions |
| `regulatory` | `what_applies(title)` | Returns `RegulatoryStack`, mapped to API schema |
| `community` | `storage.get_issues()` + relay voice counts | `whos_with_me()` alone is insufficient (see 3.4) |
| `financial` | `budget(department=...)` | Department extracted from item metadata; often empty |
| `testimony` | `what_was_said(title)`, `get_public_testimony(title)` | Top 5 excerpts each |
| `participation` | Derived from item flags + meeting data | No API call needed |

### Parallel Execution with Error Isolation

Sections are independent — query them concurrently using `asyncio.gather()`. Each section has a per-section timeout. Failed sections return `null` with error details in metadata, following the pattern from `federation.py`.

```python
SECTION_TIMEOUT_S = 10.0  # Per-section timeout
OVERALL_TIMEOUT_S = 15.0  # Overall request timeout

async def assemble_section_with_timeout(name: str, coro, timeout: float = SECTION_TIMEOUT_S):
    """Wrap a section assembly coroutine with timeout handling."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Section '{name}' timed out after {timeout}s")
        raise SectionTimeoutError(section=name, timeout=timeout)

async def assemble_context(item_type, item_id, jurisdiction, sections, depth):
    civic = CivicOS(jurisdiction)
    item = load_item(civic, item_type, item_id)  # Raises ItemNotFoundError → 404

    tasks = {}
    if "history" in sections:
        tasks["history"] = assemble_section_with_timeout(
            "history", assemble_history(civic, item, depth))
    if "regulatory" in sections:
        tasks["regulatory"] = assemble_section_with_timeout(
            "regulatory", assemble_regulatory(civic, item, depth))
    if "community" in sections:
        tasks["community"] = assemble_section_with_timeout(
            "community", assemble_community(civic, item, depth))
    if "testimony" in sections:
        tasks["testimony"] = assemble_section_with_timeout(
            "testimony", assemble_testimony(civic, item, depth))
    if "financial" in sections:
        tasks["financial"] = assemble_section_with_timeout(
            "financial", assemble_financial(civic, item, depth))

    # Execute all sections in parallel, capturing exceptions
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    # Inspect results — isolate failures, don't swallow them
    bundle_sections = {}
    section_status = {}
    section_errors = {}
    section_times = {}

    for section_name, result in zip(tasks.keys(), results):
        if isinstance(result, SectionTimeoutError):
            logger.warning(f"Section '{section_name}' timed out")
            bundle_sections[section_name] = None
            section_status[section_name] = "timeout"
            section_errors[section_name] = f"Timed out after {SECTION_TIMEOUT_S}s"
        elif isinstance(result, Exception):
            logger.error(f"Section '{section_name}' failed: {result}", exc_info=result)
            bundle_sections[section_name] = None
            section_status[section_name] = "error"
            section_errors[section_name] = str(result)
        elif result is None or (hasattr(result, 'is_empty') and result.is_empty):
            bundle_sections[section_name] = result
            section_status[section_name] = "empty"
        else:
            bundle_sections[section_name] = result
            section_status[section_name] = "ok"

    # Mark unrequested sections as skipped
    all_sections = {"history", "regulatory", "community", "financial", "testimony", "participation"}
    for s in all_sections - set(tasks.keys()):
        section_status[s] = "skipped"

    # Build metadata with error reporting
    metadata = assembly_metadata(sections, depth)
    metadata["section_status"] = section_status
    metadata["section_errors"] = section_errors
    metadata["degraded"] = bool(section_errors)

    return ContextBundle(
        item=item,
        sections=ContextSections(**bundle_sections),
        suggested_questions=generate_questions(item_type, item, bundle_sections),
        metadata=metadata,
    )
```

### Response Model with Explicit Optional Fields

Sections use explicit `Optional` fields (not a dict with optional keys) so consumers get type-safe access:

```python
class ContextSections(BaseModel):
    history: Optional[HistorySection] = None
    regulatory: Optional[RegulatorySection] = None
    community: Optional[CommunitySection] = None
    financial: Optional[FinancialSection] = None
    testimony: Optional[TestimonySection] = None
    participation: Optional[ParticipationSection] = None
```

A `null` section means it was requested but failed or had no data. Check `metadata.section_status` to distinguish `"empty"` from `"error"`.

### Item Loading

Each item type loads differently. Uses `next(..., None)` to produce clear 404 errors instead of opaque `StopIteration`:

```python
class ItemNotFoundError(Exception):
    """Raised when a civic item cannot be found by ID."""
    def __init__(self, item_type: str, item_id: str, jurisdiction: str):
        self.item_type = item_type
        self.item_id = item_id
        super().__init__(
            f"{item_type} '{item_id}' not found in jurisdiction '{jurisdiction}'"
        )

def load_item(civic, item_type: ItemType, item_id: str):
    storage = civic._storage
    jurisdiction = civic.jurisdiction

    if item_type == ItemType.agenda_item:
        items = storage.get_agenda_items(jurisdiction_id=jurisdiction)
        item = next((i for i in items if i["id"] == item_id), None)

    elif item_type == ItemType.decision:
        decisions = storage.get_decisions(jurisdiction)
        item = next((d for d in decisions if d["id"] == item_id), None)

    elif item_type == ItemType.issue:
        issues = storage.get_issues(jurisdiction_id=jurisdiction)
        item = next((i for i in issues if i["id"] == item_id), None)

    elif item_type == ItemType.legislation:
        # Use get_legislation_by_bill_id() — DO NOT load all 17K+ records
        item = storage.get_legislation_by_bill_id(state="CA", bill_id=item_id)

    elif item_type == ItemType.meeting:
        meetings = storage.get_meetings(jurisdiction)
        item = next((m for m in meetings if m["id"] == item_id), None)

    elif item_type == ItemType.initiative:
        try:
            item = load_initiative_from_relay(item_id, timeout=5.0)
        except RelayUnavailableError:
            raise HTTPException(
                status_code=503,
                detail="Initiative data temporarily unavailable (relay service down)"
            )

    if item is None:
        raise ItemNotFoundError(item_type, item_id, jurisdiction)

    return item
```

**Performance notes for item loading:**

| Item type | Record count | Loading strategy |
|-----------|-------------|-----------------|
| `agenda_item` | ~200 per jurisdiction | Filter in Python (acceptable) |
| `decision` | 44 | Filter in Python (fast) |
| `issue` | 1,730 | Filter in Python (acceptable for V1; add `get_issue_by_id()` for V2) |
| `legislation` | 17,719 | **Use `get_legislation_by_bill_id()`** — already exists on storage protocol |
| `meeting` | 98 | Filter in Python (fast) |
| `initiative` | Relay DB | Direct lookup via relay API |

V2 optimization: Add `get_by_id(item_type, item_id)` to the storage protocol for O(1) lookups on all types.

---

## 5. Surface Consumption Patterns

### Open WebUI

Open WebUI already has a civic dashboard that calls `city_pulse()`. Context assembly changes the pattern from jurisdiction-level to item-level:

```
User clicks agenda item in dashboard
  → Frontend calls GET /api/context/agenda_item/{id}?jurisdiction=city-san-rafael
  → Bundle returned as JSON
  → Frontend injects bundle into chat as system prompt context
  → User chats with the item ("What laws apply?" → LLM uses regulatory section)
```

The bundle replaces the current pattern where each chat message triggers separate MCP tool calls. Pre-assembled context is faster and more coherent.

### Browser Extension

A browser extension detects when the user is viewing civic content (city council agenda PDF, local news article about a decision) and offers CivicOS context:

```
User visits cityofsanrafael.org/agendas/2026-02-03.pdf
  → Extension detects civic content via URL pattern or page content
  → Extension extracts item identifiers from page
  → Calls GET /api/context/agenda_item/{id}?jurisdiction=city-san-rafael
  → Renders context in sidebar panel
  → User can start a chat with pre-loaded context
```

Item identification from external pages is a separate challenge (URL pattern matching, page scraping). The context API doesn't need to solve this — it takes an ID and returns context.

### MCP (Claude.ai, ChatGPT)

MCP tools already exist for individual queries. A new `get_item_context` tool wraps the context API:

```python
# New MCP tool
def get_item_context(item_type: str, item_id: str, jurisdiction: str) -> dict:
    """Get comprehensive context for a civic item."""
    return call_context_api(item_type, item_id, jurisdiction)
```

This replaces the pattern where the LLM makes 3-5 separate tool calls to build context. One call, full context.

### Embeddable Widget

Third-party sites (community forums, city websites) embed a widget that fetches and renders context:

```html
<civic-context item-type="agenda_item" item-id="abc-123"
               jurisdiction="city-san-rafael"></civic-context>
```

The widget calls the API and renders a card with key context sections. This is a post-pilot concern.

---

## 6. Federation

### V1: Single Jurisdiction (Pilot)

For the Jan 2026 pilot, context assembly queries only the local jurisdiction's data. No cross-jurisdiction fan-out.

### V2: Federated Context

When a user queries context for a state or federal item (e.g., SB 423), the context assembler fans out to peer jurisdiction relays to aggregate:

- How other cities are responding to the same legislation
- Voice counts across jurisdictions
- Related decisions in peer cities

```
GET /api/context/legislation/ca-sb423?jurisdiction=city-san-rafael&federated=true

  1. Local context: what_applies("SB 423") for San Rafael
  2. Fan-out: Query peer MCPs for their SB 423 context
     → city-berkeley MCP: decisions related to SB 423
     → city-oakland MCP: initiatives related to SB 423
  3. Merge: Aggregate into "cross_jurisdiction" section

Response includes:
{
  "sections": {
    "regulatory": { ... local context ... },
    "cross_jurisdiction": {
      "peer_responses": [
        {"jurisdiction": "city-berkeley", "decisions": [...], "voices": {...}},
        {"jurisdiction": "city-oakland", "initiatives": [...]}
      ],
      "summary": "3 Bay Area cities are tracking SB 423. Berkeley approved a related rezoning in Dec 2025."
    }
  }
}
```

This uses the existing MCP federation pattern from `handlers.py` where tools can route queries to peer MCP servers. The context API doesn't implement federation directly — it delegates to the MCP federation layer.

Federation is a V2 concern. The API schema reserves space for it (`cross_jurisdiction` section) but V1 won't populate it.

---

## 7. Caching Strategy

Context bundles are relatively expensive to assemble (multiple DB queries + vector searches). Caching is important for responsiveness.

### Cache Layers

| Layer | TTL | Scope | Invalidation |
|-------|-----|-------|-------------|
| **Response cache** | 5 min | Full bundle per (item_type, item_id, jurisdiction, depth) | Time-based |
| **Section cache** | 15 min | Per section per item | Time-based |
| **Data cache** | Existing | CivicOS API internal caching | Existing behavior |

V1 uses simple time-based expiry. V2 could use event-driven invalidation (e.g., new voice → invalidate community section for that item).

### Cache Key

```
context:{jurisdiction}:{item_type}:{item_id}:{depth}:{sections_hash}
```

### Cache Poisoning Prevention

Degraded bundles (where one or more sections failed) must NOT be cached at full TTL, or transient errors persist for minutes:

```python
if not metadata.get("degraded"):
    cache.set(cache_key, bundle, ttl=300)   # 5 min for healthy bundles
else:
    cache.set(cache_key, bundle, ttl=30)    # 30 sec for degraded bundles
```

A `?fresh=true` query parameter bypasses the cache entirely for debugging/retry.

The response includes `X-CivicOS-Degraded: true` header when serving degraded bundles, so consumers can decide whether to retry.

---

## 8. Implementation Plan

### Phase 1: Core API (This Session → Next Session)

1. Create `packages/civicos-services/src/civicos_services/servers/routers/context.py`
   - FastAPI router with `GET /api/context/{item_type}/{item_id}`
   - Pydantic response models
   - Item loading per type
2. Create `packages/civicos-services/src/civicos_services/context/assembler.py`
   - `ContextAssembler` class that orchestrates CivicOS API calls
   - Per-section assembly functions
   - Suggested question templates
3. Wire into existing API server (`servers/api.py`)

### Phase 2: Section Implementation

Each section is independently implementable:

| Section | Complexity | V1 Data Reality |
|---------|-----------|----------------|
| `participation` | Low | Fully populated from item flags — no external queries needed |
| `history` | Medium | 44 decisions with transcripts — good coverage for recent items |
| `regulatory` | Medium | 16K+ municipal code + 17K+ legislation — rich results |
| `testimony` | Medium | 19 transcripts (4,296 embeddings) — coverage depends on whether item's meeting was transcribed |
| `community` | Medium-High | `whos_with_me()` returns sparse data (`recent_voices=[]`, `active_initiatives=[]` always empty). Assembler must query issues directly + relay voice counts separately. V1 will have good `similar_issues` but sparse `voice_summary`. |
| `financial` | Low | `budget()` takes `department`/`fund` keywords, not topic string. 58 budget items total. Often returns empty. Best-effort in V1. |

### Phase 3: Surface Integration

1. Open WebUI: Add "Chat with this item" button that calls context API
2. MCP: Add `get_item_context` tool
3. Browser extension: Feasibility sketch (V2)

### Phase 4: Federation (V2)

1. Add `federated` query parameter
2. Implement fan-out to peer MCPs
3. Add `cross_jurisdiction` section

---

## 9. Relationship to Existing Features

### `city_pulse()` (MCP tool)

City pulse returns a jurisdiction-level snapshot (all upcoming items, recent outcomes, community pulse). Context assembly returns item-level depth. They're complementary:

- `city_pulse()` → "What's happening in San Rafael?" → list of items
- Context assembly → "Tell me about this specific agenda item" → deep context

City pulse could evolve to return item IDs that link to context assembly for drill-down.

### `prepare()` (CivicOS API)

`prepare()` already does item-level context assembly for agenda items, returning regulatory context, historical decisions, talking points, and allies. Context assembly generalizes this pattern:

- Works for all item types (not just agenda items)
- Returns structured JSON (not just preparation materials)
- Adds testimony, community, financial sections
- Surface-agnostic (prepare was designed for meeting prep UX)

`prepare()` remains useful as a high-level "get me ready for this meeting" action. Context assembly is the lower-level data layer that `prepare()` could eventually delegate to.

### `expandable_decisions` (P1 item)

The expandable decisions feature (click a decision row → see detail) is a direct consumer of context assembly. Instead of building custom decision-detail logic, it calls:

```
GET /api/context/decision/{decision_id}?jurisdiction=city-san-rafael&depth=standard
```

This makes expandable_decisions a thin UI concern — the context API does the heavy lifting.

---

## 10. Design Decisions and Constraints

### Resolved (from review)

1. **Section error handling:** Failed sections return `null` with error details in `metadata.section_status` and `metadata.section_errors`. The `asyncio.gather(return_exceptions=True)` pattern requires explicit exception inspection after gather — exceptions are NOT silently packed into the bundle. Pattern follows `federation.py` lines 571-586.

2. **Item loading safety:** `load_item()` uses `next(..., None)` with explicit `ItemNotFoundError` → 404. Never bare `next()` (which raises opaque `StopIteration`).

3. **Legislation performance:** Uses `get_legislation_by_bill_id()` (exists on storage protocol) instead of loading all 17,719 records.

4. **`budget()` API mismatch:** `budget()` takes keyword args (`department`, `fund`), not a topic string. Financial section extracts department from item metadata. Often returns empty — this is expected.

5. **Testimony field alignment:** Uses `start_timestamp`/`end_timestamp`/`speaker_role` matching `TranscriptExcerpt` in `types.py`, not shortened names.

6. **Cache poisoning:** Degraded bundles cached at 30s TTL (not 5 min). `?fresh=true` bypasses cache.

7. **Partial failure schema:** `metadata.section_status` distinguishes `ok`/`empty`/`error`/`timeout`/`skipped`/`unavailable`.

### Open Questions

1. **Thread safety with `asyncio.to_thread()`:** CivicOS API methods are synchronous. Parallel section assembly via `to_thread()` creates 5 concurrent threads, each opening a database connection. `PostgresBackend._get_connection()` creates a new `psycopg2.connect()` per call (no pool), so connections are thread-safe. However, 5 threads × N concurrent users could exhaust Supabase's connection limit. **V1 approach:** Use `to_thread()` but limit concurrency to 3 sections at a time via `asyncio.Semaphore`. Monitor connection counts. Consider sequential assembly as fallback if connection pressure is observed. **V2:** Connection pooling via `psycopg2.pool.ThreadedConnectionPool`.

2. **Embedding cache:** Multiple sections search with the same item title. Each `what_happened()`, `what_applies()`, `what_was_said()` call generates an embedding of the query string. A shared embedding cache (keyed on query text) reduces 4 embedding API calls to 1. **V1 approach:** Rely on the existing embedding provider's internal caching. **V2:** Add an explicit embedding cache to the vector backend.

3. **Suggested questions — static vs LLM:** V1 uses generic templates per item type that reference `project_type` but not specific item content (e.g., "What laws apply to this proposal?" not "What laws apply to this rezoning?"). V2 could use an LLM to generate context-aware questions (~$0.01/call).

4. **`why_it_matters` field:** Agenda items already have LLM-generated `why_it_matters` from classification. Other item types: use existing field if present, else omit. Don't generate at assembly time in V1.

5. **Bundle size:** A full `standard` bundle could be 5-15KB of JSON. Fine for API responses but may need truncation for MCP tool results (token limits). The `depth=minimal` option addresses this.

6. **Corpus availability checking:** Each section assembler should check if the relevant data corpus is indexed for the jurisdiction (e.g., `get_transcript_count()`) before querying. If zero records exist, return `section_status: "unavailable"` with an explanatory message rather than `"empty"`. This prevents users in newly onboarded jurisdictions from seeing perpetually empty sections with no explanation.

7. **`initiative` item type and relay dependency:** Initiative loading requires the relay database (`RELAY_DATABASE_URL`). If the relay is down, initiative context returns 503. Other item types are unaffected by relay status. Voice counts for the community section also depend on the relay — if unreachable, `voice_summary` is omitted (section status remains `ok` with zeroed voice data) rather than failing the whole section.
