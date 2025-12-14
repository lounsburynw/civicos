#!/usr/bin/env python3
"""
Civic Coordination WebSocket Server
Provides real-time messaging for coordination threads.

Architecture: Standalone Socket.io server (port 8002) alongside REST API (port 8001)
- Both servers share SQLite database (data/civic_participation.db)
- REST API handles CRUD operations
- WebSocket server handles real-time message delivery

Usage:
    python src/civic_socketio_server.py
"""

import socketio
import eventlet
import os
import logging
from typing import Dict, Optional
from collections import defaultdict
from time import time

# Import storage layer
try:
    from issue_storage import CommunityStorage
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from issue_storage import CommunityStorage

# Session 246: Use structured logging from logging_config
try:
    from logging_config import (
        configure_logging, get_logger, with_correlation_id,
        set_correlation_id, log_error
    )
    configure_logging()
    logger = get_logger('civic_socketio')
except ImportError:
    # Fallback if logging_config not available
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger('civic_socketio')

# Create Socket.IO server with CORS support
sio = socketio.Server(
    cors_allowed_origins='*',  # In production, restrict to specific origins
    async_mode='eventlet',
    logger=True,
    engineio_logger=False
)

# Storage instance
storage = CommunityStorage()

# Rate limiting: 10 messages per 60 seconds per user
MESSAGE_RATE_LIMIT = 10
MESSAGE_RATE_WINDOW = 60
message_rate_limiter = defaultdict(list)

# User session tracking (sid -> user_id mapping)
user_sessions: Dict[str, str] = {}

# Thread membership tracking (sid -> thread_id mapping)
thread_sessions: Dict[str, str] = {}


def check_message_rate_limit(user_id: str) -> bool:
    """
    Check if user has exceeded message rate limit.

    Returns:
        True if allowed, False if rate limited
    """
    now = time()
    window_start = now - MESSAGE_RATE_WINDOW

    # Remove old timestamps
    message_rate_limiter[user_id] = [
        t for t in message_rate_limiter[user_id] if t > window_start
    ]

    if len(message_rate_limiter[user_id]) >= MESSAGE_RATE_LIMIT:
        return False

    message_rate_limiter[user_id].append(now)
    return True


def verify_user_in_thread(user_id: str, thread_id: str) -> bool:
    """
    Verify user is following the focal point for this thread.

    Returns:
        True if user is a participant, False otherwise
    """
    participants = storage.get_thread_participants(thread_id)
    return any(p['user_id'] == user_id for p in participants)


@sio.event
def connect(sid, environ, auth):
    """
    Handle client connection.

    Authenticate via auth token passed during connection.
    """
    logger.info("ws_connect_attempt", extra={"sid": sid})

    # Extract user_id from auth dict
    if not auth or 'user_id' not in auth:
        logger.warning("ws_connect_rejected", extra={"sid": sid, "reason": "missing_user_id"})
        raise ConnectionRefusedError('Authentication required: user_id missing')

    user_id = auth['user_id']

    # Validate user_id (basic check - enhance in production)
    if not user_id or not isinstance(user_id, str):
        logger.warning("ws_connect_rejected", extra={"sid": sid, "reason": "invalid_user_id"})
        raise ConnectionRefusedError('Authentication required: invalid user_id')

    # Store user session
    user_sessions[sid] = user_id

    logger.info("ws_connected", extra={"sid": sid, "user_id": user_id})

    # Send welcome message
    sio.emit('connected', {'message': 'Connected to Civic Coordination Server'}, room=sid)


@sio.event
def disconnect(sid):
    """Handle client disconnection."""
    user_id = user_sessions.get(sid, 'unknown')
    thread_id = thread_sessions.get(sid)

    # Leave thread room if joined
    if thread_id:
        sio.leave_room(sid, f"thread_{thread_id}")
        # Notify other participants
        sio.emit('user_left', {'user_id': user_id}, room=f"thread_{thread_id}", skip_sid=sid)
        del thread_sessions[sid]

    # Clean up session
    if sid in user_sessions:
        del user_sessions[sid]

    logger.info("ws_disconnected", extra={"sid": sid, "user_id": user_id, "thread_id": thread_id})


@sio.event
def join_thread(sid, data):
    """
    Join a coordination thread room.

    Args:
        data: {
            'thread_id': str
        }
    """
    user_id = user_sessions.get(sid)
    if not user_id:
        logger.warning("ws_join_thread_failed", extra={"sid": sid, "reason": "no_user_session"})
        return {'error': 'Not authenticated'}

    thread_id = data.get('thread_id')
    if not thread_id:
        logger.warning("ws_join_thread_failed", extra={"sid": sid, "reason": "missing_thread_id"})
        return {'error': 'thread_id required'}

    # Verify user is a participant in this thread
    if not verify_user_in_thread(user_id, thread_id):
        logger.warning("ws_join_thread_failed", extra={"sid": sid, "user_id": user_id, "thread_id": thread_id, "reason": "not_authorized"})
        return {'error': 'Not authorized to join this thread'}

    # Join Socket.IO room
    sio.enter_room(sid, f"thread_{thread_id}")
    thread_sessions[sid] = thread_id

    logger.info("ws_thread_joined", extra={"user_id": user_id, "thread_id": thread_id})

    # Notify other participants
    sio.emit('user_joined', {'user_id': user_id}, room=f"thread_{thread_id}", skip_sid=sid)

    return {'success': True, 'thread_id': thread_id}


