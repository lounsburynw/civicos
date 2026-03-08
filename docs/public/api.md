# CivicOS Core API

The `CivicOS` class is the main entry point. It wraps storage backends and vector search to provide high-level civic data queries.

```python
from dotenv import load_dotenv
load_dotenv()  # Required — loads DATABASE_URL

from civicos import CivicOS
c = CivicOS("city-san-rafael")
```

## Query Methods

### what_happened(query, since=None) -> List[Decision]

Search past council decisions by topic.

```python
decisions = c.what_happened("housing")
for d in decisions:
    print(d.title, d.outcome, d.date)
```

**Decision fields:** `id`, `title`, `date`, `outcome`, `body`, `votes`

Outcomes: `approved`, `denied`, `continued`, `withdrawn`, `received`, `adopted`, `other`

### what_happened_full_context(query, since=None, top_k=5) -> List[DecisionWithContext]

Decisions with linked transcript excerpts and public comment context.

### whats_next(topics=None, days=30, include_elections=False) -> List[Meeting]

Upcoming meetings, optionally filtered by topic.

```python
meetings = c.whats_next(["transportation"], days=14)
for m in meetings:
    print(m.title, m.date, len(m.agenda_items), "agenda items")
```

**Meeting fields:** `id`, `title`, `date`, `body`, `agenda_items`, `location`

### what_applies(topic, location=None, ranking_mode="auto") -> RegulatoryStack

Federal, state, and local regulations relevant to a topic.

```python
regs = c.what_applies("housing", ranking_mode="section_first")
print(len(regs.federal), "federal")
print(len(regs.state), "state")
print(len(regs.local), "local")
```

### what_was_said(query, top_k=10) -> List[TranscriptExcerpt]

Search meeting transcripts by topic.

**TranscriptExcerpt fields:** `id`, `text`, `speaker`, `speaker_role`, `video_id`, `start_timestamp`, `end_timestamp`, `is_public_comment`

### get_public_testimony(topic, top_k=10) -> List[TranscriptExcerpt]

Public comment excerpts only (filters transcripts to public comment segments).


### what_happened_with_discussion(query, top_k=10, agenda_item=None) -> List[HybridSearchResult]

Combined PDF + transcript search. Each result has `source_type` ("pdf" or "transcript").

## Budget & Finance

### budget(department=None, fund=None, fiscal_year=None) -> List[BudgetItem]

```python
items = c.budget(department="Fire")
for item in items:
    print(item.department, item.line_item, f"${item.budgeted_dollars:,.0f}")
```

**BudgetItem fields:** `id`, `fund`, `department`, `line_item`, `budgeted_dollars`, `fiscal_year`, `revised_dollars`, `actual_dollars`, `source_url`, `source_page`

### budget_summary(fiscal_year=None, group_by="department") -> List[BudgetSummary]

Aggregated budget by department or fund.

### funding_flow(program=None, cfda_number=None) -> List[FundingFlow]

Trace federal-to-state-to-city funding paths.

### funding_flow_impact(program=None, cut_percentage=0.20) -> FundingFlowImpact

Model the impact of hypothetical funding cuts.

### federal_expenditures(cfda_number=None, audit_year=None) -> List[FederalExpenditure]

Audited federal spending from the Single Audit (FAC data).

### intergovernmental_revenue(fiscal_year=None, source=None) -> IntergovernmentalRevenueSummary

Revenue from federal, state, and county sources (CA State Controller data).

## Voting Records

### get_voting_record(official_name, topic=None, since=None, until=None) -> VotingRecord

Voting statistics for an elected official, optionally filtered by topic.

## AI Actions

### draft_action(action_type, topic, description, target=None, template=None) -> ActionDraft

AI-generated civic action draft (public comment, letter, etc.).

**ActionDraft fields:** `draft`, `description`, `citations`

## Storage Backends

Backend is selected automatically based on environment:

| Condition | Backend | Vectors |
|-----------|---------|---------|
| `DATABASE_URL` set (PostgreSQL) | `PostgresBackend` | `PgVectorBackend` |
| No `DATABASE_URL` | `SQLiteBackend` | ChromaDB |

```python
# Verify backend
print(type(c.storage).__name__)  # PostgresBackend or SQLiteBackend
```

## Diagnostics

```python
from civicos import CivicOS, DataStatus, format_data_status

c = CivicOS('city-san-rafael')
status = DataStatus(c.storage, c._vectors, 'city-san-rafael')
print(format_data_status(status.summary()))  # Corpus counts, gaps, coverage
print(status.gaps())  # Non-zero gaps only
```
