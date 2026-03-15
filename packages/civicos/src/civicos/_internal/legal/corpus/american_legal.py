"""
Municipal code corpus via American Legal Publishing (codelibrary.amlegal.com).

Downloads the full municipal code as a text file via AMLegal's export feature,
then parses sections from the structured plain text.

AMLegal covers ~20% of US municipalities (1,900+), complementing Municode (~60%).

Approach:
  1. Open the code page in Playwright (headed, for Cloudflare)
  2. Open the Download dialog → select all titles → Save Text
  3. Wait for server-side export (~2-4 min for full code)
  4. Download the .txt file
  5. Parse the structured text into MunicipalCodeSection objects

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
import logging
import os
import re
import time
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

try:
    from playwright.async_api import async_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

# Reuse the shared data class from the Municode module
from .municipal import MunicipalCodeSection


class AmericanLegalCorpus:
    """
    Fetch municipal code from American Legal Publishing.

    Downloads the full code as plain text via the AMLegal export feature,
    then parses sections locally. Much simpler and more complete than
    scraping the SPA page by page.

    Args:
        jurisdiction_id: Jurisdiction identifier (e.g., "city-sacramento")
        headless: Run browser in headless mode (default: False, Cloudflare blocks headless)
        cache_dir: Directory to cache downloaded text files (default: data/municipal_code)
    """

    BASE_URL = "https://codelibrary.amlegal.com"

    # Known jurisdiction mappings
    JURISDICTION_MAP = {
        "city-sacramento": {
            "state": "CA",
            "slug": "sacramentoca",
            "code_id": "sacramento_ca",
        },
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
            # Default: data/municipal_code/ relative to repo root
            # Walk up from this file to find the repo root (has data/jurisdictions/)
            p = Path(__file__).resolve()
            for parent in p.parents:
                if (parent / "data" / "jurisdictions").is_dir():
                    self._cache_dir = parent / "data" / "municipal_code"
                    break
            else:
                self._cache_dir = Path("data/municipal_code")

    def _get_jurisdiction_info(self) -> dict:
        """Get jurisdiction config from map or infer from YAML."""
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
                        amlegal_config = data.get("amlegal", {})
                        if amlegal_config.get("slug") and amlegal_config.get("code_id"):
                            return {
                                "state": data.get("state") or data.get("financial", {}).get("state"),
                                "slug": amlegal_config["slug"],
                                "code_id": amlegal_config["code_id"],
                            }
                    break
        except Exception:
            pass

        raise ValueError(
            f"Jurisdiction {self.jurisdiction_id} not found in JURISDICTION_MAP. "
            f"Add it with slug and code_id from codelibrary.amlegal.com."
        )

    def _cached_text_path(self) -> Path:
        """Path to cached text file for this jurisdiction."""
        jur_info = self._get_jurisdiction_info()
        return self._cache_dir / f"{jur_info['slug']}.txt"

    async def _download_text(self) -> str:
        """Download the full municipal code as text via AMLegal export."""
        jur_info = self._get_jurisdiction_info()
        slug = jur_info["slug"]
        code_id = jur_info["code_id"]

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=self.headless)
        page = await browser.new_page()

        try:
            # Navigate to code root
            root_url = f"{self.BASE_URL}/codes/{slug}/latest/{code_id}/0-0-0-1"
            logger.info(f"Navigating to {root_url}")
            try:
                await page.goto(root_url, wait_until="commit", timeout=60000)
            except Exception:
                pass

            # Wait for Cloudflare challenge
            for _ in range(30):
                if "Just a moment" not in await page.title():
                    break
                await asyncio.sleep(1)
            await asyncio.sleep(3)

            # Open download dialog
            download_btns = await page.query_selector_all('button[title="Download"]')
            for btn in download_btns:
                if await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(2)
                    break

            # Select all checkboxes
            checkboxes = page.locator('.modal input[type="checkbox"]')
            total = await checkboxes.count()
            logger.info(f"Selecting all {total} code sections")
            for i in range(total):
                cb = checkboxes.nth(i)
                if not await cb.is_checked():
                    await cb.click(force=True)
                    await asyncio.sleep(0.1)

            # Click Download button → format selection
            await page.locator('.modal button.btn-primary:has-text("Download")').click()
            await asyncio.sleep(2)

            # Click Save Text
            logger.info("Requesting text export...")
            await page.locator('.modal :text("Save Text")').click()
            await asyncio.sleep(3)

            # Wait for server-side export (can take 2-5 minutes for large codes)
            logger.info("Waiting for server-side export...")
            for i in range(180):  # up to 6 minutes
                exports = await page.evaluate(
                    "document.querySelector('.exports')?.innerText || ''"
                )
                if "OPEN" in exports:
                    logger.info(f"Export ready after {i * 2}s")
                    break
                if i % 15 == 0:
                    logger.info(f"  Still preparing... ({i * 2}s)")
                await asyncio.sleep(2)
            else:
                raise TimeoutError("Export timed out after 6 minutes")

            # Download the file
            async with page.expect_download(timeout=60000) as dl_info:
                await page.locator('.exports :text("OPEN")').click()
            download = await dl_info.value

            # Save to cache
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path = self._cached_text_path()
            await download.save_as(str(cache_path))
            size = os.path.getsize(cache_path)
            logger.info(f"Downloaded {size:,} bytes to {cache_path}")

            with open(cache_path, "r", errors="replace") as f:
                return f.read()

        finally:
            await browser.close()
            await pw.stop()

    def _get_text(self) -> str:
        """Get municipal code text, from cache or download."""
        cache_path = self._cached_text_path()
        if cache_path.exists():
            logger.info(f"Using cached text: {cache_path}")
            with open(cache_path, "r", errors="replace") as f:
                return f.read()

        # Download
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, self._download_text()).result()
        else:
            return asyncio.run(self._download_text())

    @staticmethod
    def _parse_text(text: str) -> list[MunicipalCodeSection]:
        """Parse structured plain text into MunicipalCodeSection objects.

        AMLegal text export uses two-line headers:
            Title 1              ← number alone on its line
            GENERAL PROVISIONS   ← ALL CAPS name on next line
            Chapters:            ← TOC (skip)
            Chapter 1.01         ← number alone on its line
            CODE ADOPTION        ← ALL CAPS name on next line
            Sections:            ← TOC (skip)
            1.01.010   Title.    ← section header
               Body text...     ← indented body
               (Ord. 2014-0021) ← ordinance history
        """
        # Two-line headers: number alone on line, name on next
        title_pattern = re.compile(r"^Title\s+(\d+)\s*$")
        chapter_pattern = re.compile(r"^Chapter\s+([\d.]+)\s*$")
        # Section: number + multi-space + title (at start of line, not indented)
        section_pattern = re.compile(r"^([\d.]+[A-Za-z]?)\s{2,}(.+)")
        # Skip lines: TOC entries, "Chapters:", "Sections:", blank
        skip_pattern = re.compile(r"^(Chapters:|Sections:|Articles:|\s*$)")
        # Ordinance history at end of section body
        history_pattern = re.compile(r"\((?:Ord\.|Prior code).*\)\s*$")

        lines = text.split("\n")
        sections = []
        current_title_number = ""
        current_title_name = ""
        current_chapter = ""
        current_chapter_title = ""
        current_section_number = None
        current_section_title = None
        body_lines = []
        in_toc = False  # True when between "Chapters:"/"Sections:" and first real content

        def flush_section():
            if current_section_number and body_lines:
                full_text = "\n".join(body_lines).strip()

                ordinance_history = None
                history_match = history_pattern.search(full_text)
                if history_match:
                    ordinance_history = history_match.group(0).strip("() ")

                sections.append(MunicipalCodeSection(
                    section_number=current_section_number,
                    section_title=current_section_title or "",
                    full_text=full_text,
                    chapter=current_chapter,
                    chapter_title=current_chapter_title,
                    title_number=current_title_number,
                    title_name=current_title_name,
                    node_id="",
                    ordinance_history=ordinance_history,
                ))

        i = 0
        while i < len(lines):
            line = lines[i]

            # Title header (two-line: "Title N" then "ALL CAPS NAME")
            title_match = title_pattern.match(line)
            if title_match:
                flush_section()
                current_section_number = None
                body_lines = []
                current_title_number = title_match.group(1)
                # Next line is the title name (ALL CAPS)
                if i + 1 < len(lines):
                    current_title_name = lines[i + 1].strip()
                    i += 2
                else:
                    current_title_name = ""
                    i += 1
                in_toc = False
                continue

            # Chapter header (two-line: "Chapter N.NN" then "ALL CAPS NAME")
            chapter_match = chapter_pattern.match(line)
            if chapter_match:
                flush_section()
                current_section_number = None
                body_lines = []
                current_chapter = chapter_match.group(1)
                if i + 1 < len(lines):
                    current_chapter_title = lines[i + 1].strip()
                    i += 2
                else:
                    current_chapter_title = ""
                    i += 1
                in_toc = False
                continue

            # TOC headers — skip subsequent TOC entries
            if skip_pattern.match(line):
                if line.strip() in ("Chapters:", "Sections:", "Articles:"):
                    in_toc = True
                i += 1
                continue

            # Section header (e.g., "1.01.010   Section title.")
            section_match = section_pattern.match(line)
            if section_match and current_chapter:
                # Verify it's a real section (number starts with chapter prefix)
                sec_num = section_match.group(1)
                if sec_num.startswith(current_chapter + ".") or sec_num.startswith(current_chapter.split(".")[0] + "."):
                    flush_section()
                    current_section_number = sec_num
                    current_section_title = section_match.group(2).strip()
                    body_lines = []
                    in_toc = False
                    i += 1
                    continue

            # TOC entries (indented section listings before actual content)
            if in_toc:
                i += 1
                continue

            # Body text
            if current_section_number is not None:
                body_lines.append(line.rstrip())

            i += 1

        flush_section()
        return sections

    def stream_sections(
        self,
        title_ids: Optional[list[str]] = None,
    ) -> Iterator[MunicipalCodeSection]:
        """
        Stream code sections from American Legal Publishing.

        Args:
            title_ids: Optional list of title numbers (e.g., ["1", "2"]) to filter.
                      If None, returns all titles.

        Yields:
            MunicipalCodeSection for each code section
        """
        text = self._get_text()
        sections = self._parse_text(text)

        if title_ids:
            sections = [s for s in sections if s.title_number in title_ids]

        yield from sections

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
        """Convert sections to document format for indexing."""
        for section in self.stream_sections(title_ids):
            section_parts = section.section_number.replace(".", "-")
            doc_id = f"{self.jurisdiction_id}-muni-{section_parts}"

            text = f"""Chapter: {section.chapter} - {section.chapter_title}
Section: {section.section_number}
Title: {section.section_title}
Full Text: {section.full_text}"""

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

            yield {
                "id": doc_id,
                "text": text,
                "metadata": metadata,
            }

    def close(self):
        """No-op (browser is closed after download)."""
        pass
