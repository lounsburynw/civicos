#!/usr/bin/env python3
"""
MCP Civic Engagement Server

Prototype Model Context Protocol server for bi-directional civic engagement tools.
Part of the civic engagement platform's evolution from "intelligent newsletter" 
to "comprehensive civic participation infrastructure."

This server provides AI-powered tools to transform newsletter readers into active
civic participants through:
- One-click public comment composition and drafting  
- Civic process guidance and submission assistance
- Integration with existing civic_digest.py newsletter system

Goal: Test the hypothesis that bi-directional MCP tools can increase 
newsletter-to-action conversion from <1% to 5-10%.

SECURITY: Input validation added to prevent XSS, SQL injection, command injection,
and prompt injection attacks. Critical security fix for production deployment.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, Dict
from pathlib import Path
from collections import Counter
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Load environment variables (for DATABASE_URL, etc.)
load_dotenv()

# Add parent directory to path for validator and federation imports
sys.path.append(str(Path(__file__).parent.parent))
from civicos_input_validator import validate_civic_input
from federation import (
    get_registry,
    query_peers_parallel,
    format_federation_summary,
    PeerQueryResult,
)

# Add packages to path for Civic import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages" / "civicos" / "src"))
from civicos import CivicOS

# Configure logging to stderr (required for MCP servers)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Civic API client for vector search tools
# Default jurisdiction is San Rafael (pilot city), can be overridden per-tool
DEFAULT_JURISDICTION = os.getenv('CIVICOS_JURISDICTION', 'san-rafael')

# Web app base URL for deep linking
# Production: https://civicos.fly.dev, Local dev: http://localhost:5173
WEB_APP_BASE_URL = os.getenv('CIVICOS_WEB_APP_URL', 'https://civicos.fly.dev')


def _generate_web_app_url(artifact_type: str, artifact_id: str, tab: str = None) -> str:
    """Generate a deep link URL for the CivicOS web app.

    Args:
        artifact_type: Artifact type ('event', 'issue', 'bill', etc.)
        artifact_id: The artifact identifier
        tab: Optional tab to open (e.g., 'discussion' for issues)

    Returns:
        Full URL with query parameters, or empty string if base URL not configured
    """
    if not WEB_APP_BASE_URL or not artifact_id:
        return ""

    # Build URL with query params
    url = f"{WEB_APP_BASE_URL}?type={artifact_type}&id={artifact_id}"
    if tab:
        url += f"&tab={tab}"
    return url
try:
    civicos_client = CivicOS(DEFAULT_JURISDICTION)
    logger.info(f"Civic client initialized for {DEFAULT_JURISDICTION} (storage: {type(civicos_client._storage).__name__})")

    # Pre-warm embedding model at startup (not on first query)
    # This prevents 30-60s hangs on first search request
    if civicos_client._vectors is not None:
        logger.info("Pre-warming embedding model...")
        import time
        start = time.time()
        # Access _embedding_provider to trigger lazy load
        provider = civicos_client._vectors._embedding_provider
        # Run a dummy encode to fully initialize the model
        _ = provider.encode(["warmup query"])
        elapsed = time.time() - start
        logger.info(f"Embedding model ready ({provider.model_name}, {elapsed:.1f}s)")
except Exception as e:
    civicos_client = None
    logger.warning(f"Failed to initialize Civic client: {e}")

# Initialize FastMCP server with transport security for production deployment
# Allow fly.dev host for remote MCP connections from Claude.ai/ChatGPT
from mcp.server.transport_security import TransportSecuritySettings

transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        "localhost",
        "127.0.0.1",
        "civicos-mcp.fly.dev",  # Fly.io (legacy)
        "civicos--civicos-mcp-mcp-endpoint.modal.run",  # Modal (production)
    ],
    allowed_origins=["*"],  # Allow all origins for MCP clients
)

mcp = FastMCP("CivicOS Engagement Server", transport_security=transport_security)

@mcp.tool()
def compose_public_comment(
    item_title: str,
    topic: Optional[str] = None,
) -> str:
    """
    Get context for writing a public comment on a civic agenda item.
    
    Returns submission guidelines, relevant past testimony, and council
    voting history. The calling LLM composes the actual comment using
    this context.
    
    Args:
        item_title: Title/description of the agenda item
        topic: Optional topic for finding related context (e.g., "housing", "traffic")
    
    Returns:
        Context for composing a public comment including:
        - Submission guidelines and deadlines
        - Past public testimony on similar topics
        - Council voting patterns on related items
        - Effective comment tips
    """
    logger.info(f"Getting comment context for: {item_title[:50]}...")
    
    # SECURITY: Validate input
    input_data = {'item_title': item_title, 'topic': topic}
    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    
    if not is_valid:
        logger.error(f"Input validation failed: {error_message}")
        return f"Error: Invalid input - {error_message}"
    
    safe_title = sanitized_data.get('item_title', item_title)
    safe_topic = sanitized_data.get('topic', topic) or safe_title
    
    result_parts = []
    result_parts.append(f"# Public Comment Context: {safe_title}")
    result_parts.append("")
    
    # 1. Submission guidelines
    result_parts.append("## Submission Guidelines")
    result_parts.append("")
    result_parts.append("**San Rafael City Council:**")
    result_parts.append("- Email: clerk@cityofsanrafael.org")
    result_parts.append("- Subject line: \"Public Comment - [Agenda Item Title]\"")
    result_parts.append("- Deadline: 5:00 PM day of meeting for written record")
    result_parts.append("- In-person: 3 minutes max, sign up before meeting")
    result_parts.append("- Meetings: 1st and 3rd Monday, 7:00 PM at City Hall")
    result_parts.append("")
    
    # 2. Past testimony on similar topics (if CivicOS client available)
    if civicos_client:
        try:
            testimony = civicos_client.get_public_testimony(safe_topic, top_k=3)
            if testimony:
                result_parts.append("## What Others Have Said")
                result_parts.append(f"*Recent public comments on \"{safe_topic}\":*")
                result_parts.append("")
                for t in testimony[:3]:
                    speaker = getattr(t, 'speaker_name', 'Resident')
                    text = getattr(t, 'text', str(t))[:200]
                    result_parts.append(f"**{speaker}:** \"{text}...\"")
                    result_parts.append("")
        except Exception as e:
            logger.warning(f"Could not fetch testimony: {e}")
    
    # 3. Voting patterns (if CivicOS client available)
    if civicos_client:
        try:
            decisions = civicos_client.what_happened(safe_topic)[:3]
            if decisions:
                result_parts.append("## Recent Council Decisions on This Topic")
                result_parts.append("")
                for d in decisions[:3]:
                    title = getattr(d, 'title', str(d))[:60]
                    outcome = getattr(d, 'outcome', 'Unknown')
                    result_parts.append(f"- **{title}**: {outcome}")
                result_parts.append("")
        except Exception as e:
            logger.warning(f"Could not fetch decisions: {e}")
    
    # 4. Tips for effective comments
    result_parts.append("## Tips for Effective Comments")
    result_parts.append("")
    result_parts.append("1. **State your position clearly** in the first sentence")
    result_parts.append("2. **Be specific** - reference the agenda item by name")
    result_parts.append("3. **Share personal impact** - how does this affect you/your neighborhood?")
    result_parts.append("4. **Propose alternatives** if opposing - what would you suggest instead?")
    result_parts.append("5. **Be respectful** - address \"Mayor and Council Members\"")
    result_parts.append("6. **Include your address** to show you're a resident")
    result_parts.append("7. **Keep it concise** - 150-300 words is ideal for written, 2-3 min for spoken")
    result_parts.append("")
    
    result_parts.append("---")
    result_parts.append("*Use this context to draft your comment. Include your name and San Rafael address.*")
    
    return "\n".join(result_parts)

@mcp.tool()
def get_comment_template(
    item_title: str,
    stance: Optional[str] = None,
    key_points: Optional[str] = None,
) -> str:
    """
    Get a fill-in-the-blank public comment template.

    For non-LLM clients (CLI tools, scripts, web apps) that just need a basic
    template structure. LLM clients should use compose_public_comment() to get
    full context and write their own comment.

    Args:
        item_title: Title of the agenda item
        stance: Optional stance (support/oppose/question/neutral)
        key_points: Optional newline-separated points to include

    Returns:
        A template comment with placeholders to fill in
    """
    logger.info(f"Generating template for: {item_title[:50]}...")

    comment_parts = []

    # Header
    comment_parts.append(f"Re: {item_title}")
    comment_parts.append("")
    comment_parts.append("Dear Mayor and Council Members,")
    comment_parts.append("")

    # Stance section
    if stance:
        stance_text = {
            "support": "I am writing to express my support for this agenda item.",
            "oppose": "I am writing to express my concerns about this agenda item.",
            "question": "I am writing to request clarification about this agenda item.",
            "neutral": "I am writing to provide input on this agenda item."
        }
        comment_parts.append(stance_text.get(stance.lower(), "I am writing to provide input on this agenda item."))
    else:
        comment_parts.append("I am writing to provide input on this agenda item.")

    comment_parts.append("")

    # Key points section
    if key_points:
        comment_parts.append("Key points:")
        for point in key_points.split("\n"):
            if point.strip():
                comment_parts.append(f"- {point.strip()}")
    else:
        comment_parts.append("Please consider the following:")
        comment_parts.append("- [Your specific concerns or suggestions here]")
        comment_parts.append("- [Impact on residents/community]")
        comment_parts.append("- [Alternatives or modifications to consider]")

    comment_parts.append("")

    # Closing
    comment_parts.append("Thank you for your consideration and service to our community.")
    comment_parts.append("")
    comment_parts.append("Sincerely,")
    comment_parts.append("[Your Name]")
    comment_parts.append("[Your Address in San Rafael]")

    return "\n".join(comment_parts)


@mcp.tool()
def get_comment_guidelines(jurisdiction: str = "san-rafael") -> str:
    """
    Get public comment guidelines and submission information for a jurisdiction.
    
    Args:
        jurisdiction: The city/jurisdiction (default: san-rafael)
    
    Returns:
        Guidelines and contact information for submitting public comments
    """
    logger.info(f"Retrieving comment guidelines for {jurisdiction}")
    
    # San Rafael specific guidelines - will be enhanced with actual research
    if jurisdiction.lower() == "san-rafael":
        return """
San Rafael Public Comment Guidelines:

EMAIL SUBMISSION:
- Send to: clerk@cityofsanrafael.org
- Subject: "Public Comment - [Agenda Item Title]"
- Include your name and San Rafael address
- Submit by 5:00 PM day of meeting for inclusion in official record

IN-PERSON COMMENTS:
- Sign up before meeting starts
- 3 minutes maximum per speaker
- Address comments to Mayor and Council
- No personal attacks or off-topic remarks

WRITTEN SUBMISSION:
- Can be submitted up to day of meeting
- Will be included in official record
- May be summarized by staff if lengthy

