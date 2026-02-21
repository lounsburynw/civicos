/**
 * Tests for FileSystemPersonalStorage.
 *
 * Uses mkdtemp to create isolated temp directories for each test.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { mkdtemp, rm, readFile, writeFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { FileSystemPersonalStorage } from '../lib/storage/filesystem-storage.js';
import { MemoryPersonalStorage } from '../lib/storage/memory-storage.js';
import type { PersonalStorage, UserProfile, UserPreferences, HistoryEntry } from '../lib/storage/personal-storage.js';

// Run the same tests for both implementations
describe.each([
  { name: 'FileSystemPersonalStorage', factory: 'filesystem' as const },
  { name: 'MemoryPersonalStorage', factory: 'memory' as const },
])('$name', ({ factory }) => {
  let storage: PersonalStorage;
  let tempDir: string;

  beforeEach(async () => {
    if (factory === 'filesystem') {
      tempDir = await mkdtemp(join(tmpdir(), 'civicos-test-'));
      storage = new FileSystemPersonalStorage(tempDir);
    } else {
      storage = new MemoryPersonalStorage();
    }
    await storage.initialize();
  });

  afterEach(async () => {
    if (factory === 'filesystem' && tempDir) {
      await rm(tempDir, { recursive: true, force: true });
    }
  });

  describe('initialize', () => {
    it('creates storage structure', async () => {
      const info = await storage.getStorageInfo();
      expect(info.type).toBe(factory);
      expect(info.version).toBe(1);
      expect(info.initialized).toBe(true);
    });
  });

  describe('profile', () => {
    it('returns empty profile by default', async () => {
      const profile = await storage.getProfile();
      expect(profile.interests).toEqual([]);
      expect(profile.name).toBeUndefined();
    });

    it('saves and loads profile', async () => {
      const profile: UserProfile = {
        name: 'Alice',
        email: 'alice@example.com',
        neighborhood: 'Terra Linda',
        latitude: 37.9735,
        longitude: -122.5311,
        interests: ['Housing', 'Transportation', 'Parks and recreation'],
      };

      await storage.saveProfile(profile);
      const loaded = await storage.getProfile();

      expect(loaded.name).toBe('Alice');
      expect(loaded.email).toBe('alice@example.com');
      expect(loaded.neighborhood).toBe('Terra Linda');
      expect(loaded.latitude).toBe(37.9735);
      expect(loaded.longitude).toBe(-122.5311);
      expect(loaded.interests).toEqual(['Housing', 'Transportation', 'Parks and recreation']);
    });

    it('overwrites existing profile', async () => {
      await storage.saveProfile({ name: 'Alice', interests: ['Housing'] });
      await storage.saveProfile({ name: 'Bob', interests: ['Transit'] });

      const loaded = await storage.getProfile();
      expect(loaded.name).toBe('Bob');
      expect(loaded.interests).toEqual(['Transit']);
    });
  });

  describe('preferences', () => {
    it('returns empty preferences by default', async () => {
      const prefs = await storage.getPreferences();
      expect(prefs.notifications).toEqual({});
      expect(prefs.display).toEqual({});
    });

    it('saves and loads preferences', async () => {
      const prefs: UserPreferences = {
        notifications: { 'Email Digest': 'weekly', 'Meeting Reminders': 'true' },
        display: { Theme: 'system', Language: 'en' },
      };

      await storage.savePreferences(prefs);
      const loaded = await storage.getPreferences();

      expect(loaded.notifications).toEqual(prefs.notifications);
      expect(loaded.display).toEqual(prefs.display);
    });
  });

  describe('jurisdictions', () => {
    it('returns empty list by default', async () => {
      const jurisdictions = await storage.getJurisdictions();
      expect(jurisdictions).toEqual([]);
    });

    it('saves and loads jurisdictions', async () => {
      const jurisdictions = ['city-san-rafael', 'county-marin', 'state-california'];
      await storage.saveJurisdictions(jurisdictions);
      const loaded = await storage.getJurisdictions();
      expect(loaded).toEqual(jurisdictions);
    });

    it('preserves order', async () => {
      await storage.saveJurisdictions(['state-california', 'city-san-rafael']);
      const loaded = await storage.getJurisdictions();
      expect(loaded).toEqual(['state-california', 'city-san-rafael']);
    });
  });

  describe('context (delegate)', () => {
    it('saves and loads per-jurisdiction context', async () => {
      const ctx = {
        version: 1 as const,
        jurisdiction: 'city-san-rafael',
        interests: ['housing'],
        following_items: [],
        created_at: Date.now(),
        updated_at: Date.now(),
      };

      await storage.context.save('city-san-rafael', ctx);
      const loaded = await storage.context.load('city-san-rafael');
      expect(loaded?.jurisdiction).toBe('city-san-rafael');
      expect(loaded?.interests).toEqual(['housing']);
    });

    it('returns null for missing jurisdiction', async () => {
      const loaded = await storage.context.load('nonexistent');
      expect(loaded).toBeNull();
    });

    it('lists jurisdictions with context', async () => {
      const ctx1 = {
        version: 1 as const,
        jurisdiction: 'city-san-rafael',
        interests: [],
        following_items: [],
        created_at: Date.now(),
        updated_at: Date.now(),
      };
      const ctx2 = { ...ctx1, jurisdiction: 'county-marin' };

      await storage.context.save('city-san-rafael', ctx1);
      await storage.context.save('county-marin', ctx2);

      const list = await storage.context.list();
      expect(list.sort()).toEqual(['city-san-rafael', 'county-marin']);
    });

    it('deletes jurisdiction context', async () => {
      const ctx = {
        version: 1 as const,
        jurisdiction: 'city-san-rafael',
        interests: [],
        following_items: [],
        created_at: Date.now(),
        updated_at: Date.now(),
      };

      await storage.context.save('city-san-rafael', ctx);
      await storage.context.delete('city-san-rafael');
      const loaded = await storage.context.load('city-san-rafael');
      expect(loaded).toBeNull();
    });
  });

  describe('wallet (delegate)', () => {
    it('returns null when no wallet exists', async () => {
      const loaded = await storage.wallet.load();
      expect(loaded).toBeNull();
    });

    it('saves and loads wallet data', async () => {
      const wallet = {
        version: 1,
        salt: 'abc123',
        iv: 'def456',
        encryptedKey: 'encrypted-data',
        publicKey: 'pub-key-hex',
        createdAt: Date.now(),
      };

      await storage.wallet.save(wallet as any);
      const loaded = await storage.wallet.load();
      expect(loaded).not.toBeNull();
      expect(loaded!.publicKey).toBe('pub-key-hex');
    });

    it('deletes wallet data', async () => {
      const wallet = {
        version: 1,
        salt: 'abc123',
        iv: 'def456',
        encryptedKey: 'encrypted-data',
        publicKey: 'pub-key-hex',
        createdAt: Date.now(),
      };

      await storage.wallet.save(wallet as any);
      await storage.wallet.delete();
      const loaded = await storage.wallet.load();
      expect(loaded).toBeNull();
    });
  });

  describe('passkey (delegate)', () => {
    it('returns null when no passkey exists', async () => {
      const loaded = await storage.passkey.load();
      expect(loaded).toBeNull();
    });

    it('saves and loads passkey data', async () => {
      const passkey = {
        version: 1,
        credentialId: 'cred-id',
        email: 'alice@example.com',
        publicKey: 'pub-key-hex',
        createdAt: Date.now(),
      };

      await storage.passkey.save(passkey as any);
      const loaded = await storage.passkey.load();
      expect(loaded).not.toBeNull();
      expect(loaded!.email).toBe('alice@example.com');
    });
  });

  describe('history', () => {
    it('returns empty history by default', async () => {
      const history = await storage.getHistory();
      expect(history).toEqual([]);
    });

    it('appends and retrieves history entries', async () => {
      const entry1: HistoryEntry = {
        timestamp: 1000,
        action: 'voice',
        jurisdiction: 'city-san-rafael',
        entity_id: 'decision-1',
      };
      const entry2: HistoryEntry = {
        timestamp: 2000,
        action: 'follow',
        jurisdiction: 'city-san-rafael',
        entity_id: 'meeting-1',
      };

      await storage.appendHistory(entry1);
      await storage.appendHistory(entry2);

      const history = await storage.getHistory();
      expect(history).toHaveLength(2);
      // Newest first
      expect(history[0].timestamp).toBe(2000);
      expect(history[1].timestamp).toBe(1000);
    });

    it('filters by jurisdiction', async () => {
      await storage.appendHistory({
        timestamp: 1000,
        action: 'voice',
        jurisdiction: 'city-san-rafael',
      });
      await storage.appendHistory({
        timestamp: 2000,
        action: 'voice',
        jurisdiction: 'county-marin',
      });

      const results = await storage.getHistory({ jurisdiction: 'city-san-rafael' });
      expect(results).toHaveLength(1);
      expect(results[0].jurisdiction).toBe('city-san-rafael');
    });

    it('filters by action type', async () => {
      await storage.appendHistory({
        timestamp: 1000,
        action: 'voice',
        jurisdiction: 'city-san-rafael',
      });
      await storage.appendHistory({
        timestamp: 2000,
        action: 'follow',
        jurisdiction: 'city-san-rafael',
      });

      const results = await storage.getHistory({ action: 'follow' });
      expect(results).toHaveLength(1);
      expect(results[0].action).toBe('follow');
    });

    it('filters by since timestamp', async () => {
      await storage.appendHistory({
        timestamp: 1000,
        action: 'voice',
        jurisdiction: 'city-san-rafael',
      });
      await storage.appendHistory({
        timestamp: 3000,
        action: 'voice',
        jurisdiction: 'city-san-rafael',
      });

      const results = await storage.getHistory({ since: 2000 });
      expect(results).toHaveLength(1);
      expect(results[0].timestamp).toBe(3000);
    });

    it('respects limit', async () => {
      for (let i = 0; i < 5; i++) {
        await storage.appendHistory({
          timestamp: i * 1000,
          action: 'voice',
          jurisdiction: 'city-san-rafael',
        });
      }

      const results = await storage.getHistory({ limit: 2 });
      expect(results).toHaveLength(2);
    });
  });
});

// Filesystem-specific tests
describe('FileSystemPersonalStorage (filesystem-specific)', () => {
  let storage: FileSystemPersonalStorage;
  let tempDir: string;

  beforeEach(async () => {
    tempDir = await mkdtemp(join(tmpdir(), 'civicos-fs-test-'));
    storage = new FileSystemPersonalStorage(tempDir);
    await storage.initialize();
  });

  afterEach(async () => {
    await rm(tempDir, { recursive: true, force: true });
  });

  it('creates .version file on initialize', async () => {
    const version = await readFile(join(tempDir, '.version'), 'utf-8');
    expect(version.trim()).toBe('1');
  });

  it('profile.md is human-readable', async () => {
    await storage.saveProfile({
      name: 'Alice',
      email: 'alice@example.com',
      neighborhood: 'Terra Linda',
      interests: ['Housing', 'Transportation'],
    });

    const content = await readFile(join(tempDir, 'profile.md'), 'utf-8');
    expect(content).toContain('# My Civic Profile');
    expect(content).toContain('## Identity');
    expect(content).toContain('- Name: Alice');
    expect(content).toContain('## Interests');
    expect(content).toContain('- Housing');
    expect(content).toContain('- Transportation');
  });

  it('reads manually-edited profile.md', async () => {
    // Simulate user editing the file
    const manualContent = `# My Civic Profile

## Identity
- Name: Bob
- Email: bob@example.com

## Location
- Neighborhood: Downtown
- Latitude: 37.9740

## Interests
- Parks
- Budget
- Public safety

Some user comment that should be ignored.
`;
    await writeFile(join(tempDir, 'profile.md'), manualContent, 'utf-8');

    const profile = await storage.getProfile();
    expect(profile.name).toBe('Bob');
    expect(profile.email).toBe('bob@example.com');
    expect(profile.neighborhood).toBe('Downtown');
    expect(profile.latitude).toBe(37.974);
    expect(profile.interests).toEqual(['Parks', 'Budget', 'Public safety']);
  });

  it('preferences.md is human-readable', async () => {
    await storage.savePreferences({
      notifications: { 'Email Digest': 'weekly' },
      display: { Theme: 'dark' },
    });

    const content = await readFile(join(tempDir, 'preferences.md'), 'utf-8');
    expect(content).toContain('# Preferences');
    expect(content).toContain('## Notifications');
    expect(content).toContain('- Email Digest: weekly');
    expect(content).toContain('## Display');
    expect(content).toContain('- Theme: dark');
  });

  it('jurisdictions.md is human-readable', async () => {
    await storage.saveJurisdictions(['city-san-rafael', 'county-marin']);

    const content = await readFile(join(tempDir, 'jurisdictions.md'), 'utf-8');
    expect(content).toContain('# My Jurisdictions');
    expect(content).toContain('1. city-san-rafael');
    expect(content).toContain('2. county-marin');
  });

  it('reads manually-edited jurisdictions.md', async () => {
    const manualContent = `# My Jurisdictions

Here are my jurisdictions, in priority order:

1. county-marin
2. city-san-rafael
3. state-california
`;
    await writeFile(join(tempDir, 'jurisdictions.md'), manualContent, 'utf-8');

    const jurisdictions = await storage.getJurisdictions();
    expect(jurisdictions).toEqual(['county-marin', 'city-san-rafael', 'state-california']);
  });

  it('context files are per-jurisdiction JSON', async () => {
    const ctx = {
      version: 1 as const,
      jurisdiction: 'city-san-rafael',
      interests: ['housing'],
      following_items: [],
      created_at: Date.now(),
      updated_at: Date.now(),
    };

    await storage.context.save('city-san-rafael', ctx);
    const content = await readFile(join(tempDir, 'context', 'city-san-rafael.json'), 'utf-8');
    const parsed = JSON.parse(content);
    expect(parsed.jurisdiction).toBe('city-san-rafael');
  });

  it('getStorageInfo returns filesystem location', async () => {
    const info = await storage.getStorageInfo();
    expect(info.type).toBe('filesystem');
    expect(info.location).toBe(tempDir);
    expect(info.version).toBe(1);
  });
});
