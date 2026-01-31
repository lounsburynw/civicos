# Documentation Critic

Review documentation files for accuracy, staleness, and bloat.

## Context

CivicOS is designed for federated collaboration—multiple contributors (human and AI) working across jurisdictions. Accurate documentation is infrastructure, not polish:

- **CLAUDE.md** is read by AI at session start; wrong instructions break workflows
- **README.md** is the onboarding path for human contributors; broken setup bounces newcomers
- **docs/** accumulates bloat over time; orphaned docs cause confusion

## Key Files

- `CLAUDE.md` - AI session instructions, slash commands, architecture overview
- `README.md` - Human onboarding, setup instructions, project overview
- `docs/critical/` - Essential architecture and operations docs
- `.critics/` - Code review prompts including this one

## Check

### Tier 1: Operational Docs (CLAUDE.md, README.md)

Run when these files are in the changeset.

**1. Explicit paths exist?**

Only check paths that include directory separators (explicit paths), not bare filenames in tables:
- `docs/critical/DEPLOYMENT_GUIDE.md` → check exists
- `packages/civicos/src/civicos/civicos.py` → check exists
- `DEPLOYMENT_GUIDE.md` (bare filename in table) → skip, implied prefix

**2. Slash commands match `.claude/commands/`?**

Commands documented with `/command` syntax should have implementation files:
```bash
# Extract /command patterns and verify .claude/commands/{command}.md exists
for cmd in $(grep -oE '`/[a-z-]+`' CLAUDE.md | tr -d '`/' | sort -u); do
  [ ! -f ".claude/commands/${cmd}.md" ] && echo "Missing: /${cmd}"
done
```

**3. Directory structure paths exist?**

Paths in "Project Structure" code blocks should exist:
```bash
# Extract directory paths from structure blocks
grep -E '^\s*(├──|└──)\s+[a-z-]+/' README.md | grep -oE '[a-z-]+/' | while read d; do
  [ ! -d "${d%/}" ] && echo "Missing directory: $d"
done
```

**4. Critics table matches files?**

The "Codebase Critics" table in CLAUDE.md should match `.critics/*.critic.md`:
```bash
# Compare documented critics to actual files
documented=$(grep -oE '[a-z]+\.critic\.md' CLAUDE.md | sort -u)
actual=$(ls .critics/*.critic.md 2>/dev/null | xargs -n1 basename | sort)
diff <(echo "$documented") <(echo "$actual")
```

### Tier 2: Bloat Detection (docs/)

Run periodically or via `/critic docs --full`.

**1. Orphaned docs?**

Docs not referenced by full path from CLAUDE.md, README.md, or other docs:
```bash
# Find docs not linked from anywhere (check full paths, not basenames)
for f in $(find docs -name "*.md" -not -path "docs/archive/*"); do
  if ! grep -rq "$f" CLAUDE.md README.md docs/ --include="*.md" 2>/dev/null; then
    echo "Orphaned: $f"
  fi
done
```

**2. Dead internal links?**

Markdown links to docs that don't exist:
```bash
# Extract markdown links and verify targets
grep -rohE '\]\([^)]+\.md\)' docs/*.md docs/**/*.md 2>/dev/null | \
  tr -d '()' | sed 's/.*]//' | sort -u | while read link; do
    # Handle relative links
    [ ! -f "$link" ] && [ ! -f "docs/$link" ] && echo "Dead link: $link"
  done
```

## Output

Respond with JSON:
```json
{
  "pass": boolean,
  "issues": ["list of documentation issues"],
  "severity": "critical" | "warning" | "info",
  "suggestions": ["actionable fixes"]
}
```

### Severity Levels

| Severity | Meaning | Examples |
|----------|---------|----------|
| **critical** | Blocks onboarding or breaks workflows | Missing explicit path in Quick Start, broken setup command |
| **warning** | Causes confusion but workarounds exist | Missing slash command, outdated critics table |
| **info** | Cleanup opportunity | Orphaned doc, archive candidate |

## Examples

### FAIL - Missing Explicit Path (critical)

CLAUDE.md contains:
```markdown
See `docs/critical/DEPLOYMENT_GUIDE.md` for production setup.
```

But `docs/critical/DEPLOYMENT_GUIDE.md` doesn't exist.

```json
{
  "pass": false,
  "issues": ["docs/critical/DEPLOYMENT_GUIDE.md referenced but doesn't exist"],
  "severity": "critical",
  "suggestions": ["Create the file or update the reference"]
}
```

### FAIL - Slash Command Mismatch (warning)

CLAUDE.md lists `/deploy` but `.claude/commands/deploy.md` doesn't exist.

```json
{
  "pass": false,
  "issues": ["/deploy documented but .claude/commands/deploy.md missing"],
  "severity": "warning",
  "suggestions": ["Remove /deploy from docs or create the command file"]
}
```

### FAIL - Orphaned Critical Doc (warning)

`docs/critical/OLD_FEATURE.md` exists but isn't referenced anywhere.

```json
{
  "pass": false,
  "issues": ["docs/critical/OLD_FEATURE.md is orphaned"],
  "severity": "warning",
  "suggestions": ["Move to docs/archive/ or add reference from CLAUDE.md"]
}
```

### PASS - Docs Accurate

```json
{
  "pass": true,
  "issues": [],
  "severity": "info",
  "suggestions": []
}
```

## Verification Script

```python
#!/usr/bin/env python3
"""Tier 1 documentation verification.

Run from repo root: python .critics/docs_verify.py
"""
import os
import re
import json
from pathlib import Path


