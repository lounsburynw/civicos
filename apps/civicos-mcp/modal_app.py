"""
Modal deployment for CivicOS MCP Server.

Deploys the complete MCP server (30 tools) as a serverless web endpoint on Modal,
proxied through Cloudflare for the production domain.

Production URL:
    https://san-rafael.civicosproject.org/mcp

Architecture:
    Claude.ai/ChatGPT -> Cloudflare Worker -> Modal -> Supabase

Key features:
    - Serverless scaling (0 to N instances based on traffic)
    - min_containers=1 prevents cold starts
    - Same platform as relay worker and vector indexer (consolidation)
    - Cloudflare proxy provides custom domain without Modal Team plan

Setup:
    1. Install Modal CLI: pip install modal
    2. Authenticate: modal token new
    3. Create secret with required env vars:
       modal secret create civicos-env \
           DATABASE_URL="postgresql://..." \
           RELAY_DATABASE_URL="postgresql://..." \
           CIVICOS_JURISDICTION="city-san-rafael"
    4. Deploy: modal deploy apps/civicos-mcp/modal_app.py

Usage:
    # Local testing
    modal serve apps/civicos-mcp/modal_app.py

    # Deploy to production
    modal deploy apps/civicos-mcp/modal_app.py

Endpoints:
    Production: https://san-rafael.civicosproject.org/mcp
    Health:     https://san-rafael.civicosproject.org/health
    Modal direct: https://lounsburynw--civicos-mcp-mcpserver-mcp-endpoint.modal.run
"""

import modal

# ─────────── MODAL APP DEFINITION ───────────

app = modal.App("civicos-mcp")

# Build image with all MCP dependencies
# This mirrors the Dockerfile.mcp dependencies
mcp_image = (
    modal.Image.debian_slim(python_version="3.11")
    # System dependencies for psycopg2, etc.
    .apt_install("libpq-dev", "gcc", "curl")
    # Python dependencies - same as Dockerfile.mcp
    .pip_install(
        # MCP server
        "mcp[cli]>=1.13.1",
        "fastmcp>=0.1.0",
        # Database
        "psycopg2-binary>=2.9.0",
        # Embeddings (for vector search)
        "fastembed>=0.3.0",
        "numpy<2",
        # HTTP/async
        "fastapi[standard]>=0.100.0",  # Must be Pydantic v2 compatible
        "httpx>=0.24.0",
        "uvicorn>=0.30.0",
        "starlette>=0.38.0",
        # Utils
        "python-dotenv>=1.0.0",
        "pydantic>=2.0.0",
        "pyyaml>=6.0.0",
        # LangGraph (for coordination workflows)
        "langgraph>=0.2.0",
        "langchain-core>=0.3.0",
        "langchain-anthropic>=0.3.0",
    )
    # Pre-download embedding model during image build (avoids 30-60s download at runtime)
    .run_commands(
        "python -c \"from fastembed import TextEmbedding; TextEmbedding('nomic-ai/nomic-embed-text-v1.5')\""
    )
    # Add local packages
    .add_local_python_source("civicos")
    .add_local_python_source("civicos_config")
    .add_local_python_source("civicos_relay")
    # Add MCP server code (replaces deprecated modal.Mount)
    .add_local_dir("apps/civicos-mcp", remote_path="/app/civicos-mcp")
    .add_local_file("apps/civicos_input_validator.py", remote_path="/app/civicos_input_validator.py")
)


# ─────────── MCP SERVER CLASS ───────────
# Uses Modal's cls pattern for proper singleton initialization
# CivicOS client and embedding model are initialized once per container

