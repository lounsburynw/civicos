# Commit Changes

Commit staged changes after running codebase critics. DO NOT include any author reference in the commit message (e.g., Anthropic, Claude Code, etc.).

## Steps

1. **Check for staged changes:**
```bash
git diff --staged --stat
```

If no staged changes, prompt user to stage files first.

2. **Run critics on staged changes:**

Run `/critic` to check for architectural issues. This analyzes the staged diff against:
- `.critics/pipeline.critic.md` - ETL pattern issues
- `.critics/protocol.critic.md` - Protocol conformance
- `.critics/architecture.critic.md` - Layer boundaries
- `.critics/session.critic.md` - Session hygiene

3. **Handle critic results:**

- If any critic returns **FAIL** with severity "critical": **STOP**. Show the issues and ask user how to proceed.
- If warnings only: Proceed with commit but note the warnings.
- If all pass: Proceed with commit.

4. **Generate commit message:**

Analyze the staged changes and create a concise commit message:
- First line: `Session N: brief_description`
- Body: What changed and why (if non-trivial)

5. **Commit:**
```bash
git commit -m "Session N: description"
```

6. **Verify:**
```bash
git status
```

## Notes

- Critics catch architectural issues that traditional linters miss
- Critical failures should be fixed before committing
- Warnings are advisory - use judgment on whether to address
