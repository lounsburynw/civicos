# CLAUDE.md

**CivicOS** - AI-enabled infrastructure for local self-organization and governance.

## Quick Start

```bash
source civicos-env/bin/activate
./init.sh                    # Verify environment + current phase
cat phase.json               # Current development phase
cat claude-progress.txt      # Where we are
```

### Verify PostgreSQL Data (Important!)

Always confirm you're using PostgreSQL with full pilot data:

```bash
source civicos-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civicos import CivicOS
c = CivicOS('city-san-rafael')
print(f'Backend: {type(c.storage).__name__}')
# Quick API test
print(f'Decisions: {len(c.what_happened(\"test\"))}')
"
```

Expected: `Backend: PostgresBackend` and non-zero decisions. If you see `SQLiteBackend`, check `.env` for `DATABASE_URL`.

## LSP Setup (Claude Code)

LSP enables faster code navigation (50ms vs 45s) and better context awareness.

**Install language servers:**
```bash
# Python (Pyright) - already in requirements.txt
pip install pyright

# TypeScript - install in extension
cd apps/civicos-extension && npm install
```

**Configuration files:**
- `pyrightconfig.json` - Python LSP config (includes all packages)

**Enable in Claude Code:**
```bash
claude
> /plugin    # Search "lsp", install Python and TypeScript plugins
```

## Development Phases

Development follows a phased approach, tracked in `phase.json`:

| Phase | Checklist | Focus |
|-------|-----------|-------|
| **implementation** | archived | Core feature development (COMPLETE) |
| **hardening** | archived | Audit, e2e tests, edge cases (COMPLETE) |
| **integration** | archived | Real data, stress tests, multi-user (COMPLETE) |
| **pilot** | archived | Deployment readiness (COMPLETE) |
| **launch** | `launch.json` | Billing, acceptance policy, token issuance, operator tooling (ACTIVE) |

Check current phase: `python3 -c "import json; print(json.load(open('phase.json'))['current_phase'])"`

### Phase Transition Criteria

- **implementation -> hardening**: All `features.json` items passing
- **hardening -> integration**: All `verification.json` items verified
- **integration -> pilot**: All `integration.json` items passing
- **pilot -> launch**: All `pilot.json` items complete (DONE)
- **launch -> production**: All `launch.json` items complete

### Priority Levels

| Priority | Meaning | Rule |
|----------|---------|------|
| **P0** | Immediate/blocking | **At most ONE P0 at a time** |
| **P1** | High priority | Current sprint work |
| **P2** | Normal priority | Planned work |
| **P3** | Low priority | Nice to have |

**Priorities are recommendations, not mandates.** `/start` suggests the highest-priority item, but sessions have discretion to choose differently if justified (dependencies, quick wins, stale context). Document reasoning when deviating.

P0 is reserved for critical blockers. `/start` and `init.sh` will warn if multiple P0 items exist.

## Core API

```python
from civicos import CivicOS
c = CivicOS("san-rafael")

# Query methods
c.whats_next()              # Upcoming meetings/decisions
c.what_happened("housing")  # Historical decisions
c.what_applies("housing")   # Relevant legislation
c.what_was_said("housing")  # Search meeting transcripts
c.get_public_testimony("housing")  # Public testimony excerpts


# Coordination — see civicos-relay package

```

### Data Access Patterns

**IMPORTANT:** Use the right abstraction layer. Never write raw SQL.

| Need | Use This | NOT This |
|------|----------|----------|
| User-facing queries | `Civic` API (`what_happened()`, etc.) | Raw SQL |
| Data counts/diagnostics | `DataStatus` or `StorageBackend.get_*_count()` | Raw SQL |
| Bulk data access | `StorageBackend.get_*()` methods | Raw SQL |
| Schema information | `CORPUS_REGISTRY` | Hardcoded column names |

**Layered architecture:**
```
CivicOS API (high-level)     →  what_happened(), what_applies()
    ↓
StorageBackend (protocol)  →  get_decisions(), get_meetings(), get_decision_count()
    ↓
PostgresBackend/SQLite     →  SQL (you never touch this directly)
```

