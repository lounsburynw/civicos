# Testing Strategy

This document describes the Civic platform's tiered testing strategy, designed to balance CI speed with comprehensive coverage.

## Test Tiers

| Tier | When | What Runs | Target Time |
|------|------|-----------|-------------|
| **Smoke** | Every push | Core API, imports, basic functionality | ~30s |
| **CI (Full)** | Every push | Synthetic data + fixture-based tests | ~5min |
| **Local** | Developer discretion | All tests including real data | ~15min |
| **Scheduled** | Weekly (future) | Heavy data tests, performance benchmarks | ~1hr |

## Markers Reference

### `@pytest.mark.requires_real_data`

Tests that depend on gitignored data files (PDFs, JSON extracts, transcripts).

```python
@pytest.mark.requires_real_data
class TestSanRafaelRAGExtraction:
    """Needs data/pilot/rag_corpus/city-san-rafael/*.json"""
    ...
```

**Behavior:**
- Automatically skipped when `CI=true` or `GITHUB_ACTIONS=true`
- Runs normally in local development
- Implemented via `pytest_collection_modifyitems` hook in `conftest.py`

**When to use:**
- Test reads from `data/pilot/rag_corpus/`
- Test reads from `data/civic_state.db`
- Test needs real PDFs, transcripts, or extracted JSON

### `@pytest.mark.integration`

Integration tests that test multiple components together.

```python
@pytest.mark.integration
class TestWhatHappenedIntegration:
    ...
```

### `@pytest.mark.rag`

Tests involving RAG infrastructure (embeddings, vector search).

```python
@pytest.mark.rag
class TestEmbeddingGeneration:
    ...
```

### `@pytest.mark.slow` (future)

Performance and load tests that take significant time.

```python
@pytest.mark.slow
class TestLoadPerformance:
    ...
```

## Skip Decorators

### Infrastructure Availability

```python
# Skip if database tables don't exist
@skip_without_db_tables
class TestRestApiE2E:
    ...

# Skip if npm/node_modules not available
@skip_without_frontend
class TestFrontendBrowserE2E:
    ...

# Skip if API server module can't be imported
@skip_without_server
class TestRestApiE2E:
    ...
```

## Test File Organization

```
packages/civic/tests/
├── conftest.py                      # Shared fixtures, marker hooks
├── test_civic.py                    # Core API smoke tests (always run)
├── test_mcp.py                      # MCP server tests
├── test_e2e_verification.py         # E2E tests (skip conditions)
├── test_integration_san_rafael.py   # San Rafael integration (requires_real_data)
└── test_integration_rag_san_rafael.py  # RAG tests (mixed synthetic/real)
```

## Running Tests

### Local Development

```bash
# Smoke tests only (quick validation)
pytest packages/civic/tests/test_civic.py -q

# All tests (including requires_real_data)
pytest packages/civic/tests/ -v

# Specific test file
pytest packages/civic/tests/test_integration_rag_san_rafael.py -v

# Skip slow tests
pytest packages/civic/tests/ -m "not slow"
```

### Simulating CI Environment

```bash
# Run as if in CI (skips requires_real_data tests)
CI=true pytest packages/civic/tests/ -v

# See what would be skipped
CI=true pytest packages/civic/tests/ --collect-only | grep "skip"
```

### CI Configuration

Tests run via GitHub Actions (`.github/workflows/tests.yml`):

```yaml
# Parallelized across 8 runners
jobs:
  test:
    strategy:
      matrix:
        group: [1, 2, 3, 4, 5, 6, 7, 8]
    steps:
      - run: pytest --splits 8 --group ${{ matrix.group }}
```

## Adding New Tests

### For CI-Compatible Tests

1. Use synthetic data or create test data in fixtures:

```python
def test_search_returns_results(self, tmp_path):
    # Create synthetic test data
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    decisions = [{"id": "d1", "title": "Test Decision", ...}]
    (corpus_dir / "decisions.json").write_text(json.dumps(decisions))

    # Test with synthetic data
    embedder = CivicEmbeddings(persist_directory=str(tmp_path / "vectors"))
    embedder.build_index(corpus_dir)
    results = embedder.search("test")
    assert len(results) > 0
```

2. Use provided fixtures for isolation:

```python
def test_with_isolated_db(self, isolated_db_path):
    civic = Civic("test", db_path=isolated_db_path)
    ...

def test_with_isolated_vectors(self, isolated_chroma_config):
    embedder = CivicEmbeddings(
        persist_directory=isolated_chroma_config["persist_directory"],
        collection_suffix=isolated_chroma_config["collection_suffix"],
    )
    ...
```

### For Tests Requiring Real Data

1. Add the marker:

```python
@pytest.mark.requires_real_data
class TestWithRealCorpus:
    """Tests that need actual San Rafael data."""
    ...
```

2. Document the data dependency:

