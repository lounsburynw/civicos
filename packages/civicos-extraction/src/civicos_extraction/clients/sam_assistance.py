"""
SAM.gov Assistance Listings Data Client

Retrieves federal program definitions from SAM.gov's published Assistance Listings
(formerly CFDA - Catalog of Federal Domestic Assistance).

Data Source:
- Bulk CSV published by GSA on data.gov
- URL: https://s3.amazonaws.com/falextracts/Assistance%20Listings/datagov/AssistanceListings_DataGov_PUBLIC_CURRENT.csv
- License: Public Domain (CC0)

Usage:
    client = SAMAssistanceClient()
    cdbg = client.get_program("14.218")  # CDBG
    housing_programs = client.search_programs("housing", agency="HUD")

The client caches the downloaded CSV locally to avoid repeated downloads.
Cache is refreshed when older than 24 hours by default.
"""

import csv
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from civicos_extraction.clients.base import HealthStatus, ValidationResult

logger = logging.getLogger(__name__)


# SAM.gov Assistance Listings bulk download URL (published by GSA)
SAM_ASSISTANCE_LISTINGS_URL = (
    "https://s3.amazonaws.com/falextracts/Assistance%20Listings/datagov/"
    "AssistanceListings_DataGov_PUBLIC_CURRENT.csv"
)

# Column name mappings (CSV header -> our field names)
COLUMN_MAPPINGS = {
    "Program Title": "program_name",
    "Program Number": "aln",  # Assistance Listing Number (formerly CFDA)
    "Popular Name (020)": "popular_name",
    "Federal Agency (030)": "agency",
    "Objectives (050)": "objectives",
    "Types of Assistance (060)": "assistance_types",
    "Uses and Use Restrictions (070)": "uses_restrictions",
    "Applicant Eligibility (081)": "applicant_eligibility",
    "Beneficiary Eligibility (082)": "beneficiary_eligibility",
    "Website Address (153)": "website",
    "URL": "sam_url",
    "Published Date": "published_date",
    "Obligations (122)": "obligations",
}

# Agency code to abbreviation mappings
AGENCY_ABBREVIATIONS = {
    "DEPARTMENT OF HOUSING AND URBAN DEVELOPMENT": "HUD",
    "HOUSING AND URBAN DEVELOPMENT, DEPARTMENT OF": "HUD",
    "DEPARTMENT OF TRANSPORTATION": "DOT",
    "TRANSPORTATION, DEPARTMENT OF": "DOT",
    "FEDERAL TRANSIT ADMINISTRATION": "FTA",
    "FEDERAL HIGHWAY ADMINISTRATION": "FHWA",
    "ENVIRONMENTAL PROTECTION AGENCY": "EPA",
    "DEPARTMENT OF EDUCATION": "ED",
    "EDUCATION, DEPARTMENT OF": "ED",
    "FEDERAL EMERGENCY MANAGEMENT AGENCY": "FEMA",
    "DEPARTMENT OF HEALTH AND HUMAN SERVICES": "HHS",
    "HEALTH AND HUMAN SERVICES, DEPARTMENT OF": "HHS",
    "DEPARTMENT OF AGRICULTURE": "USDA",
    "AGRICULTURE, DEPARTMENT OF": "USDA",
    "DEPARTMENT OF ENERGY": "DOE",
    "ENERGY, DEPARTMENT OF": "DOE",
    "DEPARTMENT OF COMMERCE": "DOC",
    "COMMERCE, DEPARTMENT OF": "DOC",
    "DEPARTMENT OF LABOR": "DOL",
    "LABOR, DEPARTMENT OF": "DOL",
    "DEPARTMENT OF JUSTICE": "DOJ",
    "JUSTICE, DEPARTMENT OF": "DOJ",
    "DEPARTMENT OF DEFENSE": "DOD",
    "DEFENSE, DEPARTMENT OF": "DOD",
    "DEPARTMENT OF HOMELAND SECURITY": "DHS",
    "HOMELAND SECURITY, DEPARTMENT OF": "DHS",
    "DEPARTMENT OF THE TREASURY": "TREASURY",
    "TREASURY, DEPARTMENT OF THE": "TREASURY",
    "DEPARTMENT OF VETERANS AFFAIRS": "VA",
    "VETERANS AFFAIRS, DEPARTMENT OF": "VA",
    "DEPARTMENT OF THE INTERIOR": "DOI",
    "INTERIOR, DEPARTMENT OF THE": "DOI",
}

