"""
Platform Detection Helper

Auto-detects which civic platform a city uses by probing known API endpoints
and scraping patterns. Used during city onboarding to bootstrap extraction config.

Usage:
    from civicos_extraction.platform_detection import detect_platform

    result = detect_platform("https://www.cityofsanrafael.org")
    if result.source_type:
        print(f"Detected {result.source_type} with {result.confidence:.0%} confidence")

Supported platforms:
- Legistar: API-based (Berkeley, Oakland, San Francisco)
- CivicClerk: OData API (El Cerrito, Hayward, San Pablo)
- ProudCity: WordPress-based scraping (San Rafael)
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Maximum view_id to probe when detecting/discovering Granicus instances
_DEFAULT_MAX_VIEW_ID = 8

# US/Canadian state/province codes used for generating subdomain candidates
_KNOWN_STATE_CODES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
    # Canadian provinces
    "ab", "bc", "mb", "nb", "nl", "ns", "nt", "nu", "on", "pe", "qc", "sk", "yt",
}


@dataclass
class DetectionResult:
    """
    Result of platform detection for a city website.

    Contains the detected platform type, confidence score, and metadata
    about the detection process.
    """

    source_type: Optional[str]  # 'legistar', 'civicclerk', 'proudcity', or None
    source_id: Optional[str]  # 'legistar-berkeley', 'civicclerk-elcerrito', etc.
    platform_name: Optional[str]  # Human-readable name
    confidence: float  # 0.0-1.0 confidence score

    # Detection metadata
    detection_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "platform_name": self.platform_name,
            "confidence": self.confidence,
            "detection_time_ms": self.detection_time_ms,
            "metadata": self.metadata,
            "errors": self.errors,
        }


def _extract_client_name(url: str) -> str:
    """
    Extract a likely client name from a city URL.

    Examples:
        https://www.cityofberkeley.info -> berkeley
        https://www.cityofsanrafael.org -> sanrafael
        https://elcerrito.ca.gov -> elcerrito
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()

    # Remove common prefixes
    domain = re.sub(r'^www\.', '', domain)

    # Extract city name from domain patterns
    # Pattern: cityof{name}.{tld}
    match = re.match(r'cityof([a-z]+)\.', domain)
    if match:
        return match.group(1)

    # Pattern: {name}.{state}.gov or {name}.gov
    match = re.match(r'([a-z]+)\.(?:[a-z]+\.)?gov', domain)
    if match:
        return match.group(1)

    # Pattern: {name}.org or {name}.com
    match = re.match(r'([a-z]+)\.(?:org|com|net|info)', domain)
    if match:
        return match.group(1)

    # Fallback: use first part of domain
    return domain.split('.')[0]


def _detect_legistar(client_name: str, timeout: int) -> tuple[float, Dict[str, Any]]:
    """
    Attempt Legistar detection by testing API endpoint.

    Returns:
        Tuple of (confidence, metadata)
    """
    api_url = f"https://webapi.legistar.com/v1/{client_name}/bodies"
    metadata: Dict[str, Any] = {"api_url": api_url}

    try:
        response = requests.get(api_url, timeout=timeout)
        metadata["status_code"] = response.status_code

        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    metadata["body_count"] = len(data)
                    # High confidence: valid JSON array response
                    return 0.95, metadata
            except ValueError:
                # JSON parse failed
                metadata["error"] = "Invalid JSON response"
                return 0.0, metadata
        elif response.status_code == 404:
            # Client name not found in Legistar
            return 0.0, metadata
        else:
            metadata["error"] = f"Unexpected status: {response.status_code}"
            return 0.0, metadata

    except requests.exceptions.Timeout:
        metadata["error"] = "Timeout"
        return 0.0, metadata
    except requests.exceptions.RequestException as e:
        metadata["error"] = str(e)
        return 0.0, metadata


def _detect_civicclerk(subdomain: str, timeout: int) -> tuple[float, Dict[str, Any]]:
    """
    Attempt CivicClerk detection by testing OData API endpoint.

    Tries Events endpoint first (always available), falls back to Boards.

    Returns:
        Tuple of (confidence, metadata)
    """
    headers = {
        "Accept": "application/json",
        "Origin": "https://portal.civicclerk.com",
    }
    metadata: Dict[str, Any] = {}

    for endpoint in ["Events?$top=1", "Boards?$top=1"]:
        api_url = f"https://{subdomain}.api.civicclerk.com/v1/{endpoint}"
        metadata["api_url"] = api_url

        try:
            response = requests.get(api_url, headers=headers, timeout=timeout)
            metadata["status_code"] = response.status_code

            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, dict) and "value" in data:
                        count = len(data.get("value", []))
                        metadata["board_count"] = count
                        return 0.95, metadata
                    elif isinstance(data, list):
                        metadata["board_count"] = len(data)
                        return 0.90, metadata
                except ValueError:
                    metadata["error"] = "Invalid JSON response"
                    continue
            elif response.status_code == 404:
                continue  # Try next endpoint
            else:
                metadata["error"] = f"Unexpected status: {response.status_code}"
                continue

        except requests.exceptions.Timeout:
            metadata["error"] = "Timeout"
            continue
        except requests.exceptions.RequestException as e:
            metadata["error"] = str(e)
            continue

    return 0.0, metadata


