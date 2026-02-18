import registryData from "../../../config/registry.json";

export interface ServerInfo {
  id: string;
  level: string;
  display_name: string;
  domain: string;
  mcp_endpoint: string;
  health_endpoint: string;
  /** Modal origin for health checks (bypasses Cloudflare same-zone loopback) */
  origin_health_endpoint: string;
  /** Parent jurisdiction IDs (e.g., city -> state -> federal) */
  parent_jurisdictions: string[];
  /** Relay HTTP endpoint for coordination (voices, subscriptions, actions) */
  relay_endpoint: string;
  /** Relay WebSocket endpoint for real-time updates */
  relay_ws_endpoint: string;
}

const LEVEL_ORDER: Record<string, number> = {
  federal: 0,
  state: 1,
  county: 2,
  city: 3,
  district: 4,
  neighborhood: 5,
};

function inferLevel(jurisdictionId: string): string {
  if (jurisdictionId.startsWith("country-")) return "federal";
  if (jurisdictionId.startsWith("state-")) return "state";
  if (jurisdictionId.startsWith("county-")) return "county";
  if (jurisdictionId.startsWith("district-")) return "district";
  if (jurisdictionId.startsWith("neighborhood-")) return "neighborhood";
  return "city";
}

export function getServers(): ServerInfo[] {
  const jurisdictions = registryData.jurisdictions as Record<
    string,
    { domain: string; display_name: string; modal_app_name: string; parent_jurisdictions?: string[]; level?: string; relay_endpoint?: string; relay_ws_endpoint?: string }
  >;

  const workspace = registryData.modal_workspace;
  const defaultRelay = (registryData as Record<string, unknown>).relay as { url: string; ws_url?: string } | undefined;
  const defaultRelayUrl = defaultRelay?.url ?? "";
  const defaultRelayWsUrl = defaultRelay?.ws_url ?? "";

  const servers: ServerInfo[] = Object.entries(jurisdictions).map(
    ([id, config]) => ({
      id,
      level: config.level || inferLevel(id),
      display_name: config.display_name,
      domain: config.domain,
      mcp_endpoint: `https://${config.domain}/mcp`,
      health_endpoint: `https://${config.domain}/health`,
      origin_health_endpoint: `https://${workspace}--${config.modal_app_name}-mcpserver-mcp-endpoint.modal.run/health`,
      parent_jurisdictions: config.parent_jurisdictions || [],
      relay_endpoint: config.relay_endpoint || defaultRelayUrl,
      relay_ws_endpoint: config.relay_ws_endpoint || defaultRelayWsUrl,
    })
  );

  servers.sort(
    (a, b) =>
      (LEVEL_ORDER[a.level] ?? 99) - (LEVEL_ORDER[b.level] ?? 99) ||
      a.display_name.localeCompare(b.display_name)
  );

  return servers;
}

export function getServerById(id: string): ServerInfo | undefined {
  return getServers().find((s) => s.id === id);
}
