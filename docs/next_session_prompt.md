# Recommended: voting_record_api

**Priority:** P0
**Area:** data_readiness > election_data
**Date:** 2026-01-03

> This is recommended context from Session 465. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 465 completed `roll_call_extraction` - parsing AYES/NOES/ABSENT vote patterns from meeting minutes. Combined with Session 464's `elected_officials_table`, all dependencies for voting record API are now ready.

**What's ready:**
- `extract_roll_call(text)` - Parses vote patterns into {"ayes": [], "noes": [], "absent": []}
- `extract_vote_tally(text)` - Returns complete VoteTally with motion attribution
- `normalize_vote_names(tally, officials)` - Maps names to official records
- `VoteTally.to_vote_results()` - Converts to {"Name": "yes/no/absent"} format
- `ElectedOfficial` model with `matches_name()` and storage methods
- 31 tests for roll call extraction, all passing

**What's missing:**
The `get_voting_record()` API method that connects everything:
```python
c.get_voting_record("Jane Smith", topic="housing")
# Returns VotingRecord with:
# - yes_count: 8
# - no_count: 2
# - absent_count: 1
# - decisions: [list of decision summaries with votes]
```

## Recommended Task

Implement `get_voting_record()` in the Civic API:

1. **Create VotingRecord dataclass:**
   ```python
   @dataclass
   class VotingRecord:
       official_name: str
       topic: Optional[str]
       yes_count: int
       no_count: int
       absent_count: int
       decisions: list[dict]  # Decision summaries with this official's vote

       @property
       def total_votes(self) -> int

       @property
       def yes_percentage(self) -> float
   ```

2. **Implement get_voting_record():**
   ```python
   def get_voting_record(
       self,
       official_name: str,
       topic: Optional[str] = None,
       start_date: Optional[str] = None,
       end_date: Optional[str] = None,
   ) -> VotingRecord:
       # 1. Find official by name (fuzzy match via elected_officials)
       # 2. Query decisions with vote_results containing this official
       # 3. Filter by topic if specified
       # 4. Aggregate yes/no/absent counts
       # 5. Return VotingRecord
   ```

3. **Storage query needed:**
   - `get_decisions_by_voter(official_name, topic, date_range)` - Find decisions where official voted
   - May need to add `vote_results` column to decisions table if not already present

## Key Files

- `packages/civic/src/civic/civic.py` - Add get_voting_record() method
- `packages/civic/src/civic/_internal/meetings/decision.py:62-75` - VoteTally.to_vote_results()
- `packages/civic/src/civic/storage/backend.py:1609-1669` - Elected officials storage methods
- `packages/civic/tests/test_roll_call_extraction.py` - Extraction tests to reference

## Sample Usage

```python
from civic import Civic

c = Civic("san-rafael")

# Get voting record for a council member on housing issues
record = c.get_voting_record("Maribeth Bushey", topic="housing")
print(f"Voted YES on {record.yes_percentage:.0%} of housing items")
print(f"Total votes: {record.total_votes} (Y:{record.yes_count} N:{record.no_count} A:{record.absent_count})")

# Show specific decisions
for d in record.decisions[:3]:
    print(f"- {d['title']}: {d['vote']}")
```

## Tests to Run

```bash
# Smoke tests
pytest packages/civic/tests/test_civic.py -q --override-ini="addopts="

# Roll call extraction (related)
pytest packages/civic/tests/test_roll_call_extraction.py -v -q --override-ini="addopts="

# Storage protocols (officials)
pytest packages/civic/tests/test_storage_protocols.py -k "elected" -v -q --override-ini="addopts="
```

## Success Criteria

- [ ] VotingRecord dataclass created
- [ ] `get_voting_record()` implemented in Civic class
- [ ] Queries decisions with populated vote_results
- [ ] Filters by topic when specified
- [ ] Returns accurate vote counts
- [ ] Unit tests for voting record API
- [ ] All existing tests passing

## Dependencies (Already Complete)

- `roll_call_extraction` (Session 465): extract_roll_call(), normalize_vote_names()
- `elected_officials_table` (Session 464): ElectedOfficial storage + fuzzy matching
