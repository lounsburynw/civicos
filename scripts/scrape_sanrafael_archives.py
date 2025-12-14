#!/usr/bin/env python3
"""
Scrape San Rafael meeting archives for 12-month retrospective analysis

Extracts meeting metadata from San Rafael's archive pages:
- City Council: https://www.cityofsanrafael.org/city-council-meetings/
- Planning Commission: https://www.cityofsanrafael.org/planning-commission-meetings/
- Tax Oversight: https://www.cityofsanrafael.org/voter-approved-tax-oversight-committee-meetings/
- Fire Commission: https://www.cityofsanrafael.org/fire-commission-meetings/
- Zoning Administrator: https://www.cityofsanrafael.org/zoning-administrator-hearings/

Meeting URL pattern:
https://www.cityofsanrafael.org/meetings/{meeting-slug}/#tab-agenda
https://www.cityofsanrafael.org/meetings/{meeting-slug}/#tab-agenda-packet
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime
import json
import re
import time


class SanRafaelArchiveScraper:
    """Scrape San Rafael meeting archives for retrospective analysis"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Civic-Engagement-Platform/1.0 (Foundation-funded civic transparency tool)'
        })

    def scrape_archive_page(self, archive_url: str, meeting_type: str) -> List[Dict]:
        """
        Scrape a meeting archive page to find all meetings

        Args:
            archive_url: Archive page URL (e.g., https://www.cityofsanrafael.org/city-council-meetings/)
            meeting_type: Type identifier (city_council, planning_commission, etc.)

        Returns:
            List of meeting dicts with metadata
        """
        print(f"\n🔍 Scraping {meeting_type} archive: {archive_url}")

        try:
            response = self.session.get(archive_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find all meeting links - San Rafael uses various patterns
            meetings = []

            # Pattern 1: Links with "meetings/" in href
            meeting_links = soup.find_all('a', href=re.compile(r'/meetings/.*'))

            for link in meeting_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)

                # Skip non-meeting links
                if not href or '/meetings/' not in href:
                    continue

                # Build full URL
                if href.startswith('http'):
                    meeting_url = href
                else:
                    meeting_url = f"https://www.cityofsanrafael.org{href}"

                # Extract meeting slug from URL
                # e.g., /meetings/city-council-october-6-2025/ -> city-council-october-6-2025
                match = re.search(r'/meetings/([^/]+)/?', meeting_url)
                if not match:
                    continue

                meeting_slug = match.group(1)

                # Parse date from slug or text
                date_str = self._extract_date_from_slug(meeting_slug, text)

                if date_str:
                    meeting = {
                        'title': text or meeting_slug.replace('-', ' ').title(),
                        'meeting_slug': meeting_slug,
                        'meeting_url': meeting_url.split('#')[0],  # Remove fragment
                        'agenda_url': f"{meeting_url.split('#')[0]}#tab-agenda",
                        'agenda_packet_url': f"{meeting_url.split('#')[0]}#tab-agenda-packet",
                        'date_parsed': date_str,
                        'meeting_type': meeting_type,
                        'source_archive': archive_url
                    }

                    # Avoid duplicates
                    if not any(m['meeting_slug'] == meeting_slug for m in meetings):
                        meetings.append(meeting)

            print(f"   ✅ Found {len(meetings)} meetings")
            return meetings

        except Exception as e:
            print(f"   ❌ Failed to scrape: {type(e).__name__}: {e}")
            return []

    def _extract_date_from_slug(self, slug: str, title: str = '') -> Optional[str]:
        """
        Extract ISO date from meeting slug or title

        Examples:
        - city-council-october-6-2025 -> 2025-10-06
        - planning-commission-november-4-2025-special-meeting -> 2025-11-04
        """
        # Try slug first
        text = slug + ' ' + title

        # Pattern: month-day-year or month day year
        months = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }

        for month_name, month_num in months.items():
            # Pattern: october-6-2025 or october 6 2025
            pattern = rf'{month_name}[-\s]+(\d{{1,2}})[-\s]+(\d{{4}})'
            match = re.search(pattern, text.lower())
            if match:
                day = int(match.group(1))
                year = int(match.group(2))
                try:
                    date_obj = datetime(year, month_num, day)
                    return date_obj.strftime('%Y-%m-%d')
                except ValueError:
                    pass

        return None

    def filter_by_date_range(
        self,
        meetings: List[Dict],
        start_date: str,
        end_date: str
    ) -> List[Dict]:
        """Filter meetings by date range"""
        start_dt = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)

        filtered = []
        for meeting in meetings:
            if meeting.get('date_parsed'):
                try:
                    meeting_dt = datetime.fromisoformat(meeting['date_parsed'])
                    if start_dt <= meeting_dt <= end_dt:
                        filtered.append(meeting)
                except ValueError:
                    pass

        return filtered

    def scrape_all_archives(
        self,
        start_date: str = "2024-11-01",
        end_date: str = "2025-11-30"
    ) -> Dict[str, List[Dict]]:
        """
        Scrape all San Rafael meeting archives

        Returns:
            Dict with meeting type as keys and lists of meetings
        """
        archives = {
            'city_council': 'https://www.cityofsanrafael.org/city-council-meetings/',
            'planning_commission': 'https://www.cityofsanrafael.org/planning-commission-meetings/',
            'tax_oversight': 'https://www.cityofsanrafael.org/voter-approved-tax-oversight-committee-meetings/',
            'fire_commission': 'https://www.cityofsanrafael.org/fire-commission-meetings/',
            'zoning_administrator': 'https://www.cityofsanrafael.org/zoning-administrator-hearings/',
            'council_subcommittees': 'https://www.cityofsanrafael.org/council-subcommittee-meetings/',
        }

        all_meetings = {}

        for meeting_type, archive_url in archives.items():
            meetings = self.scrape_archive_page(archive_url, meeting_type)

            # Filter by date range
            filtered = self.filter_by_date_range(meetings, start_date, end_date)

            all_meetings[meeting_type] = filtered

            print(f"   📅 {len(filtered)} meetings in date range ({start_date} to {end_date})")

            # Be nice to server
            time.sleep(1)

        return all_meetings

    def download_meeting_pdfs(self, meeting_url: str) -> Dict[str, Optional[str]]:
        """
        Visit meeting page and extract PDF links from multiple tabs

        Returns dict with:
        - agenda_packet_url: Full agenda packet PDF
        - minutes_url: Meeting minutes PDF
        - individual_items: List of individual agenda item PDFs (optional)
        """
        result = {
            'agenda_packet_url': None,
            'minutes_url': None,
            'individual_items': []
        }

        try:
            # Fetch the meeting page once
            response = self.session.get(meeting_url, timeout=20)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract all PDF URLs from page
            all_pdf_urls = self._extract_all_pdf_urls(soup)

            # Prioritize agenda packet (highest priority first)
            agenda_packet_patterns = [
                r'agenda-packet.*\.pdf',
                r'full.*packet.*\.pdf',
                r'complete.*agenda.*\.pdf',
                r'packet.*\d{4}-\d{2}-\d{2}.*\.pdf'
            ]

            for pattern in agenda_packet_patterns:
                for url in all_pdf_urls:
                    if re.search(pattern, url, re.I):
                        result['agenda_packet_url'] = url
                        break
                if result['agenda_packet_url']:
                    break

            # If no agenda packet found, try finding PDFs in #tab-agenda-packet section
            if not result['agenda_packet_url']:
                agenda_packet_tab = soup.find('div', {'id': 'tab-agenda-packet'})
                if agenda_packet_tab:
                    tab_pdfs = self._extract_pdf_urls_from_element(agenda_packet_tab)
                    if tab_pdfs:
                        result['agenda_packet_url'] = tab_pdfs[0]  # First PDF in agenda packet tab

            # Extract minutes URL
            # PRIORITY 1: Check #tab-minutes section first (most reliable)
            minutes_tab = soup.find('div', {'id': 'tab-minutes'})
            if minutes_tab:
                tab_pdfs = self._extract_pdf_urls_from_element(minutes_tab)
                if tab_pdfs:
                    result['minutes_url'] = tab_pdfs[0]  # First PDF in minutes tab

            # PRIORITY 2: If not found in tab, use pattern matching as fallback
            if not result['minutes_url']:
                minutes_patterns = [
                    r'cc-minutes.*\d{4}-\d{2}-\d{2}.*\.pdf',  # cc-minutes-2025-10-06.pdf
                    r'minutes-\d{4}-\d{2}-\d{2}.*\.pdf',  # minutes-2025-10-06.pdf
                    r'\d{8}-cc-minutes.*\.pdf'  # db640875-cc-minutes-2025-10-06.pdf
                ]

                for pattern in minutes_patterns:
                    for url in all_pdf_urls:
                        if re.search(pattern, url, re.I):
                            result['minutes_url'] = url
                            break
                    if result['minutes_url']:
                        break

            return result

        except Exception as e:
            print(f"      ⚠️  Failed to extract PDF URLs: {type(e).__name__}")
            return result

    def _extract_all_pdf_urls(self, soup: BeautifulSoup) -> List[str]:
        """Extract all PDF URLs from a BeautifulSoup object"""
        pdf_urls = []

        # Strategy 1: Links with .pdf
        for link in soup.find_all('a', href=re.compile(r'\.pdf', re.I)):
            href = link.get('href')
            if href:
                pdf_urls.append(self._make_absolute_url(href))

        # Strategy 2: Embeds
        for embed in soup.find_all('embed', src=re.compile(r'\.pdf', re.I)):
            src = embed.get('src')
            if src:
                pdf_urls.append(self._make_absolute_url(src))

        # Strategy 3: iframes
        for iframe in soup.find_all('iframe', src=re.compile(r'\.pdf', re.I)):
            src = iframe.get('src')
            if src:
                pdf_urls.append(self._make_absolute_url(src))

        # Strategy 4: objects
        for obj in soup.find_all('object', attrs={'data': re.compile(r'\.pdf', re.I)}):
            data = obj.get('data')
            if data:
                pdf_urls.append(self._make_absolute_url(data))

        return pdf_urls

    def _extract_pdf_urls_from_element(self, element) -> List[str]:
        """Extract PDF URLs from a specific HTML element"""
        pdf_urls = []

        # Links
        for link in element.find_all('a', href=re.compile(r'\.pdf', re.I)):
            href = link.get('href')
            if href:
                pdf_urls.append(self._make_absolute_url(href))

        # Embeds
        for embed in element.find_all('embed', src=re.compile(r'\.pdf', re.I)):
            src = embed.get('src')
            if src:
                pdf_urls.append(self._make_absolute_url(src))

        # iframes
        for iframe in element.find_all('iframe', src=re.compile(r'\.pdf', re.I)):
            src = iframe.get('src')
            if src:
                pdf_urls.append(self._make_absolute_url(src))

        # objects
        for obj in element.find_all('object', attrs={'data': re.compile(r'\.pdf', re.I)}):
            data = obj.get('data')
            if data:
                pdf_urls.append(self._make_absolute_url(data))

        return pdf_urls

    def _make_absolute_url(self, url: str) -> str:
        """Convert relative URL to absolute"""
        if url.startswith('http'):
            return url
        return f"https://www.cityofsanrafael.org{url}"


