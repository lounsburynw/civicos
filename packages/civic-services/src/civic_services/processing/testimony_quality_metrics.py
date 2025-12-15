#!/usr/bin/env python3
"""
Quality metrics tracking for testimony extraction pipeline.

Tracks and reports on pipeline performance including speaker identification rates,
confidence distribution, coverage, and costs.

Session: 111 (production hardening)

Usage:
    from testimony_quality_metrics import TestimonyQualityMetrics

    metrics = TestimonyQualityMetrics(db_path="data/civic_participation.db")
    report = metrics.calculate_meeting_metrics(meeting_id="san-rafael_2024-10-06_MpxrGRb16HQ")
    print(report.format_report())
"""

import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional
from pathlib import Path


@dataclass
class QualityReport:
    """Quality metrics for a single meeting."""
    meeting_id: str
    meeting_date: str
    jurisdiction_id: str

    # Speaker identification
    speaker_count_estimated: int
    speaker_count_actual: int
    speaker_count_accuracy: float

    # Name identification
    speakers_identified: int
    speakers_total: int
    identification_rate: float
    identification_methods: Dict[str, int]

    # Confidence distribution
    confidence_high: int
    confidence_medium: int
    confidence_low: int

    # Coverage
    utterances_total: int
    utterances_attributed: int
    coverage: float

    # Costs
    cost_youtube_llm: float
    cost_assemblyai: float
    cost_name_extraction: float
    cost_total: float

    def format_report(self) -> str:
        """Format quality report as human-readable string."""
        lines = [
            "=" * 70,
            "TESTIMONY QUALITY REPORT",
            "=" * 70,
            f"Meeting: {self.meeting_date} {self.jurisdiction_id}",
            f"Meeting ID: {self.meeting_id}",
            "",
            "Speaker Identification:",
            f"- Estimated: {self.speaker_count_estimated} speakers",
            f"- Actual: {self.speaker_count_actual} speakers",
            f"- Accuracy: {self.speaker_count_accuracy:.1%}",
            "",
            "Name Identification:",
            f"- Identified: {self.speakers_identified}/{self.speakers_total} ({self.identification_rate:.1%})",
            "- Methods:",
        ]

        for method, count in sorted(self.identification_methods.items(), key=lambda x: -x[1]):
            pct = count / self.speakers_total * 100 if self.speakers_total > 0 else 0
            lines.append(f"  - {method.replace('_', ' ').title()}: {count} ({pct:.1f}%)")

        lines.extend([
            "",
            "Confidence Distribution:",
            f"- High: {self.confidence_high} speakers ({self.confidence_high/self.speakers_total*100:.1f}%)",
            f"- Medium: {self.confidence_medium} speakers ({self.confidence_medium/self.speakers_total*100:.1f}%)",
            f"- Low: {self.confidence_low} speakers ({self.confidence_low/self.speakers_total*100:.1f}%)",
            "",
            "Coverage:",
            f"- Total utterances: {self.utterances_total}",
            f"- Attributed utterances: {self.utterances_attributed}",
            f"- Coverage: {self.coverage:.1%}",
            "",
            f"Cost: ${self.cost_total:.2f}",
            f"- YouTube LLM: ${self.cost_youtube_llm:.2f}",
            f"- AssemblyAI: ${self.cost_assemblyai:.2f}",
            f"- Name extraction: ${self.cost_name_extraction:.2f}",
            "=" * 70
        ])

        return "\n".join(lines)


