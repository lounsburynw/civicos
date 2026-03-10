# Session Critic

Review session work to ensure proper P0 assignment for next session.

## Context

Every Civic development session must end with exactly ONE P0 (immediate priority) item set for the next session. This ensures continuity and prevents priority inflation.

## Rules

1. **Exactly one P0** - No more, no less
2. **P0 is immediate** - Should be worked on next session
3. **Set before session ends** - Part of `/nextsesh` or manual update
4. **Clear artifact/test** - P0 must have clear completion criteria

## Check

Before session ends, verify:

1. **P0 count in launch.json?**
   - Run: `grep -c '"priority": 0' launch.json`
   - Should return exactly 1

2. **P0 item has clear criteria?**
   - Has `description` or `test_file` field
   - Status is `not_started`
   - Has actionable description

3. **Previous P0 resolved?**
   - Old P0 marked as `done`
   - Or explicitly carried over with reason

4. **Handoff prepared?**
   - `docs/next_session_prompt.md` updated
   - P0 item prominently featured

## Output

Respond with JSON:
```json
{
  "pass": boolean,
  "p0_count": number,
  "issues": ["list of P0 assignment issues"],
  "severity": "critical" | "warning" | "info",
  "current_p0": "item name or null"
}
```

## Examples

### FAIL - No P0 Set
```bash
$ grep '"priority": 0' launch.json
# (no output - no P0 assigned)
```

### FAIL - Multiple P0s
```bash
$ grep '"priority": 0' launch.json
    "priority": 0,
    "priority": 0,
# Two P0 items - violates rule
```

### PASS - Exactly One P0
```bash
$ grep '"priority": 0' launch.json
    "priority": 0,
# One P0 assigned, ready for next session

$ cat docs/next_session_prompt.md
# Recommended: [P0 item name]
**Priority:** P0 (IMMEDIATE)
...
```

## Verification Script

```python
import json

with open('launch.json') as f:
    data = json.load(f)

p0_items = []
skip = ['version', 'phase', 'last_updated', 'summary', 'category_order']

for cat, section in data.items():
    if cat in skip or not isinstance(section, dict):
        continue
    for item in section.get('items', []):
        if isinstance(item, dict) and item.get('priority') == 0 and item.get('status') == 'not_started':
            p0_items.append(item['name'])

if len(p0_items) == 0:
    print("FAIL: No P0 item set")
elif len(p0_items) > 1:
    print(f"FAIL: {len(p0_items)} P0 items: {p0_items}")
else:
    print(f"PASS: P0 = {p0_items[0]}")
```
