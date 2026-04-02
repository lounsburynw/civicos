# Refresh / Upsert Critic

Review code changes to data refresh, re-ingestion, and upsert logic to prevent data accumulation, silent data loss, and false change detection.

## Context

CivicOS uses temporal versioning for mutable data (municipal code, legislation). Refresh operations re-fetch data from external sources and update Postgres. These operations have caused production bugs:

- **Accumulation bug (Session 315+):** Full re-ingestion created duplicate "current" rows because `store_municipal_code` didn't close old versions for unchanged sections. 1,447 orphan rows accumulated in San Rafael.
- **Self-referential check bug:** A `check_for_update()` method compared a cached local file against itself and reported "unchanged" — preventing refresh from ever running.
- **Whitespace drift bug:** Minor whitespace differences between fetches made every section look "modified," triggering full table duplication on each refresh.
- **Truncated fetch → false removal:** A partial fetch (network timeout) makes missing sections appear "removed," and `store_municipal_code` closes them — silent data loss.

## Key Files

- `packages/civicos/src/civicos/storage/postgres_backend.py` — `store_municipal_code()`, `update_refresh_metadata()`
- `packages/civicos/src/civicos/_internal/legal/corpus/refresh.py` — `RefreshRunner`, `diff_sections()`, safety valves
- `packages/civicos/src/civicos/_internal/legal/corpus/municipal.py` — `MunicipalCodeCorpus.check_for_update()`
- `scripts/modal_ingest.py` — `refresh_municipal_code()`, `fetch_municipal_code()`

## Check

When reviewing changes to refresh, upsert, re-ingestion, or change detection logic:

### 1. Upsert idempotency: does re-running with identical data produce zero changes?

The most critical invariant. If you call `store_X()` twice with the same data, the second call must be a no-op. Common violations:

- **Missing content comparison:** Upserting without checking if content actually changed. Every row gets a new version.
- **Unnormalized comparison:** Using exact string equality (`==`) on text that may have whitespace, encoding, or line-ending drift between fetches. Must normalize (collapse whitespace, strip) before comparing.
- **Duplicate current rows:** Multiple rows for the same entity with `valid_to IS NULL`. The upsert must close or skip duplicates.

FAIL: `if new_text == existing_text:` (raw equality — whitespace drift breaks this)
PASS: `if normalize(new_text) == normalize(existing_text):` (normalized comparison)

### 2. Change detection: does the check actually reach the source?

A "check for update" must compare against the **live external source**, not against cached local data. If the check reads a local file/cache and compares it to a stored hash that was derived from the same local file, it will always report "unchanged."

FAIL: Read cached file → hash it → compare against stored hash of same cached file → "unchanged"
PASS: Call external API → get current publish date → compare against stored publish date → "changed" or "unchanged"

If lightweight source checks are impossible (e.g., Cloudflare-protected sites), the class should NOT implement a change detection interface. Return UNKNOWN or skip the check entirely — don't pretend.

### 3. Partial fetch protection: what happens if the source returns incomplete data?

External APIs can fail mid-stream (timeout, rate limit, network error). If the upsert function infers "removed" from absence (items in DB but not in incoming), a partial fetch causes mass false removals.

Guards required:
- **Safety valve on removals:** If >20% of existing items appear "removed," abort. Likely a truncated fetch.
- **Safety valve on modifications:** If >50% of existing items appear "modified," abort. Likely a normalization bug.
- **Both valves must be overridable** via `force=True` for genuine large-scale changes (code reorganization, publisher migration).

FAIL: Pass 800 sections to upsert that expects 2,364 → 1,564 sections falsely closed
PASS: Detect 66% removal rate → abort with error message → operator investigates

**Election-specific note:** Election data uses additive upserts (`store_elections` + `store_election_contests`), not replace-all semantics. A fetch returning 0 results does not delete existing data. However, fetch handlers MUST call `_check_partial_fetch()` from `election_fetch.py` to log warnings when fetch counts drop significantly — this helps operators detect source outages or data purges (especially for Clarity Elections, which purges old elections). The guard warns but does not block, since election sources legitimately shrink (e.g., Clarity purges old elections, SOS overwrites per-cycle).

