"""
Jurisdiction Registry - Centralized jurisdiction configuration management.

This module provides a single source of truth for all jurisdiction-related
configuration including timezone mappings, agent types, meeting URLs, and
contact information.

Registry entries are loaded from three sources (merged in this order):
1. Extraction configs (data/extraction/*.json) — minimal: jurisdiction_id, source_type
2. Jurisdiction YAMLs (data/jurisdictions/*.yaml) — rich: display_name, contact, etc.
3. Hardcoded entries below — richest: wiki_files, cost_efficiency_target, granicus_config

Fields not in config files are derived automatically:
- timezone: from state code (CA → America/Los_Angeles)
- display_name: from jurisdiction_id (city-san-rafael → "San Rafael")
- hall_name: from display_name + level suffix
- domains: from website URL
"""

import json as _json_mod
import logging
import re as _re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_logger = logging.getLogger(__name__)


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
    # Extended fields for jurisdiction config consolidation
    display_name: str = ""  # Human-readable name (e.g., "San Rafael")
    hall_name: str = ""  # Meeting location (e.g., "San Rafael City Hall")
    domains: Tuple[str, ...] = ()  # Associated domains for URL detection
    wiki_files: Tuple[str, ...] = ()  # Wiki documentation paths

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
# AUTO-LOADING HELPERS
# ============================================================================

_STATE_TO_TIMEZONE: Dict[str, str] = {
    "CA": "America/Los_Angeles",
    "WA": "America/Los_Angeles",
    "OR": "America/Los_Angeles",
    "NV": "America/Los_Angeles",
    "HI": "Pacific/Honolulu",
    "AK": "America/Anchorage",
    "TX": "America/Chicago",
    "IL": "America/Chicago",
    "NY": "America/New_York",
    "FL": "America/New_York",
    "PA": "America/New_York",
    "AZ": "America/Phoenix",
    "CO": "America/Denver",
    "MT": "America/Denver",
}


def _derive_display_name(jurisdiction_id: str) -> str:
    """Derive human-readable display name from jurisdiction_id."""
    name = jurisdiction_id
    is_county = name.startswith("county-")
    for prefix in ("city-", "county-", "school-", "college-", "state-", "country-"):
        if name.startswith(prefix):
            name = name[len(prefix):]
            break
    display = name.replace("-", " ").title()
    if is_county:
        display = f"{display} County"
    return display


def _derive_city_key(jurisdiction_id: str) -> str:
    """Derive the registry-style key from jurisdiction_id.

    city-san-rafael → san_rafael
    county-marin → marin_county
    school-kentfield → school_kentfield
    bart → bart
    """
    if jurisdiction_id.startswith("city-"):
        return jurisdiction_id[5:].replace("-", "_")
    if jurisdiction_id.startswith("county-"):
        return jurisdiction_id[7:].replace("-", "_") + "_county"
    for prefix in ("school-", "college-", "state-", "country-"):
        if jurisdiction_id.startswith(prefix):
            tag = prefix.rstrip("-")
            slug = jurisdiction_id[len(prefix):].replace("-", "_")
            return f"{tag}_{slug}"
    return jurisdiction_id.replace("-", "_")


def _resolve_state(yaml_data: Optional[dict], json_data: Optional[dict]) -> str:
    """Resolve state abbreviation from available config data."""
    if yaml_data:
        state = (yaml_data.get("financial") or {}).get("state", "")
        if state:
            return state
    if json_data:
        state = json_data.get("state", "")
        if state:
            return state
        state = (json_data.get("metadata") or {}).get("state", "")
        if state:
            return state
        if json_data.get("election_sources", {}).get("ca_sos_results"):
            return "CA"
    return ""


