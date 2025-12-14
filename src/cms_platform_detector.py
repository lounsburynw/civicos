"""
CMS Platform Detection for Municipal Websites
Strategic tool for scaling Berkeley's $0.003/opportunity efficiency through Drupal identification

Key Findings from Bay Area CMS Detection:
- Berkeley (Drupal): $0.003/opportunity cost efficiency (50x better than standard)
- Hayward (Drupal): Same technical fingerprint as Berkeley - high potential
- Richmond (CivicPlus): Different platform, may need different extraction approach
- Albany (Granicus): Different platform, may need different extraction approach
- Emeryville (Granicus): Different platform, may need different extraction approach
- El Cerrito (CivicPlus): Different platform, may need different extraction approach

Strategic Opportunity: Focus on Drupal cities for maximum cost efficiency scaling.
"""

import requests
from typing import Dict, List, Optional
from urllib.parse import urljoin
import re


class CMSPlatformDetector:
    """Detect CMS platforms for municipal websites to optimize data extraction strategies"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; CivicBot/1.0; +civic@example.com)'
        })

    def detect_cms_platform(self, base_url: str) -> Dict[str, any]:
        """
        Detect CMS platform for a municipal website

        Returns:
            Dict with detection results and efficiency predictions
        """
        try:
            response = self.session.get(base_url, timeout=10)
            response.raise_for_status()

            html_content = response.text
            detection_result = {
                'url': base_url,
                'platform': 'unknown',
                'confidence': 0,
                'indicators': [],
                'cost_efficiency_prediction': 'unknown',
                'recommended_extraction_method': 'standard',
                'similar_to': None
            }

            # Drupal Detection (High Priority - Berkeley's $0.003 model)
            drupal_indicators = self._detect_drupal(html_content)
            if drupal_indicators['confidence'] > 0.7:
                detection_result.update({
                    'platform': 'drupal',
                    'confidence': drupal_indicators['confidence'],
                    'indicators': drupal_indicators['indicators'],
                    'cost_efficiency_prediction': 'high',  # Based on Berkeley's $0.003/opportunity
                    'recommended_extraction_method': 'berkeley_cms',
                    'similar_to': 'berkeley'
                })
                return detection_result

            # CivicPlus Detection
            civicplus_indicators = self._detect_civicplus(html_content)
            if civicplus_indicators['confidence'] > 0.8:
                detection_result.update({
                    'platform': 'civicplus',
                    'confidence': civicplus_indicators['confidence'],
                    'indicators': civicplus_indicators['indicators'],
                    'cost_efficiency_prediction': 'medium',
                    'recommended_extraction_method': 'standard',
                    'similar_to': 'richmond'
                })
                return detection_result

            # Granicus Detection
            granicus_indicators = self._detect_granicus(html_content)
            if granicus_indicators['confidence'] > 0.8:
                detection_result.update({
                    'platform': 'granicus',
                    'confidence': granicus_indicators['confidence'],
                    'indicators': granicus_indicators['indicators'],
                    'cost_efficiency_prediction': 'medium',
                    'recommended_extraction_method': 'standard',
                    'similar_to': 'albany'
                })
                return detection_result

            # Check for highest confidence fallback
            all_detections = [drupal_indicators, civicplus_indicators, granicus_indicators]
            best_detection = max(all_detections, key=lambda x: x['confidence'])

            if best_detection['confidence'] > 0.3:
                platform_map = {
                    drupal_indicators: 'drupal',
                    civicplus_indicators: 'civicplus',
                    granicus_indicators: 'granicus'
                }

                detection_result.update({
                    'platform': platform_map[best_detection],
                    'confidence': best_detection['confidence'],
                    'indicators': best_detection['indicators'],
                    'cost_efficiency_prediction': 'unknown',
                    'recommended_extraction_method': 'standard'
                })

            return detection_result

        except Exception as e:
            return {
                'url': base_url,
                'platform': 'error',
                'confidence': 0,
                'indicators': [f"Error: {str(e)}"],
                'cost_efficiency_prediction': 'unknown',
                'recommended_extraction_method': 'standard',
                'error': str(e)
            }

    def _detect_drupal(self, html_content: str) -> Dict[str, any]:
        """Detect Drupal CMS (Priority: Berkeley $0.003/opportunity model)"""
        indicators = []
        confidence_points = 0

        # High-confidence Drupal indicators
        drupal_patterns = [
            (r'jQuery\.extend\(Drupal\.settings', 'Drupal.settings object', 0.4),
            (r'/sites/all/themes/', 'Drupal file structure', 0.3),
            (r'/sites/all/modules/', 'Drupal modules path', 0.3),
            (r'Drupal\.behaviors', 'Drupal behaviors', 0.3),
            (r'drupal\.js', 'Drupal core JS', 0.2),
            (r'\.views-', 'Views module classes', 0.2),
            (r'\.panels-', 'Panels module classes', 0.2),
            (r'jquery_update', 'jQuery Update module', 0.2),
            (r'generator.*Drupal', 'Drupal meta generator', 0.5),
        ]

        for pattern, description, points in drupal_patterns:
            if re.search(pattern, html_content, re.IGNORECASE):
                indicators.append(description)
                confidence_points += points

        return {
            'confidence': min(confidence_points, 1.0),
            'indicators': indicators
        }

    def _detect_civicplus(self, html_content: str) -> Dict[str, any]:
        """Detect CivicPlus CMS"""
        indicators = []
        confidence_points = 0

        civicplus_patterns = [
            (r'Government Websites by CivicPlus', 'CivicPlus footer', 0.9),
            (r'window\.Pages', 'CivicPlus Pages object', 0.4),
            (r'\.widgetSearch', 'CivicPlus widget classes', 0.3),
            (r'\.InfoAdvanced', 'CivicPlus info classes', 0.3),
            (r'\.fancyButton', 'CivicPlus button classes', 0.2),
            (r'/Calendar\.aspx', 'CivicPlus calendar URLs', 0.3),
            (r'/CivicAlerts\.aspx', 'CivicPlus alerts URLs', 0.3),
        ]

        for pattern, description, points in civicplus_patterns:
            if re.search(pattern, html_content, re.IGNORECASE):
                indicators.append(description)
                confidence_points += points

        return {
            'confidence': min(confidence_points, 1.0),
            'indicators': indicators
        }

    def _detect_granicus(self, html_content: str) -> Dict[str, any]:
        """Detect Granicus CMS"""
        indicators = []
        confidence_points = 0

        granicus_patterns = [
            (r'Powered by Granicus', 'Granicus footer', 0.9),
            (r'OpenCities\s*=\s*OpenCities', 'OpenCities namespace', 0.5),
            (r'OpenCities\.Paths', 'OpenCities configuration', 0.4),
            (r'/files/templates/', 'Granicus file structure', 0.3),
            (r'/files/assets/', 'Granicus assets path', 0.3),
            (r'\.background-container', 'Granicus container classes', 0.2),
            (r'\.sc-size-', 'Granicus responsive classes', 0.2),
        ]

        for pattern, description, points in granicus_patterns:
            if re.search(pattern, html_content, re.IGNORECASE):
                indicators.append(description)
                confidence_points += points

        return {
            'confidence': min(confidence_points, 1.0),
            'indicators': indicators
        }


def detect_drupal_cities_batch(city_urls: Dict[str, str]) -> Dict[str, Dict]:
    """
    Batch detect Drupal cities to scale Berkeley's cost efficiency model

    Args:
        city_urls: Dict of city_name -> base_url

    Returns:
        Dict of city_name -> detection_results
    """
    detector = CMSPlatformDetector()
    results = {}

    for city_name, url in city_urls.items():
        print(f"🔍 Detecting CMS platform for {city_name}...")
        detection = detector.detect_cms_platform(url)
        results[city_name] = detection

        # Print results immediately for progress tracking
        if detection['platform'] == 'drupal':
            print(f"🎯 DRUPAL FOUND: {city_name} - Confidence: {detection['confidence']:.2f} - Cost efficiency potential: HIGH")
        else:
            print(f"📋 {city_name}: {detection['platform'].upper()} (confidence: {detection['confidence']:.2f})")

    return results


def generate_scaling_recommendations(detection_results: Dict[str, Dict]) -> Dict[str, any]:
    """Generate recommendations for scaling Berkeley's efficiency model"""
    drupal_cities = []
    other_platforms = {}

    for city_name, result in detection_results.items():
        if result['platform'] == 'drupal' and result['confidence'] > 0.7:
            drupal_cities.append({
                'city': city_name,
                'confidence': result['confidence'],
                'cost_efficiency_prediction': 'high',
                'implementation_priority': 1
            })
        else:
            platform = result['platform']
            if platform not in other_platforms:
                other_platforms[platform] = []
            other_platforms[platform].append(city_name)

    return {
        'drupal_scaling_opportunities': drupal_cities,
        'other_platforms': other_platforms,
        'recommended_next_steps': {
            'immediate': f"Implement berkeley_cms extraction for {len(drupal_cities)} Drupal cities",
            'cost_savings_potential': f"${len(drupal_cities) * 0.15:.2f}/month if scaled to Berkeley efficiency",
            'efficiency_multiplier': f"{len(drupal_cities)}x Berkeley model scaling"
        }
    }


