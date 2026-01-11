#!/bin/bash
cd /Users/nicolaslounsbury/projects/civic
source civic-env/bin/activate

echo "=========================================="
echo "CIVIC ENVIRONMENT CHECK"
echo "=========================================="

# Run SMOKE tests only (fast - ~30 sec)
# Full test suite should only run before commits
echo ""
echo "Running smoke tests (core API)..."
pytest packages/civic/tests/test_civic.py -q --tb=no

# Quick API check
echo ""
echo "Checking Civic API..."
python -c "from civic import Civic; c = Civic('san-rafael'); print('Ready:', len(c.whats_next()), 'meetings')"

# Show current phase
echo ""
echo "=========================================="
echo "CURRENT DEVELOPMENT PHASE"
echo "=========================================="
python3 -c "
import json
import os

with open('phase.json') as f:
    phase = json.load(f)

current = phase['current_phase']
checklist = phase['active_checklist']

print(f'Phase: {current.upper()}')
print(f'Checklist: {checklist}')

# Verify checklist exists
if os.path.exists(checklist):
    print(f'Status: Checklist found')
else:
    print(f'Status: WARNING - {checklist} not found!')

# Count items
if os.path.exists(checklist):
    with open(checklist) as f:
        cl = json.load(f)

    verified = 0
    not_verified = 0

    # Phase-specific status values
    phase_status = {
        'implementation': ('implemented', 'not_implemented'),
        'hardening': ('verified', 'not_verified'),
        'integration': ('passing', 'not_tested'),
        'pilot': ('ready', 'not_ready')
    }
    done_val, pending_val = phase_status.get(current, ('verified', 'not_verified'))

    def count_items(obj):
        done, pending = 0, 0
        if isinstance(obj, dict):
            status = obj.get('status')
            if status == done_val:
                done += 1
            elif status == pending_val:
                pending += 1
            for val in obj.values():
                sub_done, sub_pending = count_items(val)
                done += sub_done
                pending += sub_pending
        elif isinstance(obj, list):
            # Handle consolidated completed items format
            for item in obj:
                sub_done, sub_pending = count_items(item)
                done += sub_done
                pending += sub_pending
        return done, pending

    done, pending = count_items(cl)
    total = done + pending
    if total > 0:
        print(f'Progress: {done}/{total} items {done_val} ({100*done//total}%)')
        if pending > 0:
            print(f'Remaining: {pending} items {pending_val}')

    # Check for P0 items (at most 1 allowed)
    p0_items = []
    skip_keys = ['version', 'phase', 'derived_from', 'last_updated', 'target', 'location', 'summary', 'category_order', 'description']
    for cat_key, cat_val in cl.items():
        if cat_key in skip_keys or not isinstance(cat_val, dict):
            continue
        for sub_key, sub_val in cat_val.items():
            if not isinstance(sub_val, dict) or sub_key in skip_keys:
                continue
            for item_key, item_val in sub_val.items():
                if isinstance(item_val, dict) and item_val.get('status') == pending_val and item_val.get('priority') == 0:
                    p0_items.append(item_key)

    if len(p0_items) > 1:
        print(f'WARNING: {len(p0_items)} P0 items (should be at most 1)')
    elif len(p0_items) == 1:
        print(f'P0 (IMMEDIATE): {p0_items[0]}')
"
echo "=========================================="