# Topic inference based on ALN prefix (agency code)
ALN_PREFIX_TO_TOPIC = {
    "10": "agriculture",  # USDA
    "11": "commerce",  # DOC
    "12": "defense",  # DOD
    "14": "housing",  # HUD
    "15": "environment",  # DOI (Interior)
    "16": "justice",  # DOJ
    "17": "labor",  # DOL
    "19": "foreign_affairs",  # State
    "20": "transportation",  # DOT
    "21": "treasury",  # Treasury
    "43": "science",  # NASA
    "45": "arts_culture",  # NEA/NEH
    "47": "science",  # NSF
    "59": "business",  # SBA
    "64": "veterans",  # VA
    "66": "environment",  # EPA
    "81": "energy",  # DOE
    "84": "education",  # ED
    "90": "community",  # AmeriCorps/CNCS
    "93": "health",  # HHS
    "94": "community",  # CNCS/AmeriCorps
    "97": "emergency",  # DHS/FEMA
}


@dataclass
class AssistanceListing:
    """
    A federal assistance program listing from SAM.gov.

    Represents a single program with its ALN (Assistance Listing Number,
    formerly CFDA number), description, eligibility, and other details.
    """

    aln: str  # "14.218" for CDBG
    program_name: str
    agency: str  # Full agency name from CSV
    agency_abbrev: str  # "HUD", "DOT", etc.
    objectives: str  # Program description
    assistance_types: str
    uses_restrictions: str
    applicant_eligibility: str
    beneficiary_eligibility: str
    website: str
    sam_url: str
    published_date: Optional[str] = None
    popular_name: Optional[str] = None
    obligations: Optional[str] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "aln": self.aln,
            "program_name": self.program_name,
            "agency": self.agency,
            "agency_abbrev": self.agency_abbrev,
            "objectives": self.objectives,
            "assistance_types": self.assistance_types,
            "uses_restrictions": self.uses_restrictions,
            "applicant_eligibility": self.applicant_eligibility,
            "beneficiary_eligibility": self.beneficiary_eligibility,
            "website": self.website,
            "sam_url": self.sam_url,
            "published_date": self.published_date,
            "popular_name": self.popular_name,
            "obligations": self.obligations,
        }


