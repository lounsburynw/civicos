# Next Session: Phase 2 Action Methods

**Branch**: `feature/mcp-modularization`
**Session**: 125
**Goal**: Implement Phase 2 action methods (start_something, add_voice, follow, prepare)

---

## Session 124 Completed

### Wired Real Data to Query Methods

All query methods now return real data:

```python
from civic import Civic
c = Civic("city-san-rafael")

# ✅ These work with real data now:
c.what_applies("housing")      # Returns 6 CA state bills + 4 federal programs
c.what_happened("bike lanes")  # Returns [] (historical queries need implementation)
c.whats_next()                 # Returns meetings from StateManager
c.whos_with_me("traffic")      # Returns Community with issue count
c.coordinate("wildfire", "plan") # Returns 50 participants via LangGraph

# These still raise NotImplementedError (Phase 2):
c.start_something(...)
c.add_voice(...)
c.follow(...)
c.prepare(...)
```

### What Was Done

1. **StateManager Data Loading** - Created `scripts/load_events_to_state.py` to load extracted events JSON into StateManager database
2. **whats_next() Fixed** - Now correctly parses `meeting_datetime` and filters by date window
3. **what_applies() Wired** - Uses `legislative_context_cache.py` to return real CA state bills and federal programs
4. **coordinate() Verified** - LangGraph workflow runs successfully with 1,340 pre-loaded issues
5. **Integration Tests** - 13 tests passing in `packages/civic/tests/test_integration_san_rafael.py`

### Files Changed

- `packages/civic/src/civic/civic.py` - Fixed `whats_next()` date parsing
- `packages/civic/src/civic/context.py` - Rewrote to use `legislative_context_cache`
- `scripts/load_events_to_state.py` - New script to load events into StateManager
- `packages/civic/tests/test_integration_san_rafael.py` - New integration tests

---

## Session 125 Task: Phase 2 Action Methods

### Priority 1: Implement start_something()

Enable users to create initiatives:

```python
initiative = c.start_something(
    topic="traffic safety",
    title="Protected bike lane on 4th St",
    description="Request for protected bike infrastructure",
    location="4th Street corridor"
)
```

- Store in `issues` table (or new `initiatives` table)
- Return `Initiative` dataclass
- Auto-link to relevant meetings via topic matching

### Priority 2: Implement add_voice()

Allow adding voice to initiatives/items:

```python
voice = c.add_voice(
    item_type="initiative",  # or "agenda_item"
    item_id="init_123",
    stance="support",        # support, oppose, question
    comment="As a daily cyclist, I strongly support this..."
)
```

- Store in new `voices` table
- Track stance distribution per item
- Enable filtering voices by stance

### Priority 3: Implement follow()

Enable subscriptions:

```python
subscription = c.follow("meeting", "mtg_456")
```

- Store in `follows` table (may already exist)
- Support item types: meeting, initiative, topic, decision

### Priority 4: Implement prepare()

Generate preparation materials:

```python
prep = c.prepare("item_789")
```

- Aggregate: regulatory context (what_applies), historical (what_happened), allies (whos_with_me)
- Generate talking points (future: LLM)
- Return `Preparation` dataclass

---

## Definition of Done

- [ ] `c.start_something()` creates and returns Initiative
- [ ] `c.add_voice()` records voice and returns Voice
- [ ] `c.follow()` creates subscription and returns Subscription
- [ ] `c.prepare()` returns aggregated preparation materials
- [ ] Tests for all new methods

---

## Quick Reference

```bash
# Activate environment
source civic-env/bin/activate

# Test the package
python -c "from civic import Civic; c = Civic('city-san-rafael'); print(c.what_applies('housing'))"

# Run tests
cd packages/civic && python -m pytest tests/ -v

# Check StateManager data
python -c "from civic._internal.state import StateManager; s = StateManager('data/civic_state.db'); print(s.get_stats('city-san-rafael'))"

# Load more events
python scripts/load_events_to_state.py --jurisdiction san-rafael
```

---

## Current Package Status

| Package | Status | Notes |
|---------|--------|-------|
| `civic` | ✅ Query methods working | All Learn methods wired to real data |
| `civic-state` | ✅ Working | StateManager, 1,340 issues loaded |
| `civic-legal` | ✅ Working | Via legislative_context_cache |
| `civic-coordination` | ✅ Working | LangGraph workflows |
| `civic-enrichment` | ⚠️ Legacy | Superseded by civic-legal |
| `civic-extraction` | ✅ Scaffolded | Platform clients |

---

## Key Files

- `packages/civic/src/civic/civic.py` - Main Civic class (Phase 2 methods need implementation)
- `packages/civic/src/civic/context.py` - what_applies() implementation
- `packages/civic/src/civic/_internal/state/manager.py` - StateManager
- `packages/civic/tests/test_integration_san_rafael.py` - Integration tests
- `scripts/load_events_to_state.py` - Event data loader

---

*Session 124: Wired real data to query methods. Session 125: Implement action methods.*
