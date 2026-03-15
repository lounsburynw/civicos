"""
Municipal code corpus via American Legal Publishing (codelibrary.amlegal.com).

Downloads the full municipal code as a text file via AMLegal's export feature,
then parses sections using deterministic format detection with LLM fallback.

AMLegal covers ~20% of US municipalities (1,900+), complementing Municode (~60%).

Format Detection Strategy:
  1. Try all known patterns (built-in + learned) against the text
  2. Pick the combination with the most matches
  3. If results are poor (< 0.1 sections/KB), trigger LLM fallback
  4. LLM classifies sample lines → derives new patterns
  5. New patterns are saved to custom_patterns.json for future use
  6. Re-run deterministic detection (now includes the learned patterns)

NOTE: Cloudflare blocks headless browsers, so headed mode (visible browser
window) is required. This is fine for batch extraction jobs.

Adding a New Municipality
=========================

1. FIND THE SLUG: Visit https://codelibrary.amlegal.com/regions/{state_abbr}
   and find the municipality. The URL will be /codes/{slug}/latest/overview.

2. FIND THE CODE ID: Click into the code. The URL will be
   /codes/{slug}/latest/{code_id}/0-0-0-{root_id}.

3. ADD TO JURISDICTION_MAP:

    JURISDICTION_MAP = {
        "city-sacramento": {
            "state": "CA",
            "slug": "sacramentoca",
            "code_id": "sacramento_ca",
        },
    }
"""

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from .municipal import MunicipalCodeSection


# ---------------------------------------------------------------------------
# Built-in pattern candidates (learned from Sacramento, Gridley, Fairfax, Pinole)
# ---------------------------------------------------------------------------

BUILTIN_TITLE_PATTERNS = [
    (r"^Title\s+(?P<number>\d+)\s*$", True),
    (r"^TITLE\s+(?P<number>\d+)\s*$", True),
    (r"^(?:Title|TITLE)\s+(?P<number>\d+)\s*$", True),
    (r"^TITLE\s+(?P<number>\d+)\s*:\s*(?P<name>.+)$", False),
]

BUILTIN_CHAPTER_PATTERNS = [
    (r"^Chapter\s+(?P<number>[\d.]+)\s*$", True),
    (r"^Chapter\s+(?P<number>[\d.]+)\s+(?P<name>.+)$", False),
    (r"^CHAPTER\s+(?P<number>[\d.]+)\s*:\s*(?P<name>.+)$", False),
    (r"^CHAPTER\s+(?P<number>[\d.]+)\s+(?P<name>.+)$", False),
]

BUILTIN_SECTION_PATTERNS = [
    r"^(?P<number>[\d.]+[A-Za-z]?)\s{2,}(?P<name>.+)",
    r"^§\s*(?P<number>[\d.]+[A-Za-z]?)\s+(?P<name>.+)",
    r"^(?P<number>[\d.]+[A-Za-z]?)\s(?P<name>.+)",
]

# Quality threshold: sections per KB of text.
# AMLegal exports typically yield 0.5-2 sections/KB.
MIN_SECTIONS_PER_KB = 0.1


# ---------------------------------------------------------------------------
# LLM classification prompt (for fallback)
# ---------------------------------------------------------------------------

LLM_CLASSIFICATION_PROMPT = """\
You are analyzing a municipal code text export. I will show you numbered lines
from the document. For each line, classify it as one of:

- TITLE_HEADER: A structural title header (e.g., "Title 1", "TITLE 5: ZONING")
- TITLE_NAME: The name line following a two-line title header
- CHAPTER_HEADER: A structural chapter header (e.g., "Chapter 1.01", "CHAPTER 1.04: RULES")
- CHAPTER_NAME: The name line following a two-line chapter header
- SECTION_CONTENT: A section header that begins actual section content (followed by body text)
- SECTION_TOC: A section listing in a table of contents (followed by more listings)
- TOC_MARKER: A line like "Chapters:", "Sections:" that introduces a TOC block

CRITICAL DISTINCTIONS:
- SECTION_CONTENT vs SECTION_TOC: Both may show "1.01.010 Title." but CONTENT lines
  are followed by body text (indented paragraphs), while TOC lines are followed by
  more section listings or blank lines.
- Two-line vs one-line: If "Title 1" appears alone (no name), the NEXT line is
  TITLE_NAME. If "TITLE 1: GENERAL PROVISIONS" has the name, there's no TITLE_NAME.

Return JSON: {"classifications": [{"line": N, "text": "...", "type": "TYPE"}, ...]}

Only include lines that are TITLE_HEADER, TITLE_NAME, CHAPTER_HEADER, CHAPTER_NAME,
SECTION_CONTENT, or TOC_MARKER. Omit BODY/SKIP lines.

LINES TO CLASSIFY:
"""