def _detect_granicus(base_url: str, client_name: str, timeout: int) -> tuple[float, Dict[str, Any]]:
    """
    Attempt Granicus detection.

    Two detection modes:
    - Direct: URL matches *.granicus.com → fetch ViewPublisher, check for tables
    - Indirect: Scrape city website for granicus.com/ViewPublisher links

    Returns:
        Tuple of (confidence, metadata)
    """
    metadata: Dict[str, Any] = {}
    parsed = urlparse(base_url)
    domain = parsed.netloc.lower()

    # Direct detection: URL is already a granicus.com domain
    if "granicus.com" in domain:
        subdomain = domain.replace(".granicus.com", "")
        metadata["granicus_domain"] = subdomain
        metadata["detection_mode"] = "direct"

        try:
            headers = {"User-Agent": "Civic-Platform-Detection/1.0"}
            # Try view_ids since some jurisdictions don't use view_id=1
            for view_id in range(1, _DEFAULT_MAX_VIEW_ID + 1):
                test_url = f"https://{subdomain}.granicus.com/ViewPublisher.php?view_id={view_id}"
                response = requests.get(test_url, headers=headers, timeout=timeout)
                metadata["status_code"] = response.status_code
                metadata["detected_view_id"] = view_id

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    tables = soup.find_all("table")
                    metadata["table_count"] = len(tables)
                    if tables:
                        return 0.95, metadata
                    else:
                        return 0.70, metadata
            # All view_ids returned non-200
            return 0.0, metadata

        except requests.exceptions.Timeout:
            metadata["error"] = "Timeout"
            return 0.0, metadata
        except requests.exceptions.RequestException as e:
            metadata["error"] = str(e)
            return 0.0, metadata

    # Indirect detection: scrape city website for granicus links
    metadata["detection_mode"] = "indirect"
    try:
        headers = {"User-Agent": "Civic-Platform-Detection/1.0"}
        response = requests.get(base_url, headers=headers, timeout=timeout)
        if response.status_code != 200:
            return 0.0, metadata

        # Look for granicus.com/ViewPublisher links
        granicus_pattern = re.compile(r"https?://([^.]+)\.granicus\.com/ViewPublisher", re.I)
        matches = granicus_pattern.findall(response.text)

        if matches:
            granicus_domain = matches[0]
            metadata["granicus_domain"] = granicus_domain
            metadata["link_count"] = len(matches)
            return 0.85, metadata

        return 0.0, metadata

    except requests.exceptions.Timeout:
        metadata["error"] = "Timeout"
        return 0.0, metadata
    except requests.exceptions.RequestException as e:
        metadata["error"] = str(e)
        return 0.0, metadata


def _detect_proudcity(base_url: str, timeout: int) -> tuple[float, Dict[str, Any]]:
    """
    Attempt ProudCity detection by scraping /meetings/ page.

    Returns:
        Tuple of (confidence, metadata)
    """
    meetings_url = f"{base_url.rstrip('/')}/meetings/"
    metadata: Dict[str, Any] = {"meetings_url": meetings_url}

    try:
        headers = {
            "User-Agent": "Civic-Platform-Detection/1.0"
        }
        response = requests.get(meetings_url, headers=headers, timeout=timeout)
        metadata["status_code"] = response.status_code

        if response.status_code != 200:
            metadata["error"] = f"Status {response.status_code}"
            return 0.0, metadata

        # Parse HTML and look for meeting archive links
        soup = BeautifulSoup(response.content, 'html.parser')

        # ProudCity pattern: links ending in -meetings/, -hearings/, etc.
        archive_pattern = re.compile(r'/([a-z0-9-]+)-(meetings|hearings|boards|committees|events|agendas|minutes)/?$')
        discovered_types: List[str] = []

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if archive_pattern.search(href):
                match = archive_pattern.search(href)
                if match:
                    type_slug = match.group(1)
                    if type_slug not in discovered_types:
                        discovered_types.append(type_slug)

        metadata["discovered_meeting_types"] = discovered_types
        metadata["meeting_type_count"] = len(discovered_types)

        # Confidence based on number of discovered archive types
        if len(discovered_types) >= 5:
            # Strong signal: many meeting type archives
            return 0.90, metadata
        elif len(discovered_types) >= 2:
            # Moderate signal: some meeting types
            return 0.75, metadata
        elif len(discovered_types) == 1:
            # Weak signal: only one type found
            return 0.50, metadata
        else:
            # No meeting type archives found
            return 0.0, metadata

    except requests.exceptions.Timeout:
        metadata["error"] = "Timeout"
        return 0.0, metadata
    except requests.exceptions.RequestException as e:
        metadata["error"] = str(e)
        return 0.0, metadata


