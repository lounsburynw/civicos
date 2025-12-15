# Track A Pilot: 5th Avenue Decision Awareness

**Status**: Ready for execution
**Focus**: Nov 3, 2025 City Council decision on 5th Avenue Angle Parking
**Method**: Retrospective analysis - manual outreach to affected complainants

---

## Hypothesis Being Tested

> Residents who filed complaints about 5th Avenue issues did NOT know about the
> Nov 3 City Council decision affecting their street, and would have participated
> if they had.

**Success Criteria**:
- Awareness gap > 50% (residents didn't know about the decision)
- Coordination interest > 50% (residents would have wanted to coordinate)

---

## Pilot Population

### 5th Avenue Complainants

| Metric | Value |
|--------|-------|
| Total Issues | 42 |
| Unique Addresses | 35 |
| Status - Open | 19 (45%) |
| Status - Acknowledged | 22 (52%) |
| Status - Closed | 1 (2%) |

### Top Issue Types (Relevant to Parking Decision)

| Issue Type | Count | Relevance |
|------------|-------|-----------|
| Traffic Signals | 14 | High - parking affects traffic flow |
| Broken Parking Meters | 9 | **DIRECT** - parking infrastructure |
| Street Sweeping | 3 | Medium - parking affects sweeping |
| Street Signs/Markings | 2 | High - parking signage |

### Candidate Addresses for Outreach

**San Rafael 5th Ave addresses only** (filtered):

```
1000 5th Ave San Rafael, California, 94901
1101 5th Ave San Rafael, CA, 94901, USA
1230 5th Ave San Rafael, CA, 94901, USA
1375 5th Ave San Rafael, CA(lifornia), 94901
1400 5th Ave San Rafael, CA(lifornia), 94901
1467-1499 5th Ave San Rafael, CA, 94901, USA
1500 5th Ave San Rafael, California, 94901
1512 5th Ave San Rafael, CA, 94901, USA
1602-1614 5th Ave San Rafael, CA, 94901, USA
1628 5th Ave San Rafael, CA, 94901, USA
1701-1781 5th Ave San Rafael, CA, 94901, USA
1721 5th Ave San Rafael, California, 94901
1801-1831 5th Ave San Rafael, CA, 94901, USA
1818 5th Ave San Rafael, California, 94901
1821 5th Ave San Rafael, California, 94901
1903 5th Ave San Rafael, California, 94901
1964 5th Ave San Rafael, California, 94901
2316-2328 5th Ave San Rafael, California, 94901
5th Ave & B St San Rafael, California, 94901
5th Ave & California Ave San Rafael, CA, 94901, USA
5th Ave & G St San Rafael, CA, 94901, USA
5th Ave & Grand Ave San Rafael, CA, 94901, USA
5th Ave & Happy Ln San Rafael, CA, 94901, USA
5th Ave & Hetherton St San Rafael, CA(lifornia), 94901
5th Ave & Irwin St San Rafael, CA, 94901, USA
5th Ave & K St San Rafael, CA, 94901, USA
709 5th Ave. San Rafael, CA 94901, USA
819 5th Ave San Rafael, CA, 94901, USA
821 5th Ave San Rafael, CA, 94901, USA
835 5th Ave. San Rafael Ca 94901
900-916 5th Ave San Rafael, CA, 94901, USA
```

**Total**: 34 San Rafael addresses (1 Oakland outlier excluded)

---

## Outreach Protocol

### Phase 1: Pilot Email (5-10 residents)

**Subject**: Your 5th Avenue concern + recent City Council decision

**Template**:
```
Hi [Name if known],

On [date], you reported an issue at [address]:
"[Issue title/summary]"

I wanted to let you know that on November 3rd, the San Rafael City Council
voted on changes to 5th Avenue parking (angle parking conversion).

I'm researching how residents learn about city decisions that affect their
neighborhoods. Would you mind answering 2 quick questions?

1. Did you know about the Nov 3 parking decision before this email?
   [ ] Yes  [ ] No

2. If you had known, would you have wanted to:
   [ ] Attend the meeting
   [ ] Submit a written comment
   [ ] Coordinate with other 5th Ave residents
   [ ] None of the above

Reply with your answers - it takes 30 seconds and helps improve
civic engagement in San Rafael.

Thanks,
[Name]
San Rafael Civic Tech Project
```

### Phase 2: Analysis

After 5-10 responses:

```
IF awareness_gap > 50% AND coordination_interest > 50%:
  → Proceed with LangGraph automation
  → Foundation pitch preparation
  → Scale to more corridors

IF awareness_gap < 50% OR coordination_interest < 50%:
  → Interview respondents (why?)
  → Test different corridors (Lincoln Ave dumping, 3rd St traffic)
  → Reassess focal point
```

---

## Connection to Nov 3 Agenda

**Agenda Item**: 5th Avenue Angle Parking

The Nov 3, 2025 San Rafael City Council meeting included consideration of
converting parallel parking to angle parking on a portion of 5th Avenue.

**Relevance to Complainants**:
- Broken parking meter complaints → directly affected by parking changes
- Traffic signal complaints → parking changes affect traffic patterns
- Street sweeping → parking layout affects sweeping schedules

---

## MCP Server Integration

The `civic-issues` MCP server can be used to query pilot data:

```python
# Using MCP tools
from mcp_servers.civic_issues import get_street_issues_summary, query_issues

# Get pilot analysis
summary = get_street_issues_summary("city-san-rafael", "5th")
issues = query_issues("city-san-rafael", street="5th", limit=50)
```

This enables:
- Claude Desktop to query pilot data directly
- LangGraph workflows to access issues via MCP protocol
- Future AI integrations via standard MCP interface

---

## Next Steps

1. **Select 5-10 pilot candidates** from address list above
2. **Personalize outreach emails** with specific complaint details
3. **Track responses** in simple spreadsheet
4. **Analyze results** after 1-2 weeks
5. **Decide go/no-go** on LangGraph automation based on metrics

---

## Files Reference

- `apps/civic-mcp/civic_issues.py` - MCP server for issue queries
- `src/state_manager.py` - StateManager with 1,340 issues
- `src/coordination_graph.py` - LangGraph prototype (for Phase 2)
- `data/civic_state.db` - SQLite database with SeeClickFix data

---

*Created: Session 119 (2025-11-25)*
*Last Updated: Session 119*
