# ADR: Vector Storage

**Status:** Accepted
**Date:** 2025-12-01

## Decision

Use pgvector on Supabase PostgreSQL for production vector storage, with ChromaDB as a local development fallback. Both backends implement the `VectorBackend` protocol, keeping application code storage-agnostic.

## Context

CivicOS uses vector embeddings for semantic search across civic data — transcripts, agenda packets, municipal code, issues, decisions, and meetings. The storage backend needs to support both production workloads and lightweight local development.

## Architecture

### Production: pgvector

Vector embeddings live in the same PostgreSQL instance as relational data, using the `pgvector` extension.

- **Embedding model**: `nomic-ai/nomic-embed-text-v1.5` (768 dimensions, 8192 token context)
- **Backend**: `PgVectorBackend` (implements `VectorBackend` protocol)

Co-locating vectors and relational data means semantic search queries can join against meetings, decisions, etc. without cross-service calls.

### Local Development: ChromaDB

When `DATABASE_URL` is not set, CivicOS falls back to ChromaDB for a lightweight local experience.

- **Backend**: `ChromaBackend` (implements `VectorBackend` protocol)
- **Storage**: Local file-based

### Backend Selection

| Condition | Storage | Vectors |
|-----------|---------|---------|
| `DATABASE_URL` set | `PostgresBackend` | `PgVectorBackend` |
| No `DATABASE_URL` | `SQLiteBackend` | `ChromaBackend` |

## Rationale

### Why pgvector over a dedicated vector database?

1. **Operational simplicity** — One database to manage, backup, and monitor
2. **Relational joins** — Semantic search results can join against structured civic data in the same query
3. **Supabase integration** — Managed backups, point-in-time recovery, no additional infrastructure
4. **Cost** — No separate vector database service to pay for

### Alternatives Considered

1. **Pinecone / Weaviate / Qdrant** — Rejected: Adds operational complexity and cost for capabilities not yet needed
2. **ChromaDB in production** — Rejected: Not designed for multi-user production workloads
3. **pgvector on self-hosted Postgres** — Rejected: Supabase provides managed infrastructure at lower operational cost

## References

- [Supabase pgvector docs](https://supabase.com/docs/guides/database/extensions/pgvector)
- [nomic-embed-text-v1.5](https://huggingface.co/nomic-ai/nomic-embed-text-v1.5)
