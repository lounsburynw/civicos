"""
Municipal code corpus via Municode API.

Fetches municipal code from Municode's public API, providing clean structured
access to ordinances without brittle PDF parsing.

San Rafael Municipal Code structure:
- Title X: Broad category (e.g., "Title 1 - GENERAL PROVISIONS")
- Chapter X.YY: Specific topic (e.g., "Chapter 1.04 - ADOPTION OF CODE")
- Section X.YY.ZZZ: Individual provision (e.g., "1.04.010 - Title.")

API Reference: https://sr.ht/~partytax/unofficial-municode-api-documentation/

Adding a New Municipality
=========================

1. VERIFY AVAILABILITY: Check if the municipality is in Municode:

    >>> import httpx
    >>> clients = httpx.get('https://api.municode.com/Clients/stateAbbr',
    ...                     params={'stateAbbr': 'CA'}).json()
    >>> [c for c in clients if 'Berkeley' in c['ClientName']]
    [{'ClientID': 123, 'ClientName': 'Berkeley'}]

2. ADD TO JURISDICTION_MAP (simple case - standard patterns):

    JURISDICTION_MAP = {
        "city-berkeley": {"state": "CA", "name": "Berkeley"},
    }

3. ADD WITH CUSTOM PRODUCT NAME (if not "Code of Ordinances"):

    JURISDICTION_MAP = {
        "county-marin": {
            "state": "CA",
            "name": "Marin County",
            "product_name": "Municipal Code",  # Check via Products API
        },
    }

4. ADD WITH CUSTOM PATTERNS (different numbering scheme):

    JURISDICTION_MAP = {
        "city-different": {
            "state": "XX",
            "name": "Different City",
            # For codes using "Ch. 1-2" format instead of "Chapter 1.02"
            "chapter_pattern": r'Ch\\.\\s+(\\d+-\\d+)\\s*[—–-]\\s*(.+)',
            # For codes using "§ 1-2-3" format instead of "1.02.030"
            "section_pattern": r'§\\s*(\\d+-\\d+-\\d+)\\s*[—–-]\\s*(.+)',
        },
    }

5. ADD CUSTOM PARSER CLASS (completely different structure):

    @register_parser("city-weird")
    class WeirdCityParser(MunicipalCodeCorpus):
        def stream_sections(self, title_ids=None):
            # Custom parsing logic for non-standard hierarchy
            ...

    # Use via factory method:
    corpus = MunicipalCodeCorpus.for_jurisdiction("city-weird")

Default Patterns (work for ~80% of California municipalities):
- Title:   r'Title\\s+(\\d+)\\s*[—–-]\\s*(.+)'
- Chapter: r'Chapter\\s+(\\d+\\.\\d+)\\s*[—–-]\\s*(.+)'
- Section: r'(\\d+\\.\\d+\\.\\d+[A-Za-z]?)\\s*[—–-]\\s*(.+)'

Pattern Requirements:
- Must have exactly 2 capture groups: (number, title/name)
- Support em-dash (—), en-dash (–), and hyphen (-) separators
"""

import logging
import re
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)
from html import unescape
from pathlib import Path
from typing import Iterator, Optional, Callable

import httpx

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


@dataclass
class MunicipalCodeSection:
    """A single section from the municipal code."""
    section_number: str  # e.g., "1.04.010"
    section_title: str  # e.g., "Title."
    full_text: str  # Plain text content (HTML stripped)
    chapter: str  # e.g., "1.04"
    chapter_title: str  # e.g., "ADOPTION OF CODE"
    title_number: str  # e.g., "1"
    title_name: str  # e.g., "GENERAL PROVISIONS"
    node_id: str  # Municode node ID for reference
    ordinance_history: Optional[str] = None  # e.g., "(Ord. 1235 § 1, 1976)"


# Municode client lookup cache
_CLIENT_CACHE: dict[str, dict] = {}

# Registry of custom parser classes for jurisdictions with non-standard formats
_PARSER_REGISTRY: dict[str, type] = {}


def register_parser(jurisdiction_id: str):
    """Decorator to register a custom parser class for a jurisdiction."""
    def decorator(cls):
        _PARSER_REGISTRY[jurisdiction_id] = cls
        return cls
    return decorator


