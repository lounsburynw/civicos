"""
CLI for civic-extraction package.

Usage:
    civic-extract discover --jurisdiction city-san-rafael
    civic-extract discover --jurisdiction city-san-rafael --schedule
    civic-extract discover --jurisdiction city-san-rafael --dry-run

    civic-extract agenda --jurisdiction city-san-rafael
    civic-extract agenda --jurisdiction city-san-rafael --dry-run
    civic-extract agenda --jurisdiction city-san-rafael --cloud
    civic-extract agenda --jurisdiction city-san-rafael --limit 5

    civic-extract youtube --jurisdiction city-san-rafael
    civic-extract youtube --jurisdiction city-san-rafael --schedule
    civic-extract youtube --jurisdiction city-san-rafael --dry-run

    civic-extract youtube-boards --jurisdiction school-san-rafael
    civic-extract youtube-boards --jurisdiction school-san-rafael --dry-run
    civic-extract youtube-boards --jurisdiction school-san-rafael --cloud
    civic-extract youtube-boards --jurisdiction school-san-rafael --validate

    civic-extract audio --jurisdiction city-san-rafael
    civic-extract audio --jurisdiction city-san-rafael --schedule
    civic-extract audio --jurisdiction city-san-rafael --dry-run

    civic-extract transcribe --jurisdiction city-san-rafael
    civic-extract transcribe --jurisdiction city-san-rafael --schedule
    civic-extract transcribe --jurisdiction city-san-rafael --dry-run

    civic-extract decisions --jurisdiction city-san-rafael
    civic-extract decisions --jurisdiction city-san-rafael --schedule
    civic-extract decisions --jurisdiction city-san-rafael --dry-run
    civic-extract decisions --jurisdiction city-san-rafael --cloud

    civic-extract chunks --jurisdiction city-san-rafael
    civic-extract chunks --jurisdiction city-san-rafael --schedule
    civic-extract chunks --jurisdiction city-san-rafael --dry-run
    civic-extract chunks --jurisdiction city-san-rafael --cloud

    civic-extract vectors --jurisdiction city-san-rafael
    civic-extract vectors --jurisdiction city-san-rafael --corpus decisions
    civic-extract vectors --jurisdiction city-san-rafael --stats
    civic-extract vectors --jurisdiction city-san-rafael --dry-run

    civic-extract issues --jurisdiction city-san-rafael
    civic-extract issues --jurisdiction city-san-rafael --provider seeclickfix
    civic-extract issues --jurisdiction city-san-rafael --cloud
    civic-extract issues --jurisdiction city-san-rafael --migrate --cloud
    civic-extract issues --jurisdiction city-san-rafael --stats --cloud

    civic-extract seeclickfix --jurisdiction city-san-rafael  # deprecated, use issues
    civic-extract seeclickfix --jurisdiction city-san-rafael --schedule
    civic-extract seeclickfix --jurisdiction city-san-rafael --dry-run

    civic-extract legislative --topic housing
    civic-extract legislative --topic all --schedule
    civic-extract legislative --topic housing --dry-run

    civic-extract municipal-code --jurisdiction city-san-rafael
    civic-extract municipal-code --jurisdiction city-san-rafael --cloud
    civic-extract municipal-code --jurisdiction city-san-rafael --stats --cloud
    civic-extract municipal-code --jurisdiction city-san-rafael --dry-run

    civic-extract uscode --input data/uscode/usc42.xml --stats
    civic-extract uscode --input data/uscode/usc42.xml --cloud
    civic-extract uscode --input data/uscode/usc42.xml --cloud --dry-run

    civic-extract research municipal-funding "San Rafael" "California"
    civic-extract research municipal-funding "San Rafael" "California" --topic housing
    civic-extract research municipal-funding "San Rafael" "California" --provider perplexity

    civic-extract monitor --check-all
    civic-extract monitor --pipeline discover --max-age 30

    civic-extract manifest list --jurisdiction city-san-rafael
    civic-extract manifest latest --jurisdiction city-san-rafael

    civic-extract audit --jurisdiction city-san-rafael

    civic-extract snapshot create --jurisdiction city-san-rafael --version Q1-2026
    civic-extract snapshot list --jurisdiction city-san-rafael
"""