def _merge_configs(base: "JurisdictionConfig", overlay: "JurisdictionConfig") -> "JurisdictionConfig":
    """Merge two configs. Overlay wins for non-default fields."""
    return JurisdictionConfig(
        jurisdiction_id=overlay.jurisdiction_id,
        agent_type=overlay.agent_type if overlay.agent_type != "standard" else base.agent_type,
        meeting_urls=overlay.meeting_urls if overlay.meeting_urls else base.meeting_urls,
        timezone=overlay.timezone if overlay.timezone != "UTC" else base.timezone,
        contact_email=overlay.contact_email or base.contact_email,
        website=overlay.website or base.website,
        meeting_calendar_url=overlay.meeting_calendar_url or base.meeting_calendar_url,
        cost_efficiency_target=(
            overlay.cost_efficiency_target
            if overlay.cost_efficiency_target is not None
            else base.cost_efficiency_target
        ),
        granicus_config=overlay.granicus_config or base.granicus_config,
        display_name=overlay.display_name or base.display_name,
        hall_name=overlay.hall_name or base.hall_name,
        domains=overlay.domains if overlay.domains else base.domains,
        wiki_files=overlay.wiki_files if overlay.wiki_files else base.wiki_files,
    )


def _load_from_files() -> Dict[str, "JurisdictionConfig"]:
    """Scan YAML and extraction JSON files to build registry entries."""
    from civicos_config.paths import JURISDICTIONS_DIR, EXTRACTION_DIR

    yaml_by_jid: Dict[str, dict] = {}
    json_by_jid: Dict[str, dict] = {}

    # Load jurisdiction YAMLs
    if JURISDICTIONS_DIR.exists():
        try:
            import yaml
        except ImportError:
            yaml = None  # type: ignore
        if yaml:
            for path in sorted(JURISDICTIONS_DIR.glob("*.yaml")):
                if path.name == "schema.yaml":
                    continue
                try:
                    data = yaml.safe_load(path.read_text())
                    if data and data.get("jurisdiction_id"):
                        yaml_by_jid[data["jurisdiction_id"]] = data
                except Exception:
                    pass

    # Load extraction JSONs
    if EXTRACTION_DIR.exists():
        for path in sorted(EXTRACTION_DIR.glob("*.json")):
            if path.name.startswith("."):
                continue
            try:
                data = _json_mod.loads(path.read_text())
                jid = data.get("jurisdiction_id")
                if jid and jid not in json_by_jid:
                    json_by_jid[jid] = data
            except Exception:
                pass

    # Build JurisdictionConfig for each unique jurisdiction_id
    all_jids = set(yaml_by_jid.keys()) | set(json_by_jid.keys())
    result: Dict[str, JurisdictionConfig] = {}

    for jid in all_jids:
        yd = yaml_by_jid.get(jid)
        jd = json_by_jid.get(jid)

        state = _resolve_state(yd, jd)
        timezone = _STATE_TO_TIMEZONE.get(state.upper(), "UTC") if state else "UTC"
        display_name = ""
        hall_name = ""
        agent_type = "standard"
        meeting_urls: List[str] = []
        contact_email = ""
        website = ""
        meeting_calendar_url = ""
        domains: Tuple[str, ...] = ()

        if yd:
            display_name = yd.get("display_name", "")
            contact = yd.get("contact_info") or {}
            contact_email = contact.get("clerk_email", "") or ""
            website = contact.get("website", "") or ""
            governing = yd.get("governing_body") or {}
            hall_name = governing.get("meeting_location", "") or ""
            meetings = (yd.get("data_sources") or {}).get("meetings") or {}
            if meetings.get("source_type"):
                agent_type = meetings["source_type"]
            if meetings.get("base_url"):
                meeting_urls = [meetings["base_url"]]
                meeting_calendar_url = meetings["base_url"]

        if jd:
            if agent_type == "standard" and jd.get("source_type"):
                agent_type = jd["source_type"]
            if not meeting_urls and jd.get("base_url"):
                meeting_urls = [jd["base_url"]]
            if not meeting_calendar_url and jd.get("base_url"):
                meeting_calendar_url = jd["base_url"]

        if not display_name:
            display_name = _derive_display_name(jid)
        if not hall_name and display_name:
            if jid.startswith("county-"):
                hall_name = f"{display_name} Administration Building"
            elif jid.startswith(("school-", "college-")):
                hall_name = f"{display_name} Board Room"
            else:
                hall_name = f"{display_name} City Hall"

        if website and not domains:
            domain = _re.sub(r"https?://(?:www\.)?", "", website).rstrip("/")
            if domain:
                domains = (domain,)

        city_key = _derive_city_key(jid)
        result[city_key] = JurisdictionConfig(
            jurisdiction_id=jid,
            agent_type=agent_type,
            meeting_urls=meeting_urls,
            timezone=timezone,
            contact_email=contact_email,
            website=website,
            meeting_calendar_url=meeting_calendar_url,
            display_name=display_name,
            hall_name=hall_name,
            domains=domains,
        )

    return result