**Examples:**
```python
# RIGHT: Use CivicOS API for semantic queries
c = CivicOS('city-san-rafael')
decisions = c.what_happened("housing")

# RIGHT: Use DataStatus for diagnostics
from civicos import DataStatus
status = DataStatus(c.storage, c._vectors, 'city-san-rafael')
print(status.gaps())

# RIGHT: Use StorageBackend for bulk access
meetings = c.storage.get_meetings('city-san-rafael')
count = c.storage.get_decision_count('city-san-rafael')

# WRONG: Never do this
cursor.execute("SELECT * FROM meetings WHERE meeting_date > ...")  # Wrong column name!
```

## Project Structure

```
phase.json                  # Current development phase
launch.json                 # Launch checklist (active)
claude-progress.txt         # Session state (append-only)
init.sh                     # Verification script
packages/civicos/             # Core API package
packages/civicos-relay/       # Federation-ready relay (voice, actions, sync, subscriptions)
packages/civicos-signer/      # Portable attestation signing service (for issuer orgs)
packages/civicos-extraction/  # Platform parsers
packages/civicos-services/    # Application layer (API server, chat, websocket)
packages/civicos-client/      # TypeScript/JavaScript client library
packages/civicos-components/  # Svelte UI components
apps/civicos-extension/       # Browser extension — PRIMARY user surface (Chrome)
apps/civicos-mcp/             # MCP server (for AI agents)
apps/civicos-workspace/       # Vue frontend (DEPRECATED)
apps/civicos-openwebui-fork/  # Open WebUI fork (secondary surface, symlink → ~/projects/civicos-openwebui)
data/                       # Extracted events, issues, legislative context
docs/public/                # Public-facing docs (architecture, API, extension, MCP, packages)
docs/internal/              # Ops docs (deployment, backup, ingestion, testing, rollback)
docs/private/               # Financial/billing (gitignored)
docs/archive/               # Historical docs (recoverable)
```

## Documentation

Organized into public (ships with the repo) and internal (operations). Read only when needed.

### Public Docs (docs/public/)

| Doc | Purpose |
|-----|---------|
| `README.md` | Project overview, architecture, quick start |
| `api.md` | Core CivicOS API — method signatures and return types |
| `data-dictionary.md` | All data schemas with field definitions |
| `extension/setup.md` | Browser extension install and user guide |
| `extension/development.md` | Extension dev workflow, tech stack, component architecture |
| `mcp/setup.md` | MCP server — connect Claude/ChatGPT, tool inventory |
| `relay/overview.md` | Relay — attestation, trust model, federation, AI proxy |
| `packages/*.md` | Per-package docs (civicos, services, relay, extraction, client, components) |
| `decisions/` | Architecture Decision Records (vector storage, entity IDs, federation) |
| `learning/` | Conceptual series — cryptography, Nostr, attestation, federation |
| `essays/` | Long-form writing |

### Internal Docs (docs/internal/)

| Doc | Purpose |
|-----|---------|
| `deployment.md` | Modal deploy, secrets, monitoring, infrastructure |
| `backup.md` | Database + blob backup procedures |
| `ingestion.md` | Data pipeline operations, checkpoints, vector indexing |
| `testing.md` | Test tiers, CI, commands |
| `rollback.md` | Recovery procedures |
| `storage-schema.md` | Database table schemas (internal, not API-facing) |

### Private Docs (docs/private/ — gitignored)
Financial, billing, and internal strategy docs.

### Archive (docs/archive/)
Historical docs from completed phases. Recoverable if needed.

## Session Protocol

1. Run `/start` - environment check, phase info, next work item
2. Run `/load_context` or spawn Explore agent - load context efficiently via subagent
3. Work on ONE item per session
4. Update checklist status when items change
5. Append to `claude-progress.txt` before ending
6. Run `/commit` - runs critics, then commits if they pass

### Slash Commands

