"""
LegiScan API Client - Automated legislative bill discovery.

Free tier: 30,000 queries/month
Cost model: ~$0 operational (within free tier)

Usage:
    client = LegiScanClient(api_key=os.getenv('LEGISCAN_API_KEY'))
    bills = client.search_bills(state='CA', query='housing density')
"""

import os
import requests
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)


class LegiScanClient:
    """
    Client for LegiScan API (legiscan.com).

    Free tier limitations:
    - 30,000 queries/month
    - Pull interface only
    - Requires API key from legiscan.com
    """

    BASE_URL = "https://api.legiscan.com/"

    # State code mapping
    STATE_CODES = {
        "california": "CA",
        "CA": "CA"
    }

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('LEGISCAN_API_KEY')

        if not self.api_key:
            logger.warning(
                "No LegiScan API key found. Set LEGISCAN_API_KEY environment variable. "
                "Register at https://legiscan.com/ for free API access (30,000 queries/month)"
            )

        self.session = requests.Session()
        self.query_count = 0

    def _request(self, operation: str, params: Dict = None) -> Dict:
        """Make API request with error handling and rate limiting"""
        if not self.api_key:
            raise ValueError("LegiScan API key required. Set LEGISCAN_API_KEY environment variable.")

        request_params = {
            'key': self.api_key,
            'op': operation
        }

        if params:
            request_params.update(params)

        try:
            response = self.session.get(self.BASE_URL, params=request_params, timeout=30)
            response.raise_for_status()

            self.query_count += 1

            data = response.json()

            if data.get('status') == 'ERROR':
                logger.error(f"LegiScan API error: {data.get('alert', {}).get('message')}")
                return {}

            return data

        except requests.exceptions.RequestException as e:
            logger.error(f"LegiScan API request failed: {e}")
            return {}

    def search_bills(
        self,
        state: str = "CA",
        query: str = None,
        year: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict]:
        """
        Search for bills by state and keywords.

        Args:
            state: State code (e.g., 'CA' for California)
            query: Search keywords (e.g., 'housing density')
            year: Legislative year (defaults to current year)
            limit: Maximum number of results

        Returns:
            List of bill summaries with basic metadata
        """
        state_code = self.STATE_CODES.get(state, state)
        year = year or datetime.now().year

        # Use getSearch operation
        params = {
            'state': state_code,
            'query': query or ''
        }

        if year:
            params['year'] = year

        logger.info(f"Searching LegiScan: state={state_code}, query={query}, year={year}")

        result = self._request('getSearch', params)

        if not result or 'searchresult' not in result:
            logger.warning(f"No search results for query: {query}")
            return []

        bills = []
        search_results = result.get('searchresult', {})

        # LegiScan returns dict where keys are 'summary', or numeric indices for results
        # Filter out metadata keys and process only bill results
        count = 0
        for key, item in search_results.items():
            if key == 'summary':
                continue  # Skip summary metadata

            if isinstance(item, dict) and 'bill_id' in item:
                bills.append({
                    'bill_id': item.get('bill_id'),
                    'bill_number': item.get('bill_number'),
                    'title': item.get('title'),
                    'description': item.get('description'),
                    'state': item.get('state'),
                    'session': item.get('session'),
                    'status': item.get('status'),
                    'status_date': item.get('status_date'),
                    'url': item.get('url'),
                    'last_action': item.get('last_action'),
                    'last_action_date': item.get('last_action_date')
                })
                count += 1
                if count >= limit:
                    break

        logger.info(f"Found {len(bills)} bills matching query: {query}")

        return bills

    def get_bill_details(self, bill_id: int) -> Optional[Dict]:
        """
        Get full details for a specific bill.

        Args:
            bill_id: LegiScan bill ID

        Returns:
            Full bill details including text, sponsors, amendments
        """
        logger.info(f"Fetching bill details for bill_id={bill_id}")

        result = self._request('getBill', {'id': bill_id})

        if not result or 'bill' not in result:
            logger.warning(f"No details found for bill_id={bill_id}")
            return None

        return result.get('bill')

    def get_master_list(
        self,
        state: str = "CA",
        session_id: Optional[int] = None
    ) -> List[Dict]:
        """
        Get master list of all bills for a state/session.

        Warning: This is a large query (can return 1000+ bills).
        Use sparingly to stay within rate limits.

        Args:
            state: State code
            session_id: Legislative session ID (optional)

        Returns:
            List of all bills in session
        """
        state_code = self.STATE_CODES.get(state, state)

        params = {'state': state_code}
        if session_id:
            params['id'] = session_id

        logger.warning(f"Fetching master list for {state_code} (large query)")

        result = self._request('getMasterList', params)

        if not result or 'masterlist' not in result:
            return []

        # Extract bill list from masterlist response
        masterlist = result.get('masterlist', {})
        bills = [v for k, v in masterlist.items() if isinstance(v, dict) and 'bill_id' in v]

        logger.info(f"Retrieved {len(bills)} bills from master list")

        return bills

    def get_recent_bills(
        self,
        state: str = "CA",
        topic_keywords: List[str] = None,
        days_back: int = 30
    ) -> List[Dict]:
        """
        Get recent bills matching topic keywords.

        Args:
            state: State code
            topic_keywords: List of keywords to search (e.g., ['housing', 'density'])
            days_back: How many days back to search

        Returns:
            List of recent bills matching keywords
        """
        if not topic_keywords:
            topic_keywords = []

        all_bills = []

        # Search for each keyword
        for keyword in topic_keywords:
            bills = self.search_bills(state=state, query=keyword, limit=20)

            # Filter to recent bills only
            cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

            recent_bills = [
                b for b in bills
                if b.get('last_action_date', '') >= cutoff_date
            ]

            all_bills.extend(recent_bills)

            # Rate limiting: small delay between searches
            time.sleep(0.5)

        # Deduplicate by bill_id
        seen = set()
        unique_bills = []
        for bill in all_bills:
            bill_id = bill.get('bill_id')
            if bill_id and bill_id not in seen:
                seen.add(bill_id)
                unique_bills.append(bill)

        logger.info(
            f"Found {len(unique_bills)} unique recent bills "
            f"(searched {len(topic_keywords)} keywords, last {days_back} days)"
        )

        return unique_bills

    def get_query_stats(self) -> Dict:
        """Get API usage statistics"""
        return {
            'queries_this_session': self.query_count,
            'monthly_limit': 30000,
            'estimated_remaining': 30000 - self.query_count
        }


# Topic-specific keyword sets for discovery
TOPIC_KEYWORDS = {
    "housing": ["housing", "affordable housing", "zoning", "density", "ADU", "duplex", "RHNA"],
    "transportation": ["transportation", "transit", "bicycle", "pedestrian", "VMT", "complete streets"],
    "environment": ["climate", "environment", "sustainability", "clean energy", "emissions", "conservation"],
    "budget": ["budget", "tax", "revenue", "bond", "fiscal", "appropriation"],
    "education": ["education", "school", "college", "student", "teacher", "curriculum"]
}
