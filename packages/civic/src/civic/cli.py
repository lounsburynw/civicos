"""
Civic CLI - Command-line interface for Civic platform.

Provides status and diagnostics for the Civic ingestion pipeline.

Usage:
    civic status                           # Show all metrics
    civic status --jurisdiction san-rafael # Specific jurisdiction
    civic status --json                    # Machine-readable output
    civic status --corpus decisions        # Single corpus
    civic status --check-gaps              # Compare ingested vs source counts

Entry point: civic-status (configured in pyproject.toml)
"""

import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ANSI color codes for terminal output
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    DIM = "\033[2m"


def colorize(text: str, color: str, no_color: bool = False) -> str:
    """Apply color to text if terminal supports it."""
    if no_color or not sys.stdout.isatty():
        return text
    return f"{color}{text}{Colors.RESET}"


def format_relative_time(dt: Optional[datetime]) -> str:
    """Format a datetime as relative time (e.g., '2 hours ago')."""
    if dt is None:
        return "never"

    now = datetime.now()
    if dt.tzinfo is not None:
        # Remove timezone for comparison
        dt = dt.replace(tzinfo=None)

    delta = now - dt

    if delta.days > 365:
        years = delta.days // 365
        return f"{years}y ago"
    elif delta.days > 30:
        months = delta.days // 30
        return f"{months}mo ago"
    elif delta.days > 0:
        return f"{delta.days}d ago"
    elif delta.seconds > 3600:
        hours = delta.seconds // 3600
        return f"{hours}h ago"
    elif delta.seconds > 60:
        mins = delta.seconds // 60
        return f"{mins}m ago"
    else:
        return "just now"


def get_freshness_indicator(dt: Optional[datetime], no_color: bool = False) -> tuple[str, str]:
    """
    Get freshness indicator based on age.

    Returns (emoji, color_code) tuple.
    - Green: < 7 days
    - Yellow: 7-30 days
    - Red: > 30 days
    """
    if dt is None:
        return "?", Colors.DIM

    now = datetime.now()
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)

    delta = now - dt

    if delta.days <= 7:
        return "OK", Colors.GREEN
    elif delta.days <= 30:
        return "STALE", Colors.YELLOW
    else:
        return "OLD", Colors.RED


