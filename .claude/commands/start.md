# Start Civic Session

You are a coding agent working on Civic, an AI-enabled platform for local self-organization. Follow this protocol exactly.

## Step 1: Sync & Environment Check

First, pull latest changes (catches merged PRs from parallel sessions):

```bash
git pull origin main --rebase 2>/dev/null || git pull origin main || echo "Pull skipped (not on main or conflict)"
```

Then run these commands in parallel to establish context:

```bash
./init.sh
```

```bash
tail -20 claude-progress.txt
```

```bash
git log --oneline -5
```

## Step 1.5: Check for Handoff Context

Check if the previous session left context for you:

```bash
if [ -f "docs/next_session_prompt.md" ]; then
    echo "=== HANDOFF FROM PREVIOUS SESSION ==="
    cat docs/next_session_prompt.md
    echo ""
    echo "=== END HANDOFF ==="
    echo ""
    echo "Review the above handoff. You may:"
    echo "1. Accept and work on the recommended item"
    echo "2. Modify the approach"
    echo "3. Ignore and use pilot.json priorities instead"
else
    echo "No handoff from previous session."
fi
```

If a handoff exists and contains a P0 item, that takes precedence over Step 2's checklist scan. Read and understand the handoff before proceeding.

## Step 1.6: Check for Open PRs from Parallel Sessions

Check if parallel sessions have open PRs waiting for review/merge:

```bash
echo "=== OPEN PRs FROM PARALLEL SESSIONS ==="
gh pr list --state open --json number,title,headRefName,author,createdAt,mergeable --jq '.[] | "PR #\(.number): \(.title)\n  Branch: \(.headRefName)\n  Created: \(.createdAt)\n  Mergeable: \(.mergeable)\n"' 2>/dev/null || echo "Unable to fetch PRs (gh not authenticated or no PRs)"
echo "=== END PR CHECK ==="
```

If open PRs exist:
- **Same track as your work**: Consider reviewing/merging first to avoid conflicts
- **Different track**: Can ignore for now, but note them for later
- **Ready to merge** (tests passing): Can merge with `gh pr merge <number> --merge`
- **Needs review**: Run `/review` on the PR branch if time permits

## Step 2: Identify Recommended Work Item

**Priority Levels (recommendations, not mandates):**
- **P0**: Immediate/blocking - at most ONE P0 item allowed at a time
- **P1**: High priority - current sprint
- **P2**: Normal priority - planned work
- **P3**: Low priority - nice to have

> The priority system suggests the next item, but you have discretion. If you see a reason to work on a different item (dependencies, quick wins, context from handoff), you may do so. Document your reasoning.

```bash
python3 -c "
import json

with open('phase.json') as f:
    phase = json.load(f)

current_phase = phase['current_phase']
checklist_file = phase['active_checklist']

print('='*50)
print(f'PHASE: {current_phase.upper()}')
print(f'Checklist: {checklist_file}')
print('='*50)

with open(checklist_file) as f:
    checklist = json.load(f)

status_pending = {
    'implementation': 'not_implemented',
    'hardening': 'not_verified',
    'integration': 'not_tested',
    'pilot': 'not_ready'
}.get(current_phase, 'not_verified')

best = None
best_priority = 999
p0_items = []

# Use category_order if defined, otherwise iterate as-is
category_order = checklist.get('category_order', [k for k in checklist.keys()])
skip_keys = ['version', 'phase', 'derived_from', 'last_updated', 'target', 'location', 'summary', 'category_order']

for category in category_order:
    if category in skip_keys or category not in checklist:
        continue
    items = checklist[category]
    if not isinstance(items, dict):
        continue
    for subcategory, subitems in items.items():
        if not isinstance(subitems, dict) or subcategory in ['description', 'target']:
            continue
        for item, info in subitems.items():
            if isinstance(info, dict) and info.get('status') == status_pending:
                priority = info.get('priority', 99)
                if priority == 0:
                    p0_items.append(item)
                if priority < best_priority:
                    best_priority = priority
                    best = {'item': item, 'category': category, 'subcategory': subcategory, 'priority': priority, 'info': info}

# Warn if multiple P0 items (violates at-most-one rule)
if len(p0_items) > 1:
    print(f'WARNING: {len(p0_items)} P0 items found (should be at most 1):')
    for item in p0_items:
        print(f'  - {item}')
    print()

if best:
    priority_label = {0: 'P0 (IMMEDIATE)', 1: 'P1', 2: 'P2', 3: 'P3'}.get(best['priority'], f'P{best[\"priority\"]}')
    print(f'RECOMMENDED: {best[\"item\"]}')
    print(f'Area: {best[\"category\"]} > {best[\"subcategory\"]}')
    print(f'Priority: {priority_label}')
    print(f'(You have discretion to choose a different item if justified)')
    if 'test' in best['info']:
        print(f'Test: {best[\"info\"][\"test\"]}')
    if 'manual_step' in best['info']:
        print(f'Manual step: {best[\"info\"][\"manual_step\"]}')
else:
    print('All items complete for this phase!')
"
```