```python
@pytest.mark.requires_real_data
class TestStaffReportExtraction:
    """
    Tests staff report extraction from real agenda packets.

    Requires: data/pilot/rag_corpus/city-san-rafael/item_6a_staff_report.json
    Generate with: python scripts/extract_staff_report.py
    """
```

## Fixture Reference

### Session-Scoped (Shared Across Workers)

```python
# Pre-loaded SentenceTransformer model
def test_embeddings(sentence_transformer_model):
    embeddings = sentence_transformer_model.encode(["test"])
    ...

# Pre-initialized embedding provider
def test_search(embedding_provider_cached):
    results = embedding_provider_cached.search("test")
    ...
```

### Test-Scoped (Isolated Per Test)

```python
# Isolated SQLite database
def test_state(isolated_db_path):
    state = StateManager(isolated_db_path)
    ...

# Isolated ChromaDB directory
def test_vectors(isolated_vector_dir):
    embedder = CivicEmbeddings(persist_directory=isolated_vector_dir)
    ...

# Complete isolation config
def test_full_isolation(isolated_chroma_config):
    embedder = CivicEmbeddings(
        persist_directory=isolated_chroma_config["persist_directory"],
        collection_suffix=isolated_chroma_config["collection_suffix"],
    )
    ...
```

## Known Issues

### Tests Skipped Due to Bugs

Two MCP tests are skipped due to test setup bugs (not data issues):

1. `test_prepare_tool_returns_preparation` - Jurisdiction mapping bug ("default" vs "city-default")
2. `test_suggestion_workflow_with_data` - Suggestion generation returns empty results

These should be fixed, not just skipped.

### Synthetic Fixture Issues

Some tests converted to synthetic data have fixture bugs:

- `TestIndexQueryLatency` - ChromaDB collection naming mismatch
- `TestCrossMeetingPatterns` - Fixture not creating data correctly
- `TestWhatWasSaidTranscripts` - Returns empty results

These are currently marked `requires_real_data` but should be fixed to use synthetic data.

## Future Work

### Synthetic Test Fixtures (pilot.json: synthetic_test_fixtures)

Create a minimal, committed test corpus:

```
tests/fixtures/
├── sample_decisions.json      # 5-10 representative decisions
├── sample_chunks.json         # ~50 text chunks
├── sample_minutes.json        # 1 meeting minutes
└── sample_testimony.json      # A few testimony entries
```

### Scheduled Heavy Data Tests (pilot.json: scheduled_data_tests)

Weekly CI workflow for full corpus tests:

```yaml
# .github/workflows/data-tests.yml
on:
  schedule:
    - cron: '0 3 * * 0'  # Weekly Sunday 3am
  workflow_dispatch:      # Manual trigger
```

## Evaluation Framework (Quality Benchmarks)

Separate from unit tests, the evaluation framework measures API quality metrics.

### Benchmark Script

```bash
# Location
scripts/benchmark_api_vs_llm.py

# Basic run (keyword-based precision)
python scripts/benchmark_api_vs_llm.py

# With LLM-as-judge (recommended for accurate evaluation)
python scripts/benchmark_api_vs_llm.py --llm-judge

# Output as JSON for tracking
python scripts/benchmark_api_vs_llm.py --llm-judge --json > results.json
```

### What It Measures

| Metric | Description |
|--------|-------------|
| **Accuracy** | Results have valid structure and reasonable dates |
| **Precision** | Relevance of returned results to query |
| **Recall** | Completeness (retrieved vs total relevant) |
| **F1 Score** | Harmonic mean of precision and recall |
| **Coverage** | Query, topic, category, and data coverage |
| **Bias** | Topic, method, temporal, and geographic bias |

### LLM-as-Judge Mode

The `--llm-judge` flag enables semantic relevance scoring via LLM (instead of keyword matching):

```bash
python scripts/benchmark_api_vs_llm.py --llm-judge
```

- **Cost:** ~$0.001-0.01 per run (gemini-2.0-flash-exp default)
- **Caching:** Results cached to minimize repeated costs
- **Clear cache:** `--clear-cache` flag

### When to Use

- **Unit tests (pytest):** Verify code correctness, run on every commit
- **Evaluation framework:** Measure retrieval quality, run periodically or after major changes

See the script's docstring for detailed documentation on metrics, ground truth, and adding new queries.

## Troubleshooting

### "Collection does not exist" errors

Usually means the fixture didn't properly create the ChromaDB collection. Check:
1. Is the persist_directory correct?
2. Did `build_index()` complete successfully?
3. Is the collection name matching what the search expects?

### Tests pass locally but fail in CI

1. Check if test uses real data - add `@pytest.mark.requires_real_data`
2. Check if test uses hardcoded paths - use `tmp_path` fixture instead
3. Check if test assumes certain environment - use environment checks

### Parallel execution failures

1. Tests using shared resources? Use `isolated_*` fixtures
2. Collection name conflicts? Use `collection_suffix` fixture
3. Database conflicts? Use `isolated_db_path` fixture