def _detect_escribe(instance_name: str, timeout: int) -> tuple[float, Dict[str, Any]]:
    """
    Attempt eScribe detection by probing the calendar API.

    Returns:
        Tuple of (confidence, metadata)
    """
    base_url = f"https://pub-{instance_name}.escribemeetings.com"
    metadata: Dict[str, Any] = {"instance_name": instance_name, "base_url": base_url}

    try:
        # Probe the calendar page — if it returns 200, instance exists
        response = requests.get(
            f"{base_url}/MeetingsCalendarView.aspx",
            headers={"User-Agent": "Civic-Platform-Detection/1.0"},
            timeout=timeout,
        )
        metadata["status_code"] = response.status_code

        if response.status_code == 200:
            # Verify it's actually eScribe by checking for characteristic content
            if "escribemeetings" in response.text.lower() or "GetCalendarMeetings" in response.text:
                metadata["confirmed"] = True
                return 0.95, metadata
            # Page exists but doesn't look like eScribe
            metadata["confirmed"] = False
            return 0.60, metadata
        else:
            return 0.0, metadata

    except requests.exceptions.Timeout:
        metadata["error"] = "Timeout"
        return 0.0, metadata
    except requests.exceptions.RequestException as e:
        metadata["error"] = str(e)
        return 0.0, metadata


def _detect_simbli(board_url: str, timeout: int) -> tuple[float, Dict[str, Any]]:
    """
    Attempt Simbli detection by probing eboardsolutions.com.

    Simbli uses Incapsula WAF which blocks most automated requests,
    but we can still detect the platform by checking if the URL resolves
    and the response contains Simbli markers.

    Returns:
        Tuple of (confidence, metadata)
    """
    metadata: Dict[str, Any] = {"board_url": board_url}

    try:
        response = requests.get(
            board_url,
            headers={"User-Agent": "Civic-Platform-Detection/1.0"},
            timeout=timeout,
            allow_redirects=True,
        )
        metadata["status_code"] = response.status_code

        if response.status_code == 200:
            content_lower = response.text.lower()
            # Simbli pages contain characteristic markers even through WAF
            if "simbli" in content_lower or "eboardsolutions" in content_lower:
                metadata["confirmed"] = True
                return 0.95, metadata
            # WAF challenge pages still indicate Simbli is there
            if "incapsula" in content_lower or "imperva" in content_lower:
                metadata["confirmed"] = "waf_detected"
                return 0.80, metadata
            return 0.0, metadata
        elif response.status_code in [403, 503]:
            # WAF blocking — still indicates Simbli exists
            metadata["waf_blocked"] = True
            return 0.70, metadata
        else:
            return 0.0, metadata

    except requests.exceptions.Timeout:
        metadata["error"] = "Timeout"
        return 0.0, metadata
    except requests.exceptions.RequestException as e:
        metadata["error"] = str(e)
        return 0.0, metadata


def _detect_universal(base_url: str, timeout: int) -> tuple[float, Dict[str, Any]]:
    """
    Last-resort detection: check if page has meeting-like content.

    Returns lower confidence than specific platform detections (0.30-0.50)
    so that specific detectors always win.

    Returns:
        Tuple of (confidence, metadata)
    """
    metadata: Dict[str, Any] = {"base_url": base_url}

    # Meeting-related keywords (case-insensitive)
    meeting_keywords = [
        "meeting", "agenda", "minutes", "council", "board",
        "commission", "committee", "hearing", "session",
    ]
    # Date patterns that suggest a meeting schedule
    date_pattern = re.compile(
        r"(January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4}"
        r"|"
        r"\d{1,2}/\d{1,2}/\d{4}"
    )

    try:
        response = requests.get(
            base_url,
            headers={"User-Agent": "Civic-Platform-Detection/1.0"},
            timeout=timeout,
        )
        metadata["status_code"] = response.status_code

        if response.status_code != 200:
            return 0.0, metadata

        content_lower = response.text.lower()

        # Count meeting keywords
        keyword_hits = sum(1 for kw in meeting_keywords if kw in content_lower)
        metadata["keyword_hits"] = keyword_hits

        # Count date patterns
        date_matches = date_pattern.findall(response.text)
        metadata["date_count"] = len(date_matches)

        # Check for table or list structures
        soup = BeautifulSoup(response.text, "html.parser")
        tables = soup.find_all("table")
        lists = soup.find_all(["ul", "ol"])
        metadata["table_count"] = len(tables)
        metadata["list_count"] = len(lists)

        # Score based on signals
        if keyword_hits >= 3 and len(date_matches) >= 2 and (tables or lists):
            return 0.50, metadata
        elif keyword_hits >= 2 and len(date_matches) >= 1:
            return 0.40, metadata
        elif keyword_hits >= 1 and len(date_matches) >= 1:
            return 0.30, metadata
        else:
            return 0.0, metadata

    except requests.exceptions.Timeout:
        metadata["error"] = "Timeout"
        return 0.0, metadata
    except requests.exceptions.RequestException as e:
        metadata["error"] = str(e)
        return 0.0, metadata


