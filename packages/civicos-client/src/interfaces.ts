/**
 * Platform-agnostic storage adapter for caching and preferences.
 *
 * Implementations: ChromeStorageAdapter (extension), localStorage adapter (web), etc.
 */
export interface StorageAdapter {
  get<T = unknown>(key: string): Promise<T | null>;
  set(key: string, value: unknown): Promise<void>;
  remove(key: string): Promise<void>;
}
