"""
Unified jurisdiction configuration loader and validator.

Single source of truth for jurisdiction configuration, used by:
- MCP tools (contact info, governance, tool settings)
- Extraction pipelines (source type, archives, financial context)
- CLI deployment (Modal secrets, container config)

Configuration files are stored in data/jurisdictions/*.yaml.

Usage:
    from civicos.jurisdiction_config import load_jurisdiction_config, get_active_jurisdictions

    # Load single jurisdiction
    config = load_jurisdiction_config("city-san-rafael")
    print(config.display_name)  # "San Rafael"
    print(config.data_sources.meetings.source_type)  # "proudcity"

    # Get all active jurisdictions
    for jid, config in get_active_jurisdictions().items():
        print(f"{jid}: {config.level}")

    # Validate a config
    from civicos.jurisdiction_config import validate_jurisdiction_config
    result = validate_jurisdiction_config(config)
    if not result.is_valid:
        for issue in result.errors:
            print(f"  {issue.field}: {issue.message}")
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Default config directory relative to project root
DEFAULT_CONFIG_DIR = "data/jurisdictions"


def _find_project_root() -> Path:
    """Find the project root by looking for known marker files."""
    current = Path(__file__).resolve()

    # Walk up looking for phase.json or .git
    for parent in [current] + list(current.parents):
        if (parent / "phase.json").exists() or (parent / ".git").exists():
            return parent

    # Fallback: assume we're in packages/civicos/src/civicos/
    return current.parent.parent.parent.parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ContactInfo:
    """Contact information for a jurisdiction."""
    clerk_email: str = ""
    city_hall_address: str = ""
    phone: str = ""
    website: str = ""
    public_comment_deadline: str = "5:00 PM day of meeting"
    in_person_time_limit: str = "3 minutes"
    public_comment_subject: str = "Public Comment - [Agenda Item Title]"


@dataclass
class GoverningBody:
    """Governing body information."""
    name: str = "City Council"
    members_title: str = "Mayor and Council Members"
    meeting_schedule: str = ""
    meeting_location: str = ""


@dataclass
class StateInfo:
    """State-level jurisdiction information."""
    abbreviation: str = ""
    timezone: str = "America/Los_Angeles"
    legislature: str = ""
    governor_title: str = "Governor"


@dataclass
class MeetingsSource:
    """Configuration for meeting data extraction."""
    source_type: str = ""  # "proudcity", "granicus", "legistar", etc.
    base_url: str = ""
    auto_discover: bool = False
    archives: Dict[str, str] = field(default_factory=dict)


@dataclass
class TranscriptsSource:
    """Configuration for transcript extraction."""
    source: str = ""  # "youtube", "granicus", etc.
    playlist_id: Optional[str] = None


@dataclass
class DataSources:
    """Data source configuration for extraction pipelines."""
    meetings: MeetingsSource = field(default_factory=MeetingsSource)
    issues: str = ""  # "seeclickfix", "311", etc.
    budget: str = ""  # "opengov", "municipal_portal", etc.
    municipal_code: str = ""  # "municode", "codified", etc.
    transcripts: TranscriptsSource = field(default_factory=TranscriptsSource)
    legislation: str = ""  # "leginfo_api", "congress_api", etc.
    revenue: str = ""  # "state_controller", etc.
    expenditures: str = ""  # "fac_api", etc.
    funding: str = ""  # "usaspending_api", etc.


@dataclass
class FinancialContext:
    """Financial context for HUD/federal data lookups."""
    state: str = ""
    county: str = ""
    sco: Dict[str, str] = field(default_factory=dict)


@dataclass
class USAspendingConfig:
    """USAspending.gov configuration for federal award lookups."""
    search_names: List[str] = field(default_factory=list)  # Recipient names to search
    allowed_names: List[str] = field(default_factory=list)  # Filter false positives
    recipient_uei: str = ""  # Unique Entity Identifier (precise matching)


@dataclass
class FederalPrograms:
    """Federal program relationships."""
    hud_grantee: str = ""
    hud_relationship: str = ""  # "direct", "consortium", "subrecipient"
    usaspending: USAspendingConfig = field(default_factory=USAspendingConfig)
    notes: str = ""


@dataclass
class ModalConfig:
    """Modal deployment configuration."""
    min_containers: int = 0
    secrets: List[str] = field(default_factory=lambda: ["civicos-env"])


@dataclass
class Metadata:
    """Configuration metadata."""
    created: str = ""
    updated: str = ""
    notes: str = ""


@dataclass
class JurisdictionConfig:
    """
    Unified configuration for a jurisdiction.

    Combines MCP tool config, extraction config, and deployment config
    into a single source of truth.
    """
    # Identity
    jurisdiction_id: str
    level: str  # "federal", "state", "county", "city"
    display_name: str

    # Hierarchy
    parent_jurisdictions: List[str] = field(default_factory=list)

    # Contact & Governance (city/county)
    contact_info: ContactInfo = field(default_factory=ContactInfo)
    governing_body: GoverningBody = field(default_factory=GoverningBody)

    # State info (state only)
    state_info: StateInfo = field(default_factory=StateInfo)

    # Data sources (extraction)
    data_sources: DataSources = field(default_factory=DataSources)

    # Financial context
    financial: FinancialContext = field(default_factory=FinancialContext)
    federal_programs: FederalPrograms = field(default_factory=FederalPrograms)

    # Geography
    zip_codes: List[str] = field(default_factory=list)
    neighborhoods: List[str] = field(default_factory=list)

    # Tool configuration
    tools_enabled: Optional[List[str]] = None
    tool_overrides: Dict[str, Any] = field(default_factory=dict)

    # Deployment
    modal: ModalConfig = field(default_factory=ModalConfig)

    # Metadata
    metadata: Metadata = field(default_factory=Metadata)

    # ─────────── Legacy Compatibility Properties ───────────

    @property
    def source_id(self) -> str:
        """Legacy: source_id from extraction config."""
        if self.data_sources.meetings.source_type:
            return f"{self.data_sources.meetings.source_type}-{self.jurisdiction_id.replace('city-', '')}"
        return self.jurisdiction_id

    @property
    def source_type(self) -> str:
        """Legacy: source_type from extraction config."""
        return self.data_sources.meetings.source_type

    @property
    def base_url(self) -> str:
        """Legacy: base_url from extraction config."""
        return self.data_sources.meetings.base_url

    @property
    def archives(self) -> Dict[str, str]:
        """Legacy: archives from extraction config."""
        return self.data_sources.meetings.archives

    @property
    def auto_discover(self) -> bool:
        """Legacy: auto_discover from extraction config."""
        return self.data_sources.meetings.auto_discover

    def to_extraction_dict(self) -> Dict[str, Any]:
        """
        Convert to legacy extraction config dict format.

        For backwards compatibility with existing extraction code.
        """
        result: Dict[str, Any] = {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "jurisdiction_id": self.jurisdiction_id,
            "base_url": self.base_url,
            "auto_discover": self.auto_discover,
            "archives": self.archives,
            "metadata": {
                "created": self.metadata.created,
                "notes": self.metadata.notes,
            },
        }

        # Financial context (only include if populated)
        if self.financial.state or self.financial.county:
            result["financial"] = {
                "state": self.financial.state,
                "county": self.financial.county,
            }
            if self.financial.sco:
                result["financial"]["sco"] = self.financial.sco

        # Federal programs (only include if populated)
        if self.federal_programs.hud_grantee:
            result["federal_programs"] = {
                "hud_grantee": self.federal_programs.hud_grantee,
                "hud_relationship": self.federal_programs.hud_relationship,
            }
            if self.federal_programs.notes:
                result["federal_programs"]["notes"] = self.federal_programs.notes

        # USAspending config (only include if configured)
        usa = self.federal_programs.usaspending
        if usa.search_names or usa.recipient_uei:
            result.setdefault("federal_programs", {})
            usa_dict: Dict[str, Any] = {}
            if usa.search_names:
                usa_dict["search_names"] = usa.search_names
            if usa.allowed_names:
                usa_dict["allowed_names"] = usa.allowed_names
            if usa.recipient_uei:
                usa_dict["recipient_uei"] = usa.recipient_uei
            result["federal_programs"]["usaspending"] = usa_dict

        return result


# ─────────────────────────────────────────────────────────────────────────────
# Config Loading
# ─────────────────────────────────────────────────────────────────────────────


def get_config_dir() -> Path:
    """Get the unified config directory path."""
    if config_dir := os.environ.get("CIVICOS_JURISDICTION_CONFIG_DIR"):
        return Path(config_dir)
    # Also check CIVICOS_JURISDICTIONS_DIR (used by civicos_config.paths / Modal)
    if config_dir := os.environ.get("CIVICOS_JURISDICTIONS_DIR"):
        return Path(config_dir)
    return _find_project_root() / DEFAULT_CONFIG_DIR


def _find_config_file(jurisdiction_id: str) -> Optional[Path]:
    """
    Find the config file for a jurisdiction.

    Looks in:
    1. data/jurisdictions/{jurisdiction_id}.yaml (unified)
    2. data/jurisdictions/{short_name}.yaml (without prefix)
    """
    config_dir = get_config_dir()

    # Try exact match first
    config_file = config_dir / f"{jurisdiction_id}.yaml"
    if config_file.exists():
        return config_file

    # Try without prefix (e.g., "city-san-rafael" -> "san-rafael.yaml")
    for prefix in ["city-", "county-", "state-", "country-"]:
        if jurisdiction_id.startswith(prefix):
            short_name = jurisdiction_id[len(prefix):]
            config_file = config_dir / f"{short_name}.yaml"
            if config_file.exists():
                return config_file

    return None


def _parse_meetings_source(data: Any) -> MeetingsSource:
    """Parse meetings data source from config."""
    if isinstance(data, str):
        # Simple format: just the source type
        return MeetingsSource(source_type=data)
    elif isinstance(data, dict):
        return MeetingsSource(
            source_type=data.get("source_type", ""),
            base_url=data.get("base_url", ""),
            auto_discover=data.get("auto_discover", False),
            archives=data.get("archives", {}),
        )
    return MeetingsSource()


def _parse_transcripts_source(data: Any) -> TranscriptsSource:
    """Parse transcripts data source from config."""
    if isinstance(data, str):
        return TranscriptsSource(source=data)
    elif isinstance(data, dict):
        return TranscriptsSource(
            source=data.get("source", ""),
            playlist_id=data.get("playlist_id"),
        )
    return TranscriptsSource()


def _parse_data_sources(data: Dict[str, Any]) -> DataSources:
    """Parse data sources section from config."""
    return DataSources(
        meetings=_parse_meetings_source(data.get("meetings")),
        issues=data.get("issues", ""),
        budget=data.get("budget", ""),
        municipal_code=data.get("municipal_code", ""),
        transcripts=_parse_transcripts_source(data.get("transcripts")),
        legislation=data.get("legislation", ""),
        revenue=data.get("revenue", ""),
        expenditures=data.get("expenditures", ""),
        funding=data.get("funding", ""),
    )


def _infer_level(jurisdiction_id: str) -> str:
    """Infer jurisdiction level from ID prefix."""
    if jurisdiction_id.startswith("city-"):
        return "city"
    elif jurisdiction_id.startswith("county-"):
        return "county"
    elif jurisdiction_id.startswith("state-"):
        return "state"
    elif jurisdiction_id.startswith("country-"):
        return "federal"
    else:
        return "city"


def _format_display_name(jurisdiction_id: str) -> str:
    """Format jurisdiction ID as display name."""
    for prefix in ["city-", "county-", "state-", "country-"]:
        if jurisdiction_id.startswith(prefix):
            return jurisdiction_id[len(prefix):].replace("-", " ").title()
    return jurisdiction_id.replace("-", " ").title()


def load_jurisdiction_config(jurisdiction_id: str) -> JurisdictionConfig:
    """
    Load unified configuration for a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction identifier (e.g., "city-san-rafael")

    Returns:
        JurisdictionConfig with loaded values or defaults

    Note:
        Returns a default config if no config file found.
        This allows the system to run without config files.
    """
    config_file = _find_config_file(jurisdiction_id)

    if config_file is None:
        logger.warning(f"No config file found for {jurisdiction_id} in {get_config_dir()}")
        return JurisdictionConfig(
            jurisdiction_id=jurisdiction_id,
            level=_infer_level(jurisdiction_id),
            display_name=_format_display_name(jurisdiction_id),
        )

    try:
        with open(config_file, "r") as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Error loading {config_file}: {e}")
        return JurisdictionConfig(
            jurisdiction_id=jurisdiction_id,
            level=_infer_level(jurisdiction_id),
            display_name=_format_display_name(jurisdiction_id),
        )

    # Parse contact info
    contact_data = data.get("contact_info", {})
    contact_info = ContactInfo(
        clerk_email=contact_data.get("clerk_email", ""),
        city_hall_address=contact_data.get("city_hall_address", ""),
        phone=contact_data.get("phone", ""),
        website=contact_data.get("website", ""),
        public_comment_deadline=contact_data.get("public_comment_deadline", "5:00 PM day of meeting"),
        in_person_time_limit=contact_data.get("in_person_time_limit", "3 minutes"),
        public_comment_subject=contact_data.get("public_comment_subject", "Public Comment - [Agenda Item Title]"),
    )

    # Parse governing body
    body_data = data.get("governing_body", {})
    governing_body = GoverningBody(
        name=body_data.get("name", "City Council"),
        members_title=body_data.get("members_title", "Mayor and Council Members"),
        meeting_schedule=body_data.get("meeting_schedule", ""),
        meeting_location=body_data.get("meeting_location", ""),
    )

    # Parse state info (for state-level jurisdictions)
    state_data = data.get("state_info", {})
    state_info = StateInfo(
        abbreviation=state_data.get("abbreviation", ""),
        timezone=state_data.get("timezone", "America/Los_Angeles"),
        legislature=state_data.get("legislature", ""),
        governor_title=state_data.get("governor_title", "Governor"),
    )

    # Parse data sources
    data_sources = _parse_data_sources(data.get("data_sources", {}))

    # Parse financial context
    fin_data = data.get("financial", {})
    financial = FinancialContext(
        state=fin_data.get("state", ""),
        county=fin_data.get("county", ""),
        sco=fin_data.get("sco", {}),
    )

    # Parse federal programs
    fed_data = data.get("federal_programs", {})
    usa_data = fed_data.get("usaspending", {})
    usaspending = USAspendingConfig(
        search_names=usa_data.get("search_names", []),
        allowed_names=usa_data.get("allowed_names", []),
        recipient_uei=usa_data.get("recipient_uei", ""),
    )
    federal_programs = FederalPrograms(
        hud_grantee=fed_data.get("hud_grantee", ""),
        hud_relationship=fed_data.get("hud_relationship", ""),
        usaspending=usaspending,
        notes=fed_data.get("notes", ""),
    )

    # Parse Modal config
    modal_data = data.get("modal", {})
    modal = ModalConfig(
        min_containers=modal_data.get("min_containers", 0),
        secrets=modal_data.get("secrets", ["civicos-env"]),
    )

    # Parse metadata
    meta_data = data.get("metadata", {})
    metadata = Metadata(
        created=meta_data.get("created", ""),
        updated=meta_data.get("updated", ""),
        notes=meta_data.get("notes", ""),
    )

    return JurisdictionConfig(
        jurisdiction_id=data.get("jurisdiction_id", jurisdiction_id),
        level=data.get("level", _infer_level(jurisdiction_id)),
        display_name=data.get("display_name", _format_display_name(jurisdiction_id)),
        parent_jurisdictions=data.get("parent_jurisdictions", []),
        contact_info=contact_info,
        governing_body=governing_body,
        state_info=state_info,
        data_sources=data_sources,
        financial=financial,
        federal_programs=federal_programs,
        zip_codes=data.get("zip_codes", []),
        neighborhoods=data.get("neighborhoods", []),
        tools_enabled=data.get("tools_enabled"),
        tool_overrides=data.get("tool_overrides", {}),
        modal=modal,
        metadata=metadata,
    )


def get_active_jurisdictions() -> Dict[str, JurisdictionConfig]:
    """
    Get all active jurisdiction configurations.

    Scans the config directory for *.yaml files (excluding schema.yaml).

    Returns:
        Dict mapping jurisdiction_id to JurisdictionConfig
    """
    config_dir = get_config_dir()
    jurisdictions: Dict[str, JurisdictionConfig] = {}

    if not config_dir.exists():
        logger.warning(f"Config directory not found: {config_dir}")
        return jurisdictions

    for config_file in config_dir.glob("*.yaml"):
        # Skip schema file
        if config_file.name == "schema.yaml":
            continue

        try:
            with open(config_file) as f:
                data = yaml.safe_load(f) or {}

            jid = data.get("jurisdiction_id")
            if not jid:
                # Derive from filename
                jid = config_file.stem

            config = load_jurisdiction_config(jid)
            jurisdictions[config.jurisdiction_id] = config

        except Exception as e:
            logger.warning(f"Error loading {config_file}: {e}")

    return jurisdictions


# ─────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ─────────────────────────────────────────────────────────────────────────────


def get_hud_grantee(jurisdiction_id: str) -> Optional[str]:
    """
    Get the HUD grantee name for a jurisdiction.

    For cities in consortiums, returns the consortium grantee name.
    """
    config = load_jurisdiction_config(jurisdiction_id)
    return config.federal_programs.hud_grantee or None


def get_hud_relationship(jurisdiction_id: str) -> Optional[str]:
    """Get the HUD relationship type for a jurisdiction."""
    config = load_jurisdiction_config(jurisdiction_id)
    return config.federal_programs.hud_relationship or None


def get_jurisdictions_with_usaspending() -> Dict[str, "JurisdictionConfig"]:
    """Get jurisdictions that have USAspending config (search_names or UEI).

    Returns:
        Dict mapping jurisdiction_id to JurisdictionConfig
    """
    all_jurisdictions = get_active_jurisdictions()
    return {
        jid: config for jid, config in all_jurisdictions.items()
        if config.federal_programs.usaspending.search_names
        or config.federal_programs.usaspending.recipient_uei
    }


def get_extraction_config(jurisdiction_id: str) -> Dict[str, Any]:
    """
    Get extraction config dict for backwards compatibility.

    Returns the legacy extraction config format used by
    civicos_extraction.config.load_jurisdiction_config().
    """
    config = load_jurisdiction_config(jurisdiction_id)
    return config.to_extraction_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Config Validation
# ─────────────────────────────────────────────────────────────────────────────

VALID_LEVELS = {"federal", "state", "county", "city"}
VALID_MEETING_PLATFORMS = {"proudcity", "granicus", "legistar", "civicclerk"}
VALID_ISSUE_PLATFORMS = {"seeclickfix", "311"}
VALID_BUDGET_PLATFORMS = {"opengov", "municipal_portal"}
VALID_CODE_PLATFORMS = {"municode", "codified"}
VALID_TRANSCRIPT_SOURCES = {"youtube", "granicus"}
VALID_HUD_RELATIONSHIPS = {"direct", "consortium", "subrecipient"}
US_STATE_ABBREVIATIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC", "PR", "GU", "VI", "AS", "MP",
}


@dataclass
class ValidationIssue:
    """A single validation finding."""
    field: str          # e.g. "data_sources.meetings.base_url"
    severity: str       # "error", "warning", "info"
    message: str        # What's wrong
    suggestion: str = ""  # How to fix it


@dataclass
class ValidationResult:
    """Result of config validation."""
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def infos(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "info"]

    @property
    def summary(self) -> str:
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} error{'s' if len(self.errors) != 1 else ''}")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warning{'s' if len(self.warnings) != 1 else ''}")
        if self.infos:
            parts.append(f"{len(self.infos)} info")
        return ", ".join(parts) if parts else "valid"


def validate_jurisdiction_config(config: JurisdictionConfig) -> ValidationResult:
    """
    Comprehensive validation of a jurisdiction config.

    Checks:
    - Required identity fields
    - Level-specific requirements (city needs meetings, state needs state_info)
    - Platform-specific rules (proudcity needs base_url, granicus needs publisher_id)
    - Hierarchy consistency
    - Format validation (URLs, emails, zip codes)
    - Data completeness warnings

    Returns:
        ValidationResult with categorized issues and actionable suggestions
    """
    issues: List[ValidationIssue] = []

    # ── 1. Required identity fields ──
    if not config.jurisdiction_id:
        issues.append(ValidationIssue(
            field="jurisdiction_id",
            severity="error",
            message="Missing jurisdiction_id",
            suggestion="Add jurisdiction_id (e.g., 'city-san-rafael', 'state-california')",
        ))

    if not config.level:
        issues.append(ValidationIssue(
            field="level",
            severity="error",
            message="Missing level",
            suggestion=f"Add level: one of {sorted(VALID_LEVELS)}",
        ))
    elif config.level not in VALID_LEVELS:
        issues.append(ValidationIssue(
            field="level",
            severity="error",
            message=f"Invalid level '{config.level}'",
            suggestion=f"Use one of: {sorted(VALID_LEVELS)}",
        ))

    if not config.display_name:
        issues.append(ValidationIssue(
            field="display_name",
            severity="error",
            message="Missing display_name",
            suggestion="Add display_name (e.g., 'San Rafael', 'California')",
        ))

    # Check jurisdiction_id matches level prefix
    if config.jurisdiction_id and config.level:
        expected_prefix = f"{config.level}-" if config.level != "federal" else "country-"
        if not config.jurisdiction_id.startswith(expected_prefix):
            issues.append(ValidationIssue(
                field="jurisdiction_id",
                severity="warning",
                message=f"jurisdiction_id '{config.jurisdiction_id}' doesn't start with expected prefix '{expected_prefix}'",
                suggestion=f"Convention: {config.level}-level IDs start with '{expected_prefix}' (e.g., '{expected_prefix}{config.display_name.lower().replace(' ', '-')}')",
            ))

    # ── 2. Hierarchy validation ──
    if config.level in ("city", "county") and not config.parent_jurisdictions:
        issues.append(ValidationIssue(
            field="parent_jurisdictions",
            severity="warning",
            message=f"{config.level}-level config has no parent_jurisdictions",
            suggestion="Add parent_jurisdictions list (e.g., ['county-marin', 'state-california', 'country-united-states'])",
        ))
    elif config.parent_jurisdictions:
        for parent in config.parent_jurisdictions:
            has_prefix = any(parent.startswith(f"{p}-") for p in ["city", "county", "state", "country"])
            if not has_prefix:
                issues.append(ValidationIssue(
                    field="parent_jurisdictions",
                    severity="warning",
                    message=f"Parent '{parent}' doesn't follow naming convention",
                    suggestion="Parent IDs should be prefixed: city-, county-, state-, or country-",
                ))

    # ── 3. Level-specific: city/county requirements ──
    if config.level in ("city", "county"):
        _validate_city_county(config, issues)

    # ── 4. Level-specific: state requirements ──
    if config.level == "state":
        _validate_state(config, issues)

    # ── 5. Platform-specific meeting rules ──
    if config.data_sources.meetings.source_type:
        _validate_meeting_platform(config, issues)

    # ── 6. Format validation ──
    _validate_formats(config, issues)

    # ── 7. Deployment readiness ──
    _validate_deployment(config, issues)

    is_valid = not any(i.severity == "error" for i in issues)
    return ValidationResult(is_valid=is_valid, issues=issues)


def _validate_city_county(config: JurisdictionConfig, issues: List[ValidationIssue]) -> None:
    """Validate city/county-specific requirements."""
    # Meetings source is required for city/county
    if not config.data_sources.meetings.source_type:
        issues.append(ValidationIssue(
            field="data_sources.meetings.source_type",
            severity="error",
            message=f"Missing meeting platform for {config.level} deployment",
            suggestion=f"Add data_sources.meetings.source_type: one of {sorted(VALID_MEETING_PLATFORMS)}",
        ))

    if not config.data_sources.meetings.base_url:
        issues.append(ValidationIssue(
            field="data_sources.meetings.base_url",
            severity="error",
            message="Missing meeting source base_url",
            suggestion="Add data_sources.meetings.base_url (e.g., 'https://www.cityofsanrafael.org')",
        ))

    # Contact info
    if not config.contact_info.clerk_email:
        issues.append(ValidationIssue(
            field="contact_info.clerk_email",
            severity="warning",
            message="Missing clerk_email — needed for public comment tools",
            suggestion="Add contact_info.clerk_email (e.g., 'clerk@city.gov')",
        ))

    if not config.contact_info.website:
        issues.append(ValidationIssue(
            field="contact_info.website",
            severity="warning",
            message="Missing website — used for platform detection and links",
            suggestion="Add contact_info.website (e.g., 'https://www.cityofsanrafael.org')",
        ))

    # Governing body
    if not config.governing_body.meeting_schedule:
        issues.append(ValidationIssue(
            field="governing_body.meeting_schedule",
            severity="info",
            message="Missing meeting_schedule — shown to users asking about upcoming meetings",
            suggestion="Add governing_body.meeting_schedule (e.g., 'First and third Monday, 7:00 PM')",
        ))

    # Financial context
    if not config.financial.state:
        issues.append(ValidationIssue(
            field="financial.state",
            severity="warning",
            message="Missing financial.state — needed for state data lookups (SCO, legislation)",
            suggestion="Add financial.state as 2-letter abbreviation (e.g., 'CA')",
        ))

    if not config.financial.county:
        issues.append(ValidationIssue(
            field="financial.county",
            severity="warning",
            message="Missing financial.county — needed for HUD/county data correlation",
            suggestion="Add financial.county (e.g., 'Marin')",
        ))

    # HUD grantee info
    if not config.federal_programs.hud_grantee:
        issues.append(ValidationIssue(
            field="federal_programs.hud_grantee",
            severity="info",
            message="Missing HUD grantee — needed for federal funding analysis",
            suggestion="Add federal_programs.hud_grantee. Many cities receive HUD funds via county consortiums.",
        ))

    # Geography
    if not config.zip_codes:
        issues.append(ValidationIssue(
            field="zip_codes",
            severity="info",
            message="No zip codes — used for geographic filtering and SeeClickFix queries",
            suggestion="Add zip_codes list (e.g., ['94901', '94903'])",
        ))


def _validate_state(config: JurisdictionConfig, issues: List[ValidationIssue]) -> None:
    """Validate state-specific requirements."""
    if not config.state_info.abbreviation:
        issues.append(ValidationIssue(
            field="state_info.abbreviation",
            severity="error",
            message="Missing state abbreviation",
            suggestion="Add state_info.abbreviation (e.g., 'CA')",
        ))
    elif config.state_info.abbreviation not in US_STATE_ABBREVIATIONS:
        issues.append(ValidationIssue(
            field="state_info.abbreviation",
            severity="warning",
            message=f"Unrecognized state abbreviation '{config.state_info.abbreviation}'",
            suggestion="Use standard 2-letter US state/territory abbreviation",
        ))

    if not config.state_info.timezone:
        issues.append(ValidationIssue(
            field="state_info.timezone",
            severity="warning",
            message="Missing timezone",
            suggestion="Add state_info.timezone (e.g., 'America/Los_Angeles')",
        ))


def _validate_meeting_platform(config: JurisdictionConfig, issues: List[ValidationIssue]) -> None:
    """Validate platform-specific meeting configuration."""
    platform = config.data_sources.meetings.source_type

    if platform not in VALID_MEETING_PLATFORMS:
        issues.append(ValidationIssue(
            field="data_sources.meetings.source_type",
            severity="warning",
            message=f"Unknown meeting platform '{platform}'",
            suggestion=f"Known platforms: {sorted(VALID_MEETING_PLATFORMS)}. Custom platforms may work but aren't validated.",
        ))
        return

    # ProudCity: needs base_url and ideally archives
    if platform == "proudcity":
        if not config.data_sources.meetings.archives:
            issues.append(ValidationIssue(
                field="data_sources.meetings.archives",
                severity="warning",
                message="ProudCity config has no archives — only auto-discovered meetings will be scraped",
                suggestion="Add archives map or set auto_discover: true. Run platform detection to discover meeting types.",
            ))

    # Granicus: archives entries need publisher_id/view_id
    elif platform == "granicus":
        for name, archive_data in config.data_sources.meetings.archives.items():
            if isinstance(archive_data, dict):
                if not archive_data.get("publisher_id"):
                    issues.append(ValidationIssue(
                        field=f"data_sources.meetings.archives.{name}.publisher_id",
                        severity="error",
                        message=f"Granicus archive '{name}' missing publisher_id",
                        suggestion=f"Add publisher_id for '{name}'. Find it in the Granicus embed URL parameters.",
                    ))
                if not archive_data.get("view_id"):
                    issues.append(ValidationIssue(
                        field=f"data_sources.meetings.archives.{name}.view_id",
                        severity="error",
                        message=f"Granicus archive '{name}' missing view_id",
                        suggestion=f"Add view_id for '{name}'. Find it in the Granicus embed URL parameters.",
                    ))
            elif not isinstance(archive_data, str):
                issues.append(ValidationIssue(
                    field=f"data_sources.meetings.archives.{name}",
                    severity="error",
                    message=f"Granicus archive '{name}' has invalid format",
                    suggestion="Granicus archives need publisher_id and view_id: {publisher_id: 5, view_id: 5}",
                ))

    # Legistar: base_url should be a Legistar domain
    elif platform == "legistar":
        base_url = config.data_sources.meetings.base_url
        if base_url and "legistar.com" not in base_url and "webapi.legistar.com" not in base_url:
            issues.append(ValidationIssue(
                field="data_sources.meetings.base_url",
                severity="info",
                message="Legistar base_url doesn't contain 'legistar.com'",
                suggestion="Legistar APIs use webapi.legistar.com. The base_url should be the client identifier or full API URL.",
            ))

    # CivicClerk: base_url should reference civicclerk.com
    elif platform == "civicclerk":
        base_url = config.data_sources.meetings.base_url
        if base_url and "civicclerk.com" not in base_url:
            issues.append(ValidationIssue(
                field="data_sources.meetings.base_url",
                severity="info",
                message="CivicClerk base_url doesn't contain 'civicclerk.com'",
                suggestion="CivicClerk APIs use {subdomain}.api.civicclerk.com. Provide the subdomain or full API URL.",
            ))


def _validate_formats(config: JurisdictionConfig, issues: List[ValidationIssue]) -> None:
    """Validate field formats (URLs, emails, zip codes)."""
    # URL format checks
    url_fields = [
        ("contact_info.website", config.contact_info.website),
        ("data_sources.meetings.base_url", config.data_sources.meetings.base_url),
    ]
    for field_name, url in url_fields:
        if url and not url.startswith(("http://", "https://")):
            issues.append(ValidationIssue(
                field=field_name,
                severity="error",
                message=f"URL must start with http:// or https://: '{url}'",
                suggestion=f"Change to 'https://{url}'",
            ))

    # Email format check
    if config.contact_info.clerk_email:
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', config.contact_info.clerk_email):
            issues.append(ValidationIssue(
                field="contact_info.clerk_email",
                severity="error",
                message=f"Invalid email format: '{config.contact_info.clerk_email}'",
                suggestion="Use a valid email address (e.g., 'clerk@city.gov')",
            ))

    # State abbreviation format
    if config.financial.state:
        if config.financial.state != config.financial.state.upper() or len(config.financial.state) != 2:
            issues.append(ValidationIssue(
                field="financial.state",
                severity="error",
                message=f"State should be 2-letter uppercase abbreviation, got '{config.financial.state}'",
                suggestion=f"Use '{config.financial.state.upper()[:2]}'",
            ))

    # Zip code format
    for zc in config.zip_codes:
        if not re.match(r'^\d{5}(-\d{4})?$', zc):
            issues.append(ValidationIssue(
                field="zip_codes",
                severity="warning",
                message=f"Invalid zip code format: '{zc}'",
                suggestion="Zip codes should be 5 digits (e.g., '94901') or 5+4 format ('94901-1234')",
            ))

    # HUD relationship value
    if config.federal_programs.hud_relationship:
        if config.federal_programs.hud_relationship not in VALID_HUD_RELATIONSHIPS:
            issues.append(ValidationIssue(
                field="federal_programs.hud_relationship",
                severity="warning",
                message=f"Unknown HUD relationship '{config.federal_programs.hud_relationship}'",
                suggestion=f"Known types: {sorted(VALID_HUD_RELATIONSHIPS)}",
            ))


def _validate_deployment(config: JurisdictionConfig, issues: List[ValidationIssue]) -> None:
    """Validate deployment readiness."""
    if not config.modal.secrets:
        issues.append(ValidationIssue(
            field="modal.secrets",
            severity="error",
            message="No Modal secrets configured",
            suggestion="Add modal.secrets: ['civicos-env'] at minimum",
        ))
    elif "civicos-env" not in config.modal.secrets:
        issues.append(ValidationIssue(
            field="modal.secrets",
            severity="warning",
            message="'civicos-env' secret not in modal.secrets list",
            suggestion="The 'civicos-env' secret contains API keys required for most operations",
        ))


def format_validation_result(result: ValidationResult, config: Optional[JurisdictionConfig] = None, no_color: bool = False) -> str:
    """Format validation result for CLI output."""
    lines = []

    if config:
        lines.append(f"Validating: {config.jurisdiction_id} ({config.level})")
        lines.append("")

    if result.is_valid and not result.warnings and not result.infos:
        lines.append("  PASS  All checks passed")
        return "\n".join(lines)

    if result.is_valid:
        lines.append(f"  PASS  Config is valid ({result.summary})")
    else:
        lines.append(f"  FAIL  Config has errors ({result.summary})")

    lines.append("")

    # Group by severity
    for severity, label in [("error", "ERRORS"), ("warning", "WARNINGS"), ("info", "INFO")]:
        severity_issues = [i for i in result.issues if i.severity == severity]
        if not severity_issues:
            continue

        lines.append(f"  {label}:")
        for issue in severity_issues:
            lines.append(f"    [{issue.field}]")
            lines.append(f"      {issue.message}")
            if issue.suggestion:
                lines.append(f"      -> {issue.suggestion}")
            lines.append("")

    return "\n".join(lines)


def validate_all_configs() -> Dict[str, ValidationResult]:
    """Validate all jurisdiction configs in the config directory."""
    results = {}
    for jid, config in get_active_jurisdictions().items():
        results[jid] = validate_jurisdiction_config(config)
    return results
