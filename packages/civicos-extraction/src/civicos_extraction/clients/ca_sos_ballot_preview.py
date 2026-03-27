"""
CA Secretary of State Ballot Preview Client.

Downloads certified candidate list PDFs from the SOS CDN and parses them
to provide pre-election ballot preview data (candidates, party, designation).

CDN URL pattern:
    https://elections.cdn.sos.ca.gov/statewide-elections/{election_slug}/{race}.pdf

Supported races: congress, state-senate, assembly, governor, lt-governor,
    controller, treasurer, attorney-general

Each PDF has a consistent per-candidate layout:
    Name[*]              (* = incumbent)
    Party Preference
    Address Line 1
    City, State ZIP
    [(xxx) xxx-xxxx ...]
    [WEBSITE: url]
    [E-MAIL: email]
    Ballot Designation

District info appears in the page footer:
    "United States Representative District N"
    "State Senate District N"
    "State Assembly Member District N"
    "Governor"  (statewide, no district number)

Usage:
    client = CASOSBallotPreviewClient("2026-primary")
    candidates = client.get_candidates("congress", districts=[2])
    # Returns: {2: [{"name": "...", "party": "Democratic", ...}, ...]}

    # Full extraction pipeline:
    extract_ca_sos_preview_to_storage(client, storage, "city-san-rafael", ...)
"""

import io
import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import httpx

from civicos_extraction.clients.base import HealthStatus, ValidationResult

logger = logging.getLogger(__name__)

# ==================== Constants ====================

CDN_BASE = "https://elections.cdn.sos.ca.gov/statewide-elections"

KNOWN_PARTIES = frozenset({
    "Democratic",
    "Republican",
    "No Party Preference",
    "American Independent",
    "Green",
    "Libertarian",
    "Peace and Freedom",
})

# Race slug -> (district regex, contest_type, title template, statewide?)
RACE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "congress": {
        "district_pattern": r"United States Representative District (\d+)",
        "contest_type": "federal_house",
        "title_template": "US House District {district}",
    },
    "state-senate": {
        "district_pattern": r"State Senate District (\d+)",
        "contest_type": "state_legislature",
        "title_template": "State Senate District {district}",
    },
    "assembly": {
        "district_pattern": r"State Assembly Member District (\d+)",
        "contest_type": "state_legislature",
        "title_template": "State Assembly District {district}",
    },
    "governor": {
        "district_pattern": r"^Governor$",
        "contest_type": "state_governor",
        "title_template": "Governor",
        "statewide": True,
    },
    "lt-governor": {
        "district_pattern": r"^Lieutenant Governor$",
        "contest_type": "state_executive",
        "title_template": "Lieutenant Governor",
        "statewide": True,
    },
    "controller": {
        "district_pattern": r"^Controller$",
        "contest_type": "state_executive",
        "title_template": "Controller",
        "statewide": True,
    },
    "treasurer": {
        "district_pattern": r"^Treasurer$",
        "contest_type": "state_executive",
        "title_template": "Treasurer",
        "statewide": True,
    },
    "attorney-general": {
        "district_pattern": r"^Attorney General$",
        "contest_type": "state_executive",
        "title_template": "Attorney General",
        "statewide": True,
    },
}


# ==================== PDF Parsing ====================


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _parse_district_from_page(text: str, race_slug: str) -> Optional[int]:
    """Extract district number from a page's footer text.

    Returns None for statewide races (governor, etc.) or if no match found.
    """
    config = RACE_CONFIGS.get(race_slug)
    if not config:
        return None
    if config.get("statewide"):
        return None
    m = re.search(config["district_pattern"], text, re.MULTILINE)
    if m:
        return int(m.group(1))
    return None


def _split_candidate_text(page_text: str) -> str:
    """Remove footer/notice text, returning only candidate entries."""
    # Remove the notice section (first page of each district)
    notice_start = page_text.find("TO ALL CANDIDATES FOR THE OFFICE")
    if notice_start != -1:
        page_text = page_text[:notice_start]

    # Remove the footer that appears on every page
    footer_start = page_text.find("Notice to Candidates")
    if footer_start != -1:
        page_text = page_text[:footer_start]

    return page_text.strip()