def _is_amlegal_jurisdiction(jurisdiction_id: str) -> bool:
    """Check if a jurisdiction uses American Legal Publishing."""
    # Check AmericanLegalCorpus.JURISDICTION_MAP (lazy import)
    try:
        from .american_legal import AmericanLegalCorpus
        if jurisdiction_id in AmericanLegalCorpus.JURISDICTION_MAP:
            return True
    except ImportError:
        pass

    # Check jurisdiction YAML (env-configured dir, then local repo traversal)
    try:
        import os
        jurisdictions_dir = os.environ.get("CIVICOS_JURISDICTIONS_DIR")
        if jurisdictions_dir:
            config_path = Path(jurisdictions_dir) / f"{jurisdiction_id}.yaml"
            if config_path.exists():
                import yaml
                with open(config_path) as f:
                    data = yaml.safe_load(f)
                return data.get("data_sources", {}).get("municipal_code") == "amlegal"
        for parent in Path(__file__).resolve().parents:
            config_path = parent / "data" / "jurisdictions" / f"{jurisdiction_id}.yaml"
            if config_path.exists():
                import yaml
                with open(config_path) as f:
                    data = yaml.safe_load(f)
                return data.get("data_sources", {}).get("municipal_code") == "amlegal"
    except Exception:
        pass

    return False


