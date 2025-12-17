#!/usr/bin/env python3
"""
Centralized configuration management for Civic platform
Handles API keys, environment detection, and security settings
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in project root
# override=True ensures .env takes precedence over shell env vars (fixes stale key caching)
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)


@dataclass
class ValidationResult:
    """Structured result from configuration validation."""

    environment: str
    passed: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    suggestions: Dict[str, str] = field(default_factory=dict)
    checked_at: Optional[datetime] = None

    def format_errors(self) -> str:
        """Format errors for display/logging."""
        lines = [f"\nConfiguration validation failed for {self.environment}:"]
        lines.append("")
        lines.append("ERRORS (must fix):")
        for error in self.errors:
            lines.append(f"  - {error}")

        if self.warnings:
            lines.append("")
            lines.append("WARNINGS (should address):")
            for warning in self.warnings:
                lines.append(f"  - {warning}")

        if self.suggestions:
            lines.append("")
            lines.append("SUGGESTIONS:")
            for key, suggestion in self.suggestions.items():
                lines.append(f"  {key}: {suggestion}")

        lines.append("")
        lines.append("See .env.example for configuration reference.")
        return "\n".join(lines)

    def format_summary(self) -> str:
        """Format a summary for display."""
        status = "PASSED" if self.passed else "FAILED"
        lines = [f"Configuration Validation: {status}"]
        lines.append(f"Environment: {self.environment}")
        lines.append(f"Errors: {len(self.errors)}")
        lines.append(f"Warnings: {len(self.warnings)}")
        if self.checked_at:
            lines.append(f"Checked: {self.checked_at.strftime('%Y-%m-%d %H:%M:%S')}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'environment': self.environment,
            'passed': self.passed,
            'errors': self.errors,
            'warnings': self.warnings,
            'suggestions': self.suggestions,
            'checked_at': self.checked_at.isoformat() if self.checked_at else None
        }


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
    
    def validate_environment(self, raise_on_error: bool = True) -> 'ValidationResult':
        """Validate required environment variables are set for current environment.

        Args:
            raise_on_error: If True, raises RuntimeError on validation failure.
                           If False, returns ValidationResult without raising.

        Returns:
            ValidationResult with detailed validation status.
        """
        result = ValidationResult(environment=self.env)

        # Run all category validators
        self._validate_core_config(result)
        self._validate_security_config(result)
        self._validate_data_paths(result)
        self._validate_llm_config(result)
        self._validate_external_services(result)

        # Determine overall pass/fail
        result.passed = len(result.errors) == 0
        result.checked_at = datetime.now()

        if not result.passed and raise_on_error:
            error_msg = result.format_errors()
            raise RuntimeError(error_msg)

        return result

    def _validate_core_config(self, result: 'ValidationResult') -> None:
        """Validate core environment configuration."""
        # CIVIC_ENV validation
        env = os.getenv('CIVIC_ENV', '')
        if not env:
            result.warnings.append("CIVIC_ENV not set, defaulting to 'development'")
            result.suggestions['CIVIC_ENV'] = "Set CIVIC_ENV=development|staging|production"
        elif env not in ['development', 'staging', 'production']:
            result.warnings.append(f"CIVIC_ENV='{env}' is non-standard, using 'development'")
            result.suggestions['CIVIC_ENV'] = "Valid values: development, staging, production"

        # Port validation
        port = os.getenv('CIVIC_API_PORT')
        if port:
            try:
                port_int = int(port)
                if not (1024 <= port_int <= 65535):
                    result.warnings.append(f"CIVIC_API_PORT={port} outside recommended range (1024-65535)")
            except ValueError:
                result.errors.append(f"CIVIC_API_PORT='{port}' is not a valid integer")
                result.suggestions['CIVIC_API_PORT'] = "Set to a valid port number (e.g., 8001)"

    def _validate_security_config(self, result: 'ValidationResult') -> None:
        """Validate authentication and security configuration."""
        has_web_key = bool(os.getenv('CIVIC_WEB_KEY'))
        has_demo_key = bool(os.getenv('CIVIC_DEMO_KEY'))
        has_dev_mode = os.getenv('CIVIC_DEV_MODE', '').lower() == 'true'

        if self.env in ['production', 'staging']:
            # Production/staging REQUIRE proper authentication
            if not has_web_key:
                result.errors.append("CIVIC_WEB_KEY is required for authentication in production/staging")
                result.suggestions['CIVIC_WEB_KEY'] = "Generate with: openssl rand -hex 32"
            elif os.getenv('CIVIC_WEB_KEY') == 'dev_key_local':
                result.errors.append("CIVIC_WEB_KEY cannot be 'dev_key_local' in production/staging")
                result.suggestions['CIVIC_WEB_KEY'] = "Generate a secure key: openssl rand -hex 32"

            # CORS must be configured
            cors = os.getenv('CIVIC_CORS_ORIGINS', '')
            if not cors:
                result.errors.append("CIVIC_CORS_ORIGINS must be set to whitelist allowed domains")
                result.suggestions['CIVIC_CORS_ORIGINS'] = "Example: https://your-domain.com,https://staging.your-domain.com"
            elif '*' in cors:
                result.errors.append("CIVIC_CORS_ORIGINS cannot contain '*' in production/staging")

        elif self.env == 'development':
            # Development needs at least one auth method
            if not any([has_web_key, has_demo_key, has_dev_mode]):
                result.errors.append("Development requires CIVIC_WEB_KEY, CIVIC_DEMO_KEY, or CIVIC_DEV_MODE=true")
                result.suggestions['CIVIC_DEV_MODE'] = "Set CIVIC_DEV_MODE=true for local development"

    def _validate_data_paths(self, result: 'ValidationResult') -> None:
        """Validate data directory paths exist and are accessible."""
        bundled_dir = self.get_bundled_data_dir()
        user_dir = self.get_user_data_dir()

        # Bundled data should exist (read-only)
        if not bundled_dir.exists():
            if self.env == 'production':
                result.errors.append(f"Bundled data directory not found: {bundled_dir}")
                result.suggestions['CIVIC_BUNDLED_DATA_DIR'] = "Ensure bundled data is deployed to /app/bundled-data"
            else:
                result.warnings.append(f"Bundled data directory not found: {bundled_dir}")
                result.suggestions['data_setup'] = "Run extraction scripts to populate data/"

        # User data should exist and be writable in production
        if self.env == 'production':
            if not user_dir.exists():
                result.errors.append(f"User data directory not found: {user_dir}")
                result.suggestions['CIVIC_USER_DATA_DIR'] = "Mount persistent volume to /app/user-data"
            elif not os.access(user_dir, os.W_OK):
                result.errors.append(f"User data directory not writable: {user_dir}")
                result.suggestions['permissions'] = "Check volume mount permissions"

    def _validate_llm_config(self, result: 'ValidationResult') -> None:
        """Validate LLM provider configuration."""
        openai_key = os.getenv('OPENAI_API_KEY', '')

        if self.env in ['production', 'staging']:
            if not openai_key:
                result.errors.append("OPENAI_API_KEY is required for AI conversation functionality")
                result.suggestions['OPENAI_API_KEY'] = "Get from: https://platform.openai.com/api-keys"
            elif openai_key.startswith('sk-proj-...') or len(openai_key) < 20:
                result.errors.append("OPENAI_API_KEY appears to be a placeholder, not a real key")
                result.suggestions['OPENAI_API_KEY'] = "Replace with your actual API key"
        elif self.env == 'development':
            if not openai_key:
                result.warnings.append("OPENAI_API_KEY not set - AI features will be limited")
                result.suggestions['OPENAI_API_KEY'] = "Get from: https://platform.openai.com/api-keys"
            elif openai_key.startswith('sk-proj-...'):
                result.warnings.append("OPENAI_API_KEY appears to be placeholder from .env.example")

        # Validate model names if set
        model = os.getenv('OPENAI_MODEL', '')
        valid_models = ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo', 'o1', 'o1-mini']
        if model and model not in valid_models:
            result.warnings.append(f"OPENAI_MODEL='{model}' not in known models: {valid_models}")

    def _validate_external_services(self, result: 'ValidationResult') -> None:
        """Validate optional external service configuration."""
        # Google Maps - useful but optional
        google_maps_key = os.getenv('GOOGLE_MAPS_API_KEY', '')
        if google_maps_key and google_maps_key.startswith('AIza...'):
            result.warnings.append("GOOGLE_MAPS_API_KEY appears to be placeholder")
            result.suggestions['GOOGLE_MAPS_API_KEY'] = "Get from: https://console.cloud.google.com/apis/credentials"

        # Check for common placeholder patterns in any API key
        placeholder_patterns = ['...', 'your-', 'xxx', 'placeholder']
        api_key_vars = [
            'LEGISCAN_API_KEY', 'ASSEMBLYAI_API_KEY', 'LLAMAPARSE_API_KEY',
            'GOOGLE_API_KEY', 'ANTHROPIC_API_KEY', 'GROQ_API_KEY',
            'PERPLEXITY_API_KEY', 'OPENROUTER_API_KEY', 'MISTRAL_API_KEY'
        ]

        for var in api_key_vars:
            value = os.getenv(var, '')
            if value:
                for pattern in placeholder_patterns:
                    if pattern in value.lower():
                        result.warnings.append(f"{var} appears to be a placeholder value")
                        break

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


def validate_config(verbose: bool = False) -> ValidationResult:
    """Validate configuration and return result.

    Convenience function for pre-deployment validation.

    Args:
        verbose: If True, prints detailed output

    Returns:
        ValidationResult with validation status
    """
    result = config.validate_environment(raise_on_error=False)

    if verbose:
        print(result.format_summary())
        print()
        if result.errors:
            print("ERRORS:")
            for error in result.errors:
                print(f"  - {error}")
        if result.warnings:
            print("\nWARNINGS:")
            for warning in result.warnings:
                print(f"  - {warning}")
        if result.suggestions:
            print("\nSUGGESTIONS:")
            for key, suggestion in result.suggestions.items():
                print(f"  {key}: {suggestion}")

    return result


def main():
    """CLI entry point for configuration validation.

    Usage:
        python -m civic_services.core.config [--json]

    Returns exit code 0 if validation passes, 1 if it fails.
    """
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description='Validate Civic platform configuration'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output result as JSON'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Treat warnings as errors'
    )
    args = parser.parse_args()

    result = config.validate_environment(raise_on_error=False)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print("=" * 50)
        print("CIVIC CONFIGURATION VALIDATION")
        print("=" * 50)
        print()
        print(result.format_summary())

        if result.errors:
            print()
            print("ERRORS (must fix before deployment):")
            for error in result.errors:
                print(f"  - {error}")

        if result.warnings:
            print()
            print("WARNINGS (recommended to address):")
            for warning in result.warnings:
                print(f"  - {warning}")

        if result.suggestions:
            print()
            print("HOW TO FIX:")
            for key, suggestion in result.suggestions.items():
                print(f"  {key}: {suggestion}")

        print()
        print("=" * 50)

    # Determine exit code
    if args.strict:
        exit_code = 0 if (result.passed and len(result.warnings) == 0) else 1
    else:
        exit_code = 0 if result.passed else 1

    sys.exit(exit_code)


if __name__ == '__main__':
    main()