def detect_platform(
    base_url: str,
    jurisdiction_id: Optional[str] = None,
    timeout: int = 10,
    state: Optional[str] = None,
) -> DetectionResult:
    """
    Auto-detect which civic platform a city uses.

    Probes known API endpoints (Legistar, CivicClerk) and scrapes
    meeting pages (ProudCity) to determine the platform type.

    Args:
        base_url: City website URL (e.g., "https://www.cityofsanrafael.org")
        jurisdiction_id: Optional jurisdiction identifier. If not provided,
                         extracted from URL.
        timeout: Request timeout in seconds (default 10)

    Returns:
        DetectionResult with source_type, confidence, and metadata

    Example:
        result = detect_platform("https://www.cityofsanrafael.org")
        if result.confidence >= 0.8:
            print(f"Detected: {result.source_type}")
    """
    start_time = time.time()
    errors: List[str] = []
    all_metadata: Dict[str, Any] = {"base_url": base_url}

    # Extract client name from URL
    client_name = _extract_client_name(base_url)
    all_metadata["extracted_client_name"] = client_name

    # Use provided jurisdiction_id or construct from client_name
    if not jurisdiction_id:
        jurisdiction_id = f"city-{client_name}"

    # Try each platform in order of API preference (faster than scraping)
    best_result: Optional[DetectionResult] = None
    best_confidence = 0.0

    # 1. Try Legistar (API-based, fastest)
    legistar_confidence, legistar_meta = _detect_legistar(client_name, timeout)
    all_metadata["legistar"] = legistar_meta
    if legistar_confidence > best_confidence:
        best_confidence = legistar_confidence
        best_result = DetectionResult(
            source_type="legistar",
            source_id=f"legistar-{client_name}",
            platform_name="Legistar",
            confidence=legistar_confidence,
            metadata=legistar_meta,
        )

    # 2. Try Granicus (HTML scraping)
    granicus_confidence, granicus_meta = _detect_granicus(base_url, client_name, timeout)
    all_metadata["granicus"] = granicus_meta
    if granicus_confidence > best_confidence:
        best_confidence = granicus_confidence
        granicus_domain = granicus_meta.get("granicus_domain", client_name)
        best_result = DetectionResult(
            source_type="granicus",
            source_id=f"granicus-{jurisdiction_id}",
            platform_name="Granicus",
            confidence=granicus_confidence,
            metadata=granicus_meta,
        )

    # 3. Try CivicClerk (API-based)
    # Try common subdomain patterns
    civicclerk_subdomains = [client_name]
    if state:
        state_suffix = state.lower().strip()
        civicclerk_subdomains.append(f"{client_name}{state_suffix}")  # e.g., elcerritoca, austintx
    civicclerk_subdomains.append(client_name.replace("city", ""))  # cityof... -> ...
    for subdomain in civicclerk_subdomains:
        if not subdomain:
            continue
        cc_confidence, cc_meta = _detect_civicclerk(subdomain, timeout)
        if cc_confidence > 0:
            all_metadata["civicclerk"] = {**cc_meta, "subdomain_tested": subdomain}
            if cc_confidence > best_confidence:
                best_confidence = cc_confidence
                best_result = DetectionResult(
                    source_type="civicclerk",
                    source_id=f"civicclerk-{subdomain}",
                    platform_name="CivicClerk",
                    confidence=cc_confidence,
                    metadata=cc_meta,
                )
            break  # Found a match, stop trying subdomains
    else:
        # Record that we tried CivicClerk but found nothing
        all_metadata["civicclerk"] = {"subdomain_tested": civicclerk_subdomains, "found": False}

    # 4. Try eScribe (probe escribemeetings.com)
    # Check if URL is already an eScribe URL
    escribe_match = re.match(r"https?://pub-([^.]+)\.escribemeetings\.com", base_url)
    if escribe_match:
        escribe_instance = escribe_match.group(1)
    else:
        escribe_instance = client_name
    escribe_confidence, escribe_meta = _detect_escribe(escribe_instance, timeout)
    all_metadata["escribe"] = escribe_meta
    if escribe_confidence > best_confidence:
        best_confidence = escribe_confidence
        best_result = DetectionResult(
            source_type="escribe",
            source_id=f"escribe-{escribe_instance}",
            platform_name="eScribe",
            confidence=escribe_confidence,
            metadata=escribe_meta,
        )

    # 5. Try Simbli (eboardsolutions.com — school boards)
    simbli_match = re.match(r"https?://[^/]*eboardsolutions\.com", base_url)
    if simbli_match:
        simbli_confidence, simbli_meta = _detect_simbli(base_url, timeout)
        all_metadata["simbli"] = simbli_meta
        if simbli_confidence > best_confidence:
            best_confidence = simbli_confidence
            best_result = DetectionResult(
                source_type="simbli",
                source_id=f"simbli-{jurisdiction_id}",
                platform_name="Simbli",
                confidence=simbli_confidence,
                metadata=simbli_meta,
            )

    # 6. Try ProudCity (scraping-based, slowest)
    pc_confidence, pc_meta = _detect_proudcity(base_url, timeout)
    all_metadata["proudcity"] = pc_meta
    if pc_confidence > best_confidence:
        best_confidence = pc_confidence
        best_result = DetectionResult(
            source_type="proudcity",
            source_id=f"proudcity-{jurisdiction_id}",
            platform_name="ProudCity",
            confidence=pc_confidence,
            metadata=pc_meta,
        )

    # 7. Try universal adapter (last resort — checks for meeting-like content)
    if best_confidence < 0.5:
        universal_confidence, universal_meta = _detect_universal(base_url, timeout)
        all_metadata["universal"] = universal_meta
        if universal_confidence > best_confidence:
            best_confidence = universal_confidence
            best_result = DetectionResult(
                source_type="universal",
                source_id=f"universal-{jurisdiction_id}",
                platform_name="Universal Adapter",
                confidence=universal_confidence,
                metadata=universal_meta,
            )

    detection_time_ms = (time.time() - start_time) * 1000

    # Return best result or "not detected"
    if best_result:
        best_result.detection_time_ms = round(detection_time_ms, 2)
        best_result.metadata = all_metadata
        best_result.errors = errors
        return best_result

    # No platform detected
    return DetectionResult(
        source_type=None,
        source_id=None,
        platform_name=None,
        confidence=0.0,
        detection_time_ms=round(detection_time_ms, 2),
        metadata=all_metadata,
        errors=errors if errors else ["No platform detected"],
    )


