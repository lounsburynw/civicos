"""
California Legislature bulk data client.

Fetches bill data from the official bulk downloads at
https://downloads.leginfo.legislature.ca.gov/

Data is provided as tab-delimited .dat files inside ZIP archives.
The same format used by modal_cacode.py for codified law sections.

Key tables parsed:
- BILL_TBL: Master bill records (ID, status, subject, session)
- BILL_VERSION_TBL: Bill text versions with subjects and flags
- BILL_HISTORY_TBL: Complete action history with dates
- BILL_SUMMARY_VOTE_TBL: Vote tallies (ayes/noes/abstain)
- BILL_DETAIL_VOTE_TBL: Individual legislator roll call votes
- COMMITTEE_HEARING_TBL: Committee hearing records
- COMMITTEE_AGENDA_TBL: Committee agenda items (which bills, when)
- DAILY_FILE_TBL: Floor session agendas
- LOCATION_CODE_TBL: Committee/location name lookup

Data source docs: capublic.sql schema in pubinfo_load.zip
"""

import io
import logging
import os
import re
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


# Measure type labels
MEASURE_TYPES = {
    "AB": "Assembly Bill",
    "SB": "Senate Bill",
    "ACA": "Assembly Constitutional Amendment",
    "SCA": "Senate Constitutional Amendment",
    "ACR": "Assembly Concurrent Resolution",
    "SCR": "Senate Concurrent Resolution",
    "AJR": "Assembly Joint Resolution",
    "SJR": "Senate Joint Resolution",
    "AR": "Assembly Resolution",
    "SR": "Senate Resolution",
}

# Status codes from measure_state field
STATUS_MAP = {
    "Introduced": "Introduced",
    "Engrossed": "Passed House",
    "Enrolled": "Enrolled",
    "Chaptered": "Chaptered",
    "Vetoed": "Vetoed",
}


@dataclass
class CABill:
    """A California Legislature bill."""
    bill_id: str          # e.g., "202520260AB123"
    session_year: str     # e.g., "2025-2026"
    measure_type: str     # e.g., "AB", "SB"
    measure_num: int
    status: str           # current measure_state
    current_location: str = ""
    current_house: str = ""
    subject: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    latest_version_id: str = ""
    chapter_num: str = ""
    chapter_year: str = ""
    active: bool = True
    # Enrichment from bill_version_tbl
    vote_required: str = ""
    appropriation: bool = False
    fiscal_committee: bool = False
    urgency: bool = False
    full_text: str = ""

    @property
    def bill_number(self) -> str:
        """Human-readable bill number like 'AB 123'."""
        return f"{self.measure_type} {self.measure_num}"

    @property
    def session_num(self) -> str:
        """Extract session number from raw bill_id (0=regular, 1+=extraordinary)."""
        # Raw bill_id format: 202520260AB123 (digit at index 8 is session_num)
        if len(self.bill_id) > 8 and self.bill_id[:8].isdigit():
            return self.bill_id[8]
        return "0"

    @property
    def normalized_bill_id(self) -> str:
        """Normalized ID for storage: 'ca-ab123' or 'ca-ab123-x1' for special sessions."""
        base = f"ca-{self.measure_type.lower()}{self.measure_num}"
        if self.session_num != "0":
            return f"{base}-x{self.session_num}"
        return base

    @property
    def official_url(self) -> str:
        """URL to the bill on leginfo."""
        session = self.session_year.replace("-", "")
        return (
            f"https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml"
            f"?bill_id={session}0{self.measure_type}{self.measure_num}"
        )


@dataclass
class CAVoteSummary:
    """A vote tally on a bill."""
    bill_id: str
    location_code: str
    vote_datetime: str
    ayes: int
    noes: int
    abstain: int
    result: str   # "PASS", "FAIL"
    motion_id: int = 0


@dataclass
class CADetailVote:
    """An individual legislator's vote."""
    bill_id: str
    legislator_name: str
    vote_code: str   # "AYE", "NOE", "ABS", "NVR"
    vote_datetime: str
    location_code: str
    motion_id: int = 0


