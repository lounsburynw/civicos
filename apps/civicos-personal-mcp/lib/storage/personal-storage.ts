/**
 * PersonalStorage - Unified storage interface for the Personal MCP.
 *
 * Composes existing narrow interfaces (WalletStorage, PasskeyStorage, ContextStorage)
 * with new human-readable profile/preference storage.
 *
 * Does NOT replace existing interfaces — wraps them for unified lifecycle management.
 */

import type { ContextStorage } from '../providers/context-storage.js';
import type { WalletStorage } from '../providers/local-wallet.js';
import type { PasskeyStorage } from '../providers/passkey.js';

/**
 * User profile stored in profile.md (human-editable).
 */
export interface UserProfile {
  name?: string;
  email?: string;
  neighborhood?: string;
  latitude?: number;
  longitude?: number;
  interests: string[];
}

/**
 * User preferences stored in preferences.md (human-editable).
 */
export interface UserPreferences {
  notifications: Record<string, string>;
  display: Record<string, string>;
}

/**
 * Single participation history entry.
 */
export interface HistoryEntry {
  timestamp: number;
  action: string; // e.g., 'voice', 'commitment', 'completion', 'follow', 'unfollow'
  jurisdiction: string;
  entity_id?: string;
  details?: Record<string, unknown>;
}

/**
 * Query options for history.
 */
export interface HistoryQueryOptions {
  jurisdiction?: string;
  action?: string;
  since?: number; // timestamp
  limit?: number;
}

/**
 * Storage metadata.
 */
export interface StorageInfo {
  type: 'filesystem' | 'memory';
  location?: string; // e.g., ~/.civicos
  version: number;
  initialized: boolean;
}

/**
 * Unified storage interface for the Personal MCP.
 */
export interface PersonalStorage {
  // Human-readable profile (from profile.md)
  getProfile(): Promise<UserProfile>;
  saveProfile(profile: UserProfile): Promise<void>;

  // Preferences (from preferences.md)
  getPreferences(): Promise<UserPreferences>;
  savePreferences(prefs: UserPreferences): Promise<void>;

  // Jurisdictions (from jurisdictions.md)
  getJurisdictions(): Promise<string[]>;
  saveJurisdictions(jurisdictions: string[]): Promise<void>;

  // Delegates to existing interfaces
  readonly context: ContextStorage;
  readonly wallet: WalletStorage;
  readonly passkey: PasskeyStorage;

  // Participation history (structured JSON)
  appendHistory(entry: HistoryEntry): Promise<void>;
  getHistory(opts?: HistoryQueryOptions): Promise<HistoryEntry[]>;

  // Lifecycle
  initialize(): Promise<void>;
  getStorageInfo(): Promise<StorageInfo>;
}
