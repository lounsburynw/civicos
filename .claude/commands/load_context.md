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

status_pending = {
    'implementation': 'not_implemented',
    'hardening': 'not_verified',
    'integration': 'not_tested',
    'pilot': 'not_ready',
    'launch': 'not_started'
}.get(current_phase, 'not_started')

best = None
best_priority = 999

skip_keys = ['version', 'phase', 'last_updated', 'summary', 'category_order']
category_order = checklist.get('category_order', [k for k in checklist.keys()])

for category in category_order:
    if category in skip_keys or category not in checklist:
        continue
    section = checklist[category]
    if not isinstance(section, dict):
        continue
    if 'items' in section:
        for item_info in section['items']:
            if isinstance(item_info, dict) and item_info.get('status') == status_pending:
                priority = item_info.get('priority', 99)
                name = item_info.get('name', '?')
                if priority < best_priority:
                    best_priority = priority
                    best = {'item': name, 'category': category, 'info': item_info}
    else:
        for subcategory, subitems in section.items():
            if not isinstance(subitems, dict) or subcategory in ['description', 'target']:
                continue
            for item, info in subitems.items():
                if isinstance(info, dict) and info.get('status') == status_pending:
                    priority = info.get('priority', 99)
                    if priority < best_priority:
                        best_priority = priority
                        best = {'item': item, 'category': category, 'info': info}

if best:
    print(f'Next item: {best[\"item\"]}')
    print(f'Area: {best[\"category\"]}')
    if best['info'].get('test_file'):
        print(f'Test: {best[\"info\"][\"test_file\"]}')
    if best['info'].get('files'):
        print(f'Files: {best[\"info\"][\"files\"]}')
"
```

2. Based on the output above, use the Task tool to spawn an Explore agent with this prompt structure:

```
Task(subagent_type="Explore", prompt="""
Explore the codebase to understand the current state for working on: [ITEM NAME]

Area: [CATEGORY]
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
