# Claude Code Development Workflow

CivicOS is developed with [Claude Code](https://claude.ai/claude-code), Anthropic's CLI for AI-assisted software engineering. The project includes custom slash commands (skills) that automate common workflows.

## Session Protocol

Every development session follows a structured protocol:

1. **`/start`** — Environment check, phase info, find next work item
2. **`/load_context`** — Explore agent loads codebase context
3. Work on **one item** per session
4. **`/critic`** — Run codebase critics on staged changes
5. **`/commit`** — Commit if critics pass
6. **`/nextsesh`** — Prepare handoff for next session

## Slash Commands Reference

### Session Management

| Command | Purpose |
|---------|---------|
| `/start` | Begin session — environment check, sync, find P0 item |
| `/start-parallel` | Begin secondary session on a different track |
| `/load_context` | Explore agent loads context for current work area |
| `/analyze-item [name]` | Deep analysis with 3 parallel agents |
| `/nextsesh` | Write handoff notes for next session |
| `/save` | Emergency session save when context is running low |

### Code Quality

| Command | Purpose |
|---------|---------|
| `/test [mode]` | Run tests — smoke, targeted, full, or profile |
| `/critic [type]` | Run LLM-based critics (pipeline, protocol, architecture, session, data, docs) |
| `/review [scope]` | Run pr-review-toolkit agents (code quality, silent failures, type design) |
| `/commit` | Run critics, then commit if they pass |

### Data Operations

| Command | Purpose |
|---------|---------|
| `/ingest [source]` | Orchestrate data ingestion pipeline |
| `/ingest-audio [jurisdiction]` | Download YouTube audio, upload to R2 |
| `/data-status [jurisdiction]` | Corpus counts, gaps, coverage |
| `/vector-coverage [jurisdiction]` | Vector embedding coverage analysis |
| `/vectors [action]` | GPU-accelerated vector indexing on Modal |
| `/checkpoint [action]` | View/reset ingestion checkpoints |

### Infrastructure

| Command | Purpose |
|---------|---------|
| `/launch` | Start dev servers (API + Open WebUI frontend) |
| `/relaunch` | Restart dev servers |
| `/db-backup [action]` | PostgreSQL backup (selective/full) |
| `/blob-backup [action]` | R2 blob storage management |

### City Onboarding

| Command | Purpose |
|---------|---------|
| `/onboard` | Interactive city onboarding wizard |

### Other

| Command | Purpose |
|---------|---------|
| `/tag` | Tag latest commit following version nomenclature |
| `/visual-review` | Screenshot browser extension UX and review |
| `/branch` | Save/resume conversation branches |

## Codebase Critics

LLM-based code review prompts in `.critics/` catch architectural issues before commit:

| Critic | What It Catches |
|--------|----------------|
| `pipeline` | ETL stage ordering, storage gaps |
| `protocol` | StorageBackend/VectorBackend conformance |
| `architecture` | Cross-package import violations |
| `session` | P0 assignment, session hygiene |
| `data` | Schema violations, type mismatches |
| `docs` | Stale paths, orphaned docs |

## Parallel Sessions

Multiple Claude Code sessions can work simultaneously using track-based partitioning:

| Track | Scope |
|-------|-------|
| **data** | Data architecture, readiness, standards, ingestion |
| **ops** | Deployment, monitoring, admin, rollback |
| **infra** | Test infrastructure, pipeline automation |
| **frontend** | UI refinement, user docs, onboarding |
| **validation** | Pilot validation |

Primary session works on P0 (main branch). Secondary sessions use `/start-parallel` to claim P1+ items in a different track on feature branches.

## pr-review-toolkit Integration

The project includes [pr-review-toolkit](https://github.com/anthropics/pr-review-toolkit) agents:

| Agent | Focus |
|-------|-------|
| `code-reviewer` | CLAUDE.md adherence, bugs, code quality |
| `pr-test-analyzer` | Test coverage quality |
| `silent-failure-hunter` | Silent failures, error handling |
| `type-design-analyzer` | Type invariants, encapsulation |

Run `/review` before creating PRs.