# ============================================================================
# LAZY-LOADING REGISTRY CACHE
# ============================================================================

_cached_registry: Optional[Dict[str, "JurisdictionConfig"]] = None
_cached_id_to_key: Optional[Dict[str, str]] = None


def _get_registry() -> Dict[str, "JurisdictionConfig"]:
    """Get the merged registry, loading from files on first access."""
    global _cached_registry, _cached_id_to_key
    if _cached_registry is not None:
        return _cached_registry

    try:
        file_entries = _load_from_files()
    except Exception:
        file_entries = {}

    merged = dict(file_entries)
    for key, hardcoded_config in _HARDCODED_REGISTRY.items():
        if key in merged:
            merged[key] = _merge_configs(merged[key], hardcoded_config)
        else:
            merged[key] = hardcoded_config

    _cached_registry = merged
    _cached_id_to_key = {
        config.jurisdiction_id: key for key, config in merged.items()
    }
    return _cached_registry


def _get_id_to_key() -> Dict[str, str]:
    """Get the jurisdiction_id → city_key reverse lookup."""
    global _cached_id_to_key
    if _cached_id_to_key is None:
        _get_registry()
    return _cached_id_to_key  # type: ignore


# ============================================================================
# HARDCODED REGISTRY DATA (enrichment layer — file-based entries are the base)
# ============================================================================