def discover_granicus_subdomain(
    city_name: str,
    state: Optional[str] = None,
    timeout: int = 8,
    max_view_id: int = _DEFAULT_MAX_VIEW_ID,
) -> Optional[Dict[str, Any]]:
    """
    Discover a Granicus subdomain by trying common URL patterns.

    Given a city name like "San Anselmo" and state "CA", tries patterns:
    - sananselmo.granicus.com
    - cityofsananselmo.granicus.com
    - townofsananselmo.granicus.com
    - sananselmo-ca.granicus.com

    For each pattern, probes ViewPublisher.php with view_id 1 through max_view_id.
    Returns on first successful hit (200 with HTML tables).

    Args:
        city_name: City name (e.g., "San Anselmo", "Mill Valley")
        state: Two-letter state code (default: "ca")
        timeout: HTTP request timeout in seconds
        max_view_id: Maximum view_id to probe (default: 8)

    Returns:
        Dict with keys: subdomain, view_id, url, table_count
        None if no Granicus instance found
    """
    # Normalize city name: lowercase, remove spaces/hyphens
    slug = re.sub(r"[\s\-]+", "", city_name.lower().strip())

    # Common Granicus subdomain patterns (ordered by frequency)
    candidates = [
        slug,                         # e.g., dublin, millvalley
        f"cityof{slug}",              # e.g., cityofmillvalley, cityofcampbell
        f"townof{slug}",              # e.g., townofsananselmo
    ]
    if state:
        state = state.lower().strip()
        candidates.insert(2, f"{slug}-{state}")   # e.g., sananselmo-ca
        candidates.append(f"{slug}{state}")        # e.g., sananselmoca

    headers = {"User-Agent": "Civic-Platform-Detection/1.0"}

    for subdomain in candidates:
        # First check if subdomain exists by probing root page
        try:
            root_url = f"https://{subdomain}.granicus.com/"
            root_resp = requests.head(root_url, headers=headers, timeout=timeout, allow_redirects=True)
            if root_resp.status_code != 200:
                continue  # Subdomain doesn't exist, try next pattern
        except requests.exceptions.RequestException:
            continue

        # Subdomain exists — probe view_ids to find one with meeting tables
        for view_id in range(1, max_view_id + 1):
            test_url = f"https://{subdomain}.granicus.com/ViewPublisher.php?view_id={view_id}"
            try:
                response = requests.get(test_url, headers=headers, timeout=timeout)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "html.parser")
                    tables = soup.find_all("table")
                    if tables:
                        logger.info(
                            f"Granicus discovered: {subdomain}.granicus.com view_id={view_id} "
                            f"({len(tables)} tables)"
                        )
                        return {
                            "subdomain": subdomain,
                            "view_id": view_id,
                            "url": test_url,
                            "table_count": len(tables),
                        }
            except requests.exceptions.RequestException:
                continue

    return None


