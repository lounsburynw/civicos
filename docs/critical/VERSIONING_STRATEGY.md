# Versioning Strategy

**Last Updated:** 2025-12-11
**Phase:** Pilot
**Related:** [ROLLBACK_PROCEDURES.md](./ROLLBACK_PROCEDURES.md), [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)

This document defines the versioning and tagging strategy for the Civic platform. Git tags provide version traceability for deployments, enabling quick identification of which code was running at any point in time.

## Table of Contents

1. [Tag Format](#tag-format)
2. [When to Create Tags](#when-to-create-tags)
3. [Creating a Release Tag](#creating-a-release-tag)
4. [Version Coordination](#version-coordination)
5. [Finding Tags for Rollback](#finding-tags-for-rollback)
6. [Automated Tagging](#automated-tagging)

---

## Tag Format

### Production Deployments (Pilot Phase)

```
v{major}.{minor}.{patch}-pilot-{YYYYMMDD}
```

**Examples:**
- `v0.2.0-pilot-20260110` - First Jan 2026 deployment
- `v0.2.1-pilot-20260115` - Bug fix deployment
- `v0.3.0-pilot-20260201` - Feature release

### Components

| Component | Description | When to Increment |
|-----------|-------------|-------------------|
| **major** | Breaking changes | API incompatibility, schema migration required |
| **minor** | New features | New functionality, backward compatible |
| **patch** | Bug fixes | Bug fixes, documentation updates |
| **pilot** | Phase identifier | Fixed during pilot phase |
| **YYYYMMDD** | Deployment date | Automatically set on deployment |

### Historical Tags

Pre-pilot phases used a different format:
```
v2.{session}.0-{feature-slug}
```

Examples: `v2.87.0-hardening-complete`, `v2.85.0-phase-framework`

These tags are preserved for history but the new format applies going forward.

---

## When to Create Tags

### Always Tag

- **Production deployments**: Every deployment to Fly.io production
- **Milestone completions**: End of development sessions with significant changes
- **Before migrations**: Tag before any database schema changes

### Don't Tag

- Local development iterations
- Failed deployments (tag only after verification)
- Minor documentation-only changes (unless deployed)

---

## Creating a Release Tag

### Manual Process

1. **Verify everything is committed:**
   ```bash
   git status
   # Should show clean working tree
   ```

2. **Determine version number:**
   - Check latest tag: `git tag --list | tail -5`
   - Increment appropriately (major/minor/patch)

3. **Create annotated tag:**
   ```bash
   # Format: v{version}-pilot-{YYYYMMDD}
   git tag -a v0.2.0-pilot-20251211 -m "Pilot release: tagged_releases infrastructure

   Changes:
   - Added versioning strategy documentation
   - Created release tagging workflow
   - Added CHANGELOG.md
   - Integrated tags with rollback procedures

   Session: 257"
   ```

4. **Push tag to remote:**
   ```bash
   git push origin v0.2.0-pilot-20251211
   ```

### Tag Message Format

```
{Brief description of release}

Changes:
- {Change 1}
- {Change 2}
- {Change 3}

Session: {N}
Breaking: {Yes/No}
Migration: {Yes/No}
```

---

## Version Coordination

### Package Version vs Git Tags

| Location | Purpose | Update Frequency |
|----------|---------|------------------|
| `pyproject.toml` version | Package version for pip | Major releases only |
| Git tags | Deployment tracking | Every deployment |
| Fly.io versions (vN) | Platform versioning | Automatic per deploy |

**Current State:**
- `pyproject.toml`: `0.1.0` (alpha, pre-pilot)
- Git tags: `v0.2.x-pilot-*` (pilot phase)
- Fly.io: `vN` (auto-incremented)

### Syncing Versions

When making a significant release:

1. Update `packages/civic/pyproject.toml`:
   ```toml
   version = "0.2.0"
   ```

2. Create matching Git tag:
   ```bash
   git tag -a v0.2.0-pilot-20251211 -m "..."
   ```

This is not required for every deployment, only for version milestones.

---

## Finding Tags for Rollback

### By Date

Find what was running on a specific date:

```bash
# List tags with dates
git tag -l --format='%(refname:short) %(creatordate:short)' | grep pilot

# Find tag closest to a date
git log --tags --simplify-by-decoration --pretty="format:%ci %d" | grep "2026-01"
```

### By Fly.io Version

Correlate Fly.io's `vN` with Git tags:

```bash
# Get Fly.io deployment info
fly releases -a civic-api

# Find corresponding Git commit
# (Fly.io shows image digest; Git tag points to same commit)
```

### Quick Reference

```bash
# List all pilot tags
git tag --list "v*-pilot-*"

# Show tag details
git show v0.2.0-pilot-20251211

# Checkout a specific tag
git checkout v0.2.0-pilot-20251211
```

---

## Automated Tagging

### GitHub Actions Workflow

The `create-release.yml` workflow provides semi-automated tagging:

**Manual Trigger (Recommended):**
```bash
# Via GitHub UI: Actions > Create Release > Run workflow
# Or via CLI:
gh workflow run create-release.yml -f version=0.2.0 -f type=patch
```

**Auto-trigger (Post-deployment):**
- Disabled by default for pilot phase
- Can be enabled when deployment workflow is ready

### Workflow Inputs

| Input | Description | Example |
|-------|-------------|---------|
| `version` | Version number (without 'v' prefix) | `0.2.1` |
| `type` | Release type | `major`, `minor`, `patch` |
| `notes` | Release notes | "Bug fixes for..." |

---

## Integration with Rollback

When rolling back, the sequence is:

1. **Identify problematic deployment:**
   ```bash
   fly releases -a civic-api
   # Note: v5 deployed at 10:00, issues started
   ```

2. **Find corresponding Git tag:**
   ```bash
   git tag --list "v*-pilot-*" --sort=-creatordate | head -5
   # v0.2.1-pilot-20260115 <- problematic
   # v0.2.0-pilot-20260110 <- last known good
   ```

3. **Roll back code:**
   ```bash
   fly deploy -a civic-api --image registry.fly.io/civic-api:v4
   ```

4. **Document in rollback log:**
   ```bash
   echo "$(date): Rolled back from v0.2.1-pilot-20260115 to v0.2.0-pilot-20260110" >> rollback-log.txt
   ```

---

## Summary

| Task | Command |
|------|---------|
| List pilot tags | `git tag --list "v*-pilot-*"` |
| Create tag | `git tag -a v0.2.0-pilot-YYYYMMDD -m "message"` |
| Push tag | `git push origin v0.2.0-pilot-YYYYMMDD` |
| Show tag info | `git show v0.2.0-pilot-YYYYMMDD` |
| Delete tag (local) | `git tag -d v0.2.0-pilot-YYYYMMDD` |
| Delete tag (remote) | `git push --delete origin v0.2.0-pilot-YYYYMMDD` |