import argparse
import sys

# Load environment variables from .env file before any other imports
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional

from civic_extraction.cli.agenda import add_agenda_parser, run_agenda
from civic_extraction.cli.audio import add_audio_parser, run_audio
from civic_extraction.cli.audit_cli import add_audit_parser, run_audit
from civic_extraction.cli.chunks import add_chunks_parser, run_chunks
from civic_extraction.cli.decisions import add_decisions_parser, run_decisions
from civic_extraction.cli.discover import add_discover_parser, run_discover
from civic_extraction.cli.issues import add_issues_parser, run_issues
from civic_extraction.cli.legislative import add_legislative_parser, run_legislative
from civic_extraction.cli.manifest_cli import add_manifest_parser, run_manifest
from civic_extraction.cli.monitor import add_monitor_parser, run_monitor
from civic_extraction.cli.municipal_code import add_municipal_code_parser, run_municipal_code
from civic_extraction.cli.research import add_research_parser, run_research
from civic_extraction.cli.seeclickfix import add_seeclickfix_parser, run_seeclickfix
from civic_extraction.cli.snapshot_cli import add_snapshot_parser, run_snapshot
from civic_extraction.cli.transcribe import add_transcribe_parser, run_transcribe
from civic_extraction.cli.uscode import add_uscode_parser, run_uscode
from civic_extraction.cli.vectors import add_vectors_parser, run_vectors
from civic_extraction.cli.youtube import add_youtube_parser, run_youtube
from civic_extraction.cli.youtube_boards import add_youtube_boards_parser, run_youtube_boards


def main() -> int:
    """Main entry point for civic-extract CLI."""
    parser = argparse.ArgumentParser(
        prog="civic-extract",
        description="Civic data extraction CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose (debug) logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Add subcommands
    add_agenda_parser(subparsers)
    add_audio_parser(subparsers)
    add_audit_parser(subparsers)
    add_chunks_parser(subparsers)
    add_decisions_parser(subparsers)
    add_discover_parser(subparsers)
    add_issues_parser(subparsers)
    add_legislative_parser(subparsers)
    add_manifest_parser(subparsers)
    add_monitor_parser(subparsers)
    add_municipal_code_parser(subparsers)
    add_research_parser(subparsers)
    add_seeclickfix_parser(subparsers)
    add_snapshot_parser(subparsers)
    add_transcribe_parser(subparsers)
    add_uscode_parser(subparsers)
    add_vectors_parser(subparsers)
    add_youtube_parser(subparsers)
    add_youtube_boards_parser(subparsers)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    # Route to appropriate command
    if args.command == "agenda":
        return run_agenda(args)
    elif args.command == "audio":
        return run_audio(args)
    elif args.command == "audit":
        return run_audit(args)
    elif args.command == "chunks":
        return run_chunks(args)
    elif args.command == "decisions":
        return run_decisions(args)
    elif args.command == "discover":
        return run_discover(args)
    elif args.command == "issues":
        return run_issues(args)
    elif args.command == "legislative":
        return run_legislative(args)
    elif args.command == "manifest":
        return run_manifest(args)
    elif args.command == "monitor":
        return run_monitor(args)
    elif args.command == "municipal-code":
        return run_municipal_code(args)
    elif args.command == "research":
        return run_research(args)
    elif args.command == "seeclickfix":
        return run_seeclickfix(args)
    elif args.command == "snapshot":
        return run_snapshot(args)
    elif args.command == "transcribe":
        return run_transcribe(args)
    elif args.command == "uscode":
        return run_uscode(args)
    elif args.command == "vectors":
        return run_vectors(args)
    elif args.command == "youtube":
        return run_youtube(args)
    elif args.command == "youtube-boards":
        return run_youtube_boards(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
