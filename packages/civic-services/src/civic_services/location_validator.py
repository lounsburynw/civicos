#!/usr/bin/env python3
"""
Location Validator - IP Geolocation Anti-Bot Protection
Validates that user's IP address is within reasonable distance of claimed address

Prevents astroturfing from out-of-area actors while preserving privacy
"""

import os
import requests
import math
from typing import Dict, Optional, Tuple, Any


class LocationValidator:
    """
    IP-based location validation to prevent astroturfing

    Uses IP geolocation to verify user is within ~50 miles of claimed address.
    This prevents bulk bot signups from distant locations while allowing
    legitimate users (VPN, mobile, travel) to still participate.
    """

    def __init__(self, ipinfo_token: Optional[str] = None):
        """
        Initialize with IPinfo API token (optional)

        Free tier: 50,000 requests/month
        No token = fallback to ip-api.com (45 req/min limit)
        """
        self.ipinfo_token = ipinfo_token or os.getenv('IPINFO_TOKEN')

        # Use IPinfo if token available, otherwise fallback to ip-api
        self.use_ipinfo = bool(self.ipinfo_token)

        if self.use_ipinfo:
            self.base_url = "https://ipinfo.io"
        else:
            self.base_url = "http://ip-api.com/json"

    def validate_location(
        self,
        user_ip: str,
        claimed_lat: float,
        claimed_lng: float,
        max_distance_miles: float = 50.0
    ) -> Dict[str, Any]:
        """
        Validate that user's IP is within max_distance of claimed address

        Args:
            user_ip: User's IP address from request
            claimed_lat: Latitude of claimed address
            claimed_lng: Longitude of claimed address
            max_distance_miles: Maximum acceptable distance (default 50 miles)

        Returns:
            {
                "valid": bool,           # True if within max_distance
                "distance_miles": float, # Actual distance in miles
                "ip_location": {
                    "city": "Oakland",
                    "region": "California",
                    "lat": 37.8,
                    "lng": -122.27
                },
                "reason": str           # Explanation if invalid
            }
        """
        try:
            # Skip validation for localhost/private IPs (development)
            if self._is_local_ip(user_ip):
                return {
                    'valid': True,
                    'distance_miles': 0.0,
                    'ip_location': {
                        'city': 'localhost',
                        'region': 'dev',
                        'lat': claimed_lat,
                        'lng': claimed_lng
                    },
                    'reason': 'localhost/private IP - validation skipped'
                }

            # Get IP geolocation
            ip_location = self._geolocate_ip(user_ip)

            if not ip_location:
                # Failed to geolocate - allow but log
                print(f"[location_validator] WARNING: Could not geolocate IP {user_ip}")
                return {
                    'valid': True,  # Fail open (don't block legitimate users)
                    'distance_miles': None,
                    'ip_location': None,
                    'reason': 'IP geolocation unavailable - allowed'
                }

            # Calculate distance
            distance = self._calculate_distance(
                ip_location['lat'],
                ip_location['lng'],
                claimed_lat,
                claimed_lng
            )

            # Validate distance
            valid = distance <= max_distance_miles

            return {
                'valid': valid,
                'distance_miles': round(distance, 2),
                'ip_location': ip_location,
                'reason': (
                    'Valid - within acceptable distance'
                    if valid
                    else f'Too far - {distance:.1f} miles exceeds {max_distance_miles} mile limit'
                )
            }

        except Exception as e:
            print(f"[location_validator] Validation error: {str(e)}")
            import traceback
            traceback.print_exc()

            # Fail open - don't block users due to validation errors
            return {
                'valid': True,
                'distance_miles': None,
                'ip_location': None,
                'reason': f'Validation error - allowed: {str(e)}'
            }

    def _is_local_ip(self, ip: str) -> bool:
        """Check if IP is localhost or private network"""
        if not ip or ip in ['localhost', '127.0.0.1', '::1']:
            return True

        # Check private IP ranges
        parts = ip.split('.')
        if len(parts) == 4:
            first = int(parts[0])
            second = int(parts[1])

            # 10.0.0.0/8
            if first == 10:
                return True

            # 172.16.0.0/12
            if first == 172 and 16 <= second <= 31:
                return True

            # 192.168.0.0/16
            if first == 192 and second == 168:
                return True

        return False

    def _geolocate_ip(self, ip: str) -> Optional[Dict[str, Any]]:
        """
        Geolocate an IP address

        Returns:
            {
                "city": "Oakland",
                "region": "California",
                "country": "US",
                "lat": 37.8,
                "lng": -122.27
            }
        """
        try:
            if self.use_ipinfo:
                # IPinfo.io (requires token)
                url = f"{self.base_url}/{ip}/json"
                params = {'token': self.ipinfo_token}
                response = requests.get(url, params=params, timeout=5)
                response.raise_for_status()
                data = response.json()

                # Parse IPinfo response
                loc = data.get('loc', '').split(',')
                if len(loc) != 2:
                    return None

                return {
                    'city': data.get('city'),
                    'region': data.get('region'),
                    'country': data.get('country'),
                    'lat': float(loc[0]),
                    'lng': float(loc[1])
                }

            else:
                # ip-api.com (free, no token required)
                url = f"{self.base_url}/{ip}"
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                data = response.json()

                if data.get('status') != 'success':
                    return None

                return {
                    'city': data.get('city'),
                    'region': data.get('regionName'),
                    'country': data.get('countryCode'),
                    'lat': data.get('lat'),
                    'lng': data.get('lon')
                }

        except requests.RequestException as e:
            print(f"[location_validator] IP geolocation API error: {str(e)}")
            return None
        except Exception as e:
            print(f"[location_validator] IP geolocation parse error: {str(e)}")
            return None

    def _calculate_distance(
        self,
        lat1: float,
        lng1: float,
        lat2: float,
        lng2: float
    ) -> float:
        """
        Calculate distance between two coordinates using Haversine formula

        Returns distance in miles
        """
        # Radius of Earth in miles
        R = 3959.0

        # Convert to radians
        lat1_rad = math.radians(lat1)
        lng1_rad = math.radians(lng1)
        lat2_rad = math.radians(lat2)
        lng2_rad = math.radians(lng2)

        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlng = lng2_rad - lng1_rad

        a = (
            math.sin(dlat / 2) ** 2 +
            math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlng / 2) ** 2
        )

        c = 2 * math.asin(math.sqrt(a))

        distance = R * c

        return distance


# Global instance (lazy-loaded)
_location_validator: Optional[LocationValidator] = None


def get_location_validator() -> LocationValidator:
    """Get or create global location validator instance"""
    global _location_validator

    if _location_validator is None:
        _location_validator = LocationValidator()

    return _location_validator


# Test/CLI interface
if __name__ == '__main__':
    import sys

    if len(sys.argv) < 4:
        print("Usage: python location_validator.py <ip> <lat> <lng>")
        print("Example: python location_validator.py 8.8.8.8 37.8044 -122.2712")
        sys.exit(1)

    user_ip = sys.argv[1]
    claimed_lat = float(sys.argv[2])
    claimed_lng = float(sys.argv[3])

    print(f"Validating IP: {user_ip}")
    print(f"Claimed location: {claimed_lat}, {claimed_lng}")
    print()

    validator = get_location_validator()
    result = validator.validate_location(user_ip, claimed_lat, claimed_lng)

    print("Validation result:")
    import json
    print(json.dumps(result, indent=2))

    if result['valid']:
        print("\n✅ Validation PASSED")
    else:
        print("\n❌ Validation FAILED")
        sys.exit(1)
