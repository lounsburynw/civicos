import type { StorageAdapter } from '@civicos/client';

export class ChromeStorageAdapter implements StorageAdapter {
  async get<T = unknown>(key: string): Promise<T | null> {
    try {
      const result = await chrome.storage.local.get(key);
      return (result[key] as T) ?? null;
    } catch {
      return null;
    }
  }

  async set(key: string, value: unknown): Promise<void> {
    await chrome.storage.local.set({ [key]: value });
  }

  async remove(key: string): Promise<void> {
    await chrome.storage.local.remove(key);
  }
}