def _parse_candidates_from_text(text: str) -> List[Dict[str, Any]]:
    """Parse candidate entries from cleaned PDF text.

    Each candidate block follows the pattern:
        Name[*]
        Party
        Address
        City, State ZIP
        [Phone]
        [WEBSITE: url]
        [E-MAIL: email]
        Ballot Designation
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    candidates = []
    i = 0

    while i < len(lines):
        # Find the next party line — the line before it is the candidate name
        if lines[i] in KNOWN_PARTIES:
            # The name is the previous line (already consumed)
            if not candidates:
                # Edge case: first candidate, name was before this party line
                # but we haven't captured it yet
                break
            # Party belongs to the last candidate that was started
            candidates[-1]["party"] = lines[i]
            i += 1
            # Now parse remaining fields until next name+party pair
            while i < len(lines):
                line = lines[i]
                # Check if this line is a name (next line would be a party)
                if i + 1 < len(lines) and lines[i + 1] in KNOWN_PARTIES:
                    break
                # Phone pattern
                if re.match(r"^\(\d{3}\)\s+\d{3}-\d{4}", line):
                    candidates[-1]["phone"] = line
                elif line.startswith("WEBSITE:"):
                    candidates[-1]["website"] = line[len("WEBSITE:"):].strip()
                elif line.startswith("E-MAIL:"):
                    candidates[-1]["email"] = line[len("E-MAIL:"):].strip()
                elif "address" not in candidates[-1]:
                    candidates[-1]["address"] = line
                elif re.match(r"^[A-Z][a-z]+.*,\s*CA\s+\d{5}", line):
                    candidates[-1]["city_state_zip"] = line
                else:
                    # Last non-matched line before next candidate is
                    # the ballot designation
                    candidates[-1]["ballot_designation"] = line
                i += 1
        else:
            # This line could be a candidate name if the next line is a party
            if i + 1 < len(lines) and lines[i + 1] in KNOWN_PARTIES:
                name = lines[i]
                incumbent = name.endswith("*")
                if incumbent:
                    name = name[:-1].strip()
                candidates.append({
                    "name": name,
                    "incumbent": incumbent,
                    "party": None,
                    "address": None,
                    "city_state_zip": None,
                    "phone": None,
                    "website": None,
                    "email": None,
                    "ballot_designation": None,
                })
            i += 1

    return candidates


def parse_candidate_pdf(
    pdf_bytes: bytes,
    race_slug: str,
) -> Dict[Optional[int], List[Dict[str, Any]]]:
    """Parse a CA SOS candidate PDF into candidates grouped by district.

    Args:
        pdf_bytes: Raw PDF file content
        race_slug: Race identifier (e.g., "congress", "state-senate")

    Returns:
        Dict mapping district number -> list of candidate dicts.
        For statewide races, the key is None.
    """
    import fitz  # pymupdf

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    config = RACE_CONFIGS.get(race_slug)
    if not config:
        raise ValueError(f"Unknown race slug: {race_slug}")

    is_statewide = config.get("statewide", False)

    # Group pages by district
    # For statewide races, all pages belong to the same group (None)
    district_pages: Dict[Optional[int], List[str]] = {}

    for page_idx in range(doc.page_count):
        page = doc[page_idx]
        full_text = page.get_text()

        if is_statewide:
            district_key = None
        else:
            district_key = _parse_district_from_page(full_text, race_slug)
            if district_key is None:
                continue

        candidate_text = _split_candidate_text(full_text)
        if candidate_text:
            district_pages.setdefault(district_key, []).append(candidate_text)

    # Parse candidates from combined text for each district
    result: Dict[Optional[int], List[Dict[str, Any]]] = {}
    for district, texts in district_pages.items():
        combined = "\n".join(texts)
        candidates = _parse_candidates_from_text(combined)
        if candidates:
            result[district] = candidates

    doc.close()
    return result


# ==================== Storage Protocol ====================


@runtime_checkable
class ElectionStorageProtocol(Protocol):
    def store_elections(
        self, jurisdiction_id: str, elections: List[Dict], as_of: Any = None
    ) -> int: ...

    def store_election_contests(
        self, election_id: str, contests: List[Dict], as_of: Any = None
    ) -> int: ...


# ==================== Storage Mappers ====================


def ca_sos_preview_candidate_to_storage(
    candidate: Dict[str, Any],
    race_slug: str,
    district: Optional[int],
) -> Dict[str, Any]:
    """Map a parsed candidate to storage format."""
    name = candidate["name"]
    slug_parts = [race_slug]
    if district is not None:
        slug_parts.append(str(district))
    slug_parts.append(_slugify(name))
    cand_id = f"ca-sos-preview-{'-'.join(slug_parts)}"

    return {
        "id": cand_id,
        "name": name,
        "party": candidate.get("party"),
        "incumbent": candidate.get("incumbent", False),
        "ballot_designation": candidate.get("ballot_designation"),
        "website": candidate.get("website"),
        "email": candidate.get("email"),
        "phone": candidate.get("phone"),
        "votes_received": None,
        "vote_percentage": None,
        "is_winner": False,
        "source": "ca_sos_ballot_preview",
    }


def ca_sos_preview_to_contest(
    race_slug: str,
    district: Optional[int],
    candidates: List[Dict[str, Any]],
    election_slug: str,
) -> Dict[str, Any]:
    """Map parsed district candidates to a contest storage dict."""
    config = RACE_CONFIGS[race_slug]
    title = config["title_template"].format(district=district)
    contest_type = config["contest_type"]

    slug_parts = [race_slug]
    if district is not None:
        slug_parts.append(str(district))
    contest_id = f"ca-sos-preview-{election_slug}-{'-'.join(slug_parts)}"

    storage_candidates = [
        ca_sos_preview_candidate_to_storage(c, race_slug, district)
        for c in candidates
    ]

    return {
        "id": contest_id,
        "title": title,
        "contest_type": contest_type,
        "district_name": title if district else None,
        "number_elected": 1,
        "candidates": storage_candidates,
        "ballot_measure": None,
        "raw_data": {
            "race_slug": race_slug,
            "district": district,
            "election_slug": election_slug,
            "source": "ca_sos_ballot_preview",
            "parsed_candidates": candidates,
        },
    }


def ca_sos_preview_to_election(
    election_slug: str,
    election_date: str,
    election_type: str = "primary",
) -> Dict[str, Any]:
    """Create an election record for ballot preview data."""
    return {
        "id": f"ca-sos-preview-{election_slug}",
        "name": f"California {election_type.title()} Election",
        "election_date": election_date,
        "election_type": election_type,
        "source": "ca_sos_ballot_preview",
        "source_url": f"{CDN_BASE}/{election_slug}/",
        "raw_data": {
            "election_slug": election_slug,
            "data_type": "pre_election_candidates",
        },
    }


# ==================== Client ====================


class CASOSBallotPreviewClient:
    """Client for downloading and parsing CA SOS certified candidate PDFs.

    Args:
        election_slug: Election identifier in the CDN path (e.g., "2026-primary")
        election_date: ISO date string (e.g., "2026-06-02")
        election_type: "primary", "general", or "special"
        request_delay: Seconds between HTTP requests (rate limiting)
        timeout: HTTP request timeout in seconds
    """

    def __init__(
        self,
        election_slug: str,
        election_date: str,
        election_type: str = "primary",
        request_delay: float = 0.5,
        timeout: int = 30,
    ):
        self.election_slug = election_slug
        self.election_date = election_date
        self.election_type = election_type
        self.request_delay = request_delay
        self.timeout = timeout
        self._pdf_cache: Dict[str, bytes] = {}

    @property
    def platform_name(self) -> str:
        return "ca_sos_ballot_preview"

    @property
    def source_id(self) -> str:
        return f"ca-sos-preview-{self.election_slug}"

    def _pdf_url(self, race_slug: str) -> str:
        return f"{CDN_BASE}/{self.election_slug}/{race_slug}.pdf"

    def _download_pdf(self, race_slug: str) -> Optional[bytes]:
        """Download a candidate PDF from the CDN. Returns None on 404/403."""
        if race_slug in self._pdf_cache:
            return self._pdf_cache[race_slug]

        url = self._pdf_url(race_slug)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url)
                if resp.status_code in (403, 404):
                    logger.info(f"PDF not available: {url} ({resp.status_code})")
                    return None
                resp.raise_for_status()
                self._pdf_cache[race_slug] = resp.content
                time.sleep(self.request_delay)
                return resp.content
        except httpx.HTTPError as e:
            logger.warning(f"Failed to download {url}: {e}")
            return None

    def get_candidates(
        self,
        race_slug: str,
        districts: Optional[List[int]] = None,
    ) -> Dict[Optional[int], List[Dict[str, Any]]]:
        """Get candidates for a race, optionally filtered by district.

        Args:
            race_slug: Race PDF name (e.g., "congress", "state-senate", "assembly")
            districts: District numbers to include (None = all districts)

        Returns:
            Dict mapping district number -> list of candidate dicts.
            For statewide races, key is None.
        """
        if race_slug not in RACE_CONFIGS:
            raise ValueError(
                f"Unknown race: {race_slug}. "
                f"Supported: {', '.join(RACE_CONFIGS)}"
            )

        pdf_bytes = self._download_pdf(race_slug)
        if pdf_bytes is None:
            return {}

        all_candidates = parse_candidate_pdf(pdf_bytes, race_slug)

        if districts is not None and not RACE_CONFIGS[race_slug].get("statewide"):
            filtered = {
                d: cands
                for d, cands in all_candidates.items()
                if d in districts
            }
            return filtered

        return all_candidates

    def get_all_candidates(
        self,
        race_districts: Dict[str, Optional[List[int]]],
    ) -> Dict[str, Dict[Optional[int], List[Dict[str, Any]]]]:
        """Get candidates for multiple races.

        Args:
            race_districts: Mapping of race_slug -> list of district numbers
                           (or None for all districts / statewide races).
                           Example: {"congress": [2], "state-senate": [2],
                                     "assembly": [12], "governor": None}

        Returns:
            Nested dict: race_slug -> district -> candidates
        """
        results = {}
        for race_slug, districts in race_districts.items():
            candidates = self.get_candidates(race_slug, districts)
            if candidates:
                results[race_slug] = candidates
        return results

    def get_available_races(self) -> List[str]:
        """Check which race PDFs are available on the CDN."""
        available = []
        for race_slug in RACE_CONFIGS:
            url = self._pdf_url(race_slug)
            try:
                with httpx.Client(timeout=10) as client:
                    resp = client.head(url)
                    if resp.status_code == 200:
                        available.append(race_slug)
                time.sleep(self.request_delay)
            except httpx.HTTPError:
                pass
        return available

    def health(self) -> HealthStatus:
        """Check if the CDN is reachable and PDFs are available."""
        start = datetime.now()
        errors = []
        available = 0

        try:
            races = self.get_available_races()
            available = len(races)
        except Exception as e:
            errors.append(str(e))

        elapsed = (datetime.now() - start).total_seconds() * 1000
        return HealthStatus(
            source_id=self.source_id,
            source_type=self.platform_name,
            jurisdiction_id="state-california",
            is_available=available > 0,
            available_count=available,
            last_checked=datetime.now(),
            check_duration_ms=elapsed,
            errors=errors,
            metadata={"election_slug": self.election_slug},
        )

    def validate(self) -> "ValidationResult":
        """Validate that candidate parsing works for available PDFs."""
        start = datetime.now()
        errors = []
        total_candidates = 0

        # Try parsing the first available race
        for race_slug in RACE_CONFIGS:
            pdf_bytes = self._download_pdf(race_slug)
            if pdf_bytes is None:
                continue
            try:
                candidates = parse_candidate_pdf(pdf_bytes, race_slug)
                for district_cands in candidates.values():
                    total_candidates += len(district_cands)
                break
            except Exception as e:
                errors.append(f"{race_slug}: {e}")

        elapsed = (datetime.now() - start).total_seconds() * 1000
        return ValidationResult(
            source_id=self.source_id,
            is_valid=total_candidates > 0,
            check_duration_ms=elapsed,
            errors=errors,
            metadata={
                "candidates_parsed": total_candidates,
                "election_slug": self.election_slug,
            },
        )


# ==================== Extraction Pipeline ====================


def extract_ca_sos_preview_to_storage(
    client: CASOSBallotPreviewClient,
    storage: ElectionStorageProtocol,
    jurisdiction_id: str,
    race_districts: Dict[str, Optional[List[int]]],
) -> Dict[str, int]:
    """Extract CA SOS ballot preview data and store it.

    Args:
        client: CASOSBallotPreviewClient instance
        storage: StorageBackend with election storage methods
        jurisdiction_id: Target jurisdiction (e.g., "city-san-rafael")
        race_districts: Race slug -> district numbers to extract.
                       Example: {"congress": [2], "state-senate": [2],
                                 "assembly": [12], "governor": None}

    Returns:
        Dict with counts: {"elections": N, "contests": M, "candidates": C}
    """
    all_candidates = client.get_all_candidates(race_districts)

    if not all_candidates:
        logger.warning(
            "No candidate data found from CA SOS PDFs — "
            "skipping storage to avoid empty election record"
        )
        return {"elections": 0, "contests": 0, "candidates": 0}

    # Store election record
    election = ca_sos_preview_to_election(
        client.election_slug, client.election_date, client.election_type
    )
    stored_elections = storage.store_elections(jurisdiction_id, [election])
    election_id = election["id"]

    # Build and store contests
    contests = []
    total_candidates = 0
    for race_slug, district_map in all_candidates.items():
        for district, candidates in district_map.items():
            contest = ca_sos_preview_to_contest(
                race_slug, district, candidates, client.election_slug
            )
            contests.append(contest)
            total_candidates += len(candidates)

    stored_contests = 0
    if contests:
        stored_contests = storage.store_election_contests(election_id, contests)

    logger.info(
        f"CA SOS ballot preview: {stored_elections} election, "
        f"{stored_contests} contests, {total_candidates} candidates "
        f"for {jurisdiction_id}"
    )

    return {
        "elections": stored_elections,
        "contests": stored_contests,
        "candidates": total_candidates,
    }
