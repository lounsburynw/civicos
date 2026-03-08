# ADR: Data Integrity Infrastructure

**Status:** Accepted
**Date:** 2025-12-29

## Decision

Add content hashing and source provenance to all extracted records, establishing a verifiable chain from source material to stored data.

## Context

CivicOS ingests civic data (transcripts, agendas, legislation) from government sources and makes it searchable. As the platform scales beyond a single jurisdiction, data integrity becomes critical for trust:

1. **Transcript verification** — Users and officials need assurance that transcripts haven't been altered after extraction
2. **Source provenance** — Legal and journalistic use cases require tracing data back to its original source
3. **Federation readiness** — Content-addressed data prevents tampering when records sync across instances
4. **Impersonation defense** — Hashed content can be verified regardless of where it's served from

## Design

### Content Hashes

All content records include a `content_hash` field:

- **Algorithm**: SHA-256 of the canonical record content
- **Computed at**: Ingest time
- **Immutable**: Never updated after creation

This covers transcripts (utterances JSON), agenda chunks (text), decisions (structured JSON), and other extracted content.

### Source Provenance

Extraction records track their origin:

| Field | Purpose |
|-------|---------|
| `audio_hash` / `pdf_hash` | SHA-256 of the source file |
| `source_url` | Where the source was retrieved |
| `source_retrieved_at` | When the source was fetched |
| `extraction_version` | Version of the extractor used |

### Soft Deletion

Records use `deleted_at` timestamps rather than hard deletes, preserving audit history.

## Rationale

### Why build this early?

- **Low cost** — Schema additions are trivial, hash computation is ~1ms per record
- **High retrofit cost** — Backfilling hashes for existing records is possible but loses provenance guarantees for the gap period
- **Foundation for trust** — Every downstream feature (federation, public APIs, legal citations) benefits from verifiable data

### Alternatives Considered

1. **Build later** — Risk: Inconsistent data (some hashed, some not) and expensive retrofit
2. **External integrity system** — Rejected: Adds complexity not justified at current scale
3. **Blockchain/merkle tree** — Rejected: Over-engineered for current needs; content hashes provide the same guarantees without the infrastructure

## References

- [Data Dictionary](../data-dictionary.md) — Field-level documentation for all schemas
