# CLAUDE.md

**Civic** - AI-enabled infrastructure for local self-organization and governance.

## Quick Start

```bash
source civic-env/bin/activate
./init.sh                    # Verify environment + current phase
cat phase.json               # Current development phase
cat claude-progress.txt      # Where we are
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
src/                        # Application layer (API server, chat, websocket)
frontend/civic-workspace/   # Vue frontend
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
6. Commit: `git commit -m "Session N: [description]"`

### Slash Commands

| Command | Purpose | Subagents |
|---------|---------|-----------|
| `/start` | Begin session, find next item | No |
| `/load_context` | Load context for work area | Yes (Explore) |
| `/analyze-item [name]` | Deep analysis of item | Yes (3 parallel) |
| `/test [mode]` | Run tests (smoke/targeted/full/profile) | No |
| `/commit` | Commit changes | No |
| `/nextsesh` | Prepare handoff notes | No |

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

## Key Commands

```bash
python src/civic_api_integrated.py           # REST API (8001)
python src/civic_socketio_server.py          # WebSocket (8002)
cd frontend/civic-workspace && npm run dev   # Frontend
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

## Constraints

- Foundation-funded (<$7/month operational)
- Pilot: San Rafael, Jan 2026
- Moat is coordination, not intelligence
