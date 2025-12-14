# MCP Civic Engagement Server

Prototype Model Context Protocol (MCP) server for bi-directional civic engagement tools. Part of the civic engagement platform's evolution from "intelligent newsletter" to "comprehensive civic participation infrastructure."

## Overview

This MCP server provides AI-powered tools to transform newsletter readers into active civic participants by enabling one-click comment composition, submission assistance, and civic process guidance.

**Goal**: Test the hypothesis that bi-directional MCP tools can increase newsletter-to-action conversion from <1% to 5-10%.

## Quick Start

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the server
python civic_server.py

# Test tools (example)
# Tools will be accessible through MCP clients like Claude Desktop
```

## Architecture

### MCP Tools

#### `compose_public_comment(item_id, item_title, resident_stance?, key_points?)`
Generates draft public comments for civic agenda items.

**Parameters:**
- `item_id` (str): Unique identifier for the agenda item
- `item_title` (str): Title/description of the agenda item  
- `resident_stance` (str, optional): "support", "oppose", "neutral", or "question"
- `key_points` (str, optional): Specific points to include (newline-separated)

**Returns:** Draft public comment text ready for resident review and submission

**Example Usage:**
```python
draft = compose_public_comment(
    item_id="2024-09-02-5a",
    item_title="Affordable Housing Project - 1234 Main St",
    resident_stance="support",
    key_points="Need more affordable housing\nGood transit access\nPlease include family units"
)
```

#### `get_comment_guidelines(jurisdiction="san-rafael")`
Retrieves public comment submission guidelines and contact information.

**Parameters:**
- `jurisdiction` (str): City/jurisdiction identifier (default: "san-rafael")

**Returns:** Formatted guidelines including email addresses, deadlines, and procedures

### MCP Resources

#### `civic-opportunities://san-rafael/meetings`
Provides current civic engagement opportunities (planned integration with existing civic_digest.py system).

## Development Status

###  Completed
- MCP development environment setup (uv, Python 3.12.6, MCP SDK 1.13.1)
- Basic server architecture with proper logging and type hints
- Core tools: `compose_public_comment` and `get_comment_guidelines`
- San Rafael-specific comment guidelines template

### = In Progress  
- Research San Rafael's actual comment submission process
- Integration with existing civic_digest.py newsletter system

### =Ë Planned
- AI-powered comment generation (currently uses templates)
- Email submission automation via `submit_public_comment` tool
- Calendar integration for meeting reminders
- A/B testing framework for measuring conversion rates

## Integration with Civic Digest System

This MCP server is designed to enhance the existing production-ready newsletter system at `/Users/nicolaslounsbury/projects/civic/civic_digest.py`.

**Current Newsletter Flow:**
```
Meeting Scraping ’ AI Enhancement ’ Newsletter Generation ’ Email Delivery
```

**Enhanced MCP Flow:**
```
Meeting Scraping ’ AI Enhancement ’ Newsletter with Action Buttons ’ MCP Tools ’ Comment Submission
```

## Testing & Validation

The server includes built-in logging for tracking:
- Comment composition requests
- Generated draft lengths and characteristics  
- Jurisdiction-specific guideline requests
- Tool usage patterns

**Success Metrics:**
- Newsletter recipients who use MCP tools (target: 5-10%)
- Comments actually submitted to San Rafael officials
- Meeting attendance correlation with MCP tool usage

## Dependencies

See `pyproject.toml` for full dependency list. Key requirements:
- `mcp[cli]>=1.13.1` - Model Context Protocol framework
- `httpx` - Async HTTP client for API integration
- `python>=3.10` - Required for MCP SDK

## Development Guidelines

### Code Style
- Use async functions for all external API calls
- Include comprehensive docstrings with parameter descriptions
- Log to stderr only (stdout reserved for MCP protocol)
- Use type hints for all function parameters and returns

### MCP Best Practices
- Tools should be stateless and focused on single actions
- Resources should provide read-only data access
- Error handling should be graceful with informative messages
- All external API calls must be async with proper timeout handling

### Security Considerations
- Never log sensitive user data (email addresses, personal information)
- Validate all input parameters before processing
- Use domain allowlists for email submission endpoints
- Implement proper authentication for production deployment

## Contributing

This is a prototype for civic engagement infrastructure. Focus areas:

1. **Accuracy**: Ensure comment guidelines match actual municipal processes
2. **Usability**: Keep tools simple and accessible for busy residents
3. **Effectiveness**: Measure and optimize for actual civic participation increases
4. **Neutrality**: Maintain political neutrality while empowering authentic resident voices

## License

Part of the civic engagement platform serving democratic participation. See parent project for licensing details.

---

**Next Development Priorities:**
1. Research San Rafael's comment submission endpoints and requirements
2. Integrate with civic_digest.py for real meeting data
3. Implement AI-powered comment generation
4. Build A/B testing framework for measuring civic impact