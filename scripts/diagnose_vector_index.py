#!/usr/bin/env python3
"""
Diagnose and optimize pgvector index for vector_embeddings table.

Without a proper index, every vector search does a full table scan with
cosine distance computation on all rows — extremely IO-intensive.

Usage:
    # Diagnose only (safe, read-only)
    python scripts/diagnose_vector_index.py

    # Recreate IVFFlat index with optimal list count
    python scripts/diagnose_vector_index.py --recreate

    # Use HNSW instead (faster queries, more memory)
    python scripts/diagnose_vector_index.py --recreate --hnsw

    # Dry run (show SQL without executing)
    python scripts/diagnose_vector_index.py --recreate --dry-run
"""

import argparse
import os
import sys
import math


def load_env():
    """Load DATABASE_URL from .env file."""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ.setdefault(key.strip(), val.strip())


def get_connection():
    """Get PostgreSQL connection."""
    import psycopg2
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("ERROR: DATABASE_URL not set. Check .env file.")
        sys.exit(1)
    return psycopg2.connect(database_url)


def diagnose(conn):
    """Diagnose current index state and performance."""
    cursor = conn.cursor()

    print("=" * 60)
    print("PGVECTOR INDEX DIAGNOSTIC")
    print("=" * 60)

    # 1. Check row count
    cursor.execute("SELECT COUNT(*) FROM vector_embeddings")
    row_count = cursor.fetchone()[0]
    print(f"\n1. Row count: {row_count:,}")

    # 2. Check corpus distribution
    cursor.execute("""
        SELECT corpus_type, COUNT(*) as cnt
        FROM vector_embeddings
        GROUP BY corpus_type
        ORDER BY cnt DESC
    """)
    print("\n2. Corpus distribution:")
    for corpus, cnt in cursor.fetchall():
        print(f"   {corpus}: {cnt:,}")

    # 3. Check existing indexes
    cursor.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'vector_embeddings'
    """)
    indexes = cursor.fetchall()
    print("\n3. Existing indexes:")

    vector_index = None
    for name, definition in indexes:
        is_vector = 'ivfflat' in definition.lower() or 'hnsw' in definition.lower()
        marker = " ← VECTOR INDEX" if is_vector else ""
        print(f"   {name}{marker}")
        print(f"      {definition[:100]}{'...' if len(definition) > 100 else ''}")
        if is_vector:
            vector_index = (name, definition)

    # 4. Analyze vector index
    print("\n4. Vector index analysis:")
    if vector_index:
        name, definition = vector_index
        if 'ivfflat' in definition.lower():
            # Extract lists count
            import re
            lists_match = re.search(r'lists\s*=\s*(\d+)', definition)
            current_lists = int(lists_match.group(1)) if lists_match else "unknown"
            optimal_lists = max(10, min(1000, int(math.sqrt(row_count))))

            print(f"   Type: IVFFlat")
            print(f"   Current lists: {current_lists}")
            print(f"   Optimal lists for {row_count:,} rows: {optimal_lists}")

            if isinstance(current_lists, int) and current_lists < optimal_lists * 0.5:
                print(f"   ⚠️  Index is UNDERSIZED - queries scanning too many vectors")
                print(f"      Recommend: --recreate to rebuild with lists={optimal_lists}")
            elif isinstance(current_lists, int) and current_lists > optimal_lists * 2:
                print(f"   ⚠️  Index is OVERSIZED - may have poor recall")
                print(f"      Recommend: --recreate to rebuild with lists={optimal_lists}")
            else:
                print(f"   ✓ Index size looks appropriate")
        elif 'hnsw' in definition.lower():
            print(f"   Type: HNSW")
            print(f"   ✓ HNSW indexes are self-tuning, no adjustment needed")
    else:
        print(f"   ⚠️  NO VECTOR INDEX FOUND")
        print(f"   Every search does a full table scan on {row_count:,} rows!")
        print(f"   This is extremely IO-intensive.")
        print(f"   Recommend: --recreate to create index")

    # 5. Check table size
    cursor.execute("""
        SELECT pg_size_pretty(pg_total_relation_size('vector_embeddings')) as total,
               pg_size_pretty(pg_relation_size('vector_embeddings')) as table,
               pg_size_pretty(pg_indexes_size('vector_embeddings')) as indexes
    """)
    total, table, indexes_size = cursor.fetchone()
    print(f"\n5. Storage:")
    print(f"   Table data: {table}")
    print(f"   Indexes: {indexes_size}")
    print(f"   Total: {total}")

    # 6. Recommendations
    print("\n6. Recommendations:")
    optimal_lists = max(10, min(1000, int(math.sqrt(row_count))))

    if not vector_index:
        print(f"   CRITICAL: Create a vector index immediately")
        print(f"   Run: python scripts/diagnose_vector_index.py --recreate")
    elif 'ivfflat' in vector_index[1].lower():
        import re
        lists_match = re.search(r'lists\s*=\s*(\d+)', vector_index[1])
        current_lists = int(lists_match.group(1)) if lists_match else 0
        if current_lists < optimal_lists * 0.5:
            print(f"   Rebuild index with more lists for better performance")
            print(f"   Run: python scripts/diagnose_vector_index.py --recreate")
        else:
            print(f"   Index looks healthy. If still seeing high IO:")
            print(f"   - Check query patterns (too many concurrent searches?)")
            print(f"   - Consider HNSW: --recreate --hnsw")

    print("=" * 60)
    return row_count, vector_index


def recreate_index(conn, row_count, use_hnsw=False, dry_run=False):
    """Recreate the vector index with optimal settings."""
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("RECREATING VECTOR INDEX")
    print("=" * 60)

    # Drop existing vector indexes
    drop_sql = """
        DROP INDEX IF EXISTS idx_vector_embeddings_embedding;
        DROP INDEX IF EXISTS idx_vector_embeddings_embedding_hnsw;
    """

    if use_hnsw:
        # HNSW: faster queries, more memory, no tuning needed
        # m=16: connections per node (default, good balance)
        # ef_construction=64: build-time search width (higher = better recall, slower build)
        create_sql = """
            CREATE INDEX idx_vector_embeddings_embedding_hnsw
            ON vector_embeddings USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        """
        index_type = "HNSW"
        settings = "m=16, ef_construction=64"
    else:
        # IVFFlat: good balance of speed and memory
        # lists = sqrt(n) for datasets < 1M rows
        optimal_lists = max(10, min(1000, int(math.sqrt(row_count))))
        create_sql = f"""
            CREATE INDEX idx_vector_embeddings_embedding
            ON vector_embeddings USING ivfflat (embedding vector_cosine_ops)
            WITH (lists = {optimal_lists});
        """
        index_type = "IVFFlat"
        settings = f"lists={optimal_lists}"

    print(f"\nIndex type: {index_type}")
    print(f"Settings: {settings}")
    print(f"Row count: {row_count:,}")

    print(f"\nSQL to execute:")
    print("-" * 40)
    print(drop_sql.strip())
    print()
    print(create_sql.strip())
    print("-" * 40)

    if dry_run:
        print("\n[DRY RUN] No changes made.")
        return

    print("\nExecuting...")

    # Drop old indexes
    cursor.execute(drop_sql)
    conn.commit()
    print("✓ Dropped old indexes")

    # Set longer timeout for index creation (10 minutes)
    # Supabase default is 2 minutes which isn't enough for large tables
    cursor.execute("SET statement_timeout = '600000'")  # 10 minutes in ms

    # Create new index (this can take a while for large tables)
    print(f"Creating {index_type} index (this may take several minutes for {row_count:,} rows)...")
    print("(Timeout set to 10 minutes)")
    cursor.execute(create_sql)
    conn.commit()
    print(f"✓ Created {index_type} index")

    # Analyze table to update statistics
    print("Analyzing table...")
    cursor.execute("ANALYZE vector_embeddings")
    conn.commit()
    print("✓ Updated table statistics")

    print("\n" + "=" * 60)
    print("INDEX RECREATION COMPLETE")
    print("=" * 60)
    print("\nVector searches should now use the index instead of full table scans.")
    print("Monitor Supabase Disk IO to verify improvement.")


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose and optimize pgvector index",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        '--recreate', action='store_true',
        help='Recreate the vector index with optimal settings'
    )
    parser.add_argument(
        '--hnsw', action='store_true',
        help='Use HNSW index instead of IVFFlat (faster queries, more memory)'
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Show SQL without executing'
    )

    args = parser.parse_args()

    load_env()

    try:
        conn = get_connection()
    except Exception as e:
        print(f"ERROR: Could not connect to database: {e}")
        sys.exit(1)

    try:
        row_count, vector_index = diagnose(conn)

        if args.recreate:
            recreate_index(conn, row_count, use_hnsw=args.hnsw, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
