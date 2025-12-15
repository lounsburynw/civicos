"""
Operational Issue → Agenda Item Matcher

Session 90: AI-powered matching between SeeClickFix operational complaints
and municipal policy agenda items.

Examples of successful matches:
- "Pothole on Main St" → "Street Repair Budget Discussion"
- "Stormwater drainage" → "Climate Adaptation Plan"
- "Illegal dumping" → "Waste Management Policy Update"
- "Speeding on Vendola Dr" → "Traffic Calming Measures"

Strategy:
1. Keyword-based pre-filtering (fast)
2. LLM semantic matching (accurate)
3. Confidence scoring (0-100)
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json


class OperationalAgendaMatcher:
    """
    Match operational complaints to policy agenda items.

    Uses hybrid approach:
    1. Keyword matching for speed
    2. LLM matching for accuracy
    """

    # Keyword mappings for common operational→policy connections
    CATEGORY_KEYWORDS = {
        'pothole': ['street', 'road', 'pavement', 'repair', 'maintenance', 'infrastructure', 'transportation'],
        'stormwater': ['drainage', 'flood', 'water', 'climate', 'storm', 'runoff', 'infrastructure'],
        'dumping': ['waste', 'trash', 'garbage', 'sanitation', 'disposal', 'recycling', 'illegal'],
        'traffic': ['speed', 'calming', 'safety', 'transportation', 'pedestrian', 'bicycle', 'crosswalk'],
        'sign': ['signage', 'marking', 'street', 'traffic', 'safety', 'visibility'],
        'tree': ['park', 'landscape', 'maintenance', 'urban', 'forestry', 'green', 'environment'],
        'sidewalk': ['pedestrian', 'accessibility', 'walkability', 'infrastructure', 'ada', 'path'],
        'park': ['recreation', 'playground', 'maintenance', 'open space', 'community'],
        'graffiti': ['vandalism', 'blight', 'cleanup', 'beautification', 'maintenance'],
        'lighting': ['street light', 'safety', 'visibility', 'infrastructure', 'crime prevention']
    }

    def __init__(self, use_llm: bool = True):
        """
        Initialize matcher.

        Args:
            use_llm: Enable LLM-based semantic matching (more accurate but slower)
        """
        self.use_llm = use_llm

        # Try to load LLM provider if available
        if use_llm:
            try:
                from .llm_provider import get_provider_for_task
                self.llm_provider = get_provider_for_task
                self.llm_available = True
            except ImportError:
                self.llm_available = False
                print("[matcher] WARNING: LLM provider not available, using keyword matching only")

    def match_issue_to_agendas(
        self,
        operational_issue: Dict[str, Any],
        agenda_items: List[Dict[str, Any]],
        min_confidence: float = 20.0
    ) -> List[Dict[str, Any]]:
        """
        Match a single operational issue to multiple agenda items.

        Args:
            operational_issue: Normalized SeeClickFix issue
            agenda_items: List of agenda items from events
            min_confidence: Minimum confidence score (0-100) to return

        Returns:
            List of matches sorted by confidence (descending):
            [
                {
                    "agenda_item": {...},
                    "confidence": 75,
                    "reasoning": "Both relate to street maintenance infrastructure",
                    "connection_type": "direct"  # or "thematic"
                }
            ]
        """
        matches = []

        for agenda_item in agenda_items:
            match_result = self._match_single_pair(operational_issue, agenda_item)

            if match_result and match_result['confidence'] >= min_confidence:
                matches.append(match_result)

        # Sort by confidence descending
        matches.sort(key=lambda x: x['confidence'], reverse=True)

        return matches

    def _match_single_pair(
        self,
        operational_issue: Dict[str, Any],
        agenda_item: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Match a single operational issue to a single agenda item.

        Returns:
            Match result or None if no match
        """
        # Extract relevant text from operational issue
        issue_text = self._extract_issue_text(operational_issue)
        issue_category = operational_issue.get('category', '').lower()

        # Extract relevant text from agenda item
        agenda_text = self._extract_agenda_text(agenda_item)
        agenda_type = agenda_item.get('project_type', '').lower()

        # Step 1: Keyword-based filtering
        keyword_confidence = self._keyword_match_confidence(
            issue_text, issue_category, agenda_text, agenda_type
        )

        # If keyword match is very weak, skip LLM (optimization)
        if keyword_confidence < 10:
            return None

        # Step 2: LLM semantic matching (if available and enabled)
        if self.use_llm and self.llm_available:
            llm_result = self._llm_semantic_match(operational_issue, agenda_item, keyword_confidence)
            if llm_result:
                return llm_result

        # Fallback: Use keyword confidence only
        if keyword_confidence >= 20:
            return {
                'agenda_item': agenda_item,
                'confidence': keyword_confidence,
                'reasoning': 'Keyword-based match (related infrastructure/policy domain)',
                'connection_type': 'thematic'
            }

        return None

    def _extract_issue_text(self, issue: Dict[str, Any]) -> str:
        """Extract searchable text from operational issue"""
        parts = [
            issue.get('title', ''),
            issue.get('description', ''),
            issue.get('category', '')
        ]
        return ' '.join(filter(None, parts)).lower()

    def _extract_agenda_text(self, agenda_item: Dict[str, Any]) -> str:
        """Extract searchable text from agenda item"""
        parts = [
            agenda_item.get('title', ''),
            agenda_item.get('description', ''),
            agenda_item.get('project_type', '')
        ]
        return ' '.join(filter(None, parts)).lower()

    def _keyword_match_confidence(
        self,
        issue_text: str,
        issue_category: str,
        agenda_text: str,
        agenda_type: str
    ) -> float:
        """
        Calculate keyword-based match confidence (0-100).

        Strategy:
        1. Identify issue category (pothole, stormwater, etc.)
        2. Check if agenda item contains related keywords
        3. Boost score for direct keyword matches
        """
        confidence = 0.0

        # Identify which category bucket this issue falls into
        matched_category = None
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            if category in issue_category or category in issue_text:
                matched_category = category
                break

        if not matched_category:
            return 0.0

        # Check how many related keywords appear in agenda item
        related_keywords = self.CATEGORY_KEYWORDS[matched_category]
        keyword_hits = sum(1 for keyword in related_keywords if keyword in agenda_text)

        if keyword_hits == 0:
            return 0.0

        # Calculate confidence based on keyword density
        # Base: 20 points per keyword hit (max 3 keywords)
        confidence = min(keyword_hits * 20, 60)

        # Bonus: Direct category match in agenda title
        if matched_category in agenda_text:
            confidence += 20

        # Bonus: Transportation/Infrastructure agenda items often relate to operational issues
        if agenda_type in ['transportation', 'infrastructure', 'housing', 'environment']:
            confidence += 10

        return min(confidence, 100)

    def _llm_semantic_match(
        self,
        operational_issue: Dict[str, Any],
        agenda_item: Dict[str, Any],
        keyword_confidence: float
    ) -> Optional[Dict[str, Any]]:
        """
        Use LLM to determine semantic match between issue and agenda item.

        This is more accurate than keyword matching but slower.
        """
        if not self.llm_available:
            return None

        try:
            # Build prompt for LLM
            prompt = f"""You are matching operational complaints to municipal policy agenda items.

OPERATIONAL COMPLAINT:
Title: {operational_issue.get('title', 'N/A')}
Category: {operational_issue.get('category', 'N/A')}
Description: {operational_issue.get('description', 'N/A')[:200]}

POLICY AGENDA ITEM:
Title: {agenda_item.get('title', 'N/A')}
Type: {agenda_item.get('project_type', 'N/A')}
Description: {agenda_item.get('description', 'N/A')[:200]}

Questions:
1. Are these related? (yes/no)
2. If yes, what's the connection? (1 sentence)
3. Confidence score (0-100): How confident are you they're related?
4. Connection type: "direct" (same specific issue) or "thematic" (related policy domain)

Format your response as JSON:
{{"related": true/false, "reasoning": "...", "confidence": 0-100, "connection_type": "direct/thematic"}}"""

            # Get LLM provider for this task (using gpt-4o-mini for cost efficiency)
            provider = self.llm_provider('matching')  # Light semantic task

            # Call LLM
            response = provider.generate(
                prompt=prompt,
                max_tokens=200,
                temperature=0.0  # Deterministic
            )

            # Parse response
            import json
            result = json.loads(response)

            if result.get('related'):
                return {
                    'agenda_item': agenda_item,
                    'confidence': min(result.get('confidence', keyword_confidence), 100),
                    'reasoning': result.get('reasoning', 'LLM detected semantic relationship'),
                    'connection_type': result.get('connection_type', 'thematic')
                }

        except Exception as e:
            print(f"[matcher] LLM matching failed: {e}")
            # Fallback to keyword confidence
            return None

        return None

    def match_issues_batch(
        self,
        operational_issues: List[Dict[str, Any]],
        agenda_items: List[Dict[str, Any]],
        min_confidence: float = 20.0
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Match multiple operational issues to agenda items in batch.

        Args:
            operational_issues: List of SeeClickFix issues
            agenda_items: List of agenda items
            min_confidence: Minimum confidence threshold

        Returns:
            {
                "scf-123": [{agenda_item, confidence, reasoning}, ...],
                "scf-456": [{agenda_item, confidence, reasoning}, ...],
                ...
            }
        """
        results = {}

        for issue in operational_issues:
            issue_id = issue.get('id')
            matches = self.match_issue_to_agendas(issue, agenda_items, min_confidence)
            if matches:
                results[issue_id] = matches

        return results

    def get_match_statistics(
        self,
        operational_issues: List[Dict[str, Any]],
        agenda_items: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate matching statistics for analysis.

        Returns:
            {
                "total_issues": 20,
                "total_agenda_items": 15,
                "matched_issues": 5,
                "match_rate": 0.25,
                "avg_confidence": 45.2,
                "by_category": {...}
            }
        """
        matches = self.match_issues_batch(operational_issues, agenda_items, min_confidence=20)

        matched_count = len(matches)
        total_issues = len(operational_issues)

        # Calculate average confidence
        all_confidences = []
        for issue_matches in matches.values():
            if issue_matches:
                all_confidences.append(issue_matches[0]['confidence'])  # Use top match

        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0

        # Group by category
        by_category = {}
        for issue in operational_issues:
            category = issue.get('category', 'Unknown')
            if category not in by_category:
                by_category[category] = {'total': 0, 'matched': 0}
            by_category[category]['total'] += 1
            if issue.get('id') in matches:
                by_category[category]['matched'] += 1

        return {
            'total_issues': total_issues,
            'total_agenda_items': len(agenda_items),
            'matched_issues': matched_count,
            'match_rate': matched_count / total_issues if total_issues > 0 else 0,
            'avg_confidence': round(avg_confidence, 1),
            'by_category': by_category
        }


# Example usage
if __name__ == "__main__":
    print("🔗 Testing Operational→Agenda Matcher")
    print("=" * 50)

    matcher = OperationalAgendaMatcher(use_llm=False)  # Keyword-only for quick test

    # Sample operational issue
    operational_issue = {
        'id': 'scf-test-1',
        'title': 'Pothole on Main Street',
        'description': 'Large pothole near intersection needs immediate repair',
        'category': 'Pothole/Road Condition',
        'location': {'address': '123 Main St'}
    }

    # Sample agenda items
    agenda_items = [
        {
            'id': 'agenda-1',
            'title': 'FY2026 Street Repair Budget Discussion',
            'description': 'Annual budget allocation for road maintenance and pothole repairs',
            'project_type': 'transportation'
        },
        {
            'id': 'agenda-2',
            'title': 'Housing Development Proposal - 456 Oak St',
            'description': 'New 50-unit affordable housing development',
            'project_type': 'housing'
        },
        {
            'id': 'agenda-3',
            'title': 'Climate Adaptation Infrastructure Plan',
            'description': 'Stormwater management and flood prevention infrastructure',
            'project_type': 'environment'
        }
    ]

    # Test matching
    matches = matcher.match_issue_to_agendas(operational_issue, agenda_items, min_confidence=15)

    print(f"\nOperational Issue: {operational_issue['title']}")
    print(f"Category: {operational_issue['category']}")
    print(f"\nFound {len(matches)} matches:\n")

    for i, match in enumerate(matches, 1):
        print(f"{i}. {match['agenda_item']['title']}")
        print(f"   Confidence: {match['confidence']}")
        print(f"   Connection: {match['connection_type']}")
        print(f"   Reasoning: {match['reasoning']}\n")

    # Statistics
    print("\nStatistics:")
    stats = matcher.get_match_statistics([operational_issue], agenda_items)
    print(f"Match Rate: {stats['match_rate']:.1%}")
    print(f"Avg Confidence: {stats['avg_confidence']}")

    print("\n" + "=" * 50)
    print("✅ Matcher test complete!")