# ---------------------------------------------------------------------------
# Pattern detection (deterministic + LLM fallback)
# ---------------------------------------------------------------------------

def _load_custom_patterns(custom_path: Path) -> dict:
    """Load learned patterns from custom_patterns.json."""
    if custom_path.exists():
        with open(custom_path) as f:
            return json.load(f)
    return {"title": [], "chapter": [], "section": []}


def _save_custom_patterns(custom_path: Path, patterns: dict) -> None:
    """Save learned patterns to custom_patterns.json."""
    custom_path.parent.mkdir(parents=True, exist_ok=True)
    with open(custom_path, "w") as f:
        json.dump(patterns, f, indent=2)
    logger.info(f"Saved learned patterns to {custom_path}")


def _detect_format_deterministic(
    lines: list[str],
    custom_patterns: Optional[dict] = None,
) -> dict:
    """Detect format by trying all known patterns and picking the best matches.

    Combines built-in patterns with any learned patterns from custom_patterns.json.
    """
    # Merge built-in + custom candidates
    title_candidates = list(BUILTIN_TITLE_PATTERNS)
    chapter_candidates = list(BUILTIN_CHAPTER_PATTERNS)
    section_candidates = list(BUILTIN_SECTION_PATTERNS)

    if custom_patterns:
        for entry in custom_patterns.get("title", []):
            title_candidates.append((entry["pattern"], entry["two_line"]))
        for entry in custom_patterns.get("chapter", []):
            chapter_candidates.append((entry["pattern"], entry["two_line"]))
        for p in custom_patterns.get("section", []):
            section_candidates.append(p)

    # --- Title ---
    title_pattern, title_two_line = _pick_best(lines, title_candidates, min_matches=3)

    # --- Chapter ---
    chapter_pattern, chapter_two_line = _pick_best(lines, chapter_candidates, min_matches=5)

    # --- Skip preamble (find first title) ---
    skip_until = 0
    title_re = re.compile(title_pattern)
    for idx, line in enumerate(lines):
        if title_re.match(line):
            skip_until = max(0, idx - 2)
            break

    # --- Section ---
    code_lines = lines[skip_until:]
    section_sym_pat = re.compile(r"^§\s*(?P<number>[\d.]+[A-Za-z]?)\s+(?P<name>.+)")
    sym_count = sum(1 for line in code_lines if section_sym_pat.match(line))

    if sym_count >= 100:
        section_pattern = r"^§\s*(?P<number>[\d.]+[A-Za-z]?)\s+(?P<name>.+)"
    else:
        section_pattern = _pick_best_section(code_lines, section_candidates, min_matches=50)

    # --- TOC markers ---
    toc_markers = []
    for marker in ["Chapters", "Sections", "Articles", "Chapter", "Section"]:
        pat = re.compile(f"^{marker}\\s*:?\\s*$")
        if any(pat.match(line) for line in lines[:500]):
            toc_markers.append(marker)

    return {
        "title_pattern": title_pattern,
        "title_two_line": title_two_line,
        "chapter_pattern": chapter_pattern,
        "chapter_two_line": chapter_two_line,
        "section_pattern": section_pattern,
        "toc_markers": toc_markers,
        "skip_until_line": skip_until,
        "notes": "Detected deterministically by pattern matching.",
    }


