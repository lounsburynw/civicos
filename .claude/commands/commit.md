# Commit Changes

Commit staged changes after running codebase critics. DO NOT include any author reference in the commit message (e.g., Anthropic, Claude Code, etc.).

## Steps

1. **Check for staged changes in both repos:**
```bash
git diff --staged --stat
git -C apps/civicos-openwebui-fork diff --staged --stat 2>/dev/null
git -C apps/civicos-openwebui-fork status --short 2>/dev/null
```

If no staged changes in either repo, prompt user to stage files first.

2. **Run critics on staged changes (civicos repo only):**

Run `/critic` to check for architectural issues. This analyzes the staged diff against:
- `.critics/pipeline.critic.md` - ETL pattern issues
- `.critics/protocol.critic.md` - Protocol conformance
- `.critics/architecture.critic.md` - Layer boundaries
- `.critics/security.critic.md` - Trust model integrity
- `.critics/jurisdiction.critic.md` - Jurisdiction isolation
- `.critics/data.critic.md` - ETL data quality
- `.critics/refresh.critic.md` - Refresh/upsert integrity
- `.critics/configuration.critic.md` - Config-driven behavior
- `.critics/docs.critic.md` - Documentation accuracy
- `.critics/session.critic.md` - Session hygiene

3. **Handle critic results:**

- If any critic returns **FAIL** with severity "critical": **STOP**. Show the issues and ask user how to proceed.
- If warnings only: Proceed with commit but note the warnings.
- If all pass: Proceed with commit.

4. **Generate commit message:**

Analyze the staged changes and create a concise commit message:
- First line: `Session N: brief_description`
- Body: What changed and why (if non-trivial)

5. **Commit civicos repo:**
```bash
git commit -m "Session N: description"
```

6. **Commit openwebui repo (if it has changes):**

If `apps/civicos-openwebui-fork` has staged or unstaged changes:
- Show the changes to the user and ask if they should be committed
- Stage and commit in the symlinked repo:
```bash
git -C apps/civicos-openwebui-fork add <files>
git -C apps/civicos-openwebui-fork commit -m "description"
git -C apps/civicos-openwebui-fork push
```

7. **Verify:**
```bash
git status
git -C apps/civicos-openwebui-fork status 2>/dev/null
```

## Notes

- Critics catch architectural issues that traditional linters miss
- Critical failures should be fixed before committing
- Warnings are advisory - use judgment on whether to address
- `apps/civicos-openwebui-fork` is a symlink to `~/projects/civicos-openwebui` (separate private repo)
- The openwebui repo has its own git history — commits there are independent
- Always push openwebui commits since the repo is private
