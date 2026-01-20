# Vector Indexing Operations

## Overview

Vector embeddings enable semantic search across civic documents. We use **Modal** for compute-intensive embedding generation, solving memory constraints of standard CI runners.

## Architecture

```
Trigger (manual/scheduled)
    │
    ▼
Modal (16GB RAM)
    │ fastembed + nomic-embed-text-v1.5
    ▼
Postgres + pgvector (Neon)
    │
    ▼
Civic API (search)
```

## Why Modal?

| Runner | RAM | Result |
|--------|-----|--------|
| GitHub Actions | 7GB | OOM on large corpus (5K+ docs) |
| Modal | 16GB+ | Handles full corpus reliably |

Modal provides:
- Configurable memory (up to 256GB)
- Per-second billing (~$0.10 for full index)
- Cached container images (fast subsequent runs)
- Scheduled execution support

## Corpus Sizes

| Corpus | Documents | Notes |
|--------|-----------|-------|
| chunks | 5,084 | Meeting content chunks |
| municipal_code | 2,366 | City code sections |
| issues | 1,330 | SeeClickFix reports |
| meetings | 46 | Meeting metadata |
| decisions | 44 | Council decisions |
| transcripts | 13 | Video transcripts (when available) |
| **Total** | **8,839** | |

## Usage

```bash
# Check current index status
modal run scripts/modal_vectors.py --stats-only

# Full refresh (all corpus types)
modal run scripts/modal_vectors.py

# Single corpus type
modal run scripts/modal_vectors.py --corpus chunks

# Force reindex (delete existing vectors first)
modal run scripts/modal_vectors.py --reindex
```

## Scheduled Refresh

Modal runs weekly refresh automatically (Sunday 6 AM UTC) via `scheduled_refresh()` function in `scripts/modal_vectors.py`.

## Secrets Required

| Secret | Contents | Created via |
|--------|----------|-------------|
| `civic-db` | DATABASE_URL | `modal secret create civic-db DATABASE_URL="..."` |
| `civic-github` | GITHUB_TOKEN | `modal secret create civic-github GITHUB_TOKEN="$(gh auth token)"` |

## Fallback: GitHub Actions

For small corpus types or if Modal is unavailable, `.github/workflows/vector-refresh.yml` provides a GitHub Actions fallback. It works for corpus types under ~2K docs.

## Embedding Model

- **Provider:** fastembed (ONNX runtime)
- **Model:** nomic-ai/nomic-embed-text-v1.5
- **Dimensions:** 768
- **Cost:** $0 (local inference)

## Monitoring

Check index coverage:
```bash
source civicos-env/bin/activate && source .env
civic-extract vectors --jurisdiction city-san-rafael --corpus all --stats
```
