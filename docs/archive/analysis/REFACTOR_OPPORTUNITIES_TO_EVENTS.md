# Refactor: Rename "opportunities" to "events"

**Status**: ✅ **COMPLETED** (2025-10-06)

## Context

The current schema uses `Newsletter.opportunities[]` to represent civic meetings/events, but "events" is more intuitive naming since the data represents calendar events (City Council meetings, Planning Commission hearings, etc.).

**Current structure:**
- `Newsletter.opportunities[]` - array of meetings/events (confusing name)
- Each opportunity has `agenda_expansion.actionable_items[]` - the actual participation opportunities

**Desired structure:**
- `Newsletter.events[]` - array of meetings/events (clearer name)
- Each event has `agenda_expansion.actionable_items[]` - the actual participation opportunities
- Each event has `participation_mechanisms[]` - how to engage

## Scope

**Files affected:** ~87 files total
- 28 Python files (317 occurrences)
- 1 JavaScript file (3 occurrences)
- 56 JSON data files (93 occurrences)
- 2 HTML files (65 occurrences)

**Total occurrences:** ~478

## Implementation Plan

### Phase 1: Schema & Core Changes

1. **Update schema** (`civic-app-schema.json`):
   - Rename `Newsletter.opportunities` → `Newsletter.events`
   - Rename definition `CivicOpportunity` → `CivicEvent`
   - Update all references in schema documentation

2. **Update core extraction** (`src/civic_digest.py` - 87 occurrences):
   - Find/replace `opportunities` → `events`
   - Update all dictionary keys, variable names, comments
   - Test with single city extraction first

3. **Update schema adapter** (`src/civic_schema_adapter.py` - 6 occurrences):
   - Update field mappings
   - Ensure backward compatibility if needed

4. **Update agenda integration** (`src/agenda_integration.py` - 4 occurrences):
   - Update field references

### Phase 2: API Layer

5. **Update API server** (`src/civic_api_integrated.py` - 66 occurrences):
   - Update endpoint responses
   - Update query logic
   - **BREAKING CHANGE**: Document API version change

6. **Update conversation API** (`src/civic_api_conversation.py` - 9 occurrences):
   - Update conversational responses

7. **Update legacy API** (`src/civic_api.py` - 14 occurrences):
   - Update if still in use

### Phase 3: Frontend

8. **Update HTML frontend** (`frontend/mcp-civic-server/civic-conversational-OS.html` - 52 occurrences):
   - Update JavaScript to reference `events` instead of `opportunities`
   - Update DOM manipulation
   - Test in browser

9. **Update MCP server** (`frontend/mcp-civic-server/civic_server.py` - 3 occurrences):
   - Update tool responses

### Phase 4: Supporting Systems

10. **Update automation** (`src/automated_civic_refresh.py` - 11 occurrences):
    - Update batch processing logic

11. **Update monitoring** (`src/multi_platform_monitor.py` - 7 occurrences):
    - Update metric collection

12. **Update registry builder** (`scripts/update_city_registry.py` - 7 occurrences):
    - Update city status calculations

13. **Update platform clients**:
    - `src/legistar_client.py` (1 occurrence)
    - `src/civicplus_regional_discovery.py` (1 occurrence)
    - `src/cdp_client.py` (1 occurrence)

### Phase 5: Data Migration

14. **Migrate existing JSON files** (56 files in `data/events/` and `backup/`):
    ```bash
    # Create migration script
    python scripts/migrate_opportunities_to_events.py
    ```
    - Read each JSON file
    - Rename `opportunities` → `events`
    - Preserve all other data
    - Backup originals first

### Phase 6: Tests

