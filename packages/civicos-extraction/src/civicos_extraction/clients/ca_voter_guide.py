"""
CA Voter Guide Ballot Measure Content Client.

Extracts ballot measure content (full text, fiscal impact, pro/con arguments)
from California official sources:

1. LAO (Legislative Analyst's Office) — fiscal impact analysis
   URL: https://lao.ca.gov/BallotAnalysis/Proposition?number={N}&year={YYYY}

2. CA SOS Voter Information Guide (HTML) — full text, arguments for/against
   URL: https://voterguide.sos.ca.gov/propositions/proposition-{N}/
   (HTML version availability varies by election cycle)

3. CA Legislature — bill text for legislative referrals (ACA, SCA, SB)
   URL: https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id={id}

Usage:
    client = CAVoterGuideClient(election_year=2024, election_type="general")
    content = client.get_proposition_content(36)
    # Returns: {"full_text": "...", "fiscal_impact": "...", "arguments_for": [...], ...}

    # Enrich existing ballot measures in storage:
    enrich_ballot_measure_content(client, storage, jurisdiction_id, election_id)
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

import httpx

from civicos_extraction.clients.base import HealthStatus, ValidationResult

logger = logging.getLogger(__name__)

# ==================== Constants ====================

LAO_BASE = "https://lao.ca.gov/BallotAnalysis"
VIG_BASE = "https://voterguide.sos.ca.gov"
LEGINFO_BASE = "https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml"


# ==================== HTML Parsing ====================


def _extract_text_blocks(html: str) -> List[str]:
    """Extract text blocks from HTML, stripping tags."""
    # Remove script/style blocks
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace block elements with newlines
    html = re.sub(r"<(br|p|div|h[1-6]|li|tr)[^>]*>", "\n", html, flags=re.IGNORECASE)
    # Strip remaining tags
    html = re.sub(r"<[^>]+>", "", html)
    # Decode common entities
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    html = html.replace("&nbsp;", " ").replace("&#8217;", "'").replace("&#8220;", '"').replace("&#8221;", '"')
    # Collapse whitespace within lines, preserve paragraph breaks
    lines = [line.strip() for line in html.split("\n")]
    return [line for line in lines if line]


def _extract_section(lines: List[str], start_pattern: str, stop_patterns: List[str]) -> str:
    """Extract text between a start pattern and any of the stop patterns."""
    collecting = False
    collected = []
    for line in lines:
        if re.search(start_pattern, line, re.IGNORECASE):
            collecting = True
            continue
        if collecting:
            if any(re.search(p, line, re.IGNORECASE) for p in stop_patterns):
                break
            collected.append(line)
    return "\n".join(collected).strip()


# ==================== LAO Parsing ====================


def parse_lao_proposition(html: str, prop_number: int) -> Dict[str, Any]:
    """Parse LAO proposition analysis page into structured content.

    Returns dict with: title, summary, fiscal_impact, background.
    """
    lines = _extract_text_blocks(html)
    if not lines:
        return {}

    # Find title — usually the first substantial line after header
    title = ""
    for line in lines:
        if f"proposition {prop_number}" in line.lower() or f"prop {prop_number}" in line.lower():
            title = line
            break

    # Extract fiscal impact section
    fiscal_impact = _extract_section(
        lines,
        r"fiscal\s+(impact|effect|analysis)",
        [r"^(background|summary|what|how|argument)", r"^\s*$"],
    )

    # Extract summary/background
    summary = _extract_section(
        lines,
        r"(summary|what\s+this\s+measure\s+would\s+do|overview)",
        [r"^(fiscal|argument|background)", r"^\s*$"],
    )

    return {
        "title": title,
        "summary": summary,
        "fiscal_impact": fiscal_impact,
        "source": "lao",
    }


# ==================== VIG Parsing ====================


def parse_vig_proposition(html: str, prop_number: int) -> Dict[str, Any]:
    """Parse CA Voter Information Guide proposition page.

    Returns dict with: full_text, fiscal_impact, arguments_for, arguments_against.
    """
    lines = _extract_text_blocks(html)
    if not lines:
        return {}

    # Extract full text of the measure
    full_text = _extract_section(
        lines,
        r"(text\s+of\s+(the\s+)?proposed\s+(law|measure|amendment))",
        [r"argument\s+(in\s+favor|for)", r"fiscal\s+impact", r"^\s*$"],
    )

    # Extract fiscal impact
    fiscal_impact = _extract_section(
        lines,
        r"fiscal\s+(impact|effect|analysis)",
        [r"argument\s+(in\s+favor|for)", r"text\s+of", r"^\s*$"],
    )

    # Extract arguments for
    arg_for = _extract_section(
        lines,
        r"argument\s+(in\s+favor|for)",
        [r"argument\s+against", r"rebuttal\s+to\s+argument\s+(in\s+favor|for)", r"^\s*$"],
    )

    # Extract arguments against
    arg_against = _extract_section(
        lines,
        r"argument\s+against",
        [r"rebuttal\s+to\s+argument\s+against", r"argument\s+(in\s+favor|for)", r"^\s*$"],
    )

    result: Dict[str, Any] = {"source": "ca_vig"}
    if full_text:
        result["full_text"] = full_text
    if fiscal_impact:
        result["fiscal_impact"] = fiscal_impact
    if arg_for:
        result["arguments_for"] = [arg_for]
    if arg_against:
        result["arguments_against"] = [arg_against]

    return result


# ==================== Client ====================


class CAVoterGuideClient:
    """Client for extracting California ballot measure content.

    Fetches proposition details from LAO, SOS voter guide, and legislature.

    Args:
        election_year: Election year (e.g., 2024)
        election_type: "primary" or "general"
        request_delay: Seconds between HTTP requests
        timeout: HTTP request timeout in seconds
    """

    def __init__(
        self,
        election_year: int,
        election_type: str = "general",
        request_delay: float = 1.0,
        timeout: float = 30.0,
    ):
        self.election_year = election_year
        self.election_type = election_type
        self.request_delay = request_delay
        self.timeout = timeout
        self._last_request_time = 0.0

    @property
    def platform_name(self) -> str:
        return "ca_voter_guide"

    @property
    def source_id(self) -> str:
        return f"ca_voter_guide-{self.election_year}-{self.election_type}"

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.time()

    def _fetch(self, url: str) -> Optional[str]:
        """Fetch URL content with rate limiting and error handling."""
        self._rate_limit()
        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "CivicOS/1.0 (civic data)"})
                if resp.status_code == 200:
                    return resp.text
                logger.warning("HTTP %d fetching %s", resp.status_code, url)
                return None
        except httpx.HTTPError as e:
            logger.warning("Error fetching %s: %s", url, e)
            return None

    def get_lao_analysis(self, prop_number: int) -> Dict[str, Any]:
        """Fetch LAO fiscal analysis for a proposition.

        Args:
            prop_number: Proposition number (e.g., 36)

        Returns:
            Dict with title, summary, fiscal_impact, or empty dict on failure.
        """
        url = f"{LAO_BASE}/Proposition?number={prop_number}&year={self.election_year}"
        html = self._fetch(url)
        if not html:
            return {}
        return parse_lao_proposition(html, prop_number)

    def get_vig_content(self, prop_number: int) -> Dict[str, Any]:
        """Fetch voter guide content for a proposition.

        The HTML voter guide may not be available until close to the election.

        Args:
            prop_number: Proposition number

        Returns:
            Dict with full_text, fiscal_impact, arguments_for, arguments_against.
        """
        url = f"{VIG_BASE}/propositions/proposition-{prop_number}/"
        html = self._fetch(url)
        if not html:
            return {}
        return parse_vig_proposition(html, prop_number)

    def get_proposition_content(self, prop_number: int) -> Dict[str, Any]:
        """Fetch all available content for a proposition, merging sources.

        Tries LAO first (fiscal impact), then VIG (full text, arguments).
        LAO is more reliably accessible; VIG may be blocked by Cloudflare.

        Args:
            prop_number: Proposition number

        Returns:
            Merged dict with all available fields.
        """
        result: Dict[str, Any] = {
            "prop_number": prop_number,
            "election_year": self.election_year,
            "full_text": None,
            "fiscal_impact": None,
            "arguments_for": [],
            "arguments_against": [],
            "full_text_url": None,
            "sources": [],
        }

        # LAO fiscal analysis
        lao = self.get_lao_analysis(prop_number)
        if lao:
            result["sources"].append("lao")
            if lao.get("fiscal_impact"):
                result["fiscal_impact"] = lao["fiscal_impact"]
            if lao.get("title") and not result.get("title"):
                result["title"] = lao["title"]
            if lao.get("summary"):
                result["summary"] = lao["summary"]

        # Voter guide (may 403)
        vig = self.get_vig_content(prop_number)
        if vig:
            result["sources"].append("ca_vig")
            if vig.get("full_text"):
                result["full_text"] = vig["full_text"]
            if vig.get("fiscal_impact") and not result["fiscal_impact"]:
                result["fiscal_impact"] = vig["fiscal_impact"]
            if vig.get("arguments_for"):
                result["arguments_for"] = vig["arguments_for"]
            if vig.get("arguments_against"):
                result["arguments_against"] = vig["arguments_against"]

        # Set full text URL
        result["full_text_url"] = (
            f"{VIG_BASE}/propositions/proposition-{prop_number}/"
        )

        return result

    def health(self) -> HealthStatus:
        """Check connectivity to data sources."""
        from datetime import datetime

        start = time.time()
        errors = []
        count = 0

        # Check LAO
        try:
            url = f"{LAO_BASE}/Propositions"
            with httpx.Client(timeout=10, follow_redirects=True) as client:
                resp = client.get(url)
                if resp.status_code == 200:
                    count += 1
                else:
                    errors.append(f"LAO returned {resp.status_code}")
        except httpx.HTTPError as e:
            errors.append(f"LAO error: {e}")

        return HealthStatus(
            source_id=self.source_id,
            source_type="ca_voter_guide",
            jurisdiction_id="state-california",
            is_available=len(errors) == 0,
            available_count=count,
            last_checked=datetime.utcnow(),
            check_duration_ms=(time.time() - start) * 1000,
            errors=errors,
        )

    def validate(self) -> ValidationResult:
        """Validate client configuration."""
        start = time.time()
        errors = []
        warnings = []

        if self.election_year < 2000 or self.election_year > 2030:
            errors.append(f"Invalid election year: {self.election_year}")
        if self.election_type not in ("primary", "general", "special"):
            errors.append(f"Invalid election type: {self.election_type}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=len(errors) == 0,
            api_reachable=True,
            errors=errors,
            warnings=warnings,
            check_duration_ms=(time.time() - start) * 1000,
        )


# ==================== Storage Enrichment ====================


def enrich_ballot_measure_content(
    client: CAVoterGuideClient,
    storage: Any,
    jurisdiction_id: str,
    election_id: str,
    prop_numbers: Optional[List[int]] = None,
) -> Dict[str, int]:
    """Enrich stored ballot measures with content from the voter guide.

    Reads election_contests from storage, finds state_proposition contests,
    fetches content for each, and updates raw_data.mapped_ballot_measure.

    Args:
        client: CAVoterGuideClient instance
        storage: StorageBackend with get/store election_contests
        jurisdiction_id: e.g., "city-san-rafael"
        election_id: Election to enrich
        prop_numbers: Optional list of specific prop numbers to fetch.
            If None, attempts all state_proposition contests.

    Returns:
        Dict with counts: {"enriched": N, "skipped": N, "failed": N}
    """
    import json

    contests = storage.get_election_contests(election_id)
    stats = {"enriched": 0, "skipped": 0, "failed": 0}

    for contest in contests:
        contest_type = contest.get("contest_type")
        if contest_type != "state_proposition":
            continue

        # Extract prop number from title (e.g., "Proposition 36" or "Measure A")
        title = contest.get("title", "")
        match = re.search(r"proposition\s+(\d+)", title, re.IGNORECASE)
        if not match:
            # Try "Prop N" format
            match = re.search(r"prop\.?\s*(\d+)", title, re.IGNORECASE)
        if not match:
            stats["skipped"] += 1
            continue

        prop_num = int(match.group(1))
        if prop_numbers and prop_num not in prop_numbers:
            stats["skipped"] += 1
            continue

        # Check if already enriched
        raw_data = contest.get("raw_data")
        if isinstance(raw_data, str):
            raw_data = json.loads(raw_data)
        raw_data = raw_data or {}
        bm = raw_data.get("mapped_ballot_measure") or {}
        if bm.get("full_text") or bm.get("fiscal_impact"):
            stats["skipped"] += 1
            continue

        # Fetch content
        try:
            content = client.get_proposition_content(prop_num)
            if not content.get("fiscal_impact") and not content.get("full_text"):
                stats["failed"] += 1
                continue

            # Merge into existing ballot measure data
            if bm:
                bm["full_text"] = content.get("full_text")
                bm["fiscal_impact"] = content.get("fiscal_impact")
                bm["arguments_for"] = content.get("arguments_for", [])
                bm["arguments_against"] = content.get("arguments_against", [])
                bm["full_text_url"] = content.get("full_text_url")
            else:
                raw_data["mapped_ballot_measure"] = {
                    "title": title,
                    "description": content.get("summary", ""),
                    "full_text": content.get("full_text"),
                    "fiscal_impact": content.get("fiscal_impact"),
                    "arguments_for": content.get("arguments_for", []),
                    "arguments_against": content.get("arguments_against", []),
                    "full_text_url": content.get("full_text_url"),
                    "source": "ca_voter_guide",
                }

            raw_data["mapped_ballot_measure"] = bm if bm else raw_data["mapped_ballot_measure"]

            # Update contest in storage
            contest["raw_data"] = raw_data
            storage.store_election_contests(
                jurisdiction_id=jurisdiction_id,
                election_id=election_id,
                contests=[contest],
            )
            stats["enriched"] += 1
            logger.info("Enriched Proposition %d with ballot measure content", prop_num)

        except Exception as e:
            logger.error("Failed to enrich Proposition %d: %s", prop_num, e)
            stats["failed"] += 1

    return stats
