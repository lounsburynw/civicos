"""
Unified Representatives API Client

Combines free data sources to provide representative lookup:
- Congress.gov API: Federal legislators (US House, Senate)
- Open States API v3: State legislators
- Local data: Manual curation (city council, mayor, school board)

This provides Ballotpedia-equivalent coverage without paid subscriptions.

Usage:
    client = RepresentativesClient("san-rafael")

    # Get all representatives for a location
    reps = client.get_representatives(lat=37.9735, lng=-122.5311)

    # Or by address (requires geocoding)
    reps = client.get_representatives_by_address("1100 4th St, San Rafael, CA 94901")
"""

import logging
import os
import requests
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from civicos_extraction.clients.base import HealthStatus, ValidationResult

logger = logging.getLogger(__name__)


@dataclass
class Representative:
    """Normalized representative data."""

    id: str
    name: str
    office: str  # "US Senator", "State Assembly Member", "City Council Member"
    level: str  # "federal", "state", "local"
    party: Optional[str] = None
    district: Optional[str] = None
    state: Optional[str] = None

    # Contact info
    phones: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)
    websites: List[str] = field(default_factory=list)

    # Additional info
    photo_url: Optional[str] = None
    term_start: Optional[str] = None
    term_end: Optional[str] = None

    source: str = "unknown"  # "congress_gov", "open_states", "local"
    raw_data: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "office": self.office,
            "level": self.level,
            "party": self.party,
            "district": self.district,
            "state": self.state,
            "phones": self.phones,
            "emails": self.emails,
            "websites": self.websites,
            "photo_url": self.photo_url,
            "term_start": self.term_start,
            "term_end": self.term_end,
            "source": self.source,
        }


