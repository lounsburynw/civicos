# Run Codebase Critics

Run LLM-based code review on staged changes to catch architectural issues.

## Usage

- `/critic` - Run all critics on staged changes
- `/critic pipeline` - Run only pipeline critic
- `/critic protocol` - Run only protocol critic
- `/critic architecture` - Run only architecture critic
- `/critic session` - Run only session critic

## Steps

1. **Get staged diff:**
```bash
git diff --staged
```

2. **Check for changes:**
If no staged changes, warn the user:
```
No staged changes. Stage your changes with `git add` first.
```

3. **Load relevant critics:**

Based on argument or all critics if none specified:
- `.critics/pipeline.critic.md` - For Pipeline changes
- `.critics/protocol.critic.md` - For storage/protocol changes
- `.critics/architecture.critic.md` - For package/import changes
- `.critics/session.critic.md` - For session end checks

4. **Run each critic:**

For each critic, analyze the staged diff against the critic's checks.
Output a structured review:

```
## Pipeline Critic
✅ PASS | ⚠️ WARNING | ❌ FAIL

Issues:
- [list any issues found]

Suggestions:
- [list any suggestions]

---
```

5. **Summary:**

```
## Summary

Critics run: 4
Passed: 3
Warnings: 1
Failed: 0

Ready to commit: Yes/No
```

## Auto-Detection

If no critic is specified, automatically select relevant critics based on changed files:

| File Pattern | Critics |
|--------------|---------|
| `**/pipeline*.py` | pipeline |
| `**/storage/*.py` | protocol |
| `**/sources/*.py` | protocol |
| Any package import changes | architecture |
| Session end (`/nextsesh`) | session |

## Notes

- Critics are defined in `.critics/*.critic.md`
- Each critic outputs JSON with pass/issues/severity
- Critical failures should block commit
- Warnings are advisory
