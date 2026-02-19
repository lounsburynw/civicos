"""
Federal Register API client for Civic Conversational OS

Fetches Executive Orders from the Federal Register's public API for tracking
presidential directives that impact local governance.

Key capabilities:
- Incremental fetch (since_date filter for scheduled updates)
- Full EO metadata (title, signing date, document number, URLs)
- Pagination support
- Robust error handling with retry logic

API Docs: https://www.federalregister.gov/developers/documentation/api/v1
"""

import requests
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode


class FederalRegisterClient:
    """Federal Register API client for Executive Order tracking"""

    def __init__(self):
        self.base_url = "https://www.federalregister.gov/api/v1"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Civic Conversational OS (civic-power-bridge)",
            "Accept": "application/json",
        })
        self.last_request_time = 0
        self.min_request_interval = 0.5  # Respectful rate limiting

    def _throttle_request(self):
        """Prevent burst requests"""
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval)
        self.last_request_time = time.time()

    def _make_request(
        self,
        endpoint: str,
        params: Dict = None,
        retries: int = 3,
    ) -> Any:
        """Make API request with exponential backoff"""
        self._throttle_request()

        url = f"{self.base_url}/{endpoint}"

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=30)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code in [429, 500, 502, 503]:
                    # Exponential backoff for server issues
                    wait_time = 2 ** attempt
                    print(f"Federal Register API {response.status_code}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"Federal Register API error {response.status_code}: {response.text[:200]}")
                    return None

            except Exception as e:
                print(f"Federal Register request failed: {str(e)[:100]}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None

        return None

    def fetch_executive_orders(
        self,
        since_date: Optional[str] = None,
        per_page: int = 100,
        max_pages: int = 50,
        include_full_text: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fetch Executive Orders from Federal Register API.

        Args:
            since_date: ISO date string (YYYY-MM-DD) for incremental fetch.
                        Only returns EOs published on or after this date.
            per_page: Results per page (max 1000)
            max_pages: Maximum pages to fetch (safety limit)
            include_full_text: If True, fetch full text for each EO.
                              Defaults to True - adds ~0.5s per EO but required for vector search.

        Returns:
            List of EO dictionaries normalized for storage in executive_orders table
        """
        all_orders = []
        page = 1

        # Build query params
        # Using conditions[type]=PRESDOCU and conditions[presidential_document_type]=executive_order
        # Must explicitly request fields to get president, signing_date, etc.
        base_params = {
            "conditions[type]": "PRESDOCU",
            "conditions[presidential_document_type]": "executive_order",
            "per_page": min(per_page, 1000),
            "order": "newest",
            # Request all fields we need (API returns minimal set by default)
            "fields[]": [
                "document_number",
                "title",
                "abstract",
                "publication_date",
                "signing_date",
                "executive_order_number",
                "president",
                "html_url",
                "pdf_url",
                "raw_text_url",
                "type",
                "subtype",
                "agencies",
                "topics",
                "citation",
            ],
        }

        if since_date:
            # Publication date filter for incremental fetch
            base_params["conditions[publication_date][gte]"] = since_date

        while page <= max_pages:
            params = {**base_params, "page": page}
            response = self._make_request("documents", params)

            if not response:
                print(f"Failed to fetch page {page}, stopping")
                break

            results = response.get("results", [])
            if not results:
                break

            for raw_eo in results:
                normalized = self._normalize_executive_order(raw_eo)
                if normalized:
                    all_orders.append(normalized)

            # Check if more pages
            total_pages = response.get("total_pages", 1)
            if page >= total_pages:
                break

            page += 1

        # Optionally fetch full text for each EO
        if include_full_text:
            for eo in all_orders:
                if eo.get("raw_text_url"):
                    full_text = self._fetch_full_text(eo["raw_text_url"])
                    if full_text:
                        eo["full_text"] = full_text
                    # Rate limit between text fetches
                    time.sleep(0.5)

        return all_orders

    def _normalize_executive_order(self, raw_eo: Dict) -> Optional[Dict[str, Any]]:
        """
        Normalize Federal Register EO response to our internal format.

        Maps Federal Register schema -> Civic executive_orders table schema
        """
        document_number = raw_eo.get("document_number")
        if not document_number:
            return None

        title = raw_eo.get("title", "")

        # Get EO number from API field or parse from title
        eo_number_raw = raw_eo.get("executive_order_number")
        eo_number = None
        if eo_number_raw:
            try:
                eo_number = int(eo_number_raw)
            except (ValueError, TypeError):
                pass
        if not eo_number and title:
            # Try parsing from title like "Executive Order 14009"
            import re
            match = re.search(r"Executive Order[:\s]+(\d+)", title, re.IGNORECASE)
            if match:
                eo_number = int(match.group(1))

        # President info from the API
        president = raw_eo.get("president", {})
        president_name = president.get("name", "Unknown")
        president_id = president.get("identifier")

        return {
            "eo_number": eo_number,
            "document_number": document_number,
            "title": title,
            "abstract": raw_eo.get("abstract"),
            "full_text": None,  # Fetched separately if needed
            "president": president_name,
            "president_id": president_id,
            "signing_date": raw_eo.get("signing_date"),
            "publication_date": raw_eo.get("publication_date"),
            "html_url": raw_eo.get("html_url"),
            "pdf_url": raw_eo.get("pdf_url"),
            "raw_text_url": raw_eo.get("raw_text_url"),
            "status": "active",  # Default; revocation tracking is separate
            "revoked_by_eo": None,
            # Extra metadata for JSONB field
            "type": raw_eo.get("type"),
            "subtype": raw_eo.get("subtype"),
            "agencies": raw_eo.get("agencies", []),
            "topics": raw_eo.get("topics", []),
            "citation": raw_eo.get("citation"),
        }

    def _fetch_full_text(self, raw_text_url: str) -> Optional[str]:
        """Fetch full text content from raw text URL"""
        try:
            response = self.session.get(raw_text_url, timeout=30)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            print(f"Failed to fetch full text: {str(e)[:50]}")
            return None

    def get_order_by_document_number(self, document_number: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single EO by its Federal Register document number.

        Args:
            document_number: The FR document number (e.g., "2021-01753")

        Returns:
            Normalized EO dict or None if not found
        """
        response = self._make_request(f"documents/{document_number}")

        if not response:
            return None

        return self._normalize_executive_order(response)

    def get_proposed_rules(
        self,
        since_date: Optional[str] = None,
        agency_ids: Optional[List[str]] = None,
        per_page: int = 100,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch proposed rules (NPRMs) with open comment periods.

        These are the primary federal participation mechanism — proposed rules
        have mandatory public comment periods where citizens can submit feedback.

        Args:
            since_date: ISO date string (YYYY-MM-DD) for incremental fetch
            agency_ids: Optional list of agency slugs to filter (e.g., ["HUD", "EPA"])
            per_page: Results per page (max 1000)
            max_pages: Maximum pages to fetch

        Returns:
            List of rule dictionaries normalized for storage in federal_rules table
        """
        return self._fetch_rules(
            document_type="PRORULE",
            since_date=since_date,
            agency_ids=agency_ids,
            per_page=per_page,
            max_pages=max_pages,
        )

    def get_final_rules(
        self,
        since_date: Optional[str] = None,
        agency_ids: Optional[List[str]] = None,
        per_page: int = 100,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch final rules published in the Federal Register.

        Args:
            since_date: ISO date string (YYYY-MM-DD) for incremental fetch
            agency_ids: Optional list of agency slugs to filter
            per_page: Results per page (max 1000)
            max_pages: Maximum pages to fetch

        Returns:
            List of rule dictionaries normalized for storage
        """
        return self._fetch_rules(
            document_type="RULE",
            since_date=since_date,
            agency_ids=agency_ids,
            per_page=per_page,
            max_pages=max_pages,
        )

    def get_notices(
        self,
        since_date: Optional[str] = None,
        agency_ids: Optional[List[str]] = None,
        per_page: int = 100,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Fetch notices from the Federal Register.

        Args:
            since_date: ISO date string (YYYY-MM-DD) for incremental fetch
            agency_ids: Optional list of agency slugs to filter
            per_page: Results per page (max 1000)
            max_pages: Maximum pages to fetch

        Returns:
            List of notice dictionaries normalized for storage
        """
        return self._fetch_rules(
            document_type="NOTICE",
            since_date=since_date,
            agency_ids=agency_ids,
            per_page=per_page,
            max_pages=max_pages,
        )

    def _fetch_rules(
        self,
        document_type: str,
        since_date: Optional[str] = None,
        agency_ids: Optional[List[str]] = None,
        per_page: int = 100,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Internal method to fetch rulemaking documents from Federal Register.

        Args:
            document_type: "PRORULE" (proposed), "RULE" (final), or "NOTICE"
            since_date: ISO date string for incremental fetch
            agency_ids: Optional agency slug filter
            per_page: Results per page
            max_pages: Max pages to fetch

        Returns:
            List of normalized rule dictionaries
        """
        all_rules = []
        page = 1

        base_params = {
            "conditions[type]": document_type,
            "per_page": min(per_page, 1000),
            "order": "newest",
            "fields[]": [
                "document_number",
                "title",
                "abstract",
                "agencies",
                "agency_names",
                "publication_date",
                "comment_url",
                "comments_close_on",
                "regulation_id_numbers",
                "docket_ids",
                "pdf_url",
                "html_url",
                "type",
                "subtype",
                "topics",
            ],
        }

        if since_date:
            base_params["conditions[publication_date][gte]"] = since_date

        if agency_ids:
            for i, agency in enumerate(agency_ids):
                base_params[f"conditions[agencies][]"] = agency

        while page <= max_pages:
            params = {**base_params, "page": page}
            response = self._make_request("documents", params)

            if not response:
                print(f"Failed to fetch page {page}, stopping")
                break

            results = response.get("results", [])
            if not results:
                break

            for raw_rule in results:
                normalized = self._normalize_rule(raw_rule, document_type)
                if normalized:
                    all_rules.append(normalized)

            total_pages = response.get("total_pages", 1)
            if page >= total_pages:
                break

            page += 1

        return all_rules

    def _normalize_rule(self, raw: Dict, document_type: str) -> Optional[Dict[str, Any]]:
        """
        Normalize a Federal Register rulemaking document.

        Maps Federal Register schema -> federal_rules table schema.
        """
        document_number = raw.get("document_number")
        if not document_number:
            return None

        # Map FR document type to our internal type
        type_map = {
            "PRORULE": "proposed_rule",
            "RULE": "final_rule",
            "NOTICE": "notice",
        }

        # Extract agency names
        agency_names = raw.get("agency_names", [])
        if not agency_names:
            agencies = raw.get("agencies", [])
            agency_names = [a.get("name", "") for a in agencies if isinstance(a, dict)]

        return {
            "document_number": document_number,
            "title": raw.get("title", ""),
            "abstract": raw.get("abstract"),
            "agency_names": agency_names,
            "publication_date": raw.get("publication_date"),
            "comments_close_on": raw.get("comments_close_on"),
            "comment_url": raw.get("comment_url"),
            "html_url": raw.get("html_url"),
            "pdf_url": raw.get("pdf_url"),
            "regulation_id_numbers": raw.get("regulation_id_numbers", []),
            "docket_ids": raw.get("docket_ids", []),
            "document_type": type_map.get(document_type, document_type.lower()),
            "topics": raw.get("topics", []),
        }

    def get_current_president_eos(
        self,
        president_name: str = None,
        per_page: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Fetch EOs from a specific president.

        Args:
            president_name: President name filter (e.g., "Biden")
            per_page: Results per page

        Returns:
            List of normalized EO dicts
        """
        params = {
            "conditions[type]": "PRESDOCU",
            "conditions[presidential_document_type]": "executive_order",
            "per_page": per_page,
            "order": "newest",
        }

        if president_name:
            params["conditions[president]"] = president_name

        response = self._make_request("documents", params)

        if not response:
            return []

        results = []
        for raw_eo in response.get("results", []):
            normalized = self._normalize_executive_order(raw_eo)
            if normalized:
                results.append(normalized)

        return results


# Convenience function for common operation
def get_recent_executive_orders(days_back: int = 30) -> List[Dict[str, Any]]:
    """Get executive orders from the last N days"""
    from datetime import timedelta

    since = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    client = FederalRegisterClient()
    return client.fetch_executive_orders(since_date=since)


# Example usage
if __name__ == "__main__":
    print("Testing Federal Register Client")
    print("=" * 50)

    client = FederalRegisterClient()

    # Test 1: Fetch recent EOs
    print("\nFetching recent Executive Orders...")
    orders = client.fetch_executive_orders(per_page=5, max_pages=1)
    print(f"Found {len(orders)} EOs")

    if orders:
        eo = orders[0]
        print(f"\nSample EO:")
        print(f"  Number: EO-{eo.get('eo_number')}")
        print(f"  Title: {eo.get('title', '')[:60]}...")
        print(f"  President: {eo.get('president')}")
        print(f"  Published: {eo.get('publication_date')}")
        print(f"  Document: {eo.get('document_number')}")

    # Test 2: Incremental fetch (last 7 days)
    print("\n\nTesting incremental fetch (last 7 days)...")
    recent = get_recent_executive_orders(days_back=7)
    print(f"Found {len(recent)} EOs in last 7 days")

    # Test 3: Proposed rules with comment periods
    print("\n\nFetching proposed rules with comment periods...")
    rules = client.get_proposed_rules(per_page=5, max_pages=1)
    print(f"Found {len(rules)} proposed rules")
    for rule in rules[:3]:
        print(f"\n  Title: {rule['title'][:80]}...")
        print(f"  Agency: {', '.join(rule.get('agency_names', []))}")
        print(f"  Comments close: {rule.get('comments_close_on', 'N/A')}")
        print(f"  Comment URL: {rule.get('comment_url', 'N/A')}")

    print("\n" + "=" * 50)
    print("Federal Register client test complete!")
