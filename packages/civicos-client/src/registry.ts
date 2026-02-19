/**
 * CivicOS Registry client — jurisdiction discovery and endpoint resolution.
 *
 * Queries registry.civicosproject.org for available jurisdiction servers,
 * caches via injected StorageAdapter, and resolves MCP/relay endpoints.
 */

import type { StorageAdapter } from './interfaces.js';

const REGISTRY_API = 'https://registry.civicosproject.org/api/v1';
const CACHE_KEY = 'civicos_registry_cache';
const CACHE_TTL_MS = 24 * 60 * 60 * 1000; // 24 hours

const JURISDICTION_KEY = 'civicos_jurisdiction';
const DEFAULT_JURISDICTION = 'city-san-rafael';

const API_STORAGE_KEY = 'civicos_api_url';
const RELAY_STORAGE_KEY = 'civicos_relay_url';

const DEFAULT_API_URL = 'https://san-rafael.civicosproject.org';
const DEFAULT_RELAY_URL = 'https://san-rafael.civicosproject.org/relay';

export type JurisdictionLevel = 'federal' | 'state' | 'county' | 'city' | 'district' | 'neighborhood' | string;

export interface RegistryServer {
  jurisdiction_id: string;
  level: JurisdictionLevel;
  display_name: string;
  mcp_endpoint: string;
  health_endpoint: string;
  relay_endpoint?: string;
  relay_ws_endpoint?: string;
  parent_jurisdictions?: string[];
}

interface RegistryCache {
  servers: RegistryServer[];
  fetched_at: number;
}

export class RegistryClient {
  constructor(private storage: StorageAdapter) {}

  // === Jurisdiction management ===

  async getActiveJurisdiction(): Promise<string> {
    const stored = await this.storage.get<string>(JURISDICTION_KEY);
    return stored || DEFAULT_JURISDICTION;
  }

  async setActiveJurisdiction(jurisdictionId: string): Promise<void> {
    await this.storage.set(JURISDICTION_KEY, jurisdictionId);
  }

  async hasJurisdictionSelected(): Promise<boolean> {
    const stored = await this.storage.get<string>(JURISDICTION_KEY);
    return !!stored;
  }

  // === Server registry ===

  async getRegistryServers(forceRefresh = false): Promise<RegistryServer[]> {
    if (!forceRefresh) {
      const cached = await this.getCachedServers();
      if (cached) return cached;
    }

    try {
      const response = await fetch(`${REGISTRY_API}/servers`);
      if (!response.ok) throw new Error(`Registry ${response.status}`);
      const data = await response.json();
      const servers: RegistryServer[] = data.servers || [];

      const cache: RegistryCache = { servers, fetched_at: Date.now() };
      await this.storage.set(CACHE_KEY, cache);

      return servers;
    } catch {
      const stale = await this.getCachedServers(true);
      return stale || [];
    }
  }

  async getServerUrl(jurisdictionId: string): Promise<string | null> {
    const servers = await this.getRegistryServers();
    const server = servers.find(s => s.jurisdiction_id === jurisdictionId);
    if (!server) return null;
    // Strip /mcp path — REST API lives at the domain root (/api/tools/*)
    return server.mcp_endpoint.replace(/\/mcp\/?$/, '');
  }

  async getParentServers(jurisdictionId?: string): Promise<RegistryServer[]> {
    const id = jurisdictionId || await this.getActiveJurisdiction();
    const servers = await this.getRegistryServers();
    const server = servers.find(s => s.jurisdiction_id === id);
    if (!server?.parent_jurisdictions?.length) return [];
    return server.parent_jurisdictions
      .map(pid => servers.find(s => s.jurisdiction_id === pid))
      .filter((s): s is RegistryServer => !!s);
  }

  async getRelayEndpoint(jurisdictionId?: string): Promise<string | null> {
    const id = jurisdictionId || await this.getActiveJurisdiction();
    const servers = await this.getRegistryServers();
    const server = servers.find(s => s.jurisdiction_id === id);
    return server?.relay_endpoint || null;
  }

  getServerBaseUrl(server: RegistryServer): string {
    // Strip /mcp path — REST API lives at the domain root (/api/tools/*)
    return server.mcp_endpoint.replace(/\/mcp\/?$/, '');
  }

  // === Endpoint resolution (merged from relay-client.ts) ===

  /**
   * Get the MCP base URL for the active jurisdiction.
   * Priority: explicit override > registry lookup > default.
   */
  async getMcpUrl(): Promise<string> {
    try {
      const override = await this.storage.get<string>(API_STORAGE_KEY);
      if (override) return override;

      const jurisdiction = await this.getActiveJurisdiction();
      const url = await this.getServerUrl(jurisdiction);
      if (url) return url;

      return DEFAULT_API_URL;
    } catch {
      return DEFAULT_API_URL;
    }
  }

  /**
   * Get the relay URL for the active jurisdiction.
   * Priority: registry lookup > default.
   */
  async getRelayUrl(): Promise<string> {
    try {
      const registryUrl = await this.getRelayEndpoint();
      if (registryUrl) return registryUrl;

      return DEFAULT_RELAY_URL;
    } catch {
      return DEFAULT_RELAY_URL;
    }
  }

  /** Set a manual MCP URL override. */
  async setMcpUrl(url: string): Promise<void> {
    await this.storage.set(API_STORAGE_KEY, url);
  }

  /** Set a manual relay URL override. */
  async setRelayUrl(url: string): Promise<void> {
    await this.storage.set(RELAY_STORAGE_KEY, url);
  }

  /** Clear stale relay URL override from storage. Does not touch API URL. */
  async clearRelayUrlOverride(): Promise<void> {
    await this.storage.set(RELAY_STORAGE_KEY, null);
  }

  // === Private ===

  private async getCachedServers(ignoreExpiry = false): Promise<RegistryServer[] | null> {
    const cache = await this.storage.get<RegistryCache>(CACHE_KEY);
    if (!cache?.servers) return null;
    if (!ignoreExpiry && Date.now() - cache.fetched_at > CACHE_TTL_MS) return null;
    return cache.servers;
  }
}