class SAMAssistanceClient:
    """
    SAM.gov Assistance Listings data client.

    Downloads and parses the bulk Assistance Listings CSV from SAM.gov/data.gov
    to provide federal program definitions. This is the authoritative source
    for program metadata (formerly CFDA catalog).

    Features:
    - Downloads bulk CSV from GSA S3 bucket (public domain)
    - Caches locally to avoid repeated downloads
    - Provides search by ALN, keyword, or agency
    - Maps agency names to abbreviations
    - Infers topic categories from ALN prefixes
    """

    def __init__(
        self,
        jurisdiction_id: str = "federal-US",
        cache_dir: Optional[str] = None,
        cache_max_age_hours: float = 24.0,
        request_delay: float = 0.5,
    ):
        """
        Initialize SAM Assistance client.

        Args:
            jurisdiction_id: Civic jurisdiction ID (default "federal-US")
            cache_dir: Directory to cache downloaded CSV (default: temp dir)
            cache_max_age_hours: Max age of cached file before refresh (default 24h)
            request_delay: Delay between requests in seconds (default 0.5)
        """
        self.jurisdiction_id = jurisdiction_id
        self.cache_dir = cache_dir or tempfile.gettempdir()
        self.cache_max_age_hours = cache_max_age_hours
        self.request_delay = request_delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })
        self.last_request_time = 0.0
        self._program_cache: Dict[str, AssistanceListing] = {}
        self._programs_loaded = False

    @property
    def platform_name(self) -> str:
        return "sam_assistance"

    @property
    def source_id(self) -> str:
        """Unique identifier: platform-jurisdiction."""
        return f"sam_assistance-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        """Type of source."""
        return "sam_assistance"

    def _throttle_request(self) -> None:
        """Ensure minimum delay between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = time.time()

    def _get_cache_path(self) -> str:
        """Get path to cached CSV file."""
        return os.path.join(self.cache_dir, "sam_assistance_listings.csv")

    def _is_cache_valid(self) -> bool:
        """Check if cache file exists and is recent enough."""
        cache_path = self._get_cache_path()
        if not os.path.exists(cache_path):
            return False

        file_age_hours = (time.time() - os.path.getmtime(cache_path)) / 3600
        return file_age_hours < self.cache_max_age_hours

    def _download_csv(self) -> Optional[str]:
        """
        Download Assistance Listings CSV from SAM.gov/data.gov.

        Returns:
            Path to downloaded file, or None if download failed
        """
        cache_path = self._get_cache_path()

        # Use cached file if valid
        if self._is_cache_valid():
            logger.debug(f"Using cached SAM assistance listings: {cache_path}")
            return cache_path

        self._throttle_request()

        try:
            logger.info("Downloading SAM.gov Assistance Listings CSV...")
            response = self.session.get(SAM_ASSISTANCE_LISTINGS_URL, timeout=120)
            response.raise_for_status()

            with open(cache_path, "wb") as f:
                f.write(response.content)

            logger.info(f"Downloaded SAM assistance listings: {cache_path}")
            return cache_path

        except requests.RequestException as e:
            logger.error(f"Failed to download SAM assistance listings: {e}")
            # Return cached file if it exists (even if stale)
            if os.path.exists(cache_path):
                logger.warning("Using stale cache due to download failure")
                return cache_path
            return None

    def _parse_csv(self, file_path: str) -> List[AssistanceListing]:
        """
        Parse the Assistance Listings CSV file.

        Args:
            file_path: Path to downloaded CSV file

        Returns:
            List of AssistanceListing objects
        """
        listings: List[AssistanceListing] = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)

                for row in reader:
                    try:
                        listing = self._row_to_listing(row)
                        if listing:
                            listings.append(listing)
                    except Exception as e:
                        logger.warning(f"Error parsing row: {e}")
                        continue

            logger.info(f"Parsed {len(listings)} assistance listings")

        except Exception as e:
            logger.error(f"Error parsing SAM CSV file: {e}")
            raise

        return listings

    def _row_to_listing(self, row: Dict[str, str]) -> Optional[AssistanceListing]:
        """Convert a CSV row to an AssistanceListing object."""
        aln = row.get("Program Number", "").strip()
        if not aln:
            return None

        program_name = row.get("Program Title", "").strip()
        if not program_name:
            return None

        agency = row.get("Federal Agency (030)", "").strip()
        agency_abbrev = self._get_agency_abbrev(agency)

        return AssistanceListing(
            aln=aln,
            program_name=program_name,
            agency=agency,
            agency_abbrev=agency_abbrev,
            objectives=row.get("Objectives (050)", "").strip(),
            assistance_types=row.get("Types of Assistance (060)", "").strip(),
            uses_restrictions=row.get("Uses and Use Restrictions (070)", "").strip(),
            applicant_eligibility=row.get("Applicant Eligibility (081)", "").strip(),
            beneficiary_eligibility=row.get("Beneficiary Eligibility (082)", "").strip(),
            website=row.get("Website Address (153)", "").strip(),
            sam_url=row.get("URL", "").strip(),
            published_date=row.get("Published Date", "").strip() or None,
            popular_name=row.get("Popular Name (020)", "").strip() or None,
            obligations=row.get("Obligations (122)", "").strip() or None,
            raw_data=dict(row),
        )

    def _get_agency_abbrev(self, agency: str) -> str:
        """Get agency abbreviation from full name."""
        agency_upper = agency.upper()

        # First try to extract from sub-agency if format is "SUB_AGENCY, PARENT_DEPT"
        parts = agency.split(",")
        if len(parts) >= 2:
            sub_agency = parts[0].strip().upper()
            for pattern, abbrev in AGENCY_ABBREVIATIONS.items():
                if pattern in sub_agency:
                    return abbrev

        # Check direct mappings on full string
        for pattern, abbrev in AGENCY_ABBREVIATIONS.items():
            if pattern in agency_upper:
                return abbrev

        # Default to first word if no match
        return agency.split()[0].upper() if agency else "UNKNOWN"

    def _load_programs(self) -> None:
        """Load all programs into cache if not already loaded."""
        if self._programs_loaded:
            return

        file_path = self._download_csv()
        if not file_path:
            logger.error("Failed to download SAM assistance listings")
            return

        listings = self._parse_csv(file_path)

        # Build cache indexed by ALN
        self._program_cache = {
            listing.aln: listing for listing in listings
        }
        self._programs_loaded = True

        logger.info(f"Loaded {len(self._program_cache)} programs into cache")

    def health(self) -> HealthStatus:
        """
        Check source availability and return standardized status.

        Performs a lightweight check by attempting to access the CSV URL.
        """
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        try:
            self._throttle_request()
            response = self.session.head(SAM_ASSISTANCE_LISTINGS_URL, timeout=30)

            if response.status_code == 200:
                is_available = True
                metadata["content_length"] = response.headers.get("Content-Length")
                metadata["last_modified"] = response.headers.get("Last-Modified")

                # Count from cache if available
                if self._programs_loaded:
                    available_count = len(self._program_cache)
            else:
                errors.append(f"SAM.gov returned status {response.status_code}")

        except Exception as e:
            errors.append(f"Health check error: {str(e)}")
            logger.warning(
                "Health check failed",
                extra={
                    "error": str(e),
                    "platform": self.platform_name,
                },
            )

        check_duration_ms = (time.time() - start_time) * 1000
        now = datetime.now()

        return HealthStatus(
            source_id=self.source_id,
            source_type=self.source_type,
            jurisdiction_id=self.jurisdiction_id,
            is_available=is_available,
            available_count=available_count,
            last_checked=now,
            check_duration_ms=round(check_duration_ms, 2),
            errors=errors,
            last_successful=now if is_available else None,
            metadata=metadata,
        )

    def validate(self) -> ValidationResult:
        """Validate source configuration and accessibility."""
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False
        metadata: Dict[str, Any] = {}

        # No special config needed for this client (uses public bulk download)
        # Just check network access
        try:
            self._throttle_request()
            response = self.session.head(SAM_ASSISTANCE_LISTINGS_URL, timeout=30)

            if response.status_code == 200:
                api_reachable = True
                content_length = response.headers.get("Content-Length")
                if content_length:
                    size_mb = int(content_length) / (1024 * 1024)
                    metadata["csv_size_mb"] = round(size_mb, 2)
            else:
                errors.append(f"Cannot reach SAM.gov: HTTP {response.status_code}")

        except requests.RequestException as e:
            errors.append(f"Network error: {str(e)}")

        # Check for existing cache
        cache_path = self._get_cache_path()
        if os.path.exists(cache_path):
            metadata["cache_exists"] = True
            metadata["cache_valid"] = self._is_cache_valid()
        else:
            metadata["cache_exists"] = False

        check_duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=config_valid,
            api_reachable=api_reachable,
            errors=errors,
            warnings=warnings,
            check_duration_ms=round(check_duration_ms, 2),
            metadata=metadata,
        )

    def get_program(self, aln: str) -> Optional[AssistanceListing]:
        """
        Get a program by Assistance Listing Number (ALN).

        Args:
            aln: Assistance Listing Number (e.g., "14.218" for CDBG)

        Returns:
            AssistanceListing if found, None otherwise
        """
        self._load_programs()
        return self._program_cache.get(aln)

    def search_programs(
        self,
        keyword: Optional[str] = None,
        agency: Optional[str] = None,
        aln_prefix: Optional[str] = None,
        limit: int = 100,
    ) -> List[AssistanceListing]:
        """
        Search programs by keyword, agency, or ALN prefix.

        Args:
            keyword: Search term for program name/description
            agency: Agency abbreviation (e.g., "HUD", "DOT", "EPA")
            aln_prefix: ALN prefix (e.g., "14" for HUD programs)
            limit: Maximum number of results (default 100)

        Returns:
            List of matching AssistanceListing objects
        """
        self._load_programs()

        results: List[AssistanceListing] = []
        keyword_lower = keyword.lower() if keyword else None
        agency_upper = agency.upper() if agency else None

        for listing in self._program_cache.values():
            # Filter by ALN prefix
            if aln_prefix and not listing.aln.startswith(aln_prefix):
                continue

            # Filter by agency
            if agency_upper and agency_upper not in listing.agency_abbrev:
                continue

            # Filter by keyword (search name, objectives, uses)
            if keyword_lower:
                searchable = " ".join([
                    listing.program_name,
                    listing.objectives,
                    listing.uses_restrictions,
                    listing.popular_name or "",
                ]).lower()

                if keyword_lower not in searchable:
                    continue

            results.append(listing)

            if len(results) >= limit:
                break

        return results

    def get_programs_by_agency(self, agency: str) -> List[AssistanceListing]:
        """
        Get all programs for an agency.

        Args:
            agency: Agency abbreviation (e.g., "HUD", "DOT")

        Returns:
            List of AssistanceListing objects for that agency
        """
        return self.search_programs(agency=agency, limit=1000)

    def get_program_eligibility(self, aln: str) -> Optional[Dict[str, str]]:
        """
        Get eligibility information for a program.

        Args:
            aln: Assistance Listing Number

        Returns:
            Dict with applicant_eligibility and beneficiary_eligibility
        """
        listing = self.get_program(aln)
        if not listing:
            return None

        return {
            "applicant_eligibility": listing.applicant_eligibility,
            "beneficiary_eligibility": listing.beneficiary_eligibility,
            "assistance_types": listing.assistance_types,
        }

    def get_program_count(self) -> int:
        """Get total number of programs available."""
        self._load_programs()
        return len(self._program_cache)

    def get_available_agencies(self) -> Dict[str, int]:
        """Get list of agencies with program counts."""
        self._load_programs()

        agency_counts: Dict[str, int] = {}
        for listing in self._program_cache.values():
            abbrev = listing.agency_abbrev
            agency_counts[abbrev] = agency_counts.get(abbrev, 0) + 1

        # Sort by count descending
        return dict(sorted(
            agency_counts.items(),
            key=lambda x: x[1],
            reverse=True
        ))


