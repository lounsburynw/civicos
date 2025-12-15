#!/usr/bin/env python3
"""
Civic Input Validator - Security-focused input validation for MCP server endpoints

This module provides comprehensive input validation to prevent security vulnerabilities
including XSS, SQL injection, command injection, and prompt injection attacks.

SECURITY STATUS:
✅ Type confusion vulnerability - FIXED (production ready)
✅ XSS, SQL injection, command injection - BLOCKED (production ready)
✅ Prompt injection - Civic topic boundaries handled by system prompts in conversation API

SECURITY APPROACH:
- Basic regex-based prompt injection detection for input validation
- Civic conversation boundaries enforced through system prompts with topic bridging
- General safety/harmful content handled by OpenAI/Anthropic providers

PRODUCTION READINESS:
- Ready for civic engagement use cases with system prompt topic bridging
- Monitor for prompt injection attempts in logs

Author: Security audit implementation
"""

import re
import html
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ValidationResult:
    """Result of input validation with sanitized value and error details"""
    is_valid: bool
    sanitized_value: str
    error_message: Optional[str] = None
    severity: str = "INFO"  # INFO, WARNING, ERROR, CRITICAL

class CivicInputValidator:
    """
    Production-ready input validator for civic engagement platform.
    Implements defense-in-depth security measures.
    """
    
    # Security patterns - characters that could be used in attacks
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',  # Script tags
        r'javascript:',               # JavaScript URLs
        r'on\w+\s*=',                # Event handlers
        r'<\s*iframe[^>]*>',         # Iframe tags
        r'<\s*object[^>]*>',         # Object tags
        r'<\s*embed[^>]*>',          # Embed tags
        r'<\s*link[^>]*>',           # Link tags (could load external resources)
        r'<\s*meta[^>]*>',           # Meta tags
        r'data:text/html',           # Data URLs
        r'vbscript:',                # VBScript URLs
        r'\beval\s*\(',              # JavaScript eval
        r'\bFunction\s*\(',          # JavaScript Function constructor
        r'<%.*?%>',                  # Server-side includes
        r'\{\{.*?\}\}',              # Template injection patterns
        r'\$\{.*?\}',                # Expression language injection
        r'<!--.*?-->',               # HTML comments (could hide payloads)
    ]
    
    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r'\bunion\s+select\b',
        r'\bselect\s+.*\bfrom\b',
        r'\binsert\s+into\b',
        r'\bupdate\s+.*\bset\b',
        r'\bdelete\s+from\b',
        r'\bdrop\s+table\b',
        r'\bor\s+1\s*=\s*1\b',
        r"'\s*or\s*'1'\s*=\s*'1",
        r'--\s',                     # SQL comments
        r'/\*.*?\*/',                # SQL block comments
        r'\bexec\s*\(',              # SQL execution
        r'\bsp_\w+',                 # Stored procedures
        r'\bxp_\w+',                 # Extended procedures
        r"admin'--",                 # Classic admin bypass
        r"admin'\s*--",              # Admin bypass with space
        r"'\s*--",                   # Generic comment injection
        r"'.*--",                    # Any quote followed by comment
        r'0x[0-9a-fA-F]+',          # Hexadecimal encoding
        r'\bhex\s*\(',               # Hex function
        r'\bchar\s*\(',              # Char function
        r'\bascii\s*\(',             # ASCII function
        r"'\s*\+\s*'",               # String concatenation
        r'\bwaitfor\s+delay\b',      # Time-based injection
        r'\bif\s*\(\s*1\s*=\s*1\s*\)', # Conditional injection
    ]
    
    # Command injection patterns
    COMMAND_INJECTION_PATTERNS = [
        r'[;&|`$()]',                # Shell metacharacters
        r'\bwget\b|\bcurl\b',        # Download commands
        r'\bnc\b|\bnetcat\b',        # Network commands
        r'\bsh\b|\bbash\b|\bcmd\b',  # Shell commands
        r'\bpython\b|\bperl\b|\bruby\b',  # Scripting languages
        r'\bcat\b|\btail\b|\bhead\b',     # File reading commands
        r'\bps\b|\btop\b|\bhtop\b',       # Process listing
        r'\bls\b|\bdir\b|\bfind\b',       # Directory listing
        r'\brm\b|\bdel\b|\bmkdir\b',      # File operations
        r'\bchmod\b|\bchown\b',           # Permission changes
        r'\bsudo\b|\bsu\b',               # Privilege escalation
    ]
    
    # Prompt injection patterns for AI models
    PROMPT_INJECTION_PATTERNS = [
        r'\bignore\s+(?:all\s+)?(?:previous|above|all|your)\s+instructions?\b',
        r'\bforget\s+(?:all\s+)?(?:previous|above|all|your)\s+(?:instructions?|role|guidelines?)\b',
        r'\bact\s+as\s+(?:if\s+)?you\s+(?:are|were)\b',
        r'\bpretend\s+(?:to\s+be|you\s+are)\b',
        r'\brole\s*:\s*(?:assistant|system|user|evil|hacker)\b',
        r'\bsystem\s*:\s*',
        r'\bassistant\s*:\s*',
        r'\buser\s*:\s*',
        r'\b(?:start|begin)\s+new\s+(?:conversation|session|context)\b',
        r'\b(?:reset|clear)\s+(?:context|memory|conversation)\b',
        r'\b(?:jailbreak|bypass|override)\s+(?:instructions?|rules?|guidelines?|safety)\b',
        r'\b(?:reveal|show|tell)\s+(?:your|the)\s+(?:prompt|instructions?|system\s+message)\b',
        r'###\s*(?:new|ignore|override|system|instructions?)',
        r'\bhack\s+(?:the\s+)?system\b',
        r'\bevil\s+ai\b',
        r'\btask\s*:\s*hack\b',
        r'\bhacker\b.*(?:assistant|ai|system)\b',
        r'\bmalicious\s+content\b',
        r'\billegal\s+activit(?:y|ies)\b',
        r'\byou\s+are\s+(?:now\s+)?(?:a\s+)?(?:different|evil|hacker)',
        r'\bcivic\s+assistant\b.*\bnow\s+(?:a\s+)?(?:different|hacker|evil)',
    ]
    
    def __init__(self):
        """Initialize the validator with compiled regex patterns for performance"""
        self.dangerous_regex = re.compile('|'.join(self.DANGEROUS_PATTERNS), re.IGNORECASE | re.DOTALL)
        self.sql_regex = re.compile('|'.join(self.SQL_INJECTION_PATTERNS), re.IGNORECASE)
        self.cmd_regex = re.compile('|'.join(self.COMMAND_INJECTION_PATTERNS), re.IGNORECASE)
        self.prompt_regex = re.compile('|'.join(self.PROMPT_INJECTION_PATTERNS), re.IGNORECASE)
    
    def validate_item_title(self, item_title: str) -> ValidationResult:
        """
        Validate item_title parameter with comprehensive security checks.
        
        Args:
            item_title: The agenda item title to validate
            
        Returns:
            ValidationResult with sanitized value and validation status
        """
        if not item_title:
            return ValidationResult(
                is_valid=False,
                sanitized_value="",
                error_message="Item title cannot be empty",
                severity="ERROR"
            )
        
        # Length validation - reasonable bounds for agenda item titles
        if len(item_title) > 500:
            return ValidationResult(
                is_valid=False,
                sanitized_value=item_title[:500],
                error_message=f"Item title too long ({len(item_title)} chars, max 500)",
                severity="ERROR"
            )
        
        if len(item_title.strip()) < 3:
            return ValidationResult(
                is_valid=False,
                sanitized_value=item_title.strip(),
                error_message="Item title too short (minimum 3 characters)",
                severity="ERROR"
            )
        
        # Security validation
        security_check = self._check_security_patterns(item_title, "item_title")
        if not security_check.is_valid:
            return security_check
        
        # Sanitize the value
        sanitized = self._sanitize_text(item_title)
        
        return ValidationResult(
            is_valid=True,
            sanitized_value=sanitized,
            severity="INFO"
        )
    
    def validate_key_points(self, key_points: str) -> ValidationResult:
        """
        Validate key_points parameter with comprehensive security checks.
        
        Args:
            key_points: The user's key points to validate
            
        Returns:
            ValidationResult with sanitized value and validation status
        """
        if not key_points:
            return ValidationResult(
                is_valid=False,
                sanitized_value="",
                error_message="Key points cannot be empty",
                severity="ERROR"
            )
        
        # Length validation - reasonable bounds for user input
        if len(key_points) > 5000:
            return ValidationResult(
                is_valid=False,
                sanitized_value=key_points[:5000],
                error_message=f"Key points too long ({len(key_points)} chars, max 5000)",
                severity="ERROR"
            )
        
        if len(key_points.strip()) < 5:
            return ValidationResult(
                is_valid=False,
                sanitized_value=key_points.strip(),
                error_message="Key points too short (minimum 5 characters)",
                severity="ERROR"
            )
        
        # Check for too many lines (potential spam/abuse)
        lines = [line.strip() for line in key_points.split('\n') if line.strip()]
        if len(lines) > 20:
            return ValidationResult(
                is_valid=False,
                sanitized_value='\n'.join(lines[:20]),
                error_message=f"Too many key points ({len(lines)} lines, max 20)",
                severity="ERROR"
            )
        
        # Security validation
        security_check = self._check_security_patterns(key_points, "key_points")
        if not security_check.is_valid:
            return security_check
        
        # Sanitize the value
        sanitized = self._sanitize_text(key_points)
        
        return ValidationResult(
            is_valid=True,
            sanitized_value=sanitized,
            severity="INFO"
        )
    
    def validate_stance(self, stance: Optional[str]) -> ValidationResult:
        """
        Validate resident_stance parameter.
        
        Args:
            stance: The user's stance (support/oppose/question/neutral)
            
        Returns:
            ValidationResult with sanitized value and validation status
        """
        if stance is None or stance == "":
            return ValidationResult(
                is_valid=True,
                sanitized_value="",
                severity="INFO"
            )
        
        # Type validation - only accept strings or None
        if not isinstance(stance, str):
            return ValidationResult(
                is_valid=False,
                sanitized_value="neutral",
                error_message=f"Stance must be a string, got {type(stance).__name__}",
                severity="ERROR"
            )
        
        # Convert to string and normalize whitespace
        stance_str = stance.lower().strip()
        
        if not stance_str:
            return ValidationResult(
                is_valid=True,
                sanitized_value="",
                severity="INFO"
            )
        
        # Length validation
        if len(stance_str) > 50:
            return ValidationResult(
                is_valid=False,
                sanitized_value="neutral",
                error_message=f"Stance too long ({len(stance_str)} chars, max 50)",
                severity="ERROR"
            )
        
        # Whitelist validation - only allow specific values
        allowed_stances = ["support", "oppose", "question", "neutral"]
        
        if stance_str not in allowed_stances:
            return ValidationResult(
                is_valid=False,
                sanitized_value="neutral",
                error_message=f"Invalid stance '{stance_str}'. Must be one of: {', '.join(allowed_stances)}",
                severity="ERROR"
            )
        
        return ValidationResult(
            is_valid=True,
            sanitized_value=stance_str,
            severity="INFO"
        )
    
    def _check_security_patterns(self, text: str, field_name: str) -> ValidationResult:
        """
        Check input against various security attack patterns.
        
        Args:
            text: The text to validate
            field_name: Name of the field for logging
            
        Returns:
            ValidationResult indicating if any security patterns were found
        """
        # Check for XSS and dangerous HTML patterns
        if self.dangerous_regex.search(text):
            logger.warning(f"Dangerous pattern detected in {field_name}: {text[:100]}...")
            return ValidationResult(
                is_valid=False,
                sanitized_value=self._sanitize_text(text),
                error_message=f"Input contains potentially dangerous content in {field_name}",
                severity="CRITICAL"
            )
        
        # Check for SQL injection patterns
        if self.sql_regex.search(text):
            logger.warning(f"SQL injection pattern detected in {field_name}: {text[:100]}...")
            return ValidationResult(
                is_valid=False,
                sanitized_value=self._sanitize_text(text),
                error_message=f"Input contains SQL injection patterns in {field_name}",
                severity="CRITICAL"
            )
        
        # Check for command injection patterns
        if self.cmd_regex.search(text):
            logger.warning(f"Command injection pattern detected in {field_name}: {text[:100]}...")
            return ValidationResult(
                is_valid=False,
                sanitized_value=self._sanitize_text(text),
                error_message=f"Input contains command injection patterns in {field_name}",
                severity="CRITICAL"
            )
        
        # Check for prompt injection patterns (specific to AI applications)
        if self.prompt_regex.search(text):
            logger.warning(f"Prompt injection pattern detected in {field_name}: {text[:100]}...")
            return ValidationResult(
                is_valid=False,
                sanitized_value=self._sanitize_text(text),
                error_message=f"Input contains prompt injection patterns in {field_name}",
                severity="CRITICAL"
            )
        
        # Note: Advanced semantic prompt injection detection is handled by the system prompt
        # in the conversation API, which uses civic topic bridging to maintain conversation boundaries.
        # OpenAI/Anthropic providers handle general safety and harmful content detection.
        
        return ValidationResult(is_valid=True, sanitized_value=text, severity="INFO")
    
    def _sanitize_text(self, text: str) -> str:
        """
        Sanitize text by removing/escaping dangerous content.
        
        Args:
            text: The text to sanitize
            
        Returns:
            Sanitized text safe for processing
        """
        # HTML escape to prevent XSS
        sanitized = html.escape(text, quote=True)
        
        # Remove null bytes and other control characters
        sanitized = ''.join(char for char in sanitized if ord(char) >= 32 or char in '\n\r\t')
        
        # Normalize whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        
        return sanitized
    
    
    def validate_request_data(self, data: Dict[str, Any]) -> Dict[str, ValidationResult]:
        """
        Validate all fields in a request data dictionary.
        
        Args:
            data: Dictionary containing request parameters
            
        Returns:
            Dictionary mapping field names to ValidationResults
        """
        results = {}
        
        # Check if data is empty or None
        if not data:
            results['_global'] = ValidationResult(
                is_valid=False,
                sanitized_value="",
                error_message="Request data cannot be empty",
                severity="ERROR"
            )
            return results
        
        # Check for required fields
        required_fields = ['item_title', 'key_points']
        missing_fields = []
        
        for field in required_fields:
            if field not in data or data[field] is None or (isinstance(data[field], str) and not data[field].strip()):
                missing_fields.append(field)
        
        if missing_fields:
            results['_global'] = ValidationResult(
                is_valid=False,
                sanitized_value="",
                error_message=f"Missing required fields: {', '.join(missing_fields)}",
                severity="ERROR"
            )
            return results
        
        # Validate item_id if present
        if 'item_id' in data:
            item_id = str(data['item_id']) if data['item_id'] is not None else ""
            if len(item_id) > 100 or not re.match(r'^[a-zA-Z0-9_-]*$', item_id):
                results['item_id'] = ValidationResult(
                    is_valid=False,
                    sanitized_value=re.sub(r'[^a-zA-Z0-9_-]', '', item_id)[:100],
                    error_message="Item ID contains invalid characters or is too long",
                    severity="ERROR"
                )
            else:
                results['item_id'] = ValidationResult(is_valid=True, sanitized_value=item_id)
        
        # Validate item_title (required)
        if 'item_title' in data:
            # Type validation - only accept strings or None
            if data['item_title'] is not None and not isinstance(data['item_title'], str):
                results['item_title'] = ValidationResult(
                    is_valid=False,
                    sanitized_value="",
                    error_message=f"Item title must be a string, got {type(data['item_title']).__name__}",
                    severity="ERROR"
                )
            else:
                title_value = str(data['item_title']) if data['item_title'] is not None else ""
                results['item_title'] = self.validate_item_title(title_value)
        
        # Validate key_points (required)  
        if 'key_points' in data:
            # Type validation - accept strings, lists, or None
            if data['key_points'] is not None and not isinstance(data['key_points'], (str, list)):
                results['key_points'] = ValidationResult(
                    is_valid=False,
                    sanitized_value="",
                    error_message=f"Key points must be a string or list, got {type(data['key_points']).__name__}",
                    severity="ERROR"
                )
            else:
                # Convert to string if not already (handle lists, etc.)
                if isinstance(data['key_points'], list):
                    key_points_value = '\n'.join(str(item) for item in data['key_points'])
                else:
                    key_points_value = str(data['key_points']) if data['key_points'] is not None else ""
                results['key_points'] = self.validate_key_points(key_points_value)
        
        # Validate stance if present (optional)
        if 'stance' in data:
            results['stance'] = self.validate_stance(data['stance'])
        
        return results

