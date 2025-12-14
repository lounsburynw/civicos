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
source civic-env/bin/activate && pytest packages/civic/tests/test_civic.py -q --tb=short
```

### targeted
First, identify the current work item's test file from integration.json, then run those tests:
```bash
# Find test_file for current item from integration.json
python3 -c "
import json
with open('phase.json') as f:
    phase = json.load(f)
with open(phase['active_checklist']) as f:
    checklist = json.load(f)

# Find first not_tested item with test_file
for cat, items in checklist.items():
    if not isinstance(items, dict): continue
    for subcat, subitems in items.items():
        if not isinstance(subitems, dict): continue
        for item, info in subitems.items():
            if isinstance(info, dict) and info.get('status') == 'not_tested':
                if 'test_file' in info:
                    print(f'Item: {item}')
                    print(f'Test: {info[\"test_file\"]}')
                    break
"
```

Then run the identified test file. If no test_file found, inform the user.

### full
Run complete test suite:
```bash
source civic-env/bin/activate && pytest packages/civic/tests/ -q
```

Wait for completion before reporting results. Do not poll excessively - check every 30-60 seconds if running in background.

### profile
Run full suite with timing analysis:
```bash
source civic-env/bin/activate && pytest packages/civic/tests/ -q --durations=20
```

Report the 20 slowest tests to help identify optimization opportunities.

## After Running

Report:
1. Pass/fail count
2. Any failures with brief context
3. Time taken
4. For profile mode: list the slowest tests
