#!/usr/bin/env python3
"""
Complaint Detection System - Conversational intent detection for civic complaints

Detects complaint intent from unstructured user messages and extracts structured metadata.
"""

import os
import json
from typing import Optional, Dict, Any
from dataclasses import dataclass
import openai


@dataclass
class ComplaintIntent:
    """Structured representation of detected complaint intent"""
    description: str
    issue_type: str  # housing, transportation, environment, infrastructure, public_safety, community
    jurisdiction_id: Optional[str] = None
    location_mention: Optional[str] = None
    confidence: str = "medium"  # high, medium, low

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            'description': self.description,
            'issue_type': self.issue_type,
            'jurisdiction_id': self.jurisdiction_id,
            'location_mention': self.location_mention,
            'confidence': self.confidence
        }


class IssueDetector:
    """Detect complaint intent in conversational messages using LLM"""

    def __init__(self, openai_api_key: Optional[str] = None):
        """Initialize with OpenAI API key"""
        self.client = openai.OpenAI(
            api_key=openai_api_key or os.getenv('OPENAI_API_KEY')
        )

    def detect_complaint(self, message: str, user_context: Optional[Dict[str, Any]] = None) -> Optional[ComplaintIntent]:
        """
        Detect complaint intent from user message

        Args:
            message: User's conversational message
            user_context: Optional context (user's default jurisdiction, etc.)

        Returns:
            ComplaintIntent if complaint detected, None otherwise
        """
        if not message or len(message.strip()) < 10:
            return None

        # Extract complaint fields using LLM
        intent_data = self._extract_complaint_fields(message)
        if not intent_data or not intent_data.get('is_complaint'):
            return None

        # Build ComplaintIntent object
        jurisdiction_id = self._resolve_jurisdiction(
            intent_data.get('location_mention'),
            user_context
        )

        return ComplaintIntent(
            description=intent_data.get('description', message),
            issue_type=intent_data.get('issue_type', 'community'),
            jurisdiction_id=jurisdiction_id,
            location_mention=intent_data.get('location_mention'),
            confidence=intent_data.get('confidence', 'medium')
        )

    def _extract_complaint_fields(self, message: str) -> Optional[Dict[str, Any]]:
        """Use LLM to extract complaint fields from message"""
        prompt = f"""Analyze this user message to detect civic complaint intent.

User Message: "{message}"

Determine if this is a complaint about a municipal issue (problem requiring civic action).

A COMPLAINT is:
- Description of a problem or concern within municipal purview
- Expression of desire for action/change
- Housing issues (rent, repairs, landlords, evictions)
- Infrastructure problems (potholes, utilities, repairs)
- Transportation concerns (transit, traffic, bike lanes)
- Environmental issues (pollution, parks, climate)
- Public safety concerns (not emergencies - those should call 911)
- Community services (libraries, programs, accessibility)

NOT a complaint:
- General questions ("When is the next meeting?")
- Information requests ("What's the zoning code?")
- Already-resolved issues ("They fixed my pothole")
- Emergencies (call 911 instead)

If this IS a complaint, extract:
{{
    "is_complaint": true,
    "description": "cleaned, clear description of the problem (1-2 sentences)",
    "issue_type": "housing|transportation|environment|infrastructure|public_safety|community",
    "location_mention": "any city/neighborhood mentioned or null",
    "confidence": "high|medium|low"
}}

If NOT a complaint:
{{
    "is_complaint": false
}}

Respond ONLY with valid JSON."""

        try:
            response_text = self._call_llm(prompt, max_tokens=300)
            return self._safe_json_parse(response_text)
        except Exception as e:
            print(f"⚠️ Complaint detection failed: {type(e).__name__}")
            return None

    def _resolve_jurisdiction(self, location_mention: Optional[str], user_context: Optional[Dict[str, Any]]) -> Optional[str]:
        """Resolve location mention to jurisdiction_id using the jurisdiction registry."""
        if location_mention:
            try:
                from civic_config.jurisdiction import JurisdictionRegistry
                jurisdiction_id = JurisdictionRegistry.get_location_display_name(location_mention)
                if jurisdiction_id:
                    return jurisdiction_id
            except ImportError:
                pass

        # Fallback to user context
        if user_context and user_context.get('jurisdiction_id'):
            return user_context['jurisdiction_id']

        return None

    def _call_llm(self, prompt: str, max_tokens: int = 300) -> str:
        """Call OpenAI API with error handling"""
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a civic engagement assistant. Detect complaint intent and extract structured information. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=max_tokens,
            temperature=0.1
        )
        return response.choices[0].message.content.strip()

    def _safe_json_parse(self, text: str) -> Optional[Dict[str, Any]]:
        """Safely parse JSON response"""
        try:
            text = text.strip()
            if text.startswith('```json'):
                text = text[7:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()
            return json.loads(text)
        except Exception:
            return None
