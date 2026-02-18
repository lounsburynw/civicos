import { getServers, getServerById } from "./registry";
import { getHealthData } from "./health";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function handleServers(): Promise<Response> {
  const servers = getServers();
  return jsonResponse({
    version: "1.0.0",
    updated: new Date().toISOString(),
    total_servers: servers.length,
    servers: servers.map((s) => ({
      jurisdiction_id: s.id,
      level: s.level,
      display_name: s.display_name,
      mcp_endpoint: s.mcp_endpoint,
      health_endpoint: s.health_endpoint,
      relay_endpoint: s.relay_endpoint,
      relay_ws_endpoint: s.relay_ws_endpoint,
      parent_jurisdictions: s.parent_jurisdictions,
    })),
  });
}

export async function handleServerById(id: string): Promise<Response> {
  const server = getServerById(id);
  if (!server) {
    return jsonResponse({ error: `Server '${id}' not found` }, 404);
  }
  return jsonResponse({
    jurisdiction_id: server.id,
    level: server.level,
    display_name: server.display_name,
    mcp_endpoint: server.mcp_endpoint,
    health_endpoint: server.health_endpoint,
    relay_endpoint: server.relay_endpoint,
    relay_ws_endpoint: server.relay_ws_endpoint,
    parent_jurisdictions: server.parent_jurisdictions,
  });
}

export async function handleHealth(): Promise<Response> {
  const servers = getServers();
  const healthMap = await getHealthData();

  let healthy = 0;
  let unhealthy = 0;
  let unknown = 0;
  let totalTools = 0;

  for (const server of servers) {
    const h = healthMap[server.id];
    if (!h || h.status === "unknown") {
      unknown++;
    } else if (h.status === "healthy") {
      healthy++;
      totalTools += h.tools_count ?? 0;
    } else {
      unhealthy++;
    }
  }

  return jsonResponse({
    updated: new Date().toISOString(),
    total_servers: servers.length,
    healthy,
    unhealthy,
    unknown,
    total_tools: totalTools,
    servers: healthMap,
  });
}