@dataclass
class CAHearing:
    """A committee hearing for a bill."""
    bill_id: str
    committee_type: str
    committee_nr: int
    hearing_date: str
    location_code: str


@dataclass
class CAAgenda:
    """A committee agenda item."""
    committee_code: str
    committee_desc: str
    agenda_date: str
    agenda_time: str
    location: str   # combined building_type + room_num


@dataclass
class CAHistoryAction:
    """A single action in a bill's history."""
    bill_id: str
    action_date: str
    action: str
    action_code: str = ""
    action_status: str = ""
    primary_location: str = ""


class CaliforniaLegislatureClient:
    """
    Client for California Legislature bulk data downloads.

    Downloads and parses the official PUBINFO archives from
    downloads.leginfo.legislature.ca.gov. Same data format as
    modal_cacode.py uses for codified law.

    Usage:
        client = CaliforniaLegislatureClient()
        bills = client.fetch_bills(session="2025-2026")
        hearings = client.fetch_hearings(session="2025-2026")
        votes = client.fetch_vote_summaries(session="2025-2026")
    """

    BASE_URL = "https://downloads.leginfo.legislature.ca.gov"

    def __init__(self, cache_dir: Optional[str] = None):
        """
        Args:
            cache_dir: Directory to cache downloaded ZIPs. If None, uses
                       a temp directory (not persisted).
        """
        self.cache_dir = cache_dir
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "CivicOS/1.0 (civic-conversational-os; research)",
        })
        # Parsed data cache (per-download)
        self._location_codes: Dict[str, str] = {}

    # ─────────── Download & Extract ───────────

    def _download_archive(self, filename: str) -> bytes:
        """Download a ZIP archive from the bulk download site."""
        url = f"{self.BASE_URL}/{filename}"
        logger.info(f"Downloading {url}...")
        start = time.time()

        response = self.session.get(url, timeout=300, stream=True)
        response.raise_for_status()

        content = response.content
        elapsed = time.time() - start
        size_mb = len(content) / 1024 / 1024
        logger.info(f"Downloaded {size_mb:.1f}MB in {elapsed:.1f}s")
        return content

    def _download_from_r2(self, r2_key: str) -> bytes:
        """Download archive from R2 blob storage (for Modal)."""
        import boto3

        blob_url = os.environ.get("BLOB_STORAGE_URL", "")
        if not blob_url.startswith("r2://"):
            raise ValueError(f"Invalid BLOB_STORAGE_URL: {blob_url}")

        parts = blob_url.replace("r2://", "").split("/", 1)
        account_id, bucket = parts

        s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
            aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        )

        logger.info(f"Downloading from R2: {r2_key}")
        response = s3.get_object(Bucket=bucket, Key=r2_key)
        return response["Body"].read()

    def _extract_tables(
        self,
        zip_content: bytes,
        table_names: List[str],
    ) -> Dict[str, Path]:
        """
        Extract specific .dat files from a ZIP archive to a temp directory.

        Args:
            zip_content: Raw ZIP bytes
            table_names: Table names to extract (e.g., ["BILL_TBL", "BILL_HISTORY_TBL"])

        Returns:
            Dict mapping table name -> Path to extracted .dat file
        """
        tmpdir = tempfile.mkdtemp(prefix="ca_legis_")
        result = {}

        with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
            for name in zf.namelist():
                for table in table_names:
                    if name == f"{table}.dat" or name.endswith(f"/{table}.dat"):
                        target = Path(tmpdir) / f"{table}.dat"
                        with zf.open(name) as src, open(target, "wb") as dst:
                            dst.write(src.read())
                        result[table] = target
                        break

            # Also extract .lob files for bill text if BILL_VERSION_TBL requested
            if "BILL_VERSION_TBL" in table_names:
                for name in zf.namelist():
                    if name.startswith("BILL_VERSION_TBL_") and name.endswith(".lob"):
                        target = Path(tmpdir) / Path(name).name
                        with zf.open(name) as src, open(target, "wb") as dst:
                            dst.write(src.read())

        logger.info(f"Extracted {len(result)} tables to {tmpdir}")
        return result

    # ─────────── Parsers ───────────

    def _parse_dat_file(self, path: Path) -> Iterator[List[str]]:
        """
        Parse a tab-delimited .dat file, yielding cleaned field lists.

        Fields are tab-separated and may be enclosed in backticks.
        """
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                # Strip backtick enclosure
                yield [p.strip("`") for p in parts]

    def _parse_datetime(self, s: str) -> Optional[str]:
        """Parse a datetime string to ISO format date."""
        if not s or s.strip() == "":
            return None
        s = s.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%m/%d/%Y %H:%M:%S %p", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    def _session_archive_name(self, session: str) -> str:
        """
        Get the archive filename for a session.

        Args:
            session: Session like "2025-2026" or "2023-2024"

        Returns:
            Archive filename like "pubinfo_2025.zip"
        """
        # Archive is named by the first year of the session
        year = session.split("-")[0]
        return f"pubinfo_{year}.zip"

    # ─────────── Location Codes ───────────

    def _load_location_codes(self, tables: Dict[str, Path]) -> Dict[str, str]:
        """Load location code -> description mapping."""
        if "LOCATION_CODE_TBL" not in tables:
            return {}

        codes = {}
        for fields in self._parse_dat_file(tables["LOCATION_CODE_TBL"]):
            if len(fields) < 6:
                continue
            code = fields[1].strip()       # location_code
            desc = fields[5].strip()       # long_description
            if not desc:
                desc = fields[4].strip()   # description
            if code:
                codes[code] = desc
        return codes

    # ─────────── Bills ───────────

    def parse_bills(self, tables: Dict[str, Path]) -> List[CABill]:
        """
        Parse BILL_TBL into CABill objects.

        Schema: bill_id, session_year, session_num, measure_type, measure_num,
                measure_state, chapter_year, chapter_type, chapter_session_num,
                chapter_num, latest_bill_version_id, active_flg, trans_uid,
                trans_update, current_location, current_secondary_loc,
                current_house, current_status, days_31st_in_print
        """
        if "BILL_TBL" not in tables:
            return []

        bills = []
        for fields in self._parse_dat_file(tables["BILL_TBL"]):
            if len(fields) < 12:
                continue

            bill_id = fields[0].strip()
            session_year = fields[1].strip()
            measure_type = fields[3].strip()

            try:
                measure_num = int(fields[4].strip())
            except (ValueError, IndexError):
                continue

            status = fields[5].strip()
            active = fields[11].strip() != "N" if len(fields) > 11 else True

            bill = CABill(
                bill_id=bill_id,
                session_year=self._format_session(session_year),
                measure_type=measure_type,
                measure_num=measure_num,
                status=status,
                current_location=fields[14].strip() if len(fields) > 14 else "",
                current_house=fields[16].strip() if len(fields) > 16 else "",
                latest_version_id=fields[10].strip() if len(fields) > 10 else "",
                chapter_num=fields[9].strip() if len(fields) > 9 else "",
                chapter_year=fields[6].strip() if len(fields) > 6 else "",
                active=active,
            )
            bills.append(bill)

        logger.info(f"Parsed {len(bills)} bills from BILL_TBL")
        return bills

    def _format_session(self, raw: str) -> str:
        """Format session year: '20252026' -> '2025-2026'."""
        raw = raw.strip()
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:]}"
        return raw

    def enrich_bills_with_versions(
        self,
        bills: List[CABill],
        tables: Dict[str, Path],
        include_text: bool = False,
    ) -> None:
        """
        Enrich bills with subject, flags from BILL_VERSION_TBL.

        Only uses the latest version for each bill (matching latest_bill_version_id).

        Schema: bill_version_id, bill_id, version_num, bill_version_action_date,
                bill_version_action, request_num, subject, vote_required,
                appropriation, fiscal_committee, local_program, substantive_changes,
                urgency, taxlevy, bill_xml, active_flg, trans_uid, trans_update
        """
        if "BILL_VERSION_TBL" not in tables:
            return

        # Build lookup by bill_id -> latest version data
        bill_lookup = {b.bill_id: b for b in bills}

        # First pass: find latest version per bill
        latest_versions: Dict[str, List[str]] = {}
        for fields in self._parse_dat_file(tables["BILL_VERSION_TBL"]):
            if len(fields) < 8:
                continue

            version_id = fields[0].strip()
            bill_id = fields[1].strip()

            if bill_id in bill_lookup:
                bill = bill_lookup[bill_id]
                if version_id == bill.latest_version_id or not bill.subject:
                    latest_versions[bill_id] = fields

        # Apply enrichment
        for bill_id, fields in latest_versions.items():
            bill = bill_lookup[bill_id]
            bill.subject = fields[6].strip() if len(fields) > 6 else ""
            bill.title = bill.subject  # subject is the closest to a title
            bill.vote_required = fields[7].strip() if len(fields) > 7 else ""
            bill.appropriation = fields[8].strip().upper() == "YES" if len(fields) > 8 else False
            bill.fiscal_committee = fields[9].strip().upper() == "YES" if len(fields) > 9 else False
            bill.urgency = fields[12].strip().upper() == "YES" if len(fields) > 12 else False

            # Bill text is in the bill_xml field (index 14) or in .lob files
            if include_text and len(fields) > 14:
                xml_content = fields[14].strip()
                if xml_content:
                    bill.full_text = self._strip_xml_tags(xml_content)

        logger.info(f"Enriched {len(latest_versions)} bills with version data")

    def enrich_bills_with_authors(
        self,
        bills: List[CABill],
        tables: Dict[str, Path],
    ) -> None:
        """
        Enrich bills with author names from BILL_VERSION_AUTHORS_TBL.

        Schema: bill_version_id, type, house, name, contribution,
                active_flg, primary_author_flg, trans_uid, trans_update
        """
        if "BILL_VERSION_AUTHORS_TBL" not in tables:
            return

        bill_lookup = {b.bill_id: b for b in bills}

        # Map version_id -> bill_id for lookup
        version_to_bill: Dict[str, str] = {}
        for b in bills:
            if b.latest_version_id:
                version_to_bill[b.latest_version_id] = b.bill_id

        for fields in self._parse_dat_file(tables["BILL_VERSION_AUTHORS_TBL"]):
            if len(fields) < 5:
                continue

            version_id = fields[0].strip()
            name = fields[3].strip()
            is_primary = fields[6].strip().upper() == "Y" if len(fields) > 6 else False

            bill_id = version_to_bill.get(version_id)
            if bill_id and bill_id in bill_lookup and name:
                bill = bill_lookup[bill_id]
                if is_primary:
                    bill.authors.insert(0, name)
                else:
                    bill.authors.append(name)

    # ─────────── History ───────────

    def parse_history(self, tables: Dict[str, Path]) -> List[CAHistoryAction]:
        """
        Parse BILL_HISTORY_TBL into action records.

        Schema: bill_id, bill_history_id, action_date, action, trans_uid,
                trans_update_dt, action_sequence, action_code, action_status,
                primary_location, secondary_location, ternary_location, end_status
        """
        if "BILL_HISTORY_TBL" not in tables:
            return []

        actions = []
        for fields in self._parse_dat_file(tables["BILL_HISTORY_TBL"]):
            if len(fields) < 4:
                continue

            bill_id = fields[0].strip()
            action_date = self._parse_datetime(fields[2])
            action_text = fields[3].strip()

            if not bill_id or not action_text:
                continue

            actions.append(CAHistoryAction(
                bill_id=bill_id,
                action_date=action_date or "",
                action=action_text,
                action_code=fields[7].strip() if len(fields) > 7 else "",
                action_status=fields[8].strip() if len(fields) > 8 else "",
                primary_location=fields[9].strip() if len(fields) > 9 else "",
            ))

        logger.info(f"Parsed {len(actions)} history actions")
        return actions

    # ─────────── Votes ───────────

    def parse_vote_summaries(self, tables: Dict[str, Path]) -> List[CAVoteSummary]:
        """
        Parse BILL_SUMMARY_VOTE_TBL into vote summaries.

        Schema: bill_id, location_code, vote_date_time, vote_date_seq,
                motion_id, ayes, noes, abstain, vote_result, trans_uid,
                trans_update, file_item_num, file_location, display_lines,
                session_date
        """
        if "BILL_SUMMARY_VOTE_TBL" not in tables:
            return []

        votes = []
        for fields in self._parse_dat_file(tables["BILL_SUMMARY_VOTE_TBL"]):
            if len(fields) < 9:
                continue

            bill_id = fields[0].strip()
            if not bill_id:
                continue

            try:
                ayes = int(fields[5].strip()) if fields[5].strip() else 0
                noes = int(fields[6].strip()) if fields[6].strip() else 0
                abstain = int(fields[7].strip()) if fields[7].strip() else 0
                motion_id = int(fields[4].strip()) if fields[4].strip() else 0
            except ValueError:
                continue

            votes.append(CAVoteSummary(
                bill_id=bill_id,
                location_code=fields[1].strip(),
                vote_datetime=self._parse_datetime(fields[2]) or "",
                ayes=ayes,
                noes=noes,
                abstain=abstain,
                result=fields[8].strip(),
                motion_id=motion_id,
            ))

        logger.info(f"Parsed {len(votes)} vote summaries")
        return votes

    def parse_detail_votes(self, tables: Dict[str, Path]) -> List[CADetailVote]:
        """
        Parse BILL_DETAIL_VOTE_TBL into individual legislator votes.

        Schema: bill_id, location_code, legislator_name, vote_date_time,
                vote_date_seq, vote_code, motion_id, trans_uid, trans_update,
                member_order, session_date, speaker
        """
        if "BILL_DETAIL_VOTE_TBL" not in tables:
            return []

        votes = []
        for fields in self._parse_dat_file(tables["BILL_DETAIL_VOTE_TBL"]):
            if len(fields) < 6:
                continue

            bill_id = fields[0].strip()
            legislator = fields[2].strip()
            if not bill_id or not legislator:
                continue

            try:
                motion_id = int(fields[6].strip()) if len(fields) > 6 and fields[6].strip() else 0
            except ValueError:
                motion_id = 0

            votes.append(CADetailVote(
                bill_id=bill_id,
                legislator_name=legislator,
                vote_code=fields[5].strip(),
                vote_datetime=self._parse_datetime(fields[3]) or "",
                location_code=fields[1].strip(),
                motion_id=motion_id,
            ))

        logger.info(f"Parsed {len(votes)} detail votes")
        return votes

    # ─────────── Hearings & Agendas ───────────

    def parse_hearings(self, tables: Dict[str, Path]) -> List[CAHearing]:
        """
        Parse COMMITTEE_HEARING_TBL.

        Schema: bill_id, committee_type, committee_nr, hearing_date,
                location_code, trans_uid, trans_update_date
        """
        if "COMMITTEE_HEARING_TBL" not in tables:
            return []

        hearings = []
        for fields in self._parse_dat_file(tables["COMMITTEE_HEARING_TBL"]):
            if len(fields) < 5:
                continue

            bill_id = fields[0].strip()
            if not bill_id:
                continue

            try:
                committee_nr = int(fields[2].strip()) if fields[2].strip() else 0
            except ValueError:
                committee_nr = 0

            hearings.append(CAHearing(
                bill_id=bill_id,
                committee_type=fields[1].strip(),
                committee_nr=committee_nr,
                hearing_date=self._parse_datetime(fields[3]) or "",
                location_code=fields[4].strip(),
            ))

        logger.info(f"Parsed {len(hearings)} hearings")
        return hearings

    def parse_agendas(self, tables: Dict[str, Path]) -> List[CAAgenda]:
        """
        Parse COMMITTEE_AGENDA_TBL.

        Schema: committee_code, committee_desc, agenda_date, agenda_time,
                line1, line2, line3, building_type, room_num
        """
        if "COMMITTEE_AGENDA_TBL" not in tables:
            return []

        agendas = []
        for fields in self._parse_dat_file(tables["COMMITTEE_AGENDA_TBL"]):
            if len(fields) < 4:
                continue

            code = fields[0].strip()
            if not code:
                continue

            building = fields[7].strip() if len(fields) > 7 else ""
            room = fields[8].strip() if len(fields) > 8 else ""
            location = f"{building} {room}".strip() if building or room else ""

            agendas.append(CAAgenda(
                committee_code=code,
                committee_desc=fields[1].strip(),
                agenda_date=self._parse_datetime(fields[2]) or "",
                agenda_time=fields[3].strip(),
                location=location,
            ))

        logger.info(f"Parsed {len(agendas)} agenda items")
        return agendas

    # ─────────── Normalization for Storage ───────────

    def normalize_bill_for_storage(self, bill: CABill) -> Dict[str, Any]:
        """
        Normalize a CABill to the dict format expected by store_legislation().

        Maps to the legislation table schema:
            bill_id, state, jurisdiction_id, bill_number, bill_name, status,
            summary, full_text, official_url, keywords, metadata
        """
        # Map measure_state to a cleaner status
        status = STATUS_MAP.get(bill.status, bill.status)

        # Enacted date from chapter info
        enacted_date = None
        if bill.chapter_year and bill.chapter_num and bill.chapter_year not in ("", "NULL"):
            enacted_date = f"{bill.chapter_year}-01-01"  # Approximate

        metadata = {
            "measure_type": bill.measure_type,
            "measure_type_label": MEASURE_TYPES.get(bill.measure_type, bill.measure_type),
            "session": bill.session_year,
            "current_location": bill.current_location,
            "current_house": bill.current_house,
            "vote_required": bill.vote_required,
            "appropriation": bill.appropriation,
            "fiscal_committee": bill.fiscal_committee,
            "urgency": bill.urgency,
            "authors": bill.authors,
            "source": "leginfo_bulk",
            "leginfo_bill_id": bill.bill_id,
        }

        # Use location codes to resolve current_location name
        if bill.current_location and self._location_codes:
            loc_name = self._location_codes.get(bill.current_location)
            if loc_name:
                metadata["current_location_name"] = loc_name

        return {
            "bill_id": bill.normalized_bill_id,
            "bill_number": bill.bill_number,
            "bill_name": bill.subject or bill.title or bill.bill_number,
            "status": status,
            "summary": bill.subject,
            "full_text": bill.full_text if bill.full_text else None,
            "official_url": bill.official_url,
            "enacted_date": enacted_date,
            "jurisdiction_id": "state-california",
            "metadata": metadata,
        }

    def normalize_hearing_for_storage(
        self,
        hearing: CAHearing,
        bill_lookup: Dict[str, CABill],
    ) -> Dict[str, Any]:
        """Normalize a hearing to store_legislative_events() format."""
        bill = bill_lookup.get(hearing.bill_id)
        normalized_bill_id = bill.normalized_bill_id if bill else self._normalize_raw_bill_id(hearing.bill_id)

        committee_name = self._location_codes.get(hearing.location_code, hearing.location_code)

        return {
            "bill_id": normalized_bill_id,
            "state": "CA",
            "event_type": "hearing",
            "event_date": hearing.hearing_date,
            "committee": committee_name,
            "location": hearing.location_code,
            "description": f"Committee hearing for {bill.bill_number if bill else normalized_bill_id}",
            "source": "leginfo_bulk",
        }

    def normalize_vote_for_storage(
        self,
        vote: CAVoteSummary,
        bill_lookup: Dict[str, CABill],
    ) -> Dict[str, Any]:
        """Normalize a vote summary to store_legislative_events() format."""
        bill = bill_lookup.get(vote.bill_id)
        normalized_bill_id = bill.normalized_bill_id if bill else self._normalize_raw_bill_id(vote.bill_id)

        committee_name = self._location_codes.get(vote.location_code, vote.location_code)
        result_text = "passed" if vote.result.upper() in ("PASS", "(PASS)") else "failed"

        return {
            "bill_id": normalized_bill_id,
            "state": "CA",
            "event_type": "vote",
            "event_date": vote.vote_datetime,
            "committee": committee_name,
            "description": (
                f"Vote {result_text}: {vote.ayes} ayes, {vote.noes} noes, "
                f"{vote.abstain} abstain in {committee_name}"
            ),
            "source": "leginfo_bulk",
        }

    def normalize_history_for_storage(
        self,
        action: CAHistoryAction,
        bill_lookup: Dict[str, CABill],
    ) -> Dict[str, Any]:
        """Normalize a history action to store_legislative_events() format."""
        bill = bill_lookup.get(action.bill_id)
        normalized_bill_id = bill.normalized_bill_id if bill else self._normalize_raw_bill_id(action.bill_id)

        # Determine event type from action text
        event_type = "action"
        action_lower = action.action.lower()
        if "hearing" in action_lower or "heard in" in action_lower:
            event_type = "hearing"
        elif "vote" in action_lower or "ayes" in action_lower:
            event_type = "vote"
        elif "sign" in action_lower or "chaptered" in action_lower:
            event_type = "signing"
        elif "referred to" in action_lower:
            event_type = "committee_referral"

        location_name = self._location_codes.get(
            action.primary_location, action.primary_location
        )

        return {
            "bill_id": normalized_bill_id,
            "state": "CA",
            "event_type": event_type,
            "event_date": action.action_date,
            "committee": location_name,
            "description": action.action[:500],
            "source": "leginfo_bulk",
        }

    # ─────────── High-Level Fetch Methods ───────────

    def fetch_session_data(
        self,
        session: str = "2025-2026",
        include_text: bool = False,
        source: str = "download",
        r2_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetch all data for a legislative session.

        Args:
            session: Session identifier (e.g., "2025-2026")
            include_text: Whether to extract bill full text (much larger)
            source: "download" for direct download, "r2" for R2 blob storage
            r2_key: R2 key if source is "r2"

        Returns:
            Dict with bills, hearings, votes, history, agendas
        """
        archive_name = self._session_archive_name(session)

        # Download
        if source == "r2" and r2_key:
            zip_content = self._download_from_r2(r2_key)
        else:
            zip_content = self._download_archive(archive_name)

        # Tables to extract
        table_names = [
            "BILL_TBL",
            "BILL_VERSION_TBL",
            "BILL_VERSION_AUTHORS_TBL",
            "BILL_HISTORY_TBL",
            "BILL_SUMMARY_VOTE_TBL",
            "BILL_DETAIL_VOTE_TBL",
            "COMMITTEE_HEARING_TBL",
            "COMMITTEE_AGENDA_TBL",
            "LOCATION_CODE_TBL",
        ]

        tables = self._extract_tables(zip_content, table_names)

        # Load location codes first (used by normalization)
        self._location_codes = self._load_location_codes(tables)

        # Parse everything
        bills = self.parse_bills(tables)
        self.enrich_bills_with_versions(bills, tables, include_text=include_text)
        self.enrich_bills_with_authors(bills, tables)
        hearings = self.parse_hearings(tables)
        vote_summaries = self.parse_vote_summaries(tables)
        history = self.parse_history(tables)
        agendas = self.parse_agendas(tables)

        return {
            "bills": bills,
            "hearings": hearings,
            "vote_summaries": vote_summaries,
            "history": history,
            "agendas": agendas,
            "location_codes": self._location_codes,
            "session": session,
        }

    # ─────────── Utilities ───────────

    def _normalize_raw_bill_id(self, raw_id: str) -> str:
        """
        Normalize a raw leginfo bill_id like '202520260AB123' to 'ca-ab123'.

        Special sessions (session_num > 0) get a suffix: 'ca-ab123-x1'.
        Falls back to lowercase if pattern doesn't match.
        """
        match = re.match(r'\d{8}(\d)(AB|SB|ACA|SCA|ACR|SCR|AJR|SJR|AR|SR)(\d+)', raw_id)
        if match:
            session_num = match.group(1)
            measure_type = match.group(2).lower()
            measure_num = match.group(3)
            if session_num != "0":
                return f"ca-{measure_type}{measure_num}-x{session_num}"
            return f"ca-{measure_type}{measure_num}"
        return raw_id.lower()

    def _strip_xml_tags(self, xml: str) -> str:
        """Strip XML/HTML tags from bill text content."""
        text = re.sub(r'<[^>]+>', ' ', xml)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