def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description='Scrape San Rafael meeting archives')
    parser.add_argument('--start-date', default='2024-11-01', help='Start date (ISO format)')
    parser.add_argument('--end-date', default='2025-11-30', help='End date (ISO format)')
    parser.add_argument('--output', default='data/pilot/san_rafael_meetings_12month.json',
                        help='Output JSON file')
    parser.add_argument('--fetch-pdf-urls', action='store_true',
                        help='Fetch direct PDF URLs (slower, visits each meeting page)')

    args = parser.parse_args()

    print("🔍 SAN RAFAEL ARCHIVE SCRAPER")
    print("=" * 60)
    print(f"Date range: {args.start_date} to {args.end_date}")
    print(f"Output: {args.output}\n")

    scraper = SanRafaelArchiveScraper()

    # Scrape all archives
    all_meetings = scraper.scrape_all_archives(args.start_date, args.end_date)

    # Count totals
    total_meetings = sum(len(meetings) for meetings in all_meetings.values())

    print("\n" + "=" * 60)
    print(f"📊 SCRAPING COMPLETE")
    print(f"   Total meetings found: {total_meetings}")
    print(f"\n   Breakdown by type:")
    for meeting_type, meetings in all_meetings.items():
        print(f"     - {meeting_type}: {len(meetings)}")

    # Optionally fetch PDF URLs (slower)
    if args.fetch_pdf_urls:
        print(f"\n🔍 Fetching direct PDF URLs for {total_meetings} meetings...")
        print("   (This may take a few minutes)")

        count = 0
        pdf_stats = {
            'agenda_packets': 0,
            'minutes': 0,
            'both': 0,
            'none': 0
        }

        for meeting_type, meetings in all_meetings.items():
            for meeting in meetings:
                count += 1
                print(f"\n   [{count}/{total_meetings}] {meeting['title']}")
                pdf_urls = scraper.download_meeting_pdfs(meeting['meeting_url'])

                # Track what we found
                has_packet = pdf_urls['agenda_packet_url'] is not None
                has_minutes = pdf_urls['minutes_url'] is not None

                if has_packet and has_minutes:
                    pdf_stats['both'] += 1
                elif has_packet:
                    pdf_stats['agenda_packets'] += 1
                elif has_minutes:
                    pdf_stats['minutes'] += 1
                else:
                    pdf_stats['none'] += 1

                # Store URLs in meeting dict
                if has_packet:
                    meeting['agenda_packet_pdf_url'] = pdf_urls['agenda_packet_url']
                    print(f"      ✅ Agenda Packet: {pdf_urls['agenda_packet_url'].split('/')[-1]}")
                else:
                    print(f"      ⚠️  No agenda packet found")

                if has_minutes:
                    meeting['minutes_pdf_url'] = pdf_urls['minutes_url']
                    print(f"      ✅ Minutes: {pdf_urls['minutes_url'].split('/')[-1]}")

                time.sleep(1)  # Be nice to server

        # Print PDF extraction statistics
        print(f"\n📊 PDF EXTRACTION STATS:")
        print(f"   Both (packet + minutes): {pdf_stats['both']}")
        print(f"   Agenda packet only: {pdf_stats['agenda_packets']}")
        print(f"   Minutes only: {pdf_stats['minutes']}")
        print(f"   None found: {pdf_stats['none']}")

    # Save results
    output_data = {
        'jurisdiction_id': 'city-san-rafael',
        'jurisdiction_name': 'San Rafael',
        'date_range': {
            'start': args.start_date,
            'end': args.end_date
        },
        'extraction_timestamp': datetime.now().isoformat(),
        'total_meetings': total_meetings,
        'meetings_by_type': {
            meeting_type: len(meetings)
            for meeting_type, meetings in all_meetings.items()
        },
        'meetings': all_meetings
    }

    import os
    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✅ Results saved to {args.output}")

    # Summary statistics
    print(f"\n📈 NEXT STEPS:")
    print(f"   1. Review extracted meetings in {args.output}")
    print(f"   2. Run retrospective analysis:")
    print(f"      python scripts/analyze_sanrafael_retrospective.py {args.output}")
    print(f"   3. Match SeeClickFix complaints to high-stakes decisions")


if __name__ == "__main__":
    main()
