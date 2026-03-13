"""
Universal Adapter config generation.

Uses an LLM to infer a declarative extraction config from sample HTML.
Runs once at onboard time — extraction uses the saved config deterministically.

See docs/public/decisions/universal_adapter.md for the design ADR.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# JSON schema for adapter config validation
ADAPTER_SCHEMA = {
    "required_fields": {"title", "date"},
    "valid_extract_modes": {"text", "href", "html"},
    "valid_page_types": {"table", "list", "card"},
    "valid_pagination_types": {"none", "next_link", "page_param", "load_more"},
}

CONFIG_PROMPT_VERSION = "universal_adapter/v2"

_CONFIG_PROMPT = """Analyze this HTML page from a government meeting listing website.

Your task: produce a JSON config that describes how to extract meeting data from this page.

The config must have this structure:
{{
  "page_type": "table" or "list" or "card",
  "listing": {{
    "container": "<CSS selector for the element containing meeting rows>",
    "row": "<CSS selector for individual meeting rows within the container>",
    "fields": {{
      "title": {{ "selector": "<CSS selector relative to row>", "extract": "text" }},
      "date": {{ "selector": "<CSS selector relative to row>", "extract": "text", "date_format": "<strftime format>" }},
      "time": {{ "selector": "<CSS selector relative to row>", "extract": "text" }},
      "agenda_url": {{ "selector": "<CSS selector for agenda link>", "extract": "href" }},
      "minutes_url": {{ "selector": "<CSS selector for minutes link>", "extract": "href" }},
      "video_url": {{ "selector": "<CSS selector for video link>", "extract": "href" }}
    }}
  }},
  "pagination": {{
    "type": "none" or "next_link" or "page_param",
    "next_selector": "<CSS selector for next page link, if applicable>",
    "max_pages": 5
  }},
  "requires_javascript": false
}}

Rules:
- "title" and "date" fields are REQUIRED. Others are optional — only include them if present on the page.
- Use CSS selectors that are specific enough to be stable but not so specific they break with minor HTML changes.
- Prefer class-based selectors over positional ones (nth-child) when classes are available.
- For "extract": use "text" for visible text content, "href" for link URLs.
- For "date_format": use Python strftime format (e.g., "%B %d, %Y" for "March 15, 2026").
- Set "requires_javascript" to true ONLY if the page content is loaded via JavaScript (AJAX/SPA).
- For pagination: check if there are next/previous page links or page number parameters.

Return ONLY the JSON object. No explanation.

HTML:
{sample_html}"""


_DETAIL_PROMPT = """Analyze this HTML page showing details for a single government meeting.

Your task: produce a JSON config describing how to extract meeting details from this page.
This page was reached by following a link from a meeting listing page.

The config must have this structure:
{{
  "fields": {{
    "title": {{ "selector": "<CSS selector>", "extract": "text" }},
    "date": {{ "selector": "<CSS selector>", "extract": "text", "date_format": "<strftime format>" }},
    "time": {{ "selector": "<CSS selector>", "extract": "text" }},
    "location": {{ "selector": "<CSS selector>", "extract": "text" }},
    "video_url": {{ "selector": "<CSS selector for video/YouTube link>", "extract": "href" }},
    "minutes_url": {{ "selector": "<CSS selector for minutes link>", "extract": "href" }}
  }}
}}

Rules:
- Only include fields that are actually present on this page.
- For "time": look for elements containing patterns like "9:30 am", "2:00 PM". If time is part of a
  larger text like "Wednesday, March 11, 2026 9:30 am", still include it — the parser handles extraction.
- For "location": look for addresses, building names, or room numbers.
- For "video_url": look for YouTube, Vimeo, or streaming links.
- Prefer semantic selectors (time.datetime, a[href*='youtube']) over positional ones.
- Return ONLY the JSON object. No explanation.