def discover_legistar_client(
    city_name: str,
    state: Optional[str] = None,
    timeout: int = 8,
) -> Optional[Dict[str, Any]]:
    """
    Discover a Legistar client name by trying common API patterns.

    Given a city name like "Berkeley" and state "CA", tries patterns:
    - berkeley (slug)
    - berkeley-ca (slug-state)
    - cityofberkeley (cityof prefix)

    For each pattern, probes webapi.legistar.com/v1/{candidate}/bodies.
    Returns on first successful hit (200 with JSON array).

    Args:
        city_name: City name (e.g., "Berkeley", "Oakland")
        state: Two-letter state/province code (optional)
        timeout: HTTP request timeout in seconds

    Returns:
        Dict with keys: client_name, body_count, url
        None if no Legistar instance found
    """
    slug = re.sub(r"[\s\-]+", "", city_name.lower().strip())

    candidates = [
        slug,                    # e.g., berkeley
        f"cityof{slug}",        # e.g., cityofberkeley
        f"countyof{slug}",      # e.g., countyofmarin
        f"townof{slug}",        # e.g., townofsananselmo
        f"{slug}city",          # e.g., berkeleycity
    ]
    if state:
        state = state.lower().strip()
        candidates.insert(1, f"{slug}-{state}")   # e.g., berkeley-ca
        candidates.append(f"{slug}{state}")        # e.g., berkeleyca (no hyphen)
        # Full state name variant (e.g., "austintexas") — common for TX cities
        state_names = {
            "al": "alabama", "ak": "alaska", "az": "arizona", "ar": "arkansas",
            "ca": "california", "co": "colorado", "ct": "connecticut", "de": "delaware",
            "fl": "florida", "ga": "georgia", "hi": "hawaii", "id": "idaho",
            "il": "illinois", "in": "indiana", "ia": "iowa", "ks": "kansas",
            "ky": "kentucky", "la": "louisiana", "me": "maine", "md": "maryland",
            "ma": "massachusetts", "mi": "michigan", "mn": "minnesota", "ms": "mississippi",
            "mo": "missouri", "mt": "montana", "ne": "nebraska", "nv": "nevada",
            "nh": "newhampshire", "nj": "newjersey", "nm": "newmexico", "ny": "newyork",
            "nc": "northcarolina", "nd": "northdakota", "oh": "ohio", "ok": "oklahoma",
            "or": "oregon", "pa": "pennsylvania", "ri": "rhodeisland", "sc": "southcarolina",
            "sd": "southdakota", "tn": "tennessee", "tx": "texas", "ut": "utah",
            "vt": "vermont", "va": "virginia", "wa": "washington", "wv": "westvirginia",
            "wi": "wisconsin", "wy": "wyoming", "dc": "dc",
        }
        full_state = state_names.get(state)
        if full_state and full_state != state:
            candidates.append(f"{slug}{full_state}")  # e.g., austintexas

    for client_name in candidates:
        api_url = f"https://webapi.legistar.com/v1/{client_name}/bodies"
        try:
            response = requests.get(api_url, timeout=timeout)
            if response.status_code == 200:
                try:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        logger.info(
                            f"Legistar discovered: {client_name} "
                            f"({len(data)} bodies)"
                        )
                        return {
                            "client_name": client_name,
                            "body_count": len(data),
                            "url": api_url,
                        }
                except ValueError:
                    continue
        except requests.exceptions.RequestException:
            continue

    return None


