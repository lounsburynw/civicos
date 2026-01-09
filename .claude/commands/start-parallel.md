# Start Parallel Session

Start a secondary Claude Code session that works on items **not conflicting** with the current P0 work.

**IMPORTANT:** This command uses **git worktrees** to enable true parallel development. Each parallel session runs in a separate directory with its own checked-out branch.

## Usage

```
/start-parallel [--role <role>]
```

**Roles:**
- `secondary` (default) - Work on P1+ items in a different track than P0
- `research` - Investigation only, no code changes
- `tooling` - Work on dev workflow improvements

## Step 1: Environment Check

Run the standard environment verification:

```bash
./init.sh
```

## Step 2: Detect Current P0 and Its Track

Categories are grouped into **tracks** to prevent file conflicts:

| Track | Categories | Typical Files |
|-------|------------|---------------|
| **data** | data_architecture, data_readiness, data_standards, data_integrity, ingestion_visibility | packages/civic/, scripts/ingest_*.py |
| **ops** | deployment_artifacts, monitoring_observability, admin_operations, rollback_procedures | scripts/, .github/, docs/critical/*DEPLOY* |
| **infra** | test_infrastructure, pipeline_automation | tests/, conftest.py, .github/workflows/ |
| **frontend** | frontend_refinement, user_documentation, city_onboarding | apps/civic-workspace/, docs/user_guides/ |
| **validation** | pilot_validation | Various (review only) |

```bash
python3 << 'EOF'
import json
import sys

# Track definitions - categories that touch similar files
TRACKS = {
    'data': ['data_architecture', 'data_readiness', 'data_standards', 'data_integrity', 'ingestion_visibility'],
    'ops': ['deployment_artifacts', 'monitoring_observability', 'admin_operations', 'rollback_procedures'],
    'infra': ['test_infrastructure', 'pipeline_automation'],
    'frontend': ['frontend_refinement', 'user_documentation', 'city_onboarding'],
    'validation': ['pilot_validation']
}

def get_track(category):
    for track, cats in TRACKS.items():
        if category in cats:
            return track
    return 'unknown'

with open('pilot.json') as f:
    cl = json.load(f)

skip = ['version', 'phase', 'derived_from', 'last_updated', 'target', 'location', 'summary', 'category_order', 'description']

# Find P0 item
p0_item = None
p0_track = None

for cat, items in cl.items():
    if cat in skip or not isinstance(items, dict):
        continue
    for sub, subitems in items.items():
        if not isinstance(subitems, dict) or sub in skip:
            continue
        for item, info in subitems.items():
            if isinstance(info, dict) and info.get('status') == 'not_ready' and info.get('priority') == 0:
                p0_item = {'name': item, 'category': cat, 'subcategory': sub, 'info': info}
                p0_track = get_track(cat)

print('=' * 60)
print('PARALLEL SESSION SETUP')
print('=' * 60)

if p0_item:
    print(f'\nCURRENT P0: {p0_item["name"]}')
    print(f'Category: {p0_item["category"]} > {p0_item["subcategory"]}')
    print(f'Track: {p0_track.upper()}')
    print(f'\nAVOID these tracks to prevent conflicts: {p0_track}')
else:
    print('\nNO P0 ITEM FOUND')
    print('Consider running /start instead to claim P0.')
    p0_track = None

# Find best secondary item (P1+ in different track)
print('\n' + '=' * 60)
print('RECOMMENDED SECONDARY ITEMS')
print('=' * 60)

candidates = []
for cat, items in cl.items():
    if cat in skip or not isinstance(items, dict):
        continue
    track = get_track(cat)
    # Skip same track as P0
    if p0_track and track == p0_track:
        continue
    for sub, subitems in items.items():
        if not isinstance(subitems, dict) or sub in skip:
            continue
        for item, info in subitems.items():
            if isinstance(info, dict) and info.get('status') == 'not_ready':
                priority = info.get('priority', 99)
                if priority > 0:  # Skip P0 items
                    candidates.append({
                        'name': item,
                        'category': cat,
                        'subcategory': sub,
                        'track': track,
                        'priority': priority,
                        'info': info
                    })

# Sort by priority
candidates.sort(key=lambda x: x['priority'])

if candidates:
    # Show top 5 candidates
    print('\nTop candidates (different track than P0):')
    for i, c in enumerate(candidates[:5]):
        priority_label = f'P{c["priority"]}'
        print(f'\n{i+1}. [{priority_label}] {c["name"]}')
        print(f'   Track: {c["track"].upper()} | {c["category"]} > {c["subcategory"]}')
        if c['info'].get('artifact'):
            artifact = c['info']['artifact'][:80] + '...' if len(c['info'].get('artifact', '')) > 80 else c['info'].get('artifact', '')
            print(f'   Artifact: {artifact}')

    # Recommend top item
    top = candidates[0]
    print(f'\n{"=" * 60}')
    print(f'RECOMMENDED: {top["name"]}')
    print(f'Track: {top["track"].upper()} (safe - different from P0)')
    print(f'Priority: P{top["priority"]}')
    print(f'{"=" * 60}')
else:
    print('\nNo suitable secondary items found.')
    print('All remaining items are in the same track as P0.')

EOF
```

## Step 3: Create Git Worktree

**Why worktrees?** Git worktrees allow multiple branches to be checked out simultaneously in separate directories. This prevents the branch-switching conflicts that occur when two sessions share one working directory.

Once you've selected an item, create a worktree:

```bash
# Set your chosen item and track (use kebab-case for item name)
ITEM_NAME="your-item-name"
TRACK="track-name"
BRANCH_NAME="feature/${TRACK}/${ITEM_NAME}"
WORKTREE_DIR="../civic-${TRACK}"

# Check if worktree already exists
if [ -d "$WORKTREE_DIR" ]; then
    echo "Worktree already exists at $WORKTREE_DIR"
    echo "To reuse: cd $WORKTREE_DIR && git checkout $BRANCH_NAME"
    echo "To remove: git worktree remove $WORKTREE_DIR"
else
    # Create branch and worktree
    git branch "$BRANCH_NAME" 2>/dev/null || echo "Branch already exists"
    git worktree add "$WORKTREE_DIR" "$BRANCH_NAME"
    echo ""
    echo "=========================================="
    echo "WORKTREE CREATED SUCCESSFULLY"
    echo "=========================================="
    echo "Location: $WORKTREE_DIR"
    echo "Branch: $BRANCH_NAME"
    echo ""
    echo "To start working:"
    echo "  1. Open new terminal"
    echo "  2. cd $WORKTREE_DIR"
    echo "  3. claude  (start new Claude Code session)"
    echo "=========================================="
fi
```

**Directory structure after setup:**
```
~/projects/
├── civic/                  # Main repo (P0 session on main)
├── civic-infra/            # Worktree for infra track
├── civic-ops/              # Worktree for ops track
├── civic-frontend/         # Worktree for frontend track
└── civic-validation/       # Worktree for validation track
```

## Step 4: Start Claude Code in Worktree

**CRITICAL:** You must start a new Claude Code session in the worktree directory:

```bash
# In a NEW terminal window:
cd ../civic-${TRACK}
source civic-env/bin/activate  # Activate venv (symlinked from main)
claude
```

The worktree shares:
- Git history and branches
- The `.env` file (via relative path)

The worktree has its own:
- Working directory (no file conflicts)
- Checked-out branch
- Uncommitted changes

## Step 5: Session Protocol

**For Secondary Sessions:**
1. Document your role at session start: "This is a **secondary session** working on [item] in the [track] track."
2. Commit frequently to your feature branch
3. Run targeted tests only (not full suite - let P0 session handle that)
4. When done, create a PR or note for merge

**For Research Sessions:**
1. No worktree needed (no code changes)
2. Document findings in scratch notes or memory
3. Can inform P0 session's approach

**For Tooling Sessions:**
1. Work on `.claude/`, `scripts/dev*.sh`, workflow files
2. Create worktree if making code changes

## Step 6: Pre-Merge Review

When your secondary work is complete, run a comprehensive review before merging:

```bash
# In your worktree directory
# Ensure your branch is up to date with main
git fetch origin main
git rebase origin/main

# Run Civic-specific critics (pipeline, protocol, architecture)
/critic

# Run pr-review-toolkit agents for general code quality
/review
```

**Review agents from pr-review-toolkit:**

| Agent | When to Use |
|-------|-------------|
| `code-reviewer` | Always - checks CLAUDE.md adherence, bugs |
| `pr-test-analyzer` | If you added/modified tests |
| `silent-failure-hunter` | If you touched error handling |
| `type-design-analyzer` | If you added new types/dataclasses |
| `code-simplifier` | Optional - for complex implementations |

## Step 7: Merge and Cleanup

After reviews pass:

```bash
# Option A: Merge via PR (recommended)
gh pr create --base main --head "$BRANCH_NAME" --title "feat: [item description]"

# Option B: Fast-forward merge (if linear history)
cd ../civic  # Main repo
git merge --ff-only "$BRANCH_NAME"
```

**Cleanup worktree after merge:**
```bash
# From main repo directory
git worktree remove ../civic-${TRACK}
git branch -d "$BRANCH_NAME"  # Delete merged branch
```

## Conflict Resolution

If you accidentally touch files being modified by P0 session:
1. **Stop immediately** - don't commit conflicting changes
2. Coordinate with P0 session (or wait for it to complete)
3. Rebase after P0 merges: `git rebase origin/main`

## Quick Reference

| Scenario | Action |
|----------|--------|
| P0 on data track | Work on ops, infra, frontend, or validation |
| P0 on frontend | Work on data, ops, or infra |
| No P0 set | Run `/start` instead to claim P0 |
| Same-track work needed | Wait for P0 to complete, or coordinate |
| Worktree already exists | `cd ../civic-{track}` and continue |

## Managing Worktrees

```bash
# List all worktrees
git worktree list

# Remove a worktree (after merging)
git worktree remove ../civic-${TRACK}

# Prune stale worktree references
git worktree prune
```

## Session End

1. Commit all changes to your feature branch
2. Push branch: `git push -u origin $BRANCH_NAME`
3. Update pilot.json status (if item complete)
4. Create PR or coordinate merge with P0 session
5. Append to `claude-progress.txt` (in main repo):
   ```
   ## Session N (Parallel): [item_name]
   **Track:** [track]
   **Worktree:** ../civic-[track]
   **Branch:** feature/[track]/[item-name]
   **Status:** [complete/in-progress]
   [Brief summary]
   ```
6. Clean up worktree if work is complete
