"""
CLI command for jurisdiction onboarding.

Usage:
    civic-extract onboard --city "Mill Valley" --state CA
    civic-extract onboard --city "Mill Valley" --state CA --dry-run
    civic-extract onboard --url https://millvalley.granicus.com --validate 1
    civic-extract onboard --url https://millvalley.granicus.com --run-pipeline
"""

import sys
import time


def add_onboard_parser(subparsers):
    """Add the onboard subcommand parser."""
    parser = subparsers.add_parser(
        "onboard",
        help="Onboard a new jurisdiction from URL or city name",
        description="Auto-detect civic platform, discover meeting bodies, generate config.",
    )
    parser.add_argument(
        "--url",
        help="Platform or city website URL (e.g., https://marin.granicus.com)",
    )
    parser.add_argument(
        "--city",
        help="City name for auto-discovery (e.g., 'Mill Valley')",
    )
    parser.add_argument(
        "--state",
        help="State/province code (required with --city, e.g., CA, TX, ON)",
    )
    parser.add_argument(
        "--jurisdiction-id", "-j",
        help="Override inferred jurisdiction ID",
    )
    parser.add_argument(
        "--level",
        default="city",
        help="Jurisdiction level for ID prefix (default: city)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/extraction",
        help="Config output directory (default: data/extraction)",
    )
    parser.add_argument(
        "--generate-yaml",
        action="store_true",
        help="Also generate jurisdiction YAML file",
    )
    parser.add_argument(
        "--validate",
        type=int,
        default=1,
        metavar="N",
        help="Run N-tier validation after config generation (1-5)",
    )
    parser.add_argument(
        "--run-pipeline",
        action="store_true",
        help="Run extraction pipeline after config generation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes",
    )
    return parser


def run_onboard(args) -> int:
    """Execute the onboard command."""
    # Validate inputs
    if not args.url and not args.city:
        print("Error: at least one of --url or --city is required", file=sys.stderr)
        return 1

    if args.city and not args.state:
        print("Error: --state is required when --city is provided", file=sys.stderr)
        return 1

    # Dry run: just show what would happen
    if args.dry_run:
        print("Dry run mode — no changes will be made\n")
        if args.city:
            print(f"  City:    {args.city}")
            print(f"  State:   {args.state}")
        if args.url:
            print(f"  URL:     {args.url}")
        if args.jurisdiction_id:
            print(f"  ID:      {args.jurisdiction_id}")
        print(f"  Level:   {args.level}")
        print(f"  Output:  {args.output_dir}")
        print(f"  YAML:    {'yes' if args.generate_yaml else 'no'}")
        print(f"  Validate: tier {args.validate}" if args.validate else "  Validate: no")
        print(f"  Pipeline: {'yes' if args.run_pipeline else 'no'}")
        print("\nSteps that would run:")
        print("  1. Detect platform (network)")
        print("  2. Discover meeting bodies (network)")
        if args.city:
            print("  3. Geocode city (network, requires GOOGLE_MAPS_API_KEY)")
        print(f"  {'4' if args.city else '3'}. Save config JSON")
        if args.generate_yaml:
            print(f"  {'5' if args.city else '4'}. Generate jurisdiction YAML")
        if args.validate:
            print(f"  ... Run tier-{args.validate} validation")
        if args.run_pipeline:
            print("  ... Run extraction pipeline")
        return 0

    # Progress callback for CLI output
    def on_progress(step: str, message: str):
        ts = time.strftime("%H:%M:%S")
        print(f"  [{ts}] {step}: {message}", file=sys.stderr)

    from civicos_extraction.onboard import onboard_jurisdiction

    result = onboard_jurisdiction(
        url=args.url or "",
        jurisdiction_id=args.jurisdiction_id,
        output_dir=args.output_dir,
        city_name=args.city,
        state=args.state,
        level=args.level,
        generate_yaml=args.generate_yaml,
        validate=args.validate,
        run_pipeline=args.run_pipeline,
        on_progress=on_progress,
    )

    if result.success:
        print(f"\nOnboarding complete: {result.jurisdiction_id}")
        print(f"  Platform:  {result.detection.get('source_type', 'unknown') if result.detection else 'unknown'}")
        bodies = result.discovered_bodies or {}
        print(f"  Bodies:    {len(bodies)} discovered")
        if result.config_path:
            print(f"  Config:    {result.config_path}")
        if result.validation:
            print(f"  Validation: tier {result.validation.highest_tier_passed} passed")
        if result.pipeline_result:
            print(f"  Pipeline:  {'success' if result.pipeline_result.success else 'failed'}")
        if result.next_steps:
            print("\nNext steps:")
            for step in result.next_steps:
                print(f"  - {step}")
        return 0
    else:
        print(f"\nOnboarding failed:", file=sys.stderr)
        for err in result.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
