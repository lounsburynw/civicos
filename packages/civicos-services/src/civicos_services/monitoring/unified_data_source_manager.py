"""
Unified Data Source Manager - Civic Conversational OS Resilience Layer
Phase 2A Implementation for Vendor Independence and Data Sovereignty

Key capabilities:
- Multi-source failover: CDP → Legistar API → civic-scraper → HTML parsing → archived data
- Vendor risk mitigation for Granicus/Legistar dependencies
- Source attribution and quality scoring
- Automatic data archival for sovereignty
- Foundation-ready civic infrastructure
"""

import json
import sqlite3
import time
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path

# Import our civic data clients with optional CDP support
try:
    from ..clients.cdp_client import CDPClient, create_cdp_client, KNOWN_CDP_JURISDICTIONS
    CDP_AVAILABLE = True
except ImportError:
    print("⚠️ CDP client not available - CDP features disabled")
    CDP_AVAILABLE = False
    CDPClient = None
    KNOWN_CDP_JURISDICTIONS = {}

from ..clients.legistar_client import LegistarClient, KNOWN_LEGISTAR_CLIENTS


@dataclass
class DataSourceConfig:
    """Configuration for a jurisdiction's data sources"""
    jurisdiction_id: str
    jurisdiction_name: str
    timezone: str

    # Available data sources (in priority order)
    cdp_available: bool = False
    legistar_available: bool = False
    civic_scraper_available: bool = False
    html_parsing_available: bool = False

    # Source-specific configurations
    legistar_client_name: Optional[str] = None
    cdp_config: Optional[Dict] = None
    civic_scraper_urls: Optional[List[str]] = None
    html_parsing_urls: Optional[List[str]] = None

    # Quality and reliability metrics
    primary_source: str = "auto"  # auto-select based on quality
    failover_enabled: bool = True
    archive_enabled: bool = False  # Default to False - only use archived data when explicitly enabled


