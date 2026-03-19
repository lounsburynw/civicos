#!/usr/bin/env python3
"""
Geocoding Service - Google Maps API Integration
Converts addresses to coordinates and determines jurisdictions

Privacy-preserving: Only stores lat/lng, not full addresses
"""

import os
import requests
from typing import Dict, Optional, List, Any
from urllib.parse import urlencode


class GeocodingService:
    """
    Wrapper for Google Maps Geocoding API

    Converts user addresses to:
    - Latitude/longitude coordinates
    - City, county, state information
    - Jurisdiction IDs for filtering
    """

    def __init__(self, api_key: Optional[str] = None):
        """Initialize with Google Maps API key"""
        self.api_key = api_key or os.getenv('GOOGLE_MAPS_API_KEY')
        if not self.api_key:
            raise ValueError(
                "Google Maps API key required. "
                "Set GOOGLE_MAPS_API_KEY environment variable."
            )

        self.base_url = "https://maps.googleapis.com/maps/api/geocode/json"

        # Jurisdiction ID mapping (city name -> jurisdiction_id)
        # Matches CITY_CONFIGS in automated_civic_refresh.py
        self.city_to_jurisdiction = {
            "Oakland": "city-oakland",
            "Berkeley": "city-berkeley",
            "Hayward": "city-hayward",
            "San Leandro": "city-san-leandro",
            "Union City": "city-union-city",
            "Dublin": "city-dublin",
            "Pleasanton": "city-pleasanton",
            "El Cerrito": "city-el-cerrito",
            "Concord": "city-concord",
            "Pleasant Hill": "city-pleasant-hill",
            "Pinole": "city-pinole",
            "Pittsburg": "city-pittsburg",
            "Antioch": "city-antioch",
            "Richmond": "city-richmond",
            "San Rafael": "city-san-rafael",
            "Santa Rosa": "city-santa-rosa",
        }

        # County name mapping
        self.county_to_jurisdiction = {
            "Alameda County": "county-alameda",
            "Contra Costa County": "county-contra-costa",
            "Marin County": "county-marin",
            "Sonoma County": "county-sonoma",
        }

    def geocode_address(self, address: str) -> Optional[Dict[str, Any]]:
        """
        Geocode an address to coordinates and jurisdictions

        Args:
            address: User-provided address (e.g., "123 Oak St, Oakland, CA")

        Returns:
            {
                "lat": 37.8044,
                "lng": -122.2712,
                "formatted_address": "123 Oak St, Oakland, CA 94612, USA",
                "city": "Oakland",
                "county": "Alameda County",
                "state": "California",
                "zip_code": "94612",
                "street_name": "Oak St",  # For display name (privacy)
                "jurisdictions": {
                    "city": "city-oakland",
                    "county": "alameda-county"
                }
            }

            Returns None if geocoding fails
        """
        try:
            # Call Google Maps Geocoding API
            params = {
                'address': address,
                'key': self.api_key
            }

            response = requests.get(self.base_url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()

            if data['status'] != 'OK' or not data.get('results'):
                print(f"[geocoding] Geocoding failed: {data.get('status')}")
                return None

            # Parse first result
            result = data['results'][0]
            geometry = result['geometry']
            location = geometry['location']

            # Extract address components
            components = self._parse_address_components(result['address_components'])

            # Determine jurisdictions
            jurisdictions = self._determine_jurisdictions(components)

            return {
                'lat': location['lat'],
                'lng': location['lng'],
                'formatted_address': result['formatted_address'],
                'city': components.get('city'),
                'county': components.get('county'),
                'state': components.get('state'),
                'zip_code': components.get('zip_code'),
                'street_name': components.get('street_name'),
                'jurisdictions': jurisdictions
            }

        except requests.RequestException as e:
            print(f"[geocoding] API request failed: {str(e)}")
            return None
        except Exception as e:
            print(f"[geocoding] Unexpected error: {str(e)}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_address_components(
        self,
        components: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        Parse Google Maps address components into structured data

        Args:
            components: List of address component dicts from Google Maps API

        Returns:
            Dict with city, county, state, zip_code, street_name
        """
        parsed = {}

        for component in components:
            types = component['types']
            long_name = component['long_name']
            short_name = component['short_name']

            # City
            if 'locality' in types:
                parsed['city'] = long_name

            # County
            elif 'administrative_area_level_2' in types:
                parsed['county'] = long_name

            # State
            elif 'administrative_area_level_1' in types:
                parsed['state'] = long_name

            # ZIP code
            elif 'postal_code' in types:
                parsed['zip_code'] = short_name

            # Street name (for display name - privacy preserving)
            elif 'route' in types:
                parsed['street_name'] = long_name

        return parsed

    def _determine_jurisdictions(
        self,
        components: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Map city/county to jurisdiction IDs

        Args:
            components: Parsed address components (city, county, etc.)

        Returns:
            {
                "city": "city-oakland",
                "county": "alameda-county"
            }
        """
        jurisdictions = {}

        # Map city
        city = components.get('city')
        if city and city in self.city_to_jurisdiction:
            jurisdictions['city'] = self.city_to_jurisdiction[city]

        # Map county
        county = components.get('county')
        if county and county in self.county_to_jurisdiction:
            jurisdictions['county'] = self.county_to_jurisdiction[county]

        return jurisdictions

    def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict[str, Any]]:
        """
        Reverse geocode coordinates to address (for validation)

        Args:
            lat: Latitude
            lng: Longitude

        Returns:
            Same format as geocode_address()
        """
        try:
            params = {
                'latlng': f"{lat},{lng}",
                'key': self.api_key
            }

            response = requests.get(self.base_url, params=params, timeout=5)
            response.raise_for_status()

            data = response.json()

            if data['status'] != 'OK' or not data.get('results'):
                return None

            result = data['results'][0]
            components = self._parse_address_components(result['address_components'])
            jurisdictions = self._determine_jurisdictions(components)

            return {
                'lat': lat,
                'lng': lng,
                'formatted_address': result['formatted_address'],
                'city': components.get('city'),
                'county': components.get('county'),
                'state': components.get('state'),
                'zip_code': components.get('zip_code'),
                'street_name': components.get('street_name'),
                'jurisdictions': jurisdictions
            }

        except Exception as e:
            print(f"[geocoding] Reverse geocoding failed: {str(e)}")
            return None


# Global instance (lazy-loaded)
_geocoding_service: Optional[GeocodingService] = None


def get_geocoding_service() -> GeocodingService:
    """Get or create global geocoding service instance"""
    global _geocoding_service

    if _geocoding_service is None:
        _geocoding_service = GeocodingService()

    return _geocoding_service


# Test/CLI interface
if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python geocoding_service.py <address>")
        print("Example: python geocoding_service.py '123 Oak St, Oakland, CA'")
        sys.exit(1)

    address = ' '.join(sys.argv[1:])

    print(f"Geocoding: {address}")
    print()

    service = get_geocoding_service()
    result = service.geocode_address(address)

    if result:
        print("✅ Geocoding successful:")
        print(json.dumps(result, indent=2))
    else:
        print("❌ Geocoding failed")
        sys.exit(1)