@app.cls(
    image=mcp_image,
    secrets=[modal.Secret.from_name("civicos-env")],
    memory=4096,  # 4GB for embedding model
    timeout=300,  # 5 min timeout for complex queries
    min_containers=1,  # Always keep 1 instance ready (no cold starts)
)
@modal.concurrent(max_inputs=20)
class MCPServer:
    """
    Modal-deployed MCP server with full parity to Fly.io deployment.

    Uses the existing civicos_server.py for all tool definitions.
    """

    @modal.enter()
    def initialize(self):
        """
        Initialize on container startup (not per-request).

        This runs once when the container starts, making subsequent
        requests fast since CivicOS and embeddings are already loaded.
        """
        import os
        import sys
        import logging
        import time

        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger("civicos-mcp-modal")

        # Add paths for imports
        sys.path.insert(0, "/app")
        sys.path.insert(0, "/app/civicos-mcp")

        self.logger.info("Initializing CivicOS MCP Server on Modal...")

        # Import CivicOS and initialize
        from civicos import CivicOS

        jurisdiction = os.getenv("CIVICOS_JURISDICTION", "city-san-rafael")
        self.jurisdiction = jurisdiction

        start = time.time()
        self.civic = CivicOS(jurisdiction)
        init_time = time.time() - start
        self.logger.info(
            f"CivicOS initialized for {jurisdiction} "
            f"(storage: {type(self.civic._storage).__name__}, {init_time:.1f}s)"
        )

        # Pre-warm embedding model
        if self.civic._vectors is not None:
            self.logger.info("Pre-warming embedding model...")
            start = time.time()
            provider = self.civic._vectors._embedding_provider
            _ = provider.encode(["warmup query"])
            warmup_time = time.time() - start
            self.logger.info(f"Embedding model ready ({provider.model_name}, {warmup_time:.1f}s)")

        # Import the input validator
        from civicos_input_validator import validate_civic_input
        self.validate_input = validate_civic_input

        # Import federation components
        from federation import (
            get_registry,
            query_peers_parallel,
            format_federation_summary,
            PeerQueryResult,
        )
        self.get_registry = get_registry
        self.query_peers_parallel = query_peers_parallel
        self.format_federation_summary = format_federation_summary

        # Initialize tool registry with all 32 tools
        self._init_tools()

        self.logger.info(f"MCP Server ready with {len(self.tools)} tools")

    def _init_tools(self):
        """Initialize the tool registry mapping tool names to handlers."""
        from datetime import datetime, timedelta
        from collections import Counter

        # Store references for use in handlers
        civic = self.civic
        logger = self.logger
        validate_input = self.validate_input
        jurisdiction = self.jurisdiction

        # Tool registry: name -> {"description": ..., "parameters": ..., "handler": ...}
        self.tools = {}

        # ─────────── Core Civic Tools ───────────

        self.tools["search_meeting_history"] = {
            "description": "Search past city council meetings and decisions on a topic",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g., 'homeless shelter', 'bike lane')"},
                    "include_transcripts": {"type": "boolean", "default": True, "description": "Include video transcript excerpts"},
                    "limit": {"type": "integer", "default": 10, "description": "Maximum results per category"},
                },
                "required": ["query"],
            },
            "handler": self._search_meeting_history,
        }

        self.tools["get_upcoming_meetings"] = {
            "description": "Get upcoming city council meetings and agenda items",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "default": 30, "description": "Days to look ahead"},
                },
            },
            "handler": self._get_upcoming_meetings,
        }

        self.tools["find_similar_issues"] = {
            "description": "Find community issues related to a topic via 311/SeeClickFix",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to search (e.g., 'traffic safety', 'pothole')"},
                    "semantic": {"type": "boolean", "default": True, "description": "Use semantic matching"},
                    "limit": {"type": "integer", "default": 20, "description": "Maximum results"},
                },
                "required": ["topic"],
            },
            "handler": self._find_similar_issues,
        }

        self.tools["search_regulatory_stack"] = {
            "description": "Search relevant laws and regulations across local, state, and federal levels",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to search (e.g., 'accessory dwelling units')"},
                    "jurisdiction": {"type": "string", "default": "san-rafael"},
                },
                "required": ["topic"],
            },
            "handler": self._search_regulatory_stack,
        }

        self.tools["compose_public_comment"] = {
            "description": "Get context for writing a public comment on a civic agenda item",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_title": {"type": "string", "description": "Title/description of the agenda item"},
                    "topic": {"type": "string", "description": "Optional topic for finding related context"},
                },
                "required": ["item_title"],
            },
            "handler": self._compose_public_comment,
        }

        self.tools["city_pulse"] = {
            "description": "Get a comprehensive snapshot of city activity (meetings, decisions, issues)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "default": 7, "description": "Days to look ahead"},
                    "days_back": {"type": "integer", "default": 30, "description": "Days to look back"},
                },
            },
            "handler": self._city_pulse,
        }

        self.tools["get_issue_analytics"] = {
            "description": "Get aggregate statistics about 311/SeeClickFix issues",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "date_range": {"type": "string", "description": "Filter: '2024', '2024-Q4', 'last_90_days', 'last_year'"},
                },
            },
            "handler": self._get_issue_analytics,
        }

        self.tools["get_issue_trends"] = {
            "description": "Analyze trends in 311 issues over time",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_type": {"type": "string", "description": "Filter by issue type"},
                    "granularity": {"type": "string", "default": "month", "description": "Time grouping: week, month, quarter, year"},
                },
            },
            "handler": self._get_issue_trends,
        }

        self.tools["geo_search_issues"] = {
            "description": "Search 311 issues by geographic area (street, neighborhood)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "area": {"type": "string", "description": "Street name, corridor, or neighborhood"},
                    "radius_blocks": {"type": "integer", "default": 2, "description": "Search radius in blocks"},
                    "issue_types": {"type": "array", "items": {"type": "string"}, "description": "Filter by types"},
                },
                "required": ["area"],
            },
            "handler": self._geo_search_issues,
        }

        self.tools["search_budget"] = {
            "description": "Search city budget data by department or category",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Department or category to search"},
                    "fiscal_year": {"type": "string", "description": "Filter by fiscal year (e.g., 'FY25-26')"},
                },
            },
            "handler": self._search_budget,
        }

        self.tools["get_public_testimony"] = {
            "description": "Get public testimony excerpts on a topic from meeting transcripts",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic to search"},
                    "limit": {"type": "integer", "default": 5, "description": "Maximum excerpts to return"},
                },
                "required": ["topic"],
            },
            "handler": self._get_public_testimony,
        }

        self.tools["search_agenda_packets"] = {
            "description": "Search agenda packets and staff reports",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
            "handler": self._search_agenda_packets,
        }

        self.tools["get_comment_guidelines"] = {
            "description": "Get public comment guidelines and submission information",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "jurisdiction": {"type": "string", "default": "san-rafael"},
                },
            },
            "handler": self._get_comment_guidelines,
        }

        self.tools["get_started"] = {
            "description": "Get an overview of what's happening in local government",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
            "handler": self._get_started,
        }

        # ─────────── 311 Analysis Tools ───────────

        self.tools["query_issue_data"] = {
            "description": "Query 311 issue data with flexible grouping and filtering",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "group_by": {"type": "string", "default": "type", "description": "Group by: type, status, street, month, year"},
                    "filter_type": {"type": "string", "description": "Filter by issue type"},
                    "filter_status": {"type": "string", "description": "Filter by status"},
                    "filter_street": {"type": "string", "description": "Filter by street name"},
                    "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                    "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
            "handler": self._query_issue_data,
        }

        self.tools["get_issue_resolution_stats"] = {
            "description": "Get resolution statistics for 311 issues (response time, rates)",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_type": {"type": "string", "description": "Filter by issue type"},
                    "zip_code": {"type": "string", "description": "Filter by zip code"},
                },
            },
            "handler": self._get_issue_resolution_stats,
        }

        self.tools["detect_trends"] = {
            "description": "Detect significant trends in 311 issue patterns",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "lookback_months": {"type": "integer", "default": 6, "description": "Compare last N months to previous N months"},
                    "min_change_pct": {"type": "number", "default": 20.0, "description": "Minimum % change to report"},
                    "zip_code": {"type": "string", "description": "Filter to specific zip code"},
                },
            },
            "handler": self._detect_trends,
        }

        self.tools["get_issue_sample"] = {
            "description": "Get a sample of raw 311 issues for pattern analysis",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "sample_size": {"type": "integer", "default": 30, "description": "Number of issues to return (max 50)"},
                    "filter_type": {"type": "string", "description": "Filter by issue type"},
                    "filter_status": {"type": "string", "description": "Filter by status"},
                    "filter_street": {"type": "string", "description": "Filter by street name"},
                    "random_sample": {"type": "boolean", "default": True, "description": "Random sample or most recent"},
                },
            },
            "handler": self._get_issue_sample,
        }

        self.tools["find_issues_near_address"] = {
            "description": "Find 311 issues near a specific address or intersection",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "address": {"type": "string", "description": "Address or intersection to search near"},
                    "radius_blocks": {"type": "integer", "default": 2, "description": "Search radius in blocks"},
                    "issue_type": {"type": "string", "description": "Filter by issue type"},
                },
                "required": ["address"],
            },
            "handler": self._find_issues_near_address,
        }

        self.tools["find_repeat_issues"] = {
            "description": "Find locations with repeated issues of the same type",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_type": {"type": "string", "description": "Filter by issue type"},
                    "min_occurrences": {"type": "integer", "default": 3, "description": "Minimum repeats to flag"},
                },
            },
            "handler": self._find_repeat_issues,
        }

        self.tools["get_seasonal_patterns"] = {
            "description": "Analyze seasonal patterns in 311 issues",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "issue_type": {"type": "string", "description": "Filter by issue type"},
                },
            },
            "handler": self._get_seasonal_patterns,
        }

        self.tools["compare_zip_codes"] = {
            "description": "Compare 311 issue patterns between zip codes",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "zip_codes": {"type": "array", "items": {"type": "string"}, "description": "Zip codes to compare"},
                },
                "required": ["zip_codes"],
            },
            "handler": self._compare_zip_codes,
        }

        self.tools["neighborhood_report"] = {
            "description": "Generate a comprehensive report for a neighborhood",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "neighborhood": {"type": "string", "description": "Neighborhood name or area"},
                },
                "required": ["neighborhood"],
            },
            "handler": self._neighborhood_report,
        }

        # ─────────── Council/Voting Tools ───────────

        self.tools["get_voting_record"] = {
            "description": "Get an elected official's voting record",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "official_name": {"type": "string", "description": "Name of the official"},
                    "topic": {"type": "string", "description": "Optional topic filter"},
                    "since": {"type": "string", "description": "Start date filter (YYYY-MM-DD)"},
                },
                "required": ["official_name"],
            },
            "handler": self._get_voting_record,
        }

        self.tools["get_decision_context"] = {
            "description": "Get decisions with linked transcript excerpts showing what was discussed",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            "handler": self._get_decision_context,
        }

        # ─────────── Financial Tools ───────────

        self.tools["get_funding_flow"] = {
            "description": "Trace intergovernmental funding from federal to state to city budget",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "program": {"type": "string", "description": "Program name (e.g., CDBG, HOME)"},
                    "cfda_number": {"type": "string", "description": "Federal CFDA number"},
                },
            },
            "handler": self._get_funding_flow,
        }

        self.tools["get_federal_expenditures"] = {
            "description": "Get audited federal expenditures from Single Audit (FAC) data",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "cfda_number": {"type": "string", "description": "Filter by CFDA/ALN number"},
                    "audit_year": {"type": "integer", "description": "Audit fiscal year"},
                },
            },
            "handler": self._get_federal_expenditures,
        }

        self.tools["get_intergovernmental_revenue"] = {
            "description": "Get intergovernmental revenue from CA State Controller data",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "fiscal_year": {"type": "integer", "description": "Fiscal year"},
                    "source": {"type": "string", "description": "Filter by source (federal, state, county)"},
                },
            },
            "handler": self._get_intergovernmental_revenue,
        }

        # ─────────── Action Tools ───────────

        self.tools["get_comment_template"] = {
            "description": "Get a fill-in-the-blank public comment template",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "item_title": {"type": "string", "description": "Title of the agenda item"},
                    "stance": {"type": "string", "description": "Stance: support, oppose, question, neutral"},
                    "key_points": {"type": "string", "description": "Newline-separated points to include"},
                },
                "required": ["item_title"],
            },
            "handler": self._get_comment_template,
        }

        self.tools["prepare_for_meeting"] = {
            "description": "Get preparation materials for participating in a city council meeting",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agenda_item_id": {"type": "string", "description": "ID of the agenda item to prepare for"},
                },
                "required": ["agenda_item_id"],
            },
            "handler": self._prepare_for_meeting,
        }

    # ─────────── Tool Handlers ───────────

    def _search_meeting_history(self, args: dict) -> str:
        """Search past city council meetings and decisions."""
        query = args.get("query", "")
        include_transcripts = args.get("include_transcripts", True)
        limit = args.get("limit", 10)

        # Validate input
        is_valid, sanitized, error = self.validate_input({"query": query})
        if not is_valid:
            return f"Error: Invalid input - {error}"
        query = sanitized.get("query", query)

        result_parts = [f"# Meeting History: {query}", ""]

        try:
            decisions = self.civic.what_happened(query)

            result_parts.append(f"## Decisions ({self.jurisdiction})")
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

            if include_transcripts:
                result_parts.append("## What Was Said (Transcript Excerpts)")
                excerpts = self.civic.what_was_said(query, top_k=limit)
                if excerpts:
                    for ex in excerpts:
                        speaker = ex.speaker_name or ex.speaker or "Unknown"
                        result_parts.append(f"### {speaker}")
                        result_parts.append(f"> {ex.text[:500]}...")
                        result_parts.append("")
                else:
                    result_parts.append("No transcript excerpts found.")

        except Exception as e:
            self.logger.error(f"Error in search_meeting_history: {e}")
            return f"Error searching meeting history: {str(e)}"

        return "\n".join(result_parts)

    def _get_upcoming_meetings(self, args: dict) -> str:
        """Get upcoming city council meetings."""
        days = args.get("days", 30)

        try:
            meetings = self.civic.whats_next(days=days)

            result_parts = [f"# Upcoming Meetings (next {days} days)", ""]

            if meetings:
                for m in meetings:
                    title = getattr(m, 'title', str(m))
                    date = getattr(m, 'meeting_datetime', getattr(m, 'date', 'TBD'))
                    result_parts.append(f"- **{title}** - {date}")
            else:
                result_parts.append("No upcoming meetings found.")

            return "\n".join(result_parts)

        except Exception as e:
            self.logger.error(f"Error in get_upcoming_meetings: {e}")
            return f"Error getting upcoming meetings: {str(e)}"

    def _find_similar_issues(self, args: dict) -> str:
        """Find community issues related to a topic."""
        topic = args.get("topic", "")
        semantic = args.get("semantic", True)
        limit = args.get("limit", 20)

        is_valid, sanitized, error = self.validate_input({"topic": topic})
        if not is_valid:
            return f"Error: Invalid input - {error}"
        topic = sanitized.get("topic", topic)

        try:
            result_parts = [f"# Community Issues: {topic}", ""]

            if semantic and self.civic._vectors is not None:
                results = self.civic._vectors.search(
                    topic,
                    self.jurisdiction,
                    'issues',
                    top_k=limit,
                )
                result_parts.append(f"**Related issues found:** {len(results)}")
                result_parts.append("")

                for r in results:
                    content = r.content[:200] if r.content else "No description"
                    score = r.score if hasattr(r, 'score') else None
                    if score:
                        result_parts.append(f"- **[{score:.0%} match]** {content}...")
                    else:
                        result_parts.append(f"- {content}...")
            else:
                result_parts.append("Semantic search unavailable.")

            return "\n".join(result_parts)

        except Exception as e:
            self.logger.error(f"Error in find_similar_issues: {e}")
            return f"Error finding similar issues: {str(e)}"

    def _search_regulatory_stack(self, args: dict) -> str:
        """Search regulatory stack for a topic."""
        topic = args.get("topic", "")

        is_valid, sanitized, error = self.validate_input({"topic": topic})
        if not is_valid:
            return f"Error: Invalid input - {error}"
        topic = sanitized.get("topic", topic)

        try:
            stack = self.civic.what_applies(topic)

            result_parts = [f"# Regulatory Stack: {stack.topic}", ""]

            # Federal
            result_parts.append("## Federal")
            if stack.federal:
                for item in stack.federal[:5]:
                    if isinstance(item, dict):
                        result_parts.append(f"- {item.get('title', str(item))}")
                    else:
                        result_parts.append(f"- {item}")
            else:
                result_parts.append("No federal regulations found.")
            result_parts.append("")

            # State
            result_parts.append("## State")
            if stack.state:
                for item in stack.state[:5]:
                    if isinstance(item, dict):
                        bill = item.get('bill_number', '')
                        name = item.get('bill_name', '')
                        result_parts.append(f"- **{bill}**: {name}" if bill else f"- {name}")
                    else:
                        result_parts.append(f"- {item}")
            else:
                result_parts.append("No state regulations found.")
            result_parts.append("")

            # Local
            result_parts.append("## Local")
            if stack.local:
                for item in stack.local[:5]:
                    if isinstance(item, dict):
                        section = item.get('section_number', '')
                        name = item.get('section_name', '')
                        result_parts.append(f"- **{section}**: {name}" if section else f"- {str(item)[:200]}")
                    else:
                        result_parts.append(f"- {str(item)[:200]}")
            else:
                result_parts.append("No local regulations found.")

            return "\n".join(result_parts)

        except Exception as e:
            self.logger.error(f"Error in search_regulatory_stack: {e}")
            return f"Error searching regulatory stack: {str(e)}"

    def _compose_public_comment(self, args: dict) -> str:
        """Get context for writing a public comment."""
        item_title = args.get("item_title", "")
        topic = args.get("topic") or item_title

        is_valid, sanitized, error = self.validate_input({"item_title": item_title, "topic": topic})
        if not is_valid:
            return f"Error: Invalid input - {error}"

        result_parts = [f"# Public Comment Context: {item_title}", ""]

        result_parts.append("## Submission Guidelines")
        result_parts.append("")
        result_parts.append("**San Rafael City Council:**")
        result_parts.append("- Email: clerk@cityofsanrafael.org")
        result_parts.append("- Subject line: \"Public Comment - [Agenda Item Title]\"")
        result_parts.append("- Deadline: 5:00 PM day of meeting for written record")
        result_parts.append("- In-person: 3 minutes max, sign up before meeting")
        result_parts.append("")

        # Past testimony
        try:
            testimony = self.civic.get_public_testimony(topic, top_k=3)
            if testimony:
                result_parts.append("## What Others Have Said")
                for t in testimony[:3]:
                    speaker = getattr(t, 'speaker_name', 'Resident')
                    text = getattr(t, 'text', str(t))[:200]
                    result_parts.append(f"**{speaker}:** \"{text}...\"")
                    result_parts.append("")
        except Exception as e:
            self.logger.warning(f"Could not fetch testimony: {e}")

        result_parts.append("## Tips for Effective Comments")
        result_parts.append("")
        result_parts.append("1. State your position clearly in the first sentence")
        result_parts.append("2. Be specific - reference the agenda item by name")
        result_parts.append("3. Share personal impact - how does this affect you?")
        result_parts.append("4. Propose alternatives if opposing")
        result_parts.append("5. Be respectful - address \"Mayor and Council Members\"")
        result_parts.append("6. Include your address to show you're a resident")

        return "\n".join(result_parts)

    def _city_pulse(self, args: dict) -> dict:
        """Get comprehensive city activity snapshot."""
        from datetime import datetime, timedelta
        from collections import Counter

        days_ahead = args.get("days_ahead", 7)
        days_back = args.get("days_back", 30)

        now = datetime.now()
        storage = self.civic._storage

        result = {
            "jurisdiction": self.jurisdiction,
            "generated_at": now.isoformat(),
            "decisions_this_week": [],
            "recent_outcomes": [],
            "community_pulse": {},
        }

        try:
            # Upcoming meetings
            meetings = storage.get_meetings(
                self.jurisdiction,
                since=now,
                until=now + timedelta(days=days_ahead),
                limit=20
            )

            for m in meetings:
                meeting_dt = m.get('meeting_datetime')
                if meeting_dt and hasattr(meeting_dt, 'strftime'):
                    date_str = meeting_dt.strftime("%a, %b %d")
                    time_str = meeting_dt.strftime("%I:%M %p").lstrip('0')
                else:
                    date_str = str(meeting_dt)[:10] if meeting_dt else "TBD"
                    time_str = ""

                result["decisions_this_week"].append({
                    "title": m.get('title') or m.get('body') or 'Meeting',
                    "date": date_str,
                    "time": time_str,
                })

            # Recent decisions
            since_date = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
            decisions = storage.get_decisions(self.jurisdiction, since=since_date, limit=10)

            for d in decisions:
                decision_date = d.get('decision_date') or d.get('meeting_datetime')
                if decision_date and hasattr(decision_date, 'strftime'):
                    date_str = decision_date.strftime("%b %d")
                else:
                    date_str = str(decision_date)[:10] if decision_date else "Recent"

                result["recent_outcomes"].append({
                    "title": d.get('title') or 'Decision',
                    "outcome": d.get('outcome') or d.get('status') or 'decided',
                    "date": date_str,
                })

            # Community pulse (issues)
            issues = storage.get_issues(jurisdiction_id=self.jurisdiction, limit=500)
            if issues:
                type_counts = Counter(i.get('issue_type', 'Other') for i in issues)
                result["community_pulse"] = {
                    "total_issues": len(issues),
                    "top_types": dict(type_counts.most_common(5)),
                }

        except Exception as e:
            self.logger.error(f"Error in city_pulse: {e}")
            result["error"] = str(e)

        return result

    def _get_issue_analytics(self, args: dict) -> str:
        """Get aggregate 311 issue statistics."""
        from collections import Counter

        try:
            issues = self.civic._storage.get_issues(
                jurisdiction_id=self.jurisdiction, limit=5000
            )

            if not issues:
                return f"No 311 issues found for {self.jurisdiction}."

            by_status = Counter(i.get('status', 'unknown') for i in issues)
            by_type = Counter(i.get('issue_type', 'Unknown') for i in issues)

            closed = sum(1 for i in issues if i.get('status', '').lower() in {'closed', 'resolved'})
            resolution_rate = (closed / len(issues) * 100) if issues else 0

            result_parts = [
                f"# 311 Issue Analytics: {self.jurisdiction}",
                f"**Total Issues:** {len(issues):,}",
                f"**Resolution Rate:** {resolution_rate:.1f}%",
                "",
                "## By Status",
            ]
            for status, count in by_status.most_common():
                result_parts.append(f"- {status}: {count}")

            result_parts.extend(["", "## By Type"])
            for itype, count in by_type.most_common(10):
                result_parts.append(f"- {itype}: {count}")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error getting issue analytics: {str(e)}"

    def _get_issue_trends(self, args: dict) -> str:
        """Analyze trends in 311 issues over time."""
        return "Issue trends analysis: Use get_issue_analytics for current data."

    def _geo_search_issues(self, args: dict) -> str:
        """Search issues by geographic area."""
        area = args.get("area", "")

        try:
            issues = self.civic._storage.get_issues(
                jurisdiction_id=self.jurisdiction, limit=2000
            )

            area_lower = area.lower()
            matched = [
                i for i in issues
                if area_lower in (i.get('address', '') or '').lower()
            ]

            result_parts = [
                f"# Issues near: {area}",
                f"**Found:** {len(matched)} issues",
                "",
            ]

            for i in matched[:20]:
                result_parts.append(f"- {i.get('issue_type', 'Issue')}: {i.get('address', 'Unknown')}")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error searching issues: {str(e)}"

    def _search_budget(self, args: dict) -> str:
        """Search city budget data."""
        query = args.get("query", "")

        try:
            budget_items = self.civic._storage.get_budget_items(self.jurisdiction)

            if not budget_items:
                return "No budget data available."

            query_lower = query.lower() if query else ""
            matched = [
                b for b in budget_items
                if not query or query_lower in (b.get('department', '') or '').lower()
                or query_lower in (b.get('category', '') or '').lower()
            ]

            result_parts = [f"# Budget Search: {query or 'All'}", ""]

            for b in matched[:20]:
                dept = b.get('department', 'Unknown')
                amount = b.get('amount', 0)
                result_parts.append(f"- **{dept}**: ${amount:,.0f}")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error searching budget: {str(e)}"

    def _get_public_testimony(self, args: dict) -> str:
        """Get public testimony excerpts."""
        topic = args.get("topic", "")
        limit = args.get("limit", 5)

        try:
            testimony = self.civic.get_public_testimony(topic, top_k=limit)

            result_parts = [f"# Public Testimony: {topic}", ""]

            if testimony:
                for t in testimony:
                    speaker = getattr(t, 'speaker_name', 'Resident')
                    text = getattr(t, 'text', str(t))[:300]
                    result_parts.append(f"**{speaker}:**")
                    result_parts.append(f"> {text}...")
                    result_parts.append("")
            else:
                result_parts.append("No public testimony found.")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error getting testimony: {str(e)}"

    def _search_agenda_packets(self, args: dict) -> str:
        """Search agenda packets and staff reports."""
        query = args.get("query", "")
        limit = args.get("limit", 10)

        try:
            if self.civic._vectors:
                results = self.civic._vectors.search(
                    query, self.jurisdiction, 'chunks', top_k=limit
                )

                result_parts = [f"# Agenda Packet Search: {query}", ""]

                for r in results:
                    result_parts.append(f"- {r.content[:200]}...")

                return "\n".join(result_parts)
            else:
                return "Agenda packet search unavailable."

        except Exception as e:
            return f"Error searching agenda packets: {str(e)}"

    def _get_comment_guidelines(self, args: dict) -> str:
        """Get public comment guidelines."""
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

