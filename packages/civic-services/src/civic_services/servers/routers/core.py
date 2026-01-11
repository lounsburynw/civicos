"""
Core API handlers: health, status, jurisdictions, config.

Mixin class containing handlers for core/utility endpoints.
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from http.server import BaseHTTPRequestHandler


class CoreMixin:
    """
    Mixin providing core utility endpoint handlers.

    Endpoints:
    - GET /api/status, /health - Health check
    - GET /api/jurisdictions - List jurisdictions
    - GET /api/config/google-maps-key - Frontend config
    - GET /help - API documentation
    """

    def serve_status(self):
        """Serve API status and health check with comprehensive system checks"""
        checks = {}
        overall_healthy = True

        # 1. Database connectivity check
        db_check = self._check_database_health()
        checks['database'] = db_check
        if db_check['status'] != 'healthy':
            overall_healthy = False

        # 2. ChromaDB availability check
        chromadb_check = self._check_chromadb_health()
        checks['chromadb'] = chromadb_check
        if chromadb_check['status'] != 'healthy':
            overall_healthy = False

        # 3. External services check (non-blocking, degraded ok)
        services_check = self._check_external_services()
        checks['services'] = services_check
        # External services being unavailable = degraded, not unhealthy

        # 4. Data availability check
        schema_dir = Path('data/events')
        schema_files = list(schema_dir.glob('newsletter_*.json')) if schema_dir.exists() else []
        # Path adjusted for routers/ subdirectory
        servers_dir = Path(__file__).parent.parent
        digest_available = (servers_dir / 'civic_digest.py').exists()

        checks['data'] = {
            'status': 'healthy' if schema_files else 'degraded',
            'schema_files_available': len(schema_files),
            'latest_data': schema_files[-1].name if schema_files else None,
            'last_updated': datetime.fromtimestamp(schema_files[-1].stat().st_mtime).isoformat() if schema_files else None,
            'civic_digest_available': digest_available,
            'pipeline_ready': digest_available and len(schema_files) > 0
        }

        # 5. Error rate check (Session 294)
        error_metrics_check = self._check_error_rate()
        checks['error_rate'] = error_metrics_check
        # Elevated error rate = degraded status
        if error_metrics_check.get('status') == 'critical':
            overall_healthy = False

        # 6. Request metrics check (Session 296)
        request_metrics_check = self._check_request_metrics()
        checks['request_metrics'] = request_metrics_check

        # 7. Active users check (Session 297)
        active_users_check = self._check_active_users()
        checks['active_users'] = active_users_check

        # Determine overall status
        if not overall_healthy:
            overall_status = 'unhealthy'
        elif (services_check.get('legistar') == 'unavailable' or
              checks['data']['status'] == 'degraded' or
              error_metrics_check.get('status') == 'elevated'):
            overall_status = 'degraded'
        else:
            overall_status = 'healthy'

        # Import config for environment check
        from ...core.config import config

        status = {
            'status': overall_status,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'version': '0.4.0',
            'checks': checks
        }

        # Add extended info for /api/status endpoint
        if self.path == '/api/status':
            status['endpoints'] = {
                'public': ['/api/status', '/health'],
                'authenticated': [
                    '/api/events (GET - list all)',
                    '/api/events/{id} (GET - single opportunity)',
                    '/api/jurisdictions (GET - list all jurisdictions with counts)',
                    '/api/issues?user_id={user} (GET - user issues)',
                    '/api/refresh (GET - refresh data)',
                    '/api/conversation (POST - AI conversation)',
                    '/api/legistar/{city}/events (GET - Legistar API events)',
                    'Available cities: oakland, santa-rosa, sonoma-county'
                ]
            }
            status['authentication'] = 'Bearer token required for protected endpoints'

        # Add sample API key for testing (development only)
        if self.path == '/health' and config.env == 'development':
            status['test_credentials'] = {
                'sample_header': 'Authorization: Bearer <your_api_key>',
                'note': 'See INTEGRATION_GUIDE.md for API key setup'
            }

        self.send_json(status)

    def serve_jurisdictions(self):
        """
        Aggregate jurisdictions from event data with counts and metadata.

        Response format:
        [
          {
            "id": "city-berkeley",
            "name": "Berkeley",
            "type": "city",
            "event_count": 35,
            "issue_count": 12,
            "cdbg_allocation": "$2.67M"
          }
        ]
        """
        try:
            # Import automated_civic_refresh to access CITY_CONFIGS
            try:
                from civic_services.monitoring.automated_civic_refresh import CITY_CONFIGS
            except ImportError:
                import sys
                sys.path.insert(0, str(Path(__file__).parent))
                from civic_services.monitoring.automated_civic_refresh import CITY_CONFIGS

            # Import issue storage for issue counts
            try:
                from civic_services.storage.issue_storage import IssueStorage
                storage = IssueStorage()
                complaint_storage_available = True
            except Exception as e:
                print(f"[civic_api] Warning: Could not load issue storage: {e}")
                complaint_storage_available = False

            # 1. List all event files
            schema_dir = Path('data/events')
            if not schema_dir.exists():
                self.send_json({'jurisdictions': [], 'message': 'No event data available'})
                return

            event_files = list(schema_dir.glob('events_*.json'))

            # 2. Extract jurisdiction_id from filenames and count events
            jurisdiction_counts: Dict[str, int] = {}
            for file_path in event_files:
                # Pattern: events_{jurisdiction_id}_{date}_{time}.json
                match = re.match(r'events_([a-z0-9\-]+)_\d{8}_\d{6}\.json', file_path.name)
                if match:
                    jurisdiction_id = match.group(1)

                    # Count events in this file
                    try:
                        with open(file_path, 'r') as f:
                            data = json.load(f)
                            event_count = len(data.get('events', []))

                            # Keep track of highest count for each jurisdiction
                            if jurisdiction_id not in jurisdiction_counts:
                                jurisdiction_counts[jurisdiction_id] = event_count
                            else:
                                # Use max count across multiple files
                                jurisdiction_counts[jurisdiction_id] = max(
                                    jurisdiction_counts[jurisdiction_id],
                                    event_count
                                )
                    except Exception as e:
                        print(f"[civic_api] Warning: Could not parse {file_path.name}: {e}")

            # 3. Build jurisdiction list with metadata
            jurisdictions = []
            for jurisdiction_id, event_count in jurisdiction_counts.items():
                # Get jurisdiction metadata from CITY_CONFIGS
                city_config = CITY_CONFIGS.get(jurisdiction_id, {})

                # Get issue count if available
                issue_count = 0
                if complaint_storage_available:
                    try:
                        issues = storage.get_issues_for_user(None)  # All issues
                        issue_count = len([i for i in issues if i.get('jurisdiction_id') == jurisdiction_id])
                    except Exception:
                        pass

                # Parse jurisdiction name from ID
                name = jurisdiction_id.replace('city-', '').replace('-', ' ').title()
                jtype = 'city' if jurisdiction_id.startswith('city-') else 'county'

                jurisdictions.append({
                    'id': jurisdiction_id,
                    'name': name,
                    'type': jtype,
                    'event_count': event_count,
                    'issue_count': issue_count,
                    'cdbg_allocation': city_config.get('cdbg_allocation', 'N/A'),
                    'population': city_config.get('population'),
                    'timezone': city_config.get('timezone', 'America/Los_Angeles')
                })

            # Sort by event count descending
            jurisdictions.sort(key=lambda x: x['event_count'], reverse=True)

            self.send_json({
                'jurisdictions': jurisdictions,
                'total': len(jurisdictions)
            })

        except Exception as e:
            print(f"[civic_api] ERROR serving jurisdictions: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")

    def serve_google_maps_key(self):
        """
        Handle GET /api/config/google-maps-key

        Returns Google Maps API key for frontend Places Autocomplete.
        This is a public endpoint - API key should be restricted by HTTP referrer in Google Cloud Console.

        Response format:
        {
          "api_key": "AIza..."
        }
        """
        try:
            api_key = os.getenv('GOOGLE_MAPS_API_KEY')
            if not api_key:
                self.send_json({'error': 'Google Maps API key not configured'}, 500)
                return

            self.send_json({'api_key': api_key})

        except Exception as e:
            print(f"[civic_api] ERROR serving Google Maps API key: {str(e)}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f"Server error: {str(e)}")
