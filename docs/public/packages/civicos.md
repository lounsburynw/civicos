# civicos

Core Python package. Provides the `CivicOS` class for querying civic data.

**Location:** `packages/civicos/`

## Public API

```python
from civicos import CivicOS

c = CivicOS("city-san-rafael")  # or a CivicOSConfig object
```

### Query Methods

| Method | Returns | Purpose |
|--------|---------|---------|
| `what_happened(query, since)` | `List[Decision]` | Past decisions |
| `what_happened_full_context(query, since, top_k)` | `List[DecisionWithContext]` | Decisions + transcript links |
| `what_happened_with_discussion(query, top_k, agenda_item)` | `List[HybridSearchResult]` | PDF + transcript combined search |
| `whats_next(topics, days, include_elections)` | `List[Meeting]` | Upcoming meetings |
| `what_applies(topic, location, ranking_mode)` | `RegulatoryStack` | Regulatory context |
| `what_was_said(query, top_k)` | `List[TranscriptExcerpt]` | Transcript search |
| `get_public_testimony(topic, top_k)` | `List[TranscriptExcerpt]` | Public comment excerpts |

| `get_voting_record(official_name, topic, since, until)` | `VotingRecord` | Official voting stats |

### Budget & Finance

| Method | Returns |
|--------|---------|
| `budget(department, fund, fiscal_year)` | `List[BudgetItem]` |
| `budget_summary(fiscal_year, group_by)` | `List[BudgetSummary]` |
| `funding_flow(program, cfda_number)` | `List[FundingFlow]` |
| `funding_flow_impact(program, cut_percentage)` | `FundingFlowImpact` |
| `federal_expenditures(cfda_number, audit_year)` | `List[FederalExpenditure]` |
| `intergovernmental_revenue(fiscal_year, source)` | `IntergovernmentalRevenueSummary` |

### AI

| Method | Returns |
|--------|---------|
| `draft_action(action_type, topic, description)` | `ActionDraft` |

## Architecture

```
CivicOS (dataclass)
  ├── storage: StorageBackend    # SQL data access
  ├── _vectors: VectorBackend    # Semantic search
  ├── _data_source: DataSource   # Query abstraction
  └── _search: LegalSearch       # Regulatory context
```

### Storage Backends

Two implementations of the `StorageBackend` protocol:

- **`PostgresBackend`** — Production (Supabase). Selected when `DATABASE_URL` is set.
- **`SQLiteBackend`** — Local dev. Selected when `DATABASE_URL` is not set.

The protocol is composed of sub-protocols: `ContentStorage`, `LegislationStorage`, `FinancialStorage`, `CommunityStorage`, `ElectionStorage`, `OperationsStorage`.

### Vector Backends

- **`PgVectorBackend`** — Production (pgvector on Supabase).
- **ChromaDB** — Local dev fallback.

## Exports

The package exports all result types, storage backends, diagnostics utilities, configuration, and path resolution. See `packages/civicos/src/civicos/__init__.py` for the full list.
