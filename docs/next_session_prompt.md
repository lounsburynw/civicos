# Recommended: Research Infrastructure Abstraction

**Priority:** P0 (IMMEDIATE)
**Area:** data_readiness > municipal_context > research_abstraction
**Date:** 2025-12-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 355 completed `san_rafael_municipal_funding` - built modular research infrastructure with Perplexity ensemble (16 queries, 82 citations), indexed 4 municipal programs to ChromaDB. Also added `build_municipal_programs_index()` and `search_municipal_programs()` methods.

**The problem:** The research infrastructure has housing-specific logic tightly coupled with generic orchestration. This makes extending to other document types (transportation, environment, county programs) require duplicating code.

## Current Coupling Points

1. **`MunicipalFundingResearcher`** (funding.py:111-1068):
   - `TOPIC_CONTEXT` dict with hardcoded topics (lines 136-149)
   - `_build_prompt()` with housing-specific structured format (lines 595-703)
   - `_extract_programs_from_prose()` with hardcoded patterns (lines 487-518)
   - Parsing logic for housing fields (in_lieu_fee, inclusionary, etc.)

2. **`query_templates.py`** - Only has `HOUSING_QUERY_TEMPLATES` (lines 38-96)

3. **`schemas.py`** - Schemas like `FundingProgram`, `BallotMeasure` are housing-specific

## Proposed Architecture

```
packages/civic-extraction/src/civic_extraction/research/
├── providers/              # Already abstract (keep as-is)
│   ├── base.py            # SearchProvider protocol
│   └── perplexity.py      # Perplexity implementation
├── core/                  # NEW: Common orchestration
│   ├── researcher.py      # BaseResearcher with ensemble/audit/rate-limiting
│   ├── indexer.py         # Generic indexing to ChromaDB
│   └── schemas.py         # Base schema classes
├── topics/                # Topic-specific implementations
│   ├── housing/
│   │   ├── schemas.py     # FundingProgram, BallotMeasure
│   │   ├── templates.py   # HOUSING_QUERY_TEMPLATES
│   │   ├── prompts.py     # Housing-specific prompt builder
│   │   └── researcher.py  # HousingFundingResearcher(BaseResearcher)
│   └── transportation/    # Future topic
│       └── ...
└── municipal/             # Keep for backward compatibility, delegate to topics/
```

## BaseResearcher Design

```python
class BaseResearcher(ABC):
    """Abstract base for topic-specific researchers."""

    def __init__(self, provider: SearchProvider, data_dir: str):
        self._provider = provider
        self._data_dir = Path(data_dir)

    # Common orchestration (already implemented in MunicipalFundingResearcher)
    def research_ensemble(self, entity: str, location: str, **kwargs) -> EnsembleResult:
        """Run ensemble research with rate limiting and audit."""
        queries = self._build_queries(entity, location, **kwargs)
        results = self._execute_queries(queries)
        return self._merge_results(results)

    def _execute_queries(self, queries) -> list[QueryResult]:
        """Execute with ThreadPoolExecutor and rate limiting."""
        ...  # Extract from current implementation

    def _save_audit(self, result) -> str:
        """Save audit trail to disk."""
        ...  # Extract from current implementation

    # Topic-specific (must be implemented by subclasses)
    @abstractmethod
    def _build_queries(self, entity: str, location: str, **kwargs) -> list[Query]:
        """Build topic-specific queries."""
        ...

    @abstractmethod
    def _merge_results(self, results: list[QueryResult]) -> MergedResult:
        """Merge and dedupe results into topic-specific schema."""
        ...

    @abstractmethod
    def _get_output_schema(self) -> type[BaseModel]:
        """Return the Pydantic model for output."""
        ...
```

## Generic Indexer Design

```python
class ResearchIndexer:
    """Generic indexer for research output."""

    def __init__(self, embeddings: CivicEmbeddings):
        self._embeddings = embeddings

    def index_programs(
        self,
        programs_file: Path,
        collection_name: str,
        text_builder: Callable[[dict], str],  # Topic-specific text extraction
        metadata_builder: Callable[[dict], dict],  # Topic-specific metadata
    ) -> Collection:
        """Index programs to ChromaDB with configurable text/metadata builders."""
        ...
```

## Implementation Steps

1. **Create `core/researcher.py`**
   - Extract common methods from `MunicipalFundingResearcher`
   - `_execute_queries()`, `_save_audit()`, `_save_ensemble_audit()`
   - Rate limiting, ThreadPoolExecutor orchestration

2. **Create `core/indexer.py`**
   - Extract common pattern from `build_municipal_programs_index()`
   - Parameterize text_builder and metadata_builder

3. **Create `topics/housing/` structure**
   - Move `schemas.py` content
   - Move `query_templates.py` content
   - Create `HousingFundingResearcher(BaseResearcher)`

4. **Update `municipal/funding.py`**
   - Make it delegate to `HousingFundingResearcher`
   - Maintain backward compatibility

5. **Update CLI**
   - `civic-extract research <topic> <entity> <location>`

## Key Files

```
packages/civic-extraction/src/civic_extraction/research/municipal/funding.py      # Current implementation
packages/civic-extraction/src/civic_extraction/research/municipal/query_templates.py
packages/civic-extraction/src/civic_extraction/research/municipal/schemas.py
packages/civic-extraction/src/civic_extraction/research/providers/base.py          # Good pattern
packages/civic/src/civic/_internal/meetings/embeddings.py:1964-2176                # Municipal indexing
```

## Success Criteria

- [ ] `core/researcher.py` with `BaseResearcher` abstract class
- [ ] `core/indexer.py` with generic `ResearchIndexer`
- [ ] `topics/housing/` with housing-specific implementation
- [ ] Existing CLI `civic-extract research municipal-funding` still works
- [ ] Tests pass for both old and new interfaces
- [ ] Adding a new topic only requires creating a new `topics/<topic>/` folder

## Benefits

1. **Extensibility** - Add transportation, environment, county research without code duplication
2. **Testability** - Test orchestration separately from topic-specific logic
3. **Maintainability** - Changes to rate limiting or audit don't require touching topic code
4. **Consistency** - All topics follow same patterns for queries, parsing, indexing

## Pilot Progress

- 162/174 items ready (93.1%)
- 12 items remaining
- P0: research_abstraction (this item)
