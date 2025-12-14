# Platform Research Archive

This directory contains research and setup guides for platforms not currently used in the production architecture.

## Contents

- `CIVIC_DATA_INGESTION_STRATEGY.md` - Early multi-platform ingestion strategy (Oct 5, 2024) - outdated city counts

**Moved to active docs:**
- `CDP_ACCESS_GUIDE.md` → `docs/platforms/` (valid platform integration guide)
- `OPEN_STATES_SETUP.md` → `docs/guides/` (useful setup guide for legislative work)

## Why Archived?

### Not Currently Used

**CDP (Council Data Project)**: Firestore-based civic video archive platform
- Discovered anonymous access pattern (no credentials required)
- Not integrated into current production architecture
- Focused on video transcripts, not agenda extraction

**Open States API**: Legislative metadata verification service
- Free API for bill verification across all 50 states
- Not actively used (legislative context uses cached data from LegiScan)
- Valuable for future legislative metadata verification

**Civic Data Ingestion Strategy**: Outdated city counts and platform distribution
- Document says "26 unique cities" (matches current, but details are outdated)
- Platform distribution has changed since Oct 5
- Information now maintained in `CLAUDE.md` production status section

## Current Platform Architecture

See active documentation:
- **`RESILIENCE_STRATEGY.md`** - Current multi-platform architecture (Legistar, CivicClerk, Granicus, HTML)
- **`LEGISTAR_AGENDA_INTEGRATION.md`** - Legistar implementation details
- **`GRANICUS_IMPLEMENTATION.md`** - Granicus ViewPublisher implementation
- **`CLAUDE.md`** - Current production status (26 cities, platform breakdown)

## Future Integration

These platforms remain viable for future expansion:
- **CDP** - Could provide video transcripts + sentiment analysis
- **Open States** - Automatic legislative metadata verification
- Research and access patterns are preserved here for future reference
