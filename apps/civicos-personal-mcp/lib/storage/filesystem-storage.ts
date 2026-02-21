/**
 * FileSystemPersonalStorage - File-based storage for Node.js environments.
 *
 * Directory layout (~/.civicos/):
 * ├── profile.md              # name, neighborhood, interests (human-editable)
 * ├── preferences.md          # notification/display prefs (human-editable)
 * ├── jurisdictions.md        # ordered jurisdiction list (human-editable)
 * ├── context/                # per-jurisdiction context JSON (programmatic)
 * │   └── city-san-rafael.json
 * ├── identity/               # encrypted keys (0o700 dir, 0o600 files)
 * │   ├── wallet.json         # EncryptedWallet (AES-256-GCM)
 * │   └── passkey.json        # StoredPasskeyIdentity
 * ├── history.json            # participation log (append-only JSON array)
 * └── .version                # storage format version (currently: 1)
 *
 * Uses only node:fs/promises, node:path, node:os. No external dependencies.
 */

import { readFile, writeFile, mkdir, readdir, unlink, access, constants } from 'node:fs/promises';
import { join } from 'node:path';
import { homedir } from 'node:os';

import type { ContextStorage, StoredUserContext } from '../providers/context-storage.js';
import type { WalletStorage } from '../providers/local-wallet.js';
import type { PasskeyStorage } from '../providers/passkey.js';
import { parseMarkdown, renderMarkdown, parseOrderedList, renderOrderedList } from './markdown-parser.js';
import type {
  PersonalStorage,
  UserProfile,
  UserPreferences,
  HistoryEntry,
  HistoryQueryOptions,
  StorageInfo,
} from './personal-storage.js';

const CURRENT_VERSION = 1;

/**
 * Default base directory for CivicOS personal data.
 */
export function getDefaultBaseDir(): string {
  return process.env.CIVICOS_DATA_DIR ?? join(homedir(), '.civicos');
}

// ============================================================
// Inner storage classes implementing existing narrow interfaces
// ============================================================

/**
 * File-based ContextStorage — one JSON file per jurisdiction.
 */
export class FileSystemContextStorage implements ContextStorage {
  private dir: string;

  constructor(baseDir: string) {
    this.dir = join(baseDir, 'context');
  }

  async save(jurisdiction: string, context: StoredUserContext): Promise<void> {
    await mkdir(this.dir, { recursive: true });
    const filePath = join(this.dir, `${jurisdiction}.json`);
    await writeFile(filePath, JSON.stringify(context, null, 2), 'utf-8');
  }

  async load(jurisdiction: string): Promise<StoredUserContext | null> {
    try {
      const filePath = join(this.dir, `${jurisdiction}.json`);
      const data = await readFile(filePath, 'utf-8');
      return JSON.parse(data) as StoredUserContext;
    } catch {
      return null;
    }
  }

  async delete(jurisdiction: string): Promise<void> {
    try {
      const filePath = join(this.dir, `${jurisdiction}.json`);
      await unlink(filePath);
    } catch {
      // File doesn't exist — that's fine
    }
  }

  async list(): Promise<string[]> {
    try {
      const files = await readdir(this.dir);
      return files
        .filter((f) => f.endsWith('.json'))
        .map((f) => f.replace('.json', ''));
    } catch {
      return [];
    }
  }
}

/**
 * File-based WalletStorage — single JSON file with restricted permissions.
 */
export class FileSystemWalletStorage implements WalletStorage {
  private dir: string;
  private filePath: string;

  constructor(identityDir: string) {
    this.dir = identityDir;
    this.filePath = join(identityDir, 'wallet.json');
  }

  async save(wallet: unknown): Promise<void> {
    await mkdir(this.dir, { recursive: true, mode: 0o700 });
    await writeFile(this.filePath, JSON.stringify(wallet, null, 2), { encoding: 'utf-8', mode: 0o600 });
  }

  async load(): Promise<any | null> {
    try {
      const data = await readFile(this.filePath, 'utf-8');
      return JSON.parse(data);
    } catch {
      return null;
    }
  }

