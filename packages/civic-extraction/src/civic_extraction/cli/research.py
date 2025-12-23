"""
CLI for research commands.

Usage:
    # Single query (fast, less comprehensive)
    civic-extract research municipal-funding "San Rafael" "California"
    civic-extract research municipal-funding "San Rafael" "California" --topic housing

    # Ensemble mode (multiple queries, more comprehensive)
    civic-extract research municipal-funding "San Rafael" "California" --ensemble
    civic-extract research municipal-funding "San Rafael" "California" --ensemble --max-queries 10
"""

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def add_research_parser(subparsers: argparse._SubParsersAction) -> None:
    """Add research subcommand parser."""
    research_parser = subparsers.add_parser(
        "research",
        help="Research civic data using AI-powered search",
        description="Research civic data from web sources using AI search providers.",
    )

    research_subparsers = research_parser.add_subparsers(
        dest="research_command",
        help="Research commands",
    )

    # municipal-funding subcommand
    funding_parser = research_subparsers.add_parser(
        "municipal-funding",
        help="Research municipal funding programs",
        description=(
            "Research municipal funding programs (housing trust funds, inclusionary "
            "housing, commercial linkage fees, ballot measures) using AI-powered search.\n\n"
            "Use --ensemble for more comprehensive results via multiple focused queries."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    funding_parser.add_argument(
        "municipality",
        help="Municipality name (e.g., 'San Rafael')",
    )

    funding_parser.add_argument(
        "state",
        help="State name (e.g., 'California')",
    )

    funding_parser.add_argument(
        "--topic",
        default="housing",
        choices=["housing", "transportation", "environment"],
        help="Topic area to research (default: housing)",
    )

    funding_parser.add_argument(
        "--provider",
        default=None,
        help="Search provider to use (default: from CIVIC_SEARCH_PROVIDER env var)",
    )

    # Ensemble mode options
    funding_parser.add_argument(
        "--ensemble",
        action="store_true",
        help="Use ensemble mode: run multiple focused queries and merge results",
    )

    funding_parser.add_argument(
        "--max-workers",
        type=int,
        default=3,
        help="Max parallel queries in ensemble mode (default: 3)",
    )

    funding_parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between queries in seconds (default: 1.0)",
    )

    funding_parser.add_argument(
        "--max-priority",
        type=int,
        default=2,
        choices=[1, 2, 3],
        help="Max query priority to include (1=high only, 3=all) (default: 2)",
    )

    # Output options
    funding_parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output file path for structured JSON (default: auto-generated)",
    )

    funding_parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save audit trail or output files",
    )

    funding_parser.add_argument(
        "--raw-only",
        action="store_true",
        help="Only output raw response, skip parsing/merging",
    )


def run_research(args: argparse.Namespace) -> int:
    """Run research command."""
    if args.research_command is None:
        print("Error: No research command specified.", file=sys.stderr)
        print("Available commands: municipal-funding", file=sys.stderr)
        return 1

    if args.research_command == "municipal-funding":
        if args.ensemble:
            return run_municipal_funding_ensemble(args)
        else:
            return run_municipal_funding(args)

    return 1


def run_municipal_funding(args: argparse.Namespace) -> int:
    """Run single-query municipal funding research."""
    try:
        from civic_extraction.research import MunicipalFundingResearcher
        from civic_extraction.research.providers import get_provider

        # Get provider
        if args.provider:
            provider = get_provider(args.provider)
        else:
            provider = get_provider()

        print(f"{'=' * 60}")
        print(f"MUNICIPAL FUNDING RESEARCH (single query)")
        print(f"{'=' * 60}")
        print(f"Municipality: {args.municipality}")
        print(f"State: {args.state}")
        print(f"Topic: {args.topic}")
        print(f"Provider: {provider.name}")
        print(f"{'=' * 60}")
        print()

        # Create researcher and run
        researcher = MunicipalFundingResearcher(provider=provider)
        result = researcher.research(
            municipality=args.municipality,
            state=args.state,
            topic=args.topic,
            save_audit=not args.no_save,
        )

        # Print results
        print("RAW RESPONSE:")
        print("-" * 60)
        print(result.raw_response.content)
        print()

        print(f"{'=' * 60}")
        print(f"CITATIONS ({len(result.raw_response.citations)} sources)")
        print(f"{'=' * 60}")
        for i, citation in enumerate(result.raw_response.citations, 1):
            print(f"{i}. {citation}")
        print()

        print(f"{'=' * 60}")
        print(f"METADATA")
        print(f"{'=' * 60}")
        print(f"Model: {result.raw_response.model}")
        print(f"Cost: ${result.raw_response.cost:.4f}")
        if result.audit_file:
            print(f"Audit file: {result.audit_file}")
        print()

        # Save structured data if parsing succeeded and not raw-only
        if not args.raw_only and result.parsed_data is not None and not args.no_save:
            output_file = researcher.save_structured_data(result, args.output)
            print(f"✅ Structured data saved to: {output_file}")
            print()
            print("Programs found:")
            for program_id, program in result.parsed_data.programs.items():
                print(f"  - {program_id}: {program.program_name}")
            if result.parsed_data.ballot_measures:
                print("Ballot measures found:")
                for measure_id, measure in result.parsed_data.ballot_measures.items():
                    print(f"  - {measure_id}: {measure.measure_name}")
        elif result.parsed_data is None:
            print("⚠️  Parsing incomplete - see audit file for raw data")
            print("   Use LLM post-processing for full structured extraction")

        return 0

    except ImportError as e:
        print(f"Error: Missing dependency - {e}", file=sys.stderr)
        print("Install with: pip install requests pydantic", file=sys.stderr)
        return 1

    except Exception as e:
        logger.exception("Research failed")
        print(f"Error: {e}", file=sys.stderr)
        return 1


