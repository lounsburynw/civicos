"""
Clarity Elections ENR Client.

Fetches election results from Clarity Elections (Election Night Reporting)
hosted at results.enr.clarityelections.com. County registrars across the US
use this platform for publishing real-time and certified election results.

Key limitations:
- Data is ephemeral — old elections are purged. Must archive on first fetch.
- Election IDs are opaque integers, not sequential.
- JSON summary persists longer than XML detail.

Usage:
    client = ClarityElectionsClient(
        jurisdiction_id="city-cupertino",
        state="CA",
        county="santa_clara",
    )
    health = client.health()
    if health.is_available:
        contests = client.get_summary(election_id="125819")
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from civicos_extraction.clients.base import (
    HealthStatus,
    ValidationResult,
    classify_contest_type,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://results.enr.clarityelections.com"


def _load_clarity_instances() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Load Clarity instance registry from config file.

    Config lives at data/extraction/clarity_instances.json. On Modal, the
    extraction config dir is mounted at CIVICOS_CONFIG_DIR. Falls back to
    an empty dict if the file is missing (e.g., in test environments).
    """
    config_dir = os.environ.get("CIVICOS_CONFIG_DIR")
    if config_dir:
        config_path = Path(config_dir) / "clarity_instances.json"
    else:
        try:
            config_path = (
                Path(__file__).resolve().parents[5]
                / "data"
                / "extraction"
                / "clarity_instances.json"
            )
        except IndexError:
            return {}
    try:
        with open(config_path) as f:
            data = json.load(f)
        return data.get("instances", {})
    except (FileNotFoundError, json.JSONDecodeError):
        logger.warning(
            f"Clarity instances config not found at {config_path}, "
            f"using empty registry",
        )
        return {}


# Registry of known Clarity Elections ENR instances by state.
# Source of truth: data/extraction/clarity_instances.json
CLARITY_INSTANCES: Dict[str, Dict[str, Dict[str, Any]]] = _load_clarity_instances()


def _county_to_url_name(county: str) -> str:
    """Convert county name to Clarity URL format (Title_Case)."""
    parts = county.replace("-", " ").replace("_", " ").split()
    return "_".join(p.capitalize() for p in parts)


def has_clarity_instance(county: str, state: str) -> bool:
    """Check whether a county has a known Clarity Elections instance."""
    state_instances = CLARITY_INSTANCES.get(state.upper(), {})
    return county.lower() in state_instances


def detect_clarity_elections(
    county: str,
    state: str,
    timeout: float = 10.0,
) -> Optional[Dict[str, Any]]:
    """Probe whether a county uses Clarity Elections for results.

    Checks the static registry first, then probes the URL dynamically.
    Returns a config dict if detected, None otherwise.
    """
    state = state.upper()
    county_lower = county.lower()

    state_instances = CLARITY_INSTANCES.get(state, {})
    instance = state_instances.get(county_lower)

    if instance:
        if instance.get("prefer_civera"):
            return None
        url_name = instance["url_name"]
    else:
        url_name = _county_to_url_name(county)

    url = f"{BASE_URL}/{state}/{url_name}/"
    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        if resp.status_code < 400:
            return {
                "county": county_lower,
                "state": state,
                "url_name": url_name,
            }
    except requests.RequestException:
        pass

    return None


