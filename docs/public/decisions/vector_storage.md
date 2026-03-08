# Vector Storage

**Status**: pgvector on Supabase PostgreSQL (production), ChromaDB (local development)

## Production: pgvector

Vector embeddings live in the same Supabase PostgreSQL instance as relational data, using the `pgvector` extension.

- **~16,786 embeddings** across transcripts, chunks, municipal code, issues, decisions, meetings
- **Embedding model**: `nomic-ai/nomic-embed-text-v1.5` (768 dimensions, 8192 token context)
- **Backend**: `PgVectorBackend` (implements `VectorBackend` protocol)
- **Backups**: Managed by Supabase (automatic daily backups, point-in-time recovery)

Vectors and relational data in one database means semantic search queries can join against meetings, decisions, etc. without cross-service calls.

## Local Development: ChromaDB

When `DATABASE_URL` is not set, CivicOS falls back to ChromaDB for a lightweight zero-dependency local experience.

- **Backend**: `ChromaBackend` (implements `VectorBackend` protocol)
- **Storage**: Local file-based (`data/` directory)

## Backend Selection

| Condition | Storage | Vectors |
|-----------|---------|---------|
| `DATABASE_URL` set | `PostgresBackend` | `PgVectorBackend` |
| No `DATABASE_URL` | `SQLiteBackend` | `ChromaBackend` |

The `VectorBackend` protocol (`packages/civicos/src/civicos/storage/vector.py`) abstracts over both backends, so application code is storage-agnostic.

## References

- [Supabase pgvector docs](https://supabase.com/docs/guides/database/extensions/pgvector)
- VectorBackend protocol: `packages/civicos/src/civicos/storage/vector.py`
