import { getServers } from "./registry";
import { getHealthData, type HealthMap, type ServerHealth } from "./health";

const LEVEL_COLORS: Record<string, string> = {
  federal: "#58a6ff",
  state: "#d29922",
  county: "#a371f7",
  city: "#3fb950",
};

function levelBadge(level: string): string {
  const color = LEVEL_COLORS[level] ?? "#8b949e";
  return `<span style="display:inline-block;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:500;background:${color}20;color:${color};border:1px solid ${color}40">${level}</span>`;
}

function statusBadge(health: ServerHealth | undefined): string {
  if (!health || health.status === "unknown") {
    return `<span style="color:#8b949e">&#9679; unknown</span>`;
  }
  if (health.status === "healthy") {
    return `<span style="color:#3fb950">&#9679; healthy</span>`;
  }
  return `<span style="color:#f85149">&#9679; unhealthy</span>`;
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export async function renderLandingPage(): Promise<Response> {
  const servers = getServers();
  let healthMap: HealthMap = {};
  try {
    healthMap = await getHealthData();
  } catch {
    // Render page without health data
  }

  let healthyCount = 0;
  let totalTools = 0;
  for (const s of servers) {
    const h = healthMap[s.id];
    if (h?.status === "healthy") {
      healthyCount++;
      totalTools += h.tools_count ?? 0;
    }
  }

  const serverRows = servers
    .map((s) => {
      const h = healthMap[s.id];
      const latency = h?.response_time_ms != null ? `${h.response_time_ms}ms` : "&mdash;";
      const tools = h?.tools_count != null ? String(h.tools_count) : "&mdash;";
      return `
      <tr>
        <td>${levelBadge(s.level)}</td>
        <td><strong>${escapeHtml(s.display_name)}</strong><br><code style="font-size:12px;color:#8b949e">${escapeHtml(s.id)}</code></td>
        <td><a href="${escapeHtml(s.mcp_endpoint)}" style="color:#58a6ff">${escapeHtml(s.domain)}/mcp</a></td>
        <td>${statusBadge(h)}</td>
        <td style="text-align:center">${tools}</td>
        <td style="text-align:right;color:#8b949e">${latency}</td>
      </tr>`;
    })
    .join("\n");

  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CivicOS MCP Registry</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #0d1117;
      color: #e6edf3;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      line-height: 1.6;
    }
    .container { max-width: 960px; margin: 0 auto; padding: 48px 24px; }
    h1 { font-size: 28px; font-weight: 600; margin-bottom: 8px; }
    .subtitle { color: #8b949e; margin-bottom: 32px; }
    .stats {
      display: flex; gap: 24px; margin-bottom: 32px; flex-wrap: wrap;
    }
    .stat {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 16px 24px;
      min-width: 140px;
    }
    .stat-value { font-size: 24px; font-weight: 600; }
    .stat-label { font-size: 13px; color: #8b949e; }
    table {
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 40px;
    }
    th {
      text-align: left;
      padding: 10px 12px;
      border-bottom: 1px solid #30363d;
      color: #8b949e;
      font-size: 13px;
      font-weight: 500;
    }
    td {
      padding: 12px;
      border-bottom: 1px solid #21262d;
      vertical-align: middle;
    }
    tr:hover { background: #161b22; }
    code {
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    }
    a { text-decoration: none; }
    a:hover { text-decoration: underline; }
    .api-section { margin-top: 48px; }
    .api-section h2 { font-size: 20px; margin-bottom: 16px; }
    .endpoint {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 12px;
    }
    .endpoint code {
      color: #58a6ff; font-size: 14px;
    }
    .endpoint p {
      color: #8b949e; font-size: 13px; margin-top: 4px;
    }
    .footer {
      margin-top: 48px;
      padding-top: 24px;
      border-top: 1px solid #21262d;
      color: #484f58;
      font-size: 13px;
    }
    .footer a { color: #58a6ff; }
  </style>
</head>
<body>
  <div class="container">
    <h1>CivicOS MCP Registry</h1>
    <p class="subtitle">Discover CivicOS Model Context Protocol servers for civic data access</p>

    <div class="stats">
      <div class="stat">
        <div class="stat-value">${servers.length}</div>
        <div class="stat-label">Servers</div>
      </div>
      <div class="stat">
        <div class="stat-value" style="color:#3fb950">${healthyCount}</div>
        <div class="stat-label">Healthy</div>
      </div>
      <div class="stat">
        <div class="stat-value">${totalTools}</div>
        <div class="stat-label">Total Tools</div>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Level</th>
          <th>Jurisdiction</th>
          <th>MCP Endpoint</th>
          <th>Status</th>
          <th style="text-align:center">Tools</th>
          <th style="text-align:right">Latency</th>
        </tr>
      </thead>
      <tbody>
        ${serverRows}
      </tbody>
    </table>

    <div class="api-section">
      <h2>API</h2>
      <div class="endpoint">
        <code>GET /api/v1/servers</code>
        <p>List all registered MCP servers</p>
      </div>
      <div class="endpoint">
        <code>GET /api/v1/servers/:id</code>
        <p>Get details for a specific server by jurisdiction ID</p>
      </div>
      <div class="endpoint">
        <code>GET /api/v1/health</code>
        <p>Aggregated health status with per-server breakdown</p>
      </div>
    </div>

    <div class="footer">
      <a href="https://civicosproject.org">CivicOS Project</a> &middot;
      <a href="https://github.com/civicosproject/civicos">GitHub</a> &middot;
      Powered by Cloudflare Workers
    </div>
  </div>
</body>
</html>`;

  return new Response(html, {
    headers: { "Content-Type": "text/html;charset=UTF-8" },
  });
}
