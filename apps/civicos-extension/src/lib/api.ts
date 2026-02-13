/**
 * CivicOS REST API client for the browser extension.
 *
 * Fetches civic data from the Jurisdiction MCP REST endpoints.
 * Base URL is configurable via chrome.storage.local and defaults
 * to the San Rafael production endpoint.
 */

import type { CityPulseData, ToolResponse } from './types.js';

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

export async function setApiUrl(url: string): Promise<void> {
  await chrome.storage.local.set({ [STORAGE_KEY]: url });
}

export async function getApiUrl(): Promise<string> {
  return getBaseUrl();
}
