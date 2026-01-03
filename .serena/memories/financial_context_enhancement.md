# Financial Context Enhancement

**Date**: 2026-01-03
**Status**: Proposed

## Summary

Enhance coordination methods (e.g., `whats_next()`, `prepare()`) to include financial stakes, creating a direct link between "what's happening" and "what money is involved."

## Rationale

Financial data is uniquely powerful for civic engagement:
- Non-partisan (everyone cares about tax money)
- Connects abstract meetings to concrete stakes
- Creates accountability when combined with coordination

## Proposed API Enhancement

```python
# Current: whats_next returns meetings
c.whats_next()  
# → [Meeting: Budget Hearing, Tuesday 7pm]

# Enhanced: Include financial stakes
c.whats_next(include_financial_context=True)
# → [Meeting: Budget Hearing, Tuesday 7pm
#      Stakes: $180M budget adoption
#      Key changes: +$2M homelessness, -$500K parks
#      Your interests: You follow "parks" - this affects you]

# Also enhance prepare()
c.prepare(meeting, include_budget_context=True)
# → Includes relevant budget line items in preparation materials
```

## Implementation Notes

This doesn't require new data sources - it connects existing:
- Budget extraction → `budget_amount_cents` per department
- Meeting extraction → agenda items
- User interests → followed topics

The join is: agenda item keywords → budget line items → dollar amounts

## Data Sources Available

| Source | Status | Financial Data |
|--------|--------|----------------|
| Budget PDFs | Extracted | Line-item amounts |
| ACFR | Extracted (new) | Audited actuals |
| SCO Revenue | Working | Intergovernmental sources |
| FAC | Working | Federal expenditures |
| USAspending | Working | Federal awards |

## Priority

Medium - valuable enhancement but not blocking pilot. Consider for post-pilot iteration.
