#!/usr/bin/env python3
"""
Build ChromaDB vector index for high-stakes decisions

Creates embeddings for semantic search across decisions.
Enables queries like:
- "Which cities allocated funds for wildfire prevention?"
- "Has Berkeley funded housing before?"
- "Who testified on environmental issues?"
"""

import json
import argparse
import os
from typing import List, Dict
from datetime import datetime

import chromadb
from sentence_transformers import SentenceTransformer


def build_vector_index(
    decisions_file: str,
    output_dir: str = "data/pilot",
    collection_name: str = "high_stakes_decisions",
    model_name: str = "all-MiniLM-L6-v2"
) -> chromadb.Collection:
    """
    Build vector index from high-stakes decisions

    Args:
        decisions_file: JSON file with high-stakes decisions
        output_dir: Where to store ChromaDB database
        collection_name: Name for the ChromaDB collection
        model_name: Sentence transformer model to use

    Returns:
        ChromaDB collection
    """
    print("🔍 BUILDING DECISION VECTOR INDEX")
    print("=" * 70)

    # Load decisions
    with open(decisions_file, 'r') as f:
        data = json.load(f)

    decisions = data.get('decisions', [])
    jurisdiction_id = data.get('jurisdiction_id', 'unknown')
    jurisdiction_name = data.get('jurisdiction_name', 'Unknown')

    print(f"Loaded {len(decisions)} decisions from {decisions_file}")
    print(f"Jurisdiction: {jurisdiction_name} ({jurisdiction_id})")
    print(f"Model: {model_name}\n")

    # Initialize sentence transformer
    print("📥 Loading sentence transformer model...")
    model = SentenceTransformer(model_name)
    print(f"   ✅ Model loaded ({model_name})")
    print(f"   Embedding dimensions: {model.get_sentence_embedding_dimension()}")

    # Generate embeddings
    print("\n🧠 Generating embeddings...")

    # Create rich text for each decision (title + description + metadata)
    texts = []
    for decision in decisions:
        # Combine multiple fields for richer semantic search
        text_parts = [
            f"Title: {decision.get('title', '')}",
            f"Description: {decision.get('description', '')}",
            f"Type: {decision.get('decision_type', '')}",
            f"Project types: {', '.join(decision.get('project_types', []))}",
            f"Keywords: {', '.join(decision.get('keywords_for_matching', []))}"
        ]

        # Add budget info if available
        if decision.get('budget_amount'):
            text_parts.append(f"Budget: ${decision['budget_amount']:,.0f}")

        # Add geographic scope
        if decision.get('geographic_scope'):
            text_parts.append(f"Scope: {decision['geographic_scope']}")

        # Add location if available
        if decision.get('project_location'):
            text_parts.append(f"Location: {decision['project_location']}")

        texts.append(" | ".join(text_parts))

    print(f"   Generating embeddings for {len(texts)} decisions...")
    embeddings = model.encode(texts, show_progress_bar=True)
    print(f"   ✅ Generated {len(embeddings)} embeddings")

    # Initialize ChromaDB
    db_path = os.path.join(output_dir, "decision_vectors.db")
    print(f"\n💾 Creating ChromaDB at {db_path}")

    client = chromadb.PersistentClient(path=db_path)

    # Delete existing collection if it exists
    try:
        client.delete_collection(name=collection_name)
        print(f"   🗑️  Deleted existing collection '{collection_name}'")
    except:
        pass

    # Create new collection
    collection = client.create_collection(
        name=collection_name,
        metadata={
            "description": "High-stakes municipal decisions for retrospective analysis",
            "jurisdiction_id": jurisdiction_id,
            "jurisdiction_name": jurisdiction_name,
            "created_at": datetime.now().isoformat(),
            "embedding_model": model_name,
            "embedding_dimensions": model.get_sentence_embedding_dimension()
        }
    )

    print(f"   ✅ Created collection '{collection_name}'")

    # Prepare metadata for each decision
    metadatas = []
    ids = []
    documents = []

    for i, decision in enumerate(decisions):
        # Create unique ID
        decision_id = f"{jurisdiction_id}-{decision.get('meeting_date', 'unknown').split('T')[0]}-{decision.get('item_ref', str(i))}"
        ids.append(decision_id)

        # Store original text as document
        documents.append(texts[i])

        # Create metadata dict (ChromaDB has type restrictions)
        metadata = {
            "item_ref": str(decision.get('item_ref', '')),
            "title": str(decision.get('title', ''))[:500],  # ChromaDB string limit
            "description": str(decision.get('description', ''))[:1000],
            "meeting_date": str(decision.get('meeting_date', '').split('T')[0]),
            "meeting_type": str(decision.get('meeting_type', '')),
            "decision_type": str(decision.get('decision_type', '')),
            "stakes_score": int(decision.get('stakes_score', 0)),
            "budget": float(decision.get('budget_amount', 0) or 0),
            "geographic_scope": str(decision.get('geographic_scope', '')),
            "jurisdiction_id": jurisdiction_id,
            "jurisdiction_name": jurisdiction_name
        }

        # Add optional fields if present
        if decision.get('project_location'):
            metadata['project_location'] = str(decision['project_location'])[:200]

        if decision.get('testimony_count') is not None:
            metadata['testimony_count'] = int(decision['testimony_count'])

        if decision.get('project_size_units'):
            metadata['project_size_units'] = int(decision['project_size_units'])

        metadatas.append(metadata)

    # Add to collection
    print(f"\n📦 Adding {len(decisions)} decisions to collection...")

    collection.add(
        embeddings=embeddings.tolist(),
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    print(f"   ✅ Added {len(decisions)} decisions")

    # Get collection stats
    count = collection.count()
    print(f"\n📊 COLLECTION STATISTICS")
    print(f"   Collection name: {collection_name}")
    print(f"   Total documents: {count}")
    print(f"   Database path: {db_path}")

    # Calculate approximate size
    db_size = 0
    if os.path.exists(db_path):
        for root, dirs, files in os.walk(db_path):
            for file in files:
                db_size += os.path.getsize(os.path.join(root, file))

    print(f"   Database size: {db_size / 1024 / 1024:.1f} MB")

    return collection


def test_semantic_search(collection: chromadb.Collection):
    """Test semantic search with example queries"""

    print("\n" + "=" * 70)
    print("🔬 TESTING SEMANTIC SEARCH")
    print("=" * 70)

    test_queries = [
        "wildfire prevention spending",
        "housing and affordable units",
        "transportation and traffic infrastructure",
        "environmental protection and climate",
        "public safety and emergency services"
    ]

    for query in test_queries:
        print(f"\n🔍 Query: \"{query}\"")

        results = collection.query(
            query_texts=[query],
            n_results=3
        )

        if results['documents'] and results['documents'][0]:
            print(f"   Top 3 matches:")
            for i, (doc, metadata, distance) in enumerate(zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            ), 1):
                print(f"\n   {i}. {metadata['title']}")
                print(f"      Date: {metadata['meeting_date']}")
                print(f"      Type: {metadata['decision_type']}")
                if metadata.get('budget', 0) > 0:
                    print(f"      Budget: ${metadata['budget']:,.0f}")
                print(f"      Similarity: {1 - distance:.3f}")
        else:
            print("   No results found")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description='Build ChromaDB vector index for high-stakes decisions'
    )
    parser.add_argument('decisions_file',
                        help='JSON file with high-stakes decisions')
    parser.add_argument('--output-dir', default='data/pilot',
                        help='Directory for ChromaDB database (default: data/pilot)')
    parser.add_argument('--collection', default='high_stakes_decisions',
                        help='Collection name (default: high_stakes_decisions)')
    parser.add_argument('--model', default='all-MiniLM-L6-v2',
                        help='Sentence transformer model (default: all-MiniLM-L6-v2)')
    parser.add_argument('--test', action='store_true',
                        help='Run test queries after building index')

    args = parser.parse_args()

    # Build index
    collection = build_vector_index(
        decisions_file=args.decisions_file,
        output_dir=args.output_dir,
        collection_name=args.collection,
        model_name=args.model
    )

    # Test if requested
    if args.test:
        test_semantic_search(collection)

    print("\n✅ Vector index built successfully!")
    print(f"\n📈 NEXT STEPS:")
    print(f"   1. Test semantic search with custom queries")
    print(f"   2. Integrate with civic_api_integrated.py for frontend")
    print(f"   3. Scale to multiple jurisdictions (26 cities)")
    print(f"\n💡 TIP: Query latency is <100ms for most queries")


if __name__ == "__main__":
    main()
