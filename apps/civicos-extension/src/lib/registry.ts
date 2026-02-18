/**
 * CivicOS Registry client — fetches available jurisdiction servers.
 *
 * Queries registry.civicosproject.org for the list of live MCP servers,
 * caches in chrome.storage.local, and provides jurisdiction lookup.
 */

const REGISTRY_API = 'https://registry.civicosproject.org/api/v1';
const CACHE_KEY = 'civicos_registry_cache';
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

export interface RegistryServer {
  jurisdiction_id: string;
  level: 'federal' | 'state' | 'county' | 'city';
  display_name: string;
  mcp_endpoint: string;
  health_endpoint: string;
  parent_jurisdictions?: string[];
}

interface RegistryCache {
  servers: RegistryServer[];
  fetched_at: number;
}

const JURISDICTION_KEY = 'civicos_jurisdiction';
const DEFAULT_JURISDICTION = 'city-san-rafael';

/** Get the stored jurisdiction ID, or null if none selected. */
export async function getActiveJurisdiction(): Promise<string> {
  try {
    const result = await chrome.storage.local.get(JURISDICTION_KEY);
    return result[JURISDICTION_KEY] || DEFAULT_JURISDICTION;
  } catch {
    return DEFAULT_JURISDICTION;
  }
}

/** Store the user's selected jurisdiction. */
export async function setActiveJurisdiction(jurisdictionId: string): Promise<void> {
  await chrome.storage.local.set({ [JURISDICTION_KEY]: jurisdictionId });
}

/** Check if a jurisdiction has been explicitly chosen (vs using default). */
export async function hasJurisdictionSelected(): Promise<boolean> {
  try {
    const result = await chrome.storage.local.get(JURISDICTION_KEY);
    return !!result[JURISDICTION_KEY];
  } catch {
    return false;
  }
}

/** Fetch server list from the registry, using cache when fresh. */
export async function getRegistryServers(forceRefresh = false): Promise<RegistryServer[]> {
  if (!forceRefresh) {
    const cached = await getCachedServers();
    if (cached) return cached;
  }

  try {
    const response = await fetch(`${REGISTRY_API}/servers`);
    if (!response.ok) throw new Error(`Registry ${response.status}`);
    const data = await response.json();
    const servers: RegistryServer[] = data.servers || [];

    // Cache the result
    const cache: RegistryCache = { servers, fetched_at: Date.now() };
    await chrome.storage.local.set({ [CACHE_KEY]: cache });

    return servers;
  } catch {
    // Fall back to cache even if stale
    const stale = await getCachedServers(true);
    return stale || [];
  }
}

/** Get the server URL for a jurisdiction from the registry. */
export async function getServerUrl(jurisdictionId: string): Promise<string | null> {
  const servers = await getRegistryServers();
  const server = servers.find(s => s.jurisdiction_id === jurisdictionId);
  if (!server) return null;
  // Derive base URL from mcp_endpoint (strip /mcp suffix)
  return server.mcp_endpoint.replace(/\/mcp$/, '');
}

/** Get parent servers for the active jurisdiction, ordered state → federal. */
export async function getParentServers(jurisdictionId?: string): Promise<RegistryServer[]> {
  const id = jurisdictionId || await getActiveJurisdiction();
  const servers = await getRegistryServers();
  const server = servers.find(s => s.jurisdiction_id === id);
  if (!server?.parent_jurisdictions?.length) return [];
  const parentIds = server.parent_jurisdictions;
  return parentIds
    .map(pid => servers.find(s => s.jurisdiction_id === pid))
    .filter((s): s is RegistryServer => !!s);
}

/** Get the base URL (without /mcp) for a specific server. */
export function getServerBaseUrl(server: RegistryServer): string {
  return server.mcp_endpoint.replace(/\/mcp$/, '');
}

async function getCachedServers(ignoreExpiry = false): Promise<RegistryServer[] | null> {
  try {
    const result = await chrome.storage.local.get(CACHE_KEY);
    const cache: RegistryCache | undefined = result[CACHE_KEY];
    if (!cache?.servers) return null;
    if (!ignoreExpiry && Date.now() - cache.fetched_at > CACHE_TTL_MS) return null;
    return cache.servers;
  } catch {
    return null;
  }
}