@sio.event
def leave_thread(sid, data):
    """
    Leave a coordination thread room.

    Args:
        data: {
            'thread_id': str
        }
    """
    user_id = user_sessions.get(sid)
    if not user_id:
        return {'error': 'Not authenticated'}

    thread_id = data.get('thread_id')
    if not thread_id:
        return {'error': 'thread_id required'}

    # Leave Socket.IO room
    sio.leave_room(sid, f"thread_{thread_id}")

    if sid in thread_sessions:
        del thread_sessions[sid]

    logger.info("ws_thread_left", extra={"user_id": user_id, "thread_id": thread_id})

    # Notify other participants
    sio.emit('user_left', {'user_id': user_id}, room=f"thread_{thread_id}", skip_sid=sid)

    return {'success': True}


@sio.event
def new_message(sid, data):
    """
    Send a new message to a thread.

    Args:
        data: {
            'thread_id': str,
            'content': str,
            'parent_message_id': str (optional - for nested replies)
        }
    """
    user_id = user_sessions.get(sid)
    if not user_id:
        logger.warning("ws_new_message_failed", extra={"sid": sid, "reason": "no_user_session"})
        return {'error': 'Not authenticated'}

    thread_id = data.get('thread_id')
    content = data.get('content')
    parent_message_id = data.get('parent_message_id')  # Optional

    if not thread_id or not content:
        logger.warning("ws_new_message_failed", extra={"sid": sid, "reason": "missing_data"})
        return {'error': 'thread_id and content required'}

    # Rate limiting
    if not check_message_rate_limit(user_id):
        logger.warning("ws_new_message_rate_limited", extra={"user_id": user_id})
        return {'error': 'Rate limit exceeded. Please wait before sending more messages.'}

    # Verify user is a participant
    if not verify_user_in_thread(user_id, thread_id):
        logger.warning("ws_new_message_failed", extra={"user_id": user_id, "thread_id": thread_id, "reason": "not_authorized"})
        return {'error': 'Not authorized to send messages in this thread'}

    try:
        # Save message to database (with optional parent_message_id for nested replies)
        message = storage.create_message(thread_id, user_id, content, parent_message_id)

        logger.info("ws_message_created", extra={
            "user_id": user_id,
            "thread_id": thread_id,
            "content_length": len(content),
            "is_reply": parent_message_id is not None
        })

        # Broadcast to all participants in thread (including sender for confirmation)
        sio.emit('message', message, room=f"thread_{thread_id}")

        return {'success': True, 'message': message}

    except Exception as e:
        logger.error("ws_new_message_failed", extra={"user_id": user_id, "thread_id": thread_id, "error": str(e), "reason": "database_error"})
        return {'error': 'Failed to save message'}


@sio.event
def typing(sid, data):
    """
    Broadcast typing indicator.

    Args:
        data: {
            'thread_id': str
        }
    """
    user_id = user_sessions.get(sid)
    if not user_id:
        return

    thread_id = data.get('thread_id')
    if not thread_id:
        return

    # Broadcast to other participants only
    sio.emit('user_typing', {'user_id': user_id, 'thread_id': thread_id},
             room=f"thread_{thread_id}", skip_sid=sid)


@sio.event
def stop_typing(sid, data):
    """
    Broadcast stop typing indicator.

    Args:
        data: {
            'thread_id': str
        }
    """
    user_id = user_sessions.get(sid)
    if not user_id:
        return

    thread_id = data.get('thread_id')
    if not thread_id:
        return

    # Broadcast to other participants only
    sio.emit('user_stop_typing', {'user_id': user_id, 'thread_id': thread_id},
             room=f"thread_{thread_id}", skip_sid=sid)


# Health check endpoint for Fly.io monitoring
def health_check(environ, start_response):
    """Simple health check endpoint for load balancer."""
    if environ.get('PATH_INFO') == '/health':
        response_body = b'{"status": "healthy", "service": "civic-websocket"}'
        start_response('200 OK', [
            ('Content-Type', 'application/json'),
            ('Content-Length', str(len(response_body)))
        ])
        return [response_body]
    return None


# Create WSGI application with health check middleware
def app_with_health(environ, start_response):
    """WSGI app that handles health checks before Socket.IO."""
    health_response = health_check(environ, start_response)
    if health_response is not None:
        return health_response
    return socketio_app(environ, start_response)


socketio_app = socketio.WSGIApp(sio, static_files={
    '/': {'content_type': 'text/html', 'filename': 'index.html'}
})

app = app_with_health


def run_server(host='0.0.0.0', port=8002):
    """Start the Socket.IO server."""
    # Structured log for server startup (machine-readable)
    logger.info("ws_server_started", extra={
        "host": host,
        "port": port,
        "rate_limit_messages": MESSAGE_RATE_LIMIT,
        "rate_limit_window_seconds": MESSAGE_RATE_WINDOW
    })

    # Console output for operators
    print(f"Civic WebSocket Server running on ws://{host}:{port}")
    print(f"Press Ctrl+C to stop")

    try:
        eventlet.wsgi.server(eventlet.listen((host, port)), app, log_output=False)
    except KeyboardInterrupt:
        logger.info("ws_server_shutdown", extra={"reason": "keyboard_interrupt"})


if __name__ == '__main__':
    import sys

    # Parse command line arguments
    port = 8002
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            logger.error("ws_server_startup_failed", extra={"error": f"Invalid port: {sys.argv[1]}"})
            sys.exit(1)

    run_server(port=port)
