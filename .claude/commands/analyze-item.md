# Deep Analysis of Specific Work Item

Perform a comprehensive analysis of a specific checklist item using subagents.

## Usage

When invoked with an item name (e.g., `/analyze-item vector_search_integration`), analyze that specific item. Otherwise, analyze the next priority item.

## Instructions

1. Identify the target item from the argument or find the next priority item:

```bash
python3 -c "
import json
import sys

# Check for argument (item name)
target_item = '$ARGUMENTS'.strip() if '$ARGUMENTS' else None

with open('phase.json') as f:
    phase = json.load(f)

current_phase = phase['current_phase']
checklist_file = phase['active_checklist']

with open(checklist_file) as f:
    checklist = json.load(f)

status_pending = {
    'implementation': 'not_implemented',
    'hardening': 'not_verified',
    'integration': 'not_tested',
    'pilot': 'not_ready'
}.get(current_phase, 'not_verified')

found = None
best_priority = 999

for category, items in checklist.items():
    if not isinstance(items, dict) or category in ['version', 'phase', 'derived_from', 'last_updated', 'target', 'location']:
        continue
    for subcategory, subitems in items.items():
        if not isinstance(subitems, dict) or subcategory in ['description', 'target']:
            continue
        for item, info in subitems.items():
            if isinstance(info, dict):
                # If target specified, look for it
                if target_item and target_item.lower() in item.lower():
                    found = {'item': item, 'category': category, 'subcategory': subcategory, 'info': info, 'status': info.get('status')}
                    break
                # Otherwise find next priority pending item
                elif not target_item and info.get('status') == status_pending:
                    priority = info.get('priority', 99)
                    if priority < best_priority:
                        best_priority = priority
                        found = {'item': item, 'category': category, 'subcategory': subcategory, 'info': info, 'status': info.get('status')}

if found:
    print(f'Item: {found[\"item\"]}')
    print(f'Status: {found[\"status\"]}')
    print(f'Category: {found[\"category\"]}')
    print(f'Subcategory: {found[\"subcategory\"]}')
    print(f'Info: {json.dumps(found[\"info\"], indent=2)}')
else:
    print('Item not found')
"
```

2. Launch parallel subagents for comprehensive analysis:

Use the Task tool to spawn THREE agents in a SINGLE message (parallel execution):

**Agent 1 - Code Explorer** (subagent_type="Explore"):
```
Explore the codebase for: [ITEM NAME]

Find:
- All source files related to this functionality
- Current implementation state
- Existing tests
- Related configuration

Return: File paths with key line numbers, implementation status, test coverage
```

**Agent 2 - Architecture Analyzer** (subagent_type="Explore"):
```
Analyze architectural context for: [ITEM NAME]

Examine:
- docs/critical/ for relevant architectural decisions
- How this item fits into the overall system
- Dependencies on other components
- Integration points

Return: Architectural constraints, patterns to follow, integration considerations
```

**Agent 3 - History Researcher** (subagent_type="Explore"):
```
Research development history for: [ITEM NAME]

Check:
- Recent git commits related to this area
- claude-progress.txt for previous work
- Any TODOs or FIXMEs in related code
- Previous session notes

Return: What's been done, what was attempted, known issues
```

3. Synthesize the findings from all three agents into an implementation plan.

## Output Format

After receiving agent results, summarize:

```
## Analysis: [Item Name]

### Current State
- Implementation status: [complete/partial/not started]
- Test coverage: [existing tests or gaps]
- Key files: [list with line numbers]

### Architecture Context
- Patterns to follow: [from docs/critical/]
- Dependencies: [what this relies on]
- Integration points: [where this connects]

### History & Context
- Previous work: [from git/progress]
- Known issues: [blockers, failed attempts]

### Recommended Approach
1. [Step 1]
2. [Step 2]
...

### Estimated Complexity
[Simple/Medium/Complex] - [brief justification]
```

## Benefits

- **Parallel exploration**: Three agents work simultaneously
- **Comprehensive coverage**: Code, architecture, and history
- **Minimal main context usage**: Only summaries return
- **Faster ramp-up**: Complete picture in one command
