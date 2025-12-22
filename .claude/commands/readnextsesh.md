# Read Next Session Context

Read the recommended context from the previous session and decide whether to accept it.

## Steps

1. **Check if context exists:**
```bash
cat docs/next_session_prompt.md 2>/dev/null || echo "No context document found. Run /start instead."
```

2. **Review the recommended context** - The previous session prepared this as a suggestion. You have full discretion to:
   - **Accept**: Follow the recommendations as written
   - **Modify**: Use it as a starting point but adjust based on current state
   - **Reject**: If outdated or no longer relevant, run `/start` for fresh prioritization

3. **Verify current state** before accepting:
```bash
# Check if P0 has changed
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
                print(f'Current P0: {item}')
"
```

4. **After session:** Clean up stale context documents to avoid confusion.

## Note

The handoff document is **recommended context**, not a mandate. The fresh session should use judgment based on:
- Has the P0 item changed?
- Is the recommended work still the highest priority?
- Are the file references still accurate?