# Global validator instance for use across the application
civic_validator = CivicInputValidator()

def validate_civic_input(data: Dict[str, Any]) -> tuple[bool, Dict[str, str], str]:
    """
    Convenience function for validating civic input data.
    
    Args:
        data: Dictionary containing input parameters
        
    Returns:
        Tuple of (is_valid, sanitized_data, error_message)
    """
    results = civic_validator.validate_request_data(data)
    
    # Check for global validation failures first
    if '_global' in results:
        global_result = results['_global']
        return global_result.is_valid, {}, global_result.error_message
    
    # Check if all validations passed
    is_valid = all(result.is_valid for result in results.values())
    
    # Extract sanitized values (exclude any global results)
    sanitized_data = {field: result.sanitized_value for field, result in results.items() 
                     if not field.startswith('_')}
    
    # Collect error messages
    errors = [result.error_message for result in results.values() if result.error_message]
    error_message = "; ".join(errors) if errors else ""
    
    # Log critical security issues
    critical_errors = [result.error_message for result in results.values() 
                      if result.severity == "CRITICAL"]
    if critical_errors:
        logger.critical(f"Critical security validation failures: {'; '.join(critical_errors)}")
    
    return is_valid, sanitized_data, error_message

# Export main functions for easy import
__all__ = ['CivicInputValidator', 'ValidationResult', 'civic_validator', 'validate_civic_input']