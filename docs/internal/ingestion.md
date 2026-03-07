# Data Ingestion

## Pipeline

All ingestion follows a 4-stage pattern:

```
FETCH → NORMALIZE → VALIDATE → STORE
```

Use the `/ingest` slash command to orchestrate, or run scripts directly.

## Sources (San Rafael Pilot)

| Source | Script/Command | Frequency |
|--------|---------------|-----------|
| Meetings (ProudCity) | `/ingest proudcity` | Weekly |
| Issues (SeeClickFix) | `/ingest seeclickfix` | Weekly |
| Legislation (LegiScan) | `/ingest legiscan` | Weekly |
| Transcripts (YouTube) | `/ingest-audio city-san-rafael` | After new meetings |
| Municipal code | One-time (Municode) | As needed |
| Budget | One-time (PDF extraction) | Annual |
| Executive orders | `/ingest federal-register` | Weekly |

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
