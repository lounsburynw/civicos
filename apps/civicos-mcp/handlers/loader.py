"""
Tool loader for jurisdiction-specific MCP servers.

Loads tools based on jurisdiction level (federal, state, city) and
applies jurisdiction configuration for contact info, etc.

Usage:
    from handlers import load_jurisdiction_config, get_tools_for_level

    config = load_jurisdiction_config("city-san-rafael")
    tools = get_tools_for_level(config.level)  # Returns tool names for city level
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ─────────── Tool Level Categorization ───────────
#
# Tools are categorized by the jurisdiction level they operate at.
# A city-level server includes city + state + federal + coordination tools.
# A state-level server includes state + federal tools.
# A federal-level server includes only federal tools.

FEDERAL_TOOLS = frozenset([
    # These tools query shared federal datasets
    "get_federal_expenditures",       # FAC Single Audit data
    "get_funding_flow",               # Federal funding traces (also shows state/city)
    "search_executive_orders",        # Search EOs by topic
    "get_recent_executive_orders",    # Recent EOs
])

STATE_TOOLS = frozenset([
    # These tools query state-level datasets
    "get_intergovernmental_revenue",  # CA State Controller data
])

# Legislation tools span state + federal levels
LEGISLATION_TOOLS = frozenset([
    "search_legislation",             # Search bills by topic/state/status
    "get_bill_detail",                # Full bill detail with leverage point
    "get_leverage_points",            # Bills with citizen action opportunities
])

# Tools available at all levels
CROSS_LEVEL_TOOLS = frozenset([
    "search_regulatory_stack",        # Federal + state + local legislation
    "city_pulse",                     # Level-aware: meetings (city) or legislation (state/federal)
])

CITY_TOOLS = frozenset([
    # Meetings and decisions
    "search_meeting_history",
    "get_upcoming_meetings",
    "get_decision_context",
    "decision_detail",
    "get_voting_record",

    # Community issues (311)
    "find_similar_issues",
    "get_issue_analytics",
    "get_issue_trends",
    "geo_search_issues",
    "query_issue_data",
    "get_issue_resolution_stats",
    "detect_trends",
    "get_issue_sample",
    "find_issues_near_address",
    "find_repeat_issues",
    "get_seasonal_patterns",
    "compare_zip_codes",
    "neighborhood_report",

    # Budget
    "search_budget",

    # Transcripts and documents
    "get_public_testimony",
    "search_agenda_packets",

    # Engagement (use jurisdiction config for contact info)
    "compose_public_comment",
    "get_comment_guidelines",
    "get_comment_template",
    "prepare_for_meeting",

    # Overview
    "get_started",

    # Context assembly
    "get_item_context",
])

COORDINATION_TOOLS = frozenset([
    # Relay-based coordination (jurisdiction-scoped but relay-agnostic)
    "get_voice_counts",
    "subscribe_to_topic",
    "prepare_voice",
    "broadcast_voice",
    "prepare_initiative",
    "broadcast_initiative",
    "list_initiatives",
    "list_relays",
])

# Complete tool level mapping
TOOL_LEVELS = {
    "federal": FEDERAL_TOOLS | LEGISLATION_TOOLS | CROSS_LEVEL_TOOLS,
    "state": FEDERAL_TOOLS | STATE_TOOLS | LEGISLATION_TOOLS | CROSS_LEVEL_TOOLS,
    "county": FEDERAL_TOOLS | STATE_TOOLS | LEGISLATION_TOOLS | CROSS_LEVEL_TOOLS,
    "city": FEDERAL_TOOLS | STATE_TOOLS | CITY_TOOLS | LEGISLATION_TOOLS | CROSS_LEVEL_TOOLS | COORDINATION_TOOLS,
}


def get_tools_for_level(level: str) -> frozenset[str]:
    """
    Get the set of tool names enabled for a jurisdiction level.

    Args:
        level: Jurisdiction level ("federal", "state", "county", "city")

    Returns:
        Set of tool names enabled for this level
    """
    return TOOL_LEVELS.get(level, TOOL_LEVELS["city"])


# ─────────── Jurisdiction Configuration ───────────


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
class JurisdictionConfig:
    """Configuration for a jurisdiction."""
    jurisdiction_id: str
    level: str
    display_name: str
    parent_jurisdictions: list[str] = field(default_factory=list)
    contact_info: ContactInfo = field(default_factory=ContactInfo)
    governing_body: GoverningBody = field(default_factory=GoverningBody)
    zip_codes: list[str] = field(default_factory=list)
    neighborhoods: list[str] = field(default_factory=list)
    tools_enabled: Optional[list[str]] = None  # None = use default for level

    def get_enabled_tools(self) -> frozenset[str]:
        """Get the set of enabled tools for this jurisdiction."""
        if self.tools_enabled:
            return frozenset(self.tools_enabled)
        return get_tools_for_level(self.level)


def _find_config_file(jurisdiction_id: str) -> Optional[Path]:
    """Find the config file for a jurisdiction."""
    # Look in jurisdictions/ directory relative to this file
    handlers_dir = Path(__file__).parent
    jurisdictions_dir = handlers_dir.parent / "jurisdictions"

    # Try exact match first
    config_file = jurisdictions_dir / f"{jurisdiction_id}.yaml"
    if config_file.exists():
        return config_file

    # Try without prefix (e.g., "city-san-rafael" -> "san-rafael.yaml")
    for prefix in ["city-", "county-", "state-", "country-"]:
        if jurisdiction_id.startswith(prefix):
            short_name = jurisdiction_id[len(prefix):]
            config_file = jurisdictions_dir / f"{short_name}.yaml"
            if config_file.exists():
                return config_file

    return None


def load_jurisdiction_config(jurisdiction_id: str) -> JurisdictionConfig:
    """
    Load configuration for a jurisdiction.

    Args:
        jurisdiction_id: Jurisdiction identifier (e.g., "city-san-rafael")

    Returns:
        JurisdictionConfig with loaded values or defaults

    Note:
        Returns a default city-level config if no config file found.
        This allows the server to run without config files.
    """
    config_file = _find_config_file(jurisdiction_id)

    if config_file is None:
        # Return default config
        return JurisdictionConfig(
            jurisdiction_id=jurisdiction_id,
            level=_infer_level(jurisdiction_id),
            display_name=_format_display_name(jurisdiction_id),
        )

    with open(config_file, "r") as f:
        data = yaml.safe_load(f)

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

    return JurisdictionConfig(
        jurisdiction_id=data.get("jurisdiction_id", jurisdiction_id),
        level=data.get("level", _infer_level(jurisdiction_id)),
        display_name=data.get("display_name", _format_display_name(jurisdiction_id)),
        parent_jurisdictions=data.get("parent_jurisdictions", []),
        contact_info=contact_info,
        governing_body=governing_body,
        zip_codes=data.get("zip_codes", []),
        neighborhoods=data.get("neighborhoods", []),
        tools_enabled=data.get("tools_enabled"),
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
        return "city"  # Default to city


def _format_display_name(jurisdiction_id: str) -> str:
    """Format jurisdiction ID as display name."""
    # Remove prefix and title-case
    for prefix in ["city-", "county-", "state-", "country-"]:
        if jurisdiction_id.startswith(prefix):
            return jurisdiction_id[len(prefix):].replace("-", " ").title()
    return jurisdiction_id.replace("-", " ").title()


# ─────────── Handler Binding Helpers ───────────


def get_config_for_handler(jurisdiction_id: str) -> JurisdictionConfig:
    """
    Get jurisdiction config for use in handlers.

    This is the main entry point for handlers that need jurisdiction-specific
    information like contact emails or meeting schedules.

    Args:
        jurisdiction_id: Current jurisdiction (from env or request)

    Returns:
        JurisdictionConfig with all settings
    """
    # Cache config in module-level variable to avoid repeated file reads
    # (In production, use a proper cache with TTL)
    return load_jurisdiction_config(jurisdiction_id)