def create_sam_assistance_client(
    cache_dir: Optional[str] = None,
) -> SAMAssistanceClient:
    """
    Create a SAM Assistance client configured for federal program lookup.

    Args:
        cache_dir: Optional directory for caching CSV (default: temp dir)

    Returns:
        Configured SAMAssistanceClient
    """
    return SAMAssistanceClient(cache_dir=cache_dir)


# ==================== Storage Mappers ====================


def infer_topic(listing: AssistanceListing) -> str:
    """
    Infer topic category from an Assistance Listing.

    Uses ALN prefix to determine the primary topic area.
    """
    if not listing.aln or "." not in listing.aln:
        return "general"

    prefix = listing.aln.split(".")[0]
    return ALN_PREFIX_TO_TOPIC.get(prefix, "general")


def extract_keywords(listing: AssistanceListing) -> List[str]:
    """
    Extract searchable keywords from an Assistance Listing.

    Combines program name, popular name, and key terms from objectives.
    """
    keywords: List[str] = []

    # Add program name words
    if listing.program_name:
        keywords.extend(listing.program_name.lower().split())

    # Add popular name if present
    if listing.popular_name:
        keywords.extend(listing.popular_name.lower().split())

    # Add agency abbreviation
    if listing.agency_abbrev:
        keywords.append(listing.agency_abbrev.lower())

    # Remove common words and deduplicate
    stopwords = {"the", "of", "and", "for", "to", "a", "an", "in", "on", "with", "by"}
    keywords = [k for k in keywords if k not in stopwords and len(k) > 2]

    return list(set(keywords))[:20]  # Limit to 20 keywords


