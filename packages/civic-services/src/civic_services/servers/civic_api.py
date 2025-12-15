#!/usr/bin/env python3
"""
Minimal API to serve schema-compliant civic events from civic_digest.py output.
No dependencies beyond standard library + what civic_digest.py already uses.
"""

import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from pathlib import Path
import sys

class CivicAPIHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler for civic data API"""
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/api/events':
            self.serve_opportunities()
        elif self.path == '/api/status':
            self.serve_status()
        else:
            self.send_error(404)
    
    def serve_opportunities(self):
        """Serve latest civic events in schema-compliant format"""
        try:
            # Find the most recent scraped data file
            output_dir = Path('data/scraped_data')
            if not output_dir.exists():
                self.send_json({'events': [], 'message': 'No data available yet'})
                return
            
            # Get most recent JSON file
            json_files = sorted(output_dir.glob('*.json'), key=os.path.getmtime, reverse=True)
            if not json_files:
                self.send_json({'events': [], 'message': 'No data available yet'})
                return
            
            # Load and transform to schema-compliant format
            with open(json_files[0], 'r') as f:
                raw_data = json.load(f)
            
            # Transform to match civic-app-schema.json structure
            events = []
            for item in raw_data.get('events', []):
                opportunity = {
                    'opportunity_id': f"opp_{hash(item.get('title', ''))}"[:12],
                    'title': item.get('title', 'Untitled'),
                    'description': item.get('description', ''),
                    'meeting_date': item.get('when', ''),
                    'location': {
                        'city': 'San Rafael',  # TODO: Extract from source
                        'state': 'CA',
                        'venue': item.get('where', 'City Hall')
                    },
                    'participation_methods': self.extract_participation_methods(item),
                    'impact_summary': item.get('impact_summary', ''),
                    'source_url': raw_data.get('source_url', ''),
                    'created_at': datetime.now().isoformat(),
                    'deadline': item.get('deadline', None),
                    'category': self.categorize_opportunity(item),
                    'tags': self.extract_tags(item)
                }
                events.append(opportunity)
            
            response = {
                'events': events,
                'metadata': {
                    'count': len(events),
                    'last_updated': datetime.fromtimestamp(os.path.getmtime(json_files[0])).isoformat(),
                    'source_file': json_files[0].name
                }
            }
            
            self.send_json(response)
            
        except Exception as e:
            self.send_error(500, f"Server error: {str(e)}")
    
    def serve_status(self):
        """Serve API status"""
        self.send_json({
            'status': 'operational',
            'version': '0.1.0',
            'endpoints': ['/api/events', '/api/status']
        })
    
    def send_json(self, data):
        """Send JSON response with CORS headers"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())
    
    def extract_participation_methods(self, item):
        """Extract participation methods from opportunity data"""
        methods = []
        how = item.get('how', '')
        
        if 'email' in how.lower() or '@' in how:
            methods.append('email_comment')
        if 'online' in how.lower() or 'zoom' in how.lower():
            methods.append('virtual_attendance')
        if 'attend' in how.lower() or 'person' in how.lower():
            methods.append('in_person_attendance')
        if 'comment' in how.lower():
            methods.append('public_comment')
        
        return methods if methods else ['public_comment']
    
    def categorize_opportunity(self, item):
        """Categorize opportunity based on content"""
        title = item.get('title', '').lower()
        desc = item.get('description', '').lower()
        combined = title + ' ' + desc
        
        if any(word in combined for word in ['housing', 'zoning', 'development', 'building']):
            return 'housing'
        elif any(word in combined for word in ['traffic', 'transportation', 'parking', 'street']):
            return 'transportation'
        elif any(word in combined for word in ['budget', 'finance', 'tax', 'fee']):
            return 'budget'
        elif any(word in combined for word in ['environment', 'climate', 'sustainability', 'green']):
            return 'environment'
        elif any(word in combined for word in ['safety', 'police', 'fire', 'emergency']):
            return 'public_safety'
        else:
            return 'general'
    
    def extract_tags(self, item):
        """Extract relevant tags from opportunity"""
        tags = []
        title = item.get('title', '').lower()
        
        # Add common civic tags
        if 'hearing' in title:
            tags.append('public_hearing')
        if 'comment' in title:
            tags.append('public_comment')
        if 'budget' in title:
            tags.append('budget')
        if 'plan' in title:
            tags.append('planning')
        
        return tags
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass

def run_server(port=8080):
    """Run the API server"""
    server = HTTPServer(('localhost', port), CivicAPIHandler)
    print(f"Civic API running on http://localhost:{port}")
    print(f"Endpoints:")
    print(f"  - http://localhost:{port}/api/events")
    print(f"  - http://localhost:{port}/api/status")
    print(f"\nPress Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()

def refresh_civic_data():
    """Safely refresh civic data by calling civic_digest functions directly"""
    try:
        # Import civic_digest module instead of using subprocess
        import civic_digest
        
        print("Refreshing civic data...")
        
        # Create digest instance (same as civic_digest.py does)
        digest = civic_digest.CivicDigest()
        
        # Use known working URL (same as test command)
        test_url = "https://www.cityofsanrafael.org/meetings/planning-commission-may-27-2025/"
        
        # Run the scraping (without sending email)
        events = digest.scrape_meeting(test_url)
        
        print(f"✅ Data refresh complete! Found {len(events)} events")
        return True
        
    except Exception as e:
        print(f"❌ Failed to refresh civic data: {e}")
        return False

if __name__ == '__main__':
    # Optional: Run civic data refresh first to ensure fresh data
    if len(sys.argv) > 1 and sys.argv[1] == '--refresh':
        refresh_civic_data()
    
    run_server()