#!/usr/bin/env python3
"""
Automated Legislative Discovery - Uses LegiScan API + LLM to discover relevant bills.

Run monthly to keep legislative context current.

Cost: ~$2/month (20 bills × $0.02/bill × 5 topics)
Time: <15 min/month manual review

Usage:
    python src/legislative_discovery.py --topic housing --review
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

from ..clients.legiscan_client import LegiScanClient, TOPIC_KEYWORDS

# OpenAI for LLM relevance filter
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("WARNING: OpenAI not available. Install with: pip install openai")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LegislativeDiscovery:
    """
    Automated discovery of locally-actionable legislation.

    Process:
    1. Query LegiScan for recent bills matching topic keywords
    2. Filter with LLM: "Does this require local implementation?"
    3. Generate local leverage point summary
    4. Output for manual review
    """

    def __init__(self, legiscan_api_key: Optional[str] = None, openai_api_key: Optional[str] = None):
        self.legiscan = LegiScanClient(api_key=legiscan_api_key)

        if openai_api_key:
            openai.api_key = openai_api_key
        elif os.getenv('OPENAI_API_KEY'):
            openai.api_key = os.getenv('OPENAI_API_KEY')

    def discover_topic(
        self,
        topic: str,
        state: str = "california",
        days_back: int = 90,
        limit: int = 20
    ) -> List[Dict]:
        """
        Discover new legislation for a topic.

        Args:
            topic: One of: housing, transportation, environment, budget, education
            state: State to search (default: california)
            days_back: How far back to search (default: 90 days)
            limit: Maximum bills to analyze with LLM

        Returns:
            List of relevant bills with local leverage points
        """
        if topic not in TOPIC_KEYWORDS:
            raise ValueError(f"Unknown topic: {topic}. Must be one of {list(TOPIC_KEYWORDS.keys())}")

        logger.info(f"Discovering {topic} legislation for {state} (last {days_back} days)")

        # Step 1: Query LegiScan
        keywords = TOPIC_KEYWORDS[topic]
        recent_bills = self.legiscan.get_recent_bills(
            state=state,
            topic_keywords=keywords[:3],  # Limit to top 3 keywords to conserve queries
            days_back=days_back
        )

        if not recent_bills:
            logger.info(f"No recent bills found for topic: {topic}")
            return []

        logger.info(f"Found {len(recent_bills)} recent bills, filtering for local relevance...")

        # Step 2: LLM relevance filter
        relevant_bills = self._filter_relevant_bills(recent_bills[:limit], topic)

        logger.info(f"Identified {len(relevant_bills)} locally-relevant bills")

        return relevant_bills

    def _filter_relevant_bills(self, bills: List[Dict], topic: str) -> List[Dict]:
        """
        Use LLM to filter bills for local relevance.

        Criteria:
        - Requires local government implementation
        - Creates opportunities for residents to influence decisions
        - Has clear local control points
        """
        if not OPENAI_AVAILABLE:
            logger.warning("OpenAI not available, returning unfiltered bills")
            return bills

        # Batch process for efficiency
        prompt = f"""Analyze these California {topic} bills to identify which ones:
1. Require local government (city/county) implementation
2. Create opportunities for residents to influence local decisions
3. Have clear local control points (what city council decides)

For each RELEVANT bill, provide:
- bill_id: LegiScan bill ID
- bill_number: Bill number (e.g., "SB 9")
- title: Short title
- local_implementation_required: true/false
- leverage_point: One sentence explaining what residents can influence at city level
- deadline: Local implementation deadline (if specified, otherwise null)

Return ONLY relevant bills as JSON array. Skip bills that are purely state-level with no local control.

