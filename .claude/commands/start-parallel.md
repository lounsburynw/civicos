# Start Parallel Session

Start a secondary Claude Code session that works on items **not conflicting** with the current P0 work.

## Usage

```
/start-parallel [--role <role>]
```

**Roles:**
- `secondary` (default) - Work on P1+ items in a different track than P0
- `research` - Investigation only, no code changes
- `tooling` - Work on dev workflow improvements (like this command!)

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
    # Show top 3 candidates
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

## Step 3: Create Feature Branch

Once you've selected an item, create a dedicated branch:

```bash
# Replace ITEM_NAME with your chosen item (use kebab-case)
ITEM_NAME="your-item-name"
TRACK="track-name"

# Create and switch to feature branch
git checkout -b feature/${TRACK}/${ITEM_NAME}

echo "Created branch: feature/${TRACK}/${ITEM_NAME}"
echo "This keeps your work isolated from the P0 session on main."
```

## Step 4: Session Protocol

**For Secondary Sessions:**
1. Document your role at session start: "This is a **secondary session** working on [item] in the [track] track."
2. Commit frequently to your feature branch
3. Run targeted tests only (not full suite - let P0 session handle that)
4. When done, create a PR or note for merge

**For Research Sessions:**
1. No git branch needed (no code changes)
2. Document findings in scratch notes or memory
3. Can inform P0 session's approach

**For Tooling Sessions:**
1. Work on `.claude/`, `scripts/dev*.sh`, workflow files
2. Usually safe to work in parallel (different file set)

## Step 5: Pre-Merge Review

When your secondary work is complete, run a comprehensive review before merging:

```bash
# Ensure your branch is up to date
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

After reviews pass, the P0 session can merge your branch or you can create a PR.

## Conflict Resolution

If you accidentally touch files being modified by P0 session:
1. **Stop immediately** - don't commit conflicting changes
2. Coordinate with P0 session (or wait for it to complete)
3. Rebase after P0 merges

## Quick Reference

| Scenario | Action |
|----------|--------|
| P0 on data track | Work on ops, infra, frontend, or validation |
| P0 on frontend | Work on data, ops, or infra |
| No P0 set | Run `/start` instead to claim P0 |
| Same-track work needed | Wait for P0 to complete, or coordinate |

## Session End

1. Commit to your feature branch
2. Update pilot.json status (if item complete)
3. Leave merge to P0 session or create PR
4. Append to `claude-progress.txt`:
   ```
   ## Session N (Parallel): [item_name]
   **Track:** [track]
   **Branch:** feature/[track]/[item-name]
   **Status:** [complete/in-progress]
   [Brief summary]
   ```
