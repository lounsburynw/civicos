# ADR: Entity ID Namespacing

**Status:** Accepted
**Date:** 2026-01-29
**Context:** Federation readiness for multi-city deployment

## Decision

All entity IDs in CivicOS will follow a namespaced format:

```
{entity_type}:{jurisdiction_id}:{source}:{identifier}
```

This ensures global uniqueness when multiple cities join the federation.

## Format Specification

### Components

| Component | Description | Examples |
|-----------|-------------|----------|
| `entity_type` | Type of entity | `meeting`, `decision`, `chunk`, `issue`, `bill`, `transcript` |
| `jurisdiction_id` | CivicOS jurisdiction | `city-san-rafael`, `city-berkeley`, `state-california`, `federal` |
| `source` | Platform or date context | `legistar`, `proudcity`, `simbli`, `seeclickfix`, `2026-01-15` |
| `identifier` | Platform-specific or local ID | `12345`, `council`, `item-6a` |

### Entity ID Formats

| Entity | Format | Example |
|--------|--------|---------|
| Meeting | `meeting:{jurisdiction}:{platform}:{platform_id}` | `meeting:city-san-rafael:legistar:12345` |
| Decision | `decision:{jurisdiction}:{date}:{item}` | `decision:city-san-rafael:2026-01-15:item-6a` |
| Chunk | `chunk:{jurisdiction}:{meeting_id}:{index}` | `chunk:city-san-rafael:meeting-legistar-12345:001` |
| Issue | `issue:{jurisdiction}:{provider}:{external_id}` | `issue:city-san-rafael:seeclickfix:12345678` |
| Bill | `bill:{jurisdiction}:{bill_type}{number}` | `bill:state-california:sb-1234` |
| Transcript | `transcript:{jurisdiction}:{video_id}` | `transcript:city-san-rafael:dQw4w9WgXcQ` |

### Jurisdiction ID Format

Jurisdictions use a prefixed format to indicate scope:

- `city-{name}` - Municipal (e.g., `city-san-rafael`, `city-berkeley`)
- `county-{name}` - County (e.g., `county-marin`)
- `state-{code}` - State (e.g., `state-california`)
- `federal` - Federal government

## Migration Strategy

### Phase 1: New Records (Pilot - Jan 2026)

All new records ingested from this point forward use namespaced IDs.

### Phase 2: Backwards Compatibility

The storage layer accepts both old and new formats transparently:

```python
# Storage layer resolves both formats
def resolve_entity_id(raw_id: str, jurisdiction_id: str, entity_type: str) -> str:
    """Resolve both legacy and namespaced ID formats."""
    if ":" in raw_id and raw_id.count(":") >= 2:
        # Already namespaced
        return raw_id
    # Legacy format - return as-is (still works in queries)
    return raw_id
```

### Phase 3: Migration Script (Post-Pilot)

After Jan 2026 launch validation, run a one-time migration to update existing records:

```sql
-- Example: Update legacy meeting IDs
UPDATE meetings
SET id = 'meeting:' || jurisdiction_id || ':' ||
         CASE
           WHEN id LIKE 'legistar-%' THEN REPLACE(id, 'legistar-' || SPLIT_PART(id, '-', 2) || '-', 'legistar:')
           WHEN id LIKE 'proudcity-%' THEN REPLACE(id, 'proudcity-' || jurisdiction_id || '-', 'proudcity:')
           ELSE id
         END
WHERE id NOT LIKE '%:%:%';
```

## Rationale

### Why Now?

1. **Federation readiness** - Second city joining would cause ID collisions without namespacing
2. **Low risk** - TEXT columns accept any format, no schema changes needed
3. **High value** - Prevents painful migration later
4. **Pilot timing** - New data gets namespaced, existing data migrated post-launch

### Alternatives Considered

1. **UUID for all IDs** - Rejected: Loses semantic meaning, harder to debug
2. **Jurisdiction prefix only** - Rejected: Doesn't distinguish entity types
3. **Database-level constraints** - Rejected: Adds complexity, hard to migrate

## Implementation Locations

| Component | File | Change |
|-----------|------|--------|
| Legistar meetings | `civicos-extraction/clients/legistar.py:400` | ID generation |
| ProudCity meetings | `civicos-extraction/clients/proudcity.py:851` | ID generation |
| Simbli meetings | `civicos-extraction/clients/simbli.py:584,684` | ID generation |
| Issues | `civicos/issues/provider.py:67` | ID property |
| Decisions | `civicos/_internal/meetings/decision.py:568` | ID generation |
| Chunks | `civicos/storage/postgres_backend.py:2633` | Fallback ID generation |
| Transcripts | Already uses UUID + video_id | No change needed |

## Verification

```python
# Test namespaced ID format
from civicos import CivicOS

c = CivicOS('city-san-rafael')

# New meetings should have namespaced IDs
meetings = c._storage.get_meetings('city-san-rafael', limit=5)
for m in meetings:
    # Should match: meeting:city-san-rafael:{platform}:{id}
    assert ':' in m['id'], f"Meeting ID not namespaced: {m['id']}"
```

## References

- pilot.json item: `entity_id_namespacing`
- Coordination Protocol: `docs/critical/COORDINATION_PROTOCOL.md`
- civicos-relay: `packages/civicos-relay/src/civicos_relay/sync/protocol.py`
