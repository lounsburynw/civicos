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
| **security** | security_fixes | packages/civicos-relay/src/civicos_relay/voice/crypto.py, server/app.py |
| **observability** | observability | apps/civicos-mcp/modal_mcp.py, apps/civicos-relay/modal_relay.py, scripts/ |
| **billing** | billing_payments | packages/civicos-services/src/civicos_services/core/stripe_billing.py |
| **acceptance** | acceptance_policy | packages/civicos-relay/src/civicos_relay/server/acceptance.py, apps/civicos-extension/ |
| **tokens** | token_issuance | New service, packages/civicos-relay/, apps/civicos-extension/ |
| **operator** | operator_readiness | docs/public/, config/ |

```bash
python3 << 'EOF'
import json
import sys

# Track definitions - categories that touch similar files
TRACKS = {
    'security': ['security_fixes'],
    'observability': ['observability'],
    'billing': ['billing_payments'],
    'acceptance': ['acceptance_policy'],
    'tokens': ['token_issuance'],
    'operator': ['operator_readiness']
}

def get_track(category):
    for track, cats in TRACKS.items():
        if category in cats:
            return track
    return 'unknown'

with open('launch.json') as f:
    cl = json.load(f)

skip = ['version', 'phase', 'last_updated', 'summary', 'category_order']

# Find P0 item
p0_item = None
p0_track = None

for cat, section in cl.items():
    if cat in skip or not isinstance(section, dict):
        continue
    for item_info in section.get('items', []):
        if isinstance(item_info, dict) and item_info.get('status') == 'not_started' and item_info.get('priority') == 0:
            p0_item = {'name': item_info['name'], 'category': cat, 'info': item_info}
            p0_track = get_track(cat)

print('=' * 60)
print('PARALLEL SESSION SETUP')
print('=' * 60)

if p0_item:
    print(f'\nCURRENT P0: {p0_item["name"]}')
    print(f'Category: {p0_item["category"]}')
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
for cat, section in cl.items():
    if cat in skip or not isinstance(section, dict):
        continue
    track = get_track(cat)
    # Skip same track as P0
    if p0_track and track == p0_track:
        continue
    for item_info in section.get('items', []):
        if isinstance(item_info, dict) and item_info.get('status') == 'not_started':
            priority = item_info.get('priority', 99)
            if priority > 0:  # Skip P0 items
                candidates.append({
                    'name': item_info['name'],
                    'category': cat,
                    'track': track,
                    'priority': priority,
                    'info': item_info
                })

# Sort by priority
candidates.sort(key=lambda x: x['priority'])

if candidates:
    # Show top 5 candidates
    print('\nTop candidates (different track than P0):')
    for i, c in enumerate(candidates[:5]):
        priority_label = f'P{c["priority"]}'
        print(f'\n{i+1}. [{priority_label}] {c["name"]}')
        print(f'   Track: {c["track"].upper()} | {c["category"]}')
        desc = c['info'].get('description', '')
        if desc:
            print(f'   Description: {desc[:80]}{"..." if len(desc) > 80 else ""}')

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
WORKTREE_DIR="../civicos-${TRACK}"

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
├── civicos/                # Main repo (P0 session on main)
├── civicos-observability/  # Worktree for observability track
├── civicos-billing/        # Worktree for billing track
├── civicos-operator/       # Worktree for operator track
└── ...
```

## Step 4: Start Claude Code in Worktree

**CRITICAL:** You must start a new Claude Code session in the worktree directory:

```bash
# In a NEW terminal window:
cd ../civicos-${TRACK}
source civicos-env/bin/activate  # Activate venv (symlinked from main)
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

## Step 6: PR Strategy

**Key principle:** One PR per feature branch, containing all related work.

### When to Create the PR

| Scenario | Action |
|----------|--------|
| Multiple related items in same category | Complete all, then create PR |
| Single isolated item | Create PR when item is done |
| Long-running work (2+ sessions) | Create draft PR early for CI visibility |

### PR Auto-Updates

PRs automatically include new commits pushed to the source branch:
```bash
# First item done - create PR
gh pr create --draft --base main --head "$BRANCH_NAME" --title "feat: description"

# Continue working on related items
# ... more commits ...
git push  # PR automatically updates

# All items done - mark ready for review
gh pr ready
```

## Step 7: Pre-Merge Review

When all related items are complete, run a comprehensive review:

```bash
# Ensure your branch is up to date with main
git fetch origin main
git rebase origin/main

# Run Civic-specific critics
/critic

# Run pr-review-toolkit agents
/review
```

## Step 8: Create/Finalize PR

**If PR already exists (draft):** Mark ready for review
```bash
gh pr ready
```

**If no PR yet:** Create one with all completed items listed
```bash
gh pr create --base main --head "$BRANCH_NAME" \
  --title "feat: [track] [description]" \
  --body "## Summary
- [x] item_1: Description
- [x] item_2: Description

## Test plan
- [x] /critic passed
- [x] /review passed"
```

## Step 9: Cleanup (After PR Merges)

```bash
# From main repo directory
git worktree remove ../civicos-${TRACK}
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
| P0 on security track | Work on observability, billing, operator, etc. |
| P0 on acceptance track | Work on observability, billing, operator, etc. |
| No P0 set | Run `/start` instead to claim P0 |
| Same-track work needed | Wait for P0 to complete, or coordinate |
| Worktree already exists | `cd ../civicos-{track}` and continue |

## Managing Worktrees

```bash
# List all worktrees
git worktree list

# Remove a worktree (after merging)
git worktree remove ../civicos-${TRACK}

# Prune stale worktree references
git worktree prune
```

## Session End

1. Commit all changes to your feature branch
2. Push branch: `git push -u origin $BRANCH_NAME`
3. Update launch.json status (if item complete)
4. Create PR or coordinate merge with P0 session
5. Append to `claude-progress.txt` (in main repo):
   ```
   ## Session N (Parallel): [item_name]
   **Track:** [track]
   **Worktree:** ../civicos-[track]
   **Branch:** feature/[track]/[item-name]
   **Status:** [complete/in-progress]
   [Brief summary]
   ```
6. Clean up worktree if work is complete