  async delete(): Promise<void> {
    try {
      await unlink(this.filePath);
    } catch {
      // File doesn't exist — that's fine
    }
  }
}

/**
 * File-based PasskeyStorage — single JSON file with restricted permissions.
 */
export class FileSystemPasskeyStorage implements PasskeyStorage {
  private dir: string;
  private filePath: string;

  constructor(identityDir: string) {
    this.dir = identityDir;
    this.filePath = join(identityDir, 'passkey.json');
  }

  async save(identity: unknown): Promise<void> {
    await mkdir(this.dir, { recursive: true, mode: 0o700 });
    await writeFile(this.filePath, JSON.stringify(identity, null, 2), { encoding: 'utf-8', mode: 0o600 });
  }

  async load(): Promise<any | null> {
    try {
      const data = await readFile(this.filePath, 'utf-8');
      return JSON.parse(data);
    } catch {
      return null;
    }
  }

  async delete(): Promise<void> {
    try {
      await unlink(this.filePath);
    } catch {
      // File doesn't exist — that's fine
    }
  }
}

// ============================================================
// Main FileSystemPersonalStorage
// ============================================================

export class FileSystemPersonalStorage implements PersonalStorage {
  readonly context: ContextStorage;
  readonly wallet: WalletStorage;
  readonly passkey: PasskeyStorage;

  private baseDir: string;
  private _initialized = false;

  constructor(baseDir?: string) {
    this.baseDir = baseDir ?? getDefaultBaseDir();
    const identityDir = join(this.baseDir, 'identity');
    this.context = new FileSystemContextStorage(this.baseDir);
    this.wallet = new FileSystemWalletStorage(identityDir);
    this.passkey = new FileSystemPasskeyStorage(identityDir);
  }

  async initialize(): Promise<void> {
    // Create base directory structure
    await mkdir(this.baseDir, { recursive: true });
    await mkdir(join(this.baseDir, 'context'), { recursive: true });
    await mkdir(join(this.baseDir, 'identity'), { recursive: true, mode: 0o700 });

    // Write version file if it doesn't exist
    const versionPath = join(this.baseDir, '.version');
    try {
      await access(versionPath, constants.F_OK);
    } catch {
      await writeFile(versionPath, String(CURRENT_VERSION), 'utf-8');
    }

    this._initialized = true;
  }

  // ---- Profile (profile.md) ----

  async getProfile(): Promise<UserProfile> {
    try {
      const content = await readFile(join(this.baseDir, 'profile.md'), 'utf-8');
      return this.parseProfile(content);
    } catch {
      return { interests: [] };
    }
  }

  async saveProfile(profile: UserProfile): Promise<void> {
    const content = this.renderProfile(profile);
    await writeFile(join(this.baseDir, 'profile.md'), content, 'utf-8');
  }

  private parseProfile(content: string): UserProfile {
    const parsed = parseMarkdown(content);
    const identity = parsed.sections['Identity'] ?? {};
    const location = parsed.sections['Location'] ?? {};

    // Parse interests from the Interests section — stored as key-only entries
    // In profile.md: `- Housing` (no colon) or `- Housing: ` (empty value)
    // We need a special approach: interests are list items under ## Interests
    const interests = this.parseInterestsList(content);

    const profile: UserProfile = { interests };

    if (identity['Name']) profile.name = identity['Name'];
    if (identity['Email']) profile.email = identity['Email'];
    if (location['Neighborhood']) profile.neighborhood = location['Neighborhood'];
    if (location['Latitude']) {
      const lat = parseFloat(location['Latitude']);
      if (!isNaN(lat)) profile.latitude = lat;
    }
    if (location['Longitude']) {
      const lng = parseFloat(location['Longitude']);
      if (!isNaN(lng)) profile.longitude = lng;
    }

    return profile;
  }