def get_state_db_stats(
    db_path: str,
    jurisdiction_id: str
) -> Dict[str, Any]:
    """Get statistics from civic_state.db."""
    stats = {
        "meetings": {"count": 0, "earliest": None, "latest": None, "updated": None},
        "agenda_items": {"count": 0, "updated": None},
        "issues": {"count": 0, "by_status": {}, "updated": None},
        "initiatives": {"count": 0, "updated": None},
    }

    if not Path(db_path).exists():
        return stats

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Meetings count and date range
    try:
        cursor.execute("""
            SELECT COUNT(*), MIN(meeting_datetime), MAX(meeting_datetime), MAX(updated_at)
            FROM meetings
            WHERE jurisdiction_id = ? AND valid_to IS NULL
        """, (jurisdiction_id,))
        row = cursor.fetchone()
        if row:
            stats["meetings"]["count"] = row[0] or 0
            stats["meetings"]["earliest"] = row[1]
            stats["meetings"]["latest"] = row[2]
            if row[3]:
                try:
                    stats["meetings"]["updated"] = datetime.fromisoformat(row[3])
                except (ValueError, TypeError):
                    pass
    except sqlite3.OperationalError:
        pass  # Table may not exist

    # Agenda items
    try:
        cursor.execute("""
            SELECT COUNT(*), MAX(enriched_at)
            FROM agenda_items
            WHERE valid_to IS NULL
              AND meeting_id IN (
                  SELECT id FROM meetings
                  WHERE jurisdiction_id = ? AND valid_to IS NULL
              )
        """, (jurisdiction_id,))
        row = cursor.fetchone()
        if row:
            stats["agenda_items"]["count"] = row[0] or 0
            if row[1]:
                try:
                    stats["agenda_items"]["updated"] = datetime.fromisoformat(row[1])
                except (ValueError, TypeError):
                    pass
    except sqlite3.OperationalError:
        pass

    # Issues
    try:
        cursor.execute("""
            SELECT COUNT(*), MAX(updated_at)
            FROM issues
            WHERE jurisdiction_id = ?
        """, (jurisdiction_id,))
        row = cursor.fetchone()
        if row:
            stats["issues"]["count"] = row[0] or 0
            if row[1]:
                try:
                    stats["issues"]["updated"] = datetime.fromisoformat(row[1])
                except (ValueError, TypeError):
                    pass

        # By status breakdown
        cursor.execute("""
            SELECT status, COUNT(*)
            FROM issues
            WHERE jurisdiction_id = ?
            GROUP BY status
        """, (jurisdiction_id,))
        stats["issues"]["by_status"] = {row[0]: row[1] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        pass

    # Initiatives
    try:
        cursor.execute("""
            SELECT COUNT(*), MAX(updated_at)
            FROM initiatives
            WHERE jurisdiction_id = ?
        """, (jurisdiction_id,))
        row = cursor.fetchone()
        if row:
            stats["initiatives"]["count"] = row[0] or 0
            if row[1]:
                try:
                    stats["initiatives"]["updated"] = datetime.fromisoformat(row[1])
                except (ValueError, TypeError):
                    pass
    except sqlite3.OperationalError:
        pass

    conn.close()
    return stats


def get_chroma_stats(
    jurisdiction_id: str,
    vectors_dir: str = "data/pilot/vectors"
) -> Dict[str, Any]:
    """Get statistics from ChromaDB collections."""
    stats = {
        "collections": {},
        "total_documents": 0,
        "db_size_bytes": 0,
    }

    persist_dir = Path(vectors_dir) / jurisdiction_id
    if not persist_dir.exists():
        return stats

    # Get DB file size
    chroma_db = persist_dir / "chroma.sqlite3"
    if chroma_db.exists():
        stats["db_size_bytes"] = chroma_db.stat().st_size

    try:
        import chromadb
        from chromadb.config import Settings

        client = chromadb.PersistentClient(
            path=str(persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )

        # Expected collection names
        collection_names = [
            f"{jurisdiction_id}_decisions",
            f"{jurisdiction_id}_chunks",
            f"{jurisdiction_id}_transcripts",
            f"{jurisdiction_id}_issues",
            f"{jurisdiction_id}_municipal_code",
        ]

        for name in collection_names:
            try:
                collection = client.get_collection(name)
                count = collection.count()
                metadata = collection.metadata or {}

                # Parse created_at from metadata
                created_at = None
                if metadata.get("created_at"):
                    try:
                        created_at = datetime.fromisoformat(metadata["created_at"])
                    except (ValueError, TypeError):
                        pass

                # Derive corpus type from collection name
                corpus_type = name.replace(f"{jurisdiction_id}_", "")

                stats["collections"][corpus_type] = {
                    "name": name,
                    "count": count,
                    "created_at": created_at,
                    "metadata": metadata,
                }
                stats["total_documents"] += count
            except Exception:
                # Collection doesn't exist
                stats["collections"][name.replace(f"{jurisdiction_id}_", "")] = None

    except ImportError:
        # ChromaDB not installed
        pass
    except Exception:
        # Other errors (e.g., database locked)
        pass

    return stats


def get_file_stats(base_path: str = ".") -> Dict[str, Any]:
    """Get file system statistics."""
    stats = {
        "state_db_size": 0,
        "participation_db_size": 0,
    }

    state_db = Path(base_path) / "data" / "civic_state.db"
    if state_db.exists():
        stats["state_db_size"] = state_db.stat().st_size

    participation_db = Path(base_path) / "data" / "civic_participation.db"
    if participation_db.exists():
        stats["participation_db_size"] = participation_db.stat().st_size

    return stats


def format_bytes(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    if size_bytes == 0:
        return "0 B"

    for unit in ["B", "KB", "MB", "GB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0

    return f"{size_bytes:.1f} TB"


def get_source_counts(
    jurisdiction_id: str,
    days_past: int = 365
) -> Dict[str, Any]:
    """
    Get counts of available data from external sources.

    Queries external APIs (ProudCity, SeeClickFix) to determine how many
    records are available at the source for comparison with ingested counts.

    Args:
        jurisdiction_id: Jurisdiction identifier (e.g., "city-san-rafael")
        days_past: How many days into the past to query

    Returns:
        Dict with source counts and metadata:
        {
            "meetings": {"count": int, "source": str, "error": str|None},
            "issues": {"count": int, "source": str, "error": str|None},
            "queried_at": datetime
        }
    """
    result = {
        "meetings": {"count": 0, "source": "proudcity", "error": None},
        "issues": {"count": 0, "source": "seeclickfix", "error": None},
        "queried_at": datetime.now(),
    }

    # Get meetings from ProudCity (San Rafael specific)
    if jurisdiction_id in ("city-san-rafael", "san-rafael"):
        try:
            from civic_extraction.clients.proudcity import create_san_rafael_client
            client = create_san_rafael_client()
            events = client.get_events(days_ahead=90, days_past=days_past)
            result["meetings"]["count"] = len(events)
        except ImportError:
            result["meetings"]["error"] = "civic-extraction not installed"
        except Exception as e:
            logger.warning(f"Failed to get ProudCity meetings: {e}")
            result["meetings"]["error"] = str(e)[:100]

    # Get issues from SeeClickFix
    try:
        # Derive place_url from jurisdiction_id
        place_url = jurisdiction_id.replace("city-", "")

        from civic_services.clients.seeclickfix_client import SeeClickFixClient
        client = SeeClickFixClient()

        # Get total count by fetching pages
        # SeeClickFix doesn't provide total count, so we paginate
        total_issues = 0
        page = 1
        max_pages = 20  # Safety limit

        while page <= max_pages:
            response = client.get_issues(
                place_url=place_url,
                per_page=100,
                page=page,
                status=None  # All statuses
            )
            issues = response.get("issues", [])
            total_issues += len(issues)

            if not response.get("metadata", {}).get("has_more", False):
                break
            if len(issues) < 100:
                break
            page += 1

        result["issues"]["count"] = total_issues

    except ImportError:
        result["issues"]["error"] = "civic-services not installed"
    except Exception as e:
        logger.warning(f"Failed to get SeeClickFix issues: {e}")
        result["issues"]["error"] = str(e)[:100]

    return result


def calculate_gaps(
    ingested_counts: Dict[str, int],
    source_counts: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculate gaps between ingested and source data.

    Args:
        ingested_counts: Dict mapping data type to ingested count
        source_counts: Dict from get_source_counts()

    Returns:
        Dict with gap analysis:
        {
            "meetings": {"ingested": int, "source": int, "gap": int, "pct": float},
            "issues": {"ingested": int, "source": int, "gap": int, "pct": float},
            "overall_coverage": float
        }
    """
    gaps = {}
    total_ingested = 0
    total_source = 0

    for data_type in ["meetings", "issues"]:
        ingested = ingested_counts.get(data_type, 0)
        source_info = source_counts.get(data_type, {})
        source = source_info.get("count", 0)
        error = source_info.get("error")

        if error:
            gaps[data_type] = {
                "ingested": ingested,
                "source": None,
                "gap": None,
                "pct": None,
                "error": error,
            }
        else:
            gap = source - ingested if source > 0 else 0
            pct = (ingested / source * 100) if source > 0 else 100.0

            gaps[data_type] = {
                "ingested": ingested,
                "source": source,
                "gap": gap,
                "pct": round(pct, 1),
                "error": None,
            }

            total_ingested += ingested
            total_source += source

    # Overall coverage
    gaps["overall_coverage"] = (
        round(total_ingested / total_source * 100, 1)
        if total_source > 0
        else 100.0
    )

    return gaps


def print_status(
    jurisdiction_id: str,
    state_db_path: str = "data/civic_state.db",
    vectors_dir: str = "data/pilot/vectors",
    corpus_filter: Optional[str] = None,
    no_color: bool = False,
    json_only: bool = False,
    check_gaps: bool = False,
) -> Dict[str, Any]:
    """
    Print ingestion status and return status dict.

    Args:
        jurisdiction_id: Jurisdiction to report on
        state_db_path: Path to civic_state.db
        vectors_dir: Path to vectors directory
        corpus_filter: Optional corpus to filter (e.g., "decisions")
        no_color: Disable colored output
        json_only: Skip human-readable output, return dict only
        check_gaps: Query external sources to compare counts

    Returns:
        Status dictionary with all gathered stats
    """
    # Gather stats
    state_stats = get_state_db_stats(state_db_path, jurisdiction_id)
    chroma_stats = get_chroma_stats(jurisdiction_id, vectors_dir)
    file_stats = get_file_stats()

    # Build status dict
    status = {
        "jurisdiction_id": jurisdiction_id,
        "timestamp": datetime.now().isoformat(),
        "state_db": state_stats,
        "chroma_db": chroma_stats,
        "files": file_stats,
    }

    # Gap analysis (optional - queries external sources)
    if check_gaps:
        source_counts = get_source_counts(jurisdiction_id)
        ingested_counts = {
            "meetings": state_stats["meetings"]["count"],
            "issues": state_stats["issues"]["count"],
        }
        gaps = calculate_gaps(ingested_counts, source_counts)
        status["gap_analysis"] = gaps
        status["source_counts"] = source_counts

    # Calculate overall health
    corpus_statuses = []
    for corpus_type, info in chroma_stats["collections"].items():
        if info is not None and info["count"] > 0:
            indicator, _ = get_freshness_indicator(info.get("created_at"))
            corpus_statuses.append(indicator)

    if not corpus_statuses:
        overall = "EMPTY"
        overall_color = Colors.RED
    elif all(s == "OK" for s in corpus_statuses):
        overall = "HEALTHY"
        overall_color = Colors.GREEN
    elif any(s == "OLD" for s in corpus_statuses):
        overall = "DEGRADED"
        overall_color = Colors.YELLOW
    else:
        overall = "OK"
        overall_color = Colors.GREEN

    status["overall_status"] = overall

    # Skip printing if JSON-only mode
    if json_only:
        return status

    # Print header
    title = f"{jurisdiction_id.replace('-', ' ').title()} Ingestion Status"
    print(colorize(f"\n{title}", Colors.BOLD, no_color))
    print("=" * len(title))
    print()

    # Overall status
    print(f"OVERALL: {colorize(overall, overall_color, no_color)}")
    print()

    # ChromaDB Collections
    print(colorize("Vector Collections:", Colors.BOLD, no_color))

    corpus_order = ["decisions", "chunks", "transcripts", "issues", "municipal_code"]
    for corpus_type in corpus_order:
        if corpus_filter and corpus_type != corpus_filter:
            continue

        info = chroma_stats["collections"].get(corpus_type)

        if info is None:
            line = f"  {corpus_type:15} : not indexed"
            print(colorize(line, Colors.DIM, no_color))
        else:
            count = info["count"]
            created_at = info.get("created_at")
            indicator, color = get_freshness_indicator(created_at, no_color)

            age_str = format_relative_time(created_at)
            status_str = colorize(f"[{indicator}]", color, no_color)

            print(f"  {corpus_type:15} : {count:,} indexed | {age_str:12} {status_str}")

    print()

    # State DB stats
    print(colorize("State Database:", Colors.BOLD, no_color))
    print(f"  meetings        : {state_stats['meetings']['count']:,}")
    print(f"  agenda_items    : {state_stats['agenda_items']['count']:,}")
    print(f"  issues          : {state_stats['issues']['count']:,}")
    print(f"  initiatives     : {state_stats['initiatives']['count']:,}")

    if state_stats["issues"]["by_status"]:
        breakdown = ", ".join(
            f"{status}: {count}"
            for status, count in sorted(state_stats["issues"]["by_status"].items())
        )
        print(f"    issue breakdown: {breakdown}")

    print()

    # File sizes
    print(colorize("Storage:", Colors.BOLD, no_color))
    print(f"  civic_state.db  : {format_bytes(file_stats['state_db_size'])}")
    print(f"  chroma.sqlite3  : {format_bytes(chroma_stats['db_size_bytes'])}")
    print()

    # Gap analysis (if enabled)
    if check_gaps and "gap_analysis" in status:
        gaps = status["gap_analysis"]
        print(colorize("Gap Analysis (ingested vs source):", Colors.BOLD, no_color))

        for data_type in ["meetings", "issues"]:
            gap_info = gaps.get(data_type, {})
            ingested = gap_info.get("ingested", 0)
            source = gap_info.get("source")
            gap = gap_info.get("gap")
            pct = gap_info.get("pct")
            error = gap_info.get("error")

            if error:
                line = f"  {data_type:15} : {ingested:,} ingested | source unavailable ({error})"
                print(colorize(line, Colors.DIM, no_color))
            elif source is not None:
                # Color based on coverage percentage
                if pct > 100:
                    # More ingested than source (historical data or API pagination limits)
                    indicator = "OK"
                    color = Colors.GREEN
                    gap_str = f"(+{abs(gap):,} extra)"
                elif pct >= 95:
                    indicator = "OK"
                    color = Colors.GREEN
                    gap_str = f"gap: {gap:,}" if gap > 0 else "complete"
                elif pct >= 80:
                    indicator = "GAP"
                    color = Colors.YELLOW
                    gap_str = f"gap: {gap:,}"
                else:
                    indicator = "LOW"
                    color = Colors.RED
                    gap_str = f"gap: {gap:,}"

                # Cap displayed percentage at 100 for clarity
                display_pct = min(pct, 100.0) if pct > 100 else pct

                status_str = colorize(f"[{indicator}]", color, no_color)
                print(f"  {data_type:15} : {ingested:,}/{source:,} | {display_pct}% coverage | {gap_str} {status_str}")

        overall_coverage = gaps.get("overall_coverage", 0)
        # Cap display at 100% for clarity
        display_coverage = min(overall_coverage, 100.0)
        if overall_coverage >= 95:
            cov_color = Colors.GREEN
        elif overall_coverage >= 80:
            cov_color = Colors.YELLOW
        else:
            cov_color = Colors.RED
        print()
        extra_note = " (includes historical)" if overall_coverage > 100 else ""
        print(f"  Overall coverage: {colorize(f'{display_coverage}%', cov_color, no_color)}{extra_note}")
        print()

    return status


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Civic platform status and diagnostics",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  civic status                           # Show all metrics
  civic status --jurisdiction san-rafael # Specific jurisdiction
  civic status --json                    # Machine-readable output
  civic status --corpus decisions        # Single corpus
  civic status --check-gaps              # Compare ingested vs source counts
        """
    )

    parser.add_argument(
        "--jurisdiction", "-j",
        default="city-san-rafael",
        help="Jurisdiction ID (default: city-san-rafael)"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    parser.add_argument(
        "--corpus", "-c",
        choices=["decisions", "chunks", "transcripts", "issues", "municipal_code"],
        help="Show only specific corpus"
    )

    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output"
    )

    parser.add_argument(
        "--state-db",
        default="data/civic_state.db",
        help="Path to civic_state.db"
    )

    parser.add_argument(
        "--vectors-dir",
        default="data/pilot/vectors",
        help="Path to vectors directory"
    )

    parser.add_argument(
        "--check-gaps",
        action="store_true",
        help="Compare ingested counts against source APIs (may be slow)"
    )

    args = parser.parse_args()

    # Normalize jurisdiction ID
    jurisdiction_id = args.jurisdiction
    if not jurisdiction_id.startswith("city-"):
        jurisdiction_id = f"city-{jurisdiction_id}"

    try:
        status = print_status(
            jurisdiction_id=jurisdiction_id,
            state_db_path=args.state_db,
            vectors_dir=args.vectors_dir,
            corpus_filter=args.corpus,
            no_color=args.no_color or args.json,
            json_only=args.json,
            check_gaps=args.check_gaps,
        )

        if args.json:
            # Convert datetime objects to strings for JSON
            def json_serializer(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

            print(json.dumps(status, indent=2, default=json_serializer))

    except KeyboardInterrupt:
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
