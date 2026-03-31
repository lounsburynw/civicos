"""
Tiered Validation Pipeline for Jurisdiction Onboarding

Runs 5 validation tiers, each building on the previous:

| Tier | Name               | Cost   | Time  | What it proves                              |
|------|--------------------|--------|-------|---------------------------------------------|
| 1    | Config+Connectivity| Free   | ~5s   | Config valid, API reachable                 |
| 2    | Fetch+Store        | Free   | ~30s  | Platform returns parseable meetings         |
| 3    | Agenda Extraction  | ~$0.10 | ~2min | LLM can extract items from agendas         |
| 4    | Decision Extraction| ~$0.50 | ~3min | LLM can extract decisions from minutes      |
| 5    | Vector Indexing    | Free   | ~1min | Semantic search works end-to-end            |

Usage:
    from civicos_extraction.validate import validate_jurisdiction
    report = validate_jurisdiction("city-berkeley", tier=3)
    print(report.summary())
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Validation data stored here (project root, gitignored)
def _get_validation_dir() -> Path:
    try:
        return Path(__file__).parents[4] / ".validation"
    except IndexError:
        return Path("/tmp/.validation")

_VALIDATION_DIR = _get_validation_dir()


@dataclass
class TierResult:
    """Result of a single validation tier."""

    tier: int
    name: str
    status: str  # "passed", "failed", "skipped", "error"
    duration_seconds: float
    details: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tier": self.tier,
            "name": self.name,
            "status": self.status,
            "duration_seconds": round(self.duration_seconds, 2),
            "details": self.details,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class ValidationReport:
    """Aggregated result of all validation tiers."""

    jurisdiction_id: str
    tiers: List[TierResult] = field(default_factory=list)
    highest_tier_passed: int = 0

    def summary(self) -> str:
        lines = [
            f"Validation Report: {self.jurisdiction_id}",
            "=" * 50,
        ]
        for t in self.tiers:
            icon = {"passed": "+", "failed": "X", "skipped": "-", "error": "!"}
            lines.append(
                f"  [{icon.get(t.status, '?')}] Tier {t.tier}: {t.name} "
                f"({t.status}, {t.duration_seconds:.1f}s)"
            )
            if t.errors:
                for e in t.errors:
                    lines.append(f"      ERROR: {e}")
            if t.warnings:
                for w in t.warnings:
                    lines.append(f"      WARN: {w}")
            if t.details:
                for k, v in t.details.items():
                    lines.append(f"      {k}: {v}")
        lines.append(f"\nHighest tier passed: {self.highest_tier_passed}")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "jurisdiction_id": self.jurisdiction_id,
            "tiers": [t.to_dict() for t in self.tiers],
            "highest_tier_passed": self.highest_tier_passed,
        }


def _get_validation_dir(jurisdiction_id: str) -> Path:
    """Get (and create) the validation directory for a jurisdiction."""
    d = _VALIDATION_DIR / jurisdiction_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_config(jurisdiction_id: str, config: Optional[Dict[str, Any]] = None):
    """Load ExtractionConfig from dict or file."""
    from civicos_extraction.clients.base import ExtractionConfig

    if config:
        financial = None
        if "financial" in config:
            from civicos_extraction.clients.base import FinancialConfig
            financial = FinancialConfig.from_dict(config["financial"])
        return ExtractionConfig(
            source_id=config["source_id"],
            source_type=config["source_type"],
            jurisdiction_id=config["jurisdiction_id"],
            base_url=config["base_url"],
            auto_discover=config.get("auto_discover", False),
            archives=config.get("archives", {}),
            metadata=config.get("metadata", {}),
            financial=financial,
        )
    return ExtractionConfig.from_jurisdiction(jurisdiction_id)


def _create_source_from_config(config):
    """Create platform-specific source/client from ExtractionConfig."""
    from civicos_extraction.clients.factory import create_source
    return create_source(config)


def _run_tier1(source, config) -> TierResult:
    """Tier 1: Config + Connectivity check."""
    start = time.time()
    errors = []
    warnings = []
    details: Dict[str, Any] = {"source_type": config.source_type}

    try:
        result = source.validate()
        details["config_valid"] = result.config_valid
        details["api_reachable"] = result.api_reachable

        if result.errors:
            errors.extend(result.errors)
        if result.warnings:
            warnings.extend(result.warnings)

        status = "passed" if result.is_valid else "failed"
    except Exception as e:
        errors.append(str(e))
        status = "error"

    return TierResult(
        tier=1,
        name="Config + Connectivity",
        status=status,
        duration_seconds=time.time() - start,
        details=details,
        errors=errors,
        warnings=warnings,
    )


def _run_tier2(source, config, storage) -> TierResult:
    """Tier 2: Fetch meetings and store in SQLite."""
    start = time.time()
    errors = []
    warnings = []
    details: Dict[str, Any] = {}

    try:
        meetings = source.get_meetings(days_ahead=90, days_past=180)
        details["meetings_fetched"] = len(meetings)

        if not meetings:
            errors.append("No meetings returned from API")
            return TierResult(
                tier=2, name="Fetch + Store", status="failed",
                duration_seconds=time.time() - start,
                details=details, errors=errors, warnings=warnings,
            )

        # Store meetings
        result = storage.store_meetings(config.jurisdiction_id, meetings)
        details["meetings_stored"] = result.stored_count

        # Analyze field completeness
        total = len(meetings)
        has_agenda = 0
        has_minutes = 0
        has_video = 0
        for m in meetings:
            md = m.__dict__ if hasattr(m, "__dict__") else (m.to_dict() if hasattr(m, "to_dict") else m)
            if md.get("agenda_url"):
                has_agenda += 1
            if md.get("minutes_url"):
                has_minutes += 1
            if md.get("video_url"):
                has_video += 1

        details["field_completeness"] = {
            "agenda_url": f"{has_agenda}/{total} ({has_agenda * 100 // total}%)",
            "minutes_url": f"{has_minutes}/{total} ({has_minutes * 100 // total}%)",
            "video_url": f"{has_video}/{total} ({has_video * 100 // total}%)",
        }

        if has_agenda == 0:
            warnings.append("No meetings have agenda_url — Tier 3 will be skipped")
        if has_minutes == 0:
            warnings.append("No meetings have minutes_url — Tier 4 will be skipped")

        # Sample meeting
        sample = meetings[0]
        sample_dict = sample.__dict__ if hasattr(sample, "__dict__") else (sample.to_dict() if hasattr(sample, "to_dict") else sample)
        details["sample_meeting"] = {
            "id": sample_dict.get("id"),
            "title": sample_dict.get("title"),
            "date": str(sample_dict.get("meeting_datetime", "")),
        }

        status = "passed" if result.stored_count > 0 else "failed"

    except Exception as e:
        errors.append(str(e))
        status = "error"

    return TierResult(
        tier=2, name="Fetch + Store", status=status,
        duration_seconds=time.time() - start,
        details=details, errors=errors, warnings=warnings,
    )


def _run_tier3(storage, jurisdiction_id: str) -> TierResult:
    """Tier 3: Agenda item extraction via LLM."""
    start = time.time()
    errors = []
    warnings = []
    details: Dict[str, Any] = {}

    try:
        # Get stored meetings with agenda_url
        all_meetings = storage.get_meetings(jurisdiction_id)
        meetings_with_agenda = [m for m in all_meetings if m.get("agenda_url")]

        if not meetings_with_agenda:
            return TierResult(
                tier=3, name="Agenda Extraction", status="skipped",
                duration_seconds=time.time() - start,
                details={"reason": "No meetings with agenda_url"},
                errors=errors, warnings=warnings,
            )

        # Check for API key
        if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            return TierResult(
                tier=3, name="Agenda Extraction", status="skipped",
                duration_seconds=time.time() - start,
                details={"reason": "No LLM API key (GOOGLE_API_KEY or OPENAI_API_KEY)"},
                errors=errors, warnings=warnings,
            )

        # Lazy cross-package import: only needed when LLM keys are present
        from civicos_services.core.llm_provider import get_model_for_task
        from civicos_extraction.processing.agenda_integration import AgendaIntegrator

        provider = get_model_for_task("long_document")
        integrator = AgendaIntegrator(provider=provider)

        # Pick up to 2 meetings
        sample_meetings = meetings_with_agenda[:2]
        total_items = 0
        actionable_count = 0
        sample_item = None

        for meeting in sample_meetings:
            event_dict = {
                "id": meeting.get("id"),
                "title": meeting.get("title"),
                "meeting_datetime": meeting.get("meeting_datetime"),
                "jurisdiction_id": jurisdiction_id,
            }
            items = integrator.parse_agenda_content(meeting["agenda_url"], event_dict)
            if items:
                # Convert AgendaItem objects to dicts for storage
                item_dicts = []
                for item in items:
                    d = item.__dict__ if hasattr(item, "__dict__") else item
                    item_dicts.append(d)
                    if d.get("actionability") == "actionable" or d.get("actionable"):
                        actionable_count += 1

                storage.store_agenda_items(meeting["id"], item_dicts)
                total_items += len(items)

                if not sample_item and item_dicts:
                    sample_item = {
                        "title": item_dicts[0].get("title"),
                        "actionability": item_dicts[0].get("actionability"),
                    }

        details["items_extracted"] = total_items
        details["actionable_count"] = actionable_count
        details["meetings_processed"] = len(sample_meetings)
        if sample_item:
            details["sample_item"] = sample_item

        status = "passed" if total_items > 0 else "failed"

    except Exception as e:
        errors.append(str(e))
        status = "error"

    return TierResult(
        tier=3, name="Agenda Extraction", status=status,
        duration_seconds=time.time() - start,
        details=details, errors=errors, warnings=warnings,
    )


def _run_tier4(storage, jurisdiction_id: str) -> TierResult:
    """Tier 4: Decision extraction via LLM."""
    start = time.time()
    errors = []
    warnings = []
    details: Dict[str, Any] = {}

    try:
        all_meetings = storage.get_meetings(jurisdiction_id)
        meetings_with_minutes = [m for m in all_meetings if m.get("minutes_url")]

        if not meetings_with_minutes:
            return TierResult(
                tier=4, name="Decision Extraction", status="skipped",
                duration_seconds=time.time() - start,
                details={"reason": "No meetings with minutes_url"},
                errors=errors, warnings=warnings,
            )

        if not os.environ.get("GOOGLE_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
            return TierResult(
                tier=4, name="Decision Extraction", status="skipped",
                duration_seconds=time.time() - start,
                details={"reason": "No LLM API key"},
                errors=errors, warnings=warnings,
            )

        # Lazy cross-package import: only needed when LLM keys are present
        from civicos_services.core.llm_provider import get_model_for_task
        from civicos_extraction.processing.retrospective_analyzer import RetrospectiveAnalyzer

        provider = get_model_for_task("long_document")
        analyzer = RetrospectiveAnalyzer(provider=provider)

        sample_meetings = meetings_with_minutes[:2]
        total_decisions = 0
        high_stakes_count = 0
        sample_decision = None

        for meeting in sample_meetings:
            event_dict = {
                "id": meeting.get("id"),
                "title": meeting.get("title"),
                "meeting_datetime": meeting.get("meeting_datetime"),
                "minutes_url": meeting.get("minutes_url"),
                "jurisdiction_id": jurisdiction_id,
            }
            decisions = analyzer.extract_high_stakes_decisions(event_dict)
            if decisions:
                decision_dicts = []
                for dec in decisions:
                    d = dec.__dict__ if hasattr(dec, "__dict__") else dec
                    d.setdefault("meeting_date", str(meeting.get("meeting_datetime", ""))[:10])
                    d.setdefault("meeting_id", meeting.get("id"))
                    decision_dicts.append(d)
                    high_stakes_count += 1

                storage.store_decisions(jurisdiction_id, decision_dicts)
                total_decisions += len(decisions)

                if not sample_decision and decision_dicts:
                    sample_decision = {
                        "title": decision_dicts[0].get("title"),
                        "outcome": decision_dicts[0].get("outcome"),
                    }

        details["decisions_extracted"] = total_decisions
        details["high_stakes_count"] = high_stakes_count
        details["meetings_processed"] = len(sample_meetings)
        if sample_decision:
            details["sample_decision"] = sample_decision

        status = "passed" if total_decisions > 0 else "failed"

    except Exception as e:
        errors.append(str(e))
        status = "error"

    return TierResult(
        tier=4, name="Decision Extraction", status=status,
        duration_seconds=time.time() - start,
        details=details, errors=errors, warnings=warnings,
    )


def _run_tier5(storage, jurisdiction_id: str, validation_dir: Path) -> TierResult:
    """Tier 5: Vector indexing + search test."""
    start = time.time()
    errors = []
    warnings = []
    details: Dict[str, Any] = {}

    try:
        from civicos._internal.legal.embeddings.store import VectorStore

        vector_dir = str(validation_dir / "vectors")
        vector_store = VectorStore(persist_directory=vector_dir)

        # Build documents from stored data
        documents = []

        # Meetings
        meetings = storage.get_meetings(jurisdiction_id)
        for m in meetings:
            doc_text = f"{m.get('title', '')} - {m.get('meeting_datetime', '')}"
            documents.append({
                "id": f"meeting-{m.get('id', '')}",
                "text": doc_text,
                "metadata": {"type": "meeting", "jurisdiction_id": jurisdiction_id},
            })

        # Agenda items
        agenda_items = storage.get_agenda_items(jurisdiction_id=jurisdiction_id)
        for item in agenda_items:
            doc_text = f"{item.get('title', '')} - {item.get('summary', '') or item.get('description', '')}"
            documents.append({
                "id": f"agenda-{item.get('id', '')}",
                "text": doc_text,
                "metadata": {"type": "agenda_item", "jurisdiction_id": jurisdiction_id},
            })

        # Decisions
        decisions = storage.get_decisions(jurisdiction_id)
        for dec in decisions:
            doc_text = f"{dec.get('title', '')} - {dec.get('summary', '')}"
            documents.append({
                "id": f"decision-{dec.get('id', '')}",
                "text": doc_text,
                "metadata": {"type": "decision", "jurisdiction_id": jurisdiction_id},
            })

        if not documents:
            return TierResult(
                tier=5, name="Vector Indexing", status="skipped",
                duration_seconds=time.time() - start,
                details={"reason": "No documents to index"},
                errors=errors, warnings=warnings,
            )

        # Index
        added = vector_store.add_documents(documents)
        details["documents_indexed"] = added

        # Test search
        results = vector_store.search("city council meeting", top_k=3)
        details["search_results"] = len(results)
        if results:
            details["top_result"] = {
                "text": results[0].text[:100],
                "score": round(results[0].score, 3),
            }

        status = "passed" if added > 0 and len(results) > 0 else "failed"

    except ImportError as e:
        warnings.append(f"ChromaDB not available: {e}")
        status = "skipped"
    except Exception as e:
        errors.append(str(e))
        status = "error"

    return TierResult(
        tier=5, name="Vector Indexing", status=status,
        duration_seconds=time.time() - start,
        details=details, errors=errors, warnings=warnings,
    )


def validate_jurisdiction(
    jurisdiction_id: str,
    tier: int = 5,
    config: Optional[Dict[str, Any]] = None,
) -> ValidationReport:
    """
    Run tiered validation for a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction ID (e.g., "city-berkeley")
        tier: Maximum tier to run (1-5, default: 5)
        config: Optional config dict (loaded from file if not provided)

    Returns:
        ValidationReport with results for each tier
    """
    report = ValidationReport(jurisdiction_id=jurisdiction_id)

    # Load config
    try:
        extraction_config = _load_config(jurisdiction_id, config)
    except Exception as e:
        report.tiers.append(TierResult(
            tier=0, name="Config Load", status="error",
            duration_seconds=0, errors=[str(e)],
        ))
        return report

    # Create source
    try:
        source = _create_source_from_config(extraction_config)
    except Exception as e:
        report.tiers.append(TierResult(
            tier=0, name="Source Creation", status="error",
            duration_seconds=0, errors=[str(e)],
        ))
        return report

    # Set up validation storage
    validation_dir = _get_validation_dir(jurisdiction_id)
    db_path = str(validation_dir / "store.db")

    from civicos.storage.sqlite_backend import SQLiteBackend
    storage = SQLiteBackend(db_path=db_path)

    # Tier 1: Config + Connectivity
    t1 = _run_tier1(source, extraction_config)
    report.tiers.append(t1)
    if t1.status == "passed":
        report.highest_tier_passed = 1
    if tier <= 1 or t1.status not in ("passed",):
        _save_report(report, validation_dir)
        return report

    # Tier 2: Fetch + Store
    t2 = _run_tier2(source, extraction_config, storage)
    report.tiers.append(t2)
    if t2.status == "passed":
        report.highest_tier_passed = 2
    if tier <= 2 or t2.status not in ("passed",):
        _save_report(report, validation_dir)
        return report

    # Tier 3: Agenda Extraction
    if tier >= 3:
        t3 = _run_tier3(storage, jurisdiction_id)
        report.tiers.append(t3)
        if t3.status == "passed":
            report.highest_tier_passed = 3
        if tier <= 3 or t3.status == "error":
            _save_report(report, validation_dir)
            return report

    # Tier 4: Decision Extraction
    if tier >= 4:
        t4 = _run_tier4(storage, jurisdiction_id)
        report.tiers.append(t4)
        if t4.status in ("passed", "skipped"):
            report.highest_tier_passed = max(report.highest_tier_passed, 4)
        if tier <= 4 or t4.status == "error":
            _save_report(report, validation_dir)
            return report

    # Tier 5: Vector Indexing
    if tier >= 5:
        t5 = _run_tier5(storage, jurisdiction_id, validation_dir)
        report.tiers.append(t5)
        if t5.status in ("passed",):
            report.highest_tier_passed = 5

    _save_report(report, validation_dir)
    return report


def _save_report(report: ValidationReport, validation_dir: Path) -> None:
    """Save report JSON to validation directory."""
    report_path = validation_dir / "report.json"
    with open(report_path, "w") as f:
        json.dump(report.to_dict(), f, indent=2, default=str)
        f.write("\n")
