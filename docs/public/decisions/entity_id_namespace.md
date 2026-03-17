# ADR: Entity ID Namespacing

**Status:** Accepted
**Date:** 2026-01-29

## Decision

All entity IDs in CivicOS follow a namespaced format that encodes entity type, jurisdiction, source, and identifier:

```
{entity_type}:{jurisdiction_id}:{source}:{identifier}
```

This ensures global uniqueness when multiple jurisdictions join the federation.

## Context

CivicOS is designed for multi-city federation. Without namespaced IDs, a second city joining would cause collisions — two different meetings could share the same ID. Retrofitting ID schemes after data is in production is painful, so the namespacing was introduced during the pilot phase.

## Format Specification

### Components

| Component | Description | Examples |
|-----------|-------------|----------|
| `entity_type` | Type of entity | `meeting`, `decision`, `chunk`, `issue`, `bill`, `transcript` |
| `jurisdiction_id` | CivicOS jurisdiction | `city-san-rafael`, `city-berkeley`, `county-marin`, `state-california` |
| `source` | Platform or date context | `legistar`, `proudcity`, `simbli`, `seeclickfix`, `2026-01-15` |
| `identifier` | Platform-specific or local ID | `12345`, `council`, `item-6a` |

### Examples by Entity Type

| Entity | Format | Example |
|--------|--------|---------|
| Meeting | `meeting:{jurisdiction}:{platform}:{platform_id}` | `meeting:city-san-rafael:legistar:12345` |
| Decision | `decision:{jurisdiction}:{meeting_id}:{ordinal}` | `decision:city-san-rafael:proudcity-city-san-rafael-city-council-january-20-2026-tuesday:03` |
| Chunk | `chunk:{jurisdiction}:{meeting_id}:{index}` | `chunk:city-san-rafael:meeting-legistar-12345:001` |
| Issue | `issue:{jurisdiction}:{provider}:{external_id}` | `issue:city-san-rafael:seeclickfix:12345678` |
| Bill | `bill:{jurisdiction}:{bill_type}{number}` | `bill:state-california:sb-1234` |
| Transcript | `transcript:{jurisdiction}:{video_id}` | `transcript:city-san-rafael:dQw4w9WgXcQ` |

### Jurisdiction ID Format

Jurisdictions use a scope prefix:

- `city-{name}` — Municipal (e.g., `city-san-rafael`)
- `county-{name}` — County (e.g., `county-marin`)
- `state-{code}` — State (e.g., `state-california`)
- `federal` — Federal government

## Backwards Compatibility

The storage layer accepts both legacy (un-namespaced) and namespaced IDs transparently. New records are always created with namespaced IDs. Legacy records continue to work and can be migrated incrementally.

## Rationale

1. **Federation readiness** — Global uniqueness across jurisdictions without coordination
2. **Debuggability** — IDs are human-readable and encode context (vs. opaque UUIDs)
3. **Low risk** — TEXT columns accept any format, so no schema changes are needed
4. **Incremental adoption** — New data gets namespaced immediately; old data migrates later

### Alternatives Considered

1. **UUID for all IDs** — Rejected: Loses semantic meaning, harder to debug and trace
2. **Jurisdiction prefix only** (e.g., `city-san-rafael:12345`) — Rejected: Doesn't distinguish entity types, still risks collisions
3. **Database-level unique constraints** — Rejected: Adds migration complexity without solving the multi-instance problem

## References

- [Data Source Federation](data_source_federation.md) — How federated queries use namespaced IDs
- [Data Dictionary](../data-dictionary.md) — Field definitions for all entity types
