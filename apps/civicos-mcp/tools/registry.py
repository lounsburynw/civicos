"""
Tool registry for CivicOS MCP server.

Provides tool definitions in a format usable by both FastMCP (decorators)
and Modal (dictionary registry).
"""

from typing import TypedDict, Callable, Any


class ToolDefinition(TypedDict, total=False):
    """MCP tool definition schema."""
    description: str
    inputSchema: dict
    handler: Callable[[dict], str]  # Optional - set at runtime
    requires_admin: bool  # If True, requires _admin_token arg


# ─────────── Tool Definitions ───────────
# These define the metadata for all 30+ tools.
# Handlers are bound at runtime by the server implementation.

TOOL_DEFINITIONS: dict[str, ToolDefinition] = {
    # ─────────── Core Civic Tools ───────────
    "search_meeting_history": {
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
    },
    "get_upcoming_meetings": {
        "description": "Get upcoming city council meetings and agenda items",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "default": 30, "description": "Days to look ahead"},
            },
        },
    },
    "find_similar_issues": {
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
    },
    "search_regulatory_stack": {
        "description": "Search relevant laws and regulations across local, state, and federal levels",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to search (e.g., 'accessory dwelling units')"},
                "jurisdiction": {"type": "string", "default": "san-rafael"},
            },
            "required": ["topic"],
        },
    },
    "compose_public_comment": {
        "description": "Get context for writing a public comment on a civic agenda item",
        "inputSchema": {
            "type": "object",
            "properties": {
                "item_title": {"type": "string", "description": "Title/description of the agenda item"},
                "topic": {"type": "string", "description": "Optional topic for finding related context"},
            },
            "required": ["item_title"],
        },
    },
    "city_pulse": {
        "description": "Get structured city activity data (meetings, decisions, community issues) as JSON. Returns raw data suitable for analysis or display. Use when you need specific counts, dates, or structured information about civic activity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days_ahead": {"type": "integer", "default": 7, "description": "Days to look ahead"},
                "days_back": {"type": "integer", "default": 30, "description": "Days to look back"},
                "parent_jurisdiction": {"type": "string", "description": "Return legislation pulse for a parent jurisdiction (e.g. state-california, country-united-states) using data from this city server"},
            },
        },
    },
    "get_issue_analytics": {
        "description": "Get aggregate statistics about 311/SeeClickFix issues",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date_range": {"type": "string", "description": "Filter: '2024', '2024-Q4', 'last_90_days', 'last_year'"},
            },
        },
    },
    "get_issue_trends": {
        "description": "Analyze trends in 311 issues over time",
        "inputSchema": {
            "type": "object",
            "properties": {
                "issue_type": {"type": "string", "description": "Filter by issue type"},
                "granularity": {"type": "string", "default": "month", "description": "Time grouping: week, month, quarter, year"},
            },
        },
    },
    "geo_search_issues": {
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
    },
    "search_budget": {
        "description": "Search city budget data by department or category",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Department or category to search"},
                "fiscal_year": {"type": "string", "description": "Filter by fiscal year (e.g., 'FY25-26')"},
            },
        },
    },
    "get_public_testimony": {
        "description": "Get public testimony excerpts on a topic from meeting transcripts",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to search"},
                "limit": {"type": "integer", "default": 5, "description": "Maximum excerpts to return"},
            },
            "required": ["topic"],
        },
    },
    "search_agenda_packets": {
        "description": "Search agenda packets and staff reports",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        },
    },
    "get_comment_guidelines": {
        "description": "Get public comment guidelines and submission information",
        "inputSchema": {
            "type": "object",
            "properties": {
                "jurisdiction": {"type": "string", "default": "san-rafael"},
            },
        },
    },
    "get_started": {
        "description": "Get a friendly welcome overview for new users. Returns formatted text with upcoming meetings, recent decisions, and suggestions for what to explore. Use when users first arrive or ask general questions like 'what can you help with?' or 'what's going on?'",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },

    # ─────────── 311 Analysis Tools ───────────
    "query_issue_data": {
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
    },
    "get_issue_resolution_stats": {
        "description": "Get resolution statistics for 311 issues (response time, rates)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "issue_type": {"type": "string", "description": "Filter by issue type"},
                "zip_code": {"type": "string", "description": "Filter by zip code"},
            },
        },
    },
    "detect_trends": {
        "description": "Detect significant trends in 311 issue patterns",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lookback_months": {"type": "integer", "default": 6, "description": "Compare last N months to previous N months"},
                "min_change_pct": {"type": "number", "default": 20.0, "description": "Minimum % change to report"},
                "zip_code": {"type": "string", "description": "Filter to specific zip code"},
            },
        },
    },
    "get_issue_sample": {
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
    },
    "find_issues_near_address": {
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
    },
    "find_repeat_issues": {
        "description": "Find locations with repeated issues of the same type",
        "inputSchema": {
            "type": "object",
            "properties": {
                "issue_type": {"type": "string", "description": "Filter by issue type"},
                "min_occurrences": {"type": "integer", "default": 3, "description": "Minimum repeats to flag"},
            },
        },
    },
    "get_seasonal_patterns": {
        "description": "Analyze seasonal patterns in 311 issues",
        "inputSchema": {
            "type": "object",
            "properties": {
                "issue_type": {"type": "string", "description": "Filter by issue type"},
            },
        },
    },
    "compare_zip_codes": {
        "description": "Compare 311 issue patterns between zip codes",
        "inputSchema": {
            "type": "object",
            "properties": {
                "zip_codes": {"type": "array", "items": {"type": "string"}, "description": "Zip codes to compare"},
            },
            "required": ["zip_codes"],
        },
    },
    "neighborhood_report": {
        "description": "Generate a comprehensive report for a neighborhood",
        "inputSchema": {
            "type": "object",
            "properties": {
                "neighborhood": {"type": "string", "description": "Neighborhood name or area"},
            },
            "required": ["neighborhood"],
        },
    },

    # ─────────── Council/Voting Tools ───────────
    "get_voting_record": {
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
    },
    "get_decision_context": {
        "description": "Get decisions with linked transcript excerpts showing what was discussed",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
    "decision_detail": {
        "description": "Get structured detail for a specific decision including testimony excerpts and related decisions. Returns JSON for dashboard expansion.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Decision title to look up"},
            },
            "required": ["title"],
        },
    },

    # ─────────── Legislation & Executive Order Tools ───────────
    "search_legislation": {
        "description": "Search state or federal legislation by topic, keyword, or status. Returns bills with sponsor info, status, and citizen leverage points where available.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search topic or keyword (e.g., 'housing', 'climate', 'transportation')"},
                "state": {"type": "string", "description": "State code: 'CA' for California, 'US' for federal. Defaults to both."},
                "status": {"type": "string", "description": "Filter by bill status (e.g., 'Enrolled', 'Engrossed', 'Introduced')"},
                "limit": {"type": "integer", "default": 10, "description": "Maximum results (default 10, max 50)"},
            },
            "required": ["query"],
        },
    },
    "get_bill_detail": {
        "description": "Get full detail for a specific bill including text, sponsors, status, and citizen leverage point (what you can do about it).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "bill_id": {"type": "string", "description": "Bill identifier (e.g., 'ca-sb9', 'us-hr1234')"},
                "state": {"type": "string", "description": "State code: 'CA' or 'US'. Will be inferred from bill_id prefix if omitted."},
            },
            "required": ["bill_id"],
        },
    },
    "get_leverage_points": {
        "description": "Find legislation with citizen action opportunities (leverage points). These are bills where residents can take specific action — testify at committee hearings, submit public comments, or advocate at local hearings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Filter by topic (e.g., 'housing', 'transportation')"},
                "state": {"type": "string", "description": "State code: 'CA' for California, 'US' for federal. Defaults to both."},
                "limit": {"type": "integer", "default": 10, "description": "Maximum results"},
            },
        },
    },
    "search_executive_orders": {
        "description": "Search active Executive Orders by topic or keyword. Uses full-text search across titles, abstracts, and text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search topic or keyword (e.g., 'immigration', 'trade', 'environment')"},
                "president": {"type": "string", "description": "Filter by president name"},
                "limit": {"type": "integer", "default": 10, "description": "Maximum results"},
            },
            "required": ["query"],
        },
    },
    "get_recent_executive_orders": {
        "description": "Get recently signed Executive Orders. Useful for tracking new federal policy actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "president": {"type": "string", "description": "Filter by president name"},
                "limit": {"type": "integer", "default": 10, "description": "Maximum results (default 10, max 50)"},
            },
        },
    },

    # ─────────── Participation Window Tools ───────────
    "get_open_comment_periods": {
        "description": "Get federal rules with open public comment periods, sorted by deadline. These are proposed rules (NPRMs) where citizens can submit feedback before the deadline. The most impactful federal participation mechanism.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10, "description": "Maximum results"},
            },
        },
    },
    "search_federal_rules": {
        "description": "Search federal rulemaking documents (proposed rules, final rules, notices) by topic. Includes comment period deadlines and links.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search topic or keyword (e.g., 'housing', 'environment', 'healthcare')"},
                "document_type": {"type": "string", "description": "Filter: 'proposed_rule', 'final_rule', or 'notice'"},
                "limit": {"type": "integer", "default": 10, "description": "Maximum results"},
            },
            "required": ["query"],
        },
    },
    "get_upcoming_hearings": {
        "description": "Get upcoming state legislative committee hearings. Shows bills with scheduled hearing dates where public testimony is possible.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "default": "CA", "description": "State code (default: CA)"},
                "topic": {"type": "string", "description": "Filter by topic keyword"},
                "days_ahead": {"type": "integer", "default": 30, "description": "Days to look ahead"},
                "limit": {"type": "integer", "default": 20, "description": "Maximum results"},
            },
        },
    },
    "get_governors_desk": {
        "description": "Get bills awaiting governor's signature (Enrolled status). These represent a 12-day action window where constituent calls to the governor's office can influence whether a bill is signed or vetoed.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "default": "CA", "description": "State code (default: CA)"},
                "topic": {"type": "string", "description": "Filter by topic keyword"},
                "limit": {"type": "integer", "default": 20, "description": "Maximum results"},
            },
        },
    },

    # ─────────── Financial Tools ───────────
    "get_funding_flow": {
        "description": "Trace intergovernmental funding from federal to state to city budget",
        "inputSchema": {
            "type": "object",
            "properties": {
                "program": {"type": "string", "description": "Program name (e.g., CDBG, HOME)"},
                "cfda_number": {"type": "string", "description": "Federal CFDA number"},
            },
        },
    },
    "get_federal_expenditures": {
        "description": "Get audited federal expenditures from Single Audit (FAC) data",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cfda_number": {"type": "string", "description": "Filter by CFDA/ALN number"},
                "audit_year": {"type": "integer", "description": "Audit fiscal year"},
            },
        },
    },
    "get_intergovernmental_revenue": {
        "description": "Get intergovernmental revenue from CA State Controller data",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fiscal_year": {"type": "integer", "description": "Fiscal year"},
                "source": {"type": "string", "description": "Filter by source (federal, state, county)"},
            },
        },
    },

    # ─────────── Action Tools ───────────
    "draft_federal_comment": {
        "description": "Draft a public comment for a federal rulemaking. Returns structured guidance, rule context, and submission instructions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_number": {"type": "string", "description": "Federal Register document number (e.g., '2026-03077')"},
                "stance": {"type": "string", "enum": ["support", "oppose", "concern", "question"], "description": "Your stance on the proposed rule"},
                "key_points": {"type": "string", "description": "Newline-separated key points to address in the comment"},
            },
            "required": ["document_number"],
        },
    },
    "prepare_federal_comment": {
        "description": "Get submission context for a federal comment: rule details, deadline, submission URL, and instructions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_number": {"type": "string", "description": "Federal Register document number (e.g., '2026-03077')"},
            },
            "required": ["document_number"],
        },
    },
    "get_comment_template": {
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
    },
    "prepare_for_meeting": {
        "description": "Get preparation materials for participating in a city council meeting",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agenda_item_id": {"type": "string", "description": "ID of the agenda item to prepare for"},
            },
            "required": ["agenda_item_id"],
        },
    },

    # ─────────── Context Assembly Tool ───────────
    "get_item_context": {
        "description": "Get comprehensive context for a civic item (agenda item, decision, issue, legislation, meeting, or initiative). Returns a structured bundle with history, regulatory, community, financial, testimony, and participation context. Pass the result to an LLM as conversation context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "item_type": {
                    "type": "string",
                    "enum": ["agenda_item", "decision", "issue", "legislation", "meeting", "initiative"],
                    "description": "Type of civic item",
                },
                "item_id": {"type": "string", "description": "Item ID (UUID or bill number)"},
                "depth": {
                    "type": "string",
                    "enum": ["minimal", "standard", "deep"],
                    "default": "standard",
                    "description": "Context depth: minimal (item only), standard (all sections), deep (extra cross-references)",
                },
                "sections": {
                    "type": "string",
                    "description": "Comma-separated sections to include (omit for all). Valid: history, regulatory, community, financial, testimony, participation",
                },
            },
            "required": ["item_type", "item_id"],
        },
    },

    # ─────────── Coordination Tools ───────────
    # These tools implement a permissionless coordination protocol.
    # Users can specify their own relay, or use the default CivicOS relay.
    # Voices are cryptographically signed - the signature is the authority, not the relay.
    "get_voice_counts": {
        "description": "Get community voice counts (support/oppose/watching) for a civic entity. Queries a relay node.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Entity identifier (e.g., 'decision:city-san-rafael:2026-01-15:item-5a')",
                },
                "relay_url": {
                    "type": "string",
                    "description": "Relay node URL to query. Defaults to CivicOS relay if not specified.",
                },
            },
            "required": ["entity"],
        },
    },
    "subscribe_to_topic": {
        "description": "Subscribe to notifications about civic topics via a relay node. You choose which relay to trust with your subscription.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of topics to subscribe to (e.g., ['housing', 'traffic'])",
                },
                "email": {
                    "type": "string",
                    "description": "Email address for notifications",
                },
                "relay_url": {
                    "type": "string",
                    "description": "Relay node URL to register subscription. Defaults to CivicOS relay if not specified.",
                },
            },
            "required": ["topics", "email"],
        },
    },
    "prepare_voice": {
        "description": "Prepare a voice payload for signing. Returns the exact message you need to sign with your private key. This is step 1 of casting a voice - you sign the payload locally, then use broadcast_voice to submit it.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Entity identifier (e.g., 'decision:city-san-rafael:2026-01-15:item-5a')",
                },
                "stance": {
                    "type": "string",
                    "enum": ["support", "oppose", "watching"],
                    "description": "Your position: support, oppose, or watching",
                },
            },
            "required": ["entity", "stance"],
        },
    },
    "broadcast_voice": {
        "description": "Broadcast a signed voice to relay node(s). This is step 2 of casting a voice - after signing the Nostr event with your private key via the Personal MCP, submit the signed event fields here.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "Entity identifier (from the signed Nostr event d-tag)",
                },
                "stance": {
                    "type": "string",
                    "enum": ["support", "oppose", "watching"],
                    "description": "Your position (from the signed Nostr event stance tag)",
                },
                "public_key": {
                    "type": "string",
                    "description": "Your public key (hex-encoded, 32-byte x-only secp256k1)",
                },
                "signature": {
                    "type": "string",
                    "description": "BIP-340 Schnorr signature (hex-encoded, 64 bytes)",
                },
                "created_at": {
                    "type": "integer",
                    "description": "Unix timestamp from the signed Nostr event",
                },
                "jurisdiction": {
                    "type": "string",
                    "description": "Jurisdiction code (e.g., 'city-san-rafael') from the signed event j-tag",
                },
                "relay_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Relay node URLs to broadcast to. Defaults to CivicOS relay if not specified.",
                },
            },
            "required": ["entity", "stance", "public_key", "signature", "created_at"],
        },
    },
    "list_relays": {
        "description": "List known relay nodes in the CivicOS network. You can use any of these relays, or run your own.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    # === Initiative Tools ===
    "prepare_initiative": {
        "description": "Prepare an initiative (focal point for coordination) for signing. Returns the exact message to sign with your secp256k1 Schnorr (BIP-340) private key. This is step 1 of creating an initiative.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic area (e.g., 'traffic safety', 'housing', 'parks')",
                },
                "title": {
                    "type": "string",
                    "description": "Short title for the initiative (e.g., 'Protected bike lane on 4th St')",
                },
                "description": {
                    "type": "string",
                    "description": "Full description of what you're trying to accomplish",
                },
                "location": {
                    "type": "string",
                    "description": "Optional physical location (e.g., '4th Street between A and B')",
                },
            },
            "required": ["topic", "title", "description"],
        },
    },
    "broadcast_initiative": {
        "description": "Broadcast a signed initiative to relay node(s). This is step 2 of creating an initiative - after signing the payload from prepare_initiative with your private key, submit the signature here.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic area (must match what you signed)",
                },
                "title": {
                    "type": "string",
                    "description": "Initiative title (must match what you signed)",
                },
                "description": {
                    "type": "string",
                    "description": "Full description (must match what you signed)",
                },
                "location": {
                    "type": "string",
                    "description": "Optional location (must match what you signed)",
                },
                "public_key": {
                    "type": "string",
                    "description": "Your public key (hex-encoded, 32-byte x-only secp256k1 Schnorr BIP-340)",
                },
                "signature": {
                    "type": "string",
                    "description": "Signature of the initiative payload (hex-encoded)",
                },
                "relay_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Relay node URLs to broadcast to. Defaults to CivicOS relay if not specified.",
                },
            },
            "required": ["topic", "title", "description", "public_key", "signature"],
        },
    },
    "list_initiatives": {
        "description": "List community-created initiatives from a relay node. Initiatives are focal points where people can coordinate around shared goals.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Filter by topic (e.g., 'traffic safety')",
                },
                "status": {
                    "type": "string",
                    "enum": ["active", "completed", "failed"],
                    "description": "Filter by status. Active initiatives are open for voices.",
                },
                "relay_url": {
                    "type": "string",
                    "description": "Relay node URL to query. Defaults to CivicOS relay if not specified.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of initiatives to return (default 20, max 100)",
                },
            },
        },
    },

    # ─────────── Admin Tools ───────────
    "admin_data_status": {
        "description": "Get corpus counts, vector coverage, and indexing gaps for a jurisdiction. Returns summary and gap analysis.",
        "requires_admin": True,
        "inputSchema": {
            "type": "object",
            "properties": {
                "_admin_token": {"type": "string", "description": "Admin authentication token"},
                "jurisdiction": {"type": "string", "description": "Override jurisdiction (defaults to server jurisdiction)"},
            },
            "required": ["_admin_token"],
        },
    },
    "admin_vector_coverage": {
        "description": "Get vector embedding coverage by corpus type. Shows indexed vs total counts per corpus.",
        "requires_admin": True,
        "inputSchema": {
            "type": "object",
            "properties": {
                "_admin_token": {"type": "string", "description": "Admin authentication token"},
                "corpus_type": {"type": "string", "description": "Filter to specific corpus type (e.g., 'transcripts', 'decisions')"},
            },
            "required": ["_admin_token"],
        },
    },
    "admin_system_health": {
        "description": "Check backend connectivity (storage, vectors). Returns component status.",
        "requires_admin": True,
        "inputSchema": {
            "type": "object",
            "properties": {
                "_admin_token": {"type": "string", "description": "Admin authentication token"},
            },
            "required": ["_admin_token"],
        },
    },
    "admin_cost_dashboard": {
        "description": "Get operating costs by service and time period. Shows LLM and compute costs.",
        "requires_admin": True,
        "inputSchema": {
            "type": "object",
            "properties": {
                "_admin_token": {"type": "string", "description": "Admin authentication token"},
                "period": {"type": "string", "default": "month", "description": "Time period: day, week, month"},
                "service": {"type": "string", "description": "Filter by service name"},
                "jurisdiction": {"type": "string", "description": "Filter by jurisdiction"},
            },
            "required": ["_admin_token"],
        },
    },
    "manage_api_keys": {
        "description": "Create, list, or revoke API keys. Actions: create (requires name, email), list, revoke (requires key_id).",
        "requires_admin": True,
        "inputSchema": {
            "type": "object",
            "properties": {
                "_admin_token": {"type": "string", "description": "Admin authentication token"},
                "action": {"type": "string", "enum": ["create", "list", "revoke"], "description": "Action to perform"},
                "name": {"type": "string", "description": "Key name (for create)"},
                "email": {"type": "string", "description": "Contact email (for create)"},
                "tier": {"type": "string", "default": "free", "description": "Key tier (for create)"},
                "jurisdictions": {"type": "array", "items": {"type": "string"}, "description": "Allowed jurisdictions (for create)"},
                "key_id": {"type": "string", "description": "Key ID (for revoke)"},
            },
            "required": ["_admin_token", "action"],
        },
    },
    "query_feedback": {
        "description": "Query user feedback submissions. Returns recent feedback items with counts by type.",
        "requires_admin": True,
        "inputSchema": {
            "type": "object",
            "properties": {
                "_admin_token": {"type": "string", "description": "Admin authentication token"},
                "jurisdiction": {"type": "string", "description": "Jurisdiction ID (e.g., 'city-san-rafael')"},
                "feedback_type": {"type": "string", "enum": ["bug", "feature", "general"], "description": "Filter by feedback type"},
                "limit": {"type": "integer", "default": 20, "description": "Max items to return"},
            },
            "required": ["_admin_token", "jurisdiction"],
        },
    },
}


