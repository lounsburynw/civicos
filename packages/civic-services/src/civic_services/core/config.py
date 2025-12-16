#!/usr/bin/env python3
"""
Centralized configuration management for Civic platform
Handles API keys, environment detection, and security settings
"""

import os
from typing import Dict, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in project root
# override=True ensures .env takes precedence over shell env vars (fixes stale key caching)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

class CivicConfig:
    """Configuration manager for Civic platform"""
    
    def __init__(self):
        self.env = self._detect_environment()
        self.debug = self.env == 'development' and os.getenv('DEBUG', 'false').lower() == 'true'
        
    def _detect_environment(self) -> str:
        """Detect current environment"""
        env = os.getenv('CIVIC_ENV', 'development').lower()
        if env not in ['development', 'staging', 'production']:
            return 'development'
        return env
    
    def get_api_keys(self) -> Dict[str, str]:
        """Get API keys from environment variables"""
        # Never hardcode keys - always use environment variables
        keys = {}
        
        # Production keys
        if os.getenv('CIVIC_WEB_KEY'):
            keys[os.getenv('CIVIC_WEB_KEY')] = 'web_interface'
        
        if os.getenv('CIVIC_DEMO_KEY'):
            keys[os.getenv('CIVIC_DEMO_KEY')] = 'demo_user'
        
        if os.getenv('CIVIC_TEST_KEY'):
            keys[os.getenv('CIVIC_TEST_KEY')] = 'test_user'
        
        # No fallback keys - all environments must use proper API keys from environment variables
        
        # Production/staging MUST have API keys configured
        if self.env in ['production', 'staging'] and not keys:
            raise RuntimeError(f"No API keys configured for {self.env} environment. Set CIVIC_WEB_KEY environment variable.")
            
        return keys
    
    def get_bundled_data_dir(self) -> Path:
        """Get bundled data directory path (read-only reference data)

        Contains: events, vectors, legislative context
        Updated on each deploy (baked into Docker image)

        In production: /app/bundled-data
        In development: data/
        """
        data_dir = os.getenv('CIVIC_BUNDLED_DATA_DIR')
        if data_dir:
            return Path(data_dir)

        if self.env == 'production':
            return Path('/app/bundled-data')
        else:
            return Path('data')

    def get_user_data_dir(self) -> Path:
        """Get user data directory path (persistent user data)

        Contains: participation database, sessions, user preferences
        Never overwritten by deploys (Fly.io persistent volume)

        In production: /app/user-data
        In development: data/
        """
        data_dir = os.getenv('CIVIC_USER_DATA_DIR')
        if data_dir:
            return Path(data_dir)

        if self.env == 'production':
            return Path('/app/user-data')
        else:
            # Development: same as bundled for simplicity
            return Path('data')

    def get_data_dir(self) -> Path:
        """Get data directory path (legacy compatibility)

        DEPRECATED: Use get_bundled_data_dir() or get_user_data_dir() instead.
        This method returns bundled data dir for backwards compatibility.
        """
        return self.get_bundled_data_dir()

    def get_api_port(self) -> int:
        """Get API server port from environment or default"""
        port = os.getenv('CIVIC_API_PORT')
        if port:
            try:
                return int(port)
            except ValueError:
                print(f"⚠️  Invalid CIVIC_API_PORT '{port}', using default")
        
        # Default ports by environment
        defaults = {
            'development': 8001,
            'staging': 8002,
            'production': 8000
        }
        return defaults.get(self.env, 8001)
    
    def get_api_endpoint(self) -> str:
        """Get API endpoint based on environment"""
        # For local development, use port-based endpoints
        if self.env == 'development':
            port = self.get_api_port()
            return f'http://localhost:{port}'
        
        # For staging/production, use environment-defined URLs
        endpoints = {
            'staging': os.getenv('CIVIC_API_STAGING', 'https://staging.civic.example.com'),
            'production': os.getenv('CIVIC_API_PROD', 'https://api.civic.example.com')
        }
        return endpoints.get(self.env, f'http://localhost:{self.get_api_port()}')
    
    def get_cors_origins(self) -> list:
        """Get allowed CORS origins based on environment"""
        if self.env == 'development':
            return ['*']  # Allow all in development
        
        # Production: whitelist specific origins
        origins = os.getenv('CIVIC_CORS_ORIGINS', '').split(',')
        origins = [o.strip() for o in origins if o.strip()]
        
        # Always allow localhost in non-production
        if self.env != 'production':
            origins.extend(['http://localhost:*', 'http://127.0.0.1:*'])
            
        return origins if origins else ['https://civic.example.com']
    
    def get_rate_limit_config(self) -> dict:
        """Get rate limiting configuration"""
        return {
            'enabled': self.env != 'development' or os.getenv('ENABLE_RATE_LIMIT', 'false').lower() == 'true',
            'requests_per_minute': int(os.getenv('RATE_LIMIT_PER_MINUTE', '60')),
            'requests_per_hour': int(os.getenv('RATE_LIMIT_PER_HOUR', '1000')),
            'burst_size': int(os.getenv('RATE_LIMIT_BURST', '10'))
        }
    
    def is_debug(self) -> bool:
        """Check if debug mode is enabled"""
        return self.debug
    
    def get_session_config(self) -> dict:
        """Get session management configuration"""
        return {
            'max_sessions': int(os.getenv('MAX_SESSIONS', '1000')),
            'session_timeout_minutes': int(os.getenv('SESSION_TIMEOUT', '60')),
            'cleanup_interval_minutes': int(os.getenv('SESSION_CLEANUP_INTERVAL', '15')),
            'max_conversation_size_kb': int(os.getenv('MAX_CONVERSATION_SIZE_KB', '100'))
        }
    
    def get_openai_config(self) -> dict:
        """Get OpenAI API configuration"""
        return {
            'api_key': os.getenv('OPENAI_API_KEY'),
            'model': os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),  # Default to gpt-4o-mini for conversational responses
            'temperature': float(os.getenv('OPENAI_TEMPERATURE', '0.7')),
            'max_completion_tokens': int(os.getenv('OPENAI_MAX_TOKENS', '2000')),  # Increased for draft comments
            'timeout': int(os.getenv('OPENAI_TIMEOUT', '30')),  # Increased timeout for longer responses
            'fallback_model': os.getenv('OPENAI_FALLBACK_MODEL', 'gpt-3.5-turbo')
        }
    
    def validate_environment(self) -> None:
        """Validate required environment variables are set for current environment"""
        errors = []
        
        # Always required
        if not os.getenv('OPENAI_API_KEY') and self.env != 'development':
            errors.append("OPENAI_API_KEY is required for AI conversation functionality")
        
        # Production/staging requirements  
        if self.env in ['production', 'staging']:
            if not os.getenv('CIVIC_WEB_KEY'):
                errors.append("CIVIC_WEB_KEY is required for authentication")
            
            if not os.getenv('CIVIC_CORS_ORIGINS'):
                errors.append("CIVIC_CORS_ORIGINS must be set to whitelist allowed domains")
        
        # Development setup warning
        if self.env == 'development' and not any([
            os.getenv('CIVIC_WEB_KEY'),
            os.getenv('CIVIC_DEMO_KEY'), 
            os.getenv('CIVIC_DEV_MODE')
        ]):
            errors.append("Development environment needs CIVIC_WEB_KEY, CIVIC_DEMO_KEY, or CIVIC_DEV_MODE=true")
        
        if errors:
            error_msg = f"\n❌ Environment validation failed for {self.env}:\n" + "\n".join(f"  - {e}" for e in errors)
            error_msg += f"\n\nSee INTEGRATION_GUIDE.md for setup instructions."
            raise RuntimeError(error_msg)

