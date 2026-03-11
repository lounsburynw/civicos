# Run Tests

Run the appropriate test tier based on the argument.

## Usage

- `/test` or `/test smoke` - Quick smoke test (~30s)
- `/test targeted` - Tests for current work item (1-5m)
- `/test full` - Full test suite before commit (~14m)
- `/test profile` - Full suite with timing info

## Instructions

Based on the argument provided (or default to smoke):

### smoke (default)
Run quick core API tests:
```bash
source civicos-env/bin/activate && pytest packages/civicos/tests/test_civicos.py -q --tb=short --override-ini="addopts="
```

### targeted
First, identify the current work item's test file from the active checklist, then run those tests:
```bash
python3 -c "
import json

with open('phase.json') as f:
    phase = json.load(f)

checklist_file = phase['active_checklist']
current_phase = phase['current_phase']

with open(checklist_file) as f:
    checklist = json.load(f)

status_pending = {
    'implementation': 'not_implemented',
    'hardening': 'not_verified',
    'integration': 'not_tested',
    'pilot': 'not_ready',
    'launch': 'not_started'
}.get(current_phase, 'not_started')

skip_keys = ['version', 'phase', 'last_updated', 'summary', 'category_order']
category_order = checklist.get('category_order', [k for k in checklist.keys()])

best = None
best_priority = 999

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
                if priority < best_priority:
                    best_priority = priority
                    best = item_info
    else:
        for subcat, subitems in section.items():
            if not isinstance(subitems, dict) or subcat in ['description', 'target']:
                continue
            for item, info in subitems.items():
                if isinstance(info, dict) and info.get('status') == status_pending:
                    priority = info.get('priority', 99)
                    if priority < best_priority:
                        best_priority = priority
                        best = info

if best:
    name = best.get('name', best.get('item', '?'))
    print(f'Item: {name}')
    tf = best.get('test_file')
    if tf:
        print(f'Test: {tf}')
    else:
        print('No test_file specified for this item.')
else:
    print('No pending items found.')
"
```

Then run the identified test file. If no test_file found, inform the user.

### full
Run complete test suite:
```bash
source civicos-env/bin/activate && pytest packages/civicos/tests/ -q --override-ini="addopts="
```

Wait for completion before reporting results. Do not poll excessively - check every 30-60 seconds if running in background.

### profile
Run full suite with timing analysis:
```bash
source civicos-env/bin/activate && pytest packages/civicos/tests/ -q --durations=20 --override-ini="addopts="
```

Report the 20 slowest tests to help identify optimization opportunities.

## After Running

Report:
1. Pass/fail count
2. Any failures with brief context
3. Time taken
4. For profile mode: list the slowest tests
