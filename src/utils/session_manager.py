#!/usr/bin/env python3
"""
Session management for Civic platform
Handles conversation storage, memory cleanup, and session lifecycle
"""

import json
import time
import threading
from typing import Dict, List, Optional, Any
from collections import deque
from pathlib import Path
# Handle both direct execution and module execution
try:
    from ..config import config
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import config

class ConversationSession:
    """Individual conversation session with memory management"""
    
    def __init__(self, session_id: str, user_id: Optional[str] = None):
        self.session_id = session_id
        self.user_id = user_id
        self.created_at = time.time()
        self.last_activity = time.time()
        self.messages: deque = deque(maxlen=100)  # Limit message history
        self.metadata = {}
        self._size_bytes = 0
        self._lock = threading.RLock()
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None):
        """Add message to conversation with size tracking"""
        with self._lock:
            message = {
                'role': role,
                'content': content,
                'timestamp': time.time(),
                'metadata': metadata or {}
            }
            
            # Check size limit
            message_size = len(json.dumps(message, ensure_ascii=False).encode())
            max_size = config.get_session_config()['max_conversation_size_kb'] * 1024
            
            if self._size_bytes + message_size > max_size:
                # Remove oldest messages to make space
                while self.messages and self._size_bytes + message_size > max_size:
                    old_message = self.messages.popleft()
                    old_size = len(json.dumps(old_message, ensure_ascii=False).encode())
                    self._size_bytes -= old_size
            
            self.messages.append(message)
            self._size_bytes += message_size
            self.last_activity = time.time()
    
    def get_recent_messages(self, limit: int = 10) -> List[Dict]:
        """Get recent messages up to limit"""
        with self._lock:
            messages = list(self.messages)
            return messages[-limit:] if limit > 0 else messages
    
    def is_expired(self) -> bool:
        """Check if session has expired"""
        timeout_minutes = config.get_session_config()['session_timeout_minutes']
        return (time.time() - self.last_activity) > (timeout_minutes * 60)
    
    def get_size_bytes(self) -> int:
        """Get current conversation size in bytes"""
        return self._size_bytes
    
    def clear_old_messages(self, keep_recent: int = 10):
        """Clear old messages, keeping only recent ones"""
        with self._lock:
            if len(self.messages) > keep_recent:
                # Keep only recent messages
                recent_messages = list(self.messages)[-keep_recent:]
                self.messages.clear()
                
                # Recalculate size
                self._size_bytes = 0
                for msg in recent_messages:
                    self.messages.append(msg)
                    self._size_bytes += len(json.dumps(msg, ensure_ascii=False).encode())

class SessionManager:
    """Global session manager with automatic cleanup"""
    
    def __init__(self):
        self.sessions: Dict[str, ConversationSession] = {}
        self._lock = threading.RLock()
        self._cleanup_thread = None
        self._stop_cleanup = threading.Event()
        self.config = config.get_session_config()
        
        # Start cleanup thread
        self.start_cleanup_thread()
    
    def start_cleanup_thread(self):
        """Start background cleanup thread"""
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
            self._cleanup_thread.start()
    
    def stop_cleanup_thread(self):
        """Stop background cleanup thread"""
        self._stop_cleanup.set()
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=1)
    
    def _cleanup_loop(self):
        """Background cleanup loop"""
        while not self._stop_cleanup.is_set():
            try:
                self.cleanup_expired_sessions()
                time.sleep(self.config['cleanup_interval_minutes'] * 60)
            except Exception as e:
                # Log error but continue cleanup loop
                print(f"Session cleanup error: {e}")
                time.sleep(60)  # Wait 1 minute before retry
    
    def get_or_create_session(self, session_id: str, user_id: Optional[str] = None) -> ConversationSession:
        """Get existing session or create new one"""
        with self._lock:
            if session_id not in self.sessions:
                # Check if we're at max sessions limit
                if len(self.sessions) >= self.config['max_sessions']:
                    self._cleanup_oldest_sessions()
                
                self.sessions[session_id] = ConversationSession(session_id, user_id)
            
            return self.sessions[session_id]
    
    def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get existing session if it exists"""
        with self._lock:
            return self.sessions.get(session_id)
    
    def remove_session(self, session_id: str) -> bool:
        """Remove a specific session"""
        with self._lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                return True
            return False
    
    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions and return count removed"""
        removed_count = 0
        
        with self._lock:
            expired_sessions = [
                session_id for session_id, session in self.sessions.items()
                if session.is_expired()
            ]
            
            for session_id in expired_sessions:
                del self.sessions[session_id]
                removed_count += 1
        
        return removed_count
    
    def _cleanup_oldest_sessions(self, keep_count: Optional[int] = None):
        """Remove oldest sessions to stay under limit"""
        if keep_count is None:
            keep_count = self.config['max_sessions'] - 10  # Remove 10 oldest
        
        if len(self.sessions) <= keep_count:
            return
        
        # Sort by last activity (oldest first)
        sorted_sessions = sorted(
            self.sessions.items(),
            key=lambda x: x[1].last_activity
        )
        
        # Remove oldest sessions
        sessions_to_remove = sorted_sessions[:len(self.sessions) - keep_count]
        for session_id, _ in sessions_to_remove:
            del self.sessions[session_id]
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        with self._lock:
            total_sessions = len(self.sessions)
            total_messages = sum(len(session.messages) for session in self.sessions.values())
            total_size_mb = sum(session.get_size_bytes() for session in self.sessions.values()) / (1024 * 1024)
            
            active_sessions = sum(
                1 for session in self.sessions.values()
                if (time.time() - session.last_activity) < 300  # Active in last 5 minutes
            )
            
            return {
                'total_sessions': total_sessions,
                'active_sessions': active_sessions,
                'total_messages': total_messages,
                'total_size_mb': round(total_size_mb, 2),
                'max_sessions': self.config['max_sessions']
            }
    
    def compact_all_sessions(self, keep_recent: int = 10):
        """Compact all sessions by keeping only recent messages"""
        with self._lock:
            for session in self.sessions.values():
                session.clear_old_messages(keep_recent)

# Global session manager instance
session_manager = SessionManager()