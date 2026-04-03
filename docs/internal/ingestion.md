# Data Ingestion

## Pipeline

All ingestion follows a 4-stage pattern:

```
FETCH → NORMALIZE → VALIDATE → STORE
```

Use the `/ingest` slash command to orchestrate, or run scripts directly.

## Sources

Meeting source is auto-detected per jurisdiction. Issue source defaults to SeeClickFix.

| Source | Platforms | Frequency |
|--------|-----------|-----------|
| Meetings | ProudCity, Granicus, Legistar, CivicClerk, CivicPlus, eScribe, Simbli, BoardDocs, Universal | Weekly |
| Issues | SeeClickFix (public API), GOGov (auth required — see below) | Weekly |
| Legislation | LegiScan | Weekly |
| Transcripts | YouTube → AssemblyAI | After new meetings |
| Municipal code | Municode | As needed |
| Budget | PDF extraction | Annual |
| Executive orders | Federal Register API | Weekly |

### 311 Issue Providers

**SeeClickFix** — Public API, no credentials needed. Auto-detected during onboarding.

**GOGov** (FixItMarin, etc.) — Requires staff credentials. API at `api.govoutreach.com`, wrapped by PyPI package [`gogov`](https://pypi.org/project/gogov/). Detection works during onboarding (`detect_issue_source()` identifies GOGov for county-level jurisdictions), but fetching requires `GOGOV_EMAIL`/`GOGOV_PASSWORD`/`GOGOV_SITE` env vars and a data sharing agreement. Known deployment: Marin County (`marincountyca`), unincorporated areas only. See `docs/public/data-ingestion.md` for full API details.

## Checkpoints

Ingestion uses checkpoint files (`data/checkpoints/`) for crash recovery. View/reset:

```bash
/checkpoint              # View all checkpoints
/checkpoint reset        # Reset specific checkpoint
```

## Vector Indexing

After ingesting new data, re-index vectors:

```bash
modal run scripts/modal_ingest.py                    # Full re-index (GPU)
/vectors reindex --corpus-type transcripts            # Specific corpus
```

## Diagnostics

Check data completeness:

```bash
/data-status city-san-rafael        # Corpus counts and gaps
/vector-coverage city-san-rafael    # Embedding coverage
```

Or programmatically:

```python
from civicos import CivicOS, DataStatus, format_data_status
c = CivicOS('city-san-rafael')
status = DataStatus(c.storage, c._vectors, 'city-san-rafael')
print(format_data_status(status.summary()))
```
