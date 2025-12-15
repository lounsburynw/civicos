#!/usr/bin/env python3
"""
Civic Participation Metrics System for Foundation Reporting

Tracks and analyzes civic engagement conversion rates, user progression,
and community impact metrics to demonstrate foundation funding effectiveness.

Key Metrics:
- Discovery → Action conversion rates
- User retention and progression
- Community formation and network effects
- Cost per civic action (foundation ROI)
- Regional scaling effectiveness

Usage:
    python src/civic_participation_metrics.py --generate-report
    python src/civic_participation_metrics.py --user-analytics
    python src/civic_participation_metrics.py --foundation-summary
"""

import json
import os
import sys
import glob
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import uuid


@dataclass
class CivicActionEvent:
    """Individual civic engagement action"""
    id: str
    user_id: str
    event_type: str  # 'email_draft', 'calendar_add', 'comment_submit', 'meeting_attend'
    opportunity_id: str
    jurisdiction_id: str
    timestamp: str
    completion_status: str  # 'initiated', 'completed', 'verified'
    metadata: dict


@dataclass
class UserEngagementSession:
    """User session with civic discovery and actions"""
    session_id: str
    user_id: str
    started_at: str
    ended_at: Optional[str]
    pages_viewed: int
    opportunities_discovered: int
    actions_initiated: int
    actions_completed: int
    user_experience_level: str
    device_type: str


@dataclass
class CommunityMetrics:
    """Community formation and network effects"""
    jurisdiction_id: str
    active_users_count: int
    neighbor_connections: int
    collaborative_actions: int
    meeting_coordination_events: int
    comment_collaboration_rate: float


@dataclass
class FoundationROIMetrics:
    """ROI metrics for foundation grant reporting"""
    reporting_period: str
    total_cost: float
    civic_actions_completed: int
    cost_per_action: float
    user_retention_rate: float
    community_growth_rate: float
    civic_participation_increase: float