| Command | Purpose | Subagents |
|---------|---------|-----------|
| `/start` | Begin session, find next item | No |
| `/start-parallel` | Begin secondary session (different track than P0) | No |
| `/launch` | Start dev servers (API, WebSocket) | No |
| `/load_context` | Load context for work area | Yes (Explore) |
| `/analyze-item [name]` | Deep analysis of item | Yes (3 parallel) |
| `/test [mode]` | Run tests (smoke/targeted/full/profile) | No |
| `/critic [type]` | Run codebase critics on staged changes | No |
| `/review [scope]` | Run pr-review-toolkit agents (code quality) | Yes (agents) |
| `/visual-review [mode]` | Screenshot extension UX + review (review/diff/both) | No |
| `/commit` | Run critics on staged changes, then commit | No |
| `/nextsesh` | Prepare handoff notes (requires P0 set) | No |
| `/ingest-audio [jurisdiction] [limit]` | Download YouTube audio locally, upload to R2 | No |
| `/db-backup [action]` | PostgreSQL backup (selective/full) | No |
| `/vectors [action]` | Vector indexing on Modal GPU | No |
| `/checkpoint [action]` | View/reset ingestion checkpoints | No |
| `/ingest [source]` | Orchestrate data ingestion pipeline | No |
| `/blob-backup [action]` | R2 blob storage management | No |
| `/data-status [jurisdiction]` | Schema-aware corpus counts, gaps, coverage | No |
| `/vector-coverage [jurisdiction]` | Vector embedding coverage analysis | No |

### Subagent Usage for Context Management

Subagents help manage context by running in isolated context windows:

```
# Load context efficiently (agent reads files, returns summary)
Task(subagent_type="Explore", prompt="Explore [area] for [item]...")

# Deep analysis with 3 parallel agents
/analyze-item vector_search
```

**When to use subagents:**
- Open-ended codebase exploration
- Loading context for a new work item
- Multi-file searches where scope is unclear

**When NOT to use subagents:**
- Reading a specific known file (use Read directly)
- Simple grep for known pattern
- Quick targeted lookups

### Phase-Specific Guidance

**Launch Phase** (current):
- Priority: Security fixes, billing infrastructure, acceptance policy
- Reference: `launch.json` for checklist items
- Focus: Usage logging, Stripe pipeline, attestation enforcement, blinded tokens, operator tooling

### Session End Requirements

**Sessions must assign exactly 1 P0 before ending.** This ensures continuity between sessions.

Before running `/nextsesh`:
1. Identify the most important next task
2. Update `launch.json` to set that item's `priority: 0`
3. `/nextsesh` will fail if no P0 is set

### Parallel Sessions

Multiple Claude Code sessions can work simultaneously using track-based partitioning.

**Tracks** (categories that touch similar files):

| Track | Categories |
|-------|------------|
| **data** | data_architecture, data_readiness, data_standards, data_integrity, ingestion_visibility |
| **ops** | deployment_artifacts, monitoring_observability, admin_operations, rollback_procedures |
| **infra** | test_infrastructure, pipeline_automation |
| **frontend** | frontend_refinement, user_documentation, city_onboarding |
| **validation** | pilot_validation |

**Workflow:**
1. **Primary session** runs `/start` and claims P0 (works on `main` or feature branch)
2. **Secondary session** runs `/start-parallel` to find P1+ work in a different track
3. Secondary session creates feature branch: `git checkout -b feature/{track}/{item-name}`
4. Sessions work independently, avoiding file conflicts
5. Secondary merges via PR after P0 session completes

**Session roles:**
- `secondary` - P1+ work in different track (default)
- `research` - Investigation only, no code changes
- `tooling` - Dev workflow improvements (.claude/, scripts/)

## Codebase Critics

LLM-based code review prompts in `.critics/` catch architectural issues before commit.

| Critic | Purpose |
|--------|---------|
| `pipeline.critic.md` | 4-stage ETL pattern (storage gaps, stage ordering) |
| `protocol.critic.md` | Protocol conformance (StorageBackend, VectorBackend) |
| `architecture.critic.md` | Layer boundaries (cross-package imports) |
| `session.critic.md` | Session hygiene (P0 assignment) |
| `security.critic.md` | Trust model integrity (silent verification bypass, env var holes, lazy crypto imports) |
| `jurisdiction.critic.md` | Jurisdiction isolation (missing filters, hardcoded jurisdictions, data leakage) |
| `data.critic.md` | ETL data quality (schema violations, type mismatches) |
| `docs.critic.md` | Documentation accuracy (stale paths, orphaned docs, bloat) |

**Usage:**
```bash
/critic              # Run all critics on staged changes
/critic pipeline     # Run specific critic
```

Critics output JSON with `pass`, `issues`, `severity`. Critical failures should block commit.

See `.critics/README.md` for full documentation.

### pr-review-toolkit Integration

The `pr-review-toolkit` Claude Code plugin provides general code quality agents that complement Civic-specific critics:

