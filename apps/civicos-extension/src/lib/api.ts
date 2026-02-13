/**
 * CivicOS REST API client for the browser extension.
 *
 * Fetches civic data from the Jurisdiction MCP REST endpoints.
 * Base URL is configurable via chrome.storage.local and defaults
 * to the San Rafael production endpoint.
 */

import type { CityPulseData, DecisionDetailData, DataProvenance, VoiceCounts, ToolResponse } from './types.js';

const DEFAULT_API_URL = 'https://san-rafael.civicosproject.org';
const STORAGE_KEY = 'civicos_api_url';

async function getBaseUrl(): Promise<string> {
  try {
    const result = await chrome.storage.local.get(STORAGE_KEY);
    return result[STORAGE_KEY] || DEFAULT_API_URL;
  } catch {
    return DEFAULT_API_URL;
  }
}

async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const baseUrl = await getBaseUrl();
  const url = `${baseUrl}${path}`;

  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`API error ${response.status}: ${response.statusText}`);
  }

  const result: ToolResponse<T> = await response.json();
  if (!result.success) {
    throw new Error(result.error || 'API returned an error');
  }
  return result.data;
}

export async function getCityPulse(daysAhead = 14, daysBack = 30): Promise<CityPulseData> {
  return apiRequest<CityPulseData>('/api/tools/city-pulse', {
    method: 'POST',
    body: JSON.stringify({ days_ahead: daysAhead, days_back: daysBack }),
  });
}

export async function getDecisionDetail(title: string): Promise<DecisionDetailData> {
  return apiRequest<DecisionDetailData>('/api/tools/decision-detail', {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export async function getDataProvenance(): Promise<DataProvenance> {
  return apiRequest<DataProvenance>('/api/tools/data-provenance');
}

export async function getVoiceCountsBatch(entityIds: string[]): Promise<Map<string, VoiceCounts>> {
  const result = new Map<string, VoiceCounts>();
  if (entityIds.length === 0) return result;

  try {
    const baseUrl = await getBaseUrl();
    // Fetch counts for each entity individually (relay has per-entity endpoint)
    const promises = entityIds.map(async (id) => {
      try {
        const url = `${baseUrl}/api/tools/voice-counts?entity_id=${encodeURIComponent(id)}`;
        const response = await fetch(url, {
          headers: { 'Content-Type': 'application/json' },
        });
        if (response.ok) {
          const data: ToolResponse<VoiceCounts> = await response.json();
          if (data.success && data.data) {
            result.set(id, data.data);
          }
        }
      } catch {
        // Silently skip unavailable voice counts
      }
    });
    await Promise.all(promises);
  } catch {
    // Voice counts are optional — return empty map
  }
  return result;
}

// === Relay API (coordination/voice endpoints) ===

const DEFAULT_RELAY_URL = 'https://api.civicosproject.org';
const RELAY_STORAGE_KEY = 'civicos_relay_url';

async function getRelayUrl(): Promise<string> {
  try {
    const result = await chrome.storage.local.get(RELAY_STORAGE_KEY);
    return result[RELAY_STORAGE_KEY] || DEFAULT_RELAY_URL;
  } catch {
    return DEFAULT_RELAY_URL;
  }
}

export async function submitVoice(
  entityId: string,
  stance: 'support' | 'oppose' | 'watching',
  jurisdiction: string,
  publicKey: string,
  signature: string,
  createdAt: number
): Promise<boolean> {
  try {
    const relayUrl = await getRelayUrl();
    const response = await fetch(`${relayUrl}/coordination/voice`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entity: entityId,
        stance,
        public_key: publicKey,
        signature,
        created_at: createdAt,
        jurisdiction,
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function revokeVoice(
  entityId: string,
  publicKey: string,
  signature: string,
  createdAt: number
): Promise<boolean> {
  try {
    const relayUrl = await getRelayUrl();
    const response = await fetch(`${relayUrl}/coordination/voice/revoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        entity: entityId,
        public_key: publicKey,
        signature,
        created_at: createdAt,
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function setApiUrl(url: string): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEY]: url });
}

export async function getApiUrl(): Promise<string> {
  return getBaseUrl();
}
