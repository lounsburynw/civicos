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

import logging
import os
import sys
from typing import Optional
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Load environment variables (for DATABASE_URL, etc.)
load_dotenv()

# Add parent directory to path for validator import
sys.path.append(str(Path(__file__).parent.parent))
from civicos_input_validator import validate_civic_input

# Add packages to path for Civic import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "packages" / "civicos" / "src"))
from civicos import CivicOS

# Configure logging to stderr (required for MCP servers)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Civic API client for vector search tools
# Default jurisdiction is San Rafael (pilot city), can be overridden per-tool
DEFAULT_JURISDICTION = os.getenv('CIVICOS_JURISDICTION', 'san-rafael')
try:
    civicos_client = CivicOS(DEFAULT_JURISDICTION)
    logger.info(f"Civic client initialized for {DEFAULT_JURISDICTION} (storage: {type(civicos_client._storage).__name__})")
except Exception as e:
    civicos_client = None
    logger.warning(f"Failed to initialize Civic client: {e}")

# Initialize FastMCP server
mcp = FastMCP("CivicOS Engagement Server")

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
        result_parts.append(f"Jurisdiction: {stack.jurisdiction}")
        result_parts.append(f"Retrieved: {stack.retrieved_at}")
        result_parts.append("")

        # Federal context
        result_parts.append("## Federal")
        if stack.federal:
            for item in stack.federal[:5]:  # Limit to 5 most relevant
                if isinstance(item, dict):
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
                    title = item.get('title', item.get('bill_number', str(item)))
                    result_parts.append(f"- {title}")
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
                    text = item.get('text', item.get('section', str(item)))[:200]
                    section = item.get('section_number', '')
                    if section:
                        result_parts.append(f"- Section {section}: {text}...")
                    else:
                        result_parts.append(f"- {text}...")
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

    Returns:
        Formatted text with decisions and transcript excerpts

    Example:
        >>> search_meeting_history("homeless services")
        # Returns past decisions and what was discussed about homeless services
    """
    logger.info(f"Searching meeting history for: {query}")

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

        # Get decisions using what_happened()
        decisions = civicos_client.what_happened(sanitized_query)

        result_parts.append("## Decisions")
        if decisions:
            for d in decisions[:limit]:
                result_parts.append(f"### {d.title}")
                result_parts.append(f"- Date: {d.date}")
                result_parts.append(f"- Outcome: {d.outcome or 'N/A'}")
                result_parts.append(f"- Body: {d.body or 'N/A'}")
                if d.votes:
                    result_parts.append(f"- Votes: {d.votes}")
                result_parts.append("")
        else:
            result_parts.append("No decisions found matching this query.")
        result_parts.append("")

        # Get transcript excerpts if requested
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
) -> str:
    """
    Find community members and issues related to a topic.

    Uses semantic matching to find issues reported through 311/SeeClickFix and
    other sources that relate to the topic. Returns a summary of community
    engagement around the issue.

    Args:
        topic: Topic to search (e.g., "traffic safety", "pothole", "graffiti")
        semantic: If True, use semantic matching to find related issues beyond exact matches

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
        # Use Civic API's whos_with_me() for semantic issue matching
        community = civicos_client.whos_with_me(sanitized_topic, semantic=semantic)

        result_parts = []
        result_parts.append(f"# Community Engagement: {community.topic}")
        result_parts.append(f"Jurisdiction: {community.jurisdiction}")
        result_parts.append("")

        result_parts.append("## Summary")
        result_parts.append(f"- **Related issues found:** {community.follower_count}")
        result_parts.append("")

        if community.follower_count > 0:
            result_parts.append("This indicates community interest in this topic.")
            result_parts.append("Citizens have reported related issues through 311/SeeClickFix.")
            if semantic:
                result_parts.append("*(Using semantic matching to find related issue types)*")
        else:
            result_parts.append("No related issues found in the database.")
            result_parts.append("This could mean:")
            result_parts.append("- The topic hasn't been reported through 311 channels")
            result_parts.append("- Try different search terms")

        result_parts.append("")

        # Include any recent voices if available
        if community.recent_voices:
            result_parts.append("## Recent Voices")
            for voice in community.recent_voices[:5]:
                result_parts.append(f"- {voice}")

        # Include active initiatives if available
        if community.active_initiatives:
            result_parts.append("## Active Initiatives")
            for initiative in community.active_initiatives[:5]:
                result_parts.append(f"- {initiative}")

        return "\n".join(result_parts)

    except Exception as e:
        logger.error(f"Error finding similar issues: {e}")
        return f"Error finding similar issues: {str(e)}"


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
        if sanitized_agenda_item:
            result_parts.append(f"Filtered to agenda item: {sanitized_agenda_item}")
        result_parts.append("")

        # Separate PDF results from transcript results
        pdf_results = [r for r in results if r.source_type == "pdf"]
        transcript_results = [r for r in results if r.source_type == "transcript"]

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
        if topic_list:
            result_parts.append(f"Filtered by topics: {', '.join(topic_list)}")
        result_parts.append("")

        if not results:
            result_parts.append("No upcoming meetings found in this time period.")
            return "\n".join(result_parts)

        meetings = [r for r in results if hasattr(r, 'agenda_items')]
        elections = [r for r in results if hasattr(r, 'election_type')]

        for meeting in meetings:
            date_str = meeting.date.strftime("%A, %B %d, %Y at %I:%M %p") if meeting.date else "TBD"
            result_parts.append(f"## {meeting.title or meeting.body or 'Meeting'}")
            result_parts.append(f"**Date:** {date_str}")
            if meeting.location:
                result_parts.append(f"**Location:** {meeting.location}")
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
                            result_parts.append(f"*[Video: {link.start_timestamp}]*")
                        result_parts.append("")

                if other_discussion:
                    result_parts.append("### Council Discussion")
                    for link in other_discussion[:3]:
                        speaker = link.speaker_name or link.speaker or "Speaker"
                        role = f" ({link.speaker_role})" if link.speaker_role else ""
                        result_parts.append(f"**{speaker}{role}:**")
                        result_parts.append(f"> {link.text[:300]}...")
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

        # Regulatory Context
        if prep.regulatory_context:
            result_parts.append("## Relevant Regulations")
            if prep.regulatory_context.get('state'):
                for item in prep.regulatory_context['state'][:3]:
                    if isinstance(item, dict):
                        result_parts.append(f"- **State:** {item.get('bill', item.get('title', str(item)))}")
            if prep.regulatory_context.get('federal'):
                for item in prep.regulatory_context['federal'][:2]:
                    if isinstance(item, dict):
                        result_parts.append(f"- **Federal:** {item.get('program_name', str(item))}")
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
    """Friendly category-based guidance for residents."""
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
- "How many complaints about traffic on Lincoln Ave?"

Tool: `find_similar_issues()`

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
            corpus_counts['issues'] = len(storage.get_issues(jurisdiction, limit=2000))
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