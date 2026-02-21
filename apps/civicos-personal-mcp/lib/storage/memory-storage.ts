/**
 * MemoryPersonalStorage - In-memory implementation for testing.
 *
 * Wraps existing MemoryContextStorage, MemoryStorage, MemoryPasskeyStorage.
 */

import { MemoryContextStorage } from '../providers/context-storage.js';
import { MemoryStorage as MemoryWalletStorage } from '../providers/local-wallet.js';
import { MemoryPasskeyStorage } from '../providers/passkey.js';
import type { ContextStorage } from '../providers/context-storage.js';
import type { WalletStorage } from '../providers/local-wallet.js';
import type { PasskeyStorage } from '../providers/passkey.js';
import type {
  PersonalStorage,
  UserProfile,
  UserPreferences,
  HistoryEntry,
  HistoryQueryOptions,
  StorageInfo,
} from './personal-storage.js';

export class MemoryPersonalStorage implements PersonalStorage {
  readonly context: ContextStorage;
  readonly wallet: WalletStorage;
  readonly passkey: PasskeyStorage;

  private profile: UserProfile = { interests: [] };
  private preferences: UserPreferences = { notifications: {}, display: {} };
  private jurisdictions: string[] = [];
  private history: HistoryEntry[] = [];
  private _initialized = false;

  constructor() {
    this.context = new MemoryContextStorage();
    this.wallet = new MemoryWalletStorage();
    this.passkey = new MemoryPasskeyStorage();
  }

  async initialize(): Promise<void> {
    this._initialized = true;
  }

  async getProfile(): Promise<UserProfile> {
    return { ...this.profile, interests: [...this.profile.interests] };
  }

  async saveProfile(profile: UserProfile): Promise<void> {
    this.profile = { ...profile, interests: [...profile.interests] };
  }

  async getPreferences(): Promise<UserPreferences> {
    return {
      notifications: { ...this.preferences.notifications },
      display: { ...this.preferences.display },
    };
  }

  async savePreferences(prefs: UserPreferences): Promise<void> {
    this.preferences = {
      notifications: { ...prefs.notifications },
      display: { ...prefs.display },
    };
  }

  async getJurisdictions(): Promise<string[]> {
    return [...this.jurisdictions];
  }

  async saveJurisdictions(jurisdictions: string[]): Promise<void> {
    this.jurisdictions = [...jurisdictions];
  }

  async appendHistory(entry: HistoryEntry): Promise<void> {
    this.history.push({ ...entry });
  }

  async getHistory(opts?: HistoryQueryOptions): Promise<HistoryEntry[]> {
    let results = [...this.history];

    if (opts?.jurisdiction) {
      results = results.filter((e) => e.jurisdiction === opts.jurisdiction);
    }
    if (opts?.action) {
      results = results.filter((e) => e.action === opts.action);
    }
    if (opts?.since) {
      results = results.filter((e) => e.timestamp >= opts.since!);
    }

    // Newest first
    results.sort((a, b) => b.timestamp - a.timestamp);

    if (opts?.limit) {
      results = results.slice(0, opts.limit);
    }

    return results;
  }

  async getStorageInfo(): Promise<StorageInfo> {
    return {
      type: 'memory',
      version: 1,
      initialized: this._initialized,
    };
  }
}
