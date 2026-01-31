"""
Shared MCP tool definitions for CivicOS.

This module provides the tool definitions that can be used by both:
- civicos_server.py (FastMCP with @mcp.tool decorators)
- modal_app.py (Modal with dictionary-based tool registry)

The tools are organized by category:
- civic: Core civic query tools (meetings, decisions, regulatory stack)
- issues: 311/SeeClickFix analysis tools
- council: Voting and decision context tools
- financial: Budget and intergovernmental funding tools
- actions: Public comment and meeting preparation tools
"""

from .registry import ToolRegistry, ToolDefinition, TOOL_DEFINITIONS, get_all_tools
from .handlers import (
    # Civic handlers
    search_meeting_history,
    get_upcoming_meetings,
    find_similar_issues,
    search_regulatory_stack,
    compose_public_comment,
    city_pulse,
    get_issue_analytics,
    get_issue_trends,
    geo_search_issues,
    search_budget,
    get_public_testimony,
    search_agenda_packets,
    get_comment_guidelines,
    get_started,
    # Issue analysis handlers
    query_issue_data,
    get_issue_resolution_stats,
    detect_trends,
    get_issue_sample,
    find_issues_near_address,
    find_repeat_issues,
    get_seasonal_patterns,
    compare_zip_codes,
    neighborhood_report,
    # Council handlers
    get_voting_record,
    get_decision_context,
    # Financial handlers
    get_funding_flow,
    get_federal_expenditures,
    get_intergovernmental_revenue,
    # Action handlers
    get_comment_template,
    prepare_for_meeting,
    # Coordination handlers
    get_voice_counts,
    subscribe_to_topic,
    prepare_voice,
    broadcast_voice,
    list_relays,
)

__all__ = [
    # Registry
    "ToolRegistry",
    "ToolDefinition",
    "TOOL_DEFINITIONS",
    "get_all_tools",
    # All handlers (for FastMCP decoration)
    "search_meeting_history",
    "get_upcoming_meetings",
    "find_similar_issues",
    "search_regulatory_stack",
    "compose_public_comment",
    "city_pulse",
    "get_issue_analytics",
    "get_issue_trends",
    "geo_search_issues",
    "search_budget",
    "get_public_testimony",
    "search_agenda_packets",
    "get_comment_guidelines",
    "get_started",
    "query_issue_data",
    "get_issue_resolution_stats",
    "detect_trends",
    "get_issue_sample",
    "find_issues_near_address",
    "find_repeat_issues",
    "get_seasonal_patterns",
    "compare_zip_codes",
    "neighborhood_report",
    "get_voting_record",
    "get_decision_context",
    "get_funding_flow",
    "get_federal_expenditures",
    "get_intergovernmental_revenue",
    "get_comment_template",
    "prepare_for_meeting",
    "get_voice_counts",
    "subscribe_to_topic",
    "prepare_voice",
    "broadcast_voice",
    "list_relays",
]
