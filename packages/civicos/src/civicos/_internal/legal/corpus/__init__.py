"""
Corpus acquisition for legal data sources.

Supports:
- California Legislature (leginfo.legislature.ca.gov)
- Federal programs (HUD, EPA, DOT)
- Municipal codes (PDF from Municode or similar)
- CourtListener case law (optional)
"""

from civicos._internal.legal.corpus.california import CaliforniaCorpus
from civicos._internal.legal.corpus.federal import FederalCorpus
from civicos._internal.legal.corpus.municipal import (
    MunicipalCodeCorpus,
    MunicipalCodeSection,
    parse_municipal_code,
    parse_municipal_code_pdf,  # Legacy alias
)
from civicos._internal.legal.corpus.refresh import (
    ChangeSignal,
    ChangeStatus,
    RefreshPolicy,
    RefreshRunner,
    RefreshableCorpus,
)

__all__ = [
    "CaliforniaCorpus",
    "FederalCorpus",
    "MunicipalCodeCorpus",
    "MunicipalCodeSection",
    "parse_municipal_code",
    "parse_municipal_code_pdf",
    "ChangeSignal",
    "ChangeStatus",
    "RefreshPolicy",
    "RefreshRunner",
    "RefreshableCorpus",
]
