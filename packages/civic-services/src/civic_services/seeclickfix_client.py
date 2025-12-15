"""
SeeClickFix API v2 client for Civic Conversational OS

Fetches operational complaints (potholes, stormwater, illegal dumping, etc.)
from SeeClickFix's public API to bridge operational 311 → policy engagement.

Key capabilities:
- City-specific issue queries (place_url)
- Neighborhood-specific queries (lat/lng + radius)
- Pagination support
- Status and category filtering
- Robust error handling with retry logic
"""

import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode

class SeeClickFixClient:
    """SeeClickFix API v2 client for operational complaint tracking"""

    def __init__(self):
        self.base_url = "https://seeclickfix.com/api/v2"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Civic Conversational OS (civic-power-bridge)',
            'Accept': 'application/json'
        })
        self.last_request_time = 0
        self.min_request_interval = 0.5  # Respectful rate limiting

    def _throttle_request(self):
        """Prevent burst requests"""
        now = time.time()
        if now - self.last_request_time < self.min_request_interval:
            time.sleep(self.min_request_interval)
        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Dict = None, retries: int = 3) -> Any:
        """Make API request with exponential backoff"""
        self._throttle_request()

        url = f"{self.base_url}/{endpoint}"

        for attempt in range(retries):
            try:
                response = self.session.get(url, params=params, timeout=10)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code in [429, 500, 502, 503]:
                    # Exponential backoff for server issues
                    wait_time = 2 ** attempt
                    print(f"⚠️ SeeClickFix Status {response.status_code}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"❌ SeeClickFix API Error {response.status_code}: {response.text[:200]}")
                    return None

            except Exception as e:
                print(f"❌ SeeClickFix request failed: {str(e)[:100]}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None

        return None

    def get_issues(
        self,
        place_url: str = None,
        lat: float = None,
        lng: float = None,
        radius: int = 5000,
        per_page: int = 20,
        page: int = 1,
        status: str = "open",
        request_types: List[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch operational issues from SeeClickFix.

        Args:
            place_url: City identifier (e.g., "san-rafael")
            lat: Latitude for geographic search
            lng: Longitude for geographic search
            radius: Search radius in meters (default: 5000)
            per_page: Results per page (default: 20, max: 100)
            page: Page number (default: 1)
            status: Filter by status - "open", "closed", "acknowledged", or None for all
            request_types: List of request type IDs to filter by

        Returns:
            {
                "issues": [...],
                "metadata": {
                    "page": 1,
                    "per_page": 20,
                    "total_pages": 5,
                    "has_more": true
                }
            }
        """
        params = {
            'per_page': min(per_page, 100),  # API max is 100
            'page': page
        }

        # Location filters (mutually exclusive)
        if place_url:
            params['place_url'] = place_url
        elif lat and lng:
            params['lat'] = lat
            params['lng'] = lng
            params['zoom'] = self._calculate_zoom_from_radius(radius)

        # Status filter
        if status:
            params['status'] = status

        # Request type filter
        if request_types:
            params['request_types'] = ','.join(map(str, request_types))

        response = self._make_request('issues', params)

        if not response:
            return {
                "issues": [],
                "metadata": {
                    "page": page,
                    "per_page": per_page,
                    "total_pages": 0,
                    "has_more": False,
                    "error": "Failed to fetch issues"
                }
            }

        # SeeClickFix returns direct array or paginated object
        if isinstance(response, list):
            issues = response
            metadata = {
                "page": page,
                "per_page": per_page,
                "total_pages": 1 if len(issues) == per_page else page,
                "has_more": len(issues) == per_page
            }
        else:
            issues = response.get('issues', [])
            metadata = response.get('metadata', {
                "page": page,
                "per_page": per_page,
                "total_pages": 1,
                "has_more": False
            })

        return {
            "issues": [self._normalize_issue(issue) for issue in issues],
            "metadata": metadata
        }

    def get_issue_by_id(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch a single issue by ID.

        Args:
            issue_id: SeeClickFix issue ID

        Returns:
            Normalized issue dict or None if not found
        """
        response = self._make_request(f'issues/{issue_id}')

        if not response:
            return None

        return self._normalize_issue(response)

    def _normalize_issue(self, raw_issue: Dict) -> Dict[str, Any]:
        """
        Normalize SeeClickFix issue to our internal format.

        Maps SeeClickFix schema → Civic Conversational OS schema
        """
        return {
            # Core fields
            "id": f"scf-{raw_issue.get('id')}",  # Prefix to distinguish from policy issues
            "external_id": raw_issue.get('id'),
            "source": "seeclickfix",
            "issue_type": "operational",  # vs. "policy"
            "title": raw_issue.get('summary', ''),
            "description": raw_issue.get('description', ''),
            "status": raw_issue.get('status', '').lower(),

            # Location
            "location": {
                "address": raw_issue.get('address', ''),
                "lat": raw_issue.get('lat'),
                "lng": raw_issue.get('lng'),
                "point": raw_issue.get('point')  # GeoJSON point
            },

            # Category/Type
            "category": raw_issue.get('request_type', {}).get('title', ''),
            "category_id": raw_issue.get('request_type', {}).get('id'),
            "organization": raw_issue.get('request_type', {}).get('organization', ''),

            # Timestamps
            "created_at": raw_issue.get('created_at'),
            "updated_at": raw_issue.get('updated_at'),
            "acknowledged_at": raw_issue.get('acknowledged_at'),
            "closed_at": raw_issue.get('closed_at'),
            "reopened_at": raw_issue.get('reopened_at'),

            # Reporter
            "reporter": {
                "id": raw_issue.get('reporter', {}).get('id'),
                "name": raw_issue.get('reporter', {}).get('name', 'Anonymous'),
                "role": raw_issue.get('reporter', {}).get('role', 'Guest'),
                "avatar": raw_issue.get('reporter', {}).get('avatar', {}).get('square_100x100'),
                "civic_points": raw_issue.get('reporter', {}).get('civic_points', 0)
            },

            # Media
            "media": {
                "image_url": raw_issue.get('media', {}).get('image_full'),
                "image_thumbnail": raw_issue.get('media', {}).get('image_square_100x100'),
                "video_url": raw_issue.get('media', {}).get('video_url')
            },

            # Engagement
            "rating": raw_issue.get('rating', 0),
            "comment_count": raw_issue.get('comment_count', 0),

            # Links
            "html_url": raw_issue.get('html_url'),
            "api_url": raw_issue.get('url'),
            "comment_url": raw_issue.get('comment_url'),

            # Raw metadata (for debugging/future use)
            "_seeclickfix_metadata": {
                "transitions": raw_issue.get('transitions', {}),
                "private_visibility": raw_issue.get('private_visibility', False),
                "show_blocked_issue_text": raw_issue.get('show_blocked_issue_text', False)
            }
        }

    def _calculate_zoom_from_radius(self, radius_meters: int) -> int:
        """
        Calculate appropriate zoom level from radius.

        SeeClickFix uses zoom levels instead of radius directly.
        Zoom levels: 1 (world) to 18 (building)
        """
        # Rough conversion (meters to zoom level)
        # https://wiki.openstreetmap.org/wiki/Zoom_levels
        if radius_meters >= 50000:
            return 10  # ~50km
        elif radius_meters >= 20000:
            return 11  # ~20km
        elif radius_meters >= 10000:
            return 12  # ~10km
        elif radius_meters >= 5000:
            return 13  # ~5km (default)
        elif radius_meters >= 2000:
            return 14  # ~2km
        elif radius_meters >= 1000:
            return 15  # ~1km
        else:
            return 16  # <1km

    def get_place_url_for_city(self, city_name: str, state: str = None) -> str:
        """
        Generate place_url from city name.

        Examples:
            "San Rafael" → "san-rafael"
            "New York City" → "new-york-city"
        """
        place_url = city_name.lower().replace(' ', '-')

        # Remove common suffixes
        place_url = place_url.replace('-city', '')

        return place_url

    def get_issues_summary(
        self,
        place_url: str = None,
        lat: float = None,
        lng: float = None,
        radius: int = 5000,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get summary statistics for issues in a location.

        Args:
            place_url: City identifier
            lat: Latitude for geographic search
            lng: Longitude for geographic search
            radius: Search radius in meters
            days: Number of days to look back (default: 30)

        Returns:
            {
                "total_open": 15,
                "total_closed": 8,
                "by_category": {
                    "Pothole/Road Condition": 5,
                    "Stormwater Drainage": 3,
                    ...
                },
                "recent_issues": [...],
                "oldest_open": {...}
            }
        """
        # Fetch open issues
        open_result = self.get_issues(
            place_url=place_url,
            lat=lat,
            lng=lng,
            radius=radius,
            status="open",
            per_page=100
        )

        # Fetch closed issues (last 30 days)
        closed_result = self.get_issues(
            place_url=place_url,
            lat=lat,
            lng=lng,
            radius=radius,
            status="closed",
            per_page=100
        )

        open_issues = open_result.get('issues', [])
        closed_issues = closed_result.get('issues', [])

        # Categorize
        by_category = {}
        for issue in open_issues + closed_issues:
            category = issue.get('category', 'Unknown')
            by_category[category] = by_category.get(category, 0) + 1

        # Find oldest open issue
        oldest_open = None
        if open_issues:
            oldest_open = min(
                open_issues,
                key=lambda x: x.get('created_at', '')
            )

        return {
            "total_open": len(open_issues),
            "total_closed": len(closed_issues),
            "by_category": by_category,
            "recent_issues": open_issues[:5],  # Most recent 5
            "oldest_open": oldest_open
        }


# Convenience functions for common operations

def get_san_rafael_issues(per_page: int = 20, page: int = 1, status: str = "open") -> Dict:
    """Get current operational issues in San Rafael"""
    client = SeeClickFixClient()
    return client.get_issues(
        place_url="san-rafael",
        per_page=per_page,
        page=page,
        status=status
    )


def get_issues_near_location(lat: float, lng: float, radius: int = 5000, per_page: int = 20) -> Dict:
    """Get operational issues near a specific location"""
    client = SeeClickFixClient()
    return client.get_issues(
        lat=lat,
        lng=lng,
        radius=radius,
        per_page=per_page,
        status="open"
    )


# Example usage
if __name__ == "__main__":
    print("🔧 Testing SeeClickFix Client")
    print("=" * 50)

    client = SeeClickFixClient()

    # Test 1: Get San Rafael issues
    print("\n📍 Fetching San Rafael operational issues...")
    result = client.get_issues(place_url="san-rafael", per_page=5)
    print(f"✅ Found {len(result['issues'])} issues")

    if result['issues']:
        issue = result['issues'][0]
        print(f"\nSample issue:")
        print(f"  ID: {issue['id']}")
        print(f"  Title: {issue['title']}")
        print(f"  Category: {issue['category']}")
        print(f"  Location: {issue['location']['address']}")
        print(f"  Status: {issue['status']}")
        print(f"  Created: {issue['created_at']}")

    # Test 2: Get summary
    print("\n\n📊 Fetching San Rafael summary...")
    summary = client.get_issues_summary(place_url="san-rafael")
    print(f"✅ Open: {summary['total_open']}, Closed: {summary['total_closed']}")
    print(f"\nBy Category:")
    for category, count in sorted(summary['by_category'].items(), key=lambda x: -x[1])[:5]:
        print(f"  {category}: {count}")

    print("\n" + "=" * 50)
    print("✅ SeeClickFix client test complete!")
