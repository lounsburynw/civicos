# Recommended: roll_call_extraction

**Priority:** P0
**Area:** data_readiness > election_data
**Date:** 2026-01-03

> This is recommended context from Session 464. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 464 completed `elected_officials_table` - the storage layer for elected officials with name variations for fuzzy matching. The elected_officials table is now populated with local officials (Mayor, Council Members, Supervisor) via `extract_elected_officials_to_storage()`.

**What's ready:**
- `ElectedOfficial` data model with `matches_name()` for fuzzy matching
- `store_elected_officials()` / `get_elected_officials()` / `get_official_by_name()` in storage
- `_generate_name_variations()` produces variants like "Councilmember Smith", "J. Smith"

**What's missing:**
Roll call votes are not yet extracted from meeting minutes. The decisions table has a `vote_results` field but it's empty.

## Recommended Task

Extract roll call votes from meeting minutes and populate `vote_results` in decisions:

1. **Find roll call patterns in minutes:**
   - Pattern: `AYES: Smith, Jones, Brown; NOES: Wilson; ABSENT: Davis`
   - Pattern: `Motion carried unanimously` (all council members = yes)

2. **Create extraction function:**
   ```python
   def extract_roll_call(text: str, officials: List[Dict]) -> Dict[str, str]:
       """
       Extract roll call vote from text.

       Args:
           text: Decision text or motion text from minutes
           officials: List from get_elected_officials()

       Returns:
           {"Jane Smith": "yes", "Bob Jones": "no", "Mary Wilson": "absent"}
       """
   ```

3. **Link to decision extraction pipeline:**
   - Add roll call extraction to decision processing
   - Populate `vote_results` field in stored decisions

## Key Files

- `packages/civic/src/civic/_internal/meetings/transcript.py` - Has partial `_parse_roll_call` (lines ~200-250)
- `packages/civic-extraction/src/civic_extraction/decision_extractor.py` - Decision extraction pipeline
- `packages/civic/src/civic/storage/backend.py:1609-1669` - `get_elected_officials()`, `get_official_by_name()`
- `packages/civic-extraction/src/civic_extraction/clients/representatives.py:842-879` - `_generate_name_variations()`

## Sample Data

Meeting minutes from San Rafael contain patterns like:
```
AYES: COUNCILMEMBERS: Bushey, Hill, Kertz, Vice Mayor Llorens Gulati, and Mayor Colin
NOES: COUNCILMEMBERS: None
ABSENT: COUNCILMEMBERS: None
```

## Suggested Approach

1. Explore existing `_parse_roll_call` in transcript.py to understand current state
2. Create robust regex patterns for AYES/NOES/ABSENT extraction
3. Use `get_elected_officials()` + `matches_name()` to normalize names
4. Add `extract_roll_call()` function to decision extractor
5. Write tests with sample minutes text

## Tests to Run

```bash
# Decision extractor tests
pytest packages/civic-extraction/tests/test_decision_extractor.py -v -q --override-ini="addopts="

# Storage protocols (officials)
pytest packages/civic/tests/test_storage_protocols.py -k "elected" -v -q --override-ini="addopts="

# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="
```

## Success Criteria

- [ ] `extract_roll_call()` function parses AYES/NOES/ABSENT patterns
- [ ] Names matched to elected_officials via fuzzy matching
- [ ] `vote_results` field populated in decisions
- [ ] Unit tests for roll call extraction
- [ ] All existing tests passing

## Dependencies (Already Complete)

- `election_integration` (Session 463): Elections storage mappers
- `elected_officials_table` (Session 464): Official storage with name variations
