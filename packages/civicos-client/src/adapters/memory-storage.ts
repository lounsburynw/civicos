import type { StorageAdapter } from '../interfaces.js';

/**
 * In-memory StorageAdapter for non-browser contexts (Node scripts, tests, SSR).
 * Data does not persist across restarts.
 */
export class MemoryStorageAdapter implements StorageAdapter {
  private store = new Map<string, unknown>();

  async get<T = unknown>(key: string): Promise<T | null> {
    return (this.store.get(key) as T) ?? null;
  }

  async set(key: string, value: unknown): Promise<void> {
    this.store.set(key, value);
  }

  async remove(key: string): Promise<void> {
    this.store.delete(key);
  }
}