class ClarityElectionsClient:
    """Client for Clarity Elections ENR (Election Night Reporting).

    Implements the ElectionExtractor protocol for fetching election results
    from county registrar Clarity Elections pages.
    """

    def __init__(
        self,
        jurisdiction_id: str,
        state: str,
        county: str,
        url_name: Optional[str] = None,
    ):
        self._jurisdiction_id = jurisdiction_id
        self._state = state.upper()
        self._county = county.lower()
        self._url_name = url_name or _county_to_url_name(county)
        self._base = f"{BASE_URL}/{self._state}/{self._url_name}"
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json, text/html"})

    @property
    def platform_name(self) -> str:
        return "clarity_elections"

    @property
    def source_id(self) -> str:
        return f"clarity-{self._county.replace(' ', '-')}"

    @property
    def source_type(self) -> str:
        return "clarity_elections"

    @property
    def url_name(self) -> str:
        return self._url_name

    def health(self) -> HealthStatus:
        start = time.time()
        try:
            resp = self._session.head(
                self._base + "/", timeout=10, allow_redirects=True,
            )
            elapsed = (time.time() - start) * 1000
            ok = resp.status_code < 400
            return HealthStatus(
                source_id=self.source_id,
                source_type=self.source_type,
                jurisdiction_id=self._jurisdiction_id,
                is_available=ok,
                available_count=0,
                last_checked=datetime.utcnow(),
                check_duration_ms=elapsed,
                errors=[] if ok else [f"HTTP {resp.status_code}"],
            )
        except requests.RequestException as e:
            elapsed = (time.time() - start) * 1000
            return HealthStatus(
                source_id=self.source_id,
                source_type=self.source_type,
                jurisdiction_id=self._jurisdiction_id,
                is_available=False,
                available_count=0,
                last_checked=datetime.utcnow(),
                check_duration_ms=elapsed,
                errors=[str(e)],
            )

    def validate(self) -> ValidationResult:
        start = time.time()
        errors: List[str] = []

        if not self._state:
            errors.append("state is required")
        if not self._county:
            errors.append("county is required")

        api_ok = False
        if not errors:
            try:
                resp = self._session.head(
                    self._base + "/", timeout=10, allow_redirects=True,
                )
                api_ok = resp.status_code < 400
                if not api_ok:
                    errors.append(
                        f"Clarity ENR not reachable: HTTP {resp.status_code}",
                    )
            except requests.RequestException as e:
                errors.append(f"Clarity ENR not reachable: {e}")

        elapsed = (time.time() - start) * 1000
        return ValidationResult(
            is_valid=len(errors) == 0 and api_ok,
            config_valid=len(errors) == 0,
            api_reachable=api_ok,
            errors=errors,
            check_duration_ms=elapsed,
        )

    def discover_elections(self, timeout: float = 15.0) -> List[Dict[str, Any]]:
        """Discover available elections for this county.

        Uses a two-tier strategy:
        1. Static registry: Known election IDs in clarity_instances.json
           (reliable, works between election periods)
        2. Landing page scrape: Regex over the SPA HTML/JS as fallback
           (unreliable — Clarity pages are JS SPAs that load data dynamically)

        Returns a list of dicts with keys: election_id, name, url.
        """
        elections: List[Dict[str, Any]] = []
        seen: set[str] = set()

        # Tier 1: Static registry (primary — always works)
        state_instances = CLARITY_INSTANCES.get(self._state, {})
        instance = state_instances.get(self._county)
        if instance:
            for eid in instance.get("election_ids", []):
                eid = str(eid)
                if eid not in seen:
                    seen.add(eid)
                    elections.append({
                        "election_id": eid,
                        "name": f"Election {eid}",
                        "url": f"{self._base}/{eid}/",
                    })

        # Tier 2: Landing page scrape (fallback — may find new IDs)
        try:
            resp = self._session.get(self._base + "/", timeout=timeout)
            if resp.status_code == 200:
                for match in re.finditer(
                    r'(?:href|url|location)["\s=:]+["\']?'
                    r"(?:https?://results\.enr\.clarityelections\.com)?"
                    rf"/?{re.escape(self._state)}/{re.escape(self._url_name)}"
                    r"/(\d{4,8})/",
                    resp.text,
                    re.IGNORECASE,
                ):
                    eid = match.group(1)
                    if eid not in seen:
                        seen.add(eid)
                        elections.append({
                            "election_id": eid,
                            "name": f"Election {eid}",
                            "url": f"{self._base}/{eid}/",
                        })
                        logger.info(
                            f"Clarity discovery: found new election ID {eid} "
                            f"for {self._county} via page scrape "
                            f"(consider adding to clarity_instances.json)",
                        )
        except requests.RequestException as e:
            if not elections:
                logger.warning(
                    f"Failed to discover Clarity elections for {self._county}: {e}",
                )

        return elections

    def get_current_version(
        self, election_id: str, timeout: float = 10.0,
    ) -> Optional[str]:
        """Get the current version string for an election."""
        url = f"{self._base}/{election_id}/current_ver.txt"
        try:
            resp = self._session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.text.strip()
        except requests.RequestException:
            pass
        return None

    def get_election_settings(
        self,
        election_id: str,
        version: Optional[str] = None,
        timeout: float = 10.0,
    ) -> Optional[Dict[str, Any]]:
        """Fetch election settings (name, date, config) for an election.

        The electionsettings.json endpoint provides authoritative election
        metadata including the official name and date.
        """
        if version is None:
            version = self.get_current_version(election_id)
        if version is None:
            return None

        url = (
            f"{self._base}/{election_id}/{version}"
            f"/json/en/electionsettings.json"
        )
        try:
            resp = self._session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except (requests.RequestException, ValueError):
            pass
        return None

    def get_summary(
        self,
        election_id: str,
        version: Optional[str] = None,
        timeout: float = 15.0,
    ) -> Optional[Any]:
        """Fetch the JSON summary for an election.

        If version is not provided, discovers it via current_ver.txt.
        Returns the parsed JSON or None if unavailable.
        """
        if version is None:
            version = self.get_current_version(election_id)
        if version is None:
            logger.warning(
                f"Could not determine version for election {election_id}",
            )
            return None

        url = f"{self._base}/{election_id}/{version}/json/en/summary.json"
        try:
            resp = self._session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning(
                f"Failed to fetch Clarity summary for election {election_id}: {e}",
            )
        return None