# Global config instance
config = CivicConfig()


def get_bundled_path(*path_parts: str) -> str:
    """Get absolute path to a file in the bundled data directory.

    Bundled data is read-only reference data baked into the Docker image.
    Contains: events, vectors, legislative context

    Args:
        *path_parts: Path components relative to bundled data directory

    Returns:
        Absolute path string

    Example:
        get_bundled_path('pilot', 'vectors', 'city-san-rafael')
        # Production: /app/bundled-data/pilot/vectors/city-san-rafael
        # Development: data/pilot/vectors/city-san-rafael
    """
    data_dir = config.get_bundled_data_dir()
    return str(data_dir.joinpath(*path_parts))


def get_user_path(*path_parts: str) -> str:
    """Get absolute path to a file in the user data directory.

    User data is persistent data stored on Fly.io volume.
    Contains: participation database, sessions, user preferences

    Args:
        *path_parts: Path components relative to user data directory

    Returns:
        Absolute path string

    Example:
        get_user_path('civic_participation.db')
        # Production: /app/user-data/civic_participation.db
        # Development: data/civic_participation.db
    """
    data_dir = config.get_user_data_dir()
    return str(data_dir.joinpath(*path_parts))


def get_data_path(*path_parts: str) -> str:
    """Get absolute path to a file in the data directory (legacy compatibility).

    DEPRECATED: Use get_bundled_path() or get_user_path() instead.
    This function returns bundled data path for backwards compatibility.
    """
    return get_bundled_path(*path_parts)