# CLAUDE.md

**Civic** - AI-enabled infrastructure for local self-organization and governance.

## Quick Start

```bash
source civic-env/bin/activate
./init.sh                    # Verify environment + current phase
cat phase.json               # Current development phase
cat claude-progress.txt      # Where we are
```

### Verify PostgreSQL Data (Important!)

Always confirm you're using PostgreSQL with full pilot data:

```bash
source civic-env/bin/activate && python3 -c "
from dotenv import load_dotenv; load_dotenv()
from civic import Civic
c = Civic('city-san-rafael')
print(f'Backend: {type(c._storage).__name__}')
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

# TypeScript - install in frontend
cd apps/civic-workspace && npm install
```

**Configuration files:**
- `pyrightconfig.json` - Python LSP config (includes all packages)
- `apps/civic-workspace/tsconfig.app.json` - TypeScript config

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
| **pilot** | `pilot.json` | Deployment readiness for Jan 2026 (ACTIVE) |

Check current phase: `python3 -c "import json; print(json.load(open('phase.json'))['current_phase'])"`

### Phase Transition Criteria

- **implementation -> hardening**: All `features.json` items passing
- **hardening -> integration**: All `verification.json` items verified
- **integration -> pilot**: All `integration.json` items passing
- **pilot -> launch**: All `pilot.json` items complete

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
from civic import Civic
c = Civic("san-rafael")

# Query methods
c.whats_next()              # Upcoming meetings/decisions
c.what_happened("housing")  # Historical decisions
c.what_applies("housing")   # Relevant legislation
c.whos_with_me("traffic")   # Community around issue

# Action methods
c.start_something(...)      # Create initiative
c.add_voice(...)            # Add voice to item
c.follow(...)               # Subscribe to updates
c.prepare(...)              # Generate prep materials