| Agent | Purpose |
|-------|---------|
| `code-reviewer` | CLAUDE.md adherence, bugs, code quality |
| `pr-test-analyzer` | Test coverage quality |
| `silent-failure-hunter` | Silent failures, error handling |
| `type-design-analyzer` | Type invariants, encapsulation |

**Pre-PR workflow:**
1. `/critic` - Civic patterns (pipeline, protocol, architecture)
2. `/review` - General quality (bugs, tests, error handling)
3. `/commit` - Commit if all pass

## Launching the App

Start the API backend for local development:

```bash
./scripts/dev.sh api                              # REST API (port 8001)
```

Or use `/launch` which starts the API and WebSocket servers.

The `dev.sh` script automatically:
- Loads `.env` (requires `GOOGLE_MAPS_API_KEY` with Geocoding API enabled)
- Sets `CIVICOS_DEV_MODE=true` and `CIVICOS_WEB_KEY=dev_key_local`
- Uses `civicos-env` venv Python directly

For browser extension development:
```bash
cd apps/civicos-extension && npm run dev          # Watch mode with hot reload
# Then load unpacked from apps/civicos-extension/dist in chrome://extensions
```

## Testing Strategy

Use tiered testing: fast tests locally, full suite in CI.

| Tier | Where | Time | When |
|------|-------|------|------|
| **Smoke** | Local | ~75s | Session start (via `init.sh`) |
| **Targeted** | Local | 1-3m | During development |
| **Full** | CI (GitHub Actions) | ~10-15m | On push/PR (automatic) |

### Workflow

1. **Session start**: `init.sh` runs smoke tests automatically
2. **During work**: Run targeted tests for your work area
3. **On push/PR**: GitHub Actions runs full suite (parallelized across 4 runners)

### Quick Reference

```bash
# Smoke test (core API)
pytest packages/civicos/tests/test_civicos.py -q --override-ini="addopts="

# Targeted test (example: RAG work)
pytest packages/civicos/tests/test_integration_rag_san_rafael.py -q --override-ini="addopts="

# Full suite locally (if needed - resource intensive!)
pytest packages/civicos/tests/ -q --override-ini="addopts="
```

### CI Integration

Full test suite runs automatically on GitHub Actions:
- **Trigger**: Push to main, PRs to main, or manual dispatch
- **Parallelization**: 4 runners × 2 workers each = 8-way parallel
- **Time**: ~10-15 minutes (vs 50+ minutes locally)
- **Config**: `.github/workflows/tests.yml`

### Rules

- **Never run full suite locally** - let CI handle it (saves RAM/time)
- **Use smoke tests for quick validation** - 31 tests, ~75s
- **Use targeted tests during dev** - each launch.json item has a `test_file` field
- **Check CI status before merging** - full coverage runs there

## Storage Backends

**IMPORTANT:** The project has TWO storage modes. Most pilot data is in PostgreSQL, NOT SQLite.

### Backend Selection

| Environment | Trigger | Storage | Vectors |
|-------------|---------|---------|---------|
| **Production** | `DATABASE_URL` set in `.env` | PostgresBackend | PgVectorBackend |
| **Local dev** | `DATABASE_URL` not set | SQLiteBackend | ChromaDB |

The `.env` file contains `DATABASE_URL` pointing to Supabase PostgreSQL. When set, the CivicOS API automatically uses PostgreSQL with full pilot data.

### Verifying Your Backend

```python
from dotenv import load_dotenv
load_dotenv()  # REQUIRED to load DATABASE_URL

from civicos import CivicOS
c = CivicOS('city-san-rafael')
print(type(c.storage).__name__)  # Should print: PostgresBackend
```

If you see `SQLiteBackend`, you forgot to load `.env` or `DATABASE_URL` is not set.

### PostgreSQL Data Inventory (Production)

San Rafael pilot data (counts approximate, run `/data-status` for current):

| Table | Count | Description |
|-------|-------|-------------|
| meetings | 98 | Oct 2025 - present |
| decisions | 44 | With outcomes, topics |
| transcripts | 19 | Full meeting transcripts |
| chunks | 5,084 | Agenda packet PDFs |
| issues | 1,730 | SeeClickFix complaints |
| budget_items | 58 | $180M FY25-26 |
| municipal_code | 16,175 | San Rafael municipal code |
| legislation | 17,719 | CA + federal bills |

### Vector Embeddings (Semantic Search)

