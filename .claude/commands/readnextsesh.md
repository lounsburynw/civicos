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
with open('launch.json') as f:
    cl = json.load(f)
skip = ['version', 'phase', 'last_updated', 'summary', 'category_order']
for cat, section in cl.items():
    if cat in skip or not isinstance(section, dict): continue
    for item in section.get('items', []):
        if isinstance(item, dict) and item.get('status') == 'not_started' and item.get('priority') == 0:
            print(f'Current P0: {item[\"name\"]}')
"
```

4. **After session:** Clean up stale context documents to avoid confusion.

## Note

The handoff document is **recommended context**, not a mandate. The fresh session should use judgment based on:
- Has the P0 item changed?
- Is the recommended work still the highest priority?
- Are the file references still accurate?