class ToolRegistry:
    """
    Registry of MCP tools with their definitions and handlers.

    Used by both FastMCP (civicos_server.py) and Modal (modal_app.py)
    to maintain a single source of truth for tool metadata.
    """

    def __init__(self):
        self.tools: dict[str, ToolDefinition] = {}
        for name, definition in TOOL_DEFINITIONS.items():
            self.tools[name] = definition.copy()

    def bind_handler(self, name: str, handler: Callable[[dict], str]) -> None:
        """Bind a handler function to a tool."""
        if name not in self.tools:
            raise ValueError(f"Unknown tool: {name}")
        self.tools[name]["handler"] = handler

    def bind_handlers(self, handlers: dict[str, Callable[[dict], str]]) -> None:
        """Bind multiple handlers at once."""
        for name, handler in handlers.items():
            self.bind_handler(name, handler)

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get a tool definition by name."""
        return self.tools.get(name)

    def list_tools(self) -> list[dict]:
        """Get tool list in MCP format (for tools/list response).

        Only returns tools that have handlers bound.
        """
        return [
            {
                "name": name,
                "description": info["description"],
                "inputSchema": info["inputSchema"],
            }
            for name, info in self.tools.items()
            if "handler" in info  # Only include tools with bound handlers
        ]

    def call_tool(self, name: str, args: dict) -> str:
        """Call a tool by name with the given arguments."""
        tool = self.tools.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")
        handler = tool.get("handler")
        if not handler:
            raise ValueError(f"No handler bound for tool: {name}")
        return handler(args)

    def __len__(self) -> int:
        """Return count of tools with handlers bound."""
        return sum(1 for info in self.tools.values() if "handler" in info)

    def __iter__(self):
        return iter(self.tools.items())


def get_all_tools() -> dict[str, ToolDefinition]:
    """Get a copy of all tool definitions (without handlers)."""
    return {name: def_.copy() for name, def_ in TOOL_DEFINITIONS.items()}