def discover_civicclerk_subdomain(
    city_name: str,
    state: Optional[str] = None,
    timeout: int = 8,
) -> Optional[Dict[str, Any]]:
    """
    Discover a CivicClerk subdomain by trying common API patterns.

    Given a city name like "El Cerrito" and state "CA", tries patterns:
    - elcerritoca (slug+state)
    - elcerrito (slug)
    - cityofelcerrito (cityof prefix)

    For each pattern, probes {candidate}.api.civicclerk.com/v1/Events.
    Returns on first successful hit (200 with OData response).

    Args:
        city_name: City name (e.g., "El Cerrito", "Hayward")
        state: Two-letter state/province code (optional)
        timeout: HTTP request timeout in seconds

    Returns:
        Dict with keys: subdomain, board_count, url
        None if no CivicClerk instance found
    """
    slug = re.sub(r"[\s\-]+", "", city_name.lower().strip())

    candidates = [
        slug,                    # e.g., elcerrito
        f"cityof{slug}",        # e.g., cityofelcerrito
        f"townof{slug}",        # e.g., townofelcerrito
    ]
    if state:
        state = state.lower().strip()
        candidates.insert(0, f"{slug}{state}")         # e.g., elcerritoca, austintx
        candidates.append(f"cityof{slug}{state}")      # e.g., cityofelcerritoca
        candidates.append(f"townof{slug}{state}")      # e.g., townofelcerritoca

    headers = {
        "Accept": "application/json",
        "Origin": "https://portal.civicclerk.com",
    }

    for subdomain in candidates:
        # Try Events first (always available), then Boards (sometimes 404)
        for endpoint in ["Events?$top=1", "Boards"]:
            api_url = f"https://{subdomain}.api.civicclerk.com/v1/{endpoint}"
            try:
                response = requests.get(api_url, headers=headers, timeout=timeout)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        count = 0
                        if isinstance(data, dict) and "value" in data:
                            count = len(data.get("value", []))
                        elif isinstance(data, list):
                            count = len(data)
                        else:
                            continue

                        if count > 0:
                            logger.info(
                                f"CivicClerk discovered: {subdomain} "
                                f"({count} items via {endpoint})"
                            )
                            return {
                                "subdomain": subdomain,
                                "board_count": count,
                                "url": f"https://{subdomain}.api.civicclerk.com/v1",
                            }
                    except ValueError:
                        continue
            except requests.exceptions.RequestException:
                continue

    return None


def discover_escribe_instance(
    city_name: str,
    state: Optional[str] = None,
    timeout: int = 8,
) -> Optional[Dict[str, Any]]:
    """
    Discover an eScribe instance by trying common URL patterns.

    eScribe instances are at pub-{instance}.escribemeetings.com.
    Tries patterns like: nationalcity, cityofnationalcity, etc.

    Args:
        city_name: City name (e.g., "National City", "Ottawa")
        state: Two-letter state/province code (optional)
        timeout: HTTP request timeout in seconds

    Returns:
        Dict with keys: instance_name, url
        None if no eScribe instance found
    """
    slug = re.sub(r"[\s\-]+", "", city_name.lower().strip())
    hyphenated = re.sub(r"[\s]+", "-", city_name.lower().strip())

    candidates = [
        slug,                    # e.g., nationalcity, ottawa
        hyphenated,              # e.g., national-city
        f"cityof{slug}",        # e.g., cityofnationalcity
        f"townof{slug}",
    ]
    if state:
        state_lower = state.lower().strip()
        candidates.insert(1, f"{slug}{state_lower}")  # e.g., nationalcityca

    for instance_name in candidates:
        confidence, meta = _detect_escribe(instance_name, timeout)
        if confidence >= 0.60:
            logger.info(f"eScribe discovered: pub-{instance_name}.escribemeetings.com")
            return {
                "instance_name": instance_name,
                "url": f"https://pub-{instance_name}.escribemeetings.com",
            }

    return None


def discover_simbli_instance(
    district_name: str,
    state: Optional[str] = None,
    timeout: int = 8,
) -> Optional[Dict[str, Any]]:
    """
    Discover a Simbli instance by trying common URL patterns.

    Simbli instances are at simbli.eboardsolutions.com with district-specific
    S= parameters. Discovery probes the meeting listing page.

    Args:
        district_name: School district name (e.g., "San Rafael City Schools")
        state: Two-letter state code (optional)
        timeout: HTTP request timeout in seconds

    Returns:
        Dict with keys: board_url, district_name
        None if no Simbli instance found
    """
    # Simbli uses eboardsolutions.com with various subdomain patterns
    slug = re.sub(r"[\s\-]+", "", district_name.lower().strip())

    # Common Simbli URL patterns
    # Most districts use simbli.eboardsolutions.com with an S= parameter
    # Some use custom subdomains like srcs.simbli.com
    candidates = [
        slug,                    # e.g., srcs
        f"{slug}usd",          # e.g., sanleandrousd
    ]
    if state:
        state_lower = state.lower().strip()
        candidates.append(f"{slug}{state_lower}")  # e.g., srcsca

    # Try subdomain patterns: {name}.simbli.com
    for candidate in candidates:
        board_url = f"https://{candidate}.simbli.com/index.php"
        confidence, meta = _detect_simbli(board_url, timeout)
        if confidence >= 0.70:
            logger.info(f"Simbli discovered: {board_url}")
            return {
                "board_url": board_url,
                "district_name": district_name,
            }

    return None