HTML:
{sample_html}"""


def _extract_detail_sample(html: str, max_chars: int = 8000) -> str:
    """Extract the relevant section of a detail page for LLM analysis."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "nav", "footer"]):
        tag.decompose()

    main = soup.find("main") or soup.find(id="content") or soup.find("article")
    target = main or soup.find("body") or soup

    sample = str(target)
    if len(sample) > max_chars:
        sample = sample[:max_chars]
    return sample


def _generate_detail_config(
    detail_url: str,
    provider,
    timeout: int = 30,
    use_playwright: bool = False,
) -> Optional[Dict[str, Any]]:
    """Generate a detail page config by sampling one meeting detail page.

    Args:
        detail_url: URL of a single meeting detail page
        provider: LLM provider instance
        timeout: HTTP request timeout
        use_playwright: Whether to use Playwright for JS rendering

    Returns:
        Detail config dict with "url_field" and "fields", or None if generation fails
    """
    try:
        if use_playwright:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(detail_url, wait_until="networkidle", timeout=30000)
                html = page.content()
                browser.close()
        else:
            response = requests.get(
                detail_url,
                headers={"User-Agent": "CivicOS-UniversalAdapter/1.0"},
                timeout=timeout,
            )
            response.raise_for_status()
            html = response.text

        sample = _extract_detail_sample(html)
        prompt = _DETAIL_PROMPT.format(sample_html=sample)

        result = provider.complete(
            messages=[{"role": "user", "content": prompt}]
        )
        raw = result.content.strip()

        json_match = re.search(r"\{[\s\S]+\}", raw)
        if not json_match:
            logger.warning(f"Detail config LLM did not return JSON for {detail_url}")
            return None

        detail_fields = json.loads(json_match.group())

        # Must have a "fields" key
        fields = detail_fields.get("fields", detail_fields)
        if not isinstance(fields, dict) or not fields:
            logger.warning(f"Detail config has no usable fields for {detail_url}")
            return None

        # Validate selectors against the page
        soup = BeautifulSoup(html, "html.parser")
        valid_fields = {}
        for name, conf in fields.items():
            if not isinstance(conf, dict):
                continue
            sel = conf.get("selector", "")
            if sel:
                match = soup.select_one(sel)
                if match:
                    valid_fields[name] = conf
                else:
                    logger.warning(f"Detail selector '{sel}' for '{name}' matched nothing")
            else:
                valid_fields[name] = conf

        if not valid_fields:
            logger.warning(f"No detail selectors matched for {detail_url}")
            return None

        logger.info(
            f"Generated detail config for {detail_url}: "
            f"fields={list(valid_fields.keys())}"
        )
        return {"fields": valid_fields, "provenance": {"detail_url": detail_url, "raw_response": raw}}

    except Exception as e:
        logger.warning(f"Detail config generation failed for {detail_url}: {e}")
        return None


