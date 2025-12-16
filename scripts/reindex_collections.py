#!/usr/bin/env python3
"""
Re-index ChromaDB collections with new embedding model.

This script re-embeds all existing collections from the old model
(all-MiniLM-L6-v2, 384 dims) to the new model (nomic-embed-text-v1.5, 768 dims).

Collections re-indexed:
- city-san-rafael_chunks: PDF/agenda text chunks
- city-san-rafael_issues: SeeClickFix citizen reports
- city-san-rafael_municipal_code: Municipal code sections

Usage:
    python scripts/reindex_collections.py
    python scripts/reindex_collections.py --jurisdiction city-berkeley
    python scripts/reindex_collections.py --dry-run
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "civic" / "src"))

import chromadb
from civic._internal.meetings.embeddings import CivicEmbeddings


def get_collection_stats(client: chromadb.PersistentClient, collection_name: str) -> dict:
    """Get stats for a collection if it exists."""
    try:
        col = client.get_collection(collection_name)
        metadata = col.metadata or {}
        return {
            "exists": True,
            "count": col.count(),
            "model": metadata.get("embedding_model", "unknown"),
            "dimension": metadata.get("embedding_dimension", "unknown"),
        }
    except Exception:
        return {"exists": False, "count": 0, "model": "n/a", "dimension": "n/a"}


def reindex_collections(
    jurisdiction_id: str = "city-san-rafael",
    corpus_dir: Optional[str] = None,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """
    Re-index all collections for a jurisdiction with the new embedding model.

    Args:
        jurisdiction_id: Jurisdiction to reindex (e.g., "city-san-rafael")
        corpus_dir: Path to corpus directory (defaults to data/pilot/rag_corpus/{jurisdiction_id})
        dry_run: If True, only report what would be done without actually re-indexing
        verbose: Print progress information

    Returns:
        Dict with statistics about the re-indexing operation
    """
    if corpus_dir is None:
        corpus_dir = f"data/pilot/rag_corpus/{jurisdiction_id}"

    results = {
        "jurisdiction_id": jurisdiction_id,
        "started_at": datetime.now().isoformat(),
        "dry_run": dry_run,
        "collections": {},
    }

    if verbose:
        print("=" * 70)
        print("CIVIC COLLECTION RE-INDEXING")
        print("=" * 70)
        print(f"Jurisdiction: {jurisdiction_id}")
        print(f"Corpus dir: {corpus_dir}")
        print(f"Target model: nomic-ai/nomic-embed-text-v1.5 (768 dims)")
        print(f"Dry run: {dry_run}")
        print()

    # Initialize embedder with new model
    embedder = CivicEmbeddings(jurisdiction_id)
    client = embedder._client

    # Define collections to reindex
    collections = [
        {
            "name": embedder.chunks_collection_name,
            "type": "chunks",
            "build_method": "build_chunks_index",
            "args": {"corpus_dir": corpus_dir},
        },
        {
            "name": embedder.issues_collection_name,
            "type": "issues",
            "build_method": "build_issues_index",
            "args": {"db_path": "data/civic_state.db"},
        },
        {
            "name": embedder.municipal_code_collection_name,
            "type": "municipal_code",
            "build_method": "build_municipal_code_index",
            "args": {},
        },
    ]

    if verbose:
        print("Collections to process:")
        print("-" * 70)

    for col_info in collections:
        col_name = col_info["name"]
        stats_before = get_collection_stats(client, col_name)

        if verbose:
            print(f"\n{col_info['type'].upper()}: {col_name}")
            print(f"  Before: {stats_before['count']} docs, model={stats_before['model']}, dim={stats_before['dimension']}")

        results["collections"][col_info["type"]] = {
            "name": col_name,
            "before": stats_before,
        }

        if dry_run:
            if verbose:
                print(f"  [DRY RUN] Would rebuild with new model")
            results["collections"][col_info["type"]]["status"] = "skipped (dry run)"
            continue

        # Actually rebuild the collection
        try:
            if verbose:
                print(f"  Rebuilding...")
            start_time = time.time()

            method = getattr(embedder, col_info["build_method"])
            method(**col_info["args"])

            elapsed = time.time() - start_time
            stats_after = get_collection_stats(client, col_name)

            if verbose:
                print(f"  After: {stats_after['count']} docs, model={stats_after['model']}, dim={stats_after['dimension']}")
                print(f"  Time: {elapsed:.1f}s")

            results["collections"][col_info["type"]]["after"] = stats_after
            results["collections"][col_info["type"]]["elapsed_seconds"] = elapsed
            results["collections"][col_info["type"]]["status"] = "success"

        except FileNotFoundError as e:
            if verbose:
                print(f"  ERROR: {e}")
            results["collections"][col_info["type"]]["status"] = f"error: {e}"
        except Exception as e:
            if verbose:
                print(f"  ERROR: {e}")
            results["collections"][col_info["type"]]["status"] = f"error: {e}"

    results["completed_at"] = datetime.now().isoformat()

    if verbose:
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        for ctype, cdata in results["collections"].items():
            status = cdata.get("status", "unknown")
            before_count = cdata["before"]["count"]
            after_count = cdata.get("after", {}).get("count", "n/a")
            print(f"  {ctype}: {before_count} -> {after_count} docs [{status}]")

    return results


def verify_reindexing(jurisdiction_id: str = "city-san-rafael") -> bool:
    """
    Verify that collections have been properly re-indexed with new model.

    Returns:
        True if all collections are using the new model, False otherwise
    """
    embedder = CivicEmbeddings(jurisdiction_id)
    client = embedder._client

    expected_model = "nomic-ai/nomic-embed-text-v1.5"
    expected_dim = 768

    collections_to_check = [
        embedder.chunks_collection_name,
        embedder.issues_collection_name,
        embedder.municipal_code_collection_name,
    ]

    all_valid = True
    print("\nVerifying re-indexed collections:")
    print("-" * 50)

    for col_name in collections_to_check:
        stats = get_collection_stats(client, col_name)

        if not stats["exists"]:
            print(f"  {col_name}: MISSING")
            all_valid = False
            continue

        model_ok = stats["model"] == expected_model
        dim_ok = stats["dimension"] == expected_dim

        if model_ok and dim_ok:
            print(f"  {col_name}: OK ({stats['count']} docs)")
        else:
            print(f"  {col_name}: INVALID")
            print(f"    Model: {stats['model']} (expected {expected_model})")
            print(f"    Dim: {stats['dimension']} (expected {expected_dim})")
            all_valid = False

    return all_valid


def main():
    parser = argparse.ArgumentParser(
        description="Re-index ChromaDB collections with new embedding model"
    )
    parser.add_argument(
        "--jurisdiction",
        default="city-san-rafael",
        help="Jurisdiction ID to reindex (default: city-san-rafael)",
    )
    parser.add_argument(
        "--corpus-dir",
        help="Path to corpus directory (default: data/pilot/rag_corpus/{jurisdiction})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually re-indexing",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Only verify that collections use new model (no re-indexing)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output",
    )

    args = parser.parse_args()

    if args.verify:
        valid = verify_reindexing(args.jurisdiction)
        sys.exit(0 if valid else 1)

    results = reindex_collections(
        jurisdiction_id=args.jurisdiction,
        corpus_dir=args.corpus_dir,
        dry_run=args.dry_run,
        verbose=not args.quiet,
    )

    # Exit with error if any collection failed
    for ctype, cdata in results["collections"].items():
        if cdata.get("status", "").startswith("error"):
            sys.exit(1)

    # Verify after reindexing (unless dry run)
    if not args.dry_run:
        print()
        valid = verify_reindexing(args.jurisdiction)
        if not valid:
            print("\nWARNING: Verification failed after re-indexing")
            sys.exit(1)

    print("\nRe-indexing completed successfully!")


if __name__ == "__main__":
    main()
