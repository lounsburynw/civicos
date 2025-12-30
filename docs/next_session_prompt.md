# Recommended: vectors_e2e_cloud (Remote Embedding Support)

**Priority:** P0
**Area:** pilot_validation > e2e_cloud_data_verification
**Date:** 2025-12-29

> This is recommended context from Session 405. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 405 identified that local `sentence-transformers` embedding is not portable for production ETL:
- Requires ML environment (sentence-transformers, torch) everywhere it runs
- Can't run in lightweight CI/CD, GitHub Actions, or serverless
- Need remote embedding API support for portable refresh pipelines

## Current State

**Vector stats (San Rafael):**
| Corpus | To Index | Status |
|--------|----------|--------|
| chunks | 5,040 | 0.9% coverage |
| municipal_code | 2,366 | 0% |
| issues | 1,330 | 0% |
| meetings | 46 | 0% |
| decisions | 44 | 0% |
| transcripts | 13 | 0% |
| **Total** | **8,839** | |

**Current embedding model:** `nomic-ai/nomic-embed-text-v1.5` (768 dims, local)

## Task

Add configurable embedding provider support to `civic-extract vectors` CLI:

```bash
# Local (default, for dev)
civic-extract vectors --jurisdiction city-san-rafael --corpus all

# Remote (for production/CI)
civic-extract vectors --jurisdiction city-san-rafael --corpus all --provider openai
civic-extract vectors --jurisdiction city-san-rafael --corpus all --provider voyage
```

## Key Files

| File | Purpose |
|------|---------|
| `packages/civic-extraction/src/civic_extraction/cli/vectors.py` | Add `--provider` flag |
| `packages/civic/src/civic/storage/pgvector_backend.py` | Abstract embedding generation |
| `packages/civic/src/civic/embeddings/` | May need new provider abstraction |

## Suggested Approach

### 1. Use Hosted Open-Source Models (Preferred)

Keep using `nomic-embed-text-v1.5` but run it remotely for portability:

| Provider | Model | Cost | Notes |
|----------|-------|------|-------|
| **Hugging Face Inference API** | nomic-ai/nomic-embed-text-v1.5 | Free tier, then ~$0.06/1M chars | Same model, hosted |
| **Together AI** | togethercomputer/m2-bert-80M-8k-retrieval | ~$0.008/1M tokens | Fast, cheap |
| **Modal** | Any sentence-transformers | ~$0.10/hr GPU | Serverless, flexible |

**Recommendation:** Hugging Face Inference API - same model, free tier, no dimension mismatch.

### 2. Abstract Embedding Provider

```python
class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...

class LocalEmbedding:
    """sentence-transformers locally (default for dev)"""
    def embed(self, texts):
        return self.model.encode(texts)

class HuggingFaceEmbedding:
    """Same nomic model via HF Inference API (portable)"""
    def embed(self, texts):
        response = requests.post(
            "https://api-inference.huggingface.co/models/nomic-ai/nomic-embed-text-v1.5",
            headers={"Authorization": f"Bearer {HF_TOKEN}"},
            json={"inputs": texts}
        )
        return response.json()
```

### 3. Update CLI

```python
parser.add_argument(
    "--provider",
    choices=["local", "huggingface", "together", "openai"],
    default="local",
    help="Embedding provider (default: local, use huggingface for CI/CD)"
)
```

### 4. Environment Variables

```bash
HF_TOKEN=hf_...            # For --provider huggingface (free tier available)
TOGETHER_API_KEY=...       # For --provider together
OPENAI_API_KEY=sk-...      # For --provider openai (fallback)
```

### 5. Cost Estimation

For ~9k documents at ~500 tokens avg:
- **Hugging Face (nomic)**: Free tier likely covers it, then ~$0.03
- **Together AI**: ~$0.04
- **Local**: $0 but not portable

All well within <$7/month constraint.

## Why Open-Source Remote is Better

1. **Same embeddings everywhere** - 768 dims, no mismatch between dev/prod
2. **No vendor lock-in** - model is open, just compute is hosted
3. **Consistent search quality** - identical results in CI vs local
4. **Future-proof** - can swap to newer open-source models easily

## Success Criteria

- [ ] `--provider` flag added to vectors CLI
- [ ] OpenAI embedding provider implemented
- [ ] Local remains default (no breaking change)
- [ ] All 8,839 docs indexed with remote provider
- [ ] Search works with new embeddings
- [ ] Mark `vectors_e2e_cloud` as ready

## After This

Once remote embedding works, the `data_refresh_strategy` item becomes unblocked - can document how to run vector refresh from GitHub Actions or cron.