# ==================== Mappers ====================


def _infer_election_type(name: str) -> str:
    """Infer election type from the election name string."""
    lower = name.lower()
    if "primary" in lower:
        return "primary"
    if "runoff" in lower:
        return "runoff"
    if "special" in lower:
        return "special"
    if "recall" in lower:
        return "recall"
    return "general"


def _infer_election_date(name: str) -> Optional[str]:
    """Try to extract a date from the election name.

    Clarity names often contain dates like "November 5, 2024 General"
    or "E145 December 30, 2025 Runoff".
    """
    match = re.search(
        r"(January|February|March|April|May|June|July|August|September"
        r"|October|November|December)\s+(\d{1,2}),?\s+(\d{4})",
        name,
    )
    if match:
        try:
            dt = datetime.strptime(
                f"{match.group(1)} {match.group(2)} {match.group(3)}",
                "%B %d %Y",
            )
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", name)
    if match:
        try:
            dt = datetime(
                int(match.group(3)), int(match.group(1)), int(match.group(2)),
            )
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def clarity_results_to_election(
    election_id: str,
    election_name: str,
    county_slug: str,
    state: str,
    url_name: str,
    election_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Map Clarity election metadata to storage format."""
    if not election_date:
        election_date = _infer_election_date(election_name)

    return {
        "id": f"clarity-{county_slug.replace(' ', '-')}-{election_id}",
        "name": election_name,
        "election_date": election_date,
        "election_type": _infer_election_type(election_name),
        "source": "clarity_elections",
        "source_url": f"{BASE_URL}/{state}/{url_name}/{election_id}/",
        "raw_data": {
            "election_id": election_id,
            "county": county_slug,
            "state": state,
        },
    }


def _is_parallel_array_format(contest: Dict[str, Any]) -> bool:
    """Detect Clarity's parallel-array JSON format.

    Live Clarity summary.json uses parallel arrays at the contest level:
    CH = ["Alice", "Bob"], V = [5000, 4000], PCT = [55.5, 44.5]
    rather than nested objects: V = [{"CH": "Alice", "TOT": 5000}, ...]
    """
    ch = contest.get("CH")
    v = contest.get("V")
    return (
        isinstance(ch, list)
        and len(ch) > 0
        and isinstance(ch[0], str)
        and isinstance(v, list)
        and len(v) > 0
        and not isinstance(v[0], dict)
    )


def clarity_contest_to_storage(
    contest: Dict[str, Any],
    county_slug: str,
    election_id: str,
) -> Dict[str, Any]:
    """Map a Clarity JSON contest to ContestDict format.

    Handles two Clarity JSON formats:
    1. Nested objects: V = [{"CH": "Alice", "TOT": 5000, "PE": "55.5"}, ...]
       Field variants: CT/N/text for title, IQ/isQuestion for ballot question.
    2. Parallel arrays (live ENR): C = "Assessor", CH = ["Alice", "Bob"],
       V = [5000, 4000], PCT = [55.5, 44.5], P = ["", ""], W = [0, 1]
    """
    # Detect parallel-array format from live Clarity ENR
    if _is_parallel_array_format(contest):
        title = (
            contest.get("C")
            or contest.get("CT")
            or contest.get("N")
            or contest.get("text", "Unknown Contest")
        )
        is_question = contest.get("IQ") or contest.get("isQuestion", False)
        if isinstance(is_question, str):
            is_question = is_question.lower() == "true"

        # Live ENR has no IQ flag — detect ballot measures from YES/NO candidates
        names = contest.get("CH", [])
        if not is_question and len(names) == 2:
            lower_names = {n.lower() for n in names}
            if lower_names <= {"yes", "no", "bonds yes", "bonds no"}:
                is_question = True

        names = contest.get("CH", [])
        votes_arr = contest.get("V", [])
        pct_arr = contest.get("PCT", [])
        party_arr = contest.get("P", [])
        winner_arr = contest.get("W", [])

        safe_title = re.sub(r"[^a-z0-9]+", "-", title.lower())[:50].strip("-")
        county_id = county_slug.replace(" ", "-")
        contest_id = f"clarity-{county_id}-{election_id}-{safe_title}"

        candidates: List[Dict[str, Any]] = []
        for i, name in enumerate(names):
            votes = votes_arr[i] if i < len(votes_arr) else None
            pct = pct_arr[i] if i < len(pct_arr) else None
            party = party_arr[i] if i < len(party_arr) else None

            if isinstance(votes, str):
                cleaned = votes.replace(",", "")
                votes = int(cleaned) if cleaned.isdigit() else None
            if isinstance(pct, str):
                try:
                    pct = float(pct)
                except ValueError:
                    pct = None

            # Treat empty party strings as None
            if party == "":
                party = None

            is_winner = bool(winner_arr[i]) if i < len(winner_arr) else False

            cand_slug = re.sub(r"[^a-z0-9]+", "-", name.lower())[:40].strip("-")
            candidates.append({
                "id": f"{contest_id}-{i}-{cand_slug}",
                "name": name,
                "party": party,
                "votes_received": votes,
                "vote_percentage": pct,
                "is_winner": is_winner,
                "source": "clarity_elections",
            })

        # If no W flags set, fall back to highest vote count
        if not any(c["is_winner"] for c in candidates):
            with_votes = [c for c in candidates if c["votes_received"] and c["votes_received"] > 0]
            if with_votes:
                winner = max(with_votes, key=lambda c: c["votes_received"])
                winner["is_winner"] = True

        contest_type = "local_measure" if is_question else classify_contest_type(title)

        ballot_measure = None
        if is_question:
            yes_cand = next(
                (c for c in candidates if c["name"].lower() in ("yes", "bonds yes")),
                None,
            )
            no_cand = next(
                (c for c in candidates if c["name"].lower() in ("no", "bonds no")),
                None,
            )
            ballot_measure = {
                "id": f"clarity-{county_id}-measure-{election_id}-{safe_title}",
                "title": title,
                "description": title,
                "measure_type": "measure",
                "full_text": None,
                "full_text_url": None,
                "fiscal_impact": None,
                "arguments_for": [],
                "arguments_against": [],
                "passed": bool(yes_cand and yes_cand.get("is_winner")),
                "yes_votes": yes_cand["votes_received"] if yes_cand else None,
                "no_votes": no_cand["votes_received"] if no_cand else None,
                "yes_percentage": yes_cand["vote_percentage"] if yes_cand else None,
                "no_percentage": no_cand["vote_percentage"] if no_cand else None,
                "source": "clarity_elections",
            }

        enriched_raw = {
            **contest,
            "mapped_candidates": candidates,
            "mapped_ballot_measure": ballot_measure,
        }

        return {
            "id": contest_id,
            "title": title,
            "contest_type": contest_type,
            "district_name": county_slug.replace("_", " ").replace("-", " ").title() + " County",
            "number_elected": 0 if is_question else 1,
            "candidates": candidates,
            "ballot_measure": ballot_measure,
            "raw_data": enriched_raw,
        }

    # ---- Nested-object format (original session-1 fixtures) ----
    title = (
        contest.get("CT")
        or contest.get("N")
        or contest.get("text", "Unknown Contest")
    )
    is_question = contest.get("IQ") or contest.get("isQuestion", False)
    if isinstance(is_question, str):
        is_question = is_question.lower() == "true"

    safe_title = re.sub(r"[^a-z0-9]+", "-", title.lower())[:50].strip("-")
    county_id = county_slug.replace(" ", "-")
    contest_id = f"clarity-{county_id}-{election_id}-{safe_title}"

    choices = contest.get("V") or contest.get("Choice") or []
    if not isinstance(choices, list):
        choices = []

    candidates = []
    for i, choice in enumerate(choices):
        name = (
            choice.get("CH")
            or choice.get("N")
            or choice.get("text", f"Choice {i + 1}")
        )
        votes = choice.get("TOT") or choice.get("V") or choice.get("totalVotes")
        pct = choice.get("PE") or choice.get("P")

        if isinstance(votes, str):
            cleaned = votes.replace(",", "")
            votes = int(cleaned) if cleaned.isdigit() else None
        if isinstance(pct, str):
            try:
                pct = float(pct)
            except ValueError:
                pct = None

        cand_slug = re.sub(r"[^a-z0-9]+", "-", name.lower())[:40].strip("-")
        candidates.append({
            "id": f"{contest_id}-{i}-{cand_slug}",
            "name": name,
            "party": choice.get("party"),
            "votes_received": votes,
            "vote_percentage": pct,
            "is_winner": False,
            "source": "clarity_elections",
        })

    # Mark winner as highest vote recipient
    with_votes = [c for c in candidates if c["votes_received"] and c["votes_received"] > 0]
    if with_votes:
        winner = max(with_votes, key=lambda c: c["votes_received"])
        winner["is_winner"] = True

    contest_type = "local_measure" if is_question else classify_contest_type(title)

    ballot_measure = None
    if is_question:
        yes_cand = next(
            (c for c in candidates if c["name"].lower() in ("yes", "bonds yes")),
            None,
        )
        no_cand = next(
            (c for c in candidates if c["name"].lower() in ("no", "bonds no")),
            None,
        )
        ballot_measure = {
            "id": f"clarity-{county_id}-measure-{election_id}-{safe_title}",
            "title": title,
            "description": title,
            "measure_type": "measure",
            "full_text": None,
            "full_text_url": None,
            "fiscal_impact": None,
            "arguments_for": [],
            "arguments_against": [],
            "passed": bool(yes_cand and yes_cand.get("is_winner")),
            "yes_votes": yes_cand["votes_received"] if yes_cand else None,
            "no_votes": no_cand["votes_received"] if no_cand else None,
            "yes_percentage": yes_cand["vote_percentage"] if yes_cand else None,
            "no_percentage": no_cand["vote_percentage"] if no_cand else None,
            "source": "clarity_elections",
        }

    enriched_raw = {
        **contest,
        "mapped_candidates": candidates,
        "mapped_ballot_measure": ballot_measure,
    }

    return {
        "id": contest_id,
        "title": title,
        "contest_type": contest_type,
        "district_name": county_slug.replace("_", " ").replace("-", " ").title() + " County",
        "number_elected": 0 if is_question else 1,
        "candidates": candidates,
        "ballot_measure": ballot_measure,
        "raw_data": enriched_raw,
    }


def parse_summary_contests(summary: Any) -> List[Dict[str, Any]]:
    """Extract contest dicts from Clarity summary JSON.

    The summary format varies by Clarity version. Common structures:
    - Array of groups, each with "C" (contests) array (nested-object format)
    - Direct array of contests with CT/N/text keys (nested-object format)
    - Object with "Contests" key
    - Live ENR parallel-array format: flat array where each item has C (string),
      CH (list of names), V (list of votes), PCT (list of percentages)
    """
    contests: List[Dict[str, Any]] = []

    if isinstance(summary, list):
        for item in summary:
            if isinstance(item, dict):
                if "C" in item and isinstance(item["C"], list):
                    # Grouped format: C is an array of sub-contests
                    for c in item["C"]:
                        if isinstance(c, dict):
                            contests.append(c)
                elif "C" in item and isinstance(item["C"], str) and "CH" in item:
                    # Live parallel-array format: C is contest name, CH is candidate list
                    contests.append(item)
                elif "CT" in item or "N" in item or "text" in item:
                    contests.append(item)
    elif isinstance(summary, dict):
        if "Contests" in summary and isinstance(summary["Contests"], list):
            contests = summary["Contests"]
        elif "C" in summary and isinstance(summary["C"], list):
            contests = summary["C"]

    return contests


def extract_clarity_results_to_storage(
    client: ClarityElectionsClient,
    storage: Any,
    jurisdiction_id: str,
    county_slug: str,
    state: str = "CA",
    archive_blob: Any = None,
) -> Dict[str, int]:
    """Extract election results from Clarity ENR and store them.

    Discovers available elections, fetches summary JSON for each,
    parses contests, and stores via storage backend.

    Args:
        archive_blob: Optional BlobStorage backend. When provided, the raw
            summary JSON is archived before parsing. Clarity data is ephemeral
            (purged without warning), so archiving on first fetch is critical.

    Returns:
        Dict with counts: {"elections": N, "contests": M, "candidates": C}
    """
    elections = client.discover_elections()
    if not elections:
        logger.info(f"No elections found for Clarity {county_slug}")
        return {"elections": 0, "contests": 0, "candidates": 0}

    total_elections = 0
    total_contests = 0
    total_candidates = 0

    for election_info in elections:
        eid = election_info["election_id"]
        ename = election_info.get("name", f"Election {eid}")

        summary = client.get_summary(eid)
        if not summary:
            logger.info(
                f"  Clarity {county_slug}: election {eid} "
                f"— no summary available (may be purged)",
            )
            continue

        # Archive raw JSON to blob storage before parsing (ephemeral data!)
        if archive_blob is not None:
            archive_key = (
                f"clarity-elections/{state}/{client.url_name}"
                f"/{eid}/summary.json"
            )
            try:
                raw_json = json.dumps(summary, ensure_ascii=False).encode("utf-8")
                archive_blob.upload(
                    key=archive_key,
                    data=raw_json,
                    content_type="application/json",
                    metadata={
                        "election_id": eid,
                        "county": county_slug,
                        "state": state,
                        "archived_at": datetime.utcnow().isoformat(),
                    },
                )
                logger.info(
                    f"  Clarity {county_slug}: archived {archive_key} "
                    f"({len(raw_json)} bytes)",
                )
            except Exception as e:
                # Archive failure should not block extraction
                logger.warning(
                    f"  Clarity {county_slug}: failed to archive {archive_key}: {e}",
                )

        raw_contests = parse_summary_contests(summary)
        if not raw_contests:
            logger.info(
                f"  Clarity {county_slug}: election {eid} "
                f"— no contests in summary",
            )
            continue

        # Get authoritative election name/date from settings endpoint
        election_date = None
        settings = client.get_election_settings(eid)
        if settings:
            settings_name = settings.get("ElectionName") or settings.get("EL")
            if settings_name:
                ename = settings_name
            edate_raw = settings.get("ElectionDate") or settings.get("ED")
            if edate_raw:
                election_date = _infer_election_date(edate_raw)

        # Also check summary metadata for election name
        summary_name = None
        if isinstance(summary, list) and summary:
            first = summary[0]
            if isinstance(first, dict):
                summary_name = first.get("EL") or first.get("ElectionName")
        elif isinstance(summary, dict):
            summary_name = summary.get("ElectionName") or summary.get("EL")

        # Prefer settings name > summary name > discovery name
        if not settings and summary_name:
            ename = summary_name

        election = clarity_results_to_election(
            eid, ename, county_slug, state, client.url_name,
            election_date=election_date,
        )

        stored = storage.store_elections(jurisdiction_id, [election])
        total_elections += stored

        mapped = [
            clarity_contest_to_storage(c, county_slug, eid)
            for c in raw_contests
        ]

        # Format-drift canary: warn if contests parsed but produced 0 candidates.
        # This signals an unknown JSON schema variant that slipped through.
        empty = [m for m in mapped if not m.get("candidates")]
        if empty and len(empty) == len(mapped):
            logger.warning(
                f"  Clarity {county_slug}: election {eid} — all {len(mapped)} "
                f"contests produced 0 candidates. Possible format drift. "
                f"Sample keys: {sorted(raw_contests[0].keys()) if raw_contests else '?'}",
            )

        contest_count = storage.store_election_contests(election["id"], mapped)
        total_contests += contest_count
        total_candidates += sum(len(c.get("candidates", [])) for c in mapped)

        logger.info(
            f"  Clarity {county_slug}: '{ename}' "
            f"— {len(mapped)} contests stored",
        )

    logger.info(
        f"Clarity results ({county_slug}): {total_elections} elections, "
        f"{total_contests} contests, {total_candidates} candidates "
        f"for {jurisdiction_id}",
    )

    return {
        "elections": total_elections,
        "contests": total_contests,
        "candidates": total_candidates,
    }