class CongressGovClient:
    """
    Congress.gov API client for federal legislators.

    API docs: https://api.congress.gov/
    Rate limit: 5000 requests/hour
    """

    BASE_URL = "https://api.congress.gov/v3"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Congress.gov client.

        Args:
            api_key: API key from data.gov. Falls back to CONGRESS_GOV_API_KEY,
                     FAC_API_KEY, or DATA_GOV_API_KEY env vars (all use data.gov).
        """
        self.api_key = (
            api_key
            or os.environ.get("CONGRESS_GOV_API_KEY")
            or os.environ.get("FAC_API_KEY")  # data.gov key used by FAC client
            or os.environ.get("DATA_GOV_API_KEY")
        )
        self.session = requests.Session()
        self.last_request_time = 0.0
        self.min_request_interval = 0.1  # 10 req/sec max

    def _throttle_request(self):
        """Prevent burst requests."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Make API request with retries."""
        if not self.api_key:
            logger.warning("No Congress.gov API key configured")
            return None

        self._throttle_request()
        url = f"{self.BASE_URL}/{endpoint}"

        request_params = {"api_key": self.api_key, "format": "json"}
        if params:
            request_params.update(params)

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=request_params, timeout=30)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.warning(
                        f"Congress.gov API error: {response.status_code} - {response.text[:200]}"
                    )
                    return None

            except (requests.Timeout, requests.ConnectionError) as e:
                logger.warning(f"Request failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

        return None

    def get_members_by_state(self, state_code: str, current_only: bool = True) -> List[Representative]:
        """
        Get all Congress members for a state.

        Args:
            state_code: Two-letter state code (e.g., "CA")
            current_only: Only return current members

        Returns:
            List of Representative objects
        """
        params = {"limit": 250}
        if current_only:
            params["currentMember"] = "true"

        result = self._make_request(f"member/{state_code}", params=params)
        if not result:
            return []

        members = result.get("members", [])
        return [self._normalize_member(m) for m in members]

    def get_members_by_district(
        self,
        state_code: str,
        district: int,
        current_only: bool = True
    ) -> List[Representative]:
        """
        Get House member for a specific congressional district.

        Args:
            state_code: Two-letter state code (e.g., "CA")
            district: Congressional district number (e.g., 2)
            current_only: Only return current members

        Returns:
            List of Representative objects (typically 1 for House)
        """
        params = {"limit": 10}
        if current_only:
            params["currentMember"] = "true"

        result = self._make_request(f"member/{state_code}/{district}", params=params)
        if not result:
            return []

        members = result.get("members", [])
        return [self._normalize_member(m) for m in members]

    # ==================== Committee Hearings ====================

    def get_committee_hearings(
        self,
        congress: int = 119,
        chamber: Optional[str] = None,
        limit: int = 250,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List committee meetings/hearings for a congress.

        Uses the /committee-meeting endpoint which returns scheduled hearings,
        markups, and other committee events.

        Args:
            congress: Congress number (e.g., 119)
            chamber: Filter by "house" or "senate" (optional)
            limit: Max results per page
            offset: Pagination offset

        Returns:
            List of committee meeting summary dicts with eventId, chamber, url
        """
        if chamber:
            endpoint = f"committee-meeting/{congress}/{chamber.lower()}"
        else:
            endpoint = f"committee-meeting/{congress}"

        result = self._make_request(endpoint, params={"limit": limit, "offset": offset})
        if not result:
            return []
        return result.get("committeeMeetings", [])

    def get_committee_hearing_detail(
        self,
        congress: int,
        chamber: str,
        event_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get detail for a specific committee meeting/hearing.

        Returns title, date, committees, location, meetingStatus, type,
        and meetingDocuments (related bills, hearing notices).

        Args:
            congress: Congress number
            chamber: "house" or "senate"
            event_id: Event ID from the list endpoint

        Returns:
            Meeting detail dict or None
        """
        result = self._make_request(
            f"committee-meeting/{congress}/{chamber.lower()}/{event_id}"
        )
        if not result:
            return None
        return result.get("committeeMeeting")

    # ==================== Vote Retrieval ====================

    def get_house_roll_calls(
        self,
        congress: int = 119,
        session: int = 1,
        limit: int = 250,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List House roll call votes for a congress/session.

        Args:
            congress: Congress number (e.g., 119)
            session: Session number (1 or 2)
            limit: Max results per page
            offset: Pagination offset

        Returns:
            List of roll call vote summary dicts
        """
        result = self._make_request(
            f"house-vote/{congress}/{session}",
            params={"limit": limit, "offset": offset},
        )
        if not result:
            return []
        return result.get("houseRollCallVotes", [])

    def get_house_vote_detail(
        self,
        congress: int,
        session: int,
        roll_call: int,
    ) -> Optional[Dict[str, Any]]:
        """
        Get detail for a specific House roll call vote (summary only, no member votes).

        Args:
            congress: Congress number
            session: Session number
            roll_call: Roll call number

        Returns:
            Vote detail dict or None
        """
        result = self._make_request(f"house-vote/{congress}/{session}/{roll_call}")
        if not result:
            return None
        return result.get("houseRollCallVote")

    def get_house_member_votes(
        self,
        congress: int,
        session: int,
        roll_call: int,
        bioguide_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get individual member vote positions from House Clerk XML.

        The Congress.gov API doesn't expose per-member votes, so we parse
        the authoritative House Clerk XML source directly.

        Args:
            congress: Congress number (e.g., 119)
            session: Session number (1 or 2)
            roll_call: Roll call number
            bioguide_ids: If provided, only return votes for these members

        Returns:
            List of dicts with keys: bioguide_id, name, party, state, vote
        """
        # House Clerk XML: https://clerk.house.gov/evs/{year}/roll{number}.xml
        # We need to map congress+session to year. Congress 119 session 1 = 2025.
        year = 2013 + (congress - 113) * 2 + (session - 1)
        url = f"https://clerk.house.gov/evs/{year}/roll{roll_call}.xml"

        self._throttle_request()
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code != 200:
                logger.warning(f"House Clerk XML {response.status_code}: {url}")
                return []
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.warning(f"House Clerk XML request failed: {e}")
            return []

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            logger.warning(f"Failed to parse House Clerk XML: {e}")
            return []

        # Parse vote metadata
        metadata = root.find("vote-metadata")
        vote_question = ""
        vote_desc = ""
        legis_num = ""
        vote_result = ""
        if metadata is not None:
            vq = metadata.find("vote-question")
            vote_question = vq.text if vq is not None and vq.text else ""
            vd = metadata.find("vote-desc")
            vote_desc = vd.text if vd is not None and vd.text else ""
            ln = metadata.find("legis-num")
            legis_num = ln.text if ln is not None and ln.text else ""
            vr = metadata.find("vote-result")
            vote_result = vr.text if vr is not None and vr.text else ""

        bioguide_set = set(bioguide_ids) if bioguide_ids else None
        votes = []

        vote_data = root.find("vote-data")
        if vote_data is None:
            return []

        for recorded_vote in vote_data.findall("recorded-vote"):
            legislator = recorded_vote.find("legislator")
            vote_el = recorded_vote.find("vote")
            if legislator is None or vote_el is None:
                continue

            bioguide_id = legislator.get("name-id", "")
            if bioguide_set and bioguide_id not in bioguide_set:
                continue

            # Normalize vote positions: House uses both Yea/Nay and Aye/No
            raw_vote = vote_el.text or ""
            vote_normalized = {
                "Yea": "Yea", "Aye": "Yea",
                "Nay": "Nay", "No": "Nay",
                "Not Voting": "Not Voting",
                "Present": "Present",
            }.get(raw_vote, raw_vote)

            votes.append({
                "bioguide_id": bioguide_id,
                "name": legislator.get("unaccented-name", legislator.text or ""),
                "party": legislator.get("party", ""),
                "state": legislator.get("state", ""),
                "vote": vote_normalized,
                "vote_question": vote_question,
                "vote_description": vote_desc,
                "legislation_number": legis_num,
                "vote_result": vote_result,
            })

        return votes

    def get_senate_member_votes(
        self,
        congress: int,
        session: int,
        vote_number: int,
        bioguide_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get individual senator vote positions from Senate XML.

        Args:
            congress: Congress number (e.g., 119)
            session: Session number (1 or 2)
            vote_number: Senate vote number
            bioguide_ids: If provided, only return votes for these senators

        Returns:
            List of dicts with keys: bioguide_id, name, party, state, vote
        """
        # Senate XML: https://www.senate.gov/legislative/LIS/roll_call_votes/
        #   vote{congress}{session}/vote_{congress}_{session}_{vote_number:05d}.xml
        url = (
            f"https://www.senate.gov/legislative/LIS/roll_call_votes/"
            f"vote{congress}{session}/"
            f"vote_{congress}_{session}_{vote_number:05d}.xml"
        )

        self._throttle_request()
        try:
            response = self.session.get(url, timeout=30)
            if response.status_code != 200:
                logger.warning(f"Senate XML {response.status_code}: {url}")
                return []
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.warning(f"Senate XML request failed: {e}")
            return []

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as e:
            logger.warning(f"Failed to parse Senate XML: {e}")
            return []

        # Parse vote metadata
        vote_question = ""
        vote_title = ""
        vote_result = ""
        vote_date = ""
        doc_number = ""
        vq = root.find("question")
        if vq is not None and vq.text:
            vote_question = vq.text
        vt = root.find("vote_title")
        if vt is not None and vt.text:
            vote_title = vt.text
        vr = root.find("vote_result")
        if vr is not None and vr.text:
            vote_result = vr.text
        vd = root.find("vote_date")
        if vd is not None and vd.text:
            # Senate date format: "January 9, 2025,  02:54 PM" → parse to YYYY-MM-DD
            try:
                raw_date = vd.text.split(",")[0] + "," + vd.text.split(",")[1]
                vote_date = datetime.strptime(raw_date.strip(), "%B %d, %Y").strftime("%Y-%m-%d")
            except (ValueError, IndexError):
                vote_date = ""
        doc = root.find("document")
        if doc is not None:
            dn = doc.find("document_name")
            if dn is not None and dn.text:
                doc_number = dn.text

        # Senate XML uses lis_member_id, not bioguide_id directly
        # We'll need to map via name for now (bioguide_ids filter uses name matching)
        bioguide_set = set(bioguide_ids) if bioguide_ids else None
        votes = []

        members = root.find("members")
        if members is None:
            return []

        for member in members.findall("member"):
            last_name_el = member.find("last_name")
            first_name_el = member.find("first_name")
            party_el = member.find("party")
            state_el = member.find("state")
            vote_el = member.find("vote_cast")
            lis_id_el = member.find("lis_member_id")

            if vote_el is None:
                continue

            last_name = last_name_el.text if last_name_el is not None else ""
            first_name = first_name_el.text if first_name_el is not None else ""
            name = f"{first_name} {last_name}".strip() or last_name
            lis_id = lis_id_el.text if lis_id_el is not None else ""

            # Map Senate vote values to consistent format
            vote_text = vote_el.text or ""
            vote_map = {"Yea": "Yea", "Nay": "Nay", "Not Voting": "Not Voting", "Present": "Present"}
            vote_text = vote_map.get(vote_text, vote_text)

            # We store lis_member_id as a placeholder — the ingest function
            # maps to bioguide_id via elected_officials table
            votes.append({
                "lis_member_id": lis_id,
                "bioguide_id": "",  # Filled by ingest function via elected_officials lookup
                "name": name,
                "party": party_el.text if party_el is not None else "",
                "state": state_el.text if state_el is not None else "",
                "vote": vote_text,
                "vote_date": vote_date,
                "vote_question": vote_question,
                "vote_description": vote_title,
                "legislation_number": doc_number,
                "vote_result": vote_result,
            })

        # Filter by bioguide_ids if provided (after mapping)
        if bioguide_set:
            votes = [v for v in votes if v["bioguide_id"] in bioguide_set]

        return votes

    def _normalize_member(self, raw: Dict[str, Any]) -> Representative:
        """Normalize Congress.gov member to Representative."""
        # Determine office type from terms
        terms = raw.get("terms", {}).get("item", [])
        current_term = terms[-1] if terms else {}
        chamber = current_term.get("chamber", "")

        if chamber == "Senate":
            office = "US Senator"
        elif chamber == "House of Representatives":
            office = "US Representative"
        else:
            office = "Member of Congress"

        # Get district info
        district = current_term.get("district")
        if district:
            district = str(district)

        # Get depiction (photo)
        depiction = raw.get("depiction", {})
        photo_url = depiction.get("imageUrl")

        return Representative(
            id=f"congress-{raw.get('bioguideId', 'unknown')}",
            name=raw.get("name", "Unknown"),
            office=office,
            level="federal",
            party=raw.get("partyName"),
            district=district,
            state=raw.get("state"),
            photo_url=photo_url,
            term_start=current_term.get("startYear"),
            term_end=current_term.get("endYear"),
            source="congress_gov",
            raw_data=raw,
        )


class OpenStatesClient:
    """
    Open States API v3 client for state legislators.

    API docs: https://docs.openstates.org/api-v3/
    Key signup: https://open.pluralpolicy.com/accounts/profile/
    """

    BASE_URL = "https://v3.openstates.org"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Open States client.

        Args:
            api_key: API key from pluralpolicy.com. Falls back to OPEN_STATES_API_KEY
                     or OPENSTATES_API_KEY env vars.
        """
        self.api_key = (
            api_key
            or os.environ.get("OPEN_STATES_API_KEY")
            or os.environ.get("OPENSTATES_API_KEY")
        )
        self.session = requests.Session()
        self.last_request_time = 0.0
        self.min_request_interval = 0.2  # Conservative rate

    def _throttle_request(self):
        """Prevent burst requests."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Make API request with retries."""
        if not self.api_key:
            logger.warning("No Open States API key configured")
            return None

        self._throttle_request()
        url = f"{self.BASE_URL}/{endpoint}"

        headers = {"X-API-KEY": self.api_key}
        request_params = params or {}

        for attempt in range(retries):
            try:
                response = self.session.get(
                    url,
                    params=request_params,
                    headers=headers,
                    timeout=30
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.warning(
                        f"Open States API error: {response.status_code} - {response.text[:200]}"
                    )
                    return None

            except (requests.Timeout, requests.ConnectionError) as e:
                logger.warning(f"Request failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

        return None

    def get_legislators_by_geo(self, lat: float, lng: float) -> List[Representative]:
        """
        Get state legislators for a geographic location.

        Args:
            lat: Latitude
            lng: Longitude

        Returns:
            List of Representative objects
        """
        result = self._make_request("people.geo", params={"lat": lat, "lng": lng})
        if not result:
            return []

        legislators = result.get("results", [])
        return [self._normalize_legislator(leg) for leg in legislators]

    def get_legislators_by_state(self, state: str) -> List[Representative]:
        """
        Get all current state legislators for a state.

        Args:
            state: State jurisdiction (e.g., "ca" for California)

        Returns:
            List of Representative objects
        """
        result = self._make_request(
            "people",
            params={"jurisdiction": state, "current": "true", "per_page": 200}
        )
        if not result:
            return []

        legislators = result.get("results", [])
        return [self._normalize_legislator(leg) for leg in legislators]

    def _normalize_legislator(self, raw: Dict[str, Any]) -> Representative:
        """Normalize Open States person to Representative."""
        # Get current role and jurisdiction
        roles = raw.get("current_role", {})
        jurisdiction = raw.get("jurisdiction", {})
        jurisdiction_classification = jurisdiction.get("classification", "state")

        # Determine level (federal vs state)
        is_federal = jurisdiction_classification == "country"
        level = "federal" if is_federal else "state"

        # Determine office based on level and org_classification
        org_classification = roles.get("org_classification", "")
        title = roles.get("title", "")

        if is_federal:
            if org_classification == "upper" or title == "Senator":
                office = "US Senator"
            elif org_classification == "lower" or title == "Representative":
                office = "US Representative"
            else:
                office = "Member of Congress"
        else:
            if org_classification == "upper":
                office = "State Senator"
            elif org_classification == "lower":
                office = "State Assembly Member"
            else:
                office = title or "State Legislator"

        # Extract contact info from various sources
        emails = []
        phones = []
        websites = []

        for link in raw.get("links", []):
            url = link.get("url", "")
            if url:
                websites.append(url)

        for office_info in raw.get("offices", []):
            if email := office_info.get("email"):
                emails.append(email)
            if phone := office_info.get("voice"):
                phones.append(phone)

        # Extract state from division_id (e.g., "ocd-division/country:us/state:ca/...")
        division_id = roles.get("division_id", "")
        state = ""
        if "/state:" in division_id:
            state_part = division_id.split("/state:")[1]
            state = state_part.split("/")[0].upper()

        return Representative(
            id=f"openstates-{raw.get('id', 'unknown')}",
            name=raw.get("name", "Unknown"),
            office=office,
            level=level,
            party=raw.get("party"),
            district=roles.get("district"),
            state=state,
            emails=emails,
            phones=phones,
            websites=websites,
            photo_url=raw.get("image"),
            source="open_states",
            raw_data=raw,
        )


class LegiScanLegislatorsClient:
    """
    LegiScan API client for state legislators.

    NOTE: This is distinct from LegiScanClient in legiscan.py which handles bill discovery.
    This client specifically handles legislator/people data via getSessionPeople endpoint.

    API docs: https://legiscan.com/legiscan
    Key signup: https://legiscan.com/user/register
    Free tier: 30,000 queries/month

    Primary source for state legislator data, replacing Open States
    which was acquired by PE-backed SAI360 in Dec 2025.
    """

    BASE_URL = "https://api.legiscan.com/"

    # Cache session data to avoid repeated lookups
    _session_cache: Dict[str, Dict[str, Any]] = {}

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize LegiScan client.

        Args:
            api_key: API key from legiscan.com. Falls back to LEGISCAN_API_KEY env var.
        """
        self.api_key = api_key or os.environ.get("LEGISCAN_API_KEY")
        self.session = requests.Session()
        self.last_request_time = 0.0
        self.min_request_interval = 0.2  # Conservative rate

    def _throttle_request(self):
        """Prevent burst requests."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def _make_request(
        self,
        operation: str,
        params: Optional[Dict[str, Any]] = None,
        retries: int = 3,
    ) -> Optional[Dict[str, Any]]:
        """Make API request with retries."""
        if not self.api_key:
            logger.warning("No LegiScan API key configured")
            return None

        self._throttle_request()

        request_params = {"key": self.api_key, "op": operation}
        if params:
            request_params.update(params)

        for attempt in range(retries):
            try:
                response = self.session.get(
                    self.BASE_URL,
                    params=request_params,
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "OK":
                        return data
                    else:
                        logger.warning(
                            f"LegiScan API error: {data.get('alert', {}).get('message', 'Unknown error')}"
                        )
                        return None
                elif response.status_code == 429:
                    wait_time = 2 ** attempt
                    logger.warning(f"Rate limited, waiting {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.warning(
                        f"LegiScan API error: {response.status_code} - {response.text[:200]}"
                    )
                    return None

            except (requests.Timeout, requests.ConnectionError) as e:
                logger.warning(f"Request failed: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)

        return None

    def get_current_session(self, state: str) -> Optional[Dict[str, Any]]:
        """
        Get the current legislative session for a state.

        Args:
            state: Two-letter state code (e.g., "CA")

        Returns:
            Session dict with session_id, session_title, year_start, etc.
        """
        # Check cache first
        cache_key = f"session_{state.upper()}"
        if cache_key in self._session_cache:
            return self._session_cache[cache_key]

        result = self._make_request("getSessionList", {"state": state.upper()})
        if not result:
            return None

        sessions = result.get("sessions", [])
        if not sessions:
            return None

        # First session is most recent
        current_session = sessions[0]
        self._session_cache[cache_key] = current_session
        return current_session

    def get_legislators_by_state(self, state: str) -> List[Representative]:
        """
        Get all current state legislators for a state.

        Args:
            state: Two-letter state code (e.g., "CA")

        Returns:
            List of Representative objects
        """
        session = self.get_current_session(state)
        if not session:
            logger.warning(f"No session found for state {state}")
            return []

        session_id = session.get("session_id")
        result = self._make_request("getSessionPeople", {"id": session_id})
        if not result:
            return []

        people = result.get("sessionpeople", {}).get("people", [])
        return [self._normalize_legislator(p, state.upper()) for p in people]

    def get_legislator_by_district(
        self,
        state: str,
        chamber: str,
        district: str,
    ) -> Optional[Representative]:
        """
        Get legislator for a specific district.

        Args:
            state: Two-letter state code (e.g., "CA")
            chamber: "upper" (Senate) or "lower" (Assembly)
            district: District number (e.g., "14")

        Returns:
            Representative or None if not found
        """
        legislators = self.get_legislators_by_state(state)

        # LegiScan uses prefixes like "SD-014" for Senate, "AD-014" for Assembly
        prefix = "SD-" if chamber == "upper" else "AD-"
        target_district = f"{prefix}{district.zfill(3)}"

        for leg in legislators:
            if leg.raw_data and leg.raw_data.get("district") == target_district:
                return leg

        return None

    def _normalize_legislator(self, raw: Dict[str, Any], state: str) -> Representative:
        """Normalize LegiScan person to Representative."""
        role = raw.get("role", "")

        # Determine office from role
        if role == "Sen":
            office = "State Senator"
            level = "state"
        elif role == "Rep" or role == "Asm":
            office = "State Assembly Member"
            level = "state"
        else:
            office = role or "State Legislator"
            level = "state"

        # Parse district (e.g., "SD-014" -> "14")
        raw_district = raw.get("district", "")
        district = raw_district.split("-")[-1].lstrip("0") if "-" in raw_district else raw_district

        # Map party abbreviation
        party_map = {"D": "Democratic", "R": "Republican", "I": "Independent", "L": "Libertarian"}
        party = party_map.get(raw.get("party", ""), raw.get("party"))

        return Representative(
            id=f"legiscan-{raw.get('people_id', 'unknown')}",
            name=raw.get("name", "Unknown"),
            office=office,
            level=level,
            party=party,
            district=district,
            state=state,
            # LegiScan doesn't include contact info in getSessionPeople
            # Would need separate getPerson calls for each
            emails=[],
            phones=[],
            websites=[],
            source="legiscan",
            raw_data=raw,
        )


@dataclass
class LocalRepresentative:
    """
    Local official data (manually curated).

    For cities like San Rafael, this covers:
    - Mayor
    - City Council members
    - County Supervisors
    - School Board members
    """

    id: str
    name: str
    office: str
    party: Optional[str] = None
    district: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    photo_url: Optional[str] = None
    term_end: Optional[str] = None


# San Rafael local officials (manually curated)
# Source: https://www.cityofsanrafael.org/city-council/
# Last updated: 2026-01-03
SAN_RAFAEL_LOCAL_OFFICIALS: List[LocalRepresentative] = [
    LocalRepresentative(
        id="local-sr-mayor",
        name="Kate Colin",
        office="Mayor",
        email="kate.colin@cityofsanrafael.org",
        website="https://www.cityofsanrafael.org/city-council/",
    ),
    LocalRepresentative(
        id="local-sr-vice-mayor",
        name="Maribeth Bushey",
        office="Vice Mayor",
        email="maribeth.bushey@cityofsanrafael.org",
        website="https://www.cityofsanrafael.org/city-council/",
    ),
    LocalRepresentative(
        id="local-sr-council-1",
        name="Rachel Kertz",
        office="City Council Member",
        email="rachel.kertz@cityofsanrafael.org",
        website="https://www.cityofsanrafael.org/city-council/",
    ),
    LocalRepresentative(
        id="local-sr-council-2",
        name="Eli Hill",
        office="City Council Member",
        email="eli.hill@cityofsanrafael.org",
        website="https://www.cityofsanrafael.org/city-council/",
    ),
    LocalRepresentative(
        id="local-sr-council-3",
        name="Cynthia Silveri",
        office="City Council Member",
        email="cynthia.silveri@cityofsanrafael.org",
        website="https://www.cityofsanrafael.org/city-council/",
    ),
]

# Marin County Supervisors (District 1 covers San Rafael)
# Source: https://www.marincounty.org/depts/bs/board-of-supervisors
MARIN_COUNTY_SUPERVISORS: List[LocalRepresentative] = [
    LocalRepresentative(
        id="local-marin-sup-1",
        name="Mary Sackett",
        office="County Supervisor",
        district="1",  # San Rafael, Larkspur, Corte Madera
        email="msackett@marincounty.org",
        website="https://www.marincounty.org/depts/bs/board-of-supervisors/district-1",
    ),
]


class RepresentativesClient:
    """
    Unified client for representative lookup across all levels of government.

    Combines:
    - Congress.gov API (federal)
    - Open States API (state)
    - Local data (manual curation)

    Usage:
        client = RepresentativesClient("san-rafael")
        reps = client.get_representatives(lat=37.9735, lng=-122.5311)
    """

    # San Rafael geographic info
    SAN_RAFAEL_LAT = 37.9735
    SAN_RAFAEL_LNG = -122.5311
    SAN_RAFAEL_STATE = "CA"
    SAN_RAFAEL_CONGRESSIONAL_DISTRICT = 2  # CA-02 (Jared Huffman)

    def __init__(
        self,
        jurisdiction_id: str,
        congress_api_key: Optional[str] = None,
        legiscan_api_key: Optional[str] = None,
        open_states_api_key: Optional[str] = None,
    ):
        """
        Initialize unified representatives client.

        Args:
            jurisdiction_id: Civic jurisdiction ID (e.g., "san-rafael")
            congress_api_key: Congress.gov API key (optional, uses env var)
            legiscan_api_key: LegiScan API key (optional, uses env var) - PRIMARY for state
            open_states_api_key: Open States API key (optional, uses env var) - DEPRECATED fallback
        """
        self.jurisdiction_id = jurisdiction_id
        self.congress_client = CongressGovClient(api_key=congress_api_key)
        self.legiscan_client = LegiScanLegislatorsClient(api_key=legiscan_api_key)
        self.open_states_client = OpenStatesClient(api_key=open_states_api_key)

    @property
    def platform_name(self) -> str:
        return "representatives"

    @property
    def source_id(self) -> str:
        return f"representatives-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "representatives"

    def health(self) -> HealthStatus:
        """Check health of all representative data sources."""
        start_time = time.time()
        errors: List[str] = []
        is_available = False
        available_count = 0
        metadata: Dict[str, Any] = {}

        # Check Congress.gov (federal)
        if self.congress_client.api_key:
            try:
                members = self.congress_client.get_members_by_state("CA", current_only=True)
                if members:
                    metadata["congress_gov"] = "available"
                    metadata["federal_count"] = len(members)
                    available_count += len(members)
                    is_available = True
                else:
                    metadata["congress_gov"] = "no_data"
            except Exception as e:
                errors.append(f"Congress.gov error: {e}")
                metadata["congress_gov"] = "error"
        else:
            metadata["congress_gov"] = "no_api_key"
            errors.append("No Congress.gov API key configured (CONGRESS_GOV_API_KEY or FAC_API_KEY)")

        # Check LegiScan (primary for state)
        if self.legiscan_client.api_key:
            try:
                legislators = self.legiscan_client.get_legislators_by_state("CA")
                if legislators:
                    metadata["legiscan"] = "available"
                    metadata["state_count"] = len(legislators)
                    available_count += len(legislators)
                    is_available = True
                else:
                    metadata["legiscan"] = "no_data"
            except Exception as e:
                errors.append(f"LegiScan error: {e}")
                metadata["legiscan"] = "error"
        else:
            metadata["legiscan"] = "no_api_key"
            errors.append("No LegiScan API key configured (LEGISCAN_API_KEY)")

        # Check Open States (deprecated fallback)
        if self.open_states_client.api_key:
            try:
                legislators = self.open_states_client.get_legislators_by_geo(
                    self.SAN_RAFAEL_LAT, self.SAN_RAFAEL_LNG
                )
                if legislators:
                    metadata["open_states"] = "available (deprecated)"
                else:
                    metadata["open_states"] = "no_data"
            except Exception as e:
                metadata["open_states"] = f"error: {e}"
        else:
            metadata["open_states"] = "no_api_key (OK - deprecated)"

        # Local data is always available
        local_count = len(SAN_RAFAEL_LOCAL_OFFICIALS) + len(MARIN_COUNTY_SUPERVISORS)
        metadata["local"] = "available"
        metadata["local_count"] = local_count
        available_count += local_count
        is_available = True

        check_duration_ms = (time.time() - start_time) * 1000

        return HealthStatus(
            source_id=self.source_id,
            source_type=self.source_type,
            jurisdiction_id=self.jurisdiction_id,
            is_available=is_available,
            available_count=available_count,
            last_checked=datetime.utcnow(),
            check_duration_ms=round(check_duration_ms, 2),
            errors=errors,
            last_successful=datetime.utcnow() if is_available else None,
            metadata=metadata,
        )

    def validate(self) -> ValidationResult:
        """Validate representative data source configuration."""
        start_time = time.time()
        errors: List[str] = []
        warnings: List[str] = []
        config_valid = True
        api_reachable = False

        # Check API keys
        if not self.congress_client.api_key:
            warnings.append(
                "No Congress.gov API key (CONGRESS_GOV_API_KEY or FAC_API_KEY) - "
                "federal representatives unavailable. Get a free key at https://api.data.gov/signup/"
            )

        if not self.legiscan_client.api_key:
            warnings.append(
                "No LegiScan API key (LEGISCAN_API_KEY) - "
                "state legislators unavailable. Get a free key at https://legiscan.com/user/register"
            )

        # Open States is deprecated but can serve as fallback
        if not self.legiscan_client.api_key and not self.open_states_client.api_key:
            warnings.append(
                "No state legislator API keys configured. "
                "LegiScan (primary) or Open States (deprecated fallback) needed."
            )

        # At minimum, local data is always available
        api_reachable = True

        check_duration_ms = (time.time() - start_time) * 1000

        return ValidationResult(
            is_valid=len(errors) == 0,
            config_valid=config_valid,
            api_reachable=api_reachable,
            errors=errors,
            warnings=warnings,
            check_duration_ms=round(check_duration_ms, 2),
        )

    def get_representatives(
        self,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
        include_federal: bool = True,
        include_state: bool = True,
        include_local: bool = True,
    ) -> List[Representative]:
        """
        Get all representatives for a location.

        Args:
            lat: Latitude (defaults to San Rafael)
            lng: Longitude (defaults to San Rafael)
            include_federal: Include US Congress members
            include_state: Include state legislators
            include_local: Include local officials

        Returns:
            List of Representative objects from all levels

        Data Sources:
            - Federal: Congress.gov API (stable government source)
            - State: LegiScan (primary), Open States (deprecated fallback)
            - Local: Curated data
        """
        lat = lat or self.SAN_RAFAEL_LAT
        lng = lng or self.SAN_RAFAEL_LNG

        representatives: List[Representative] = []

        # Federal representatives from Congress.gov (stable government API)
        if include_federal:
            # Get senators for the state
            senators = self.congress_client.get_members_by_state(
                self.SAN_RAFAEL_STATE, current_only=True
            )
            # Filter to just senators (not all members)
            senators = [s for s in senators if "Senator" in s.office]
            representatives.extend(senators)

            # Get House rep for the district
            house_reps = self.congress_client.get_members_by_district(
                self.SAN_RAFAEL_STATE,
                self.SAN_RAFAEL_CONGRESSIONAL_DISTRICT,
                current_only=True,
            )
            representatives.extend(house_reps)

        # State legislators - LegiScan primary, Open States fallback
        if include_state:
            state_legislators = []

            # Try LegiScan first (primary source)
            if self.legiscan_client.api_key:
                state_legislators = self.legiscan_client.get_legislators_by_state(
                    self.SAN_RAFAEL_STATE
                )
                # Filter to just the legislators for San Rafael's districts
                # CA Assembly District 12, CA Senate District 2
                # For now, return all CA legislators (152) - filtering by geo would need
                # district boundary data which LegiScan doesn't provide
                if state_legislators:
                    logger.debug(f"Got {len(state_legislators)} state legislators from LegiScan")

            # Fallback to Open States if LegiScan failed (deprecated - PE risk)
            if not state_legislators and self.open_states_client.api_key:
                logger.warning(
                    "LegiScan unavailable, falling back to Open States (deprecated)"
                )
                all_legislators = self.open_states_client.get_legislators_by_geo(lat, lng)
                state_legislators = [leg for leg in all_legislators if leg.level == "state"]

            representatives.extend(state_legislators)

        # Local representatives (always from curated data)
        if include_local:
            for local in SAN_RAFAEL_LOCAL_OFFICIALS:
                representatives.append(Representative(
                    id=local.id,
                    name=local.name,
                    office=local.office,
                    level="local",
                    party=local.party,
                    district=local.district,
                    emails=[local.email] if local.email else [],
                    phones=[local.phone] if local.phone else [],
                    websites=[local.website] if local.website else [],
                    photo_url=local.photo_url,
                    term_end=local.term_end,
                    source="local",
                ))

            for supervisor in MARIN_COUNTY_SUPERVISORS:
                representatives.append(Representative(
                    id=supervisor.id,
                    name=supervisor.name,
                    office=supervisor.office,
                    level="local",
                    district=supervisor.district,
                    emails=[supervisor.email] if supervisor.email else [],
                    websites=[supervisor.website] if supervisor.website else [],
                    source="local",
                ))

        return representatives

    def get_federal_representatives(self) -> List[Representative]:
        """Get only federal representatives (senators + house rep)."""
        return self.get_representatives(
            include_federal=True,
            include_state=False,
            include_local=False,
        )

    def get_state_representatives(
        self,
        lat: Optional[float] = None,
        lng: Optional[float] = None,
    ) -> List[Representative]:
        """Get only state legislators."""
        return self.get_representatives(
            lat=lat,
            lng=lng,
            include_federal=False,
            include_state=True,
            include_local=False,
        )

    def get_local_representatives(self) -> List[Representative]:
        """Get only local officials."""
        return self.get_representatives(
            include_federal=False,
            include_state=False,
            include_local=True,
        )


def create_san_rafael_representatives_client(
    congress_api_key: Optional[str] = None,
    legiscan_api_key: Optional[str] = None,
    open_states_api_key: Optional[str] = None,
) -> RepresentativesClient:
    """
    Create representatives client configured for City of San Rafael.

    Args:
        congress_api_key: Congress.gov API key (optional, uses env var)
        legiscan_api_key: LegiScan API key (optional, uses env var) - PRIMARY for state
        open_states_api_key: Open States API key (optional, uses env var) - DEPRECATED

    Returns:
        Configured RepresentativesClient
    """
    return RepresentativesClient(
        jurisdiction_id="san-rafael",
        congress_api_key=congress_api_key,
        legiscan_api_key=legiscan_api_key,
        open_states_api_key=open_states_api_key,
    )


# ==================== Storage Mappers ====================

try:
    from typing import Protocol, runtime_checkable
except ImportError:
    from typing_extensions import Protocol, runtime_checkable


@runtime_checkable
class ElectedOfficialStorageProtocol(Protocol):
    """
    Protocol for storage backends that support elected official operations.

    This is a subset of StorageBackend defined locally to avoid circular imports.
    The civic.storage.StorageBackend implements this protocol.
    """

    def store_elected_officials(
        self,
        jurisdiction_id: str,
        officials: List[Dict[str, Any]],
        as_of: Optional[datetime] = None,
    ) -> int:
        """Store elected officials with temporal versioning."""
        ...


def _generate_name_variations(name: str, office: str) -> List[str]:
    """
    Generate name variations for matching in roll call votes.

    Args:
        name: Full name (e.g., "Jane Smith")
        office: Office held (e.g., "City Council Member")

    Returns:
        List of name variations for fuzzy matching
    """
    variations = [name]
    parts = name.split()

    if len(parts) >= 2:
        # Last name only
        last_name = parts[-1]
        variations.append(last_name)

        # First initial + last name (e.g., "J. Smith")
        first_initial = parts[0][0] + "."
        variations.append(f"{first_initial} {last_name}")

        # Title + last name variations
        office_lower = office.lower()
        if "council" in office_lower:
            variations.append(f"Councilmember {last_name}")
            variations.append(f"Council Member {last_name}")
        if "mayor" in office_lower:
            variations.append(f"Mayor {last_name}")
        if "supervisor" in office_lower:
            variations.append(f"Supervisor {last_name}")
        if "senator" in office_lower:
            variations.append(f"Senator {last_name}")
        if "representative" in office_lower or "assembly" in office_lower:
            variations.append(f"Representative {last_name}")

    return variations


def representative_to_elected_official(
    representative: Representative,
    jurisdiction_id: str,
) -> Dict[str, Any]:
    """
    Map Representative (from RepresentativesClient) to storage format.

    Args:
        representative: Representative object with all details
        jurisdiction_id: Target jurisdiction (e.g., "san-rafael")

    Returns:
        Dict ready for StorageBackend.store_elected_officials()
    """
    # Parse term dates if available
    term_start = None
    if representative.term_start:
        try:
            # Handle both ISO format and year-only
            if len(representative.term_start) == 4:
                term_start = f"{representative.term_start}-01-01"
            else:
                term_start = representative.term_start
        except (ValueError, TypeError):
            pass

    term_end = None
    if representative.term_end:
        try:
            if len(representative.term_end) == 4:
                term_end = f"{representative.term_end}-12-31"
            else:
                term_end = representative.term_end
        except (ValueError, TypeError):
            pass

    # Use current date if no term_start (for active officials)
    if not term_start:
        term_start = datetime.now().strftime("%Y-%m-%d")

    # Generate name variations for roll call matching
    name_variations = _generate_name_variations(
        representative.name,
        representative.office,
    )

    return {
        "id": representative.id,
        "name": representative.name,
        "seat": representative.office,
        "term_start": term_start,
        "term_end": term_end,
        "name_variations": name_variations,
        "candidate_id": None,  # Linked later after elections sync
    }


def extract_elected_officials_to_storage(
    client: RepresentativesClient,
    storage: ElectedOfficialStorageProtocol,
    jurisdiction_id: str,
    include_federal: bool = True,
    include_state: bool = True,
    include_local: bool = True,
) -> int:
    """
    Extract officials from RepresentativesClient and store them.

    Args:
        client: RepresentativesClient instance
        storage: StorageBackend instance with store_elected_officials method
        jurisdiction_id: Target jurisdiction (e.g., "san-rafael")
        include_federal: Include federal representatives
        include_state: Include state representatives
        include_local: Include local officials

    Returns:
        Number of officials stored
    """
    representatives = client.get_representatives(
        include_federal=include_federal,
        include_state=include_state,
        include_local=include_local,
    )

    if not representatives:
        logger.info(f"No representatives found for {jurisdiction_id}")
        return 0

    officials = [
        representative_to_elected_official(rep, jurisdiction_id)
        for rep in representatives
    ]

    count = storage.store_elected_officials(jurisdiction_id, officials)
    logger.info(
        f"Stored {count} elected officials for {jurisdiction_id} "
        f"(federal={include_federal}, state={include_state}, local={include_local})"
    )
    return count
