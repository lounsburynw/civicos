# ADR: DataSource Protocol for Federation

**Status:** Accepted
**Date:** 2026-01-29

## Decision

Introduce a `DataSource` protocol that abstracts data access, enabling CivicOS to query civic data without knowing whether it's local or from a federated instance. For the pilot, only a local implementation exists; federation support will be added when a second jurisdiction joins.

## Context

CivicOS queries civic data through a `StorageBackend` that talks directly to the database. This works for a single jurisdiction, but federation requires querying data that may live on another operator's instance. Rather than retrofit this abstraction later, we introduced it during the pilot phase as a thin delegation layer with zero behavior change.

## Protocol Design

```python
@runtime_checkable
class DataSource(Protocol):
    """Read-only interface for civic data access (local or federated)."""

    @property
    def source_type(self) -> str:
        """Returns 'local', 'federated', or 'hybrid'."""
        ...

    def get_meetings(self, jurisdiction_id, since, until, limit) -> List[Dict]: ...
    def get_decisions(self, jurisdiction_id, since, until, limit) -> List[Dict]: ...
    def get_elections(self, jurisdiction_id, include_past, limit) -> List[Dict]: ...
    def get_budget_items(self, jurisdiction_id, fiscal_year, department, limit) -> List[Dict]: ...
    # ... additional query methods
```

### Key Design Choices

1. **Read-only** — `DataSource` handles queries only. Write operations stay on `StorageBackend` because only local data should be written.

2. **Dict-based returns** — Methods return `List[Dict]` for JSON serialization and cross-process compatibility (important for MCP relay communication).

3. **Simple parameter types** — Query methods use `str`, `datetime`, `int`, `bool` — types that serialize cleanly over the MCP protocol.

## Implementations

### LocalDataSource (Current)

Wraps `StorageBackend` with zero behavior change:

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
            since=since, until=until, limit=limit,
        )
```

CivicOS routes all queries through `_data_source`:

```python
class CivicOS:
    def __post_init__(self):
        self._storage = get_storage_backend(database_url)
        self._data_source = LocalDataSource(self._storage)

    def whats_next(self, topics=None, days=30):
        meetings = self._data_source.get_meetings(...)
```

### FederatedDataSource (Future)

Will use the civicos-relay MCP protocol to fan out queries to remote instances:

```python
class FederatedDataSource:
    def __init__(self, relay_urls: List[str]):
        self._relays = [MCPClient(url) for url in relay_urls]

    def get_meetings(self, jurisdiction_id, since, until, limit):
        relay = self._get_relay_for_jurisdiction(jurisdiction_id)
        return relay.call_tool("get_meetings", {...})
```

A factory function will select the appropriate implementation based on configuration:

```python
def get_data_source(storage=None, relay_urls=None) -> DataSource:
    if relay_urls:
        return FederatedDataSource(relay_urls)
    return LocalDataSource(storage or get_storage_backend())
```

## Rationale

1. **Federation readiness** — A second city joining would require this abstraction anyway
2. **Low risk** — Simple delegation pattern with zero behavior change for existing code
3. **Clear boundaries** — Separates *where* data lives from *how* it's queried
4. **Testability** — Enables mocking data sources without a database

### Alternatives Considered

1. **Query remote databases directly** — Rejected: Requires VPN/firewall complexity, doesn't scale
2. **Replicate all data locally** — Rejected: Expensive, sync complexity, stale data risk
3. **Wait until second city joins** — Rejected: Harder to retrofit the abstraction into existing query paths

## References

- [Entity ID Namespacing](entity_id_namespace.md) — How namespaced IDs enable federation
- [Federation Domain Architecture](federation_domain_architecture.md) — Domain and operator model
- [civicos-relay package](../packages/civicos-relay.md) — Relay protocol details