class TestimonyQualityMetrics:
    """
    Calculate and track quality metrics for testimony extraction pipeline.

    Provides methods to calculate metrics for individual meetings or aggregate
    across multiple meetings.
    """

    def __init__(self, db_path: str = "data/civic_participation.db"):
        """
        Initialize quality metrics tracker.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path)

        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

    def _get_db_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def calculate_meeting_metrics(self, meeting_id: str) -> Optional[QualityReport]:
        """
        Calculate quality metrics for a single meeting.

        Args:
            meeting_id: Meeting ID to analyze

        Returns:
            QualityReport with all metrics, or None if meeting not found
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            # Get meeting data
            cursor.execute("""
                SELECT
                    meeting_id,
                    jurisdiction_id,
                    meeting_date,
                    speaker_count_estimated,
                    speaker_count_actual,
                    processing_cost_usd
                FROM testimony_meetings
                WHERE meeting_id = ?
            """, (meeting_id,))

            meeting_row = cursor.fetchone()
            if not meeting_row:
                return None

            meeting = dict(meeting_row)

            # Calculate speaker count accuracy
            estimated = meeting['speaker_count_estimated'] or 0
            actual = meeting['speaker_count_actual'] or 0
            accuracy = min(estimated, actual) / max(estimated, actual) if max(estimated, actual) > 0 else 0.0

            # Get speaker identification stats
            cursor.execute("""
                SELECT
                    COUNT(*) as total_speakers,
                    COUNT(CASE WHEN name NOT LIKE 'Unknown%' THEN 1 END) as identified_speakers,
                    COUNT(CASE WHEN confidence = 'high' THEN 1 END) as confidence_high,
                    COUNT(CASE WHEN confidence = 'medium' THEN 1 END) as confidence_medium,
                    COUNT(CASE WHEN confidence = 'low' THEN 1 END) as confidence_low
                FROM testimony_speakers
                WHERE meeting_id = ?
            """, (meeting_id,))

            speaker_stats = dict(cursor.fetchone())

            # Get identification methods breakdown
            cursor.execute("""
                SELECT
                    identification_method,
                    COUNT(*) as count
                FROM testimony_speakers
                WHERE meeting_id = ?
                GROUP BY identification_method
            """, (meeting_id,))

            methods = {row['identification_method']: row['count'] for row in cursor.fetchall()}

            # Get utterance coverage
            cursor.execute("""
                SELECT
                    COUNT(*) as total_utterances
                FROM testimony_utterances u
                JOIN testimony_speakers s ON s.speaker_id = u.speaker_id
                WHERE s.meeting_id = ?
            """, (meeting_id,))

            utterance_count = cursor.fetchone()['total_utterances']

            # Calculate costs (estimated breakdown)
            total_cost = meeting['processing_cost_usd'] or 0.0
            cost_youtube = 0.20  # Fixed cost for YouTube LLM speaker estimation
            cost_assemblyai = total_cost - cost_youtube - (speaker_stats['total_speakers'] * 0.0001)
            cost_name_extraction = speaker_stats['total_speakers'] * 0.0001  # ~$0.0001 per speaker for LLM

            # Build report
            report = QualityReport(
                meeting_id=meeting['meeting_id'],
                meeting_date=meeting['meeting_date'],
                jurisdiction_id=meeting['jurisdiction_id'],

                # Speaker identification
                speaker_count_estimated=estimated,
                speaker_count_actual=actual,
                speaker_count_accuracy=accuracy,

                # Name identification
                speakers_identified=speaker_stats['identified_speakers'],
                speakers_total=speaker_stats['total_speakers'],
                identification_rate=speaker_stats['identified_speakers'] / speaker_stats['total_speakers']
                    if speaker_stats['total_speakers'] > 0 else 0.0,
                identification_methods=methods,

                # Confidence distribution
                confidence_high=speaker_stats['confidence_high'],
                confidence_medium=speaker_stats['confidence_medium'],
                confidence_low=speaker_stats['confidence_low'],

                # Coverage
                utterances_total=utterance_count,
                utterances_attributed=utterance_count,  # All utterances are attributed by definition
                coverage=1.0,

                # Costs
                cost_youtube_llm=cost_youtube,
                cost_assemblyai=cost_assemblyai,
                cost_name_extraction=cost_name_extraction,
                cost_total=total_cost
            )

            return report

        finally:
            conn.close()

    def calculate_aggregate_metrics(
        self,
        jurisdiction_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict:
        """
        Calculate aggregate metrics across multiple meetings.

        Args:
            jurisdiction_id: Optional filter by jurisdiction
            start_date: Optional filter by start date (ISO format)
            end_date: Optional filter by end date (ISO format)

        Returns:
            Dictionary with aggregate metrics
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            # Build query with filters
            where_clauses = []
            params = []

            if jurisdiction_id:
                where_clauses.append("m.jurisdiction_id = ?")
                params.append(jurisdiction_id)

            if start_date:
                where_clauses.append("m.meeting_date >= ?")
                params.append(start_date)

            if end_date:
                where_clauses.append("m.meeting_date <= ?")
                params.append(end_date)

            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

            # Get aggregate stats
            # Build subquery WHERE clause (add AND if where_sql exists)
            subquery_where = f"{where_sql} AND" if where_sql else "WHERE"

            cursor.execute(f"""
                SELECT
                    COUNT(DISTINCT m.meeting_id) as total_meetings,
                    SUM(m.speaker_count_actual) as total_speakers,
                    SUM(m.processing_cost_usd) as total_cost,
                    AVG(
                        CAST(m.speaker_count_estimated AS REAL) /
                        NULLIF(m.speaker_count_actual, 0)
                    ) as avg_count_accuracy,
                    (
                        SELECT COUNT(*)
                        FROM testimony_speakers s2
                        JOIN testimony_meetings m2 ON m2.meeting_id = s2.meeting_id
                        {subquery_where} s2.name NOT LIKE 'Unknown%'
                    ) as identified_speakers,
                    (
                        SELECT COUNT(*)
                        FROM testimony_utterances u2
                        JOIN testimony_speakers s2 ON s2.speaker_id = u2.speaker_id
                        JOIN testimony_meetings m2 ON m2.meeting_id = s2.meeting_id
                        {where_sql}
                    ) as total_utterances
                FROM testimony_meetings m
                {where_sql}
            """, params * 3)  # params repeated for subqueries

            row = cursor.fetchone()

            return {
                'total_meetings': row['total_meetings'] or 0,
                'total_speakers': row['total_speakers'] or 0,
                'total_utterances': row['total_utterances'] or 0,
                'identified_speakers': row['identified_speakers'] or 0,
                'identification_rate': (row['identified_speakers'] or 0) / (row['total_speakers'] or 1),
                'avg_count_accuracy': row['avg_count_accuracy'] or 0.0,
                'total_cost': row['total_cost'] or 0.0,
                'cost_per_meeting': (row['total_cost'] or 0.0) / (row['total_meetings'] or 1)
            }

        finally:
            conn.close()

    def get_identification_breakdown(self, meeting_id: str) -> List[Dict]:
        """
        Get detailed breakdown of speaker identification for a meeting.

        Args:
            meeting_id: Meeting ID to analyze

        Returns:
            List of speaker records with identification details
        """
        conn = self._get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    speaker_label,
                    name,
                    role,
                    confidence,
                    identification_method,
                    utterance_count
                FROM testimony_speakers
                WHERE meeting_id = ?
                ORDER BY utterance_count DESC
            """, (meeting_id,))

            return [dict(row) for row in cursor.fetchall()]

        finally:
            conn.close()
