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
"""

import argparse
import sys

from civic_extraction.cli.audio import add_audio_parser, run_audio
from civic_extraction.cli.discover import add_discover_parser, run_discover
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
    add_discover_parser(subparsers)
    add_youtube_parser(subparsers)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    # Route to appropriate command
    if args.command == "audio":
        return run_audio(args)
    elif args.command == "discover":
        return run_discover(args)
    elif args.command == "youtube":
        return run_youtube(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