def sam_program_to_storage(
    listing: AssistanceListing,
) -> Dict[str, Any]:
    """
    Map SAM.gov Assistance Listing to federal_programs storage format.

    Args:
        listing: AssistanceListing from SAMAssistanceClient

    Returns:
        Dict ready for store_federal_programs()
    """
    topic = infer_topic(listing)
    keywords = extract_keywords(listing)

    # Parse objectives into description (take first 2000 chars)
    description = listing.objectives[:2000] if listing.objectives else ""

    # Parse uses_restrictions into eligible_activities list
    eligible_activities: List[str] = []
    if listing.uses_restrictions and listing.uses_restrictions != "Not Applicable":
        # Split on common delimiters
        uses = listing.uses_restrictions.replace(";", "\n").replace(".", ".\n")
        for line in uses.split("\n"):
            line = line.strip()
            if line and len(line) > 10:
                eligible_activities.append(line[:500])  # Limit each activity
        eligible_activities = eligible_activities[:10]  # Limit to 10 activities

    return {
        "program_id": f"sam_{listing.aln.replace('.', '_')}",
        "program_name": listing.program_name,
        "administering_agency": listing.agency_abbrev,
        "description": description,
        "eligible_activities": eligible_activities,
        "cfda_number": listing.aln,  # ALN is the modern name for CFDA
        "keywords": keywords,
        "topic": topic,
        "official_url": listing.website or listing.sam_url,
        "source_url": SAM_ASSISTANCE_LISTINGS_URL,
        "source": "sam_assistance_listings",
        "metadata": {
            "full_agency": listing.agency,
            "popular_name": listing.popular_name,
            "applicant_eligibility": listing.applicant_eligibility[:1000]
            if listing.applicant_eligibility else None,
            "beneficiary_eligibility": listing.beneficiary_eligibility[:1000]
            if listing.beneficiary_eligibility else None,
            "assistance_types": listing.assistance_types,
            "published_date": listing.published_date,
        },
    }