def _pick_best(lines: list[str], candidates: list[tuple], min_matches: int = 3) -> tuple:
    """Pick the (pattern, two_line) tuple with the most matches."""
    best_pattern, best_two_line, best_count = candidates[0][0], candidates[0][1], 0
    for pattern, two_line in candidates:
        count = sum(1 for line in lines if re.compile(pattern).match(line))
        if count > best_count and count >= min_matches:
            best_pattern, best_two_line, best_count = pattern, two_line, count
    return best_pattern, best_two_line


def _pick_best_section(lines: list[str], candidates: list[str], min_matches: int = 50) -> str:
    """Pick the section pattern with the most matches."""
    best_pattern, best_count = candidates[0], 0
    for pattern in candidates:
        count = sum(1 for line in lines if re.compile(pattern).match(line))
        if count > best_count and count >= min_matches:
            best_pattern, best_count = pattern, count
    return best_pattern


# ---------------------------------------------------------------------------
# LLM fallback: classify lines → derive patterns → persist
# ---------------------------------------------------------------------------

def _llm_derive_patterns(text: str) -> dict:
    """Use LLM to classify sample lines, then derive regex patterns.

    Returns a dict with title/chapter/section patterns suitable for
    appending to custom_patterns.json.
    """
    import openai

    lines = text.split("\n")
    total = len(lines)

    # Sample from 3 regions: beginning, ~25%, ~50%
    sample_lines = []
    for start in [0, total // 4, total // 2]:
        for idx in range(start, min(start + 80, total)):
            sample_lines.append((idx + 1, lines[idx]))

    numbered = "\n".join(f"[{num}] {txt}" for num, txt in sample_lines)

    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are an expert at analyzing structured municipal code text. Return only valid JSON.",
            },
            {"role": "user", "content": LLM_CLASSIFICATION_PROMPT + numbered},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    result = json.loads(response.choices[0].message.content)
    classifications = result.get("classifications", [])

    # Group by type
    by_type: dict[str, list[dict]] = {}
    for c in classifications:
        by_type.setdefault(c.get("type", "SKIP"), []).append(c)

    new_patterns: dict[str, list] = {"title": [], "chapter": [], "section": []}

    # Derive title pattern from examples
    title_examples = by_type.get("TITLE_HEADER", [])
    has_title_name = len(by_type.get("TITLE_NAME", [])) > 0
    if title_examples:
        pat = _pattern_from_example(title_examples[0].get("text", ""), "title", has_title_name)
        if pat:
            new_patterns["title"].append({"pattern": pat, "two_line": has_title_name})

    # Derive chapter pattern from examples
    chapter_examples = by_type.get("CHAPTER_HEADER", [])
    has_chapter_name = len(by_type.get("CHAPTER_NAME", [])) > 0
    if chapter_examples:
        pat = _pattern_from_example(chapter_examples[0].get("text", ""), "chapter", has_chapter_name)
        if pat:
            new_patterns["chapter"].append({"pattern": pat, "two_line": has_chapter_name})

    # Derive section pattern from examples
    section_examples = by_type.get("SECTION_CONTENT", [])
    if section_examples:
        pat = _pattern_from_example(section_examples[0].get("text", ""), "section", False)
        if pat:
            new_patterns["section"].append(pat)

    logger.info(
        f"LLM derived patterns: "
        f"{len(new_patterns['title'])} title, "
        f"{len(new_patterns['chapter'])} chapter, "
        f"{len(new_patterns['section'])} section"
    )
    return new_patterns