def discover_platform(
    city_name: str,
    state: Optional[str] = None,
    timeout: int = 8,
) -> Optional[Dict[str, Any]]:
    """
    Discover the civic platform for a city by trying all known platforms.

    Tries Legistar, CivicClerk, Granicus, eScribe, and ProudCity discovery
    in order of API speed.

    Args:
        city_name: City name (e.g., "Berkeley", "El Cerrito", "Dublin")
        state: Two-letter state code (default: "ca")
        timeout: HTTP request timeout in seconds

    Returns:
        Dict with keys: platform, confidence, details
        - platform: "legistar", "civicclerk", "granicus", "escribe", or "proudcity"
        - confidence: 0.0-1.0
        - details: platform-specific discovery results
        None if no platform found
    """
    slug = re.sub(r"[\s\-]+", "", city_name.lower().strip())

    # 1. Try Legistar (fastest — single API call per candidate)
    legistar = discover_legistar_client(city_name, state=state, timeout=timeout)
    if legistar:
        return {
            "platform": "legistar",
            "confidence": 0.95,
            "details": legistar,
        }

    # 2. Try CivicClerk (fast — single API call per candidate)
    civicclerk = discover_civicclerk_subdomain(city_name, state=state, timeout=timeout)
    if civicclerk:
        return {
            "platform": "civicclerk",
            "confidence": 0.95,
            "details": civicclerk,
        }

    # 3. Try Granicus (slower — probes root + view_ids)
    granicus = discover_granicus_subdomain(city_name, state=state, timeout=timeout)
    if granicus:
        return {
            "platform": "granicus",
            "confidence": 0.95,
            "details": granicus,
        }

    # 4. Try eScribe (probes escribemeetings.com)
    escribe = discover_escribe_instance(city_name, state=state, timeout=timeout)
    if escribe:
        return {
            "platform": "escribe",
            "confidence": 0.95,
            "details": escribe,
        }

    # 5. Try Simbli (school boards at eboardsolutions.com)
    simbli = discover_simbli_instance(city_name, state=state, timeout=timeout)
    if simbli:
        return {
            "platform": "simbli",
            "confidence": 0.95,
            "details": simbli,
        }

    # 6. Try ProudCity (slowest — guess website URL, then scrape)
    hyphenated = re.sub(r"[\s]+", "-", city_name.lower().strip())
    proudcity_urls = [
        f"https://www.cityof{slug}.org",
        f"https://cityof{slug}.org",
        f"https://www.{slug}.org",
        f"https://{slug}.org",
        f"https://www.{slug}.gov",
    ]
    if state:
        proudcity_urls.append(f"https://{slug}.{state.lower()}.gov")
    # Add hyphenated variants for multi-word cities (e.g., "san-rafael" vs "sanrafael")
    if hyphenated != slug:
        proudcity_urls.extend([
            f"https://www.cityof{hyphenated}.org",
            f"https://www.{hyphenated}.org",
            f"https://www.{hyphenated}.gov",
        ])
    for url in proudcity_urls:
        try:
            pc_confidence, pc_meta = _detect_proudcity(url, timeout=timeout)
            if pc_confidence >= 0.50:
                return {
                    "platform": "proudcity",
                    "confidence": pc_confidence,
                    "details": {
                        "url": url,
                        **pc_meta,
                    },
                }
        except Exception:
            continue

    return None


def detect_platform_batch(
    urls: List[str],
    timeout: int = 10
) -> Dict[str, DetectionResult]:
    """
    Detect platforms for multiple city URLs.

    Args:
        urls: List of city website URLs
        timeout: Per-request timeout in seconds

    Returns:
        Dict mapping URL to DetectionResult
    """
    results = {}
    for url in urls:
        try:
            results[url] = detect_platform(url, timeout=timeout)
        except Exception as e:
            logger.error(f"Detection failed for {url}: {e}")
            results[url] = DetectionResult(
                source_type=None,
                source_id=None,
                platform_name=None,
                confidence=0.0,
                errors=[str(e)],
            )
    return results
