"""
Playwright + LLM Direct Extraction

For municipalities where the universal adapter's CSS selector approach fails,
this module renders the page with Playwright and asks an LLM to extract
meeting data directly from the visible text.

Advantages over the CSS selector approach:
- Handles JavaScript-rendered content (tabs, date filters, dynamic tables)
- No brittle CSS selectors — reads text like a human
- Can distinguish government meetings from community events
- Works on any page structure

Trade-off: requires an LLM call per extraction (vs deterministic CSS selectors).
With Gemini Flash at $0.075/1M tokens, a page extraction costs ~$0.001.

Usage:
    meetings = extract_meetings_from_page(
        url="https://www.townofrossca.gov/meetings",
        jurisdiction_id="city-ross",
    )
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
You are extracting government meeting data from a municipal website. \
Below is the visible text from the meetings page of {jurisdiction_id}.

Extract ALL government meetings (city council, planning commission, advisory \
boards, committees). Exclude non-government events (concerts, festivals, \
community social events, holiday notices).

For each meeting, extract:
- title: The meeting body name (e.g., "Town Council Meeting", "Planning Commission")
- date: Date and time in ISO 8601 format (YYYY-MM-DDTHH:MM:SS). Use the year from the page content.
- meeting_type: The body slug (e.g., "town_council", "planning_commission")
- agenda_url: Full URL to the agenda PDF if visible (null if not)
- minutes_url: Full URL to minutes PDF if visible (null if not)
- video_url: Full URL to video if visible (null if not)

Respond with ONLY a JSON array (no markdown fences):
[
  {{"title": "...", "date": "...", "meeting_type": "...", "agenda_url": ..., "minutes_url": ..., "video_url": ...}},
  ...
]

If the page has tabs or filters like "All Meetings" vs "Upcoming", note that the \
text below may represent only one view. Extract what is visible.

Page text:
{page_text}
"""