def check_explicit_paths(content: str, filename: str) -> list[str]:
    """Check paths that include directory separators (explicit paths only)."""
    issues = []

    # Match backtick-quoted paths containing / and ending with common extensions
    # This excludes bare filenames in tables which have implied prefixes
    pattern = r'`([a-zA-Z0-9_./+-]+/[a-zA-Z0-9_.+-]+\.(py|json|md|sh|ts|vue|toml|yaml|yml))`'
    paths = re.findall(pattern, content)

    for path, _ in paths:
        # Skip URLs
        if path.startswith('http'):
            continue
        # Skip obvious code patterns
        if '=' in path or path.startswith('pip') or path.startswith('pytest'):
            continue
        # Check if file exists
        if not os.path.exists(path) and not os.path.exists(path.lstrip('./')):
            issues.append(f"{filename}: Missing path: {path}")

    return issues


def check_slash_commands(content: str) -> list[str]:
    """Check that documented slash commands have implementation files."""
    issues = []
    commands_dir = Path('.claude/commands')

    if not commands_dir.exists():
        return issues

    available = {f.stem for f in commands_dir.glob('*.md')}
    builtin = {'help', 'clear', 'compact', 'config', 'doctor', 'init', 'login', 'logout', 'mcp', 'memory', 'model', 'permissions', 'pr-review-toolkit', 'resume', 'review', 'status', 'vim'}

    # Extract /command patterns (must be backtick-quoted to be a documented command)
    listed = set(re.findall(r'`/([a-z][-a-z]*)`', content))

    for cmd in listed:
        if cmd not in available and cmd not in builtin:
            issues.append(f"CLAUDE.md: /{cmd} documented but .claude/commands/{cmd}.md missing")

    return issues


def check_directory_structure(content: str) -> list[str]:
    """Check that directories in Project Structure blocks exist."""
    issues = []

    # Find directories in tree-style structure (├── or └── followed by dir/)
    dirs = re.findall(r'[├└]── ([a-z][-a-z0-9]*)/\s', content)

    for d in dirs:
        # Check common locations
        if not os.path.isdir(d) and not os.path.isdir(f'packages/{d}') and not os.path.isdir(f'apps/{d}'):
            issues.append(f"README.md: Directory '{d}/' in structure but doesn't exist")

    return issues


def check_critics_table(content: str) -> list[str]:
    """Check that critics table matches actual .critic.md files."""
    issues = []
    critics_dir = Path('.critics')

    if not critics_dir.exists():
        return issues

    # Get documented critics from table
    documented = set(re.findall(r'`([a-z]+\.critic\.md)`', content))

    # Get actual critic files
    actual = {f.name for f in critics_dir.glob('*.critic.md')}

    # Check for documented but missing
    for doc in documented:
        if doc not in actual:
            issues.append(f"CLAUDE.md: {doc} in table but file missing")

    # Check for actual but undocumented (warning only)
    for act in actual:
        if act not in documented:
            issues.append(f"CLAUDE.md: {act} exists but not in critics table")

    return issues


def main():
    all_issues = []

    # Check CLAUDE.md
    if os.path.exists('CLAUDE.md'):
        with open('CLAUDE.md') as f:
            claude_content = f.read()
        all_issues.extend(check_explicit_paths(claude_content, 'CLAUDE.md'))
        all_issues.extend(check_slash_commands(claude_content))
        all_issues.extend(check_critics_table(claude_content))

    # Check README.md
    if os.path.exists('README.md'):
        with open('README.md') as f:
            readme_content = f.read()
        all_issues.extend(check_explicit_paths(readme_content, 'README.md'))
        all_issues.extend(check_directory_structure(readme_content))

    # Determine severity
    severity = "info"
    if all_issues:
        severity = "warning"
        if any("Quick Start" in i or "setup" in i.lower() or "Missing path" in i for i in all_issues):
            severity = "critical"

    result = {
        "pass": len(all_issues) == 0,
        "issues": all_issues,
        "severity": severity,
        "suggestions": []
    }

    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == '__main__':
    exit(main())
```

## Integration with /critic

When running `/critic` on a changeset that includes `.md` files:

1. **Tier 1 runs automatically** if CLAUDE.md or README.md changed
2. **Tier 2 runs on request** via `/critic docs --full`

The critic should be fast for Tier 1 (seconds) to not slow down commits.

## Tier 2 Invocation

To run full bloat detection:
```bash
/critic docs --full
```

Or manually:
```bash
# Find orphaned docs
for f in $(find docs -name "*.md" -not -path "docs/archive/*"); do
  grep -rq "$f" CLAUDE.md README.md docs/ --include="*.md" 2>/dev/null || echo "Orphaned: $f"
done
```
