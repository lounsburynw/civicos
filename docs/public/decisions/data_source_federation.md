# ADR: DataSource Protocol for Federation

**Status:** Accepted
**Date:** 2026-01-29
**Context:** Federation readiness for multi-city deployment

## Decision

Introduce a `DataSource` protocol that abstracts data access, enabling CivicOS to query data without knowing if it's local or from a federated city. For pilot, only `LocalDataSource` (wrapping `StorageBackend`) is implemented.

## Protocol Design

```python
@runtime_checkable
class DataSource(Protocol):
    """Read-only interface for civic data access (local or federated)."""

    @property
    def source_type(self) -> str:
        """Returns 'local', 'federated', or 'hybrid'"""
        ...

    def get_meetings(self, jurisdiction_id, since, until, limit) -> List[Dict]
    def get_decisions(self, jurisdiction_id, since, until, limit) -> List[Dict]
    def get_elections(self, jurisdiction_id, include_past, limit) -> List[Dict]
    def get_budget_items(self, jurisdiction_id, fiscal_year, department, limit) -> List[Dict]
    # ... additional query methods
```

### Key Design Choices

1. **Read-only interface**: DataSource handles queries only. Write operations (`store_*`, `update_*`, `delete_*`) stay on `StorageBackend` because only local data should be written.

2. **Dict-based returns**: Methods return `List[Dict]` or `Dict` for JSON serialization and cross-process compatibility (important for MCP relay).

3. **Simple parameters**: Query methods use basic types (str, datetime, int, bool) that can be serialized over MCP protocol.

## Implementation

### Pilot (Jan 2026)

`LocalDataSource` wraps `StorageBackend` with zero behavior change:

```python
class LocalDataSource:
    def __init__(self, storage: StorageBackend):
        self._storage = storage

    @property
    def source_type(self) -> str:
        return "local"

    def get_meetings(self, jurisdiction_id, since, until, limit):
        return self._storage.get_meetings(
            jurisdiction_id=jurisdiction_id,
            since=since,
            until=until,
            limit=limit,
        )
```

CivicOS uses `DataSource` through `_data_source` field:

```python
@dataclass
class CivicOS:
    _storage: StorageBackend = field(default=None)
    _data_source: DataSource = field(default=None)

    def __post_init__(self):
        self._storage = get_storage_backend(database_url)
        self._data_source = LocalDataSource(self._storage)

    def whats_next(self, topics=None, days=30):
        meetings = self._data_source.get_meetings(
            jurisdiction_id=self.jurisdiction,
            since=start_of_today,
            until=cutoff,
        )
        # ... rest of method unchanged
```

### Post-Pilot (Federation)

`FederatedDataSource` will use civicos-relay MCP protocol:

```python
class FederatedDataSource:
    def __init__(self, relay_urls: List[str]):
        self._relays = [MCPClient(url) for url in relay_urls]

    @property
    def source_type(self) -> str:
        return "federated"

    def get_meetings(self, jurisdiction_id, since, until, limit):
        # Fan-out query to relevant relay
        relay = self._get_relay_for_jurisdiction(jurisdiction_id)
        return relay.call_tool("get_meetings", {
            "jurisdiction_id": jurisdiction_id,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "limit": limit,
        })
```

Factory function will support federation configuration:

```python
def get_data_source(
    storage: Optional[StorageBackend] = None,
    relay_urls: Optional[List[str]] = None,
) -> DataSource:
    if relay_urls:
        return FederatedDataSource(relay_urls)
    if storage is None:
        storage = get_storage_backend()
    return LocalDataSource(storage)
```

## Rationale

### Why Introduce This Now?

1. **Federation readiness**: Second city joining would require query abstraction anyway
2. **Low risk**: Simple delegation pattern, no behavior change
3. **Clear boundaries**: Separates WHERE data comes from (backend) from HOW it's queried (interface)
4. **Testing**: Enables mocking data sources for unit tests

### Alternatives Considered

1. **Query remote databases directly** - Rejected: Requires VPN/firewall complexity, doesn't scale
2. **Replicate all data locally** - Rejected: Expensive, sync complexity, stale data
3. **Wait until second city joins** - Rejected: Harder to retrofit abstraction later

## Implementation Files

| File | Purpose |
|------|---------|
| `packages/civicos/src/civicos/storage/data_source.py` | DataSource protocol + LocalDataSource |
| `packages/civicos/src/civicos/storage/__init__.py` | Export DataSource types |
| `packages/civicos/src/civicos/civicos.py` | Wire CivicOS to use _data_source |
| `packages/civicos/tests/test_data_source.py` | Protocol and delegation tests |

## Migration Path

### Phase 1: Protocol Introduction (Pilot - Completed)

- [x] Define `DataSource` protocol
- [x] Implement `LocalDataSource` wrapping `StorageBackend`
- [x] Update CivicOS to use `_data_source` for queries
- [x] All existing tests pass (zero behavior change)

### Phase 2: Federation (Post-Pilot)

- [ ] Implement `FederatedDataSource` with MCP relay
- [ ] Add relay discovery/configuration
- [ ] Update `get_data_source()` factory
- [ ] Handle cross-city query routing

## Testing

```bash
# Run DataSource tests
pytest packages/civicos/tests/test_data_source.py -v

# Verify no regression in CivicOS
pytest packages/civicos/tests/test_civicos.py -v
```

All 16 DataSource tests + 42 CivicOS smoke tests pass.
