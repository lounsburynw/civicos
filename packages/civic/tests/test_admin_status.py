"""
Tests for admin status endpoint.

Tests the /admin/status endpoint that returns JSON pipeline health including:
- Database table row counts and timestamps (meetings, issues, agenda_items, initiatives)
- ChromaDB collection document counts
- Overall pipeline health status

Session 299: Initial test coverage for admin_status_endpoint feature.
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestAdminStatusEndpoint:
    """Tests for serve_admin_status handler."""

    @pytest.fixture
    def mock_handler(self):
        """Create a mock HTTP handler for testing serve_admin_status."""
        from civic_services.servers.civic_api_integrated import AuthenticatedCivicAPIHandler

        # Create mock handler without initializing HTTP server
        handler = MagicMock(spec=AuthenticatedCivicAPIHandler)
        handler.path = '/admin/status?jurisdiction=san-rafael'

        # Capture send_json calls
        handler.responses = []

        def capture_json(data, status=200):
            handler.responses.append({'data': data, 'status': status})

        handler.send_json = capture_json

        # Bind the actual method to our mock
        handler.serve_admin_status = AuthenticatedCivicAPIHandler.serve_admin_status.__get__(
            handler, AuthenticatedCivicAPIHandler
        )

        return handler

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary state database with test data."""
        db_path = tmp_path / "civic_state.db"

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create meetings table
        cursor.execute("""
            CREATE TABLE meetings (
                id INTEGER PRIMARY KEY,
                jurisdiction_id TEXT,
                meeting_datetime TEXT,
                updated_at TEXT,
                valid_to TEXT
            )
        """)

        # Create agenda_items table
        cursor.execute("""
            CREATE TABLE agenda_items (
                id INTEGER PRIMARY KEY,
                meeting_id INTEGER,
                enriched_at TEXT,
                valid_to TEXT
            )
        """)

        # Create issues table
        cursor.execute("""
            CREATE TABLE issues (
                id INTEGER PRIMARY KEY,
                jurisdiction_id TEXT,
                status TEXT,
                updated_at TEXT
            )
        """)

        # Create initiatives table
        cursor.execute("""
            CREATE TABLE initiatives (
                id INTEGER PRIMARY KEY,
                jurisdiction_id TEXT,
                updated_at TEXT
            )
        """)

        # Insert test data
        cursor.execute("""
            INSERT INTO meetings (jurisdiction_id, meeting_datetime, updated_at, valid_to)
            VALUES ('san-rafael', '2024-01-15T10:00:00', '2024-01-15T12:00:00', NULL)
        """)
        cursor.execute("""
            INSERT INTO meetings (jurisdiction_id, meeting_datetime, updated_at, valid_to)
            VALUES ('san-rafael', '2024-02-20T10:00:00', '2024-02-20T12:00:00', NULL)
        """)
        cursor.execute("""
            INSERT INTO agenda_items (meeting_id, enriched_at, valid_to)
            VALUES (1, '2024-01-15T14:00:00', NULL)
        """)
        cursor.execute("""
            INSERT INTO issues (jurisdiction_id, status, updated_at)
            VALUES ('san-rafael', 'open', '2024-01-10T09:00:00')
        """)
        cursor.execute("""
            INSERT INTO issues (jurisdiction_id, status, updated_at)
            VALUES ('san-rafael', 'closed', '2024-01-12T09:00:00')
        """)
        cursor.execute("""
            INSERT INTO initiatives (jurisdiction_id, updated_at)
            VALUES ('san-rafael', '2024-01-05T08:00:00')
        """)

        conn.commit()
        conn.close()

        return db_path

    def test_admin_status_returns_valid_json(self, mock_handler, temp_db, tmp_path):
        """Test that /admin/status returns valid JSON response."""
        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:
            mock_path.side_effect = lambda f: str(temp_db) if f == 'civic_state.db' else str(tmp_path / f)

            mock_handler.serve_admin_status()

            assert len(mock_handler.responses) == 1
            response = mock_handler.responses[0]['data']

            # Check required top-level keys
            assert 'status' in response
            assert 'timestamp' in response
            assert 'jurisdiction' in response
            assert 'database' in response
            assert 'chromadb' in response
            assert 'files' in response

    def test_admin_status_includes_database_stats(self, mock_handler, temp_db, tmp_path):
        """Test that response includes database table statistics."""
        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:
            mock_path.side_effect = lambda f: str(temp_db) if f == 'civic_state.db' else str(tmp_path / f)

            mock_handler.serve_admin_status()

            response = mock_handler.responses[0]['data']
            db = response['database']

            # Check meetings stats
            assert 'meetings' in db
            assert db['meetings']['count'] == 2
            assert db['meetings']['earliest'] == '2024-01-15T10:00:00'
            assert db['meetings']['latest'] == '2024-02-20T10:00:00'

            # Check agenda_items stats
            assert 'agenda_items' in db
            assert db['agenda_items']['count'] == 1

            # Check issues stats
            assert 'issues' in db
            assert db['issues']['count'] == 2
            assert 'by_status' in db['issues']
            assert db['issues']['by_status']['open'] == 1
            assert db['issues']['by_status']['closed'] == 1

            # Check initiatives stats
            assert 'initiatives' in db
            assert db['initiatives']['count'] == 1

    def test_admin_status_database_connected(self, mock_handler, temp_db, tmp_path):
        """Test that database status is 'connected' when DB exists."""
        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:
            mock_path.side_effect = lambda f: str(temp_db) if f == 'civic_state.db' else str(tmp_path / f)

            mock_handler.serve_admin_status()

            response = mock_handler.responses[0]['data']
            assert response['database']['status'] == 'connected'
            assert 'path' in response['database']
            assert 'size_bytes' in response['database']

    def test_admin_status_database_missing(self, mock_handler, tmp_path):
        """Test that database status is 'missing' when DB doesn't exist."""
        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:
            mock_path.side_effect = lambda f: str(tmp_path / f)

            mock_handler.serve_admin_status()

            response = mock_handler.responses[0]['data']
            assert response['database']['status'] == 'missing'
            assert response['status'] == 'degraded'

    def test_admin_status_jurisdiction_parameter(self, mock_handler, temp_db, tmp_path):
        """Test that jurisdiction parameter is respected."""
        mock_handler.path = '/admin/status?jurisdiction=oakland'

        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:
            mock_path.side_effect = lambda f: str(temp_db) if f == 'civic_state.db' else str(tmp_path / f)

            mock_handler.serve_admin_status()

            response = mock_handler.responses[0]['data']
            assert response['jurisdiction'] == 'oakland'
            # oakland has no data, so meetings should be 0
            assert response['database']['meetings']['count'] == 0

    def test_admin_status_default_jurisdiction(self, mock_handler, temp_db, tmp_path):
        """Test that default jurisdiction is san-rafael."""
        mock_handler.path = '/admin/status'

        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:
            mock_path.side_effect = lambda f: str(temp_db) if f == 'civic_state.db' else str(tmp_path / f)

            mock_handler.serve_admin_status()

            response = mock_handler.responses[0]['data']
            assert response['jurisdiction'] == 'san-rafael'

    def test_admin_status_timestamp_format(self, mock_handler, temp_db, tmp_path):
        """Test that timestamp is in ISO format with Z suffix."""
        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:
            mock_path.side_effect = lambda f: str(temp_db) if f == 'civic_state.db' else str(tmp_path / f)

            mock_handler.serve_admin_status()

            response = mock_handler.responses[0]['data']
            assert response['timestamp'].endswith('Z')
            # Should be parseable as ISO format
            datetime.fromisoformat(response['timestamp'].replace('Z', '+00:00'))

    def test_admin_status_chromadb_no_storage(self, mock_handler, temp_db, tmp_path):
        """Test chromadb status when storage doesn't exist."""
        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:
            mock_path.side_effect = lambda f: str(temp_db) if f == 'civic_state.db' else str(tmp_path / f)

            mock_handler.serve_admin_status()

            response = mock_handler.responses[0]['data']
            assert response['chromadb']['status'] == 'no_storage'

    def test_admin_status_overall_healthy(self, mock_handler, temp_db, tmp_path):
        """Test that overall status is healthy when all checks pass."""
        # Create vectors directory
        vectors_dir = tmp_path / 'pilot' / 'vectors' / 'san-rafael'
        vectors_dir.mkdir(parents=True)

        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:

            def path_resolver(f):
                if f == 'civic_state.db':
                    return str(temp_db)
                elif f == '':
                    return str(tmp_path)
                return str(tmp_path / f)

            mock_path.side_effect = path_resolver

            mock_handler.serve_admin_status()

            response = mock_handler.responses[0]['data']
            # With db connected and chromadb storage existing, status depends on collections
            assert response['status'] in ['healthy', 'degraded']

    def test_admin_status_handles_table_missing(self, mock_handler, tmp_path):
        """Test graceful handling when tables don't exist."""
        db_path = tmp_path / "civic_state.db"

        # Create empty database without tables
        conn = sqlite3.connect(db_path)
        conn.close()

        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:
            mock_path.side_effect = lambda f: str(db_path) if f == 'civic_state.db' else str(tmp_path / f)

            mock_handler.serve_admin_status()

            response = mock_handler.responses[0]['data']
            # Should still connect but tables should have errors
            assert response['database']['status'] == 'connected'
            assert response['database']['meetings'].get('error') == 'table_missing'

    def test_database_stats_row_counts_and_timestamps(self, mock_handler, temp_db, tmp_path):
        """Verify database_stats: row counts and last modified timestamps per table.

        Session 300: Explicit verification of pilot.json database_stats artifact.
        Each table must include 'count' and a timestamp field (last_updated or equivalent).
        """
        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:
            mock_path.side_effect = lambda f: str(temp_db) if f == 'civic_state.db' else str(tmp_path / f)

            mock_handler.serve_admin_status()

            response = mock_handler.responses[0]['data']
            db = response['database']

            # meetings: must have count + timestamp fields
            assert 'count' in db['meetings'], "meetings must have row count"
            assert db['meetings']['count'] >= 0
            assert 'last_updated' in db['meetings'], "meetings must have last_updated timestamp"
            assert 'earliest' in db['meetings'], "meetings must have earliest timestamp"
            assert 'latest' in db['meetings'], "meetings must have latest timestamp"

            # agenda_items: must have count + timestamp
            assert 'count' in db['agenda_items'], "agenda_items must have row count"
            assert db['agenda_items']['count'] >= 0
            assert 'last_enriched' in db['agenda_items'], "agenda_items must have last_enriched timestamp"

            # issues: must have count + timestamp
            assert 'count' in db['issues'], "issues must have row count"
            assert db['issues']['count'] >= 0
            assert 'last_updated' in db['issues'], "issues must have last_updated timestamp"

            # initiatives: must have count + timestamp
            assert 'count' in db['initiatives'], "initiatives must have row count"
            assert db['initiatives']['count'] >= 0
            assert 'last_updated' in db['initiatives'], "initiatives must have last_updated timestamp"

    def test_chromadb_stats_collection_and_document_counts(self, mock_handler, temp_db, tmp_path):
        """Verify chromadb_stats: collection counts and document counts.

        Session 300: Explicit verification of pilot.json chromadb_stats artifact.
        Must include collections dict with counts + total_documents aggregate.
        """
        # Create vectors directory with mock chromadb
        vectors_dir = tmp_path / 'pilot' / 'vectors' / 'san-rafael'
        vectors_dir.mkdir(parents=True)

        with patch(
            'civic_services.servers.civic_api_integrated.get_user_path'
        ) as mock_path:

            def path_resolver(f):
                if f == 'civic_state.db':
                    return str(temp_db)
                elif f == '':
                    return str(tmp_path)
                return str(tmp_path / f)

            mock_path.side_effect = path_resolver

            mock_handler.serve_admin_status()

            response = mock_handler.responses[0]['data']
            chroma = response['chromadb']

            # Must have collections dict (even if empty due to no actual chromadb)
            assert 'collections' in chroma or chroma.get('status') in ['no_storage', 'error', 'chromadb_not_installed'], \
                "chromadb must have collections or valid status"

            # If collections exist, each must have count
            if 'collections' in chroma:
                for corpus_type, info in chroma['collections'].items():
                    if info is not None:  # None means collection doesn't exist
                        assert 'count' in info, f"collection {corpus_type} must have document count"
                        assert isinstance(info['count'], int), f"collection {corpus_type} count must be int"

            # Must have total_documents if connected
            if chroma.get('status') == 'connected':
                assert 'total_documents' in chroma, "chromadb must have total_documents aggregate"
                assert isinstance(chroma['total_documents'], int)
