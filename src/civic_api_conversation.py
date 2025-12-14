#!/usr/bin/env python3
"""
Civic API with Conversation Service Integration
Extends existing civic_api_integrated.py with MCP-powered conversation endpoints
"""

import json
import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from flask import Flask, jsonify, request
from flask_cors import CORS
from functools import wraps
import uuid

# Handle both direct execution and module execution
try:
    from .utils.conversation_service import conversation_service
    from .civic_schema_adapter import CivicSchemaAdapter
except ImportError:
    import sys
    from pathlib import Path
    src_path = str(Path(__file__).parent)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    from utils.conversation_service import conversation_service
    from civic_schema_adapter import CivicSchemaAdapter

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins=['http://localhost:*', 'file://*'])

# Authentication configuration
API_KEYS = {
    'web': os.getenv('CIVIC_WEB_KEY', 'test-web-key-2024'),
    'demo': os.getenv('CIVIC_DEMO_KEY', 'demo-key-2024')
}

# Schema adapter for civic data
schema_adapter = CivicSchemaAdapter()

# In-memory storage for conversation contexts (production: use Redis/database)
conversation_contexts = {}
user_profiles = {}

def require_auth(f):
    """Decorator to require Bearer token authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'error': 'No authorization header'}), 401
        
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Invalid authorization format'}), 401
        
        token = auth_header.replace('Bearer ', '')
        
        if token not in API_KEYS.values():
            return jsonify({'error': 'Invalid API key'}), 401
        
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'civic-conversation-api',
        'mcp_enabled': conversation_service.enable_mcp,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/conversation', methods=['POST'])
@require_auth
def handle_conversation():
    """
    Main conversation endpoint - handles user messages and returns MCP-powered responses
    
    Request body:
    {
        "message": "user message text",
        "user_id": "user-uuid",
        "conversation_id": "conversation-uuid" (optional)
    }
    
    Response:
    {
        "message": { Message entity from schema },
        "actions": [ MessageAction entities ],
        "conversation_id": "conversation-uuid"
    }
    """
    try:
        data = request.json
        
        if not data or 'message' not in data:
            return jsonify({'error': 'Message required'}), 400
        
        user_message = data['message']
        user_id = data.get('user_id', str(uuid.uuid4()))
        conversation_id = data.get('conversation_id', str(uuid.uuid4()))
        
        # Get or create user profile
        if user_id not in user_profiles:
            user_profiles[user_id] = {
                "id": user_id,
                "email": data.get('email', f"user_{user_id[:8]}@example.com"),
                "experience_level": "new",
                "location": {
                    "city": data.get('city', 'San Rafael'),
                    "state": data.get('state', 'California'),
                    "county": data.get('county', 'Marin County')
                },
                "civic_profile": {
                    "interests": data.get('interests', []),
                    "participation_history": [],
                    "impact_score": 0,
                    "neighbors_connected": 0,
                    "visits": 1,
                    "interactions": 0
                },
                "created_at": datetime.now().isoformat(),
                "last_active": datetime.now().isoformat()
            }
        
        user_profile = user_profiles[user_id]
        
        # Get or create conversation context
        conversation_context = conversation_contexts.get(conversation_id)
        
        # Handle conversation through MCP service
        response = conversation_service.handle_conversation(
            user_message=user_message,
            user_profile=user_profile,
            conversation_context=conversation_context
        )
        
        # Store updated conversation context
        conversation_contexts[conversation_id] = response.get('conversation_context', {})
        
        # Store updated user profile
        user_profiles[user_id] = user_profile
        
        return jsonify({
            'message': response['message'],
            'actions': response.get('actions', []),
            'conversation_id': conversation_id,
            'user_experience': user_profile.get('experience_level', 'new')
        })
        
    except Exception as e:
        logger.error(f"Conversation error: {e}")
        return jsonify({
            'error': 'Failed to process conversation',
            'details': str(e)
        }), 500

@app.route('/api/mcp-tools', methods=['GET'])
@require_auth
def get_mcp_tools():
    """Get available MCP tools and their capabilities"""
    return jsonify({
        'tools': [
            {
                'name': 'compose_public_comment',
                'description': 'Generate AI-powered public comments for civic agenda items',
                'parameters': {
                    'item_id': 'string',
                    'item_title': 'string',
                    'resident_stance': 'optional<support|oppose|neutral|question>',
                    'key_points': 'optional<string>'
                }
            },
            {
                'name': 'get_comment_guidelines',
                'description': 'Get submission guidelines for public comments',
                'parameters': {
                    'jurisdiction': 'string (default: san-rafael)'
                }
            }
        ],
        'enabled': conversation_service.enable_mcp
    })

@app.route('/api/civic-events', methods=['GET'])
@require_auth
def get_civic_opportunities():
    """Get civic events (existing endpoint from civic_api_integrated.py)"""
    try:
        # Load schema data
        schema_dir = Path(__file__).parent / "output" / "schema"
        events = []
        
        if schema_dir.exists():
            for schema_file in schema_dir.glob("*.json"):
                with open(schema_file, 'r') as f:
                    data = json.load(f)
                    if "civic_opportunities" in data:
                        events.extend(data["civic_opportunities"])
        
        return jsonify({
            'events': events,
            'count': len(events),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Error loading events: {e}")
        return jsonify({'error': 'Failed to load events'}), 500

@app.route('/api/user-profile', methods=['GET', 'PUT'])
@require_auth
def manage_user_profile():
    """Get or update user profile"""
    user_id = request.args.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    if request.method == 'GET':
        profile = user_profiles.get(user_id)
        if not profile:
            return jsonify({'error': 'User not found'}), 404
        return jsonify(profile)
    
    elif request.method == 'PUT':
        data = request.json
        if user_id not in user_profiles:
            user_profiles[user_id] = {
                "id": user_id,
                "created_at": datetime.now().isoformat()
            }
        
        # Update profile fields
        profile = user_profiles[user_id]
        for key in ['email', 'experience_level', 'location', 'civic_profile']:
            if key in data:
                profile[key] = data[key]
        
        profile['last_active'] = datetime.now().isoformat()
        user_profiles[user_id] = profile
        
        return jsonify(profile)

@app.route('/api/conversation-context', methods=['GET'])
@require_auth
def get_conversation_context():
    """Get conversation context for debugging/monitoring"""
    conversation_id = request.args.get('conversation_id')
    
    if not conversation_id:
        return jsonify({'error': 'conversation_id required'}), 400
    
    context = conversation_contexts.get(conversation_id)
    if not context:
        return jsonify({'error': 'Conversation not found'}), 404
    
    return jsonify(context)

# Error handlers
@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {e}")
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    
    # Log startup information
    logger.info(f"Starting Civic Conversation API on port {port}")
    logger.info(f"MCP enabled: {conversation_service.enable_mcp}")
    logger.info(f"Loaded {len(conversation_service.civic_opportunities)} civic events")
    
    # Run server
    app.run(host='0.0.0.0', port=port, debug=True)