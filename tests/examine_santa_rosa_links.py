#!/usr/bin/env python3
"""
Examine Santa Rosa meeting links to understand the real structure
"""

import os
import sys
import requests
import re
from bs4 import BeautifulSoup

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

def examine_meeting_links():
    """Examine the actual meeting links from Santa Rosa"""
    print("🔍 Examining Santa Rosa meeting links...")

    santa_rosa_url = "https://santa-rosa.legistar.com/Calendar.aspx"

    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (CivicEngagement/1.0)'})

        response = session.get(santa_rosa_url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')

        # Find links with "meeting" text
        meeting_links = soup.find_all('a', string=re.compile(r'meeting', re.I))

        print(f"📝 Found {len(meeting_links)} links with 'meeting' text")

        # Examine first 10 meeting links
        print("\n🔗 Sample meeting links:")
        for i, link in enumerate(meeting_links[:10]):
            href = link.get('href', 'No href')
            text = link.get_text().strip()
            print(f"{i+1:2d}. {text[:50]:<50} -> {href}")

        # Look for patterns in hrefs
        print("\n📊 Analyzing link patterns...")

        href_patterns = {}
        for link in meeting_links:
            href = link.get('href', '')
            if href:
                # Extract base pattern
                if 'MeetingDetail' in href:
                    href_patterns['MeetingDetail'] = href_patterns.get('MeetingDetail', 0) + 1
                elif 'EventID' in href:
                    href_patterns['EventID'] = href_patterns.get('EventID', 0) + 1
                elif 'Calendar' in href:
                    href_patterns['Calendar'] = href_patterns.get('Calendar', 0) + 1
                elif href.startswith('javascript:'):
                    href_patterns['JavaScript'] = href_patterns.get('JavaScript', 0) + 1
                else:
                    pattern = href.split('?')[0] if '?' in href else href
                    href_patterns[pattern] = href_patterns.get(pattern, 0) + 1

        for pattern, count in href_patterns.items():
            print(f"  {pattern}: {count} links")

        # Look for any links that might contain actual meeting details
        print("\n🎯 Looking for promising meeting links...")

        promising_links = []
        for link in meeting_links:
            href = link.get('href', '')
            text = link.get_text().strip()

            # Skip navigation links
            if any(skip in text.lower() for skip in ['search', 'calendar', 'legislation', 'home']):
                continue

            # Look for date patterns or meeting names
            if re.search(r'\d{4}|\d{1,2}/\d{1,2}|commission|council|board', text.lower()):
                promising_links.append((text, href))

        print(f"Found {len(promising_links)} promising meeting links:")
        for i, (text, href) in enumerate(promising_links[:15]):
            print(f"{i+1:2d}. {text[:60]:<60} -> {href}")

        # Look at the overall page structure for calendar data
        print("\n📅 Looking for calendar/meeting data structures...")

        # Look for any data that might be embedded or in specific containers
        calendar_divs = soup.find_all('div', id=re.compile(r'calendar|meeting', re.I))
        for div in calendar_divs:
            print(f"Calendar div: {div.get('id')} - {len(div.get_text())} chars")

        # Look for any script tags that might load meeting data
        scripts = soup.find_all('script')
        for script in scripts:
            script_content = script.get_text()
            if any(keyword in script_content.lower() for keyword in ['meeting', 'calendar', 'event']):
                print(f"\n📜 Script with meeting-related content found ({len(script_content)} chars)")
                # Show a sample of the script
                lines = script_content.split('\n')
                relevant_lines = [line.strip() for line in lines if
                                any(keyword in line.lower() for keyword in ['meeting', 'calendar', 'event'])]
                for line in relevant_lines[:5]:
                    if len(line) > 20:
                        print(f"  {line[:100]}")

        return True

    except Exception as e:
        print(f"❌ Error examining Santa Rosa links: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    examine_meeting_links()

if __name__ == "__main__":
    main()