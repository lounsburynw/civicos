# Changelog

All notable changes to the Civic platform are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Reversible schema migrations with `--rollback` and `--rollback-to` flags (Session 334)
- Post-ingestion validation report for data pipeline verification (Session 333)
- Platform-specific technical reference documentation (Session 332)
- Admin data management guide (Session 331)
- Admin troubleshooting guide (Session 330)
- Comprehensive FAQ for end users (Session 329)
- End-user feature documentation guide (Session 328)
- Pipeline monitor CLI for detecting overdue runs (Session 327)
- Legislative refresh CLI for weekly context updates (Session 326)
- SeeClickFix CLI for 311 issue refresh automation (Session 325)
- Transcription CLI for automated meeting transcription (Session 324)
- Audio download CLI for automated audio extraction (Session 323)
- YouTube discovery CLI for automated video discovery (Session 322)
- Meeting discovery CLI for automated meeting detection (Session 321)
- LLM-based codebase critics for code review (Session 320)
- City onboarding documentation guide (Session 319)
- This changelog maintenance process

### Changed
- Integrated `/critic` into `/commit` workflow for automated code review
- Refactored meeting_discovery_cron to civic-extract CLI

---

## [0.2.0-pilot-20251214] - 2025-12-14

**Initial Pilot Phase Release**

This release establishes version management infrastructure for the pilot phase,
enabling deployment traceability and rollback capabilities for Jan 2026 launch.

### Added
- **Package Reorganization**
  - `src/` → `packages/civic`, `civic-services`, `civic-extraction`
  - `frontend/` and `mcp_servers/` → `apps/`
  - Legal index relocation: `data/vectors/legal/`

- **Version Management**
  - Git tagging infrastructure with format: `v{major}.{minor}.{patch}-pilot-{YYYYMMDD}`
  - Release tagging workflow (`.github/workflows/create-release.yml`)
  - Versioning strategy documentation (`docs/critical/VERSIONING_STRATEGY.md`)

- **Deployment Infrastructure**
  - Fly.io hosting configuration (`fly.toml`, `fly.websocket.toml`)
  - Docker multi-stage builds for API and WebSocket servers
  - Comprehensive deployment guide (`docs/critical/DEPLOYMENT_GUIDE.md`)

- **Backup & Rollback**
  - Automated backup script (`scripts/backup.py`) with compression and checksums
  - Daily backup GitHub Actions workflow (2 AM UTC)
  - Pre-deployment backup procedures
  - Comprehensive rollback documentation (`docs/critical/ROLLBACK_PROCEDURES.md`)
  - 26 automated tests for backup/restore functionality

- **Monitoring**
  - Health check endpoints for API and WebSocket
  - Structured JSON logging with correlation IDs
  - Uptime monitoring guide (`docs/critical/UPTIME_MONITORING.md`)

- **Testing**
  - Parallel test execution with pytest-xdist
  - Test isolation fixtures for ChromaDB
  - 34 smoke tests, 158+ total tests

### Infrastructure
- **Hosting:** Fly.io (SJC region)
- **Cost:** ~$4.73/month estimated
- **Apps:** civic-api, civic-websocket

---

## Pre-Pilot Releases

Prior to the pilot phase, development used a different tagging scheme:
`v2.{session}.0-{feature-slug}`

### Notable Pre-Pilot Tags

| Tag | Description |
|-----|-------------|
| `v2.87.0-hardening-complete` | Hardening phase completion |
| `v2.86.0-framework-complete` | Phase framework implementation |
| `v2.85.0-phase-framework` | Development phase tracking |
| `v2.84.0-schema-reconciled` | Database schema unification |
| `v2.83.0-mcp-colocated` | MCP server integration |

For complete history, see: `git tag --list "v2.*"`

---

## Changelog Maintenance

### When to Update

Update CHANGELOG.md as part of the development workflow:

1. **During development**: Add notable changes to `[Unreleased]`
2. **Before tagging**: Move items from `[Unreleased]` to a new version section

### What to Include

| Section | Description | Examples |
|---------|-------------|----------|
| **Added** | New features | New CLI commands, API endpoints, documentation |
| **Changed** | Changes in existing functionality | Workflow changes, refactors with user impact |
| **Deprecated** | Features to be removed | APIs being phased out |
| **Removed** | Features removed | Deleted commands or endpoints |
| **Fixed** | Bug fixes | Resolved issues |
| **Security** | Vulnerability fixes | Security patches |

### What NOT to Include

- Internal refactoring without user-visible changes
- Minor documentation fixes
- Test additions or fixes (unless major test infrastructure)
- Developer tooling changes (unless they affect workflow)

### Creating a Release

```bash
# 1. Update CHANGELOG.md
# - Add new version header: ## [0.2.1-pilot-YYYYMMDD] - YYYY-MM-DD
# - Move [Unreleased] items to new version section
# - Keep [Unreleased] section for future changes

# 2. Commit the changelog update
git add CHANGELOG.md
git commit -m "Release v0.2.1-pilot-YYYYMMDD"

# 3. Create and push the tag
git tag -a v0.2.1-pilot-YYYYMMDD -m "Brief description"
git push origin v0.2.1-pilot-YYYYMMDD
```

See: [VERSIONING_STRATEGY.md](docs/critical/VERSIONING_STRATEGY.md)

---

[Unreleased]: https://github.com/nicolaslounsbury/civic/compare/v0.2.0-pilot-20251214...HEAD
[0.2.0-pilot-20251214]: https://github.com/nicolaslounsbury/civic/releases/tag/v0.2.0-pilot-20251214
