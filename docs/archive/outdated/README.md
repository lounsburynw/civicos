# Outdated Terminology Archive

This directory contains documentation using deprecated "complaint" terminology.

## Contents

- `COMPLAINT_INTEGRATION_GUIDE.md` - Integration guide using old "complaint" terminology
- `COMPLAINT_TO_CIVIC_IMPLEMENTATION_ROADMAP.md` - Implementation roadmap with old terminology
- `COMPLAINT_TO_CIVIC_TECHNICAL_ARCHITECTURE.md` - Technical architecture with old terminology
- `LEGISLATIVE_AUTOMATION_SETUP.md` - Deprecated legislative automation (replaced by manual setup)

## Why Archived?

### Deprecated Terminology (3 docs)

**Terminology Change**: The platform renamed "complaints" → "issues" in migration 008 (2024-10-25).

### Evidence of Change:
- **Database**: `migrations/008_rename_complaints_to_issues.sql` renames all tables
- **Backend**: All source files now use `issue_*.py` naming (`issue_storage.py`, `issue_handler.py`, etc.)
- **Frontend**: Components use `IssueArtifact.vue`, `IssueForm.vue`, etc.
- **API**: Endpoints use `/api/issues/` instead of `/api/complaints/`

### Updated Documentation (Complaints → Issues)

See current docs:
- `COMMUNITY_CIVIC_PMF_STRATEGY.md` - Uses "issue" terminology throughout
- `API_DOCUMENTATION.md` - Current API endpoints with `/api/issues/`
- `FRONTEND_IMPLEMENTATION_ROADMAP.md` - Issue system architecture

---

### Deprecated Approach (1 doc)

**LEGISLATIVE_AUTOMATION_SETUP.md** (Deprecated 2025-10-07):
- **Problem**: Automated legislative discovery achieved only 60-70% precision
- **Issues**: Temporal recency bias, LLM non-determinism, metadata loss
- **Replaced by**: `LEGISLATIVE_CONTEXT_SETUP_GUIDE.md` (96-98% precision via manual curation)
- **Why kept**: Documents the failed automation experiment for future reference

## Historical Context

These docs provide valuable historical context for understanding:
- System evolution from complaint-focused to issue-focused terminology
- Failed automation experiments and why manual curation was chosen
- Technical decisions and architecture changes over time

All technical information remains valid if you mentally substitute "issue" for "complaint" (for the 3 terminology docs).
