# CLAUDE.md

**Civic** - AI-enabled infrastructure for local self-organization and governance.

## Quick Start

```bash
source civic-env/bin/activate
./init.sh                    # Verify environment + current phase
cat phase.json               # Current development phase
cat claude-progress.txt      # Where we are
```

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

## Critical Docs

Read only when needed for architectural decisions:

- `docs/critical/FINAL_PACKAGE_ARCHITECTURE.md` - **Master architecture** (API, LangGraph, coordination, error handling)
- `docs/critical/MCP_INTEGRATION_STRATEGY.md` - MCP server design
- `docs/critical/FOCAL_POINT_DECISION_AWARENESS.md` - Core hypothesis
- `docs/critical/FOUNDATION_FUNDING_THESIS.md` - Business model
- `docs/critical/PILOT_ROADMAP.md` - Jan 2026 validation plan
- `docs/VERIFICATION_TUTORIAL.md` - Hands-on platform verification guide
- `docs/TESTING_STRATEGY.md` - Test tiers, markers, fixtures, and CI strategy

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

## Cloud Infrastructure

Production uses Supabase (free tier) + Cloudflare R2:

| Data Type | Backend | Service |
|-----------|---------|---------|
| SQL | PostgresBackend | Supabase Postgres |
| Vectors | PgVectorBackend | Supabase pgvector |
| Blobs | R2Backend | Cloudflare R2 |

**Local dev:** SQLite + ChromaDB (no cloud dependency)

**Config:** `DATABASE_URL` in `.env` switches to cloud backends automatically.

**Security:** RLS enabled via `scripts/sql/enable_rls.sql` - only service_role can access.

## Constraints

- Foundation-funded (<$7/month operational)
- Pilot: San Rafael, Jan 2026
- Moat is coordination, not intelligence
