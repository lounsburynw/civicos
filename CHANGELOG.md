# Changelog

All notable changes to the Civic platform are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Release tagging workflow (`.github/workflows/create-release.yml`)
- Versioning strategy documentation (`docs/critical/VERSIONING_STRATEGY.md`)
- This CHANGELOG.md file

---

## [v0.2.0-pilot-20251211] - 2025-12-11

**First Pilot Phase Release**

This release marks the transition to the pilot phase with comprehensive deployment
and rollback infrastructure ready for Jan 2026 launch.

### Added
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

- **Version Management**
  - Git tagging strategy for deployments
  - Release creation workflow
  - Version coordination documentation

- **Monitoring**
  - Health check endpoints for API and WebSocket
  - Structured JSON logging with correlation IDs
  - Uptime monitoring guide (`docs/critical/UPTIME_MONITORING.md`)

- **Testing**
  - Parallel test execution with pytest-xdist
  - Test isolation fixtures for ChromaDB
  - 31 smoke tests, 158+ total tests

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

## Release Process

1. Create tag: `git tag -a v{version}-pilot-{YYYYMMDD} -m "message"`
2. Push tag: `git push origin v{version}-pilot-{YYYYMMDD}`
3. Update this CHANGELOG

Or use the automated workflow:
- GitHub Actions > Create Release > Run workflow

See: [VERSIONING_STRATEGY.md](docs/critical/VERSIONING_STRATEGY.md)
