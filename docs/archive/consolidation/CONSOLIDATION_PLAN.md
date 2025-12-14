# Consolidation Plan

**Created:** Session 226 (Dec 9, 2025)
**Purpose:** Multi-session plan for consolidating checklists and merging branches
**Status:** Planning complete, ready for execution

---

## Current State

### Branches
| Branch | State | Last Session | Notes |
|--------|-------|--------------|-------|
| `main` | Stable | 119 | MCP server + LangGraph integration |
| `feature/mcp-modularization` | Active | 224 | 125 commits ahead, 305 files changed |
| `backup/mcp-modularization-session-225` | Backup | 224 | Safety copy created Session 226 |

### Checklists
| File | Status | Items | Action |
|------|--------|-------|--------|
| `features.json` | COMPLETE | ~50 | Archive |
| `integration.json` | COMPLETE | 103 | Archive |
| `verification.json` | COMPLETE | ~40 | Archive |
| `operations.json` | NEW | 58 | Merge into pilot.json |
| `pilot.json` | ACTIVE | 43 | Primary checklist |

### Progress Log
- `claude-progress.txt` - Sessions 125-224 (~100 sessions)
- Growing large, affects context loading

---

## Consolidation Steps

### Phase 1: Archive Completed Work (This Session)

```bash
# 1. Create archive directory
mkdir -p docs/archive/checklists

# 2. Move completed checklists
mv features.json docs/archive/checklists/
mv integration.json docs/archive/checklists/
mv verification.json docs/archive/checklists/

# 3. Archive old progress entries
head -n 500 claude-progress.txt > docs/archive/progress_sessions_125-200.txt
tail -n 100 claude-progress.txt > claude-progress-recent.txt
mv claude-progress-recent.txt claude-progress.txt
```

### Phase 2: Merge operations.json into pilot.json

1. Read both files
2. Identify overlaps (deployment_artifacts, monitoring, documentation)
3. Merge non-overlapping items from operations.json
4. Delete operations.json
5. Update phase.json to reference pilot.json

### Phase 3: Branch Strategy (Future Session)

**Option A: Merge to main**
```bash
git checkout main
git merge feature/mcp-modularization -m "Merge Sessions 120-224: Integration phase complete"
git tag v0.9-integration-complete
git push origin main --tags
```

**Option B: Rebase and squash** (cleaner history)
```bash
git checkout feature/mcp-modularization
git rebase -i main  # Squash into logical commits
git checkout main
git merge feature/mcp-modularization
```

**Recommended:** Option A (merge). 125 commits represent real work history. Squashing loses granularity.

**Before merging:**
- [ ] Run full test suite on feature branch
- [ ] Verify main still works independently
- [ ] Document breaking changes (if any)
- [ ] Update README if API changed

---

## Checklist Consolidation Details

### Items to merge from operations.json → pilot.json

**Already in pilot.json:**
- containerization (Dockerfile, docker-compose)
- health_checks (api_health_endpoint)
- logging (structured_logging)
- deployment_documented
- backup procedures

**NEW from operations.json (add to pilot.json):**
```
ingestion_visibility:
  - civic_status_command (CLI)
  - admin_status_endpoint (API)
  - frontend_dashboard (Vue)
  - freshness_warnings
  - gap_detection

admin_operations_gui:
  - manual_triggers (6 buttons)
  - operation_status
  - cost_tracking

pipeline_automation:
  - cron scheduling (6 pipelines)
  - incremental_processing
  - heartbeat_monitoring

data_gaps:
  - seeclickfix_refresh
  - seeclickfix_vector_indexing
  - legislative_context
  - transcript_backlog
```

### Proposed pilot.json Structure After Merge

```
pilot.json
├── deployment_artifacts (existing)
├── monitoring_observability (existing + expand)
├── rollback_procedures (existing)
├── user_documentation (existing)
├── pilot_validation (existing)
├── ingestion_visibility (NEW)
├── admin_operations (NEW)
├── pipeline_automation (NEW)
└── data_freshness (NEW)
```

---

## Context Management for Future Sessions

### Problem
- claude-progress.txt growing (~30K tokens)
- Multiple JSON files to load
- Each session starts with context overhead

### Solution
1. **Archive aggressively** - Move completed work out of active files
2. **Summarize progress** - Keep only last 25 sessions in active file
3. **Single active checklist** - pilot.json only
4. **init.sh shows what matters** - Current phase, next item, blockers

### Updated Session Protocol

```bash
# Start of session
./init.sh                    # Verify environment, show current phase
cat pilot.json | head -50    # See priority items (optional)

# Work
# ... do the work ...

# End of session
# Append to claude-progress.txt (brief summary)
# Commit with session number
```

---

## Execution Timeline

| Session | Task | Est. Time |
|---------|------|-----------|
| 226 (current) | Create this plan, backup branch | Done |
| 227 | Archive checklists, merge operations→pilot | 1 hour |
| 228 | Trim claude-progress.txt, update init.sh | 30 min |
| 229+ | Begin pilot.json items (Layer 0 first) | Ongoing |
| TBD | Merge feature→main (after tests pass) | 1 hour |

---

## Safety Checklist

Before any destructive operation:
- [x] Backup branch created: `backup/mcp-modularization-session-225`
- [ ] Full test suite passes
- [ ] Main branch verified working independently
- [ ] No uncommitted changes
- [ ] Remote backup exists (push backup branch)

---

## Notes

- Main branch (Session 119) has: MCP server, LangGraph basics, initial pilot data
- Feature branch adds: Full test suite, RAG infrastructure, video transcripts, operations tooling
- These are complementary, not conflicting
- Merge is additive, not destructive