def _pattern_from_example(example: str, element_type: str, two_line: bool) -> Optional[str]:
    """Derive a regex pattern from a single classified example line."""
    example = example.strip()
    if not example:
        return None

    if element_type == "title":
        # "Title 1", "TITLE 1", "TITLE 1: NAME", "Article I", etc.
        m = re.match(r"^(Title|TITLE|Article|ARTICLE)\s+(\d+|[IVXLCDM]+)\s*:\s*(.+)$", example)
        if m:
            word = m.group(1)
            num_pat = r"\d+" if m.group(2).isdigit() else r"[IVXLCDM]+"
            return f"^{word}\\s+(?P<number>{num_pat})\\s*:\\s*(?P<name>.+)$"
        m = re.match(r"^(Title|TITLE|Article|ARTICLE)\s+(\d+|[IVXLCDM]+)\s*$", example)
        if m:
            word = m.group(1)
            num_pat = r"\d+" if m.group(2).isdigit() else r"[IVXLCDM]+"
            return f"^{word}\\s+(?P<number>{num_pat})\\s*$"

    elif element_type == "chapter":
        # "Chapter 1.01", "CHAPTER 1.04: NAME", "Ch. 1-2", "Part 1", etc.
        m = re.match(r"^(Chapter|CHAPTER|Part|PART|Ch\.?)\s+([\d.\-]+)\s*:\s*(.+)$", example)
        if m:
            word = re.escape(m.group(1))
            return f"^{word}\\s+(?P<number>[\\d.\\-]+)\\s*:\\s*(?P<name>.+)$"
        m = re.match(r"^(Chapter|CHAPTER|Part|PART|Ch\.?)\s+([\d.\-]+)\s+(\S.+)$", example)
        if m:
            word = re.escape(m.group(1))
            return f"^{word}\\s+(?P<number>[\\d.\\-]+)\\s+(?P<name>.+)$"
        m = re.match(r"^(Chapter|CHAPTER|Part|PART|Ch\.?)\s+([\d.\-]+)\s*$", example)
        if m:
            word = re.escape(m.group(1))
            return f"^{word}\\s+(?P<number>[\\d.\\-]+)\\s*$"

    elif element_type == "section":
        # "§ 1.04.010 NAME", "Sec. 1-2-3 NAME", "1.01.010   Name"
        if example.startswith("§"):
            return r"^§\s*(?P<number>[\d.\-]+[A-Za-z]?)\s+(?P<name>.+)"
        m = re.match(r"^(Sec\.?)\s+([\d.\-]+)\s+(.+)$", example)
        if m:
            return r"^Sec\.?\s+(?P<number>[\d.\-]+[A-Za-z]?)\s+(?P<name>.+)"
        if re.match(r"^[\d.]+[A-Za-z]?\s{2,}", example):
            return r"^(?P<number>[\d.\-]+[A-Za-z]?)\s{2,}(?P<name>.+)"
        if re.match(r"^[\d.]+[A-Za-z]?\s\S", example):
            return r"^(?P<number>[\d.\-]+[A-Za-z]?)\s(?P<name>.+)"

    return None


# ---------------------------------------------------------------------------
# Text parser
# ---------------------------------------------------------------------------