# Orchestration methods (AI-driven)
c.suggestions()             # Proactive recommendations
c.coordinate(...)           # LangGraph coordination workflow
c.report_outcome(...)       # Close feedback loop
```

## Project Structure

```
phase.json                  # Current development phase
pilot.json                  # Pilot checklist (active)
claude-progress.txt         # Session state (append-only)
init.sh                     # Verification script
packages/civic/             # Core API package
packages/civic-extraction/  # Platform parsers
packages/civic-services/         # Application layer (API server, chat, websocket)
apps/civic-workspace/       # Vue frontend
apps/civic-mcp/             # MCP server
data/                       # Extracted events, issues, legislative context
docs/critical/              # Essential architecture docs
docs/archive/               # Historical docs (recoverable)
docs/archive/checklists/    # Completed phase checklists
```

## Documentation

Read only when needed. Organized by purpose:

### Architecture & Design (docs/critical/)
| Doc | Purpose |
|-----|---------|
| `FINAL_PACKAGE_ARCHITECTURE.md` | **Master architecture** - API, LangGraph, coordination, error handling |
| `FOCAL_POINT_DECISION_AWARENESS.md` | Core hypothesis - why civic coordination works |
| `MCP_INTEGRATION_STRATEGY.md` | MCP server design |
| `VECTOR_RAG_SCHEMA.md` | Vector storage schema, corpus types |
| `COMMITMENT_TRACKER_ARCHITECTURE.md` | Tracking official commitments |
| `FINANCIAL_DATA_INTEGRATION.md` | Budget, ACFR, intergovernmental data |
| `FEDERAL_FUNDING_DATA_SOURCES.md` | FAC, USAspending, federal data |
| `ELECTION_INTEGRATION.md` | Election data integration |

### Operations & Deployment (docs/critical/)
| Doc | Purpose |
|-----|---------|
| `PILOT_ROADMAP.md` | Jan 2026 validation plan |
| `DEPLOYMENT_GUIDE.md` | Production deployment |
| `HOSTING_DECISION.md` | Infrastructure choices |
| `ROLLBACK_PROCEDURES.md` | Recovery procedures |
| `UPTIME_MONITORING.md` | Health checks, alerting |
| `PRE_DEPLOYMENT_BACKUP.md` | Backup before deploy |
| `DAILY_BACKUP_SCHEDULE.md` | Ongoing backup schedule |
| `SECRETS_MANAGEMENT.md` | Environment variables, keys |
| `DATA_INGESTION_OPERATIONS.md` | ETL operations |
| `VERSIONING_STRATEGY.md` | Release versioning |

### Development Guides (docs/)
| Doc | Purpose |
|-----|---------|
| `TESTING_STRATEGY.md` | Test tiers, markers, fixtures, CI |
| `VERIFICATION_TUTORIAL.md` | Hands-on platform verification |
| `DATA_DICTIONARY.md` | Data schemas, field definitions |
| `EXTRACTOR_PROTOCOL.md` | Platform parser patterns |
| `BUDGET_EXTRACTION.md` | Budget PDF extraction |
| `ARCHITECTURE_AUDIT_2026_01.md` | Pre-pilot architecture review |
| `critical/SQLITE_CHROMADB_JOIN_PATTERNS.md` | Local dev storage patterns |

### Decisions (docs/decisions/)
Architecture Decision Records (ADRs):
- `vector_storage.md` - ChromaDB vs pgvector choice
- `data_integrity_infrastructure.md` - Data validation approach

### Operations Runbooks (docs/operations/)
- `VECTOR_INDEXING.md` - Re-indexing vectors

### Strategy & Business (docs/)
- `SUSTAINABILITY_MODEL.md` - Business model, pricing, open source
- `critical/FOUNDATION_FUNDING_THESIS.md` - Grant funding strategy

### User Guides (docs/user_guides/)
For end users and city admins:
- `GETTING_STARTED.md`, `FEATURE_GUIDE.md`, `FAQ.md`
- `ADMIN_SETUP_GUIDE.md`, `ADMIN_DATA_MANAGEMENT.md`, `ADMIN_TROUBLESHOOTING.md`
- `CITY_ONBOARDING_GUIDE.md`, `MCP_SETUP_GUIDE.md`
- `PLATFORM_SPECIFIC_NOTES.md`, `PILOT_USER_IDENTIFICATION.md`

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
| `/launch` | Start dev servers (API, WebSocket, Frontend) | No |
| `/load_context` | Load context for work area | Yes (Explore) |
| `/analyze-item [name]` | Deep analysis of item | Yes (3 parallel) |
| `/test [mode]` | Run tests (smoke/targeted/full/profile) | No |
| `/critic [type]` | Run codebase critics on staged changes | No |
| `/commit` | Run critics on staged changes, then commit | No |
| `/nextsesh` | Prepare handoff notes (requires P0 set) | No |

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

**Pilot Phase** (current):
- Priority: Deployment artifacts and monitoring
- Reference: `pilot.json` for checklist items
- Focus: Rollback procedures, user documentation, Jan 2026 launch readiness

### Session End Requirements

**Sessions must assign exactly 1 P0 before ending.** This ensures continuity between sessions.

Before running `/nextsesh`:
1. Identify the most important next task
2. Update `pilot.json` to set that item's `priority: 0`
3. `/nextsesh` will fail if no P0 is set

## Codebase Critics

LLM-based code review prompts in `.critics/` catch architectural issues before commit.

| Critic | Purpose |
|--------|---------|
| `pipeline.critic.md` | 4-stage ETL pattern (storage gaps, stage ordering) |
| `protocol.critic.md` | Protocol conformance (StorageBackend, VectorBackend) |
| `architecture.critic.md` | Layer boundaries (cross-package imports) |
| `session.critic.md` | Session hygiene (P0 assignment) |

**Usage:**
```bash
/critic              # Run all critics on staged changes
/critic pipeline     # Run specific critic
```

Critics output JSON with `pass`, `issues`, `severity`. Critical failures should block commit.

See `.critics/README.md` for full documentation.

## Launching the App

Use the dev launch script to start all services with proper environment configuration:

```bash
./scripts/dev.sh          # Start all services (API, WebSocket, Frontend)
./scripts/dev.sh api      # REST API only (port 8001)
./scripts/dev.sh ws       # WebSocket only (port 8002)
./scripts/dev.sh frontend # Vue frontend only (port 5173)
```

The script automatically:
- Loads `.env` (requires `GOOGLE_MAPS_API_KEY` with Geocoding API enabled)
- Sets `CIVIC_DEV_MODE=true` and `CIVIC_WEB_KEY=dev_key_local`
- Activates `civic-env` virtual environment

Or use the `/launch` command which documents the full process.

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
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# Targeted test (example: RAG work)
pytest packages/civic/tests/test_integration_rag_san_rafael.py -q --override-ini="addopts="

# Full suite locally (if needed - resource intensive!)
pytest packages/civic/tests/ -q --override-ini="addopts="
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
- **Use targeted tests during dev** - each pilot.json item has a `test_file` field
- **Check CI status before merging** - full coverage runs there

## Storage Backends

**IMPORTANT:** The project has TWO storage modes. Most pilot data is in PostgreSQL, NOT SQLite.

### Backend Selection

| Environment | Trigger | Storage | Vectors |
|-------------|---------|---------|---------|
| **Production** | `DATABASE_URL` set in `.env` | PostgresBackend | PgVectorBackend |
| **Local dev** | `DATABASE_URL` not set | SQLiteBackend | ChromaDB |

The `.env` file contains `DATABASE_URL` pointing to Supabase PostgreSQL. When set, the Civic API automatically uses PostgreSQL with full pilot data.

### Verifying Your Backend

```python
from dotenv import load_dotenv
load_dotenv()  # REQUIRED to load DATABASE_URL

from civic import Civic
c = Civic('city-san-rafael')
print(type(c._storage).__name__)  # Should print: PostgresBackend
```

If you see `SQLiteBackend`, you forgot to load `.env` or `DATABASE_URL` is not set.

### PostgreSQL Data Inventory (Production)

San Rafael pilot data as of Jan 2026:

| Table | Count | Description |
|-------|-------|-------------|
| meetings | 98 | Oct 2025 - Jan 2026 |
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
| issues | 1,459 | `whos_with_me()` semantic matching |
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

## Constraints

- Foundation-funded (<$7/month operational)
- Pilot: San Rafael, Jan 2026
- Moat is coordination, not intelligence
