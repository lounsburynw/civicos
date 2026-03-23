# Recommended: Pagination Protocol Update

**Priority:** P0 (pagination_protocol_update)
**Area:** federation_testbed
**Date:** 2026-03-23

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

The previous session completed the extension token wallet (Phase 7 of the token pipeline): blind.ts, token-wallet.ts, service worker wiring, payment_proof on the voice cast path, and token issuer HTTP endpoints. All server-side tests pass. Extension builds cleanly.

The next P0 is adding `offset` to all `StorageBackend.get_*()` methods. A detailed spec exists — **read `docs/internal/pagination-protocol-spec.md` first**, it has the full design, SQL patterns, and phased implementation plan.

## What Exists Now

- **`limit` already exists** on most `get_*()` methods in `backend.py` — but `offset` is missing everywhere
- 6 sub-protocol files define the interfaces in `packages/civicos/src/civicos/storage/protocols/`
- `backend.py` is the composite `StorageBackend` protocol (~1200 lines)
- `postgres_backend.py` and `sqlite_backend.py` are the two implementations
- The spec calls for 4 phases: (1) Protocol+Postgres, (2) SQLite, (3) API layer, (4) cross-jurisdiction

## Key Files

| File | Purpose |
|------|---------|
| `docs/internal/pagination-protocol-spec.md` | **Read first** — full spec with SQL patterns |
| `packages/civicos/src/civicos/storage/backend.py` | Composite StorageBackend protocol |
| `packages/civicos/src/civicos/storage/protocols/content.py` | ContentStorage (meetings, decisions, transcripts, chunks) |
| `packages/civicos/src/civicos/storage/protocols/legislation.py` | LegislationStorage (legislation, municipal_code) |
| `packages/civicos/src/civicos/storage/protocols/community.py` | CommunityStorage (issues) |
| `packages/civicos/src/civicos/storage/protocols/financial.py` | FinancialStorage (budget_items) |
| `packages/civicos/src/civicos/storage/protocols/operations.py` | OperationsStorage (videos) |
| `packages/civicos/src/civicos/storage/protocols/elections.py` | ElectionsStorage (agenda_items) |
| `packages/civicos/src/civicos/storage/postgres_backend.py` | PostgresBackend — add OFFSET to SQL |
| `packages/civicos/src/civicos/storage/sqlite_backend.py` | SQLiteBackend — add OFFSET to SQL |

## Suggested Approach

1. Read the spec (`docs/internal/pagination-protocol-spec.md`)
2. Add `offset: int = 0` to all `get_*()` methods that already have `limit` in the 6 sub-protocols
3. Update `StorageBackend` composite in `backend.py` to match
4. Update `PostgresBackend` SQL queries: add `OFFSET %s` when `offset > 0`
5. Update `SQLiteBackend` similarly
6. Write tests for limit+offset behavior on both backends
7. If time permits: add `limit`/`offset` query params to REST API endpoints (Phase 3 in spec)

## Tests to Run

```bash
# Smoke test
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Storage-specific
pytest packages/civicos/tests/ -k "storage or backend or pagination" -q --override-ini="addopts="

# Full suite before commit
pytest packages/civicos/tests/ -q --override-ini="addopts="
```

## Success Criteria

- [ ] All `get_*()` methods in sub-protocols accept `offset: int = 0`
- [ ] `StorageBackend` composite protocol updated to match
- [ ] `PostgresBackend` applies OFFSET to SQL queries
- [ ] `SQLiteBackend` applies OFFSET to SQL queries
- [ ] `limit=None` still returns all results (backward compatibility)
- [ ] `offset` beyond result count returns empty list
- [ ] Existing tests pass (no regressions)

## Deferred Items

- **token_issuer_env_config** (P2, not_started) — Add TOKEN_ISSUER_SECRET to Modal secrets, document TOKEN_ISSUER_* env vars and /coordination/tokens/* endpoints. Flagged by docs critic 2026-03-23.
- **token_purchase_ui** (P3) — Stripe checkout flow for buying tokens.
