# End Parallel Session

Document and wrap up a parallel session. Unlike `/nextsesh`, this does NOT require P0 ownership since parallel sessions work on P1+ items in separate tracks.

## When to Use

Use this command when ending a parallel session that was started with `/start-parallel`. This command:
- Documents what was accomplished on this branch
- Suggests next steps (push, PR, merge)
- Appends session summary to `claude-progress.txt`
- Does NOT set or require P0 (that's the main session's job)

## Steps

1. **Verify this is a parallel session:**
```bash
BRANCH=$(git branch --show-current)
WORKTREE=$(pwd)

echo "=============================================="
echo "PARALLEL SESSION STATUS"
echo "=============================================="
echo "Branch: $BRANCH"
echo "Worktree: $WORKTREE"
echo ""

# Check if on a feature branch (not main)
if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
    echo "WARNING: You're on $BRANCH, not a feature branch."
    echo "This command is for parallel sessions on feature branches."
    echo "Use /nextsesh instead for main session handoff."
fi

# Show uncommitted changes
echo "Uncommitted changes:"
git status --short
echo ""

# Show commits on this branch not in main
echo "Commits ahead of main:"
git log main..HEAD --oneline 2>/dev/null || echo "(could not compare to main)"
```

2. **Check item status in pilot.json:**
```bash
python3 << 'EOF'
import json
import subprocess

# Get current branch to infer item name
branch = subprocess.run(['git', 'branch', '--show-current'],
                       capture_output=True, text=True).stdout.strip()

# Parse item name from branch (feature/{track}/{item-name})
parts = branch.split('/')
if len(parts) >= 3:
    track = parts[1]
    item_name = parts[2].replace('-', '_')
    print(f"Track: {track.upper()}")
    print(f"Inferred item: {item_name}")
else:
    item_name = None
    print(f"Could not parse item from branch: {branch}")

# Find item in pilot.json
with open('pilot.json') as f:
    cl = json.load(f)

skip = ['version', 'phase', 'derived_from', 'last_updated', 'target', 'location', 'summary', 'category_order', 'description']

found = None
for cat, items in cl.items():
    if cat in skip or not isinstance(items, dict): continue
    for sub, subitems in items.items():
        if not isinstance(subitems, dict) or sub in skip: continue
        for item, info in subitems.items():
            if item_name and item == item_name:
                found = {'name': item, 'cat': cat, 'sub': sub, 'info': info}
                break

if found:
    print(f"\nItem: {found['name']}")
    print(f"Category: {found['cat']} > {found['sub']}")
    print(f"Status: {found['info'].get('status')}")
    print(f"Priority: P{found['info'].get('priority', '?')}")
    if found['info'].get('status') == 'ready':
        print("\n✓ Item already marked ready!")
    else:
        print("\n⚠ Item still not_ready - update pilot.json if work is complete")
else:
    print(f"\nCould not find matching item in pilot.json")
    print("You may need to manually update the item status.")
EOF
```

3. **Determine next steps:**

Based on the session state, choose one:

**If work is complete and ready for merge:**
```bash
# Push the branch
git push -u origin $(git branch --show-current)

# Create PR
gh pr create --base main --title "feat: [description]" --body "$(cat <<'BODY'
## Summary
- [What was done]

## Test plan
- [ ] Tests pass
- [ ] Benchmark runs

Parallel session work from civic-infra worktree.
BODY
)"
```

**If work is in progress (will continue later):**
```bash
# Just push to save progress
git push -u origin $(git branch --show-current)
echo "Branch pushed. Continue with: cd $(pwd) && claude"
```

**If work is complete and can fast-forward merge:**
```bash
# Only if you're confident and tests pass
cd ../civic  # Main repo
git fetch origin
git merge --ff-only origin/$(git branch --show-current)
```

4. **Append to claude-progress.txt:**

Add a session summary to the main repo's progress file:

```bash
# Get session info
BRANCH=$(git branch --show-current)
TRACK=$(echo $BRANCH | cut -d'/' -f2)
ITEM=$(echo $BRANCH | cut -d'/' -f3)
DATE=$(date +%Y-%m-%d)

# Append to progress file (in main repo if in worktree)
PROGRESS_FILE="claude-progress.txt"
if [[ ! -f "$PROGRESS_FILE" ]]; then
    PROGRESS_FILE="../civic/claude-progress.txt"
fi

cat >> "$PROGRESS_FILE" << EOF

## Session (Parallel): ${ITEM}
**Date:** ${DATE}
**Track:** ${TRACK}
**Branch:** ${BRANCH}
**Worktree:** $(pwd)

### Completed
- [List what was accomplished]

### Status
- [ ] Pushed to origin
- [ ] PR created / Ready for merge
- [ ] pilot.json updated

EOF

echo "Appended session summary to $PROGRESS_FILE"
echo "Edit the file to fill in the [List what was accomplished] section."
```

5. **Final checklist:**

Before ending the session, verify:
- [ ] All changes committed to feature branch
- [ ] Branch pushed to origin (or PR created)
- [ ] pilot.json item status updated if complete
- [ ] Session summary appended to claude-progress.txt

## Cleanup (After Merge)

Once the PR is merged or work is integrated:

```bash
# From main repo directory
cd ../civic

# Remove the worktree
git worktree remove ../civic-${TRACK}

# Delete the merged branch
git branch -d feature/${TRACK}/${ITEM}

# Prune stale worktree refs
git worktree prune
```

## Differences from /nextsesh

| Aspect | /nextsesh | /nextsesh-parallel |
|--------|-----------|-------------------|
| P0 required | Yes, must set one | No |
| Output | docs/next_session_prompt.md | claude-progress.txt append |
| Branch | main (usually) | feature/{track}/{item} |
| Next action | Handoff to next session | Push/PR/merge |
| Worktree | Main repo | Separate worktree |
