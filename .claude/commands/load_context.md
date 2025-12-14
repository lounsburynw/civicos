# Load Context for Current Work Area

Use the Task tool with `subagent_type="Explore"` to investigate the codebase area relevant to the current development phase and work item.

## Instructions

1. First, determine the current phase and next work item:

```bash
python3 -c "
import json

with open('phase.json') as f:
    phase = json.load(f)

current_phase = phase['current_phase']
checklist_file = phase['active_checklist']

print(f'Phase: {current_phase}')
print(f'Checklist: {checklist_file}')

with open(checklist_file) as f:
    checklist = json.load(f)

# Find next item based on phase
status_pending = {
    'implementation': 'not_implemented',
    'hardening': 'not_verified',
    'integration': 'not_tested',
    'pilot': 'not_ready'
}.get(current_phase, 'not_verified')

best = None
best_priority = 999

for category, items in checklist.items():
    if not isinstance(items, dict) or category in ['version', 'phase', 'derived_from', 'last_updated', 'target', 'location']:
        continue
    for subcategory, subitems in items.items():
        if not isinstance(subitems, dict) or subcategory in ['description', 'target']:
            continue
        for item, info in subitems.items():
            if isinstance(info, dict) and info.get('status') == status_pending:
                priority = info.get('priority', 99)
                if priority < best_priority:
                    best_priority = priority
                    best = {'item': item, 'category': category, 'subcategory': subcategory, 'info': info}

if best:
    print(f'Next item: {best[\"item\"]}')
    print(f'Area: {best[\"category\"]} > {best[\"subcategory\"]}')
    if 'test' in best['info']:
        print(f'Test: {best[\"info\"][\"test\"]}')
    if 'manual_step' in best['info']:
        print(f'Manual step: {best[\"info\"][\"manual_step\"]}')
"
```

2. Based on the output above, use the Task tool to spawn an Explore agent with this prompt structure:

```
Task(subagent_type="Explore", prompt="""
Explore the codebase to understand the current state for working on: [ITEM NAME]

Area: [CATEGORY] > [SUBCATEGORY]
Phase: [CURRENT PHASE]

Investigate:
1. Find the relevant source files for this area
2. Understand the current implementation state
3. Identify key patterns, dependencies, and architectural decisions
4. Note any existing tests related to this area
5. Look for TODOs or incomplete sections

Return a focused summary with:
- Key files involved (with line numbers for important sections)
- Current implementation status
- Dependencies and patterns to follow
- Suggested approach for completing this item
- Any potential blockers or considerations

Be thorough but concise - this summary will guide the implementation work.
""")
```

3. Review the agent's findings before starting implementation work.

## Why This Helps

- **Saves context**: The Explore agent reads files in its own context window
- **Returns focused summary**: Only key insights come back to main conversation
- **Discovers patterns**: Agent finds relevant code you might not know about
- **Speeds up ramp-up**: Get oriented quickly without manual file exploration