class MunicipalCodeCorpus:
    """
    Fetch municipal code from Municode API.

    Uses Municode's public API to retrieve structured municipal code data.
    Much more reliable than PDF parsing.

    Args:
        jurisdiction_id: Jurisdiction identifier (e.g., "city-san-rafael")
        client_id: Municode client ID (auto-discovered if not provided)
        product_id: Municode product ID (auto-discovered if not provided)
        rate_limit: Requests per second (default: 2)

    Extensibility:
        JURISDICTION_MAP supports these optional keys for customization:
        - product_name: Override default "Code of Ordinances"
        - chapter_pattern: Regex for chapter detection (must have 2 groups: number, title)
        - section_pattern: Regex for section detection (must have 2 groups: number, title)
        - title_pattern: Regex for title detection in TOC (must have 2 groups: number, name)

        For complex cases, use @register_parser decorator to register a custom parser class.
    """

    BASE_URL = "https://api.municode.com"

    # Default patterns - work for most California municipalities
    # Override in JURISDICTION_MAP for jurisdictions with different formats
    DEFAULT_CHAPTER_PATTERN = r'Chapter\s+(\d+\.\d+)\s*[—–-]\s*(.+)'
    DEFAULT_SECTION_PATTERN = r'(\d+\.\d+\.\d+[A-Za-z]?)\s*[—–-]\s*(.+)'
    DEFAULT_TITLE_PATTERN = r'Title\s+(\d+)\s*[—–-]\s*(.+)'

    # Known jurisdiction mappings
    # product_name defaults to "Code of Ordinances" if not specified
    # chapter_pattern/section_pattern override default parsing patterns
    JURISDICTION_MAP = {
        "city-san-rafael": {"state": "CA", "name": "San Rafael"},
        "city-berkeley": {"state": "CA", "name": "Berkeley"},
        "city-oakland": {"state": "CA", "name": "Oakland"},
        "county-marin": {"state": "CA", "name": "Marin County", "product_name": "Municipal Code"},
    }

    def __init__(
        self,
        jurisdiction_id: str = "city-san-rafael",
        client_id: Optional[int] = None,
        product_id: Optional[int] = None,
        rate_limit: float = 2.0,
        **kwargs,
    ):
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for Municode API access. "
                "Install with: pip install httpx"
            )

        self.jurisdiction_id = jurisdiction_id
        self._client_id = client_id
        self._product_id = product_id
        self._job_id: Optional[int] = None
        self.rate_limit = rate_limit
        self._last_request = 0.0
        self._client: Optional[httpx.Client] = None

        # Cache compiled patterns for this jurisdiction
        self._chapter_pattern = self._get_pattern("chapter_pattern", self.DEFAULT_CHAPTER_PATTERN)
        self._section_pattern = self._get_pattern("section_pattern", self.DEFAULT_SECTION_PATTERN)
        self._title_pattern = self._get_pattern("title_pattern", self.DEFAULT_TITLE_PATTERN)

    def _get_pattern(self, key: str, default: str) -> re.Pattern:
        """Get compiled regex pattern for this jurisdiction."""
        jur_info = self.JURISDICTION_MAP.get(self.jurisdiction_id, {})
        pattern_str = jur_info.get(key, default)
        return re.compile(pattern_str)

    def _infer_title_pattern(self, headings: list[str]) -> Optional[re.Pattern]:
        """Infer a title pattern from TOC headings.

        Strategy: LLM-first (handles any format), hardcoded patterns as
        offline fallback (when no LLM API key is available).

        Returns a compiled regex with 2 capture groups (number, name), or None.
        """
        if not headings:
            return None

        # Strategy 1: LLM inference (handles arbitrary formats)
        llm_result = self._llm_infer_pattern(headings, "title")
        if llm_result:
            return llm_result

        # Strategy 2: Hardcoded alternative patterns (offline fallback)
        return self._match_alternative_title_patterns(headings)

    def _match_alternative_title_patterns(
        self, headings: list[str]
    ) -> Optional[re.Pattern]:
        """Try common alternative title patterns against headings.

        Offline fallback when LLM is unavailable. Covers ~80% of
        non-standard formats seen in US municipal codes.
        """
        alternative_patterns = [
            # "TITLE 1. - GENERAL" (with optional period, case-insensitive)
            r'(?i)TITLE\s+([IVXLCDM\d]+)\.?\s*[—–-]\s*(.+)',
            # "CHAPTER I - GENERAL" (roman numerals)
            r'CHAPTER\s+([IVXLCDM]+)\s*[—–-]\s*(.+)',
            # "Chapter 1 - General" (arabic, top-level)
            r'Chapter\s+(\d+)\s*[—–-]\s*(.+)',
            # "ARTICLE I - GENERAL" (roman numerals)
            r'ARTICLE\s+([IVXLCDM]+)\s*[—–-]\s*(.+)',
            # "Part 1 - General" or "PART I - GENERAL"
            r'(?:Part|PART)\s+(\w+)\s*[—–-]\s*(.+)',
            # "Division 1 - General"
            r'Division\s+(\d+)\s*[—–-]\s*(.+)',
        ]

        for pattern_str in alternative_patterns:
            pattern = re.compile(pattern_str)
            matches = sum(1 for h in headings if pattern.match(h))
            if matches >= 3:
                logger.info(
                    f"Matched {matches}/{len(headings)} headings with "
                    f"alternative pattern: {pattern_str}"
                )
                return pattern

        return None

    def _llm_infer_pattern(
        self, headings: list[str], pattern_type: str
    ) -> Optional[re.Pattern]:
        """Use an LLM to infer a regex pattern from sample headings.

        Args:
            headings: Sample headings to analyze
            pattern_type: "title" or "section" (affects the prompt)

        Returns a compiled regex with 2 capture groups, or None.
        """
        try:
            from civicos_services.core.llm_provider import get_model_for_task
        except ImportError:
            logger.debug("LLM not available for pattern inference")
            return None

        sample = headings[:30]

        if pattern_type == "title":
            prompt = (
                "These are headings from a municipal code table of contents. "
                "Identify which headings represent the top-level divisions "
                "(like Titles, Chapters, Articles, or Parts — NOT charter, "
                "supplement history tables, code comparative tables, or "
                "individual ordinances).\n\n"
                + "\n".join(f"- {h}" for h in sample)
                + "\n\nReturn ONLY a Python regex string with exactly 2 "
                "capture groups: (number_or_id, name). The regex should "
                "match the top-level division headings. Support em-dash "
                "(—), en-dash (–), and hyphen (-) as separators. Handle "
                "optional trailing periods after numbers (e.g., 'TITLE 1.' "
                "and 'TITLE 1' should both match). Example: "
                r"r'(?i)TITLE\s+(\d+)\.?\s*[—–-]\s*(.+)'"
                "\n\nReturn ONLY the regex string, no explanation or "
                "markdown formatting."
            )
        else:  # section
            prompt = (
                "These are headings from a municipal code's content sections. "
                "Identify the pattern for individual code sections (numbered "
                "provisions like '1-3.1 - Name' or '1.04.010 - Name').\n\n"
                + "\n".join(f"- {h}" for h in sample)
                + "\n\nReturn ONLY a Python regex string with exactly 2 "
                "capture groups: (section_number, section_name). Support "
                "em-dash (—), en-dash (–), and hyphen (-) separators. "
                "Example: r'(\\d+-\\d+(?:\\.\\d+)?)\\s*[—–-]\\s*(.+)'"
                "\n\nReturn ONLY the regex string, no explanation or "
                "markdown formatting."
            )

        try:
            model = get_model_for_task("fast")
            response = model.complete(prompt)
            pattern_str = self._clean_llm_regex(response)
            pattern = re.compile(pattern_str)
            # Validate: must match at least 3 headings
            matches = sum(1 for h in headings if pattern.match(h))
            if matches >= 3:
                logger.info(
                    f"LLM inferred {pattern_type} pattern "
                    f"({matches}/{len(headings)} matches): {pattern_str}"
                )
                return pattern
            else:
                logger.warning(
                    f"LLM {pattern_type} pattern matched only {matches} "
                    f"headings, discarding: {pattern_str}"
                )
                return None
        except Exception as e:
            logger.warning(f"LLM {pattern_type} pattern inference failed: {e}")
            return None

    @staticmethod
    def _clean_llm_regex(response: str) -> str:
        """Extract a clean regex string from LLM response."""
        text = response.strip()
        # Remove markdown code fences
        if "```" in text:
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        # Remove r-string prefix and quotes
        for prefix in ["r'", 'r"', "r'''", 'r"""']:
            if text.startswith(prefix):
                end_quote = prefix[1:]  # matching closing quote
                text = text[len(prefix):]
                if text.endswith(end_quote):
                    text = text[:-len(end_quote)]
                break
        # Remove bare quotes
        text = text.strip("'\"")
        return text

    @classmethod
    def for_jurisdiction(cls, jurisdiction_id: str, **kwargs) -> "MunicipalCodeCorpus":
        """
        Factory method that returns the appropriate parser for a jurisdiction.

        Routing order:
        1. Custom parser registered via @register_parser
        2. AmericanLegalCorpus if jurisdiction uses AMLegal
        3. Standard MunicipalCodeCorpus (Municode API)

        AMLegal jurisdictions are detected by:
        - Presence in AmericanLegalCorpus.JURISDICTION_MAP, or
        - data_sources.municipal_code == "amlegal" in jurisdiction YAML
        """
        if jurisdiction_id in _PARSER_REGISTRY:
            return _PARSER_REGISTRY[jurisdiction_id](jurisdiction_id, **kwargs)

        # Check if this jurisdiction uses American Legal Publishing
        if _is_amlegal_jurisdiction(jurisdiction_id):
            from .american_legal import AmericanLegalCorpus
            return AmericanLegalCorpus(jurisdiction_id, **kwargs)

        return cls(jurisdiction_id, **kwargs)

    def _infer_jurisdiction_info(self) -> dict:
        """Infer Municode lookup info from jurisdiction ID and YAML config.

        Attempts to derive (state, name) from:
        1. Jurisdiction YAML file (data/jurisdictions/{id}.yaml)
        2. Jurisdiction ID parsing (e.g., "city-san-rafael" -> "San Rafael", state from YAML)

        Returns dict with 'state', 'name', and optionally 'product_name'.
        """
        jid = self.jurisdiction_id

        # Try loading jurisdiction YAML for state info
        state = None
        yaml_name = None
        try:
            from pathlib import Path
            # Walk up to find repo root (contains data/jurisdictions/)
            p = Path(__file__).resolve()
            for parent in p.parents:
                yaml_path = parent / "data" / "jurisdictions" / f"{jid}.yaml"
                if yaml_path.exists():
                    import yaml
                    with open(yaml_path) as f:
                        data = yaml.safe_load(f)
                    if data:
                        state = data.get("state") or data.get("financial", {}).get("state")
                        yaml_name = data.get("display_name")
                    break
        except Exception:
            pass

        # Derive city/county name from jurisdiction ID
        # e.g., "city-san-rafael" -> "San Rafael", "county-marin" -> "Marin County"
        parts = jid.split("-", 1)
        if len(parts) == 2:
            level, slug = parts
            name = yaml_name or " ".join(w.capitalize() for w in slug.split("-"))
            if level == "county" and not name.lower().endswith("county"):
                name = f"{name} County"
        else:
            name = yaml_name or jid

        if not state:
            raise ValueError(
                f"Cannot infer state for {jid}. "
                f"Either add it to JURISDICTION_MAP or create data/jurisdictions/{jid}.yaml with a 'state' field."
            )

        # Counties often use "Municipal Code" instead of "Code of Ordinances"
        product_name = "Municipal Code" if jid.startswith("county-") else "Code of Ordinances"

        import logging
        logging.getLogger(__name__).info(f"Inferred Municode lookup: {name}, {state} (product: {product_name})")
        return {"state": state, "name": name, "product_name": product_name}

    def _get_client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=30.0,
                headers={"Accept": "application/json"},
            )
        return self._client

    def _rate_limit(self):
        """Apply rate limiting."""
        elapsed = time.time() - self._last_request
        min_interval = 1.0 / self.rate_limit
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request = time.time()

    def _fetch(self, endpoint: str, params: dict = None) -> dict:
        """Fetch from Municode API with rate limiting."""
        self._rate_limit()
        client = self._get_client()
        url = f"{self.BASE_URL}/{endpoint}"
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _discover_client(self) -> tuple[int, int, int]:
        """Discover client_id, product_id, and job_id for jurisdiction."""
        if self._client_id and self._product_id and self._job_id:
            return self._client_id, self._product_id, self._job_id

        # Look up jurisdiction info — check hardcoded map first, then infer
        if self.jurisdiction_id in self.JURISDICTION_MAP:
            jur_info = self.JURISDICTION_MAP[self.jurisdiction_id]
        else:
            jur_info = self._infer_jurisdiction_info()

        state = jur_info["state"]
        name = jur_info["name"]
        product_name = jur_info.get("product_name", "Code of Ordinances")

        # Check cache
        cache_key = f"{state}_{name}"
        if cache_key in _CLIENT_CACHE:
            cached = _CLIENT_CACHE[cache_key]
            return cached["client_id"], cached["product_id"], cached["job_id"]

        # Fetch clients for state
        clients = self._fetch("Clients/stateAbbr", {"stateAbbr": state})

        # Find matching client
        client_id = None
        for c in clients:
            if c["ClientName"].lower() == name.lower():
                client_id = c["ClientID"]
                break

        if not client_id:
            raise ValueError(f"Client not found in Municode: {name}, {state}")

        # Get product info
        product = self._fetch(
            "Products/name",
            {"clientId": client_id, "productName": product_name},
        )
        product_id = product["ProductID"]

        # Get latest job
        job = self._fetch(f"Jobs/latest/{product_id}")
        job_id = job["Id"]

        # Cache results
        _CLIENT_CACHE[cache_key] = {
            "client_id": client_id,
            "product_id": product_id,
            "job_id": job_id,
        }

        self._client_id = client_id
        self._product_id = product_id
        self._job_id = job_id

        return client_id, product_id, job_id

    def get_metadata(self) -> dict:
        """Get code metadata."""
        client_id, product_id, job_id = self._discover_client()
        job = self._fetch(f"Jobs/latest/{product_id}")

        return {
            "jurisdiction_id": self.jurisdiction_id,
            "client_id": client_id,
            "product_id": product_id,
            "job_id": job_id,
            "job_name": job.get("Name"),
            "publish_date": job.get("PublishDate"),
            "online_date": job.get("OnlineDate"),
            "banner_text": job.get("BannerText"),
            "source": "municode.com API",
        }

    def get_fingerprint(self) -> str:
        """Get current fingerprint: Municode job publish date.

        Lightweight — single API call to Jobs/latest.
        """
        meta = self.get_metadata()
        publish_date = meta.get("publish_date") or meta.get("online_date") or ""
        job_id = str(meta.get("job_id", ""))
        return f"municode:{job_id}:{publish_date}"

    def check_for_update(self, last_fingerprint: Optional[str] = None):
        """Check if the municipal code has been republished.

        Compares the current job publish date against the stored fingerprint.
        """
        from .refresh import ChangeSignal, ChangeStatus

        try:
            new_fp = self.get_fingerprint()
        except Exception as e:
            return ChangeSignal(
                status=ChangeStatus.ERROR,
                message=f"Failed to get Municode metadata: {e}",
            )

        if not last_fingerprint:
            return ChangeSignal(
                status=ChangeStatus.UNKNOWN,
                new_fingerprint=new_fp,
                message="No prior fingerprint — first fetch or unknown state",
            )

        if new_fp == last_fingerprint:
            return ChangeSignal(
                status=ChangeStatus.UNCHANGED,
                old_fingerprint=last_fingerprint,
                new_fingerprint=new_fp,
            )

        return ChangeSignal(
            status=ChangeStatus.CHANGED,
            old_fingerprint=last_fingerprint,
            new_fingerprint=new_fp,
            message=f"Job changed: {last_fingerprint} → {new_fp}",
        )

    def get_toc(self) -> list[dict]:
        """Get table of contents (top-level titles)."""
        _, product_id, job_id = self._discover_client()
        return self._fetch(
            "codesToc/children",
            {"jobId": job_id, "productId": product_id},
        )

    def _html_to_text(self, html: Optional[str]) -> str:
        """Convert HTML content to plain text."""
        if not html:
            return ""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)
        # Decode HTML entities
        text = unescape(text)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _extract_ordinance_history(self, html: Optional[str]) -> Optional[str]:
        """Extract ordinance history from HTML content."""
        if not html:
            return None
        match = re.search(r'class="historynote[^"]*"[^>]*>([^<]+)', html)
        if match:
            return match.group(1).strip()
        return None

    def _find_chapter_nodes(
        self,
        parent_id: str,
        job_id: int,
        product_id: int,
        max_depth: int = 3,
    ) -> Iterator[dict]:
        """
        Recursively find chapter nodes under a parent.

        Some titles have nested structures (Title > Division > Chapter).
        This method traverses the TOC tree to find actual chapter nodes.

        Args:
            parent_id: Node ID to search under
            job_id: Municode job ID
            product_id: Municode product ID
            max_depth: Maximum recursion depth (safety limit)

        Yields:
            TOC nodes that match the chapter pattern
        """
        if max_depth <= 0:
            return

        children = self._fetch(
            "codesToc/children",
            {"jobId": job_id, "productId": product_id, "nodeId": parent_id},
        )

        for child in children:
            heading = child.get("Heading", "")
            if self._chapter_pattern.match(heading):
                # This is a chapter node - yield it
                yield child
            elif child.get("HasChildren"):
                # Not a chapter (e.g., Division, Article) - recurse
                yield from self._find_chapter_nodes(
                    child["Id"], job_id, product_id, max_depth - 1
                )

    def _infer_section_pattern(self, doc_headings: list[str]) -> Optional[re.Pattern]:
        """Infer a section pattern from document headings.

        Strategy: LLM-first, hardcoded patterns as offline fallback.

        Returns a compiled regex with 2 capture groups (number, title), or None.
        """
        if not doc_headings:
            return None

        # Strategy 1: LLM inference
        llm_result = self._llm_infer_pattern(doc_headings, "section")
        if llm_result:
            return llm_result

        # Strategy 2: Hardcoded alternative patterns (offline fallback)
        alternative_patterns = [
            # "1-3.1 - Name" (Alameda-style: dash-separated with optional sub-number)
            r'(\d+-\d+(?:\.\d+)?[A-Za-z]?)\s*[—–-]\s*(.+)',
            # "§ 1-2-3 - Name"
            r'§\s*(\d+-\d+-\d+)\s*[—–-]\s*(.+)',
            # "Sec. 1-23 - Name"
            r'Sec\.\s*(\d+-\d+)\s*[—–-]\s*(.+)',
            # "1.02.030 - Name" (standard but with different separator)
            r'(\d+\.\d+\.\d+)\s*[—–-]\s*(.+)',
        ]

        for pattern_str in alternative_patterns:
            pattern = re.compile(pattern_str)
            matches = sum(1 for h in doc_headings if pattern.match(h))
            if matches >= 3:
                logger.info(
                    f"Inferred section pattern ({matches}/{len(doc_headings)} "
                    f"matches): {pattern_str}"
                )
                return pattern

        return None

    def _yield_sections_from_docs(
        self,
        docs: list[dict],
        chapter: str,
        chapter_title: str,
        title_number: str,
        title_name: str,
    ) -> Iterator[MunicipalCodeSection]:
        """Extract sections from CodesContent docs.

        Tries the configured section pattern first. If nothing matches,
        infers a section pattern from the doc headings.
        """
        # Collect headings to check pattern match rate
        headings = [doc.get("Title", "") for doc in docs]

        # Try configured pattern first
        section_pattern = self._section_pattern
        matched = sum(1 for h in headings if section_pattern.match(h))

        if matched == 0 and len(headings) > 3:
            # No matches — try to infer a section pattern
            inferred = self._infer_section_pattern(headings)
            if inferred:
                section_pattern = inferred
                # Cache for subsequent calls
                self._section_pattern = inferred

        for doc in docs:
            doc_id = doc.get("Id", "")
            heading = doc.get("Title", "")
            html_content = doc.get("Content", "")

            section_match = section_pattern.match(heading)
            if section_match:
                section_number = section_match.group(1)
                section_title = section_match.group(2).strip()

                full_text = self._html_to_text(html_content)
                ordinance_history = self._extract_ordinance_history(html_content)

                yield MunicipalCodeSection(
                    section_number=section_number,
                    section_title=section_title,
                    full_text=full_text,
                    chapter=chapter,
                    chapter_title=chapter_title,
                    title_number=title_number,
                    title_name=title_name,
                    node_id=doc_id,
                    ordinance_history=ordinance_history,
                )

    def stream_sections(
        self,
        title_ids: Optional[list[str]] = None,
    ) -> Iterator[MunicipalCodeSection]:
        """
        Stream code sections from Municode API.

        Args:
            title_ids: Optional list of title node IDs to fetch.
                      If None, fetches all titles.

        Yields:
            MunicipalCodeSection for each code section
        """
        _, product_id, job_id = self._discover_client()

        # Get top-level TOC
        toc = self.get_toc()

        # Filter to actual title nodes (skip charter, tables, etc.)
        # Use title pattern to identify valid titles
        titles = []
        for node in toc:
            heading = node.get("Heading", "")
            if self._title_pattern.match(heading) and node.get("HasChildren", False):
                titles.append(node)

        if not titles:
            # Try LLM-based pattern inference before giving up
            headings = [n.get("Heading", "") for n in toc if n.get("HasChildren", False)]
            inferred = self._infer_title_pattern(headings)
            if inferred:
                logger.info(
                    f"Inferred title pattern for {self.jurisdiction_id}: "
                    f"{inferred.pattern}"
                )
                self._title_pattern = inferred
                for node in toc:
                    heading = node.get("Heading", "")
                    if self._title_pattern.match(heading) and node.get("HasChildren", False):
                        titles.append(node)

            if not titles:
                all_headings = [n.get("Heading", "") for n in toc[:10]]
                logger.warning(
                    f"No TOC nodes matched title pattern for {self.jurisdiction_id}. "
                    f"TOC has {len(toc)} nodes. Headings: {all_headings}. "
                    f"Pattern: {self._title_pattern.pattern}"
                )
                return

        if title_ids:
            titles = [t for t in titles if t["Id"] in title_ids]

        for title_node in titles:
            title_id = title_node["Id"]
            title_heading = title_node["Heading"]

            # Parse title number and name using configurable pattern
            title_match = self._title_pattern.match(title_heading)
            if title_match:
                title_number = title_match.group(1)
                title_name = title_match.group(2).strip()
            else:
                title_number = ""
                title_name = title_heading

            # Find chapter nodes (handles nested structures like Title > Division > Chapter)
            chapter_nodes = list(self._find_chapter_nodes(title_id, job_id, product_id))

            if not chapter_nodes:
                # Fallback: fetch content directly from the title node.
                # Many codes (e.g., Alameda) have sections directly under the
                # top-level division, with no intermediate "Chapter" layer.
                # CodesContent on the title node returns all nested sections.
                logger.debug(
                    f"No chapter nodes found under {title_heading}, "
                    "fetching content from title node directly"
                )
                chapter_nodes = [title_node]

            for chapter_node in chapter_nodes:
                chapter_id = chapter_node["Id"]
                chapter_heading = chapter_node.get("Heading", "")

                # Parse chapter from heading
                chapter_match = self._chapter_pattern.match(chapter_heading)
                if chapter_match:
                    current_chapter = chapter_match.group(1)
                    current_chapter_title = chapter_match.group(2).strip()
                else:
                    current_chapter = ""
                    current_chapter_title = chapter_heading

                # Fetch content at chapter level (or title level for fallback)
                content = self._fetch(
                    "CodesContent",
                    {"jobId": job_id, "productId": product_id, "nodeId": chapter_id},
                )

                docs = content.get("Docs", [])

                yield from self._yield_sections_from_docs(
                    docs, current_chapter, current_chapter_title,
                    title_number, title_name,
                )

    def get_sections_list(
        self,
        title_ids: Optional[list[str]] = None,
    ) -> list[MunicipalCodeSection]:
        """Get all sections as a list."""
        return list(self.stream_sections(title_ids))

    def to_documents(
        self,
        title_ids: Optional[list[str]] = None,
    ) -> Iterator[dict]:
        """
        Convert sections to document format for indexing.

        Yields documents matching VECTOR_RAG_SCHEMA.md municipal_code spec:
        - id: {jurisdiction_id}-muni-{section}
        - text: Formatted for embedding
        - metadata: Flat types only (string, int, float, bool)
        """
        for section in self.stream_sections(title_ids):
            # Build document ID per schema
            # city-san-rafael-muni-1-04-010
            section_parts = section.section_number.replace('.', '-')
            doc_id = f"{self.jurisdiction_id}-muni-{section_parts}"

            # Build text representation per schema
            text = f"""Chapter: {section.chapter} - {section.chapter_title}
Section: {section.section_number}
Title: {section.section_title}
Full Text: {section.full_text}"""

            # Build metadata (flat types only)
            metadata = {
                "muni_code_id": doc_id,
                "chapter": section.chapter,
                "section": section.section_number,
                "chapter_title": section.chapter_title[:500],
                "section_title": section.section_title[:200],
                "jurisdiction_id": self.jurisdiction_id,
                "title_number": section.title_number,
                "title_name": section.title_name,
                "hierarchy_level": 2,  # Section level
                "node_id": section.node_id,
            }

            if section.ordinance_history:
                metadata["ordinance_history"] = section.ordinance_history[:200]

            yield {
                "id": doc_id,
                "text": text,
                "metadata": metadata,
            }

    def close(self):
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None


def parse_municipal_code(
    jurisdiction_id: str = "city-san-rafael",
    title_ids: Optional[list[str]] = None,
) -> list[dict]:
    """
    Convenience function to fetch municipal code.

    Args:
        jurisdiction_id: Jurisdiction identifier
        title_ids: Optional list of title node IDs to fetch

    Returns:
        List of document dicts ready for indexing
    """
    corpus = MunicipalCodeCorpus(jurisdiction_id)
    try:
        return list(corpus.to_documents(title_ids))
    finally:
        corpus.close()


# Keep old name for backwards compatibility
def parse_municipal_code_pdf(
    pdf_path: str | Path,
    jurisdiction_id: str = "city-san-rafael",
) -> list[dict]:
    """
    Legacy function - now uses Municode API instead of PDF.

    Args:
        pdf_path: Ignored (kept for API compatibility)
        jurisdiction_id: Jurisdiction identifier

    Returns:
        List of document dicts ready for indexing
    """
    return parse_municipal_code(jurisdiction_id)
