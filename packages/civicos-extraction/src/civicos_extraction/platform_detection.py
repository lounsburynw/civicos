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

    Returns:
        Tuple of (confidence, metadata)
    """
    api_url = f"https://{subdomain}.api.civicclerk.com/v1/Boards?$top=1"
    metadata: Dict[str, Any] = {"api_url": api_url}

    try:
        headers = {"Accept": "application/json"}
        response = requests.get(api_url, headers=headers, timeout=timeout)
        metadata["status_code"] = response.status_code

        if response.status_code == 200:
            try:
                data = response.json()
                # CivicClerk uses OData format with 'value' key
                if isinstance(data, dict) and "value" in data:
                    boards = data.get("value", [])
                    metadata["board_count"] = len(boards)
                    # High confidence: valid OData response
                    return 0.95, metadata
                elif isinstance(data, list):
                    # Some endpoints return direct list
                    metadata["board_count"] = len(data)
                    return 0.90, metadata
            except ValueError:
                metadata["error"] = "Invalid JSON response"
                return 0.0, metadata
        elif response.status_code == 404:
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

        # ProudCity pattern: links ending in -meetings/ or -hearings/
        archive_pattern = re.compile(r'/([a-z0-9-]+)-(meetings|hearings)/?$')
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


def detect_platform(
    base_url: str,
    jurisdiction_id: Optional[str] = None,
    timeout: int = 10
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

    # 2. Try CivicClerk (API-based)
    # Try common subdomain patterns
    civicclerk_subdomains = [
        client_name,
        f"{client_name}ca",  # e.g., elcerritoca
        client_name.replace("city", ""),  # cityof... -> ...
    ]
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

    # 3. Try ProudCity (scraping-based, slowest)
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