15. **Update all test files** (~10 files):
    - `tests/test_phase2_automation.py` (7 occurrences)
    - `tests/test_frontend_integration.py` (12 occurrences)
    - `tests/test_integration_e2e.py` (18 occurrences)
    - `tests/test_civic_schema.py` (10 occurrences)
    - `tests/test_civic_bridging.py` (8 occurrences)
    - `tests/test_participation_reference_architecture.py` (6 occurrences)
    - `tests/test_meeting_id_parsing.py` (4 occurrences)
    - `tests/test_legistar_endpoint.py` (4 occurrences)
    - `tests/test_action_buttons.py` (1 occurrence)
    - `tests/test_phase2a_resilience_integration.py` (1 occurrence)
    - `tests/test_all_fixes.py` (1 occurrence)
    - `tests/test_frontend_browser.js` (3 occurrences)
    - `tests/integration.html` (13 occurrences)

16. **Run full test suite**:
    ```bash
    python tests/test_all_fixes.py
    python tests/test_phase2_automation.py
    python tests/test_integration_e2e.py
    ```

### Phase 7: Documentation

17. **Update documentation**:
    - `CLAUDE.md` - update all references
    - `docs/INTEGRATION_GUIDE.md` - update API examples
    - `docs/LEGISTAR_AGENDA_INTEGRATION.md` - update field names
    - `docs/COMMUNITY_CIVIC_PMF_STRATEGY.md` - update terminology
    - Any other docs that reference the schema

## Verification Checklist

After implementation:

- [ ] Schema validates correctly
- [ ] Single city extraction works (test with Berkeley)
- [ ] All city extraction works (`automated_civic_refresh.py --future-only`)
- [ ] API server starts and returns correct format
- [ ] Frontend displays events correctly
- [ ] Registry builder works
- [ ] All tests pass
- [ ] Existing JSON files migrated successfully
- [ ] No references to "opportunities" remain (grep check)
- [ ] Cost monitoring still works
- [ ] Documentation updated

## Migration Script Template

Create `scripts/migrate_opportunities_to_events.py`:

```python
#!/usr/bin/env python3
"""Migrate opportunities → events in JSON files"""

import json
import os
import shutil
from pathlib import Path

def migrate_file(filepath):
    """Migrate single JSON file"""
    # Backup original
    backup_path = f"{filepath}.backup"
    shutil.copy(filepath, backup_path)

    # Read and migrate
    with open(filepath, 'r') as f:
        data = json.load(f)

    # Rename field
    if 'opportunities' in data:
        data['events'] = data.pop('opportunities')

    # Write back
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"✅ Migrated: {filepath}")

def main():
    # Migrate all JSON files in data/events/
    json_files = list(Path('data/events').rglob('*.json'))

    print(f"Found {len(json_files)} JSON files to migrate")

    for filepath in json_files:
        migrate_file(str(filepath))

    print(f"\n✅ Migration complete: {len(json_files)} files")

if __name__ == '__main__':
    main()
```

## Rollback Plan

If something breaks:

1. **Restore from git**:
   ```bash
   git checkout -- .
   ```

2. **Restore JSON backups**:
   ```bash
   find data/events -name "*.backup" -exec bash -c 'mv "$0" "${0%.backup}"' {} \;
   ```

## Estimated Effort

- **Implementation**: 2-3 hours
- **Testing**: 1 hour
- **Documentation**: 30 minutes
- **Total**: 3.5-4.5 hours

## Recommended Timing

**Do this refactor when:**
- ✅ All 26 cities verified and stable in registry
- ✅ No active feature development
- ✅ Can dedicate focused time for testing
- ✅ Have git checkpoint to rollback if needed

**Don't do this when:**
- ❌ In middle of city verification (current status)
- ❌ About to demo to foundation
- ❌ Working on complaint-to-civic integration

## Notes

- This is a **breaking change** for any external API consumers
- Consider versioning the API (`/v1/events` vs `/v2/events`)
- The schema itself is correct - this is cosmetic for better DX
- Not blocking any current functionality
- Low risk if done carefully with testing

## Success Criteria

Refactor is successful when:
1. All extractions work identically to before
2. All tests pass
3. Frontend displays data correctly
4. No grep results for `\bopportunities\b` in Python/JS code
5. Data files all use `events` field
6. Documentation updated and accurate
