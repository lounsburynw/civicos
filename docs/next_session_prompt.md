# Recommended: Feedback Channel

**Priority:** P0 (IMMEDIATE)
**Area:** pilot_validation > user_readiness
**Date:** 2025-12-22

> This is recommended context from the previous session. Review and decide whether to accept, modify, or run `/start` for fresh prioritization.

## Context

Session 353 completed `data_dictionary` - updated docs/DATA_DICTIONARY.md with all core models (CityState, Meeting, AgendaItem, Decision, VoteTally, Issue, StaffRecommendation, PublicInput, LegalInstrument). Added source file locations, field types, and usage examples. (160/174 items ready, 92.0%)

**The opportunity:** Add a feedback mechanism for pilot users to report bugs and issues during the Jan 2026 pilot.

## Recommended Task

Implement a user feedback channel. Options to consider:

1. **GitHub Issues link** - Direct users to create issues on the repo
2. **Email contact** - Simple mailto link for feedback
3. **In-app form** - Embedded feedback form that sends to email/webhook

## Key Files to Reference

```
apps/civic-workspace/                    # Vue frontend
packages/civic-services/src/civic_services/servers/  # API server
docs/user_guides/GETTING_STARTED.md      # User-facing docs
```

## Suggested Approach

1. **Choose mechanism** - GitHub link is simplest, in-app form is best UX
2. **Add to frontend** - Feedback button/link in header or footer
3. **Update user docs** - Document how to report issues
4. **Test the flow** - Verify feedback reaches intended destination

## Success Criteria

- [ ] Users have a clear way to report issues
- [ ] Feedback mechanism documented in user guides
- [ ] pilot.json `feedback_channel` marked as ready

## Upcoming P1 Items (Newly Prioritized)

After feedback_channel, consider these data items (bumped from P3 to P1):

1. **marin_county_code** - Index relevant Marin County code sections (housing, land use)
2. **san_rafael_municipal_funding** - Research and index city funding programs (housing trust fund, inclusionary housing, general fund allocations)

## Pilot Progress

- 160/174 items ready (92.0%)
- 14 items remaining
- P0: feedback_channel (this item)
