"""
civicos-legal: Legal RAG system for civic data

Provides semantic search over California legislation, federal programs, and case law.
Supersedes civic-enrichment with true vector retrieval capabilities.

Architecture:
    - corpus/     Data acquisition (CA bills, federal programs, case law)
    - embeddings/ Vector layer (chunking, ChromaDB storage)
    - retrieval/  Search layer (similarity search, reranking, context building)
    - enrichment/ Event enrichment (keyword + semantic paths)

Note: Legislation indexing now uses pgvector via expand_legislation_to_chunks()
+ PgVectorBackend.index_from_storage(). LegalIndexer was removed.

Usage:
    # Corpus fetching
    from civicos._internal.legal.corpus import CaliforniaCorpus
    corpus = CaliforniaCorpus()
    bills = await corpus.fetch_session("2023-2024")

    # Semantic search (requires [embeddings])
    from civicos._internal.legal.retrieval import LegalSearch
    search = LegalSearch()
    results = search.query("wildfire prevention funding")

    # Event enrichment (backwards compatible)
    from civicos._internal.legal.enrichment import enrich_opportunity
    context = enrich_opportunity(opportunity)
"""

__version__ = "0.1.0"

# Core exports - always available
from civicos._internal.legal.corpus import CaliforniaCorpus, FederalCorpus

# Enrichment - backwards compatible with civic-enrichment
from civicos._internal.legal.enrichment import (
    LegislativeCache,
    create_default_cache,
    enrich_opportunity,
    enrich_opportunities_batch,
    find_relevant_bills,
    find_relevant_programs,
    extract_state_from_jurisdiction,
    TOPIC_ENRICHMENT_POLICY,
)

# Optional: Embeddings (requires [embeddings])
try:
    from civicos._internal.legal.embeddings import LegalChunker, VectorStore
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    LegalChunker = None
    VectorStore = None

# Optional: Retrieval (requires [embeddings])
try:
    from civicos._internal.legal.retrieval import LegalSearch, Reranker, ContextBuilder
    RETRIEVAL_AVAILABLE = True
except ImportError:
    RETRIEVAL_AVAILABLE = False
    LegalSearch = None
    Reranker = None
    ContextBuilder = None

# Optional: MCP (requires [mcp])
try:
    from civicos._internal.legal.mcp import create_mcp_server, LegalServer
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    create_mcp_server = None
    LegalServer = None

__all__ = [
    # Version
    "__version__",
    # Corpus
    "CaliforniaCorpus",
    "FederalCorpus",
    # Enrichment (backwards compatible)
    "LegislativeCache",
    "create_default_cache",
    "enrich_opportunity",
    "enrich_opportunities_batch",
    "find_relevant_bills",
    "find_relevant_programs",
    "extract_state_from_jurisdiction",
    "TOPIC_ENRICHMENT_POLICY",
    # Embeddings (optional)
    "LegalChunker",
    "VectorStore",
    "EMBEDDINGS_AVAILABLE",
    # Retrieval (optional)
    "LegalSearch",
    "Reranker",
    "ContextBuilder",
    "RETRIEVAL_AVAILABLE",
    # MCP (optional)
    "create_mcp_server",
    "LegalServer",
    "MCP_AVAILABLE",
]
