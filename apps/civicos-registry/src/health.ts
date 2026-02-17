import { getServers, type ServerInfo } from "./registry";

export interface ServerHealth {
  status: "healthy" | "unhealthy" | "unknown";
  tools_count: number | null;
  tools: string[];
  display_name: string | null;
  response_time_ms: number | null;
  checked_at: string;
}

export type HealthMap = Record<string, ServerHealth>;

const CACHE_KEY = "https://registry.civicosproject.org/_internal/health-cache";
const CACHE_TTL = 60; // seconds

async function checkServerHealth(server: ServerInfo): Promise<ServerHealth> {
  const start = Date.now();
  try {
    const response = await fetch(server.origin_health_endpoint, {
      signal: AbortSignal.timeout(5000),
    });
    const elapsed = Date.now() - start;

    if (response.ok) {
      const data = (await response.json()) as Record<string, unknown>;
      return {
        status: "healthy",
        tools_count: (data.tools_count as number) ?? null,
        tools: (data.tools as string[]) ?? [],
        display_name: (data.display_name as string) ?? null,
        response_time_ms: elapsed,
        checked_at: new Date().toISOString(),
      };
    }
    return {
      status: "unhealthy",
      tools_count: null,
      tools: [],
      display_name: null,
      response_time_ms: elapsed,
      checked_at: new Date().toISOString(),
    };
  } catch {
    return {
      status: "unknown",
      tools_count: null,
      tools: [],
      display_name: null,
      response_time_ms: null,
      checked_at: new Date().toISOString(),
    };
  }
}

async function fetchAllHealth(): Promise<HealthMap> {
  const servers = getServers();
  const results = await Promise.all(servers.map(checkServerHealth));

  const healthMap: HealthMap = {};
  servers.forEach((server, i) => {
    healthMap[server.id] = results[i];
  });
  return healthMap;
}

export async function getHealthData(): Promise<HealthMap> {
  // Try Cache API (works in production, may not in local dev)
  try {
    const cache = caches.default;
    const cacheRequest = new Request(CACHE_KEY);

    const cached = await cache.match(cacheRequest);
    if (cached) {
      return (await cached.json()) as HealthMap;
    }

    const healthMap = await fetchAllHealth();

    const cacheResponse = new Response(JSON.stringify(healthMap), {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": `s-maxage=${CACHE_TTL}`,
      },
    });
    cache.put(cacheRequest, cacheResponse);

    return healthMap;
  } catch {
    // Cache API unavailable — fetch directly
    return fetchAllHealth();
  }
}