| Corpus Type | Embeddings | Enables |
|-------------|------------|---------|
| transcripts | 4,296 | `what_was_said()`, `get_public_testimony()` |
| chunks | 5,084 | PDF/agenda search |
| municipal_code | 5,857 | Legal code search |
| issues | 1,459 | SeeClickFix issue search |
| decisions | 44 | `what_happened()` semantic search |
| meetings | 46 | Meeting search |

**Total: 16,786 embeddings for city-san-rafael**

### SQLite Data (Local Dev)

The `data/civic_state.db` file contains a subset of data for offline development. Do NOT rely on SQLite counts when assessing pilot readiness—always check PostgreSQL.

### Cloud Services

| Service | Purpose | Config |
|---------|---------|--------|
| Supabase Postgres | SQL + pgvector | `DATABASE_URL` in `.env` |
| Cloudflare R2 | Blob storage (PDFs, audio) | `BLOB_STORAGE_URL` in `.env` |

**Security:** RLS enabled via `scripts/sql/enable_rls.sql` - only service_role can access.

### Data Diagnostics

Use the `civic.diagnostics` module for schema-aware data queries. This prevents common mistakes with column/table names.

```python
from civicos import CivicOS, DataStatus, VectorCoverage, format_data_status

c = CivicOS('city-san-rafael')
status = DataStatus(c.storage, c._vectors, 'city-san-rafael')
print(format_data_status(status.summary()))  # Corpus counts, gaps, coverage
print(status.gaps())  # Only corpora with indexing gaps
```

**Schema reference** (avoid these common mistakes):

| Table | Correct Column | NOT This |
|-------|----------------|----------|
| meetings | `meeting_datetime` | ~~meeting_date~~ |
| chunks | `meeting_id` | ~~content_id~~ |
| vector_embeddings | (pgvector table) | ~~embeddings~~ |

Use `/data-status` and `/vector-coverage` commands for quick checks.

## Deployment

All production services run on **Modal** (serverless Python). Data lives in **Supabase PostgreSQL** (with pgvector). Blobs in **Cloudflare R2**.

```bash
# Deploy services
modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py
modal deploy apps/civicos-mcp/modal_mcp.py
modal deploy packages/civicos-relay/src/civicos_relay/modal_relay.py

# Vector indexing (GPU)
modal run scripts/modal_ingest.py

# Check status
modal app list
modal app logs civicos-api
```

- Never deploy to Fly.io or other platforms — Modal only.
- Local file edits are not automatically included — code is bundled at deploy time.
- Modal Secrets (`civicos-secrets`) store DATABASE_URL, OPENAI_API_KEY, etc. Check with `modal secret list`.
- See `docs/internal/deployment.md` for full procedures.

## UX Surfaces

The primary UX surface is the **browser extension** (`apps/civicos-extension/`). When discussing UI/UX changes, always target the extension unless explicitly told otherwise.

| Surface | Package | Role | Status |
|---------|---------|------|--------|
| **Browser extension** | `apps/civicos-extension/` | Primary — end users | Active |
| **MCP server** | `apps/civicos-mcp/` | AI agents (Claude, ChatGPT) | Active |
| **REST API** | `packages/civicos-services/` | Developers, integrations | Active |
| **Open WebUI fork** | `apps/civicos-openwebui-fork/` | Secondary — advanced users | Maintained |
| **Vue frontend** | `apps/civicos-workspace/` | Deprecated | Do not use |

### Browser Extension Development

```bash
cd apps/civicos-extension
npm run dev          # Watch mode, auto-rebuilds on change
npm run build        # Production build
```

Load the extension in Chrome: `chrome://extensions` → Developer mode → Load unpacked → select `apps/civicos-extension/dist`.

The extension uses Svelte, communicates with the CivicOS API, and manages local identity (Nostr keys) in browser storage. See `docs/public/extension/development.md` for design details.

## Protocol (Nostr)

This project uses **Nostr protocol with secp256k1 Schnorr signatures** (not P-256 ECDSA). All cryptographic operations must use the correct curve. Entity IDs follow Nostr conventions and require proper namespacing for federation. See `packages/civicos-relay/src/civicos_relay/voice/crypto.py` and `packages/civicos-relay/src/civicos_relay/nostr/kinds.py`.

## Constraints

- Foundation-funded
- Pilot: San Rafael
- Moat is coordination, not intelligence