Bills to analyze:
{json.dumps([{
    'bill_id': b.get('bill_id'),
    'bill_number': b.get('bill_number'),
    'title': b.get('title', ''),
    'description': (b.get('description') or '')[:200],
    'last_action': b.get('last_action') or ''
} for b in bills], indent=2)}
"""

        try:
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "system",
                    "content": "You are an expert in California local government and civic engagement. Identify legislation that creates actionable opportunities for residents to influence local decisions."
                }, {
                    "role": "user",
                    "content": prompt
                }],
                response_format={"type": "json_object"},
                temperature=0.1
            )

            result_text = response.choices[0].message.content
            result = json.loads(result_text)

            # Handle both array and object with "bills" key
            relevant_bills = result if isinstance(result, list) else result.get('bills', result.get('relevant_bills', []))

            logger.info(f"LLM filtered {len(bills)} bills → {len(relevant_bills)} relevant")

            return relevant_bills

        except Exception as e:
            logger.error(f"LLM filtering failed: {e}")
            return []

    def update_legislative_context(
        self,
        topic: str,
        relevant_bills: List[Dict],
        state: str = "california",
        dry_run: bool = True
    ) -> Path:
        """
        Update legislative context file with new bills.

        Args:
            topic: Topic key
            relevant_bills: Bills filtered by LLM
            state: State code
            dry_run: If True, print changes without writing

        Returns:
            Path to updated file
        """
        context_file = Path(f"data/legislative_context/{state}_{topic}.json")

        # Load existing context if it exists
        if context_file.exists():
            with open(context_file, 'r') as f:
                context = json.load(f)
        else:
            context = {
                "jurisdiction": state,
                "topic": topic,
                "last_updated": datetime.now().isoformat(),
                "data_sources": [
                    "LegiScan API",
                    "LLM-assisted relevance filtering",
                    "Manual review"
                ],
                "state_legislation": {},
                "federal_programs": {}
            }

        # Add new bills (don't overwrite existing ones)
        new_count = 0
        for bill in relevant_bills:
            bill_key = self._normalize_bill_id(bill.get('bill_number', f"bill-{bill.get('bill_id')}"))

            if bill_key not in context['state_legislation']:
                context['state_legislation'][bill_key] = {
                    "bill": bill.get('title', bill.get('bill_number')),
                    "status": bill.get('status', 'Active'),
                    "enacted": bill.get('status_date'),
                    "local_implementation_required": bill.get('local_implementation_required', True),
                    "local_deadline": bill.get('deadline'),
                    "leverage_point": bill.get('leverage_point', 'Local implementation details TBD'),
                    "official_url": bill.get('url', ''),
                    "summary": bill.get('description', '')[:200],
                    "keywords": TOPIC_KEYWORDS.get(topic, [])[:5],
                    "_legiscan_id": bill.get('bill_id')
                }
                new_count += 1

        context['last_updated'] = datetime.now().isoformat()

        if dry_run:
            logger.info(f"DRY RUN: Would add {new_count} new bills to {context_file}")
            logger.info(f"Review:\n{json.dumps(context['state_legislation'], indent=2)}")
            return context_file

        # Write updated context
        context_file.parent.mkdir(parents=True, exist_ok=True)
        with open(context_file, 'w') as f:
            json.dump(context, f, indent=2)

        logger.info(f"Updated {context_file} with {new_count} new bills")

        return context_file

    def _normalize_bill_id(self, bill_number: str) -> str:
        """Convert bill number to normalized key (e.g., 'SB 9' → 'ca-sb-9')"""
        return 'ca-' + bill_number.lower().replace(' ', '-').replace('.', '-')


def main():
    """CLI for automated legislative discovery"""
    import argparse

    parser = argparse.ArgumentParser(description="Discover locally-relevant legislation")
    parser.add_argument(
        '--topic',
        required=True,
        choices=['housing', 'transportation', 'environment', 'budget', 'education', 'all'],
        help='Topic to discover'
    )
    parser.add_argument(
        '--state',
        default='california',
        help='State to search (default: california)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=90,
        help='Days back to search (default: 90)'
    )
    parser.add_argument(
        '--review',
        action='store_true',
        help='Dry run mode - show results without updating files'
    )

    args = parser.parse_args()

    # Initialize discovery
    discovery = LegislativeDiscovery()

    # Handle "all" topics
    topics = list(TOPIC_KEYWORDS.keys()) if args.topic == 'all' else [args.topic]

    for topic in topics:
        print(f"\n{'='*60}")
        print(f"Discovering {topic.upper()} legislation")
        print(f"{'='*60}")

        # Discover relevant bills
        relevant_bills = discovery.discover_topic(
            topic=topic,
            state=args.state,
            days_back=args.days
        )

        if relevant_bills:
            print(f"\n✓ Found {len(relevant_bills)} relevant bills:\n")
            for bill in relevant_bills:
                print(f"  - {bill.get('bill_number')}: {bill.get('leverage_point', 'TBD')}")

            # Update context file
            discovery.update_legislative_context(
                topic=topic,
                relevant_bills=relevant_bills,
                state=args.state,
                dry_run=args.review
            )
        else:
            print(f"\n○ No relevant bills found for {topic}")

    # Show API usage
    stats = discovery.legiscan.get_query_stats()
    print(f"\n{'='*60}")
    print(f"LegiScan API Usage")
    print(f"{'='*60}")
    print(f"Queries this session: {stats['queries_this_session']}")
    print(f"Monthly limit: {stats['monthly_limit']}")
    print(f"Estimated remaining: {stats['estimated_remaining']}")


if __name__ == "__main__":
    main()