CONTACT INFO:
- City Clerk: clerk@cityofsanrafael.org  
- Council meetings: First and third Monday, 7:00 PM
- City Hall: 1400 Fifth Avenue, San Rafael CA 94901
        """.strip()
    
    return f"Guidelines not yet available for {jurisdiction}. Please check the jurisdiction's official website."

@mcp.resource("civic-events://san-rafael/meetings")
def get_meeting_opportunities() -> str:
    """Get current civic engagement events for San Rafael"""
    # This will be enhanced to integrate with the existing civic_digest.py system
    return "Meeting events will be populated from civic_digest.py integration"


# ─────────── VECTOR SEARCH TOOLS ───────────
# These tools expose cross-corpus semantic search to LLM clients
# enabling RAG patterns where LLMs reason over retrieved civic context

@mcp.tool()
def search_regulatory_stack(
    topic: str,
    jurisdiction: str = "san-rafael",
) -> str:
    """
    Search the regulatory stack for a topic across local, state, and federal law.

    Returns relevant regulations, code sections, and legislative context for the topic.
    Searches municipal code, state legislation, and federal programs.

    Args:
        topic: The topic to search (e.g., "accessory dwelling units", "short term rentals")
        jurisdiction: The jurisdiction to search (default: san-rafael)

    Returns:
        Formatted text with relevant regulations from all three levels of government

    Example:
        >>> search_regulatory_stack("accessory dwelling units")
        # Returns local zoning code, CA SB 9/SB 13, federal housing programs
    """
    logger.info(f"Searching regulatory stack for: {topic} in {jurisdiction}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {'topic': topic, 'jurisdiction': jurisdiction}
    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    if not is_valid:
        logger.error(f"Input validation failed: {error_message}")
        return f"Error: Invalid input - {error_message}"

    sanitized_topic = sanitized_data.get('topic', topic)

    try:
        # Use Civic API to get regulatory context
        # Note: what_applies returns RegulatoryStack with federal, state, local
        stack = civicos_client.what_applies(sanitized_topic)

        # Format response for LLM consumption
        result_parts = []
        result_parts.append(f"# Regulatory Stack for: {stack.topic}")
        result_parts.append("")

        # Query context (inline notes for transparency)
        federal_count = len(stack.federal) if stack.federal else 0
        state_count = len(stack.state) if stack.state else 0
        local_count = len(stack.local) if stack.local else 0
        result_parts.append("---")
        result_parts.append(f"🔍 **Query:** \"{sanitized_topic}\" in {stack.jurisdiction}")
        result_parts.append(f"📊 **Searched:** State legislation, federal programs, municipal code")
        result_parts.append(f"📋 **Found:** {state_count} state, {federal_count} federal, {local_count} local results")
        result_parts.append(f"⏱️ **Retrieved:** {stack.retrieved_at}")
        result_parts.append("---")
        result_parts.append("")

        # Federal context
        result_parts.append("## Federal")
        if stack.federal:
            for item in stack.federal[:5]:  # Limit to 5 most relevant
                if isinstance(item, dict):
                    item_type = item.get('type', '')
                    if item_type in ('codified_law', 'cfr'):
                        citation = item.get('citation', '')
                        heading = item.get('heading', '')
                        result_parts.append(f"- **{citation}**: {heading}")
                        if item.get('text_preview'):
                            result_parts.append(f"  *{item.get('text_preview')[:150]}...*")
                    else:
                        result_parts.append(f"- {item.get('title', item.get('program_name', str(item)))}")
                else:
                    result_parts.append(f"- {item}")
        else:
            result_parts.append("No federal regulations found for this topic.")
        result_parts.append("")

        # State context
        result_parts.append("## State")
        if stack.state:
            for item in stack.state[:5]:
                if isinstance(item, dict):
                    bill_number = item.get('bill_number', '')
                    bill_name = item.get('bill_name', '')
                    title = bill_name or bill_number or str(item)
                    # Bill header with status
                    status_label = item.get('status_label', '')
                    status_suffix = f" ({status_label})" if status_label else ""
                    result_parts.append(f"- **{bill_number}**: {title}{status_suffix}" if bill_number else f"- {title}{status_suffix}")
                    if item.get('summary'):
                        result_parts.append(f"  *{item.get('summary')[:150]}...*")
                    # Local action requirements
                    if item.get('requires_local_action') or item.get('local_implementation_required'):
                        deadline = item.get('local_deadline')
                        if deadline:
                            result_parts.append(f"  - Requires local implementation by {deadline}")
                        else:
                            result_parts.append(f"  - Requires local implementation")
                    if item.get('official_url'):
                        result_parts.append(f"  [View bill text]({item.get('official_url')})")
                else:
                    result_parts.append(f"- {item}")
        else:
            result_parts.append("No state regulations found for this topic.")
        result_parts.append("")

        # Local context
        result_parts.append("## Local")
        if stack.local:
            for item in stack.local[:5]:
                if isinstance(item, dict):
                    item_type = item.get('type', '')
                    section = item.get('section_number', '')
                    section_name = item.get('section_name', '')
                    text_preview = item.get('text_preview', item.get('text', ''))[:200]

                    if item_type == 'county_ordinance':
                        county = item.get('jurisdiction', 'County')
                        if section and section_name:
                            result_parts.append(f"- **{county} § {section}** - {section_name}")
                        elif section:
                            result_parts.append(f"- **{county} § {section}**")
                        else:
                            result_parts.append(f"- {county}: {text_preview}...")
                    else:
                        if section and section_name:
                            result_parts.append(f"- **§ {section}** - {section_name}")
                        elif section:
                            result_parts.append(f"- **§ {section}**: {text_preview}...")
                        else:
                            result_parts.append(f"- {text_preview}...")
                    if text_preview and section_name:
                        result_parts.append(f"  *{text_preview}...*")
                else:
                    result_parts.append(f"- {str(item)[:200]}...")
        else:
            result_parts.append("No local regulations found for this topic.")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error searching regulatory stack: {e}")
        return f"Error searching regulatory stack: {str(e)}"


@mcp.tool()
def search_meeting_history(
    query: str,
    include_transcripts: bool = True,
    limit: int = 10,
    federate: bool = False,
) -> str:
    """
    Search past city council meetings and decisions on a topic.

    Returns relevant decisions (motions, resolutions, votes) and optionally
    transcript excerpts from meeting discussions. Use this to understand what
    the council has decided on similar issues in the past.

    Args:
        query: Search query (e.g., "homeless shelter", "bike lane", "housing")
        include_transcripts: If True, also search video transcripts for spoken content
        limit: Maximum number of results per category (default: 10)
        federate: If True, also search peer jurisdictions and aggregate results

    Returns:
        Formatted text with decisions and transcript excerpts

    Example:
        >>> search_meeting_history("homeless services")
        # Returns past decisions and what was discussed about homeless services

        >>> search_meeting_history("housing policy", federate=True)
        # Returns decisions from local + peer jurisdictions
    """
    logger.info(f"Searching meeting history for: {query} (federate={federate})")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {'query': query}
    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    if not is_valid:
        logger.error(f"Input validation failed: {error_message}")
        return f"Error: Invalid input - {error_message}"

    sanitized_query = sanitized_data.get('query', query)

    try:
        result_parts = []
        result_parts.append(f"# Meeting History: {sanitized_query}")
        result_parts.append("")

        # Get local decisions using what_happened()
        decisions = civicos_client.what_happened(sanitized_query)

        # Query peer jurisdictions if federate=True
        peer_results: Dict[str, PeerQueryResult] = {}
        if federate:
            try:
                peer_results = asyncio.run(
                    query_peers_parallel(
                        tool_name="search_meeting_history",
                        tool_args={
                            "query": sanitized_query,
                            "include_transcripts": include_transcripts,
                            "limit": limit,
                            "federate": False,  # Prevent infinite recursion
                        },
                        timeout=10.0,
                    )
                )
            except Exception as e:
                logger.warning(f"Federated query failed: {e}")
                # Continue with local results only

        # Query context (inline notes for transparency)
        decision_count = len(decisions) if decisions else 0
        result_parts.append("---")
        result_parts.append(f"🔍 **Query:** \"{sanitized_query}\"")
        result_parts.append(f"📊 **Searched:** Council decisions, meeting minutes" + (", video transcripts" if include_transcripts else ""))
        result_parts.append(f"📋 **Found:** {decision_count} decisions (local)")

        # Show federation summary
        if federate:
            result_parts.append(format_federation_summary(civicos_client.jurisdiction, peer_results))
        else:
            result_parts.append(f"🏛️ **Jurisdiction:** {civicos_client.jurisdiction}")

        result_parts.append("---")
        result_parts.append("")

        # Format local decisions
        result_parts.append(f"## Decisions ({civicos_client.jurisdiction})")
        if decisions:
            for d in decisions[:limit]:
                result_parts.append(f"### {d.title}")
                result_parts.append(f"- Date: {d.date}")
                result_parts.append(f"- Outcome: {d.outcome or 'N/A'}")
                result_parts.append(f"- Body: {d.body or 'N/A'}")
                if d.votes:
                    result_parts.append(f"- Votes: {d.votes}")
                # Add web app deep link if decision has an ID
                decision_id = getattr(d, 'id', None) or getattr(d, 'meeting_id', None)
                if decision_id:
                    web_url = _generate_web_app_url('event', decision_id)
                    if web_url:
                        result_parts.append(f"- [View in CivicOS]({web_url})")
                result_parts.append("")
        else:
            result_parts.append("No decisions found matching this query.")
        result_parts.append("")

        # Format peer decisions if federated
        if federate and peer_results:
            for jurisdiction_id, peer_result in peer_results.items():
                if peer_result.success and peer_result.raw_response:
                    result_parts.append(f"## Decisions ({jurisdiction_id})")
                    # Peer responses are already formatted markdown
                    # Extract just the decisions section if possible
                    result_parts.append(peer_result.raw_response)
                    result_parts.append("")
                elif not peer_result.success:
                    result_parts.append(f"## Decisions ({jurisdiction_id})")
                    result_parts.append(f"⚠️ Query failed: {peer_result.error}")
                    result_parts.append("")

        # Get transcript excerpts if requested (local only for now)
        if include_transcripts:
            result_parts.append("## What Was Said (Transcript Excerpts)")
            excerpts = civicos_client.what_was_said(sanitized_query, top_k=limit)

            if excerpts:
                for ex in excerpts:
                    speaker = ex.speaker_name or ex.speaker or "Unknown"
                    role = f" ({ex.speaker_role})" if ex.speaker_role else ""
                    timestamp = ex.start_timestamp or ""

                    result_parts.append(f"### {speaker}{role}")
                    if timestamp:
                        # Include clickable YouTube link if video_id is available
                        video_url = ex.video_url
                        if video_url:
                            result_parts.append(f"*[Watch at {timestamp}]({video_url})*")
                        else:
                            result_parts.append(f"*Video timestamp: {timestamp}*")
                    if ex.is_public_comment:
                        result_parts.append("*[Public Comment]*")
                    result_parts.append(f"> {ex.text[:500]}...")
                    result_parts.append("")
            else:
                result_parts.append("No transcript excerpts found for this query.")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error searching meeting history: {e}")
        return f"Error searching meeting history: {str(e)}"


@mcp.tool()
def find_similar_issues(
    topic: str,
    semantic: bool = True,
    limit: int = 20,
) -> str:
    """
    Find community members and issues related to a topic.

    Uses semantic matching to find issues reported through 311/SeeClickFix and
    other sources that relate to the topic. Returns a summary of community
    engagement around the issue.

    Args:
        topic: Topic to search (e.g., "traffic safety", "pothole", "graffiti")
        semantic: If True, use semantic matching to find related issues beyond exact matches
        limit: Maximum number of issues to return (default: 20)

    Returns:
        Summary of community engagement: issue counts, related topics, and trends

    Example:
        >>> find_similar_issues("traffic safety")
        # Returns count of related issues like "speeding", "crosswalk", "stop sign"
    """
    logger.info(f"Finding similar issues for: {topic}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {'topic': topic}
    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    if not is_valid:
        logger.error(f"Input validation failed: {error_message}")
        return f"Error: Invalid input - {error_message}"

    sanitized_topic = sanitized_data.get('topic', topic)

    try:
        result_parts = []
        result_parts.append(f"# Community Issues: {sanitized_topic}")
        result_parts.append("")

        # Query context (inline notes for transparency)
        search_type = "semantic (AI similarity)" if semantic else "keyword"
        result_parts.append("---")
        result_parts.append(f"🔍 **Query:** \"{sanitized_topic}\"")
        result_parts.append(f"📊 **Searched:** 311/SeeClickFix issue reports ({search_type})")
        result_parts.append(f"🏛️ **Jurisdiction:** {civicos_client.jurisdiction}")
        result_parts.append("---")
        result_parts.append("")

        # Use vector search directly for semantic matching
        # This bypasses whos_with_me() which incorrectly uses SQLite state
        if semantic and civicos_client._vectors is not None:
            results = civicos_client._vectors.search(
                sanitized_topic,
                civicos_client.jurisdiction,
                'issues',
                top_k=limit,
            )

            result_parts.append("## Summary")
            result_parts.append(f"- **Related issues found:** {len(results)}")
            result_parts.append("")

            if results:
                result_parts.append("This indicates community interest in this topic.")
                result_parts.append("Citizens have reported related issues through 311/SeeClickFix.")
                result_parts.append("*(Using semantic matching to find related issue types)*")
                result_parts.append("")

                result_parts.append("## Similar Issues Reported")

                # Build ID-to-URL and ID-to-type lookups from storage
                # URLs come from provider_metadata.html_url (populated during ingestion)
                issue_urls = {}
                issue_types = {}
                if civicos_client._storage is not None:
                    try:
                        all_issues = civicos_client._storage.get_issues(
                            jurisdiction_id=civicos_client.jurisdiction,
                            limit=2000,
                        )
                        for issue in all_issues:
                            issue_id = issue.get('id')
                            metadata = issue.get('provider_metadata') or {}
                            html_url = metadata.get('html_url')
                            if issue_id:
                                if html_url:
                                    issue_urls[issue_id] = html_url
                                if issue.get('issue_type'):
                                    issue_types[issue_id] = issue['issue_type']
                    except Exception as e:
                        logger.warning(f"Could not load issue data: {e}")

                # Issue type breakdown for matched results
                matched_ids = {r.id for r in results if r.id}
                type_counts = Counter(
                    issue_types[rid] for rid in matched_ids if rid in issue_types
                )
                if type_counts:
                    breakdown = ", ".join(
                        f"{count} {itype.replace('_', ' ')}"
                        for itype, count in type_counts.most_common()
                    )
                    result_parts.append(f"- **Issue types:** {breakdown}")
                    result_parts.append("")

                for r in results:
                    # Extract issue details from vector result
                    content = r.content[:200] if r.content else "No description"
                    score = r.score if hasattr(r, 'score') else None

                    # Get external URL for this issue if available
                    issue_url = issue_urls.get(r.id)

                    # Generate internal web app link
                    web_app_url = _generate_web_app_url('issue', r.id) if r.id else ""

                    # Format issue entry with links
                    links = []
                    if web_app_url:
                        links.append(f"[Open in CivicOS]({web_app_url})")
                    if issue_url:
                        links.append(f"[View on SeeClickFix]({issue_url})")
                    link_text = " | ".join(links) if links else ""

                    if score is not None:
                        if link_text:
                            result_parts.append(f"- **[{score:.0%} match]** {content}... {link_text}")
                        else:
                            result_parts.append(f"- **[{score:.0%} match]** {content}...")
                    else:
                        if link_text:
                            result_parts.append(f"- {content}... {link_text}")
                        else:
                            result_parts.append(f"- {content}...")
            else:
                result_parts.append("No related issues found via semantic search.")
                result_parts.append("Try different search terms or broader topics.")
        else:
            # Fall back to storage-based keyword search if vectors unavailable
            result_parts.append("## Summary")
            result_parts.append("Semantic search unavailable. Using keyword search.")
            result_parts.append("")

            # Try to get issues from storage directly
            if civicos_client._storage is not None:
                issues = civicos_client._storage.get_issues(
                    jurisdiction_id=civicos_client.jurisdiction,
                    limit=limit,
                )
                # Filter by keyword match (basic fallback)
                topic_lower = sanitized_topic.lower()
                matched = [
                    i for i in issues
                    if topic_lower in (getattr(i, 'description', '') or '').lower()
                    or topic_lower in (getattr(i, 'issue_type', '') or '').lower()
                ]
                result_parts.append(f"- **Keyword matches found:** {len(matched)}")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error finding similar issues: {e}")
        return f"Error finding similar issues: {str(e)}"


# ─────────── CITY STATUS DASHBOARD ───────────
# Aggregated city status for the "city pulse" dashboard experience
# See: docs/critical/CIVIC_DASHBOARD_VISION.md

@mcp.tool()
def city_pulse(
    jurisdiction: Optional[str] = None,
    days_ahead: int = 7,
    days_back: int = 30,
) -> dict:
    """
    Get a comprehensive snapshot of city activity for dashboard display.

    Returns structured data about what's being decided, what just happened,
    and community activity patterns. Designed for both AI-native rendering
    (Claude artifacts, ChatGPT canvas) and web dashboard display.

    IMPORTANT: Meeting dates include the day of week (e.g., "Mon, Feb 02").
    Always use the day of week exactly as provided - do not recalculate it.

    Args:
        jurisdiction: City identifier (default: san-rafael)
        days_ahead: Days to look ahead for upcoming decisions (default: 7)
        days_back: Days to look back for recent outcomes (default: 30)

    Returns:
        Dictionary with:
        - decisions_this_week: Upcoming meetings and key agenda items
        - recent_outcomes: Decisions made in the past N days
        - community_pulse: Issue patterns and activity levels
        - visualization_hints: Suggestions for rendering
        - narrative_hints: Key insights for LLM summarization

    Example:
        >>> city_pulse()
        # Returns city status snapshot for San Rafael
        >>> city_pulse(days_ahead=14)
        # Looks two weeks ahead for upcoming decisions
    """
    logger.info(f"Getting city pulse: jurisdiction={jurisdiction}, days_ahead={days_ahead}, days_back={days_back}")

    if civicos_client is None:
        return {"error": "Civic client not initialized. Check server configuration."}

    jid = jurisdiction or civicos_client.jurisdiction
    storage = civicos_client._storage
    now = datetime.now()

    result = {
        "jurisdiction": jid,
        "generated_at": now.isoformat(),
        "decisions_this_week": [],
        "recent_outcomes": [],
        "community_pulse": {},
        "visualization_hints": [],
        "narrative_hints": {
            "notable": [],
            "patterns": [],
        },
    }

    try:
        # ─── UPCOMING DECISIONS ───
        # Show meetings in a window around now: recent past + upcoming future.
        # This gives a "what's happening" view even between meeting weeks.
        meetings = storage.get_meetings(
            jid,
            since=now,
            until=now + timedelta(days=days_ahead),
            limit=20
        )

        # Determine meeting status for labeling
        meetings_label = "upcoming"  # "upcoming", "recent", "historical"
        if not meetings:
            # No future meetings — show recent past (last 14 days)
            meetings = storage.get_meetings(
                jid,
                since=now - timedelta(days=14),
                until=now,
                limit=10
            )
            if meetings:
                meetings_label = "recent"
                # Show most recent first for past meetings
                meetings = list(reversed(meetings))
            else:
                # No meetings in last 14 days — show most recent from last 90 days
                meetings = storage.get_meetings(
                    jid,
                    since=now - timedelta(days=90),
                    until=now,
                    limit=10
                )
                meetings_label = "historical"
                meetings = list(reversed(meetings))

        upcoming = []
        for m in meetings:
            meeting_datetime = m.get('meeting_datetime')
            if meeting_datetime:
                # Format date nicely
                if hasattr(meeting_datetime, 'strftime'):
                    date_str = meeting_datetime.strftime("%a, %b %d")
                    time_str = meeting_datetime.strftime("%I:%M %p").lstrip('0')
                else:
                    date_str = str(meeting_datetime)[:10]
                    time_str = ""

                meeting_id = m.get('id')
                upcoming.append({
                    "id": meeting_id,
                    "title": m.get('title') or m.get('body') or 'Meeting',
                    "date": date_str,
                    "time": time_str,
                    "meeting_type": m.get('meeting_type', 'meeting'),
                    "agenda_url": m.get('agenda_url'),
                    "web_app_url": _generate_web_app_url('event', meeting_id) if meeting_id else None,
                    "_is_historical": meetings_label == "historical",
                })

        result["decisions_this_week"] = upcoming
        result["_meetings_are_historical"] = meetings_label == "historical"
        result["_meetings_label"] = meetings_label

        if upcoming:
            if meetings_label == "upcoming":
                result["narrative_hints"]["notable"].append(
                    f"{len(upcoming)} meeting(s) scheduled in the next {days_ahead} days"
                )
            elif meetings_label == "recent":
                result["narrative_hints"]["notable"].append(
                    f"{len(upcoming)} recent meeting(s) in the past 2 weeks (no upcoming meetings scheduled)"
                )
            else:
                result["narrative_hints"]["notable"].append(
                    f"Showing {len(upcoming)} most recent meetings (data may not be current)"
                )

        # ─── RECENT OUTCOMES ───
        # Get decisions from the past N days
        since_date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
        decisions = storage.get_decisions(jid, since=since_date, limit=10)

        # Fallback: if no recent decisions, show most recent regardless of date
        show_historical_decisions = False
        if not decisions:
            decisions = storage.get_decisions(jid, limit=5)
            show_historical_decisions = True

        outcomes = []
        outcome_types = Counter()
        for d in decisions:
            outcome = d.get('outcome') or d.get('status') or 'decided'
            outcome_types[outcome] += 1

            decision_date = d.get('decision_date') or d.get('meeting_datetime')
            if decision_date and hasattr(decision_date, 'strftime'):
                date_str = decision_date.strftime("%b %d")
            else:
                date_str = str(decision_date)[:10] if decision_date else "Recent"

            decision_id = d.get('id')
            outcomes.append({
                "id": decision_id,
                "title": d.get('title') or d.get('item_title') or 'Decision',
                "outcome": outcome,
                "date": date_str,
                "topics": d.get('topics', []),
                "web_app_url": _generate_web_app_url('event', decision_id) if decision_id else None,
            })

        result["recent_outcomes"] = outcomes
        result["_decisions_are_historical"] = show_historical_decisions

        if outcomes:
            # Summarize outcomes
            top_outcome = outcome_types.most_common(1)[0] if outcome_types else None
            if top_outcome:
                if show_historical_decisions:
                    result["narrative_hints"]["notable"].append(
                        f"Showing {len(outcomes)} most recent decisions"
                    )
                else:
                    result["narrative_hints"]["notable"].append(
                        f"{len(outcomes)} decisions in the past {days_back} days"
                    )

        # ─── COMMUNITY PULSE ───
        # Get issue patterns (311/SeeClickFix)
        try:
            issues = storage.get_issues(jurisdiction_id=jid, limit=500)

            if issues:
                # Aggregate by type
                type_counts = Counter()
                status_counts = Counter()
                recent_count = 0

                for issue in issues:
                    issue_type = issue.get('issue_type') or issue.get('category') or 'Other'
                    type_counts[issue_type] += 1

                    status = issue.get('status') or 'unknown'
                    status_counts[status] += 1

                    # Count issues from last 30 days
                    created = issue.get('created_at')
                    if created:
                        try:
                            if isinstance(created, str):
                                created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                            else:
                                created_dt = created
                            if created_dt.replace(tzinfo=None) > now - timedelta(days=30):
                                recent_count += 1
                        except:
                            pass

                result["community_pulse"] = {
                    "total_issues": len(issues),
                    "recent_30_days": recent_count,
                    "top_types": dict(type_counts.most_common(5)),
                    "by_status": dict(status_counts),
                }

                # Calculate resolution rate
                resolved = status_counts.get('Closed', 0) + status_counts.get('closed', 0)
                if len(issues) > 0:
                    resolution_rate = round(resolved / len(issues) * 100, 1)
                    result["community_pulse"]["resolution_rate_pct"] = resolution_rate

                top_type = type_counts.most_common(1)[0] if type_counts else None
                if top_type:
                    result["narrative_hints"]["patterns"].append(
                        f"Top community concern: {top_type[0]} ({top_type[1]} reports)"
                    )
        except Exception as e:
            logger.warning(f"Could not get issue data for city_pulse: {e}")
            result["community_pulse"] = {"error": str(e)}

        # ─── VISUALIZATION HINTS ───
        result["visualization_hints"] = [
            {
                "type": "calendar_heatmap",
                "title": "Upcoming Participation Opportunities",
                "data_key": "decisions_this_week",
                "x": "date",
            },
            {
                "type": "outcome_summary",
                "title": "Recent Decisions",
                "data_key": "recent_outcomes",
            },
            {
                "type": "donut_chart",
                "title": "Community Concerns by Type",
                "data_key": "community_pulse.top_types",
            },
        ]

    except Exception as e:
        logger.error(f"Error generating city pulse: {e}")
        result["error"] = str(e)

    return result


def _format_city_pulse_for_display(pulse: dict) -> str:
    """Format city_pulse data as readable markdown for get_started."""
    parts = []

    jid = pulse.get('jurisdiction', 'your city')
    jid_display = jid.replace('city-', '').replace('-', ' ').title()

    # Check if data is historical (fallback mode)
    is_historical = pulse.get('_meetings_are_historical', False)

    # Header
    if is_historical:
        parts.append(f"# {jid_display} Overview")
        parts.append("*Showing recent activity (live data sync pending)*")
    else:
        parts.append(f"# {jid_display} This Week")
    parts.append("")

    # Upcoming decisions
    upcoming = pulse.get('decisions_this_week', [])
    if upcoming:
        if is_historical:
            parts.append("## Recent Meetings")
        else:
            parts.append("## Deciding Soon")
        for m in upcoming[:3]:
            date_time = f"{m['date']}"
            if m.get('time') and m['time'] != "12:00 AM":
                date_time += f" at {m['time']}"
            parts.append(f"- **{m['title']}** - {date_time}")
        if len(upcoming) > 3:
            parts.append(f"  *...and {len(upcoming) - 3} more meetings*")
        parts.append("")
    else:
        parts.append("## Meetings")
        parts.append("*No meeting data available*")
        parts.append("")

    # Recent outcomes
    outcomes = pulse.get('recent_outcomes', [])
    if outcomes:
        if pulse.get('_decisions_are_historical', False):
            parts.append("## Recent Decisions")
        else:
            parts.append("## Just Decided")
        for d in outcomes[:3]:
            outcome_emoji = {
                'approved': '✓',
                'denied': '✗',
                'continued': '→',
                'tabled': '⏸',
            }.get(d['outcome'].lower(), '•')
            parts.append(f"- {outcome_emoji} **{d['title']}** ({d['outcome']}) - {d['date']}")
        if len(outcomes) > 3:
            parts.append(f"  *...and {len(outcomes) - 3} more decisions*")
        parts.append("")

    # Community pulse
    community = pulse.get('community_pulse', {})
    if community and not community.get('error'):
        parts.append("## Community Pulse")
        top_types = community.get('top_types', {})
        if top_types:
            top_items = list(top_types.items())[:3]
            concerns = ", ".join([f"{t} ({c})" for t, c in top_items])
            parts.append(f"Top concerns: {concerns}")

        resolution = community.get('resolution_rate_pct')
        if resolution is not None:
            parts.append(f"Issue resolution rate: {resolution}%")
        parts.append("")

    return "\n".join(parts)


# ─────────── 311 DATA ANALYSIS TOOLS ───────────
# These tools enable AI assistants to analyze 311/SeeClickFix issue data
# for pattern discovery, trend analysis, and community insights

@mcp.tool()
def get_issue_analytics(
    date_range: Optional[str] = None,
) -> str:
    """
    Get aggregate statistics about 311/SeeClickFix issues for analysis.

    Returns pre-computed statistics including counts by type, status, location,
    and time. Use this for high-level understanding before drilling down.

    Args:
        date_range: Optional filter - "2024", "2024-Q4", "last_90_days", "last_year"

    Returns:
        Formatted analytics including:
        - Total counts and resolution rates
        - Breakdown by issue type
        - Breakdown by status
        - Top corridors/streets
        - Temporal trends (by year/month)
        - Seasonal patterns

    Example:
        >>> get_issue_analytics()
        # Returns full analytics for all 311 issues
        >>> get_issue_analytics(date_range="2024")
        # Returns analytics filtered to 2024
    """
    logger.info(f"Getting issue analytics: date_range={date_range}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    try:
        storage = civicos_client._storage
        jurisdiction = civicos_client.jurisdiction

        # Get all issues (up to reasonable limit for analysis)
        all_issues = storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        if not all_issues:
            return f"No 311 issues found for {jurisdiction}."

        # Parse date filter
        from datetime import datetime, timedelta
        from collections import Counter

        filtered_issues = all_issues
        filter_description = "All time"

        if date_range:
            now = datetime.now()
            if date_range == "last_90_days":
                cutoff = now - timedelta(days=90)
                filter_description = "Last 90 days"
            elif date_range == "last_year":
                cutoff = now - timedelta(days=365)
                filter_description = "Last 12 months"
            elif date_range.startswith("20") and len(date_range) == 4:
                # Year filter like "2024"
                year = int(date_range)
                cutoff = datetime(year, 1, 1)
                end = datetime(year + 1, 1, 1)
                filter_description = f"Year {year}"
                filtered_issues = [
                    i for i in all_issues
                    if i.get('created_at') and cutoff <= _parse_date(i.get('created_at')) < end
                ]
            elif "-Q" in date_range:
                # Quarter filter like "2024-Q4"
                year, q = date_range.split("-Q")
                quarter = int(q)
                start_month = (quarter - 1) * 3 + 1
                cutoff = datetime(int(year), start_month, 1)
                end_month = start_month + 3
                if end_month > 12:
                    end = datetime(int(year) + 1, 1, 1)
                else:
                    end = datetime(int(year), end_month, 1)
                filter_description = f"{year} Q{quarter}"
                filtered_issues = [
                    i for i in all_issues
                    if i.get('created_at') and cutoff <= _parse_date(i.get('created_at')) < end
                ]

            if date_range in ("last_90_days", "last_year"):
                filtered_issues = [
                    i for i in all_issues
                    if i.get('created_at') and _parse_date(i.get('created_at')) >= cutoff
                ]

        issues = filtered_issues
        total = len(issues)

        if total == 0:
            return f"No issues found for date range: {filter_description}"

        # Calculate statistics
        by_status = Counter(i.get('status', 'unknown') for i in issues)
        by_type = Counter(i.get('issue_type', 'Unknown') for i in issues)

        # Extract street from address
        def extract_street(addr):
            if not addr:
                return "Unknown"
            # Simple extraction: take the street name portion
            parts = addr.split(',')[0].split()
            # Remove house number if present
            if parts and parts[0].isdigit():
                parts = parts[1:]
            return ' '.join(parts[:3]) if parts else "Unknown"

        by_street = Counter(extract_street(i.get('address')) for i in issues)

        # By year
        by_year = Counter()
        by_month = Counter()
        for i in issues:
            created = i.get('created_at')
            if created:
                dt = _parse_date(created)
                if dt:
                    by_year[dt.year] += 1
                    by_month[dt.strftime('%Y-%m')] += 1

        # Resolution rate
        closed_statuses = {'closed', 'resolved', 'archived'}
        resolved = sum(1 for i in issues if i.get('status', '').lower() in closed_statuses)
        resolution_rate = (resolved / total * 100) if total > 0 else 0

        # Build response
        result_parts = []
        result_parts.append(f"# 311 Issue Analytics: {jurisdiction}")
        result_parts.append(f"**Period:** {filter_description}")
        result_parts.append(f"**Total Issues:** {total:,}")
        result_parts.append(f"**Resolution Rate:** {resolution_rate:.1f}%")
        result_parts.append("")

        # By Status
        result_parts.append("## By Status")
        for status, count in by_status.most_common():
            pct = count / total * 100
            result_parts.append(f"- **{status}:** {count:,} ({pct:.1f}%)")
        result_parts.append("")

        # By Type (top 10)
        result_parts.append("## By Issue Type (Top 10)")
        for issue_type, count in by_type.most_common(10):
            pct = count / total * 100
            result_parts.append(f"- **{issue_type}:** {count:,} ({pct:.1f}%)")
        result_parts.append("")

        # By Street (top 10)
        result_parts.append("## Top Streets/Corridors")
        for street, count in by_street.most_common(10):
            if street != "Unknown":
                result_parts.append(f"- **{street}:** {count:,} issues")
        result_parts.append("")

        # By Year
        if by_year:
            result_parts.append("## By Year")
            for year in sorted(by_year.keys()):
                result_parts.append(f"- **{year}:** {by_year[year]:,}")
            result_parts.append("")

        # Recent months (last 6)
        if by_month:
            result_parts.append("## Recent Months")
            recent_months = sorted(by_month.keys())[-6:]
            for month in recent_months:
                result_parts.append(f"- **{month}:** {by_month[month]:,}")
            result_parts.append("")

        result_parts.append("---")
        result_parts.append("*Use `query_issue_data()` for detailed breakdowns with custom filters.*")
        result_parts.append("*Use `get_issue_sample()` to see actual issue descriptions.*")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error getting issue analytics: {e}")
        return f"Error getting issue analytics: {str(e)}"


def _parse_date(date_val) -> Optional[datetime]:
    """Helper to parse various date formats to datetime."""
    from datetime import datetime
    if date_val is None:
        return None
    if isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, str):
        # Try common formats
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y-%m-%dT%H:%M:%S.%f'):
            try:
                return datetime.strptime(date_val[:19], fmt[:len(date_val[:19])])
            except ValueError:
                continue
        # Try with timezone suffix
        try:
            return datetime.fromisoformat(date_val.replace('Z', '+00:00'))
        except ValueError:
            pass
    return None


@mcp.tool()
def query_issue_data(
    group_by: str = "type",
    filter_type: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_street: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 50,
) -> str:
    """
    Query 311 issue data with flexible grouping and filtering.

    Enables analysis queries like:
    - "Issues on Lincoln Ave grouped by type"
    - "Pothole complaints by month"
    - "Open issues by street"

    Args:
        group_by: How to group results - "type", "status", "street", "month", "year"
        filter_type: Filter by issue type (e.g., "pothole", "graffiti")
        filter_status: Filter by status (e.g., "open", "closed", "acknowledged")
        filter_street: Filter by street name (partial match)
        date_from: Start date (YYYY-MM-DD format)
        date_to: End date (YYYY-MM-DD format)
        limit: Max results per group (default: 50)

    Returns:
        Grouped and filtered issue data suitable for analysis

    Example:
        >>> query_issue_data(group_by="type", filter_street="Lincoln")
        # Issues on Lincoln Ave broken down by type
        >>> query_issue_data(group_by="month", filter_type="pothole")
        # Pothole complaints by month
    """
    logger.info(f"Querying issue data: group_by={group_by}, type={filter_type}, street={filter_street}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate inputs
    input_data = {'group_by': group_by}
    if filter_type:
        input_data['filter_type'] = filter_type
    if filter_status:
        input_data['filter_status'] = filter_status
    if filter_street:
        input_data['filter_street'] = filter_street

    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    if not is_valid:
        logger.error(f"Input validation failed: {error_message}")
        return f"Error: Invalid input - {error_message}"

    try:
        from collections import Counter
        from datetime import datetime

        storage = civicos_client._storage
        jurisdiction = civicos_client.jurisdiction

        # Get issues with optional status filter
        all_issues = storage.get_issues(
            jurisdiction_id=jurisdiction,
            status=filter_status,
            limit=5000,
        )

        if not all_issues:
            return f"No issues found for {jurisdiction}."

        # Apply filters
        issues = all_issues

        if filter_type:
            filter_type_lower = filter_type.lower()
            issues = [
                i for i in issues
                if filter_type_lower in (i.get('issue_type', '') or '').lower()
            ]

        if filter_street:
            filter_street_lower = filter_street.lower()
            issues = [
                i for i in issues
                if filter_street_lower in (i.get('address', '') or '').lower()
            ]

        if date_from:
            try:
                from_dt = datetime.strptime(date_from, '%Y-%m-%d')
                issues = [
                    i for i in issues
                    if i.get('created_at') and _parse_date(i.get('created_at')) >= from_dt
                ]
            except ValueError:
                pass

        if date_to:
            try:
                to_dt = datetime.strptime(date_to, '%Y-%m-%d')
                issues = [
                    i for i in issues
                    if i.get('created_at') and _parse_date(i.get('created_at')) <= to_dt
                ]
            except ValueError:
                pass

        if not issues:
            return "No issues match the specified filters."

        # Group data
        def extract_street(addr):
            if not addr:
                return "Unknown"
            parts = addr.split(',')[0].split()
            if parts and parts[0].isdigit():
                parts = parts[1:]
            return ' '.join(parts[:3]) if parts else "Unknown"

        grouped = Counter()
        details = {}  # Store sample issues per group

        for issue in issues:
            if group_by == "type":
                key = issue.get('issue_type', 'Unknown')
            elif group_by == "status":
                key = issue.get('status', 'unknown')
            elif group_by == "street":
                key = extract_street(issue.get('address'))
            elif group_by == "month":
                created = issue.get('created_at')
                if created:
                    dt = _parse_date(created)
                    key = dt.strftime('%Y-%m') if dt else 'Unknown'
                else:
                    key = 'Unknown'
            elif group_by == "year":
                created = issue.get('created_at')
                if created:
                    dt = _parse_date(created)
                    key = str(dt.year) if dt else 'Unknown'
                else:
                    key = 'Unknown'
            else:
                key = issue.get('issue_type', 'Unknown')

            grouped[key] += 1

            # Store first few examples per group
            if key not in details:
                details[key] = []
            if len(details[key]) < 3:  # Keep 3 examples per group
                details[key].append({
                    'description': (issue.get('description') or '')[:100],
                    'address': issue.get('address', 'N/A'),
                    'status': issue.get('status', 'N/A'),
                })

        # Build response
        result_parts = []
        result_parts.append(f"# Issue Query Results")

        # Describe filters
        filter_desc = []
        if filter_type:
            filter_desc.append(f"Type contains '{filter_type}'")
        if filter_status:
            filter_desc.append(f"Status = '{filter_status}'")
        if filter_street:
            filter_desc.append(f"Street contains '{filter_street}'")
        if date_from or date_to:
            filter_desc.append(f"Date range: {date_from or 'start'} to {date_to or 'now'}")

        if filter_desc:
            result_parts.append(f"**Filters:** {', '.join(filter_desc)}")
        result_parts.append(f"**Grouped by:** {group_by}")
        result_parts.append(f"**Total matching issues:** {len(issues):,}")
        result_parts.append("")

        # Results table
        result_parts.append(f"## Results by {group_by.title()}")
        result_parts.append("")

        sorted_groups = sorted(grouped.items(), key=lambda x: (-x[1], x[0]))[:limit]

        for key, count in sorted_groups:
            pct = count / len(issues) * 100
            result_parts.append(f"### {key}: {count:,} ({pct:.1f}%)")

            # Show examples
            if details.get(key):
                for ex in details[key]:
                    desc = ex['description'] or 'No description'
                    result_parts.append(f"- *{desc}...* ({ex['address']})")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error querying issue data: {e}")
        return f"Error querying issue data: {str(e)}"


@mcp.tool()
def get_issue_sample(
    sample_size: int = 30,
    filter_type: Optional[str] = None,
    filter_status: Optional[str] = None,
    filter_street: Optional[str] = None,
    random_sample: bool = True,
) -> str:
    """
    Get a sample of raw 311 issues for pattern analysis.

    Returns individual issue records with full descriptions. Use this when you
    need to analyze actual content (descriptions, specific complaints) rather
    than just aggregate statistics.

    Limited to manage token usage - use filters to target specific segments.

    Args:
        sample_size: Number of issues to return (max 50, default 30)
        filter_type: Filter by issue type (e.g., "traffic", "pothole")
        filter_status: Filter by status (e.g., "open")
        filter_street: Filter by street name (partial match)
        random_sample: If True, return random sample; if False, return most recent

    Returns:
        Sample of issue records with full details for content analysis

    Example:
        >>> get_issue_sample(filter_type="traffic", sample_size=20)
        # Get 20 random traffic-related issues to analyze
        >>> get_issue_sample(filter_street="4th St", random_sample=False)
        # Get most recent issues on 4th Street
    """
    logger.info(f"Getting issue sample: size={sample_size}, type={filter_type}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # Limit sample size
    sample_size = min(sample_size, 50)

    # SECURITY: Validate inputs
    input_data = {}
    if filter_type:
        input_data['filter_type'] = filter_type
    if filter_status:
        input_data['filter_status'] = filter_status
    if filter_street:
        input_data['filter_street'] = filter_street

    if input_data:
        is_valid, sanitized_data, error_message = validate_civic_input(input_data)
        if not is_valid:
            logger.error(f"Input validation failed: {error_message}")
            return f"Error: Invalid input - {error_message}"

    try:
        import random

        storage = civicos_client._storage
        jurisdiction = civicos_client.jurisdiction

        # Get issues
        all_issues = storage.get_issues(
            jurisdiction_id=jurisdiction,
            status=filter_status,
            limit=2000,
        )

        if not all_issues:
            return f"No issues found for {jurisdiction}."

        # Apply filters
        issues = all_issues

        if filter_type:
            filter_type_lower = filter_type.lower()
            issues = [
                i for i in issues
                if filter_type_lower in (i.get('issue_type', '') or '').lower()
                or filter_type_lower in (i.get('description', '') or '').lower()
            ]

        if filter_street:
            filter_street_lower = filter_street.lower()
            issues = [
                i for i in issues
                if filter_street_lower in (i.get('address', '') or '').lower()
            ]

        if not issues:
            return "No issues match the specified filters."

        # Sample or get most recent
        if random_sample and len(issues) > sample_size:
            sample = random.sample(issues, sample_size)
        else:
            # Sort by date (most recent first) and take top N
            sorted_issues = sorted(
                issues,
                key=lambda x: x.get('created_at') or '',
                reverse=True
            )
            sample = sorted_issues[:sample_size]

        # Build response
        result_parts = []
        result_parts.append(f"# Issue Sample ({len(sample)} of {len(issues):,} matching)")

        # Describe filters
        filter_desc = []
        if filter_type:
            filter_desc.append(f"Type: '{filter_type}'")
        if filter_status:
            filter_desc.append(f"Status: '{filter_status}'")
        if filter_street:
            filter_desc.append(f"Street: '{filter_street}'")

        if filter_desc:
            result_parts.append(f"**Filters:** {', '.join(filter_desc)}")
        result_parts.append(f"**Sample type:** {'Random' if random_sample else 'Most recent'}")
        result_parts.append("")

        result_parts.append("---")
        result_parts.append("")

        for i, issue in enumerate(sample, 1):
            issue_id = issue.get('id')
            issue_type = issue.get('issue_type', 'Unknown')
            status = issue.get('status', 'unknown')
            address = issue.get('address', 'N/A')
            created = issue.get('created_at', 'N/A')
            description = issue.get('description', 'No description provided')
            # Get external URL from provider_metadata
            metadata = issue.get('provider_metadata') or {}
            html_url = metadata.get('html_url')
            # Generate internal web app link
            web_app_url = _generate_web_app_url('issue', issue_id) if issue_id else ""

            # Parse date for cleaner display
            if created and created != 'N/A':
                dt = _parse_date(created)
                created = dt.strftime('%Y-%m-%d') if dt else str(created)[:10]

            # Format header - prefer web app link over external
            if web_app_url:
                result_parts.append(f"## {i}. [{issue_type}]({web_app_url})")
            elif html_url:
                result_parts.append(f"## {i}. [{issue_type}]({html_url})")
            else:
                result_parts.append(f"## {i}. {issue_type}")
            result_parts.append(f"**Status:** {status} | **Date:** {created}")
            result_parts.append(f"**Location:** {address}")
            # Add links line if we have URLs
            links = []
            if web_app_url:
                links.append(f"[Open in CivicOS]({web_app_url})")
            if html_url:
                links.append(f"[View on SeeClickFix]({html_url})")
            if links:
                result_parts.append(f"**Links:** {' | '.join(links)}")
            result_parts.append("")
            result_parts.append(f"> {description[:400]}{'...' if len(description) > 400 else ''}")
            result_parts.append("")

        result_parts.append("---")
        result_parts.append("*Analyze descriptions for themes, patterns, or specific concerns.*")
        result_parts.append("*Use `query_issue_data()` for aggregate breakdowns.*")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error getting issue sample: {e}")
        return f"Error getting issue sample: {str(e)}"


@mcp.tool()
def get_issue_resolution_stats(
    issue_type: Optional[str] = None,
    zip_code: Optional[str] = None,
) -> str:
    """
    Get resolution statistics for 311 issues.

    Shows how responsive the city is: resolution rates, average time to close,
    and performance by issue type. Use this for accountability analysis.

    Args:
        issue_type: Filter by issue type (e.g., "pothole", "graffiti")
        zip_code: Filter by zip code (e.g., "94901")

    Returns:
        Resolution metrics including:
        - Overall resolution rate
        - Average days to resolution
        - Resolution rate by issue type
        - Best/worst performing categories

    Example:
        >>> get_issue_resolution_stats()
        # Overall city responsiveness
        >>> get_issue_resolution_stats(issue_type="pothole")
        # How quickly are potholes fixed?
    """
    logger.info(f"Getting resolution stats: type={issue_type}, zip={zip_code}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    try:
        from datetime import datetime
        from collections import defaultdict

        storage = civicos_client._storage
        jurisdiction = civicos_client.jurisdiction

        all_issues = storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        if not all_issues:
            return f"No issues found for {jurisdiction}."

        # Apply filters
        issues = all_issues

        if issue_type:
            issue_type_lower = issue_type.lower()
            issues = [
                i for i in issues
                if issue_type_lower in (i.get('issue_type', '') or '').lower()
            ]

        if zip_code:
            issues = [
                i for i in issues
                if zip_code in (i.get('address', '') or '')
            ]

        if not issues:
            return "No issues match the specified filters."

        total = len(issues)

        # Calculate resolution stats
        closed_statuses = {'closed', 'resolved', 'archived'}
        resolved_issues = [
            i for i in issues
            if i.get('status', '').lower() in closed_statuses
        ]
        resolved_count = len(resolved_issues)
        resolution_rate = (resolved_count / total * 100) if total > 0 else 0

        # Calculate time to resolution for closed issues
        resolution_times = []
        for issue in resolved_issues:
            created = issue.get('created_at')
            updated = issue.get('updated_at') or issue.get('closed_at')
            if created and updated:
                created_dt = _parse_date(created)
                updated_dt = _parse_date(updated)
                if created_dt and updated_dt and updated_dt > created_dt:
                    days = (updated_dt - created_dt).days
                    if days >= 0 and days < 365 * 5:  # Sanity check
                        resolution_times.append(days)

        avg_days = sum(resolution_times) / len(resolution_times) if resolution_times else None
        median_days = sorted(resolution_times)[len(resolution_times) // 2] if resolution_times else None

        # Resolution rate by type
        type_stats = defaultdict(lambda: {'total': 0, 'resolved': 0})
        for issue in issues:
            issue_t = issue.get('issue_type', 'Unknown')
            type_stats[issue_t]['total'] += 1
            if issue.get('status', '').lower() in closed_statuses:
                type_stats[issue_t]['resolved'] += 1

        # Build response
        result_parts = []
        result_parts.append(f"# Issue Resolution Statistics")

        filter_desc = []
        if issue_type:
            filter_desc.append(f"Type: '{issue_type}'")
        if zip_code:
            filter_desc.append(f"Zip: {zip_code}")
        if filter_desc:
            result_parts.append(f"**Filters:** {', '.join(filter_desc)}")

        result_parts.append(f"**Total Issues:** {total:,}")
        result_parts.append("")

        result_parts.append("## Overall Resolution")
        result_parts.append(f"- **Resolved:** {resolved_count:,} ({resolution_rate:.1f}%)")
        result_parts.append(f"- **Still Open:** {total - resolved_count:,}")
        if avg_days is not None:
            result_parts.append(f"- **Avg Days to Resolution:** {avg_days:.1f}")
        if median_days is not None:
            result_parts.append(f"- **Median Days to Resolution:** {median_days}")
        result_parts.append("")

        # Best and worst performing types
        type_rates = [
            (t, stats['resolved'] / stats['total'] * 100 if stats['total'] > 0 else 0, stats['total'])
            for t, stats in type_stats.items()
            if stats['total'] >= 5  # Min sample size
        ]

        if type_rates:
            sorted_types = sorted(type_rates, key=lambda x: x[1], reverse=True)

            result_parts.append("## Best Resolution Rates")
            for t, rate, count in sorted_types[:5]:
                result_parts.append(f"- **{t}:** {rate:.1f}% resolved ({count} issues)")
            result_parts.append("")

            result_parts.append("## Lowest Resolution Rates")
            for t, rate, count in sorted_types[-5:]:
                result_parts.append(f"- **{t}:** {rate:.1f}% resolved ({count} issues)")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error getting resolution stats: {e}")
        return f"Error getting resolution stats: {str(e)}"


@mcp.tool()
def find_issues_near_address(
    address: str,
    radius_miles: float = 0.25,
    issue_type: Optional[str] = None,
    limit: int = 30,
) -> str:
    """
    Find 311 issues near a specific address.

    Geocodes the address and finds issues within the specified radius.
    Useful for discovering neighborhood concerns around your location.

    Args:
        address: Street address to search near (e.g., "123 4th St, San Rafael, CA")
        radius_miles: Search radius in miles (default: 0.25 = ~2 blocks)
        issue_type: Filter by issue type (e.g., "traffic", "pothole")
        limit: Maximum results (default: 30)

    Returns:
        Issues near the address sorted by distance

    Example:
        >>> find_issues_near_address("1400 Fifth Ave, San Rafael, CA")
        # Issues within 2 blocks of City Hall
        >>> find_issues_near_address("123 4th St", radius_miles=0.5, issue_type="parking")
        # Parking issues within half mile
    """
    logger.info(f"Finding issues near: {address}, radius={radius_miles}mi")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {'address': address}
    if issue_type:
        input_data['issue_type'] = issue_type
    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    if not is_valid:
        return f"Error: Invalid input - {error_message}"

    try:
        import os
        import math

        # Geocode the address using Google Maps API
        api_key = os.getenv('GOOGLE_MAPS_API_KEY')
        if not api_key:
            return "Error: Geocoding not available (GOOGLE_MAPS_API_KEY not set)."

        import urllib.request
        import urllib.parse
        import json

        encoded_address = urllib.parse.quote(address)
        geocode_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"

        with urllib.request.urlopen(geocode_url, timeout=10) as response:
            geocode_data = json.loads(response.read().decode())

        if geocode_data.get('status') != 'OK' or not geocode_data.get('results'):
            return f"Could not geocode address: {address}. Try a more complete address."

        location = geocode_data['results'][0]['geometry']['location']
        center_lat = location['lat']
        center_lng = location['lng']
        formatted_address = geocode_data['results'][0]['formatted_address']

        # Get all issues with coordinates
        storage = civicos_client._storage
        jurisdiction = civicos_client.jurisdiction
        all_issues = storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        # Filter to issues with coordinates
        issues_with_coords = [
            i for i in all_issues
            if i.get('lat') and i.get('lng')
        ]

        if issue_type:
            issue_type_lower = issue_type.lower()
            issues_with_coords = [
                i for i in issues_with_coords
                if issue_type_lower in (i.get('issue_type', '') or '').lower()
            ]

        # Haversine distance calculation
        def haversine(lat1, lon1, lat2, lon2):
            R = 3959  # Earth radius in miles
            lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            return R * c

        # Calculate distance for each issue
        issues_with_distance = []
        for issue in issues_with_coords:
            try:
                issue_lat = float(issue['lat'])
                issue_lng = float(issue['lng'])
                distance = haversine(center_lat, center_lng, issue_lat, issue_lng)
                if distance <= radius_miles:
                    issues_with_distance.append((issue, distance))
            except (ValueError, TypeError):
                continue

        # Sort by distance
        issues_with_distance.sort(key=lambda x: x[1])
        nearby = issues_with_distance[:limit]

        # Build response
        result_parts = []
        result_parts.append(f"# Issues Near {formatted_address}")
        result_parts.append(f"**Search Radius:** {radius_miles} miles")
        if issue_type:
            result_parts.append(f"**Filter:** {issue_type}")
        result_parts.append(f"**Found:** {len(nearby)} issues")
        result_parts.append("")

        if not nearby:
            result_parts.append("No issues found within the search radius.")
            result_parts.append("Try increasing the radius or removing filters.")
            return "\n".join(result_parts)

        # Group by type for summary
        from collections import Counter
        type_counts = Counter(i[0].get('issue_type', 'Unknown') for i in nearby)

        result_parts.append("## Summary by Type")
        for issue_t, count in type_counts.most_common(5):
            result_parts.append(f"- **{issue_t}:** {count}")
        result_parts.append("")

        result_parts.append("## Nearby Issues")
        for issue, distance in nearby[:20]:
            issue_type_str = issue.get('issue_type', 'Unknown')
            status = issue.get('status', 'unknown')
            addr = issue.get('address', 'N/A')
            desc = (issue.get('description') or '')[:100]

            result_parts.append(f"### {issue_type_str} ({distance:.2f} mi)")
            result_parts.append(f"**Status:** {status} | **Location:** {addr}")
            if desc:
                result_parts.append(f"> {desc}...")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error finding nearby issues: {e}")
        return f"Error finding nearby issues: {str(e)}"


@mcp.tool()
def detect_trends(
    lookback_months: int = 6,
    min_change_pct: float = 20.0,
    zip_code: Optional[str] = None,
) -> str:
    """
    Detect significant trends in 311 issue patterns.

    Compares recent period to previous period to identify what's getting
    better or worse. Useful for spotting emerging problems.

    Args:
        lookback_months: Compare last N months to previous N months (default: 6)
        min_change_pct: Minimum % change to report as significant (default: 20)
        zip_code: Filter to specific zip code

    Returns:
        Trends showing increasing and decreasing issue types

    Example:
        >>> detect_trends()
        # What's changed in the last 6 months?
        >>> detect_trends(lookback_months=3, zip_code="94901")
        # Recent trends in downtown San Rafael
    """
    logger.info(f"Detecting trends: lookback={lookback_months}mo, zip={zip_code}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    try:
        from datetime import datetime, timedelta
        from collections import Counter

        storage = civicos_client._storage
        jurisdiction = civicos_client.jurisdiction

        all_issues = storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        if zip_code:
            all_issues = [
                i for i in all_issues
                if zip_code in (i.get('address', '') or '')
            ]

        if not all_issues:
            return "No issues found for analysis."

        # Define time periods
        now = datetime.now()
        recent_start = now - timedelta(days=lookback_months * 30)
        previous_start = recent_start - timedelta(days=lookback_months * 30)

        # Categorize issues by period
        recent_issues = []
        previous_issues = []

        for issue in all_issues:
            created = issue.get('created_at')
            if not created:
                continue
            dt = _parse_date(created)
            if not dt:
                continue

            if dt >= recent_start:
                recent_issues.append(issue)
            elif dt >= previous_start:
                previous_issues.append(issue)

        if not recent_issues and not previous_issues:
            return "Not enough historical data to detect trends."

        # Count by type
        recent_counts = Counter(i.get('issue_type', 'Unknown') for i in recent_issues)
        previous_counts = Counter(i.get('issue_type', 'Unknown') for i in previous_issues)

        # Calculate changes
        all_types = set(recent_counts.keys()) | set(previous_counts.keys())
        changes = []

        for issue_type in all_types:
            recent = recent_counts.get(issue_type, 0)
            previous = previous_counts.get(issue_type, 0)

            if previous > 0:
                pct_change = ((recent - previous) / previous) * 100
            elif recent > 0:
                pct_change = 100  # New issue type
            else:
                continue

            if abs(pct_change) >= min_change_pct and (recent >= 3 or previous >= 3):
                changes.append({
                    'type': issue_type,
                    'recent': recent,
                    'previous': previous,
                    'change': pct_change,
                })

        # Sort by magnitude of change
        increasing = sorted([c for c in changes if c['change'] > 0], key=lambda x: -x['change'])
        decreasing = sorted([c for c in changes if c['change'] < 0], key=lambda x: x['change'])

        # Build response
        result_parts = []
        result_parts.append(f"# Issue Trends Analysis")
        result_parts.append(f"**Period:** Last {lookback_months} months vs previous {lookback_months} months")
        if zip_code:
            result_parts.append(f"**Zip Code:** {zip_code}")
        result_parts.append(f"**Threshold:** Changes >= {min_change_pct}%")
        result_parts.append("")

        result_parts.append("## Overview")
        result_parts.append(f"- **Recent period:** {len(recent_issues):,} issues")
        result_parts.append(f"- **Previous period:** {len(previous_issues):,} issues")
        total_change = ((len(recent_issues) - len(previous_issues)) / len(previous_issues) * 100) if previous_issues else 0
        trend_arrow = "↑" if total_change > 0 else "↓" if total_change < 0 else "→"
        result_parts.append(f"- **Overall trend:** {trend_arrow} {abs(total_change):.1f}%")
        result_parts.append("")

        if increasing:
            result_parts.append("## 📈 Increasing Issues")
            for c in increasing[:7]:
                result_parts.append(f"- **{c['type']}:** {c['previous']} → {c['recent']} (+{c['change']:.0f}%)")
            result_parts.append("")

        if decreasing:
            result_parts.append("## 📉 Decreasing Issues")
            for c in decreasing[:7]:
                result_parts.append(f"- **{c['type']}:** {c['previous']} → {c['recent']} ({c['change']:.0f}%)")
            result_parts.append("")

        if not increasing and not decreasing:
            result_parts.append("No significant trends detected with current thresholds.")
            result_parts.append("Try lowering min_change_pct or increasing lookback_months.")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error detecting trends: {e}")
        return f"Error detecting trends: {str(e)}"


@mcp.tool()
def find_repeat_issues(
    min_occurrences: int = 3,
    zip_code: Optional[str] = None,
    issue_type: Optional[str] = None,
) -> str:
    """
    Find locations with recurring issues (same problem, multiple reports).

    Identifies systemic problems that aren't being permanently fixed.
    Useful for advocacy and accountability.

    Args:
        min_occurrences: Minimum reports at same location (default: 3)
        zip_code: Filter to specific zip code
        issue_type: Filter by issue type

    Returns:
        Locations with repeat issues, sorted by frequency

    Example:
        >>> find_repeat_issues()
        # Find problem locations across the city
        >>> find_repeat_issues(issue_type="pothole", min_occurrences=5)
        # Streets with persistent pothole problems
    """
    logger.info(f"Finding repeat issues: min={min_occurrences}, zip={zip_code}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    try:
        from collections import defaultdict

        storage = civicos_client._storage
        jurisdiction = civicos_client.jurisdiction

        all_issues = storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        # Apply filters
        issues = all_issues

        if zip_code:
            issues = [i for i in issues if zip_code in (i.get('address', '') or '')]

        if issue_type:
            issue_type_lower = issue_type.lower()
            issues = [
                i for i in issues
                if issue_type_lower in (i.get('issue_type', '') or '').lower()
            ]

        if not issues:
            return "No issues match the specified filters."

        # Group by normalized location
        def normalize_address(addr):
            if not addr:
                return None
            # Simple normalization: lowercase, remove extra spaces
            addr = ' '.join(addr.lower().split())
            # Remove apartment/unit numbers for grouping
            import re
            addr = re.sub(r'\s+(apt|unit|#|ste|suite)\s*\S*', '', addr)
            return addr[:50]  # Truncate for grouping

        location_issues = defaultdict(list)
        for issue in issues:
            addr = normalize_address(issue.get('address'))
            if addr:
                location_issues[addr].append(issue)

        # Find repeat locations
        repeats = [
            (addr, issues_list)
            for addr, issues_list in location_issues.items()
            if len(issues_list) >= min_occurrences
        ]

        # Sort by count
        repeats.sort(key=lambda x: -len(x[1]))

        # Build response
        result_parts = []
        result_parts.append(f"# Repeat Issue Locations")
        result_parts.append(f"**Minimum occurrences:** {min_occurrences}")
        if zip_code:
            result_parts.append(f"**Zip Code:** {zip_code}")
        if issue_type:
            result_parts.append(f"**Issue Type:** {issue_type}")
        result_parts.append(f"**Problem locations found:** {len(repeats)}")
        result_parts.append("")

        if not repeats:
            result_parts.append("No repeat issue locations found with current criteria.")
            result_parts.append("Try lowering min_occurrences.")
            return "\n".join(result_parts)

        for addr, issues_list in repeats[:15]:
            count = len(issues_list)
            # Get original address format from first issue
            original_addr = issues_list[0].get('address', addr)

            # Summarize issue types at this location
            from collections import Counter
            types = Counter(i.get('issue_type', 'Unknown') for i in issues_list)
            type_summary = ', '.join(f"{t} ({c})" for t, c in types.most_common(3))

            # Date range
            dates = [_parse_date(i.get('created_at')) for i in issues_list if i.get('created_at')]
            dates = [d for d in dates if d]
            if dates:
                date_range = f"{min(dates).strftime('%Y-%m')} to {max(dates).strftime('%Y-%m')}"
            else:
                date_range = "N/A"

            result_parts.append(f"## {original_addr}")
            result_parts.append(f"**Reports:** {count} | **Period:** {date_range}")
            result_parts.append(f"**Types:** {type_summary}")

            # Sample descriptions
            result_parts.append("**Recent reports:**")
            for issue in issues_list[:3]:
                desc = (issue.get('description') or '')[:80]
                if desc:
                    result_parts.append(f"- {desc}...")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error finding repeat issues: {e}")
        return f"Error finding repeat issues: {str(e)}"


@mcp.tool()
def get_seasonal_patterns(
    issue_type: Optional[str] = None,
    zip_code: Optional[str] = None,
) -> str:
    """
    Analyze seasonal patterns in 311 issues.

    Shows which months have more/fewer issues, helping predict and
    prepare for seasonal spikes.

    Args:
        issue_type: Filter by issue type (e.g., "pothole")
        zip_code: Filter to specific zip code

    Returns:
        Monthly breakdown showing seasonal patterns

    Example:
        >>> get_seasonal_patterns()
        # Overall seasonal patterns
        >>> get_seasonal_patterns(issue_type="pothole")
        # When do potholes peak? (hint: after rainy season)
    """
    logger.info(f"Getting seasonal patterns: type={issue_type}, zip={zip_code}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    try:
        from collections import Counter

        storage = civicos_client._storage
        jurisdiction = civicos_client.jurisdiction

        all_issues = storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        # Apply filters
        issues = all_issues

        if zip_code:
            issues = [i for i in issues if zip_code in (i.get('address', '') or '')]

        if issue_type:
            issue_type_lower = issue_type.lower()
            issues = [
                i for i in issues
                if issue_type_lower in (i.get('issue_type', '') or '').lower()
            ]

        if not issues:
            return "No issues match the specified filters."

        # Count by month
        month_counts = Counter()
        for issue in issues:
            created = issue.get('created_at')
            if created:
                dt = _parse_date(created)
                if dt:
                    month_counts[dt.month] += 1

        if not month_counts:
            return "No date data available for seasonal analysis."

        # Calculate statistics
        total = sum(month_counts.values())
        avg_monthly = total / 12

        month_names = [
            'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
            'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
        ]

        # Build response
        result_parts = []
        result_parts.append("# Seasonal Issue Patterns")
        if issue_type:
            result_parts.append(f"**Issue Type:** {issue_type}")
        if zip_code:
            result_parts.append(f"**Zip Code:** {zip_code}")
        result_parts.append(f"**Total Issues Analyzed:** {total:,}")
        result_parts.append(f"**Average per Month:** {avg_monthly:.1f}")
        result_parts.append("")

        # Monthly breakdown with visual bar
        result_parts.append("## Monthly Distribution")
        result_parts.append("")
        max_count = max(month_counts.values()) if month_counts else 1

        for month in range(1, 13):
            count = month_counts.get(month, 0)
            pct = (count / total * 100) if total > 0 else 0
            bar_len = int((count / max_count) * 20) if max_count > 0 else 0
            bar = '█' * bar_len + '░' * (20 - bar_len)
            vs_avg = ((count - avg_monthly) / avg_monthly * 100) if avg_monthly > 0 else 0
            trend = "↑" if vs_avg > 10 else "↓" if vs_avg < -10 else ""
            result_parts.append(f"**{month_names[month-1]}:** {bar} {count:>4} ({pct:>5.1f}%) {trend}")

        result_parts.append("")

        # Identify peaks and troughs
        sorted_months = sorted(month_counts.items(), key=lambda x: -x[1])
        peak_months = [month_names[m-1] for m, _ in sorted_months[:3]]
        low_months = [month_names[m-1] for m, _ in sorted_months[-3:] if month_counts.get(m, 0) > 0]

        result_parts.append("## Insights")
        result_parts.append(f"- **Peak months:** {', '.join(peak_months)}")
        if low_months:
            result_parts.append(f"- **Lowest months:** {', '.join(low_months)}")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error getting seasonal patterns: {e}")
        return f"Error getting seasonal patterns: {str(e)}"


@mcp.tool()
def generate_neighborhood_report(
    zip_code: str,
    include_trends: bool = True,
    include_repeat_issues: bool = True,
) -> str:
    """
    Generate a comprehensive 311 report for a neighborhood (by zip code).

    Creates a shareable summary suitable for community meetings or advocacy.
    Combines statistics, trends, and problem areas.

    Args:
        zip_code: Zip code to analyze (e.g., "94901")
        include_trends: Include trend analysis (default: True)
        include_repeat_issues: Include repeat issue locations (default: True)

    Returns:
        Comprehensive neighborhood report

    Example:
        >>> generate_neighborhood_report("94901")
        # Full report for downtown San Rafael
    """
    logger.info(f"Generating neighborhood report: zip={zip_code}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {'zip_code': zip_code}
    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    if not is_valid:
        return f"Error: Invalid input - {error_message}"

    try:
        from datetime import datetime, timedelta
        from collections import Counter

        storage = civicos_client._storage
        jurisdiction = civicos_client.jurisdiction

        all_issues = storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        # Filter to zip code
        issues = [i for i in all_issues if zip_code in (i.get('address', '') or '')]

        if not issues:
            return f"No issues found for zip code {zip_code}."

        total = len(issues)

        # Basic stats
        by_status = Counter(i.get('status', 'unknown') for i in issues)
        by_type = Counter(i.get('issue_type', 'Unknown') for i in issues)

        # Resolution rate
        closed_statuses = {'closed', 'resolved', 'archived'}
        resolved = sum(1 for i in issues if i.get('status', '').lower() in closed_statuses)
        resolution_rate = (resolved / total * 100) if total > 0 else 0

        # Date range
        dates = [_parse_date(i.get('created_at')) for i in issues if i.get('created_at')]
        dates = [d for d in dates if d]
        if dates:
            date_range = f"{min(dates).strftime('%Y-%m-%d')} to {max(dates).strftime('%Y-%m-%d')}"
        else:
            date_range = "N/A"

        # Build report
        result_parts = []
        result_parts.append(f"# Neighborhood Report: {zip_code}")
        result_parts.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d')}")
        result_parts.append(f"**Data Period:** {date_range}")
        result_parts.append("")

        result_parts.append("---")
        result_parts.append("")

        result_parts.append("## Executive Summary")
        result_parts.append(f"- **Total 311 Issues:** {total:,}")
        result_parts.append(f"- **Resolution Rate:** {resolution_rate:.1f}%")
        result_parts.append(f"- **Top Issue:** {by_type.most_common(1)[0][0] if by_type else 'N/A'}")
        result_parts.append("")

        result_parts.append("## Issues by Type")
        for issue_type, count in by_type.most_common(10):
            pct = count / total * 100
            result_parts.append(f"- **{issue_type}:** {count} ({pct:.1f}%)")
        result_parts.append("")

        result_parts.append("## Issues by Status")
        for status, count in by_status.most_common():
            pct = count / total * 100
            result_parts.append(f"- **{status}:** {count} ({pct:.1f}%)")
        result_parts.append("")

        # Trends section
        if include_trends:
            result_parts.append("## Recent Trends (6 months)")
            now = datetime.now()
            recent_start = now - timedelta(days=180)
            previous_start = recent_start - timedelta(days=180)

            recent = [i for i in issues if _parse_date(i.get('created_at')) and _parse_date(i.get('created_at')) >= recent_start]
            previous = [i for i in issues if _parse_date(i.get('created_at')) and previous_start <= _parse_date(i.get('created_at')) < recent_start]

            if recent and previous:
                change = ((len(recent) - len(previous)) / len(previous) * 100) if previous else 0
                trend_arrow = "📈" if change > 10 else "📉" if change < -10 else "➡️"
                result_parts.append(f"- **Recent:** {len(recent)} issues (last 6 mo)")
                result_parts.append(f"- **Previous:** {len(previous)} issues")
                result_parts.append(f"- **Trend:** {trend_arrow} {change:+.1f}%")
            else:
                result_parts.append("*Insufficient data for trend analysis*")
            result_parts.append("")

        # Repeat issues section
        if include_repeat_issues:
            result_parts.append("## Problem Locations (3+ reports)")
            from collections import defaultdict

            def normalize_address(addr):
                if not addr:
                    return None
                addr = ' '.join(addr.lower().split())
                import re
                addr = re.sub(r'\s+(apt|unit|#|ste|suite)\s*\S*', '', addr)
                return addr[:50]

            location_issues = defaultdict(list)
            for issue in issues:
                addr = normalize_address(issue.get('address'))
                if addr:
                    location_issues[addr].append(issue)

            repeats = [(addr, issues_list) for addr, issues_list in location_issues.items() if len(issues_list) >= 3]
            repeats.sort(key=lambda x: -len(x[1]))

            if repeats:
                for addr, issues_list in repeats[:5]:
                    original_addr = issues_list[0].get('address', addr)
                    result_parts.append(f"- **{original_addr}:** {len(issues_list)} reports")
            else:
                result_parts.append("*No locations with 3+ reports*")
            result_parts.append("")

        result_parts.append("---")
        result_parts.append(f"*Report generated by CivicOS for {jurisdiction}*")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error generating neighborhood report: {e}")
        return f"Error generating neighborhood report: {str(e)}"


@mcp.tool()
def compare_zip_codes(
    zip_codes: str,
) -> str:
    """
    Compare 311 issue patterns across multiple zip codes.

    Useful for identifying which neighborhoods have more issues or
    different issue mixes.

    Args:
        zip_codes: Comma-separated zip codes (e.g., "94901,94903,94904")

    Returns:
        Comparative analysis across zip codes

    Example:
        >>> compare_zip_codes("94901,94903")
        # Compare downtown vs Terra Linda
    """
    logger.info(f"Comparing zip codes: {zip_codes}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # Parse zip codes
    zips = [z.strip() for z in zip_codes.split(',') if z.strip()]

    if len(zips) < 2:
        return "Please provide at least 2 zip codes separated by commas."

    if len(zips) > 6:
        return "Please provide no more than 6 zip codes for comparison."

    try:
        from collections import Counter

        storage = civicos_client._storage
        jurisdiction = civicos_client.jurisdiction

        all_issues = storage.get_issues(jurisdiction_id=jurisdiction, limit=5000)

        # Analyze each zip code
        zip_data = {}
        for zc in zips:
            issues = [i for i in all_issues if zc in (i.get('address', '') or '')]
            if not issues:
                zip_data[zc] = None
                continue

            by_type = Counter(i.get('issue_type', 'Unknown') for i in issues)
            closed_statuses = {'closed', 'resolved', 'archived'}
            resolved = sum(1 for i in issues if i.get('status', '').lower() in closed_statuses)

            zip_data[zc] = {
                'total': len(issues),
                'resolved': resolved,
                'resolution_rate': (resolved / len(issues) * 100) if issues else 0,
                'top_types': by_type.most_common(5),
                'by_type': by_type,
            }

        # Build comparison
        result_parts = []
        result_parts.append("# Zip Code Comparison")
        result_parts.append(f"**Comparing:** {', '.join(zips)}")
        result_parts.append("")

        # Summary table
        result_parts.append("## Overview")
        result_parts.append("")
        result_parts.append("| Zip Code | Total Issues | Resolution Rate | Top Issue |")
        result_parts.append("|----------|--------------|-----------------|-----------|")

        for zc in zips:
            data = zip_data.get(zc)
            if data:
                top_issue = data['top_types'][0][0] if data['top_types'] else 'N/A'
                result_parts.append(f"| {zc} | {data['total']:,} | {data['resolution_rate']:.1f}% | {top_issue} |")
            else:
                result_parts.append(f"| {zc} | 0 | N/A | N/A |")

        result_parts.append("")

        # Detailed breakdown per zip
        for zc in zips:
            data = zip_data.get(zc)
            if not data:
                continue

            result_parts.append(f"## {zc}")
            result_parts.append(f"**Total:** {data['total']:,} | **Resolved:** {data['resolution_rate']:.1f}%")
            result_parts.append("")
            result_parts.append("**Top Issue Types:**")
            for issue_type, count in data['top_types']:
                pct = count / data['total'] * 100
                result_parts.append(f"- {issue_type}: {count} ({pct:.1f}%)")
            result_parts.append("")

        # Find unique characteristics
        result_parts.append("## Notable Differences")

        # Which zip has highest rate of each major issue type?
        all_types = set()
        for data in zip_data.values():
            if data:
                all_types.update(data['by_type'].keys())

        for issue_type in list(all_types)[:5]:  # Top 5 issue types
            rates = []
            for zc in zips:
                data = zip_data.get(zc)
                if data and data['total'] > 0:
                    count = data['by_type'].get(issue_type, 0)
                    rate = count / data['total'] * 100
                    rates.append((zc, rate, count))

            if rates:
                rates.sort(key=lambda x: -x[1])
                highest = rates[0]
                lowest = rates[-1]
                if highest[1] > lowest[1] + 5:  # At least 5% difference
                    result_parts.append(f"- **{issue_type}:** Highest in {highest[0]} ({highest[1]:.1f}%), lowest in {lowest[0]} ({lowest[1]:.1f}%)")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error comparing zip codes: {e}")
        return f"Error comparing zip codes: {str(e)}"


@mcp.tool()
def search_agenda_packets(
    query: str,
    agenda_item: Optional[str] = None,
    limit: int = 10,
) -> str:
    """
    Search staff reports, fiscal analyses, and agenda packet documents.

    Searches the full text of PDF documents attached to meeting agendas.
    This includes staff recommendations, fiscal impact analyses, legal opinions,
    and supporting materials. Use this to understand the "why" behind decisions.

    Args:
        query: Search query (e.g., "homeless shelter funding", "traffic study")
        agenda_item: Optional agenda item filter (e.g., "6.a") to get related docs
        limit: Maximum number of results (default: 10)

    Returns:
        Formatted text with PDF excerpts including page numbers and context

    Example:
        >>> search_agenda_packets("fiscal impact housing")
        # Returns staff report excerpts about housing project costs
    """
    logger.info(f"Searching agenda packets for: {query}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {'query': query}
    if agenda_item:
        input_data['agenda_item'] = agenda_item
    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    if not is_valid:
        logger.error(f"Input validation failed: {error_message}")
        return f"Error: Invalid input - {error_message}"

    sanitized_query = sanitized_data.get('query', query)
    sanitized_agenda_item = sanitized_data.get('agenda_item', agenda_item)

    try:
        # Use what_happened_with_discussion() for hybrid PDF + transcript search
        results = civicos_client.what_happened_with_discussion(
            sanitized_query,
            top_k=limit,
            agenda_item=sanitized_agenda_item,
        )

        result_parts = []
        result_parts.append(f"# Agenda Packet Search: {sanitized_query}")
        result_parts.append("")

        # Separate PDF results from transcript results
        pdf_results = [r for r in results if r.source_type == "pdf"]
        transcript_results = [r for r in results if r.source_type == "transcript"]

        # Query context (inline notes for transparency)
        result_parts.append("---")
        result_parts.append(f"🔍 **Query:** \"{sanitized_query}\"")
        if sanitized_agenda_item:
            result_parts.append(f"🏷️ **Agenda item filter:** {sanitized_agenda_item}")
        result_parts.append(f"📊 **Searched:** Staff reports, fiscal analyses, agenda packet PDFs, meeting transcripts")
        result_parts.append(f"📋 **Found:** {len(pdf_results)} documents, {len(transcript_results)} transcript excerpts")
        result_parts.append(f"🏛️ **Jurisdiction:** {civicos_client.jurisdiction}")
        result_parts.append("---")
        result_parts.append("")

        result_parts.append(f"## Staff Reports & Documents ({len(pdf_results)} found)")
        if pdf_results:
            for r in pdf_results:
                result_parts.append(f"### Page {r.page_start or 'N/A'}")
                if r.agenda_item:
                    result_parts.append(f"*Agenda Item: {r.agenda_item}*")
                result_parts.append(f"> {r.text[:600]}...")
                result_parts.append("")
        else:
            result_parts.append("No PDF documents found matching this query.")
        result_parts.append("")

        result_parts.append(f"## Related Discussion ({len(transcript_results)} excerpts)")
        if transcript_results:
            for r in transcript_results:
                speaker = r.speaker_name or r.speaker or "Unknown"
                role = f" ({r.speaker_role})" if r.speaker_role else ""
                result_parts.append(f"### {speaker}{role}")
                if r.start_timestamp:
                    video_url = r.video_url
                    if video_url:
                        result_parts.append(f"*[Watch at {r.start_timestamp}]({video_url})*")
                    else:
                        result_parts.append(f"*Video: {r.start_timestamp}*")
                if r.is_public_comment:
                    result_parts.append("*[Public Comment]*")
                result_parts.append(f"> {r.text[:400]}...")
                result_parts.append("")
        else:
            result_parts.append("No transcript excerpts found.")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error searching agenda packets: {e}")
        return f"Error searching agenda packets: {str(e)}"


@mcp.tool()
def search_budget(
    department: Optional[str] = None,
    fund: Optional[str] = None,
    min_amount: Optional[int] = None,
    fiscal_year: Optional[str] = None,
) -> str:
    """
    Search the municipal budget by department, fund, or amount.

    Query San Rafael's $180M annual budget. Returns line items with
    budgeted amounts, departments, and fund sources.

    Args:
        department: Filter by department (e.g., "Police", "Fire", "Parks")
        fund: Filter by fund (e.g., "General Fund", "Enterprise Fund")
        min_amount: Minimum budget amount in dollars (e.g., 1000000 for $1M+)
        fiscal_year: Fiscal year (e.g., "2025-2026"), defaults to current

    Returns:
        Budget summary with department totals and line items

    Example:
        >>> search_budget(department="Police")
        # Returns Police department budget breakdown
        >>> search_budget(min_amount=5000000)
        # Returns all budget items over $5M
    """
    logger.info(f"Searching budget: dept={department}, fund={fund}, min=${min_amount}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {}
    if department:
        input_data['department'] = department
    if fund:
        input_data['fund'] = fund
    if fiscal_year:
        input_data['fiscal_year'] = fiscal_year

    if input_data:
        is_valid, sanitized_data, error_message = validate_civic_input(input_data)
        if not is_valid:
            logger.error(f"Input validation failed: {error_message}")
            return f"Error: Invalid input - {error_message}"
        department = sanitized_data.get('department', department)
        fund = sanitized_data.get('fund', fund)
        fiscal_year = sanitized_data.get('fiscal_year', fiscal_year)

    try:
        result_parts = []
        result_parts.append("# San Rafael Budget")
        result_parts.append("")

        # Query context (inline notes for transparency)
        filters = []
        if department:
            filters.append(f"department={department}")
        if fund:
            filters.append(f"fund={fund}")
        if min_amount:
            filters.append(f"min=${min_amount:,}")
        filter_str = ", ".join(filters) if filters else "none"

        result_parts.append("---")
        result_parts.append(f"🔍 **Filters:** {filter_str}")
        result_parts.append(f"📊 **Data source:** FY{fiscal_year or '25-26'} Adopted Budget")
        result_parts.append(f"📋 **Contains:** 58 line items, $180M total appropriations")
        result_parts.append(f"🏛️ **Jurisdiction:** {civicos_client.jurisdiction}")
        result_parts.append("---")
        result_parts.append("")

        # Get summary first
        summary = civicos_client.budget_summary(fiscal_year=fiscal_year)
        if summary:
            total = sum(s.budgeted_dollars for s in summary)
            result_parts.append(f"**Total Budget:** ${total:,.0f}")
            result_parts.append(f"**Fiscal Year:** {fiscal_year or 'Current'}")
            result_parts.append("")

            result_parts.append("## By Department")
            for s in sorted(summary, key=lambda x: x.budgeted_dollars, reverse=True)[:10]:
                pct = (s.budgeted_dollars / total * 100) if total > 0 else 0
                result_parts.append(f"- **{s.name}:** ${s.budgeted_dollars:,.0f} ({pct:.1f}%)")
            result_parts.append("")

        # Get detailed items if filtered
        if department or fund or min_amount:
            items = civicos_client.budget(
                department=department,
                fund=fund,
                min_amount=min_amount,
                fiscal_year=fiscal_year,
                limit=20,
            )

            filter_desc = []
            if department:
                filter_desc.append(f"Department: {department}")
            if fund:
                filter_desc.append(f"Fund: {fund}")
            if min_amount:
                filter_desc.append(f"Min: ${min_amount:,}")

            result_parts.append(f"## Filtered Results ({', '.join(filter_desc)})")
            if items:
                for item in items:
                    result_parts.append(f"### {item.line_item or item.program or 'Line Item'}")
                    result_parts.append(f"- Department: {item.department}")
                    result_parts.append(f"- Fund: {item.fund}")
                    result_parts.append(f"- Budgeted: ${item.budgeted_dollars:,.0f}")
                    if item.notes:
                        result_parts.append(f"- Notes: {item.notes[:100]}")
                    # Add source citation for budget verification
                    if item.source_url:
                        page_info = f" (page {item.source_page})" if item.source_page else ""
                        result_parts.append(f"- [View in budget document]({item.source_url}){page_info}")
                    result_parts.append("")
            else:
                result_parts.append("No items match the filter criteria.")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error searching budget: {e}")
        return f"Error searching budget: {str(e)}"


@mcp.tool()
def get_upcoming_meetings(
    topics: Optional[str] = None,
    days: int = 30,
    include_elections: bool = False,
) -> str:
    """
    Get upcoming city council meetings and agenda items.

    Returns scheduled meetings with their agenda items for the next N days.
    Use this to see what decisions are coming up that residents might want
    to participate in.

    IMPORTANT: Meeting dates are pre-formatted with the correct day of week
    (e.g., "Monday, February 2, 2026"). Always use the day of week exactly
    as provided in the response - do not attempt to recalculate it.

    Args:
        topics: Comma-separated topics to filter by (e.g., "housing,transportation")
        days: Number of days to look ahead (default: 30)
        include_elections: If True, also include upcoming elections and deadlines

    Returns:
        List of upcoming meetings with dates, bodies, and agenda items

    Example:
        >>> get_upcoming_meetings(topics="housing")
        # Returns upcoming meetings with housing-related agenda items
    """
    logger.info(f"Getting upcoming meetings: topics={topics}, days={days}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # Parse topics if provided
    topic_list = None
    if topics:
        # SECURITY: Validate input
        is_valid, sanitized_data, error_message = validate_civic_input({'topics': topics})
        if not is_valid:
            logger.error(f"Input validation failed: {error_message}")
            return f"Error: Invalid input - {error_message}"
        topic_list = [t.strip() for t in sanitized_data.get('topics', topics).split(',')]

    try:
        results = civicos_client.whats_next(
            topics=topic_list,
            days=days,
            include_elections=include_elections,
        )

        result_parts = []
        result_parts.append(f"# Upcoming Meetings (Next {days} Days)")
        result_parts.append("")

        # Query context (inline notes for transparency)
        meeting_count = len([r for r in results if hasattr(r, 'agenda_items')]) if results else 0
        election_count = len([r for r in results if hasattr(r, 'election_type')]) if results else 0
        result_parts.append("---")
        result_parts.append(f"🔍 **Looking ahead:** {days} days")
        if topic_list:
            result_parts.append(f"🏷️ **Topic filter:** {', '.join(topic_list)}")
        result_parts.append(f"📊 **Searched:** City council calendars, Legistar agendas")
        result_parts.append(f"📋 **Found:** {meeting_count} meetings" + (f", {election_count} elections" if include_elections and election_count else ""))
        result_parts.append(f"🏛️ **Jurisdiction:** {civicos_client.jurisdiction}")
        result_parts.append("---")
        result_parts.append("")

        if not results:
            result_parts.append("No upcoming meetings found in this time period.")
            return "\n".join(result_parts)

        meetings = [r for r in results if hasattr(r, 'agenda_items')]
        elections = [r for r in results if hasattr(r, 'election_type')]

        for meeting in meetings:
            date_str = meeting.date.strftime("%A, %B %d, %Y at %I:%M %p") if meeting.date else "TBD"
            meeting_title = meeting.title or meeting.body or 'Meeting'

            # Generate web app deep link for meeting
            meeting_id = getattr(meeting, 'id', None)
            web_app_url = _generate_web_app_url('event', meeting_id) if meeting_id else ""

            # Format header with link if available
            if web_app_url:
                result_parts.append(f"## [{meeting_title}]({web_app_url})")
            else:
                result_parts.append(f"## {meeting_title}")
            result_parts.append(f"**Date:** {date_str}")
            if meeting.location:
                result_parts.append(f"**Location:** {meeting.location}")
            if web_app_url:
                result_parts.append(f"**[Open in CivicOS]({web_app_url})**")
            result_parts.append("")

            if meeting.agenda_items:
                result_parts.append("### Agenda Items")
                for item in meeting.agenda_items[:10]:
                    if isinstance(item, dict):
                        title = item.get('title', item.get('description', 'Item'))[:100]
                        item_num = item.get('item_number', '')
                        if item_num:
                            result_parts.append(f"- **{item_num}:** {title}")
                        else:
                            result_parts.append(f"- {title}")
                    else:
                        result_parts.append(f"- {str(item)[:100]}")
            result_parts.append("")

        if elections:
            result_parts.append("## Upcoming Elections")
            for election in elections:
                date_str = election.election_date.strftime("%B %d, %Y") if election.election_date else "TBD"
                result_parts.append(f"### {election.name}")
                result_parts.append(f"**Date:** {date_str}")
                result_parts.append(f"**Type:** {election.election_type}")
                if election.deadlines:
                    result_parts.append("**Key Deadlines:**")
                    for d in election.deadlines[:5]:
                        result_parts.append(f"- {d.get('deadline_type')}: {d.get('deadline_date')}")
                result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error getting upcoming meetings: {e}")
        return f"Error getting upcoming meetings: {str(e)}"


@mcp.tool()
def get_voting_record(
    official_name: str,
    topic: Optional[str] = None,
    since: Optional[str] = None,
) -> str:
    """
    Get an elected official's voting record.

    Shows how a council member or official has voted on past decisions,
    with optional filtering by topic or date range.

    Args:
        official_name: Name of the official (e.g., "Kate Colin", "Maribeth Bushey")
        topic: Optional topic filter (e.g., "housing", "transportation")
        since: Optional start date filter (YYYY-MM-DD format)

    Returns:
        Voting statistics and list of votes with outcomes

    Example:
        >>> get_voting_record("Kate Colin", topic="housing")
        # Returns Kate Colin's votes on housing-related items
    """
    logger.info(f"Getting voting record for: {official_name}, topic={topic}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {'official_name': official_name}
    if topic:
        input_data['topic'] = topic
    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    if not is_valid:
        logger.error(f"Input validation failed: {error_message}")
        return f"Error: Invalid input - {error_message}"

    sanitized_name = sanitized_data.get('official_name', official_name)
    sanitized_topic = sanitized_data.get('topic', topic)

    try:
        record = civicos_client.get_voting_record(
            official_name=sanitized_name,
            topic=sanitized_topic,
            since=since,
        )

        result_parts = []
        result_parts.append(f"# Voting Record: {record.official_name}")
        if sanitized_topic:
            result_parts.append(f"Filtered by topic: {sanitized_topic}")
        if since:
            result_parts.append(f"Since: {since}")
        result_parts.append("")

        # Summary statistics
        result_parts.append("## Summary")
        result_parts.append(f"- **Total Votes:** {record.total_votes}")
        result_parts.append(f"- **Yes Votes:** {record.yes_votes} ({record.yes_percentage:.0f}%)")
        result_parts.append(f"- **No Votes:** {record.no_votes} ({record.no_percentage:.0f}%)")
        result_parts.append(f"- **Abstain/Absent:** {record.abstain_votes}")
        result_parts.append("")

        # Individual votes
        if record.decisions:
            result_parts.append("## Recent Votes")
            for d in record.decisions[:15]:
                vote_emoji = {"yes": "✅", "no": "❌", "absent": "⚪"}.get(d.get('vote'), "❓")
                result_parts.append(f"### {d.get('title', 'Item')[:80]}")
                result_parts.append(f"- **Date:** {d.get('date', 'N/A')}")
                result_parts.append(f"- **Vote:** {vote_emoji} {d.get('vote', 'N/A').upper()}")
                result_parts.append(f"- **Outcome:** {d.get('outcome', 'N/A')}")
                if d.get('topics'):
                    result_parts.append(f"- **Topics:** {', '.join(d.get('topics', []))}")
                # Add CivicOS deep link for the decision
                decision_id = d.get('id') or d.get('meeting_id')
                if decision_id:
                    web_url = _generate_web_app_url('event', decision_id)
                    if web_url:
                        result_parts.append(f"- [View in CivicOS]({web_url})")
                result_parts.append("")

        return "\n".join(result_parts)

    except ValueError as e:
        # Official not found
        return f"Official not found: {sanitized_name}. Try the full name as it appears in meeting minutes."
    except Exception as e:
        logger.error(f"Error getting voting record: {e}")
        return f"Error getting voting record: {str(e)}"


@mcp.tool()
def get_decision_context(
    query: str,
    limit: int = 5,
) -> str:
    """
    Get decisions with linked transcript excerpts showing what was discussed.

    Returns both the official decision (from minutes) AND what was actually
    said during the meeting. This provides complete context including public
    testimony, staff recommendations, and council deliberations.

    Args:
        query: Search query (e.g., "homeless shelter", "housing development")
        limit: Maximum number of decisions to return (default: 5)

    Returns:
        Decisions with linked transcript excerpts organized by speaker role

    Example:
        >>> get_decision_context("affordable housing")
        # Returns housing decisions with public comments and council discussion
    """
    logger.info(f"Getting decision context for: {query}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {'query': query}
    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    if not is_valid:
        logger.error(f"Input validation failed: {error_message}")
        return f"Error: Invalid input - {error_message}"

    sanitized_query = sanitized_data.get('query', query)

    try:
        results = civicos_client.what_happened_full_context(
            sanitized_query,
            top_k=limit,
        )

        result_parts = []
        result_parts.append(f"# Decisions with Context: {sanitized_query}")
        result_parts.append("")

        if not results:
            result_parts.append("No decisions found matching this query.")
            return "\n".join(result_parts)

        for r in results:
            d = r.decision
            result_parts.append(f"## {d.title}")
            result_parts.append(f"- **Date:** {d.date}")
            result_parts.append(f"- **Outcome:** {d.outcome or 'N/A'}")
            result_parts.append(f"- **Body:** {d.body or 'N/A'}")
            # Add CivicOS deep link for the decision
            decision_id = getattr(d, 'id', None) or getattr(d, 'meeting_id', None)
            if decision_id:
                web_url = _generate_web_app_url('event', decision_id)
                if web_url:
                    result_parts.append(f"- [View in CivicOS]({web_url})")
            result_parts.append("")

            if r.transcript_links:
                # Separate by speaker role
                public_comments = [l for l in r.transcript_links if l.is_public_comment]
                other_discussion = [l for l in r.transcript_links if not l.is_public_comment]

                if public_comments:
                    result_parts.append("### Public Testimony")
                    for link in public_comments[:3]:
                        speaker = link.speaker_name or link.speaker or "Resident"
                        result_parts.append(f"**{speaker}:**")
                        result_parts.append(f"> {link.text[:300]}...")
                        if link.start_timestamp:
                            video_url = link.video_url
                            if video_url:
                                result_parts.append(f"*[Watch at {link.start_timestamp}]({video_url})*")
                            else:
                                result_parts.append(f"*Video: {link.start_timestamp}*")
                        result_parts.append("")

                if other_discussion:
                    result_parts.append("### Council Discussion")
                    for link in other_discussion[:3]:
                        speaker = link.speaker_name or link.speaker or "Speaker"
                        role = f" ({link.speaker_role})" if link.speaker_role else ""
                        result_parts.append(f"**{speaker}{role}:**")
                        result_parts.append(f"> {link.text[:300]}...")
                        if link.start_timestamp:
                            video_url = link.video_url
                            if video_url:
                                result_parts.append(f"*[Watch at {link.start_timestamp}]({video_url})*")
                        result_parts.append("")
            else:
                result_parts.append("*No transcript excerpts linked to this decision.*")
                result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error getting decision context: {e}")
        return f"Error getting decision context: {str(e)}"


@mcp.tool()
def get_public_testimony(
    topic: str,
    limit: int = 10,
) -> str:
    """
    Get public testimony from city council meetings on a topic.

    Returns only the public comment portions of meeting transcripts,
    filtered by topic. Use this to find what residents have said about
    specific issues at council meetings.

    Args:
        topic: Topic to search (e.g., "traffic safety", "housing")
        limit: Maximum number of testimonies to return (default: 10)

    Returns:
        Public testimony excerpts with speaker names and video timestamps

    Example:
        >>> get_public_testimony("bike lanes")
        # Returns what residents said about bike lanes at council meetings
    """
    logger.info(f"Getting public testimony for: {topic}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {'topic': topic}
    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    if not is_valid:
        logger.error(f"Input validation failed: {error_message}")
        return f"Error: Invalid input - {error_message}"

    sanitized_topic = sanitized_data.get('topic', topic)

    try:
        testimonies = civicos_client.get_public_testimony(sanitized_topic, top_k=limit)

        result_parts = []
        result_parts.append(f"# Public Testimony: {sanitized_topic}")
        result_parts.append(f"*{len(testimonies)} public comments found*")
        result_parts.append("")

        if not testimonies:
            result_parts.append("No public testimony found for this topic.")
            result_parts.append("Try broader search terms or check meeting transcripts directly.")
            return "\n".join(result_parts)

        for t in testimonies:
            speaker = t.speaker_name or t.speaker or "Resident"
            result_parts.append(f"## {speaker}")
            if t.start_timestamp:
                # Include clickable YouTube link if video_url is available
                video_url = t.video_url
                if video_url:
                    result_parts.append(f"*[Watch at {t.start_timestamp}]({video_url})*")
                else:
                    result_parts.append(f"*Video timestamp: {t.start_timestamp}*")
            result_parts.append("")
            result_parts.append(f"> {t.text[:500]}...")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error getting public testimony: {e}")
        return f"Error getting public testimony: {str(e)}"


@mcp.tool()
def get_funding_flow(
    program: Optional[str] = None,
    cfda_number: Optional[str] = None,
) -> str:
    """
    Trace intergovernmental funding from federal to state to city budget.

    Shows how federal and state grant dollars flow through the system to
    local budget items. Use for "what if" analysis (e.g., "what if CDBG
    is cut 20%?").

    Args:
        program: Program name to search (e.g., "CDBG", "HOME", "FEMA")
        cfda_number: Federal CFDA number (e.g., "14.218" for CDBG)

    Returns:
        Funding flow chains showing federal->state->city connections

    Example:
        >>> get_funding_flow(program="CDBG")
        # Shows how Community Development Block Grant funds reach city programs
    """
    logger.info(f"Getting funding flow: program={program}, cfda={cfda_number}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {}
    if program:
        input_data['program'] = program
    if cfda_number:
        input_data['cfda_number'] = cfda_number

    if input_data:
        is_valid, sanitized_data, error_message = validate_civic_input(input_data)
        if not is_valid:
            logger.error(f"Input validation failed: {error_message}")
            return f"Error: Invalid input - {error_message}"
        program = sanitized_data.get('program', program)
        cfda_number = sanitized_data.get('cfda_number', cfda_number)

    try:
        flows = civicos_client.funding_flow(
            program=program,
            cfda_number=cfda_number,
        )

        result_parts = []
        result_parts.append("# Intergovernmental Funding Flow")
        if program:
            result_parts.append(f"Program: {program}")
        if cfda_number:
            result_parts.append(f"CFDA: {cfda_number}")
        result_parts.append("")

        if not flows:
            result_parts.append("No funding flows found matching criteria.")
            result_parts.append("")
            result_parts.append("Note: Funding flow data requires explicit linkages between")
            result_parts.append("budget items and federal/state grants. Use `get_federal_expenditures()`")
            result_parts.append("for authoritative audited federal spending data.")
            return "\n".join(result_parts)

        total_budget = sum(f.budget_dollars for f in flows)
        result_parts.append(f"**Total Linked Budget:** ${total_budget:,.0f}")
        result_parts.append("")

        for flow in flows[:10]:
            result_parts.append(f"## {flow.budget_description}")
            result_parts.append(f"- **Department:** {flow.department or 'N/A'}")
            result_parts.append(f"- **Budget:** ${flow.budget_dollars:,.0f}")

            if flow.federal_program_name:
                result_parts.append(f"- **Federal Source:** {flow.federal_program_name}")
                if flow.federal_dollars:
                    result_parts.append(f"- **Federal Amount:** ${flow.federal_dollars:,.0f}")

            if flow.state_program_name:
                result_parts.append(f"- **State Pass-Through:** {flow.state_program_name}")
                if flow.state_dollars:
                    result_parts.append(f"- **State Amount:** ${flow.state_dollars:,.0f}")

            result_parts.append(f"- **Match Confidence:** {flow.match_confidence:.0%}")
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error getting funding flow: {e}")
        return f"Error getting funding flow: {str(e)}"


@mcp.tool()
def get_federal_expenditures(
    cfda_number: Optional[str] = None,
    audit_year: Optional[int] = None,
) -> str:
    """
    Get audited federal expenditures from Single Audit (FAC) data.

    Returns authoritative data on how the city actually spent federal funds,
    from the Schedule of Expenditures of Federal Awards (SEFA) in the city's
    annual Single Audit filed with the Federal Audit Clearinghouse.

    This is the most reliable source for federal funding data.

    Args:
        cfda_number: Filter by CFDA/ALN number (e.g., "20.205" for Highway Planning)
        audit_year: Audit fiscal year (e.g., 2023)

    Returns:
        Audited federal expenditure data by program

    Example:
        >>> get_federal_expenditures(audit_year=2023)
        # Returns all federal spending for FY2023 from Single Audit
    """
    logger.info(f"Getting federal expenditures: cfda={cfda_number}, year={audit_year}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    try:
        # Get summary first
        summary = civicos_client.federal_expenditures_summary(audit_year=audit_year)

        result_parts = []
        result_parts.append("# Federal Expenditures (Single Audit)")
        result_parts.append(f"**Audit Year:** {summary.get('audit_year', 'N/A')}")
        result_parts.append(f"**Total Federal Spending:** ${summary.get('total_dollars', 0):,.0f}")
        result_parts.append("")

        programs = summary.get('programs', [])
        if programs:
            result_parts.append("## By Program")
            for p in programs[:15]:
                major_flag = " ⭐" if p.get('is_major') else ""
                result_parts.append(f"- **{p.get('cfda', 'N/A')}:** ${p.get('dollars', 0):,.0f}{major_flag}")
                if p.get('program_name'):
                    result_parts.append(f"  *{p.get('program_name')}*")
                if p.get('source_url'):
                    result_parts.append(f"  [View in FAC]({p.get('source_url')})")
            result_parts.append("")
            result_parts.append("*⭐ = Major Program (subject to additional audit)*")
        else:
            result_parts.append("No federal expenditure data found for this period.")
            result_parts.append("Data may not be available for recent years (18-24 month lag).")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error getting federal expenditures: {e}")
        return f"Error getting federal expenditures: {str(e)}"


@mcp.tool()
def get_intergovernmental_revenue(
    fiscal_year: Optional[int] = None,
    source: Optional[str] = None,
) -> str:
    """
    Get intergovernmental revenue from CA State Controller data.

    Returns federal, state, and county revenue as reported to the California
    State Controller. More current than FAC data and includes state/county
    sources not available elsewhere.

    Args:
        fiscal_year: Fiscal year (e.g., 2024). Defaults to most recent.
        source: Filter by source ("federal", "state", "county") or None for all

    Returns:
        Revenue breakdown by source with line-item details

    Example:
        >>> get_intergovernmental_revenue(fiscal_year=2024)
        # Returns all intergovernmental revenue for FY2024
    """
    logger.info(f"Getting intergovernmental revenue: year={fiscal_year}, source={source}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    if source:
        is_valid, sanitized_data, error_message = validate_civic_input({'source': source})
        if not is_valid:
            logger.error(f"Input validation failed: {error_message}")
            return f"Error: Invalid input - {error_message}"
        source = sanitized_data.get('source', source)

    try:
        summary = civicos_client.intergovernmental_revenue(
            fiscal_year=fiscal_year,
            source=source,
        )

        result_parts = []
        result_parts.append("# Intergovernmental Revenue")
        result_parts.append(f"**Entity:** {summary.entity_name}")
        result_parts.append(f"**Fiscal Year:** {summary.fiscal_year}")
        result_parts.append(f"**Total:** ${summary.total_dollars:,.0f}")
        result_parts.append("")

        result_parts.append("## By Source")
        result_parts.append(f"- **Federal:** ${summary.federal_total_dollars:,.0f}")
        result_parts.append(f"- **State:** ${summary.state_total_dollars:,.0f}")
        result_parts.append(f"- **County:** ${summary.county_total_dollars:,.0f}")
        if summary.undetermined_total_dollars > 0:
            result_parts.append(f"- **Undetermined:** ${summary.undetermined_total_dollars:,.0f}")
        result_parts.append("")

        # Show details if filtered or if there are few items
        if summary.details and (source or len(summary.details) <= 20):
            result_parts.append("## Details")
            for d in summary.details[:20]:
                result_parts.append(f"- **{d.source.upper()}:** ${d.amount_dollars:,.0f}")
                if d.line_description:
                    result_parts.append(f"  *{d.line_description[:60]}*")
            result_parts.append("")

        result_parts.append("*Source: CA State Controller ByTheNumbers*")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error getting intergovernmental revenue: {e}")
        return f"Error getting intergovernmental revenue: {str(e)}"


# ─────────── ACTION TOOLS ───────────
# Tools that help users take action, not just query

@mcp.tool()
def prepare_for_meeting(
    agenda_item_id: str,
) -> str:
    """
    Get preparation materials for participating in a city council meeting.

    Generates comprehensive prep including regulatory context, talking points,
    who else is interested (allies), and logistics (time, location, rules).

    Args:
        agenda_item_id: ID of the agenda item to prepare for

    Returns:
        Preparation materials with context, talking points, allies, logistics

    Example:
        >>> prepare_for_meeting("item-2024-housing-123")
        # Returns prep materials for speaking on that housing item
    """
    logger.info(f"Preparing for meeting: {agenda_item_id}")

    if civicos_client is None:
        return "Error: Civic client not initialized. Check server configuration."

    # SECURITY: Validate input
    input_data = {'agenda_item_id': agenda_item_id}
    is_valid, sanitized_data, error_message = validate_civic_input(input_data)
    if not is_valid:
        logger.error(f"Input validation failed: {error_message}")
        return f"Error: Invalid input - {error_message}"

    sanitized_id = sanitized_data.get('agenda_item_id', agenda_item_id)

    try:
        prep = civicos_client.prepare(sanitized_id)

        result_parts = []
        result_parts.append(f"# Meeting Preparation")
        result_parts.append(f"**Agenda Item:** {prep.agenda_item_id}")
        result_parts.append("")

        # Logistics
        result_parts.append("## Logistics")
        if prep.logistics:
            if prep.logistics.get('meeting_title'):
                result_parts.append(f"- **Meeting:** {prep.logistics['meeting_title']}")
            if prep.logistics.get('meeting_datetime'):
                result_parts.append(f"- **When:** {prep.logistics['meeting_datetime']}")
            if prep.logistics.get('location'):
                result_parts.append(f"- **Where:** {prep.logistics['location']}")
            if prep.logistics.get('virtual_url'):
                result_parts.append(f"- **Virtual:** {prep.logistics['virtual_url']}")
            if prep.logistics.get('tips'):
                result_parts.append("")
                result_parts.append("**Tips:**")
                for tip in prep.logistics['tips']:
                    result_parts.append(f"- {tip}")
        result_parts.append("")

        # Talking Points
        result_parts.append("## Talking Points")
        if prep.talking_points:
            for point in prep.talking_points:
                result_parts.append(f"- {point}")
        else:
            result_parts.append("- Introduce yourself and state your position")
            result_parts.append("- Explain why this matters to you")
            result_parts.append("- Request a specific action from the council")
        result_parts.append("")

        # Legal Citations (formatted, actionable references)
        if prep.legal_citations:
            result_parts.append("## Legal Citations")
            result_parts.append("*Cite these in your comments for stronger arguments:*")
            result_parts.append("")
            for citation in prep.legal_citations:
                cite_str = citation.get('citation', '')
                title = citation.get('title', '')
                cite_type = citation.get('type', '')
                relevance = citation.get('relevance', 0)

                # Format based on type
                if cite_type == 'state_bill':
                    if citation.get('requires_local_action'):
                        deadline = citation.get('local_deadline', '')
                        if deadline:
                            result_parts.append(f"- **{cite_str}** - {title}")
                            result_parts.append(f"  - ⚠️ *Requires local action by {deadline}*")
                        else:
                            result_parts.append(f"- **{cite_str}** - {title}")
                            result_parts.append(f"  - *Requires local implementation*")
                    else:
                        result_parts.append(f"- **{cite_str}** - {title}")
                elif cite_type in ('ordinance', 'county_ordinance'):
                    result_parts.append(f"- **{cite_str}** - {title}")
                    result_parts.append(f"  - *Local law - directly applicable*")
                elif cite_type == 'federal_program':
                    agency = citation.get('agency', '')
                    result_parts.append(f"- **{cite_str}**")
                    if agency:
                        result_parts.append(f"  - *Federal funding via {agency}*")
                elif cite_type == 'federal_bill':
                    result_parts.append(f"- **{cite_str}** - {title}")
                else:
                    result_parts.append(f"- **{cite_str}** - {title}")

                # Add URL if available
                url = citation.get('url', '')
                if url:
                    result_parts.append(f"  - [Source]({url})")
            result_parts.append("")

        # Allies
        if prep.allies:
            result_parts.append("## Others Interested")
            result_parts.append(f"*{len(prep.allies)} others have voiced or followed this item*")
            result_parts.append("")

        return "\n".join(result_parts)

    except ValueError as e:
        return f"Agenda item not found: {sanitized_id}. Use get_upcoming_meetings() to find valid agenda item IDs."
    except Exception as e:
        logger.error(f"Error preparing for meeting: {e}")
        return f"Error preparing for meeting: {str(e)}"


# ─────────── ONBOARDING TOOLS ───────────
# Help users discover what Civic can do

@mcp.tool()
def get_started(
    user_type: str = "resident",
) -> str:
    """
    Get help discovering what you can ask Civic.

    Returns example questions and guidance tailored to your role.
    Use this when you're new to Civic or want to explore its capabilities.

    Args:
        user_type: Your role - "resident", "city_staff", or "developer"

    Returns:
        Example questions organized by category, with suggested follow-ups
    """
    logger.info(f"Getting started guide for user_type: {user_type}")

    user_type = user_type.lower().strip()

    if user_type in ("resident", "citizen", "community_member", ""):
        return _get_started_resident()
    elif user_type in ("city_staff", "staff", "clerk", "planner"):
        return _get_started_city_staff()
    elif user_type in ("developer", "dev", "engineer", "technical"):
        return _get_started_developer()
    else:
        return _get_started_resident()


def _get_started_resident() -> str:
    """Friendly category-based guidance for residents with live city status."""
    # Try to get live city pulse data
    pulse_content = ""
    try:
        if civicos_client is not None:
            pulse_data = city_pulse(days_ahead=7, days_back=30)
            if not pulse_data.get('error'):
                pulse_content = _format_city_pulse_for_display(pulse_data)
    except Exception as e:
        logger.warning(f"Could not get city pulse for get_started: {e}")

    # If we have live data, show it first
    if pulse_content:
        return f"""{pulse_content}
---

## Want to Go Deeper?

**Explore what's being decided:**
- "Tell me more about [specific meeting above]"
- "What's the background on [topic]?"

**Research past decisions:**
- "What has the council decided about housing?"
- "What did residents say about the bike lane project?"

**Take action:**
- "Help me prepare to speak at Monday's meeting"
- "How do I submit a public comment?"

---
*Just ask your question naturally - I'll find the answer!*"""

    # Fallback to static content if no live data
    return """# Welcome to Civic

What would you like to explore?

## 1. What's Happening
*Upcoming meetings and agenda items*

Try asking:
- "What's on the agenda this week?"
- "When is the next council meeting about housing?"

## 2. What Happened
*Past decisions and what people said*

Try asking:
- "What has the council decided about parking downtown?"
- "What did residents say about the bike lane project?"

## 3. Take Action
*Submit comments or prepare to speak*

Try asking:
- "How do I submit a public comment?"
- "Help me prepare to speak at Monday's meeting"

---
*Just ask your question naturally - I'll find the answer!*"""


def _get_started_city_staff() -> str:
    """Workflow-oriented guidance for city staff."""
    return """# Civic for City Staff

## Meeting Prep
*Research background for upcoming items*

- "Summarize what was said about [topic] at previous meetings"
- "What public testimony was given on housing?"
- "Search staff reports for homeless services recommendations"

Tools: `search_meeting_history()`, `get_public_testimony()`, `search_agenda_packets()`

## Constituent Insights
*Understand community concerns*

- "What issues are residents reporting downtown?"
- "Analyze 311 complaint trends in San Rafael"
- "Compare 311 patterns across zip codes 94901 vs 94903"
- "Which locations have repeat complaints that aren't getting fixed?"
- "Generate a neighborhood report for zip code 94901"

Tools: `get_issue_analytics()`, `query_issue_data()`, `detect_trends()`, `compare_zip_codes()`, `find_repeat_issues()`, `generate_neighborhood_report()`

## Policy Research
*Regulations and voting history*

- "What state laws affect ADU policy?"
- "How did council vote on similar items?"
- "What federal programs fund housing?"

Tools: `search_regulatory_stack()`, `get_voting_record()`, `get_federal_expenditures()`

## Budget Questions
*Department spending and revenue*

- "What's budgeted for Community Development?"
- "How much federal money do we receive?"

Tools: `search_budget()`, `get_intergovernmental_revenue()`

---
*Ask naturally or call tools directly for precise queries.*"""


def _get_started_developer() -> str:
    """Technical reference for developers."""
    return """# Civic MCP Tools Reference

## Semantic Search
| Tool | Purpose |
|------|---------|
| `search_meeting_history(query)` | Decisions + transcripts |
| `search_regulatory_stack(topic)` | Local/state/federal law |
| `search_agenda_packets(query)` | PDF staff reports |
| `get_public_testimony(topic)` | Public comments |
| `find_similar_issues(topic)` | 311/SeeClickFix match |
| `get_decision_context(query)` | Decisions + linked discussion |

## 311 Data Analysis
| Tool | Purpose |
|------|---------|
| `get_issue_analytics(date_range)` | Aggregate stats, trends |
| `query_issue_data(group_by, filters)` | Drill-down analysis |
| `get_issue_sample(filters)` | Raw records for patterns |
| `detect_trends(lookback_months)` | What's increasing/decreasing |
| `get_seasonal_patterns(type)` | Monthly distribution |
| `get_issue_resolution_stats()` | Resolution rates, time to fix |
| `find_repeat_issues(min_count)` | Recurring problem locations |
| `find_issues_near_address(addr)` | Geo-based search |
| `compare_zip_codes(zips)` | Neighborhood comparison |
| `generate_neighborhood_report(zip)` | Comprehensive zip report |

## Structured Queries
| Tool | Purpose |
|------|---------|
| `search_budget(department, fund)` | Budget items |
| `get_upcoming_meetings(topics, days)` | Scheduled meetings |
| `get_voting_record(official_name)` | Vote history |
| `get_federal_expenditures(cfda)` | Single Audit data |
| `get_intergovernmental_revenue()` | State Controller data |

## Action Tools
| Tool | Purpose |
|------|---------|
| `compose_public_comment(item)` | Comment context |
| `prepare_for_meeting(item_id)` | Prep materials |

## Resources
- `civicos://san-rafael/meetings`
- `civicos://san-rafael/decisions`
- `civicos://san-rafael/corpus-stats`

## Prompts
- `research_topic(topic)` - Multi-step research
- `meeting_prep(description)` - Meeting preparation

Jurisdiction: san-rafael (env: CIVICOS_JURISDICTION)"""


# ─────────── MCP RESOURCES ───────────
# Browsable data that clients can discover and explore

@mcp.resource("civicos://san-rafael/meetings")
def list_meetings() -> str:
    """List recent and upcoming city council meetings."""
    if civicos_client is None:
        return "Error: Civic client not initialized."

    try:
        # Get recent meetings from storage
        meetings = civicos_client._storage.get_meetings(civicos_client.jurisdiction, limit=20)

        result_parts = []
        result_parts.append("# San Rafael Meetings")
        result_parts.append(f"*{len(meetings)} recent meetings*")
        result_parts.append("")

        for m in meetings[:20]:
            # Handle both dict and object returns
            if isinstance(m, dict):
                date_val = m.get('meeting_datetime') or m.get('date')
                title = m.get('title') or m.get('body') or 'Meeting'
                m_id = m.get('id', 'N/A')
            else:
                date_val = getattr(m, 'date', None) or getattr(m, 'meeting_datetime', None)
                title = getattr(m, 'title', None) or getattr(m, 'body', 'Meeting')
                m_id = getattr(m, 'id', 'N/A')

            date_str = date_val.strftime("%Y-%m-%d") if date_val and hasattr(date_val, 'strftime') else str(date_val)[:10] if date_val else "TBD"
            result_parts.append(f"- **{date_str}:** {title}")
            result_parts.append(f"  ID: `{m_id}`")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error listing meetings: {str(e)}"


@mcp.resource("civicos://san-rafael/decisions")
def list_decisions() -> str:
    """List recent city council decisions."""
    if civicos_client is None:
        return "Error: Civic client not initialized."

    try:
        decisions = civicos_client._storage.get_decisions(civicos_client.jurisdiction, limit=20)

        result_parts = []
        result_parts.append("# San Rafael Decisions")
        result_parts.append(f"*{len(decisions)} recent decisions*")
        result_parts.append("")

        for d in decisions[:20]:
            # Handle both dict and object returns
            if isinstance(d, dict):
                date_val = d.get('date')
                outcome = d.get('outcome', 'pending')
                title = d.get('title', 'Decision')[:60]
            else:
                date_val = getattr(d, 'date', None)
                outcome = getattr(d, 'outcome', 'pending')
                title = (getattr(d, 'title', 'Decision') or 'Decision')[:60]

            date_str = date_val.strftime("%Y-%m-%d") if date_val and hasattr(date_val, 'strftime') else str(date_val)[:10] if date_val else "N/A"
            result_parts.append(f"- **{date_str}:** {title}...")
            result_parts.append(f"  Outcome: {outcome}")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error listing decisions: {str(e)}"


@mcp.resource("civicos://san-rafael/budget-departments")
def list_budget_departments() -> str:
    """List city budget departments and totals."""
    if civicos_client is None:
        return "Error: Civic client not initialized."

    try:
        summary = civicos_client.budget_summary()

        result_parts = []
        result_parts.append("# San Rafael Budget by Department")

        if summary:
            total = sum(s.budgeted_dollars for s in summary)
            result_parts.append(f"**Total:** ${total:,.0f}")
            result_parts.append("")

            for s in sorted(summary, key=lambda x: x.budgeted_dollars, reverse=True):
                pct = (s.budgeted_dollars / total * 100) if total > 0 else 0
                result_parts.append(f"- **{s.name}:** ${s.budgeted_dollars:,.0f} ({pct:.1f}%)")
        else:
            result_parts.append("No budget data available.")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error listing budget: {str(e)}"


@mcp.resource("civicos://san-rafael/corpus-stats")
def get_corpus_stats() -> str:
    """Get data inventory and corpus statistics."""
    if civicos_client is None:
        return "Error: Civic client not initialized."

    try:
        storage = civicos_client._storage
        jurisdiction = civicos_client.jurisdiction

        result_parts = []
        result_parts.append("# San Rafael Data Inventory")
        result_parts.append(f"**Jurisdiction:** {jurisdiction}")
        result_parts.append("")

        result_parts.append("## Corpus Counts")

        # Get counts by fetching data (limited approach but works)
        corpus_counts = {}
        try:
            corpus_counts['meetings'] = len(storage.get_meetings(jurisdiction, limit=1000))
        except Exception:
            pass
        try:
            corpus_counts['decisions'] = len(storage.get_decisions(jurisdiction, limit=1000))
        except Exception:
            pass
        try:
            corpus_counts['issues'] = len(storage.get_issues(jurisdiction_id=jurisdiction, limit=2000))
        except Exception:
            pass

        total_records = 0
        for corpus, count in corpus_counts.items():
            if count > 0:
                result_parts.append(f"- **{corpus}:** {count:,}+ records")
                total_records += count

        result_parts.append("")
        result_parts.append("*Note: Counts may be limited. Use /data-status for complete inventory.*")

        return "\n".join(result_parts)

    except Exception as e:
        return f"Error getting corpus stats: {str(e)}"


# ─────────── MCP PROMPTS ───────────
# Discoverable workflow templates for common tasks

@mcp.prompt()
def research_topic(topic: str) -> str:
    """
    Research a civic topic comprehensively.

    Guides the LLM through a multi-step research process combining
    regulatory context, historical decisions, and community input.
    """
    return f"""Research the civic topic: "{topic}"

Please use the following tools to gather comprehensive information:

1. **Regulatory Context**: Call `search_regulatory_stack("{topic}")` to find relevant local, state, and federal regulations.

2. **Historical Decisions**: Call `search_meeting_history("{topic}")` to find past council decisions and what was said.

3. **Community Interest**: Call `find_similar_issues("{topic}")` to see if residents have reported related issues.

4. **Budget Impact**: Call `search_budget()` and look for departments related to {topic}.

After gathering this information, synthesize a summary that includes:
- Key regulations that apply
- How the council has handled similar issues
- Community sentiment and engagement level
- Budget considerations

Provide actionable insights for someone wanting to engage on this topic."""


@mcp.prompt()
def meeting_prep(meeting_description: str) -> str:
    """
    Prepare for an upcoming city council meeting.

    Guides the LLM through gathering all relevant context for effective
    participation in a specific meeting or agenda item.
    """
    return f"""Help me prepare for this meeting/agenda item: "{meeting_description}"

Please use the following tools:

1. **Find the Meeting**: Call `get_upcoming_meetings()` to find meetings matching this description.

2. **Background Research**: Based on the agenda topics:
   - Call `search_meeting_history()` for relevant past decisions
   - Call `search_agenda_packets()` for staff reports and analysis
   - Call `search_regulatory_stack()` for applicable regulations

3. **Public Sentiment**: Call `get_public_testimony()` to see what residents have said about similar topics.

4. **If you find an agenda item ID**: Call `prepare_for_meeting(agenda_item_id)` for structured prep materials.

Provide a briefing that includes:
- Meeting logistics (date, time, location)
- Background on relevant agenda items
- Key points from staff reports
- What others have said about this
- Suggested talking points if I want to participate"""


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CivicOS MCP Server")
    parser.add_argument(
        "--transport", "-t",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport protocol: stdio (Claude Desktop), http (ChatGPT/Claude.ai), sse (legacy)"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="Port for HTTP/SSE transport (default: 8000)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host for HTTP/SSE transport (default: 0.0.0.0)"
    )
    args = parser.parse_args()

    # Map 'http' to 'streamable-http' (the actual transport name)
    transport = "streamable-http" if args.transport == "http" else args.transport

    logger.info(f"Starting CivicOS MCP Server (transport={transport})")

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # For HTTP/SSE, we need to reconfigure the server with host/port
        # FastMCP settings are set at construction time
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        logger.info(f"Listening on http://{args.host}:{args.port}/mcp")
        mcp.run(transport=transport)