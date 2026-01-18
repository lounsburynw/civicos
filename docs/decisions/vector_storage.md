# Vector Storage Decision

**Date**: 2025-12-26
**Status**: Decided
**Decision**: ChromaDB on Fly.io volume

## Context

Civic requires a vector database for semantic search over meeting transcripts, decisions, and municipal code. The production deployment must:

1. Stay under $7/month operational budget (foundation constraint)
2. Support ~13MB vector index (current San Rafael corpus)
3. Handle low-traffic queries (pilot phase)
4. Be deployable on Fly.io alongside the API server

## Current State

- **Implementation**: ChromaDB via `CivicEmbeddings` class (`packages/civic/src/civic/_internal/meetings/embeddings.py`)
- **Embedding model**: `nomic-ai/nomic-embed-text-v1.5` (768 dimensions, 8192 token context)
- **Index size**: ~13MB for San Rafael (city-san-rafael)
- **Protocol**: `VectorBackend` defined in `packages/civic/src/civic/storage/vector.py`

## Options Evaluated

### Option 1: ChromaDB on Fly.io Volume (RECOMMENDED)

**Description**: Self-host ChromaDB on Fly.io with a persistent volume.

**Pros**:
- Already fully implemented and tested
- No code changes required
- Simple deployment - just add volume mount
- Full control over data and uptime
- Scales to zero when idle

**Cons**:
- Must manage volume backups
- Single instance (no replication)

**Cost**:
- Volume: 3GB @ $0.15/GB/mo = **$0.45/month**
- Compute: Shared CPU (part of existing API server)

### Option 2: Qdrant Cloud Free Tier

**Description**: Use Qdrant's managed 1GB free tier.

**Pros**:
- Managed service, zero ops
- 1GB free forever (no credit card)
- High-performance purpose-built vector DB

**Cons**:
- Requires new backend implementation (`QdrantBackend`)
- Auto-suspends after 1 week of inactivity
- Auto-deletes after 4 weeks if not reactivated
- Different API from ChromaDB (migration work)
- External dependency for core functionality

**Cost**: $0/month (if within 1GB)

### Option 3: pgvector on Supabase/Neon Free Tier

**Description**: Use PostgreSQL with pgvector extension on a managed Postgres service.

**Pros**:
- Unified database (relational + vectors in one place)
- Standard PostgreSQL tools and ecosystem
- Free tiers available (Supabase 500MB, Neon 3GB)

**Cons**:
- `PgVectorBackend` is currently a stub (not implemented)
- Requires significant implementation work
- Would add external Postgres dependency
- Free tier limitations (Supabase: 500MB, Neon: shared compute)

**Cost**: $0/month (if within free tier limits)

## Decision

**ChromaDB on Fly.io volume** (Option 1)

### Rationale

1. **Already implemented**: ChromaDB integration is complete and tested. Zero development work.

2. **Budget compliant**: $0.45/month for 3GB volume is well under the $7/month budget.

3. **Simplest deployment**: Add volume mount to existing Fly.io app. No external dependencies.

4. **No migration risk**: Production uses the same stack as development.

5. **Future flexibility**: The `VectorBackend` protocol allows switching backends later if needed.

### Rejected Alternatives

- **Qdrant Cloud**: The auto-suspend/delete behavior is problematic for a civic tool that may have periods of low activity. The 4-week deletion risk is unacceptable for production data.

- **pgvector**: Requires implementing `PgVectorBackend` from scratch. The consolidation benefit doesn't outweigh the implementation risk for pilot launch.

## Implementation

### Fly.io Configuration

```toml
# fly.toml (add to existing app)
[mounts]
  source = "civic_vectors"
  destination = "/data/vectors"
```

```bash
# Create volume
fly volumes create civic_vectors --size 3 --region sjc
```

### Environment Variables

```bash
CIVICOS_VECTORS_DIR=/data/vectors
CIVICOS_EMBEDDING_MODEL=nomic-ai/nomic-embed-text-v1.5
```

### Backup Strategy

Weekly backup via Fly.io machine snapshot or export to R2 blob storage.

## Cost Summary

| Component | Monthly Cost |
|-----------|-------------|
| Vector storage (3GB volume) | $0.45 |
| Compute | Included in API server |
| **Total** | **$0.45/month** |

## Migration Path (Future)

If scale requirements change, the `VectorBackend` protocol supports alternative backends:

1. **Higher scale**: Implement `QdrantBackend` or use Qdrant paid tier
2. **Unified DB**: Implement `PgVectorBackend` for PostgreSQL consolidation
3. **Self-hosted cluster**: Deploy ChromaDB cluster for high availability

## References

- [Fly.io Pricing](https://fly.io/pricing/) - $0.15/GB/month for volumes
- [Qdrant Cloud Pricing](https://qdrant.tech/pricing/) - 1GB free tier with limitations
- [Supabase pgvector](https://supabase.com/docs/guides/database/extensions/pgvector) - Vector extension docs
- VectorBackend protocol: `packages/civic/src/civic/storage/vector.py`
- CivicEmbeddings: `packages/civic/src/civic/_internal/meetings/embeddings.py`