class CivicDataArchive:
    """Local data sovereignty through SQLite archival system"""

    def __init__(self, archive_path: str = "data/civic_participation.db"):
        self.archive_path = Path(archive_path)
        self.archive_path.parent.mkdir(exist_ok=True)
        self._initialize_database()

    def _initialize_database(self):
        """Create archive tables for civic data sovereignty"""
        conn = sqlite3.connect(self.archive_path)

        # Events table for civic events
        conn.execute("""
            CREATE TABLE IF NOT EXISTS civic_events (
                id TEXT PRIMARY KEY,
                jurisdiction TEXT NOT NULL,
                title TEXT NOT NULL,
                meeting_datetime TEXT NOT NULL,
                status TEXT,
                meeting_type TEXT,
                location TEXT,
                agenda_uri TEXT,
                minutes_uri TEXT,
                video_uri TEXT,
                source_platform TEXT NOT NULL,
                source_uri TEXT,
                data_quality_score REAL,
                participation_methods TEXT, -- JSON array
                comment_deadline TEXT,
                archived_timestamp TEXT NOT NULL,
                last_verified TEXT
            )
        """)

        # Source reliability tracking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS source_reliability (
                jurisdiction TEXT,
                source_platform TEXT,
                date_checked TEXT,
                events_found INTEGER,
                quality_score REAL,
                response_time_ms INTEGER,
                error_count INTEGER,
                success_rate REAL,
                PRIMARY KEY (jurisdiction, source_platform, date_checked)
            )
        """)

        # Vendor dependency tracking
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vendor_dependency (
                jurisdiction TEXT PRIMARY KEY,
                legistar_dependency_pct REAL,
                granicus_dependency_pct REAL,
                vendor_risk_score REAL,
                independence_score REAL,
                last_assessment TEXT
            )
        """)

        conn.commit()
        conn.close()

    def archive_events(self, events: List[Dict], source_platform: str, jurisdiction: str, quality_score: float):
        """Archive civic events with source attribution"""
        if not events:
            return

        conn = sqlite3.connect(self.archive_path)
        timestamp = datetime.now(timezone.utc).isoformat()

        for event in events:
            # Convert participation methods to JSON string
            participation_json = json.dumps(event.get('participation_methods', []))

            conn.execute("""
                INSERT OR REPLACE INTO civic_events
                (id, jurisdiction, title, meeting_datetime, status, meeting_type, location,
                 agenda_uri, minutes_uri, video_uri, source_platform, source_uri,
                 data_quality_score, participation_methods, comment_deadline,
                 archived_timestamp, last_verified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.get('id', ''),
                jurisdiction,
                event.get('title', ''),
                event.get('meeting_datetime', ''),
                event.get('status', ''),
                event.get('meeting_type', ''),
                event.get('location', ''),
                event.get('agenda_uri', ''),
                event.get('minutes_uri', ''),
                event.get('video_uri', ''),
                source_platform,
                event.get('source_uri', ''),
                quality_score,
                participation_json,
                event.get('comment_deadline', ''),
                timestamp,
                timestamp
            ))

        conn.commit()
        conn.close()

        logging.info(f"Archived {len(events)} events from {source_platform} for {jurisdiction}")

    def get_archived_events(self, jurisdiction: str, days_forward: int = 14) -> List[Dict]:
        """Retrieve archived events when live sources fail"""
        conn = sqlite3.connect(self.archive_path)

        end_date = (datetime.now() + timedelta(days=days_forward)).isoformat()

        cursor = conn.execute("""
            SELECT * FROM civic_events
            WHERE jurisdiction = ? AND meeting_datetime <= ?
            ORDER BY meeting_datetime DESC
            LIMIT 50
        """, (jurisdiction, end_date))

        columns = [desc[0] for desc in cursor.description]
        events = []

        for row in cursor.fetchall():
            event = dict(zip(columns, row))
            # Convert JSON string back to list
            event['participation_methods'] = json.loads(event.get('participation_methods', '[]'))
            events.append(event)

        conn.close()
        return events

    def update_source_reliability(self, jurisdiction: str, source_platform: str,
                                events_found: int, quality_score: float,
                                response_time_ms: int, error_count: int):
        """Track source reliability for failover optimization"""
        conn = sqlite3.connect(self.archive_path)

        date_checked = datetime.now().date().isoformat()
        success_rate = max(0.0, 1.0 - (error_count * 0.2))  # Simple reliability metric

        conn.execute("""
            INSERT OR REPLACE INTO source_reliability
            (jurisdiction, source_platform, date_checked, events_found,
             quality_score, response_time_ms, error_count, success_rate)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (jurisdiction, source_platform, date_checked, events_found,
              quality_score, response_time_ms, error_count, success_rate))

        conn.commit()
        conn.close()