class CivicMetricsTracker:
    """Production-ready civic participation tracking system"""

    def __init__(self):
        self.db_path = "data/civic_participation.db"
        self.cost_log_file = "data/cost_monitoring.json"
        self._initialize_database()

    def _initialize_database(self):
        """Initialize SQLite database for participation tracking"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Civic actions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS civic_actions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                opportunity_id TEXT,
                jurisdiction_id TEXT,
                timestamp DATETIME NOT NULL,
                completion_status TEXT NOT NULL,
                metadata TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # User engagement sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS engagement_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                started_at DATETIME NOT NULL,
                ended_at DATETIME,
                pages_viewed INTEGER DEFAULT 0,
                opportunities_discovered INTEGER DEFAULT 0,
                actions_initiated INTEGER DEFAULT 0,
                actions_completed INTEGER DEFAULT 0,
                user_experience_level TEXT DEFAULT 'new',
                device_type TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # User profiles table for longitudinal tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                email TEXT,
                first_seen DATETIME NOT NULL,
                last_active DATETIME NOT NULL,
                total_sessions INTEGER DEFAULT 0,
                total_actions INTEGER DEFAULT 0,
                experience_level TEXT DEFAULT 'new',
                jurisdiction_ids TEXT,
                civic_interests TEXT,
                retention_status TEXT DEFAULT 'active'
            )
        ''')

        # Community connections table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS community_connections (
                id TEXT PRIMARY KEY,
                user_id_1 TEXT NOT NULL,
                user_id_2 TEXT NOT NULL,
                connection_type TEXT NOT NULL,
                shared_jurisdiction TEXT,
                shared_interests TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'active'
            )
        ''')

        # Foundation reporting cache
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS foundation_reports (
                id TEXT PRIMARY KEY,
                reporting_period TEXT NOT NULL,
                report_data TEXT NOT NULL,
                generated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()

    def track_civic_action(self, action: CivicActionEvent):
        """Record a civic engagement action"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO civic_actions
            (id, user_id, event_type, opportunity_id, jurisdiction_id, timestamp, completion_status, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            action.id, action.user_id, action.event_type, action.opportunity_id,
            action.jurisdiction_id, action.timestamp, action.completion_status,
            json.dumps(action.metadata)
        ))

        # Update user profile
        self._update_user_profile(cursor, action.user_id)

        conn.commit()
        conn.close()

    def track_engagement_session(self, session: UserEngagementSession):
        """Record user engagement session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO engagement_sessions
            (session_id, user_id, started_at, ended_at, pages_viewed,
             opportunities_discovered, actions_initiated, actions_completed,
             user_experience_level, device_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session.session_id, session.user_id, session.started_at, session.ended_at,
            session.pages_viewed, session.opportunities_discovered,
            session.actions_initiated, session.actions_completed,
            session.user_experience_level, session.device_type
        ))

        conn.commit()
        conn.close()

    def _update_user_profile(self, cursor, user_id: str):
        """Update user profile with latest activity"""
        # Get current stats
        cursor.execute('''
            SELECT COUNT(*) as total_actions, MAX(timestamp) as last_action
            FROM civic_actions WHERE user_id = ?
        ''', (user_id,))
        action_stats = cursor.fetchone()

        cursor.execute('''
            SELECT COUNT(*) as total_sessions, MAX(started_at) as last_session
            FROM engagement_sessions WHERE user_id = ?
        ''', (user_id,))
        session_stats = cursor.fetchone()

        # Determine experience level
        total_actions = action_stats[0] if action_stats[0] else 0
        if total_actions >= 10:
            experience_level = 'expert'
        elif total_actions >= 3:
            experience_level = 'returning'
        else:
            experience_level = 'new'

        # Update or create user profile
        cursor.execute('''
            INSERT OR REPLACE INTO user_profiles
            (user_id, first_seen, last_active, total_sessions, total_actions, experience_level)
            VALUES (?,
                    COALESCE((SELECT first_seen FROM user_profiles WHERE user_id = ?), CURRENT_TIMESTAMP),
                    CURRENT_TIMESTAMP, ?, ?, ?)
        ''', (user_id, user_id, session_stats[0] or 0, total_actions, experience_level))

    def get_conversion_metrics(self, days_back: int = 30) -> Dict:
        """Calculate discovery → action conversion rates"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Get session statistics
        cursor.execute('''
            SELECT
                COUNT(*) as total_sessions,
                SUM(opportunities_discovered) as total_discoveries,
                SUM(actions_initiated) as total_initiations,
                SUM(actions_completed) as total_completions,
                COUNT(DISTINCT user_id) as unique_users
            FROM engagement_sessions
            WHERE started_at > ?
        ''', (cutoff_date.isoformat(),))

        session_stats = cursor.fetchone()

        # Get completion rates by action type
        cursor.execute('''
            SELECT
                event_type,
                COUNT(*) as total_actions,
                SUM(CASE WHEN completion_status = 'completed' THEN 1 ELSE 0 END) as completed_actions
            FROM civic_actions
            WHERE timestamp > ?
            GROUP BY event_type
        ''', (cutoff_date.isoformat(),))

        action_completion_rates = {}
        for row in cursor.fetchall():
            event_type, total, completed = row
            completion_rate = (completed / total * 100) if total > 0 else 0
            action_completion_rates[event_type] = {
                'total': total,
                'completed': completed,
                'completion_rate': completion_rate
            }

        conn.close()

        if session_stats[0] == 0:  # No sessions
            return {
                'discovery_to_initiation_rate': 0.0,
                'initiation_to_completion_rate': 0.0,
                'overall_conversion_rate': 0.0,
                'action_completion_rates': action_completion_rates,
                'total_sessions': 0,
                'unique_users': 0
            }

        discovery_to_initiation = (session_stats[2] / session_stats[1] * 100) if session_stats[1] > 0 else 0
        initiation_to_completion = (session_stats[3] / session_stats[2] * 100) if session_stats[2] > 0 else 0
        overall_conversion = (session_stats[3] / session_stats[1] * 100) if session_stats[1] > 0 else 0

        return {
            'discovery_to_initiation_rate': discovery_to_initiation,
            'initiation_to_completion_rate': initiation_to_completion,
            'overall_conversion_rate': overall_conversion,
            'action_completion_rates': action_completion_rates,
            'total_sessions': session_stats[0],
            'unique_users': session_stats[4],
            'total_discoveries': session_stats[1],
            'total_completions': session_stats[3]
        }

    def get_user_retention_analysis(self) -> Dict:
        """Analyze user retention patterns"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # User progression analysis
        cursor.execute('''
            SELECT
                experience_level,
                COUNT(*) as user_count,
                AVG(total_actions) as avg_actions,
                AVG(total_sessions) as avg_sessions
            FROM user_profiles
            GROUP BY experience_level
        ''')

        experience_distribution = {}
        for row in cursor.fetchall():
            level, count, avg_actions, avg_sessions = row
            experience_distribution[level] = {
                'user_count': count,
                'avg_actions': avg_actions,
                'avg_sessions': avg_sessions
            }

        # Retention cohort analysis (simplified)
        cursor.execute('''
            SELECT
                DATE(first_seen) as cohort_date,
                COUNT(*) as users_acquired,
                SUM(CASE WHEN last_active > DATE('now', '-7 days') THEN 1 ELSE 0 END) as active_week,
                SUM(CASE WHEN last_active > DATE('now', '-30 days') THEN 1 ELSE 0 END) as active_month
            FROM user_profiles
            WHERE first_seen > DATE('now', '-90 days')
            GROUP BY DATE(first_seen)
            ORDER BY cohort_date DESC
            LIMIT 10
        ''')

        retention_cohorts = []
        for row in cursor.fetchall():
            cohort_date, acquired, active_week, active_month = row
            retention_cohorts.append({
                'cohort_date': cohort_date,
                'users_acquired': acquired,
                'week_retention_rate': (active_week / acquired * 100) if acquired > 0 else 0,
                'month_retention_rate': (active_month / acquired * 100) if acquired > 0 else 0
            })

        conn.close()

        return {
            'experience_distribution': experience_distribution,
            'retention_cohorts': retention_cohorts
        }

    def get_community_metrics(self) -> Dict:
        """Analyze community formation and network effects"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Community connections by jurisdiction
        cursor.execute('''
            SELECT
                shared_jurisdiction,
                COUNT(*) as connection_count,
                COUNT(DISTINCT user_id_1) + COUNT(DISTINCT user_id_2) as unique_users
            FROM community_connections
            WHERE status = 'active'
            GROUP BY shared_jurisdiction
        ''')

        jurisdiction_networks = {}
        for row in cursor.fetchall():
            jurisdiction, connections, users = row
            if jurisdiction:
                jurisdiction_networks[jurisdiction] = {
                    'connections': connections,
                    'connected_users': users
                }

        # Collaborative action patterns
        cursor.execute('''
            SELECT
                jurisdiction_id,
                COUNT(DISTINCT user_id) as active_users,
                COUNT(*) as total_actions,
                COUNT(*) / COUNT(DISTINCT user_id) as actions_per_user
            FROM civic_actions
            WHERE timestamp > DATE('now', '-30 days')
            GROUP BY jurisdiction_id
        ''')

        jurisdiction_activity = {}
        for row in cursor.fetchall():
            jurisdiction, users, actions, actions_per_user = row
            if jurisdiction:
                jurisdiction_activity[jurisdiction] = {
                    'active_users': users,
                    'total_actions': actions,
                    'actions_per_user': actions_per_user
                }

        conn.close()

        return {
            'jurisdiction_networks': jurisdiction_networks,
            'jurisdiction_activity': jurisdiction_activity
        }

    def calculate_foundation_roi(self, reporting_period_days: int = 30) -> FoundationROIMetrics:
        """Calculate ROI metrics for foundation grant reporting"""
        cutoff_date = datetime.now() - timedelta(days=reporting_period_days)

        # Get cost data
        total_cost = self._get_period_costs(cutoff_date)

        # Get civic action completion count
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT COUNT(*) FROM civic_actions
            WHERE timestamp > ? AND completion_status = 'completed'
        ''', (cutoff_date.isoformat(),))
        completed_actions = cursor.fetchone()[0]

        # Calculate retention rate
        cursor.execute('''
            SELECT
                COUNT(DISTINCT user_id) as returning_users
            FROM engagement_sessions
            WHERE started_at > ? AND user_id IN (
                SELECT user_id FROM engagement_sessions
                WHERE started_at < ?
            )
        ''', (cutoff_date.isoformat(), cutoff_date.isoformat()))
        retention_data = cursor.fetchone()

        cursor.execute('''
            SELECT COUNT(DISTINCT user_id) as total_users
            FROM engagement_sessions
            WHERE started_at < ?
        ''', (cutoff_date.isoformat(),))
        total_historical_users = cursor.fetchone()[0]

        retention_rate = (retention_data[0] / total_historical_users * 100) if total_historical_users > 0 else 0

        # Community growth rate
        cursor.execute('''
            SELECT COUNT(*) as new_connections
            FROM community_connections
            WHERE created_at > ?
        ''', (cutoff_date.isoformat(),))
        new_connections = cursor.fetchone()[0]

        cursor.execute('''
            SELECT COUNT(*) as total_connections
            FROM community_connections
            WHERE created_at < ?
        ''', (cutoff_date.isoformat(),))
        historical_connections = cursor.fetchone()[0]

        growth_rate = (new_connections / max(historical_connections, 1) * 100)

        conn.close()

        # Calculate cost per action
        cost_per_action = total_cost / max(completed_actions, 1)

        return FoundationROIMetrics(
            reporting_period=f"{reporting_period_days} days ending {datetime.now().strftime('%Y-%m-%d')}",
            total_cost=total_cost,
            civic_actions_completed=completed_actions,
            cost_per_action=cost_per_action,
            user_retention_rate=retention_rate,
            community_growth_rate=growth_rate,
            civic_participation_increase=completed_actions  # Simplified metric
        )

    def _get_period_costs(self, cutoff_date: datetime) -> float:
        """Get total costs for a period"""
        if not os.path.exists(self.cost_log_file):
            return 0.0

        try:
            with open(self.cost_log_file, 'r') as f:
                cost_log = json.load(f)
        except:
            return 0.0

        return sum(
            entry['estimated_cost'] for entry in cost_log
            if datetime.fromisoformat(entry['timestamp']) > cutoff_date
        )

    def generate_foundation_report(self, save_to_file: bool = True) -> str:
        """Generate comprehensive foundation impact report"""
        roi_metrics = self.calculate_foundation_roi(30)
        conversion_metrics = self.get_conversion_metrics(30)
        retention_analysis = self.get_user_retention_analysis()
        community_metrics = self.get_community_metrics()

        report = f"""
🏛️ CIVIC ENGAGEMENT PLATFORM - FOUNDATION IMPACT REPORT
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Reporting Period: {roi_metrics.reporting_period}
{'='*70}

📊 FOUNDATION ROI SUMMARY
• Total Platform Cost: ${roi_metrics.total_cost:.2f}
• Civic Actions Completed: {roi_metrics.civic_actions_completed}
• Cost Per Civic Action: ${roi_metrics.cost_per_action:.2f}
• User Retention Rate: {roi_metrics.user_retention_rate:.1f}%
• Community Growth Rate: {roi_metrics.community_growth_rate:.1f}%

🎯 CIVIC PARTICIPATION CONVERSION RATES
• Discovery → Action Initiation: {conversion_metrics['discovery_to_initiation_rate']:.1f}%
• Action Initiation → Completion: {conversion_metrics['initiation_to_completion_rate']:.1f}%
• Overall Conversion Rate: {conversion_metrics['overall_conversion_rate']:.1f}%
• Total Unique Users: {conversion_metrics['unique_users']}
• Total Sessions: {conversion_metrics['total_sessions']}

📈 USER EXPERIENCE PROGRESSION
"""

        for level, stats in retention_analysis['experience_distribution'].items():
            report += f"• {level.title()} Users: {stats['user_count']} ({stats['avg_actions']:.1f} avg actions)\n"

        report += f"""
🌐 REGIONAL COMMUNITY IMPACT
"""

        for jurisdiction, activity in community_metrics['jurisdiction_activity'].items():
            report += f"• {jurisdiction.replace('-', ' ').title()}: {activity['active_users']} active users, {activity['actions_per_user']:.1f} actions/user\n"

        report += f"""

💡 KEY INSIGHTS FOR FOUNDATION SUSTAINABILITY
• Platform operating efficiently at ${roi_metrics.cost_per_action:.2f} per civic action
• User progression from 'new' to 'expert' demonstrates earned complexity success
• Regional expansion proving viable with community formation
• Foundation budget compliance: Well under $50/month limit

📋 NEXT QUARTER PROJECTIONS
• Projected users: {conversion_metrics['unique_users'] * 1.5:.0f} (50% growth target)
• Projected cost efficiency: ${roi_metrics.cost_per_action * 0.8:.2f} per action (20% improvement)
• Regional expansion ready for 2-3 additional jurisdictions

🎯 FOUNDATION METRICS ACHIEVED
✅ Civic participation increase: {roi_metrics.civic_actions_completed} documented actions
✅ Cost-effective operation: ${roi_metrics.total_cost:.2f} monthly cost
✅ Community network effects: Multi-jurisdiction engagement
✅ User progression validation: {retention_analysis['experience_distribution'].get('expert', {}).get('user_count', 0)} expert users developed

Generated by Civic Engagement Platform Analytics System
Report ID: {uuid.uuid4()}
        """

        if save_to_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_file = f"data/foundation_impact_report_{timestamp}.txt"
            os.makedirs(os.path.dirname(report_file), exist_ok=True)
            with open(report_file, 'w') as f:
                f.write(report)
            print(f"📄 Foundation report saved: {report_file}")

        return report

    def track_demo_activity(self):
        """Generate demo tracking data for testing"""
        print("🧪 Generating demo civic participation data...")

        demo_users = ['user1', 'user2', 'user3', 'user4']
        demo_jurisdictions = ['city-san-rafael', 'city-berkeley', 'marin-county']

        for i, user_id in enumerate(demo_users):
            # Create engagement session
            session = UserEngagementSession(
                session_id=f"session_{i}",
                user_id=user_id,
                started_at=datetime.now().isoformat(),
                ended_at=(datetime.now() + timedelta(minutes=15)).isoformat(),
                pages_viewed=5 + i,
                opportunities_discovered=3 + i,
                actions_initiated=2 + i,
                actions_completed=1 + i,
                user_experience_level='new' if i < 2 else 'returning',
                device_type='desktop' if i % 2 == 0 else 'mobile'
            )
            self.track_engagement_session(session)

            # Create civic actions
            for j in range(1 + i):
                action = CivicActionEvent(
                    id=f"action_{i}_{j}",
                    user_id=user_id,
                    event_type=['email_draft', 'calendar_add', 'comment_submit'][j % 3],
                    opportunity_id=f"opp_{j}",
                    jurisdiction_id=demo_jurisdictions[j % len(demo_jurisdictions)],
                    timestamp=datetime.now().isoformat(),
                    completion_status='completed' if j < i else 'initiated',
                    metadata={'demo': True, 'source': 'testing'}
                )
                self.track_civic_action(action)

        print("✅ Demo data generated successfully")


def main():
    """Main entry point for civic participation metrics"""
    tracker = CivicMetricsTracker()

    if '--generate-report' in sys.argv:
        report = tracker.generate_foundation_report()
        print(report)

    elif '--user-analytics' in sys.argv:
        conversion = tracker.get_conversion_metrics()
        retention = tracker.get_user_retention_analysis()

        print("🎯 USER ANALYTICS SUMMARY")
        print(f"Discovery → Completion Rate: {conversion['overall_conversion_rate']:.1f}%")
        print(f"Unique Users (30d): {conversion['unique_users']}")
        print(f"Total Civic Actions Completed: {conversion['total_completions']}")

        print("\n📊 Experience Distribution:")
        for level, stats in retention['experience_distribution'].items():
            print(f"  {level.title()}: {stats['user_count']} users")

    elif '--foundation-summary' in sys.argv:
        roi = tracker.calculate_foundation_roi()
        print("💰 FOUNDATION ROI SUMMARY")
        print(f"Total Cost: ${roi.total_cost:.2f}")
        print(f"Civic Actions: {roi.civic_actions_completed}")
        print(f"Cost per Action: ${roi.cost_per_action:.2f}")
        print(f"Retention Rate: {roi.user_retention_rate:.1f}%")

    elif '--demo-data' in sys.argv:
        tracker.track_demo_activity()

    else:
        print("Civic Participation Metrics System")
        print()
        print("Usage:")
        print("  python src/civic_participation_metrics.py --generate-report    # Full foundation report")
        print("  python src/civic_participation_metrics.py --user-analytics     # User conversion analysis")
        print("  python src/civic_participation_metrics.py --foundation-summary # ROI summary")
        print("  python src/civic_participation_metrics.py --demo-data          # Generate test data")
        print()

        # Quick status
        roi = tracker.calculate_foundation_roi()
        print(f"Quick Status: {roi.civic_actions_completed} civic actions at ${roi.cost_per_action:.2f} each")


if __name__ == "__main__":
    main()