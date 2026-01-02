"""
Modal function for California Codes ingestion to PostgreSQL.

California provides public law data at:
https://downloads.leginfo.legislature.ca.gov/

Data structure:
- pubinfo_YYYY.zip: Full annual snapshot with all law sections
- LAW_SECTION_TBL.dat: Tab-separated section metadata
- LAW_SECTION_TBL_*.lob: XML content files for each section
- CODES_TBL.dat: Code abbreviation -> full name mapping

Setup:
    Ensure Modal secrets exist:
    modal secret create civic-db DATABASE_URL="postgresql://..."
    modal secret create civic-r2 \
        R2_ACCOUNT_ID="..." \
        R2_ACCESS_KEY_ID="..." \
        R2_SECRET_ACCESS_KEY="..." \
        R2_BUCKET_NAME="civic-pilot"

Usage:
    # Upload local ZIP to R2 first (run locally with civic-env activated)
    python scripts/upload_cacode_r2.py

    # Then ingest from R2 (runs in Modal cloud)
    modal run scripts/modal_cacode.py

    # Dry run (parse only)
    modal run scripts/modal_cacode.py --dry-run

    # Stats only
    modal run scripts/modal_cacode.py --stats-only

    # Ingest specific code (e.g., Government Code)
    modal run scripts/modal_cacode.py --code GOV
"""

import modal
import os
import re
from dataclasses import dataclass, asdict
from typing import Dict, Iterator, List, Optional
import xml.etree.ElementTree as ET

# Define the Modal app
app = modal.App("civic-cacode")

# Build image with dependencies
civic_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libpq-dev", "gcc")
    .pip_install(
        "psycopg2-binary>=2.9.0",
        "boto3>=1.26.0",
        "httpx>=0.24.0",
        "langgraph>=0.2.0",
        "langchain-core>=0.3.0",
    )
    .add_local_python_source("civic")
)

# R2 path for California codes
R2_PREFIX = "cacode/2025"

# All 29 California code abbreviations
# From: https://leginfo.legislature.ca.gov/
ALL_CODES = {
    "BPC": "Business and Professions Code",
    "CIV": "Civil Code",
    "CCP": "Code of Civil Procedure",
    "COM": "Commercial Code",
    "CORP": "Corporations Code",
    "EDC": "Education Code",
    "ELEC": "Elections Code",
    "EVID": "Evidence Code",
    "FAM": "Family Code",
    "FIN": "Financial Code",
    "FGC": "Fish and Game Code",
    "FAC": "Food and Agricultural Code",
    "GOV": "Government Code",
    "HNC": "Harbors and Navigation Code",
    "HSC": "Health and Safety Code",
    "INS": "Insurance Code",
    "LAB": "Labor Code",
    "MVC": "Military and Veterans Code",
    "PEN": "Penal Code",
    "PROB": "Probate Code",
    "PCC": "Public Contract Code",
    "PRC": "Public Resources Code",
    "PUC": "Public Utilities Code",
    "RTC": "Revenue and Taxation Code",
    "SHC": "Streets and Highways Code",
    "UIC": "Unemployment Insurance Code",
    "VEH": "Vehicle Code",
    "WAT": "Water Code",
    "WIC": "Welfare and Institutions Code",
}


@dataclass
class CACodeSection:
    """A single section of California Code."""
    title_number: int  # Will use code index (1-29) as "title_number" for consistency
    title_name: str    # Full code name
    section_number: str
    heading: str
    text: str
    citation: str
    identifier: str
    status: Optional[str] = None
    chapter: Optional[str] = None
    division: Optional[str] = None
    part: Optional[str] = None
    article: Optional[str] = None
    history: Optional[str] = None
    effective_date: Optional[str] = None
    law_code: Optional[str] = None  # Original code abbreviation

    def to_dict(self) -> dict:
        return asdict(self)

    def is_active(self) -> bool:
        return self.status != "N"