class UnifiedDataSourceManager:
    """
    Unified manager for all civic data sources with automatic failover
    Core component of Phase 2A resilience strategy
    """

    def __init__(self, config: DataSourceConfig):
        self.config = config
        self.jurisdiction = config.jurisdiction_name.lower()

        # Initialize archive system
        self.archive = CivicDataArchive()

        # Initialize available clients
        self.cdp_client = None
        self.legistar_client = None

        if config.cdp_available and CDP_AVAILABLE:
            self.cdp_client = create_cdp_client(self.jurisdiction)

        if config.legistar_available and config.legistar_client_name:
            self.legistar_client = LegistarClient(config.legistar_client_name)

        # Source priority order (CDP → Legistar API → civic-scraper → HTML → archived)
        self.source_priority = []
        if self.cdp_client:
            self.source_priority.append(("cdp", self.cdp_client))
        if self.legistar_client:
            self.source_priority.append(("legistar_api", self.legistar_client))
        if config.civic_scraper_available:
            self.source_priority.append(("civic_scraper", None))
        if config.html_parsing_available:
            self.source_priority.append(("html_parsing", None))

        # Include archive as final fallback (unless disabled for testing/verification)
        if config.archive_enabled:
            self.source_priority.append(("archived", self.archive))

        logging.info(f"Initialized UnifiedDataSourceManager for {config.jurisdiction_name}")
        logging.info(f"Available sources: {[s[0] for s in self.source_priority]}")

    def get_civic_opportunities(self, days_forward: int = 14, days_back: int = 7) -> Tuple[List[Dict], str, Dict]:
        """
        Get civic events with automatic failover across all sources
        Returns: (events, source_used, metadata)
        """
        start_time = time.time()
        last_error = None

        for source_name, client in self.source_priority:
            try:
                logging.info(f"Trying {source_name} for {self.config.jurisdiction_name}...")

                events = []
                quality_score = 0.0

                if source_name == "cdp":
                    events = client.get_civic_events(days_forward, days_back)
                    quality_score = self._assess_quality_score(events)

                elif source_name == "legistar_api":
                    # Skip probe for known working clients - probe can hit rate limits
                    # Just try to fetch events directly (has proper error handling)
                    events = client.get_recent_events(days_back, days_forward)
                    events = self._normalize_legistar_to_schema(events)
                    quality_score = self._assess_quality_score(events)

                elif source_name == "civic_scraper":
                    events = self._get_civic_scraper_events(days_forward, days_back)
                    quality_score = self._assess_quality_score(events)

                elif source_name == "html_parsing":
                    events = self._get_html_parsing_events(days_forward, days_back)
                    quality_score = self._assess_quality_score(events)

                elif source_name == "archived":
                    events = client.get_archived_events(self.config.jurisdiction_id, days_forward)
                    quality_score = 0.7  # Archived data is reliable but potentially stale

                # Record source performance
                response_time_ms = int((time.time() - start_time) * 1000)
                error_count = 0 if events else 1

                self.archive.update_source_reliability(
                    self.config.jurisdiction_id, source_name, len(events),
                    quality_score, response_time_ms, error_count
                )

                if events and len(events) > 0:
                    # Archive successful data for future resilience
                    if source_name != "archived":
                        self.archive.archive_events(events, source_name,
                                                  self.config.jurisdiction_id, quality_score)

                    metadata = {
                        "source_used": source_name,
                        "events_count": len(events),
                        "quality_score": quality_score,
                        "response_time_ms": response_time_ms,
                        "failover_level": self.source_priority.index((source_name, client)),
                        "vendor_independence": self._calculate_vendor_independence(),
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }

                    logging.info(f"✅ Success with {source_name}: {len(events)} events, quality {quality_score:.2f}")
                    return events, source_name, metadata

            except Exception as e:
                last_error = e
                logging.warning(f"❌ {source_name} failed: {e}")
                continue

        # All sources failed
        logging.error(f"All data sources failed for {self.config.jurisdiction_name}. Last error: {last_error}")
        return [], "none", {
            "source_used": "none",
            "events_count": 0,
            "quality_score": 0.0,
            "error": str(last_error),
            "vendor_independence": self._calculate_vendor_independence(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    def _normalize_legistar_to_schema(self, legistar_events: List[Dict]) -> List[Dict]:
        """Normalize Legistar events to civic-app-schema format"""
        normalized = []

        for event in legistar_events:
            normalized_event = {
                "id": f"legistar_{event.get('event_id', '')}",
                "title": event.get("title", ""),
                "meeting_datetime": event.get("meeting_datetime", ""),
                "status": event.get("status", "").lower(),
                "meeting_type": event.get("meeting_type", ""),
                "jurisdiction": self.config.jurisdiction_name,
                "location": event.get("location", ""),
                "agenda_uri": event.get("agenda_url", ""),
                "minutes_uri": event.get("minutes_url", ""),
                "video_uri": event.get("video_url", ""),
                "source_uri": f"https://webapi.legistar.com/v1/{self.config.legistar_client_name}/events/{event.get('event_id', '')}",

                # Civic engagement fields
                "participation_methods": ["public_comment", "in_person_attendance"],
                "comment_deadline": self._calculate_comment_deadline(event.get("date", "")),
                "public_comment_allowed": True,

                # Metadata
                "source_platform": "legistar_api",
                "data_source": f"legistar_{self.config.legistar_client_name}",
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            normalized.append(normalized_event)

        return normalized

    def _get_civic_scraper_events(self, days_forward: int, days_back: int) -> List[Dict]:
        """Get events using civic-scraper (placeholder implementation)"""
        # This would integrate with civic-scraper CLI or library
        # For now, return empty list indicating implementation needed
        logging.info(f"civic-scraper integration for {self.config.jurisdiction_name} - implementation needed")
        return []

    def _get_html_parsing_events(self, days_forward: int, days_back: int) -> List[Dict]:
        """Get events using HTML parsing (existing civic_digest.py logic)"""
        # This would integrate with existing civic_digest.py GPT-4 parsing
        logging.info(f"HTML parsing for {self.config.jurisdiction_name} - integration with civic_digest.py needed")
        return []

    def _assess_quality_score(self, events: List[Dict]) -> float:
        """Assess data quality score (0.0 - 1.0)"""
        if not events:
            return 0.0

        required_fields = ["title", "meeting_datetime", "status"]
        desirable_fields = ["agenda_uri", "location", "participation_methods"]

        total_score = 0.0

        for event in events:
            score = 0.0

            # Required fields (70% weight)
            for field in required_fields:
                if event.get(field):
                    score += 0.7 / len(required_fields)

            # Desirable fields (30% weight)
            for field in desirable_fields:
                if event.get(field):
                    score += 0.3 / len(desirable_fields)

            total_score += score

        return total_score / len(events)

    def _calculate_comment_deadline(self, meeting_datetime: str) -> str:
        """Calculate comment deadline (typically 24 hours before meeting)"""
        if not meeting_datetime:
            return ""

        try:
            dt = datetime.fromisoformat(meeting_datetime.replace('Z', '+00:00'))
            deadline = dt - timedelta(hours=24)
            return deadline.isoformat()
        except Exception:
            return ""

    def _calculate_vendor_independence(self) -> Dict[str, Any]:
        """Calculate vendor independence metrics"""
        total_sources = len(self.source_priority) - 1  # Exclude archived
        granicus_dependent = 1 if any(s[0] == "legistar_api" for s in self.source_priority) else 0

        independence_score = 1.0 - (granicus_dependent / max(total_sources, 1))

        return {
            "total_sources": total_sources,
            "granicus_dependency": granicus_dependent > 0,
            "independence_score": round(independence_score, 2),
            "vendor_risk_level": "high" if independence_score < 0.5 else "medium" if independence_score < 0.8 else "low"
        }

    def generate_resilience_report(self) -> Dict[str, Any]:
        """Generate comprehensive resilience and vendor independence report"""
        # Get recent reliability data from archive
        conn = sqlite3.connect(self.archive.archive_path)

        # Source reliability over last 7 days
        week_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
        cursor = conn.execute("""
            SELECT source_platform, AVG(success_rate) as avg_success_rate,
                   AVG(quality_score) as avg_quality, COUNT(*) as checks
            FROM source_reliability
            WHERE jurisdiction = ? AND date_checked >= ?
            GROUP BY source_platform
        """, (self.config.jurisdiction_id, week_ago))

        source_reliability = {}
        for row in cursor.fetchall():
            source_reliability[row[0]] = {
                "success_rate": round(row[1], 3),
                "quality_score": round(row[2], 3),
                "checks_performed": row[3]
            }

        # Total archived events for sovereignty assessment
        cursor = conn.execute("""
            SELECT COUNT(*) as total_archived,
                   COUNT(DISTINCT source_platform) as unique_sources,
                   MAX(archived_timestamp) as last_archive
            FROM civic_events
            WHERE jurisdiction = ?
        """, (self.config.jurisdiction_id,))

        archive_stats = cursor.fetchone()
        conn.close()

        report = {
            "jurisdiction": self.config.jurisdiction_name,
            "assessment_timestamp": datetime.now(timezone.utc).isoformat(),

            "resilience_metrics": {
                "available_sources": len(self.source_priority) - 1,  # Exclude archived
                "primary_source_health": source_reliability,
                "failover_capable": len(self.source_priority) > 2,
                "data_sovereignty": {
                    "total_archived_events": archive_stats[0] if archive_stats else 0,
                    "unique_source_coverage": archive_stats[1] if archive_stats else 0,
                    "last_archive_date": archive_stats[2] if archive_stats else None
                }
            },

            "vendor_risk_assessment": self._calculate_vendor_independence(),

            "recommendations": self._generate_resilience_recommendations(source_reliability)
        }

        return report

    def _generate_resilience_recommendations(self, source_reliability: Dict) -> List[str]:
        """Generate specific recommendations for improving resilience"""
        recommendations = []

        vendor_metrics = self._calculate_vendor_independence()

        if vendor_metrics["vendor_risk_level"] == "high":
            recommendations.append("HIGH PRIORITY: Diversify data sources to reduce vendor dependency")

        if not source_reliability:
            recommendations.append("Establish baseline reliability monitoring across all sources")

        # Check for CDP availability
        if not self.cdp_client:
            recommendations.append("Investigate CDP (Council Data Project) integration for enhanced data sovereignty")

        # Check for multiple working sources
        working_sources = [k for k, v in source_reliability.items() if v.get("success_rate", 0) > 0.8]
        if len(working_sources) < 2:
            recommendations.append("Implement additional data sources for redundancy")

        # Archive recommendations
        if len(recommendations) == 0:
            recommendations.append("Excellent resilience posture - maintain current multi-source architecture")

        return recommendations


# Factory for creating unified managers for known jurisdictions
def create_unified_manager(jurisdiction: str) -> Optional[UnifiedDataSourceManager]:
    """Create unified data source manager for known jurisdictions"""

    # Oakland configuration - dual-source validation ready
    if jurisdiction.lower() == "oakland":
        config = DataSourceConfig(
            jurisdiction_id="city-oakland",
            jurisdiction_name="Oakland",
            timezone="America/Los_Angeles",
            cdp_available=True,
            legistar_available=True,
            civic_scraper_available=True,
            html_parsing_available=True,
            legistar_client_name="oakland",
            cdp_config=KNOWN_CDP_JURISDICTIONS.get("oakland"),
            primary_source="auto"
        )
        return UnifiedDataSourceManager(config)

    # Berkeley configuration - cost-efficient HTML parsing
    elif jurisdiction.lower() == "berkeley":
        config = DataSourceConfig(
            jurisdiction_id="city-berkeley",
            jurisdiction_name="Berkeley",
            timezone="America/Los_Angeles",
            cdp_available=False,
            legistar_available=False,
            civic_scraper_available=True,
            html_parsing_available=True,
            html_parsing_urls=["https://www.cityofberkeley.info/"],
            primary_source="html_parsing"
        )
        return UnifiedDataSourceManager(config)

    # San Rafael configuration - proven HTML parsing
    elif jurisdiction.lower() == "san-rafael":
        config = DataSourceConfig(
            jurisdiction_id="city-san-rafael",
            jurisdiction_name="San Rafael",
            timezone="America/Los_Angeles",
            cdp_available=False,
            legistar_available=False,
            civic_scraper_available=False,
            html_parsing_available=True,
            html_parsing_urls=["https://cityofsanrafael.org/meetings/"],
            primary_source="html_parsing"
        )
        return UnifiedDataSourceManager(config)

    else:
        logging.warning(f"No unified manager configuration for {jurisdiction}")
        return None


# Example usage and testing
if __name__ == "__main__":
    # Test Oakland dual-source manager
    oakland_manager = create_unified_manager("oakland")
    if oakland_manager:
        print(f"✅ Oakland unified manager created")
        print(f"📊 Available sources: {[s[0] for s in oakland_manager.source_priority]}")

        # Test civic events with failover
        events, source_used, metadata = oakland_manager.get_civic_opportunities()
        print(f"📅 Found {len(events)} events using {source_used}")
        print(f"🎯 Quality score: {metadata.get('quality_score', 0):.2f}")
        print(f"🛡️  Vendor independence: {metadata.get('vendor_independence', {}).get('independence_score', 0):.2f}")

        # Generate resilience report
        report = oakland_manager.generate_resilience_report()
        print(f"\\n📋 Resilience Report:")
        print(f"   Available sources: {report['resilience_metrics']['available_sources']}")
        print(f"   Vendor risk: {report['vendor_risk_assessment']['vendor_risk_level']}")
        print(f"   Recommendations: {len(report['recommendations'])}")

    else:
        print("❌ Failed to create Oakland unified manager")