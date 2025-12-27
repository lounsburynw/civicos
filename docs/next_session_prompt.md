# Recommended: issues_cloud_storage

**Priority:** P0
**Area:** pipeline_automation > cloud_integration
**Date:** 2025-12-27

> This is recommended context from Session 384. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 384 completed `vector_indexing_cloud`. The user requested a proper 311 abstraction layer for future portability (PublicStuff, CitySourced, custom APIs) rather than a SeeClickFix-specific implementation.

## E2E Cloud ETL Roadmap (10 items)

| # | Item | Status | Data Flow |
|---|------|--------|-----------|
| 1 | `pipeline_cloud_storage` | Done | Meetings -> Postgres |
| 2 | `r2_source_caching` | Done | Cache HTML/PDFs in R2 |
| 3 | `youtube_cloud_storage` | Done | Video metadata -> Postgres |
| 4 | `audio_cloud_storage` | Done | Audio files -> R2 |
| 5 | `assemblyai_transcript_storage` | Done | Transcripts -> Postgres |
| 6 | `decision_extraction_pipeline` | Done | Agendas -> Decisions |
| 7 | `chunks_cloud_storage` | Done | PDF chunks -> Postgres |
| 8 | **`issues_cloud_storage`** | **P0** | 311 Issues -> Postgres |
| 9 | `vector_indexing_cloud` | Done | All data -> pgvector |
| 10 | `e2e_fresh_ingestion` | P1 | Full verification |

## Current State

**SeeClickFix is tightly coupled:**
- `seeclickfix_client.py` (423 lines) - provider-specific API wrapper
- `seeclickfix.py` CLI - stores to local JSON in `data/pilot/`
- No StorageBackend integration for issues

**Portable foundation exists:**
- `Issue` dataclass in `civic/_internal/state/models.py` - already generic
- `issue_matcher.py` - provider-agnostic matching logic

## Recommended Task

Create a portable 311 abstraction layer:

1. **IssueProvider protocol** - abstract interface for 311 providers
2. **NormalizedIssue dataclass** - provider-agnostic issue representation
3. **StorageBackend methods** - `store_issues()` / `get_issues()`
4. **Unified CLI** - `civic-extract issues --provider seeclickfix`
5. **SeeclickfixProvider** - refactor existing client as first implementation

## Suggested Architecture

```
packages/civic/src/civic/issues/
├── __init__.py
├── provider.py          # IssueProvider protocol + NormalizedIssue
└── providers/
    ├── __init__.py
    └── seeclickfix.py   # Refactored from civic-services

packages/civic-extraction/src/civic_extraction/cli/
└── issues.py            # Unified CLI with --provider flag
```

## Key Files

- `packages/civic-services/src/civic_services/clients/seeclickfix_client.py` - Existing client to refactor
- `packages/civic/src/civic/_internal/state/models.py:123-158` - Existing Issue dataclass
- `packages/civic/src/civic/storage/backend.py` - StorageBackend protocol (add issue methods)
- `packages/civic/src/civic/storage/postgres_backend.py:1225-1380` - Chunks pattern to follow

## Suggested Approach

### Step 1: Create IssueProvider Protocol
```python
# packages/civic/src/civic/issues/provider.py
@dataclass
class NormalizedIssue:
    provider: str           # "seeclickfix", "publicstuff", etc.
    external_id: str        # Provider's issue ID
    title: str
    description: str
    issue_type: str         # Normalized category
    status: str             # "open", "closed", "acknowledged"
    address: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    created_at: datetime
    updated_at: Optional[datetime]
    closed_at: Optional[datetime]
    reporter_name: Optional[str]
    images: List[str]
    provider_metadata: Dict[str, Any]  # Passthrough for provider-specific fields

class IssueProvider(Protocol):
    def get_issues(self, jurisdiction: str, **filters) -> List[NormalizedIssue]: ...
    def get_issue(self, issue_id: str) -> Optional[NormalizedIssue]: ...
    @property
    def provider_name(self) -> str: ...
```

### Step 2: Add StorageBackend Methods
```python
# Add to PostgresBackend
def store_issues(self, jurisdiction_id: str, issues: List[Dict], as_of=None) -> int
def get_issues(self, jurisdiction_id: str, provider=None, status=None, limit=None) -> List[Dict]
```

### Step 3: Create Issues Table
```sql
CREATE TABLE IF NOT EXISTS issues (
    id TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL,
    provider TEXT NOT NULL,           -- "seeclickfix", "publicstuff", etc.
    external_id TEXT,
    title TEXT,
    description TEXT,
    issue_type TEXT,
    status TEXT,
    address TEXT,
    latitude REAL,
    longitude REAL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    closed_at TIMESTAMP,
    reporter_name TEXT,
    images JSONB,
    provider_metadata JSONB,
    valid_from TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_to TIMESTAMP,
    UNIQUE(provider, external_id)     -- Prevent duplicates per provider
);
```

### Step 4: Create Unified CLI
```bash
civic-extract issues --provider seeclickfix --jurisdiction city-san-rafael --cloud
civic-extract issues --provider all --jurisdiction city-san-rafael  # Future: all providers
```

### Step 5: Refactor SeeclickfixProvider
Move normalization logic from `seeclickfix_client.py` to implement `IssueProvider` protocol.

## Tests to Run

```bash
# Storage protocol tests
pytest packages/civic/tests/test_storage_protocols.py -v

# Smoke tests
pytest packages/civic/tests/test_civic.py -q
```

## Success Criteria

- [ ] `IssueProvider` protocol defined with `NormalizedIssue` dataclass
- [ ] `store_issues()` / `get_issues()` added to StorageBackend
- [ ] Issues table with `provider` field and `(provider, external_id)` unique constraint
- [ ] `SeeclickfixProvider` implements `IssueProvider`
- [ ] `civic-extract issues --provider seeclickfix --cloud` works
- [ ] 1,340 existing issues migrated to Postgres
- [ ] Existing tests pass

## Why This Approach?

- **Portability**: Adding PublicStuff or CitySourced = new provider file + register
- **Single storage path**: All 311 data flows through same StorageBackend
- **Future-proof**: `provider` field enables multi-source queries
- **Minimal breaking changes**: Existing seeclickfix CLI can remain as deprecated alias