class CACodeParser:
    """Parser for California Codes data files."""

    def __init__(self, data_dir: str, codes_map: Dict[str, str]):
        """
        Initialize parser.

        Args:
            data_dir: Directory containing extracted .dat and .lob files
            codes_map: Mapping of code abbreviations to full names
        """
        from pathlib import Path
        self.data_dir = Path(data_dir)
        self.codes_map = codes_map
        self._sections_data = None
        self._lob_files = None

    def _load_sections_data(self) -> List[dict]:
        """Load and parse LAW_SECTION_TBL.dat."""
        if self._sections_data is not None:
            return self._sections_data

        dat_path = self.data_dir / "LAW_SECTION_TBL.dat"
        if not dat_path.exists():
            raise FileNotFoundError(f"LAW_SECTION_TBL.dat not found in {self.data_dir}")

        self._sections_data = []

        # Fields from the schema (tab-separated, backtick-enclosed)
        # ID, LAW_CODE, SECTION_NUM, OP_STATUES, OP_CHAPTER, OP_SECTION,
        # EFFECTIVE_DATE, LAW_SECTION_VERSION_ID, DIVISION, TITLE, PART,
        # CHAPTER, ARTICLE, HISTORY, <content_xml_path>, ACTIVE_FLG, TRANS_UID, TRANS_UPDATE

        with open(dat_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                # Remove enclosing backticks and split by tab
                parts = line.strip().split("\t")
                if len(parts) < 16:
                    continue

                # Clean backticks from values
                parts = [p.strip("`") for p in parts]

                section = {
                    "id": parts[0],
                    "law_code": parts[1],
                    "section_num": parts[2],
                    "op_statutes": parts[3] if len(parts) > 3 else None,
                    "op_chapter": parts[4] if len(parts) > 4 else None,
                    "op_section": parts[5] if len(parts) > 5 else None,
                    "effective_date": parts[6] if len(parts) > 6 else None,
                    "law_section_version_id": parts[7] if len(parts) > 7 else None,
                    "division": parts[8] if len(parts) > 8 else None,
                    "title": parts[9] if len(parts) > 9 else None,
                    "part": parts[10] if len(parts) > 10 else None,
                    "chapter": parts[11] if len(parts) > 11 else None,
                    "article": parts[12] if len(parts) > 12 else None,
                    "history": parts[13] if len(parts) > 13 else None,
                    "content_xml_path": parts[14] if len(parts) > 14 else None,
                    "active_flg": parts[15] if len(parts) > 15 else "Y",
                }
                self._sections_data.append(section)

        return self._sections_data

    def _get_lob_content(self, lob_filename: str) -> Optional[str]:
        """Read XML content from a .lob file."""
        if not lob_filename:
            return None

        # The path in the dat file might be a Windows path like "c:\pubinfo\LAW_SECTION_TBL_123.lob"
        # We just need the filename
        lob_name = lob_filename.replace("\\", "/").split("/")[-1]
        lob_path = self.data_dir / lob_name

        if not lob_path.exists():
            return None

        try:
            return lob_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

    def _extract_text_from_xml(self, xml_content: str) -> tuple:
        """Extract heading and text from CA code XML content.

        CA Codes XML format uses caml:Content tags:
        <caml:Content xmlns:caml="..."><p>Section text...</p></caml:Content>

        Multiple Content elements may exist for sections with multiple parts.
        Headings are not in the XML - they come from section metadata.
        """
        if not xml_content:
            return "", ""

        heading = ""  # Heading comes from section metadata, not XML
        text_parts = []

        # CA XML uses caml: namespace prefix
        # Format: <caml:Content xmlns:caml="..."><p>text</p></caml:Content>
        # May have multiple Content elements

        try:
            # Handle namespace by wrapping in root element if needed
            if not xml_content.strip().startswith("<?xml"):
                # Wrap multiple content elements in a root
                wrapped = f"<root>{xml_content}</root>"
            else:
                wrapped = xml_content

            root = ET.fromstring(wrapped)

            # Find all Content elements (namespace-aware)
            ns = {"caml": "http://lc.ca.gov/legalservices/schemas/caml.1#"}
            for content in root.findall(".//caml:Content", ns):
                text = self._get_element_text(content)
                if text.strip():
                    text_parts.append(text.strip())

            # Also try without namespace (in case it varies)
            if not text_parts:
                for content in root.iter():
                    if "Content" in content.tag:
                        text = self._get_element_text(content)
                        if text.strip():
                            text_parts.append(text.strip())

        except ET.ParseError:
            # Fallback: extract text with regex from <p> tags
            p_matches = re.findall(r"<p>(.*?)</p>", xml_content, re.DOTALL)
            for match in p_matches:
                # Strip remaining HTML tags
                text = re.sub(r"<[^>]+>", " ", match)
                text = " ".join(text.split())  # Normalize whitespace
                if text.strip():
                    text_parts.append(text.strip())

        return heading, "\n\n".join(text_parts)

    def _get_element_text(self, elem) -> str:
        """Recursively get text from an XML element."""
        parts = []
        if elem.text:
            parts.append(elem.text)
        for child in elem:
            parts.append(self._get_element_text(child))
            if child.tail:
                parts.append(child.tail)
        return " ".join(parts)

    def parse_sections(
        self,
        code_filter: Optional[str] = None,
        include_inactive: bool = False,
    ) -> Iterator[CACodeSection]:
        """
        Parse and yield sections from the data files.

        Args:
            code_filter: Only parse specific code (e.g., "GOV")
            include_inactive: Include inactive (repealed) sections
        """
        sections_data = self._load_sections_data()

        # Create code index mapping for title_number
        code_index = {code: i + 1 for i, code in enumerate(sorted(ALL_CODES.keys()))}

        for section in sections_data:
            law_code = section.get("law_code", "").strip()

            # Filter by code if specified
            if code_filter and law_code != code_filter:
                continue

            # Filter inactive if not including
            if not include_inactive and section.get("active_flg") == "N":
                continue

            # Skip if no valid code
            if law_code not in self.codes_map:
                continue

            # Get XML content
            xml_content = self._get_lob_content(section.get("content_xml_path"))
            heading, text = self._extract_text_from_xml(xml_content)

            section_num = section.get("section_num", "").strip()

            # Build citation (e.g., "Cal. Gov. Code § 12345")
            code_full = self.codes_map.get(law_code, law_code)
            # Clean up code name for citation: "Government Code - GOV" -> "Gov."
            code_short = code_full.split(" Code")[0].split(" - ")[0]
            # Abbreviate common words
            code_short = code_short.replace("Business and Professions", "Bus. & Prof.")
            code_short = code_short.replace("Code of Civil Procedure", "Civ. Proc.")
            code_short = code_short.replace("Civil", "Civ.")
            code_short = code_short.replace("Commercial", "Com.")
            code_short = code_short.replace("Corporations", "Corp.")
            code_short = code_short.replace("Education", "Educ.")
            code_short = code_short.replace("Elections", "Elec.")
            code_short = code_short.replace("Evidence", "Evid.")
            code_short = code_short.replace("Family", "Fam.")
            code_short = code_short.replace("Financial", "Fin.")
            code_short = code_short.replace("Fish and Game", "Fish & G.")
            code_short = code_short.replace("Food and Agricultural", "Food & Agric.")
            code_short = code_short.replace("Government", "Gov.")
            code_short = code_short.replace("Harbors and Navigation", "Harb. & Nav.")
            code_short = code_short.replace("Health and Safety", "Health & Saf.")
            code_short = code_short.replace("Insurance", "Ins.")
            code_short = code_short.replace("Labor", "Lab.")
            code_short = code_short.replace("Military and Veterans", "Mil. & Vet.")
            code_short = code_short.replace("Penal", "Pen.")
            code_short = code_short.replace("Probate", "Prob.")
            code_short = code_short.replace("Public Contract", "Pub. Contract")
            code_short = code_short.replace("Public Resources", "Pub. Resources")
            code_short = code_short.replace("Public Utilities", "Pub. Util.")
            code_short = code_short.replace("Revenue and Taxation", "Rev. & Tax.")
            code_short = code_short.replace("Streets and Highways", "Sts. & Hy.")
            code_short = code_short.replace("Unemployment Insurance", "Unemp. Ins.")
            code_short = code_short.replace("Vehicle", "Veh.")
            code_short = code_short.replace("Water", "Wat.")
            code_short = code_short.replace("Welfare and Institutions", "Welf. & Inst.")
            citation = f"Cal. {code_short} Code § {section_num}"

            # Build identifier (unique per section)
            identifier = f"/ca/{law_code.lower()}/s{section_num}"

            yield CACodeSection(
                title_number=code_index.get(law_code, 0),
                title_name=code_full,
                section_number=section_num,
                heading=heading,
                text=text,
                citation=citation,
                identifier=identifier,
                status=None if section.get("active_flg") == "Y" else "repealed",
                chapter=section.get("chapter"),
                division=section.get("division"),
                part=section.get("part"),
                article=section.get("article"),
                history=section.get("history"),
                effective_date=section.get("effective_date"),
                law_code=law_code,
            )


@app.function(
    image=civic_image,
    secrets=[
        modal.Secret.from_name("civic-db"),
        modal.Secret.from_name("civic-blob"),
    ],
    memory=8192,  # 8GB - CA codes data is larger than US Code
    timeout=7200,  # 2 hours
)
def ingest_cacode(
    jurisdiction_id: str = "state-CA",
    dry_run: bool = False,
    stats_only: bool = False,
    code_filter: Optional[str] = None,
) -> dict:
    """
    Ingest California Codes sections from R2 to PostgreSQL.

    Args:
        jurisdiction_id: Target jurisdiction
        dry_run: Parse only, don't store
        stats_only: Show database stats only
        code_filter: Only ingest specific code (e.g., "GOV")

    Returns:
        Dict with ingestion results
    """
    import time
    import zipfile
    import tempfile
    from io import BytesIO
    import boto3

    # Get database connection
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return {"error": "DATABASE_URL not set"}

    # Stats only mode
    if stats_only:
        from civic.storage.postgres_backend import PostgresBackend
        db = PostgresBackend(database_url)
        count = db.get_codified_law_count(jurisdiction_id)
        return {
            "jurisdiction_id": jurisdiction_id,
            "sections_in_db": count,
        }

    # Download from R2
    print("Downloading CA Codes from R2...")
    start = time.time()

    blob_url = os.environ.get("BLOB_STORAGE_URL", "")
    if not blob_url.startswith("r2://"):
        return {"error": f"Invalid BLOB_STORAGE_URL: {blob_url}"}
    parts = blob_url.replace("r2://", "").split("/", 1)
    if len(parts) != 2:
        return {"error": f"Invalid BLOB_STORAGE_URL format: {blob_url}"}
    account_id, bucket = parts

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )

    key = f"{R2_PREFIX}/pubinfo_2025.zip"
    response = s3.get_object(Bucket=bucket, Key=key)
    zip_content = response["Body"].read()
    download_time = time.time() - start
    print(f"Downloaded {len(zip_content) / 1024 / 1024:.1f}MB in {download_time:.1f}s")

    # Extract to temp directory
    print("Extracting archive...")
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(BytesIO(zip_content)) as zf:
            # Only extract the files we need
            needed_files = [f for f in zf.namelist()
                          if f.startswith("LAW_SECTION_TBL") or f == "CODES_TBL.dat"]
            for f in needed_files:
                zf.extract(f, tmpdir)
            print(f"Extracted {len(needed_files)} files")

        # Load codes mapping
        codes_path = os.path.join(tmpdir, "CODES_TBL.dat")
        codes_map = ALL_CODES.copy()  # Use our predefined mapping
        if os.path.exists(codes_path):
            # Override with actual codes from data if available
            with open(codes_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\t")
                    if len(parts) >= 2:
                        code = parts[0].strip("`")
                        name = parts[1].strip("`")
                        codes_map[code] = name

        # Parse sections
        print("Parsing California Codes...")
        parser = CACodeParser(tmpdir, codes_map)

        seen_identifiers = set()
        sections = []

        for section in parser.parse_sections(code_filter=code_filter):
            if section.identifier and section.identifier not in seen_identifiers:
                seen_identifiers.add(section.identifier)
                sections.append(section.to_dict())

        print(f"Parsed {len(sections)} unique sections")

    if dry_run:
        # Show sample and stats by code
        by_code = {}
        for s in sections:
            code = s.get("law_code", "UNK")
            by_code[code] = by_code.get(code, 0) + 1

        return {
            "sections_parsed": len(sections),
            "dry_run": True,
            "by_code": by_code,
            "sample": sections[0] if sections else None,
        }

    # Store to PostgreSQL
    print("Storing to PostgreSQL...")
    from civic.storage.postgres_backend import PostgresBackend
    db = PostgresBackend(database_url)

    start = time.time()
    stored = db.store_codified_law(
        jurisdiction_id=jurisdiction_id,
        sections=sections,
        use_copy=True,
    )
    store_time = time.time() - start

    print(f"Stored {stored} sections in {store_time:.1f}s")

    # Get final count
    total = db.get_codified_law_count(jurisdiction_id)

    return {
        "jurisdiction_id": jurisdiction_id,
        "sections_parsed": len(sections),
        "sections_stored": stored,
        "total_in_db": total,
        "download_time_s": download_time,
        "store_time_s": store_time,
    }


@app.local_entrypoint()
def main(
    jurisdiction_id: str = "state-CA",
    dry_run: bool = False,
    stats_only: bool = False,
    code: str = "",
):
    """CLI entrypoint for Modal."""
    code_filter = code if code else None

    if code_filter:
        print(f"Ingesting California {ALL_CODES.get(code_filter, code_filter)}...")
    else:
        print(f"Ingesting all {len(ALL_CODES)} California Codes...")

    result = ingest_cacode.remote(
        jurisdiction_id=jurisdiction_id,
        dry_run=dry_run,
        stats_only=stats_only,
        code_filter=code_filter,
    )

    print("\n" + "=" * 50)
    print("RESULT:")
    for key, value in result.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")
    print("=" * 50)
