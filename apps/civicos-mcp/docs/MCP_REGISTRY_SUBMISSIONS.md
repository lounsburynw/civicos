# MCP Registry Submissions

This document tracks CivicOS MCP server submissions to various MCP directories.

## Server Information

- **Name**: CivicOS San Rafael
- **MCP Endpoint**: https://san-rafael.civicosproject.org/mcp
- **Health Check**: https://san-rafael.civicosproject.org/health
- **GitHub**: https://github.com/civicosproject/civicos
- **Documentation**: https://civicosproject.org/docs/mcp

## Submission Status

| Directory | Status | Date | Notes |
|-----------|--------|------|-------|
| MCP.so | Pending | - | Submit via GitHub issue |
| MCPServers.org | Pending | - | Submit via web form |
| Official MCP Registry | Pending | - | Requires namespace verification |

## 1. MCP.so Submission

**Where**: https://github.com/chatmcp/mcp-directory/issues/1

**Submission Text**:
```
CivicOS MCP Server - Access San Rafael city council meetings, decisions, budget data, and 311 issues

Features:
- Search past council meetings and decisions
- Get upcoming meetings and agendas
- Find 311/SeeClickFix issues by topic or location
- Search city budget and expenditures
- Get public testimony with video timestamps
- Prepare public comments with context
- Search laws across local/state/federal levels

GitHub: https://github.com/civicosproject/civicos
MCP Endpoint: https://san-rafael.civicosproject.org/mcp
Documentation: https://civicosproject.org/docs/mcp
```

## 2. MCPServers.org Submission

**Where**: https://mcpservers.org/submit

**Form Fields**:
- **Name**: CivicOS San Rafael
- **Description**: Access San Rafael city council meetings, decisions, budget data, and 311 issues. Research civic topics, prepare public comments, and track what your local government is doing.
- **GitHub URL**: https://github.com/civicosproject/civicos
- **Category**: Government / Civic
- **Tags**: civic, government, local-government, city-council, meetings, public-comment, budget, california

## 3. Official MCP Registry

**Where**: https://registry.modelcontextprotocol.io

**Requirements**:
1. Namespace verification (need to prove ownership of civicosproject.org)
2. Domain verification via DNS TXT record or HTTP challenge
3. Use mcp-publisher CLI tool

**Namespace**: `org.civicosproject/san-rafael`

**Steps**:
```bash
# 1. Clone the registry repo and build publisher
git clone https://github.com/modelcontextprotocol/registry
cd registry
make publisher

# 2. Verify domain ownership (DNS method)
# Add TXT record: _mcp-verify.civicosproject.org -> <verification-code>

# 3. Publish
./bin/mcp-publisher publish --namespace org.civicosproject --name san-rafael
```

## Server Metadata

See `apps/civicos-mcp/server.json` for the complete server metadata in JSON format.

## Notes

- The MCP server is deployed on Modal with Cloudflare proxy
- Production URL uses custom domain: san-rafael.civicosproject.org
- Server supports Claude Desktop, Claude.ai, and ChatGPT
- 30+ tools covering meetings, decisions, budget, issues, legislation
