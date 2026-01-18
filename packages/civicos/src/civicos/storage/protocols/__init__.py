"""
Storage sub-protocols for domain-specific storage operations.

This module decomposes the 82-method StorageBackend protocol into
domain-specific sub-protocols for better organization, testing, and
type narrowing in API code.

Sub-protocols:
- ContentStorage: Meetings, decisions, chunks, agenda items, transcripts, videos
- LegislationStorage: Bills, municipal code, codified law, executive orders
- FinancialStorage: Budget items, federal awards, state pass-through, funding links
- CommunityStorage: 311 issues and public feedback
- ElectionStorage: Elections, contests, deadlines, officials
- OperationsStorage: ETL operations and cost tracking

The composite StorageBackend protocol inherits from all sub-protocols,
maintaining backward compatibility while allowing narrower type constraints.

Usage:
    # Narrow type for legislation-only function
    def search_bills(storage: LegislationStorage, query: str) -> List[Dict]:
        return storage.get_legislation(state="CA", topic=query)

    # Full backend still works
    backend: StorageBackend = get_storage_backend()
    search_bills(backend, "housing")  # Works, StorageBackend is LegislationStorage
"""

from civicos.storage.protocols.content import ContentStorage
from civicos.storage.protocols.legislation import LegislationStorage
from civicos.storage.protocols.financial import FinancialStorage
from civicos.storage.protocols.community import CommunityStorage
from civicos.storage.protocols.elections import ElectionStorage
from civicos.storage.protocols.operations import OperationsStorage

__all__ = [
    "ContentStorage",
    "LegislationStorage",
    "FinancialStorage",
    "CommunityStorage",
    "ElectionStorage",
    "OperationsStorage",
]
