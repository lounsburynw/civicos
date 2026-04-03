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

    # 1. Render page with Playwright
    html, page_text = _render_page(url, timeout)

    # Truncate to fit LLM context
    if len(page_text) > max_text_chars:
        page_text = page_text[:max_text_chars] + "\n\n[... truncated ...]"

    # 2. Resolve base URL for making relative links absolute
    from urllib.parse import urlparse
    parsed = urlparse(url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # 3. Ask LLM to extract meetings
    from civicos_services.core.llm_provider import get_model_for_task
    provider = get_model_for_task("navigation")

    prompt = _EXTRACTION_PROMPT.format(
        jurisdiction_id=jurisdiction_id,
        page_text=page_text,
    )

    result = provider.complete(
        [{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    text = result.content.strip()

    # 4. Parse JSON response
    json_match = re.search(r"\[.*\]", text, re.DOTALL)
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


def _render_page(url: str, timeout: int = 20) -> tuple:
    """Render a page with Playwright stealth and return (html, visible_text).

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
        text = page.inner_text("body")
        browser.close()

    return html, text
