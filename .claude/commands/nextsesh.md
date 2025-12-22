# Prepare Next Session Context

Write a **recommended context** document for the next Claude Code session. The next session (fresh, no memory) will review this and decide whether to accept, modify, or reject the recommendations.

## Guardrails

**BEFORE writing:**
1. Read `claude-progress.txt` (last 30 lines) to understand current state
2. Check for P0 item in `pilot.json` - if exists, it MUST be prominently featured
3. Read any existing `docs/next_session_prompt.md` to avoid losing context

**WHEN writing:**
1. Be specific and actionable - the next session starts fresh with no memory
2. Include file paths with line numbers for key locations
3. If there's a P0 item, it goes at the TOP with full context
4. Frame as recommendations, not mandates - the next session has discretion
5. Keep it concise - aim for <100 lines

**NEVER:**
- Overwrite without reading existing content first
- Omit P0 items from the context
- Include vague suggestions like "continue the work"

## Steps

1. **Read current state:**
```bash
tail -30 claude-progress.txt
```

2. **Check for P0 item:**
```bash
python3 -c "
import json
with open('pilot.json') as f:
    cl = json.load(f)
skip = ['version', 'phase', 'derived_from', 'last_updated', 'target', 'location', 'summary', 'category_order', 'description']
for cat, items in cl.items():
    if cat in skip or not isinstance(items, dict): continue
    for sub, subitems in items.items():
        if not isinstance(subitems, dict) or sub in skip: continue
        for item, info in subitems.items():
            if isinstance(info, dict) and info.get('status') == 'not_ready' and info.get('priority') == 0:
                print(f'P0 ITEM: {item}')
                print(f'Area: {cat} > {sub}')
                print(f'Artifact: {info.get(\"artifact\", \"N/A\")}')
                print(f'Note: {info.get(\"note\", \"N/A\")}')
"
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
