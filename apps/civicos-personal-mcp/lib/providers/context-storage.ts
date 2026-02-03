/**
 * Context Storage - User context personalization persistence.
 *
 * Stores civic context preferences locally:
 * - Neighborhood/location
 * - Interest topics
 * - Followed items (decisions, meetings, issues)
 *
 * Privacy model: All data stored client-side only.
 * Never transmitted to server without explicit user action.
 */

/**
 * Entity type for following items.
 */
export type FollowableEntityType = 'decision' | 'meeting' | 'issue' | 'topic';

/**
 * Item being followed by the user.
 */
export interface FollowingItem {
  entity_type: FollowableEntityType;
  entity_id: string;
  label?: string; // Human-readable label
  followed_at: number; // Timestamp
}

/**
 * User's neighborhood location.
 */
export interface UserNeighborhood {
  neighborhood: string; // e.g., 'Terra Linda'
  lat?: number;
  lng?: number;
}

/**
 * Stored user context (persisted to storage).
 */
export interface StoredUserContext {
  version: 1;
  jurisdiction: string;
  neighborhood?: UserNeighborhood;
  interests: string[];
  following_items: FollowingItem[];
  created_at: number;
  updated_at: number;
}

// Storage key pattern: civicos-context:{jurisdiction}
const STORAGE_KEY_PREFIX = 'civicos-context';

/**
 * Get storage key for a jurisdiction.
 */
function getStorageKey(jurisdiction: string): string {
  return `${STORAGE_KEY_PREFIX}:${jurisdiction}`;
}

/**
 * Create default empty context for a jurisdiction.
 */
export function createDefaultContext(jurisdiction: string): StoredUserContext {
  const now = Date.now();
  return {
    version: 1,
    jurisdiction,
    interests: [],
    following_items: [],
    created_at: now,
    updated_at: now,
  };
}

/**
 * Storage interface for user context.
 * Allows different implementations for browser vs testing.
 */
export interface ContextStorage {
  save(jurisdiction: string, context: StoredUserContext): Promise<void>;
  load(jurisdiction: string): Promise<StoredUserContext | null>;
  delete(jurisdiction: string): Promise<void>;
  list(): Promise<string[]>; // List all jurisdictions with saved context
}

/**
 * LocalStorage implementation for browsers.
 */
export class LocalStorageContextStorage implements ContextStorage {
  async save(jurisdiction: string, context: StoredUserContext): Promise<void> {
    const key = getStorageKey(jurisdiction);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(key, JSON.stringify(context));
    }
  }

  async load(jurisdiction: string): Promise<StoredUserContext | null> {
    if (typeof localStorage === 'undefined') {
      return null;
    }
    const key = getStorageKey(jurisdiction);
    const data = localStorage.getItem(key);
    if (!data) return null;
    try {
      return JSON.parse(data) as StoredUserContext;
    } catch {
      return null;
    }
  }

  async delete(jurisdiction: string): Promise<void> {
    if (typeof localStorage !== 'undefined') {
      const key = getStorageKey(jurisdiction);
      localStorage.removeItem(key);
    }
  }

  async list(): Promise<string[]> {
    if (typeof localStorage === 'undefined') {
      return [];
    }
    const jurisdictions: string[] = [];
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (key?.startsWith(STORAGE_KEY_PREFIX + ':')) {
        jurisdictions.push(key.slice(STORAGE_KEY_PREFIX.length + 1));
      }
    }
    return jurisdictions;
  }
}

/**
 * In-memory storage for testing.
 */
export class MemoryContextStorage implements ContextStorage {
  private contexts: Map<string, StoredUserContext> = new Map();

  async save(jurisdiction: string, context: StoredUserContext): Promise<void> {
    this.contexts.set(jurisdiction, context);
  }

  async load(jurisdiction: string): Promise<StoredUserContext | null> {
    return this.contexts.get(jurisdiction) ?? null;
  }

  async delete(jurisdiction: string): Promise<void> {
    this.contexts.delete(jurisdiction);
  }

  async list(): Promise<string[]> {
    return Array.from(this.contexts.keys());
  }

  // Test helper to clear all contexts
  clear(): void {
    this.contexts.clear();
  }
}