def _extract_sample(html: str, max_chars: int = 12000) -> str:
    """Extract the most relevant section of HTML for LLM analysis.

    Finds the largest table or list structure (likely the meeting listing)
    and returns a truncated version to keep token count manageable.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, nav, footer — they're noise
    for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    # Try to find the main content area
    main = soup.find("main") or soup.find(id="content") or soup.find(class_="content")
    search_area = main or soup

    # Find the largest table
    tables = search_area.find_all("table")
    if tables:
        target = max(tables, key=lambda t: len(t.find_all("tr")))
        # Include some parent context
        parent = target.parent
        sample = str(parent) if parent and len(str(parent)) < max_chars * 2 else str(target)
        if len(sample) > max_chars:
            sample = sample[:max_chars]
        return sample

    # No table — find largest list or repeated div structure
    lists = search_area.find_all(["ul", "ol"])
    if lists:
        target = max(lists, key=lambda l: len(l.find_all("li")))
        sample = str(target)
        if len(sample) > max_chars:
            sample = sample[:max_chars]
        return sample

    # Last resort: return body content truncated
    body = soup.find("body") or soup
    sample = str(body)
    if len(sample) > max_chars:
        sample = sample[:max_chars]
    return sample


def _validate_config(config: Dict[str, Any]) -> list[str]:
    """Validate adapter config structure. Returns list of errors."""
    errors = []

    if not isinstance(config, dict):
        return ["Config must be a dictionary"]

    # Check page_type
    page_type = config.get("page_type")
    if page_type and page_type not in ADAPTER_SCHEMA["valid_page_types"]:
        errors.append(f"Invalid page_type '{page_type}'")

    # Check listing
    listing = config.get("listing")
    if not listing:
        errors.append("Missing 'listing' section")
        return errors

    if not listing.get("row"):
        errors.append("Missing 'listing.row' selector")

    # Check fields
    fields = listing.get("fields", {})
    for required in ADAPTER_SCHEMA["required_fields"]:
        if required not in fields:
            errors.append(f"Missing required field '{required}'")

    for field_name, field_config in fields.items():
        if not isinstance(field_config, dict):
            errors.append(f"Field '{field_name}' must be a dict")
            continue
        extract = field_config.get("extract", "text")
        if not extract.startswith("attr:") and extract not in ADAPTER_SCHEMA["valid_extract_modes"]:
            errors.append(f"Invalid extract mode '{extract}' for field '{field_name}'")

    # Check pagination
    pagination = config.get("pagination", {})
    pag_type = pagination.get("type", "none")
    if pag_type not in ADAPTER_SCHEMA["valid_pagination_types"]:
        errors.append(f"Invalid pagination type '{pag_type}'")

    return errors


def _smoke_test(config: Dict[str, Any], html: str) -> list[str]:
    """Run the config against sample HTML and verify it extracts data.

    Returns list of errors (empty = success).
    """
    errors = []
    soup = BeautifulSoup(html, "html.parser")
    listing = config.get("listing", {})

    # Test container selector
    container_sel = listing.get("container", "")
    if container_sel:
        container = soup.select_one(container_sel)
        if not container:
            errors.append(f"Container selector '{container_sel}' matched 0 elements")
            return errors
    else:
        container = soup

    # Test row selector
    row_sel = listing.get("row", "")
    if row_sel:
        rows = container.select(row_sel)
        if not rows:
            errors.append(f"Row selector '{row_sel}' matched 0 elements")
            return errors
    else:
        errors.append("No row selector to test")
        return errors

    # Test field extraction on first few rows
    fields = listing.get("fields", {})
    titles_found = 0
    dates_found = 0

    for row in rows[:5]:
        if "title" in fields:
            title_sel = fields["title"].get("selector", "")
            if title_sel:
                el = row.select_one(title_sel)
                if el and el.get_text(strip=True):
                    titles_found += 1
            else:
                # No selector — try text of row itself
                if row.get_text(strip=True):
                    titles_found += 1

        if "date" in fields:
            date_sel = fields["date"].get("selector", "")
            if date_sel:
                el = row.select_one(date_sel)
                if el and el.get_text(strip=True):
                    dates_found += 1

    if titles_found == 0:
        errors.append("Title selector extracted 0 values from sample rows")
    if dates_found == 0:
        errors.append("Date selector extracted 0 values from sample rows")

    return errors


def generate_adapter_config(
    url: str,
    timeout: int = 30,
    use_playwright: bool = False,
) -> Dict[str, Any]:
    """
    Fetch a municipal meeting page and use LLM to infer extraction config.

    Args:
        url: URL of the meeting listing page
        timeout: HTTP request timeout in seconds
        use_playwright: If True, use Playwright to render JS-heavy pages

    Returns:
        Complete adapter config dict with provenance

    Raises:
        RuntimeError: If LLM cannot produce a valid config after retry
    """
    from civicos_services.core.llm_provider import get_model_for_task

    # 1. Fetch the page
    if use_playwright:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, wait_until="networkidle", timeout=30000)
                html = page.content()
                browser.close()
        except ImportError:
            raise ImportError("Playwright required. pip install playwright && playwright install chromium")
    else:
        response = requests.get(
            url,
            headers={"User-Agent": "CivicOS-UniversalAdapter/1.0"},
            timeout=timeout,
        )
        response.raise_for_status()
        html = response.text

    # 2. Extract relevant sample
    sample_html = _extract_sample(html)
    sample_hash = hashlib.sha256(sample_html.encode()).hexdigest()

    # 3. Ask LLM to generate config
    provider = get_model_for_task("navigation")
    prompt = _CONFIG_PROMPT.format(sample_html=sample_html)

    result = provider.complete(
        messages=[{"role": "user", "content": prompt}]
    )
    raw_response = result.content.strip()

    # 4. Parse JSON from response
    json_match = re.search(r"\{[\s\S]+\}", raw_response)
    if not json_match:
        raise RuntimeError(f"LLM did not return valid JSON: {raw_response[:300]}")

    try:
        config = json.loads(json_match.group())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM returned invalid JSON: {e}")

    # 5. Validate structure
    validation_errors = _validate_config(config)

    # 6. Smoke test against sample HTML
    if not validation_errors:
        smoke_errors = _smoke_test(config, html)
        validation_errors.extend(smoke_errors)

    # 7. If validation failed, retry once with error feedback
    if validation_errors:
        logger.warning(
            f"First config attempt had errors: {validation_errors}. Retrying..."
        )
        retry_prompt = (
            f"{prompt}\n\n"
            f"IMPORTANT: Your previous attempt had these errors:\n"
            + "\n".join(f"- {e}" for e in validation_errors)
            + "\n\nFix these issues and return a corrected JSON config."
        )
        result = provider.complete(
            messages=[{"role": "user", "content": retry_prompt}]
        )
        raw_response_retry = result.content.strip()

        json_match = re.search(r"\{[\s\S]+\}", raw_response_retry)
        if not json_match:
            raise RuntimeError(
                f"LLM retry did not return valid JSON. "
                f"Original errors: {validation_errors}"
            )

        try:
            config = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            raise RuntimeError(f"LLM retry returned invalid JSON: {e}")

        retry_errors = _validate_config(config)
        if not retry_errors:
            retry_errors = _smoke_test(config, html)

        if retry_errors:
            raise RuntimeError(
                f"Config generation failed after retry. Errors: {retry_errors}. "
                f"Manual config may be needed for this page."
            )

        raw_response = raw_response_retry

    # 8. Add URL template and provenance
    config["listing"]["url_template"] = url
    config["provenance"] = {
        "sample_url": url,
        "sample_html_hash": f"sha256:{sample_hash}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_version": CONFIG_PROMPT_VERSION,
        "raw_response": raw_response,
    }

    # 9. Generate detail page config if listing has a link field
    #    Follow the first extracted link to sample a detail page
    link_field = None
    listing_fields = config.get("listing", {}).get("fields", {})
    for candidate in ["agenda_url", "minutes_url", "detail_url"]:
        if candidate in listing_fields:
            link_field = candidate
            break

    if link_field:
        # Do a quick extraction to get a real detail URL
        try:
            from civicos_extraction.clients.universal import UniversalExtractor
            test_extractor = UniversalExtractor("_config_gen", config, url)
            test_events = test_extractor._extract_rows_from_page(html)
            if test_events:
                detail_url = test_events[0].get(link_field)
                if detail_url:
                    detail_config = _generate_detail_config(
                        detail_url, provider, timeout=timeout,
                        use_playwright=use_playwright,
                    )
                    if detail_config:
                        config["detail"] = {
                            "url_field": link_field,
                            "fields": detail_config["fields"],
                        }
                        config["provenance"]["detail"] = detail_config.get("provenance", {})
        except Exception as e:
            logger.warning(f"Detail config generation skipped: {e}")

    logger.info(
        f"Generated universal adapter config for {url}: "
        f"page_type={config.get('page_type')}, "
        f"listing_fields={list(listing_fields.keys())}, "
        f"detail={'yes' if 'detail' in config else 'no'}"
    )
    return config