  private parseInterestsList(content: string): string[] {
    const interests: string[] = [];
    let inInterests = false;

    for (const rawLine of content.split('\n')) {
      const line = rawLine.trim();

      if (line.startsWith('## ')) {
        inInterests = line === '## Interests';
        continue;
      }

      if (inInterests) {
        // Match `- Interest topic` (no colon — plain list items)
        const match = line.match(/^[-*]\s+(.+)$/);
        if (match) {
          interests.push(match[1].trim());
        }
      }
    }

    return interests;
  }

  private renderProfile(profile: UserProfile): string {
    const lines: string[] = ['# My Civic Profile', ''];

    // Identity section
    lines.push('## Identity');
    if (profile.name) lines.push(`- Name: ${profile.name}`);
    if (profile.email) lines.push(`- Email: ${profile.email}`);
    lines.push('');

    // Location section
    lines.push('## Location');
    if (profile.neighborhood) lines.push(`- Neighborhood: ${profile.neighborhood}`);
    if (profile.latitude !== undefined) lines.push(`- Latitude: ${profile.latitude}`);
    if (profile.longitude !== undefined) lines.push(`- Longitude: ${profile.longitude}`);
    lines.push('');

    // Interests section (plain list, no key: value)
    lines.push('## Interests');
    for (const interest of profile.interests) {
      lines.push(`- ${interest}`);
    }
    lines.push('');

    return lines.join('\n');
  }

  // ---- Preferences (preferences.md) ----

  async getPreferences(): Promise<UserPreferences> {
    try {
      const content = await readFile(join(this.baseDir, 'preferences.md'), 'utf-8');
      return this.parsePreferences(content);
    } catch {
      return { notifications: {}, display: {} };
    }
  }

  async savePreferences(prefs: UserPreferences): Promise<void> {
    const parsed = {
      title: 'Preferences',
      sections: {
        Notifications: prefs.notifications,
        Display: prefs.display,
      },
    };
    const content = renderMarkdown(parsed);
    await writeFile(join(this.baseDir, 'preferences.md'), content, 'utf-8');
  }

  private parsePreferences(content: string): UserPreferences {
    const parsed = parseMarkdown(content);
    return {
      notifications: parsed.sections['Notifications'] ?? {},
      display: parsed.sections['Display'] ?? {},
    };
  }

  // ---- Jurisdictions (jurisdictions.md) ----

  async getJurisdictions(): Promise<string[]> {
    try {
      const content = await readFile(join(this.baseDir, 'jurisdictions.md'), 'utf-8');
      return parseOrderedList(content);
    } catch {
      return [];
    }
  }

  async saveJurisdictions(jurisdictions: string[]): Promise<void> {
    const content = renderOrderedList(
      'My Jurisdictions',
      'Ordered by priority. Edit freely — the Personal MCP reads this on each request.',
      jurisdictions
    );
    await writeFile(join(this.baseDir, 'jurisdictions.md'), content, 'utf-8');
  }

  // ---- History (history.json) ----

  async appendHistory(entry: HistoryEntry): Promise<void> {
    const history = await this.loadHistory();
    history.push(entry);
    await writeFile(
      join(this.baseDir, 'history.json'),
      JSON.stringify(history, null, 2),
      'utf-8'
    );
  }

  async getHistory(opts?: HistoryQueryOptions): Promise<HistoryEntry[]> {
    let results = await this.loadHistory();

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

  private async loadHistory(): Promise<HistoryEntry[]> {
    try {
      const data = await readFile(join(this.baseDir, 'history.json'), 'utf-8');
      return JSON.parse(data) as HistoryEntry[];
    } catch {
      return [];
    }
  }

  // ---- Storage Info ----

  async getStorageInfo(): Promise<StorageInfo> {
    let version = CURRENT_VERSION;
    try {
      const versionStr = await readFile(join(this.baseDir, '.version'), 'utf-8');
      version = parseInt(versionStr.trim(), 10) || CURRENT_VERSION;
    } catch {
      // Default version
    }

    return {
      type: 'filesystem',
      location: this.baseDir,
      version,
      initialized: this._initialized,
    };
  }
}