### 4. Diff is for reporting, not for filtering?

When refreshing, the full incoming dataset should be passed to the storage layer. The storage layer handles its own internal diffing (content comparison, temporal versioning). A pre-storage diff (`diff_sections`) is useful for logging/reporting, but should NOT be used to filter what gets stored.

FAIL: `store_municipal_code(sections=diff["added"] + diff["modified"])` (missing sections look "removed")
PASS: `store_municipal_code(sections=all_incoming_sections)` (storage layer does its own diff)

### 5. Fingerprint stored after fetch?

After a successful fetch, the provider's fingerprint (publish date, supplement string, content hash) must be persisted in `refresh_metadata.last_fetch_hash`. If not stored, the next refresh can't do a cheap skip-check.

FAIL: `update_refresh_metadata(...)` without `last_fetch_hash=fingerprint`
PASS: `update_refresh_metadata(..., last_fetch_hash=corpus.get_fingerprint())`

### 6. Duplicate row defense?

Upsert functions should detect and close duplicate "current" rows (multiple rows with the same key and `valid_to IS NULL`). This is a defensive cleanup for prior bugs.

FAIL: `if sn not in current_map: current_map[sn] = row` (silently ignores duplicates)
PASS: Track duplicates, close them with `SET valid_to = now()`, log a warning

## Output

Respond with JSON:
```json
{
  "pass": boolean,
  "issues": ["list of specific refresh/upsert violations"],
  "severity": "critical" | "warning" | "info",
  "suggestions": ["fixes or improvements"]
}
```

## Examples

### FAIL - Raw String Comparison

```python
# BAD: Whitespace drift will cause full table duplication
if new_text == existing_text:
    continue  # skip unchanged
```

Output:
```json
{
  "pass": false,
  "issues": ["Content comparison uses raw string equality — whitespace/encoding drift between fetches will mark every section as 'modified', duplicating the entire table"],
  "severity": "critical",
  "suggestions": ["Normalize both sides: collapse whitespace, strip before comparing"]
}
```

### FAIL - Self-Referential Change Check

```python
# BAD: Reads local cache, compares against hash derived from same cache
def check_for_update(self, last_fingerprint):
    cached_text = open(self.cache_path).read()
    current_fp = hash(cached_text[:100])
    return current_fp == last_fingerprint  # Always True!
```

Output:
```json
{
  "pass": false,
  "issues": ["check_for_update compares cached local data against a stored hash of the same cached data — this will always report 'unchanged'. The check must reach the live external source."],
  "severity": "critical",
  "suggestions": ["Either make a live API call to check the source, or don't implement change detection (return UNKNOWN, let interval-based refresh handle it)"]
}
```

### FAIL - No Partial Fetch Guard

```python
# BAD: If API returns 800/2364 sections, 1564 get falsely removed
incoming = list(corpus.stream_sections())  # May be truncated!
storage.store_municipal_code(jurisdiction, incoming)  # Closes missing sections
```

Output:
```json
{
  "pass": false,
  "issues": ["No guard against truncated fetch — if the source API times out mid-stream, missing sections will be marked as removed. store_municipal_code closes sections not in incoming list."],
  "severity": "critical",
  "suggestions": ["Add safety valve: if >20% of existing sections appear removed, abort. Allow override with force=True."]
}
```

### PASS - Proper Refresh Pattern

```python
# GOOD: Normalized comparison, safety valves, full dataset to storage
incoming = list(corpus.stream_sections())
existing = storage.get_municipal_code(jurisdiction)
diff = diff_sections(existing, incoming)  # Reporting only

if diff["removed"] > len(existing) * 0.2:
    raise RefreshError("Too many removals — likely truncated fetch")

stored = storage.store_municipal_code(jurisdiction, incoming)  # Internal diff
storage.update_refresh_metadata(
    jurisdiction, "municipal_code",
    last_fetch_hash=corpus.get_fingerprint(),
    items_stored=stored,
)
```