def _parse_text(text: str, format_spec: dict) -> list[MunicipalCodeSection]:
    """Parse municipal code text using format patterns."""
    lines = text.split("\n")

    title_re = re.compile(format_spec["title_pattern"])
    chapter_re = re.compile(format_spec["chapter_pattern"])
    section_re = re.compile(format_spec["section_pattern"])
    title_two_line = format_spec.get("title_two_line", False)
    chapter_two_line = format_spec.get("chapter_two_line", False)
    toc_markers = [m.lower() for m in format_spec.get("toc_markers", [])]
    skip_until = format_spec.get("skip_until_line", 0)
    history_re = re.compile(r"\((?:Ord\.|Prior code).*\)\s*$")

    sections = []
    t_num = t_name = ch = ch_title = ""
    s_num = s_title = None
    body = []
    in_toc = False

    def flush():
        nonlocal s_num
        if s_num and body:
            ft = "\n".join(body).strip()
            if ft:
                hist = None
                hm = history_re.search(ft)
                if hm:
                    hist = hm.group(0).strip("() ")
                sections.append(MunicipalCodeSection(
                    section_number=s_num, section_title=s_title or "",
                    full_text=ft, chapter=ch, chapter_title=ch_title,
                    title_number=t_num, title_name=t_name,
                    node_id="", ordinance_history=hist,
                ))

    def valid_sec(sn):
        if not ch:
            return False
        cp = ch.rstrip(".")
        return sn.startswith(cp + ".") or sn.startswith(cp.split(".")[0] + ".")

    i = max(skip_until, 0)
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.lower().rstrip(":") in toc_markers or stripped.lower() in toc_markers:
            in_toc = True
            i += 1
            continue

        if not stripped:
            i += 1
            continue

        m = title_re.match(line)
        if m:
            flush()
            s_num = None
            body = []
            t_num = m.group("number")
            if title_two_line:
                t_name = lines[i + 1].strip() if i + 1 < len(lines) else ""
                i += 2
            else:
                t_name = m.group("name").strip() if "name" in m.groupdict() else ""
                i += 1
            in_toc = False
            continue

        m = chapter_re.match(line)
        if m:
            flush()
            s_num = None
            body = []
            ch = m.group("number").rstrip(".")
            if chapter_two_line:
                ch_title = lines[i + 1].strip() if i + 1 < len(lines) else ""
                i += 2
            else:
                ch_title = m.group("name").strip() if "name" in m.groupdict() else ""
                i += 1
            in_toc = False
            continue

        m = section_re.match(line)
        if m and ch:
            sn = m.group("number").rstrip(".")
            if valid_sec(sn):
                flush()
                s_num = sn
                s_title = m.group("name").strip().rstrip(".") if "name" in m.groupdict() else ""
                body = []
                in_toc = False
                i += 1
                continue

        if in_toc:
            i += 1
            continue

        if s_num is not None:
            body.append(line.rstrip())

        i += 1

    flush()
    return sections


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class AmericanLegalCorpus:
    """
    Fetch municipal code from American Legal Publishing.

    Downloads the full code as plain text via the AMLegal export feature,
    then parses sections using deterministic format detection. If the
    deterministic approach yields poor results, an LLM fallback derives
    new patterns and persists them for future use.
    """

    BASE_URL = "https://codelibrary.amlegal.com"

    JURISDICTION_MAP = {
        "city-sacramento": {"state": "CA", "slug": "sacramentoca", "code_id": "sacramento_ca"},
        "city-losangeles": {"state": "CA", "slug": "los_angeles", "code_id": "lamc"},
        "city-sanfrancisco": {"state": "CA", "slug": "san_francisco", "code_id": "sf_admin"},
        "city-chicago": {"state": "IL", "slug": "chicago", "code_id": "chicago_il"},
        "city-gridley": {"state": "CA", "slug": "gridley", "code_id": "gridley_ca"},
        "city-fairfax": {"state": "CA", "slug": "fairfax", "code_id": "fairfax_ca"},
        "city-pinole": {"state": "CA", "slug": "pinole", "code_id": "pinole_ca"},
    }

    def __init__(
        self,
        jurisdiction_id: str = "city-sacramento",
        headless: bool = False,
        cache_dir: Optional[str] = None,
        **kwargs,
    ):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "playwright is required for American Legal Publishing. "
                "Install with: pip install playwright && playwright install chromium"
            )
        self.jurisdiction_id = jurisdiction_id
        self.headless = headless
        if cache_dir:
            self._cache_dir = Path(cache_dir)
        else:
            p = Path(__file__).resolve()
            for parent in p.parents:
                if (parent / "data" / "jurisdictions").is_dir():
                    self._cache_dir = parent / "data" / "municipal_code"
                    break
            else:
                self._cache_dir = Path("data/municipal_code")

    def _get_jurisdiction_info(self) -> dict:
        if self.jurisdiction_id in self.JURISDICTION_MAP:
            return self.JURISDICTION_MAP[self.jurisdiction_id]
        try:
            import yaml
            p = Path(__file__).resolve()
            for parent in p.parents:
                yaml_path = parent / "data" / "jurisdictions" / f"{self.jurisdiction_id}.yaml"
                if yaml_path.exists():
                    with open(yaml_path) as f:
                        data = yaml.safe_load(f)
                    if data and data.get("data_sources", {}).get("municipal_code") == "amlegal":
                        ac = data.get("amlegal", {})
                        if ac.get("slug") and ac.get("code_id"):
                            return {
                                "state": data.get("state") or data.get("financial", {}).get("state"),
                                "slug": ac["slug"], "code_id": ac["code_id"],
                            }
                    break
        except Exception:
            pass
        raise ValueError(
            f"Jurisdiction {self.jurisdiction_id} not found in JURISDICTION_MAP. "
            f"Add it with slug and code_id from codelibrary.amlegal.com."
        )

    def _cached_text_path(self) -> Path:
        return self._cache_dir / f"{self._get_jurisdiction_info()['slug']}.txt"

    def _cached_format_path(self) -> Path:
        return self._cache_dir / f"{self._get_jurisdiction_info()['slug']}.format.json"

    def _custom_patterns_path(self) -> Path:
        return self._cache_dir / "custom_patterns.json"

    async def _download_text(self) -> str:
        """Download the full municipal code as text via AMLegal export."""
        jur = self._get_jurisdiction_info()
        slug, code_id = jur["slug"], jur["code_id"]

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=self.headless)
        page = await browser.new_page()

        try:
            root_url = f"{self.BASE_URL}/codes/{slug}/latest/{code_id}/0-0-0-1"
            logger.info(f"Navigating to {root_url}")
            try:
                await page.goto(root_url, wait_until="commit", timeout=60000)
            except Exception:
                pass

            for _ in range(30):
                if "Just a moment" not in await page.title():
                    break
                await asyncio.sleep(1)
            await asyncio.sleep(3)

            for btn in await page.query_selector_all('button[title="Download"]'):
                if await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(2)
                    break

            checkboxes = page.locator('.modal input[type="checkbox"]')
            total = await checkboxes.count()
            logger.info(f"Selecting all {total} code sections")
            for idx in range(total):
                cb = checkboxes.nth(idx)
                if not await cb.is_checked():
                    await cb.click(force=True)
                    await asyncio.sleep(0.1)

            await page.locator('.modal button.btn-primary:has-text("Download")').click()
            await asyncio.sleep(2)

            logger.info("Requesting text export...")
            await page.locator('.modal :text("Save Text")').click()
            await asyncio.sleep(3)

            logger.info("Waiting for server-side export...")
            for idx in range(450):
                exports = await page.evaluate(
                    "document.querySelector('.exports')?.innerText || ''"
                )
                if "OPEN" in exports:
                    logger.info(f"Export ready after {idx * 2}s")
                    break
                if idx % 15 == 0:
                    logger.info(f"  Still preparing... ({idx * 2}s)")
                await asyncio.sleep(2)
            else:
                raise TimeoutError("Export timed out after 15 minutes")

            async with page.expect_download(timeout=60000) as dl_info:
                await page.locator('.exports :text("OPEN")').click()
            download = await dl_info.value

            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = self._cached_text_path()
            await download.save_as(str(cache_path))
            logger.info(f"Downloaded {os.path.getsize(cache_path):,} bytes to {cache_path}")

            with open(cache_path, "r", errors="replace") as f:
                return f.read()
        finally:
            await browser.close()
            await pw.stop()

    def _get_text(self) -> str:
        cache_path = self._cached_text_path()
        if cache_path.exists():
            logger.info(f"Using cached text: {cache_path}")
            with open(cache_path, "r", errors="replace") as f:
                return f.read()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self._download_text()).result()
        return asyncio.run(self._download_text())

    def _detect_format(self, text: str) -> dict:
        """Detect text format: deterministic first, LLM fallback if poor results.

        If the deterministic approach yields < MIN_SECTIONS_PER_KB, triggers
        the LLM to classify sample lines, derives new patterns, saves them
        to custom_patterns.json, and re-runs detection.
        """
        lines = text.split("\n")
        custom_path = self._custom_patterns_path()
        custom = _load_custom_patterns(custom_path)

        # First pass: deterministic
        spec = _detect_format_deterministic(lines, custom)
        sections = _parse_text(text, spec)
        text_kb = len(text) / 1024
        sections_per_kb = len(sections) / text_kb if text_kb > 0 else 0

        if sections_per_kb >= MIN_SECTIONS_PER_KB:
            logger.info(
                f"Format detected deterministically: {len(sections)} sections "
                f"({sections_per_kb:.2f}/KB)"
            )
            return spec

        # Fallback: LLM derives new patterns
        logger.warning(
            f"Poor deterministic results: {len(sections)} sections "
            f"({sections_per_kb:.2f}/KB < {MIN_SECTIONS_PER_KB}). "
            f"Triggering LLM fallback..."
        )

        new_patterns = _llm_derive_patterns(text)

        # Merge into custom patterns (dedup by pattern string)
        existing_title_pats = {e["pattern"] for e in custom.get("title", [])}
        for entry in new_patterns.get("title", []):
            if entry["pattern"] not in existing_title_pats:
                custom.setdefault("title", []).append(entry)

        existing_ch_pats = {e["pattern"] for e in custom.get("chapter", [])}
        for entry in new_patterns.get("chapter", []):
            if entry["pattern"] not in existing_ch_pats:
                custom.setdefault("chapter", []).append(entry)

        existing_sec_pats = set(custom.get("section", []))
        for pat in new_patterns.get("section", []):
            if pat not in existing_sec_pats:
                custom.setdefault("section", []).append(pat)

        _save_custom_patterns(custom_path, custom)

        # Re-run deterministic with expanded pattern library
        spec = _detect_format_deterministic(lines, custom)
        sections = _parse_text(text, spec)
        new_spk = len(sections) / text_kb if text_kb > 0 else 0

        # Safety net: if LLM learned title/chapter but missed section pattern,
        # inject the standard section patterns as fallback candidates
        if new_spk < MIN_SECTIONS_PER_KB:
            logger.warning("LLM fallback still insufficient. Trying standard section patterns...")
            for fallback_pat in [
                r"^(?P<number>[\d.]+[A-Za-z]?)\s{2,}(?P<name>.+)",
                r"^§\s*(?P<number>[\d.]+[A-Za-z]?)\s+(?P<name>.+)",
                r"^(?P<number>[\d.]+[A-Za-z]?)\s(?P<name>.+)",
            ]:
                if fallback_pat not in custom.get("section", []):
                    custom.setdefault("section", []).append(fallback_pat)
            _save_custom_patterns(custom_path, custom)
            spec = _detect_format_deterministic(lines, custom)
            sections = _parse_text(text, spec)
            new_spk = len(sections) / text_kb if text_kb > 0 else 0

        logger.info(
            f"After LLM fallback: {len(sections)} sections "
            f"({new_spk:.2f}/KB)"
        )
        return spec

    @staticmethod
    def _parse_text(text: str, format_spec: dict) -> list[MunicipalCodeSection]:
        return _parse_text(text, format_spec)

    def _get_format_spec(self, text: str) -> dict:
        fmt_path = self._cached_format_path()
        if fmt_path.exists():
            logger.info(f"Using cached format: {fmt_path}")
            with open(fmt_path) as f:
                return json.load(f)
        spec = self._detect_format(text)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        with open(fmt_path, "w") as f:
            json.dump(spec, f, indent=2)
        logger.info(f"Format spec cached to {fmt_path}")
        return spec

    def stream_sections(self, title_ids: Optional[list[str]] = None) -> Iterator[MunicipalCodeSection]:
        text = self._get_text()
        spec = self._get_format_spec(text)
        sections = self._parse_text(text, spec)
        if title_ids:
            sections = [s for s in sections if s.title_number in title_ids]
        yield from sections

    def get_sections_list(self, title_ids: Optional[list[str]] = None) -> list[MunicipalCodeSection]:
        return list(self.stream_sections(title_ids))

    def to_documents(self, title_ids: Optional[list[str]] = None) -> Iterator[dict]:
        for section in self.stream_sections(title_ids):
            doc_id = f"{self.jurisdiction_id}-muni-{section.section_number.replace('.', '-')}"
            text = (
                f"Chapter: {section.chapter} - {section.chapter_title}\n"
                f"Section: {section.section_number}\n"
                f"Title: {section.section_title}\n"
                f"Full Text: {section.full_text}"
            )
            metadata = {
                "muni_code_id": doc_id,
                "chapter": section.chapter,
                "section": section.section_number,
                "chapter_title": section.chapter_title[:500],
                "section_title": section.section_title[:200],
                "jurisdiction_id": self.jurisdiction_id,
                "title_number": section.title_number,
                "title_name": section.title_name,
                "hierarchy_level": 2,
                "node_id": section.node_id,
            }
            if section.ordinance_history:
                metadata["ordinance_history"] = section.ordinance_history[:200]
            yield {"id": doc_id, "text": text, "metadata": metadata}

    def close(self):
        pass
