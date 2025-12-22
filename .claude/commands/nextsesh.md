# Prepare Next Session Context

Write a **recommended context** document for the next Claude Code session. The next session (fresh, no memory) will review this and decide whether to accept, modify, or reject the recommendations.

## P0 Requirement

**CRITICAL: Before running /nextsesh, you MUST ensure exactly ONE P0 item exists in pilot.json.**

If no P0 item exists:
1. Identify the most important next task
2. Update `pilot.json` to set that item's priority to 0
3. Only then proceed with writing the handoff

## Guardrails

**BEFORE writing:**
1. Verify exactly one P0 item exists (run the check below)
2. Read `claude-progress.txt` (last 30 lines) to understand current state
3. Read any existing `docs/next_session_prompt.md` to avoid losing context

**WHEN writing:**
1. Be specific and actionable - the next session starts fresh with no memory
2. Include file paths with line numbers for key locations
3. The P0 item goes at the TOP with full context
4. Frame as recommendations, not mandates - the next session has discretion
5. Keep it concise - aim for <100 lines

**NEVER:**
- End session without exactly one P0 item set
- Overwrite without reading existing content first
- Omit P0 items from the context
- Include vague suggestions like "continue the work"

## Steps

1. **Verify exactly one P0 exists:**
```bash
python3 -c "
import json
import sys

with open('pilot.json') as f:
    cl = json.load(f)

skip = ['version', 'phase', 'derived_from', 'last_updated', 'target', 'location', 'summary', 'category_order', 'description']
p0_items = []

for cat, items in cl.items():
    if cat in skip or not isinstance(items, dict): continue
    for sub, subitems in items.items():
        if not isinstance(subitems, dict) or sub in skip: continue
        for item, info in subitems.items():
            if isinstance(info, dict) and info.get('status') == 'not_ready' and info.get('priority') == 0:
                p0_items.append({'name': item, 'cat': cat, 'sub': sub, 'info': info})

if len(p0_items) == 0:
    print('ERROR: No P0 item set!')
    print('You MUST set exactly one P0 item before running /nextsesh.')
    print('Update pilot.json to set priority: 0 on the most important next task.')
    sys.exit(1)
elif len(p0_items) > 1:
    print(f'ERROR: {len(p0_items)} P0 items found (should be exactly 1):')
    for p in p0_items:
        print(f'  - {p[\"name\"]}')
    print('Fix pilot.json to have exactly one P0 item.')
    sys.exit(1)
else:
    p = p0_items[0]
    print(f'P0 ITEM: {p[\"name\"]}')
    print(f'Area: {p[\"cat\"]} > {p[\"sub\"]}')
    print(f'Artifact: {p[\"info\"].get(\"artifact\", \"N/A\")}')
    print(f'Note: {p[\"info\"].get(\"note\", \"N/A\")}')
"
```

If this step fails, STOP and fix `pilot.json` before continuing.

2. **Read current state:**
```bash
tail -30 claude-progress.txt
```

3. **Read existing handoff (if any):**
```bash
cat docs/next_session_prompt.md 2>/dev/null || echo "No existing handoff"
```

4. **Write the recommended context** to `docs/next_session_prompt.md` with this structure:

```markdown
# Recommended: [Item Name]

**Priority:** P0/P1/P2
**Area:** [category > subcategory]
**Date:** [today's date]

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context
[2-3 sentences on what was accomplished and why this is recommended next]

## Recommended Task
[Clear description of what the previous session suggests doing]

## Key Files
- `path/to/file.py:123` - [what's there]
- `path/to/other.py:456` - [what's there]

## Suggested Approach
1. [First step]
2. [Second step]
3. [Third step]

## Tests to Run
```bash
pytest path/to/test.py -v
```

## Success Criteria
- [ ] [Criterion 1]
- [ ] [Criterion 2]
```

5. **Confirm the write:**
```bash
cat docs/next_session_prompt.md
```
