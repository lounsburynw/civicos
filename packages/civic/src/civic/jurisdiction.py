"""
Jurisdiction Registry - Centralized jurisdiction configuration management.

This module provides a single source of truth for all jurisdiction-related
configuration including timezone mappings, agent types, meeting URLs, and
contact information. Consolidates previously scattered CITY_CONFIGS and
JURISDICTION_TIMEZONES from multiple files.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class GranicusConfig:
    """Granicus-specific configuration for jurisdictions using that platform."""
    subdomain: str
    view_id: int


@dataclass(frozen=True)
class JurisdictionConfig:
    """
    Complete configuration for a jurisdiction.

    All jurisdiction metadata is stored here - timezone, agent type,
    meeting URLs, contact info, etc. This is the authoritative source.
    """
    jurisdiction_id: str
    agent_type: str
    meeting_urls: List[str]
    timezone: str
    contact_email: str = ""
    website: str = ""
    meeting_calendar_url: str = ""
    cost_efficiency_target: Optional[float] = None
    granicus_config: Optional[GranicusConfig] = None

    # Timezone display abbreviation (derived from timezone)
    @property
    def timezone_display(self) -> str:
        """Return short timezone display name (PT, ET, CT, MT)."""
        TIMEZONE_ABBREVS = {
            "America/Los_Angeles": "PT",
            "America/New_York": "ET",
            "America/Chicago": "CT",
            "America/Denver": "MT",
            "America/Phoenix": "MT",  # Arizona doesn't observe DST but same offset
        }
        return TIMEZONE_ABBREVS.get(self.timezone, "UTC")


# ============================================================================
# JURISDICTION REGISTRY DATA
# ============================================================================
# This is the single source of truth for all jurisdiction configuration.
# Previously scattered across CITY_CONFIGS in automated_civic_refresh.py
# and JURISDICTION_TIMEZONES in civic_schema_adapter.py.
# ============================================================================

_REGISTRY: Dict[str, JurisdictionConfig] = {
    # ---------- San Rafael (pilot city) ----------
    "san_rafael": JurisdictionConfig(
        jurisdiction_id="city-san-rafael",
        agent_type="san_rafael_cms",  # BeautifulSoup-based table extraction (100% accuracy)
        meeting_urls=["https://www.cityofsanrafael.org/city-council-meetings/"],
        contact_email="planning@cityofsanrafael.org",
        timezone="America/Los_Angeles",
        website="https://www.cityofsanrafael.org",
        meeting_calendar_url="https://www.cityofsanrafael.org/departments/public-meetings/",
    ),

    # ---------- Berkeley ----------
    "berkeley": JurisdictionConfig(
        jurisdiction_id="city-berkeley",
        agent_type="berkeley_cms",  # Multi-pass extraction with uncertainty metrics
        meeting_urls=["https://berkeleyca.gov/community-recreation/events?field_event_category_tid=104"],
        contact_email="council@cityofberkeley.info",
        timezone="America/Los_Angeles",
        website="https://berkeleyca.gov",
        meeting_calendar_url="https://berkeleyca.gov/community-recreation/events",
    ),

    # ---------- Legistar Platform Cities ----------
    "santa_rosa": JurisdictionConfig(
        jurisdiction_id="city-santa-rosa",
        agent_type="legistar",
        meeting_urls=["https://santa-rosa.legistar.com/Calendar.aspx"],
        contact_email="citycouncil@srcity.org",
        timezone="America/Los_Angeles",
    ),
    "hayward": JurisdictionConfig(
        jurisdiction_id="city-hayward",
        agent_type="legistar",
        meeting_urls=["https://hayward.legistar.com/Calendar.aspx"],
        contact_email="clerk@hayward-ca.gov",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.05,
    ),
    "oakland": JurisdictionConfig(
        jurisdiction_id="city-oakland",
        agent_type="legistar",
        meeting_urls=["https://oakland.legistar.com/Calendar.aspx"],
        contact_email="cityclerk@oaklandca.gov",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.05,
    ),
    "sonoma_county": JurisdictionConfig(
        jurisdiction_id="sonoma-county",
        agent_type="legistar",
        meeting_urls=["https://sonoma-county.legistar.com/Calendar.aspx"],
        contact_email="clerk@sonoma-county.org",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.05,
    ),
    "napa": JurisdictionConfig(
        jurisdiction_id="city-napa",
        agent_type="legistar",
        meeting_urls=["https://napa.legistar.com/Calendar.aspx"],
        contact_email="cityclerk@cityofnapa.org",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.05,
    ),
    "bart": JurisdictionConfig(
        jurisdiction_id="bart",
        agent_type="legistar",
        meeting_urls=["https://bart.legistar.com/Calendar.aspx"],
        contact_email="boardmeetings@bart.gov",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.05,
    ),

    # ---------- CivicClerk Platform Cities ----------
    "richmond": JurisdictionConfig(
        jurisdiction_id="city-richmond",
        agent_type="civicclerk",
        meeting_urls=["https://richmondca.portal.civicclerk.com"],
        contact_email="cityclerk@ci.richmond.ca.us",
        timezone="America/Los_Angeles",
        website="https://www.ci.richmond.ca.us",
        meeting_calendar_url="https://richmondca.portal.civicclerk.com",
        cost_efficiency_target=0.05,
    ),
    "el_cerrito": JurisdictionConfig(
        jurisdiction_id="city-el-cerrito",
        agent_type="civicclerk",
        meeting_urls=["https://elcerritoca.portal.civicclerk.com"],
        contact_email="cityclerk@elcerrito.gov",
        timezone="America/Los_Angeles",
        website="https://www.elcerrito.gov",
        meeting_calendar_url="https://elcerritoca.portal.civicclerk.com",
        cost_efficiency_target=0.05,
    ),
    "los_altos": JurisdictionConfig(
        jurisdiction_id="city-los-altos",
        agent_type="civicclerk",
        meeting_urls=["https://losaltosca.portal.civicclerk.com"],
        contact_email="cityclerk@losaltosca.gov",
        timezone="America/Los_Angeles",
        website="https://www.losaltosca.gov",
        meeting_calendar_url="https://losaltosca.portal.civicclerk.com",
        cost_efficiency_target=0.05,
    ),
    "daly_city": JurisdictionConfig(
        jurisdiction_id="city-daly-city",
        agent_type="civicclerk",
        meeting_urls=["https://dalycityca.portal.civicclerk.com"],
        contact_email="cityclerk@dalycity.org",
        timezone="America/Los_Angeles",
        website="https://www.dalycity.org",
        meeting_calendar_url="https://dalycityca.portal.civicclerk.com",
        cost_efficiency_target=0.05,
    ),
    "los_altos_hills": JurisdictionConfig(
        jurisdiction_id="city-los-altos-hills",
        agent_type="civicclerk",
        meeting_urls=["https://losaltoshillsca.portal.civicclerk.com"],
        contact_email="cityclerk@losaltoshills.ca.gov",
        timezone="America/Los_Angeles",
        website="https://www.losaltoshills.ca.gov",
        meeting_calendar_url="https://losaltoshillsca.portal.civicclerk.com",
        cost_efficiency_target=0.05,
    ),
    "milpitas": JurisdictionConfig(
        jurisdiction_id="city-milpitas",
        agent_type="civicclerk",
        meeting_urls=["https://milpitasca.portal.civicclerk.com"],
        contact_email="cityclerk@ci.milpitas.ca.gov",
        timezone="America/Los_Angeles",
        website="https://www.ci.milpitas.ca.gov",
        meeting_calendar_url="https://milpitasca.portal.civicclerk.com",
        cost_efficiency_target=0.05,
    ),
    "pinole": JurisdictionConfig(
        jurisdiction_id="city-pinole",
        agent_type="civicclerk",
        meeting_urls=["https://pinoleca.portal.civicclerk.com"],
        contact_email="cityclerk@ci.pinole.ca.us",
        timezone="America/Los_Angeles",
        website="https://www.ci.pinole.ca.us",
        meeting_calendar_url="https://pinoleca.portal.civicclerk.com",
        cost_efficiency_target=0.05,
    ),
    "pleasanton": JurisdictionConfig(
        jurisdiction_id="city-pleasanton",
        agent_type="civicclerk",
        meeting_urls=["https://pleasantonca.portal.civicclerk.com"],
        contact_email="cityclerk@cityofpleasantonca.gov",
        timezone="America/Los_Angeles",
        website="https://www.cityofpleasantonca.gov",
        meeting_calendar_url="https://pleasantonca.portal.civicclerk.com",
        cost_efficiency_target=0.05,
    ),
    "scotts_valley": JurisdictionConfig(
        jurisdiction_id="city-scotts-valley",
        agent_type="civicclerk",
        meeting_urls=["https://scottsvalleyca.portal.civicclerk.com"],
        contact_email="cityclerk@scottsvalley.org",
        timezone="America/Los_Angeles",
        website="https://www.scottsvalley.org",
        meeting_calendar_url="https://scottsvalleyca.portal.civicclerk.com",
        cost_efficiency_target=0.05,
    ),
    "pittsburg": JurisdictionConfig(
        jurisdiction_id="city-pittsburg",
        agent_type="civicclerk",
        meeting_urls=["https://pittsburgca.portal.civicclerk.com"],
        contact_email="cityclerk@ci.pittsburg.ca.us",
        timezone="America/Los_Angeles",
        website="https://www.ci.pittsburg.ca.us",
        meeting_calendar_url="https://pittsburgca.portal.civicclerk.com",
        cost_efficiency_target=0.05,
    ),
    "antioch": JurisdictionConfig(
        jurisdiction_id="city-antioch",
        agent_type="civicclerk",
        meeting_urls=["https://antiochca.portal.civicclerk.com"],
        contact_email="cityclerk@ci.antioch.ca.us",
        timezone="America/Los_Angeles",
        website="https://www.antiochca.gov",
        meeting_calendar_url="https://antiochca.portal.civicclerk.com",
        cost_efficiency_target=0.05,
    ),

    # ---------- Granicus Platform Cities ----------
    "dublin": JurisdictionConfig(
        jurisdiction_id="city-dublin",
        agent_type="granicus",
        meeting_urls=["https://dublin.granicus.com/ViewPublisher.php?view_id=1"],
        contact_email="citycouncil@dublin.ca.gov",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.05,
        granicus_config=GranicusConfig(subdomain="dublin", view_id=1),
    ),
    "campbell": JurisdictionConfig(
        jurisdiction_id="city-campbell",
        agent_type="granicus",
        meeting_urls=["https://cityofcampbell.granicus.com/ViewPublisher.php?view_id=2"],
        contact_email="clerk@ci.campbell.ca.us",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.05,
        granicus_config=GranicusConfig(subdomain="cityofcampbell", view_id=2),
    ),

    # ---------- CivicPlus Platform Cities ----------
    "union_city": JurisdictionConfig(
        jurisdiction_id="city-union-city",
        agent_type="civicplus_cms",
        meeting_urls=["https://www.unioncity.org/AgendaCenter"],
        contact_email="cityclerk@unioncity.org",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.08,
    ),
    "concord": JurisdictionConfig(
        jurisdiction_id="city-concord",
        agent_type="civicplus_cms",
        meeting_urls=["https://www.cityofconcord.org/AgendaCenter"],
        contact_email="clerk@cityofconcord.org",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.048,
    ),
    "san_leandro": JurisdictionConfig(
        jurisdiction_id="city-san-leandro",
        agent_type="civicplus_cms",
        meeting_urls=["https://www.sanleandro.org/AgendaCenter"],
        contact_email="clerk@sanleandro.org",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.048,
    ),
    "pleasant_hill": JurisdictionConfig(
        jurisdiction_id="city-pleasant-hill",
        agent_type="civicplus_cms",
        meeting_urls=["https://www.ci.pleasant-hill.ca.us/AgendaCenter"],
        contact_email="clerk@ci.pleasant-hill.ca.us",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.048,
    ),
}

# Build reverse lookup from jurisdiction_id to city key
_JURISDICTION_ID_TO_KEY: Dict[str, str] = {
    config.jurisdiction_id: key for key, config in _REGISTRY.items()
}


class JurisdictionRegistry:
    """
    Centralized registry for jurisdiction configuration.

    Provides lookup methods by city key (e.g., "san_rafael") or
    jurisdiction ID (e.g., "city-san-rafael"). All jurisdiction
    metadata should be accessed through this class.

    Usage:
        config = JurisdictionRegistry.get("san_rafael")
        config = JurisdictionRegistry.get_by_id("city-san-rafael")
        timezone = JurisdictionRegistry.get_timezone("city-san-rafael")
    """

    @classmethod
    def get(cls, city_key: str) -> Optional[JurisdictionConfig]:
        """
        Get jurisdiction config by city key.

        Args:
            city_key: The city key (e.g., "san_rafael", "berkeley")

        Returns:
            JurisdictionConfig or None if not found
        """
        return _REGISTRY.get(city_key)

    @classmethod
    def get_by_id(cls, jurisdiction_id: str) -> Optional[JurisdictionConfig]:
        """
        Get jurisdiction config by jurisdiction ID.

        Args:
            jurisdiction_id: The jurisdiction ID (e.g., "city-san-rafael")

        Returns:
            JurisdictionConfig or None if not found
        """
        city_key = _JURISDICTION_ID_TO_KEY.get(jurisdiction_id)
        if city_key:
            return _REGISTRY.get(city_key)
        return None

    @classmethod
    def get_timezone(cls, jurisdiction_id: str, default: str = "UTC") -> str:
        """
        Get timezone for a jurisdiction ID.

        Args:
            jurisdiction_id: The jurisdiction ID (e.g., "city-san-rafael")
            default: Default timezone if not found

        Returns:
            Timezone string (e.g., "America/Los_Angeles")
        """
        config = cls.get_by_id(jurisdiction_id)
        if config:
            return config.timezone
        return default

    @classmethod
    def get_timezone_display(cls, jurisdiction_id: str) -> Tuple[str, str]:
        """
        Get timezone and display abbreviation for a jurisdiction.

        Args:
            jurisdiction_id: The jurisdiction ID

        Returns:
            Tuple of (timezone_name, display_abbrev) e.g., ("America/Los_Angeles", "PT")
        """
        config = cls.get_by_id(jurisdiction_id)
        if config:
            return (config.timezone, config.timezone_display)
        return ("UTC", "UTC")

    @classmethod
    def all_configs(cls) -> Dict[str, JurisdictionConfig]:
        """
        Get all jurisdiction configurations.

        Returns:
            Dictionary of city_key -> JurisdictionConfig
        """
        return dict(_REGISTRY)

    @classmethod
    def all_jurisdiction_ids(cls) -> List[str]:
        """
        Get all registered jurisdiction IDs.

        Returns:
            List of jurisdiction IDs
        """
        return [config.jurisdiction_id for config in _REGISTRY.values()]

    @classmethod
    def has_jurisdiction(cls, jurisdiction_id: str) -> bool:
        """
        Check if a jurisdiction ID is registered.

        Args:
            jurisdiction_id: The jurisdiction ID to check

        Returns:
            True if registered, False otherwise
        """
        return jurisdiction_id in _JURISDICTION_ID_TO_KEY


# ============================================================================
# COMPATIBILITY: Export CITY_CONFIGS dict for backward compatibility
# ============================================================================
# This allows existing code to import CITY_CONFIGS from this module.
# New code should use JurisdictionRegistry class methods instead.
# ============================================================================

def _config_to_dict(config: JurisdictionConfig) -> Dict:
    """Convert JurisdictionConfig to legacy dict format."""
    result = {
        "jurisdiction_id": config.jurisdiction_id,
        "agent_type": config.agent_type,
        "meeting_urls": list(config.meeting_urls),
        "timezone": config.timezone,
    }
    if config.contact_email:
        result["contact_email"] = config.contact_email
    if config.website:
        result["website"] = config.website
    if config.meeting_calendar_url:
        result["meeting_calendar_url"] = config.meeting_calendar_url
    if config.cost_efficiency_target is not None:
        result["cost_efficiency_target"] = config.cost_efficiency_target
    if config.granicus_config:
        result["granicus_config"] = {
            "subdomain": config.granicus_config.subdomain,
            "view_id": config.granicus_config.view_id,
        }
    return result


# Legacy CITY_CONFIGS dict for backward compatibility
CITY_CONFIGS: Dict[str, Dict] = {
    key: _config_to_dict(config) for key, config in _REGISTRY.items()
}
