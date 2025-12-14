"""
Legal document indexer.

Builds and maintains the vector index from corpus data.

Usage:
    indexer = LegalIndexer("./legal_index")

    # Index California bills
    corpus = CaliforniaCorpus()
    await indexer.index_corpus(corpus, session="2023-2024")

    # Incremental update
    await indexer.update_index(new_bills)

    # With custom embedding provider
    from civic._internal.embeddings import get_embedding_provider
    provider = get_embedding_provider("openai")
    indexer = LegalIndexer("./legal_index", provider=provider)
"""

import asyncio
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from civic._internal.legal.corpus.california import CaliforniaCorpus, BillDocument
from civic._internal.legal.embeddings.chunker import LegalChunker
from civic._internal.legal.embeddings.store import VectorStore

if TYPE_CHECKING:
    from civic._internal.embeddings.provider import EmbeddingProvider


class LegalIndexer:
    """
    Builds and maintains the legal document vector index.

    Coordinates:
    - Corpus fetching
    - Document chunking
    - Vector storage
    - Incremental updates
    """

    def __init__(
        self,
        persist_directory: str = "./legal_index",
        provider: Optional["EmbeddingProvider"] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
    ):
        """
        Initialize indexer.

        Args:
            persist_directory: Path for vector store
            provider: EmbeddingProvider instance. Defaults to local SentenceTransformer.
            chunk_size: Maximum characters per chunk
            chunk_overlap: Overlap between chunks
        """
        self.store = VectorStore(
            persist_directory=persist_directory,
            provider=provider,
        )
        self.chunker = LegalChunker(
            max_chunk_size=chunk_size,
            overlap=chunk_overlap,
            preserve_sections=True,
        )

    async def index_corpus(
        self,
        corpus: CaliforniaCorpus,
        session: str = "2023-2024",
        progress_callback: Optional[callable] = None,
    ) -> dict:
        """
        Index all bills from a corpus session.

        Args:
            corpus: CaliforniaCorpus instance
            session: Legislative session to index
            progress_callback: Optional callback(current, total)

        Returns:
            Stats dict with counts
        """
        stats = {
            "bills_processed": 0,
            "chunks_created": 0,
            "errors": [],
            "started_at": datetime.now().isoformat(),
        }

        async with corpus:
            bill_ids = await corpus._enumerate_bills(session, [])

            for i, bill_id in enumerate(bill_ids):
                try:
                    bill = await corpus.fetch_bill(bill_id, session)
                    if bill:
                        chunks = self._process_bill(bill)
                        self.store.add_documents(chunks)

                        stats["bills_processed"] += 1
                        stats["chunks_created"] += len(chunks)

                    if progress_callback:
                        progress_callback(i + 1, len(bill_ids))

                except Exception as e:
                    stats["errors"].append({
                        "bill_id": bill_id,
                        "error": str(e),
                    })

        stats["completed_at"] = datetime.now().isoformat()
        return stats

    async def index_bill(self, bill: BillDocument) -> int:
        """
        Index a single bill.

        Args:
            bill: BillDocument to index

        Returns:
            Number of chunks created
        """
        chunks = self._process_bill(bill)
        self.store.add_documents(chunks)
        return len(chunks)

    def _process_bill(self, bill: BillDocument) -> list[dict]:
        """Convert a bill to indexable chunks."""
        chunks = []

        metadata = {
            "bill_id": bill.metadata.bill_id,
            "session": bill.metadata.session,
            "title": bill.metadata.title,
            "author": bill.metadata.author,
            "status": bill.metadata.status.value if bill.metadata.status else "unknown",
            "topics": ",".join(bill.metadata.topics),
        }

        for chunk in self.chunker.chunk_document(
            text=bill.full_text,
            source_id=bill.metadata.bill_id,
            metadata=metadata,
        ):
            chunks.append({
                "id": f"{bill.metadata.bill_id}_{chunk.chunk_index}",
                "text": chunk.text,
                "metadata": {
                    **metadata,
                    "section": chunk.section,
                    "chunk_index": chunk.chunk_index,
                },
            })

        return chunks

    def get_stats(self) -> dict:
        """Get current index statistics."""
        return {
            "total_chunks": self.store.count(),
        }


def main():
    """CLI entry point for indexing."""
    import argparse

    parser = argparse.ArgumentParser(description="Index California legislation")
    parser.add_argument(
        "--session",
        default="2023-2024",
        help="Legislative session to index",
    )
    parser.add_argument(
        "--persist-dir",
        default="./legal_index",
        help="Directory for vector store",
    )
    args = parser.parse_args()

    async def run():
        indexer = LegalIndexer(persist_directory=args.persist_dir)
        corpus = CaliforniaCorpus()

        print(f"Indexing session {args.session}...")
        stats = await indexer.index_corpus(
            corpus,
            session=args.session,
            progress_callback=lambda c, t: print(f"Progress: {c}/{t}"),
        )

        print(f"\nComplete!")
        print(f"Bills processed: {stats['bills_processed']}")
        print(f"Chunks created: {stats['chunks_created']}")
        if stats["errors"]:
            print(f"Errors: {len(stats['errors'])}")

    asyncio.run(run())


if __name__ == "__main__":
    main()