def extract_programs_for_topics(
    client: SAMAssistanceClient,
    topics: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Extract programs for specified topics, ready for storage.

    Args:
        client: SAMAssistanceClient instance
        topics: List of topics to extract (default: housing, transportation,
                environment, education, health, emergency)

    Returns:
        List of program dicts ready for store_federal_programs()
    """
    if topics is None:
        # Default to topics relevant for local government
        topics = ["housing", "transportation", "environment", "education",
                  "health", "emergency", "community"]

    # Map topics to ALN prefixes
    topic_to_prefix = {v: k for k, v in ALN_PREFIX_TO_TOPIC.items()}

    results: List[Dict[str, Any]] = []

    for topic in topics:
        prefix = topic_to_prefix.get(topic)
        if prefix:
            listings = client.search_programs(aln_prefix=prefix, limit=500)
            for listing in listings:
                results.append(sam_program_to_storage(listing))

    logger.info(
        f"Extracted {len(results)} programs for topics: {topics}"
    )
    return results


def extract_programs_by_aln(
    client: SAMAssistanceClient,
    alns: List[str],
) -> List[Dict[str, Any]]:
    """
    Extract specific programs by ALN, ready for storage.

    Args:
        client: SAMAssistanceClient instance
        alns: List of ALNs to extract (e.g., ["14.218", "14.239", "20.507"])

    Returns:
        List of program dicts ready for store_federal_programs()
    """
    results: List[Dict[str, Any]] = []

    for aln in alns:
        listing = client.get_program(aln)
        if listing:
            results.append(sam_program_to_storage(listing))
        else:
            logger.warning(f"Program not found: {aln}")

    logger.info(f"Extracted {len(results)}/{len(alns)} programs by ALN")
    return results
