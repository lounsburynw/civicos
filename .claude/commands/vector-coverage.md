# Vector Coverage

Analyze vector embedding coverage across corpus types. Shows which corpora need indexing.

## Usage

```
/vector-coverage [jurisdiction] [options]
```

**Arguments:**
- `jurisdiction` - Target jurisdiction (default: city-san-rafael)

**Options:**
- `--total` - Show only total summary
- `--low` - Show only corpora with <90% coverage

## Examples

```
/vector-coverage                       # Coverage for city-san-rafael
/vector-coverage city-san-rafael       # Explicit jurisdiction
/vector-coverage --total               # Just totals
/vector-coverage --low                 # Corpora needing attention
```

## What This Shows

| Column | Description |
|--------|-------------|
| **Corpus** | Data type |
| **Docs** | Documents in storage |
| **Indexed** | Vector embeddings |
| **Coverage** | Percent (>100% means expanded) |
| **Status** | complete/good/partial/low/unknown |

### Status Levels

| Status | Coverage | Meaning |
|--------|----------|---------|
| complete | >= 99% | Fully indexed |
| good | 90-99% | Nearly complete |
| partial | 50-90% | Needs attention |
| low | < 50% | Priority for indexing |
| unknown | N/A | Unable to calculate |

## Steps

### 1. Show All Coverage (Default)

```bash
source civic-env/bin/activate && python3 -c "
from dotenv import load_dotenv
load_dotenv()

from civic import Civic, VectorCoverage, format_vector_coverage

jurisdiction = '$1' if '$1' else 'city-san-rafael'
c = Civic(jurisdiction)

coverage = VectorCoverage(c._storage, c._vectors, jurisdiction)
print(f'Vector Coverage: {jurisdiction}')
print()
print(format_vector_coverage(coverage.by_corpus()))
"
```

### 2. Show Total Summary

```bash
source civic-env/bin/activate && python3 -c "
from dotenv import load_dotenv
load_dotenv()

from civic import Civic, VectorCoverage

jurisdiction = '$1' if '$1' else 'city-san-rafael'
c = Civic(jurisdiction)

coverage = VectorCoverage(c._storage, c._vectors, jurisdiction)
totals = coverage.total()

print(f'Vector Coverage Summary: {jurisdiction}')
print()
print(f'Total storage docs:  {totals[\"total_storage\"]:>10}')
print(f'Total vector docs:   {totals[\"total_vector\"]:>10}')
print(f'Total gap:           {totals[\"total_gap\"]:>10}')
coverage_pct = f'{totals[\"coverage_percent\"]:.1f}%' if totals['coverage_percent'] else 'N/A'
print(f'Overall coverage:    {coverage_pct:>10}')
print(f'Corpus types:        {totals[\"corpus_count\"]:>10}')
"
```

### 3. Show Low Coverage Only

```bash
source civic-env/bin/activate && python3 -c "
from dotenv import load_dotenv
load_dotenv()

from civic import Civic, VectorCoverage

jurisdiction = '$1' if '$1' else 'city-san-rafael'
c = Civic(jurisdiction)

coverage = VectorCoverage(c._storage, c._vectors, jurisdiction)
by_corpus = coverage.by_corpus()

# Filter to corpora with positive gaps (need indexing)
needs_indexing = [
    c for c in by_corpus
    if c['storage_count'] > c['vector_count'] and c['storage_count'] > 0
]

if needs_indexing:
    print(f'Corpora needing indexing: {jurisdiction}')
    print()
    print(f'{\"Corpus\":<20} {\"Docs\":>8} {\"Indexed\":>10} {\"Gap\":>8}')
    print('-' * 50)
    for item in needs_indexing:
        gap = item['storage_count'] - item['vector_count']
        print(f'{item[\"display_name\"]:<20} {item[\"storage_count\"]:>8} {item[\"vector_count\"]:>10} {gap:>8}')
else:
    print('All corpora are fully indexed!')
"
```

## Understanding Coverage > 100%

Some corpus types expand documents into multiple embeddings:

| Corpus | Why > 100% |
|--------|------------|
| Transcripts | 1 transcript -> N speaker turns |
| Municipal Code | 1 section -> M text chunks |
| Legislation | 1 bill -> K sections |

This is **expected behavior** for semantic search quality.

## Related Commands

| Command | Purpose |
|---------|---------|
| `/data-status` | Full data status with SQL counts |
| `/vectors reindex` | Trigger vector re-indexing |
| `/checkpoint` | View ingestion progress |