CONTACT INFO:
- City Clerk: clerk@cityofsanrafael.org
- Council meetings: First and third Monday, 7:00 PM
- City Hall: 1400 Fifth Avenue, San Rafael CA 94901
        """.strip()

    def _get_started(self, args: dict) -> str:
        """Get overview of local government activity."""
        pulse = self._city_pulse({})

        result_parts = [f"# Welcome to {self.jurisdiction.replace('city-', '').title()}", ""]

        # Upcoming meetings
        meetings = pulse.get("decisions_this_week", [])
        if meetings:
            result_parts.append("## Coming Up")
            for m in meetings[:3]:
                result_parts.append(f"- **{m['title']}** - {m['date']}")
            result_parts.append("")

        # Recent decisions
        decisions = pulse.get("recent_outcomes", [])
        if decisions:
            result_parts.append("## Recently Decided")
            for d in decisions[:3]:
                result_parts.append(f"- {d['title']} ({d['outcome']})")
            result_parts.append("")

        result_parts.append("## What Can I Help With?")
        result_parts.append("- Search past council decisions")
        result_parts.append("- Find upcoming meetings")
        result_parts.append("- Discover community issues")
        result_parts.append("- Get help writing public comments")

        return "\n".join(result_parts)

    def _issue_accountability(self, args: dict) -> str:
        """Track city response to issues."""
        return "Issue accountability tracking: Use get_issue_analytics for response statistics."

    def _neighborhood_report(self, args: dict) -> str:
        """Generate neighborhood report."""
        neighborhood = args.get("neighborhood", "")

        issues_result = self._geo_search_issues({"area": neighborhood})

        return f"# Neighborhood Report: {neighborhood}\n\n{issues_result}"

    # ─────────── 311 Analysis Handlers ───────────

    def _query_issue_data(self, args: dict) -> str:
        """Query 311 issue data with flexible grouping and filtering."""
        from collections import Counter
        from datetime import datetime

        group_by = args.get("group_by", "type")
        filter_type = args.get("filter_type")
        filter_status = args.get("filter_status")
        filter_street = args.get("filter_street")
        date_from = args.get("date_from")
        date_to = args.get("date_to")
        limit = args.get("limit", 50)

        try:
            issues = self.civic._storage.get_issues(
                jurisdiction_id=self.jurisdiction,
                status=filter_status,
                limit=5000,
            )

            if not issues:
                return f"No issues found for {self.jurisdiction}."

            # Apply filters
            if filter_type:
                filter_type_lower = filter_type.lower()
                issues = [i for i in issues if filter_type_lower in (i.get('issue_type', '') or '').lower()]

            if filter_street:
                filter_street_lower = filter_street.lower()
                issues = [i for i in issues if filter_street_lower in (i.get('address', '') or '').lower()]

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
            for issue in issues:
                if group_by == "type":
                    key = issue.get('issue_type', 'Unknown')
                elif group_by == "status":
                    key = issue.get('status', 'unknown')
                elif group_by == "street":
                    key = extract_street(issue.get('address'))
                else:
                    key = issue.get('issue_type', 'Unknown')
                grouped[key] += 1

            result_parts = [
                f"# Issue Query Results",
                f"**Grouped by:** {group_by}",
                f"**Total matching issues:** {len(issues):,}",
                "",
                f"## Results by {group_by.title()}",
            ]

            for key, count in grouped.most_common(limit):
                pct = count / len(issues) * 100
                result_parts.append(f"- **{key}:** {count:,} ({pct:.1f}%)")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error querying issue data: {str(e)}"

    def _get_issue_resolution_stats(self, args: dict) -> str:
        """Get resolution statistics for 311 issues."""
        from collections import defaultdict

        issue_type = args.get("issue_type")
        zip_code = args.get("zip_code")

        try:
            issues = self.civic._storage.get_issues(jurisdiction_id=self.jurisdiction, limit=5000)

            if not issues:
                return f"No issues found for {self.jurisdiction}."

            # Apply filters
            if issue_type:
                issue_type_lower = issue_type.lower()
                issues = [i for i in issues if issue_type_lower in (i.get('issue_type', '') or '').lower()]

            if zip_code:
                issues = [i for i in issues if zip_code in (i.get('address', '') or '')]

            if not issues:
                return "No issues match the specified filters."

            total = len(issues)
            closed_statuses = {'closed', 'resolved', 'archived'}
            resolved = [i for i in issues if i.get('status', '').lower() in closed_statuses]
            resolved_count = len(resolved)
            resolution_rate = (resolved_count / total * 100) if total > 0 else 0

            result_parts = [
                f"# Issue Resolution Statistics",
                f"**Total Issues:** {total:,}",
                "",
                "## Overall Resolution",
                f"- **Resolved:** {resolved_count:,} ({resolution_rate:.1f}%)",
                f"- **Still Open:** {total - resolved_count:,}",
            ]

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error getting resolution stats: {str(e)}"

    def _detect_trends(self, args: dict) -> str:
        """Detect significant trends in 311 issue patterns."""
        from datetime import datetime, timedelta
        from collections import Counter

        lookback_months = args.get("lookback_months", 6)
        min_change_pct = args.get("min_change_pct", 20.0)
        zip_code = args.get("zip_code")

        try:
            issues = self.civic._storage.get_issues(jurisdiction_id=self.jurisdiction, limit=5000)

            if zip_code:
                issues = [i for i in issues if zip_code in (i.get('address', '') or '')]

            if not issues:
                return "No issues found for analysis."

            now = datetime.now()
            recent_start = now - timedelta(days=lookback_months * 30)
            previous_start = recent_start - timedelta(days=lookback_months * 30)

            recent_issues = []
            previous_issues = []

            for issue in issues:
                created = issue.get('created_at')
                if not created:
                    continue
                try:
                    if isinstance(created, str):
                        dt = datetime.fromisoformat(created.replace('Z', '+00:00')).replace(tzinfo=None)
                    else:
                        dt = created
                    if dt >= recent_start:
                        recent_issues.append(issue)
                    elif dt >= previous_start:
                        previous_issues.append(issue)
                except:
                    continue

            if not recent_issues and not previous_issues:
                return "Not enough historical data to detect trends."

            recent_counts = Counter(i.get('issue_type', 'Unknown') for i in recent_issues)
            previous_counts = Counter(i.get('issue_type', 'Unknown') for i in previous_issues)

            changes = []
            all_types = set(recent_counts.keys()) | set(previous_counts.keys())
            for issue_type in all_types:
                recent = recent_counts.get(issue_type, 0)
                previous = previous_counts.get(issue_type, 0)
                if previous > 0:
                    pct_change = ((recent - previous) / previous) * 100
                elif recent > 0:
                    pct_change = 100
                else:
                    continue
                if abs(pct_change) >= min_change_pct and (recent >= 3 or previous >= 3):
                    changes.append({'type': issue_type, 'recent': recent, 'previous': previous, 'change': pct_change})

            increasing = sorted([c for c in changes if c['change'] > 0], key=lambda x: -x['change'])
            decreasing = sorted([c for c in changes if c['change'] < 0], key=lambda x: x['change'])

            result_parts = [
                f"# Issue Trends Analysis",
                f"**Period:** Last {lookback_months} months vs previous {lookback_months} months",
                f"**Recent:** {len(recent_issues):,} issues | **Previous:** {len(previous_issues):,} issues",
                "",
            ]

            if increasing:
                result_parts.append("## Increasing Issues")
                for c in increasing[:7]:
                    result_parts.append(f"- **{c['type']}:** {c['previous']} -> {c['recent']} (+{c['change']:.0f}%)")
                result_parts.append("")

            if decreasing:
                result_parts.append("## Decreasing Issues")
                for c in decreasing[:7]:
                    result_parts.append(f"- **{c['type']}:** {c['previous']} -> {c['recent']} ({c['change']:.0f}%)")

            if not increasing and not decreasing:
                result_parts.append("No significant trends detected.")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error detecting trends: {str(e)}"

    def _get_issue_sample(self, args: dict) -> str:
        """Get a sample of raw 311 issues for pattern analysis."""
        import random

        sample_size = min(args.get("sample_size", 30), 50)
        filter_type = args.get("filter_type")
        filter_status = args.get("filter_status")
        filter_street = args.get("filter_street")
        random_sample = args.get("random_sample", True)

        try:
            issues = self.civic._storage.get_issues(
                jurisdiction_id=self.jurisdiction,
                status=filter_status,
                limit=5000,
            )

            if not issues:
                return f"No issues found for {self.jurisdiction}."

            # Apply filters
            if filter_type:
                filter_type_lower = filter_type.lower()
                issues = [i for i in issues if filter_type_lower in (i.get('issue_type', '') or '').lower()]

            if filter_street:
                filter_street_lower = filter_street.lower()
                issues = [i for i in issues if filter_street_lower in (i.get('address', '') or '').lower()]

            if not issues:
                return "No issues match the specified filters."

            # Sample
            if random_sample and len(issues) > sample_size:
                sample = random.sample(issues, sample_size)
            else:
                sample = issues[:sample_size]

            result_parts = [
                f"# Issue Sample",
                f"**Sample size:** {len(sample)} of {len(issues)} matching issues",
                "",
            ]

            for i, issue in enumerate(sample, 1):
                result_parts.append(f"## Issue {i}")
                result_parts.append(f"- **Type:** {issue.get('issue_type', 'Unknown')}")
                result_parts.append(f"- **Status:** {issue.get('status', 'Unknown')}")
                result_parts.append(f"- **Address:** {issue.get('address', 'N/A')}")
                desc = (issue.get('description') or '')[:300]
                if desc:
                    result_parts.append(f"- **Description:** {desc}...")
                result_parts.append("")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error getting issue sample: {str(e)}"

    def _find_issues_near_address(self, args: dict) -> str:
        """Find 311 issues near a specific address."""
        address = args.get("address", "")
        issue_type = args.get("issue_type")

        is_valid, sanitized, error = self.validate_input({"address": address})
        if not is_valid:
            return f"Error: Invalid input - {error}"

        try:
            issues = self.civic._storage.get_issues(
                jurisdiction_id=self.jurisdiction, limit=2000
            )

            # Filter by address proximity (simple string match)
            address_lower = address.lower()
            address_parts = address_lower.split()

            matched = []
            for i in issues:
                issue_addr = (i.get('address', '') or '').lower()
                # Match if any part of search address appears in issue address
                if any(part in issue_addr for part in address_parts if len(part) > 2):
                    matched.append(i)

            # Filter by type if specified
            if issue_type:
                issue_type_lower = issue_type.lower()
                matched = [i for i in matched if issue_type_lower in (i.get('issue_type', '') or '').lower()]

            result_parts = [
                f"# Issues Near: {address}",
                f"**Found:** {len(matched)} issues",
                "",
            ]

            for i in matched[:30]:
                result_parts.append(f"- **{i.get('issue_type', 'Issue')}**: {i.get('address', 'Unknown')}")
                desc = (i.get('description') or '')[:100]
                if desc:
                    result_parts.append(f"  > {desc}...")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error finding nearby issues: {str(e)}"

    def _find_repeat_issues(self, args: dict) -> str:
        """Find locations with repeated issues."""
        from collections import Counter

        issue_type = args.get("issue_type")
        min_occurrences = args.get("min_occurrences", 3)

        try:
            issues = self.civic._storage.get_issues(jurisdiction_id=self.jurisdiction, limit=5000)

            if issue_type:
                issue_type_lower = issue_type.lower()
                issues = [i for i in issues if issue_type_lower in (i.get('issue_type', '') or '').lower()]

            # Group by address
            address_counts = Counter(i.get('address', 'Unknown') for i in issues if i.get('address'))
            repeats = [(addr, count) for addr, count in address_counts.items() if count >= min_occurrences]
            repeats.sort(key=lambda x: -x[1])

            result_parts = [
                f"# Repeat Issue Locations",
                f"**Minimum occurrences:** {min_occurrences}",
                f"**Found:** {len(repeats)} locations with repeat issues",
                "",
            ]

            for addr, count in repeats[:20]:
                result_parts.append(f"- **{addr}**: {count} issues")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error finding repeat issues: {str(e)}"

    def _get_seasonal_patterns(self, args: dict) -> str:
        """Analyze seasonal patterns in 311 issues."""
        from collections import Counter

        issue_type = args.get("issue_type")

        try:
            issues = self.civic._storage.get_issues(jurisdiction_id=self.jurisdiction, limit=5000)

            if issue_type:
                issue_type_lower = issue_type.lower()
                issues = [i for i in issues if issue_type_lower in (i.get('issue_type', '') or '').lower()]

            by_month = Counter()
            for issue in issues:
                created = issue.get('created_at')
                if created:
                    try:
                        if isinstance(created, str):
                            dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        else:
                            dt = created
                        by_month[dt.strftime('%B')] += 1
                    except:
                        continue

            result_parts = [
                f"# Seasonal Patterns",
                f"**Issue type:** {issue_type or 'All'}",
                "",
                "## Issues by Month",
            ]

            month_order = ['January', 'February', 'March', 'April', 'May', 'June',
                          'July', 'August', 'September', 'October', 'November', 'December']
            for month in month_order:
                count = by_month.get(month, 0)
                if count > 0:
                    result_parts.append(f"- **{month}:** {count}")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error analyzing seasonal patterns: {str(e)}"

    def _compare_zip_codes(self, args: dict) -> str:
        """Compare 311 issue patterns between zip codes."""
        from collections import Counter

        zip_codes = args.get("zip_codes", [])

        if not zip_codes or len(zip_codes) < 2:
            return "Please provide at least 2 zip codes to compare."

        try:
            issues = self.civic._storage.get_issues(jurisdiction_id=self.jurisdiction, limit=5000)

            result_parts = [f"# Zip Code Comparison", ""]

            for zip_code in zip_codes[:5]:
                zip_issues = [i for i in issues if zip_code in (i.get('address', '') or '')]
                type_counts = Counter(i.get('issue_type', 'Unknown') for i in zip_issues)

                result_parts.append(f"## {zip_code}")
                result_parts.append(f"**Total issues:** {len(zip_issues)}")
                for itype, count in type_counts.most_common(5):
                    result_parts.append(f"- {itype}: {count}")
                result_parts.append("")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error comparing zip codes: {str(e)}"

    # ─────────── Council/Voting Handlers ───────────

    def _get_voting_record(self, args: dict) -> str:
        """Get an elected official's voting record."""
        official_name = args.get("official_name", "")
        topic = args.get("topic")
        since = args.get("since")

        is_valid, sanitized, error = self.validate_input({"official_name": official_name})
        if not is_valid:
            return f"Error: Invalid input - {error}"

        try:
            record = self.civic.get_voting_record(
                official_name=official_name,
                topic=topic,
                since=since,
            )

            result_parts = [
                f"# Voting Record: {record.official_name}",
                "",
                "## Summary",
                f"- **Total Votes:** {record.total_votes}",
                f"- **Yes Votes:** {record.yes_votes} ({record.yes_percentage:.0f}%)",
                f"- **No Votes:** {record.no_votes} ({record.no_percentage:.0f}%)",
                "",
            ]

            if record.decisions:
                result_parts.append("## Recent Votes")
                for d in record.decisions[:10]:
                    vote_emoji = {"yes": "Y", "no": "N", "absent": "-"}.get(d.get('vote'), "?")
                    result_parts.append(f"- [{vote_emoji}] {d.get('title', 'Item')[:60]} ({d.get('date', 'N/A')})")

            return "\n".join(result_parts)

        except ValueError as e:
            return f"Official not found: {official_name}"
        except Exception as e:
            return f"Error getting voting record: {str(e)}"

    def _get_decision_context(self, args: dict) -> str:
        """Get decisions with linked transcript excerpts."""
        query = args.get("query", "")
        limit = args.get("limit", 5)

        is_valid, sanitized, error = self.validate_input({"query": query})
        if not is_valid:
            return f"Error: Invalid input - {error}"

        try:
            results = self.civic.what_happened_full_context(query, top_k=limit)

            result_parts = [f"# Decisions with Context: {query}", ""]

            if not results:
                return "No decisions found matching this query."

            for r in results:
                d = r.decision
                result_parts.append(f"## {d.title}")
                result_parts.append(f"- **Date:** {d.date}")
                result_parts.append(f"- **Outcome:** {d.outcome or 'N/A'}")
                result_parts.append("")

                if r.transcript_links:
                    public_comments = [l for l in r.transcript_links if l.is_public_comment]
                    if public_comments:
                        result_parts.append("### Public Testimony")
                        for link in public_comments[:3]:
                            speaker = link.speaker_name or "Resident"
                            result_parts.append(f"**{speaker}:** {link.text[:200]}...")
                            result_parts.append("")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error getting decision context: {str(e)}"

    # ─────────── Financial Handlers ───────────

    def _get_funding_flow(self, args: dict) -> str:
        """Trace intergovernmental funding flow."""
        program = args.get("program")
        cfda_number = args.get("cfda_number")

        try:
            flows = self.civic.funding_flow(program=program, cfda_number=cfda_number)

            result_parts = [
                "# Intergovernmental Funding Flow",
                f"**Program:** {program or 'All'}" if program else "",
                "",
            ]

            if not flows:
                result_parts.append("No funding flows found matching criteria.")
                result_parts.append("Use search_budget() for budget data.")
                return "\n".join(result_parts)

            total = sum(f.budget_dollars for f in flows)
            result_parts.append(f"**Total Linked Budget:** ${total:,.0f}")
            result_parts.append("")

            for flow in flows[:10]:
                result_parts.append(f"## {flow.budget_description}")
                result_parts.append(f"- **Department:** {flow.department or 'N/A'}")
                result_parts.append(f"- **Budget:** ${flow.budget_dollars:,.0f}")
                if flow.federal_program_name:
                    result_parts.append(f"- **Federal Source:** {flow.federal_program_name}")
                result_parts.append("")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error getting funding flow: {str(e)}"

    def _get_federal_expenditures(self, args: dict) -> str:
        """Get audited federal expenditures from Single Audit."""
        audit_year = args.get("audit_year")

        try:
            summary = self.civic.federal_expenditures_summary(audit_year=audit_year)

            result_parts = [
                "# Federal Expenditures (Single Audit)",
                f"**Audit Year:** {summary.get('audit_year', 'N/A')}",
                f"**Total Federal Spending:** ${summary.get('total_dollars', 0):,.0f}",
                "",
            ]

            programs = summary.get('programs', [])
            if programs:
                result_parts.append("## By Program")
                for p in programs[:15]:
                    result_parts.append(f"- **{p.get('cfda', 'N/A')}:** ${p.get('dollars', 0):,.0f}")
                    if p.get('program_name'):
                        result_parts.append(f"  *{p.get('program_name')}*")
            else:
                result_parts.append("No federal expenditure data found.")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error getting federal expenditures: {str(e)}"

    def _get_intergovernmental_revenue(self, args: dict) -> str:
        """Get intergovernmental revenue from CA State Controller."""
        fiscal_year = args.get("fiscal_year")
        source = args.get("source")

        try:
            revenue = self.civic.intergovernmental_revenue(fiscal_year=fiscal_year, source=source)

            result_parts = [
                "# Intergovernmental Revenue",
                f"**Fiscal Year:** {revenue.get('fiscal_year', 'N/A')}",
                f"**Total Revenue:** ${revenue.get('total', 0):,.0f}",
                "",
            ]

            by_source = revenue.get('by_source', {})
            if by_source:
                result_parts.append("## By Source")
                for src, amount in by_source.items():
                    result_parts.append(f"- **{src}:** ${amount:,.0f}")

            return "\n".join(result_parts)

        except Exception as e:
            return f"Error getting intergovernmental revenue: {str(e)}"

    # ─────────── Action Handlers ───────────

    def _get_comment_template(self, args: dict) -> str:
        """Get a fill-in-the-blank public comment template."""
        item_title = args.get("item_title", "")
        stance = args.get("stance")
        key_points = args.get("key_points")

        parts = [
            f"Re: {item_title}",
            "",
            "Dear Mayor and Council Members,",
            "",
        ]

        if stance:
            stance_text = {
                "support": "I am writing to express my support for this agenda item.",
                "oppose": "I am writing to express my concerns about this agenda item.",
                "question": "I am writing to request clarification about this agenda item.",
                "neutral": "I am writing to provide input on this agenda item."
            }
            parts.append(stance_text.get(stance.lower(), "I am writing to provide input on this agenda item."))
        else:
            parts.append("I am writing to provide input on this agenda item.")

        parts.append("")

        if key_points:
            parts.append("Key points:")
            for point in key_points.split("\n"):
                if point.strip():
                    parts.append(f"- {point.strip()}")
        else:
            parts.append("Please consider the following:")
            parts.append("- [Your specific concerns or suggestions here]")
            parts.append("- [Impact on residents/community]")
            parts.append("- [Alternatives or modifications to consider]")

        parts.extend([
            "",
            "Thank you for your consideration and service to our community.",
            "",
            "Sincerely,",
            "[Your Name]",
            "[Your Address in San Rafael]",
        ])

        return "\n".join(parts)

    def _prepare_for_meeting(self, args: dict) -> str:
        """Get preparation materials for a city council meeting."""
        agenda_item_id = args.get("agenda_item_id", "")

        is_valid, sanitized, error = self.validate_input({"agenda_item_id": agenda_item_id})
        if not is_valid:
            return f"Error: Invalid input - {error}"

        try:
            prep = self.civic.prepare(agenda_item_id)

            result_parts = [
                f"# Meeting Preparation",
                f"**Agenda Item:** {prep.agenda_item_id}",
                "",
                "## Logistics",
            ]

            if prep.logistics:
                if prep.logistics.get('meeting_title'):
                    result_parts.append(f"- **Meeting:** {prep.logistics['meeting_title']}")
                if prep.logistics.get('meeting_datetime'):
                    result_parts.append(f"- **When:** {prep.logistics['meeting_datetime']}")
                if prep.logistics.get('location'):
                    result_parts.append(f"- **Where:** {prep.logistics['location']}")
            result_parts.append("")

            result_parts.append("## Talking Points")
            if prep.talking_points:
                for point in prep.talking_points:
                    result_parts.append(f"- {point}")
            else:
                result_parts.append("- Introduce yourself and state your position")
                result_parts.append("- Explain why this matters to you")
                result_parts.append("- Request a specific action from the council")

            return "\n".join(result_parts)

        except ValueError:
            return f"Agenda item not found: {agenda_item_id}. Use get_upcoming_meetings() to find valid agenda item IDs."
        except Exception as e:
            return f"Error preparing for meeting: {str(e)}"

    # ─────────── MCP Protocol Handler ───────────

    @modal.fastapi_endpoint(method="POST", docs=True)
    def mcp_endpoint(self, request: dict) -> dict:
        """
        MCP JSON-RPC endpoint.

        Handles the MCP protocol requests from Claude.ai and ChatGPT.
        Supports: initialize, tools/list, tools/call
        """
        try:
            method = request.get("method", "")
            params = request.get("params", {})
            request_id = request.get("id", 1)

            self.logger.debug(f"MCP request: {method}")

            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {
                            "name": "CivicOS MCP Server",
                            "version": "1.0.0",
                        },
                        "capabilities": {
                            "tools": {"listChanged": False},
                            "resources": {"listChanged": False},
                        },
                    },
                    "id": request_id,
                }

            elif method == "tools/list":
                tool_list = [
                    {
                        "name": name,
                        "description": info["description"],
                        "inputSchema": info["inputSchema"],
                    }
                    for name, info in self.tools.items()
                ]
                return {
                    "jsonrpc": "2.0",
                    "result": {"tools": tool_list},
                    "id": request_id,
                }

            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})

                if tool_name not in self.tools:
                    return {
                        "jsonrpc": "2.0",
                        "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
                        "id": request_id,
                    }

                # Call the tool handler
                handler = self.tools[tool_name]["handler"]
                result = handler(tool_args)

                # Format result for MCP
                if isinstance(result, dict):
                    import json
                    result_text = json.dumps(result, indent=2, default=str)
                elif isinstance(result, list):
                    result_text = "\n\n".join(str(item) for item in result[:20])
                else:
                    result_text = str(result)

                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "content": [{"type": "text", "text": result_text}],
                        "isError": False,
                    },
                    "id": request_id,
                }

            elif method == "resources/list":
                # Resources for browsing
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "resources": [
                            {
                                "uri": f"civicos://{self.jurisdiction}/meetings",
                                "name": "Upcoming Meetings",
                                "description": "City council meetings and agendas",
                            },
                            {
                                "uri": f"civicos://{self.jurisdiction}/decisions",
                                "name": "Recent Decisions",
                                "description": "Recent council decisions and outcomes",
                            },
                        ]
                    },
                    "id": request_id,
                }

            elif method == "prompts/list":
                return {
                    "jsonrpc": "2.0",
                    "result": {
                        "prompts": [
                            {
                                "name": "research_topic",
                                "description": "Research a civic topic thoroughly",
                                "arguments": [
                                    {"name": "topic", "description": "The topic to research", "required": True}
                                ],
                            },
                            {
                                "name": "meeting_prep",
                                "description": "Prepare for an upcoming council meeting",
                                "arguments": [
                                    {"name": "meeting_description", "description": "Meeting or agenda item", "required": True}
                                ],
                            },
                        ]
                    },
                    "id": request_id,
                }

            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": request_id,
                }

        except Exception as e:
            import traceback
            self.logger.error(f"MCP endpoint error: {e}")
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": str(e),
                    "data": traceback.format_exc(),
                },
                "id": request.get("id", 1),
            }

    @modal.fastapi_endpoint(method="GET", docs=True)
    def health(self) -> dict:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "civicos-mcp",
            "jurisdiction": self.jurisdiction,
            "platform": "modal",
            "tools_count": len(self.tools),
            "tools": list(self.tools.keys()),
        }


# ─────────── LOCAL ENTRYPOINT ───────────

@app.local_entrypoint()
def main():
    """Local entrypoint for testing."""
    print("CivicOS MCP Server (Modal - Full Parity)")
    print()
    print("Deploy:")
    print("  modal deploy apps/civicos-mcp/modal_app.py")
    print()
    print("Test locally:")
    print("  modal serve apps/civicos-mcp/modal_app.py")
    print()
    print("After deployment, endpoints will be available at:")
    print("  MCP:    https://civicos--civicos-mcp-mcp-endpoint.modal.run")
    print("  Health: https://civicos--civicos-mcp-health.modal.run")
    print()
    print("Connect from Claude.ai/ChatGPT using the MCP endpoint URL.")
