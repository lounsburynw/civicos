"""
CLI for civic-extraction package.

Usage:
    civic-extract discover --jurisdiction city-san-rafael
    civic-extract discover --jurisdiction city-san-rafael --schedule
    civic-extract discover --jurisdiction city-san-rafael --dry-run

    civic-extract youtube --jurisdiction city-san-rafael
    civic-extract youtube --jurisdiction city-san-rafael --schedule
    civic-extract youtube --jurisdiction city-san-rafael --dry-run

    civic-extract audio --jurisdiction city-san-rafael
    civic-extract audio --jurisdiction city-san-rafael --schedule
    civic-extract audio --jurisdiction city-san-rafael --dry-run

    civic-extract transcribe --jurisdiction city-san-rafael
    civic-extract transcribe --jurisdiction city-san-rafael --schedule
    civic-extract transcribe --jurisdiction city-san-rafael --dry-run

    civic-extract seeclickfix --jurisdiction city-san-rafael
    civic-extract seeclickfix --jurisdiction city-san-rafael --schedule
    civic-extract seeclickfix --jurisdiction city-san-rafael --dry-run

    civic-extract legislative --topic housing
    civic-extract legislative --topic all --schedule
    civic-extract legislative --topic housing --dry-run

    civic-extract monitor --check-all
    civic-extract monitor --pipeline discover --max-age 30

    civic-extract manifest list --jurisdiction city-san-rafael
    civic-extract manifest latest --jurisdiction city-san-rafael

    civic-extract audit --jurisdiction city-san-rafael
"""

import argparse
import sys

from civic_extraction.cli.audio import add_audio_parser, run_audio
from civic_extraction.cli.audit_cli import add_audit_parser, run_audit
from civic_extraction.cli.discover import add_discover_parser, run_discover
from civic_extraction.cli.legislative import add_legislative_parser, run_legislative
from civic_extraction.cli.manifest_cli import add_manifest_parser, run_manifest
from civic_extraction.cli.monitor import add_monitor_parser, run_monitor
from civic_extraction.cli.seeclickfix import add_seeclickfix_parser, run_seeclickfix
from civic_extraction.cli.transcribe import add_transcribe_parser, run_transcribe
from civic_extraction.cli.youtube import add_youtube_parser, run_youtube


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
    add_audio_parser(subparsers)
    add_audit_parser(subparsers)
    add_discover_parser(subparsers)
    add_legislative_parser(subparsers)
    add_manifest_parser(subparsers)
    add_monitor_parser(subparsers)
    add_seeclickfix_parser(subparsers)
    add_transcribe_parser(subparsers)
    add_youtube_parser(subparsers)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    # Route to appropriate command
    if args.command == "audio":
        return run_audio(args)
    elif args.command == "audit":
        return run_audit(args)
    elif args.command == "discover":
        return run_discover(args)
    elif args.command == "legislative":
        return run_legislative(args)
    elif args.command == "manifest":
        return run_manifest(args)
    elif args.command == "monitor":
        return run_monitor(args)
    elif args.command == "seeclickfix":
        return run_seeclickfix(args)
    elif args.command == "transcribe":
        return run_transcribe(args)
    elif args.command == "youtube":
        return run_youtube(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
