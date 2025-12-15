#!/usr/bin/env python3
"""
Rate limiting implementation for Civic API endpoints
Prevents abuse and ensures fair resource usage
"""

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Dict, Tuple, Optional
# Handle both direct execution and module execution
try:
    from .config import config
except ImportError:
    from config import config

class RateLimiter:
    """Token bucket rate limiter with sliding window"""
    
    def __init__(self):
        self.config = config.get_rate_limit_config()
        self.enabled = self.config['enabled']
        
        # Tracking structures per client (IP or API key)
        self.minute_requests: Dict[str, deque] = defaultdict(lambda: deque())
        self.hour_requests: Dict[str, deque] = defaultdict(lambda: deque())
        self.lock = Lock()
        
        # Burst tracking
        self.burst_tokens: Dict[str, int] = defaultdict(lambda: self.config['burst_size'])
        self.last_refill: Dict[str, float] = defaultdict(time.time)
    
    def _clean_old_requests(self, client_id: str, now: float):
        """Remove expired requests from tracking"""
        minute_ago = now - 60
        hour_ago = now - 3600
        
        # Clean minute window
        while self.minute_requests[client_id] and self.minute_requests[client_id][0] < minute_ago:
            self.minute_requests[client_id].popleft()
        
        # Clean hour window
        while self.hour_requests[client_id] and self.hour_requests[client_id][0] < hour_ago:
            self.hour_requests[client_id].popleft()
    
    def _refill_burst_tokens(self, client_id: str, now: float):
        """Refill burst tokens based on time elapsed"""
        time_since_refill = now - self.last_refill[client_id]
        if time_since_refill >= 1.0:  # Refill every second
            tokens_to_add = int(time_since_refill)
            self.burst_tokens[client_id] = min(
                self.config['burst_size'],
                self.burst_tokens[client_id] + tokens_to_add
            )
            self.last_refill[client_id] = now
    
    def check_rate_limit(self, client_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if request is allowed under rate limits
        Returns: (allowed, limit_info)
        """
        if not self.enabled:
            return True, None
        
        with self.lock:
            now = time.time()
            
            # Clean old requests
            self._clean_old_requests(client_id, now)
            
            # Refill burst tokens
            self._refill_burst_tokens(client_id, now)
            
            # Check limits
            minute_count = len(self.minute_requests[client_id])
            hour_count = len(self.hour_requests[client_id])
            
            # Check if limits exceeded
            if minute_count >= self.config['requests_per_minute']:
                retry_after = 60 - (now - self.minute_requests[client_id][0])
                return False, {
                    'limit': 'minute',
                    'retry_after': int(retry_after),
                    'limit_value': self.config['requests_per_minute']
                }
            
            if hour_count >= self.config['requests_per_hour']:
                retry_after = 3600 - (now - self.hour_requests[client_id][0])
                return False, {
                    'limit': 'hour',
                    'retry_after': int(retry_after),
                    'limit_value': self.config['requests_per_hour']
                }
            
            # Check burst limit
            if self.burst_tokens[client_id] <= 0:
                return False, {
                    'limit': 'burst',
                    'retry_after': 1,
                    'limit_value': self.config['burst_size']
                }
            
            # Request allowed - record it
            self.minute_requests[client_id].append(now)
            self.hour_requests[client_id].append(now)
            self.burst_tokens[client_id] -= 1
            
            # Return rate limit headers info
            return True, {
                'X-RateLimit-Limit-Minute': str(self.config['requests_per_minute']),
                'X-RateLimit-Remaining-Minute': str(self.config['requests_per_minute'] - minute_count - 1),
                'X-RateLimit-Limit-Hour': str(self.config['requests_per_hour']),
                'X-RateLimit-Remaining-Hour': str(self.config['requests_per_hour'] - hour_count - 1),
                'X-RateLimit-Burst-Remaining': str(self.burst_tokens[client_id])
            }
    
    def get_client_id(self, request_handler) -> str:
        """Extract client identifier from request"""
        # Try API key first
        auth_header = request_handler.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return f"key:{auth_header[7:]}"
        
        # Fall back to IP address
        # Handle X-Forwarded-For for proxied requests
        x_forwarded = request_handler.headers.get('X-Forwarded-For')
        if x_forwarded:
            # Take first IP in chain
            client_ip = x_forwarded.split(',')[0].strip()
        else:
            client_ip = request_handler.client_address[0]
        
        return f"ip:{client_ip}"

# Global rate limiter instance
rate_limiter = RateLimiter()