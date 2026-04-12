"""
Tests for the city_pulse MCP tool.

Tests the data aggregation logic for the city status dashboard,
using the real handler from tools/handlers.py with a live CivicOS client.
"""

import pytest
import sys
import os
import logging

# Add MCP server to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'apps', 'civicos-mcp'))


def _noop_validate(args):
    """Validator that accepts all input."""
    return True, args, None


class TestCityPulseIntegration:
    """Integration tests requiring database connection."""

    @pytest.mark.requires_real_data
    def test_city_pulse_returns_structured_data(self):
        """city_pulse should return meetings, outcomes, and community data."""
        from dotenv import load_dotenv
        load_dotenv()

        from tools.handlers import city_pulse
        from civicos import CivicOS

        civic = CivicOS('city-san-rafael')
        logger = logging.getLogger('test')

        result = city_pulse(civic, 'city-san-rafael', _noop_validate, logger, {})

        # Specific value check — jurisdiction must match input
        assert result['jurisdiction'] == 'city-san-rafael'

        # generated_at must be a valid ISO timestamp
        from datetime import datetime
        generated = datetime.fromisoformat(result['generated_at'])
        assert (datetime.now() - generated).total_seconds() < 60

        # Meetings list with expected shape
        assert isinstance(result['decisions_this_week'], list)
        for meeting in result['decisions_this_week']:
            assert 'title' in meeting and isinstance(meeting['title'], str)
            assert len(meeting['title']) > 0, "Meeting title must not be empty"
            assert 'date' in meeting

        # Outcomes list with expected shape
        assert isinstance(result['recent_outcomes'], list)
        for outcome in result['recent_outcomes']:
            assert 'title' in outcome and len(outcome['title']) > 0
            assert outcome['outcome'] in {
                'approved', 'denied', 'tabled', 'continued',
                'decided', 'on_agenda', 'received and filed',
                'adopted', 'withdrawn',
            } or isinstance(outcome['outcome'], str)

        # Community pulse structure
        pulse = result.get('community_pulse', {})
        if pulse:
            assert pulse['total_issues'] > 0, "Non-empty pulse must have issues"
            assert len(pulse['top_types']) >= 1

    @pytest.mark.requires_real_data
    def test_city_pulse_days_ahead_param(self):
        """days_ahead parameter should control meeting lookahead window."""
        from dotenv import load_dotenv
        load_dotenv()

        from tools.handlers import city_pulse
        from civicos import CivicOS

        civic = CivicOS('city-san-rafael')
        logger = logging.getLogger('test')

        # Narrow window
        narrow = city_pulse(civic, 'city-san-rafael', _noop_validate, logger, {'days_ahead': 1})
        # Wide window
        wide = city_pulse(civic, 'city-san-rafael', _noop_validate, logger, {'days_ahead': 30})

        # Wide window should have >= meetings as narrow
        assert len(wide['decisions_this_week']) >= len(narrow['decisions_this_week'])

    @pytest.mark.requires_real_data
    def test_get_started_returns_formatted_welcome(self):
        """get_started should return markdown with jurisdiction name and sections."""
        from dotenv import load_dotenv
        load_dotenv()

        from tools.handlers import get_started
        from civicos import CivicOS

        civic = CivicOS('city-san-rafael')
        logger = logging.getLogger('test')

        result = get_started(civic, 'city-san-rafael', _noop_validate, logger, {})

        assert isinstance(result, str)
        # Must include the formatted jurisdiction name in heading
        assert '# Welcome to San-Rafael' in result
        # Must include the action menu
        assert 'What Can I Help With?' in result
        assert 'Search past council decisions' in result
