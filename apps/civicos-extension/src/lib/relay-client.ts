/**
 * Pure-TS relay client for service worker context.
 *
 * This module has zero Svelte/DOM dependencies so it can be imported
 * by the service worker without pulling in shared chunks that reference `window`.
 */

const DEFAULT_RELAY_URL = 'https://civicos--civicos-relay-relayserver-relay-endpoint.modal.run';
const RELAY_STORAGE_KEY = 'civicos_relay_url';

const DEFAULT_API_URL = 'https://san-rafael.civicosproject.org';
const API_STORAGE_KEY = 'civicos_api_url';

export async function getRelayUrl(): Promise<string> {
  try {
    const result = await chrome.storage.local.get(RELAY_STORAGE_KEY);
    return result[RELAY_STORAGE_KEY] || DEFAULT_RELAY_URL;
  } catch {
    return DEFAULT_RELAY_URL;
  }
}

/**
 * Get the base URL for the active jurisdiction's MCP server.
 * Priority: explicit override (civicos_api_url) > registry lookup > default.
 */
export async function getBaseUrl(): Promise<string> {
  try {
    // 1. Explicit override (set by Options page or legacy)
    const result = await chrome.storage.local.get(API_STORAGE_KEY);
    if (result[API_STORAGE_KEY]) return result[API_STORAGE_KEY];

    // 2. Registry-based lookup from stored jurisdiction
    const { getServerUrl, getActiveJurisdiction } = await import('./registry.js');
    const jurisdiction = await getActiveJurisdiction();
    const url = await getServerUrl(jurisdiction);
    if (url) return url;

    // 3. Fallback
    return DEFAULT_API_URL;
  } catch {
    return DEFAULT_API_URL;
  }
}

export async function redeemAttestationCode(
  code: string,
  publicKey: string,
  signature: string,
  createdAt: number
): Promise<{ success: boolean; attestation_event?: Record<string, unknown>; error?: string }> {
  try {
    const relayUrl = await getRelayUrl();
    const response = await fetch(`${relayUrl}/coordination/attest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code,
        public_key: publicKey,
        signature,
        created_at: createdAt,
      }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({ detail: response.statusText }));
      return { success: false, error: data.detail || `Error ${response.status}` };
    }
    return response.json();
  } catch (err) {
    return { success: false, error: err instanceof Error ? err.message : 'Network error' };
  }
}
