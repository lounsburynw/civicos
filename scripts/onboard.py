#!/usr/bin/env python3
"""
Turnkey jurisdiction onboarding.

Generates configs locally, runs a validation sample, then runs full ingestion.
Single command from zero to searchable data.

Usage:
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin
    python scripts/onboard.py --city "San Anselmo" --state CA --county Marin
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --dry-run
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --skip-ingestion
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --force
    python scripts/onboard.py --city "Mill Valley" --state CA --county Marin --no-validate
    python scripts/onboard.py --cleanup city-austin          # Remove test data + configs
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# Ensure we can import civicos packages
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "civicos-extraction" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "civicos" / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "packages" / "civicos-services" / "src"))

SAMPLE_DAYS = 30
DEFAULT_DAYS_PAST = 365

# Cost model — all rates approximate
# Tier 1: Meeting processing (Modal compute + fetch)
COST_MEETING_FETCH_USD = 0.002        # Modal compute per meeting
COST_MEETING_CHUNKS_USD = 0.003       # PDF parsing per meeting
# Tier 2: LLM extraction (OpenAI)
COST_MEETING_AGENDA_USD = 0.005       # Agenda item extraction per meeting
COST_MEETING_DECISIONS_USD = 0.005    # Decision extraction per meeting
# Tier 3a: YouTube captions (free — auto-generated text, no speaker labels)
COST_CAPTIONS_PER_MEETING = 0.0       # YouTube Data API, free tier
# Tier 3b: AssemblyAI transcription (high-quality + speaker diarization)
COST_TRANSCRIPTION_PER_HOUR = 0.21    # Universal v3 Pro
COST_DIARIZATION_PER_HOUR = 0.02      # Speaker diarization add-on
AVG_MEETING_HOURS = 1.5               # Default estimate for city council meetings
# Flat costs (independent of meeting count)
COST_VECTOR_FLAT_USD = 0.10           # Vector indexing (GPU)
COST_ISSUES_FLAT_USD = 0.02           # SeeClickFix fetch
COST_MUNICIPAL_FLAT_USD = 0.05        # Municipal code fetch
COST_LEGISLATION_FLAT_USD = 0.20      # LegiScan sync

# Transcript modes
TRANSCRIPT_NONE = "none"              # No transcripts
TRANSCRIPT_CAPTIONS = "captions"      # YouTube auto-captions (free, no speaker labels)
TRANSCRIPT_ASSEMBLYAI = "assemblyai"  # AssemblyAI (paid, speaker diarization)


def _estimate_cost(sample_meetings: int, sample_days: int, full_days: int,
                   has_meetings: bool = True, has_issues: bool = True,
                   has_municipal: bool = False, has_legislation: bool = False,
                   transcript_mode: str = TRANSCRIPT_NONE,
                   has_diarization: bool = False,
                   avg_meeting_hours: float = AVG_MEETING_HOURS) -> dict:
    """Extrapolate cost from sample to full backfill.

    transcript_mode controls audio cost:
        "none"       — no transcription
        "captions"   — YouTube auto-captions (free, searchable, no speakers)
        "assemblyai" — AssemblyAI ($0.21/hr + optional $0.02/hr diarization)

    Returns dict with projected_meetings, line items by tier, and total.
    """
    if sample_days <= 0 or not has_meetings:
        projected = 0
    else:
        projected = int(sample_meetings * (full_days / sample_days))

    # Tier 1+2: Per-meeting costs
    per_meeting = COST_MEETING_FETCH_USD + COST_MEETING_CHUNKS_USD
    per_meeting += COST_MEETING_AGENDA_USD + COST_MEETING_DECISIONS_USD
    meeting_cost = projected * per_meeting

    # Tier 3: Transcription
    transcription_cost = 0.0
    if transcript_mode == TRANSCRIPT_ASSEMBLYAI and projected > 0:
        hourly_rate = COST_TRANSCRIPTION_PER_HOUR
        if has_diarization:
            hourly_rate += COST_DIARIZATION_PER_HOUR
        transcription_cost = projected * avg_meeting_hours * hourly_rate
    # captions mode: $0.00 (YouTube API free tier)

    # Flat costs
    flat_cost = COST_VECTOR_FLAT_USD
    if has_issues:
        flat_cost += COST_ISSUES_FLAT_USD
    if has_municipal:
        flat_cost += COST_MUNICIPAL_FLAT_USD
    if has_legislation:
        flat_cost += COST_LEGISLATION_FLAT_USD

    return {
        "projected_meetings": projected,
        "meeting_cost": meeting_cost,
        "transcription_cost": transcription_cost,
        "transcript_mode": transcript_mode,
        "flat_cost": flat_cost,
        "total": meeting_cost + transcription_cost + flat_cost,
        "has_diarization": has_diarization,
    }


def _get_data_counts(database_url: str, jid: str) -> dict:
    """Query PostgreSQL for corpus counts."""
    from civicos.storage.postgres_backend import PostgresBackend
    backend = PostgresBackend(database_url)
    meetings = backend.get_meetings(jid)
    meeting_count = len(meetings)
    decision_count = backend.get_decision_count(jid)
    chunk_count = backend.get_chunk_count(jid)
    agenda_item_count = backend.get_agenda_item_count(jid)
    municipal_code_count = backend.get_municipal_code_count(jid)

    return {
        "meetings": meeting_count,
        "decisions": decision_count,
        "chunks": chunk_count,
        "agenda_items": agenda_item_count,
        "municipal_code": municipal_code_count,
    }


class QualityIssue:
    """A quality issue with severity and remediation guidance."""

    CRITICAL = "CRITICAL"  # Blocks progression — likely config error or platform failure
    WARNING = "WARNING"    # Informational — may be expected for this platform

    def __init__(self, severity: str, message: str, remediation: str):
        self.severity = severity
        self.message = message
        self.remediation = remediation

    def __str__(self):
        return f"[{self.severity}] {self.message}"


def _quality_report(counts: dict, label: str = "", has_meetings: bool = True,
                    jid: str = "") -> tuple:
    """Generate quality report with severity-classified issues.

    Returns (lines, issues) where issues is a list of QualityIssue objects.
    CRITICAL issues should block progression; WARNING issues are informational.
    """
    lines = []
    issues = []
    meetings = counts["meetings"]
    municipal_code = counts.get("municipal_code", 0)

    header = f"Quality Report{f' ({label})' if label else ''}"
    lines.append(f"\n  {header}")
    lines.append(f"  {'─' * len(header)}")
    lines.append(f"  Meetings:       {meetings}")
    lines.append(f"  Chunks:         {counts['chunks']}")
    lines.append(f"  Agenda items:   {counts['agenda_items']}")
    lines.append(f"  Decisions:      {counts['decisions']}")
    lines.append(f"  Municipal code: {municipal_code}")

    config_hint = f"data/extraction/{jid}.json" if jid else "extraction config"

    if meetings == 0 and has_meetings:
        issues.append(QualityIssue(
            QualityIssue.CRITICAL,
            "meetings = 0 on a meeting-capable platform",
            f"Check {config_hint}: verify source_type and base_url are correct. "
            f"Try opening the platform URL in a browser to confirm meetings are listed. "
            f"If the platform requires auth or uses a non-standard format, this may need "
            f"a custom extractor."
        ))
    elif meetings == 0 and not has_meetings:
        # No meeting stages — this is expected, not a failure
        pass

    if meetings > 0:
        chunks_per = counts["chunks"] / meetings
        agenda_per = counts["agenda_items"] / meetings
        decisions_per = counts["decisions"] / meetings
        lines.append(f"\n  Ratios (vs San Rafael baseline):")
        lines.append(f"    chunks/meeting:       {chunks_per:.1f}  (baseline: ~52)")
        lines.append(f"    agenda_items/meeting: {agenda_per:.1f}  (baseline: ~3)")
        lines.append(f"    decisions/meeting:    {decisions_per:.2f}  (baseline: ~0.45)")

        if chunks_per == 0:
            issues.append(QualityIssue(
                QualityIssue.WARNING,
                "chunks/meeting = 0",
                "This platform likely uses HTML agendas instead of PDFs. "
                "Chunk-based search won't work, but agenda item extraction may still succeed. "
                "This is expected for some platforms — not an error."
            ))
        if agenda_per == 0:
            issues.append(QualityIssue(
                QualityIssue.CRITICAL,
                "agenda_items/meeting = 0 — LLM extraction produced nothing",
                f"Check if agendas are behind auth, in an unsupported format (scanned PDF), "
                f"or if the platform URL in {config_hint} points to pages without agenda content. "
                f"Try fetching one meeting URL manually to verify content is accessible."
            ))
        if decisions_per == 0:
            issues.append(QualityIssue(
                QualityIssue.WARNING,
                "decisions/meeting = 0 — no decisions extracted from minutes",
                "Minutes may not be posted yet, or may be too thin for decision extraction. "
                "Decision search won't work until minutes with outcomes are available. "
                "Re-run ingestion after more meetings have occurred."
            ))
        elif decisions_per < 0.1:
            issues.append(QualityIssue(
                QualityIssue.WARNING,
                f"decisions/meeting = {decisions_per:.2f} (low)",
                "Minutes may be thin or only partially posted. "
                "Decision quality will be limited. This often improves over time."
            ))

    # Format issues into report lines
    critical = [i for i in issues if i.severity == QualityIssue.CRITICAL]
    warnings = [i for i in issues if i.severity == QualityIssue.WARNING]

    if critical:
        lines.append(f"\n  CRITICAL ({len(critical)}):")
        for issue in critical:
            lines.append(f"    ✗ {issue.message}")
            lines.append(f"      → {issue.remediation}")
    if warnings:
        lines.append(f"\n  WARNINGS ({len(warnings)}):")
        for issue in warnings:
            lines.append(f"    • {issue.message}")
            lines.append(f"      → {issue.remediation}")
    if not issues:
        lines.append(f"\n  ✓ All quality checks passed")

    return lines, issues


def _get_ingestion_stages(jid: str) -> list:
    """Determine Modal ingestion stages from jurisdiction config.

    Reads the jurisdiction YAML and extraction config to decide which
    stages are appropriate. Avoids running meeting-dependent stages when
    the meeting platform isn't yet supported.
    """
    import yaml as _yaml

    stages = []

    # Check extraction config for meeting source type
    extraction_path = PROJECT_ROOT / "data" / "extraction" / f"{jid}.json"
    source_type = None
    if extraction_path.exists():
        with open(extraction_path) as f:
            ext_config = json.load(f)
        if not isinstance(ext_config, dict) or "source_type" not in ext_config:
            print(f"  Warning: extraction config for {jid} missing source_type field")
        else:
            source_type = ext_config["source_type"]

    # Meeting-dependent stages only if source_type is supported
    from civicos_extraction.clients import SUPPORTED_MEETING_SOURCES, SUPPORTED_ISSUE_SOURCES
    if source_type in SUPPORTED_MEETING_SOURCES:
        stages.extend(["meetings", "chunks", "agenda", "decisions"])
    elif source_type:
        print(f"  Note: source_type '{source_type}' not yet supported for meetings — "
              f"skipping meeting stages (supported: {', '.join(sorted(SUPPORTED_MEETING_SOURCES))})")

    # Issue stages only if issue_source is supported
    issue_source = ext_config.get("issue_source", "seeclickfix") if extraction_path.exists() else "seeclickfix"
    if issue_source in SUPPORTED_ISSUE_SOURCES:
        stages.append("issues")
    else:
        print(f"  Note: issue_source '{issue_source}' not yet supported — "
              f"skipping issue stages (supported: {', '.join(sorted(SUPPORTED_ISSUE_SOURCES))})")

    # Check jurisdiction YAML for optional stages
    yaml_path = PROJECT_ROOT / "data" / "jurisdictions" / f"{jid}.yaml"
    if yaml_path.exists():
        with open(yaml_path) as f:
            jur_config = _yaml.safe_load(f) or {}
        if not isinstance(jur_config, dict):
            print(f"  Warning: jurisdiction YAML for {jid} is not a valid config")
        else:
            ingestion = jur_config.get("ingestion", {})
            if isinstance(ingestion, dict):
                if ingestion.get("municipal_code"):
                    stages.append("municipal")
                if ingestion.get("transcription"):
                    # Use --transcribe (which includes Granicus video discovery)
                    # instead of bare --transcripts when a Granicus domain is configured
                    if ext_config.get("metadata", {}).get("granicus_domain"):
                        stages.append("transcribe")
                    else:
                        stages.append("transcripts")

    # Always include vectors (indexes whatever data exists)
    stages.append("vectors")

    return stages


def _diagnose_config_failure(jid: str, result) -> list:
    """Diagnose why config generation failed. Returns actionable hints for headless agents."""
    diagnostics = []
    extraction_path = PROJECT_ROOT / "data" / "extraction" / f"{jid}.json"

    # Check if extraction config was written (partial success)
    if extraction_path.exists():
        try:
            with open(extraction_path) as f:
                config = json.load(f)

            source_type = config.get("source_type", "unknown")
            base_url = config.get("base_url", "")
            archives = config.get("archives", {})
            default_vid = config.get("metadata", {}).get("default_view_id", "1")

            diagnostics.append(f"Platform detected: {source_type} at {base_url}")

            if not archives:
                diagnostics.append(f"Empty archives — view_id discovery failed")

                if source_type == "granicus":
                    # Probe view_ids to find which ones respond
                    diagnostics.append(f"Probing Granicus view_ids 1-15...")
                    try:
                        import requests
                        domain = config.get("metadata", {}).get("granicus_domain", "")
                        responding = []
                        for vid in range(1, 16):
                            try:
                                url = f"https://{domain}.granicus.com/ViewPublisher.php?view_id={vid}"
                                resp = requests.get(url, timeout=5)
                                if resp.status_code == 200 and len(resp.text) > 1000:
                                    responding.append(vid)
                            except Exception:
                                pass
                        if responding:
                            diagnostics.append(
                                f"Responding view_ids: {responding}. "
                                f"Set archives.multiple to the one with meetings "
                                f"(visit ViewPublisher.php?view_id=N to check)."
                            )
                        else:
                            diagnostics.append(
                                "No view_ids 1-15 responded. "
                                "Search the city website for agenda/minutes links "
                                "to find the correct Granicus URL and view_id."
                            )
                    except Exception as e:
                        diagnostics.append(f"View_id probe failed: {e}")
            else:
                diagnostics.append(f"Archives: {archives}")

        except Exception as e:
            diagnostics.append(f"Could not read extraction config: {e}")
    else:
        diagnostics.append("No extraction config was written — platform detection may have failed entirely")

    return diagnostics


def _probe_meeting_source(jid: str) -> dict:
    """Pre-ingestion probe: validate the extraction client can reach the platform.

    Uses the client's built-in validate() method — no storage layer, no temp
    databases, no full fetch. Just checks config correctness and API reachability.

    For playwright_llm (no validate()), checks env prerequisites instead.

    Returns a dict with:
      - pass: bool
      - source_type: str
      - error: optional error message
      - remediation: optional fix suggestion
      - details: optional ValidationResult dict
    """
    from civicos_extraction.clients.base import ExtractionConfig

    extraction_path = PROJECT_ROOT / "data" / "extraction" / f"{jid}.json"
    if not extraction_path.exists():
        return {"pass": False, "source_type": "unknown",
                "error": "No extraction config found",
                "remediation": "Run config generation first."}

    with open(extraction_path) as f:
        raw_config = json.load(f)

    source_type = raw_config.get("source_type", "unknown")
    base_url = raw_config.get("base_url", "")
    archives = raw_config.get("archives", {})

    # --- Config-level checks (fast, no network) ---

    if source_type == "granicus" and not archives:
        return {"pass": False, "source_type": source_type,
                "error": "Granicus config has empty archives — no view_ids to fetch.",
                "remediation": "Set archives in data/extraction/{}.json "
                "(e.g., {{\"city_council\": \"7\"}}). Check ViewPublisher.php?view_id=N to find valid IDs.".format(jid)}

    if source_type == "civicplus" and not archives:
        return {"pass": False, "source_type": source_type,
                "error": "CivicPlus config has empty archives — no AMIDs to scrape.",
                "remediation": "Set archives in data/extraction/{}.json "
                "(e.g., {{\"city_council\": \"49\"}}). Check Archive.aspx?AMID=N on the city site.".format(jid)}

    if source_type == "playwright_llm":
        # playwright_llm has no validate() — check prerequisites instead
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            return {"pass": False, "source_type": source_type,
                    "error": "Playwright+LLM requires an LLM API key (OPENAI_API_KEY or GOOGLE_API_KEY).",
                    "remediation": "Set OPENAI_API_KEY or GOOGLE_API_KEY in .env."}
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            return {"pass": False, "source_type": source_type,
                    "error": "Playwright not installed.",
                    "remediation": "pip install playwright && python -m playwright install chromium"}
        # Can't cheaply validate without running the LLM, so pass on prereqs alone
        return {"pass": True, "source_type": source_type}

    # --- Client-level validation (hits the platform, no storage) ---

    try:
        ext_config = ExtractionConfig.from_jurisdiction(jid)
        client = _instantiate_client(ext_config)
        if client is None:
            return {"pass": False, "source_type": source_type,
                    "error": f"No client available for source_type '{source_type}'.",
                    "remediation": f"Ensure {source_type} is in SUPPORTED_MEETING_SOURCES."}

        result = client.validate()
        if result.is_valid:
            return {"pass": True, "source_type": source_type, "details": result.to_dict()}

        # Distinguish config errors (fatal) from reachability errors (warning).
        # A valid config with a flaky network check shouldn't block ingestion.
        if not result.config_valid:
            return {"pass": False, "source_type": source_type,
                    "error": "; ".join(result.errors) if result.errors else "Invalid config",
                    "remediation": f"Fix config in data/extraction/{jid}.json.",
                    "details": result.to_dict()}
        else:
            # Config is valid but API check failed — warn, don't block
            return {"pass": True, "source_type": source_type,
                    "warnings": result.errors,
                    "details": result.to_dict()}
    except Exception as e:
        return {"pass": False, "source_type": source_type,
                "error": f"Probe failed: {type(e).__name__}: {e}",
                "remediation": f"Check that {source_type} client works for {base_url}."}


def _instantiate_client(config):
    """Create an extraction source from an ExtractionConfig.

    Uses the Source wrapper classes (not raw Client classes) because the
    wrappers implement validate() from the DataSource protocol.

    Returns None if source_type is unsupported.
    """
    st = config.source_type
    if st == "granicus":
        from civicos_extraction.clients.granicus import GranicusSource
        return GranicusSource(config)
    elif st == "civicplus":
        from civicos_extraction.clients.civicplus import CivicPlusSource
        return CivicPlusSource(config)
    elif st == "proudcity":
        from civicos_extraction.clients.proudcity import ProudCitySource
        return ProudCitySource(config)
    elif st == "legistar":
        from civicos_extraction.clients.legistar import LegistarClient
        return LegistarClient(
            client_name=config.metadata.get("client_name", config.source_id.replace("legistar-", "")),
            jurisdiction_id=config.jurisdiction_id,
        )
    elif st == "civicclerk":
        from civicos_extraction.clients.civicclerk import CivicClerkClient
        return CivicClerkClient(
            subdomain=config.metadata.get("subdomain", config.source_id.replace("civicclerk-", "")),
            jurisdiction_id=config.jurisdiction_id,
        )
    elif st == "escribe":
        from civicos_extraction.clients.escribe import EScribeClient
        return EScribeClient(
            instance_name=config.metadata.get("instance_name", config.source_id.replace("escribe-", "")),
            jurisdiction_id=config.jurisdiction_id,
        )
    elif st == "boarddocs":
        from civicos_extraction.clients.boarddocs import BoardDocsClient
        return BoardDocsClient(
            committee_id=config.metadata.get("committee_id", ""),
            jurisdiction_id=config.jurisdiction_id,
        )
    elif st == "simbli":
        from civicos_extraction.clients.simbli import SimbliClient
        return SimbliClient(
            board_id=config.metadata.get("board_id", ""),
            jurisdiction_id=config.jurisdiction_id,
        )
    elif st == "universal":
        from civicos_extraction.clients.universal import UniversalSource
        return UniversalSource(config)
    elif st == "playwright_llm":
        # playwright_llm has no Source wrapper with validate().
        # Handled by prerequisite checks in _probe_meeting_source() instead.
        return None
    return None


def _check_cron_readiness(jid: str) -> list:
    """Verify a jurisdiction will be picked up by the cron refresh pipeline.

    Checks the same code path that crons use (get_active_jurisdictions,
    source_type dispatch in modal_ingest) without running anything on Modal.

    Returns a list of issue strings. Empty list = ready for crons.
    """
    import yaml as _yaml

    issues = []

    # 1. Check extraction config is parseable by get_active_jurisdictions()
    extraction_path = PROJECT_ROOT / "data" / "extraction" / f"{jid}.json"
    if not extraction_path.exists():
        issues.append(f"No extraction config at {extraction_path.relative_to(PROJECT_ROOT)}")
        return issues

    try:
        with open(extraction_path) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        issues.append(f"Extraction config is invalid JSON: {e}")
        return issues

    if "jurisdiction_id" not in config:
        issues.append("Extraction config missing 'jurisdiction_id' field — "
                       "get_active_jurisdictions() will skip it")

    # 2. Check source_type is handled by modal_ingest.py's fetch_meetings dispatch
    source_type = config.get("source_type", "")
    modal_supported = {
        "proudcity", "granicus", "legistar", "civicclerk",
        "escribe", "boarddocs", "civicplus", "universal", "simbli",
        "playwright_llm",
    }
    if source_type and source_type not in modal_supported:
        issues.append(f"source_type '{source_type}' is not handled by modal_ingest.py "
                       f"(supported: {', '.join(sorted(modal_supported))}). "
                       f"Cron will log a warning and skip meetings for this city.")

    # 3. Check YAML refresh config exists and has valid strategies
    yaml_path = PROJECT_ROOT / "data" / "jurisdictions" / f"{jid}.yaml"
    if not yaml_path.exists():
        issues.append(f"No jurisdiction YAML at {yaml_path.relative_to(PROJECT_ROOT)} — "
                       "refresh intervals won't be configured")
    else:
        try:
            with open(yaml_path) as f:
                jur_config = _yaml.safe_load(f) or {}
            refresh = jur_config.get("refresh", {})
            if not refresh:
                issues.append("YAML has no 'refresh' section — crons will use defaults")
            else:
                valid_strategies = {"incremental", "content_hash", "full"}
                for corpus, cfg in refresh.items():
                    if isinstance(cfg, dict):
                        strategy = cfg.get("strategy", "")
                        if strategy and strategy not in valid_strategies:
                            issues.append(f"refresh.{corpus}.strategy '{strategy}' "
                                          f"is not valid (use: {', '.join(sorted(valid_strategies))})")
        except Exception as e:
            issues.append(f"Could not parse YAML: {e}")

    # 4. Check registry has an entry for this jurisdiction
    registry_path = PROJECT_ROOT / "config" / "registry.json"
    if registry_path.exists():
        try:
            with open(registry_path) as f:
                registry = json.load(f)
            jurisdictions = registry.get("jurisdictions", registry)
            if jid not in jurisdictions:
                issues.append(f"'{jid}' not in config/registry.json — API won't serve it. "
                              "Run: python scripts/generate_registries.py")
        except Exception:
            pass

    return issues


def _run_cleanup(jid: str) -> None:
    """Remove all data and configs for a jurisdiction. Used after test onboarding."""
    from dotenv import load_dotenv
    load_dotenv()

    print(f"Cleaning up {jid}...")

    # 1. Remove from Postgres
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        try:
            import psycopg2
            conn = psycopg2.connect(database_url)
            cur = conn.cursor()
            tables = [
                "vector_embeddings", "chunks", "agenda_items", "decisions",
                "transcripts", "issues", "municipal_code", "meetings",
            ]
            total = 0
            for table in tables:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE jurisdiction_id = %s", (jid,))
                    count = cur.rowcount
                    if count > 0:
                        print(f"  {table}: deleted {count} rows")
                        total += count
                except Exception:
                    conn.rollback()
            conn.commit()
            conn.close()
            if total == 0:
                print(f"  No data found in Postgres for {jid}")
            else:
                print(f"  Total: {total} rows deleted from Postgres")
        except Exception as e:
            print(f"  Could not clean Postgres: {e}")
    else:
        print(f"  No DATABASE_URL — skipping Postgres cleanup")

    # 2. Remove config files
    extraction_path = PROJECT_ROOT / "data" / "extraction" / f"{jid}.json"
    yaml_path = PROJECT_ROOT / "data" / "jurisdictions" / f"{jid}.yaml"
    for path in [extraction_path, yaml_path]:
        if path.exists():
            path.unlink()
            print(f"  Removed {path.relative_to(PROJECT_ROOT)}")

    print(f"Done. {jid} cleaned up.")


def _run_modal_ingestion(jid: str, days_past: int, dry_run: bool = False,
                         stages: str = "all", detach: bool = False) -> int:
    """Run Modal ingestion and return exit code.

    Args:
        detach: If True, adds --detach so the Modal job runs remotely and
                this process doesn't need to stay connected. Use for full
                backfills; avoid for validation samples that need exit codes.
    """
    modal_cmd = ["modal", "run"]
    if detach:
        modal_cmd.append("--detach")
    modal_cmd.append("scripts/modal_ingest.py")

    if stages == "all":
        # Use dynamic stages based on jurisdiction config
        stage_list = _get_ingestion_stages(jid)
        for stage in stage_list:
            modal_cmd.append(f"--{stage}")
    else:
        for stage in stages.split(","):
            modal_cmd.append(f"--{stage.strip()}")

    modal_cmd.extend(["--jurisdiction", jid, "--meetings-days-past", str(days_past)])
    if dry_run:
        modal_cmd.append("--dry-run")

    print(f"  Command: {' '.join(modal_cmd)}")
    if detach:
        print(f"  (detached — job continues on Modal regardless of local connection)")
    print()
    result = subprocess.run(modal_cmd, cwd=str(PROJECT_ROOT))
    return result.returncode


def _update_registry(jid: str) -> bool:
    """Add jurisdiction to config/registry.json using YAML parent info.

    Reads parent_jurisdictions and display_name from the jurisdiction YAML,
    then adds/updates the entry in the registry. Returns True if updated.
    """
    import yaml as _yaml

    yaml_path = PROJECT_ROOT / "data" / "jurisdictions" / f"{jid}.yaml"
    registry_path = PROJECT_ROOT / "config" / "registry.json"

    if not yaml_path.exists():
        print(f"  Warning: No YAML at {yaml_path}, skipping registry update")
        return False

    if not registry_path.exists():
        print(f"  Warning: No registry at {registry_path}, skipping registry update")
        return False

    with open(yaml_path) as f:
        jur = _yaml.safe_load(f) or {}

    with open(registry_path) as f:
        registry = json.load(f)

    jurisdictions = registry.setdefault("jurisdictions", {})

    if jid in jurisdictions:
        print(f"  Registry already has {jid}")
        return False

    # Derive display_name from YAML or jurisdiction ID
    display_name = jur.get("display_name", "")
    if not display_name:
        # "city-mill-valley" -> "Mill Valley"
        slug = re.sub(r"^(city|county|town|district|state|province|council)-", "", jid)
        display_name = slug.replace("-", " ").title()

    # Derive parent_jurisdictions from YAML
    parents = jur.get("parent_jurisdictions", [])
    state = jur.get("financial", {}).get("state", "")
    if not parents and state:
        state_jid = f"state-{state.lower()}"
        parents = [state_jid, "country-united-states"]

    # Build domain slug: "city-mill-valley" -> "mill-valley"
    domain_slug = re.sub(r"^(city|county|town|district|state|province|council)-", "", jid)

    entry = {
        "domain": f"{domain_slug}.civicosproject.org",
        "display_name": display_name,
        "modal_app_name": f"civicos-{domain_slug}",
        "parent_jurisdictions": parents,
    }

    jurisdictions[jid] = entry

    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2)
        f.write("\n")

    print(f"  Added {jid} to registry:")
    print(f"    display_name: {display_name}")
    print(f"    parents: {parents}")
    return True


def _deploy_modal_api() -> int:
    """Deploy the API to Modal. Returns exit code.

    NOTE: The API server (packages/civicos-services/.../api.py) does not yet
    have a Modal wrapper (modal_api.py). Data is written directly to shared
    Postgres/pgvector, so new jurisdictions are queryable without an API
    redeploy. A Modal wrapper is tracked as a separate launch.json item.
    """
    print("  Skipping — no Modal API wrapper exists yet.")
    print("  Data is in Postgres and will be queryable by any API instance reading from it.")
    return 0


def _verify_jurisdiction(jid: str) -> bool:
    """Verify a jurisdiction is queryable on the live API. Returns True if ok."""
    import urllib.request
    import urllib.error

    api_key = os.environ.get("CIVICOS_WEB_KEY", "")
    api_url = "https://civicos--civicos-api-fastapi-app.modal.run/api/v2/civic/search"

    payload = json.dumps({
        "query": "meeting",
        "jurisdiction": jid,
        "corpus": ["meetings"],
        "limit": 1,
    }).encode()

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        req = urllib.request.Request(api_url, data=payload, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            total = data.get("total", 0)
            print(f"  API returned {total} result(s) for '{jid}'")
            return total > 0
    except urllib.error.HTTPError as e:
        print(f"  API error: {e.code} {e.reason}")
        return False
    except Exception as e:
        print(f"  Could not reach API: {e}")
        return False


def _run_batch(cities: list, shared_args: list) -> int:
    """Run onboarding for multiple cities sequentially.

    Each city runs as a separate subprocess so quality gates and cost
    estimates are independent. Returns 0 if all succeed, 1 otherwise.
    """
    results = {}
    total = len(cities)

    print("\n" + "=" * 60)
    print(f"CivicOS Batch Onboard — {total} cities")
    print("=" * 60)
    for i, city in enumerate(cities, 1):
        print(f"\n{'─' * 60}")
        print(f"[{i}/{total}] {city}")
        print(f"{'─' * 60}")

        cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "onboard.py"),
               "--city", city] + shared_args
        rc = subprocess.run(cmd, cwd=str(PROJECT_ROOT)).returncode
        results[city] = rc

    # Aggregate report
    print("\n" + "=" * 60)
    print("Batch Summary")
    print("=" * 60)
    succeeded = [c for c, rc in results.items() if rc == 0]
    failed = [(c, rc) for c, rc in results.items() if rc != 0]

    for city in succeeded:
        print(f"  OK  {city}")
    for city, rc in failed:
        label = "quality issues" if rc == 2 else f"error (exit {rc})"
        print(f"  FAIL  {city} — {label}")

    print(f"\n  {len(succeeded)}/{total} succeeded")
    if failed:
        print(f"  {len(failed)}/{total} failed")

    return 0 if not failed else 1


def main():
    parser = argparse.ArgumentParser(description="Turnkey jurisdiction onboarding")
    parser.add_argument("--city", default="", help="City name (e.g., 'Mill Valley')")
    parser.add_argument("--cities", default="",
                        help="Comma-separated city names for batch mode")
    parser.add_argument("--url", default="", help="Direct platform URL")
    parser.add_argument("--state", default="CA", help="Two-letter state code")
    parser.add_argument("--county", default="", help="County name (e.g., 'Marin')")
    parser.add_argument("--level", default="city", help="Jurisdiction level")
    parser.add_argument("--jurisdiction", default="", help="Override jurisdiction ID")
    parser.add_argument("--days-past", type=int, default=None,
                        help="Days of history (default: from YAML or 365)")
    parser.add_argument("--sample-days", type=int, default=None,
                        help="Days for validation sample (default: from YAML or 30)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't store")
    parser.add_argument("--skip-ingestion", action="store_true", help="Only generate configs")
    parser.add_argument("--no-validate", action="store_true",
                        help="Skip validation gate, run full ingestion immediately")
    parser.add_argument("--force", action="store_true", help="Regenerate configs")
    parser.add_argument("--force-continue", action="store_true",
                        help="Continue past critical quality issues (for debugging)")
    parser.add_argument("--detect-issues", action="store_true",
                        help="Re-detect issue provider for existing config and exit")
    parser.add_argument("--deploy", action="store_true",
                        help="Deploy API to Modal after ingestion (updates registry + redeploys)")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Auto-confirm cost estimate (skip prompt)")
    parser.add_argument("--captions-only", action="store_true",
                        help="Use free YouTube captions instead of AssemblyAI transcription")
    parser.add_argument("--cleanup", metavar="JURISDICTION_ID",
                        help="Remove all data + configs for a jurisdiction (e.g., --cleanup city-austin)")
    parser.add_argument("--sandbox", action="store_true",
                        help="Ingest to local SQLite instead of production Postgres (no Modal required)")
    parser.add_argument("--trial", action="store_true",
                        help="Full sandbox trial: configs → registry → ingest (meetings+issues+elections) → QC. "
                             "No production changes. Outputs structured JSON summary.")
    args = parser.parse_args()

    # --trial implies sandbox + no-validate + skip the Modal validation gate
    if args.trial:
        args.sandbox = True
        args.no_validate = True

    # Cleanup mode: --cleanup city-austin
    if args.cleanup:
        _run_cleanup(args.cleanup)
        return

    # Batch mode: --cities "Corte Madera,Larkspur,Fairfax"
    if args.cities:
        cities = [c.strip() for c in args.cities.split(",") if c.strip()]
        if not cities:
            parser.error("--cities requires at least one city name")

        # Build shared flags (everything except --city/--cities/--url/--jurisdiction)
        shared = []
        if args.state:
            shared.extend(["--state", args.state])
        if args.county:
            shared.extend(["--county", args.county])
        if args.level != "city":
            shared.extend(["--level", args.level])
        if args.days_past is not None:
            shared.extend(["--days-past", str(args.days_past)])
        if args.sample_days is not None:
            shared.extend(["--sample-days", str(args.sample_days)])
        if args.dry_run:
            shared.append("--dry-run")
        if args.skip_ingestion:
            shared.append("--skip-ingestion")
        if args.no_validate:
            shared.append("--no-validate")
        if args.force:
            shared.append("--force")
        if args.force_continue:
            shared.append("--force-continue")
        if args.deploy:
            shared.append("--deploy")
        if args.yes:
            shared.append("--yes")
        if args.captions_only:
            shared.append("--captions-only")

        sys.exit(_run_batch(cities, shared))

    # --level school: use school district lookup table
    if args.level == "school" and not args.url:
        from civicos_extraction.onboard import (
            load_school_districts,
            lookup_school_district,
            lookup_school_districts_by_county,
        )

        districts_table = load_school_districts()
        if not districts_table:
            print("WARNING: data/school_districts.json not found, falling back to standard onboarding")
        else:
            # Batch mode: --county "Marin" --level school
            if args.county and not args.city:
                matches = lookup_school_districts_by_county(args.state, args.county, districts_table)
                if matches:
                    print(f"\nFound {len(matches)} school district(s) in {args.county} County, {args.state}:\n")
                    for i, d in enumerate(matches, 1):
                        existing = (PROJECT_ROOT / "data" / "extraction" / f"{d['jurisdiction_id']}.json").exists()
                        status = " (config exists)" if existing else ""
                        print(f"  {i}. {d['name']} [{d['platform']}]{status}")
                    print()
                    # Run each district through onboarding via --url
                    shared = ["--state", args.state, "--level", "school", "--skip-ingestion"]
                    if args.force:
                        shared.append("--force")
                    if args.dry_run:
                        shared.append("--dry-run")
                    if args.yes:
                        shared.append("--yes")

                    failed = 0
                    for d in matches:
                        jid = d["jurisdiction_id"]
                        extraction_path = PROJECT_ROOT / "data" / "extraction" / f"{jid}.json"
                        if extraction_path.exists() and not args.force:
                            print(f"  [{jid}] Config exists, skipping (use --force to regenerate)")
                            continue
                        cmd = [
                            sys.executable, __file__,
                            "--url", d["board_url"],
                            "--jurisdiction", jid,
                            *shared,
                        ]
                        print(f"  Onboarding {d['name']}...")
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode != 0:
                            print(f"    FAILED: {result.stderr.strip()[:200]}")
                            failed += 1
                        else:
                            print(f"    OK")

                    print(f"\nBatch complete: {len(matches) - failed}/{len(matches)} succeeded")
                    sys.exit(0 if not failed else 1)
                else:
                    print(f"No school districts found for {args.county} County, {args.state}")
                    sys.exit(1)

            # Single lookup: --city "Novato" --level school
            if args.city:
                match = lookup_school_district(args.city, args.state, args.county or None, districts_table)
                if match:
                    print(f"\nFound: {match['name']} [{match['platform']}]")
                    print(f"  URL: {match['board_url']}")
                    print(f"  ID:  {match['jurisdiction_id']}")
                    print()
                    # Set url and jurisdiction from lookup, continue to standard flow
                    args.url = match["board_url"]
                    if not args.jurisdiction:
                        args.jurisdiction = match["jurisdiction_id"]
                else:
                    print(f"No school district matching '{args.city}' in lookup table.")
                    print("Falling back to platform auto-discovery...")

    if not args.city and not args.url:
        parser.error("Provide --city 'City Name', --cities 'A,B,C', or --url 'https://...'")

    start_time = time.time()

    print("\n" + "=" * 60)
    print("CivicOS Turnkey Onboard")
    print("=" * 60)
    if args.city:
        print(f"City: {args.city}")
    if args.url:
        print(f"URL: {args.url}")
    print(f"State: {args.state}, County: {args.county or '(auto-detect)'}")
    print(f"Level: {args.level}")
    if args.jurisdiction:
        print(f"Jurisdiction ID: {args.jurisdiction}")
    print(f"Days of history: {args.days_past or '(auto)'}")
    if not args.no_validate:
        print(f"Validation sample: {args.sample_days or '(auto)'} days")
    print(f"Dry run: {args.dry_run}")
    print("=" * 60)

    # -------------------------------------------------------------------
    # Phase 1: Generate configs locally
    # -------------------------------------------------------------------
    print("\n[Phase 1] Config generation...")

    from dotenv import load_dotenv
    load_dotenv()

    # Derive jurisdiction ID
    jid = args.jurisdiction
    if not jid and args.city:
        # Normalize: lowercase, strip, collapse whitespace/special chars to hyphens
        slug = re.sub(r"[^a-z0-9]+", "-", args.city.strip().lower()).strip("-")
        jid = f"{args.level}-{slug}"

    extraction_path = PROJECT_ROOT / "data" / "extraction" / f"{jid}.json"
    yaml_path = PROJECT_ROOT / "data" / "jurisdictions" / f"{jid}.yaml"

    # --detect-issues: re-run issue provider detection on existing config
    if args.detect_issues:
        from civicos_extraction.onboard import detect_issue_source

        # Try with level prefix first, then without (legacy configs like san-rafael.json)
        if not extraction_path.exists():
            slug = re.sub(r"^(city|county|town|district|state|province|council)-", "", jid)
            alt_path = PROJECT_ROOT / "data" / "extraction" / f"{slug}.json"
            if alt_path.exists():
                extraction_path = alt_path
            else:
                print(f"  ERROR: No extraction config at {extraction_path}")
                sys.exit(1)
        if not args.city:
            parser.error("--detect-issues requires --city")

        print(f"  Probing 311/issue providers for '{args.city}'...")
        detected = detect_issue_source(args.city, jid)

        with open(extraction_path) as f:
            ext_config = json.load(f)

        old_source = ext_config.get("issue_source")
        if detected:
            ext_config["issue_source"] = detected
            with open(extraction_path, "w") as f:
                json.dump(ext_config, f, indent=2)
                f.write("\n")
            if old_source and old_source != detected:
                print(f"  Updated issue_source: {old_source} -> {detected}")
            elif old_source == detected:
                print(f"  Issue source unchanged: {detected}")
            else:
                print(f"  Set issue_source: {detected}")
        else:
            print(f"  No issue provider detected for '{args.city}'")
            if old_source:
                print(f"  Keeping existing issue_source: {old_source}")

        return

    configs_exist = extraction_path.exists() and yaml_path.exists()

    _should_generate = not configs_exist  # Fresh: always generate

    if configs_exist and not args.force:
        print(f"  Configs already exist for {jid}:")
        print(f"    Extraction: {extraction_path}")
        print(f"    YAML: {yaml_path}")
        print(f"  Skipping generation (use --force to regenerate)")
    elif configs_exist and args.force:
        # Check for manual edits before clobbering
        _has_manual_edits = False
        try:
            with open(yaml_path) as _yf:
                _yaml_content = _yf.read()
            if "manually corrected" in _yaml_content or "manually edited" in _yaml_content:
                _has_manual_edits = True
            import json as _json_check
            with open(extraction_path) as _ef:
                _ext_data = _json_check.load(_ef)
            if _ext_data.get("archives") and _ext_data.get("metadata", {}).get("column_map"):
                _has_manual_edits = True
        except Exception:
            pass

        if _has_manual_edits:
            print(f"  WARNING: Existing configs appear to have manual edits:")
            print(f"    Extraction: {extraction_path}")
            print(f"    YAML: {yaml_path}")
            print(f"  --force will overwrite these edits. Backing up...")
            import shutil
            shutil.copy2(extraction_path, str(extraction_path) + ".bak")
            shutil.copy2(yaml_path, str(yaml_path) + ".bak")
            print(f"    Backed up to *.bak files")
        _should_generate = True

    if _should_generate:
        from civicos_extraction.onboard import onboard_jurisdiction

        result = onboard_jurisdiction(
            url=args.url or "",
            jurisdiction_id=args.jurisdiction or None,
            city_name=args.city or None,
            state=args.state,
            county=args.county or None,
            level=args.level,
            generate_yaml=True,
            generate_registries=False,
            validate=1,
            run_pipeline=False,
            index_vectors=False,
            on_progress=lambda step, msg: print(f"  [{step}] {msg}"),
        )

        if not result.success:
            print(f"\nERROR: Config generation failed")
            for err in result.errors:
                print(f"  - {err}")

            # --trial: output structured JSON even on failure so headless agents can parse it
            if args.trial:
                _diag = _diagnose_config_failure(jid, result)
                trial_fail = {
                    "jurisdiction": jid,
                    "trial": True,
                    "pass": False,
                    "phase": "config_generation",
                    "errors": result.errors,
                    "diagnostics": _diag,
                    "next_steps": result.next_steps if hasattr(result, 'next_steps') else [],
                }
                if _diag:
                    print(f"\n  Diagnostics:")
                    for d in _diag:
                        print(f"    - {d}")
                print(f"\n[TRIAL_RESULT_JSON]")
                print(json.dumps(trial_fail))

            sys.exit(1)

        jid = result.jurisdiction_id
        print(f"\n  Jurisdiction ID: {jid}")
        print(f"  Extraction config: {result.config_path}")
        if result.discovered_bodies:
            print(f"  Discovered {len(result.discovered_bodies)} meeting bodies:")
            for name, view_id in result.discovered_bodies.items():
                print(f"    - {name} (view {view_id})")

    # Enrich YAML with county if provided and missing
    yaml_path = PROJECT_ROOT / "data" / "jurisdictions" / f"{jid}.yaml"
    if args.county and yaml_path.exists():
        import yaml as _yaml
        with open(yaml_path) as f:
            data = _yaml.safe_load(f) or {}
        needs_update = False
        if "financial" not in data or not data.get("financial", {}).get("county"):
            state_upper = args.state.upper() if args.state else ""
            data.setdefault("financial", {})
            data["financial"]["state"] = state_upper
            data["financial"]["county"] = args.county
            needs_update = True
        if "federal_programs" not in data:
            data["federal_programs"] = {
                "hud_grantee": f"{args.county} County",
                "hud_relationship": "consortium",
                "notes": f"Receives HUD funds via {args.county} County",
            }
            needs_update = True
        if needs_update:
            with open(yaml_path, "w") as f:
                _yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            print(f"  Enriched YAML with county: {args.county}")

    # Auto-detect YouTube channel for meeting transcripts
    yaml_path = PROJECT_ROOT / "data" / "jurisdictions" / f"{jid}.yaml"
    if yaml_path.exists() and args.city:
        import yaml as _yaml_yt
        with open(yaml_path) as f:
            yt_data = _yaml_yt.safe_load(f) or {}

        # Only probe if transcripts section doesn't already have a channel_id
        transcripts = yt_data.get("data_sources", {}).get("transcripts", {})
        if not transcripts.get("channel_id"):
            print(f"\n  Probing YouTube for '{args.city}' meeting channel...")
            from civicos_extraction.onboard import detect_youtube_channel
            yt_result = detect_youtube_channel(args.city, args.state or "")
            if yt_result:
                print(f"  Found: {yt_result['channel_title']} ({yt_result['channel_id']})")
                yt_data.setdefault("data_sources", {})
                yt_data["data_sources"].setdefault("transcripts", {})
                yt_data["data_sources"]["transcripts"]["source"] = "youtube"
                yt_data["data_sources"]["transcripts"]["channel_id"] = yt_result["channel_id"]
                yt_data["data_sources"]["transcripts"]["channel_title"] = yt_result["channel_title"]
                with open(yaml_path, "w") as f:
                    _yaml_yt.dump(yt_data, f, default_flow_style=False, sort_keys=False)
                print(f"  Updated YAML with YouTube channel.")
            else:
                print(f"  No YouTube channel found (will skip transcription).")
        else:
            print(f"\n  YouTube channel already configured: {transcripts.get('channel_id')}")

    # -------------------------------------------------------------------
    # Resolve defaults: CLI flags > YAML ingestion config > hardcoded
    # -------------------------------------------------------------------
    yaml_path = PROJECT_ROOT / "data" / "jurisdictions" / f"{jid}.yaml"
    if yaml_path.exists():
        import yaml as _yaml2
        with open(yaml_path) as f:
            _jur_cfg = _yaml2.safe_load(f) or {}
        _ing = _jur_cfg.get("ingestion", {}) if isinstance(_jur_cfg.get("ingestion"), dict) else {}
    else:
        _ing = {}

    if args.days_past is None:
        args.days_past = _ing.get("days_past", DEFAULT_DAYS_PAST)
    if args.sample_days is None:
        args.sample_days = _ing.get("sample_days", SAMPLE_DAYS)

    # -------------------------------------------------------------------
    # Phase 2: Check existing data
    # -------------------------------------------------------------------
    print(f"\n[Phase 2] Checking existing data for {jid}...")

    # Pre-compute stages to inform quality checks
    ingestion_stages = _get_ingestion_stages(jid)
    has_meetings = "meetings" in ingestion_stages
    print(f"  Ingestion stages: {', '.join(ingestion_stages)}")

    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        try:
            counts_before = _get_data_counts(database_url, jid)
            print(f"  Existing meetings:       {counts_before['meetings']}")
            print(f"  Existing chunks:         {counts_before['chunks']}")
            print(f"  Existing agenda items:   {counts_before['agenda_items']}")
            print(f"  Existing decisions:      {counts_before['decisions']}")
            print(f"  Existing municipal code: {counts_before['municipal_code']}")
        except Exception as e:
            print(f"  Could not check: {e}")
            counts_before = None
    else:
        print("  WARNING: No DATABASE_URL set")
        counts_before = None

    if args.skip_ingestion or args.dry_run:
        stage_flags = " ".join(f"--{s}" for s in ingestion_stages)
        print(f"\n[DONE] Configs generated{' (dry run)' if args.dry_run else ''}. To ingest:")
        print(f"  modal run scripts/modal_ingest.py {stage_flags} "
              f"--jurisdiction {jid} --meetings-days-past {args.days_past}")
        return

    # -------------------------------------------------------------------
    # Phase 2.1: Pre-ingestion probe (quick platform check)
    # -------------------------------------------------------------------
    if has_meetings:
        print(f"\n[Phase 2.1] Pre-ingestion probe...")
        probe = _probe_meeting_source(jid)
        if probe["pass"]:
            print(f"  PASS: {probe['source_type']} — config valid, API reachable")
            if probe.get("warnings"):
                for w in probe["warnings"]:
                    print(f"  WARN: {w}")
        else:
            print(f"  FAIL: {probe.get('error', 'Unknown error')}")
            if probe.get("remediation"):
                print(f"  Fix:  {probe['remediation']}")

            if args.trial:
                trial_fail = {
                    "jurisdiction": jid,
                    "trial": True,
                    "pass": False,
                    "phase": "pre_ingestion_probe",
                    "source_type": probe.get("source_type", "unknown"),
                    "error": probe.get("error", ""),
                    "remediation": probe.get("remediation", ""),
                }
                print(f"\n[TRIAL_RESULT_JSON]")
                print(json.dumps(trial_fail))

            if not args.force_continue:
                print(f"\n  Use --force-continue to skip this check and ingest anyway.")
                sys.exit(1)
            else:
                print(f"  --force-continue: proceeding despite probe failure.")

    # -------------------------------------------------------------------
    # Phase 2.5: Validation gate (sample before full backfill)
    # -------------------------------------------------------------------
    if not args.no_validate and args.days_past > args.sample_days:
        print(f"\n[Phase 2.5] Validation gate ({args.sample_days}-day sample)...")
        print(f"  Running sample ingestion to check data quality before full backfill.")

        rc = _run_modal_ingestion(jid, args.sample_days, args.dry_run)
        if rc != 0:
            print(f"\nERROR: Sample ingestion failed (exit code {rc})")
            sys.exit(rc)

        # Check quality after sample
        if database_url:
            try:
                sample_counts = _get_data_counts(database_url, jid)
                report_lines, issues = _quality_report(
                    sample_counts, f"{args.sample_days}-day sample",
                    has_meetings=has_meetings, jid=jid)
                for line in report_lines:
                    print(line)

                critical = [i for i in issues if i.severity == QualityIssue.CRITICAL]
                warnings = [i for i in issues if i.severity == QualityIssue.WARNING]

                if critical:
                    print(f"\n  {len(critical)} CRITICAL issue(s) in sample.")
                    print(f"  Full backfill ({args.days_past} days) would waste LLM tokens.")
                    if args.force_continue:
                        print(f"  --force-continue: proceeding despite critical issues.")
                    else:
                        print(f"  Fix the issues above, then re-run.")
                        print(f"  (Use --force-continue to override this gate)")
                        sys.exit(2)
                elif warnings:
                    print(f"\n  {len(warnings)} warning(s) in sample (non-blocking).")
                else:
                    print(f"\n  Sample looks good.")

                # Determine transcript mode from YAML + env + flags
                _transcript_mode = TRANSCRIPT_NONE
                _has_diarization = False
                _has_legislation = False
                _has_youtube = False
                _yaml_check = PROJECT_ROOT / "data" / "jurisdictions" / f"{jid}.yaml"
                if _yaml_check.exists():
                    import yaml as _yaml_cost
                    with open(_yaml_check) as _yf:
                        _ycfg = _yaml_cost.safe_load(_yf) or {}
                    _ds = _ycfg.get("data_sources", {})
                    _ing_cfg = _ycfg.get("ingestion", {}) if isinstance(_ycfg.get("ingestion"), dict) else {}
                    _has_youtube = bool(_ds.get("transcripts", {}).get("channel_id"))
                    if _has_youtube:
                        if args.captions_only:
                            _transcript_mode = TRANSCRIPT_CAPTIONS
                        elif os.environ.get("ASSEMBLYAI_API_KEY"):
                            _transcript_mode = TRANSCRIPT_ASSEMBLYAI
                            _has_diarization = _ing_cfg.get("diarization", True)
                        else:
                            # YouTube channel found but no AssemblyAI key — default to captions
                            _transcript_mode = TRANSCRIPT_CAPTIONS
                    _has_legislation = bool(_ds.get("legislation"))

                # Cost estimate based on sample
                est = _estimate_cost(
                    sample_meetings=sample_counts["meetings"],
                    sample_days=args.sample_days,
                    full_days=args.days_past,
                    has_meetings=has_meetings,
                    has_issues="issues" in ingestion_stages,
                    has_municipal="municipal" in ingestion_stages,
                    has_legislation=_has_legislation,
                    transcript_mode=_transcript_mode,
                    has_diarization=_has_diarization,
                )
                print(f"\n  Cost Estimate ({args.days_past}-day backfill):")
                print(f"    Projected meetings: ~{est['projected_meetings']}")
                print(f"    Meeting processing (fetch + LLM): ~${est['meeting_cost']:.2f}")
                if est["transcript_mode"] == TRANSCRIPT_ASSEMBLYAI:
                    label = "transcription + diarization" if est["has_diarization"] else "transcription"
                    print(f"    Audio {label} (AssemblyAI): ~${est['transcription_cost']:.2f}")
                elif est["transcript_mode"] == TRANSCRIPT_CAPTIONS:
                    print(f"    Audio captions (YouTube): FREE")
                print(f"    Fixed costs (vectors, issues, etc.): ~${est['flat_cost']:.2f}")
                print(f"    {'─' * 37}")
                print(f"    Total estimated: ~${est['total']:.2f}")
                if _has_youtube and _transcript_mode == TRANSCRIPT_CAPTIONS:
                    if not args.captions_only and not os.environ.get("ASSEMBLYAI_API_KEY"):
                        print(f"    (using free captions — set ASSEMBLYAI_API_KEY for speaker diarization)")
                    elif args.captions_only:
                        print(f"    (--captions-only: using free YouTube captions)")
                elif not _has_youtube and has_meetings:
                    print(f"    (no YouTube channel detected — transcripts unavailable)")

                if not args.yes and not args.force_continue:
                    try:
                        answer = input(f"\n  Proceed with full {args.days_past}-day backfill? [Y/n] ")
                        if answer.strip().lower() in ("n", "no"):
                            print("  Aborted by user.")
                            sys.exit(0)
                    except (EOFError, KeyboardInterrupt):
                        print("\n  Aborted.")
                        sys.exit(0)

            except Exception as e:
                print(f"  Could not run quality check: {e}")
                print(f"  Proceeding with full backfill anyway...")

    # -------------------------------------------------------------------
    # Phase 3: Run ingestion (Modal or local sandbox)
    # -------------------------------------------------------------------
    if args.sandbox:
        print(f"\n[Phase 3] Running LOCAL ingestion (SQLite sandbox)...")
        print(f"  Stages: meetings → issues → vectors")
        print(f"  Days: {args.days_past}")
        local_script = PROJECT_ROOT / "scripts" / "ingest_local.py"
        local_cmd = [
            sys.executable, str(local_script),
            "--jurisdiction", jid,
            "--all",
            "--days-past", str(args.days_past),
        ]
        print(f"  Command: {' '.join(local_cmd)}")
        rc = subprocess.run(local_cmd).returncode
    else:
        print(f"\n[Phase 3] Running Modal ingestion pipeline (detached)...")
        print(f"  Stages: meetings → chunks → agenda → decisions → vectors")
        print(f"  Days: {args.days_past}")
        rc = _run_modal_ingestion(jid, args.days_past, args.dry_run, detach=True)

    if rc != 0:
        print(f"\nERROR: Ingestion failed (exit code {rc})")
        sys.exit(rc)

    # -------------------------------------------------------------------
    # Phase 3.5: Registry + Deploy (optional)
    # -------------------------------------------------------------------
    registry_updated = _update_registry(jid)

    if args.deploy:
        print(f"\n[Phase 3.5] Deploying API to Modal...")
        if registry_updated:
            print(f"  Registry updated — redeploy will pick up new jurisdiction.")
        rc = _deploy_modal_api()
        if rc != 0:
            print(f"  WARNING: Modal deploy failed (exit code {rc})")
            print(f"  Data is ingested but API may not reflect registry changes until redeploy.")
        else:
            print(f"\n  Verifying {jid} is queryable...")
            if _verify_jurisdiction(jid):
                print(f"  {jid} is live!")
            else:
                print(f"  Verification returned 0 results (data may still be indexing).")
    elif registry_updated:
        print(f"\n  Registry updated. Run with --deploy to redeploy API, or:")
        print(f"    modal deploy packages/civicos-services/src/civicos_services/servers/modal_api.py")

    # -------------------------------------------------------------------
    # Phase 3.7: Cron readiness check (will refresh pipeline find this city?)
    # -------------------------------------------------------------------
    print(f"\n[Phase 3.7] Cron readiness check...")
    cron_issues = _check_cron_readiness(jid)
    if cron_issues:
        print(f"  WARNING: {len(cron_issues)} issue(s) that may affect automated refresh:")
        for issue in cron_issues:
            print(f"    - {issue}")
        print(f"\n  The city is onboarded, but crons may skip it or fail.")
        print(f"  Fix these before relying on automated refresh.")
    else:
        print(f"  PASS: {jid} will be picked up by cron refresh pipelines.")

    # -------------------------------------------------------------------
    # Phase 4: Quality report
    # -------------------------------------------------------------------
    elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"Onboard Complete: {jid}")
    print(f"Total time: {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print("=" * 60)

    exit_code = 0

    if args.sandbox:
        db_path = PROJECT_ROOT / "data" / f"sandbox_{jid}.sqlite"

        # --trial: also run elections, registries, and QC
        if args.trial:
            # Elections are already included via --all in ingest_local.py
            # Registry generation
            print(f"\n[Phase 3c] Registry generation...")
            reg_cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "generate_registries.py")]
            subprocess.run(reg_cmd, capture_output=True)
            print(f"  Registry updated.")

            # QC
            print(f"\n[Phase 4] Quality check...")
            qc_cmd = [
                sys.executable, str(PROJECT_ROOT / "scripts" / "qc_sandbox.py"),
                "--jurisdiction", jid, "--json",
                "--db", str(db_path),
            ]
            qc_result = subprocess.run(qc_cmd, capture_output=True, text=True)
            try:
                qc_data = json.loads(qc_result.stdout)
                qc_pass = qc_data.get("pass", False)

                # Print human-readable summary with quality metrics
                print(f"\n  {'PASS' if qc_pass else 'FAIL'}: {jid}")

                for name, corpus in qc_data.get("corpora", {}).items():
                    count = corpus.get("count", 0)
                    status = "ok" if corpus.get("pass") else "FAIL"
                    details = corpus.get("details", {})

                    # Build inline quality metrics
                    metrics = []
                    if name == "meetings" and count > 0:
                        dr = details.get("date_range", [])
                        if dr and len(dr) == 2 and dr[0] and dr[1]:
                            metrics.append(f"{dr[0][:10]}..{dr[1][:10]}")
                        ac = details.get("agenda_coverage")
                        if ac is not None:
                            metrics.append(f"agenda {ac:.0f}%")
                        vc = details.get("video_coverage")
                        if vc is not None and vc > 0:
                            metrics.append(f"video {vc:.0f}%")
                        types = details.get("types", {})
                        if types:
                            metrics.append(f"{len(types)} bodies")
                    elif name == "issues" and count > 0:
                        dr = details.get("date_range", [])
                        if dr and len(dr) == 2 and dr[0]:
                            metrics.append(f"since {dr[0][:10]}")
                        statuses = details.get("statuses", {})
                        if statuses:
                            metrics.append(" ".join(f"{v} {k}" for k, v in statuses.items()))
                    elif name == "elections" and count > 0:
                        dr = details.get("date_range", [])
                        if dr and len(dr) == 2:
                            metrics.append(f"{dr[0]}..{dr[1]}")
                        sources = details.get("sources", {})
                        if sources:
                            metrics.append(", ".join(sources.keys()))

                    metric_str = f"  ({', '.join(metrics)})" if metrics else ""
                    print(f"    {name:20s} {count:>6d}  [{status}]{metric_str}")

                # LLM review summary (one line)
                llm = qc_data.get("llm_review", {})
                if llm and llm.get("summary"):
                    llm_status = "pass" if llm.get("pass") else "FAIL"
                    print(f"    {'llm_review':20s}        [{llm_status}]  {llm['summary']}")

                if qc_data.get("warnings"):
                    print(f"\n  Warnings:")
                    for w in qc_data["warnings"]:
                        print(f"    - {w}")

                if qc_data.get("errors"):
                    print(f"\n  Errors:")
                    for e in qc_data["errors"]:
                        print(f"    - {e}")

                # Print JSON for headless consumption
                print(f"\n[TRIAL_RESULT_JSON]")
                trial_result = {
                    "jurisdiction": jid,
                    "trial": True,
                    "pass": qc_pass,
                    "database": str(db_path),
                    "elapsed_seconds": round(time.time() - start_time, 1),
                    "qc": qc_data,
                }
                print(json.dumps(trial_result))

            except (json.JSONDecodeError, Exception) as e:
                print(f"  QC output: {qc_result.stdout[:500]}")
                print(f"  QC error: {e}")

            print(f"\n  To clean up: python scripts/onboard.py --cleanup {jid}")
            sys.exit(0 if qc_pass else 1)

        # Regular sandbox (no --trial)
        print(f"\n  [SANDBOX] Data stored in local SQLite: {db_path}")
        print(f"  [SANDBOX] Production Postgres was NOT modified.")
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cur = conn.cursor()
            for table in ["meetings", "chunks", "issues", "agenda_items", "decisions",
                          "elections", "election_contests", "elected_officials"]:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cur.fetchone()[0]
                    if count > 0:
                        print(f"    {table}: {count}")
                except Exception:
                    pass
            conn.close()
        except Exception as e:
            print(f"  Could not read sandbox: {e}")
        print(f"\n  To clean up: python scripts/ingest_local.py --cleanup {jid}")
        print(f"  To also remove configs: python scripts/onboard.py --cleanup {jid}")
        sys.exit(0)

    if database_url:
        try:
            final_counts = _get_data_counts(database_url, jid)
            report_lines, issues = _quality_report(final_counts, "final",
                                                   has_meetings=has_meetings, jid=jid)
            for line in report_lines:
                print(line)

            # Show delta from before
            if counts_before:
                print(f"\n  Delta from start:")
                for key in ["meetings", "chunks", "agenda_items", "decisions", "municipal_code"]:
                    delta = final_counts[key] - counts_before[key]
                    if delta > 0:
                        print(f"    {key}: +{delta}")

            if issues:
                critical = [i for i in issues if i.severity == QualityIssue.CRITICAL]
                warnings = [i for i in issues if i.severity == QualityIssue.WARNING]
                if critical:
                    print(f"\n  {len(critical)} CRITICAL issue(s) — data may not be usable.")
                if warnings:
                    print(f"\n  {len(warnings)} warning(s) — review remediation steps above.")
                exit_code = 2
        except Exception as e:
            print(f"\n  Could not generate quality report: {e}")
            print(f"\n  Verify manually:")
            print(f"    modal run scripts/modal_ingest.py --stats-only --jurisdiction {jid}")
    else:
        print(f"\nVerify:")
        print(f"  modal run scripts/modal_ingest.py --stats-only --jurisdiction {jid}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
