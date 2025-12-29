# Data Integrity Infrastructure

**Status:** Approved
**Date:** 2025-12-29
**Context:** Simulated adversarial scenarios for scaled platform

## Decision

Add content hashing and source provenance to all extracted records during pilot phase, before these become expensive to retrofit.

## Rationale

Simulations of platform at scale revealed attack vectors that require data integrity infrastructure:

1. **Transcript manipulation attacks**: Bad actors could serve modified transcripts. Defense: content hashes allow verification.

2. **Impersonation sites**: Fake sites serving altered data. Defense: signed/hashed data can be verified regardless of source.

3. **Legal disputes**: "That transcript is defamatory." Defense: provenance chain to source video.

4. **Federation requirements**: Future federation needs content-addressed data to prevent tampering across instances.

5. **Astroturfing detection**: Engagement history tracking enables distinguishing genuine civic participants from coordinated campaigns.

## Implementation

### Content Hashes

Add to all content tables:

- `content_hash`: SHA-256 of record content (utterances JSON, chunk text, decision JSON)
- Computed at ingest time, stored with record
- Immutable after creation

### Source Provenance

Add to extraction records:

- `audio_hash` / `pdf_hash`: SHA-256 of source file
- `source_url`: Where source was retrieved
- `source_retrieved_at`: When source was fetched (already exists on some tables)
- `extraction_version`: Version of extractor used

### Audit Trail

Add to all content tables:

- `deleted_at`: Soft delete timestamp (never hard delete)
- Future: `deleted_by`, `deletion_reason`

### Engagement Tracking Schema (Stub)

Create empty table for future population:

```sql
CREATE TABLE IF NOT EXISTS civic_engagement (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jurisdiction_id TEXT NOT NULL,
    engagement_type TEXT NOT NULL,  -- '311_report', 'meeting_testimony', 'thread_participation'
    external_id TEXT,               -- Reference to source record
    actor_hash TEXT,                -- Pseudonymous identifier (hashed email/address)
    engaged_at TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT now()
);
```

## Cost

- Schema additions: Trivial
- Hash computation: ~1ms per record
- Storage: ~64 bytes per hash field

## Migration Plan

1. Add columns to existing tables via migration script
2. Update ETL pipelines to compute hashes on ingest
3. New records get hashes immediately
4. Backfill existing records as time permits (not blocking)

## What NOT to Build Now

The simulations also showed things that would be premature:

| Feature                   | Why Wait                                 |
|---------------------------|------------------------------------------|
| Full identity/auth system | No users yet to authenticate             |
| Federation protocol       | Need canonical instance to succeed first |
| Access logging            | No access patterns to log yet            |
| Coordination threads      | Data layer isn't complete                |
| Opt-in discovery settings | No discovery feature yet                 |
| Moderation tools          | No content to moderate                   |

These all depend on having users and usage patterns. Build them when you have signal on what's actually needed.

## Alternatives Considered

1. **Build later**: Risk is retrofit cost and inconsistent data (some hashed, some not)
2. **External integrity system**: Complexity not justified at current scale
3. **Don't build**: Acceptable for pilot, problematic at scale

## Decision

Build during pilot phase. Low cost, high future value. Data integrity is the foundation everything else rests on.

## Related

- `pilot.json` → `data_integrity` section
- `migrations/015_data_integrity.sql` → Schema migration
- `docs/DATA_DICTIONARY.md` → Field documentation
