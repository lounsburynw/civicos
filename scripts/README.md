# City Status Registry Scripts

Operational visibility and duplicate detection for solo dev workflow.

## Quick Start

```bash
# Generate/update registry after extractions
python scripts/update_city_registry.py --report

# Incremental update (faster - only analyzes new/changed cities)
python scripts/update_city_registry.py --incremental --report

# View all cities
python scripts/city_status_dashboard.py

# View specific city detail
python scripts/city_status_dashboard.py oakland

# Filter by platform
python scripts/city_status_dashboard.py --platform Legistar

# Show only broken cities
python scripts/city_status_dashboard.py --broken
```

## Scripts

### `update_city_registry.py`

Analyzes all event files in `data/events/` and generates machine-readable registry with operational status, metrics, and duplicate detection.

**Usage**:
```bash
python scripts/update_city_registry.py                      # Full regeneration
python scripts/update_city_registry.py --report             # Full regen + human report
python scripts/update_city_registry.py --incremental        # Only analyze new/changed cities
python scripts/update_city_registry.py --incremental --report  # Incremental + report
python scripts/update_city_registry.py --city oakland       # Filter to single city
```

**Output**: `data/city_status_registry.json`

**What it tracks**:
- Platform detection (Legistar, CivicClerk, Granicus, HTML, Unknown)
- Parse rates and trends
- Extraction history (last 3 runs)
- Known limitations per platform
- Duplicate jurisdiction_id warnings
- Status classification: operational / degraded / broken

**Modes**:

- **Full regeneration** (default): Re-analyzes all cities from scratch (~30-40ms for 30 cities)
  - Use when: First run, major changes, troubleshooting

- **Incremental mode** (`--incremental`): Only re-analyzes cities with new event files (~20-30ms for 30 cities)
  - Use when: After single city extraction, automated workflows
  - Compares event file timestamps with registry data
  - Skips unchanged cities, preserves existing analysis
  - Falls back to full regeneration if no existing registry found

### `city_status_dashboard.py`

Interactive CLI for viewing city status and debugging.

**Usage**:
```bash
# Summary views
python scripts/city_status_dashboard.py                    # All cities
python scripts/city_status_dashboard.py --platform Legistar # Filter by platform
python scripts/city_status_dashboard.py --operational       # Show only operational
python scripts/city_status_dashboard.py --broken            # Show only broken

# Detail view (single city)
python scripts/city_status_dashboard.py oakland
python scripts/city_status_dashboard.py "el cerrito"  # Partial name match
```

**City detail view includes**:
- Current metrics (events, parse rate, items)
- Extraction history with timestamps
- Known limitations
- Platform config
- Debugging suggestions for broken cities

## Workflow

### After batch extraction:
```bash
# 1. Run automated refresh
python src/automated_civic_refresh.py --future-only

# 2. Update registry (use --incremental for faster updates)
python scripts/update_city_registry.py --incremental --report

# 3. Check for issues
python scripts/city_status_dashboard.py --broken
python scripts/city_status_dashboard.py --degraded
```

### After single city extraction:
```bash
# 1. Extract city
python src/civic_digest.py schema "<meeting-url>"

# 2. Incremental update (only re-analyzes this city)
python scripts/update_city_registry.py --incremental

# 3. Check result
python scripts/city_status_dashboard.py <city-name>
```

### When investigating a city:
```bash
# View detail
python scripts/city_status_dashboard.py campbell

# Check extraction history
ls -lht data/events/events_city-campbell*.json

# Re-run extraction
python src/civic_digest.py schema "<meeting-url>" --skip-agenda-parsing
```

## Registry Output Format

**`data/city_status_registry.json`**:
```json
{
  "last_updated": "2025-10-05T20:16:52Z",
  "total_cities": 30,
  "duplicate_count": 0,
  "cities": {
    "city-oakland": {
      "name": "Oakland",
      "jurisdiction_id": "city-oakland",
      "platform": "Legistar",
      "status": "operational",
      "last_extraction": "2025-10-04T13:34:27Z",
      "extraction_history": [...],
      "current_metrics": {
        "events": 15,
        "agendas_parsed": 13,
        "actionable_items": 56,
        "parse_rate": 0.87
      },
      "known_limitations": [],
      "notes": "Best performing city - consistent agenda publication"
    }
  },
  "platform_summary": {
    "Legistar": {
      "cities": 6,
      "avg_parse_rate": 0.80,
      "total_items": 116,
      "status": "excellent"
    }
  }
}
```

## Status Classifications

- **operational**: Events extracting, parse rate acceptable for platform
- **degraded**: Low parse rate (except CivicClerk, which is expected)
- **broken**: Platform detection failed or zero events found

## Platform-Specific Notes

**Legistar** (6 cities, 80% avg parse):
- Excellent: API-based, consistent agenda publication
- Expect 70%+ parse rates

**CivicClerk** (15 cities, 12% avg parse):
- Operational: Low parse rates are NORMAL
- Agendas not published until closer to meeting dates
- Parse rate improves over time

**Granicus** (2 cities, 34% avg parse):
- ViewPublisher requires view_id parameter
- May need manual URL inspection per city

**HTML** (1 city, 100% parse):
- Custom per-city parsers
- Not generalized

**Unknown** (6 cities):
- Platform detection failed
- Needs manual URL inspection and config updates

## Performance

**Registry Update Speed** (30 cities):

| Mode | Time | Use Case |
|------|------|----------|
| Full regeneration | ~30-40ms | First run, troubleshooting, major changes |
| Incremental (0 changes) | ~20-30ms | No new extractions (skips all cities) |
| Incremental (1 change) | ~25-35ms | Single city extraction |

**Scalability**:
- Current (30 cities): Difference negligible (~10ms savings)
- At 100 cities: Full ~100ms, Incremental ~30ms (~70ms savings)
- At 500 cities: Full ~500ms, Incremental ~50ms (~450ms savings)

**Recommendation**: Use `--incremental` by default in automated workflows. Performance gains increase with city count.

## Duplicate Detection

The registry automatically detects duplicate jurisdiction extractions (e.g., `city-milpitas` vs `city-milpitasca`).

**Resolution**:
1. Check `duplicate_warning` field in registry
2. Verify correct jurisdiction_id in `automated_civic_refresh.py` CITY_CONFIGS
3. Delete incorrect duplicate files
4. Re-run extraction with corrected config

## Debugging Broken Cities

Dashboard provides debugging suggestions for broken cities:

```bash
python scripts/city_status_dashboard.py campbell
```

Output includes:
```
--- 🔧 DEBUGGING SUGGESTIONS ---
1. Check source URL accessibility:
   curl -I 'https://...'
2. Test extraction manually:
   python src/civic_digest.py schema '<meeting_url>' --skip-agenda-parsing
3. Inspect platform HTML structure
4. Check automated_civic_refresh.py CITY_CONFIGS
```