def run_municipal_funding_ensemble(args: argparse.Namespace) -> int:
    """Run ensemble municipal funding research with multiple queries."""
    try:
        from civic_extraction.research import MunicipalFundingResearcher
        from civic_extraction.research.providers import get_provider

        # Get provider
        if args.provider:
            provider = get_provider(args.provider)
        else:
            provider = get_provider()

        print(f"{'=' * 60}")
        print(f"MUNICIPAL FUNDING RESEARCH (ensemble mode)")
        print(f"{'=' * 60}")
        print(f"Municipality: {args.municipality}")
        print(f"State: {args.state}")
        print(f"Topic: {args.topic}")
        print(f"Provider: {provider.name}")
        print(f"Max workers: {args.max_workers}")
        print(f"Query delay: {args.delay}s")
        print(f"Max priority: {args.max_priority}")
        print(f"{'=' * 60}")
        print()

        # Create researcher
        researcher = MunicipalFundingResearcher(provider=provider)

        # Check for config file
        config = researcher._load_municipality_config(args.municipality)
        if config.known_programs or config.custom_queries:
            print(f"📋 Loaded municipality config:")
            print(f"   Known programs: {len(config.known_programs)}")
            print(f"   Custom queries: {len(config.custom_queries)}")
            print(f"   Query overrides: {len(config.query_overrides)}")
            print()

        # Run ensemble research
        print("🔍 Running ensemble queries...")
        print()

        result = researcher.research_ensemble(
            municipality=args.municipality,
            state=args.state,
            topic=args.topic,
            save_audit=not args.no_save,
            max_workers=args.max_workers,
            delay_between_queries=args.delay,
            max_priority=args.max_priority,
        )

        # Print query summaries
        print(f"{'=' * 60}")
        print(f"QUERY RESULTS ({len(result.query_results)} queries)")
        print(f"{'=' * 60}")
        for i, qr in enumerate(result.query_results, 1):
            print(f"\n--- Query {i}: {qr.template_key or 'custom'} ---")
            print(f"Query: {qr.query[:80]}...")
            print(f"Cost: ${qr.response.cost:.4f}")
            print(f"Citations: {len(qr.response.citations)}")
            # Show first 200 chars of response
            preview = qr.response.content[:200].replace('\n', ' ')
            print(f"Preview: {preview}...")

        # Print all citations
        all_citations = []
        for qr in result.query_results:
            all_citations.extend(qr.response.citations)
        all_citations = list(set(all_citations))

        print()
        print(f"{'=' * 60}")
        print(f"ALL CITATIONS ({len(all_citations)} unique sources)")
        print(f"{'=' * 60}")
        for i, citation in enumerate(all_citations, 1):
            print(f"{i}. {citation}")

        # Print summary
        print()
        print(f"{'=' * 60}")
        print(f"SUMMARY")
        print(f"{'=' * 60}")
        print(f"Total queries: {len(result.query_results)}")
        print(f"Total cost: ${result.total_cost:.4f}")
        if result.audit_file:
            print(f"Audit file: {result.audit_file}")

        # Save merged data
        if not args.raw_only and result.merged_data is not None and not args.no_save:
            output_file = researcher.save_ensemble_data(result, args.output)
            print()
            print(f"✅ Merged data saved to: {output_file}")
            print()
            print("Programs found:")
            for program_id, program in result.merged_data.programs.items():
                desc_preview = program.description[:60] + "..." if len(program.description) > 60 else program.description
                print(f"  - {program_id}: {program.program_name}")
                print(f"    {desc_preview}")
            if result.merged_data.ballot_measures:
                print()
                print("Ballot measures found:")
                for measure_id, measure in result.merged_data.ballot_measures.items():
                    print(f"  - {measure_id}: {measure.measure_name} ({measure.status})")
        elif result.merged_data is None:
            print()
            print("⚠️  Merging incomplete - see audit file for raw data")

        return 0

    except ImportError as e:
        print(f"Error: Missing dependency - {e}", file=sys.stderr)
        print("Install with: pip install requests pydantic pyyaml", file=sys.stderr)
        return 1

    except Exception as e:
        logger.exception("Ensemble research failed")
        print(f"Error: {e}", file=sys.stderr)
        return 1