if __name__ == "__main__":
    # Test Bay Area cities for Drupal pattern matching
    bay_area_cities = {
        'hayward': 'https://www.hayward-ca.gov/',
        'richmond': 'https://www.ci.richmond.ca.us/',
        'albany': 'https://www.albanyca.gov/',
        'emeryville': 'https://www.emeryville.org/',
        'el_cerrito': 'http://www.elcerrito.gov/',
        'dublin': 'https://www.dublin.ca.gov/',
        'berkeley': 'https://berkeleyca.gov/',
        'milpitas': 'https://www.ci.milpitas.ca.gov/',
        'union_city': 'https://www.unioncity.org/',
        'newark': 'https://www.newark.org/'
    }

    print("🏛️ MUNICIPAL CMS DETECTION - Scaling Berkeley's $0.003/opportunity efficiency\n")

    # Run batch detection
    results = detect_drupal_cities_batch(bay_area_cities)

    # Generate scaling recommendations
    recommendations = generate_scaling_recommendations(results)

    print("\n" + "="*60)
    print("📊 SCALING RECOMMENDATIONS")
    print("="*60)

    print(f"\n🎯 Drupal Cities (Berkeley Model Scaling):")
    for city in recommendations['drupal_scaling_opportunities']:
        print(f"  • {city['city'].title()}: {city['confidence']:.2f} confidence, Priority {city['implementation_priority']}")

    print(f"\n📋 Other Platforms:")
    for platform, cities in recommendations['other_platforms'].items():
        print(f"  • {platform.title()}: {', '.join(cities)}")

    print(f"\n⚡ Next Steps:")
    for step, description in recommendations['recommended_next_steps'].items():
        print(f"  • {step.title()}: {description}")