def extract_meetings_from_page(
    url: str,
    jurisdiction_id: str,
    timeout: int = 20,
    max_text_chars: int = 15000,
) -> List[Dict[str, Any]]:
    """Render a page with Playwright and extract meetings via LLM.

    Args:
        url: Meeting page URL
        jurisdiction_id: Jurisdiction ID for context
        timeout: Page load timeout in seconds
        max_text_chars: Max characters of page text to send to LLM

    Returns:
        List of meeting dicts with title, date, meeting_type, agenda_url, etc.
    """
    import os
    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise RuntimeError("LLM API key required for Playwright+LLM extraction")

    # 1. Render page with Playwright (returns link-aware text from DOM API)
    html, page_text = _render_page(url, timeout)

    # Truncate to fit LLM context
    if len(page_text) > max_text_chars:
        page_text = page_text[:max_text_chars] + "\n\n[... truncated ...]"

    # 2. Resolve base URL for making relative links absolute
    from urllib.parse import urlparse
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # 3. Ask LLM to extract meetings
    from civicos_extraction.llm import get_llm_provider
    provider = get_llm_provider("navigation")

    prompt = _EXTRACTION_PROMPT.format(
        jurisdiction_id=jurisdiction_id,
        page_text=page_text,
    )

    result = provider.complete(
        [{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=4096,
    )
    text = result.content.strip()

    # 4. Parse JSON response (strip markdown fences if present)
    # LLMs sometimes wrap in ```json ... ```
    text_clean = re.sub(r"^```(?:json)?\s*", "", text)
    text_clean = re.sub(r"\s*```\s*$", "", text_clean)

    json_match = re.search(r"\[.*\]", text_clean, re.DOTALL)
    if not json_match:
        logger.warning(f"LLM returned no JSON array: {text[:200]}")
        return []

    try:
        meetings_raw = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse LLM response: {e}")
        return []

    # 5. Normalize and resolve URLs
    meetings = []
    for m in meetings_raw:
        if not isinstance(m, dict):
            continue
        title = m.get("title", "")
        if not title:
            continue

        # Resolve relative URLs
        for url_field in ("agenda_url", "minutes_url", "video_url"):
            val = m.get(url_field)
            if val and not val.startswith("http"):
                m[url_field] = base_url + (val if val.startswith("/") else "/" + val)

        meetings.append(m)

    logger.info(f"Playwright+LLM extracted {len(meetings)} meetings from {url}")
    return meetings


# ---------------------------------------------------------------------------
# Officials extraction
# ---------------------------------------------------------------------------

_OFFICIALS_PROMPT = """\
You are extracting current elected officials from a municipal government website. \
Below is the visible text from {jurisdiction_id}'s government/council page.

Extract ALL currently serving elected officials. Include:
- Mayor, Vice Mayor, Council Members, Board Members, Supervisors
- Their role/title exactly as shown
- District number if shown
- Email and phone if shown on the page

Do NOT include:
- City staff (city manager, clerk, etc.) — only elected officials
- Former/past officials
- Candidates not yet in office

Respond with ONLY a JSON array (no markdown fences):
[
  {{"name": "...", "role": "...", "district": null, "email": null, "phone": null}},
  ...
]

If you cannot find any elected officials on this page, return an empty array [].

Page text:
{page_text}
"""


def extract_officials_from_page(
    url: str,
    jurisdiction_id: str,
    timeout: int = 20,
    max_text_chars: int = 10000,
) -> List[Dict[str, Any]]:
    """Render a government page with Playwright and extract officials via LLM.

    Args:
        url: Government/council page URL
        jurisdiction_id: Jurisdiction ID for context
        timeout: Page load timeout in seconds
        max_text_chars: Max characters of page text to send to LLM

    Returns:
        List of official dicts with name, role, district, email, phone.
    """
    import os
    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        return []

    html, page_text = _render_page(url, timeout)

    if len(page_text) > max_text_chars:
        page_text = page_text[:max_text_chars] + "\n\n[... truncated ...]"

    from civicos_extraction.llm import get_llm_provider
    provider = get_llm_provider("navigation")

    prompt = _OFFICIALS_PROMPT.format(
        jurisdiction_id=jurisdiction_id,
        page_text=page_text,
    )

    result = provider.complete(
        [{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    text = result.content.strip()

    json_match = re.search(r"\[.*\]", text, re.DOTALL)
    if not json_match:
        logger.warning(f"Officials LLM returned no JSON array: {text[:200]}")
        return []

    try:
        officials_raw = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse officials LLM response: {e}")
        return []

    officials = []
    for o in officials_raw:
        if not isinstance(o, dict) or not o.get("name"):
            continue
        officials.append({
            "id": "web-{}-{}".format(
                jurisdiction_id,
                re.sub(r"[^a-z0-9]+", "-", o["name"].lower()).strip("-"),
            ),
            "name": o["name"],
            "seat": o.get("role", "Elected Official"),
            "jurisdiction_id": jurisdiction_id,
            "district": o.get("district"),
            "email": o.get("email"),
            "phone": o.get("phone"),
            "source": "website",
        })

    logger.info(f"Playwright+LLM extracted {len(officials)} officials from {url}")
    return officials


def find_government_page(base_url: str, html: str) -> Optional[str]:
    """Find the city council / government page URL from a city's homepage.

    Args:
        base_url: City's base URL (e.g., "https://www.cortemadera.gov")
        html: Homepage HTML content

    Returns:
        Full URL to the government/council page, or None.
    """
    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    resolved = f"{parsed.scheme}://{parsed.netloc}"

    # Find links to the council/officials page (not meeting pages)
    _GOV_RE = re.compile(
        r'<a[^>]*href=["\']([^"\']{3,200})["\'][^>]*>[^<]*'
        r'(?:city\s+council|town\s+council|board\s+of|supervisors|'
        r'elected\s+officials|your\s+government|government|'
        r'mayor\s+and\s+council|council\s+members)[^<]*</a>',
        re.IGNORECASE,
    )

    # Negative patterns — these are meetings/events, not official listings
    _SKIP = {"meeting", "agenda", "minute", "event/", "calendar", "archive"}

    candidates = []
    for match in _GOV_RE.finditer(html):
        href = match.group(1)
        if href.startswith(("#", "javascript:", "mailto:")):
            continue
        if any(skip in href.lower() for skip in _SKIP):
            continue
        if href.startswith("/"):
            href = resolved + href
        elif not href.startswith("http"):
            href = resolved + "/" + href
        if parsed.netloc in href:
            candidates.append(href)

    if not candidates:
        # Fallback: try common council page paths directly
        for path in ["/government/city-council", "/government/town-council",
                     "/city-council", "/town-council", "/council-members",
                     "/your-government/city-council"]:
            candidates.append(resolved + path)

    # Score: prefer "council-members" > "city-council" > "government"
    def _score(url: str) -> int:
        lower = url.lower()
        if "council-member" in lower or "elected-official" in lower:
            return 10
        if "city-council" in lower or "town-council" in lower:
            return 5
        if "government" in lower:
            return 1
        return 0

    candidates.sort(key=_score, reverse=True)
    return candidates[0] if candidates else None


def _render_page(url: str, timeout: int = 20) -> tuple:
    """Render a page with Playwright stealth and return (html, link_aware_text).

    The link_aware_text is the visible page text with document link URLs
    annotated inline (e.g., ``Agenda [https://...pdf]``). This is generated
    via Playwright's DOM API, which correctly handles:
    - display:none elements (excluded, unlike raw HTML parsing)
    - JavaScript-rendered content
    - All link types (PDFs, query-string URLs, relative paths)

    Attempts to click "All Meetings" or similar tabs to get full content.
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    stealth = Stealth()
    with sync_playwright() as p:
        stealth.hook_playwright_context(p)
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        stealth.apply_stealth_sync(page)
        page.goto(url, wait_until="networkidle", timeout=timeout * 1000)

        # Try to expand to full meeting list by clicking common tab/button patterns
        for selector in [
            "a:has-text('All Meetings')",
            "a:has-text('All')",
            "a:has-text('Past Meetings')",
            "button:has-text('Show All')",
            "a:has-text('View All')",
        ]:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    el.click()
                    page.wait_for_load_state("networkidle", timeout=5000)
                    logger.info(f"Clicked '{selector}' to expand meeting list")
                    break
            except Exception:
                continue

        html = page.content()

        # Extract link-aware text via DOM API.
        # Annotates visible <a> tags that point to documents with [url].
        link_text = page.evaluate("""() => {
            const DOC_RE = /\\.(pdf|doc|docx|xls|xlsx)(\\?|#|$)/i;
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT,
                {
                    acceptNode(node) {
                        if (node.nodeType === Node.ELEMENT_NODE) {
                            const style = window.getComputedStyle(node);
                            if (style.display === 'none' || style.visibility === 'hidden')
                                return NodeFilter.FILTER_REJECT;
                            const tag = node.tagName;
                            if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT')
                                return NodeFilter.FILTER_REJECT;
                            return NodeFilter.FILTER_SKIP;
                        }
                        return NodeFilter.FILTER_ACCEPT;
                    }
                }
            );

            const parts = [];
            let node;
            while ((node = walker.nextNode())) {
                if (node.nodeType !== Node.TEXT_NODE) continue;
                const text = node.textContent.trim();
                if (!text) continue;

                // Check if this text node is inside an <a> with a document href
                const anchor = node.parentElement?.closest('a');
                if (anchor) {
                    const href = anchor.href;
                    if (href && DOC_RE.test(href)) {
                        parts.push(text + ' [' + href + ']');
                        continue;
                    }
                }
                parts.push(text);
            }
            return parts.join('\\n');
        }""")

        browser.close()

    return html, link_text


# ---------------------------------------------------------------------------
# Source wrapper for pipeline integration
# ---------------------------------------------------------------------------


class PlaywrightLLMSource:
    """DataSource wrapper around the Playwright+LLM extraction functions.

    Implements the source protocol (source_id, source_type, health,
    get_events, normalize_event) so that playwright_llm can be used as a
    drop-in replacement in the extraction pipeline and factory.
    """

    def __init__(self, config):
        """Initialize from an ExtractionConfig.

        Args:
            config: ExtractionConfig with source_type='playwright_llm' and
                    metadata.meeting_page_url set to the calendar URL.
        """
        self.jurisdiction_id = config.jurisdiction_id
        self._meeting_page_url = config.metadata.get("meeting_page_url", config.base_url)
        self._config = config

    @property
    def source_id(self) -> str:
        return f"playwright-llm-{self.jurisdiction_id}"

    @property
    def source_type(self) -> str:
        return "playwright_llm"

    def health(self):
        """Check that the meeting page is reachable and returns meetings."""
        import time as _time
        from civicos_extraction.clients.base import HealthStatus

        start = _time.time()
        errors = []
        count = 0
        try:
            meetings = extract_meetings_from_page(
                url=self._meeting_page_url,
                jurisdiction_id=self.jurisdiction_id,
            )
            count = len(meetings)
        except Exception as e:
            errors.append(f"Playwright+LLM health check failed: {e}")

        elapsed_ms = (_time.time() - start) * 1000
        return HealthStatus(
            source_id=self.source_id,
            source_type=self.source_type,
            jurisdiction_id=self.jurisdiction_id,
            is_available=count > 0,
            available_count=count,
            last_checked=datetime.now(timezone.utc),
            check_duration_ms=elapsed_ms,
            errors=errors,
        )

    def validate(self):
        """Validate that the config has what we need."""
        from civicos_extraction.clients.base import ValidationResult

        errors = []
        if not self._meeting_page_url:
            errors.append("No meeting_page_url in config metadata")
        return ValidationResult(
            is_valid=not errors,
            config_valid=not errors,
            api_reachable=True,
            errors=errors,
        )

    def get_events(self, days_ahead: int = 90, days_past: int = 0):
        """Extract meetings via Playwright+LLM."""
        return extract_meetings_from_page(
            url=self._meeting_page_url,
            jurisdiction_id=self.jurisdiction_id,
        )

    def get_meetings(self, days_ahead: int = 90, days_past: int = 0):
        """Alias for get_events."""
        return self.get_events(days_ahead=days_ahead, days_past=days_past)

    def normalize_event(self, event: Dict[str, Any]):
        """Normalize a Playwright+LLM meeting dict to Meeting format."""
        import hashlib
        from civicos_extraction.clients.base import Meeting

        title = event.get("title", "Unknown Meeting")
        date_str = event.get("date", "")
        try:
            parsed_date = datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            parsed_date = datetime(1970, 1, 1)

        id_source = f"{self.jurisdiction_id}:{title}:{parsed_date.isoformat()}"
        meeting_id = hashlib.sha256(id_source.encode()).hexdigest()[:16]

        return Meeting(
            meeting_id=meeting_id,
            title=title,
            meeting_datetime=parsed_date,
            meeting_type=event.get("meeting_type", ""),
            jurisdiction_id=self.jurisdiction_id,
            source_id=self.source_id,
            source_type=self.source_type,
            source_url=self._meeting_page_url,
            agenda_url=event.get("agenda_url"),
            minutes_url=event.get("minutes_url"),
            video_url=event.get("video_url"),
        )