_HARDCODED_REGISTRY: Dict[str, JurisdictionConfig] = {
    # ---------- San Rafael (pilot city) ----------
    "san_rafael": JurisdictionConfig(
        jurisdiction_id="city-san-rafael",
        agent_type="san_rafael_cms",  # BeautifulSoup-based table extraction (100% accuracy)
        meeting_urls=["https://www.cityofsanrafael.org/city-council-meetings/"],
        contact_email="planning@cityofsanrafael.org",
        timezone="America/Los_Angeles",
        website="https://www.cityofsanrafael.org",
        meeting_calendar_url="https://www.cityofsanrafael.org/departments/public-meetings/",
        display_name="San Rafael",
        hall_name="San Rafael City Hall",
        domains=("cityofsanrafael.org", "sanrafael.org"),
        wiki_files=(
            "wiki/jurisdictions/california/cities/san-rafael.md",
            "wiki/engagement-strategies/municipal/public-comment-best-practices.md",
        ),
    ),

    # ---------- San Rafael City Schools (pilot school district) ----------
    "school_san_rafael": JurisdictionConfig(
        jurisdiction_id="school-san-rafael",
        agent_type="srcs_cms",  # BoardDocs-based extraction
        meeting_urls=["https://go.boarddocs.com/ca/srcs/Board.nsf/Public"],
        contact_email="board@srcs.org",
        timezone="America/Los_Angeles",
        website="https://www.srcs.org",
        meeting_calendar_url="https://go.boarddocs.com/ca/srcs/Board.nsf/Public",
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
        display_name="Berkeley",
        hall_name="Berkeley City Hall",
        domains=("berkeleyca.gov", "cityofberkeley.info"),
        wiki_files=(
            "wiki/jurisdictions/california/cities/berkeley.md",
            "wiki/engagement-strategies/municipal/public-comment-best-practices.md",
        ),
    ),

    # ---------- Mill Valley (federation test) ----------
    "mill_valley": JurisdictionConfig(
        jurisdiction_id="city-mill-valley",
        agent_type="granicus",
        meeting_urls=["https://cityofmillvalley.granicus.com/ViewPublisher.php?view_id=2"],
        contact_email="cityclerk@cityofmillvalley.org",
        timezone="America/Los_Angeles",
        website="https://www.cityofmillvalley.org",
        meeting_calendar_url="https://cityofmillvalley.granicus.com/ViewPublisher.php?view_id=2",
        display_name="Mill Valley",
        hall_name="Mill Valley City Hall",
        domains=("cityofmillvalley.org",),
        granicus_config=GranicusConfig(subdomain="cityofmillvalley", view_id=2),
    ),

    # ---------- San Anselmo (federation test) ----------
    "san_anselmo": JurisdictionConfig(
        jurisdiction_id="city-san-anselmo",
        agent_type="granicus",
        meeting_urls=["https://sananselmo-ca.granicus.com/ViewPublisher.php?view_id=8"],
        contact_email="townclerk@townofsananselmo.org",
        timezone="America/Los_Angeles",
        website="https://www.townofsananselmo.org",
        meeting_calendar_url="https://sananselmo-ca.granicus.com/ViewPublisher.php?view_id=8",
        display_name="San Anselmo",
        hall_name="San Anselmo Town Hall",
        domains=("townofsananselmo.org",),
        granicus_config=GranicusConfig(subdomain="sananselmo-ca", view_id=8),
    ),

    # ---------- Marin County ----------
    "marin_county": JurisdictionConfig(
        jurisdiction_id="county-marin",
        agent_type="standard",
        meeting_urls=["https://www.marincounty.org/depts/bs/board-of-supervisors/meetings-agendas-and-minutes"],
        contact_email="boardclerk@marincounty.org",
        timezone="America/Los_Angeles",
        website="https://www.marincounty.org",
        display_name="Marin County",
        hall_name="Marin County Civic Center",
        domains=("marincounty.org", "marincounty.gov"),
        wiki_files=(
            "wiki/jurisdictions/california/counties/marin-county.md",
            "wiki/engagement-strategies/municipal/public-comment-best-practices.md",
        ),
    ),

    # ---------- Legistar Platform Cities ----------
    "santa_rosa": JurisdictionConfig(
        jurisdiction_id="city-santa-rosa",
        agent_type="legistar",
        meeting_urls=["https://santa-rosa.legistar.com/Calendar.aspx"],
        contact_email="citycouncil@srcity.org",
        timezone="America/Los_Angeles",
        display_name="Santa Rosa",
        hall_name="Santa Rosa City Hall",
        domains=("srcity.org", "santa-rosa.legistar.com"),
    ),
    "hayward": JurisdictionConfig(
        jurisdiction_id="city-hayward",
        agent_type="legistar",
        meeting_urls=["https://hayward.legistar.com/Calendar.aspx"],
        contact_email="clerk@hayward-ca.gov",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.05,
        display_name="Hayward",
        hall_name="Hayward City Hall",
        domains=("hayward-ca.gov", "hayward.legistar.com"),
    ),
    "oakland": JurisdictionConfig(
        jurisdiction_id="city-oakland",
        agent_type="legistar",
        meeting_urls=["https://oakland.legistar.com/Calendar.aspx"],
        contact_email="cityclerk@oaklandca.gov",
        timezone="America/Los_Angeles",
        cost_efficiency_target=0.05,
        display_name="Oakland",
        hall_name="Oakland City Hall",
        domains=("oaklandca.gov", "oakland.legistar.com"),
    ),
    "sonoma_county": JurisdictionConfig(
        jurisdiction_id="county-sonoma",
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
        display_name="El Cerrito",
        hall_name="El Cerrito City Hall",
        domains=("elcerrito.gov", "elcerritoca.portal.civicclerk.com"),
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
        return _get_registry().get(city_key)

    @classmethod
    def get_by_id(cls, jurisdiction_id: str) -> Optional[JurisdictionConfig]:
        """
        Get jurisdiction config by jurisdiction ID.

        Args:
            jurisdiction_id: The jurisdiction ID (e.g., "city-san-rafael")

        Returns:
            JurisdictionConfig or None if not found
        """
        city_key = _get_id_to_key().get(jurisdiction_id)
        if city_key:
            return _get_registry().get(city_key)
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
        return dict(_get_registry())

    @classmethod
    def all_jurisdiction_ids(cls) -> List[str]:
        """
        Get all registered jurisdiction IDs.

        Returns:
            List of jurisdiction IDs
        """
        return [config.jurisdiction_id for config in _get_registry().values()]

    @classmethod
    def has_jurisdiction(cls, jurisdiction_id: str) -> bool:
        """
        Check if a jurisdiction ID is registered.

        Args:
            jurisdiction_id: The jurisdiction ID to check

        Returns:
            True if registered, False otherwise
        """
        return jurisdiction_id in _get_id_to_key()

    @classmethod
    def get_by_domain(cls, domain: str) -> Optional[JurisdictionConfig]:
        """
        Get jurisdiction config by domain name.

        Args:
            domain: Domain to look up (e.g., "cityofsanrafael.org")

        Returns:
            JurisdictionConfig or None if not found
        """
        domain_lower = domain.lower()
        for config in _get_registry().values():
            if any(d.lower() in domain_lower or domain_lower in d.lower()
                   for d in config.domains):
                return config
        return None

    @classmethod
    def get_hall_name(cls, jurisdiction_id: str, default: str = "City Hall") -> str:
        """
        Get meeting hall name for a jurisdiction.

        Args:
            jurisdiction_id: The jurisdiction ID (e.g., "city-san-rafael")
            default: Default hall name if not configured

        Returns:
            Hall name string (e.g., "San Rafael City Hall")
        """
        config = cls.get_by_id(jurisdiction_id)
        if config and config.hall_name:
            return config.hall_name
        return default

    @classmethod
    def get_display_name(cls, jurisdiction_id: str, default: str = "") -> str:
        """
        Get human-readable display name for a jurisdiction.

        Args:
            jurisdiction_id: The jurisdiction ID (e.g., "city-san-rafael")
            default: Default display name if not configured

        Returns:
            Display name string (e.g., "San Rafael")
        """
        config = cls.get_by_id(jurisdiction_id)
        if config and config.display_name:
            return config.display_name
        return default

    @classmethod
    def get_wiki_files(cls, jurisdiction_id: str) -> Tuple[str, ...]:
        """
        Get wiki documentation file paths for a jurisdiction.

        Args:
            jurisdiction_id: The jurisdiction ID (e.g., "city-san-rafael")

        Returns:
            Tuple of wiki file paths (may be empty)
        """
        config = cls.get_by_id(jurisdiction_id)
        if config:
            return config.wiki_files
        return ()

    @classmethod
    def get_jurisdiction_id_by_domain(cls, domain: str) -> Optional[str]:
        """
        Get jurisdiction ID by domain name.

        Args:
            domain: Domain to look up (e.g., "cityofsanrafael.org")

        Returns:
            Jurisdiction ID or None if not found
        """
        config = cls.get_by_domain(domain)
        if config:
            return config.jurisdiction_id
        return None

    @classmethod
    def get_location_display_name(cls, location_mention: str) -> Optional[str]:
        """
        Resolve a location mention to a jurisdiction ID.

        Args:
            location_mention: City/location name (e.g., "san rafael", "Berkeley")

        Returns:
            Jurisdiction ID or None if not found
        """
        location_lower = location_mention.lower().strip()
        for config in _get_registry().values():
            if config.display_name and config.display_name.lower() == location_lower:
                return config.jurisdiction_id
            # Also check partial matches for multi-word names
            if config.display_name and location_lower in config.display_name.lower():
                return config.jurisdiction_id
        return None

    @classmethod
    def reload(cls) -> None:
        """Force re-scan of config files. Primarily for testing."""
        global _cached_registry, _cached_id_to_key
        _cached_registry = None
        _cached_id_to_key = None
        # Also clear CITY_CONFIGS cache
        if hasattr(CITY_CONFIGS, "_cache"):
            CITY_CONFIGS._cache = None


# ============================================================================
# COMPATIBILITY: Export CITY_CONFIGS dict for backward compatibility
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


class _LazyCityConfigs(dict):
    """Lazy dict that builds from registry on first access."""

    def _ensure_loaded(self):
        if not super().__len__():
            data = {
                key: _config_to_dict(config)
                for key, config in _get_registry().items()
            }
            super().update(data)

    def __getitem__(self, key):
        self._ensure_loaded()
        return super().__getitem__(key)

    def __contains__(self, key):
        self._ensure_loaded()
        return super().__contains__(key)

    def __iter__(self):
        self._ensure_loaded()
        return super().__iter__()

    def __len__(self):
        self._ensure_loaded()
        return super().__len__()

    def items(self):
        self._ensure_loaded()
        return super().items()

    def keys(self):
        self._ensure_loaded()
        return super().keys()

    def values(self):
        self._ensure_loaded()
        return super().values()

    def get(self, key, default=None):
        self._ensure_loaded()
        return super().get(key, default)

    # For reload support
    _cache = None


# Legacy CITY_CONFIGS dict for backward compatibility
CITY_CONFIGS = _LazyCityConfigs()
