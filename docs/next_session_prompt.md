# Recommended: Extraction Audit Log

**Priority:** P0 (IMMEDIATE)
**Area:** data_standards > provenance
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 350 completed `ingestion_manifest` - created IngestionManifest dataclass with provenance tracking (source entries, validation summaries, checksums), Pipeline.run(save_manifest=True) integration, and CLI command for viewing history (157/174 items ready, 90.2%).

**The opportunity:** Build on IngestionManifest to create an extraction audit log:
- Track extraction runs with success/failure counts per platform
- Aggregate metrics across multiple runs
- Provide audit trail for data provenance

## Recommended Task

Add extraction audit logging that builds on IngestionManifest:

1. **AuditLog class** - aggregates extraction runs per platform
2. **Log entries** - track: platform, run count, success rate, last run, total records
3. **CLI command** - `civic-extract audit --jurisdiction city-san-rafael`

## Key Files to Reference

```
packages/civic-extraction/src/civic_extraction/manifest.py  # IngestionManifest
packages/civic-extraction/src/civic_extraction/cli/monitor.py  # Monitor patterns
packages/civic-extraction/tests/test_manifest.py  # Test patterns
```

## Suggested Approach

1. **Extend manifest module** - Add AuditEntry and AuditLog classes
2. **Aggregate manifests** - Build audit log from manifest history
3. **Add CLI** - `civic-extract audit` command for viewing
4. **Add tests** - Test aggregation and CLI functionality

## Tests to Run

```bash
# Manifest tests
pytest packages/civic-extraction/tests/test_manifest.py -v --override-ini="addopts="

# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] AuditLog class aggregates extraction runs per platform
- [ ] CLI command displays audit information
- [ ] Tests cover aggregation and CLI
- [ ] pilot.json `extraction_audit_log` marked as ready

## Pilot Progress

- 157/174 items ready (90.2%)
- 17 items remaining
- P0: extraction_audit_log (this item)