## Step 3: Load Context with Subagent (Recommended)

Use the Task tool with `subagent_type="Explore"` to investigate the work area. This saves main conversation context by having the agent read files in its own context window.

**Spawn an Explore agent with this prompt** (customize based on Step 2 output):

```
Explore the Civic codebase to understand the current state for: [ITEM NAME from Step 2]

Phase: [CURRENT PHASE]
Area: [CATEGORY > SUBCATEGORY]

Investigate:
1. Find relevant source files in packages/civicos/src/civic/ and related areas
2. Check existing tests in packages/civicos/tests/
3. Look at docs/critical/ for architectural context if relevant
4. Identify patterns and dependencies

Return a focused summary:
- Key files with line numbers
- Current implementation state
- Patterns to follow
- Suggested approach
- Any blockers or considerations

Be thorough but concise.
```

**Alternative**: For complex items, use `/analyze-item` which spawns 3 parallel agents for comprehensive analysis.

## Step 4: Work Rules

1. **ONE ITEM** per session - do not work on multiple items
2. **Read before edit** - understand existing code before modifying
3. **Test strategically** (see Testing section below)
4. **Commit on success** - `git commit -m "Session N: description"`

### Testing Strategy

Use tiered testing to save time:

| Tier | When | Command |
|------|------|---------|
| **Smoke** | Session start (automatic via `init.sh`) | `pytest test_civicos.py -q` (~30s) |
| **Targeted** | During development | `pytest {item's test_file} -q` (1-5m) |
| **Full** | Before commit only | `pytest packages/civicos/tests/ -q` (~14m) |

**Find the targeted test**: Check the `test_file` field in the item's checklist entry (if specified).

**Example workflow**:
```bash
# Working on 'hybrid_queries' item
pytest packages/civicos/tests/test_integration_rag_san_rafael.py -q  # targeted
# ... make changes, iterate ...
pytest packages/civicos/tests/ -q  # full suite before commit
```

### Phase-Specific Rules

| Phase | Status Field | Complete When |
|-------|--------------|---------------|
| hardening | not_verified → verified | Automated test passes |
| integration | not_tested → passing | Real data test passes |
| pilot | not_ready → ready | Artifact/check complete |

## Step 5: Session End Protocol

Before ending:

1. Update checklist status if item complete
2. Append summary to `claude-progress.txt`
3. Run pre-commit checks:
   ```bash
   /critic              # Civic-specific patterns
   /review              # General code quality (pr-review-toolkit)
   ```
4. Commit: `/commit` or `git commit -m "Session N: brief_description"`

## Available Commands

| Command | Purpose | Uses Subagents |
|---------|---------|----------------|
| `/start` | Begin session, find next item | No |
| `/start-parallel` | Begin secondary session (different track) | No |
| `/load_context` | Load context for current work area | Yes (Explore) |
| `/analyze-item` | Deep analysis of specific item | Yes (3 parallel) |
| `/test [mode]` | Run tests (smoke/targeted/full/profile) | No |
| `/critic [type]` | Run Civic-specific critics | No |
| `/review [scope]` | Run pr-review-toolkit agents | Yes (agents) |
| `/commit` | Commit changes | No |
| `/nextsesh` | Prepare handoff notes | No |

Now proceed: Run Steps 1-2, then use Step 3 to load context efficiently.
